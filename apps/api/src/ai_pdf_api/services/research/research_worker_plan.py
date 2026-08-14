from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from uuid import uuid4

from ai_pdf_api.models import (
    HumanDecision,
    ResearchArtifact,
    ResearchArtifactPromptVersion,
    ResearchPlanRevision,
    ResearchPlanRevisionAsset,
    ResearchStep,
)
from ai_pdf_api.schemas.research import ResearchPlanArtifactPayload, ResearchPlanSubproblem
from ai_pdf_api.services.research import (
    ResearchError,
    append_research_event,
    canonical_json,
)
from ai_pdf_api.services.research.research_worker_lease import _locked_attempt
from ai_pdf_api.services.research.research_worker_types import PlanSubproblemDraft
from ai_pdf_api.services.storage import delete_object_if_exists, upload_bytes
from sqlalchemy import select
from sqlalchemy.orm import Session


def publish_research_plan(
    db: Session,
    *,
    attempt_id: str,
    lease_token: str,
    summary: str,
    subproblems: Sequence[PlanSubproblemDraft],
    known_gaps: Sequence[str] = (),
    estimated_provider_calls: int,
    estimated_input_tokens: int | None = None,
    estimated_output_tokens: int | None = None,
    store_bytes: Callable[[str, bytes, str], None] = upload_bytes,
    cleanup_bytes: Callable[[str], None] = delete_object_if_exists,
    now: datetime | None = None,
) -> dict[str, object]:
    published_at = now or datetime.now(UTC)
    run, step, attempt = _locked_attempt(
        db,
        attempt_id=attempt_id,
        lease_token=lease_token,
        now=published_at,
    )
    if step.step_kind != "planner" or step.plan_revision_id != run.current_plan_revision_id:
        raise ResearchError("research_state_conflict", "Only the current Planner Step can publish a plan.", 409)
    revision = db.get(ResearchPlanRevision, step.plan_revision_id)
    if revision is None or revision.run_id != run.id or revision.workspace_id != run.workspace_id:
        raise ResearchError("research_state_conflict", "Research Planner revision chain is invalid.", 409)
    plan_assets = list(
        db.scalars(
            select(ResearchPlanRevisionAsset).where(
                ResearchPlanRevisionAsset.plan_revision_id == revision.id
            )
        ).all()
    )
    frozen_asset_ids = {item.asset_id for item in plan_assets}
    plan_subproblems = [
        ResearchPlanSubproblem(
            id=str(uuid4()),
            order=index,
            question=draft.question.strip(),
            asset_ids=list(draft.asset_ids),
            expected_evidence=list(draft.expected_evidence),
        )
        for index, draft in enumerate(subproblems)
    ]
    if any(not set(item.asset_ids).issubset(frozen_asset_ids) for item in plan_subproblems):
        raise ResearchError("tool_scope_violation", "Research plan exceeds its frozen Asset scope.", 409)
    payload = ResearchPlanArtifactPayload(
        summary=summary.strip(),
        subproblems=plan_subproblems,
        known_gaps=list(known_gaps),
        estimated_provider_calls=estimated_provider_calls,
        estimated_input_tokens=estimated_input_tokens,
        estimated_output_tokens=estimated_output_tokens,
    )
    artifact_bytes = canonical_json(payload.model_dump(mode="json", by_alias=True))
    artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    artifact_id = str(uuid4())
    object_key = f"research/{run.workspace_id}/{run.id}/{artifact_id}/plan.json"
    stored = False
    try:
        store_bytes(object_key, artifact_bytes, "application/json")
        stored = True
        artifact = ResearchArtifact(
            id=artifact_id,
            workspace_id=run.workspace_id,
            run_id=run.id,
            generated_by_step_id=step.id,
            generated_by_attempt_id=attempt.id,
            artifact_kind="research_plan",
            visibility="user",
            logical_key=f"plan:revision-{revision.revision_number}",
            schema_version="1",
            object_key=object_key,
            content_type="application/json",
            byte_size=len(artifact_bytes),
            content_sha256=artifact_sha256,
            workflow_version_id=revision.proposed_workflow_version_id,
            direct_prompt_version_id=revision.planner_prompt_version_id,
            generation_provider=revision.proposed_generation_provider,
            generation_model=revision.proposed_generation_model,
            retention_class="workspace_lifetime",
            created_at=published_at,
        )
        gate = ResearchStep(
            workspace_id=run.workspace_id,
            run_id=run.id,
            plan_revision_id=revision.id,
            step_key=f"revision-{revision.revision_number}:plan-gate",
            step_kind="plan_approval_gate",
            status="waiting",
            max_attempts_snapshot=1,
            created_at=published_at,
            updated_at=published_at,
        )
        db.add_all([artifact, gate])
        db.flush()
        db.add(
            ResearchArtifactPromptVersion(
                artifact_id=artifact.id,
                node_key="planner",
                prompt_version_id=revision.planner_prompt_version_id,
            )
        )
        decision = HumanDecision(
            workspace_id=run.workspace_id,
            run_id=run.id,
            gate_step_id=gate.id,
            decision_type="plan_approval",
            request_number=revision.revision_number,
            status="pending",
            input_artifact_id=artifact.id,
            input_artifact_sha256=artifact.content_sha256,
            input_snapshot_sha256=revision.planning_snapshot_sha256,
            requested_at=published_at,
        )
        db.add(decision)
        db.flush()
        attempt.status = "succeeded"
        attempt.output_sha256 = artifact_sha256
        attempt.finished_at = published_at
        attempt.lease_expires_at = None
        step.status = "succeeded"
        step.state_version += 1
        step.finished_at = published_at
        step.updated_at = published_at
        run.state_version += 1
        append_research_event(
            db,
            run,
            event_type="step_succeeded",
            dedupe_key=f"step-succeeded:{attempt.id}",
            step_id=step.id,
            attempt_id=attempt.id,
            data={
                "stepId": step.id,
                "stepKind": step.step_kind,
                "attemptId": attempt.id,
                "attemptNumber": attempt.attempt_number,
                "evidenceCount": 0,
                "artifactIds": [artifact.id],
                "stepStateVersion": step.state_version,
                "runStateVersion": run.state_version,
            },
            now=published_at,
        )
        run.state_version += 1
        append_research_event(
            db,
            run,
            event_type="artifact_published",
            dedupe_key=f"artifact-published:{artifact.id}",
            data={
                "artifactId": artifact.id,
                "artifactKind": artifact.artifact_kind,
                "visibility": artifact.visibility,
                "byteSize": artifact.byte_size,
                "sha256": artifact.content_sha256,
                "runStateVersion": run.state_version,
            },
            now=published_at,
        )
        run.state_version += 1
        append_research_event(
            db,
            run,
            event_type="step_waiting",
            dedupe_key=f"step-waiting:{gate.id}:{decision.id}",
            step_id=gate.id,
            data={
                "stepId": gate.id,
                "stepKind": gate.step_kind,
                "decisionId": decision.id,
                "decisionType": decision.decision_type,
                "stepStateVersion": gate.state_version,
                "decisionStateVersion": decision.state_version,
                "runStateVersion": run.state_version,
            },
            now=published_at,
        )
        run.state_version += 1
        append_research_event(
            db,
            run,
            event_type="approval_requested",
            dedupe_key=f"approval-requested:{decision.id}",
            data={
                "decisionId": decision.id,
                "decisionType": decision.decision_type,
                "inputArtifactId": artifact.id,
                "inputArtifactSha256": artifact.content_sha256,
                "decisionStateVersion": decision.state_version,
                "runStateVersion": run.state_version,
            },
            now=published_at,
        )
        previous_status = run.status
        run.status = "awaiting_plan_approval"
        run.state_version += 1
        run.updated_at = published_at
        append_research_event(
            db,
            run,
            event_type="run_status_changed",
            dedupe_key=f"planning-complete:{revision.id}",
            data={
                "previousStatus": previous_status,
                "status": run.status,
                "runStateVersion": run.state_version,
                "reasonCode": None,
            },
            now=published_at,
        )
        db.commit()
    except Exception:
        db.rollback()
        if stored:
            cleanup_bytes(object_key)
        raise
    return {
        "artifactId": artifact_id,
        "artifactSha256": artifact_sha256,
        "decisionId": decision.id,
        "subproblems": [item.model_dump(mode="json", by_alias=True) for item in plan_subproblems],
    }
