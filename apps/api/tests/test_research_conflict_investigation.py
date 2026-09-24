from sqlalchemy import select, func
from sqlalchemy.orm import Session
import pytest
from citeframe_persistence.models import (
    ResearchConflictTurn,
    ResearchClaim,
    WorkspaceMembership,
    ResearchClaimEvidence,
    ResearchStepAttempt,
)
from citeframe_research_persistence.conflict_investigation import (
    conflict_turn,
    investigation_view,
)
from citeframe_research_persistence.conflict_policy import INVESTIGATION_WORKFLOW_ID
from citeframe_research_persistence.errors import ResearchError
from research_worker_test_support import lease_default_step


def gate(f):
    f.snapshot.workflow_version_id = INVESTIGATION_WORKFLOW_ID
    f.step.step_kind = "conflict_decision_gate"
    f.step.step_key = "conflict_decision_gate"
    f.step.branch_key = None
    f.db.commit()
    return lease_default_step(f)


def call(f, lease, number=0, phase="inspect", request=None, result=None):
    return conflict_turn(
        f.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        operation_number=number,
        phase=phase,
        request=request or {"sources": []},
        result=result,
        now=f.now,
    )


def test_operation_survives_new_session_and_replays_without_duplicate(
    research_worker_db,
):
    f = research_worker_db
    lease = gate(f)
    assert call(f, lease)["status"] == "reserved"
    assert call(f, lease, result={"inspected": True})["status"] == "succeeded"
    f.db.commit()
    with Session(f.db.get_bind()) as db:
        result = conflict_turn(
            db,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            operation_number=0,
            phase="inspect",
            request={"sources": []},
            now=f.now,
        )
        assert result == {"status": "succeeded", "result": {"inspected": True}}
        assert db.scalar(select(func.count()).select_from(ResearchConflictTurn)) == 1


def test_ambiguous_operation_does_not_reserve_another_call(research_worker_db):
    f = research_worker_db
    lease = gate(f)
    call(f, lease)
    f.db.commit()
    assert call(f, lease)["status"] == "outcome_unknown"
    assert f.db.scalar(select(func.count()).select_from(ResearchConflictTurn)) == 1


def test_changed_replay_and_out_of_order_rejected(research_worker_db):
    f = research_worker_db
    lease = gate(f)
    call(f, lease)
    f.db.commit()
    with pytest.raises(ResearchError):
        call(f, lease, request={"sources": ["forged"]})
    f.db.rollback()
    with pytest.raises(ResearchError):
        call(f, lease, number=1)


@pytest.mark.parametrize("mutation", ["cancel", "permission", "lease", "legacy"])
def test_guards_prevent_checkpoint_writes(research_worker_db, mutation):
    f = research_worker_db
    lease = gate(f)
    if mutation == "cancel":
        f.run.status = "cancel_requested"
        f.run.cancel_requested_by_user_id = f.run.created_by_user_id
        f.run.cancel_requested_at = f.now
        f.run.cancel_reason_code = "user_requested"
    elif mutation == "permission":
        for row in f.db.scalars(select(WorkspaceMembership)):
            f.db.delete(row)
    elif mutation == "legacy":
        f.snapshot.workflow_version_id = "30000000-0000-4000-8000-000000000001"
    else:
        from dataclasses import replace

        lease = replace(lease, lease_token="invalid")
    f.db.commit()
    with pytest.raises(ResearchError):
        call(f, lease)
    f.db.rollback()
    assert f.db.scalar(select(func.count()).select_from(ResearchConflictTurn)) == 0


def test_duplicate_queries_and_round_bounds_are_persisted(research_worker_db):
    f = research_worker_db
    lease = gate(f)
    call(f, lease, phase="search", request={"query": "same query"})
    call(
        f,
        lease,
        phase="search",
        request={"query": "same query"},
        result={"evidence": []},
    )
    f.db.commit()
    with pytest.raises(ResearchError):
        call(f, lease, number=1, phase="search", request={"query": " SAME   QUERY "})
    with pytest.raises(ResearchError):
        call(f, lease, number=13)


def test_status_change_alone_cannot_resolve(research_worker_db):
    f = research_worker_db
    lease = gate(f)
    call(f, lease, phase="finish", request={"conflictClaimIds": []})
    with pytest.raises(ResearchError, match="verification"):
        call(
            f,
            lease,
            phase="finish",
            request={"conflictClaimIds": []},
            result={
                "resolved": True,
                "originalClaims": [],
                "revisions": [],
                "evidence": [],
            },
        )


def test_worker_gate_persists_sources_correction_and_rechecks_across_sessions(
    research_worker_db,
):
    from types import SimpleNamespace as N
    from uuid import uuid4
    from citeframe_contracts import VerifiedClaim
    from ai_pdf_worker.research.conflict_investigation import investigate
    from ai_pdf_worker.research.core import _evidence_handle
    from ai_pdf_api.services.research.research_worker_evidence import (
        _frozen_evidence_value,
    )
    from citeframe_research_persistence.conflict_report import investigation_report
    from citeframe_research_persistence.conflict_investigation import (
        investigation_outcome,
    )
    from research_worker_test_support import seed_frozen_evidence, add_step, sha256

    f = research_worker_db
    db = f.db
    source_lease = lease_default_step(f)
    handle = seed_frozen_evidence(f, source_lease.attempt_id)
    source = _evidence_handle(
        _frozen_evidence_value(db, handle, branch_key=f.step.branch_key)
    )
    originals = []
    for i, text in enumerate(("Use A", "Use B")):
        claim = ResearchClaim(
            id=str(uuid4()),
            workspace_id=f.run.workspace_id,
            run_id=f.run.id,
            claim_key=f"conflict-{i}",
            claim_order=i,
            statement_text=text,
            statement_sha256=sha256(text),
            produced_by_step_id=f.step.id,
            verification_status="supported",
            conflict_status="conflicted",
            created_at=f.now,
        )
        db.add(claim)
        originals.append(claim)
    for claim in originals:
        db.add(
            ResearchClaimEvidence(
                claim_id=claim.id,
                evidence_snapshot_id=handle.evidence_snapshot_id,
                evidence_order=0,
                relationship="supports",
                assessed_by_step_id=f.step.id,
            )
        )
    f.step.status = "succeeded"
    origin = db.get(ResearchStepAttempt, source_lease.attempt_id)
    origin.status = "succeeded"
    origin.finished_at = f.now
    origin.lease_expires_at = None
    next_step = add_step(
        f, step_key="conflict_decision_gate", step_kind="conflict_decision_gate"
    )
    object.__setattr__(f, "step", next_step)
    lease = gate(f)
    calls = []

    class Agents:
        def investigator(self, payload, lease):
            calls.append("inspect")
            return {
                "inspections": [
                    {
                        "evidenceHandleId": source.id,
                        "quote": source.excerpt,
                        "version": None,
                        "environment": None,
                        "time": None,
                        "conditions": None,
                    }
                ],
                "revisions": [
                    {
                        "originalClaimIds": [c.id for c in originals],
                        "text": "The frozen excerpt is the applicable source.",
                        "evidenceHandleIds": [source.id],
                    }
                ],
                "nextQuery": None,
                "gaps": [],
                "reason": "Checked the original frozen excerpt.",
            }

        def verifier(self, claims, evidence, lease):
            calls.append("verify")
            return [
                VerifiedClaim(c.id, c.text, c.evidence_handle_ids, "supported")
                for c in claims
            ]

        def critic(self, claims, lease):
            calls.append("critic")
            return []

    def checkpoint(lease, number, phase, request, result=None):
        with Session(db.get_bind()) as session:
            value = conflict_turn(
                session,
                attempt_id=lease.attempt_id,
                lease_token=lease.lease_token,
                operation_number=number,
                phase=phase,
                request=request,
                result=result,
                now=f.now,
            )
            session.commit()
            return value

    state = {
        "conflicts": [c.id for c in originals],
        "verified_claims": [
            VerifiedClaim(
                c.id, c.statement_text, (source.id,), "supported", "conflicted"
            )
            for c in originals
        ],
        "branch_results": [N(evidence=[source])],
    }
    kwargs = dict(
        execution=N(frozen_assets=[N(asset_id=f.asset.id)], retrieval_top_k=3),
        state=state,
        agents=Agents(),
        lease=lease,
        tools=lambda _: None,
        checkpoint=checkpoint,
    )
    result = investigate(**kwargs)
    assert result["resolved"] and calls == ["inspect", "verify", "critic"]
    calls.clear()
    assert investigate(**kwargs) == result and calls == []
    db.expire_all()
    view = investigation_view(db, f.run.id, "running")
    assert (
        view["status"] == "resolved"
        and view["sources"][0]["locatorId"] == source.locator_id
    )
    assert investigation_outcome(db, f.run.id) == result
    report = investigation_report(
        db, f.run.id, fact_claims=[], unresolved_claims=originals
    ).decode()
    assert "Unresolved Evidence Conflicts" not in report
    assert (
        "The frozen excerpt is the applicable source." in report
        and source.locator_id in report
    )
    assert [c.statement_text for c in originals] == ["Use A", "Use B"]


@pytest.mark.parametrize("nullable_input", [False, True])
def test_v4_gate_search_load_uses_frozen_evidence_service_and_dedup_ledger(
    research_worker_db, monkeypatch, nullable_input
):
    from ai_pdf_api.services.research.research_worker import (
        search_frozen_evidence,
        load_frozen_evidence,
    )
    from citeframe_persistence.models import ResearchToolCall
    from research_worker_test_support import seed_frozen_evidence

    f = research_worker_db
    if nullable_input:
        f.step.input_sha256 = None
    lease = gate(f)
    from types import SimpleNamespace as N
    from citeframe_persistence.models import ResearchEvidenceSnapshot, EvidenceLocator
    from ai_pdf_api.services.research import research_worker_evidence

    handle = seed_frozen_evidence(f, lease.attempt_id)
    evidence = f.db.get(ResearchEvidenceSnapshot, handle.evidence_snapshot_id)
    locator = f.db.get(EvidenceLocator, evidence.evidence_locator_id)

    class Embedding:
        provider = f.snapshot.embedding_provider
        model = f.snapshot.embedding_model
        version = f.snapshot.embedding_version

        def embed_query(self, query):
            return [0.1, 0.2]

    monkeypatch.setattr(
        research_worker_evidence,
        "retrieve_query_content",
        lambda *a, **k: [
            N(
                asset=f.asset,
                locator=locator,
                channel="text",
                distance=0.1,
                content_unit=N(
                    representation_id=evidence.representation_id_snapshot,
                    index_version=f.asset.current_index_version,
                    text_content="A supplemental frozen excerpt.",
                ),
            )
        ],
    )
    context = dict(
        run_id=f.run.id,
        execution_snapshot_id=f.snapshot.id,
        step_id=f.step.id,
        attempt_id=lease.attempt_id,
        branch_key="conflicts",
        now=f.now,
    )
    search = dict(
        tool_call_key="investigation-1:search",
        query="facts",
        asset_ids=(f.asset.id,),
        top_k=f.snapshot.retrieval_top_k,
        embedding_provider=Embedding(),
    )
    found = search_frozen_evidence(f.db, **context, **search)
    assert found and all(h.owner_step_id == f.step.id for h in found)
    from dataclasses import asdict
    from ai_pdf_worker.research.core import _evidence_handle
    from citeframe_research_persistence.conflict_provenance import validate_sources

    validate_sources(
        f.db,
        f.step,
        [],
        {
            "originalClaims": [],
            "evidence": [asdict(_evidence_handle(h)) for h in found],
        },
    )

    load = dict(
        tool_call_key="investigation-1:load",
        evidence_handle_ids=tuple(h.evidence_handle for h in found),
    )
    loaded = load_frozen_evidence(f.db, **context, **load)
    f.db.commit()
    from ai_pdf_worker.research.core import _evidence_handle

    assert [
        _evidence_handle(h) for h in search_frozen_evidence(f.db, **context, **search)
    ] == [_evidence_handle(h) for h in found]
    assert load_frozen_evidence(f.db, **context, **load) == loaded
    assert (
        f.db.scalar(
            select(func.count())
            .select_from(ResearchToolCall)
            .where(ResearchToolCall.tool_call_key.like("investigation-1:%"))
        )
        == 2
    )


def test_third_distinct_search_cannot_be_reserved(research_worker_db):
    f = research_worker_db
    lease = gate(f)
    for number, query in enumerate(("first", "second")):
        request = {"query": query}
        call(f, lease, number=number, phase="search", request=request)
        call(
            f,
            lease,
            number=number,
            phase="search",
            request=request,
            result={"evidence": []},
        )
    with pytest.raises(ResearchError, match="limit"):
        call(f, lease, number=2, phase="search", request={"query": "third"})


@pytest.mark.parametrize("completed", [False, True])
@pytest.mark.parametrize("explicit_input", [False, True])
@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "attempt_hash",
        "step_hash",
        "tool_workspace",
        "tool_snapshot",
        "handle_run",
        "evidence_run",
    ],
)
def test_live_gate_source_hash_and_scope(research_worker_db, explicit_input, mutation, completed):
    from dataclasses import asdict
    from uuid import uuid4
    from ai_pdf_api.services.research.research_worker_evidence import (
        _frozen_evidence_value,
    )
    from ai_pdf_worker.research.core import _evidence_handle
    from citeframe_persistence.models import ResearchEvidenceSnapshot, ResearchToolCall
    from citeframe_research_persistence.conflict_provenance import validate_sources
    from research_worker_test_support import seed_frozen_evidence, sha256

    f = research_worker_db
    f.step.input_sha256 = sha256("explicit gate input") if explicit_input else None
    lease = gate(f)
    attempt = f.db.get(ResearchStepAttempt, lease.attempt_id)
    assert attempt.input_sha256 == (f.step.input_sha256 or sha256(f.step.id))
    if completed:
        f.step.status = attempt.status = "succeeded"
        f.step.finished_at = attempt.finished_at = f.now
        attempt.lease_expires_at = None
        f.db.commit()
    handle = seed_frozen_evidence(f, lease.attempt_id)
    value = asdict(
        _evidence_handle(_frozen_evidence_value(f.db, handle, branch_key="conflicts"))
    )
    tool = f.db.get(ResearchToolCall, handle.created_by_tool_call_id)
    if mutation == "attempt_hash":
        attempt.input_sha256 = sha256("wrong attempt")
    elif mutation == "step_hash":
        f.step.input_sha256 = sha256("changed step")
    elif mutation == "tool_workspace":
        tool.workspace_id = str(uuid4())
    elif mutation == "tool_snapshot":
        tool.execution_snapshot_id = str(uuid4())
    elif mutation == "handle_run":
        handle.run_id = str(uuid4())
    elif mutation == "evidence_run":
        f.db.get(ResearchEvidenceSnapshot, handle.evidence_snapshot_id).run_id = str(
            uuid4()
        )
    f.db.commit()
    outcome = {"originalClaims": [], "evidence": [value]}
    if mutation:
        with pytest.raises(ResearchError, match="provenance"):
            validate_sources(f.db, f.step, [], outcome)
    else:
        validate_sources(f.db, f.step, [], outcome)
