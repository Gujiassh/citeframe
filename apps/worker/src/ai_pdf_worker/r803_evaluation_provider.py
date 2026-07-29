from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic, sleep
from typing import Protocol

import httpx
from ai_pdf_api.services.providers import (
    GenerationMessage,
    ModelProviderError,
    OpenAIGenerationProvider,
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


class _UsageCapturingClient:
    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.usage_final = False

    def post(
        self,
        url: str,
        *,
        json: object,
        headers: dict[str, str],
        timeout: float,
    ) -> httpx.Response:
        response = httpx.post(url, json=json, headers=headers, timeout=timeout)
        try:
            payload = response.json()
        except ValueError:
            return response
        usage = payload.get("usage") if isinstance(payload, dict) else None
        if isinstance(usage, dict):
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
            if isinstance(input_tokens, int) and input_tokens >= 0 and isinstance(output_tokens, int) and output_tokens >= 0:
                self.input_tokens = input_tokens
                self.output_tokens = output_tokens
                self.usage_final = True
        return response


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
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._api_base = api_base
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens

    def generate(self, messages: list[GenerationMessage], *, node_key: str) -> ProviderResult:
        del node_key
        client = _UsageCapturingClient()
        output = OpenAIGenerationProvider(
            model=self.model,
            api_key=self._api_key,
            api_base=self._api_base,
            timeout_seconds=self._timeout_seconds,
            max_output_tokens=self._max_output_tokens,
            client=client,
        ).generate(messages)
        return ProviderResult(
            output=output,
            input_tokens=client.input_tokens,
            output_tokens=client.output_tokens,
            usage_final=client.usage_final,
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
    return canonical_sha256(
        {
            "mode": "quick",
            "systemPrompt": quick["systemPrompt"],
            "evaluationContract": quick["evaluationContract"],
        }
    )


def research_prompt_binding_sha256(package: EvaluationPackage) -> str:
    research = package.document["research"]
    if (
        research["releaseId"] != V2_RELEASE_ID
        or research["workflowVersionId"] != V2_WORKFLOW_VERSION_ID
        or research["agentResultSchemaVersion"] != AGENT_RESULT_SCHEMA_VERSION
    ):
        raise ResearchExecutionError("research_prompt_binding_mismatch")
    prompts = frozen_v2_prompts()
    return canonical_sha256(
        {
            "releaseId": V2_RELEASE_ID,
            "workflowVersionId": V2_WORKFLOW_VERSION_ID,
            "agentResultSchemaVersion": AGENT_RESULT_SCHEMA_VERSION,
            "agentResultSchemasSha256": canonical_sha256(AGENT_RESULT_SCHEMAS),
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
        for attempt_number in range(1, 4):
            started = monotonic()
            try:
                result = self._provider.generate(messages, node_key=node_key)
            except Exception as error:
                self._record(
                    ProviderCallRecord(
                        node_key=node_key,
                        logical_call_key=logical_call_key,
                        attempt_number=attempt_number,
                        duration_ms=int((monotonic() - started) * 1000),
                        input_tokens=0,
                        output_tokens=0,
                        usage_final=False,
                        status="failed",
                    )
                )
                retryable = (
                    isinstance(error, ModelProviderError)
                    and error.code == "generation_provider_unreachable"
                    and attempt_number < 3
                )
                if not retryable:
                    raise
                sleep(attempt_number)
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
