"""Atomic finalization and two-pass compensation for publication intents."""

# ruff: noqa: BLE001
from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta

from citeframe_contracts import PublicationResult
from citeframe_persistence.models import (
    EvidenceLocator,
    HumanDecision,
    HumanDecisionClaim,
    ResearchArtifact,
    ResearchArtifactClaim,
    ResearchArtifactPromptVersion,
    ResearchClaim,
    ResearchClaimEvidence,
    ResearchEvent,
    ResearchEvidenceHandle,
    ResearchEvidenceSnapshot,
    ResearchExecutionPromptVersion,
    ResearchExecutionSnapshot,
    ResearchPublicationIntent,
    ResearchStep,
    ResearchStepAttempt,
    ResearchToolCall,
)
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from .errors import ResearchError, canonical_json, canonical_sha256
from .events import append_research_event
from .evidence import validate_evidence_source_fingerprint
from .membership import finalize_cancel_if_idle
from .publication_prepare import _commit_phase
from .publication_render import canonical_final_report
from .publication_saga_support import (
    _COMPENSATION_SWEEP_PENDING,
    PUBLICATION_IDLE_SWEEP_SECONDS,
    PUBLICATION_RETRY_SECONDS,
    PublicationClaim,
    _as_utc,
    _clear_claim,
    _lock_fenced_intent,
    _lock_publication_chain,
    _PublicationHeartbeatLost,
    _release_for_retry,
    _release_locked_for_reconcile,
    _run_storage_operation,
    _safe_rollback,
    _selection_ids,
    _transition_claim_compensating,
    _transition_compensating,
    _verify_claim_matches_intent,
    _verify_compensation_claim_scope,
    _verify_frozen_intent,
)
from .snapshot_integrity import execution_snapshot_provenance_is_valid


def _artifact_conflict_query(
    intent: ResearchPublicationIntent,
    *,
    object_key: str | None,
):
    """Locate any Artifact that makes this intent unsafe to finalize or delete."""

    conditions = [
        and_(
            ResearchArtifact.run_id == intent.run_id,
            ResearchArtifact.logical_key == "final-report",
        ),
        ResearchArtifact.id == intent.artifact_id,
        ResearchArtifact.object_key.like(f"{intent.object_prefix}/%"),
    ]
    if object_key is not None:
        conditions.append(ResearchArtifact.object_key == object_key)
    return select(ResearchArtifact.id).where(or_(*conditions)).limit(1)


def _defer_compensating(
    db: Session,
    intent: ResearchPublicationIntent,
    *,
    db_now: datetime,
    error_code: str,
    next_reconcile_at: datetime | None = None,
) -> None:
    """Keep permanent conflicts durable without allowing a destructive sweep."""

    _transition_compensating(
        db,
        intent=intent,
        db_now=db_now,
        reason_code=error_code,
    )
    intent.next_reconcile_at = next_reconcile_at or (
        db_now + timedelta(seconds=PUBLICATION_IDLE_SWEEP_SECONDS)
    )
    _clear_claim(intent)


def _guard_compensation_storage_ownership(
    db: Session,
    claim: PublicationClaim,
) -> bool:
    """Fail closed before LIST/DELETE when an Artifact owns this id or prefix."""

    intent, db_now = _lock_fenced_intent(
        db,
        claim,
        expected_statuses=("compensating",),
    )
    _verify_compensation_claim_scope(intent, claim)
    conflict = db.scalar(_artifact_conflict_query(intent, object_key=claim.object_key))
    if conflict is not None:
        _defer_compensating(
            db,
            intent,
            db_now=db_now,
            error_code="research_publication_artifact_ownership_conflict",
        )
        db.commit()
        return False
    _safe_rollback(db)
    return True


def _is_succeeded_snapshot_step(
    candidate: ResearchStep | None,
    *,
    run_id: str,
    workspace_id: str,
    snapshot_id: str,
    step_kind: str,
) -> bool:
    return bool(
        candidate is not None
        and candidate.run_id == run_id
        and candidate.workspace_id == workspace_id
        and candidate.execution_snapshot_id == snapshot_id
        and candidate.step_kind == step_kind
        and candidate.status == "succeeded"
        and candidate.finished_at is not None
        and candidate.error_code is None
        and candidate.error_message is None
    )


def _current_succeeded_attempt(
    db: Session,
    *,
    step: ResearchStep,
    workspace_id: str,
    require_step_finished_match: bool = True,
) -> ResearchStepAttempt | None:
    latest_attempt_id = db.scalar(
        select(ResearchStepAttempt.id)
        .where(ResearchStepAttempt.step_id == step.id)
        .order_by(ResearchStepAttempt.attempt_number.desc())
        .limit(1)
    )
    attempt = db.scalar(
        select(ResearchStepAttempt)
        .where(
            ResearchStepAttempt.step_id == step.id,
            ResearchStepAttempt.attempt_number == step.current_attempt_number,
        )
        .execution_options(populate_existing=True)
    )
    if (
        attempt is None
        or latest_attempt_id != attempt.id
        or attempt.workspace_id != workspace_id
        or attempt.status != "succeeded"
        or attempt.finished_at is None
        or attempt.lease_expires_at is not None
        or attempt.error_code is not None
        or attempt.error_message is not None
        or (require_step_finished_match and step.finished_at != attempt.finished_at)
    ):
        return None
    return attempt


def _conflict_decision_is_valid(
    db: Session,
    *,
    claim: ResearchClaim,
    run_id: str,
    workspace_id: str,
    snapshot: ResearchExecutionSnapshot,
    prompt_rows: Sequence[ResearchExecutionPromptVersion],
) -> bool:
    expected_prompts = {(row.node_key, row.prompt_version_id) for row in prompt_rows}
    critic_prompt_id = dict(expected_prompts).get("critic")
    decisions = list(
        db.execute(
            select(HumanDecisionClaim, HumanDecision)
            .join(HumanDecision, HumanDecision.id == HumanDecisionClaim.decision_id)
            .where(HumanDecisionClaim.claim_id == claim.id)
        ).all()
    )
    valid_decisions: list[str] = []
    for binding, decision in decisions:
        gate = db.scalar(
            select(ResearchStep)
            .where(ResearchStep.id == decision.gate_step_id)
            .execution_options(populate_existing=True)
        )
        if not _is_succeeded_snapshot_step(
            gate,
            run_id=run_id,
            workspace_id=workspace_id,
            snapshot_id=snapshot.id,
            step_kind="conflict_decision_gate",
        ):
            continue
        assert gate is not None
        gate_attempt = _current_succeeded_attempt(
            db,
            step=gate,
            workspace_id=workspace_id,
            require_step_finished_match=False,
        )
        conflict_artifact = db.scalar(
            select(ResearchArtifact)
            .where(ResearchArtifact.id == decision.input_artifact_id)
            .execution_options(populate_existing=True)
        )
        if conflict_artifact is None or gate_attempt is None:
            continue
        raw_binding_count = (
            db.scalar(
                select(func.count())
                .select_from(ResearchArtifactClaim)
                .where(ResearchArtifactClaim.artifact_id == conflict_artifact.id)
            )
            or 0
        )
        conflict_bindings = list(
            db.scalars(
                select(ResearchArtifactClaim)
                .where(ResearchArtifactClaim.artifact_id == conflict_artifact.id)
                .order_by(ResearchArtifactClaim.claim_order)
            ).all()
        )
        conflict_claim_ids = [row.claim_id for row in conflict_bindings]
        payload = canonical_json(
            {"schemaVersion": 1, "conflictClaimIds": conflict_claim_ids}
        )
        actual_prompts = set(
            db.execute(
                select(
                    ResearchArtifactPromptVersion.node_key,
                    ResearchArtifactPromptVersion.prompt_version_id,
                ).where(
                    ResearchArtifactPromptVersion.artifact_id == conflict_artifact.id
                )
            ).all()
        )
        expected_object_key = (
            f"research/{workspace_id}/{run_id}/{conflict_artifact.id}/conflicts.json"
        )
        if (
            binding.disposition == "leave_unresolved"
            and decision.workspace_id == workspace_id
            and decision.run_id == run_id
            and decision.decision_type == "conflict_resolution"
            and decision.status == "submitted"
            and decision.action == "keep_as_unresolved"
            and decision.decided_by_user_id is not None
            and decision.decided_at is not None
            and _as_utc(decision.decided_at) >= _as_utc(decision.requested_at)
            and decision.requested_at == conflict_artifact.created_at
            and decision.input_snapshot_sha256 == snapshot.execution_snapshot_sha256
            and decision.input_artifact_sha256 == conflict_artifact.content_sha256
            and gate.finished_at == decision.decided_at
            and gate_attempt.output_sha256 == conflict_artifact.content_sha256
            and gate_attempt.checkpoint_artifact_id is None
            and gate_attempt.finished_at == conflict_artifact.created_at
            and conflict_artifact.workspace_id == workspace_id
            and conflict_artifact.run_id == run_id
            and conflict_artifact.generated_by_step_id == gate.id
            and conflict_artifact.generated_by_attempt_id == gate_attempt.id
            and conflict_artifact.artifact_kind == "conflict_report"
            and conflict_artifact.visibility == "user"
            and conflict_artifact.logical_key == "conflict-report:1"
            and conflict_artifact.schema_version == "1"
            and conflict_artifact.object_key == expected_object_key
            and conflict_artifact.content_type == "application/json"
            and conflict_artifact.byte_size == len(payload)
            and conflict_artifact.content_sha256 == hashlib.sha256(payload).hexdigest()
            and conflict_artifact.workflow_version_id == snapshot.workflow_version_id
            and critic_prompt_id is not None
            and conflict_artifact.direct_prompt_version_id == critic_prompt_id
            and actual_prompts == expected_prompts
            and conflict_artifact.generation_provider == snapshot.generation_provider
            and conflict_artifact.generation_model == snapshot.generation_model
            and conflict_artifact.retention_class == "workspace_lifetime"
            and conflict_artifact.expires_at is None
            and conflict_artifact.supersedes_artifact_id is None
            and len(conflict_bindings) == raw_binding_count
            and conflict_claim_ids
            and len(conflict_claim_ids) == len(set(conflict_claim_ids))
            and [row.claim_order for row in conflict_bindings]
            == list(range(len(conflict_bindings)))
            and all(row.section_kind == "conflict" for row in conflict_bindings)
            and claim.id in conflict_claim_ids
        ):
            valid_decisions.append(decision.id)
    return len(valid_decisions) == 1


def _claim_provenance_is_valid(
    db: Session,
    *,
    claims: Sequence[ResearchClaim],
    fact_ids: Sequence[str],
    unresolved_ids: Sequence[str],
    run_id: str,
    workspace_id: str,
    snapshot: ResearchExecutionSnapshot,
    prompt_rows: Sequence[ResearchExecutionPromptVersion],
) -> bool:
    """Validate the mutable Claim graph again at the irreversible commit boundary."""

    step_ids = {
        step_id
        for claim in claims
        for step_id in (
            claim.produced_by_step_id,
            claim.verified_by_step_id,
            claim.critic_step_id,
        )
        if step_id is not None
    }
    steps = (
        list(
            db.scalars(
                select(ResearchStep)
                .where(ResearchStep.id.in_(step_ids))
                .execution_options(populate_existing=True)
            ).all()
        )
        if step_ids
        else []
    )
    steps_by_id = {row.id: row for row in steps}
    if set(steps_by_id) != step_ids:
        return False

    unresolved = set(unresolved_ids)
    facts = set(fact_ids)
    for claim in claims:
        producer = steps_by_id.get(claim.produced_by_step_id)
        verifier = steps_by_id.get(claim.verified_by_step_id or "")
        critic = steps_by_id.get(claim.critic_step_id or "")
        if (
            not _is_succeeded_snapshot_step(
                producer,
                run_id=run_id,
                workspace_id=workspace_id,
                snapshot_id=snapshot.id,
                step_kind="researcher",
            )
            or not _is_succeeded_snapshot_step(
                verifier,
                run_id=run_id,
                workspace_id=workspace_id,
                snapshot_id=snapshot.id,
                step_kind="verifier",
            )
            or claim.verified_at is None
        ):
            return False
        assert producer is not None and verifier is not None
        producer_attempt = _current_succeeded_attempt(
            db,
            step=producer,
            workspace_id=workspace_id,
        )
        verifier_attempt = _current_succeeded_attempt(
            db,
            step=verifier,
            workspace_id=workspace_id,
        )
        prompt_by_node = {row.node_key: row.prompt_version_id for row in prompt_rows}
        if (
            producer_attempt is None
            or verifier_attempt is None
            or producer.prompt_version_id != prompt_by_node.get("researchers")
            or verifier.prompt_version_id != prompt_by_node.get("verifier")
            or claim.created_at != producer_attempt.finished_at
            or claim.verified_at != verifier_attempt.finished_at
        ):
            return False
        if claim.id in facts:
            # A Claim that traversed conflict resolution cannot return to ``none``.
            if claim.critic_step_id is not None:
                return False
        elif claim.id in unresolved:
            if not _is_succeeded_snapshot_step(
                critic,
                run_id=run_id,
                workspace_id=workspace_id,
                snapshot_id=snapshot.id,
                step_kind="critic",
            ):
                return False
            assert critic is not None
            critic_attempt = _current_succeeded_attempt(
                db,
                step=critic,
                workspace_id=workspace_id,
            )
            if (
                critic_attempt is None
                or critic.prompt_version_id != prompt_by_node.get("critic")
                or not _conflict_decision_is_valid(
                    db,
                    claim=claim,
                    run_id=run_id,
                    workspace_id=workspace_id,
                    snapshot=snapshot,
                    prompt_rows=prompt_rows,
                )
            ):
                return False
        else:
            return False

        raw_relation_count = (
            db.scalar(
                select(func.count())
                .select_from(ResearchClaimEvidence)
                .where(ResearchClaimEvidence.claim_id == claim.id)
            )
            or 0
        )
        relations = list(
            db.execute(
                select(ResearchClaimEvidence, ResearchEvidenceSnapshot)
                .join(
                    ResearchEvidenceSnapshot,
                    ResearchEvidenceSnapshot.id
                    == ResearchClaimEvidence.evidence_snapshot_id,
                )
                .where(ResearchClaimEvidence.claim_id == claim.id)
                .order_by(ResearchClaimEvidence.evidence_order)
            ).all()
        )
        if (
            not relations
            or len(relations) != raw_relation_count
            or [relation.evidence_order for relation, _evidence in relations]
            != list(range(len(relations)))
        ):
            return False
        for relation, evidence in relations:
            handles = list(
                db.scalars(
                    select(ResearchEvidenceHandle).where(
                        ResearchEvidenceHandle.evidence_snapshot_id == evidence.id,
                        ResearchEvidenceHandle.owner_step_id == producer.id,
                    )
                ).all()
            )
            locator = db.scalar(
                select(EvidenceLocator)
                .where(EvidenceLocator.id == evidence.evidence_locator_id)
                .execution_options(populate_existing=True)
            )
            try:
                if locator is not None:
                    validate_evidence_source_fingerprint(
                        evidence,
                        locator_kind=locator.locator_kind,
                    )
            except ValueError:
                return False
            if (
                relation.relationship != "supports"
                or relation.assessed_by_step_id != verifier.id
                or evidence.workspace_id != workspace_id
                or evidence.run_id != run_id
                or evidence.captured_by_step_id != producer.id
                or locator is None
                or locator.workspace_id != workspace_id
                or locator.asset_id != evidence.asset_id
                or locator.processing_generation_snapshot
                != evidence.processing_generation_snapshot
                or locator.representation_id_snapshot
                != evidence.representation_id_snapshot
                or not handles
                or any(
                    handle.workspace_id != workspace_id
                    or handle.run_id != run_id
                    or handle.execution_snapshot_id != snapshot.id
                    or handle.owner_step_id != producer.id
                    or handle.evidence_snapshot_id != evidence.id
                    or (
                        (
                            tool_call := db.scalar(
                                select(ResearchToolCall)
                                .where(
                                    ResearchToolCall.id
                                    == handle.created_by_tool_call_id
                                )
                                .execution_options(populate_existing=True)
                            )
                        )
                        is None
                        or tool_call.workspace_id != workspace_id
                        or tool_call.run_id != run_id
                        or tool_call.execution_snapshot_id != snapshot.id
                        or tool_call.step_id != producer.id
                        or tool_call.attempt_id != producer_attempt.id
                        or tool_call.status != "succeeded"
                        or tool_call.finished_at is None
                    )
                    for handle in handles
                )
            ):
                return False
    return True


def _synthesis_checkpoint_is_valid(
    db: Session,
    *,
    run,
    snapshot: ResearchExecutionSnapshot,
    synthesizer: ResearchStep | None,
    expected_prompt_id: str | None,
    fact_ids: Sequence[str],
    unresolved_ids: Sequence[str],
) -> bool:
    if (
        not _is_succeeded_snapshot_step(
            synthesizer,
            run_id=run.id,
            workspace_id=run.workspace_id,
            snapshot_id=snapshot.id,
            step_kind="synthesizer",
        )
        or expected_prompt_id is None
    ):
        return False
    assert synthesizer is not None
    latest_attempt_id = db.scalar(
        select(ResearchStepAttempt.id)
        .where(ResearchStepAttempt.step_id == synthesizer.id)
        .order_by(ResearchStepAttempt.attempt_number.desc())
        .limit(1)
    )
    synthesis_attempt = db.scalar(
        select(ResearchStepAttempt)
        .where(
            ResearchStepAttempt.step_id == synthesizer.id,
            ResearchStepAttempt.attempt_number == synthesizer.current_attempt_number,
        )
        .execution_options(populate_existing=True)
    )
    checkpoint = (
        db.scalar(
            select(ResearchArtifact)
            .where(ResearchArtifact.id == synthesis_attempt.checkpoint_artifact_id)
            .execution_options(populate_existing=True)
        )
        if synthesis_attempt is not None
        and synthesis_attempt.checkpoint_artifact_id is not None
        else None
    )
    payload = canonical_json(
        {
            "schemaVersion": 1,
            "runId": run.id,
            "stepId": synthesizer.id,
            "attemptId": synthesis_attempt.id
            if synthesis_attempt is not None
            else None,
            "factClaimIds": list(fact_ids),
            "unresolvedClaimIds": list(unresolved_ids),
        }
    )
    expected_selection_sha = canonical_sha256(
        {"factClaimIds": list(fact_ids), "unresolvedClaimIds": list(unresolved_ids)}
    )
    expected_object_key = (
        f"research/{run.workspace_id}/{run.id}/{checkpoint.id}/checkpoint.json"
        if checkpoint is not None
        else None
    )
    return bool(
        synthesis_attempt is not None
        and checkpoint is not None
        and latest_attempt_id == synthesis_attempt.id
        and synthesizer.current_attempt_number == synthesis_attempt.attempt_number
        and synthesizer.prompt_version_id == expected_prompt_id
        and synthesis_attempt.workspace_id == run.workspace_id
        and synthesis_attempt.status == "succeeded"
        and synthesis_attempt.output_sha256 == expected_selection_sha
        and synthesis_attempt.finished_at is not None
        and synthesis_attempt.lease_expires_at is None
        and synthesis_attempt.error_code is None
        and synthesis_attempt.error_message is None
        and synthesis_attempt.checkpoint_artifact_id == checkpoint.id
        and run.latest_checkpoint_artifact_id == checkpoint.id
        and checkpoint.workspace_id == run.workspace_id
        and checkpoint.run_id == run.id
        and checkpoint.generated_by_step_id == synthesizer.id
        and checkpoint.generated_by_attempt_id == synthesis_attempt.id
        and checkpoint.artifact_kind == "execution_checkpoint"
        and checkpoint.visibility == "internal"
        and checkpoint.logical_key == "checkpoint:synthesis"
        and checkpoint.schema_version == "1"
        and checkpoint.object_key == expected_object_key
        and checkpoint.content_type == "application/json"
        and checkpoint.byte_size == len(payload)
        and checkpoint.content_sha256 == hashlib.sha256(payload).hexdigest()
        and checkpoint.workflow_version_id == snapshot.workflow_version_id
        and checkpoint.direct_prompt_version_id == expected_prompt_id
        and checkpoint.generation_provider == snapshot.generation_provider
        and checkpoint.generation_model == snapshot.generation_model
        and checkpoint.retention_class == "workspace_lifetime"
        and checkpoint.expires_at is None
        and checkpoint.supersedes_artifact_id is None
        and checkpoint.created_at == synthesis_attempt.finished_at
    )


def _terminal_event_semantic_conflict(
    db: Session,
    *,
    run_id: str,
    step_id: str,
    attempt_id: str,
    artifact_id: str,
) -> bool:
    events = list(
        db.scalars(
            select(ResearchEvent).where(
                ResearchEvent.run_id == run_id,
                ResearchEvent.event_type.in_(
                    ("step_succeeded", "artifact_published", "run_completed")
                ),
            )
        ).all()
    )
    return any(
        event.event_type == "run_completed"
        or (
            event.event_type == "step_succeeded"
            and (event.step_id == step_id or event.attempt_id == attempt_id)
        )
        or (
            event.event_type == "artifact_published"
            and (
                not isinstance(event.payload_json, dict)
                or not isinstance(event.payload_json.get("artifactId"), str)
                or event.payload_json.get("artifactId") == artifact_id
            )
        )
        for event in events
    )


def _finalize(
    db: Session,
    claim: PublicationClaim,
    *,
    append_event: Callable[..., object],
    session_factory: Callable[[], Session] | None,
    prompt_loader: Callable[
        [Session, ResearchExecutionSnapshot], list[dict[str, object]]
    ],
) -> PublicationResult:
    try:
        run, step, attempt, intent, db_now = _lock_publication_chain(db, claim)
        if intent.status == "committed":
            _safe_rollback(db)
            return PublicationResult.committed(intent.artifact_id)
        try:
            _verify_frozen_intent(intent)
            _verify_claim_matches_intent(intent, claim)
            fact_ids, unresolved_ids = _selection_ids(intent)
        except ResearchError as error:
            _transition_compensating(
                db,
                intent=intent,
                db_now=db_now,
                reason_code=error.code,
            )
            db.commit()
            return PublicationResult.reconcile_pending(intent.id)
        if run.status == "cancel_requested":
            _transition_compensating(
                db,
                intent=intent,
                db_now=db_now,
                reason_code="research_publication_cancelled",
            )
            db.commit()
            return PublicationResult.reconcile_pending(intent.id)
        attempt_expiry = (
            _as_utc(attempt.lease_expires_at)
            if attempt.lease_expires_at is not None
            else None
        )
        if claim.requires_attempt_lease and (
            claim.attempt_lease_token_hash is None
            or attempt.lease_token_hash != claim.attempt_lease_token_hash
            or attempt_expiry is None
            or attempt_expiry <= db_now
        ):
            _release_locked_for_reconcile(
                intent,
                db_now=db_now,
                error_code="research_publication_attempt_lease_expired",
            )
            db.commit()
            return PublicationResult.reconcile_pending(intent.id)
        if not claim.requires_attempt_lease and attempt_expiry is None:
            _transition_compensating(
                db,
                intent=intent,
                db_now=db_now,
                reason_code="research_publication_attempt_lease_invalid",
            )
            db.commit()
            return PublicationResult.reconcile_pending(intent.id)
        if (
            not claim.requires_attempt_lease
            and attempt_expiry is not None
            and attempt_expiry > db_now
        ):
            _release_locked_for_reconcile(
                intent,
                db_now=db_now,
                error_code="research_publication_attempt_lease_active",
                next_reconcile_at=attempt_expiry,
            )
            db.commit()
            return PublicationResult.reconcile_pending(intent.id)
        latest_attempt_id = db.scalar(
            select(ResearchStepAttempt.id)
            .where(ResearchStepAttempt.step_id == step.id)
            .order_by(ResearchStepAttempt.attempt_number.desc())
            .limit(1)
        )
        if (
            run.status != "running"
            or step.step_kind != "artifact_publisher"
            or step.execution_snapshot_id != intent.execution_snapshot_id
            or step.current_attempt_number != attempt.attempt_number
            or latest_attempt_id != attempt.id
            or attempt.status != "running"
            or intent.run_id != run.id
            or intent.step_id != step.id
            or intent.attempt_id != attempt.id
            or intent.workspace_id != run.workspace_id
            or intent.current_object_generation != claim.generation
            or intent.current_object_key != claim.object_key
            or intent.status != "committing"
        ):
            _transition_compensating(
                db,
                intent=intent,
                db_now=db_now,
                reason_code="research_publication_scope_conflict",
            )
            db.commit()
            return PublicationResult.reconcile_pending(intent.id)
        snapshot = db.scalar(
            select(ResearchExecutionSnapshot)
            .where(ResearchExecutionSnapshot.id == intent.execution_snapshot_id)
            .execution_options(populate_existing=True)
        )
        if (
            snapshot is None
            or snapshot.run_id != run.id
            or snapshot.workspace_id != run.workspace_id
            or run.approved_execution_snapshot_id != snapshot.id
        ):
            _transition_compensating(
                db,
                intent=intent,
                db_now=db_now,
                reason_code="research_publication_provenance_conflict",
            )
            db.commit()
            return PublicationResult.reconcile_pending(intent.id)

        prompt_rows = list(
            db.scalars(
                select(ResearchExecutionPromptVersion)
                .where(
                    ResearchExecutionPromptVersion.execution_snapshot_id == snapshot.id
                )
                .execution_options(populate_existing=True)
            ).all()
        )
        prompt_by_node = {row.node_key: row.prompt_version_id for row in prompt_rows}
        synthesizer_prompt_id = prompt_by_node.get("synthesizer")
        try:
            release_prompt_dtos = prompt_loader(db, snapshot)
        except ValueError:
            # The production release oracle uses ValueError only for an explicit,
            # deterministic workflow/prompt contract mismatch.  Database and other
            # operational failures must escape this block so the caller retains the
            # nonterminal intent for retry instead of deleting its uploaded object.
            _transition_compensating(
                db,
                intent=intent,
                db_now=db_now,
                reason_code="research_publication_provenance_conflict",
            )
            db.commit()
            return PublicationResult.reconcile_pending(intent.id)
        try:
            release_prompt_bindings = [
                (str(item["nodeKey"]), str(item["promptVersionId"]))
                for item in release_prompt_dtos
            ]
        except (KeyError, TypeError):
            release_prompt_bindings = []
        frozen_prompt_bindings = [
            (row.node_key, row.prompt_version_id)
            for row in sorted(prompt_rows, key=lambda row: row.node_key)
        ]
        release_prompt_bindings_valid = (
            len(release_prompt_bindings) == len(frozen_prompt_bindings)
            and sorted(release_prompt_bindings) == frozen_prompt_bindings
        )
        snapshot_provenance_valid = execution_snapshot_provenance_is_valid(
            db,
            run=run,
            snapshot=snapshot,
            prompt_rows=prompt_rows,
        )

        selected_ids = [*fact_ids, *unresolved_ids]
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
        by_id = {row.id: row for row in claims}
        claims_valid = set(by_id) == set(selected_ids) and all(
            row.statement_sha256
            == hashlib.sha256(row.statement_text.encode("utf-8")).hexdigest()
            for row in claims
        )
        claims_valid = claims_valid and all(
            by_id[item].verification_status == "supported"
            and by_id[item].conflict_status == "none"
            for item in fact_ids
        )
        claims_valid = claims_valid and all(
            by_id[item].verification_status == "supported"
            and by_id[item].conflict_status == "resolved_unresolved"
            for item in unresolved_ids
        )
        frozen_report_matches_claims = bool(
            claims_valid
            and canonical_final_report(
                fact_claims=[by_id[item] for item in fact_ids],
                unresolved_claims=[by_id[item] for item in unresolved_ids],
            )
            == bytes(intent.payload_bytes)
        )
        synthesizer = db.scalar(
            select(ResearchStep)
            .where(
                ResearchStep.run_id == run.id,
                ResearchStep.workspace_id == run.workspace_id,
                ResearchStep.step_kind == "synthesizer",
            )
            .execution_options(populate_existing=True)
        )
        if (
            not release_prompt_bindings_valid
            or not snapshot_provenance_valid
            or not claims_valid
            or not frozen_report_matches_claims
            or not _claim_provenance_is_valid(
                db,
                claims=claims,
                fact_ids=fact_ids,
                unresolved_ids=unresolved_ids,
                run_id=run.id,
                workspace_id=run.workspace_id,
                snapshot=snapshot,
                prompt_rows=prompt_rows,
            )
            or not _synthesis_checkpoint_is_valid(
                db,
                run=run,
                snapshot=snapshot,
                synthesizer=synthesizer,
                expected_prompt_id=synthesizer_prompt_id,
                fact_ids=fact_ids,
                unresolved_ids=unresolved_ids,
            )
            or step.prompt_version_id != synthesizer_prompt_id
        ):
            _transition_compensating(
                db,
                intent=intent,
                db_now=db_now,
                reason_code="research_publication_provenance_conflict",
            )
            db.commit()
            return PublicationResult.reconcile_pending(intent.id)

        existing = db.scalar(
            _artifact_conflict_query(intent, object_key=claim.object_key)
        )
        terminal_event_count = (
            db.scalar(
                select(func.count())
                .select_from(ResearchEvent)
                .where(
                    ResearchEvent.run_id == run.id,
                    ResearchEvent.dedupe_key.in_(
                        (
                            f"step-succeeded:{attempt.id}",
                            f"artifact-published:{intent.artifact_id}",
                            f"run-completed:{intent.artifact_id}",
                        )
                    ),
                )
            )
            or 0
        )
        if (
            existing is not None
            or terminal_event_count
            or _terminal_event_semantic_conflict(
                db,
                run_id=run.id,
                step_id=step.id,
                attempt_id=attempt.id,
                artifact_id=intent.artifact_id,
            )
        ):
            _transition_compensating(
                db,
                intent=intent,
                db_now=db_now,
                reason_code="research_publication_integrity_mismatch",
            )
            db.commit()
            return PublicationResult.reconcile_pending(intent.id)
        artifact = ResearchArtifact(
            id=intent.artifact_id,
            workspace_id=run.workspace_id,
            run_id=run.id,
            generated_by_step_id=step.id,
            generated_by_attempt_id=attempt.id,
            artifact_kind="final_report",
            visibility="user",
            logical_key="final-report",
            schema_version="1",
            object_key=claim.object_key,
            content_type=intent.content_type,
            byte_size=intent.byte_size,
            content_sha256=intent.content_sha256,
            workflow_version_id=snapshot.workflow_version_id,
            direct_prompt_version_id=synthesizer_prompt_id,
            generation_provider=snapshot.generation_provider,
            generation_model=snapshot.generation_model,
            retention_class="workspace_lifetime",
            created_at=db_now,
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
        attempt.output_sha256 = intent.content_sha256
        attempt.finished_at = db_now
        attempt.lease_expires_at = None
        step.status = "succeeded"
        step.state_version += 1
        step.finished_at = db_now
        step.updated_at = db_now
        run.state_version += 1
        append_event(
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
            now=db_now,
        )
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
            now=db_now,
        )
        run.status = "completed"
        run.finished_at = db_now
        run.updated_at = db_now
        run.state_version += 1
        append_event(
            db,
            run,
            event_type="run_completed",
            dedupe_key=f"run-completed:{artifact.id}",
            data={
                "status": "completed",
                "finalArtifactId": artifact.id,
                "runStateVersion": run.state_version,
            },
            now=db_now,
        )
        intent.status = "committed"
        intent.committed_artifact_id = artifact.id
        intent.adopted_object_generation = claim.generation
        intent.adopted_object_key = claim.object_key
        intent.current_object_generation = None
        intent.current_object_key = None
        intent.state_version += 1
        intent.last_error_code = None
        intent.resolved_at = db_now
        intent.orphan_sweep_after = db_now
        intent.updated_at = db_now
        _clear_claim(intent)
        db.flush()
    except ResearchError as error:
        _safe_rollback(db)
        if error.code in {"research_publication_fenced"}:
            return PublicationResult.reconcile_pending(claim.intent_id)
        _transition_claim_compensating(db, claim, reason_code=error.code)
        return PublicationResult.reconcile_pending(claim.intent_id)
    except Exception:
        _safe_rollback(db)
        raise

    pending = _commit_phase(
        db,
        intent_id=claim.intent_id,
        session_factory=session_factory,
    )
    return pending or PublicationResult.committed(intent.artifact_id)


def _mark_compensation_sweep_pending(
    db: Session,
    claim: PublicationClaim,
    *,
    observation_seconds: int,
) -> None:
    intent, db_now = _lock_fenced_intent(db, claim, expected_statuses=("compensating",))
    _verify_compensation_claim_scope(intent, claim)
    intent.last_error_code = _COMPENSATION_SWEEP_PENDING
    intent.next_reconcile_at = db_now + timedelta(seconds=observation_seconds)
    intent.state_version += 1
    intent.updated_at = db_now
    _clear_claim(intent)
    db.commit()


def _finalize_absent(db: Session, claim: PublicationClaim) -> bool:
    try:
        run, step, attempt, intent, db_now = _lock_publication_chain(db, claim)
        if intent.status != "compensating":
            _safe_rollback(db)
            return False
        _verify_compensation_claim_scope(intent, claim)
        existing = db.scalar(
            _artifact_conflict_query(intent, object_key=claim.object_key)
        )
        terminal_events = (
            db.scalar(
                select(func.count())
                .select_from(ResearchEvent)
                .where(
                    ResearchEvent.run_id == run.id,
                    ResearchEvent.dedupe_key.in_(
                        (
                            f"step-succeeded:{attempt.id}",
                            f"artifact-published:{intent.artifact_id}",
                            f"run-completed:{intent.artifact_id}",
                        )
                    ),
                )
            )
            or 0
        )
        if existing is not None or terminal_events:
            _defer_compensating(
                db,
                intent,
                db_now=db_now,
                error_code="research_publication_artifact_ownership_conflict"
                if existing is not None
                else "research_publication_integrity_mismatch",
            )
            db.commit()
            return False
        latest_attempt_id = db.scalar(
            select(ResearchStepAttempt.id)
            .where(ResearchStepAttempt.step_id == step.id)
            .order_by(ResearchStepAttempt.attempt_number.desc())
            .limit(1)
        )
        snapshot = db.scalar(
            select(ResearchExecutionSnapshot)
            .where(ResearchExecutionSnapshot.id == intent.execution_snapshot_id)
            .execution_options(populate_existing=True)
        )
        locator_valid = (
            intent.run_id == run.id
            and intent.step_id == step.id
            and intent.attempt_id == attempt.id
            and intent.workspace_id == run.workspace_id
            and claim.run_id == intent.run_id
            and claim.attempt_id == intent.attempt_id
            and claim.workspace_id == intent.workspace_id
            and claim.artifact_id == intent.artifact_id
            and claim.object_prefix == intent.object_prefix
            and step.run_id == run.id
            and step.workspace_id == run.workspace_id
            and attempt.step_id == step.id
            and attempt.workspace_id == run.workspace_id
            and latest_attempt_id == attempt.id
            and snapshot is not None
            and snapshot.run_id == run.id
            and snapshot.workspace_id == run.workspace_id
            and run.approved_execution_snapshot_id == snapshot.id
        )
        active_chain_valid = (
            locator_valid
            and step.step_kind == "artifact_publisher"
            and step.current_attempt_number == attempt.attempt_number
            and step.execution_snapshot_id == intent.execution_snapshot_id
            and step.status == "running"
            and attempt.status == "running"
        )
        cancelling_chain_valid = (
            run.status == "cancel_requested"
            and locator_valid
            and step.step_kind == "artifact_publisher"
            and step.current_attempt_number == attempt.attempt_number
            and step.execution_snapshot_id == intent.execution_snapshot_id
            and step.status in {"running", "cancelled"}
            and attempt.status in {"running", "cancelled"}
        )
        if run.status not in {"running", "cancel_requested"} or not (
            active_chain_valid or cancelling_chain_valid
        ):
            intent.last_error_code = "research_publication_terminal_run_conflict"
            intent.next_reconcile_at = db_now + timedelta(
                seconds=PUBLICATION_RETRY_SECONDS
            )
            intent.state_version += 1
            intent.updated_at = db_now
            _clear_claim(intent)
            db.commit()
            return False

        # Cancellation is an explicit Run authority and may terminate the
        # active publication Attempt.  Every other reconciler must wait for
        # the ordinary Attempt lease to expire; an origin publisher may only
        # compensate while it still proves the matching live lease.
        attempt_expiry = (
            _as_utc(attempt.lease_expires_at)
            if attempt.lease_expires_at is not None
            else None
        )
        if run.status != "cancel_requested":
            if claim.requires_attempt_lease:
                origin_authorized = (
                    claim.attempt_lease_token_hash is not None
                    and attempt.lease_token_hash == claim.attempt_lease_token_hash
                    and attempt_expiry is not None
                    and attempt_expiry > db_now
                )
                if not origin_authorized:
                    _defer_compensating(
                        db,
                        intent,
                        db_now=db_now,
                        error_code="research_publication_attempt_lease_expired",
                        next_reconcile_at=db_now,
                    )
                    db.commit()
                    return False
            elif attempt_expiry is None:
                _defer_compensating(
                    db,
                    intent,
                    db_now=db_now,
                    error_code="research_publication_attempt_lease_invalid",
                )
                db.commit()
                return False
            elif attempt_expiry > db_now:
                _defer_compensating(
                    db,
                    intent,
                    db_now=db_now,
                    error_code="research_publication_attempt_lease_active",
                    next_reconcile_at=attempt_expiry,
                )
                db.commit()
                return False

        intent.status = "absent"
        intent.current_object_generation = None
        intent.current_object_key = None
        intent.resolved_at = db_now
        intent.orphan_sweep_after = db_now
        intent.state_version += 1
        intent.last_error_code = None
        intent.updated_at = db_now
        _clear_claim(intent)

        attempt.finished_at = db_now
        attempt.lease_expires_at = None
        attempt.error_code = "research_publication_compensated"
        attempt.error_message = "Research publication was safely compensated."
        if run.status == "cancel_requested":
            attempt.status = "cancelled"
            # SessionLocal uses autoflush=False.  Cancellation's active-Attempt
            # count must observe this transition inside the same transaction.
            db.flush()
            finalize_cancel_if_idle(db, run, now=db_now)
        else:
            attempt.status = "failed"
            step.status = "failed"
            step.state_version += 1
            step.error_code = "research_publication_compensated"
            step.error_message = "Research publication was safely compensated."
            step.finished_at = db_now
            step.updated_at = db_now
            run.state_version += 1
            run.updated_at = db_now
            append_research_event(
                db,
                run,
                event_type="step_failed",
                dedupe_key=f"step-failed:{attempt.id}",
                step_id=step.id,
                attempt_id=attempt.id,
                data={
                    "stepId": step.id,
                    "stepKind": step.step_kind,
                    "attemptId": attempt.id,
                    "attemptNumber": attempt.attempt_number,
                    "reasonCode": "research_publication_compensated",
                    "retryable": True,
                    "stepStateVersion": step.state_version,
                    "runStateVersion": run.state_version,
                },
                now=db_now,
            )
            if step.current_attempt_number < step.max_attempts_snapshot:
                step.status = "queued"
                step.state_version += 1
                step.error_code = None
                step.error_message = None
                step.queued_at = db_now
                step.finished_at = None
                run.failure_code = None
                run.failure_message = None
                run.state_version += 1
                append_research_event(
                    db,
                    run,
                    event_type="step_queued",
                    dedupe_key=f"step-queued:{step.id}:{step.current_attempt_number}",
                    step_id=step.id,
                    data={
                        "stepId": step.id,
                        "stepKind": step.step_kind,
                        "branchKey": step.branch_key,
                        "attemptNumber": step.current_attempt_number,
                        "stepStateVersion": step.state_version,
                        "runStateVersion": run.state_version,
                    },
                    now=db_now,
                )
            else:
                run.status = "awaiting_retry"
                run.failure_code = "research_publication_compensated"
                run.failure_message = "Research publication was safely compensated."
        db.flush()
        db.commit()
        return True
    except Exception:
        _safe_rollback(db)
        return False


def _compensate(
    db: Session,
    claim: PublicationClaim,
    *,
    list_keys: Callable[[str], Sequence[str]],
    cleanup_bytes: Callable[[str], None],
    session_factory: Callable[[], Session] | None,
    observation_seconds: int,
) -> None:
    try:
        if not _guard_compensation_storage_ownership(db, claim):
            return
        prefix = f"{claim.object_prefix}/"
        keys = list(
            _run_storage_operation(
                db,
                claim,
                session_factory=session_factory,
                operation=lambda: list_keys(prefix),
                require_current_object=False,
            )
        )
        if any(not key.startswith(f"{claim.object_prefix}/") for key in keys):
            raise ResearchError(
                "research_publication_integrity_mismatch",
                "Research publication prefix listing escaped its scope.",
                409,
            )
        for key in keys:
            if not _guard_compensation_storage_ownership(db, claim):
                return
            _run_storage_operation(
                db,
                claim,
                session_factory=session_factory,
                operation=lambda key=key: cleanup_bytes(key),
                require_current_object=False,
            )
        if not _guard_compensation_storage_ownership(db, claim):
            return
        remaining = list(
            _run_storage_operation(
                db,
                claim,
                session_factory=session_factory,
                operation=lambda: list_keys(prefix),
                require_current_object=False,
            )
        )
        if any(not key.startswith(prefix) for key in remaining):
            raise ResearchError(
                "research_publication_integrity_mismatch",
                "Research publication prefix listing escaped its scope.",
                409,
            )
        if remaining:
            raise RuntimeError("publication prefix is not empty")
        intent = db.get(ResearchPublicationIntent, claim.intent_id)
        second_sweep = (
            intent is not None and intent.last_error_code == _COMPENSATION_SWEEP_PENDING
        )
        _safe_rollback(db)
        if second_sweep:
            _finalize_absent(db, claim)
        else:
            _mark_compensation_sweep_pending(
                db,
                claim,
                observation_seconds=observation_seconds,
            )
    except _PublicationHeartbeatLost:
        _safe_rollback(db)
    except ResearchError as error:
        _safe_rollback(db)
        _release_for_retry(db, claim, error.code)
    except Exception as error:
        _safe_rollback(db)
        _release_for_retry(db, claim, type(error).__name__)
