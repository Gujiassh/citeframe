"""Deterministic publication saga integration; no external provider or object store."""

from datetime import timedelta
from types import SimpleNamespace as N
import pytest
from sqlalchemy import select
from citeframe_contracts import VerifiedClaim
from citeframe_persistence.models import (
    ResearchStep,
    ResearchStepAttempt,
    ResearchEvidenceHandle,
    ResearchArtifact,
    ResearchConflictTurn,
)
from citeframe_research_persistence.conflict_policy import INVESTIGATION_WORKFLOW_ID
from citeframe_research_persistence.conflict_investigation import conflict_turn
from ai_pdf_worker.research_conflict_investigation import investigate
from ai_pdf_worker.research_runtime_core import _evidence_handle
from ai_pdf_api.services.research.research_worker_evidence import _frozen_evidence_value
from ai_pdf_api.services.research.research_worker import publish_final_report
from research_worker_test_support import (
    make_final_publication_chain,
    lease_default_step,
    sha256,
)
from test_research_worker_evidence_publication import (
    MemoryPublicationStore,
    local_publication_callbacks,
)


@pytest.mark.parametrize("resolved", [True, False])
@pytest.mark.parametrize("tamper", [False, True])
def test_v4_journal_survives_final_publication_adoption(
    research_worker_db, resolved, tamper
):
    f = research_worker_db
    fact, original = make_final_publication_chain(
        f, workflow_id=INVESTIGATION_WORKFLOW_ID
    )
    db = f.db
    gate = db.scalar(
        select(ResearchStep).where(
            ResearchStep.run_id == f.run.id,
            ResearchStep.step_kind == "conflict_decision_gate",
        )
    )
    attempt = db.scalar(
        select(ResearchStepAttempt).where(ResearchStepAttempt.step_id == gate.id)
    )
    handle = db.scalar(select(ResearchEvidenceHandle))
    source = _evidence_handle(_frozen_evidence_value(db, handle, branch_key="branch-1"))
    gate_finish, attempt_finish, output = (
        gate.finished_at,
        attempt.finished_at,
        attempt.output_sha256,
    )
    gate.status = attempt.status = "running"
    gate.finished_at = attempt.finished_at = None
    attempt.output_sha256 = None
    attempt.lease_token_hash = sha256("investigation-lease")
    attempt.lease_expires_at = f.now + timedelta(seconds=60)
    original.conflict_status = "conflicted"
    db.commit()
    lease = N(step_id=gate.id, attempt_id=attempt.id, lease_token="investigation-lease")

    class Agents:
        def investigator(self, payload, lease):
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
                        "originalClaimIds": [original.id],
                        "text": "Corrected conclusion from the original excerpt.",
                        "evidenceHandleIds": [source.id],
                    }
                ]
                if resolved
                else [],
                "nextQuery": None,
                "gaps": []
                if resolved
                else ["The source does not establish the applicable version."],
                "reason": "Compared the original source.",
            }

        def verifier(self, claims, evidence, lease):
            return [
                VerifiedClaim(c.id, c.text, c.evidence_handle_ids, "supported")
                for c in claims
            ]

        def critic(self, claims, lease):
            return []

    def checkpoint(lease, number, phase, request, result=None):
        value = conflict_turn(
            db,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            operation_number=number,
            phase=phase,
            request=request,
            result=result,
            now=f.now,
        )
        db.commit()
        return value

    outcome = investigate(
        execution=N(frozen_assets=[], retrieval_top_k=3),
        state={
            "conflicts": [original.id],
            "verified_claims": [
                VerifiedClaim(fact.id, fact.statement_text, (source.id,), "supported", "none"),
                VerifiedClaim(
                    original.id,
                    original.statement_text,
                    (source.id,),
                    "supported",
                    "conflicted",
                )
            ],
            "branch_results": [N(evidence=[source])],
        },
        agents=Agents(),
        lease=lease,
        tools=lambda _: None,
        checkpoint=checkpoint,
    )
    assert outcome["resolved"] == resolved
    gate.status = attempt.status = "succeeded"
    gate.finished_at, attempt.finished_at, attempt.output_sha256 = (
        gate_finish,
        attempt_finish,
        output,
    )
    attempt.lease_expires_at = None
    original.conflict_status = "resolved_unresolved"
    db.commit()
    publisher = lease_default_step(f)
    store = MemoryPublicationStore()
    args = local_publication_callbacks(f, store)
    if tamper:

        def put(key, payload, kind):
            store.put(key, payload, kind)
            row = db.scalar(
                select(ResearchConflictTurn).where(
                    ResearchConflictTurn.phase == "finish"
                )
            )
            row.result_json = {
                **row.result_json,
                "explanation": "changed after preparation",
            }
            db.commit()

        args["store_bytes"] = put
    result = publish_final_report(
        db,
        attempt_id=publisher.attempt_id,
        lease_token=publisher.lease_token,
        fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(original.id,),
        **args,
    )
    db.expire_all()
    artifact = db.scalar(
        select(ResearchArtifact).where(ResearchArtifact.artifact_kind == "final_report")
    )
    if tamper:
        assert artifact is None
        assert not store.objects
        return
    assert artifact is not None, result
    report = store.objects[artifact.object_key][0].decode()
    assert "Conflict investigation" in report and source.locator_id in report
    assert ("Corrected conclusion" in report) == resolved
    assert ("Unresolved Evidence Conflicts" in report) != resolved
    assert original.statement_text == "Supported but unresolved claim."
