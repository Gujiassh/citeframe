from contextlib import contextmanager

from ai_pdf_api.services.capabilities import connection_profile
from ai_pdf_api.services.model_config_types import ModelConnection, ModelConfigurationError
from ai_pdf_api.services.model_transport import model_client
from ai_pdf_api.services.providers import (
    DeepSeekGenerationProvider, ModelProviderError, OllamaEmbeddingProvider,
    OpenAIEmbeddingProvider, OpenAIGenerationProvider, _attach_profile,
)


class _BoundProvider:
    def __init__(self, connection: ModelConnection):
        self.connection = connection
        self.provider, self.model = connection.provider, connection.model
        self.dimensions, self.version = connection.dimensions, connection.version
        self.allow_legacy_index = connection.source == "server"
        self.capability_profile = connection_profile(connection)
        self.config_fingerprint = self.capability_profile.config_fingerprint

    @contextmanager
    def adapter(self):
        c = self.connection
        try:
            with model_client(c.base_url, c.timeout_seconds) as client:
                if c.capability == "embedding":
                    adapter = OpenAIEmbeddingProvider(model=c.model, dimensions=c.dimensions, version=c.version,
                        api_key=c.api_key, api_base=c.base_url, timeout_seconds=c.timeout_seconds, client=client, exact_base=True)
                else:
                    from ai_pdf_api.services.chat_completions import ChatCompletionsProvider
                    cls = ChatCompletionsProvider if c.protocol == "openai_chat_completions" else OpenAIGenerationProvider
                    adapter = cls(model=c.model, api_key=c.api_key, api_base=c.base_url,
                        timeout_seconds=c.timeout_seconds, max_output_tokens=c.max_output_tokens, client=client, exact_base=True)
                yield adapter
        except ModelConfigurationError as error:
            raise ModelProviderError(error.code, error.message) from None

    def generate(self, messages, *, max_output_tokens=None):
        with self.adapter() as adapter:
            return adapter.generate(messages, max_output_tokens=max_output_tokens)

    def stream(self, messages, *, max_output_tokens=None):
        with self.adapter() as adapter:
            yield from adapter.stream(messages, max_output_tokens=max_output_tokens)

    def embed_documents(self, texts):
        with self.adapter() as adapter:
            return adapter.embed_documents(texts)

    def embed_query(self, text):
        with self.adapter() as adapter:
            return adapter.embed_query(text)


def embedding_provider_for(c: ModelConnection):
    if c.source == "workspace":
        return _BoundProvider(c)
    if c.protocol == "ollama":
        provider = OllamaEmbeddingProvider(model=c.model, dimensions=c.dimensions, version=c.version,
            base_url=c.base_url, query_instruction=c.query_instruction, timeout_seconds=c.timeout_seconds)
    else:
        provider = OpenAIEmbeddingProvider(model=c.model, dimensions=c.dimensions, version=c.version,
            api_key=c.api_key, api_base=c.base_url, timeout_seconds=c.timeout_seconds)
    provider.allow_legacy_index = True
    return _attach_profile(provider, connection_profile(c))


def generation_provider_for(c: ModelConnection):
    if c.source == "workspace":
        return _BoundProvider(c)
    cls = DeepSeekGenerationProvider if c.protocol == "anthropic_messages" else OpenAIGenerationProvider
    return _attach_profile(cls(model=c.model, api_key=c.api_key, api_base=c.base_url,
        timeout_seconds=c.timeout_seconds, max_output_tokens=c.max_output_tokens), connection_profile(c))
