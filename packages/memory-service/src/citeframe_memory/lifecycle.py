"""Synchronous instruction invalidation; no jobs or model calls."""
from datetime import UTC, datetime
from sqlalchemy import select
from citeframe_contracts.memory import SourceUnavailable
from citeframe_persistence.models.memory import MemoryRecord, MemoryRevision, MemorySource, MemoryUse


def invalidate_instruction(commands, context, source_id: str) -> None:
    session = commands.session
    with session.begin():
        commands._authorize(context)
        source = session.scalar(select(MemorySource).where(
            MemorySource.id == source_id, MemorySource.workspace_id == context.workspace_id,
            MemorySource.owner_user_id == context.actor_user_id).with_for_update())
        if source is None or source.state == "deleted":
            raise SourceUnavailable("source_unavailable")
        if source.state != "current":
            return
        now = datetime.now(UTC)
        source.state, source.invalidated_at = "stale", now
        ids = set(session.scalars(select(MemoryRevision.memory_id).join(
            MemoryUse, MemoryUse.consumer_revision_id == MemoryRevision.revision_id).where(
            MemoryUse.source_id == source_id)))
        for mid in sorted(ids):
            record = commands._record(context, mid)
            head = commands._head(record)
            if head.intent != "deleted":
                commands._append(record, head, head.instruction_id, head.intent, "invalidate", now,
                                 validity="invalidated")
