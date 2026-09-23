from __future__ import annotations

RETRY_POLICY_VERSION = "r803-provider-retry-v3"
MAX_PROVIDER_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (5, 15)
RETRYABLE_PROVIDER_CODES = frozenset(
    {
        "generation_incomplete_response",
        "generation_invalid_response",
        "generation_provider_transient",
        "generation_provider_unreachable",
    }
)
