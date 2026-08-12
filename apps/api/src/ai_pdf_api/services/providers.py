from __future__ import annotations

from dataclasses import dataclass
import logging
import json
from collections.abc import Iterator
from typing import Literal, Protocol, TypeAlias, TypeVar
from urllib.parse import urlsplit, urlunsplit

import httpx

from ai_pdf_api.core.metrics import observe_provider_request
from ai_pdf_api.core.settings import settings
from ai_pdf_api.services.capabilities import (
    CapabilityProfile,
    CapabilityUnavailableError,
    build_capability_registry,
)

logger = logging.getLogger(__name__)


class ModelProviderError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class EmbeddingProvider(Protocol):
    provider: str
    model: str
    dimensions: int
    version: str
    config_fingerprint: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


GenerationMessage: TypeAlias = dict[str, object]


class GenerationProvider(Protocol):
    provider: str
    model: str
    config_fingerprint: str

    def generate(self, messages: list[GenerationMessage], *, max_output_tokens: int | None = None) -> str:
        ...

    def stream(self, messages: list[GenerationMessage], *, max_output_tokens: int | None = None) -> Iterator[str]:
        ...


@dataclass(frozen=True)
class ProviderMetadata:
    provider: str
    model: str
    dimensions: int
    version: str


class OpenAIEmbeddingProvider:
    provider = "openai"

    def __init__(
        self,
        *,
        model: str,
        dimensions: int,
        version: str,
        api_key: str | None,
        api_base: str,
        timeout_seconds: float,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self.dimensions = dimensions
        self.version = version
        self._api_key = _normalize_api_key(api_key)
        self._api_base = _normalize_openai_base(api_base)
        self._timeout_seconds = timeout_seconds
        self._client = client
        self.config_fingerprint = ""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        vectors = self._embed([text])
        return vectors[0]

    def _embed(self, texts: list[str]) -> list[list[float]]:
        # Fail closed before HTTP; blank/whitespace keys normalize to missing.
        if _normalize_api_key(self._api_key) is None:
            raise ModelProviderError(
                "embedding_provider_not_configured",
                "OpenAI embedding API key is not configured.",
            )
        with observe_provider_request(self.provider, "embedding"):
            payload = {
                "model": self.model,
                "input": texts,
                "dimensions": self.dimensions,
                "encoding_format": "float",
            }
            response = self._post(
                f"{self._api_base}/embeddings",
                payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            data = response.get("data")
            if not isinstance(data, list) or len(data) != len(texts):
                raise ModelProviderError("embedding_invalid_response", "Embedding provider returned an invalid vector count.")
            indexes = [item.get("index") if isinstance(item, dict) else None for item in data]
            if sorted(index for index in indexes if isinstance(index, int)) != list(range(len(texts))):
                raise ModelProviderError("embedding_invalid_response", "Embedding provider returned invalid vector indexes.")
            ordered = sorted(data, key=lambda item: item["index"])
            vectors = [item.get("embedding") for item in ordered if isinstance(item, dict)]
            if len(vectors) != len(texts) or any(not isinstance(vector, list) for vector in vectors):
                raise ModelProviderError("embedding_invalid_response", "Embedding provider returned invalid vectors.")
            _validate_dimensions(vectors, self.dimensions)
            return vectors

    def _post(self, url: str, payload: dict, *, headers: dict[str, str]) -> dict:
        request_headers = {"Content-Type": "application/json", **headers}
        try:
            if self._client is not None:
                response = self._client.post(url, json=payload, headers=request_headers, timeout=self._timeout_seconds)
            else:
                response = httpx.post(url, json=payload, headers=request_headers, timeout=self._timeout_seconds)
        except httpx.RequestError as error:
            logger.error("model_provider_request_failed provider=openai kind=embedding error_type=%s", type(error).__name__)
            raise ModelProviderError("embedding_provider_unreachable", "Embedding provider is unreachable.") from error
        if response.is_error:
            raise ModelProviderError(
                "embedding_provider_error",
                f"Embedding provider returned HTTP {response.status_code}.",
            )
        try:
            data = response.json()
        except ValueError as error:
            raise ModelProviderError("embedding_invalid_response", "Embedding provider returned invalid JSON.") from error
        if not isinstance(data, dict):
            raise ModelProviderError("embedding_invalid_response", "Embedding provider returned an invalid payload.")
        return data


class OllamaEmbeddingProvider:
    provider = "ollama"

    def __init__(
        self,
        *,
        model: str,
        dimensions: int,
        version: str,
        base_url: str,
        query_instruction: str,
        timeout_seconds: float,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self.dimensions = dimensions
        self.version = version
        self._base_url = base_url.rstrip("/")
        self._query_instruction = query_instruction
        self._timeout_seconds = timeout_seconds
        self._client = client
        self.config_fingerprint = ""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        query = f"Instruct: {self._query_instruction}\nQuery: {text}"
        return self._embed([query])[0]

    def _embed(self, texts: list[str]) -> list[list[float]]:
        with observe_provider_request(self.provider, "embedding"):
            response = self._post(
                f"{self._base_url}/api/embed",
                {"model": self.model, "input": texts},
            )
            vectors = response.get("embeddings")
            if not isinstance(vectors, list) or len(vectors) != len(texts) or any(not isinstance(v, list) for v in vectors):
                raise ModelProviderError("embedding_invalid_response", "Ollama returned invalid embedding vectors.")
            _validate_dimensions(vectors, self.dimensions)
            return vectors

    def _post(self, url: str, payload: dict) -> dict:
        try:
            if self._client is not None:
                response = self._client.post(url, json=payload, timeout=self._timeout_seconds)
            else:
                response = httpx.post(url, json=payload, timeout=self._timeout_seconds)
        except httpx.RequestError as error:
            logger.error("model_provider_request_failed provider=ollama kind=embedding error_type=%s", type(error).__name__)
            raise ModelProviderError("embedding_provider_unreachable", "Ollama embedding provider is unreachable.") from error
        if response.is_error:
            raise ModelProviderError("embedding_provider_error", f"Ollama returned HTTP {response.status_code}.")
        try:
            data = response.json()
        except ValueError as error:
            raise ModelProviderError("embedding_invalid_response", "Ollama returned invalid JSON.") from error
        if not isinstance(data, dict):
            raise ModelProviderError("embedding_invalid_response", "Ollama returned an invalid payload.")
        return data


class OpenAIGenerationProvider:
    provider = "openai"

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        api_base: str,
        timeout_seconds: float,
        max_output_tokens: int,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self._api_key = _normalize_api_key(api_key)
        self._api_base = _normalize_openai_base(api_base)
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens
        self._client = client
        self.config_fingerprint = ""

    def generate(self, messages: list[GenerationMessage], *, max_output_tokens: int | None = None) -> str:
        output_limit = self._max_output_tokens if max_output_tokens is None else max_output_tokens
        if output_limit < 1:
            raise ValueError("max_output_tokens must be >= 1")
        with observe_provider_request(self.provider, "generation"):
            # Fail closed before HTTP; blank/whitespace keys normalize to missing.
            if _normalize_api_key(self._api_key) is None:
                raise ModelProviderError(
                    "generation_provider_not_configured",
                    "OpenAI generation API key is not configured.",
                )
            response = self._post(
                f"{self._api_base}/responses",
                {
                    "model": self.model,
                    "input": messages,
                    "max_output_tokens": output_limit,
                },
            )
            incomplete_details = response.get("incomplete_details")
            status = response.get("status")
            if status != "completed" or (
                isinstance(incomplete_details, dict)
                and incomplete_details.get("reason") in {"max_output_tokens", "max_tokens"}
            ):
                raise ModelProviderError(
                    "research_provider_output_incomplete",
                    "Generation provider did not prove that the response completed.",
                )
            output_text = response.get("output_text")
            if isinstance(output_text, str) and output_text.strip():
                return output_text.strip()
            output = response.get("output")
            if isinstance(output, list):
                parts: list[str] = []
                for item in output:
                    if not isinstance(item, dict):
                        continue
                    content_items = item.get("content")
                    if not isinstance(content_items, list):
                        continue
                    for content in content_items:
                        if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                            text = content.get("text")
                            if isinstance(text, str):
                                parts.append(text)
                if parts:
                    return "".join(parts).strip()
            raise ModelProviderError("generation_invalid_response", "Generation provider returned no answer text.")

    def stream(self, messages: list[GenerationMessage], *, max_output_tokens: int | None = None) -> Iterator[str]:
        output_limit = self._max_output_tokens if max_output_tokens is None else max_output_tokens
        if output_limit < 1:
            raise ValueError("max_output_tokens must be >= 1")
        with observe_provider_request(self.provider, "generation_stream"):
            if _normalize_api_key(self._api_key) is None:
                raise ModelProviderError(
                    "generation_provider_not_configured",
                    "OpenAI generation API key is not configured.",
                )
            payload = {
                "model": self.model,
                "input": messages,
                "max_output_tokens": output_limit,
                "stream": True,
            }
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self._api_key}"}
            try:
                if self._client is not None:
                    response_context = self._client.stream(
                        "POST",
                        f"{self._api_base}/responses",
                        json=payload,
                        headers=headers,
                        timeout=self._timeout_seconds,
                    )
                else:
                    response_context = httpx.stream(
                        "POST",
                        f"{self._api_base}/responses",
                        json=payload,
                        headers=headers,
                        timeout=self._timeout_seconds,
                    )
                with response_context as response:
                    if response.is_error:
                        raise ModelProviderError(
                            "generation_provider_error",
                            f"Generation provider returned HTTP {response.status_code}.",
                        )
                    yield from _read_response_stream(response)
            except httpx.RequestError as error:
                logger.error("model_provider_request_failed provider=openai kind=generation_stream error_type=%s", type(error).__name__)
                raise ModelProviderError("generation_provider_unreachable", "Generation provider is unreachable.") from error

    def _post(self, url: str, payload: dict) -> dict:
        if _normalize_api_key(self._api_key) is None:
            raise ModelProviderError(
                "generation_provider_not_configured",
                "OpenAI generation API key is not configured.",
            )
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self._api_key}"}
        try:
            if self._client is not None:
                response = self._client.post(url, json=payload, headers=headers, timeout=self._timeout_seconds)
            else:
                response = httpx.post(url, json=payload, headers=headers, timeout=self._timeout_seconds)
        except httpx.RequestError as error:
            logger.error("model_provider_request_failed provider=openai kind=generation error_type=%s", type(error).__name__)
            raise ModelProviderError("generation_provider_unreachable", "Generation provider is unreachable.") from error
        if response.is_error:
            raise ModelProviderError("generation_provider_error", f"Generation provider returned HTTP {response.status_code}.")
        try:
            data = response.json()
        except ValueError as error:
            raise ModelProviderError("generation_invalid_response", "Generation provider returned invalid JSON.") from error
        if not isinstance(data, dict):
            raise ModelProviderError("generation_invalid_response", "Generation provider returned an invalid payload.")
        return data


def get_embedding_provider() -> EmbeddingProvider:
    profile = _profile_for("embedding")
    if profile.provider == "openai":
        return _attach_profile(
            OpenAIEmbeddingProvider(
                model=settings.embedding_model,
                dimensions=settings.embedding_dimensions,
                version=settings.embedding_version,
                api_key=settings.openai_api_key,
                api_base=settings.openai_api_base,
                timeout_seconds=settings.embedding_timeout_seconds,
            ),
            profile,
        )
    return _attach_profile(
        OllamaEmbeddingProvider(
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            version=settings.embedding_version,
            base_url=settings.ollama_base_url,
            query_instruction=settings.embedding_query_instruction,
            timeout_seconds=settings.embedding_timeout_seconds,
        ),
        profile,
    )


class DeepSeekGenerationProvider:
    provider = "deepseek"

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        api_base: str,
        timeout_seconds: float,
        max_output_tokens: int,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self._api_key = _normalize_api_key(api_key)
        self._api_base = _normalize_deepseek_base(api_base)
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens
        self._client = client
        self.config_fingerprint = ""

    def generate(self, messages: list[GenerationMessage], *, max_output_tokens: int | None = None) -> str:
        output_limit = self._max_output_tokens if max_output_tokens is None else max_output_tokens
        if output_limit < 1:
            raise ValueError("max_output_tokens must be >= 1")
        with observe_provider_request(self.provider, "generation"):
            if _normalize_api_key(self._api_key) is None:
                raise ModelProviderError(
                    "generation_provider_not_configured",
                    "DeepSeek generation API key is not configured.",
                )
            response = self._post(
                f"{self._api_base}/messages",
                self._build_payload(messages, max_output_tokens=output_limit),
            )
            stop_reason = response.get("stop_reason")
            if stop_reason not in {"end_turn", "stop_sequence"}:
                raise ModelProviderError(
                    "research_provider_output_incomplete",
                    "Generation provider did not prove that the response completed.",
                )
            content = response.get("content")
            if not isinstance(content, list) or not content:
                raise ModelProviderError("generation_invalid_response", "Generation provider returned no content blocks.")
            text = _extract_anthropic_text(content)
            if not text:
                raise ModelProviderError("generation_invalid_response", "Generation provider returned no answer text.")
            return text

    def stream(self, messages: list[GenerationMessage], *, max_output_tokens: int | None = None) -> Iterator[str]:
        output_limit = self._max_output_tokens if max_output_tokens is None else max_output_tokens
        if output_limit < 1:
            raise ValueError("max_output_tokens must be >= 1")
        with observe_provider_request(self.provider, "generation_stream"):
            if _normalize_api_key(self._api_key) is None:
                raise ModelProviderError(
                    "generation_provider_not_configured",
                    "DeepSeek generation API key is not configured.",
                )
            payload = self._build_payload(messages, max_output_tokens=output_limit)
            payload["stream"] = True
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
            }
            try:
                if self._client is not None:
                    response_context = self._client.stream(
                        "POST",
                        f"{self._api_base}/messages",
                        json=payload,
                        headers=headers,
                        timeout=self._timeout_seconds,
                    )
                else:
                    response_context = httpx.stream(
                        "POST",
                        f"{self._api_base}/messages",
                        json=payload,
                        headers=headers,
                        timeout=self._timeout_seconds,
                    )
                with response_context as response:
                    if response.is_error:
                        raise ModelProviderError(
                            "generation_provider_error",
                            f"Generation provider returned HTTP {response.status_code}.",
                        )
                    yield from _read_anthropic_response_stream(response)
            except httpx.RequestError as error:
                logger.error("model_provider_request_failed provider=deepseek kind=generation_stream error_type=%s", type(error).__name__)
                raise ModelProviderError("generation_provider_unreachable", "Generation provider is unreachable.") from error

    def _build_payload(self, messages: list[GenerationMessage], *, max_output_tokens: int | None = None) -> dict:
        system_text, conversation = _split_deepseek_system_and_messages(messages)
        payload: dict[str, object] = {
            "model": self.model,
            "messages": _map_messages_for_deepseek_anthropic(conversation),
            "max_tokens": self._max_output_tokens if max_output_tokens is None else max_output_tokens,
        }
        if system_text:
            payload["system"] = system_text
        return payload

    def _post(self, url: str, payload: dict) -> dict:
        if _normalize_api_key(self._api_key) is None:
            raise ModelProviderError(
                "generation_provider_not_configured",
                "DeepSeek generation API key is not configured.",
            )
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
        }
        try:
            if self._client is not None:
                response = self._client.post(url, json=payload, headers=headers, timeout=self._timeout_seconds)
            else:
                response = httpx.post(url, json=payload, headers=headers, timeout=self._timeout_seconds)
        except httpx.RequestError as error:
            logger.error("model_provider_request_failed provider=deepseek kind=generation error_type=%s", type(error).__name__)
            raise ModelProviderError("generation_provider_unreachable", "Generation provider is unreachable.") from error
        if response.is_error:
            raise ModelProviderError("generation_provider_error", f"Generation provider returned HTTP {response.status_code}.")
        try:
            data = response.json()
        except ValueError as error:
            raise ModelProviderError("generation_invalid_response", "Generation provider returned invalid JSON.") from error
        if not isinstance(data, dict):
            raise ModelProviderError("generation_invalid_response", "Generation provider returned an invalid payload.")
        return data


def get_generation_provider() -> GenerationProvider:
    profile = _profile_for("generation")
    if profile.provider == "deepseek":
        return _attach_profile(
            DeepSeekGenerationProvider(
                model=settings.generation_model,
                api_key=settings.deepseek_api_key,
                api_base=settings.deepseek_api_base,
                timeout_seconds=settings.generation_timeout_seconds,
                max_output_tokens=settings.generation_max_output_tokens,
            ),
            profile,
        )
    return _attach_profile(
        OpenAIGenerationProvider(
            model=settings.generation_model,
            api_key=settings.openai_api_key,
            api_base=settings.openai_api_base,
            timeout_seconds=settings.generation_timeout_seconds,
            max_output_tokens=settings.generation_max_output_tokens,
        ),
        profile,
    )


ProviderT = TypeVar("ProviderT")


def _profile_for(capability: Literal["generation", "embedding", "vision"]) -> CapabilityProfile:
    try:
        return build_capability_registry().resolve(capability)
    except CapabilityUnavailableError as error:
        raise ModelProviderError(error.code, error.message) from error


def _attach_profile(provider: ProviderT, profile: CapabilityProfile) -> ProviderT:
    setattr(provider, "config_fingerprint", profile.config_fingerprint)
    setattr(provider, "capability_profile", profile)
    return provider


def _validate_dimensions(vectors: list[list[float]], dimensions: int) -> None:
    if any(len(vector) != dimensions for vector in vectors):
        raise ModelProviderError(
            "embedding_dimension_mismatch",
            f"Embedding provider returned a vector with dimensions other than {dimensions}.",
        )


def _normalize_api_key(api_key: str | None) -> str | None:
    """Treat None/empty/whitespace-only provider secrets as missing before HTTP."""

    if api_key is None:
        return None
    stripped = api_key.strip()
    return stripped or None


def _normalize_openai_base(api_base: str) -> str:
    from ai_pdf_api.services.capabilities import normalize_provider_endpoint

    normalized = normalize_provider_endpoint(api_base, provider="openai")
    if normalized:
        return normalized
    base = api_base.rstrip("/")
    path = urlsplit(base).path.rstrip("/")
    return base if path.endswith("/v1") else f"{base}/v1"


def _read_response_stream(response: httpx.Response) -> Iterator[str]:
    completed = False
    for line in response.iter_lines():
        if not line or not line.startswith("data:"):
            continue
        raw_data = line[5:].strip()
        if raw_data == "[DONE]":
            break
        try:
            event = json.loads(raw_data)
        except json.JSONDecodeError as error:
            raise ModelProviderError("generation_invalid_response", "Generation provider returned invalid stream data.") from error
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        if event_type in {"response.failed", "error"}:
            raise ModelProviderError("generation_provider_error", "Generation provider reported a streaming error.")
        if event_type == "response.incomplete":
            raise ModelProviderError(
                "research_provider_output_incomplete",
                "Generation provider reported an incomplete streaming response.",
            )
        if event_type == "response.completed":
            response_data = event.get("response")
            if isinstance(response_data, dict) and response_data.get("status") not in {None, "completed"}:
                raise ModelProviderError(
                    "research_provider_output_incomplete",
                    "Generation provider did not prove that the response completed.",
                )
            completed = True
            continue
        if event_type == "response.output_text.delta":
            delta = event.get("delta")
            if isinstance(delta, str) and delta:
                yield delta
    if not completed:
        raise ModelProviderError(
            "research_provider_output_incomplete",
            "Generation provider did not prove that the response completed.",
        )


def _normalize_deepseek_base(api_base: str) -> str:
    """Return the canonical DeepSeek Anthropic-compatible API base URL.

    The real endpoint is https://api.deepseek.com/anthropic/v1/messages.
    This function normalises a user-supplied base so callers always append
    ``/messages`` onto a URL ending with ``/anthropic/v1``.
    """
    from ai_pdf_api.services.capabilities import normalize_provider_endpoint

    normalized = normalize_provider_endpoint(api_base, provider="deepseek")
    if normalized:
        return normalized
    base = api_base.rstrip("/")
    parts = urlsplit(base)
    path = parts.path.rstrip("/")
    if path.endswith("/anthropic/v1"):
        pass
    elif path.endswith("/anthropic"):
        path = f"{path}/v1"
    elif path.endswith("/v1"):
        path = f"{path[:-len('/v1')]}/anthropic/v1"
    else:
        path = f"{path}/anthropic/v1"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))



def _split_deepseek_system_and_messages(
    messages: list[GenerationMessage],
) -> tuple[str | None, list[GenerationMessage]]:
    """Extract Chat-style system messages into Anthropic top-level system text.

    Anthropic Messages does not accept role=system inside messages. Production
    Chat builds [system, ...user/assistant history, user]. Multiple system
    messages are merged in order; empty system text is omitted.
    """

    system_parts: list[str] = []
    conversation: list[GenerationMessage] = []
    for message in messages:
        if not isinstance(message, dict):
            raise ModelProviderError(
                "generation_input_unsupported",
                "DeepSeek generation requires dict messages.",
            )
        role = message.get("role")
        if role == "system":
            text_value = _extract_deepseek_system_text(message.get("content"))
            if text_value:
                system_parts.append(text_value)
            continue
        if role not in {"user", "assistant"}:
            raise ModelProviderError(
                "generation_input_unsupported",
                f"DeepSeek generation does not support message role {role!r}.",
            )
        conversation.append(message)
    system_text = "\n\n".join(system_parts).strip()
    return (system_text or None, conversation)


def _extract_deepseek_system_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        raise ModelProviderError(
            "generation_input_unsupported",
            "DeepSeek system content must be a string or text content-part list.",
        )
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            raise ModelProviderError(
                "generation_input_unsupported",
                "DeepSeek system content parts must be objects.",
            )
        part_type = item.get("type")
        if part_type in {"text", "input_text"}:
            text_value = item.get("text")
            if not isinstance(text_value, str):
                raise ModelProviderError(
                    "generation_input_unsupported",
                    "DeepSeek system text parts require string text.",
                )
            if text_value.strip():
                parts.append(text_value.strip())
            continue
        raise ModelProviderError(
            "generation_input_unsupported",
            f"DeepSeek system content does not support part type {part_type!r}.",
        )
    return "\n".join(parts).strip()


def _map_messages_for_deepseek_anthropic(messages: list[GenerationMessage]) -> list[dict[str, object]]:
    mapped: list[dict[str, object]] = []
    for message in messages:
        if not isinstance(message, dict):
            raise ModelProviderError(
                "generation_input_unsupported",
                "DeepSeek generation requires dict messages.",
            )
        role = message.get("role")
        if role not in {"user", "assistant"}:
            raise ModelProviderError(
                "generation_input_unsupported",
                f"DeepSeek generation messages only accept user/assistant roles, not {role!r}.",
            )
        content = message.get("content")
        mapped_message: dict[str, object] = {
            key: value for key, value in message.items() if key != "content"
        }
        mapped_message["role"] = role
        mapped_message["content"] = _map_deepseek_content(content)
        mapped.append(mapped_message)
    return mapped


def _map_deepseek_content(content: object) -> object:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        raise ModelProviderError(
            "generation_input_unsupported",
            "DeepSeek generation content must be a string or content-part list.",
        )
    parts: list[dict[str, object]] = []
    for item in content:
        if not isinstance(item, dict):
            raise ModelProviderError(
                "generation_input_unsupported",
                "DeepSeek generation content parts must be objects.",
            )
        part_type = item.get("type")
        if part_type in {"text", "input_text"}:
            text_value = item.get("text")
            if not isinstance(text_value, str):
                raise ModelProviderError(
                    "generation_input_unsupported",
                    "DeepSeek text parts require string text.",
                )
            parts.append({"type": "text", "text": text_value})
            continue
        if part_type in {"image", "input_image"}:
            parts.append(_map_deepseek_image_part(item))
            continue
        raise ModelProviderError(
            "generation_input_unsupported",
            f"DeepSeek generation does not support content part type {part_type!r}.",
        )
    return parts


def _map_deepseek_image_part(item: dict[str, object]) -> dict[str, object]:
    # Already Anthropic-shaped image part.
    source = item.get("source")
    if isinstance(source, dict) and source.get("type") == "base64":
        media_type = source.get("media_type")
        data = source.get("data")
        if isinstance(media_type, str) and isinstance(data, str) and media_type and data:
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": data,
                },
            }
        raise ModelProviderError(
            "generation_input_unsupported",
            "DeepSeek Anthropic image source requires media_type and base64 data.",
        )

    image_url = item.get("image_url")
    if isinstance(image_url, dict):
        image_url = image_url.get("url")
    if not isinstance(image_url, str) or not image_url:
        raise ModelProviderError(
            "generation_input_unsupported",
            "DeepSeek image parts require a data:image base64 URL or Anthropic base64 source.",
        )
    if not image_url.startswith("data:image/") or ";base64," not in image_url:
        raise ModelProviderError(
            "generation_input_unsupported",
            "DeepSeek image parts only support data:image/*;base64 URLs.",
        )
    header, _, data = image_url.partition(",")
    media_type = header[len("data:") :].split(";", 1)[0]
    if not media_type.startswith("image/") or not data:
        raise ModelProviderError(
            "generation_input_unsupported",
            "DeepSeek image parts require a non-empty image/* base64 payload.",
        )
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": data,
        },
    }


def _extract_anthropic_text(content_blocks: list[object]) -> str:
    parts: list[str] = []
    for block in content_blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts).strip()


def _read_anthropic_response_stream(response: httpx.Response) -> Iterator[str]:
    completed = False
    for line in response.iter_lines():
        if not line or not line.startswith("data:"):
            continue
        raw_data = line[5:].strip()
        if raw_data == "[DONE]":
            break
        try:
            event = json.loads(raw_data)
        except json.JSONDecodeError as error:
            raise ModelProviderError("generation_invalid_response", "Generation provider returned invalid stream data.") from error
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        if event_type in {"error"}:
            raise ModelProviderError("generation_provider_error", "Generation provider reported a streaming error.")
        if event_type == "message_stop":
            stop_reason = event.get("stop_reason")
            if stop_reason not in {"end_turn", "stop_sequence"}:
                raise ModelProviderError(
                    "research_provider_output_incomplete",
                    "Generation provider did not prove that the response completed.",
                )
            completed = True
            continue
        if event_type == "content_block_delta":
            delta = event.get("delta")
            if isinstance(delta, dict) and delta.get("type") == "text_delta":
                text = delta.get("text")
                if isinstance(text, str) and text:
                    yield text
    if not completed:
        raise ModelProviderError(
            "research_provider_output_incomplete",
            "Generation provider did not prove that the response completed.",
        )
