"""Compatibility facade for neutral Research persistence idempotency."""
from citeframe_research_persistence.errors import (
    ResearchError,
    canonical_json,
    canonical_sha256,
    persisted_error_payload as _persisted_error_payload,
    validate_idempotency_key,
)
from citeframe_research_persistence.idempotency import (
    _frozen_error,
    _idempotent_mutation,
    idempotent_mutation,
)

__all__ = [
    "ResearchError",
    "_frozen_error",
    "_idempotent_mutation",
    "_persisted_error_payload",
    "canonical_json",
    "canonical_sha256",
    "idempotent_mutation",
    "validate_idempotency_key",
]
