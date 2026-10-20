"""Actual native prepare/finalize/fail with deterministic retrieval and full-chain PG."""
from dataclasses import replace
from datetime import datetime, UTC, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from citeframe_contracts.compaction import ContextOwner, CoverageUnit
from citeframe_contracts.memory import GenerationRequest, GenerationMessage, ModelConnectionSnapshot
from citeframe_memory.compaction.repository import CompactionRepository
from citeframe_memory.compaction.journal import CallJournal
from citeframe_memory.compaction.gate import DispatchGate
from citeframe_memory.compaction.policy import CompactionError, CompactionPolicy, CounterIdentity
from citeframe_persistence import Base
from test_compaction_fixture import pg43, seed_chat
from test_compaction_repository import adopt, summary
from test_compaction_gate import Provider, Counter, Files

QUESTION = "CURRENT QUESTION 中文😀: preserve 37.5 ms; never production; only batch=8"
STREAMING = "STREAMING_ASSISTANT_MUST_NEVER_ENTER_SHARED_CONTEXT_43"
HISTORY = "37.5 ms never production only batch=8. " * 400


@pytest.fixture
def native_chat(pg43, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "apps/api/src"))
    from ai_pdf_api.services import chat, workspace_models
    from ai_pdf_api.schemas.chat import AllReadyAssetScope
    from ai_pdf_api.services.retrieval import RetrievedContent
    from citeframe_persistence.models import Asset, AssetRepresentation, ContentUnit, EvidenceLocator, PdfLocatorDetail, ChatThread

    scope = seed_chat(pg43)
    scope = replace(scope, thread_id=scope.other_thread_id, other_thread_id=scope.thread_id)
    with Session(pg43, expire_on_commit=False) as db:
        asset = Asset(workspace_id=scope.workspace_id, created_by_user_id=scope.user_id, asset_kind="pdf",
            title="Fixture source", source_filename="fixture.pdf", object_key="unused", mime_type="application/pdf",
            byte_size=10, status="ready", current_processing_generation=1, current_index_version=1)
        db.add(asset); db.flush()
        representation = AssetRepresentation(workspace_id=scope.workspace_id, asset_id=asset.id,
            representation_kind="pdf_text_legacy", processing_generation=1, generator_version="fixture-v1")
        db.add(representation); db.flush()
        locator = EvidenceLocator(workspace_id=scope.workspace_id, asset_id=asset.id, locator_kind="pdf_page",
            locator_version=1, processing_generation_snapshot=1, representation_id_snapshot=representation.id)
        db.add(locator); db.flush()
        db.add(PdfLocatorDetail(locator_id=locator.id, page_number=1))
        content = ContentUnit(workspace_id=scope.workspace_id, asset_id=asset.id, representation_id=representation.id,
            source_locator_id=locator.id, unit_kind="pdf_text_chunk", unit_order=0,
            text_content="37.5 ms; never production; only batch=8", token_count=12, index_version=1)
        db.add(content); db.commit()
        item = RetrievedContent(content, asset, locator, "text", 0.0, (asset.id, "pdf_page:1"))
        monkeypatch.setattr(chat, "retrieve_query_content", lambda *args, **kwargs: [item])
        monkeypatch.setattr(workspace_models, "resolve_workspace_models", lambda *args: SimpleNamespace(embedding=None, generation=None))
        class Embedding:
            def embed_query(self, question): return [1.0] * 1024
        class Generation:
            provider = "fixture"
            model = "fixture"
            def generate(self, messages): raise AssertionError("No generation permitted in native preparation")
        def no_download(key): raise AssertionError("No object/network download permitted")
        def prepare(question=QUESTION, **kwargs):
            db.expire_all()
            return chat.prepare_chat(db, workspace_id=scope.workspace_id, user_id=scope.user_id,
                thread=db.get(ChatThread, scope.thread_id), question=question,
                asset_scope=AllReadyAssetScope(mode="all_ready"), embedding_provider=Embedding(),
                generation_provider=Generation(), image_bytes_loader=no_download, **kwargs)
        yield SimpleNamespace(scope=scope, db=db, chat=chat, prepare=prepare)


def prepare_scenario(native, scenario):
    if scenario == "first":
        return native.prepare(), [], None
    prior = native.prepare(HISTORY)
    native.chat.finalize_chat(native.db, prior, "First completed answer")
    selected = prior.assistant_message.id
    history = [prior.user_message.id, selected]
    active = selected
    if scenario == "older_sibling":
        sibling = native.prepare("UNSELECTED_SIBLING_BODY", use_thread_active_parent=False)
        native.chat.finalize_chat(native.db, sibling, "UNSELECTED_SIBLING_ANSWER")
        active = sibling.assistant_message.id
        current = native.prepare(parent_message_id=selected, use_thread_active_parent=False)
    elif scenario == "edited_root":
        current = native.prepare(use_thread_active_parent=False)
        history = []
    elif scenario == "failed_parent":
        failed = native.prepare("An attempt that fails")
        native.chat.fail_chat(native.db, failed, "fixture_failure", "FAILED_ANCESTOR: unresolved; never confirmed")
        active = failed.assistant_message.id
        history += [failed.user_message.id, active]
        current = native.prepare()
    else:
        current = native.prepare()
    return current, history, active


def execution(engine, native, prepared, history):
    now = datetime.now(UTC); deadline = now + timedelta(hours=1)
    with engine.begin() as db:
        db.execute(text("UPDATE chat_messages SET content=:marker WHERE id=:id"), {"marker": STREAMING, "id": prepared.assistant_message.id})
    owner = ContextOwner(native.scope.workspace_id, native.scope.user_id, "chat", str(uuid4()), "a" * 64)
    policy = dict(schemaVersion="compaction-policy-v1", maxCalls=100, maxInputTokens=100000, maxOutputTokens=10000,
        maxSummaryCalls=20, maxEpisodes=4, deadlineAt=deadline.isoformat())
    repo = CompactionRepository(lambda: Session(engine), clock=lambda: now)
    repo.create_chat(owner, thread_id=native.scope.thread_id, user_message_id=prepared.user_message.id,
        assistant_message_id=prepared.assistant_message.id, request_id=str(uuid4()), request_sha256="b" * 64,
        policy=policy, deadline_at=deadline, lease_expires_at=deadline)
    ids = history + [prepared.user_message.id]
    units = tuple(CoverageUnit(str(index), repo.register_source(owner, "chat_message", id_),
        parent_message_id=ids[index-1] if index else None) for index, id_ in enumerate(ids))
    return repo, owner, policy, units


def raw_rows(engine, thread):
    with engine.connect() as db:
        native_thread = db.scalar(text("SELECT to_jsonb(t) FROM chat_threads t WHERE id=:id"), {"id": thread})
        messages = db.execute(text("SELECT to_jsonb(m) FROM chat_messages m WHERE thread_id=:id ORDER BY id"), {"id": thread}).scalars().all()
        citations = db.execute(text("""SELECT to_jsonb(c) FROM message_citations c
            JOIN chat_messages m ON m.id=c.message_id WHERE m.thread_id=:id ORDER BY c.id"""), {"id": thread}).scalars().all()
        locators = db.execute(text("SELECT to_jsonb(l) FROM evidence_locators l WHERE workspace_id=:id ORDER BY id"), {"id": native_thread["workspace_id"]}).scalars().all()
        details = db.execute(text("""SELECT to_jsonb(d) FROM pdf_locator_details d JOIN evidence_locators l ON l.id=d.locator_id
            WHERE l.workspace_id=:id ORDER BY d.locator_id"""), {"id": native_thread["workspace_id"]}).scalars().all()
        return native_thread, messages, citations, locators, details


def make_gate(repo, units, tmp_path):
    provider = Provider(summary(units))
    connection = ModelConnectionSnapshot("openai_responses", "https://fixture.invalid", "fixture", "unused", 10, "f"*64, 25000, 2048)
    gate = DispatchGate(repo, CallJournal(repo, object_store=Files(tmp_path)), provider, Counter(), connection,
        CounterIdentity("fixture", "v1", "estimated", "f"*64), input_ceiling=22000,
        policy=CompactionPolicy(soft_ratio=.6, target_ratio=.4, min_new_tokens=1, min_gain_tokens=1))
    return gate, provider


@pytest.mark.parametrize("scenario", ["first", "later", "older_sibling", "edited_root", "failed_parent"])
def test_actual_preparation_selected_ancestry_initial_and_continuation(pg43, tmp_path, native_chat, scenario):
    prepared, history, active = prepare_scenario(native_chat, scenario)
    assert prepared.user_message.content == QUESTION
    assert prepared.user_message.status == "completed" and prepared.assistant_message.status == "streaming"
    assert prepared.assistant_message.parent_message_id == prepared.user_message.id
    repo, owner, policy, units = execution(pg43, native_chat, prepared, history)
    before = raw_rows(pg43, native_chat.scope.thread_id)
    assert before[0]["active_message_id"] == active
    assert repo.read_source(owner, units[-1].source) == QUESTION
    with pytest.raises(CompactionError):
        repo.register_source(owner, "chat_message", prepared.assistant_message.id)
    if scenario in ("older_sibling", "edited_root"):
        with pytest.raises(CompactionError, match="source_branch_mismatch"):
            repo.register_source(owner, "chat_message", active)
    gate, provider = make_gate(repo, units, tmp_path)
    template = GenerationRequest((GenerationMessage("system", "trusted"),), 2048)
    version = 0
    for mode in ("initial", "continuation"):
        permit = gate.prepare_main_dispatch(owner, template, units, policy, expected_context_version=version,
            logical_key=mode, mode=mode, recent_units=1, protected_keys=frozenset({units[-1].key}))
        request = gate.authorize_send(permit, policy)
        assert sum(message.content == QUESTION for message in request.messages) == 1
        assert request.messages[-1].role == "user" and request.messages[-1].content == QUESTION
        assert STREAMING not in repr(request)
        assert "UNSELECTED_SIBLING" not in repr(request)
        version = permit.captured.context_version
        if history:
            assert permit.checkpoint_id and version == 1
    assert raw_rows(pg43, native_chat.scope.thread_id) == before
    assert all(STREAMING not in repr(request) and "UNSELECTED_SIBLING" not in repr(request) for request in provider.calls)
    assert len(provider.calls) == (1 if history else 0)
    with pg43.connect() as db:
        assert db.scalar(text("SELECT anchor_leaf_id FROM chat_memory_executions WHERE id=:id"), {"id": owner.owner_id}) == active
        assert db.scalar(text("SELECT count(*) FROM memory_sources WHERE native_id=:id"), {"id": prepared.assistant_message.id}) == 0


@pytest.mark.parametrize("terminal", ["finalize", "fail"])
def test_actual_native_terminal_transition_preserves_checkpoint_and_stops_dispatch(pg43, tmp_path, native_chat, terminal):
    prepared, history, active = prepare_scenario(native_chat, "later")
    repo, owner, policy, units = execution(pg43, native_chat, prepared, history)
    gate, provider = make_gate(repo, units, tmp_path)
    template = GenerationRequest((GenerationMessage("system", "trusted"),), 2048)
    permit = gate.prepare_main_dispatch(owner, template, units, policy, expected_context_version=0,
        logical_key="pending", protected_keys=frozenset({units[-1].key}))
    assert permit.checkpoint_id
    with pg43.connect() as db:
        checkpoint = db.scalar(text("SELECT to_jsonb(s) FROM task_memory_snapshots s WHERE id=:id"), {"id": permit.checkpoint_id})
        coverage = db.execute(text("SELECT to_jsonb(c) FROM task_memory_coverage c ORDER BY ordinal")).scalars().all()
    evidence_before = raw_rows(pg43, native_chat.scope.thread_id)[2:]
    current_citations = [row for row in evidence_before[0] if row["message_id"] == prepared.assistant_message.id]
    assert len(current_citations) == 1
    current_locators = {row["evidence_locator_id"] for row in current_citations}
    assert current_locators <= {row["id"] for row in evidence_before[1]}
    assert current_locators <= {row["locator_id"] for row in evidence_before[2]}
    if terminal == "finalize":
        native_chat.chat.finalize_chat(native_chat.db, prepared, "Final native answer")
    else:
        native_chat.chat.fail_chat(native_chat.db, prepared, "fixture_failure", "Native generation failed")
    evidence_after = raw_rows(pg43, native_chat.scope.thread_id)[2:]
    if terminal == "finalize":
        assert evidence_after == evidence_before
    else:
        assert evidence_after == (
            [row for row in evidence_before[0] if row["message_id"] != prepared.assistant_message.id],
            [row for row in evidence_before[1] if row["id"] not in current_locators],
            [row for row in evidence_before[2] if row["locator_id"] not in current_locators],
        )
    for action in (lambda: repo.capture(owner, units, policy), lambda: gate.authorize_send(permit, policy),
                   lambda: repo.read_source(owner, units[-1].source)):
        with pytest.raises(CompactionError): action()
    with pg43.connect() as db:
        assert db.scalar(text("SELECT active_message_id FROM chat_threads WHERE id=:id"), {"id": native_chat.scope.thread_id}) == prepared.assistant_message.id
        assert db.scalar(text("SELECT status FROM chat_messages WHERE id=:id"), {"id": prepared.assistant_message.id}) == ("completed" if terminal == "finalize" else "failed")
        assert db.scalar(text("SELECT to_jsonb(s) FROM task_memory_snapshots s WHERE id=:id"), {"id": permit.checkpoint_id}) == checkpoint
        assert db.execute(text("SELECT to_jsonb(c) FROM task_memory_coverage c ORDER BY ordinal")).scalars().all() == coverage
        assert db.execute(text("SELECT anchor_leaf_id,checkpoint_id,context_version FROM chat_memory_executions WHERE id=:id"), {"id": owner.owner_id}).one() == (active, permit.checkpoint_id, 1)
        assert db.scalar(text("SELECT count(*) FROM memory_calls WHERE purpose='main' AND state='sent'")) == 0


@pytest.mark.parametrize("fault", [None, "snapshot", "coverage", "uses", "pointer", "before_commit"])
def test_actual_first_turn_null_anchor_atomic_snapshot(pg43, native_chat, fault):
    prepared, history, active = prepare_scenario(native_chat, "first")
    repo, owner, policy, units = execution(pg43, native_chat, prepared, history)
    before = raw_rows(pg43, native_chat.scope.thread_id)
    captured = repo.capture(owner, units, policy)
    if fault:
        def fail(stage):
            if stage == fault: raise RuntimeError("injected_atomic_failure")
        repo.fault = fail
        with pytest.raises(RuntimeError, match="injected_atomic_failure"):
            adopt(repo, captured, policy)
    else:
        receipt = adopt(repo, captured, policy)
    with pg43.connect() as db:
        assert db.scalar(text("SELECT anchor_leaf_id FROM chat_memory_executions WHERE id=:id"), {"id": owner.owner_id}) is None
        assert db.scalar(text("SELECT count(*) FROM task_memory_snapshots")) == (0 if fault else 1)
        assert db.scalar(text("SELECT count(*) FROM task_memory_coverage")) == (0 if fault else 1)
        assert db.scalar(text("SELECT count(*) FROM memory_uses WHERE consumer_snapshot_id IS NOT NULL")) == (0 if fault else 1)
        pointer = db.execute(text("SELECT context_version,checkpoint_id FROM chat_memory_executions WHERE id=:id"), {"id": owner.owner_id}).one()
        assert pointer == ((0, None) if fault else (1, receipt.snapshot_id))
        if not fault:
            assert db.scalar(text("SELECT anchor_leaf_id FROM task_memory_snapshots")) is None
            assert db.execute(text("SELECT ordinal,source_id FROM task_memory_coverage")).one() == (0, units[0].source.source_id)
    assert raw_rows(pg43, native_chat.scope.thread_id) == before
    for table in ("chat_memory_executions", "task_memory_snapshots"):
        column = next(item for item in inspect(pg43).get_columns(table) if item["name"] == "anchor_leaf_id")
        assert column["nullable"] is True and Base.metadata.tables[table].c.anchor_leaf_id.nullable is True
