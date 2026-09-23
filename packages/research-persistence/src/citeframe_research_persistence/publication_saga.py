"""Public facade for the durable multi-transaction final-report publication saga."""
# ruff: noqa: BLE001

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

from citeframe_contracts import PublicationResult
from citeframe_persistence.models import (
    ResearchArtifact,
    ResearchExecutionSnapshot,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
)
from sqlalchemy.orm import Session

from .events import append_research_event
from .lease import _locked_attempt
from .publication_prepare import _commit_phase, _prepare_publication
from .publication_reconcile import _process_claim, reconcile_one_publication_intent
from .publication_saga_support import (
    DEFAULT_PUBLICATION_OBSERVATION_SECONDS,
    _safe_rollback,
)


def publish_final_report(
    db: Session,
    *,
    attempt_id: str,
    lease_token: str,
    fact_claim_ids: Sequence[str],
    unresolved_claim_ids: Sequence[str],
    store_bytes: Callable[[str, bytes, str], None],
    load_bytes: Callable[[str], bytes],
    list_keys: Callable[[str], Sequence[str]],
    cleanup_bytes: Callable[[str], None],
    committed_session_factory: Callable[[], Session] | None,
    prompt_loader: Callable[
        [Session, ResearchExecutionSnapshot], list[dict[str, object]]
    ],
    observation_seconds: int = DEFAULT_PUBLICATION_OBSERVATION_SECONDS,
    now: datetime | None = None,
    locked_attempt: Callable[..., tuple[object, object, object]] = _locked_attempt,
    append_event: Callable[..., object] = append_research_event,
) -> PublicationResult:
    # Publication ownership uses database time exclusively. ``now`` remains accepted only
    # so older in-process adapters fail by behavior rather than by signature drift.
    del now
    if observation_seconds <= 0:
        raise ValueError("publication observation_seconds must be positive")
    claim, result = _prepare_publication(
        db,
        attempt_id=attempt_id,
        lease_token=lease_token,
        fact_claim_ids=fact_claim_ids,
        unresolved_claim_ids=unresolved_claim_ids,
        prompt_loader=prompt_loader,
        locked_attempt=locked_attempt,
    )
    if result is not None:
        _safe_rollback(db)
        return result
    assert claim is not None
    pending = _commit_phase(
        db,
        intent_id=claim.intent_id,
        session_factory=committed_session_factory,
        expected_prepare_claim=claim,
    )
    if pending is not None:
        return pending
    return _process_claim(
        db,
        claim,
        store_bytes=store_bytes,
        load_bytes=load_bytes,
        list_keys=list_keys,
        cleanup_bytes=cleanup_bytes,
        session_factory=committed_session_factory,
        append_event=append_event,
        observation_seconds=observation_seconds,
        prompt_loader=prompt_loader,
    )


def final_commit_state(
    session_factory: Callable[[], Session] | None,
    *,
    artifact_id: str,
    run_id: str,
    step_id: str,
    attempt_id: str,
    artifact_sha256: str,
    object_key: str,
) -> str:
    """Compatibility oracle retained for API tests and old internal callers."""

    if session_factory is None:
        return "unknown"
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
                and artifact.content_sha256 == artifact_sha256
                and artifact.object_key == object_key
                and run is not None
                and run.status == "completed"
                and step is not None
                and step.status == "succeeded"
                and attempt is not None
                and attempt.status == "succeeded"
            ):
                return "committed"
            return "unknown"
    except Exception:
        return "unknown"


__all__ = [
    "final_commit_state",
    "publish_final_report",
    "reconcile_one_publication_intent",
]
