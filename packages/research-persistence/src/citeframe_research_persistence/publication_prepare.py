"""Durable preparation and commit-outcome oracles for final-report publication."""

# ruff: noqa: BLE001
from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable, Sequence
from datetime import timedelta
from uuid import uuid4

from citeframe_contracts import PublicationResult
from citeframe_persistence.models import (
    ResearchArtifact,
    ResearchArtifactClaim,
    ResearchArtifactPromptVersion,
    ResearchClaim,
    ResearchEvent,
    ResearchExecutionPromptVersion,
    ResearchExecutionSnapshot,
    ResearchPublicationIntent,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import ResearchError, canonical_json
from .locks import lock_attempt_chain
from .conflict_report import render_final_report
from .publication_saga_support import (
    MAX_PUBLICATION_BYTES,
    PUBLICATION_CLAIM_SECONDS,
    PublicationClaim,
    _as_utc,
    _claim_from_intent,
    _database_now,
    _safe_rollback,
    _selection_ids,
    _token_hash,
    _verify_frozen_intent,
)


def _committed_result_from_session(
    db: Session,
    intent: ResearchPublicationIntent,
) -> PublicationResult | None:
    if (
        intent.status != "committed"
        or intent.committed_artifact_id != intent.artifact_id
        or intent.adopted_object_generation is None
        or intent.adopted_object_generation <= 0
        or intent.adopted_object_key is None
        or intent.current_object_generation is not None
        or intent.current_object_key is not None
        or intent.resolved_at is None
        or intent.orphan_sweep_after is None
        or any(
            value is not None
            for value in (
                intent.claim_owner,
                intent.claim_token_hash,
                intent.claim_expires_at,
                intent.claim_heartbeat_at,
            )
        )
    ):
        return None
    try:
        _verify_frozen_intent(intent)
        fact_ids, unresolved_ids = _selection_ids(intent)
    except (ResearchError, KeyError, TypeError):
        return None
    def refreshed(model, row_id: str):
        return db.scalar(
            select(model)
            .where(model.id == row_id)
            .execution_options(populate_existing=True)
        )

    run = refreshed(ResearchRun, intent.run_id)
    step = refreshed(ResearchStep, intent.step_id)
    attempt = refreshed(ResearchStepAttempt, intent.attempt_id)
    snapshot = refreshed(ResearchExecutionSnapshot, intent.execution_snapshot_id)
    artifact = refreshed(ResearchArtifact, intent.artifact_id)
    if (
        run is None
        or step is None
        or attempt is None
        or snapshot is None
        or artifact is None
        or run.workspace_id != intent.workspace_id
        or run.status != "completed"
        or run.approved_execution_snapshot_id != snapshot.id
        or snapshot.run_id != run.id
        or snapshot.workspace_id != run.workspace_id
        or step.run_id != run.id
        or step.workspace_id != run.workspace_id
        or step.execution_snapshot_id != snapshot.id
        or step.step_kind != "artifact_publisher"
        or step.status != "succeeded"
        or step.current_attempt_number != attempt.attempt_number
        or step.finished_at is None
        or step.error_code is not None
        or step.error_message is not None
        or attempt.step_id != step.id
        or attempt.workspace_id != run.workspace_id
        or attempt.status != "succeeded"
        or attempt.output_sha256 != intent.content_sha256
        or attempt.finished_at is None
        or attempt.lease_expires_at is not None
        or attempt.error_code is not None
        or attempt.error_message is not None
        or artifact.workspace_id != run.workspace_id
        or artifact.run_id != run.id
        or artifact.generated_by_step_id != step.id
        or artifact.generated_by_attempt_id != attempt.id
        or artifact.artifact_kind != "final_report"
        or artifact.visibility != "user"
        or artifact.logical_key != "final-report"
        or artifact.schema_version != "1"
        or artifact.object_key != intent.adopted_object_key
        or artifact.content_type != intent.content_type
        or artifact.byte_size != intent.byte_size
        or artifact.content_sha256 != intent.content_sha256
        or artifact.workflow_version_id != snapshot.workflow_version_id
        or artifact.generation_provider != snapshot.generation_provider
        or artifact.generation_model != snapshot.generation_model
        or artifact.retention_class != "workspace_lifetime"
        or artifact.expires_at is not None
        or artifact.supersedes_artifact_id is not None
        or run.finished_at is None
        or run.failure_code is not None
        or run.failure_message is not None
        or attempt.finished_at != intent.resolved_at
        or step.finished_at != intent.resolved_at
        or run.finished_at != intent.resolved_at
        or step.updated_at != intent.resolved_at
        or run.updated_at != intent.resolved_at
        or artifact.created_at != intent.resolved_at
    ):
        return None
    prompt_rows = list(
        db.scalars(
            select(ResearchExecutionPromptVersion).where(
                ResearchExecutionPromptVersion.execution_snapshot_id == snapshot.id
            )
        ).all()
    )
    expected_prompts = {(row.node_key, row.prompt_version_id) for row in prompt_rows}
    actual_prompts = set(
        db.execute(
            select(
                ResearchArtifactPromptVersion.node_key,
                ResearchArtifactPromptVersion.prompt_version_id,
            ).where(ResearchArtifactPromptVersion.artifact_id == artifact.id)
        ).all()
    )
    synthesizer_prompt = dict(expected_prompts).get("synthesizer")
    expected_claims = [
        *((claim_id, index, "fact") for index, claim_id in enumerate(fact_ids)),
        *(
            (claim_id, len(fact_ids) + index, "unresolved")
            for index, claim_id in enumerate(unresolved_ids)
        ),
    ]
    actual_claims = list(
        db.execute(
            select(
                ResearchArtifactClaim.claim_id,
                ResearchArtifactClaim.claim_order,
                ResearchArtifactClaim.section_kind,
            )
            .where(ResearchArtifactClaim.artifact_id == artifact.id)
            .order_by(ResearchArtifactClaim.claim_order)
        ).all()
    )
    event_expectations = {
        f"step-succeeded:{attempt.id}": ("step_succeeded", step.id, attempt.id),
        f"artifact-published:{artifact.id}": ("artifact_published", None, None),
        f"run-completed:{artifact.id}": ("run_completed", None, None),
    }
    events = list(
        db.scalars(
            select(ResearchEvent).where(
                ResearchEvent.run_id == run.id,
                ResearchEvent.dedupe_key.in_(tuple(event_expectations)),
            )
        ).all()
    )
    semantic_terminal_events = list(
        db.scalars(
            select(ResearchEvent).where(
                ResearchEvent.run_id == run.id,
                ResearchEvent.event_type.in_(
                    ("step_succeeded", "artifact_published", "run_completed")
                ),
            )
        ).all()
    )
    semantic_terminal_events_valid = (
        len(
            [
                event
                for event in semantic_terminal_events
                if event.event_type == "run_completed"
            ]
        )
        == 1
        and all(
            isinstance(event.payload_json, dict)
            and isinstance(event.payload_json.get("artifactId"), str)
            for event in semantic_terminal_events
            if event.event_type == "artifact_published"
        )
        and len(
            [
                event
                for event in semantic_terminal_events
                if event.event_type == "step_succeeded"
                and (event.step_id == step.id or event.attempt_id == attempt.id)
            ]
        )
        == 1
        and len(
            [
                event
                for event in semantic_terminal_events
                if event.event_type == "artifact_published"
                and isinstance(event.payload_json, dict)
                and event.payload_json.get("artifactId") == artifact.id
            ]
        )
        == 1
    )
    events_by_key = {event.dedupe_key: event for event in events}
    step_event = events_by_key.get(f"step-succeeded:{attempt.id}")
    artifact_event = events_by_key.get(f"artifact-published:{artifact.id}")
    run_event = events_by_key.get(f"run-completed:{artifact.id}")
    expected_step_payload = {
        "stepId": step.id,
        "stepKind": step.step_kind,
        "attemptId": attempt.id,
        "attemptNumber": attempt.attempt_number,
        "evidenceCount": 0,
        "artifactIds": [artifact.id],
        "stepStateVersion": step.state_version,
        "runStateVersion": run.state_version - 2,
    }
    expected_artifact_payload = {
        "artifactId": artifact.id,
        "artifactKind": artifact.artifact_kind,
        "visibility": artifact.visibility,
        "byteSize": artifact.byte_size,
        "sha256": artifact.content_sha256,
        "runStateVersion": run.state_version - 1,
    }
    expected_run_payload = {
        "status": "completed",
        "finalArtifactId": artifact.id,
        "runStateVersion": run.state_version,
    }
    event_payloads_valid = bool(
        step_event is not None
        and artifact_event is not None
        and run_event is not None
        and all(event.workspace_id == run.workspace_id for event in events)
        and all(event.event_schema_version == "1" for event in events)
        and all(event.created_at == intent.resolved_at for event in events)
        and step_event.event_type == "step_succeeded"
        and step_event.step_id == step.id
        and step_event.attempt_id == attempt.id
        and step_event.payload_json == expected_step_payload
        and artifact_event.event_type == "artifact_published"
        and artifact_event.step_id is None
        and artifact_event.attempt_id is None
        and artifact_event.payload_json == expected_artifact_payload
        and run_event.event_type == "run_completed"
        and run_event.step_id is None
        and run_event.attempt_id is None
        and run_event.payload_json == expected_run_payload
        and artifact_event.seq == step_event.seq + 1
        and run_event.seq == artifact_event.seq + 1
        and run.next_event_seq == run_event.seq + 1
    )
    if (
        actual_prompts != expected_prompts
        or synthesizer_prompt is None
        or step.prompt_version_id != synthesizer_prompt
        or artifact.direct_prompt_version_id != synthesizer_prompt
        or actual_claims != expected_claims
        or len(events) != 3
        or not semantic_terminal_events_valid
        or not event_payloads_valid
    ):
        return None
    return PublicationResult.committed(artifact.id)


def _existing_result(
    session_factory: Callable[[], Session] | None,
    *,
    intent_id: str,
) -> PublicationResult | None:
    if session_factory is None:
        return None
    try:
        with session_factory() as verification_db:
            intent = verification_db.get(ResearchPublicationIntent, intent_id)
            if intent is not None and intent.status == "committed":
                committed = _committed_result_from_session(verification_db, intent)
                if committed is not None:
                    return committed
            if intent is not None:
                return PublicationResult.reconcile_pending(intent.id)
    except Exception:
        return None
    return None


def _observe_prepare_result(
    session_factory: Callable[[], Session] | None,
    *,
    claim: PublicationClaim,
) -> PublicationResult | None:
    """Return ``None`` only when the exact prepared claim is durably observable."""

    if session_factory is None:
        return PublicationResult.reconcile_pending(claim.intent_id)
    try:
        with session_factory() as verification_db:
            intent = verification_db.scalar(
                select(ResearchPublicationIntent)
                .where(ResearchPublicationIntent.id == claim.intent_id)
                .execution_options(populate_existing=True)
            )
            if intent is None:
                return PublicationResult.reconcile_pending(claim.intent_id)
            if intent.status == "committed":
                committed = _committed_result_from_session(verification_db, intent)
                if committed is not None:
                    return committed
                return PublicationResult.reconcile_pending(intent.id)
            expected_selection = {
                "factClaimIds": list(claim.fact_claim_ids),
                "unresolvedClaimIds": list(claim.unresolved_claim_ids),
            }
            claim_expiry = (
                _as_utc(intent.claim_expires_at)
                if intent.claim_expires_at is not None
                else None
            )
            claim_heartbeat = (
                _as_utc(intent.claim_heartbeat_at)
                if intent.claim_heartbeat_at is not None
                else None
            )
            exact_prepare = (
                intent.status == "prepared"
                and intent.workspace_id == claim.workspace_id
                and intent.run_id == claim.run_id
                and intent.step_id == claim.step_id
                and intent.attempt_id == claim.attempt_id
                and intent.execution_snapshot_id == claim.execution_snapshot_id
                and intent.logical_key == claim.logical_key == "final-report"
                and intent.artifact_id == claim.artifact_id
                and claim.generation > 0
                and intent.claim_generation == claim.generation
                and claim.current_object_generation == claim.generation
                and intent.current_object_generation
                == claim.current_object_generation
                and intent.current_object_key == claim.object_key
                and claim.object_key is not None
                and intent.object_prefix == claim.object_prefix
                and bytes(intent.payload_bytes) == claim.payload_bytes
                and intent.byte_size == claim.byte_size == len(claim.payload_bytes)
                and intent.content_sha256 == claim.content_sha256
                and intent.render_schema_version
                == claim.render_schema_version
                == "final-report-v1"
                and intent.selection_json == expected_selection
                and intent.selection_sha256 == claim.selection_sha256
                and intent.content_type == claim.content_type == "text/markdown"
                and claim.claim_owner is not None
                and bool(claim.claim_owner)
                and intent.claim_owner == claim.claim_owner
                and bool(claim.token)
                and claim.token_hash == _token_hash(claim.token)
                and intent.claim_token_hash == claim.token_hash
                and claim.claim_expires_at is not None
                and claim.claim_heartbeat_at is not None
                and claim_expiry == claim.claim_expires_at
                and claim_heartbeat == claim.claim_heartbeat_at
                and claim.claim_expires_at > claim.claim_heartbeat_at
            )
            return (
                None
                if exact_prepare
                else PublicationResult.reconcile_pending(intent.id)
            )
    except Exception:
        return PublicationResult.reconcile_pending(claim.intent_id)


def _commit_phase(
    db: Session,
    *,
    intent_id: str,
    session_factory: Callable[[], Session] | None,
    expected_prepare_claim: PublicationClaim | None = None,
) -> PublicationResult | None:
    try:
        db.commit()
        return None
    except Exception:
        try:
            _safe_rollback(db)
        except Exception as rollback_error:
            # A poisoned caller session must not suppress the independent outcome oracle.
            del rollback_error
        if expected_prepare_claim is not None:
            return _observe_prepare_result(
                session_factory, claim=expected_prepare_claim
            )
        observed = _existing_result(session_factory, intent_id=intent_id)
        return observed or PublicationResult.reconcile_pending(intent_id)


def _prepare_publication(
    db: Session,
    *,
    attempt_id: str,
    lease_token: str,
    fact_claim_ids: Sequence[str],
    unresolved_claim_ids: Sequence[str],
    prompt_loader: Callable[
        [Session, ResearchExecutionSnapshot], list[dict[str, object]]
    ],
    locked_attempt: Callable[..., tuple[object, object, object]],
) -> tuple[PublicationClaim | None, PublicationResult | None]:
    existing = db.scalar(
        select(ResearchPublicationIntent)
        .where(ResearchPublicationIntent.attempt_id == attempt_id)
        .with_for_update(of=ResearchPublicationIntent)
        .execution_options(populate_existing=True)
    )
    if existing is not None:
        if existing.status == "committed":
            committed = _committed_result_from_session(db, existing)
            if committed is not None:
                return None, committed
        return None, PublicationResult.reconcile_pending(existing.id)
    # Establish the canonical Run -> Step -> Attempt lock chain before taking the
    # command's single DB wall-clock sample.  The injected validator then reacquires
    # the same rows in this transaction without another wait and applies its full
    # lease/scope/membership checks against that post-lock timestamp.
    lock_attempt_chain(db, attempt_id)
    db_now = _database_now(db)
    existing = db.scalar(
        select(ResearchPublicationIntent)
        .where(ResearchPublicationIntent.attempt_id == attempt_id)
        .with_for_update(of=ResearchPublicationIntent)
        .execution_options(populate_existing=True)
    )
    if existing is not None:
        if existing.status == "committed":
            committed = _committed_result_from_session(db, existing)
            if committed is not None:
                return None, committed
        return None, PublicationResult.reconcile_pending(existing.id)
    run, step, attempt = locked_attempt(
        db,
        attempt_id=attempt_id,
        lease_token=lease_token,
        now=db_now,
    )
    if (
        step.step_kind != "artifact_publisher"
        or step.execution_snapshot_id is None
        or run.status != "running"
    ):
        raise ResearchError(
            "research_state_conflict", "Research final report cannot be published.", 409
        )
    snapshot = db.get(ResearchExecutionSnapshot, step.execution_snapshot_id)
    if (
        snapshot is None
        or snapshot.run_id != run.id
        or snapshot.workspace_id != run.workspace_id
        or run.approved_execution_snapshot_id != snapshot.id
    ):
        raise ResearchError(
            "research_state_conflict",
            "Research final publication chain is invalid.",
            409,
        )
    prompt_dtos = prompt_loader(db, snapshot)
    prompt_by_node = {
        str(item["nodeKey"]): str(item["promptVersionId"]) for item in prompt_dtos
    }
    synthesizer_prompt_id = prompt_by_node.get("synthesizer")
    if synthesizer_prompt_id is None or step.prompt_version_id != synthesizer_prompt_id:
        raise ResearchError(
            "research_state_conflict", "Research final Prompt chain is invalid.", 409
        )
    prompt_rows = list(
        db.scalars(
            select(ResearchExecutionPromptVersion).where(
                ResearchExecutionPromptVersion.execution_snapshot_id == snapshot.id
            )
        ).all()
    )
    if {row.node_key: row.prompt_version_id for row in prompt_rows} != prompt_by_node:
        raise ResearchError(
            "research_state_conflict", "Research final Prompt snapshot is invalid.", 409
        )

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
                select(ResearchClaim)
                .execution_options(populate_existing=True)
                .where(
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
        raise ResearchError(
            "research_state_conflict", "Final report references an invalid Claim.", 409
        )
    if any(
        claim.statement_sha256
        != hashlib.sha256(claim.statement_text.encode("utf-8")).hexdigest()
        for claim in claims
    ):
        raise ResearchError(
            "research_state_conflict", "Final report Claim integrity is invalid.", 409
        )
    if any(
        by_id[claim_id].verification_status != "supported"
        or by_id[claim_id].conflict_status != "none"
        for claim_id in fact_ids
    ):
        raise ResearchError(
            "research_state_conflict", "Final report facts are not publishable.", 409
        )
    if any(
        by_id[claim_id].verification_status != "supported"
        or by_id[claim_id].conflict_status != "resolved_unresolved"
        for claim_id in unresolved_ids
    ):
        raise ResearchError(
            "research_state_conflict",
            "Final report unresolved Claims are not publishable.",
            409,
        )

    report_bytes = render_final_report(
        db, snapshot,
        fact_claims=[by_id[claim_id] for claim_id in fact_ids],
        unresolved_claims=[by_id[claim_id] for claim_id in unresolved_ids],
    )
    if len(report_bytes) > MAX_PUBLICATION_BYTES:
        raise ResearchError(
            "research_publication_payload_too_large",
            "Research final report exceeds the publication size limit.",
            409,
        )
    selection = {"factClaimIds": fact_ids, "unresolvedClaimIds": unresolved_ids}
    selection_bytes = canonical_json(selection)
    artifact_id = str(uuid4())
    intent_id = str(uuid4())
    token = secrets.token_urlsafe(32)
    token_hash = _token_hash(token)
    object_prefix = f"research/{run.workspace_id}/{run.id}/{artifact_id}"
    generation = 1
    object_key = f"{object_prefix}/publication/{generation}/final.md"
    owner = attempt.worker_instance_id or "publication-origin"
    intent = ResearchPublicationIntent(
        id=intent_id,
        workspace_id=run.workspace_id,
        run_id=run.id,
        step_id=step.id,
        attempt_id=attempt.id,
        execution_snapshot_id=snapshot.id,
        logical_key="final-report",
        artifact_id=artifact_id,
        object_prefix=object_prefix,
        current_object_generation=generation,
        current_object_key=object_key,
        content_type="text/markdown",
        render_schema_version="final-report-v1",
        payload_bytes=report_bytes,
        byte_size=len(report_bytes),
        content_sha256=hashlib.sha256(report_bytes).hexdigest(),
        selection_json=selection,
        selection_sha256=hashlib.sha256(selection_bytes).hexdigest(),
        status="prepared",
        state_version=1,
        claim_generation=generation,
        claim_owner=owner,
        claim_token_hash=token_hash,
        claim_expires_at=db_now + timedelta(seconds=PUBLICATION_CLAIM_SECONDS),
        claim_heartbeat_at=db_now,
        next_reconcile_at=db_now,
        reconcile_attempt_count=1,
        created_at=db_now,
        updated_at=db_now,
    )
    db.add(intent)
    db.flush()
    return (
        _claim_from_intent(
            intent,
            token,
            requires_attempt_lease=True,
            attempt_lease_token_hash=_token_hash(lease_token),
        ),
        None,
    )
