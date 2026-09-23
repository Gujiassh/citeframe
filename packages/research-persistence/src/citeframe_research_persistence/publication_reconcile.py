"""Publication reconcile claiming, storage orchestration, and terminal orphan sweeps."""

# ruff: noqa: BLE001
from __future__ import annotations

import hashlib
import logging
import secrets
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta

from citeframe_contracts import PublicationResult
from citeframe_persistence.models import (
    ResearchArtifact,
    ResearchExecutionSnapshot,
    ResearchPublicationIntent,
)
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from .errors import ResearchError
from .events import append_research_event
from .publication_finalize import _compensate, _finalize
from .publication_saga_support import (
    _NONTERMINAL,
    _TERMINAL,
    _TERMINAL_SWEEP_PENDING,
    DEFAULT_PUBLICATION_OBSERVATION_SECONDS,
    PUBLICATION_CLAIM_SECONDS,
    PUBLICATION_IDLE_SWEEP_SECONDS,
    PUBLICATION_RETRY_SECONDS,
    PublicationClaim,
    _as_utc,
    _claim_from_intent,
    _claim_key,
    _database_now,
    _mark_committing,
    _mark_uploaded,
    _PublicationHeartbeatLost,
    _record_object_mismatch,
    _release_for_retry,
    _run_storage_operation,
    _safe_rollback,
    _token_hash,
    _transition_claim_compensating,
)

logger = logging.getLogger(__name__)


def _process_claim(
    db: Session,
    claim: PublicationClaim,
    *,
    store_bytes: Callable[[str, bytes, str], None],
    load_bytes: Callable[[str], bytes],
    list_keys: Callable[[str], Sequence[str]],
    cleanup_bytes: Callable[[str], None],
    session_factory: Callable[[], Session] | None,
    append_event: Callable[..., object],
    observation_seconds: int,
    prompt_loader: Callable[
        [Session, ResearchExecutionSnapshot], list[dict[str, object]]
    ],
) -> PublicationResult:
    if claim.status == "compensating":
        _compensate(
            db,
            claim,
            list_keys=list_keys,
            cleanup_bytes=cleanup_bytes,
            session_factory=session_factory,
            observation_seconds=observation_seconds,
        )
        return PublicationResult.reconcile_pending(claim.intent_id)
    if claim.object_key is None:
        _release_for_retry(db, claim, "research_publication_object_key_missing")
        return PublicationResult.reconcile_pending(claim.intent_id)
    try:
        _run_storage_operation(
            db,
            claim,
            session_factory=session_factory,
            operation=lambda: store_bytes(
                claim.object_key, claim.payload_bytes, claim.content_type
            ),
        )
        stored = _run_storage_operation(
            db,
            claim,
            session_factory=session_factory,
            operation=lambda: load_bytes(claim.object_key),
        )
        if (
            len(stored) != len(claim.payload_bytes)
            or hashlib.sha256(stored).hexdigest() != claim.content_sha256
        ):
            _record_object_mismatch(db, claim)
            return PublicationResult.reconcile_pending(claim.intent_id)
        if not _mark_uploaded(db, claim):
            current = db.get(ResearchPublicationIntent, claim.intent_id)
            if current is not None and current.status == "compensating":
                _safe_rollback(db)
                _compensate(
                    db,
                    claim,
                    list_keys=list_keys,
                    cleanup_bytes=cleanup_bytes,
                    session_factory=session_factory,
                    observation_seconds=observation_seconds,
                )
            return PublicationResult.reconcile_pending(claim.intent_id)
        if not _mark_committing(db, claim):
            return PublicationResult.reconcile_pending(claim.intent_id)
        stored = _run_storage_operation(
            db,
            claim,
            session_factory=session_factory,
            operation=lambda: load_bytes(claim.object_key),
        )
        if (
            len(stored) != len(claim.payload_bytes)
            or hashlib.sha256(stored).hexdigest() != claim.content_sha256
        ):
            _record_object_mismatch(db, claim)
            return PublicationResult.reconcile_pending(claim.intent_id)
        result = _finalize(
            db,
            claim,
            append_event=append_event,
            session_factory=session_factory,
            prompt_loader=prompt_loader,
        )
        if result.kind == "reconcile_pending":
            current = db.get(ResearchPublicationIntent, claim.intent_id)
            if current is not None and current.status == "compensating":
                _safe_rollback(db)
                _compensate(
                    db,
                    claim,
                    list_keys=list_keys,
                    cleanup_bytes=cleanup_bytes,
                    session_factory=session_factory,
                    observation_seconds=observation_seconds,
                )
        return result
    except _PublicationHeartbeatLost:
        _safe_rollback(db)
        return PublicationResult.reconcile_pending(claim.intent_id)
    except ResearchError as error:
        _safe_rollback(db)
        if error.code == "research_publication_integrity_mismatch":
            _transition_claim_compensating(db, claim, reason_code=error.code)
            # This exception path returns without running compensation in the
            # current process.  Release the claim so another reconciler can
            # durably continue instead of waiting for the full lease timeout.
            _release_for_retry(db, claim, error.code)
        else:
            _release_for_retry(db, claim, error.code)
        return PublicationResult.reconcile_pending(claim.intent_id)
    except Exception as error:
        _safe_rollback(db)
        _release_for_retry(db, claim, type(error).__name__)
        return PublicationResult.reconcile_pending(claim.intent_id)


def _take_over_locked_intent(
    intent: ResearchPublicationIntent,
    *,
    worker_instance_id: str,
    db_now: datetime,
) -> PublicationClaim:
    if intent.status in {"uploaded", "committing"}:
        intent.status = "prepared"
    intent.claim_generation += 1
    token = secrets.token_urlsafe(32)
    intent.claim_owner = worker_instance_id[:128]
    intent.claim_token_hash = _token_hash(token)
    intent.claim_heartbeat_at = db_now
    intent.claim_expires_at = db_now + timedelta(seconds=PUBLICATION_CLAIM_SECONDS)
    intent.reconcile_attempt_count += 1
    intent.updated_at = db_now
    if intent.status == "compensating":
        intent.current_object_generation = None
        intent.current_object_key = None
    else:
        intent.current_object_generation = intent.claim_generation
        intent.current_object_key = _claim_key(intent, intent.claim_generation)
    intent.state_version += 1
    return _claim_from_intent(intent, token)


def _claim_expired_committing(
    db: Session,
    *,
    worker_instance_id: str,
) -> tuple[PublicationClaim | None, bool, bool]:
    """Wait behind an old final transaction, then recheck before takeover."""

    clock = (
        func.clock_timestamp()
        if db.get_bind().dialect.name == "postgresql"
        else func.current_timestamp()
    )
    intent_ids = tuple(
        db.scalars(
            select(ResearchPublicationIntent.id)
            .where(
                ResearchPublicationIntent.status == "committing",
                ResearchPublicationIntent.next_reconcile_at <= clock,
                ResearchPublicationIntent.claim_expires_at <= clock,
            )
            .order_by(
                ResearchPublicationIntent.next_reconcile_at,
                ResearchPublicationIntent.id,
            )
            .limit(8)
        ).all()
    )
    # The clock-bearing locator is only a prefilter.  End that transaction so
    # each actual claim transaction takes its sole authoritative DB timestamp
    # after any row-lock wait.
    _safe_rollback(db)
    if not intent_ids:
        return None, False, False
    for intent_id in intent_ids:
        try:
            if db.get_bind().dialect.name == "postgresql":
                db.execute(text("SET LOCAL lock_timeout = '1s'"))
            intent = db.scalar(
                select(ResearchPublicationIntent)
                .where(ResearchPublicationIntent.id == intent_id)
                .with_for_update(of=ResearchPublicationIntent)
                .execution_options(populate_existing=True)
            )
            db_now = _database_now(db)
            expiry = (
                _as_utc(intent.claim_expires_at)
                if intent and intent.claim_expires_at
                else None
            )
            next_reconcile = _as_utc(intent.next_reconcile_at) if intent else None
            if (
                intent is None
                or intent.status != "committing"
                or expiry is None
                or expiry > db_now
                or next_reconcile is None
                or next_reconcile > db_now
            ):
                _safe_rollback(db)
                return None, True, False
            claim = _take_over_locked_intent(
                intent,
                worker_instance_id=worker_instance_id,
                db_now=db_now,
            )
            db.flush()
            return claim, True, False
        except DBAPIError as error:
            _safe_rollback(db)
            sqlstate = getattr(error.orig, "sqlstate", None)
            if sqlstate != "55P03":
                raise
            logger.warning(
                "publication_claim_lock_timeout intent_id=%s sqlstate=55P03",
                intent_id,
            )
            # Do not skip the globally earliest due responsibility and then
            # process newer work; the terminal lane may already be overdue.
            return None, False, True
    return None, False, False


def _committing_work_is_earliest_nonterminal(db: Session) -> bool:
    clock = (
        func.clock_timestamp()
        if db.get_bind().dialect.name == "postgresql"
        else func.current_timestamp()
    )
    status = db.scalar(
        select(ResearchPublicationIntent.status)
        .where(
            ResearchPublicationIntent.status.in_(_NONTERMINAL),
            ResearchPublicationIntent.next_reconcile_at <= clock,
            or_(
                ResearchPublicationIntent.claim_owner.is_(None),
                ResearchPublicationIntent.claim_expires_at <= clock,
            ),
        )
        .order_by(
            ResearchPublicationIntent.next_reconcile_at,
            ResearchPublicationIntent.id,
        )
        .limit(1)
    )
    _safe_rollback(db)
    return status == "committing"


def _claim_next(
    db: Session,
    *,
    worker_instance_id: str,
    skip_committing: bool = False,
) -> tuple[PublicationClaim | None, bool, bool]:
    if not skip_committing and _committing_work_is_earliest_nonterminal(db):
        committing_claim, committing_handled, committing_blocked = (
            _claim_expired_committing(
                db,
                worker_instance_id=worker_instance_id,
            )
        )
        if committing_handled or committing_blocked:
            return committing_claim, committing_handled, committing_blocked
    clock = (
        func.clock_timestamp()
        if db.get_bind().dialect.name == "postgresql"
        else func.current_timestamp()
    )
    candidate_ids = tuple(
        db.scalars(
            select(ResearchPublicationIntent.id)
            .where(
                ResearchPublicationIntent.status.in_(
                    ("prepared", "uploaded", "compensating")
                ),
                ResearchPublicationIntent.next_reconcile_at <= clock,
                or_(
                    ResearchPublicationIntent.claim_owner.is_(None),
                    ResearchPublicationIntent.claim_expires_at <= clock,
                ),
            )
            .order_by(
                ResearchPublicationIntent.next_reconcile_at,
                ResearchPublicationIntent.id,
            )
            .limit(8)
        ).all()
    )
    _safe_rollback(db)
    if not candidate_ids:
        return None, False, False
    intent = None
    for candidate_id in candidate_ids:
        intent = db.scalar(
            select(ResearchPublicationIntent)
            .where(ResearchPublicationIntent.id == candidate_id)
            .with_for_update(of=ResearchPublicationIntent, skip_locked=True)
            .execution_options(populate_existing=True)
        )
        if intent is not None:
            break
        _safe_rollback(db)
        # Preserve the global durable ordering across lanes.  A later
        # nonterminal cannot jump an older locked row and starve terminal work.
        return None, False, True
    if intent is None:
        return None, False, False
    db_now = _database_now(db)
    expiry = _as_utc(intent.claim_expires_at) if intent.claim_expires_at else None
    if (
        intent.status not in {"prepared", "uploaded", "compensating"}
        or _as_utc(intent.next_reconcile_at) > db_now
        or (intent.claim_owner is not None and (expiry is None or expiry > db_now))
    ):
        _safe_rollback(db)
        return None, True, False
    claim = _take_over_locked_intent(
        intent,
        worker_instance_id=worker_instance_id,
        db_now=db_now,
    )
    db.flush()
    return claim, True, False


def _assert_terminal_storage_ownership(
    db: Session,
    *,
    locator,
    prefix: str,
    keep: str | None,
    lock_intent: bool = False,
) -> ResearchPublicationIntent:
    intent_query = select(ResearchPublicationIntent).where(
        ResearchPublicationIntent.id == locator.id
    )
    if lock_intent:
        intent_query = intent_query.with_for_update(of=ResearchPublicationIntent)
    intent = db.scalar(intent_query.execution_options(populate_existing=True))
    if (
        intent is None
        or intent.status != locator.status
        or intent.workspace_id != locator.workspace_id
        or intent.run_id != locator.run_id
        or intent.artifact_id != locator.artifact_id
        or intent.object_prefix != locator.object_prefix
        or intent.adopted_object_generation != locator.adopted_object_generation
        or intent.adopted_object_key != locator.adopted_object_key
        or intent.last_error_code != locator.last_error_code
        or intent.orphan_sweep_after != locator.orphan_sweep_after
    ):
        raise ResearchError(
            "research_publication_integrity_mismatch",
            "Research terminal publication changed during storage cleanup.",
            409,
        )
    ownership_conditions = [
        ResearchArtifact.id == locator.artifact_id,
        ResearchArtifact.object_key.like(f"{prefix}%"),
    ]
    if locator.status == "committed":
        ownership_conditions.append(
            and_(
                ResearchArtifact.run_id == locator.run_id,
                ResearchArtifact.logical_key == "final-report",
            )
        )
    scope_artifacts = list(
        db.scalars(
            select(ResearchArtifact)
            .where(or_(*ownership_conditions))
            .execution_options(populate_existing=True)
        ).all()
    )
    if locator.status == "committed":
        adopted_artifact = scope_artifacts[0] if len(scope_artifacts) == 1 else None
        if (
            adopted_artifact is None
            or adopted_artifact.id != locator.artifact_id
            or adopted_artifact.workspace_id != locator.workspace_id
            or adopted_artifact.run_id != locator.run_id
            or adopted_artifact.artifact_kind != "final_report"
            or adopted_artifact.logical_key != "final-report"
            or adopted_artifact.object_key != keep
        ):
            raise ResearchError(
                "research_publication_artifact_ownership_conflict",
                "Research terminal publication Artifact ownership is invalid.",
                409,
            )
    elif scope_artifacts:
        raise ResearchError(
            "research_publication_artifact_ownership_conflict",
            "Absent Research publication prefix is owned by an Artifact.",
            409,
        )
    return intent


def _sweep_terminal(
    db: Session,
    *,
    list_keys: Callable[[str], Sequence[str]],
    cleanup_bytes: Callable[[str], None],
    observation_seconds: int,
) -> bool:
    db_now = _database_now(db)
    locator = db.execute(
        select(
            ResearchPublicationIntent.id,
            ResearchPublicationIntent.status,
            ResearchPublicationIntent.workspace_id,
            ResearchPublicationIntent.run_id,
            ResearchPublicationIntent.artifact_id,
            ResearchPublicationIntent.object_prefix,
            ResearchPublicationIntent.adopted_object_generation,
            ResearchPublicationIntent.adopted_object_key,
            ResearchPublicationIntent.last_error_code,
            ResearchPublicationIntent.orphan_sweep_after,
        )
        .where(
            ResearchPublicationIntent.status.in_(_TERMINAL),
            or_(
                ResearchPublicationIntent.orphan_sweep_after.is_(None),
                ResearchPublicationIntent.orphan_sweep_after <= db_now,
            ),
        )
        .order_by(
            ResearchPublicationIntent.orphan_sweep_after.is_not(None),
            ResearchPublicationIntent.orphan_sweep_after,
            ResearchPublicationIntent.id,
        )
        .limit(1)
    ).one_or_none()
    _safe_rollback(db)
    if locator is None:
        return False
    try:
        expected_prefix = (
            f"research/{locator.workspace_id}/{locator.run_id}/{locator.artifact_id}"
        )
        expected_adopted_key = (
            f"{expected_prefix}/publication/{locator.adopted_object_generation}/final.md"
            if locator.adopted_object_generation is not None
            else None
        )
        if (
            locator.object_prefix != expected_prefix
            or locator.orphan_sweep_after is None
            or (
                locator.status == "committed"
                and (
                    locator.adopted_object_generation is None
                    or locator.adopted_object_generation <= 0
                    or locator.adopted_object_key != expected_adopted_key
                )
            )
            or (
                locator.status == "absent"
                and (
                    locator.adopted_object_generation is not None
                    or locator.adopted_object_key is not None
                )
            )
        ):
            raise ResearchError(
                "research_publication_integrity_mismatch",
                "Research terminal publication storage scope is invalid.",
                409,
            )
        prefix = f"{locator.object_prefix}/"
        keys = list(list_keys(prefix))
        if any(not key.startswith(prefix) for key in keys):
            raise RuntimeError("publication terminal sweep escaped its prefix")
        keep = locator.adopted_object_key if locator.status == "committed" else None
        _assert_terminal_storage_ownership(
            db,
            locator=locator,
            prefix=prefix,
            keep=keep,
        )
        _safe_rollback(db)
        deleted = False
        for key in keys:
            if key != keep:
                _assert_terminal_storage_ownership(
                    db,
                    locator=locator,
                    prefix=prefix,
                    keep=keep,
                )
                _safe_rollback(db)
                cleanup_bytes(key)
                deleted = True
        _assert_terminal_storage_ownership(
            db,
            locator=locator,
            prefix=prefix,
            keep=keep,
        )
        _safe_rollback(db)
        remaining = list(list_keys(prefix))
        if any(not key.startswith(prefix) for key in remaining):
            raise RuntimeError("publication terminal sweep escaped its prefix")
        if any(key != keep for key in remaining):
            raise RuntimeError("publication terminal sweep left orphan objects")
        if locator.status == "committed" and keep not in remaining:
            raise ResearchError(
                "research_publication_adopted_object_missing",
                "Research terminal publication adopted object is missing.",
                409,
            )
        _assert_terminal_storage_ownership(
            db,
            locator=locator,
            prefix=prefix,
            keep=keep,
        )
        _safe_rollback(db)
        intent = _assert_terminal_storage_ownership(
            db,
            locator=locator,
            prefix=prefix,
            keep=keep,
            lock_intent=True,
        )
        db_now = _database_now(db)
        first_observation = locator.last_error_code != _TERMINAL_SWEEP_PENDING
        if first_observation or deleted:
            intent.last_error_code = _TERMINAL_SWEEP_PENDING
            intent.orphan_sweep_after = db_now + timedelta(seconds=observation_seconds)
        else:
            intent.last_error_code = None
            intent.orphan_sweep_after = db_now + timedelta(
                seconds=PUBLICATION_IDLE_SWEEP_SECONDS
            )
        intent.updated_at = db_now
        db.commit()
    except Exception as error:
        _safe_rollback(db)
        try:
            intent = db.scalar(
                select(ResearchPublicationIntent)
                .where(ResearchPublicationIntent.id == locator.id)
                .with_for_update(of=ResearchPublicationIntent)
            )
            db_now = _database_now(db)
            if (
                intent is not None
                and intent.status == locator.status
                and intent.object_prefix == locator.object_prefix
                and intent.adopted_object_generation
                == locator.adopted_object_generation
                and intent.adopted_object_key == locator.adopted_object_key
                and intent.last_error_code == locator.last_error_code
                and intent.orphan_sweep_after == locator.orphan_sweep_after
            ):
                intent.last_error_code = (
                    error.code
                    if isinstance(error, ResearchError)
                    else type(error).__name__
                )[:128]
                intent.orphan_sweep_after = db_now + timedelta(
                    seconds=PUBLICATION_RETRY_SECONDS
                )
                intent.updated_at = db_now
                db.commit()
            else:
                _safe_rollback(db)
        except Exception:
            _safe_rollback(db)
    return True


def _terminal_work_is_earliest_due(db: Session) -> bool:
    """Choose one due lane by its durable schedule so neither lane can starve."""

    clock = (
        func.clock_timestamp()
        if db.get_bind().dialect.name == "postgresql"
        else func.current_timestamp()
    )
    terminal_due = db.scalar(
        select(ResearchPublicationIntent.orphan_sweep_after)
        .where(
            ResearchPublicationIntent.status.in_(_TERMINAL),
            or_(
                ResearchPublicationIntent.orphan_sweep_after.is_(None),
                ResearchPublicationIntent.orphan_sweep_after <= clock,
            ),
        )
        .order_by(
            ResearchPublicationIntent.orphan_sweep_after.is_not(None),
            ResearchPublicationIntent.orphan_sweep_after,
            ResearchPublicationIntent.id,
        )
        .limit(1)
    )
    terminal_exists = db.scalar(
        select(func.count())
        .select_from(ResearchPublicationIntent)
        .where(
            ResearchPublicationIntent.status.in_(_TERMINAL),
            or_(
                ResearchPublicationIntent.orphan_sweep_after.is_(None),
                ResearchPublicationIntent.orphan_sweep_after <= clock,
            ),
        )
    )
    if not terminal_exists:
        return False
    # A terminal row with a missing schedule is an integrity failure and gets
    # immediate priority so it cannot disappear from both scheduler lanes.
    if terminal_due is None:
        return True
    nonterminal_due = db.scalar(
        select(ResearchPublicationIntent.next_reconcile_at)
        .where(
            ResearchPublicationIntent.status.in_(_NONTERMINAL),
            ResearchPublicationIntent.next_reconcile_at <= clock,
            or_(
                ResearchPublicationIntent.claim_owner.is_(None),
                ResearchPublicationIntent.claim_expires_at <= clock,
            ),
        )
        .order_by(
            ResearchPublicationIntent.next_reconcile_at,
            ResearchPublicationIntent.id,
        )
        .limit(1)
    )
    return nonterminal_due is None or _as_utc(terminal_due) <= _as_utc(nonterminal_due)


def _terminal_work_is_due(db: Session) -> bool:
    clock = (
        func.clock_timestamp()
        if db.get_bind().dialect.name == "postgresql"
        else func.current_timestamp()
    )
    return bool(
        db.scalar(
            select(func.count())
            .select_from(ResearchPublicationIntent)
            .where(
                ResearchPublicationIntent.status.in_(_TERMINAL),
                or_(
                    ResearchPublicationIntent.orphan_sweep_after.is_(None),
                    ResearchPublicationIntent.orphan_sweep_after <= clock,
                ),
            )
        )
    )


def reconcile_one_publication_intent(
    db: Session,
    *,
    worker_instance_id: str,
    store_bytes: Callable[[str, bytes, str], None],
    load_bytes: Callable[[str], bytes],
    list_keys: Callable[[str], Sequence[str]],
    cleanup_bytes: Callable[[str], None],
    committed_session_factory: Callable[[], Session] | None,
    prompt_loader: Callable[
        [Session, ResearchExecutionSnapshot], list[dict[str, object]]
    ],
    observation_seconds: int = DEFAULT_PUBLICATION_OBSERVATION_SECONDS,
) -> bool:
    """Handle at most one durable publication responsibility."""

    if observation_seconds <= 0:
        raise ValueError("publication observation_seconds must be positive")
    if _terminal_work_is_earliest_due(db):
        _safe_rollback(db)
        return _sweep_terminal(
            db,
            list_keys=list_keys,
            cleanup_bytes=cleanup_bytes,
            observation_seconds=observation_seconds,
        )
    claim, handled, committing_blocked = _claim_next(
        db, worker_instance_id=worker_instance_id
    )
    if committing_blocked:
        _safe_rollback(db)
        if _terminal_work_is_due(db):
            _safe_rollback(db)
            return _sweep_terminal(
                db,
                list_keys=list_keys,
                cleanup_bytes=cleanup_bytes,
                observation_seconds=observation_seconds,
            )
        claim, handled, _blocked = _claim_next(
            db,
            worker_instance_id=worker_instance_id,
            skip_committing=True,
        )
    if claim is None:
        _safe_rollback(db)
        terminal_handled = _sweep_terminal(
            db,
            list_keys=list_keys,
            cleanup_bytes=cleanup_bytes,
            observation_seconds=observation_seconds,
        )
        return handled or terminal_handled
    try:
        db.commit()
    except Exception:
        _safe_rollback(db)
        return False
    _process_claim(
        db,
        claim,
        store_bytes=store_bytes,
        load_bytes=load_bytes,
        list_keys=list_keys,
        cleanup_bytes=cleanup_bytes,
        session_factory=committed_session_factory,
        append_event=append_research_event,
        observation_seconds=observation_seconds,
        prompt_loader=prompt_loader,
    )
    return True
