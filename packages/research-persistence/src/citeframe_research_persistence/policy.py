from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class PricingRate:
    input_microunits_per_million_tokens: int
    output_microunits_per_million_tokens: int

@dataclass(frozen=True)
class FailureDisposition:
    reason_code: str
    retryable: bool
    auto_requeued: bool
    step_status: str
    run_status: str

PRICE_BOOK = {("openai", "gpt-5.5", "research-pricing-v1"): PricingRate(2_500_000, 15_000_000)}
TRANSIENT_FAILURE_CODES = {"provider_timeout", "provider_temporarily_unavailable", "tool_temporarily_unavailable"}
SAFE_FAILURE_CODE_MAP = {"TimeoutError": "provider_timeout", "generation_provider_unreachable": "provider_temporarily_unavailable", "generation_provider_error": "provider_temporarily_unavailable", "embedding_provider_unreachable": "tool_temporarily_unavailable", "embedding_provider_error": "tool_temporarily_unavailable", "tool_temporarily_unavailable": "tool_temporarily_unavailable", "provider_timeout": "provider_timeout", "provider_temporarily_unavailable": "provider_temporarily_unavailable", "generation_provider_not_configured": "provider_not_configured", "embedding_provider_not_configured": "provider_not_configured", "generation_invalid_response": "provider_invalid_response", "embedding_invalid_response": "provider_invalid_response", "tool_input_invalid": "tool_input_invalid", "tool_scope_violation": "tool_scope_violation", "evidence_handle_not_found": "evidence_handle_not_found", "research_budget_limit": "research_budget_limit", "research_context_limit_exceeded": "research_context_limit_exceeded", "research_provider_output_incomplete": "research_provider_output_incomplete", "research_retrieval_top_k_mismatch": "research_retrieval_top_k_mismatch", "research_agent_io_version_unavailable": "research_agent_io_version_unavailable", "lease_expired": "lease_expired", "embedding_index_mismatch": "embedding_index_mismatch"}

def estimate_provider_cost(*, provider: str, model: str, pricing_version: str | None, input_tokens: int, output_tokens: int) -> int | None:
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token estimates must be non-negative")
    rate = PRICE_BOOK.get((provider, model, pricing_version)) if pricing_version else None
    if rate is None:
        return None
    numerator = input_tokens * rate.input_microunits_per_million_tokens + output_tokens * rate.output_microunits_per_million_tokens
    return (numerator + 999_999) // 1_000_000

def add_optional_cost(current: int | None, delta: int | None) -> int | None:
    return None if current is None or delta is None else current + delta

def subtract_optional_cost(current: int | None, delta: int | None) -> int | None:
    return None if current is None or delta is None else current - delta

def normalize_failure_code(error_code: str) -> str:
    return SAFE_FAILURE_CODE_MAP.get(error_code, "research_execution_failed")

def is_transient_failure(reason_code: str) -> bool:
    return reason_code in TRANSIENT_FAILURE_CODES
