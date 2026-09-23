"""Publication intent fencing, validation, claims, and DB-time heartbeats."""

# ruff: noqa: BLE001
from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TypeVar, cast

from citeframe_persistence.models import (
    ResearchPublicationIntent,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
)
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .errors import ResearchError, canonical_json
from .locks import lock_attempt, lock_run, lock_step

MAX_PUBLICATION_BYTES = 16 * 1024 * 1024
PUBLICATION_CLAIM_SECONDS = 60
PUBLICATION_RETRY_SECONDS = 5
DEFAULT_PUBLICATION_OBSERVATION_SECONDS = 30
PUBLICATION_HEARTBEAT_DB_TIMEOUT_SECONDS = 3
PUBLICATION_HEARTBEAT_JOIN_SECONDS = PUBLICATION_HEARTBEAT_DB_TIMEOUT_SECONDS + 1
PUBLICATION_IDLE_SWEEP_SECONDS = 24 * 60 * 60
_NONTERMINAL = (
    "prepared",
    "uploaded",
    "committing",
    "compensating",
)
_TERMINAL = ("committed", "absent")
_COMPENSATION_SWEEP_PENDING = "publication_compensation_sweep_pending"
_TERMINAL_SWEEP_PENDING = "publication_terminal_sweep_pending"
_T = TypeVar("_T")


@dataclass(frozen=True)
class PublicationClaim:
    intent_id: str
    workspace_id: str
    run_id: str
    step_id: str
    attempt_id: str
    execution_snapshot_id: str
    logical_key: str
    artifact_id: str
    generation: int
    token: str
    token_hash: str
    claim_owner: str | None
    claim_expires_at: datetime | None
    claim_heartbeat_at: datetime | None
    current_object_generation: int | None
    object_key: str | None
    object_prefix: str
    payload_bytes: bytes
    byte_size: int
    render_schema_version: str
    fact_claim_ids: tuple[str, ...]
    unresolved_claim_ids: tuple[str, ...]
    selection_sha256: str
    content_type: str
    content_sha256: str
    status: str
    requires_attempt_lease: bool = False
    attempt_lease_token_hash: str | None = None


class _PublicationHeartbeatLost(RuntimeError):
    """The storage side effect finished after durable ownership became uncertain."""


def _as_utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _database_now(db: Session) -> datetime:
    dialect = db.get_bind().dialect.name
    clock = (
        func.clock_timestamp() if dialect == "postgresql" else func.current_timestamp()
    )
    value = db.scalar(select(clock))
    if value is None:
        raise RuntimeError("database timestamp is unavailable")
    return _as_utc(value)


def _safe_rollback(db: Session) -> None:
    try:
        db.rollback()
    except Exception as rollback_error:
        # Outcome verification always uses a fresh session after the caller is poisoned.
        del rollback_error


def _claim_key(intent: ResearchPublicationIntent, generation: int) -> str:
    return f"{intent.object_prefix}/publication/{generation}/final.md"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _clear_claim(intent: ResearchPublicationIntent) -> None:
    intent.claim_owner = None
    intent.claim_token_hash = None
    intent.claim_expires_at = None
    intent.claim_heartbeat_at = None


def _claim_from_intent(
    intent: ResearchPublicationIntent,
    token: str,
    *,
    requires_attempt_lease: bool = False,
    attempt_lease_token_hash: str | None = None,
) -> PublicationClaim:
    selection = intent.selection_json
    fact_claim_ids = (
        selection.get("factClaimIds") if isinstance(selection, dict) else None
    )
    unresolved_claim_ids = (
        selection.get("unresolvedClaimIds") if isinstance(selection, dict) else None
    )
    return PublicationClaim(
        intent_id=intent.id,
        workspace_id=intent.workspace_id,
        run_id=intent.run_id,
        step_id=intent.step_id,
        attempt_id=intent.attempt_id,
        execution_snapshot_id=intent.execution_snapshot_id,
        logical_key=intent.logical_key,
        artifact_id=intent.artifact_id,
        generation=intent.claim_generation,
        token=token,
        token_hash=_token_hash(token),
        claim_owner=intent.claim_owner,
        claim_expires_at=(
            _as_utc(intent.claim_expires_at) if intent.claim_expires_at else None
        ),
        claim_heartbeat_at=(
            _as_utc(intent.claim_heartbeat_at) if intent.claim_heartbeat_at else None
        ),
        current_object_generation=intent.current_object_generation,
        object_key=intent.current_object_key,
        object_prefix=intent.object_prefix,
        payload_bytes=bytes(intent.payload_bytes),
        byte_size=intent.byte_size,
        render_schema_version=intent.render_schema_version,
        fact_claim_ids=(
            tuple(fact_claim_ids)
            if isinstance(fact_claim_ids, list)
            and all(isinstance(value, str) for value in fact_claim_ids)
            else ()
        ),
        unresolved_claim_ids=(
            tuple(unresolved_claim_ids)
            if isinstance(unresolved_claim_ids, list)
            and all(isinstance(value, str) for value in unresolved_claim_ids)
            else ()
        ),
        selection_sha256=intent.selection_sha256,
        content_type=intent.content_type,
        content_sha256=intent.content_sha256,
        status=intent.status,
        requires_attempt_lease=requires_attempt_lease,
        attempt_lease_token_hash=attempt_lease_token_hash,
    )


def _lock_fenced_intent(
    db: Session,
    claim: PublicationClaim,
    *,
    expected_statuses: Sequence[str] = _NONTERMINAL,
) -> tuple[ResearchPublicationIntent, datetime]:
    intent = db.scalar(
        select(ResearchPublicationIntent)
        .where(ResearchPublicationIntent.id == claim.intent_id)
        .with_for_update(of=ResearchPublicationIntent)
        .execution_options(populate_existing=True)
    )
    # PostgreSQL clock_timestamp() is evaluated after any row-lock wait, so an
    # ownership lease cannot remain valid merely because this transaction began earlier.
    db_now = _database_now(db)
    expiry = (
        _as_utc(intent.claim_expires_at) if intent and intent.claim_expires_at else None
    )
    if (
        intent is None
        or intent.status not in expected_statuses
        or intent.claim_generation != claim.generation
        or intent.claim_token_hash != claim.token_hash
        or expiry is None
        or expiry <= db_now
    ):
        raise ResearchError(
            "research_publication_fenced",
            "Research publication ownership was fenced.",
            409,
        )
    return intent, db_now


def _verify_storage_scope(intent: ResearchPublicationIntent) -> None:
    expected_prefix = (
        f"research/{intent.workspace_id}/{intent.run_id}/{intent.artifact_id}"
    )
    if intent.object_prefix != expected_prefix:
        raise ResearchError(
            "research_publication_integrity_mismatch",
            "Research publication object prefix is invalid.",
            409,
        )
    if intent.current_object_generation is not None and (
        intent.current_object_generation <= 0
        or intent.current_object_key
        != _claim_key(intent, intent.current_object_generation)
    ):
        raise ResearchError(
            "research_publication_integrity_mismatch",
            "Research publication object generation is invalid.",
            409,
        )
    if intent.adopted_object_generation is not None and (
        intent.adopted_object_generation <= 0
        or intent.adopted_object_key
        != _claim_key(intent, intent.adopted_object_generation)
    ):
        raise ResearchError(
            "research_publication_integrity_mismatch",
            "Research publication adopted object generation is invalid.",
            409,
        )


def _verify_frozen_intent(intent: ResearchPublicationIntent) -> None:
    _verify_storage_scope(intent)
    selection = intent.selection_json
    if not isinstance(selection, dict) or set(selection) != {
        "factClaimIds",
        "unresolvedClaimIds",
    }:
        raise ResearchError(
            "research_publication_integrity_mismatch",
            "Research publication selection integrity is invalid.",
            409,
        )
    try:
        selection_bytes = canonical_json(selection)
    except (TypeError, ValueError) as error:
        raise ResearchError(
            "research_publication_integrity_mismatch",
            "Research publication selection integrity is invalid.",
            409,
        ) from error
    if (
        intent.render_schema_version != "final-report-v1"
        or intent.content_type != "text/markdown"
        or not 0 <= intent.byte_size <= MAX_PUBLICATION_BYTES
        or intent.byte_size != len(intent.payload_bytes)
        or hashlib.sha256(intent.payload_bytes).hexdigest() != intent.content_sha256
        or hashlib.sha256(selection_bytes).hexdigest() != intent.selection_sha256
    ):
        raise ResearchError(
            "research_publication_integrity_mismatch",
            "Research publication frozen payload integrity is invalid.",
            409,
        )
    fact_ids = selection.get("factClaimIds")
    unresolved_ids = selection.get("unresolvedClaimIds")
    if (
        not isinstance(fact_ids, list)
        or not isinstance(unresolved_ids, list)
        or any(not isinstance(value, str) for value in [*fact_ids, *unresolved_ids])
        or len(fact_ids) != len(set(fact_ids))
        or len(unresolved_ids) != len(set(unresolved_ids))
        or set(fact_ids).intersection(unresolved_ids)
    ):
        raise ResearchError(
            "research_publication_integrity_mismatch",
            "Research publication selection integrity is invalid.",
            409,
        )


def _verify_claim_matches_intent(
    intent: ResearchPublicationIntent,
    claim: PublicationClaim,
    *,
    require_current_object: bool = True,
) -> None:
    """Bind every external side effect to the exact frozen in-memory claim."""

    expected_selection = {
        "factClaimIds": list(claim.fact_claim_ids),
        "unresolvedClaimIds": list(claim.unresolved_claim_ids),
    }
    mismatch = (
        intent.id != claim.intent_id
        or intent.workspace_id != claim.workspace_id
        or intent.run_id != claim.run_id
        or intent.step_id != claim.step_id
        or intent.attempt_id != claim.attempt_id
        or intent.execution_snapshot_id != claim.execution_snapshot_id
        or intent.logical_key != claim.logical_key
        or intent.artifact_id != claim.artifact_id
        or intent.object_prefix != claim.object_prefix
        or bytes(intent.payload_bytes) != claim.payload_bytes
        or intent.byte_size != claim.byte_size
        or intent.render_schema_version != claim.render_schema_version
        or intent.content_type != claim.content_type
        or intent.content_sha256 != claim.content_sha256
        or intent.selection_json != expected_selection
        or intent.selection_sha256 != claim.selection_sha256
        or intent.claim_generation != claim.generation
        or intent.claim_owner != claim.claim_owner
        or intent.claim_token_hash != claim.token_hash
    )
    if require_current_object:
        mismatch = mismatch or (
            intent.current_object_generation != claim.current_object_generation
            or claim.current_object_generation != claim.generation
            or intent.current_object_key != claim.object_key
            or claim.object_key is None
        )
    if mismatch:
        raise ResearchError(
            "research_publication_integrity_mismatch",
            "Research publication claim no longer matches its frozen intent.",
            409,
        )


def _verify_compensation_claim_scope(
    intent: ResearchPublicationIntent,
    claim: PublicationClaim,
) -> None:
    """Bind destructive compensation to stable ownership, not frozen content.

    A permanent payload/selection integrity failure is itself a valid reason to
    compensate.  Requiring that already-known-bad frozen content to verify again
    would make the durable responsibility impossible to resolve.  Deletion is
    instead fenced by the exact intent/chain locator, token generation, and the
    deterministic workspace/run/artifact prefix.  Any drift in those ownership
    fields remains fail-closed.
    """

    _verify_storage_scope(intent)
    if (
        intent.status != "compensating"
        or intent.id != claim.intent_id
        or intent.workspace_id != claim.workspace_id
        or intent.run_id != claim.run_id
        or intent.step_id != claim.step_id
        or intent.attempt_id != claim.attempt_id
        or intent.execution_snapshot_id != claim.execution_snapshot_id
        or intent.logical_key != claim.logical_key
        or intent.artifact_id != claim.artifact_id
        or intent.object_prefix != claim.object_prefix
        or intent.claim_generation != claim.generation
        or intent.claim_owner != claim.claim_owner
        or intent.claim_token_hash != claim.token_hash
        or intent.current_object_generation is not None
        or intent.current_object_key is not None
    ):
        raise ResearchError(
            "research_publication_integrity_mismatch",
            "Research publication compensation ownership is invalid.",
            409,
        )


def _heartbeat(
    db: Session,
    claim: PublicationClaim,
    *,
    cancel_event: threading.Event | None = None,
) -> bool:
    try:
        if db.get_bind().dialect.name == "postgresql":
            db.execute(
                text(
                    "SET LOCAL lock_timeout = "
                    f"'{PUBLICATION_HEARTBEAT_DB_TIMEOUT_SECONDS}s'"
                )
            )
            db.execute(
                text(
                    "SET LOCAL statement_timeout = "
                    f"'{PUBLICATION_HEARTBEAT_DB_TIMEOUT_SECONDS}s'"
                )
            )
        intent, db_now = _lock_fenced_intent(db, claim)
        try:
            if intent.status == "compensating":
                _verify_compensation_claim_scope(intent, claim)
            else:
                _verify_frozen_intent(intent)
                _verify_claim_matches_intent(intent, claim)
        except ResearchError as error:
            was_compensating = intent.status == "compensating"
            _transition_compensating(
                db,
                intent=intent,
                db_now=db_now,
                reason_code=error.code,
            )
            _clear_claim(intent)
            if was_compensating:
                intent.next_reconcile_at = db_now + timedelta(
                    seconds=PUBLICATION_IDLE_SWEEP_SECONDS
                )
            db.commit()
            return False
        if cancel_event is not None and cancel_event.is_set():
            _safe_rollback(db)
            return False
        intent.claim_heartbeat_at = db_now
        intent.claim_expires_at = db_now + timedelta(seconds=PUBLICATION_CLAIM_SECONDS)
        intent.updated_at = db_now
        db.commit()
        return True
    except Exception:
        _safe_rollback(db)
        return False


def _run_storage_operation(
    db: Session,
    claim: PublicationClaim,
    *,
    session_factory: Callable[[], Session] | None,
    operation: Callable[[], _T],
    require_current_object: bool = True,
) -> _T:
    """Run one bounded storage call while renewing the DB-time publication lease.

    The background session never shares ``db`` across threads.  If any attempted
    heartbeat fails, the caller must leave the intent untouched: a later generation
    owns verification and adoption of any external side effect that may have landed.
    """

    try:
        intent, _db_now = _lock_fenced_intent(db, claim)
        _verify_storage_scope(intent)
        if (
            intent.workspace_id != claim.workspace_id
            or intent.run_id != claim.run_id
            or intent.attempt_id != claim.attempt_id
            or intent.artifact_id != claim.artifact_id
            or intent.object_prefix != claim.object_prefix
        ) or (
            require_current_object
            and (
                claim.object_key is None
                or intent.current_object_generation != claim.generation
                or intent.current_object_key != claim.object_key
            )
        ):
            raise ResearchError(
                "research_publication_integrity_mismatch",
                "Research publication storage claim scope is invalid.",
                409,
            )
        if require_current_object:
            _verify_frozen_intent(intent)
            _verify_claim_matches_intent(intent, claim)
        _safe_rollback(db)
    except Exception:
        _safe_rollback(db)
        raise
    if not _heartbeat(
        db,
        claim,
    ):
        raise _PublicationHeartbeatLost
    stop = threading.Event()
    heartbeat_lost = threading.Event()

    def renew() -> None:
        assert session_factory is not None
        while not stop.wait(max(1, PUBLICATION_CLAIM_SECONDS // 6)):
            try:
                with session_factory() as heartbeat_db:
                    if not _heartbeat(
                        heartbeat_db,
                        claim,
                        cancel_event=stop,
                    ):
                        heartbeat_lost.set()
                        return
            except Exception:
                heartbeat_lost.set()
                return

    thread = None
    if session_factory is not None:
        thread = threading.Thread(
            target=renew,
            name=f"publication-heartbeat-{claim.intent_id[:8]}",
            daemon=True,
        )
        thread.start()
    result: _T | None = None
    operation_error: Exception | None = None
    try:
        result = operation()
    except Exception as error:
        operation_error = error
    finally:
        stop.set()
        if thread is not None:
            thread.join(timeout=PUBLICATION_HEARTBEAT_JOIN_SECONDS)
            if thread.is_alive():
                heartbeat_lost.set()
    if heartbeat_lost.is_set() or not _heartbeat(
        db,
        claim,
    ):
        raise _PublicationHeartbeatLost
    if operation_error is not None:
        raise operation_error
    return cast(_T, result)


def _release_for_retry(db: Session, claim: PublicationClaim, error_code: str) -> None:
    try:
        intent, db_now = _lock_fenced_intent(db, claim)
        try:
            if intent.status == "compensating":
                _verify_compensation_claim_scope(intent, claim)
            else:
                _verify_frozen_intent(intent)
                _verify_claim_matches_intent(intent, claim)
        except ResearchError as integrity_error:
            was_compensating = intent.status == "compensating"
            _transition_compensating(
                db,
                intent=intent,
                db_now=db_now,
                reason_code=integrity_error.code,
            )
            _clear_claim(intent)
            if was_compensating:
                intent.next_reconcile_at = db_now + timedelta(
                    seconds=PUBLICATION_IDLE_SWEEP_SECONDS
                )
            db.commit()
            return
        if intent.status != "compensating":
            intent.status = "prepared"
        intent.current_object_generation = None
        intent.current_object_key = None
        intent.state_version += 1
        intent.last_error_code = error_code[:128]
        intent.next_reconcile_at = db_now + timedelta(seconds=PUBLICATION_RETRY_SECONDS)
        intent.updated_at = db_now
        _clear_claim(intent)
        db.commit()
    except Exception:
        _safe_rollback(db)


def _record_object_mismatch(db: Session, claim: PublicationClaim) -> None:
    """Retry one corrupt read under a new generation, then compensate if it repeats."""

    code = "research_publication_object_hash_mismatch"
    try:
        intent, db_now = _lock_fenced_intent(db, claim)
        try:
            _verify_frozen_intent(intent)
            _verify_claim_matches_intent(intent, claim)
        except ResearchError as integrity_error:
            _transition_compensating(
                db,
                intent=intent,
                db_now=db_now,
                reason_code=integrity_error.code,
            )
            db.commit()
            return
        repeated = intent.last_error_code == code
        if repeated:
            _transition_compensating(
                db,
                intent=intent,
                db_now=db_now,
                reason_code="research_publication_storage_integrity_conflict",
            )
        else:
            intent.status = "prepared"
            intent.current_object_generation = None
            intent.current_object_key = None
            intent.state_version += 1
            intent.last_error_code = code
            intent.next_reconcile_at = db_now + timedelta(
                seconds=PUBLICATION_RETRY_SECONDS
            )
            intent.updated_at = db_now
            _clear_claim(intent)
        db.commit()
    except Exception:
        _safe_rollback(db)


def _mark_uploaded(
    db: Session,
    claim: PublicationClaim,
) -> bool:
    try:
        intent, db_now = _lock_fenced_intent(db, claim, expected_statuses=("prepared",))
        try:
            _verify_frozen_intent(intent)
            _verify_claim_matches_intent(intent, claim)
        except ResearchError as error:
            _transition_compensating(
                db,
                intent=intent,
                db_now=db_now,
                reason_code=error.code,
            )
            db.commit()
            return False
        if (
            intent.current_object_generation != claim.generation
            or intent.current_object_key != claim.object_key
            or claim.object_key is None
        ):
            raise ResearchError(
                "research_publication_fenced",
                "Research publication object was fenced.",
                409,
            )
        intent.status = "uploaded"
        intent.state_version += 1
        intent.last_error_code = None
        intent.next_reconcile_at = db_now
        intent.updated_at = db_now
        db.commit()
        return True
    except Exception:
        _safe_rollback(db)
        return False


def _mark_committing(
    db: Session,
    claim: PublicationClaim,
) -> bool:
    try:
        intent, db_now = _lock_fenced_intent(db, claim, expected_statuses=("uploaded",))
        try:
            _verify_frozen_intent(intent)
            _verify_claim_matches_intent(intent, claim)
        except ResearchError as error:
            _transition_compensating(
                db,
                intent=intent,
                db_now=db_now,
                reason_code=error.code,
            )
            db.commit()
            return False
        if (
            intent.current_object_generation != claim.generation
            or intent.current_object_key != claim.object_key
        ):
            raise ResearchError(
                "research_publication_fenced",
                "Research publication object was fenced.",
                409,
            )
        intent.status = "committing"
        intent.state_version += 1
        intent.next_reconcile_at = db_now
        intent.updated_at = db_now
        db.commit()
        return True
    except Exception:
        _safe_rollback(db)
        return False


def _transition_compensating(
    db: Session,
    *,
    intent: ResearchPublicationIntent,
    db_now: datetime,
    reason_code: str,
) -> None:
    intent.status = "compensating"
    intent.current_object_generation = None
    intent.current_object_key = None
    intent.state_version += 1
    intent.last_error_code = reason_code[:128]
    intent.next_reconcile_at = db_now
    intent.updated_at = db_now


def _release_locked_for_reconcile(
    intent: ResearchPublicationIntent,
    *,
    db_now: datetime,
    error_code: str,
    next_reconcile_at: datetime | None = None,
) -> None:
    intent.status = "prepared"
    intent.current_object_generation = None
    intent.current_object_key = None
    intent.state_version += 1
    intent.last_error_code = error_code[:128]
    intent.next_reconcile_at = next_reconcile_at or db_now
    intent.updated_at = db_now
    _clear_claim(intent)


def _transition_claim_compensating(
    db: Session,
    claim: PublicationClaim,
    *,
    reason_code: str,
) -> None:
    try:
        intent, db_now = _lock_fenced_intent(db, claim)
        _transition_compensating(
            db,
            intent=intent,
            db_now=db_now,
            reason_code=reason_code,
        )
        db.commit()
    except Exception:
        _safe_rollback(db)


def _lock_publication_chain(
    db: Session,
    claim: PublicationClaim,
) -> tuple[
    ResearchRun, ResearchStep, ResearchStepAttempt, ResearchPublicationIntent, datetime
]:
    locator = db.execute(
        select(
            ResearchPublicationIntent.run_id,
            ResearchPublicationIntent.step_id,
            ResearchPublicationIntent.attempt_id,
            ResearchPublicationIntent.workspace_id,
        ).where(ResearchPublicationIntent.id == claim.intent_id)
    ).one_or_none()
    if locator is None:
        raise ResearchError(
            "research_publication_fenced",
            "Research publication intent is missing.",
            409,
        )
    if (
        locator.workspace_id != claim.workspace_id
        or locator.run_id != claim.run_id
        or locator.step_id != claim.step_id
        or locator.attempt_id != claim.attempt_id
    ):
        raise ResearchError(
            "research_publication_integrity_mismatch",
            "Research publication chain no longer matches its claim.",
            409,
        )
    run = lock_run(db, locator.run_id)
    step = lock_step(
        db, locator.step_id, run_id=locator.run_id, workspace_id=locator.workspace_id
    )
    attempt = (
        lock_attempt(
            db,
            locator.attempt_id,
            step_id=locator.step_id,
            workspace_id=locator.workspace_id,
        )
        if step is not None
        else None
    )
    intent, db_now = _lock_fenced_intent(db, claim)
    if run is None or step is None or attempt is None:
        raise ResearchError(
            "research_state_conflict", "Research publication chain is invalid.", 409
        )
    return run, step, attempt, intent, db_now


def _selection_ids(intent: ResearchPublicationIntent) -> tuple[list[str], list[str]]:
    _verify_frozen_intent(intent)
    return (
        list(intent.selection_json["factClaimIds"]),
        list(intent.selection_json["unresolvedClaimIds"]),
    )
