"""HTTP projection and fresh-session composition for private management."""
from __future__ import annotations

import base64
import hmac
import json
import time

from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from citeframe_contracts.memory import (
    AccessContext, MemoryConditions, MemoryError, MemoryRequest, MemoryStatement, VersionConflict,
)
from citeframe_memory.access import WorkspaceAccess
from citeframe_memory.commands import MemoryCommands
from citeframe_memory.management_queries import ManagementQueries
from ai_pdf_api.schemas.memory import (
    CorrectionReceipt, DeleteReceipt, InstructionSourceDto, MemoryPage,
    MemoryResponse, MutationReceipt, OperationDto,
)


class ManagementError(MemoryError):
    def __init__(self, code, current_version=None):
        super().__init__(code)
        self.current_version = current_version


class Cursors:
    def __init__(self, secret):
        self.key = hmac.digest(secret.encode(), b"citeframe:memory-management:cursor:v1", "sha256")

    @staticmethod
    def encode_bytes(value):
        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    def encode(self, binding, after):
        payload = json.dumps(dict(v=1, binding=binding, after=after, expires=int(time.time()) + 900),
                             sort_keys=True, separators=(",", ":")).encode()
        return self.encode_bytes(payload) + "." + self.encode_bytes(hmac.digest(self.key, payload, "sha256"))

    def decode(self, cursor, binding):
        if cursor is None:
            return None
        try:
            if len(cursor) > 4096:
                raise ValueError()
            body, signature = cursor.split(".")
            payload = base64.b64decode(body + "=" * (-len(body) % 4), altchars=b"-_", validate=True)
            mac = base64.b64decode(signature + "=" * (-len(signature) % 4), altchars=b"-_", validate=True)
            if not hmac.compare_digest(mac, hmac.digest(self.key, payload, "sha256")):
                raise ValueError()
            value = json.loads(payload)
            if (value["v"] != 1 or value["binding"] != binding or value["expires"] <= time.time()
                    or set(value) != {"v", "binding", "after", "expires"}):
                raise ValueError()
            return value["after"]
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise ManagementError("invalid_cursor") from None


class MemoryManagement:
    def __init__(self, engine, actor_id, workspace_id, cursor_secret, render_error):
        self.engine = engine
        self.render_error = render_error
        self.context = AccessContext(actor_id, workspace_id, "management", "private")
        self.cursors = Cursors(cursor_secret)

    def _read(self, schema, callback, *, status_code=200):
        with Session(self.engine) as session, session.begin():
            try:
                queries = ManagementQueries(session, self.context)
                value = callback(queries)
                payload = schema.model_validate(value).model_dump(mode="json")
                return JSONResponse(content=payload, status_code=status_code)
            except MemoryError as error:
                # Owner-only errors must render before these authorization locks release.
                return self.render_error(error)

    def _binding(self, endpoint, limit, **filters):
        return dict(actor=self.context.actor_user_id, workspace=self.context.workspace_id,
                    endpoint=endpoint, limit=limit, **filters)

    def list(self, status, limit, cursor):
        binding = self._binding("list", limit, status=status, scope="workspace")
        after = self.cursors.decode(cursor, binding)
        def query(q):
            rows = q.page(status=status, limit=limit, after=after)
            selected = rows[:limit]
            next_cursor = None
            if len(rows) > limit:
                record = selected[-1][0]
                next_cursor = self.cursors.encode(binding, [record.created_at.isoformat(), record.id])
            return dict(items=[q.projection(r, v) for r, v in selected], nextCursor=next_cursor)
        return self._read(MemoryPage, query)

    def current(self, memory_id):
        def query(q):
            record = q.record(memory_id)
            if q.head(record).intent == "deleted":
                raise ManagementError("erased")
            return dict(memory=q.projection(record))
        return self._read(MemoryResponse, query)

    def history(self, memory_id, limit, cursor):
        binding = self._binding("history", limit, memory=memory_id)
        after = self.cursors.decode(cursor, binding)
        def query(q):
            record = q.record(memory_id)
            if q.head(record).intent == "deleted":
                raise ManagementError("erased")
            rows = q.history(record, limit=limit, after=after)
            return dict(items=[q.projection(record, r) for r in rows[:limit]],
                        nextCursor=self.cursors.encode(binding, [rows[limit-1].version])
                        if len(rows) > limit else None)
        return self._read(MemoryPage, query)

    def operation(self, identifier, by_request=False):
        def query(q):
            op = q.operation(identifier, by_request=by_request)
            record = q.record(op.resource_id)
            resource = q.projection(record)
            return dict(requestId=op.request_id, accepted=True, operationId=op.id, state="committed",
                        resourceId=op.resource_id, resultVersion=op.result_version,
                        currentVersion=record.current_version, intent=resource["intent"],
                        contentAvailable=resource["contentAvailable"],
                        cleanupState="completed" if op.method == "DELETE" else "not_required")
        return self._read(OperationDto, query)

    def source(self, reference):
        def query(q):
            value = q.source(reference.model_dump())
            return dict(sourceRef=reference.model_dump(), content=value.content,
                        contentKind="explicit_instruction", occurredAt=value.created_at,
                        sourceState="current", provenance=dict(role="user", actorUserId=value.actor_user_id,
                        actorAttribution="authenticated", confirmation="explicit_remember"),
                        branchRelation="other_task", truncated=False, nextCursor=None)
        return self._read(InstructionSourceDto, query)

    def mutate(self, action, payload, key, memory_id=None):
        request = MemoryRequest(payload.requestId, key)
        arguments = [self.context, request]
        if memory_id is not None:
            arguments.extend((memory_id, payload.expectedVersion))
        if action in ("remember", "correct"):
            arguments.append(MemoryStatement(payload.content, MemoryConditions(
                payload.conditions.subject, payload.conditions.applicability,
                payload.conditions.effectiveFrom), payload.kind, payload.pinned, payload.validUntil))
        try:
            with Session(self.engine) as session:
                commands = MemoryCommands(session, WorkspaceAccess(session))
                receipt = getattr(commands, action)(*arguments)
        except VersionConflict as exc:
            code = str(exc)
            def conflict(q):
                raise ManagementError(code, q.record(memory_id).current_version)
            return self._read(None, conflict)
        except SQLAlchemyError:
            # A failed commit acknowledgement cannot establish whether the mutation persisted.
            raise ManagementError("outcome_unknown") from None
        schema = DeleteReceipt if action == "delete" else CorrectionReceipt if action == "correct" else MutationReceipt
        def query(q):
            op = q.operation(receipt.operation_id)
            record = q.record(op.resource_id)
            if action == "delete":
                return dict(requestId=op.request_id, operationId=op.id, resultVersion=op.result_version,
                            id=record.id, intent="deleted", version=record.current_version, cleanupState="completed")
            result = dict(requestId=op.request_id, operationId=op.id, resultVersion=op.result_version,
                          memory=q.projection(record), indexState="not_enabled")
            if action == "correct":
                result["supersededMemoryId"] = record.supersedes_id
            return result
        try:
            return self._read(schema, query, status_code=201 if action in ("remember", "correct") else 200)
        except SQLAlchemyError:
            raise ManagementError("outcome_unknown") from None
