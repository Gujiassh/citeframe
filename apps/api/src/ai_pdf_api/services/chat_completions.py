import json
import httpx

from ai_pdf_api.services.providers import GenerationMessage, ModelProviderError, OpenAIGenerationProvider


def chat_messages(messages: list[GenerationMessage]) -> list[dict]:
    result = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            converted = []
            for part in content:
                if not isinstance(part, dict):
                    raise ModelProviderError("generation_input_unsupported", "Invalid generation input part.")
                kind = part.get("type")
                if kind in {"input_text", "text"} and isinstance(part.get("text"), str):
                    converted.append({"type": "text", "text": part["text"]})
                elif kind == "input_image" and isinstance(part.get("image_url"), str) and part["image_url"].startswith("data:image/"):
                    image = {"url": part["image_url"]}
                    if part.get("detail") in {"auto", "low", "high"}:
                        image["detail"] = part["detail"]
                    converted.append({"type": "image_url", "image_url": image})
                else:
                    raise ModelProviderError("generation_input_unsupported", "Unsupported generation input part.")
            content = converted
        elif not isinstance(content, str):
            raise ModelProviderError("generation_input_unsupported", "Unsupported generation message.")
        result.append({"role": message["role"], "content": content})
    return result


def _incomplete():
    raise ModelProviderError("research_provider_output_incomplete", "Generation provider did not prove that the response completed.")


class ChatCompletionsProvider(OpenAIGenerationProvider):
    def _payload(self, messages, max_output_tokens, stream=False):
        limit = self._max_output_tokens if max_output_tokens is None else max_output_tokens
        if limit < 1:
            raise ValueError("max_output_tokens must be >= 1")
        return {"model": self.model, "messages": chat_messages(messages), "max_tokens": limit, "stream": stream}

    def generate(self, messages, *, max_output_tokens=None):
        result = self._post(f"{self._api_base}/chat/completions", self._payload(messages, max_output_tokens))
        choices = result.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise ModelProviderError("generation_invalid_response", "Generation provider returned invalid choices.")
        choice = choices[0]
        if choice.get("finish_reason") != "stop":
            _incomplete()
        message = choice.get("message")
        if not isinstance(message, dict) or message.get("tool_calls") or message.get("refusal"):
            _incomplete()
        text = message.get("content")
        if not isinstance(text, str) or not text.strip():
            raise ModelProviderError("generation_invalid_response", "Generation provider returned no answer text.")
        return text.strip()

    def stream(self, messages, *, max_output_tokens=None):
        if not self._api_key:
            raise ModelProviderError("generation_provider_not_configured", "Generation API key is not configured.")
        completed = False
        try:
            with self._client.stream("POST", f"{self._api_base}/chat/completions", json=self._payload(messages, max_output_tokens, True),
                    headers={"Authorization": f"Bearer {self._api_key}"}, timeout=self._timeout_seconds, follow_redirects=False) as response:
                if not response.is_success:
                    raise ModelProviderError("generation_provider_error", f"Generation provider returned HTTP {response.status_code}.")
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        event = json.loads(raw)
                    except ValueError:
                        raise ModelProviderError("generation_invalid_response", "Generation provider returned invalid stream data.") from None
                    if not isinstance(event, dict) or event.get("error"):
                        raise ModelProviderError("generation_provider_error", "Generation provider reported a streaming error.")
                    choices = event.get("choices")
                    if not isinstance(choices, list):
                        raise ModelProviderError("generation_invalid_response", "Generation provider returned invalid stream choices.")
                    for choice in choices:
                        if not isinstance(choice, dict) or choice.get("index", 0) != 0:
                            raise ModelProviderError("generation_invalid_response", "Generation provider returned unexpected stream choices.")
                        delta = choice.get("delta", {})
                        if not isinstance(delta, dict) or delta.get("tool_calls") or delta.get("refusal"):
                            _incomplete()
                        reason = choice.get("finish_reason")
                        if reason is not None:
                            if reason != "stop":
                                _incomplete()
                            completed = True
                        text = delta.get("content")
                        if isinstance(text, str) and text:
                            yield text
                if not completed:
                    _incomplete()
        except httpx.RequestError:
            raise ModelProviderError("generation_provider_unreachable", "Generation provider is unreachable.") from None
