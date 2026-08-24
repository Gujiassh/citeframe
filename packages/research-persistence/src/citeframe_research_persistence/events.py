from __future__ import annotations

from datetime import UTC, datetime
from sqlalchemy.orm import Session
from citeframe_persistence.models import ResearchEvent, ResearchRun
from .constants import EVENT_FIELDS, EVENT_TYPES
from .errors import ResearchError


def append_research_event(db: Session, run: ResearchRun, *, event_type: str, dedupe_key: str, data: dict[str, object], step_id: str | None = None, attempt_id: str | None = None, now: datetime | None = None) -> ResearchEvent:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unsupported Research event type: {event_type}")
    if set(data) != EVENT_FIELDS[event_type]:
        raise ValueError(f"Research event {event_type} does not match its closed payload schema")
    if run.next_event_seq > 10_000:
        raise ResearchError("research_event_limit", "The Research event limit has been reached.", 409)
    event = ResearchEvent(workspace_id=run.workspace_id, run_id=run.id, seq=run.next_event_seq, event_type=event_type, event_schema_version="1", step_id=step_id, attempt_id=attempt_id, dedupe_key=dedupe_key, payload_json=data, created_at=now or datetime.now(UTC))
    run.next_event_seq += 1
    db.add(event)
    return event
