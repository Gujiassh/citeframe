from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic, sleep
from typing import Protocol
from urllib.parse import urlsplit

import httpx
from ai_pdf_api.services.providers import (
    GenerationMessage,
    ModelProviderError,
)
from ai_pdf_api.services.research_prompt_provenance import (
    PROMPT_NODE_ORDER,
    V2_PROMPT_SPECS,
    V2_PROMPT_VERSION_IDS,
    V2_RELEASE_ID,
    V2_WORKFLOW_VERSION_ID,
)

from ai_pdf_worker.r803_evaluation_contract import (
    EvaluationPackage,
    ProviderCallRecord,
    canonical_sha256,
)
from ai_pdf_worker.r803_evaluation_policy import (
    MAX_PROVIDER_ATTEMPTS,
    RETRY_BACKOFF_SECONDS,
    RETRY_POLICY_VERSION,
    RETRYABLE_PROVIDER_CODES,
)
from ai_pdf_worker.r803_structured_output import (
    PROMPT_RESULT_SCHEMA_NODES,
    PROVIDER_RESULT_SCHEMAS,
    QUICK_RESULT_SCHEMA,
    QUICK_RESULT_SCHEMA_VERSION,
    STRUCTURED_OUTPUT_SCHEMA_SET_VERSION,
    STRUCTURED_OUTPUT_TRANSPORT_VERSION,
    structured_output_format,
)
from ai_pdf_worker.research_agent_schemas import (
    AGENT_RESULT_SCHEMA_VERSION,
    AGENT_RESULT_SCHEMAS,
)
from ai_pdf_worker.research_executor import (
    ApprovedResearchExecution,
    FrozenPrompt,
    ResearchExecutionError,
    StepLease,
)
from ai_pdf_worker.research_runtime_core import _prompt_for


@dataclass(frozen=True)
class ProviderResult:
    output: str
    input_tokens: int
    output_tokens: int
    usage_final: bool


class RecordedProvider(Protocol):
    provider: str
    model: str

    def generate(self, messages: list[GenerationMessage], *, node_key: str) -> ProviderResult: ...


class RecordedProviderError(ModelProviderError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        usage_final: bool = False,
    ) -> None:
        super().__init__(code, message)
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.usage_final = usage_final


def _response_usage(payload: object) -> tuple[int, int, bool]:
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        return 0, 0, False
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if (
        type(input_tokens) is int
        and input_tokens >= 0
        and type(output_tokens) is int
        and output_tokens >= 0
    ):
        return input_tokens, output_tokens, True
    return 0, 0, False


def _response_output(payload: dict[str, object]) -> str | None:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    output = payload.get("output")
    if not isinstance(output, list):
        return None
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content_items = item.get("content")
        if not isinstance(content_items, list):
            continue
        for content in content_items:
            if not isinstance(content, dict) or content.get("type") not in {
                "output_text",
                "text",
            }:
                continue
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    joined = "".join(parts).strip()
    return joined or None


class OpenAIRecordedProvider:
    provider = "openai"

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        api_base: str,
        timeout_seconds: float,
        max_output_tokens: int,
        structured_output_transport: str,
    ) -> None:
        if structured_output_transport != STRUCTURED_OUTPUT_TRANSPORT_VERSION:
            raise ValueError("unsupported_structured_output_transport")
        self.model = model
        self._api_key = api_key
        base = api_base.rstrip("/")
        self._api_base = base if urlsplit(base).path.rstrip("/").endswith("/v1") else f"{base}/v1"
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens

    def generate(self, messages: list[GenerationMessage], *, node_key: str) -> ProviderResult:
        try:
            response = httpx.post(
                f"{self._api_base}/responses",
                json={
                    "model": self.model,
                    "input": messages,
                    "max_output_tokens": self._max_output_tokens,
                    "text": {"format": structured_output_format(node_key)},
                },
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self._timeout_seconds,
            )
        except httpx.RequestError as error:
            raise RecordedProviderError(
                "generation_provider_unreachable",
                "Generation provider is unreachable.",
            ) from error
        try:
            payload = response.json()
        except ValueError as error:
            code = (
                "generation_provider_transient"
                if response.status_code == 429 or response.status_code >= 500
                else "generation_provider_error"
                if response.is_error
                else "generation_invalid_response"
            )
            raise RecordedProviderError(
                code,
                "Generation provider returned invalid JSON.",
            ) from error
        input_tokens, output_tokens, usage_final = _response_usage(payload)
        if response.is_error:
            code = (
                "generation_provider_transient"
                if response.status_code == 429 or response.status_code >= 500
                else "generation_provider_error"
            )
            raise RecordedProviderError(
                code,
                f"Generation provider returned HTTP {response.status_code}.",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                usage_final=usage_final,
            )
        if not isinstance(payload, dict):
            raise RecordedProviderError(
                "generation_invalid_response",
                "Generation provider returned an invalid payload.",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                usage_final=usage_final,
            )
        output = _response_output(payload)
        if output is None:
            code = (
                "generation_incomplete_response"
                if payload.get("status") == "incomplete"
                else "generation_invalid_response"
            )
            raise RecordedProviderError(
                code,
                "Generation provider returned no answer text.",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                usage_final=usage_final,
            )
        return ProviderResult(
            output=output,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            usage_final=usage_final,
        )


def frozen_v2_prompts() -> tuple[FrozenPrompt, ...]:
    return tuple(
        FrozenPrompt(
            node_key=node_key,
            prompt_version_id=V2_PROMPT_VERSION_IDS[node_key],
            prompt_key=V2_PROMPT_SPECS[node_key].prompt_key,
            version=2,
            step_kind=V2_PROMPT_SPECS[node_key].step_kind,
            template_text=V2_PROMPT_SPECS[node_key].template_text,
            variables_schema_version="2",
            variables_schema=V2_PROMPT_SPECS[node_key].variables_schema,
            template_sha256=V2_PROMPT_SPECS[node_key].template_sha256,
        )
        for node_key in PROMPT_NODE_ORDER
    )


def quick_prompt_binding_sha256(package: EvaluationPackage) -> str:
    quick = package.document["quick"]
    structured_output = package.document["structuredOutput"]
    return canonical_sha256(
        {
            "mode": "quick",
            "systemPrompt": quick["systemPrompt"],
            "evaluationContract": quick["evaluationContract"],
            "structuredOutputTransport": structured_output["transportVersion"],
            "schemaSetVersion": structured_output["schemaSetVersion"],
            "resultSchemaVersion": QUICK_RESULT_SCHEMA_VERSION,
            "resultSchemaSha256": canonical_sha256(QUICK_RESULT_SCHEMA),
            "providerResultSchemaSha256": canonical_sha256(
                PROVIDER_RESULT_SCHEMAS["quick"]
            ),
        }
    )


def research_prompt_binding_sha256(package: EvaluationPackage) -> str:
    research = package.document["research"]
    structured_output = package.document["structuredOutput"]
    if (
        research["releaseId"] != V2_RELEASE_ID
        or research["workflowVersionId"] != V2_WORKFLOW_VERSION_ID
        or research["agentResultSchemaVersion"] != AGENT_RESULT_SCHEMA_VERSION
        or structured_output["transportVersion"]
        != STRUCTURED_OUTPUT_TRANSPORT_VERSION
        or structured_output["schemaSetVersion"]
        != STRUCTURED_OUTPUT_SCHEMA_SET_VERSION
    ):
        raise ResearchExecutionError("research_prompt_binding_mismatch")
    prompts = frozen_v2_prompts()
    return canonical_sha256(
        {
            "releaseId": V2_RELEASE_ID,
            "workflowVersionId": V2_WORKFLOW_VERSION_ID,
            "agentResultSchemaVersion": AGENT_RESULT_SCHEMA_VERSION,
            "agentResultSchemasSha256": canonical_sha256(AGENT_RESULT_SCHEMAS),
            "structuredOutputTransport": structured_output["transportVersion"],
            "schemaSetVersion": structured_output["schemaSetVersion"],
            "providerResultSchemasSha256": canonical_sha256(
                {
                    prompt_node: PROVIDER_RESULT_SCHEMAS[schema_node]
                    for prompt_node, schema_node in PROMPT_RESULT_SCHEMA_NODES.items()
                }
            ),
            "prompts": [
                {
                    "nodeKey": item.node_key,
                    "promptVersionId": item.prompt_version_id,
                    "templateSha256": item.template_sha256,
                }
                for item in prompts
            ],
        }
    )


class EvaluationGeneration:
    def __init__(self, provider: RecordedProvider, execution: ApprovedResearchExecution) -> None:
        if execution.retry_policy_version != RETRY_POLICY_VERSION:
            raise ValueError("unsupported_r803_retry_policy")
        self._provider = provider
        self._execution = execution
        self._records: list[ProviderCallRecord] = []
        self._lock = Lock()

    @property
    def execution(self) -> ApprovedResearchExecution:
        return self._execution

    def prompt(self, node_key: str) -> FrozenPrompt:
        return _prompt_for(self._execution, node_key)

    def records_since(self, index: int) -> tuple[ProviderCallRecord, ...]:
        with self._lock:
            return tuple(self._records[index:])

    def update_execution(self, execution: ApprovedResearchExecution) -> None:
        self._execution = execution

    def generate(
        self,
        lease: StepLease,
        *,
        node_key: str,
        messages: list[GenerationMessage],
    ) -> str:
        logical_call_key = f"{lease.step_id}:{node_key}"
        for attempt_number in range(1, MAX_PROVIDER_ATTEMPTS + 1):
            started = monotonic()
            try:
                result = self._provider.generate(messages, node_key=node_key)
            except Exception as error:
                input_tokens = error.input_tokens if isinstance(error, RecordedProviderError) else 0
                output_tokens = error.output_tokens if isinstance(error, RecordedProviderError) else 0
                usage_final = error.usage_final if isinstance(error, RecordedProviderError) else False
                self._record(
                    ProviderCallRecord(
                        node_key=node_key,
                        logical_call_key=logical_call_key,
                        attempt_number=attempt_number,
                        duration_ms=int((monotonic() - started) * 1000),
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        usage_final=usage_final,
                        status="failed",
                    )
                )
                retryable = (
                    isinstance(error, ModelProviderError)
                    and error.code in RETRYABLE_PROVIDER_CODES
                    and attempt_number < MAX_PROVIDER_ATTEMPTS
                )
                if not retryable:
                    raise
                sleep(RETRY_BACKOFF_SECONDS[attempt_number - 1])
                continue
            self._record(
                ProviderCallRecord(
                    node_key=node_key,
                    logical_call_key=logical_call_key,
                    attempt_number=attempt_number,
                    duration_ms=int((monotonic() - started) * 1000),
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    usage_final=result.usage_final,
                    status="succeeded",
                )
            )
            return result.output
        raise AssertionError("unreachable provider retry state")

    def _record(self, record: ProviderCallRecord) -> None:
        with self._lock:
            self._records.append(record)
