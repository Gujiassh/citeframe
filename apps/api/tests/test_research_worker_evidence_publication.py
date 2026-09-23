from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from threading import Event
from time import monotonic
from uuid import uuid4

import pytest
from ai_pdf_api.models import (
    AssetRepresentation,
    ContentUnit,
    EvidenceLocator,
    HumanDecision,
    PdfLocatorDetail,
    PromptVersion,
    ResearchArtifact,
    ResearchArtifactClaim,
    ResearchArtifactPromptVersion,
    ResearchClaim,
    ResearchEvent,
    ResearchEvidenceHandle,
    ResearchEvidenceSnapshot,
    ResearchExecutionAsset,
    ResearchExecutionPromptVersion,
    ResearchPlanRevisionAsset,
    ResearchPublicationIntent,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
    ResearchToolCall,
    ResearchToolCallInputHandle,
    WorkflowPromptBinding,
    WorkflowVersion,
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
from ai_pdf_api.services.research.research_evidence_provenance import (
    evidence_source_fingerprint,
)
from ai_pdf_api.services.research.research_idempotency import (
    ResearchError,
    canonical_sha256,
)
from ai_pdf_api.services.research.research_worker import (
    load_frozen_evidence,
    publish_final_report,
    reclaim_expired_research_steps,
    reconcile_one_publication_intent,
    restore_frozen_evidence,
    search_frozen_evidence,
)
from ai_pdf_api.services.research.research_worker_policy import (
    is_transient_failure,
    normalize_failure_code,
)
from ai_pdf_api.services.retrieval import RetrievedContent
from citeframe_contracts import PublicationResult
from citeframe_research_persistence.publication_finalize import _finalize_absent
from citeframe_research_persistence.publication_saga import (
    reconcile_one_publication_intent as reconcile_one_publication_intent_neutral,
)
from citeframe_research_persistence.publication_saga_support import (
    _COMPENSATION_SWEEP_PENDING,
    _claim_from_intent,
    _token_hash,
)
from research_worker_test_support import (
    assert_research_error,
    lease_default_step,
    make_final_publication_chain,
    seed_frozen_evidence,
    sha256,
)
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker


class MemoryPublicationStore:
    def __init__(self, *, fail_puts: int = 0) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.put_keys: list[str] = []
        self.get_keys: list[str] = []
        self.list_prefixes: list[str] = []
        self.deleted_keys: list[str] = []
        self.fail_puts = fail_puts

    def put(self, key: str, content: bytes, content_type: str) -> None:
        self.put_keys.append(key)
        if self.fail_puts:
            self.fail_puts -= 1
            raise RuntimeError("injected publication PUT failure")
        self.objects[key] = (bytes(content), content_type)

    def get(self, key: str) -> bytes:
        self.get_keys.append(key)
        return self.objects[key][0]

    def list(self, prefix: str) -> list[str]:
        self.list_prefixes.append(prefix)
        return sorted(key for key in self.objects if key.startswith(prefix))

    def delete(self, key: str) -> None:
        self.deleted_keys.append(key)
        self.objects.pop(key, None)

    def callbacks(self) -> dict[str, object]:
        return {
            "store_bytes": self.put,
            "load_bytes": self.get,
            "list_keys": self.list,
            "cleanup_bytes": self.delete,
        }


def local_publication_callbacks(
    fixture, storage: MemoryPublicationStore
) -> dict[str, object]:
    return {
        **storage.callbacks(),
        "committed_session_factory": sessionmaker(
            bind=fixture.db.get_bind(), expire_on_commit=False, future=True
        ),
    }


def test_frozen_evidence_search_rejects_asset_outside_execution_scope(
    research_worker_db,
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
            top_k=6,
            now=fixture.now + timedelta(seconds=1),
        )
    assert_research_error(scope_error, "tool_scope_violation", 409)
    fixture.db.rollback()
    assert fixture.db.scalar(select(ResearchToolCall)) is None


def test_frozen_evidence_search_rejects_top_k_mismatch_before_provider_or_ledger(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    with pytest.raises(ResearchError) as mismatch_error:
        search_frozen_evidence(
            fixture.db,
            run_id=fixture.run.id,
            execution_snapshot_id=fixture.snapshot.id,
            step_id=fixture.step.id,
            attempt_id=lease.attempt_id,
            branch_key=fixture.step.branch_key or "",
            tool_call_key="search-top-k-mismatch",
            query="facts",
            asset_ids=(),
            top_k=3,
            now=fixture.now + timedelta(seconds=1),
        )
    assert_research_error(mismatch_error, "research_retrieval_top_k_mismatch", 409)
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
    calls = {"embed": 0, "retrieve": 0, "limits": []}

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
        calls["limits"].append(_kwargs["limit"])
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

    monkeypatch.setattr(
        research_worker_evidence, "retrieve_query_content", fake_retrieve
    )
    args = {
        "run_id": fixture.run.id,
        "execution_snapshot_id": fixture.snapshot.id,
        "step_id": fixture.step.id,
        "attempt_id": lease.attempt_id,
        "branch_key": fixture.step.branch_key or "",
        "tool_call_key": "search-live-then-replay",
        "query": "facts",
        "asset_ids": (fixture.asset.id,),
        "top_k": 6,
        "embedding_provider": FakeEmbeddingProvider(),
        "now": fixture.now + timedelta(seconds=1),
    }

    first = search_frozen_evidence(fixture.db, **args)
    second = search_frozen_evidence(fixture.db, **args)

    assert calls == {
        "embed": 1,
        "retrieve": 1,
        "limits": [fixture.snapshot.retrieval_top_k],
    }
    assert [item.evidence_handle for item in first] == [
        item.evidence_handle for item in second
    ]
    assert first[0].excerpt == "Retrieved frozen evidence."
    assert first[0].score == pytest.approx(0.9)
    assert fixture.db.scalar(select(ResearchEvidenceSnapshot)) is not None
    assert len(list(fixture.db.scalars(select(ResearchEvidenceHandle)).all())) == 1
    assert len(list(fixture.db.scalars(select(ResearchToolCall)).all())) == 1
    fixture.db.refresh(fixture.ledger)
    assert fixture.ledger.actual_tool_calls == 1
    assert fixture.ledger.reserved_tool_calls == 0


def test_frozen_evidence_search_and_load_replay_persisted_handle_set(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    handle = seed_frozen_evidence(fixture, lease.attempt_id, top_k=6)

    search_args = {
        "run_id": fixture.run.id,
        "execution_snapshot_id": fixture.snapshot.id,
        "step_id": fixture.step.id,
        "attempt_id": lease.attempt_id,
        "branch_key": fixture.step.branch_key or "",
        "tool_call_key": "search-replay",
        "query": "facts",
        "asset_ids": (fixture.asset.id,),
        "top_k": 6,
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
        fixture.db.scalars(
            select(ResearchToolCall).order_by(ResearchToolCall.call_order)
        ).all()
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
    assert [(item.evidence_handle_id, item.input_order) for item in input_handles] == [
        (handle.id, 0)
    ]


def test_frozen_evidence_load_rejects_handle_owned_by_another_step(
    research_worker_db,
) -> None:
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


def test_restore_frozen_evidence_rejects_tampered_excerpt_fingerprint(
    research_worker_db,
) -> None:
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


def test_load_frozen_evidence_rejects_oversized_persisted_excerpt(
    research_worker_db,
) -> None:
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


def test_publish_final_report_commits_claim_mapping_terminal_state_and_events(
    research_worker_db,
) -> None:
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
    storage = MemoryPublicationStore()
    caller_now = fixture.now + timedelta(days=7)

    artifact_id = publish_final_report(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        **local_publication_callbacks(fixture, storage),
        now=caller_now,
    )

    fixture.db.expire_all()
    artifact = fixture.db.get(ResearchArtifact, artifact_id)
    run = fixture.db.get(ResearchRun, fixture.run.id)
    step = fixture.db.get(ResearchStep, fixture.step.id)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert artifact is not None and artifact.artifact_kind == "final_report"
    assert artifact.visibility == "user"
    assert artifact.content_sha256 == hashlib.sha256(report_bytes).hexdigest()
    assert storage.objects == {artifact.object_key: (report_bytes, "text/markdown")}
    assert "/publication/1/final.md" in artifact.object_key
    mappings = list(
        fixture.db.scalars(
            select(ResearchArtifactClaim)
            .where(ResearchArtifactClaim.artifact_id == artifact.id)
            .order_by(ResearchArtifactClaim.claim_order)
        ).all()
    )
    assert [
        (item.claim_id, item.claim_order, item.section_kind) for item in mappings
    ] == [
        (fact.id, 0, "fact"),
        (unresolved.id, 1, "unresolved"),
    ]
    assert run is not None and run.status == "completed"
    assert run.finished_at is not None
    finished_at = run.finished_at.replace(tzinfo=UTC)
    assert fixture.now <= finished_at <= datetime.now(UTC) + timedelta(seconds=1)
    assert finished_at != caller_now
    assert step is not None and step.status == "succeeded"
    assert attempt is not None and attempt.status == "succeeded"
    assert attempt.output_sha256 == artifact.content_sha256
    events = list(
        fixture.db.scalars(
            select(ResearchEvent)
            .where(ResearchEvent.run_id == fixture.run.id)
            .order_by(ResearchEvent.seq)
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
    intent = fixture.db.scalar(
        select(ResearchPublicationIntent).where(
            ResearchPublicationIntent.attempt_id == lease.attempt_id
        )
    )
    assert intent is not None
    assert intent.status == "committed"
    assert bytes(intent.payload_bytes) == report_bytes
    assert intent.content_sha256 == hashlib.sha256(report_bytes).hexdigest()
    assert intent.selection_json == {
        "factClaimIds": [fact.id],
        "unresolvedClaimIds": [unresolved.id],
    }
    assert intent.committed_artifact_id == artifact.id
    assert intent.adopted_object_key == artifact.object_key


def test_publish_final_report_same_attempt_replays_the_committed_artifact(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    storage = MemoryPublicationStore()
    arguments = {
        "attempt_id": lease.attempt_id,
        "lease_token": lease.lease_token,
        "fact_claim_ids": (fact.id,),
        "unresolved_claim_ids": (unresolved.id,),
        **local_publication_callbacks(fixture, storage),
    }

    first = publish_final_report(fixture.db, **arguments)
    second = publish_final_report(fixture.db, **arguments)

    assert isinstance(first, str)
    assert second == first
    assert len(storage.put_keys) == 1
    assert (
        fixture.db.scalar(
            select(ResearchPublicationIntent).where(
                ResearchPublicationIntent.attempt_id == lease.attempt_id
            )
        ).artifact_id
        == first
    )


def test_publish_final_report_retries_without_generic_failure_when_final_event_write_fails(
    research_worker_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    storage = MemoryPublicationStore()

    def fail_event(*_args, **_kwargs):
        raise RuntimeError("final event write failed")

    monkeypatch.setattr(
        research_worker_publication, "append_research_event", fail_event
    )
    result = publish_final_report(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        **local_publication_callbacks(fixture, storage),
        now=fixture.now + timedelta(seconds=1),
    )

    fixture.db.expire_all()
    assert isinstance(result, PublicationResult)
    assert result.kind == "reconcile_pending"
    intent = fixture.db.get(ResearchPublicationIntent, result.intent_id)
    assert intent is not None and intent.status == "prepared"
    assert len(storage.objects) == 1
    assert storage.deleted_keys == []
    assert (
        fixture.db.scalar(
            select(ResearchArtifact).where(
                ResearchArtifact.run_id == fixture.run.id,
                ResearchArtifact.artifact_kind == "final_report",
            )
        )
        is None
    )
    assert (
        fixture.db.scalar(
            select(ResearchArtifactClaim).where(
                ResearchArtifactClaim.artifact_id == intent.artifact_id
            )
        )
        is None
    )
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


@pytest.mark.parametrize(
    "invalid_selection",
    [
        None,
        "scalar",
        [],
        {"factClaimIds": [], "unresolvedClaimIds": [], "extra": True},
        {"factClaimIds": []},
        {"factClaimIds": [1], "unresolvedClaimIds": []},
    ],
    ids=["null", "scalar", "array", "extra", "missing-key", "non-string-list"],
)
def test_reconcile_treats_invalid_frozen_selection_shape_as_permanent_integrity(
    research_worker_db,
    invalid_selection: object,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    storage = MemoryPublicationStore(fail_puts=1)
    result = publish_final_report(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        **local_publication_callbacks(fixture, storage),
    )
    assert isinstance(result, PublicationResult)
    assert result.kind == "reconcile_pending"
    intent = fixture.db.get(ResearchPublicationIntent, result.intent_id)
    assert intent is not None and intent.status == "prepared"
    intent.selection_json = invalid_selection  # type: ignore[assignment]
    selection_bytes = json.dumps(
        invalid_selection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    intent.selection_sha256 = hashlib.sha256(selection_bytes).hexdigest()
    intent.next_reconcile_at = fixture.now - timedelta(seconds=1)
    fixture.db.commit()
    storage.put_keys.clear()
    storage.get_keys.clear()
    storage.list_prefixes.clear()
    storage.deleted_keys.clear()

    assert reconcile_one_publication_intent(
        fixture.db,
        worker_instance_id="reconciler-1",
        **local_publication_callbacks(fixture, storage),
    )

    fixture.db.expire_all()
    intent = fixture.db.get(ResearchPublicationIntent, result.intent_id)
    assert intent is not None and intent.status == "compensating"
    assert storage.put_keys == []
    assert storage.get_keys == []
    assert storage.list_prefixes == []
    assert storage.deleted_keys == []


def test_generic_reclaimer_yields_to_non_absent_publication_intent(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    storage = MemoryPublicationStore(fail_puts=1)
    result = publish_final_report(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        **local_publication_callbacks(fixture, storage),
    )
    assert isinstance(result, PublicationResult)
    assert result.kind == "reconcile_pending"
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert attempt is not None
    attempt.lease_expires_at = fixture.now - timedelta(seconds=1)
    fixture.db.commit()

    assert (
        reclaim_expired_research_steps(
            fixture.db,
            now=fixture.now + timedelta(seconds=1),
        )
        == 0
    )

    fixture.db.expire_all()
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    step = fixture.db.get(ResearchStep, fixture.step.id)
    intent = fixture.db.get(ResearchPublicationIntent, result.intent_id)
    assert attempt is not None and attempt.status == "running"
    assert step is not None and step.status == "running"
    assert intent is not None and intent.status != "absent"
    assert (
        fixture.db.scalar(
            select(ResearchStepAttempt).where(
                ResearchStepAttempt.step_id == fixture.step.id,
                ResearchStepAttempt.attempt_number > lease.attempt_number,
            )
        )
        is None
    )


def test_reconciler_waits_for_origin_attempt_lease_then_finalizes_without_token(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    storage = MemoryPublicationStore(fail_puts=1)
    pending = publish_final_report(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        **local_publication_callbacks(fixture, storage),
    )
    assert isinstance(pending, PublicationResult)
    assert pending.kind == "reconcile_pending"
    intent = fixture.db.get(ResearchPublicationIntent, pending.intent_id)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert intent is not None and attempt is not None
    active_expiry = fixture.now + timedelta(minutes=2)
    attempt.lease_expires_at = active_expiry
    intent.next_reconcile_at = fixture.now - timedelta(seconds=1)
    fixture.db.commit()
    storage.put_keys.clear()

    assert reconcile_one_publication_intent(
        fixture.db,
        worker_instance_id="reconciler-before-origin-expiry",
        **local_publication_callbacks(fixture, storage),
    )

    fixture.db.expire_all()
    intent = fixture.db.get(ResearchPublicationIntent, pending.intent_id)
    assert intent is not None
    assert intent.status == "prepared"
    assert intent.last_error_code == "research_publication_attempt_lease_active"
    assert intent.claim_owner is None
    assert intent.current_object_key is None
    assert intent.next_reconcile_at.replace(tzinfo=UTC) == active_expiry
    assert len(storage.put_keys) == 1
    assert (
        fixture.db.scalar(
            select(ResearchArtifact).where(
                ResearchArtifact.artifact_kind == "final_report"
            )
        )
        is None
    )
    assert (
        fixture.db.scalar(
            select(ResearchEvent).where(
                ResearchEvent.event_type.in_(
                    ("step_succeeded", "artifact_published", "run_completed")
                )
            )
        )
        is None
    )

    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert attempt is not None
    attempt.lease_expires_at = fixture.now - timedelta(seconds=1)
    intent.next_reconcile_at = fixture.now - timedelta(seconds=1)
    fixture.db.commit()

    assert reconcile_one_publication_intent(
        fixture.db,
        worker_instance_id="reconciler-after-origin-expiry",
        **local_publication_callbacks(fixture, storage),
    )

    fixture.db.expire_all()
    intent = fixture.db.get(ResearchPublicationIntent, pending.intent_id)
    assert intent is not None and intent.status == "committed"
    assert intent.committed_artifact_id == intent.artifact_id
    assert fixture.db.get(ResearchArtifact, intent.artifact_id) is not None
    assert len(storage.put_keys) == 2


@pytest.mark.parametrize(
    ("event_type", "dedupe_key"),
    [
        ("step_succeeded", "step-succeeded:{attempt_id}"),
        ("artifact_published", "artifact-published:{artifact_id}"),
        ("run_completed", "run-completed:{artifact_id}"),
    ],
)
def test_reconcile_compensates_when_terminal_event_key_preexists(
    research_worker_db,
    event_type: str,
    dedupe_key: str,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    storage = MemoryPublicationStore(fail_puts=1)
    pending = publish_final_report(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        **local_publication_callbacks(fixture, storage),
    )
    assert isinstance(pending, PublicationResult)
    intent = fixture.db.get(ResearchPublicationIntent, pending.intent_id)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    run = fixture.db.get(ResearchRun, fixture.run.id)
    assert intent is not None and attempt is not None and run is not None
    resolved_key = dedupe_key.format(
        attempt_id=attempt.id,
        artifact_id=intent.artifact_id,
    )
    fixture.db.add(
        ResearchEvent(
            workspace_id=run.workspace_id,
            run_id=run.id,
            seq=run.next_event_seq,
            event_type=event_type,
            event_schema_version="1",
            step_id=fixture.step.id if event_type == "step_succeeded" else None,
            attempt_id=attempt.id if event_type == "step_succeeded" else None,
            dedupe_key=resolved_key,
            payload_json={},
            created_at=fixture.now,
        )
    )
    run.next_event_seq += 1
    attempt.lease_expires_at = fixture.now - timedelta(seconds=1)
    intent.next_reconcile_at = fixture.now - timedelta(seconds=1)
    fixture.db.commit()
    storage.put_keys.clear()

    assert reconcile_one_publication_intent(
        fixture.db,
        worker_instance_id=f"reconciler-preexisting-{event_type}",
        **local_publication_callbacks(fixture, storage),
    )

    fixture.db.expire_all()
    intent = fixture.db.get(ResearchPublicationIntent, pending.intent_id)
    assert intent is not None and intent.status == "compensating"
    assert intent.last_error_code == "publication_compensation_sweep_pending"
    assert (
        fixture.db.scalar(
            select(ResearchArtifact).where(
                ResearchArtifact.artifact_kind == "final_report"
            )
        )
        is None
    )
    terminal_events = list(
        fixture.db.scalars(
            select(ResearchEvent).where(
                ResearchEvent.run_id == run.id,
                ResearchEvent.event_type.in_(
                    ("step_succeeded", "artifact_published", "run_completed")
                ),
            )
        ).all()
    )
    assert [(event.event_type, event.dedupe_key) for event in terminal_events] == [
        (event_type, resolved_key)
    ]
    assert len(storage.put_keys) == 1


def test_blocked_heartbeat_session_is_bounded_and_cannot_adopt_uploaded_object(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    storage = MemoryPublicationStore()
    real_factory = sessionmaker(
        bind=fixture.db.get_bind(), expire_on_commit=False, future=True
    )
    heartbeat_entered = Event()
    release_heartbeat = Event()
    heartbeat_released = Event()
    storage_completed_at = 0.0

    def blocked_factory():
        heartbeat_entered.set()
        release_heartbeat.wait(timeout=30)
        heartbeat_released.set()
        return real_factory()

    def slow_put(key: str, content: bytes, content_type: str) -> None:
        nonlocal storage_completed_at
        assert heartbeat_entered.wait(timeout=12)
        storage.put(key, content, content_type)
        storage_completed_at = monotonic()

    try:
        result = publish_final_report(
            fixture.db,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            fact_claim_ids=(fact.id,),
            unresolved_claim_ids=(unresolved.id,),
            store_bytes=slow_put,
            load_bytes=storage.get,
            list_keys=storage.list,
            cleanup_bytes=storage.delete,
            committed_session_factory=blocked_factory,
        )
        returned_at = monotonic()

        assert isinstance(result, PublicationResult)
        assert result.kind == "reconcile_pending"
        assert 3.5 <= returned_at - storage_completed_at <= 6.0
        fixture.db.expire_all()
        intent = fixture.db.get(ResearchPublicationIntent, result.intent_id)
        assert intent is not None and intent.status == "prepared"
        assert intent.committed_artifact_id is None
        assert intent.adopted_object_key is None
        assert (
            fixture.db.scalar(
                select(ResearchArtifact).where(
                    ResearchArtifact.run_id == fixture.run.id,
                    ResearchArtifact.artifact_kind == "final_report",
                )
            )
            is None
        )
        assert (
            fixture.db.scalar(
                select(ResearchEvent).where(
                    ResearchEvent.run_id == fixture.run.id,
                    ResearchEvent.event_type.in_(
                        ("artifact_published", "run_completed")
                    ),
                )
            )
            is None
        )
    finally:
        release_heartbeat.set()
        assert heartbeat_released.wait(timeout=5)


def test_publish_final_report_rejects_tampered_claim_before_upload(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    fact.statement_text = "Tampered after verification."
    fixture.db.commit()
    storage = MemoryPublicationStore()

    with pytest.raises(ResearchError) as integrity_error:
        publish_final_report(
            fixture.db,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            fact_claim_ids=(fact.id,),
            unresolved_claim_ids=(unresolved.id,),
            **local_publication_callbacks(fixture, storage),
            now=fixture.now + timedelta(seconds=1),
        )
    assert_research_error(integrity_error, "research_state_conflict", 409)
    assert storage.put_keys == []


def test_publish_final_report_rejects_oversize_before_intent_or_object(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    fact.statement_text = "x" * (16 * 1024 * 1024)
    fact.statement_sha256 = hashlib.sha256(fact.statement_text.encode()).hexdigest()
    fixture.db.commit()
    lease = lease_default_step(fixture)
    storage = MemoryPublicationStore()

    with pytest.raises(ResearchError) as too_large:
        publish_final_report(
            fixture.db,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            fact_claim_ids=(fact.id,),
            unresolved_claim_ids=(unresolved.id,),
            **local_publication_callbacks(fixture, storage),
        )

    assert_research_error(too_large, "research_publication_payload_too_large", 409)
    assert storage.put_keys == []
    assert (
        fixture.db.scalar(
            select(ResearchPublicationIntent).where(
                ResearchPublicationIntent.attempt_id == lease.attempt_id
            )
        )
        is None
    )


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
    storage = MemoryPublicationStore()

    with pytest.raises(ValueError, match="research_execution_prompt_binding_invalid"):
        publish_final_report(
            fixture.db,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            fact_claim_ids=(fact.id,),
            unresolved_claim_ids=(unresolved.id,),
            **local_publication_callbacks(fixture, storage),
            now=fixture.now + timedelta(seconds=1),
        )
    assert storage.put_keys == []


def test_publish_final_report_continues_after_exact_prepare_commit_response_is_lost(
    research_worker_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    factory = sessionmaker(
        bind=fixture.db.get_bind(), expire_on_commit=False, future=True
    )
    storage = MemoryPublicationStore()
    real_commit = fixture.db.commit
    commit_calls = 0

    def first_commit_then_raise() -> None:
        nonlocal commit_calls
        commit_calls += 1
        real_commit()
        if commit_calls == 1:
            raise RuntimeError("prepare commit acknowledgement lost")

    monkeypatch.setattr(fixture.db, "commit", first_commit_then_raise)
    artifact_id = publish_final_report(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        **storage.callbacks(),
        committed_session_factory=factory,
        now=fixture.now + timedelta(seconds=1),
    )

    assert isinstance(artifact_id, str)
    assert commit_calls > 1
    with factory() as verification_db:
        artifact = verification_db.get(ResearchArtifact, artifact_id)
        intent = verification_db.scalar(
            select(ResearchPublicationIntent).where(
                ResearchPublicationIntent.attempt_id == lease.attempt_id
            )
        )
        assert artifact is not None
        assert intent is not None and intent.status == "committed"
        assert artifact.object_key in storage.objects
        assert storage.put_keys == [artifact.object_key]


@pytest.mark.parametrize(
    "corruption",
    ["object-key", "payload", "selection", "claim-token", "generation"],
)
def test_prepare_commit_unknown_requires_exact_durable_claim_predicate(
    research_worker_db,
    monkeypatch: pytest.MonkeyPatch,
    corruption: str,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    factory = sessionmaker(
        bind=fixture.db.get_bind(), expire_on_commit=False, future=True
    )
    storage = MemoryPublicationStore()
    real_commit = fixture.db.commit
    commit_calls = 0

    def first_commit_then_corrupt_and_raise() -> None:
        nonlocal commit_calls
        commit_calls += 1
        real_commit()
        if commit_calls != 1:
            return
        with factory() as corruption_db:
            intent = corruption_db.scalar(
                select(ResearchPublicationIntent).where(
                    ResearchPublicationIntent.attempt_id == lease.attempt_id
                )
            )
            assert intent is not None
            if corruption == "object-key":
                intent.current_object_key = f"{intent.object_prefix}/tampered/final.md"
            elif corruption == "payload":
                payload = b"# Different but internally consistent payload\n"
                intent.payload_bytes = payload
                intent.byte_size = len(payload)
                intent.content_sha256 = hashlib.sha256(payload).hexdigest()
            elif corruption == "selection":
                selection = {"factClaimIds": [], "unresolvedClaimIds": []}
                selection_bytes = json.dumps(
                    selection,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
                intent.selection_json = selection
                intent.selection_sha256 = hashlib.sha256(selection_bytes).hexdigest()
            elif corruption == "claim-token":
                intent.claim_token_hash = sha256("different-claim-token")
            else:
                intent.claim_generation += 1
                intent.current_object_generation = intent.claim_generation
            corruption_db.commit()
        raise RuntimeError("prepare commit acknowledgement lost after corruption")

    monkeypatch.setattr(fixture.db, "commit", first_commit_then_corrupt_and_raise)
    result = publish_final_report(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        **storage.callbacks(),
        committed_session_factory=factory,
    )

    assert isinstance(result, PublicationResult)
    assert result.kind == "reconcile_pending"
    assert commit_calls == 1
    assert storage.put_keys == []
    assert storage.deleted_keys == []
    with factory() as verification_db:
        intent = verification_db.get(ResearchPublicationIntent, result.intent_id)
        assert intent is not None and intent.status == "prepared"
        assert (
            verification_db.scalar(
                select(ResearchArtifact).where(
                    ResearchArtifact.artifact_kind == "final_report"
                )
            )
            is None
        )


def test_publish_final_report_returns_pending_without_upload_when_prepare_is_absent(
    research_worker_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    factory = sessionmaker(
        bind=fixture.db.get_bind(), expire_on_commit=False, future=True
    )
    storage = MemoryPublicationStore()
    monkeypatch.setattr(
        fixture.db,
        "commit",
        lambda: (_ for _ in ()).throw(RuntimeError("prepare commit rejected")),
    )

    result = publish_final_report(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        **storage.callbacks(),
        committed_session_factory=factory,
        now=fixture.now + timedelta(seconds=1),
    )

    assert isinstance(result, PublicationResult)
    assert result.kind == "reconcile_pending"
    assert storage.put_keys == []
    assert storage.deleted_keys == []
    with factory() as verification_db:
        assert verification_db.get(ResearchPublicationIntent, result.intent_id) is None
        assert (
            verification_db.scalar(
                select(ResearchArtifact).where(
                    ResearchArtifact.run_id == fixture.run.id,
                    ResearchArtifact.artifact_kind == "final_report",
                )
            )
            is None
        )


def test_publish_final_report_keeps_prepare_unknown_out_of_the_generic_failure_path(
    research_worker_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    storage = MemoryPublicationStore()
    monkeypatch.setattr(
        fixture.db,
        "commit",
        lambda: (_ for _ in ()).throw(
            RuntimeError("prepare commit acknowledgement unavailable")
        ),
    )

    def unavailable_verification_session():
        raise RuntimeError("verification database unavailable")

    result = publish_final_report(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        **storage.callbacks(),
        committed_session_factory=unavailable_verification_session,
        now=fixture.now + timedelta(seconds=1),
    )

    assert isinstance(result, PublicationResult)
    assert result.kind == "reconcile_pending"
    assert storage.put_keys == []
    assert storage.deleted_keys == []
    assert (
        fixture.db.scalar(
            select(ResearchArtifact).where(
                ResearchArtifact.run_id == fixture.run.id,
                ResearchArtifact.artifact_kind == "final_report",
            )
        )
        is None
    )


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

    monkeypatch.setattr(
        research_worker_evidence, "retrieve_query_content", raise_mismatch
    )

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
            top_k=6,
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


def _pending_publication(fixture, storage: MemoryPublicationStore):
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    storage.fail_puts = 1
    result = publish_final_report(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        **local_publication_callbacks(fixture, storage),
    )
    assert isinstance(result, PublicationResult) and result.kind == "reconcile_pending"
    intent = fixture.db.get(ResearchPublicationIntent, result.intent_id)
    assert intent is not None
    return lease, intent


def _add_scheduled_publication_intent(
    fixture,
    *,
    status: str,
    next_reconcile_at: datetime,
) -> ResearchPublicationIntent:
    """Seed a constraint-valid scheduler row without duplicating full provenance."""

    run_id = str(uuid4())
    step_id = str(uuid4())
    attempt_id = str(uuid4())
    artifact_id = str(uuid4())
    payload = b"# Scheduler candidate\n"
    selection = {"factClaimIds": [], "unresolvedClaimIds": []}
    selection_bytes = json.dumps(
        selection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    prefix = f"research/{fixture.run.workspace_id}/{run_id}/{artifact_id}"
    claimed = status == "committing"
    run = ResearchRun(
        id=run_id,
        workspace_id=fixture.run.workspace_id,
        created_by_user_id=fixture.run.created_by_user_id,
        status="running",
        state_version=1,
        next_event_seq=1,
        cost_currency="USD",
        created_at=fixture.now,
        started_at=fixture.now,
        updated_at=fixture.now,
    )
    step = ResearchStep(
        id=step_id,
        workspace_id=fixture.run.workspace_id,
        run_id=run_id,
        execution_snapshot_id=fixture.snapshot.id,
        step_key="artifact_publisher",
        step_kind="artifact_publisher",
        status="running",
        state_version=1,
        max_attempts_snapshot=3,
        current_attempt_number=1,
        input_sha256=sha256(f"scheduler-{run_id}"),
        queued_at=fixture.now,
        started_at=fixture.now,
        created_at=fixture.now,
        updated_at=fixture.now,
    )
    attempt = ResearchStepAttempt(
        id=attempt_id,
        workspace_id=fixture.run.workspace_id,
        step_id=step_id,
        attempt_number=1,
        status="running",
        lease_token_hash=sha256(f"attempt-{attempt_id}"),
        worker_instance_id="scheduler-origin",
        lease_expires_at=fixture.now - timedelta(minutes=10),
        heartbeat_at=fixture.now - timedelta(minutes=11),
        input_sha256=step.input_sha256,
        provider_call_count=0,
        tool_call_count=0,
        input_tokens=0,
        output_tokens=0,
        cost_microunits=0,
        started_at=fixture.now - timedelta(minutes=20),
    )
    intent = ResearchPublicationIntent(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        run_id=run_id,
        step_id=step_id,
        attempt_id=attempt_id,
        execution_snapshot_id=fixture.snapshot.id,
        logical_key="final-report",
        artifact_id=artifact_id,
        object_prefix=prefix,
        current_object_generation=1 if claimed else None,
        current_object_key=f"{prefix}/publication/1/final.md" if claimed else None,
        content_type="text/markdown",
        render_schema_version="final-report-v1",
        payload_bytes=payload,
        byte_size=len(payload),
        content_sha256=hashlib.sha256(payload).hexdigest(),
        selection_json=selection,
        selection_sha256=hashlib.sha256(selection_bytes).hexdigest(),
        status=status,
        state_version=1,
        claim_generation=1 if claimed else 0,
        claim_owner="expired-committer" if claimed else None,
        claim_token_hash=sha256("expired-claim-token") if claimed else None,
        claim_expires_at=(fixture.now - timedelta(minutes=5)) if claimed else None,
        claim_heartbeat_at=(fixture.now - timedelta(minutes=6)) if claimed else None,
        next_reconcile_at=next_reconcile_at,
        reconcile_attempt_count=0,
        created_at=fixture.now - timedelta(minutes=30),
        updated_at=fixture.now - timedelta(minutes=5),
    )
    fixture.db.add_all([run, step, attempt, intent])
    fixture.db.commit()
    return intent


def _claim_compensating_intent(
    fixture,
    intent: ResearchPublicationIntent,
    *,
    lease_token: str,
    requires_attempt_lease: bool,
):
    token = "compensation-owner-token"
    intent.status = "compensating"
    intent.current_object_generation = None
    intent.current_object_key = None
    intent.last_error_code = _COMPENSATION_SWEEP_PENDING
    intent.claim_owner = "compensation-owner"
    intent.claim_token_hash = _token_hash(token)
    intent.claim_expires_at = fixture.now + timedelta(minutes=5)
    intent.claim_heartbeat_at = fixture.now
    intent.next_reconcile_at = fixture.now
    intent.state_version += 1
    fixture.db.commit()
    return _claim_from_intent(
        intent,
        token,
        requires_attempt_lease=requires_attempt_lease,
        attempt_lease_token_hash=(
            _token_hash(lease_token) if requires_attempt_lease else None
        ),
    )


@pytest.mark.parametrize(
    ("requires_attempt_lease", "lease_active", "expected_absent"),
    [
        (True, True, True),
        (True, False, False),
        (False, True, False),
        (False, False, True),
    ],
    ids=[
        "origin-live-lease",
        "origin-expired-lease",
        "reconciler-live-lease",
        "reconciler-expired-lease",
    ],
)
def test_finalize_absent_enforces_origin_and_reconciler_attempt_lease_gate(
    research_worker_db,
    requires_attempt_lease: bool,
    lease_active: bool,
    expected_absent: bool,
) -> None:
    fixture = research_worker_db
    lease, intent = _pending_publication(fixture, MemoryPublicationStore())
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert attempt is not None
    attempt.lease_expires_at = (
        fixture.now + timedelta(minutes=5)
        if lease_active
        else fixture.now - timedelta(minutes=5)
    )
    claim = _claim_compensating_intent(
        fixture,
        intent,
        lease_token=lease.lease_token,
        requires_attempt_lease=requires_attempt_lease,
    )

    assert _finalize_absent(fixture.db, claim) is expected_absent

    fixture.db.expire_all()
    intent = fixture.db.get(ResearchPublicationIntent, intent.id)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert intent is not None and attempt is not None
    assert intent.status == ("absent" if expected_absent else "compensating")
    assert attempt.status == ("failed" if expected_absent else "running")
    if not expected_absent:
        assert intent.claim_owner is None


def test_finalize_absent_cancellation_flushes_attempt_before_idle_check(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    lease, intent = _pending_publication(fixture, MemoryPublicationStore())
    run = fixture.db.get(ResearchRun, fixture.run.id)
    assert run is not None
    run.status = "cancel_requested"
    run.cancel_requested_by_user_id = run.created_by_user_id
    run.cancel_reason_code = "user_requested"
    run.cancel_requested_at = fixture.now
    claim = _claim_compensating_intent(
        fixture,
        intent,
        lease_token=lease.lease_token,
        requires_attempt_lease=False,
    )

    assert _finalize_absent(fixture.db, claim)

    fixture.db.expire_all()
    run = fixture.db.get(ResearchRun, fixture.run.id)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    intent = fixture.db.get(ResearchPublicationIntent, intent.id)
    assert run is not None and run.status == "cancelled"
    assert attempt is not None and attempt.status == "cancelled"
    assert intent is not None and intent.status == "absent"
    assert (
        fixture.db.scalar(
            select(ResearchEvent).where(
                ResearchEvent.run_id == run.id,
                ResearchEvent.event_type == "run_cancelled",
            )
        )
        is not None
    )


@pytest.mark.parametrize("drift", ["approved-snapshot", "step-snapshot"])
def test_finalize_absent_cancellation_rejects_snapshot_drift(
    research_worker_db,
    drift: str,
) -> None:
    fixture = research_worker_db
    lease, intent = _pending_publication(fixture, MemoryPublicationStore())
    run = fixture.db.get(ResearchRun, fixture.run.id)
    step = fixture.db.get(ResearchStep, fixture.step.id)
    assert run is not None and step is not None
    run.status = "cancel_requested"
    run.cancel_requested_by_user_id = run.created_by_user_id
    run.cancel_reason_code = "user_requested"
    run.cancel_requested_at = fixture.now
    if drift == "approved-snapshot":
        run.approved_execution_snapshot_id = None
    else:
        step.execution_snapshot_id = None
    before_event_count = fixture.db.scalar(
        select(func.count()).select_from(ResearchEvent)
    )
    claim = _claim_compensating_intent(
        fixture,
        intent,
        lease_token=lease.lease_token,
        requires_attempt_lease=False,
    )

    assert not _finalize_absent(fixture.db, claim)

    fixture.db.expire_all()
    run = fixture.db.get(ResearchRun, fixture.run.id)
    step = fixture.db.get(ResearchStep, fixture.step.id)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    intent = fixture.db.get(ResearchPublicationIntent, intent.id)
    assert run is not None and run.status == "cancel_requested"
    assert step is not None and step.status == "running"
    assert attempt is not None and attempt.status == "running"
    assert intent is not None and intent.status == "compensating"
    assert intent.claim_owner is None
    assert (
        fixture.db.scalar(select(func.count()).select_from(ResearchEvent))
        == before_event_count
    )


def test_finalize_absent_rejects_replacement_attempt(research_worker_db) -> None:
    fixture = research_worker_db
    lease, intent = _pending_publication(fixture, MemoryPublicationStore())
    step = fixture.db.get(ResearchStep, fixture.step.id)
    original = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert step is not None and original is not None
    replacement = ResearchStepAttempt(
        id=str(uuid4()),
        workspace_id=original.workspace_id,
        step_id=step.id,
        attempt_number=2,
        status="running",
        input_sha256=original.input_sha256,
        lease_token_hash=sha256("replacement-token"),
        lease_expires_at=fixture.now + timedelta(minutes=5),
        worker_instance_id="replacement-worker",
        started_at=fixture.now,
    )
    step.current_attempt_number = 2
    fixture.db.add(replacement)
    claim = _claim_compensating_intent(
        fixture,
        intent,
        lease_token=lease.lease_token,
        requires_attempt_lease=False,
    )

    assert not _finalize_absent(fixture.db, claim)

    fixture.db.expire_all()
    intent = fixture.db.get(ResearchPublicationIntent, intent.id)
    original = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert intent is not None and intent.status == "compensating"
    assert original is not None and original.status == "running"
    assert fixture.db.get(ResearchStepAttempt, replacement.id) is not None


@pytest.mark.parametrize(
    "mutation",
    [
        "object-key",
        "gate-output",
        "direct-prompt",
        "prompt-mapping",
        "content-hash",
        "claim-order",
    ],
)
def test_finalization_rejects_conflict_report_provenance_mutation(
    research_worker_db,
    mutation: str,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    conflict_artifact = fixture.db.scalar(
        select(ResearchArtifact).where(
            ResearchArtifact.artifact_kind == "conflict_report"
        )
    )
    assert conflict_artifact is not None
    gate_attempt = fixture.db.get(
        ResearchStepAttempt, conflict_artifact.generated_by_attempt_id
    )
    assert gate_attempt is not None
    if mutation == "object-key":
        conflict_artifact.object_key = f"{conflict_artifact.object_key}.tampered"
    elif mutation == "gate-output":
        gate_attempt.output_sha256 = sha256("tampered-gate-output")
    elif mutation == "direct-prompt":
        synthesizer_prompt_id = fixture.db.scalar(
            select(ResearchExecutionPromptVersion.prompt_version_id).where(
                ResearchExecutionPromptVersion.execution_snapshot_id
                == fixture.snapshot.id,
                ResearchExecutionPromptVersion.node_key == "synthesizer",
            )
        )
        assert synthesizer_prompt_id is not None
        conflict_artifact.direct_prompt_version_id = synthesizer_prompt_id
    elif mutation == "prompt-mapping":
        prompt_mapping = fixture.db.scalar(
            select(ResearchArtifactPromptVersion).where(
                ResearchArtifactPromptVersion.artifact_id == conflict_artifact.id
            )
        )
        assert prompt_mapping is not None
        fixture.db.delete(prompt_mapping)
    elif mutation == "content-hash":
        conflict_artifact.content_sha256 = sha256("tampered-conflict-payload")
    else:
        claim_mapping = fixture.db.scalar(
            select(ResearchArtifactClaim).where(
                ResearchArtifactClaim.artifact_id == conflict_artifact.id
            )
        )
        assert claim_mapping is not None
        claim_mapping.claim_order = 1
    fixture.db.commit()

    lease = lease_default_step(fixture)
    storage = MemoryPublicationStore()
    result = publish_final_report(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        **local_publication_callbacks(fixture, storage),
    )

    assert isinstance(result, PublicationResult)
    assert result.kind == "reconcile_pending"
    intent = fixture.db.get(ResearchPublicationIntent, result.intent_id)
    assert intent is not None and intent.status == "compensating"
    assert (
        fixture.db.scalar(
            select(ResearchArtifact).where(
                ResearchArtifact.artifact_kind == "final_report"
            )
        )
        is None
    )


@pytest.mark.parametrize("mutation", ["approved-snapshot", "publisher-prompt"])
def test_finalization_rejects_stale_snapshot_or_prompt_identity(
    research_worker_db,
    mutation: str,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    critic_prompt_id = fixture.db.scalar(
        select(ResearchExecutionPromptVersion.prompt_version_id).where(
            ResearchExecutionPromptVersion.execution_snapshot_id == fixture.snapshot.id,
            ResearchExecutionPromptVersion.node_key == "critic",
        )
    )
    assert critic_prompt_id is not None
    lease = lease_default_step(fixture)
    storage = MemoryPublicationStore()
    factory = sessionmaker(
        bind=fixture.db.get_bind(), expire_on_commit=False, future=True
    )
    mutated = False

    def mutate_after_prepare(key: str, content: bytes, content_type: str) -> None:
        nonlocal mutated
        storage.put(key, content, content_type)
        if mutated:
            return
        mutated = True
        with factory() as mutation_db:
            if mutation == "approved-snapshot":
                run = mutation_db.get(ResearchRun, fixture.run.id)
                assert run is not None
                run.approved_execution_snapshot_id = None
            else:
                step = mutation_db.get(ResearchStep, fixture.step.id)
                assert step is not None
                step.prompt_version_id = critic_prompt_id
            mutation_db.commit()

    result = publish_final_report(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        store_bytes=mutate_after_prepare,
        load_bytes=storage.get,
        list_keys=storage.list,
        cleanup_bytes=storage.delete,
        committed_session_factory=factory,
    )

    assert isinstance(result, PublicationResult)
    assert result.kind == "reconcile_pending"
    assert mutated
    intent = fixture.db.get(ResearchPublicationIntent, result.intent_id)
    assert intent is not None and intent.status == "compensating"
    assert (
        fixture.db.scalar(
            select(ResearchArtifact).where(
                ResearchArtifact.artifact_kind == "final_report"
            )
        )
        is None
    )


def test_storage_callback_cannot_mutate_frozen_payload_and_selection_into_adoption(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    storage = MemoryPublicationStore()
    factory = sessionmaker(
        bind=fixture.db.get_bind(), expire_on_commit=False, future=True
    )
    mutation_count = 0

    def mutate_after_put(key: str, content: bytes, content_type: str) -> None:
        nonlocal mutation_count
        storage.put(key, content, content_type)
        if mutation_count:
            return
        mutation_count += 1
        with factory() as mutation_db:
            intent = mutation_db.scalar(
                select(ResearchPublicationIntent).where(
                    ResearchPublicationIntent.attempt_id == lease.attempt_id
                )
            )
            assert intent is not None
            mutated_payload = b"# Concurrent but internally consistent mutation\n"
            mutated_selection = {
                "factClaimIds": [],
                "unresolvedClaimIds": [],
            }
            selection_bytes = json.dumps(
                mutated_selection,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            intent.payload_bytes = mutated_payload
            intent.byte_size = len(mutated_payload)
            intent.content_sha256 = hashlib.sha256(mutated_payload).hexdigest()
            intent.selection_json = mutated_selection
            intent.selection_sha256 = hashlib.sha256(selection_bytes).hexdigest()
            mutation_db.commit()

    result = publish_final_report(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        store_bytes=mutate_after_put,
        load_bytes=storage.get,
        list_keys=storage.list,
        cleanup_bytes=storage.delete,
        committed_session_factory=factory,
    )

    assert isinstance(result, PublicationResult)
    assert result.kind == "reconcile_pending"
    assert mutation_count == 1
    assert len(storage.put_keys) == 1
    assert (
        fixture.db.scalar(
            select(ResearchArtifact).where(
                ResearchArtifact.artifact_kind == "final_report"
            )
        )
        is None
    )


def _add_foreign_artifact(
    fixture,
    intent: ResearchPublicationIntent,
    conflict: str,
) -> ResearchArtifact:
    if conflict == "id":
        artifact_id = intent.artifact_id
        object_key = (
            f"research/{fixture.run.workspace_id}/{fixture.run.id}/foreign-id.md"
        )
    elif conflict == "key":
        artifact_id = str(uuid4())
        object_key = f"{intent.object_prefix}/publication/1/final.md"
    else:
        artifact_id = str(uuid4())
        object_key = f"{intent.object_prefix}/foreign-prefix.md"
    artifact = ResearchArtifact(
        id=artifact_id,
        workspace_id=fixture.run.workspace_id,
        run_id=fixture.run.id,
        generated_by_step_id=fixture.step.id,
        generated_by_attempt_id=intent.attempt_id,
        artifact_kind="trace_export",
        visibility="internal",
        logical_key=f"foreign-{conflict}-{uuid4()}",
        schema_version="1",
        object_key=object_key,
        content_type="text/plain",
        byte_size=7,
        content_sha256=sha256("foreign"),
        workflow_version_id=fixture.snapshot.workflow_version_id,
        direct_prompt_version_id=fixture.step.prompt_version_id,
        generation_provider=fixture.snapshot.generation_provider,
        generation_model=fixture.snapshot.generation_model,
        retention_class="workspace_lifetime",
        created_at=fixture.now,
    )
    fixture.db.add(artifact)
    fixture.db.commit()
    return artifact


@pytest.mark.parametrize("conflict", ["id", "key", "prefix"])
def test_compensation_never_deletes_storage_owned_by_foreign_artifact(
    research_worker_db,
    conflict: str,
) -> None:
    fixture = research_worker_db
    storage = MemoryPublicationStore()
    lease, intent = _pending_publication(fixture, storage)
    del lease
    intent.status = "compensating"
    intent.current_object_generation = None
    intent.current_object_key = None
    intent.claim_owner = None
    intent.claim_token_hash = None
    intent.claim_expires_at = None
    intent.claim_heartbeat_at = None
    intent.next_reconcile_at = fixture.now - timedelta(seconds=1)
    fixture.db.commit()
    foreign = _add_foreign_artifact(fixture, intent, conflict)
    storage.objects[foreign.object_key] = (b"foreign", "text/plain")

    assert reconcile_one_publication_intent(
        fixture.db,
        worker_instance_id=f"foreign-{conflict}-guard",
        **local_publication_callbacks(fixture, storage),
    )

    fixture.db.expire_all()
    intent = fixture.db.get(ResearchPublicationIntent, intent.id)
    assert intent is not None and intent.status == "compensating"
    assert intent.last_error_code == "research_publication_artifact_ownership_conflict"
    assert storage.objects[foreign.object_key][0] == b"foreign"
    assert storage.deleted_keys == []
    assert storage.list_prefixes == []


@pytest.mark.parametrize("corruption", ["selection", "payload"])
def test_permanent_frozen_integrity_conflict_can_complete_two_pass_compensation(
    research_worker_db,
    corruption: str,
) -> None:
    fixture = research_worker_db
    storage = MemoryPublicationStore()
    lease, intent = _pending_publication(fixture, storage)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert attempt is not None
    attempt.lease_expires_at = fixture.now - timedelta(seconds=1)
    if corruption == "selection":
        invalid_selection = {
            "factClaimIds": list(intent.selection_json["factClaimIds"]),
            "unresolvedClaimIds": list(intent.selection_json["unresolvedClaimIds"]),
            "unexpected": True,
        }
        intent.selection_json = invalid_selection
        intent.selection_sha256 = hashlib.sha256(
            json.dumps(
                invalid_selection,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    else:
        intent.payload_bytes = bytes(intent.payload_bytes) + b"corrupt"
        intent.byte_size = len(intent.payload_bytes)
    intent.next_reconcile_at = fixture.now - timedelta(seconds=1)
    fixture.db.commit()
    storage.put_keys.clear()

    # The first pass detects the permanent frozen-data conflict before any PUT
    # and releases the durable intent into the compensation lane.
    assert reconcile_one_publication_intent(
        fixture.db,
        worker_instance_id=f"frozen-{corruption}-detect",
        observation_seconds=1,
        **local_publication_callbacks(fixture, storage),
    )
    fixture.db.expire_all()
    intent = fixture.db.get(ResearchPublicationIntent, intent.id)
    assert intent is not None and intent.status == "compensating"
    assert intent.claim_owner is None
    assert storage.put_keys == []

    # Compensation deliberately validates only exact ownership/scope.  It may
    # therefore sweep content whose frozen payload/selection is already known
    # to be corrupt, while retaining the two-empty-sweep observation contract.
    for worker in ("first-empty-sweep", "second-empty-sweep"):
        intent.next_reconcile_at = fixture.now - timedelta(seconds=1)
        fixture.db.commit()
        assert reconcile_one_publication_intent(
            fixture.db,
            worker_instance_id=f"frozen-{corruption}-{worker}",
            observation_seconds=1,
            **local_publication_callbacks(fixture, storage),
        )
        fixture.db.expire_all()
        intent = fixture.db.get(ResearchPublicationIntent, intent.id)
        assert intent is not None

    assert intent.status == "absent"
    assert len(storage.list_prefixes) == 4
    assert storage.deleted_keys == []
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert attempt is not None and attempt.status == "failed"


def test_tampered_compensation_prefix_never_reaches_storage_and_stays_durable(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    storage = MemoryPublicationStore()
    _lease, intent = _pending_publication(fixture, storage)
    intent.object_prefix = (
        f"research/{fixture.run.workspace_id}/{fixture.run.id}/different-artifact"
    )
    intent.next_reconcile_at = fixture.now - timedelta(seconds=1)
    fixture.db.commit()
    storage.put_keys.clear()
    storage.get_keys.clear()

    assert reconcile_one_publication_intent(
        fixture.db,
        worker_instance_id="tampered-prefix-detect",
        observation_seconds=1,
        **local_publication_callbacks(fixture, storage),
    )

    fixture.db.expire_all()
    intent = fixture.db.get(ResearchPublicationIntent, intent.id)
    assert intent is not None and intent.status == "compensating"
    assert intent.resolved_at is None
    assert storage.put_keys == []
    assert storage.get_keys == []
    assert storage.list_prefixes == []
    assert storage.deleted_keys == []


@pytest.mark.parametrize(
    "mutation",
    [
        "snapshot-model",
        "plan-asset",
        "approval-artifact-hash",
        "workflow-binding",
        "prompt-contract",
        "prompt-contract-coherent",
        "workflow-contract-coherent",
    ],
)
def test_finalize_rejects_mutated_execution_snapshot_source_graph(
    research_worker_db,
    mutation: str,
) -> None:
    fixture = research_worker_db
    storage = MemoryPublicationStore()
    lease, intent = _pending_publication(fixture, storage)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert attempt is not None
    if mutation == "snapshot-model":
        fixture.snapshot.generation_model = "tampered-model"
    elif mutation == "plan-asset":
        plan_asset = fixture.db.scalar(
            select(ResearchPlanRevisionAsset).where(
                ResearchPlanRevisionAsset.plan_revision_id
                == fixture.snapshot.approved_plan_revision_id
            )
        )
        assert plan_asset is not None
        plan_asset.asset_title_snapshot = "tampered frozen title"
    elif mutation == "approval-artifact-hash":
        approval = fixture.db.get(HumanDecision, fixture.snapshot.approval_decision_id)
        assert approval is not None
        approval.input_artifact_sha256 = "a" * 64
    elif mutation == "workflow-binding":
        binding = fixture.db.scalar(
            select(WorkflowPromptBinding).where(
                WorkflowPromptBinding.workflow_version_id
                == fixture.snapshot.workflow_version_id,
                WorkflowPromptBinding.node_key == "synthesizer",
            )
        )
        planner_binding = fixture.db.scalar(
            select(WorkflowPromptBinding).where(
                WorkflowPromptBinding.workflow_version_id
                == fixture.snapshot.workflow_version_id,
                WorkflowPromptBinding.node_key == "planner",
            )
        )
        assert binding is not None and planner_binding is not None
        binding.prompt_version_id = planner_binding.prompt_version_id
    elif mutation in {"prompt-contract", "prompt-contract-coherent"}:
        binding = fixture.db.scalar(
            select(WorkflowPromptBinding).where(
                WorkflowPromptBinding.workflow_version_id
                == fixture.snapshot.workflow_version_id,
                WorkflowPromptBinding.node_key == "planner",
            )
        )
        assert binding is not None
        prompt = fixture.db.get(PromptVersion, binding.prompt_version_id)
        assert prompt is not None
        prompt.template_text += " tampered"
        if mutation == "prompt-contract-coherent":
            prompt.variables_schema_json = {
                **prompt.variables_schema_json,
                "coherentTamper": {"type": "string"},
            }
            prompt.template_sha256 = canonical_sha256(
                {
                    "template": prompt.template_text,
                    "variables": prompt.variables_schema_json,
                }
            )
    else:
        workflow = fixture.db.get(WorkflowVersion, fixture.snapshot.workflow_version_id)
        assert workflow is not None
        workflow.manifest_json = {
            **workflow.manifest_json,
            "coherentTamper": True,
        }
        workflow.manifest_sha256 = canonical_sha256(workflow.manifest_json)
    attempt.lease_expires_at = fixture.now - timedelta(seconds=1)
    intent.next_reconcile_at = fixture.now - timedelta(seconds=1)
    fixture.db.commit()
    storage.put_keys.clear()

    assert reconcile_one_publication_intent(
        fixture.db,
        worker_instance_id=f"snapshot-graph-{mutation}",
        observation_seconds=1,
        **local_publication_callbacks(fixture, storage),
    )

    fixture.db.expire_all()
    intent = fixture.db.get(ResearchPublicationIntent, intent.id)
    assert intent is not None and intent.status == "compensating"
    assert fixture.db.get(ResearchArtifact, intent.artifact_id) is None
    assert storage.objects == {}
    terminal_count = fixture.db.scalar(
        select(func.count())
        .select_from(ResearchEvent)
        .where(
            ResearchEvent.run_id == fixture.run.id,
            ResearchEvent.event_type.in_(
                ("step_succeeded", "artifact_published", "run_completed")
            ),
        )
    )
    assert terminal_count == 0


def test_direct_publish_rechecks_release_after_prepare_commit_and_storage_write(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    storage = MemoryPublicationStore()
    factory = sessionmaker(
        bind=fixture.db.get_bind(), expire_on_commit=False, future=True
    )
    workflow_strong_ref = fixture.db.get(
        WorkflowVersion, fixture.snapshot.workflow_version_id
    )
    synthesizer_binding_strong_ref = fixture.db.scalar(
        select(WorkflowPromptBinding).where(
            WorkflowPromptBinding.workflow_version_id
            == fixture.snapshot.workflow_version_id,
            WorkflowPromptBinding.node_key == "synthesizer",
        )
    )
    assert workflow_strong_ref is not None
    assert synthesizer_binding_strong_ref is not None
    prompt_strong_ref = fixture.db.get(
        PromptVersion, synthesizer_binding_strong_ref.prompt_version_id
    )
    assert prompt_strong_ref is not None
    release_mutated = False

    def store_then_mutate_release(key: str, content: bytes, content_type: str) -> None:
        nonlocal release_mutated
        storage.put(key, content, content_type)
        if release_mutated:
            return
        release_mutated = True
        with factory() as mutation_db:
            binding = mutation_db.scalar(
                select(WorkflowPromptBinding).where(
                    WorkflowPromptBinding.workflow_version_id
                    == fixture.snapshot.workflow_version_id,
                    WorkflowPromptBinding.node_key == "synthesizer",
                )
            )
            assert binding is not None
            prompt = mutation_db.get(PromptVersion, binding.prompt_version_id)
            assert prompt is not None
            prompt.template_text += " coherent post-prepare tamper"
            prompt.variables_schema_json = {
                **prompt.variables_schema_json,
                "postPrepareTamper": {"type": "boolean"},
            }
            prompt.template_sha256 = canonical_sha256(
                {
                    "template": prompt.template_text,
                    "variables": prompt.variables_schema_json,
                }
            )
            mutation_db.commit()

    result = publish_final_report(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        store_bytes=store_then_mutate_release,
        load_bytes=storage.get,
        list_keys=storage.list,
        cleanup_bytes=storage.delete,
        committed_session_factory=factory,
        observation_seconds=1,
    )

    assert isinstance(result, PublicationResult)
    assert result.kind == "reconcile_pending"
    fixture.db.expire_all()
    intent = fixture.db.get(ResearchPublicationIntent, result.intent_id)
    assert intent is not None and intent.status == "compensating"
    assert fixture.db.get(ResearchArtifact, intent.artifact_id) is None
    assert storage.objects == {}
    assert storage.deleted_keys
    assert "postPrepareTamper" in prompt_strong_ref.variables_schema_json
    terminal_count = fixture.db.scalar(
        select(func.count())
        .select_from(ResearchEvent)
        .where(
            ResearchEvent.run_id == fixture.run.id,
            ResearchEvent.event_type.in_(
                ("step_succeeded", "artifact_published", "run_completed")
            ),
        )
    )
    assert terminal_count == 0


def test_temporary_release_loader_database_error_retries_without_compensation(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    storage = MemoryPublicationStore()
    lease, intent = _pending_publication(fixture, storage)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert attempt is not None
    attempt.lease_expires_at = fixture.now - timedelta(seconds=1)
    intent.next_reconcile_at = fixture.now - timedelta(seconds=1)
    provider_calls_before = attempt.provider_call_count
    tool_calls_before = attempt.tool_call_count
    fixture.db.commit()
    storage.put_keys.clear()

    def unavailable_release_loader(_db, _snapshot):
        raise OperationalError(
            "SELECT publication release",
            {},
            RuntimeError("temporary database outage"),
        )

    assert reconcile_one_publication_intent_neutral(
        fixture.db,
        worker_instance_id="temporary-release-loader-db-error",
        prompt_loader=unavailable_release_loader,
        observation_seconds=1,
        **local_publication_callbacks(fixture, storage),
    )

    fixture.db.expire_all()
    intent = fixture.db.get(ResearchPublicationIntent, intent.id)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert intent is not None and intent.status == "prepared"
    assert intent.last_error_code == "OperationalError"
    assert intent.claim_owner is None
    assert intent.current_object_key is None
    assert attempt is not None and attempt.status == "running"
    assert attempt.provider_call_count == provider_calls_before
    assert attempt.tool_call_count == tool_calls_before
    assert fixture.db.get(ResearchArtifact, intent.artifact_id) is None
    assert len(storage.objects) == 1
    assert storage.deleted_keys == []
    assert storage.list_prefixes == []


def test_finalize_rejects_claim_text_hash_mutation_that_no_longer_matches_payload(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    storage = MemoryPublicationStore()
    lease, intent = _pending_publication(fixture, storage)
    fact_id = intent.selection_json["factClaimIds"][0]
    fact = fixture.db.get(ResearchClaim, fact_id)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert fact is not None and attempt is not None
    fact.statement_text = "Coherently rehashed but not present in frozen report."
    fact.statement_sha256 = hashlib.sha256(fact.statement_text.encode()).hexdigest()
    attempt.lease_expires_at = fixture.now - timedelta(seconds=1)
    intent.next_reconcile_at = fixture.now - timedelta(seconds=1)
    fixture.db.commit()
    storage.put_keys.clear()

    assert reconcile_one_publication_intent(
        fixture.db,
        worker_instance_id="claim-payload-cross-check",
        observation_seconds=1,
        **local_publication_callbacks(fixture, storage),
    )

    fixture.db.expire_all()
    intent = fixture.db.get(ResearchPublicationIntent, intent.id)
    assert intent is not None and intent.status == "compensating"
    assert fixture.db.get(ResearchArtifact, intent.artifact_id) is None
    assert storage.objects == {}


def test_committed_terminal_sweep_retries_when_adopted_object_is_missing(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    storage = MemoryPublicationStore()
    artifact_id = publish_final_report(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        **local_publication_callbacks(fixture, storage),
    )
    assert isinstance(artifact_id, str)
    intent = fixture.db.scalar(
        select(ResearchPublicationIntent).where(
            ResearchPublicationIntent.attempt_id == lease.attempt_id
        )
    )
    assert intent is not None and intent.adopted_object_key is not None
    storage.objects.pop(intent.adopted_object_key)

    for pass_number in range(2):
        intent.orphan_sweep_after = fixture.now - timedelta(seconds=1)
        fixture.db.commit()
        assert reconcile_one_publication_intent(
            fixture.db,
            worker_instance_id=f"missing-adopted-{pass_number}",
            **local_publication_callbacks(fixture, storage),
        )
        fixture.db.expire_all()
        intent = fixture.db.get(ResearchPublicationIntent, intent.id)
        assert intent is not None and intent.status == "committed"
        assert intent.last_error_code == "research_publication_adopted_object_missing"
        assert fixture.db.get(ResearchArtifact, artifact_id) is not None


def test_absent_terminal_sweep_removes_old_prefix_late_put_after_replacement_commits(
    research_worker_db,
) -> None:
    """A retry's committed Artifact must not suppress cleanup of an older absent saga."""

    fixture = research_worker_db
    storage = MemoryPublicationStore()
    fact, unresolved = make_final_publication_chain(fixture)
    first_lease = lease_default_step(fixture)
    storage.fail_puts = 1
    pending = publish_final_report(
        fixture.db,
        attempt_id=first_lease.attempt_id,
        lease_token=first_lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        **local_publication_callbacks(fixture, storage),
    )
    assert isinstance(pending, PublicationResult)
    assert pending.kind == "reconcile_pending"
    old_intent = fixture.db.get(ResearchPublicationIntent, pending.intent_id)
    assert old_intent is not None
    old_prefix = old_intent.object_prefix
    old_late_key = f"{old_prefix}/publication/1/final.md"
    compensation_claim = _claim_compensating_intent(
        fixture,
        old_intent,
        lease_token=first_lease.lease_token,
        requires_attempt_lease=True,
    )
    assert _finalize_absent(fixture.db, compensation_claim)

    # The ordinary retry path publishes a new Artifact under a distinct prefix.
    replacement_lease = lease_default_step(fixture)
    replacement_id = publish_final_report(
        fixture.db,
        attempt_id=replacement_lease.attempt_id,
        lease_token=replacement_lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        **local_publication_callbacks(fixture, storage),
    )
    assert isinstance(replacement_id, str)
    replacement_artifact = fixture.db.get(ResearchArtifact, replacement_id)
    assert replacement_artifact is not None
    replacement_key = replacement_artifact.object_key
    assert replacement_key != old_late_key
    assert replacement_key in storage.objects

    # A response-lost PUT from the absent generation arrives after replacement
    # commit.  The old terminal sweep owns only its immutable old prefix.
    storage.objects[old_late_key] = (b"late old generation", "text/markdown")
    old_intent = fixture.db.get(ResearchPublicationIntent, pending.intent_id)
    replacement_intent = fixture.db.scalar(
        select(ResearchPublicationIntent).where(
            ResearchPublicationIntent.committed_artifact_id == replacement_id
        )
    )
    assert old_intent is not None and replacement_intent is not None
    old_intent.orphan_sweep_after = fixture.now - timedelta(minutes=2)
    replacement_intent.orphan_sweep_after = fixture.now + timedelta(minutes=2)
    fixture.db.commit()

    assert reconcile_one_publication_intent(
        fixture.db,
        worker_instance_id="old-absent-terminal-sweep",
        **local_publication_callbacks(fixture, storage),
    )

    fixture.db.expire_all()
    old_intent = fixture.db.get(ResearchPublicationIntent, pending.intent_id)
    replacement_intent = fixture.db.get(
        ResearchPublicationIntent, replacement_intent.id
    )
    assert old_intent is not None and old_intent.status == "absent"
    assert replacement_intent is not None and replacement_intent.status == "committed"
    assert old_late_key not in storage.objects
    assert replacement_key in storage.objects
    assert storage.deleted_keys == [old_late_key]


def test_terminal_sweep_fails_closed_when_foreign_artifact_appears_after_list(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    storage = MemoryPublicationStore()
    lease, intent = _pending_publication(fixture, storage)
    compensation_claim = _claim_compensating_intent(
        fixture,
        intent,
        lease_token=lease.lease_token,
        requires_attempt_lease=True,
    )
    assert _finalize_absent(fixture.db, compensation_claim)
    late_key = f"{intent.object_prefix}/publication/1/final.md"
    storage.objects[late_key] = (b"late response-lost PUT", "text/markdown")
    intent = fixture.db.get(ResearchPublicationIntent, intent.id)
    assert intent is not None
    intent.orphan_sweep_after = fixture.now - timedelta(seconds=1)
    fixture.db.commit()
    inserted = False

    def list_then_insert_foreign_artifact(prefix: str) -> list[str]:
        nonlocal inserted
        keys = storage.list(prefix)
        if not inserted:
            inserted = True
            _add_foreign_artifact(fixture, intent, "prefix")
        return keys

    callbacks = local_publication_callbacks(fixture, storage)
    callbacks["list_keys"] = list_then_insert_foreign_artifact
    assert reconcile_one_publication_intent(
        fixture.db,
        worker_instance_id="terminal-list-race",
        **callbacks,
    )

    fixture.db.expire_all()
    intent = fixture.db.get(ResearchPublicationIntent, intent.id)
    assert inserted
    assert intent is not None and intent.status == "absent"
    assert intent.last_error_code == "research_publication_artifact_ownership_conflict"
    assert late_key in storage.objects
    assert storage.deleted_keys == []


def test_committed_terminal_sweep_fails_closed_on_foreign_artifact_after_list(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    storage = MemoryPublicationStore()
    artifact_id = publish_final_report(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        **local_publication_callbacks(fixture, storage),
    )
    assert isinstance(artifact_id, str)
    intent = fixture.db.scalar(
        select(ResearchPublicationIntent).where(
            ResearchPublicationIntent.committed_artifact_id == artifact_id
        )
    )
    artifact = fixture.db.get(ResearchArtifact, artifact_id)
    assert intent is not None and artifact is not None
    old_key = f"{intent.object_prefix}/publication/999/final.md"
    storage.objects[old_key] = (b"old committed generation", "text/markdown")
    intent.orphan_sweep_after = fixture.now - timedelta(seconds=1)
    fixture.db.commit()
    inserted_artifact: ResearchArtifact | None = None

    def list_then_insert_foreign_artifact(prefix: str) -> list[str]:
        nonlocal inserted_artifact
        keys = storage.list(prefix)
        if inserted_artifact is None:
            inserted_artifact = _add_foreign_artifact(fixture, intent, "prefix")
            storage.objects[inserted_artifact.object_key] = (b"foreign", "text/plain")
        return keys

    callbacks = local_publication_callbacks(fixture, storage)
    callbacks["list_keys"] = list_then_insert_foreign_artifact
    assert reconcile_one_publication_intent(
        fixture.db,
        worker_instance_id="committed-terminal-list-race",
        **callbacks,
    )

    fixture.db.expire_all()
    intent = fixture.db.get(ResearchPublicationIntent, intent.id)
    assert inserted_artifact is not None
    assert intent is not None and intent.status == "committed"
    assert intent.last_error_code == "research_publication_artifact_ownership_conflict"
    assert artifact.object_key in storage.objects
    assert old_key in storage.objects
    assert inserted_artifact.object_key in storage.objects
    assert storage.deleted_keys == []


def test_due_terminal_sweep_wins_earliest_schedule_under_nonterminal_backlog(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    storage = MemoryPublicationStore()
    fact, unresolved = make_final_publication_chain(fixture)
    first_lease = lease_default_step(fixture)
    storage.fail_puts = 1
    first = publish_final_report(
        fixture.db,
        attempt_id=first_lease.attempt_id,
        lease_token=first_lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        **local_publication_callbacks(fixture, storage),
    )
    assert isinstance(first, PublicationResult)
    old_intent = fixture.db.get(ResearchPublicationIntent, first.intent_id)
    assert old_intent is not None
    old_claim = _claim_compensating_intent(
        fixture,
        old_intent,
        lease_token=first_lease.lease_token,
        requires_attempt_lease=True,
    )
    assert _finalize_absent(fixture.db, old_claim)

    replacement_lease = lease_default_step(fixture)
    storage.fail_puts = 1
    replacement = publish_final_report(
        fixture.db,
        attempt_id=replacement_lease.attempt_id,
        lease_token=replacement_lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        **local_publication_callbacks(fixture, storage),
    )
    assert isinstance(replacement, PublicationResult)
    active_intent = fixture.db.get(ResearchPublicationIntent, replacement.intent_id)
    assert active_intent is not None and active_intent.status == "prepared"
    before_attempts = active_intent.reconcile_attempt_count
    old_prefix = f"{old_intent.object_prefix}/"
    storage.list_prefixes.clear()

    # Keep the nonterminal retry due on both turns.  The older terminal schedule
    # must be selected each time rather than being starved by the active backlog.
    for worker_id in ("fairness-terminal-first", "fairness-terminal-second"):
        old_intent = fixture.db.get(ResearchPublicationIntent, old_intent.id)
        active_intent = fixture.db.get(ResearchPublicationIntent, active_intent.id)
        assert old_intent is not None and active_intent is not None
        old_intent.orphan_sweep_after = fixture.now - timedelta(minutes=2)
        active_intent.next_reconcile_at = fixture.now - timedelta(minutes=1)
        fixture.db.commit()
        assert reconcile_one_publication_intent(
            fixture.db,
            worker_instance_id=worker_id,
            **local_publication_callbacks(fixture, storage),
        )

    fixture.db.expire_all()
    active_intent = fixture.db.get(ResearchPublicationIntent, active_intent.id)
    assert active_intent is not None and active_intent.status == "prepared"
    assert active_intent.reconcile_attempt_count == before_attempts
    assert storage.list_prefixes == [old_prefix, old_prefix, old_prefix, old_prefix]


def test_scheduler_uses_global_due_order_ahead_of_later_expired_committing(
    research_worker_db,
) -> None:
    """Committing recovery cannot permanently jump older prepared/terminal work."""

    fixture = research_worker_db
    storage = MemoryPublicationStore()
    lease, terminal = _pending_publication(fixture, storage)
    terminal_claim = _claim_compensating_intent(
        fixture,
        terminal,
        lease_token=lease.lease_token,
        requires_attempt_lease=True,
    )
    assert _finalize_absent(fixture.db, terminal_claim)
    terminal = fixture.db.get(ResearchPublicationIntent, terminal.id)
    assert terminal is not None
    terminal.orphan_sweep_after = fixture.now - timedelta(minutes=20)
    fixture.db.commit()
    prepared = _add_scheduled_publication_intent(
        fixture,
        status="prepared",
        next_reconcile_at=fixture.now - timedelta(minutes=30),
    )
    committing = _add_scheduled_publication_intent(
        fixture,
        status="committing",
        next_reconcile_at=fixture.now - timedelta(minutes=10),
    )

    assert reconcile_one_publication_intent(
        fixture.db,
        worker_instance_id="global-order-prepared",
        **local_publication_callbacks(fixture, storage),
    )
    fixture.db.expire_all()
    prepared = fixture.db.get(ResearchPublicationIntent, prepared.id)
    committing = fixture.db.get(ResearchPublicationIntent, committing.id)
    terminal = fixture.db.get(ResearchPublicationIntent, terminal.id)
    assert prepared is not None and prepared.reconcile_attempt_count == 1
    assert committing is not None and committing.reconcile_attempt_count == 0
    assert terminal is not None and terminal.last_error_code is None

    # One call owns one responsibility.  The next globally due item is the
    # terminal sweep; the later expired committing row still must not jump it.
    assert reconcile_one_publication_intent(
        fixture.db,
        worker_instance_id="global-order-terminal",
        **local_publication_callbacks(fixture, storage),
    )
    fixture.db.expire_all()
    committing = fixture.db.get(ResearchPublicationIntent, committing.id)
    terminal = fixture.db.get(ResearchPublicationIntent, terminal.id)
    assert committing is not None and committing.reconcile_attempt_count == 0
    assert terminal is not None
    assert terminal.last_error_code == "publication_terminal_sweep_pending"


@pytest.mark.parametrize(
    ("event_type", "step_scoped"),
    [
        ("step_succeeded", True),
        ("artifact_published", False),
        ("run_completed", False),
    ],
)
def test_finalization_rejects_terminal_event_with_alternate_dedupe_key(
    research_worker_db,
    event_type: str,
    step_scoped: bool,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    run = fixture.db.get(ResearchRun, fixture.run.id)
    assert run is not None
    if event_type != "artifact_published":
        fixture.db.add(
            ResearchEvent(
                workspace_id=run.workspace_id,
                run_id=run.id,
                seq=run.next_event_seq,
                event_type=event_type,
                event_schema_version="1",
                step_id=fixture.step.id if step_scoped else None,
                attempt_id=lease.attempt_id if step_scoped else None,
                dedupe_key=f"alternate-terminal:{event_type}:{uuid4()}",
                payload_json={"tampered": True},
                created_at=fixture.now,
            )
        )
        run.next_event_seq += 1
        fixture.db.commit()
    storage = MemoryPublicationStore()
    factory = sessionmaker(
        bind=fixture.db.get_bind(), expire_on_commit=False, future=True
    )
    injected_artifact_event = False

    def store_with_alternate_artifact_event(
        key: str, content: bytes, content_type: str
    ) -> None:
        nonlocal injected_artifact_event
        storage.put(key, content, content_type)
        if event_type != "artifact_published" or injected_artifact_event:
            return
        injected_artifact_event = True
        with factory() as event_db:
            intent = event_db.scalar(
                select(ResearchPublicationIntent).where(
                    ResearchPublicationIntent.attempt_id == lease.attempt_id
                )
            )
            locked_run = event_db.get(ResearchRun, fixture.run.id)
            assert intent is not None and locked_run is not None
            event_db.add(
                ResearchEvent(
                    workspace_id=locked_run.workspace_id,
                    run_id=locked_run.id,
                    seq=locked_run.next_event_seq,
                    event_type="artifact_published",
                    event_schema_version="1",
                    step_id=None,
                    attempt_id=None,
                    dedupe_key=f"alternate-terminal:artifact_published:{uuid4()}",
                    payload_json={"artifactId": intent.artifact_id},
                    created_at=fixture.now,
                )
            )
            locked_run.next_event_seq += 1
            event_db.commit()

    result = publish_final_report(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,),
        store_bytes=store_with_alternate_artifact_event,
        load_bytes=storage.get,
        list_keys=storage.list,
        cleanup_bytes=storage.delete,
        committed_session_factory=factory,
    )

    assert isinstance(result, PublicationResult)
    assert result.kind == "reconcile_pending"
    assert (
        fixture.db.scalar(
            select(ResearchArtifact).where(
                ResearchArtifact.artifact_kind == "final_report"
            )
        )
        is None
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "run-status",
        "run-finished",
        "run-failure",
        "step-status",
        "step-finished",
        "step-error",
        "attempt-status",
        "attempt-output",
        "attempt-finished",
        "attempt-lease",
        "event-schema",
        "event-type",
        "event-payload",
        "event-order",
        "claim-mapping",
        "prompt-mapping",
    ],
)
def test_committed_replay_fails_closed_on_terminal_projection_mutation(
    research_worker_db,
    mutation: str,
) -> None:
    fixture = research_worker_db
    fact, unresolved = make_final_publication_chain(fixture)
    lease = lease_default_step(fixture)
    storage = MemoryPublicationStore()
    arguments = {
        "attempt_id": lease.attempt_id,
        "lease_token": lease.lease_token,
        "fact_claim_ids": (fact.id,),
        "unresolved_claim_ids": (unresolved.id,),
        **local_publication_callbacks(fixture, storage),
    }
    artifact_id = publish_final_report(fixture.db, **arguments)
    assert isinstance(artifact_id, str)
    run = fixture.db.get(ResearchRun, fixture.run.id)
    step = fixture.db.get(ResearchStep, fixture.step.id)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    events = list(
        fixture.db.scalars(
            select(ResearchEvent)
            .where(
                ResearchEvent.run_id == fixture.run.id,
                ResearchEvent.event_type.in_(
                    ("step_succeeded", "artifact_published", "run_completed")
                ),
            )
            .order_by(ResearchEvent.seq)
        ).all()
    )
    assert run is not None and step is not None and attempt is not None
    if mutation == "run-status":
        # Keep the row schema-valid while proving that a different terminal
        # projection cannot be mistaken for the committed publication result.
        run.status = "failed"
        run.failure_code = "tampered"
        run.failure_message = "tampered"
    elif mutation == "run-finished":
        run.finished_at += timedelta(microseconds=1)
    elif mutation == "run-failure":
        run.failure_code = "tampered"
    elif mutation == "step-status":
        step.status = "failed"
        step.error_code = "tampered"
        step.error_message = "tampered"
    elif mutation == "step-finished":
        step.finished_at += timedelta(microseconds=1)
    elif mutation == "step-error":
        step.error_code = "tampered"
    elif mutation == "attempt-status":
        attempt.status = "failed"
        attempt.error_code = "tampered"
        attempt.error_message = "tampered"
    elif mutation == "attempt-output":
        attempt.output_sha256 = sha256("tampered")
    elif mutation == "attempt-finished":
        attempt.finished_at += timedelta(microseconds=1)
    elif mutation == "attempt-lease":
        attempt.lease_expires_at = fixture.now + timedelta(minutes=5)
    elif mutation == "event-schema":
        events[0].event_schema_version = "2"
    elif mutation == "event-type":
        events[0].event_type = "step_failed"
    elif mutation == "event-payload":
        events[1].payload_json = {**events[1].payload_json, "byteSize": 0}
    elif mutation == "event-order":
        first_seq, second_seq = events[0].seq, events[1].seq
        events[0].seq = 10_000
        fixture.db.flush()
        events[1].seq = first_seq
        fixture.db.flush()
        events[0].seq = second_seq
    elif mutation == "claim-mapping":
        mapping = fixture.db.scalar(
            select(ResearchArtifactClaim).where(
                ResearchArtifactClaim.artifact_id == artifact_id
            )
        )
        assert mapping is not None
        fixture.db.delete(mapping)
    else:
        mapping = fixture.db.scalar(
            select(ResearchArtifactPromptVersion).where(
                ResearchArtifactPromptVersion.artifact_id == artifact_id
            )
        )
        assert mapping is not None
        fixture.db.delete(mapping)
    fixture.db.commit()
    storage.put_keys.clear()

    replay = publish_final_report(fixture.db, **arguments)

    assert isinstance(replay, PublicationResult)
    assert replay.kind == "reconcile_pending"
    assert storage.put_keys == []
