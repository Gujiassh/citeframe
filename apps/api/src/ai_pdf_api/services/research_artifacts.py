"""Research artifact listing/detail and event/SSE serialization."""

from __future__ import annotations

from ai_pdf_api.models import ResearchArtifact, ResearchEvent, ResearchRun
from ai_pdf_api.services.research_idempotency import ResearchError, canonical_json
from ai_pdf_api.services.research_runs import get_research_run
from ai_pdf_api.services.research_views import (
    USER_ARTIFACT_KINDS,
    artifact_detail,
    artifact_summary,
    iso,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def list_artifacts(db: Session, workspace_id: str, run_id: str) -> dict[str, object]:
    get_research_run(db, workspace_id, run_id)
    artifacts = list(
        db.scalars(
            select(ResearchArtifact)
            .where(
                ResearchArtifact.workspace_id == workspace_id,
                ResearchArtifact.run_id == run_id,
                ResearchArtifact.visibility == "user",
                ResearchArtifact.artifact_kind.in_(USER_ARTIFACT_KINDS),
            )
            .order_by(ResearchArtifact.created_at, ResearchArtifact.id)
        ).all()
    )
    return {"items": [artifact_summary(db, item) for item in artifacts]}

def get_artifact(db: Session, workspace_id: str, run_id: str, artifact_id: str) -> ResearchArtifact:
    get_research_run(db, workspace_id, run_id)
    artifact = db.scalar(
        select(ResearchArtifact).where(
            ResearchArtifact.id == artifact_id,
            ResearchArtifact.workspace_id == workspace_id,
            ResearchArtifact.run_id == run_id,
            ResearchArtifact.visibility == "user",
            ResearchArtifact.artifact_kind.in_(USER_ARTIFACT_KINDS),
        )
    )
    if artifact is None:
        raise ResearchError("research_resource_not_found", "Research artifact not found.", 404)
    return artifact

def get_artifact_detail(db: Session, workspace_id: str, run_id: str, artifact_id: str) -> dict[str, object]:
    artifact = get_artifact(db, workspace_id, run_id, artifact_id)
    try:
        detail = artifact_detail(db, artifact)
    except Exception as error:
        raise ResearchError(
            "research_artifact_unavailable",
            "Research artifact provenance is unavailable.",
            410,
        ) from error
    return {"artifact": detail}

def list_events_after(db: Session, run: ResearchRun, cursor: int) -> list[ResearchEvent]:
    current = run.next_event_seq - 1
    if cursor < 0:
        raise ResearchError("invalid_event_cursor", "Last-Event-ID must be a non-negative decimal integer.", 400)
    if cursor > current:
        raise ResearchError("research_state_conflict", "Last-Event-ID is ahead of the Research run.", 409)
    first_seq = db.scalar(select(func.min(ResearchEvent.seq)).where(ResearchEvent.run_id == run.id))
    if first_seq is not None and cursor < first_seq - 1:
        raise ResearchError("research_event_history_unavailable", "Research event history is unavailable.", 410)
    events = list(
        db.scalars(
            select(ResearchEvent)
            .where(ResearchEvent.run_id == run.id, ResearchEvent.seq > cursor)
            .order_by(ResearchEvent.seq)
        ).all()
    )
    expected = cursor + 1
    for event in events:
        if event.seq != expected:
            raise ResearchError("research_event_history_unavailable", "Research event history is unavailable.", 410)
        expected += 1
    return events

def serialize_sse_event(event: ResearchEvent) -> str:
    envelope = {
        "schemaVersion": 1,
        "eventId": event.id,
        "runId": event.run_id,
        "seq": event.seq,
        "type": event.event_type,
        "occurredAt": iso(event.created_at),
        "data": event.payload_json,
    }
    return f"id: {event.seq}\nevent: {event.event_type}\ndata: {canonical_json(envelope).decode('utf-8')}\n\n"
