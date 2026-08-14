"""Human decision submission for plan approval and conflict resolution."""

from __future__ import annotations

from datetime import UTC, datetime

from ai_pdf_api.models import (
    HumanDecision,
    HumanDecisionClaim,
    ResearchArtifactClaim,
    ResearchClaim,
    ResearchPlanRevision,
    ResearchRun,
    ResearchStep,
    ResearchStepDependency,
)
from ai_pdf_api.schemas.research import ConflictDecisionRequest, PlanDecisionRequest
from ai_pdf_api.services.research.research_events import append_research_event
from ai_pdf_api.services.research.research_idempotency import (
    ResearchError,
    _idempotent_mutation,
    validate_idempotency_key,
)
from ai_pdf_api.services.research.research_plan_approval import _approve_plan
from ai_pdf_api.services.research.research_runs import (
    _add_revision,
    _get_research_run_for_update,
)
from ai_pdf_api.services.research.research_views import run_detail
from sqlalchemy import select
from sqlalchemy.orm import Session


def _get_pending_decision(
    db: Session,
    *,
    workspace_id: str,
    run_id: str,
    decision_id: str,
    decision_type: str,
) -> tuple[ResearchRun, HumanDecision]:
    run = _get_research_run_for_update(db, workspace_id, run_id)
    decision = db.scalar(
        select(HumanDecision).where(
            HumanDecision.id == decision_id,
            HumanDecision.run_id == run_id,
            HumanDecision.workspace_id == workspace_id,
            HumanDecision.decision_type == decision_type,
        )
    )
    if decision is None:
        raise ResearchError("research_resource_not_found", "Research decision not found.", 404)
    if decision.status != "pending":
        raise ResearchError("research_state_conflict", "Research decision has already been submitted.", 409)
    return run, decision

def _validate_decision_versions(
    run: ResearchRun,
    decision: HumanDecision,
    *,
    expected_run_version: int,
    expected_decision_version: int,
    artifact_hash: str,
    snapshot_hash: str,
) -> None:
    if run.state_version != expected_run_version or decision.state_version != expected_decision_version:
        raise ResearchError("stale_state_version", "Research decision state is stale.", 409)
    if decision.input_artifact_sha256 != artifact_hash or decision.input_snapshot_sha256 != snapshot_hash:
        raise ResearchError("stale_plan_snapshot", "Research decision input no longer matches.", 409)

def _submit_decision(
    db: Session,
    run: ResearchRun,
    decision: HumanDecision,
    *,
    actor_user_id: str,
    action: str,
    comment: str | None,
    now: datetime,
) -> None:
    decision.status = "submitted"
    decision.state_version += 1
    decision.decided_by_user_id = actor_user_id
    decision.action = action
    decision.comment_text = comment.strip() if comment else None
    decision.decided_at = now
    run.state_version += 1
    run.updated_at = now
    append_research_event(
        db,
        run,
        event_type="decision_submitted",
        dedupe_key=f"decision-submitted:{decision.id}",
        step_id=decision.gate_step_id,
        data={
            "decisionId": decision.id,
            "decisionType": decision.decision_type,
            "inputArtifactId": decision.input_artifact_id,
            "inputArtifactSha256": decision.input_artifact_sha256,
            "action": action,
            "actorUserId": actor_user_id,
            "decisionStateVersion": decision.state_version,
            "runStateVersion": run.state_version,
        },
        now=now,
    )

def decide_plan(
    db: Session,
    *,
    workspace_id: str,
    actor_user_id: str,
    run_id: str,
    decision_id: str,
    payload: PlanDecisionRequest,
    idempotency_key: str,
) -> tuple[int, dict[str, object], bool]:
    key = validate_idempotency_key(idempotency_key)
    path = f"/v1/workspaces/{workspace_id}/research-runs/{run_id}/plan-decisions/{decision_id}"
    body = payload.model_dump(mode="json", by_alias=True)

    def execute() -> tuple[int, dict[str, object], str]:
        run, decision = _get_pending_decision(
            db,
            workspace_id=workspace_id,
            run_id=run_id,
            decision_id=decision_id,
            decision_type="plan_approval",
        )
        if actor_user_id != run.created_by_user_id:
            raise ResearchError("research_permission_denied", "Only the Run creator can decide its plan.", 403)
        if run.status != "awaiting_plan_approval":
            raise ResearchError("research_state_conflict", "Research run is not awaiting plan approval.", 409)
        _validate_decision_versions(
            run,
            decision,
            expected_run_version=payload.expected_state_version,
            expected_decision_version=payload.expected_decision_state_version,
            artifact_hash=payload.input_artifact_sha256,
            snapshot_hash=payload.input_snapshot_sha256,
        )
        revision = db.get(ResearchPlanRevision, run.current_plan_revision_id)
        if revision is None or revision.planning_snapshot_sha256 != decision.input_snapshot_sha256:
            raise ResearchError("stale_plan_snapshot", "Current plan revision does not match the decision.", 409)
        now = datetime.now(UTC)
        previous_status = run.status
        _submit_decision(
            db,
            run,
            decision,
            actor_user_id=actor_user_id,
            action=payload.action,
            comment=payload.comment,
            now=now,
        )
        if payload.action == "approve":
            _approve_plan(db, run, decision, revision, now)
            run.status = "queued"
        elif payload.action == "request_revision":
            assert payload.revision is not None
            if revision.revision_number >= 5:
                raise ResearchError("research_plan_revision_limit", "The plan revision limit has been reached.", 409)
            _new_revision, queued_step = _add_revision(
                db,
                run=run,
                actor_user_id=actor_user_id,
                question=payload.revision.question,
                scope=payload.revision.asset_scope,
                revision_number=revision.revision_number + 1,
                supersedes_revision_id=revision.id,
                now=now,
            )
            run.status = "planning"
        else:
            run.status = "cancel_requested"
            run.cancel_requested_by_user_id = actor_user_id
            run.cancel_reason_code = "user_requested"
            run.cancel_requested_at = now
        run.state_version += 1
        run.updated_at = now
        if payload.action == "cancel_run":
            append_research_event(
                db,
                run,
                event_type="cancel_requested",
                dedupe_key=f"plan-cancel:{decision.id}",
                data={"actorUserId": actor_user_id, "reasonCode": "user_requested", "runStateVersion": run.state_version},
                now=now,
            )
        else:
            append_research_event(
                db,
                run,
                event_type="run_status_changed",
                dedupe_key=f"plan-status:{decision.id}",
                data={
                    "previousStatus": previous_status,
                    "status": run.status,
                    "runStateVersion": run.state_version,
                    "reasonCode": None,
                },
                now=now,
            )
            if payload.action == "request_revision":
                run.state_version += 1
                append_research_event(
                    db,
                    run,
                    event_type="step_queued",
                    dedupe_key=f"step-queued:{queued_step.id}:0",
                    step_id=queued_step.id,
                    data={
                        "stepId": queued_step.id,
                        "stepKind": queued_step.step_kind,
                        "branchKey": None,
                        "attemptNumber": 0,
                        "stepStateVersion": queued_step.state_version,
                        "runStateVersion": run.state_version,
                    },
                    now=now,
                )
        db.flush()
        from ai_pdf_api.services.research.research_views import _decision_dto

        return 200, {"decision": _decision_dto(decision), "run": run_detail(db, run)}, decision.id

    return _idempotent_mutation(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        operation="submit_plan_decision",
        resource_path=path,
        key=key,
        request_body=body,
        execute=execute,
    )

def decide_conflict(
    db: Session,
    *,
    workspace_id: str,
    actor_user_id: str,
    run_id: str,
    decision_id: str,
    payload: ConflictDecisionRequest,
    idempotency_key: str,
) -> tuple[int, dict[str, object], bool]:
    key = validate_idempotency_key(idempotency_key)
    path = f"/v1/workspaces/{workspace_id}/research-runs/{run_id}/conflict-decisions/{decision_id}"
    body = payload.model_dump(mode="json", by_alias=True)

    def execute() -> tuple[int, dict[str, object], str]:
        run, decision = _get_pending_decision(
            db,
            workspace_id=workspace_id,
            run_id=run_id,
            decision_id=decision_id,
            decision_type="conflict_resolution",
        )
        if actor_user_id != run.created_by_user_id:
            raise ResearchError("research_permission_denied", "Only the Run creator can decide conflicts.", 403)
        if run.status != "awaiting_human_decision":
            raise ResearchError("research_state_conflict", "Research run is not awaiting a conflict decision.", 409)
        _validate_decision_versions(
            run,
            decision,
            expected_run_version=payload.expected_state_version,
            expected_decision_version=payload.expected_decision_state_version,
            artifact_hash=payload.input_artifact_sha256,
            snapshot_hash=payload.input_snapshot_sha256,
        )
        now = datetime.now(UTC)
        previous_status = run.status
        _submit_decision(
            db,
            run,
            decision,
            actor_user_id=actor_user_id,
            action=payload.action,
            comment=payload.comment,
            now=now,
        )
        if payload.action == "cancel_run":
            run.status = "cancel_requested"
            run.cancel_requested_by_user_id = actor_user_id
            run.cancel_reason_code = "user_requested"
            run.cancel_requested_at = now
        else:
            disposition = "exclude" if payload.action == "exclude_conflicted_claims" else "leave_unresolved"
            target_status = "resolved_excluded" if disposition == "exclude" else "resolved_unresolved"
            claims = list(
                db.scalars(
                    select(ResearchClaim)
                    .join(ResearchArtifactClaim, ResearchArtifactClaim.claim_id == ResearchClaim.id)
                    .where(
                        ResearchArtifactClaim.artifact_id == decision.input_artifact_id,
                        ResearchClaim.run_id == run.id,
                        ResearchClaim.workspace_id == run.workspace_id,
                    )
                    .order_by(ResearchArtifactClaim.claim_order)
                ).all()
            )
            if not claims:
                raise ResearchError("invalid_decision", "Conflict report has no bound Claims.", 422)
            for claim in claims:
                if claim.verification_status != "supported" or claim.conflict_status != "conflicted":
                    raise ResearchError("research_state_conflict", "Conflict Claim state is invalid.", 409)
                claim.conflict_status = target_status
                existing = db.get(HumanDecisionClaim, (decision.id, claim.id))
                if existing is None:
                    db.add(
                        HumanDecisionClaim(
                            decision_id=decision.id,
                            claim_id=claim.id,
                            disposition=disposition,
                        )
                    )
                elif existing.disposition != disposition:
                    raise ResearchError("research_state_conflict", "Conflict disposition does not match.", 409)
            run.status = "queued"
            gate = db.get(ResearchStep, decision.gate_step_id)
            if gate:
                gate.status = "succeeded"
                gate.state_version += 1
                gate.finished_at = now
                gate.updated_at = now
        run.state_version += 1
        run.updated_at = now
        if payload.action == "cancel_run":
            append_research_event(
                db,
                run,
                event_type="cancel_requested",
                dedupe_key=f"conflict-cancel:{decision.id}",
                data={"actorUserId": actor_user_id, "reasonCode": "user_requested", "runStateVersion": run.state_version},
                now=now,
            )
        else:
            append_research_event(
                db,
                run,
                event_type="run_status_changed",
                dedupe_key=f"conflict-status:{decision.id}",
                data={
                    "previousStatus": previous_status,
                    "status": run.status,
                    "runStateVersion": run.state_version,
                    "reasonCode": None,
                },
                now=now,
            )
            gate = db.get(ResearchStep, decision.gate_step_id)
            if gate is not None:
                dependent_ids = list(
                    db.scalars(
                        select(ResearchStepDependency.step_id).where(
                            ResearchStepDependency.depends_on_step_id == gate.id
                        )
                    ).all()
                )
                for dependent_id in dependent_ids:
                    dependent = db.get(ResearchStep, dependent_id)
                    if (
                        dependent is None
                        or dependent.run_id != run.id
                        or dependent.workspace_id != run.workspace_id
                        or dependent.status != "pending"
                    ):
                        continue
                    dependencies = list(
                        db.scalars(
                            select(ResearchStep)
                            .join(
                                ResearchStepDependency,
                                ResearchStepDependency.depends_on_step_id == ResearchStep.id,
                            )
                            .where(ResearchStepDependency.step_id == dependent.id)
                        ).all()
                    )
                    if not dependencies or any(item.status != "succeeded" for item in dependencies):
                        continue
                    dependent.status = "queued"
                    dependent.state_version += 1
                    dependent.queued_at = now
                    dependent.updated_at = now
                    run.state_version += 1
                    append_research_event(
                        db,
                        run,
                        event_type="step_queued",
                        dedupe_key=f"step-queued:{dependent.id}:{dependent.current_attempt_number}",
                        step_id=dependent.id,
                        data={
                            "stepId": dependent.id,
                            "stepKind": dependent.step_kind,
                            "branchKey": dependent.branch_key,
                            "attemptNumber": dependent.current_attempt_number,
                            "stepStateVersion": dependent.state_version,
                            "runStateVersion": run.state_version,
                        },
                        now=now,
                    )
        db.flush()
        from ai_pdf_api.services.research.research_views import _decision_dto

        return 200, {"decision": _decision_dto(decision), "run": run_detail(db, run)}, decision.id

    return _idempotent_mutation(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        operation="submit_conflict_decision",
        resource_path=path,
        key=key,
        request_body=body,
        execute=execute,
    )
