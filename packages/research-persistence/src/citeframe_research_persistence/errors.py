"""Neutral Research persistence errors and canonical serialization helpers."""
from __future__ import annotations

import hashlib
import json
from uuid import uuid4


class ResearchError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int, details: dict[str, object] | None = None, request_id: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.request_id = request_id


class ResearchAdmissionDeferred(RuntimeError):
    """Internal Worker signal: retry the claim scan without this cap-full Run."""

    def __init__(self, run_id: str) -> None:
        super().__init__("researcher admission is temporarily full")
        self.run_id = run_id


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def validate_idempotency_key(value: str | None) -> str:
    if value is None:
        raise ResearchError("idempotency_key_required", "Idempotency-Key is required.", 400)
    if not 16 <= len(value) <= 128 or any(not 0x20 <= ord(character) <= 0x7E for character in value):
        raise ResearchError("invalid_idempotency_key", "Idempotency-Key must contain 16 to 128 printable ASCII characters.", 400)
    return value


def persisted_error_payload(error: ResearchError) -> dict[str, object]:
    request_id = error.request_id or str(uuid4())
    error.request_id = request_id
    payload: dict[str, object] = {"code": error.code, "message": error.message, "requestId": request_id, "retryable": error.status_code == 503}
    if error.details:
        payload["details"] = error.details
    return {"error": payload}
