"""API composition facade for neutral Research provider persistence commands."""
from __future__ import annotations

from functools import wraps

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ai_pdf_api.models import ResearchPlanRevision, ResearchExecutionSnapshot, ResearchStep
from ai_pdf_api.services.research import ResearchError
from ai_pdf_api.services.research.research_worker_types import ProviderReservation
from citeframe_research_persistence.lease import (
    _active_attempt_chain,
    _ledger_and_limits,
    _locked_attempt_chain,
)
from citeframe_research_persistence.provider import (
    _provider_call_chain,
    cancel_provider_reservation as _cancel_provider_reservation,
    mark_provider_call_sent as _mark_provider_call_sent,
    reconcile_provider_call as _reconcile_provider_call,
    reserve_provider_call as _reserve_provider_call,
)


def _frozen_retrieval_top_k(db: Session, step: ResearchStep) -> int:
    if step.execution_snapshot_id is not None:
        snapshot = db.get(ResearchExecutionSnapshot, step.execution_snapshot_id)
        if snapshot is None:
            raise ResearchError(
                "research_state_conflict",
                "Research execution snapshot is missing for provider profile resolution.",
                409,
            )
        return snapshot.retrieval_top_k
    if step.plan_revision_id is not None:
        revision = db.get(ResearchPlanRevision, step.plan_revision_id)
        if revision is None:
            raise ResearchError(
                "research_state_conflict",
                "Research plan revision is missing for provider profile resolution.",
                409,
            )
        return revision.proposed_retrieval_top_k
    raise ResearchError(
        "research_state_conflict",
        "Research step is missing a frozen plan revision or execution snapshot.",
        409,
    )


def resolve_actual_research_provider_config_fingerprint(db: Session, step: ResearchStep) -> str:
    """Resolve the current capability fingerprint at the API composition boundary."""
    from ai_pdf_api.services.capabilities import current_execution_profile_fingerprint

    return current_execution_profile_fingerprint(
        retrieval_top_k=_frozen_retrieval_top_k(db, step),
    )


def frozen_provider_config_matches_actual(
    db: Session,
    step: ResearchStep,
    frozen_fingerprint: str,
) -> bool:
    from ai_pdf_api.services.capabilities import matches_frozen_execution_fingerprint

    return matches_frozen_execution_fingerprint(
        frozen_fingerprint,
        retrieval_top_k=_frozen_retrieval_top_k(db, step),
    )


def reserve_provider_call(
    db: Session,
    *,
    attempt_id: str,
    logical_call_key: str,
    request_sha256: str,
    provider: str,
    model: str,
    provider_config_fingerprint: str,
    reserved_input_tokens: int,
    reserved_output_tokens: int,
    now: datetime | None = None,
) -> ProviderReservation:
    # Keep the legacy matcher patch point while the neutral command owns all DB transitions.
    try:
        result = _reserve_provider_call(
            db,
            attempt_id=attempt_id,
            logical_call_key=logical_call_key,
            request_sha256=request_sha256,
            provider=provider,
            model=model,
            provider_config_fingerprint=provider_config_fingerprint,
            reserved_input_tokens=reserved_input_tokens,
            reserved_output_tokens=reserved_output_tokens,
            now=now,
            provider_config_matcher=frozen_provider_config_matches_actual,
        )
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def _commit_command(db: Session, command, /, *args, **kwargs):
    try:
        result = command(db, *args, **kwargs)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@wraps(_cancel_provider_reservation)
def cancel_provider_reservation(db: Session, *args, **kwargs):
    return _commit_command(db, _cancel_provider_reservation, *args, **kwargs)


@wraps(_mark_provider_call_sent)
def mark_provider_call_sent(db: Session, *args, **kwargs):
    return _commit_command(db, _mark_provider_call_sent, *args, **kwargs)


@wraps(_reconcile_provider_call)
def reconcile_provider_call(db: Session, *args, **kwargs):
    return _commit_command(db, _reconcile_provider_call, *args, **kwargs)


reserve_provider_call.__wrapped__ = _reserve_provider_call

__all__ = [
    "ProviderReservation",
    "cancel_provider_reservation",
    "frozen_provider_config_matches_actual",
    "mark_provider_call_sent",
    "reconcile_provider_call",
    "resolve_actual_research_provider_config_fingerprint",
    "reserve_provider_call",
]
