"""API-owned validated materialization injected into plan publication."""
from citeframe_research_persistence.automatic_decisions import submit_policy_decision
from citeframe_research_persistence.membership import ensure_creator_membership
from ai_pdf_api.services.research.research_plan_approval import _approve_plan
from ai_pdf_api.services.research.research_events import append_research_event
from ai_pdf_api.services.research.research_idempotency import ResearchError


def auto_start_plan(db, run, decision, revision, now):
    if (run.status not in {"planning", "running"} or decision.status != "pending"
        or run.current_plan_revision_id != revision.id
        or decision.input_snapshot_sha256 != revision.planning_snapshot_sha256):
        raise ResearchError("research_state_conflict", "Research plan cannot auto-start.", 409)
    previous_status = run.status
    ensure_creator_membership(db, run, now=now)
    _approve_plan(db, run, decision, revision, now)
    submit_policy_decision(db, run, decision, action="approve", now=now)
    run.status = "queued"
    run.state_version += 1
    append_research_event(db, run, event_type="run_status_changed",
        dedupe_key=f"plan-status:{decision.id}",
        data={"previousStatus": previous_status, "status": run.status,
              "runStateVersion": run.state_version, "reasonCode": None}, now=now)
