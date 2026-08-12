import httpx
import pytest
from prometheus_client import generate_latest

from ai_pdf_api.core.metrics import PROVIDER_REQUESTS
from ai_pdf_api.modalities.image_caption import OpenAIImageCaptionProvider
from ai_pdf_api.services.providers import (
    DeepSeekGenerationProvider,
    ModelProviderError,
    OpenAIEmbeddingProvider,
    OpenAIGenerationProvider,
    _normalize_deepseek_base,
)


def test_openai_embedding_provider_batches_and_validates_dimensions() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = request.read()
        requests.append({"url": str(request.url), "body": payload})
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0, 0.0]},
                    {"index": 0, "embedding": [1.0, 0.0, 0.0]},
                ]
            },
        )

    provider = OpenAIEmbeddingProvider(
        model="text-embedding-3-small",
        dimensions=3,
        version="test-v1",
        api_key="test-key",
        api_base="https://example.test/v1",
        timeout_seconds=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    vectors = provider.embed_documents(["first", "second"])

    assert vectors == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    assert requests[0]["url"] == "https://example.test/v1/embeddings"


def test_openai_embedding_provider_rejects_invalid_indexes() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 0, "embedding": [1.0, 0.0, 0.0]},
                    {"index": 0, "embedding": [0.0, 1.0, 0.0]},
                ]
            },
        )

    provider = OpenAIEmbeddingProvider(
        model="text-embedding-3-small",
        dimensions=3,
        version="test-v1",
        api_key="test-key",
        api_base="https://example.test/v1",
        timeout_seconds=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ModelProviderError, match="invalid vector indexes"):
        provider.embed_documents(["first", "second"])


def test_openai_embedding_provider_requires_key() -> None:
    provider = OpenAIEmbeddingProvider(
        model="text-embedding-3-small",
        dimensions=3,
        version="test-v1",
        api_key=None,
        api_base="https://example.test/v1",
        timeout_seconds=2,
    )

    with pytest.raises(ModelProviderError, match="not configured") as captured:
        provider.embed_query("question")
    assert captured.value.code == "embedding_provider_not_configured"


@pytest.mark.parametrize("missing_key", [None, "", "   ", "\t\n"])
def test_openai_embedding_blank_or_whitespace_key_fails_before_http(
    missing_key: str | None,
) -> None:
    http_calls: list[str] = []

    def reject_http(*_args, **_kwargs):  # noqa: ANN002, ANN003
        http_calls.append("called")
        raise AssertionError("blank embedding key must not call provider HTTP")

    provider = OpenAIEmbeddingProvider(
        model="text-embedding-3-small",
        dimensions=3,
        version="test-v1",
        api_key=missing_key,
        api_base="https://example.test/v1",
        timeout_seconds=2,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: (_ for _ in ()).throw(AssertionError("no HTTP"))
            )
        ),
    )
    # Factories remain startable; failure is method preflight before HTTP.
    with pytest.raises(ModelProviderError) as captured:
        provider.embed_query("question")
    assert captured.value.code == "embedding_provider_not_configured"
    if missing_key:
        assert missing_key not in captured.value.message
    assert http_calls == []


def test_openai_generation_provider_reads_responses_output_text() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.read())
        return httpx.Response(200, json={"status": "completed", "output_text": "answer from provider"})

    provider = OpenAIGenerationProvider(
        model="gpt-5.5",
        api_key="test-key",
        api_base="https://example.test/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert provider.generate(
        [{"role": "user", "content": "question"}], max_output_tokens=77
    ) == "answer from provider"
    assert requests[0].decode() == (
        '{"model":"gpt-5.5","input":[{"role":"user","content":"question"}],'
        '"max_output_tokens":77}'
    )


def test_openai_generation_provider_preserves_multimodal_message_parts() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.read())
        return httpx.Response(200, json={"status": "completed", "output_text": "visual answer"})

    provider = OpenAIGenerationProvider(
        model="gpt-5.5",
        api_key="test-key",
        api_base="https://example.test/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Analyze this region."},
                {
                    "type": "input_image",
                    "image_url": "data:image/png;base64,Y3JvcHBlZC1wbmc=",
                    "detail": "high",
                },
            ],
        }
    ]

    assert provider.generate(messages) == "visual answer"
    payload = httpx.Response(200, content=requests[0]).json()
    assert payload["input"] == messages


def test_openai_image_caption_provider_sends_canonical_png_as_responses_image_input() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append({"url": str(request.url), "body": request.read().decode()})
        return httpx.Response(200, json={"output_text": "Visible chart caption."})

    provider = OpenAIImageCaptionProvider(
        model="gpt-5.5",
        version="image-caption-v1",
        detail="high",
        api_key="test-key",
        api_base="https://example.test/v1",
        timeout_seconds=2,
        max_output_tokens=320,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    caption = provider.caption(b"canonical-png", content_type="image/png")

    assert caption == "Visible chart caption."
    assert requests[0]["url"] == "https://example.test/v1/responses"
    assert '"type":"input_text"' in requests[0]["body"]
    assert '"type":"input_image"' in requests[0]["body"]
    assert '"image_url":"data:image/png;base64,Y2Fub25pY2FsLXBuZw=="' in requests[0]["body"]
    assert '"detail":"high"' in requests[0]["body"]


def test_openai_image_caption_provider_rejects_invalid_input_and_empty_output() -> None:
    provider = OpenAIImageCaptionProvider(
        model="gpt-5.5",
        version="image-caption-v1",
        detail="high",
        api_key="test-key",
        api_base="https://example.test/v1",
        timeout_seconds=2,
        max_output_tokens=320,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json={"output": [{"content": []}]})
            )
        ),
    )

    with pytest.raises(ModelProviderError) as invalid_input:
        provider.caption(b"jpeg", content_type="image/jpeg")
    assert invalid_input.value.code == "image_caption_input_invalid"

    with pytest.raises(ModelProviderError) as empty_output:
        provider.caption(b"png", content_type="image/png")
    assert empty_output.value.code == "image_caption_invalid_response"


def test_openai_generation_provider_streams_response_text_deltas() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.read())
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                'event: response.output_text.delta\n'
                'data: {"type":"response.output_text.delta","delta":"first"}\n\n'
                'data: {"type":"response.output_text.delta","delta":" second"}\n\n'
                'data: {"type":"response.completed","response":{"status":"completed"}}\n\n'
            ).encode(),
        )

    provider = OpenAIGenerationProvider(
        model="gpt-5.5",
        api_key="test-key",
        api_base="https://example.test/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert list(
        provider.stream(
            [{"role": "user", "content": "question"}], max_output_tokens=77
        )
    ) == ["first", " second"]
    stream_payload = httpx.Response(200, content=requests[0]).json()
    assert stream_payload["max_output_tokens"] == 77
    assert stream_payload["stream"] is True


def test_openai_generation_provider_records_cancelled_stream() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                'data: {"type":"response.output_text.delta","delta":"first"}\n\n'
                'data: {"type":"response.output_text.delta","delta":"second"}\n\n'
                'data: {"type":"response.completed"}\n\n'
            ).encode(),
        )

    provider = OpenAIGenerationProvider(
        model="gpt-5.5",
        api_key="test-key",
        api_base="https://cancelled-provider.test/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    cancelled = PROVIDER_REQUESTS.labels(
        provider="openai", kind="generation_stream", outcome="cancelled"
    )
    success = PROVIDER_REQUESTS.labels(
        provider="openai", kind="generation_stream", outcome="success"
    )
    before_cancelled = cancelled._value.get()
    before_success = success._value.get()

    stream = provider.stream([{"role": "user", "content": "question"}])
    assert next(stream) == "first"
    stream.close()

    assert cancelled._value.get() == before_cancelled + 1
    assert success._value.get() == before_success


def test_openai_generation_stream_requires_completion_event() -> None:
    provider = OpenAIGenerationProvider(
        model="gpt-5.5",
        api_key="test-key",
        api_base="https://example.test/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content=b'data: {"type":"response.output_text.delta","delta":"partial"}\n\n',
                )
            )
        ),
    )
    with pytest.raises(ModelProviderError) as error:
        list(provider.stream([{"role": "user", "content": "question"}]))
    assert error.value.code == "research_provider_output_incomplete"


def test_openai_generation_provider_rejects_null_content_items() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "completed", "output": [{"content": None}]})

    provider = OpenAIGenerationProvider(
        model="gpt-5.5",
        api_key="test-key",
        api_base="https://example.test/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ModelProviderError, match="no answer text"):
        provider.generate([{"role": "user", "content": "question"}])


def test_openai_generation_provider_requires_completion_metadata() -> None:
    provider = OpenAIGenerationProvider(
        model="gpt-5.5",
        api_key="test-key",
        api_base="https://example.test/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"output_text": "answer"})
        )),
    )
    with pytest.raises(ModelProviderError) as error:
        provider.generate([{"role": "user", "content": "question"}])
    assert error.value.code == "research_provider_output_incomplete"


def test_deepseek_generation_provider_requires_completion_metadata() -> None:
    provider = DeepSeekGenerationProvider(
        model="deepseek-chat",
        api_key="sk-test-key",
        api_base="https://api.deepseek.com/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"content": [{"type": "text", "text": "answer"}]})
        )),
    )
    with pytest.raises(ModelProviderError) as error:
        provider.generate([{"role": "user", "content": "question"}])
    assert error.value.code == "research_provider_output_incomplete"


def test_provider_metrics_record_business_success_and_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "completed", "output_text": "answer"})

    provider = OpenAIGenerationProvider(
        model="gpt-5.5",
        api_key="test-key",
        api_base="https://metrics-provider.test/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    missing_key_provider = OpenAIGenerationProvider(
        model="gpt-5.5",
        api_key=None,
        api_base="https://metrics-provider.test/v1",
        timeout_seconds=2,
        max_output_tokens=100,
    )

    success = PROVIDER_REQUESTS.labels(provider="openai", kind="generation", outcome="success")
    error = PROVIDER_REQUESTS.labels(provider="openai", kind="generation", outcome="error")
    before_success = success._value.get()
    before_error = error._value.get()

    assert provider.generate([{"role": "user", "content": "question"}]) == "answer"
    with pytest.raises(ModelProviderError):
        missing_key_provider.generate([{"role": "user", "content": "question"}])

    assert success._value.get() == before_success + 1
    assert error._value.get() == before_error + 1
    assert 'ai_pdf_provider_request_duration_seconds_bucket{kind="generation",le="120.0",provider="openai"}' in generate_latest().decode()


# -- DeepSeek generation provider tests --


class TestDeepSeekBaseNormalization:
    def test_plain_base_adds_anthropic_v1(self) -> None:
        assert _normalize_deepseek_base("https://api.deepseek.com") == "https://api.deepseek.com/anthropic/v1"

    def test_anthropic_suffix_adds_v1(self) -> None:
        assert _normalize_deepseek_base("https://api.deepseek.com/anthropic") == "https://api.deepseek.com/anthropic/v1"

    def test_preserves_already_normalized_anthropic_v1(self) -> None:
        assert _normalize_deepseek_base("https://api.deepseek.com/anthropic/v1") == "https://api.deepseek.com/anthropic/v1"

    def test_plain_v1_rewrites_to_anthropic_v1(self) -> None:
        """A bare /v1 refers to the OpenAI‑compatible endpoint; it must be
        rewritten to the Anthropic‑compatible /anthropic/v1."""
        assert _normalize_deepseek_base("https://api.deepseek.com/v1") == "https://api.deepseek.com/anthropic/v1"

    def test_handles_trailing_slash(self) -> None:
        assert _normalize_deepseek_base("https://api.deepseek.com/") == "https://api.deepseek.com/anthropic/v1"

    def test_anthropic_v1_trailing_slash(self) -> None:
        assert _normalize_deepseek_base("https://api.deepseek.com/anthropic/v1/") == "https://api.deepseek.com/anthropic/v1"


def test_deepseek_generation_provider_sends_correct_headers_and_payload() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            {
                "url": str(request.url),
                "headers": dict(request.headers),
                "body": request.read(),
            }
        )
        return httpx.Response(
            200,
            json={"stop_reason": "end_turn", "content": [{"type": "text", "text": "DeepSeek answer"}]},
        )

    provider = DeepSeekGenerationProvider(
        model="deepseek-chat",
        api_key="sk-test-deepseek-key",
        api_base="https://api.deepseek.com/v1",
        timeout_seconds=2,
        max_output_tokens=200,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert provider.generate(
        [{"role": "user", "content": "hello"}], max_output_tokens=77
    ) == "DeepSeek answer"

    assert len(requests) == 1
    assert requests[0]["url"] == "https://api.deepseek.com/anthropic/v1/messages"
    assert requests[0]["headers"]["x-api-key"] == "sk-test-deepseek-key"
    assert requests[0]["headers"]["anthropic-version"] == "2023-06-01"
    payload = httpx.Response(200, content=requests[0]["body"]).json()
    assert payload["model"] == "deepseek-chat"
    assert payload["messages"] == [{"role": "user", "content": "hello"}]
    assert payload["max_tokens"] == 77
    assert "stream" not in payload


def test_deepseek_generation_provider_preserves_multimodal_message_parts() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.read())
        return httpx.Response(
            200,
            json={"stop_reason": "end_turn", "content": [{"type": "text", "text": "visual answer"}]},
        )

    provider = DeepSeekGenerationProvider(
        model="deepseek-chat",
        api_key="sk-test-key",
        api_base="https://api.deepseek.com/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Analyze this region."},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": "Y3JvcHBlZC1wbmc=",
                    },
                },
            ],
        }
    ]

    assert provider.generate(messages) == "visual answer"
    payload = httpx.Response(200, content=requests[0]).json()
    assert payload["messages"] == messages






def test_deepseek_generation_provider_extracts_chat_system_messages() -> None:
    """Chat-shaped [system, history, user] becomes top-level system + user/assistant messages."""

    requests: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.read())
        return httpx.Response(
            200,
            json={"stop_reason": "end_turn", "content": [{"type": "text", "text": "chat answer"}]},
        )

    provider = DeepSeekGenerationProvider(
        model="deepseek-chat",
        api_key="sk-test-key",
        api_base="https://api.deepseek.com/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    messages = [
        {"role": "system", "content": "You are a careful research assistant."},
        {"role": "system", "content": "Prefer citations from the provided evidence."},
        {"role": "user", "content": "Earlier question"},
        {"role": "assistant", "content": "Earlier answer"},
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "What changed after release three?"},
                {
                    "type": "input_image",
                    "image_url": "data:image/png;base64,Y3JvcHBlZC1wbmc=",
                },
            ],
        },
    ]
    assert provider.generate(messages) == "chat answer"
    payload = httpx.Response(200, content=requests[0]).json()
    assert payload["system"] == (
        "You are a careful research assistant.\n\nPrefer citations from the provided evidence."
    )
    assert all(message["role"] in {"user", "assistant"} for message in payload["messages"])
    assert not any(message.get("role") == "system" for message in payload["messages"])
    assert payload["messages"][0] == {"role": "user", "content": "Earlier question"}
    assert payload["messages"][1] == {"role": "assistant", "content": "Earlier answer"}
    assert payload["messages"][2]["role"] == "user"
    assert payload["messages"][2]["content"] == [
        {"type": "text", "text": "What changed after release three?"},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": "Y3JvcHBlZC1wbmc=",
            },
        },
    ]
    assert "system" in payload

    # No system messages: omit top-level system field entirely.
    requests.clear()
    assert provider.generate([{"role": "user", "content": "hello"}]) == "chat answer"
    no_system_payload = httpx.Response(200, content=requests[0]).json()
    assert "system" not in no_system_payload
    assert no_system_payload["messages"] == [{"role": "user", "content": "hello"}]

    # Unsupported remote image URL still fails closed before HTTP.
    requests.clear()
    with pytest.raises(ModelProviderError) as unsupported:
        provider.generate(
            [
                {"role": "system", "content": "Guard"},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_image",
                            "image_url": "https://example.com/image.png",
                        }
                    ],
                },
            ]
        )
    assert unsupported.value.code == "generation_input_unsupported"
    assert requests == []


def test_deepseek_generation_provider_maps_openai_image_parts() -> None:
    requests: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.read())
        return httpx.Response(
            200,
            json={"stop_reason": "end_turn", "content": [{"type": "text", "text": "mapped"}]},
        )

    provider = DeepSeekGenerationProvider(
        model="deepseek-chat",
        api_key="sk-test-key",
        api_base="https://api.deepseek.com/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Describe"},
                {
                    "type": "input_image",
                    "image_url": "data:image/png;base64,Y3JvcHBlZC1wbmc=",
                },
            ],
        }
    ]
    assert provider.generate(messages) == "mapped"
    payload = httpx.Response(200, content=requests[0]).json()
    assert payload["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe"},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": "Y3JvcHBlZC1wbmc=",
                    },
                },
            ],
        }
    ]

    with pytest.raises(ModelProviderError) as unsupported:
        provider.generate(
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_image",
                            "image_url": "https://example.com/image.png",
                        }
                    ],
                }
            ]
        )
    assert unsupported.value.code == "generation_input_unsupported"


def test_deepseek_generation_provider_streams_text_deltas() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.read())
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello"}}\n\n'
                'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":" world"}}\n\n'
                'data: {"type":"message_stop","stop_reason":"end_turn"}\n\n'
            ).encode(),
        )

    provider = DeepSeekGenerationProvider(
        model="deepseek-chat",
        api_key="sk-test-key",
        api_base="https://api.deepseek.com/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert list(
        provider.stream(
            [{"role": "user", "content": "hello"}], max_output_tokens=77
        )
    ) == ["Hello", " world"]
    stream_payload = httpx.Response(200, content=requests[0]).json()
    assert stream_payload["max_tokens"] == 77
    assert stream_payload["stream"] is True


def test_deepseek_generation_stream_requires_message_stop() -> None:
    provider = DeepSeekGenerationProvider(
        model="deepseek-chat",
        api_key="sk-test-key",
        api_base="https://api.deepseek.com/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content=(
                        b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"partial"}}\n\n'
                    ),
                )
            )
        ),
    )
    with pytest.raises(ModelProviderError) as error:
        list(provider.stream([{"role": "user", "content": "hello"}]))
    assert error.value.code == "research_provider_output_incomplete"


def test_deepseek_generation_provider_rejects_empty_content() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"stop_reason": "end_turn", "content": []})

    provider = DeepSeekGenerationProvider(
        model="deepseek-chat",
        api_key="sk-test-key",
        api_base="https://api.deepseek.com/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ModelProviderError, match="no content blocks"):
        provider.generate([{"role": "user", "content": "hello"}])


def test_deepseek_generation_provider_rejects_missing_content_key() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "msg_123", "stop_reason": "end_turn"})

    provider = DeepSeekGenerationProvider(
        model="deepseek-chat",
        api_key="sk-test-key",
        api_base="https://api.deepseek.com/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ModelProviderError, match="no content blocks"):
        provider.generate([{"role": "user", "content": "hello"}])


def test_deepseek_generation_provider_rejects_malformed_json() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    provider = DeepSeekGenerationProvider(
        model="deepseek-chat",
        api_key="sk-test-key",
        api_base="https://api.deepseek.com/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ModelProviderError, match="invalid JSON"):
        provider.generate([{"role": "user", "content": "hello"}])


def test_deepseek_generation_provider_requires_key() -> None:
    provider = DeepSeekGenerationProvider(
        model="deepseek-chat",
        api_key=None,
        api_base="https://api.deepseek.com/v1",
        timeout_seconds=2,
        max_output_tokens=100,
    )

    with pytest.raises(ModelProviderError, match="not configured") as generate_error:
        provider.generate([{"role": "user", "content": "hello"}])
    assert generate_error.value.code == "generation_provider_not_configured"

    with pytest.raises(ModelProviderError, match="not configured") as stream_error:
        list(provider.stream([{"role": "user", "content": "hello"}]))
    assert stream_error.value.code == "generation_provider_not_configured"


@pytest.mark.parametrize("missing_key", [None, "", "   ", "\t\n"])
def test_openai_generation_blank_or_whitespace_key_fails_before_http(
    missing_key: str | None,
) -> None:
    provider = OpenAIGenerationProvider(
        model="gpt-5.5",
        api_key=missing_key,
        api_base="https://example.test/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: (_ for _ in ()).throw(AssertionError("no HTTP"))
            )
        ),
    )
    with pytest.raises(ModelProviderError) as generate_error:
        provider.generate([{"role": "user", "content": "hello"}])
    assert generate_error.value.code == "generation_provider_not_configured"
    with pytest.raises(ModelProviderError) as stream_error:
        list(provider.stream([{"role": "user", "content": "hello"}]))
    assert stream_error.value.code == "generation_provider_not_configured"
    if missing_key:
        assert missing_key not in generate_error.value.message
        assert missing_key not in stream_error.value.message


@pytest.mark.parametrize("missing_key", [None, "", "   ", "\t\n"])
def test_deepseek_generation_blank_or_whitespace_key_fails_before_http(
    missing_key: str | None,
) -> None:
    provider = DeepSeekGenerationProvider(
        model="deepseek-chat",
        api_key=missing_key,
        api_base="https://api.deepseek.com/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: (_ for _ in ()).throw(AssertionError("no HTTP"))
            )
        ),
    )
    with pytest.raises(ModelProviderError) as generate_error:
        provider.generate([{"role": "user", "content": "hello"}])
    assert generate_error.value.code == "generation_provider_not_configured"
    with pytest.raises(ModelProviderError) as stream_error:
        list(provider.stream([{"role": "user", "content": "hello"}]))
    assert stream_error.value.code == "generation_provider_not_configured"
    if missing_key:
        assert missing_key not in generate_error.value.message
        assert missing_key not in stream_error.value.message


def test_deepseek_generation_provider_handles_http_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    provider = DeepSeekGenerationProvider(
        model="deepseek-chat",
        api_key="sk-test-key",
        api_base="https://api.deepseek.com/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ModelProviderError, match="HTTP 500"):
        provider.generate([{"role": "user", "content": "hello"}])


def test_deepseek_generation_provider_handles_stream_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b'data: {"type":"error","error":{"message":"bad request"}}\n\n',
        )

    provider = DeepSeekGenerationProvider(
        model="deepseek-chat",
        api_key="sk-test-key",
        api_base="https://api.deepseek.com/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ModelProviderError, match="streaming error"):
        list(provider.stream([{"role": "user", "content": "hello"}]))


def test_deepseek_provider_metrics_record_success_and_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"stop_reason": "end_turn", "content": [{"type": "text", "text": "answer"}]})

    provider = DeepSeekGenerationProvider(
        model="deepseek-chat",
        api_key="sk-test-key",
        api_base="https://metrics-deepseek.test/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    missing_key_provider = DeepSeekGenerationProvider(
        model="deepseek-chat",
        api_key=None,
        api_base="https://metrics-deepseek.test/v1",
        timeout_seconds=2,
        max_output_tokens=100,
    )

    success = PROVIDER_REQUESTS.labels(provider="deepseek", kind="generation", outcome="success")
    error = PROVIDER_REQUESTS.labels(provider="deepseek", kind="generation", outcome="error")
    before_success = success._value.get()
    before_error = error._value.get()

    assert provider.generate([{"role": "user", "content": "hello"}]) == "answer"
    with pytest.raises(ModelProviderError):
        missing_key_provider.generate([{"role": "user", "content": "hello"}])

    assert success._value.get() == before_success + 1
    assert error._value.get() == before_error + 1
    assert 'ai_pdf_provider_request_duration_seconds_bucket{kind="generation",le="120.0",provider="deepseek"}' in generate_latest().decode()
