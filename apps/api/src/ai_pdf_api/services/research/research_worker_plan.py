"""API storage composition facade for neutral Research plan publication."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

from sqlalchemy.orm import Session

from ai_pdf_api.services.research import append_research_event
from ai_pdf_api.services.research.research_worker_lease import _locked_attempt
from ai_pdf_api.services.storage import delete_object_if_exists, upload_bytes
from citeframe_research_persistence.plan import publish_research_plan as _publish_research_plan
from citeframe_research_persistence.types import PlanSubproblemDraft


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
    try:
        result = _publish_research_plan(
            db,
            attempt_id=attempt_id,
            lease_token=lease_token,
            summary=summary,
            subproblems=subproblems,
            known_gaps=known_gaps,
            estimated_provider_calls=estimated_provider_calls,
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
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



publish_research_plan.__wrapped__ = _publish_research_plan

__all__ = ["PlanSubproblemDraft", "publish_research_plan"]
