from __future__ import annotations

from citeframe_contracts.validation import AgentResultValidationError
import json
from ai_pdf_api.services.providers import ModelProviderError
from citeframe_evaluation.contracts import ProviderCallRecord
from citeframe_evaluation.diagnostics import (
    DiagnosticCapture,
    OutputFailureDiagnostic,
    RawOutputRecord,
    with_failure_origin,
)
from ai_pdf_worker.research.executor import ResearchExecutionError


_SEMANTIC_NODE_FAILURES: dict[str, str] = {
    "claim_evidence_not_in_branch": "researcher",
    "claim_requires_evidence": "researcher",
    "duplicate_claim_evidence": "researcher",
    "duplicate_claim_id": "researcher",
    "duplicate_branch_evidence": "researcher",
    "unproven_branch_evidence": "researcher",
    "researcher_branch_mismatch": "researcher",
    "invalid_claim": "researcher",
    "invalid_research_plan": "planner",
    "verifier_claim_set_mismatch": "verifier",
    "verifier_mutated_claim": "verifier",
    "verifier_status_invalid": "verifier",
    "verifier_evidence_scope_mismatch": "verifier",
    "critic_conflict_set_mismatch": "critic",
    "invalid_synthesis_selection": "synthesizer",
}


def _bind_capture_record(
    diagnostic_capture: DiagnosticCapture | None,
    *,
    node_key: str | None,
    logical_call_key: str | None = None,
) -> RawOutputRecord | None:
    if diagnostic_capture is None:
        return None
    if logical_call_key:
        bound = diagnostic_capture.get_by_logical_call_key(logical_call_key)
        if bound is not None:
            return bound
    if node_key is None:
        return None
    # Exact single-node semantic failures bind the unique record for that node.
    matches = [item for item in diagnostic_capture.records if item.node_key == node_key]
    if len(matches) == 1:
        return matches[0]
    # Branch researcher failures must never silently pick "latest" when multiple
    # researcher logical calls exist without an exact key.
    if node_key == "researcher" and len(matches) != 1:
        return None
    return matches[-1] if matches else None


def _diagnostic_for_semantic_failure(
    failure_code: str,
    diagnostic_capture: DiagnosticCapture | None,
    *,
    logical_call_key: str | None = None,
) -> OutputFailureDiagnostic | None:
    node_key = _SEMANTIC_NODE_FAILURES.get(failure_code)
    if node_key is None and failure_code.endswith("_invalid_output"):
        node_key = failure_code[: -len("_invalid_output")]
    if node_key is None:
        return None
    bound = _bind_capture_record(
        diagnostic_capture,
        node_key=node_key,
        logical_call_key=logical_call_key,
    )
    return with_failure_origin(
        OutputFailureDiagnostic(
            stage="research_semantic_or_schema",
            rule=failure_code,
            path="$",
            node_key=node_key,
            logical_call_key=bound.logical_call_key if bound else logical_call_key,
            raw_output_sha256=bound.sha256 if bound else None,
            failure_code=failure_code,
        )
    )


def _safe_failure_code(error: Exception) -> str:
    """Preserve historical public wrapper codes for unknown exceptions.

    v4-compatible `run_quick_case` / `run_research_case` keep
    `type(error).__name__` for unexpected failures (e.g. RuntimeError).
    Campaign/scorer v5 still classifies unknown origins as engineering/
    integrity and modelQuality=not_evaluable at campaign gates.
    """
    if isinstance(error, json.JSONDecodeError):
        return "quick_invalid_output"
    if isinstance(error, ModelProviderError):
        return error.code
    if isinstance(error, AgentResultValidationError):
        return error.failure_code
    if isinstance(error, ResearchExecutionError):
        value = str(error).strip()
        if (
            value
            and len(value) <= 96
            and all(character.isalnum() or character in "._:-" for character in value)
        ):
            return value
        return "research_execution_error"
    return type(error).__name__


def _require_final_usage(records: tuple[ProviderCallRecord, ...]) -> None:
    if any(item.status == "succeeded" and not item.usage_final for item in records):
        raise ResearchExecutionError("provider_usage_unavailable")
