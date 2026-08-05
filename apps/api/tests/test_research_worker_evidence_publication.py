from __future__ import annotations

import hashlib
from datetime import UTC, timedelta
from uuid import uuid4

import pytest
from ai_pdf_api.models import (
    AssetRepresentation,
    ContentUnit,
    EvidenceLocator,
    PdfLocatorDetail,
    ResearchArtifact,
    ResearchArtifactClaim,
    ResearchEvent,
    ResearchEvidenceHandle,
    ResearchEvidenceSnapshot,
    ResearchExecutionAsset,
    ResearchExecutionPromptVersion,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
    ResearchToolCall,
    ResearchToolCallInputHandle,
)
from ai_pdf_api.services import (
    research_worker_evidence,
    research_worker_publication,
)
from ai_pdf_api.services.embedding_index import (
    EMBEDDING_INDEX_MISMATCH_CODE,
    EMBEDDING_INDEX_MISMATCH_MESSAGE,
)
from ai_pdf_api.services.providers import ModelProviderError
from ai_pdf_api.services.research_evidence_provenance import evidence_source_fingerprint
from ai_pdf_api.services.research_idempotency import ResearchError
from ai_pdf_api.services.research_worker import (
    load_frozen_evidence,
    publish_final_report,
    restore_frozen_evidence,
    search_frozen_evidence,
)
from ai_pdf_api.services.research_worker_policy import (
    is_transient_failure,
    normalize_failure_code,
)
from ai_pdf_api.services.retrieval import RetrievedContent
from research_worker_test_support import (
    assert_research_error,
    lease_default_step,
    make_final_publication_chain,
    seed_frozen_evidence,
    sha256,
)
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


def test_frozen_evidence_search_rejects_asset_outside_execution_scope(research_worker_db) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    fixture.db.add(
        ResearchExecutionAsset(
            execution_snapshot_id=fixture.snapshot.id,
            workspace_id=fixture.run.workspace_id,
            asset_id=fixture.asset.id,
            asset_order=0,
            asset_kind_snapshot=fixture.asset.asset_kind,
            asset_title_snapshot=fixture.asset.title,
            processing_generation_snapshot=fixture.asset.current_processing_generation,
            index_version_snapshot=fixture.asset.current_index_version,
        )
    )
    fixture.db.commit()

    with pytest.raises(ResearchError) as scope_error:
        search_frozen_evidence(
            fixture.db,
            run_id=fixture.run.id,
            execution_snapshot_id=fixture.snapshot.id,
            step_id=fixture.step.id,
            attempt_id=lease.attempt_id,
            branch_key=fixture.step.branch_key or "",
            tool_call_key="search-out-of-scope",
            query="facts",
            asset_ids=(str(uuid4()),),
            top_k=3,
            now=fixture.now + timedelta(seconds=1),
        )
    assert_research_error(scope_error, "tool_scope_violation", 409)
    fixture.db.rollback()
    assert fixture.db.scalar(select(ResearchToolCall)) is None


def test_frozen_evidence_search_persists_then_replays_without_retrieval(
    research_worker_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    representation = AssetRepresentation(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        asset_id=fixture.asset.id,
        representation_kind="pdf_page_layout",
        processing_generation=fixture.asset.current_processing_generation,
        generator_provider="test-parser",
        generator_model="test-parser-model",
        generator_version="test-parser-v1",
        object_key=f"representations/{fixture.asset.id}/pages.json",
        content_sha256=sha256("representation"),
        created_at=fixture.now,
    )
    locator = EvidenceLocator(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        asset_id=fixture.asset.id,
        locator_kind="pdf_page",
        locator_version=1,
        processing_generation_snapshot=fixture.asset.current_processing_generation,
        representation_id_snapshot=representation.id,
        created_at=fixture.now,
    )
    content_unit = ContentUnit(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        asset_id=fixture.asset.id,
        representation_id=representation.id,
        source_locator_id=locator.id,
        unit_kind="pdf_text",
        unit_order=0,
        text_content="Retrieved frozen evidence.",
        token_count=4,
        index_version=fixture.asset.current_index_version,
        created_at=fixture.now,
    )
    fixture.db.add_all(
        [
            ResearchExecutionAsset(
                execution_snapshot_id=fixture.snapshot.id,
                workspace_id=fixture.run.workspace_id,
                asset_id=fixture.asset.id,
                asset_order=0,
                asset_kind_snapshot=fixture.asset.asset_kind,
                asset_title_snapshot=fixture.asset.title,
                processing_generation_snapshot=fixture.asset.current_processing_generation,
                index_version_snapshot=fixture.asset.current_index_version,
            ),
            representation,
            locator,
            PdfLocatorDetail(locator_id=locator.id, page_number=1),
            content_unit,
        ]
    )
    fixture.db.commit()
    calls = {"embed": 0, "retrieve": 0}

    class FakeEmbeddingProvider:
        provider = fixture.snapshot.embedding_provider
        model = fixture.snapshot.embedding_model
        version = fixture.snapshot.embedding_version

        def embed_query(self, query: str) -> list[float]:
            assert query == "facts"
            calls["embed"] += 1
            return [0.25, 0.75]

    def fake_retrieve(*_args, **_kwargs):
        calls["retrieve"] += 1
        return [
            RetrievedContent(
                content_unit=content_unit,
                asset=fixture.asset,
                locator=locator,
                channel="text",
                distance=0.1,
                location_key=(fixture.asset.id, "pdf_page:1"),
            )
        ]

    monkeypatch.setattr(research_worker_evidence, "retrieve_query_content", fake_retrieve)
    args = {
        "run_id": fixture.run.id,
        "execution_snapshot_id": fixture.snapshot.id,
        "step_id": fixture.step.id,
        "attempt_id": lease.attempt_id,
        "branch_key": fixture.step.branch_key or "",
        "tool_call_key": "search-live-then-replay",
        "query": "facts",
        "asset_ids": (fixture.asset.id,),
        "top_k": 3,
        "embedding_provider": FakeEmbeddingProvider(),
        "now": fixture.now + timedelta(seconds=1),
    }

    first = search_frozen_evidence(fixture.db, **args)
    second = search_frozen_evidence(fixture.db, **args)

    assert calls == {"embed": 1, "retrieve": 1}
    assert [item.evidence_handle for item in first] == [item.evidence_handle for item in second]
    assert first[0].excerpt == "Retrieved frozen evidence."
    assert first[0].score == pytest.approx(0.9)
    assert fixture.db.scalar(select(ResearchEvidenceSnapshot)) is not None
    assert len(list(fixture.db.scalars(select(ResearchEvidenceHandle)).all())) == 1
    assert len(list(fixture.db.scalars(select(ResearchToolCall)).all())) == 1
    fixture.db.refresh(fixture.ledger)
    assert fixture.ledger.actual_tool_calls == 1
    assert fixture.ledger.reserved_tool_calls == 0


def test_frozen_evidence_search_and_load_replay_persisted_handle_set(research_worker_db) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    handle = seed_frozen_evidence(fixture, lease.attempt_id)

    search_args = {
        "run_id": fixture.run.id,
        "execution_snapshot_id": fixture.snapshot.id,
        "step_id": fixture.step.id,
        "attempt_id": lease.attempt_id,
        "branch_key": fixture.step.branch_key or "",
        "tool_call_key": "search-replay",
        "query": "facts",
        "asset_ids": (fixture.asset.id,),
        "top_k": 3,
        "now": fixture.now + timedelta(seconds=1),
    }
    first_search = search_frozen_evidence(fixture.db, **search_args)
    second_search = search_frozen_evidence(fixture.db, **search_args)
    assert [item.evidence_handle for item in first_search] == [handle.id]
    assert first_search == second_search
    assert first_search[0].excerpt == "Frozen evidence excerpt."
    assert len(list(fixture.db.scalars(select(ResearchToolCall)).all())) == 1

    with pytest.raises(ResearchError) as changed_replay:
        search_frozen_evidence(fixture.db, **{**search_args, "query": "changed query"})
    assert_research_error(changed_replay, "research_state_conflict", 409)
    fixture.db.rollback()

    load_args = {
        "run_id": fixture.run.id,
        "execution_snapshot_id": fixture.snapshot.id,
        "step_id": fixture.step.id,
        "attempt_id": lease.attempt_id,
        "branch_key": fixture.step.branch_key or "",
        "tool_call_key": "load-replay",
        "evidence_handle_ids": (handle.id,),
        "now": fixture.now + timedelta(seconds=2),
    }
    first_load = load_frozen_evidence(fixture.db, **load_args)
    second_load = load_frozen_evidence(fixture.db, **load_args)
    assert first_load == second_load
    assert first_load[0].evidence_handle == handle.id
    assert first_load[0].content == "Frozen evidence excerpt."
    assert first_load[0].source_available is True
    calls = list(
        fixture.db.scalars(select(ResearchToolCall).order_by(ResearchToolCall.call_order)).all()
    )
    assert [(call.tool_name, call.call_order, call.status) for call in calls] == [
        ("evidence.search", 0, "succeeded"),
        ("evidence.load", 1, "succeeded"),
    ]
    input_handles = list(
        fixture.db.scalars(
            select(ResearchToolCallInputHandle).where(
                ResearchToolCallInputHandle.tool_call_id == calls[1].id
            )
        ).all()
    )
    assert [(item.evidence_handle_id, item.input_order) for item in input_handles] == [(handle.id, 0)]


def test_frozen_evidence_load_rejects_handle_owned_by_another_step(research_worker_db) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    handle = seed_frozen_evidence(fixture, lease.attempt_id)
    handle.owner_step_id = str(uuid4())
    fixture.db.commit()

    with pytest.raises(ResearchError) as scope_error:
        load_frozen_evidence(
            fixture.db,
            run_id=fixture.run.id,
            execution_snapshot_id=fixture.snapshot.id,
            step_id=fixture.step.id,
            attempt_id=lease.attempt_id,
            branch_key=fixture.step.branch_key or "",
            tool_call_key="load-cross-step",
            evidence_handle_ids=(handle.id,),
            now=fixture.now + timedelta(seconds=1),
        )
    assert_research_error(scope_error, "evidence_handle_not_found", 404)
    fixture.db.rollback()
    assert len(list(fixture.db.scalars(select(ResearchToolCall)).all())) == 1


def test_restore_frozen_evidence_rejects_tampered_excerpt_fingerprint(research_worker_db) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    handle = seed_frozen_evidence(fixture, lease.attempt_id)
    evidence = fixture.db.get(ResearchEvidenceSnapshot, handle.evidence_snapshot_id)
    assert evidence is not None
    evidence.excerpt_snapshot += " tampered"
    fixture.db.commit()

    with pytest.raises(ResearchError) as integrity_error:
        restore_frozen_evidence(
            fixture.db,
            run_id=fixture.run.id,
            execution_snapshot_id=fixture.snapshot.id,
            owner_step_id=fixture.step.id,
        )
    assert_research_error(integrity_error, "research_state_conflict", 409)


def test_load_frozen_evidence_rejects_oversized_persisted_excerpt(research_worker_db) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    handle = seed_frozen_evidence(fixture, lease.attempt_id)
    evidence = fixture.db.get(ResearchEvidenceSnapshot, handle.evidence_snapshot_id)
    assert evidence is not None
    evidence.excerpt_snapshot = "x" * 2001
    evidence.source_fingerprint_sha256 = evidence_source_fingerprint(
        evidence,
        locator_kind="pdf_page",
    )
    fixture.db.commit()

    with pytest.raises(ResearchError) as integrity_error:
        load_frozen_evidence(
            fixture.db,
            run_id=fixture.run.id,
            execution_snapshot_id=fixture.snapshot.id,
            step_id=fixture.step.id,
            attempt_id=lease.attempt_id,
            branch_key=fixture.step.branch_key or "",
            tool_call_key="load-oversized",
            evidence_handle_ids=(handle.id,),
            now=fixture.now + timedelta(seconds=1),
        )
    assert_research_error(integrity_error, "research_state_conflict", 409)


def test_publish_final_report_commits_claim_mapping_terminal_state_and_events(research_worker_db) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    report_bytes = (
        "# Citeframe Research Report\n\n"
        "## Findings\n"
        f"<!-- citeframe:claim id={fact.id} section=fact -->\n"
        "- Supported fact.\n\n"
        "## Unresolved Evidence Conflicts\n"
        f"<!-- citeframe:claim id={unresolved.id} section=unresolved -->\n"
        "- Supported but unresolved claim.\n"
    ).encode()
    stored: dict[str, tuple[bytes, str]] = {}

    artifact_id = publish_final_report(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        store_bytes=lambda key, content, content_type: stored.__setitem__(
            key, (content, content_type)
        ),
        now=fixture.now + timedelta(seconds=1),
    )

    fixture.db.expire_all()
    artifact = fixture.db.get(ResearchArtifact, artifact_id)
    run = fixture.db.get(ResearchRun, fixture.run.id)
    step = fixture.db.get(ResearchStep, fixture.step.id)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert artifact is not None and artifact.artifact_kind == "final_report"
    assert artifact.visibility == "user"
    assert artifact.content_sha256 == hashlib.sha256(report_bytes).hexdigest()
    assert stored == {artifact.object_key: (report_bytes, "text/markdown")}
    mappings = list(
        fixture.db.scalars(
            select(ResearchArtifactClaim)
            .where(ResearchArtifactClaim.artifact_id == artifact.id)
            .order_by(ResearchArtifactClaim.claim_order)
        ).all()
    )
    assert [(item.claim_id, item.claim_order, item.section_kind) for item in mappings] == [
        (fact.id, 0, "fact"),
        (unresolved.id, 1, "unresolved"),
    ]
    assert run is not None and run.status == "completed"
    assert run.finished_at is not None
    assert run.finished_at.replace(tzinfo=UTC) == fixture.now + timedelta(seconds=1)
    assert step is not None and step.status == "succeeded"
    assert attempt is not None and attempt.status == "succeeded"
    assert attempt.output_sha256 == artifact.content_sha256
    events = list(
        fixture.db.scalars(
            select(ResearchEvent).where(ResearchEvent.run_id == fixture.run.id).order_by(ResearchEvent.seq)
        ).all()
    )
    assert [event.event_type for event in events] == [
        "run_status_changed",
        "step_started",
        "step_succeeded",
        "artifact_published",
        "run_completed",
    ]
    assert events[-1].payload_json["finalArtifactId"] == artifact.id


def test_publish_final_report_rolls_back_and_cleans_bytes_when_event_write_fails(
    research_worker_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    stored_keys: list[str] = []
    cleaned_keys: list[str] = []

    def fail_event(*_args, **_kwargs):
        raise RuntimeError("final event write failed")

    monkeypatch.setattr(research_worker_publication, "append_research_event", fail_event)
    with pytest.raises(RuntimeError, match="final event write failed"):
        publish_final_report(
            fixture.db,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            fact_claim_ids=(fact.id,),
            unresolved_claim_ids=(unresolved.id,),
            store_bytes=lambda key, _content, _content_type: stored_keys.append(key),
            cleanup_bytes=cleaned_keys.append,
            now=fixture.now + timedelta(seconds=1),
        )

    fixture.db.expire_all()
    assert cleaned_keys == stored_keys
    assert len(cleaned_keys) == 1
    assert (
        fixture.db.scalar(
            select(ResearchArtifact).where(
                ResearchArtifact.run_id == fixture.run.id,
                ResearchArtifact.artifact_kind == "final_report",
            )
        )
        is None
    )
    assert fixture.db.scalar(select(ResearchArtifactClaim)) is None
    run = fixture.db.get(ResearchRun, fixture.run.id)
    step = fixture.db.get(ResearchStep, fixture.step.id)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert run is not None and run.status == "running"
    assert run.finished_at is None
    assert step is not None and step.status == "running"
    assert attempt is not None and attempt.status == "running"
    assert (
        fixture.db.scalar(
            select(ResearchEvent).where(ResearchEvent.event_type == "run_completed")
        )
        is None
    )


def test_publish_final_report_rejects_tampered_claim_before_upload(research_worker_db) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    fact.statement_text = "Tampered after verification."
    fixture.db.commit()
    stored_keys: list[str] = []

    with pytest.raises(ResearchError) as integrity_error:
        publish_final_report(
            fixture.db,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            fact_claim_ids=(fact.id,),
            unresolved_claim_ids=(unresolved.id,),
            store_bytes=lambda key, _content, _content_type: stored_keys.append(key),
            now=fixture.now + timedelta(seconds=1),
        )
    assert_research_error(integrity_error, "research_state_conflict", 409)
    assert stored_keys == []


def test_publish_final_report_rejects_incomplete_prompt_snapshot_before_upload(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    prompt = fixture.db.scalar(
        select(ResearchExecutionPromptVersion).where(
            ResearchExecutionPromptVersion.execution_snapshot_id == fixture.snapshot.id,
            ResearchExecutionPromptVersion.node_key == "critic",
        )
    )
    assert prompt is not None
    fixture.db.delete(prompt)
    fixture.db.commit()
    lease = lease_default_step(fixture)
    stored_keys: list[str] = []

    with pytest.raises(ValueError, match="research_execution_prompt_binding_invalid"):
        publish_final_report(
            fixture.db,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            fact_claim_ids=(fact.id,),
            unresolved_claim_ids=(unresolved.id,),
            store_bytes=lambda key, _content, _content_type: stored_keys.append(key),
            now=fixture.now + timedelta(seconds=1),
        )
    assert stored_keys == []


def test_publish_final_report_recovers_ambiguous_committed_transaction(
    research_worker_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    factory = sessionmaker(bind=fixture.db.get_bind(), expire_on_commit=False, future=True)
    stored: dict[str, bytes] = {}
    real_commit = fixture.db.commit

    def commit_then_raise() -> None:
        real_commit()
        raise RuntimeError("commit acknowledgement lost")

    monkeypatch.setattr(fixture.db, "commit", commit_then_raise)
    artifact_id = publish_final_report(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        store_bytes=lambda key, content, _content_type: stored.__setitem__(key, content),
        cleanup_bytes=lambda key: stored.pop(key, None),
        committed_session_factory=factory,
        now=fixture.now + timedelta(seconds=1),
    )

    with factory() as verification_db:
        artifact = verification_db.get(ResearchArtifact, artifact_id)
        assert artifact is not None
        assert artifact.object_key in stored


def test_publish_final_report_cleans_object_when_commit_is_confirmed_absent(
    research_worker_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    factory = sessionmaker(bind=fixture.db.get_bind(), expire_on_commit=False, future=True)
    stored_keys: list[str] = []
    cleaned_keys: list[str] = []
    monkeypatch.setattr(
        fixture.db,
        "commit",
        lambda: (_ for _ in ()).throw(RuntimeError("commit rejected")),
    )

    with pytest.raises(RuntimeError, match="commit rejected"):
        publish_final_report(
            fixture.db,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            fact_claim_ids=(fact.id,),
            unresolved_claim_ids=(unresolved.id,),
            store_bytes=lambda key, _content, _content_type: stored_keys.append(key),
            cleanup_bytes=cleaned_keys.append,
            committed_session_factory=factory,
            now=fixture.now + timedelta(seconds=1),
        )
    assert cleaned_keys == stored_keys
    with factory() as verification_db:
        assert verification_db.scalar(
            select(ResearchArtifact).where(ResearchArtifact.run_id == fixture.run.id)
        ) is None


def test_frozen_evidence_search_maps_embedding_index_mismatch_to_research_error(
    research_worker_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    fixture.db.add(
        ResearchExecutionAsset(
            execution_snapshot_id=fixture.snapshot.id,
            workspace_id=fixture.run.workspace_id,
            asset_id=fixture.asset.id,
            asset_order=0,
            asset_kind_snapshot=fixture.asset.asset_kind,
            asset_title_snapshot=fixture.asset.title,
            processing_generation_snapshot=fixture.asset.current_processing_generation,
            index_version_snapshot=fixture.asset.current_index_version,
        )
    )
    fixture.db.commit()

    class FakeEmbeddingProvider:
        provider = fixture.snapshot.embedding_provider
        model = fixture.snapshot.embedding_model
        version = fixture.snapshot.embedding_version

        def embed_query(self, query: str) -> list[float]:
            assert query == "facts"
            return [0.25, 0.75]

    def raise_mismatch(*_args, **_kwargs):
        raise ModelProviderError(
            EMBEDDING_INDEX_MISMATCH_CODE,
            EMBEDDING_INDEX_MISMATCH_MESSAGE,
        )

    monkeypatch.setattr(research_worker_evidence, "retrieve_query_content", raise_mismatch)

    with pytest.raises(ResearchError) as mismatch_error:
        search_frozen_evidence(
            fixture.db,
            run_id=fixture.run.id,
            execution_snapshot_id=fixture.snapshot.id,
            step_id=fixture.step.id,
            attempt_id=lease.attempt_id,
            branch_key=fixture.step.branch_key or "",
            tool_call_key="search-embedding-index-mismatch",
            query="facts",
            asset_ids=(fixture.asset.id,),
            top_k=3,
            embedding_provider=FakeEmbeddingProvider(),
            now=fixture.now + timedelta(seconds=1),
        )

    assert_research_error(mismatch_error, EMBEDDING_INDEX_MISMATCH_CODE, 409)
    assert mismatch_error.value.message == EMBEDDING_INDEX_MISMATCH_MESSAGE
    assert "explicit reindex" in mismatch_error.value.message.lower()

    call = fixture.db.scalar(select(ResearchToolCall))
    assert call is not None
    assert call.status == "failed"
    assert call.error_code == EMBEDDING_INDEX_MISMATCH_CODE
    assert call.error_code != "tool_temporarily_unavailable"

    # Policy path used by fail_research_step must keep this non-retryable.
    reason = normalize_failure_code(EMBEDDING_INDEX_MISMATCH_CODE)
    assert reason == EMBEDDING_INDEX_MISMATCH_CODE
    assert is_transient_failure(reason) is False
