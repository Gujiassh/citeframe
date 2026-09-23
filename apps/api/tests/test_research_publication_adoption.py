"""Adoption must retain authorization and accept ledgered retry evidence."""
from datetime import timedelta
from uuid import uuid4
import pytest
from sqlalchemy import delete, func, select
from ai_pdf_api.models import (WorkspaceMembership, ResearchArtifact, ResearchEvent,
    ResearchPublicationIntent, ResearchStep, ResearchStepAttempt, ResearchToolCall)
from ai_pdf_api.services.research.research_worker import (
    publish_final_report, reconcile_one_publication_intent, fail_research_step,
    claim_specific_research_step, complete_research_step,
    search_frozen_evidence, load_frozen_evidence)
from research_worker_test_support import make_final_publication_chain, lease_default_step, sha256
from test_research_worker_evidence_publication import MemoryPublicationStore, local_publication_callbacks


@pytest.mark.parametrize("reconcile", [False, True])
@pytest.mark.parametrize("phase", ["before_put", "after_put"])
def test_revocation_prevents_adoption(research_worker_db, reconcile, phase):
    f = research_worker_db
    fact, unresolved = make_final_publication_chain(f)
    lease = lease_default_step(f)
    store = MemoryPublicationStore(fail_puts=1 if reconcile else 0)
    args = local_publication_callbacks(f, store)
    def revoke():
        f.db.execute(delete(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == f.run.workspace_id,
            WorkspaceMembership.user_id == f.run.created_by_user_id))
        f.db.commit()
    def put(key, payload, kind):
        if phase == "before_put": revoke()
        store.put(key, payload, kind)
        if phase == "after_put": revoke()
    if not reconcile: args["store_bytes"] = put
    result = publish_final_report(f.db, attempt_id=lease.attempt_id,
        lease_token=lease.lease_token, fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,), **args)
    if reconcile:
        intent = f.db.get(ResearchPublicationIntent, result.intent_id)
        f.db.get(ResearchStepAttempt, lease.attempt_id).lease_expires_at = f.now - timedelta(seconds=1)
        intent.next_reconcile_at = f.now - timedelta(seconds=1)
        f.db.commit()
        args["store_bytes"] = put
        assert reconcile_one_publication_intent(f.db, worker_instance_id="revocation-test", **args)
    f.db.expire_all()
    intent = f.db.scalar(select(ResearchPublicationIntent).where(ResearchPublicationIntent.attempt_id == lease.attempt_id))
    assert intent.status in {"compensating", "absent"}
    assert f.run.status in {"cancel_requested", "cancelled"}
    assert f.run.cancel_reason_code == "creator_membership_removed"
    assert f.db.scalar(select(func.count()).select_from(ResearchArtifact).where(ResearchArtifact.artifact_kind == "final_report")) == 0
    assert f.db.scalar(select(func.count()).select_from(ResearchEvent).where(ResearchEvent.event_type == "run_completed")) == 0
    assert not store.objects


def retry_evidence(f, fact):
    producer = f.db.get(ResearchStep, fact.produced_by_step_id)
    old = f.db.scalar(select(ResearchStepAttempt).where(ResearchStepAttempt.step_id == producer.id))
    output = old.output_sha256
    # The downstream graph is a publication fixture; replay/fail/claim/complete
    # below use production services, without any live provider invocation.
    f.run.status = "running"
    producer.status = old.status = "running"
    producer.finished_at = old.finished_at = None
    old.output_sha256 = None
    old.lease_token_hash = sha256("first-lease")
    old.lease_expires_at = f.now + timedelta(seconds=60)
    f.db.commit()
    first_context = dict(run_id=f.run.id, execution_snapshot_id=f.snapshot.id,
        step_id=producer.id, attempt_id=old.id, branch_key=producer.branch_key or "", now=f.now)
    search = dict(tool_call_key="final-publication-evidence", query="facts",
        asset_ids=(f.asset.id,), top_k=f.snapshot.retrieval_top_k)
    handles = search_frozen_evidence(f.db, **first_context, **search)
    load = dict(tool_call_key="load-retry", evidence_handle_ids=tuple(h.evidence_handle for h in handles))
    first_load = load_frozen_evidence(f.db, **first_context, **load)
    f.db.commit()
    assert fail_research_step(f.db, attempt_id=old.id, lease_token="first-lease",
        error_code="provider_timeout", now=f.now).auto_requeued
    retry = claim_specific_research_step(f.db, run_id=f.run.id, step_key=producer.step_key,
        branch_key=producer.branch_key, worker_instance_id="retry-worker", lease_seconds=60, now=f.now)
    context = {**first_context, "attempt_id": retry.attempt_id}
    assert search_frozen_evidence(f.db, **context, **search) == handles
    assert load_frozen_evidence(f.db, **context, **load) == first_load
    f.db.commit()
    complete_research_step(f.db, attempt_id=retry.attempt_id, lease_token=retry.lease_token,
        output_sha256=output, now=f.now)
    tools = list(f.db.scalars(select(ResearchToolCall).where(ResearchToolCall.step_id == producer.id)))
    assert len(tools) == 2 and all(t.attempt_id == old.id for t in tools)
    return old, next(t for t in tools if t.tool_name == "evidence.search")


@pytest.mark.parametrize("corrupt", [None, "step", "snapshot", "failed_tool", "input", "running_origin"])
def test_retry_evidence_reaches_final_publication(research_worker_db, corrupt):
    f = research_worker_db
    fact, unresolved = make_final_publication_chain(f)
    old, tool = retry_evidence(f, fact)
    if corrupt == "step": tool.step_id = f.step.id
    if corrupt == "snapshot": tool.execution_snapshot_id = str(uuid4())
    if corrupt == "failed_tool": tool.status = "failed"
    if corrupt == "input": old.input_sha256 = sha256("different-scope")
    if corrupt == "running_origin": old.status = "running"
    f.db.commit()
    lease = lease_default_step(f)
    store = MemoryPublicationStore()
    result = publish_final_report(f.db, attempt_id=lease.attempt_id,
        lease_token=lease.lease_token, fact_claim_ids=(fact.id,),
        unresolved_claim_ids=(unresolved.id,), **local_publication_callbacks(f, store))
    f.db.expire_all()
    intent = f.db.scalar(select(ResearchPublicationIntent).where(ResearchPublicationIntent.attempt_id == lease.attempt_id))
    count = f.db.scalar(select(func.count()).select_from(ResearchArtifact).where(ResearchArtifact.artifact_kind == "final_report"))
    if corrupt is None:
        assert intent.status == "committed" and f.run.status == "completed" and count == 1
    else:
        assert intent.status == "compensating" and count == 0 and not store.objects
