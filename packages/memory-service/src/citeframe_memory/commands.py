"""Synchronous instruction-only commands; receipts leave only after commit."""
from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
import json
from uuid import UUID, uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from citeframe_contracts.memory import (
    AccessContext, AccessDenied, AccessPort, IdempotencyConflict, MemoryConditions,
    MemoryError, MemoryReceipt, MemoryRequest, MemoryStatement, MemoryView,
    SourceUnavailable, VersionConflict,
)
from citeframe_persistence.models.memory import (
    MemoryInstruction, MemoryOperation, MemoryRecord, MemoryRevision, MemorySource, MemoryUse,
)
from .access import require_private_management
from .admission import admit_statement
from .sources import resolve_instruction


def new_id() -> str:
    return str(uuid4())


def canonical_hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, default=lambda v: v.isoformat()).encode()).hexdigest()


def content_hash(content: str) -> str:
    return sha256(content.encode()).hexdigest()


def conditions_json(statement: MemoryStatement) -> dict:
    c = statement.conditions
    return {"subject": c.subject, "applicability": c.applicability,
            "effectiveFrom": c.effective_from.isoformat() if c.effective_from else None}


class MemoryCommands:
    def __init__(self, session: Session, access: AccessPort):
        if access is None or not callable(getattr(access, "authorize", None)):
            raise AccessDenied("authorizer_required")
        if session.get_bind().dialect.name != "postgresql":
            raise ValueError("memory_requires_postgresql")
        self.session = session
        self.access = access

    def _authorize(self, context: AccessContext) -> None:
        require_private_management(context, context.actor_user_id)
        self.access.authorize(context, owner_user_id=context.actor_user_id)

    def _record(self, context: AccessContext, memory_id: str) -> MemoryRecord:
        record = self.session.scalar(select(MemoryRecord).where(
            MemoryRecord.id == memory_id, MemoryRecord.workspace_id == context.workspace_id,
            MemoryRecord.owner_user_id == context.actor_user_id).with_for_update())
        if record is None:
            raise AccessDenied("memory_unavailable")
        return record

    def _head(self, record: MemoryRecord) -> MemoryRevision:
        return self.session.get(MemoryRevision, (record.id, record.current_version))

    def _view(self, record: MemoryRecord, revision: MemoryRevision | None = None) -> MemoryView:
        head = self._head(record)
        revision = revision or head
        erased = head.intent == "deleted" or revision.erased_at is not None
        statement = None
        invalid = self.session.scalar(select(MemoryUse.id).join(
            MemorySource, MemorySource.id == MemoryUse.source_id).join(
            MemoryInstruction, MemoryInstruction.id == MemorySource.instruction_id).where(
            MemoryUse.consumer_revision_id == revision.revision_id,
            or_(MemorySource.state != "current", MemoryInstruction.erased_at.is_not(None),
                MemorySource.content_sha256 != MemoryInstruction.content_sha256)).limit(1)) is not None
        if not erased:
            c = revision.conditions
            statement = MemoryStatement(revision.content, MemoryConditions(c["subject"], c["applicability"],
                datetime.fromisoformat(c["effectiveFrom"]) if c["effectiveFrom"] else None),
                revision.kind, revision.pinned, revision.valid_until)
        return MemoryView(record.id, revision.version, revision.revision_id,
                          revision.intent, "invalidated" if invalid else revision.validity,
                          statement, revision.confirmation_source_id, erased)

    def read(self, context: AccessContext, memory_id: str) -> MemoryView:
        with self.session.begin():
            self._authorize(context)
            result = self._view(self._record(context, memory_id))
        return result

    def history(self, context: AccessContext, memory_id: str) -> tuple[MemoryView, ...]:
        with self.session.begin():
            self._authorize(context)
            record = self._record(context, memory_id)
            result = tuple(self._view(record, r) for r in self.session.scalars(
                select(MemoryRevision).where(MemoryRevision.memory_id == memory_id)
                .order_by(MemoryRevision.version)))
        return result

    def read_source(self, context: AccessContext, source_id: str):
        with self.session.begin():
            result = resolve_instruction(self.session, self.access, context, source_id)
        return result

    def _receipt(self, context: AccessContext, operation: MemoryOperation) -> MemoryReceipt:
        if operation.state != "committed":
            raise MemoryError("operation_not_settled")
        return MemoryReceipt(operation.id, operation.request_id, operation.result_version,
                             self._view(self._record(context, operation.resource_id)))

    def reconcile(self, context: AccessContext, request_id: str) -> MemoryReceipt | None:
        """Use a fresh Session after an unknown acknowledgement; never assume rollback."""
        with self.session.begin():
            self._authorize(context)
            operation = self.session.scalar(select(MemoryOperation).where(
                MemoryOperation.workspace_id == context.workspace_id,
                MemoryOperation.actor_user_id == context.actor_user_id,
                MemoryOperation.request_id == request_id))
            result = self._receipt(context, operation) if operation else None
        return result

    def remember(self, context: AccessContext, request: MemoryRequest,
                 statement: MemoryStatement) -> MemoryReceipt:
        return self._mutate(context, request, "remember", statement=statement)

    def correct(self, context: AccessContext, request: MemoryRequest, memory_id: str,
                expected_version: int, statement: MemoryStatement) -> MemoryReceipt:
        return self._mutate(context, request, "correct", memory_id, expected_version, statement)

    def deactivate(self, context: AccessContext, request: MemoryRequest, memory_id: str,
                   expected_version: int) -> MemoryReceipt:
        return self._mutate(context, request, "deactivate", memory_id, expected_version)

    def delete(self, context: AccessContext, request: MemoryRequest, memory_id: str,
               expected_version: int) -> MemoryReceipt:
        return self._mutate(context, request, "delete", memory_id, expected_version)

    def _mutate(self, context, request, action, memory_id=None, expected_version=None, statement=None):
        if str(UUID(request.request_id)) != request.request_id:
            raise ValueError("invalid_request_id")
        if not 8 <= len(request.idempotency_key) <= 128 or any(
                not 33 <= ord(c) <= 126 for c in request.idempotency_key):
            raise ValueError("invalid_idempotency_key")
        if memory_id is not None and (type(expected_version) is not int or expected_version < 1):
            raise ValueError("invalid_expected_version")
        method = {"remember": "POST", "correct": "POST", "deactivate": "PATCH", "delete": "DELETE"}[action]
        path = f"/memory/{memory_id or ''}/{action}"
        digest = canonical_hash({"method": method, "path": path, "expectedVersion": expected_version,
                                 "statement": asdict(statement) if statement else None})
        with self.session.begin():
            self._authorize(context)
            matches = list(self.session.scalars(select(MemoryOperation).where(
                MemoryOperation.workspace_id == context.workspace_id,
                MemoryOperation.actor_user_id == context.actor_user_id,
                or_(MemoryOperation.request_id == request.request_id,
                    (MemoryOperation.method == method) & (MemoryOperation.path == path)
                    & (MemoryOperation.key == request.idempotency_key))).with_for_update()))
            if matches:
                if len(matches) != 1 or matches[0].request_sha256 != digest:
                    raise IdempotencyConflict("idempotency_conflict")
                result = self._receipt(context, matches[0])
            else:
                now = datetime.now(UTC)
                record = self._record(context, memory_id) if memory_id else None
                head = self._head(record) if record else None
                if record and record.current_version != expected_version:
                    raise VersionConflict("version_conflict")
                if head and (head.intent == "deleted" or (action != "delete" and head.intent == "superseded")):
                    raise VersionConflict("terminal_memory")
                if action in ("remember", "correct"):
                    admit_statement(statement)
                instruction = MemoryInstruction(id=new_id(), workspace_id=context.workspace_id,
                    actor_user_id=context.actor_user_id, operation=action, request_id=request.request_id,
                    target_memory_id=memory_id, expected_version=expected_version,
                    content=statement.content if statement else None,
                    content_sha256=content_hash(statement.content) if statement else None,
                    created_at=now, erased_at=None)
                self.session.add(instruction)
                self.session.flush()
                if action in ("remember", "correct"):
                    if record:
                        self._append(record, head, instruction.id, "superseded", "correct", now)
                    record = self._create(context, instruction, statement, memory_id, now)
                elif action == "deactivate":
                    self._append(record, head, instruction.id, "inactive", "deactivate", now)
                else:
                    self._append(record, head, instruction.id, "deleted", "delete", now)
                    self._erase(record, now)
                operation = MemoryOperation(id=new_id(), workspace_id=context.workspace_id,
                    actor_user_id=context.actor_user_id, request_id=request.request_id, method=method,
                    path=path, key=request.idempotency_key, request_sha256=digest, state="committed",
                    resource_id=record.id, result_version=record.current_version,
                    http_status=201 if action in ("remember", "correct") else 200, created_at=now, settled_at=now)
                self.session.add(operation)
                self.session.flush()
                result = self._receipt(context, operation)
        return result

    def _create(self, context, instruction, statement, predecessor, now):
        source = MemorySource(id=new_id(), workspace_id=context.workspace_id, kind="memory_instruction",
            native_id=instruction.id, instruction_id=instruction.id, source_version=1,
            native_version={"instructionId": instruction.id, "requestId": instruction.request_id},
            content_sha256=instruction.content_sha256, actor_user_id=context.actor_user_id,
            audience="private", owner_user_id=context.actor_user_id, state="current", created_at=now)
        self.session.add(source)
        self.session.flush()
        record = MemoryRecord(id=new_id(), workspace_id=context.workspace_id,
            owner_user_id=context.actor_user_id, scope_kind="workspace", visibility="private",
            current_version=1, supersedes_id=predecessor, created_at=now)
        self.session.add(record)
        self.session.flush()
        revision = MemoryRevision(workspace_id=context.workspace_id, memory_id=record.id,
            version=1, revision_id=new_id(), intent="active", validity="valid",
            cause="correct" if predecessor else "create", kind=statement.kind,
            content=statement.content, content_sha256=content_hash(statement.content),
            confirmation="explicit_remember", confirmation_source_id=source.id,
            conditions=conditions_json(statement), pinned=statement.pinned, valid_until=statement.valid_until,
            instruction_id=instruction.id, created_at=now, erased_at=None)
        self.session.add(revision)
        self.session.flush()
        self.session.add(MemoryUse(id=new_id(), workspace_id=context.workspace_id,
            consumer_revision_id=revision.revision_id, source_id=source.id, use_mode="support",
            atom_key="statement", support_group="instruction", relation="confirmation"))
        return record

    def _append(self, record, head, instruction_id, intent, cause, now, validity=None):
        erased = intent == "deleted"
        revision = MemoryRevision(workspace_id=record.workspace_id, memory_id=record.id,
            version=record.current_version + 1, revision_id=new_id(), intent=intent,
            validity=validity or head.validity, cause=cause, kind=head.kind,
            content=None if erased else head.content, content_sha256=None if erased else head.content_sha256,
            confirmation=head.confirmation, confirmation_source_id=head.confirmation_source_id,
            conditions=None if erased else head.conditions, pinned=head.pinned, valid_until=head.valid_until,
            instruction_id=instruction_id, created_at=now, erased_at=now if erased else None)
        self.session.add(revision)
        self.session.flush()
        for support in self.session.scalars(select(MemoryUse).where(
                MemoryUse.consumer_revision_id == head.revision_id)):
            self.session.add(MemoryUse(id=new_id(), workspace_id=record.workspace_id,
                consumer_revision_id=revision.revision_id, source_id=support.source_id,
                use_mode=support.use_mode, atom_key=support.atom_key,
                support_group=support.support_group, relation=support.relation))
        record.current_version = revision.version
        self.session.flush()
        return revision

    def _erase(self, record, now):
        self.session.execute(update(MemoryRevision).where(
            MemoryRevision.memory_id == record.id, MemoryRevision.erased_at.is_(None)).values(
                content=None, content_sha256=None, conditions=None, erased_at=now))
        source_ids = set(self.session.scalars(select(MemoryUse.source_id).join(
            MemoryRevision, MemoryRevision.revision_id == MemoryUse.consumer_revision_id).where(
            MemoryRevision.memory_id == record.id)))
        protected_instructions = set()
        for sid in sorted(source_ids):
            source = self.session.get(MemorySource, sid)
            another_live = self.session.scalar(select(MemoryRevision.revision_id).join(
                MemoryUse, MemoryUse.consumer_revision_id == MemoryRevision.revision_id).where(
                MemoryUse.source_id == sid, MemoryRevision.memory_id != record.id,
                MemoryRevision.erased_at.is_(None)).limit(1))
            if another_live:
                protected_instructions.add(source.instruction_id)
                continue
            source.state, source.content_sha256, source.invalidated_at = "deleted", None, now
            instruction = self.session.get(MemoryInstruction, source.instruction_id)
            if instruction.erased_at is None:
                instruction.content = instruction.content_sha256 = None
                instruction.erased_at = now
        instruction_ids = set(self.session.scalars(select(MemoryRevision.instruction_id).where(
            MemoryRevision.memory_id == record.id)))
        for iid in instruction_ids - protected_instructions:
            # A correction action can support its new successor as well as audit its predecessor.
            live = self.session.scalar(select(MemoryRevision.revision_id).where(
                MemoryRevision.instruction_id == iid, MemoryRevision.erased_at.is_(None)).limit(1))
            instruction = self.session.get(MemoryInstruction, iid)
            if not live and instruction.erased_at is None:
                instruction.content = instruction.content_sha256 = None
                instruction.erased_at = now
        self.session.flush()
