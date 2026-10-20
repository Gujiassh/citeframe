"""Bounded, transaction-bound owner queries; no mutation or model authority."""
from datetime import UTC, datetime

from sqlalchemy import and_, case, exists, or_, select, tuple_
from sqlalchemy.orm import Session, aliased

from citeframe_contracts.memory import AccessContext, AccessDenied, MemoryError, SourceUnavailable
from citeframe_persistence.models.memory import (
    MemoryInstruction, MemoryOperation, MemoryRecord, MemoryRevision, MemorySource, MemoryUse,
)
from .access import WorkspaceAccess
from .sources import resolve_instruction


class ManagementQueries:
    def __init__(self, session: Session, context: AccessContext):
        if session.get_bind().dialect.name != "postgresql":
            raise MemoryError("memory_requires_postgresql")
        self.session, self.context = session, context
        self.access = WorkspaceAccess(session)
        self.access.authorize(context, owner_user_id=context.actor_user_id)
        self.now = datetime.now(UTC)

    def record(self, memory_id):
        record = self.session.scalar(select(MemoryRecord).where(
            MemoryRecord.id == memory_id,
            MemoryRecord.workspace_id == self.context.workspace_id,
            MemoryRecord.owner_user_id == self.context.actor_user_id).with_for_update())
        if record is None:
            raise AccessDenied("memory_unavailable")
        return record

    def head(self, record):
        return self.session.get(MemoryRevision, (record.id, record.current_version))

    def operation(self, identifier, *, by_request=False):
        column = MemoryOperation.request_id if by_request else MemoryOperation.id
        operation = self.session.scalar(select(MemoryOperation).where(
            column == identifier, MemoryOperation.workspace_id == self.context.workspace_id,
            MemoryOperation.actor_user_id == self.context.actor_user_id).with_for_update())
        if operation is None:
            raise MemoryError("operation_not_found")
        if operation.state != "committed":
            raise MemoryError("operation_in_progress")
        return operation

    def source(self, reference):
        source = self.session.scalar(select(MemorySource).where(
            MemorySource.id == reference["sourceId"],
            MemorySource.workspace_id == self.context.workspace_id,
            MemorySource.owner_user_id == self.context.actor_user_id).with_for_update())
        if source is None:
            raise MemoryError("source_not_found")
        if (source.source_version != reference["sourceVersion"]
                or source.content_sha256 != reference["contentSha256"]):
            raise SourceUnavailable("source_version_unavailable")
        return resolve_instruction(self.session, self.access, self.context, source.id)

    def support_available(self, revision):
        use, source, instruction = aliased(MemoryUse), aliased(MemorySource), aliased(MemoryInstruction)
        eligible = and_(
            source.workspace_id == self.context.workspace_id,
            source.owner_user_id == self.context.actor_user_id,
            source.actor_user_id == self.context.actor_user_id,
            source.audience == "private", source.kind == "memory_instruction",
            source.state == "current", source.content_sha256.is_not(None),
            instruction.workspace_id == self.context.workspace_id,
            instruction.actor_user_id == self.context.actor_user_id,
            instruction.erased_at.is_(None), instruction.content.is_not(None),
            source.content_sha256 == instruction.content_sha256)
        invalid = exists(select(use.id).outerjoin(source, source.id == use.source_id)
            .outerjoin(instruction, instruction.id == source.instruction_id).where(
                use.consumer_revision_id == revision.revision_id,
                or_(source.id.is_(None), instruction.id.is_(None), ~eligible)))
        confirmation = exists(select(MemoryUse.id).where(
            MemoryUse.consumer_revision_id == revision.revision_id,
            MemoryUse.source_id == revision.confirmation_source_id))
        return and_(~invalid, confirmation)

    def status_expression(self):
        r = MemoryRevision
        return case(
            (r.intent == "deleted", "deleted"),
            (r.intent == "superseded", "superseded"),
            (r.intent == "inactive", "inactive"),
            (or_(r.validity == "invalidated", ~self.support_available(r)), "invalidated"),
            (r.valid_until <= self.now, "expired"), else_="active")

    def page(self, *, status, limit, after=None):
        query = select(MemoryRecord, MemoryRevision).join(MemoryRevision, and_(
            MemoryRevision.memory_id == MemoryRecord.id,
            MemoryRevision.version == MemoryRecord.current_version)).where(
                MemoryRecord.workspace_id == self.context.workspace_id,
                MemoryRecord.owner_user_id == self.context.actor_user_id)
        if status != "all":
            query = query.where(self.status_expression() == status)
        if after:
            query = query.where(tuple_(MemoryRecord.created_at, MemoryRecord.id) <
                                tuple_(datetime.fromisoformat(after[0]), after[1]))
        return list(self.session.execute(query.order_by(
            MemoryRecord.created_at.desc(), MemoryRecord.id.desc()).limit(limit + 1)))

    def history(self, record, *, limit, after=None):
        query = select(MemoryRevision).where(MemoryRevision.memory_id == record.id)
        if after:
            query = query.where(MemoryRevision.version > after[0])
        return list(self.session.scalars(query.order_by(MemoryRevision.version).limit(limit + 1)))

    def projection(self, record, revision=None):
        head = self.head(record)
        revision = revision or head
        erased = head.intent == "deleted" or revision.erased_at is not None
        available = not erased and revision.validity == "valid"
        refs = []
        if available:
            sources = list(self.session.scalars(select(MemorySource).join(
                MemoryUse, MemoryUse.source_id == MemorySource.id).where(
                MemoryUse.consumer_revision_id == revision.revision_id).order_by(MemorySource.id)))
            available = bool(sources) and any(s.id == revision.confirmation_source_id for s in sources)
            for source in sources:
                try:
                    resolved = resolve_instruction(self.session, self.access, self.context, source.id)
                except SourceUnavailable:
                    available = False
                    break
                refs.append(dict(sourceId=source.id, sourceVersion=source.source_version,
                                 contentSha256=resolved.content_sha256, span=None))
        display = ("deleted" if erased else revision.intent if revision.intent in ("inactive", "superseded")
                   else "invalidated" if not available else "expired" if revision.valid_until
                   and revision.valid_until <= self.now else "active")
        result = dict(id=record.id, version=revision.version, intent=revision.intent,
                      validity=revision.validity, displayStatus=display, contentAvailable=available)
        if not available:
            return dict(result, reason="erased" if erased else "source_unavailable")
        return dict(result, workspaceId=record.workspace_id, ownerUserId=record.owner_user_id,
            visibility="private", scope=dict(kind="workspace", threadId=None, runId=None),
            revisionId=revision.revision_id, kind=revision.kind, confirmation=revision.confirmation,
            conditions=revision.conditions, pinned=revision.pinned, validUntil=revision.valid_until,
            supersedesId=record.supersedes_id, createdAt=record.created_at, updatedAt=revision.created_at,
            content=revision.content, sourceRefs=refs)
