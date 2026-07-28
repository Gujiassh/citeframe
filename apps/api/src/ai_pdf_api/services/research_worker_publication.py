from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from uuid import uuid4

from ai_pdf_api.models import (
    HumanDecision,
    ResearchArtifact,
    ResearchArtifactClaim,
    ResearchArtifactPromptVersion,
    ResearchClaim,
    ResearchExecutionPromptVersion,
    ResearchExecutionSnapshot,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
)
from ai_pdf_api.services.research import (
    ResearchError,
    append_research_event,
    canonical_json,
)
from ai_pdf_api.services.research_prompt_provenance import load_execution_prompt_dtos
from ai_pdf_api.services.storage import delete_object_if_exists, upload_bytes
from sqlalchemy import select
from sqlalchemy.orm import Session


def publish_final_report(
    db: Session,
    *,
    attempt_id: str,
    lease_token: str,
    fact_claim_ids: Sequence[str],
    unresolved_claim_ids: Sequence[str],
    store_bytes: Callable[[str, bytes, str], None] = upload_bytes,
    cleanup_bytes: Callable[[str], None] = delete_object_if_exists,
    committed_session_factory: Callable[[], Session] | None = None,
    now: datetime | None = None,
) -> str:
    from ai_pdf_api.services.research_worker_lease import _locked_attempt

    published_at = now or datetime.now(UTC)
    run, step, attempt = _locked_attempt(
        db,
        attempt_id=attempt_id,
        lease_token=lease_token,
        now=published_at,
    )
    if step.step_kind != "artifact_publisher" or step.execution_snapshot_id is None or run.status != "running":
        raise ResearchError("research_state_conflict", "Research final report cannot be published.", 409)
    snapshot = db.get(ResearchExecutionSnapshot, step.execution_snapshot_id)
    if (
        snapshot is None
        or snapshot.run_id != run.id
        or snapshot.workspace_id != run.workspace_id
        or run.approved_execution_snapshot_id != snapshot.id
    ):
        raise ResearchError("research_state_conflict", "Research final publication chain is invalid.", 409)
    prompt_dtos = load_execution_prompt_dtos(db, snapshot)
    prompt_by_node = {
        str(item["nodeKey"]): str(item["promptVersionId"])
        for item in prompt_dtos
    }
    synthesizer_prompt_id = prompt_by_node.get("synthesizer")
    if synthesizer_prompt_id is None or step.prompt_version_id != synthesizer_prompt_id:
        raise ResearchError("research_state_conflict", "Research final Prompt chain is invalid.", 409)
    fact_ids = list(fact_claim_ids)
    unresolved_ids = list(unresolved_claim_ids)
    selected_ids = [*fact_ids, *unresolved_ids]
    if (
        len(fact_ids) != len(set(fact_ids))
        or len(unresolved_ids) != len(set(unresolved_ids))
        or set(fact_ids).intersection(unresolved_ids)
    ):
        raise ValueError("final report Claim selections must be unique and disjoint")
    claims = (
        list(
            db.scalars(
                select(ResearchClaim).where(
                    ResearchClaim.id.in_(selected_ids),
                    ResearchClaim.run_id == run.id,
                    ResearchClaim.workspace_id == run.workspace_id,
                )
            ).all()
        )
        if selected_ids
        else []
    )
    by_id = {claim.id: claim for claim in claims}
    if set(by_id) != set(selected_ids):
        raise ResearchError("research_state_conflict", "Final report references an invalid Claim.", 409)
    if any(
        claim.statement_sha256
        != hashlib.sha256(claim.statement_text.encode("utf-8")).hexdigest()
        for claim in claims
    ):
        raise ResearchError("research_state_conflict", "Final report Claim integrity is invalid.", 409)
    if any(
        by_id[claim_id].verification_status != "supported"
        or by_id[claim_id].conflict_status != "none"
        for claim_id in fact_ids
    ):
        raise ResearchError("research_state_conflict", "Final report facts are not publishable.", 409)
    if any(
        by_id[claim_id].verification_status != "supported"
        or by_id[claim_id].conflict_status != "resolved_unresolved"
        for claim_id in unresolved_ids
    ):
        raise ResearchError("research_state_conflict", "Final report unresolved Claims are not publishable.", 409)
    report_bytes = _canonical_final_report(
        fact_claims=[by_id[claim_id] for claim_id in fact_ids],
        unresolved_claims=[by_id[claim_id] for claim_id in unresolved_ids],
    )
    artifact_id = str(uuid4())
    artifact_sha256 = hashlib.sha256(report_bytes).hexdigest()
    object_key = f"research/{run.workspace_id}/{run.id}/{artifact_id}/final.md"
    stored = False
    try:
        store_bytes(object_key, report_bytes, "text/markdown")
        stored = True
        prompt_rows = list(
            db.scalars(
                select(ResearchExecutionPromptVersion).where(
                    ResearchExecutionPromptVersion.execution_snapshot_id == snapshot.id
                )
            ).all()
        )
        persisted_prompt_by_node = {row.node_key: row.prompt_version_id for row in prompt_rows}
        if persisted_prompt_by_node != prompt_by_node:
            raise ResearchError("research_state_conflict", "Research final Prompt snapshot is invalid.", 409)
        artifact = ResearchArtifact(
            id=artifact_id,
            workspace_id=run.workspace_id,
            run_id=run.id,
            generated_by_step_id=step.id,
            generated_by_attempt_id=attempt.id,
            artifact_kind="final_report",
            visibility="user",
            logical_key="final-report",
            schema_version="1",
            object_key=object_key,
            content_type="text/markdown",
            byte_size=len(report_bytes),
            content_sha256=artifact_sha256,
            workflow_version_id=snapshot.workflow_version_id,
            direct_prompt_version_id=synthesizer_prompt_id,
            generation_provider=snapshot.generation_provider,
            generation_model=snapshot.generation_model,
            retention_class="workspace_lifetime",
            created_at=published_at,
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
        claim_order = 0
        for claim_id in fact_ids:
            db.add(
                ResearchArtifactClaim(
                    artifact_id=artifact.id,
                    claim_id=claim_id,
                    claim_order=claim_order,
                    section_kind="fact",
                )
            )
            claim_order += 1
        for claim_id in unresolved_ids:
            db.add(
                ResearchArtifactClaim(
                    artifact_id=artifact.id,
                    claim_id=claim_id,
                    claim_order=claim_order,
                    section_kind="unresolved",
                )
            )
            claim_order += 1
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
        run.status = "completed"
        run.finished_at = published_at
        run.updated_at = published_at
        run.state_version += 1
        append_research_event(
            db,
            run,
            event_type="run_completed",
            dedupe_key=f"run-completed:{artifact.id}",
            data={
                "status": "completed",
                "finalArtifactId": artifact.id,
                "runStateVersion": run.state_version,
            },
            now=published_at,
        )
        db.flush()
    except Exception:
        db.rollback()
        if stored:
            cleanup_bytes(object_key)
        raise
    try:
        db.commit()
    except Exception as commit_error:
        db.rollback()
        commit_state = _final_commit_state(
            committed_session_factory,
            artifact_id=artifact_id,
            run_id=run.id,
            step_id=step.id,
            attempt_id=attempt.id,
            artifact_sha256=artifact_sha256,
            object_key=object_key,
        )
        if commit_state == "committed":
            return artifact_id
        if commit_state == "absent" and stored:
            cleanup_bytes(object_key)
        if commit_state == "unknown":
            raise ResearchError(
                "research_commit_outcome_unknown",
                "Research final publication commit outcome is unknown.",
                503,
            ) from commit_error
        raise
    return artifact_id


def _final_commit_state(
    session_factory: Callable[[], Session] | None,
    *,
    artifact_id: str,
    run_id: str,
    step_id: str,
    attempt_id: str,
    artifact_sha256: str,
    object_key: str,
) -> str:
    if session_factory is None:
        from ai_pdf_api.db.session import SessionLocal

        session_factory = SessionLocal
    try:
        with session_factory() as verification_db:
            artifact = verification_db.get(ResearchArtifact, artifact_id)
            if artifact is None:
                return "absent"
            run = verification_db.get(ResearchRun, run_id)
            step = verification_db.get(ResearchStep, step_id)
            attempt = verification_db.get(ResearchStepAttempt, attempt_id)
            if (
                artifact.run_id == run_id
                and artifact.generated_by_step_id == step_id
                and artifact.generated_by_attempt_id == attempt_id
                and artifact.artifact_kind == "final_report"
                and artifact.content_sha256 == artifact_sha256
                and artifact.object_key == object_key
                and run is not None
                and run.status == "completed"
                and step is not None
                and step.status == "succeeded"
                and attempt is not None
                and attempt.status == "succeeded"
                and attempt.output_sha256 == artifact_sha256
            ):
                return "committed"
            return "unknown"
    except Exception:
        return "unknown"


def _canonical_final_report(
    *,
    fact_claims: Sequence[ResearchClaim],
    unresolved_claims: Sequence[ResearchClaim],
) -> bytes:
    def append_claim(lines: list[str], claim: ResearchClaim, section: str) -> None:
        statement = (
            claim.statement_text.replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("<!--", "&lt;!--")
            .replace("-->", "--&gt;")
            .strip()
        )
        rendered = statement.replace("\n", "\n  ")
        lines.extend(
            (
                f"<!-- citeframe:claim id={claim.id} section={section} -->",
                f"- {rendered}",
            )
        )

    lines = ["# Citeframe Research Report", "", "## Findings"]
    if fact_claims:
        for claim in fact_claims:
            append_claim(lines, claim, "fact")
    else:
        lines.append("- No supported findings.")
    if unresolved_claims:
        lines.extend(("", "## Unresolved Evidence Conflicts"))
        for claim in unresolved_claims:
            append_claim(lines, claim, "unresolved")
    return ("\n".join(lines) + "\n").encode("utf-8")


def wait_for_conflict_decision(
    db: Session,
    *,
    attempt_id: str,
    lease_token: str,
    conflict_claim_ids: Sequence[str],
    store_bytes: Callable[[str, bytes, str], None] = upload_bytes,
    cleanup_bytes: Callable[[str], None] = delete_object_if_exists,
    now: datetime | None = None,
) -> str:
    from ai_pdf_api.services.research_worker_lease import _locked_attempt

    requested_at = now or datetime.now(UTC)
    run, step, attempt = _locked_attempt(
        db,
        attempt_id=attempt_id,
        lease_token=lease_token,
        now=requested_at,
    )
    if step.step_kind != "conflict_decision_gate" or step.execution_snapshot_id is None:
        raise ResearchError("research_state_conflict", "Research conflict gate is invalid.", 409)
    snapshot = db.get(ResearchExecutionSnapshot, step.execution_snapshot_id)
    claim_ids = list(conflict_claim_ids)
    if not claim_ids or len(claim_ids) != len(set(claim_ids)):
        raise ValueError("conflict Claim ids must be non-empty and unique")
    claims = list(
        db.scalars(
            select(ResearchClaim).where(
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
        raise ResearchError("research_state_conflict", "Research conflict report chain is invalid.", 409)
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
        attempt.status = "succeeded"
        attempt.output_sha256 = payload_sha256
        attempt.finished_at = requested_at
        attempt.lease_expires_at = None
        step.status = "waiting"
        step.state_version += 1
        step.updated_at = requested_at
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
            now=requested_at,
        )
        run.state_version += 1
        append_research_event(
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
            now=requested_at,
        )
        previous_status = run.status
        run.status = "awaiting_human_decision"
        run.updated_at = requested_at
        run.state_version += 1
        append_research_event(
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
        db.commit()
    except Exception:
        db.rollback()
        if stored:
            cleanup_bytes(object_key)
        raise
    return decision.id
