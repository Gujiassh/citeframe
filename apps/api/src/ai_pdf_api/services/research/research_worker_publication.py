"""API storage/prompt composition facade for neutral Research publication."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

from sqlalchemy.orm import Session

from ai_pdf_api.services.research import append_research_event
from ai_pdf_api.services.research.research_prompt_provenance import load_execution_prompt_dtos
from ai_pdf_api.services.research.research_worker_lease import _locked_attempt
from ai_pdf_api.services.storage import delete_object_if_exists, upload_bytes
from citeframe_research_persistence.publication import (
    _canonical_final_report,
    _final_commit_state,
    publish_final_report as _publish_final_report,
    wait_for_conflict_decision as _wait_for_conflict_decision,
)


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
    if committed_session_factory is None:
        from ai_pdf_api.db.session import SessionLocal

        committed_session_factory = SessionLocal
    return _publish_final_report(
        db,
        attempt_id=attempt_id,
        lease_token=lease_token,
        fact_claim_ids=fact_claim_ids,
        unresolved_claim_ids=unresolved_claim_ids,
        store_bytes=store_bytes,
        cleanup_bytes=cleanup_bytes,
        committed_session_factory=committed_session_factory,
        prompt_loader=load_execution_prompt_dtos,
        now=now,
        locked_attempt=_locked_attempt,
        append_event=append_research_event,
    )


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
    try:
        result = _wait_for_conflict_decision(
            db,
            attempt_id=attempt_id,
            lease_token=lease_token,
            conflict_claim_ids=conflict_claim_ids,
            store_bytes=store_bytes,
            cleanup_bytes=cleanup_bytes,
            now=now,
            locked_attempt=_locked_attempt,
            append_event=append_research_event,
        )
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise



publish_final_report.__wrapped__ = _publish_final_report
wait_for_conflict_decision.__wrapped__ = _wait_for_conflict_decision

__all__ = [
    "_canonical_final_report",
    "_final_commit_state",
    "publish_final_report",
    "wait_for_conflict_decision",
]
