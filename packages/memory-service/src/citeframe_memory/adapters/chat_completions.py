"""OpenAI Chat Completions-compatible neutral adapter."""
from ._generation import NativeGenerationAdapter
from ._streams import ChatState


class ChatCompletionsAdapter(NativeGenerationAdapter):
    protocol = "openai_chat_completions"
    state_type = ChatState
