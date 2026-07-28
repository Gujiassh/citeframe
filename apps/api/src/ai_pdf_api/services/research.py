"""Stable Research service facade.

Public API is re-exported from focused modules. Callers should continue to
import from ``ai_pdf_api.services.research``.
"""

from __future__ import annotations

from ai_pdf_api.services.research_artifacts import (
    get_artifact,
    get_artifact_detail,
    list_artifacts,
    list_events_after,
    serialize_sse_event,
)
from ai_pdf_api.services.research_decisions import decide_conflict, decide_plan
from ai_pdf_api.services.research_events import append_research_event
from ai_pdf_api.services.research_idempotency import (
    ResearchError,
    canonical_json,
    canonical_sha256,
)
from ai_pdf_api.services.research_recovery import retry_research_step
from ai_pdf_api.services.research_runs import (
    build_execution_snapshot_hash_payload,
    build_plan_snapshot_hash_payload,
    cancel_research_run,
    create_research_run,
    finalize_cancel_if_idle,
    get_research_run,
    list_research_runs,
)

__all__ = [
    "ResearchError",
    "append_research_event",
    "build_execution_snapshot_hash_payload",
    "build_plan_snapshot_hash_payload",
    "cancel_research_run",
    "canonical_json",
    "canonical_sha256",
    "create_research_run",
    "decide_conflict",
    "decide_plan",
    "finalize_cancel_if_idle",
    "get_artifact",
    "get_artifact_detail",
    "get_research_run",
    "list_artifacts",
    "list_events_after",
    "list_research_runs",
    "retry_research_step",
    "serialize_sse_event",
]
