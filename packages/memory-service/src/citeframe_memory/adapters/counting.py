"""Explicit model-specific counting; estimates preserve their provenance."""

from collections.abc import Callable
from dataclasses import dataclass
from math import ceil

from citeframe_contracts.memory import GenerationRequest, ModelConnectionSnapshot, ProtocolError, TokenCount

from ._requests import serialized


@dataclass(frozen=True)
class CountingProfile:
    protocol: str
    model: str
    config_fingerprint: str
    context_window_tokens: int
    counter_id: str
    counter_version: str
    mode: str


class PayloadTokenCounter:
    """The injected counter accounts for full native payload and protocol overhead."""

    def __init__(self, profile: CountingProfile, count_payload: Callable[[str], int]):
        self.profile = profile
        self.count_payload = count_payload

    def count(self, request: GenerationRequest, connection: ModelConnectionSnapshot) -> TokenCount:
        profile = self.profile
        if (profile.protocol != connection.protocol or profile.model != connection.model
                or profile.config_fingerprint != connection.config_fingerprint
                or type(profile.context_window_tokens) is not int or profile.context_window_tokens < 1
                or profile.context_window_tokens != connection.context_window_tokens
                or not isinstance(profile.counter_id, str) or not profile.counter_id
                or not isinstance(profile.counter_version, str) or not profile.counter_version or profile.mode not in {"exact", "estimated"}):
            raise ProtocolError("memory_counting_profile_unknown")
        try:
            count = self.count_payload(serialized(request, connection))
        except Exception:
            raise ProtocolError("memory_counting_failed") from None
        if type(count) is not int or count < 0:
            raise ProtocolError("memory_counting_invalid")
        return TokenCount(count, profile.mode, profile.counter_id, profile.counter_version, profile.config_fingerprint)


class CharacterEstimateCounter(PayloadTokenCounter):
    def __init__(self, profile: CountingProfile, *, characters_per_token: float, protocol_overhead_tokens: int):
        if profile.mode != "estimated" or type(characters_per_token) not in (int, float) or not 0 < characters_per_token < float("inf") or type(protocol_overhead_tokens) is not int or protocol_overhead_tokens < 0:
            raise ValueError("invalid estimated counting profile")
        super().__init__(profile, lambda text: ceil(len(text) / characters_per_token) + protocol_overhead_tokens)
