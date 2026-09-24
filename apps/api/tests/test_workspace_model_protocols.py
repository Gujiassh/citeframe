import json
from dataclasses import replace

import httpx
import pytest

from ai_pdf_api.services.model_config_types import ModelConnection
from ai_pdf_api.services.providers import ModelProviderError, get_embedding_provider, get_generation_provider
from ai_pdf_api.services import workspace_providers


def connection(protocol="openai_chat_completions", capability="generation"):
    return ModelConnection(capability, "workspace", 1, protocol, "openai", "test-model", "https://fixture.test/custom", "fixture-key", 5)


def client_factory(monkeypatch, handler):
    clients = []
    def factory(base, timeout):
        client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
        clients.append(client)
        return client
    monkeypatch.setattr(workspace_providers, "model_client", factory)
    return clients


@pytest.mark.parametrize("protocol", ["openai_responses", "openai_chat_completions"])
def test_generate_and_stream_exact_base_and_separate_credentials(monkeypatch, protocol):
    requests = []
    def handler(request):
        body = json.loads(request.content)
        requests.append((str(request.url), request.headers["Authorization"], body))
        chat = protocol == "openai_chat_completions"
        if body.get("stream"):
            event = {"choices": [{"index": 0, "delta": {"content": "answer"}, "finish_reason": "stop"}]} if chat else {"type": "response.output_text.delta", "delta": "answer"}
            data = "data: " + json.dumps(event) + "\n\n"
            if not chat:
                data += 'data: {"type":"response.completed","response":{"status":"completed"}}\n\n'
            return httpx.Response(200, text=data + "data: [DONE]\n\n")
        return httpx.Response(200, json={"choices": [{"message": {"content": "answer"}, "finish_reason": "stop"}]} if chat else {"status": "completed", "output_text": "answer"})
    clients = client_factory(monkeypatch, handler)
    a = get_generation_provider(connection(protocol))
    b = get_generation_provider(replace(connection(protocol), api_key="second-key", model="second-model", base_url="https://other.test/path"))
    messages = [{"role": "user", "content": [{"type": "input_text", "text": "question"}, {"type": "input_image", "image_url": "data:image/png;base64,YQ==", "detail": "low"}]}]
    assert a.generate(messages) == "answer"
    assert "".join(b.stream(messages)) == "answer"
    endpoint = "chat/completions" if protocol == "openai_chat_completions" else "responses"
    assert requests[0][0] == "https://fixture.test/custom/" + endpoint
    assert requests[1][0] == "https://other.test/path/" + endpoint
    assert requests[0][1] == "Bearer fixture-key" and requests[1][1] == "Bearer second-key"
    assert requests[1][2]["model"] == "second-model"
    if protocol == "openai_chat_completions":
        assert requests[0][2]["messages"][0]["content"][1] == {"type": "image_url", "image_url": {"url": "data:image/png;base64,YQ==", "detail": "low"}}
    assert all(c.is_closed for c in clients)


@pytest.mark.parametrize("finish", [None, "length", "content_filter", "tool_calls"])
def test_chat_incomplete_never_succeeds(monkeypatch, finish):
    def handler(request):
        body = json.loads(request.content)
        choice = {"message": {"content": "partial"}, "delta": {"content": "partial"}, "finish_reason": finish}
        return httpx.Response(200, text='data: '+json.dumps({"choices": [choice]})+'\n\ndata: [DONE]\n\n') if body.get("stream") else httpx.Response(200, json={"choices": [choice]})
    clients = client_factory(monkeypatch, handler)
    provider = get_generation_provider(connection())
    for call in (lambda: provider.generate([{"role": "user", "content": "q"}]), lambda: list(provider.stream([{"role": "user", "content": "q"}]))):
        with pytest.raises(ModelProviderError) as error:
            call()
        assert error.value.code == "research_provider_output_incomplete"
    assert all(c.is_closed for c in clients)


def test_stream_cancel_closes_client(monkeypatch):
    clients = client_factory(monkeypatch, lambda request: httpx.Response(200, text='data: {"choices":[{"delta":{"content":"first"},"finish_reason":null}]}\n\n'))
    stream = get_generation_provider(connection()).stream([{"role": "user", "content": "q"}])
    assert next(stream) == "first"
    stream.close()
    assert clients[0].is_closed


@pytest.mark.parametrize("dimension,value,code", [(1536, 1, "embedding_dimension_mismatch"), (1024, float("nan"), "embedding_invalid_response"), (1024, True, "embedding_invalid_response")])
def test_embedding_dimensions_and_numbers(monkeypatch, dimension, value, code):
    clients = client_factory(monkeypatch, lambda request: httpx.Response(200, content=json.dumps({"data": [{"index": 0, "embedding": [value]*dimension}]})))
    provider = get_embedding_provider(connection("openai_embeddings", "embedding"))
    with pytest.raises(ModelProviderError) as error:
        provider.embed_query("query")
    assert error.value.code == code
    assert clients[0].is_closed


def test_embedding_response_indexes_are_ordered(monkeypatch):
    def handler(request):
        assert request.url.path == "/custom/embeddings"
        assert json.loads(request.content)["dimensions"] == 1024
        return httpx.Response(200, json={"data": [{"index": 1, "embedding": [2.0]*1024}, {"index": 0, "embedding": [1.0]*1024}]})
    client_factory(monkeypatch, handler)
    vectors = get_embedding_provider(connection("openai_embeddings", "embedding")).embed_documents(["a", "b"])
    assert [v[0] for v in vectors] == [1, 2]
