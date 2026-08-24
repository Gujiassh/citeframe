from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from citeframe_persistence.models import ResearchIdempotencyRecord
from .constants import IDEMPOTENCY_TTL
from .errors import ResearchError, canonical_json, canonical_sha256, validate_idempotency_key, persisted_error_payload


def _frozen_error(record: ResearchIdempotencyRecord) -> ResearchError:
    payload = record.response_json or {}
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return ResearchError("research_state_conflict", "The previous request failed.", record.http_status or 409)
    return ResearchError(str(error.get("code", "research_state_conflict")), str(error.get("message", "The previous request failed.")), record.http_status or 409, error.get("details") if isinstance(error.get("details"), dict) else {}, str(error["requestId"]) if isinstance(error.get("requestId"), str) else None)


def idempotent_mutation(db: Session, *, workspace_id: str, actor_user_id: str, operation: str, resource_path: str, key: str, request_body: object, execute: Callable[[], tuple[int, dict[str, object], str]]) -> tuple[int, dict[str, object], bool]:
    now = datetime.now(UTC)
    request_hash = canonical_sha256(request_body)
    record = db.scalar(select(ResearchIdempotencyRecord).where(ResearchIdempotencyRecord.workspace_id == workspace_id, ResearchIdempotencyRecord.actor_user_id == actor_user_id, ResearchIdempotencyRecord.operation == operation, ResearchIdempotencyRecord.canonical_resource_path == resource_path, ResearchIdempotencyRecord.idempotency_key == key))
    expires_at = record.expires_at if record else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if record and expires_at is not None and expires_at <= now:
        db.delete(record)
        db.commit()
        record = None
    if record:
        if record.request_sha256 != request_hash:
            raise ResearchError("idempotency_key_reused", "Idempotency-Key was already used with a different request.", 409)
        if record.status == "completed" and record.response_json is not None:
            return record.http_status or 200, record.response_json, True
        if record.status == "failed":
            raise _frozen_error(record)
        raise ResearchError("idempotency_request_in_progress", "The original request is still in progress.", 409)
    record = ResearchIdempotencyRecord(workspace_id=workspace_id, actor_user_id=actor_user_id, operation=operation, canonical_resource_path=resource_path, idempotency_key=key, request_sha256=request_hash, status="in_progress", created_at=now, expires_at=now + IDEMPOTENCY_TTL)
    db.add(record)
    db.commit()
    try:
        http_status, response_json, result_id = execute()
        record = db.get(ResearchIdempotencyRecord, record.id)
        assert record is not None
        record.status = "completed"
        record.http_status = http_status
        record.result_resource_id = result_id
        record.response_schema_version = "1"
        record.response_json = response_json
        record.completed_at = datetime.now(UTC)
        db.commit()
        return http_status, response_json, False
    except ResearchError as error:
        db.rollback()
        record = db.get(ResearchIdempotencyRecord, record.id)
        if record is not None:
            record.status = "failed"
            record.http_status = error.status_code
            record.response_schema_version = "1"
            record.response_json = persisted_error_payload(error)
            record.completed_at = datetime.now(UTC)
            db.commit()
        raise
    except Exception as error:
        db.rollback()
        record = db.get(ResearchIdempotencyRecord, record.id)
        safe_error = ResearchError("research_internal_error", "The Research request failed before completion.", 500)
        if record is not None:
            record.status = "failed"
            record.http_status = 500
            record.response_schema_version = "1"
            record.response_json = persisted_error_payload(safe_error)
            record.completed_at = datetime.now(UTC)
            db.commit()
        raise safe_error from error


# Private compatibility spelling retained for API composition adapters.
_idempotent_mutation = idempotent_mutation
