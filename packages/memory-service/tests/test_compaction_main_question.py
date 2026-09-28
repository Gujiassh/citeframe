"""Mandatory current-question identity and effect-free rejection on real PostgreSQL."""
from dataclasses import asdict, replace
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from citeframe_contracts.compaction import CoverageUnit
from citeframe_contracts.memory import GenerationMessage, GenerationRequest, ToolCall
from citeframe_memory.compaction.archive import ToolArchive
from citeframe_memory.compaction.gate import DispatchGate, DispatchPermit
from citeframe_memory.compaction.guards import digest
from citeframe_memory.compaction.journal import CallJournal
from citeframe_memory.compaction.policy import CompactionError, CompactionPolicy
from citeframe_memory.compaction.units import ContextUnit
from test_compaction_fixture import insert_message, pg43
from test_compaction_gate import Files, Provider, prepared_main
from test_compaction_native_packing import PROTOCOLS, native_counter
from test_compaction_repository import adopt, summary


def gate_fixture(engine, tmp_path, protocol="openai_responses"):
    scope, repo, owner, policy, units = prepared_main(engine)
    connection, counter, identity = native_counter(protocol, context=8000, output=1000)
    provider = Provider(summary(units))
    files = Files(tmp_path)
    archive = ToolArchive(repo, files)
    gate = DispatchGate(repo, CallJournal(repo, object_store=files), provider, counter, connection, identity,
        input_ceiling=5500, archive=archive, policy=CompactionPolicy(min_new_tokens=1, min_gain_tokens=1, soft_ratio=.6, target_ratio=.4))
    return scope, repo, owner, policy, units, gate, provider, archive


def effects(engine, owner, path):
    with engine.connect() as db:
        calls = db.execute(text("SELECT to_jsonb(c) FROM memory_calls c WHERE chat_execution_id=:id ORDER BY id"), {"id": owner.owner_id}).scalars().all()
        pointer = db.execute(text("SELECT context_version,checkpoint_id FROM chat_memory_executions WHERE id=:id"), {"id": owner.owner_id}).one()
        counts = tuple(db.scalar(text("SELECT count(*) FROM " + table)) for table in ("task_memory_snapshots", "task_memory_coverage", "memory_uses"))
    objects = {str(p.relative_to(path)): p.read_bytes() for p in path.rglob("*") if p.is_file()}
    return calls, pointer, counts, objects


def sibling_current(engine, scope, repo, owner, policy):
    user, assistant = str(uuid4()), str(uuid4())
    with engine.begin() as db:
        insert_message(db, scope, user, content="current request")
        insert_message(db, scope, assistant, parent_id=user, content="")
        db.execute(text("UPDATE chat_messages SET role='assistant',status='streaming' WHERE id=:id"), {"id": assistant})
    sibling = replace(owner, owner_id=str(uuid4()))
    deadline = datetime.fromisoformat(policy["deadlineAt"])
    repo.create_chat(sibling, thread_id=scope.thread_id, user_message_id=user, assistant_message_id=assistant,
        request_id=str(uuid4()), request_sha256="c"*64, policy=policy, deadline_at=deadline, lease_expires_at=deadline)
    return CoverageUnit("foreign-current", repo.register_source(sibling, "chat_message", user))


@pytest.mark.parametrize("case,code", [
    ("empty", "designated_question_required"), ("history_only", "designated_question_required"),
    ("foreign_current", "source_branch_mismatch"), ("duplicate_current", "duplicate_source_coverage"),
    ("template_user", "main_template_must_be_system"), ("template_assistant", "main_template_must_be_system"),
    ("tools_before_current", "designated_question_order"),
])
def test_invalid_current_question_rejected_before_reservation_objects_or_generation(pg43, tmp_path, case, code):
    scope, repo, owner, policy, units, gate, provider, archive = gate_fixture(pg43, tmp_path)
    template = GenerationRequest((GenerationMessage("system", "trusted"),), 1000)
    coverage = units
    if case == "empty": coverage = ()
    elif case == "history_only": coverage = units[:-1]
    elif case == "foreign_current": coverage = (sibling_current(pg43, scope, repo, owner, policy),)
    elif case == "duplicate_current": coverage += (replace(units[-1], key="duplicate-current"),)
    elif case.startswith("template_"):
        template = replace(template, messages=template.messages + (GenerationMessage(case.removeprefix("template_"), "current request"),))
    else:
        batch = ContextUnit("batch", "tool_group", (GenerationMessage("assistant", "", (ToolCall("read-1", "read_source", "{}"),)),
            GenerationMessage("tool", "complete original", tool_call_id="read-1")), ("succeeded",))
        call = archive.persist(repo.capture(owner, units, policy), policy, batch, (units[0].source,))
        coverage = units[:-1] + (CoverageUnit("batch", tool_group_id=call), units[-1])
    before = effects(pg43, owner, tmp_path)
    with pytest.raises(CompactionError, match="^" + code + "$"):
        gate.prepare_main_dispatch(owner, template, coverage, policy, expected_context_version=0,
            logical_key="invalid", recent_units=0, protected_keys=frozenset({"invented-protected-key"}))
    assert effects(pg43, owner, tmp_path) == before
    assert not provider.calls


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_gate_derives_protection_for_current_question_across_dispatch_modes(pg43, tmp_path, protocol):
    scope, repo, owner, policy, units, gate, provider, archive = gate_fixture(pg43, tmp_path, protocol)
    with pg43.begin() as db:
        db.execute(text("UPDATE chat_messages SET content=:body WHERE id=:id"), {"id": scope.parent_id, "body": "37.5 ms never production only batch=8. "*400})
    units = (replace(units[0], source=repo.register_source(owner, "chat_message", scope.parent_id)), *units[1:])
    provider.result = summary(units)
    template = GenerationRequest((GenerationMessage("system", "trusted"),), 1000)
    version = 0
    for mode in ("initial", "continuation", "resume"):
        permit = gate.prepare_main_dispatch(owner, template, units, policy, expected_context_version=version,
            logical_key=mode, mode=mode, recent_units=0)
        request = gate.authorize_send(permit, policy)
        assert sum(message.content == "current request" for message in request.messages) == 1
        assert request.messages[-1] == GenerationMessage("user", "current request")
        assert permit.checkpoint_id and permit.captured.owner == owner
        assert gate.counter.count(request, gate.connection).tokens <= 5500
        version = permit.captured.context_version
    assert len(provider.calls) == 1
    with pg43.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM memory_calls WHERE purpose='main' AND state='sent'")) == 3


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_historical_same_text_does_not_replace_designated_source_identity(pg43, tmp_path, protocol):
    scope, repo, owner, policy, units, gate, provider, archive = gate_fixture(pg43, tmp_path, protocol)
    with pg43.begin() as db:
        db.execute(text("UPDATE chat_messages SET content='current request' WHERE id=:id"), {"id": scope.parent_id})
    units = (replace(units[0], source=repo.register_source(owner, "chat_message", scope.parent_id)), *units[1:])
    assert units[0].source.source_id != units[-1].source.source_id
    captured = repo.capture(owner, units, policy)
    assert repo.main_question_key(captured, policy) == units[-1].key
    permit = gate.prepare_main_dispatch(owner, GenerationRequest((GenerationMessage("system", "trusted"),), 1000),
        units, policy, expected_context_version=0, logical_key="same-text", recent_units=0)
    request = gate.authorize_send(permit, policy)
    assert request.messages[1:] == tuple(GenerationMessage(role, repo.read_source(owner, unit.source))
        for role, unit in zip(("user", "assistant", "user"), units))
    assert sum(message.content == "current request" for message in request.messages) == 2
    with pytest.raises(CompactionError, match="designated_question_required"):
        gate.prepare_main_dispatch(owner, GenerationRequest((GenerationMessage("system", "trusted"),), 1000),
            units[:-1], policy, expected_context_version=0, logical_key="same-text-is-not-current", recent_units=0)
    assert not provider.calls


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_forged_lowlevel_permit_cannot_send_system_only_request(pg43, tmp_path, protocol):
    scope, repo, owner, policy, units, gate, provider, archive = gate_fixture(pg43, tmp_path, protocol)
    captured = repo.capture(owner, units, policy)
    request = GenerationRequest((GenerationMessage("system", "trusted"),), 1000)
    receipt = gate.journal.reserve(captured, policy, logical_key="lowlevel-forged", purpose="main",
        request_sha256=digest(asdict(request)), input_tokens=gate.counter.count(request, gate.connection).tokens,
        output_tokens=request.max_output_tokens, provider=gate.connection.protocol, model=gate.connection.model,
        profile_fingerprint=gate.connection.config_fingerprint, dispatch_profile=gate._profile())
    forged = DispatchPermit(request, captured, receipt, captured.checkpoint_id, "unchanged", "initial")
    before = effects(pg43, owner, tmp_path)
    with pytest.raises(CompactionError, match="^main_rendering_changed$"):
        gate.authorize_send(forged, policy)
    assert effects(pg43, owner, tmp_path) == before
    assert not provider.calls
    with pg43.connect() as db:
        assert db.execute(text("SELECT state,request_object_key FROM memory_calls WHERE id=:id"), {"id": receipt.call_id}).one() == ("reserved", None)



def test_lowlevel_checkpoint_cannot_hide_designated_question_at_main_boundary(pg43, tmp_path):
    scope, repo, owner, policy, units, gate, provider, archive = gate_fixture(pg43, tmp_path)
    receipt = adopt(repo, repo.capture(owner, units, policy), policy, count=len(units), store=Files(tmp_path))
    before = effects(pg43, owner, tmp_path)
    for mode in ("initial", "continuation", "resume"):
        with pytest.raises(CompactionError, match="^checkpoint_protected_anchor_hidden$"):
            gate.prepare_main_dispatch(owner, GenerationRequest((GenerationMessage("system", "trusted"),), 1000),
                units, policy, expected_context_version=receipt.context_version, logical_key="hidden-" + mode,
                mode=mode, recent_units=0)
        assert effects(pg43, owner, tmp_path) == before
    assert not provider.calls
