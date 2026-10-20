"""Anthropic Messages-compatible neutral adapter."""
from ._generation import NativeGenerationAdapter
from ._streams import AnthropicState


class AnthropicAdapter(NativeGenerationAdapter):
    protocol = "anthropic"
    state_type = AnthropicState
