"""Automatic conflict decisions must survive the final publication oracle."""
import pytest
from sqlalchemy import select
from ai_pdf_api.models import HumanDecision, ResearchPublicationIntent
from citeframe_research_persistence.automatic_decisions import submit_policy_decision
from citeframe_research_persistence.autonomy import AUTONOMOUS_WORKFLOW_ID
from research_worker_test_support import make_final_publication_chain, lease_default_step
from test_research_worker_evidence_publication import MemoryPublicationStore, local_publication_callbacks, publish_final_report


@pytest.mark.parametrize("corrupt", [None, "actor", "policy"])
def test_policy_decision_final_publish(research_worker_db, corrupt):
    f = research_worker_db
    fact, unresolved = make_final_publication_chain(f)
    assert f.snapshot.workflow_version_id == AUTONOMOUS_WORKFLOW_ID
    decision = f.db.scalar(select(HumanDecision).where(HumanDecision.decision_type == "conflict_resolution"))
    # The graph includes immutable artifact/claim/prompt bindings; submit through
    # the production policy transition and retain that graph for final adoption.
    submit_policy_decision(f.db, f.run, decision, action="keep_as_unresolved", now=decision.decided_at)
    if corrupt == "actor": decision.decided_by_user_id = f.run.created_by_user_id
    if corrupt == "policy": decision.comment_text = "unrecognized-policy"
    f.db.commit()
    lease = lease_default_step(f)
    store = MemoryPublicationStore()
    result = publish_final_report(f.db, attempt_id=lease.attempt_id, lease_token=lease.lease_token,
        fact_claim_ids=(fact.id,), unresolved_claim_ids=(unresolved.id,), **local_publication_callbacks(f, store))
    f.db.expire_all()
    intent = f.db.scalar(select(ResearchPublicationIntent).where(ResearchPublicationIntent.attempt_id == lease.attempt_id))
    if corrupt is None:
        assert intent.status == "committed" and f.run.status == "completed"
        report = bytes(intent.payload_bytes).decode()
        findings, conflicts = report.split("## Unresolved Evidence Conflicts")
        assert unresolved.statement_text not in findings and unresolved.statement_text in conflicts
    else:
        assert intent.status == "compensating" and not store.objects


def test_historical_workflow_rejects_policy_actor():
    from types import SimpleNamespace
    from citeframe_research_persistence.automatic_decisions import decision_origin_is_valid
    decision = SimpleNamespace(decision_origin="policy", decided_by_user_id=None,
        comment_text="research-autonomy-v1")
    assert not decision_origin_is_valid(decision, "20000000-0000-4000-8000-000000000001")
