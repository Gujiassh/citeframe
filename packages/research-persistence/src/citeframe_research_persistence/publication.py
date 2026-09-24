from __future__ import annotations
from citeframe_research_persistence.conflict_policy import INVESTIGATION_WORKFLOW_ID

import hashlib
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from uuid import uuid4

from citeframe_persistence.models import (
    HumanDecision,
    HumanDecisionClaim,
    ResearchArtifact,
    ResearchArtifactClaim,
    ResearchArtifactPromptVersion,
    ResearchClaim,
    ResearchExecutionPromptVersion,
    ResearchExecutionSnapshot,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import ResearchError, canonical_json
from .events import append_research_event
from .lease import _locked_attempt, complete_research_step
from .autonomy import AUTONOMOUS_WORKFLOW_ID
from .automatic_decisions import submit_policy_decision
from .publication_render import canonical_final_report as _canonical_final_report
from .publication_saga import final_commit_state as _final_commit_state
from .publication_saga import publish_final_report

__all__ = [
    "_canonical_final_report",
    "_final_commit_state",
    "publish_final_report",
    "wait_for_conflict_decision",
]


def wait_for_conflict_decision(
    db: Session,
    *,
    attempt_id: str,
    lease_token: str,
    conflict_claim_ids: Sequence[str],
    store_bytes: Callable[[str, bytes, str], None],
    cleanup_bytes: Callable[[str], None],
    now: datetime | None = None,
    locked_attempt: Callable[..., tuple[object, object, object]] = _locked_attempt,
    append_event: Callable[..., object] = append_research_event,
) -> str:
    requested_at = now or datetime.now(UTC)
    run, step, attempt = locked_attempt(
        db,
        attempt_id=attempt_id,
        lease_token=lease_token,
        now=requested_at,
    )
    if step.step_kind != "conflict_decision_gate" or step.execution_snapshot_id is None:
        raise ResearchError(
            "research_state_conflict", "Research conflict gate is invalid.", 409
        )
    snapshot = db.get(ResearchExecutionSnapshot, step.execution_snapshot_id)
    claim_ids = list(conflict_claim_ids)
    if not claim_ids or len(claim_ids) != len(set(claim_ids)):
        raise ValueError("conflict Claim ids must be non-empty and unique")
    claims = list(
        db.scalars(
            select(ResearchClaim)
            .execution_options(populate_existing=True)
            .where(
                ResearchClaim.id.in_(claim_ids),
                ResearchClaim.run_id == run.id,
                ResearchClaim.workspace_id == run.workspace_id,
            )
        ).all()
    )
    by_id = {claim.id: claim for claim in claims}
    if (
        snapshot is None
        or snapshot.run_id != run.id
        or snapshot.workspace_id != run.workspace_id
        or set(by_id) != set(claim_ids)
        or any(
            by_id[claim_id].verification_status != "supported"
            or by_id[claim_id].conflict_status != "conflicted"
            for claim_id in claim_ids
        )
    ):
        raise ResearchError(
            "research_state_conflict", "Research conflict report chain is invalid.", 409
        )
    if snapshot.workflow_version_id == INVESTIGATION_WORKFLOW_ID:
        from .conflict_investigation import investigation_outcome
        outcome = investigation_outcome(db, run.id)
        if outcome is None or {c["id"] for c in outcome["originalClaims"]} != set(claim_ids):
            raise ResearchError("research_state_conflict", "Conflict investigation is incomplete.", 409)
    artifact_id = str(uuid4())
    payload = canonical_json({"schemaVersion": 1, "conflictClaimIds": claim_ids})
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    object_key = f"research/{run.workspace_id}/{run.id}/{artifact_id}/conflicts.json"
    stored = False
    try:
        store_bytes(object_key, payload, "application/json")
        stored = True
        prompt_rows = list(
            db.scalars(
                select(ResearchExecutionPromptVersion).where(
                    ResearchExecutionPromptVersion.execution_snapshot_id == snapshot.id
                )
            ).all()
        )
        prompt_by_node = {row.node_key: row.prompt_version_id for row in prompt_rows}
        artifact = ResearchArtifact(
            id=artifact_id,
            workspace_id=run.workspace_id,
            run_id=run.id,
            generated_by_step_id=step.id,
            generated_by_attempt_id=attempt.id,
            artifact_kind="conflict_report",
            visibility="user",
            logical_key="conflict-report:1",
            schema_version="1",
            object_key=object_key,
            content_type="application/json",
            byte_size=len(payload),
            content_sha256=payload_sha256,
            workflow_version_id=snapshot.workflow_version_id,
            direct_prompt_version_id=prompt_by_node.get("critic"),
            generation_provider=snapshot.generation_provider,
            generation_model=snapshot.generation_model,
            retention_class="workspace_lifetime",
            created_at=requested_at,
        )
        db.add(artifact)
        db.flush()
        db.add_all(
            [
                ResearchArtifactPromptVersion(
                    artifact_id=artifact.id,
                    node_key=row.node_key,
                    prompt_version_id=row.prompt_version_id,
                )
                for row in prompt_rows
            ]
        )
        db.add_all(
            [
                ResearchArtifactClaim(
                    artifact_id=artifact.id,
                    claim_id=claim_id,
                    claim_order=index,
                    section_kind="conflict",
                )
                for index, claim_id in enumerate(claim_ids)
            ]
        )
        decision = HumanDecision(
            workspace_id=run.workspace_id,
            run_id=run.id,
            gate_step_id=step.id,
            decision_type="conflict_resolution",
            request_number=1,
            status="pending",
            input_artifact_id=artifact.id,
            input_artifact_sha256=artifact.content_sha256,
            input_snapshot_sha256=snapshot.execution_snapshot_sha256,
            requested_at=requested_at,
        )
        db.add(decision)
        db.flush()
        if snapshot.workflow_version_id in {AUTONOMOUS_WORKFLOW_ID, INVESTIGATION_WORKFLOW_ID}:
            def retain_unresolved(session, current_run, current_step, current_attempt):
                for claim in claims:
                    claim.conflict_status = "resolved_unresolved"
                    session.add(HumanDecisionClaim(decision_id=decision.id, claim_id=claim.id,
                                                   disposition="leave_unresolved"))
                submit_policy_decision(session, current_run, decision,
                                       action="keep_as_unresolved", now=requested_at)
                return 0, [artifact.id]
            complete_research_step(db, attempt_id=attempt_id, lease_token=lease_token,
                output_sha256=payload_sha256, complete=retain_unresolved, now=requested_at)
            run.state_version += 1
            append_event(db, run, event_type="artifact_published",
                dedupe_key=f"artifact-published:{artifact.id}",
                data={"artifactId": artifact.id, "artifactKind": artifact.artifact_kind,
                      "visibility": artifact.visibility, "byteSize": artifact.byte_size,
                      "sha256": artifact.content_sha256, "runStateVersion": run.state_version}, now=requested_at)
            db.flush()
            return decision.id
        attempt.status = "succeeded"
        attempt.output_sha256 = payload_sha256
        attempt.finished_at = requested_at
        attempt.lease_expires_at = None
        step.status = "waiting"
        step.state_version += 1
        step.updated_at = requested_at
        run.state_version += 1
        append_event(
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
            now=requested_at,
        )
        run.state_version += 1
        append_event(
            db,
            run,
            event_type="step_waiting",
            dedupe_key=f"step-waiting:{step.id}:{decision.id}",
            step_id=step.id,
            attempt_id=attempt.id,
            data={
                "stepId": step.id,
                "stepKind": step.step_kind,
                "decisionId": decision.id,
                "decisionType": decision.decision_type,
                "stepStateVersion": step.state_version,
                "decisionStateVersion": decision.state_version,
                "runStateVersion": run.state_version,
            },
            now=requested_at,
        )
        run.state_version += 1
        append_event(
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
            now=requested_at,
        )
        previous_status = run.status
        run.status = "awaiting_human_decision"
        run.updated_at = requested_at
        run.state_version += 1
        append_event(
            db,
            run,
            event_type="run_status_changed",
            dedupe_key=f"conflict-waiting:{decision.id}",
            data={
                "previousStatus": previous_status,
                "status": run.status,
                "runStateVersion": run.state_version,
                "reasonCode": None,
            },
            now=requested_at,
        )
        db.flush()
    except Exception:
        db.rollback()
        if stored:
            cleanup_bytes(object_key)
        raise
    return decision.id
