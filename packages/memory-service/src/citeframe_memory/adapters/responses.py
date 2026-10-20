"""OpenAI Responses-compatible neutral adapter."""
from ._generation import NativeGenerationAdapter
from ._streams import ResponsesState


class ResponsesAdapter(NativeGenerationAdapter):
    protocol = "openai_responses"
    state_type = ResponsesState
