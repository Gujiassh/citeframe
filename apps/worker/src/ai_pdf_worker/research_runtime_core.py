"""Production Research orchestration ports.

The worker owns orchestration and provider adapters.  The API owns the Research
ledger and the transaction boundaries.  This module deliberately contains no
SQLAlchemy model imports: a missing or incomplete API port is a hard failure.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from ai_pdf_worker.research_runtime_ports import SqlResearchLedgerAdapter

from ai_pdf_api.core.research_observability import (
    observe_research_tool,
    research_log,
    research_span,
)
from ai_pdf_api.services.providers import (
    GenerationMessage,
)
from ai_pdf_api.services.research.research_agent_io_registry import resolve_registry

from ai_pdf_worker.research_executor import (
    ApprovedResearchExecution,
    EvidenceHandle,
    FrozenAsset,
    FrozenPrompt,
    LoadedEvidence,
    ResearchExecutionError,
    ResearchStepAutoRequeued,
    ResearchSubproblem,
    StepLease,
    ToolExecutionContext,
)

logger = logging.getLogger("ai_pdf_worker.research_runtime")

LEASE_SECONDS = 300
HEARTBEAT_SECONDS = 30
MAX_EVIDENCE_EXCERPT = 2000
MAX_EVIDENCE_CONTENT = 12000
PROMPT_NODE_ORDER = ("planner", "researchers", "verifier", "critic", "synthesizer")
PROMPT_STEP_KINDS = {
    "planner": "planner",
    "researchers": "researcher",
    "verifier": "verifier",
    "critic": "critic",
    "synthesizer": "synthesizer",
}
PROMPT_REQUIRED_VARIABLES = {
    "planner": {"question", "frozenAssetScope", "planningLimits", "planOutputSchema"},
    "researchers": {"subproblem", "frozenAssetScope", "toolContracts", "resultSchema"},
    "verifier": {"claims", "evidence", "reasonTaxonomy", "resultSchema"},
    "critic": {"claims", "resultSchema"},
    "synthesizer": {"question", "claims", "resultSchema"},
}
GENERATION_PROMPT_NODES = {
    "planner": "planner",
    "researcher": "researchers",
    "verifier": "verifier",
    "critic": "critic",
    "synthesizer": "synthesizer",
}


class ResearchPortError(ResearchExecutionError):
    """The API ledger port rejected or could not complete a worker operation."""


@dataclass(frozen=True)
class VerificationRecord:
    claim_id: str
    status: str
    reason_code: str | None = None


class _ToolObservation:
    def __init__(self) -> None:
        self.evidence_count = 0


@contextmanager
def _observed_tool(
    context: ToolExecutionContext,
    tool_name: str,
) -> Iterator[_ToolObservation]:
    started = monotonic()
    attributes = {
        "research.run_id": context.run_id,
        "research.workspace_id": context.workspace_id,
        "research.execution_snapshot_id": context.execution_snapshot_id,
        "research.step_id": context.step_id,
        "research.attempt_id": context.attempt_id,
        "research.step_kind": "researcher",
        "research.tool_name": tool_name,
    }
    observation = _ToolObservation()
    with research_span("research.tool", attributes) as span:
        research_log(
            logger,
            tag="research_tool",
            status="started",
            fields={
                "run_id": context.run_id,
                "workspace_id": context.workspace_id,
                "step_id": context.step_id,
                "attempt_id": context.attempt_id,
                "step_kind": "researcher",
                "tool_name": tool_name,
            },
        )
        try:
            yield observation
        except Exception as error:
            duration = monotonic() - started
            observe_research_tool(tool_name, "error", duration)
            research_log(
                logger,
                tag="research_tool",
                status="error",
                level=logging.ERROR,
                fields={
                    "run_id": context.run_id,
                    "workspace_id": context.workspace_id,
                    "step_id": context.step_id,
                    "attempt_id": context.attempt_id,
                    "step_kind": "researcher",
                    "tool_name": tool_name,
                    "reason_code": type(error).__name__,
                    "duration_ms": round(duration * 1000, 3),
                },
            )
            raise
        else:
            duration = monotonic() - started
            span.set_attributes({"research.evidence_count": observation.evidence_count})
            observe_research_tool(
                tool_name,
                "success",
                duration,
                observation.evidence_count,
            )
            research_log(
                logger,
                tag="research_tool",
                status="succeeded",
                fields={
                    "run_id": context.run_id,
                    "workspace_id": context.workspace_id,
                    "step_id": context.step_id,
                    "attempt_id": context.attempt_id,
                    "step_kind": "researcher",
                    "tool_name": tool_name,
                    "duration_ms": round(duration * 1000, 3),
                    "evidence_count": observation.evidence_count,
                },
            )


class ResearchWorkerService(Protocol):
    def claim_next_research_step(self, db: Any, *, worker_instance_id: str, lease_seconds: int, now: datetime) -> Any: ...

    def claim_specific_research_step(
        self,
        db: Any,
        *,
        run_id: str,
        step_key: str,
        branch_key: str | None,
        worker_instance_id: str,
        lease_seconds: int,
        now: datetime,
    ) -> Any: ...


class SessionFactory(Protocol):
    def __call__(self) -> Any: ...


class _ApiPort:
    def __init__(self, sessions: SessionFactory, service: ResearchWorkerService) -> None:
        if not callable(sessions):
            raise TypeError("Research runtime requires a SessionFactory")
        self._sessions = sessions
        self._service = service

    @contextmanager
    def _db(self, *, write: bool = False) -> Iterator[Any]:
        db = self._sessions()
        try:
            yield db
            if write:
                db.commit()
        except Exception:
            if hasattr(db, "rollback"):
                db.rollback()
            raise
        finally:
            if hasattr(db, "close"):
                db.close()

    def _call(self, name: str, *, write: bool = False, **kwargs: Any) -> Any:
        function = _require_service(self._service, name)
        with self._db(write=write) as db:
            return function(db, **kwargs)


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        if name in value:
            return value[name]
        camel = name.split("_")[0] + "".join(part.capitalize() for part in name.split("_")[1:])
        if camel in value:
            return value[camel]
        raise ResearchPortError(f"research_port_missing_field:{name}")
    try:
        return getattr(value, name)
    except AttributeError as error:
        raise ResearchPortError(f"research_port_missing_field:{name}") from error


def _hash_json(value: object) -> str:
    payload = json.dumps(_json_value(value), ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _json_value(value: object) -> object:
    if is_dataclass(value):
        return {key: _json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def _now() -> datetime:
    return datetime.now(UTC)


def _token_estimate(messages: Sequence[GenerationMessage], output: str) -> tuple[int, int]:
    """Versioned local estimator used only when a provider returns no usage."""

    input_chars = sum(len(str(message.get("content", ""))) for message in messages)
    return max(1, (input_chars + 3) // 4), max(1, (len(output) + 3) // 4)


def _failure_code(error: BaseException) -> str:
    code = getattr(error, "code", None)
    return code if isinstance(code, str) and code else type(error).__name__


def _persist_step_failure(
    ledger: SqlResearchLedgerAdapter,
    lease: StepLease,
    error: Exception,
) -> None:
    disposition = ledger.step_failed(lease, _failure_code(error))
    if disposition.auto_requeued:
        raise ResearchStepAutoRequeued(disposition.reason_code) from error


def _prompt_contract_sha256(template: str, variables_schema: Mapping[str, object]) -> str:
    payload = json.dumps(
        {"template": template, "variables": variables_schema},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _frozen_prompt(payload: Any, *, expected_node: str) -> FrozenPrompt:
    node_key = str(_field(payload, "node_key"))
    prompt_version_id = str(_field(payload, "prompt_version_id"))
    prompt_key = str(_field(payload, "prompt_key"))
    version = int(_field(payload, "version"))
    step_kind = str(_field(payload, "step_kind"))
    template = str(_field(payload, "template"))
    variables_schema_version = str(_field(payload, "variables_schema_version"))
    variables_schema = _field(payload, "variables_schema")
    template_sha256 = str(_field(payload, "template_sha256"))
    required = variables_schema.get("required") if isinstance(variables_schema, Mapping) else None
    properties = variables_schema.get("properties") if isinstance(variables_schema, Mapping) else None
    try:
        canonical_prompt_id = str(UUID(prompt_version_id)) == prompt_version_id
    except ValueError:
        canonical_prompt_id = False
    if (
        node_key != expected_node
        or step_kind != PROMPT_STEP_KINDS[expected_node]
        or not canonical_prompt_id
        or not prompt_key
        or version < 1
        or not template
        or len(template) > 12000
        or variables_schema_version != "2"
        or not isinstance(variables_schema, Mapping)
        or variables_schema.get("schemaVersion") != 2
        or variables_schema.get("type") != "object"
        or variables_schema.get("additionalProperties") is not False
        or not isinstance(required, list)
        or len(required) != len(set(required))
        or set(required) != PROMPT_REQUIRED_VARIABLES[expected_node]
        or not isinstance(properties, Mapping)
        or set(properties) != PROMPT_REQUIRED_VARIABLES[expected_node]
        or len(template_sha256) != 64
        or _prompt_contract_sha256(template, variables_schema) != template_sha256
    ):
        raise ResearchPortError("research_prompt_contract_invalid")
    return FrozenPrompt(
        node_key=node_key,
        prompt_version_id=prompt_version_id,
        prompt_key=prompt_key,
        version=version,
        step_kind=step_kind,
        template_text=template,
        variables_schema_version=variables_schema_version,
        variables_schema=dict(variables_schema),
        template_sha256=template_sha256,
    )


def _frozen_prompts(payload: Any) -> tuple[FrozenPrompt, ...]:
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
        raise ResearchPortError("research_prompt_contract_invalid")
    rows = tuple(payload)
    if len(rows) != len(PROMPT_NODE_ORDER):
        raise ResearchPortError("research_prompt_contract_invalid")
    return tuple(
        _frozen_prompt(row, expected_node=node_key)
        for node_key, row in zip(PROMPT_NODE_ORDER, rows, strict=True)
    )


def _prompt_for(execution: ApprovedResearchExecution, generation_node: str) -> FrozenPrompt:
    prompt_node = GENERATION_PROMPT_NODES.get(generation_node)
    prompt = next((item for item in execution.prompts if item.node_key == prompt_node), None)
    if prompt is None:
        raise ResearchPortError("research_prompt_contract_invalid")
    return prompt


def _validate_prompt_variables(prompt: FrozenPrompt, variables: Mapping[str, object]) -> None:
    if set(variables) != PROMPT_REQUIRED_VARIABLES[prompt.node_key]:
        raise ResearchPortError("research_prompt_variables_invalid")


@contextmanager
def lease_heartbeat(ledger: SqlResearchLedgerAdapter, lease: StepLease) -> Iterator[None]:
    """Keep a running attempt alive while an external provider is blocking."""

    stop = threading.Event()
    errors: list[BaseException] = []

    def run() -> None:
        while not stop.wait(HEARTBEAT_SECONDS):
            try:
                ledger.heartbeat(lease)
            except BaseException as error:  # noqa: BLE001 - surface heartbeat failure on provider return
                errors.append(error)
                stop.set()
                return

    thread = threading.Thread(target=run, name=f"research-heartbeat-{lease.attempt_id}", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1)
    if errors:
        raise ResearchPortError("lease_heartbeat_failed") from errors[0]


def _require_service(service: Any, name: str) -> Any:
    function = getattr(service, name, None)
    if function is None or not callable(function):
        raise ResearchPortError(f"research_port_unavailable:{name}")
    return function


def _frozen_assets(payload: Any) -> tuple[FrozenAsset, ...]:
    rows = _field(payload, "frozen_assets")
    return tuple(
        FrozenAsset(
            str(_field(row, "asset_id")),
            int(_field(row, "processing_generation")),
            int(_field(row, "index_version")),
        )
        for row in rows
    )


def _subproblems(payload: Any) -> tuple[ResearchSubproblem, ...]:
    rows = _field(payload, "subproblems")
    return tuple(
        ResearchSubproblem(
            step_id=str(_field(row, "step_id")),
            branch_key=str(_field(row, "branch_key")),
            question=str(_field(row, "question")),
            asset_ids=tuple(str(item) for item in _field(row, "asset_ids")),
        )
        for row in rows
    )


def _planning_runtime_payload(payload: Any, *, run_id: str) -> dict[str, object]:
    """Flatten the API planning read DTO into the executor's runtime fields."""

    snapshot = _field(payload, "input_snapshot")
    planning = _field(snapshot, "planning_execution")
    provider = _field(planning, "provider")
    limits = _field(planning, "limits")
    proposed_limits = _field(_field(snapshot, "proposed_research_execution"), "limits")
    scope = _field(snapshot, "planning_asset_scope")
    assets = _field(scope, "assets")
    planner_prompt = _frozen_prompt(_field(payload, "planner_prompt"), expected_node="planner")
    if planner_prompt.prompt_version_id != str(_field(planning, "planner_prompt_version_id")):
        raise ResearchPortError("research_prompt_contract_invalid")
    max_cost = (
        int(_field(_field(limits, "max_cost"), "amount_micros"))
        if isinstance(limits, Mapping) and ("max_cost" in limits or "maxCost" in limits)
        else 0
    )
    agent_result_schema_version = (
        planning.get("agentResultSchemaVersion") or planning.get("agent_result_schema_version")
        if isinstance(planning, Mapping)
        else None
    )
    context_policy_version = (
        planning.get("contextPolicyVersion") or planning.get("context_policy_version")
        if isinstance(planning, Mapping)
        else None
    )
    compact_policy_version = (
        planning.get("compactPolicyVersion") or planning.get("compact_policy_version")
        if isinstance(planning, Mapping)
        else None
    )
    return {
        "workspace_id": _field(payload, "workspace_id"),
        "run_id": run_id,
        "plan_revision_id": _field(payload, "revision_id"),
        "question": _field(snapshot, "question"),
        "snapshot_sha256": _field(snapshot, "snapshot_sha256"),
        "workflow_version_id": _field(planning, "workflow_version_id"),
        "planner_prompt_version_id": _field(planning, "planner_prompt_version_id"),
        "prompts": (planner_prompt,),
        "provider_config_fingerprint": _field(provider, "provider_config_fingerprint"),
        "budget_policy_version": _field(planning, "budget_policy_version"),
        "retry_policy_version": _field(planning, "retry_policy_version"),
        "max_parallel_researchers": _field(proposed_limits, "max_parallel_researchers"),
        "max_provider_calls": _field(limits, "max_provider_calls"),
        "proposed_max_provider_calls": _field(proposed_limits, "max_provider_calls"),
        "max_tool_calls": 1,
        "max_input_tokens": _field(limits, "max_input_tokens"),
        "max_output_tokens": _field(limits, "max_output_tokens"),
        "max_cost_microunits": max_cost,
        "agent_result_schema_version": str(agent_result_schema_version or "research-agent-results-legacy-v0"),
        "context_policy_version": str(context_policy_version or "research-context-policy-legacy-v0"),
        "compact_policy_version": str(compact_policy_version or "research-compact-policy-legacy-v0"),
        "frozen_assets": tuple(
            FrozenAsset(str(_field(item, "asset_id")), int(_field(item, "processing_generation")), int(_field(item, "index_version")))
            for item in assets
        ),
    }


def as_approved_execution(payload: Any, *, expected_run_id: str | None = None) -> ApprovedResearchExecution:
    """Convert the API port DTO into the executor's immutable runtime snapshot."""

    run_id = str(_field(payload, "run_id"))
    if expected_run_id is not None and run_id != expected_run_id:
        raise ResearchPortError("execution_run_scope_mismatch")
    snapshot = _field(payload, "snapshot") if isinstance(payload, Mapping) and "snapshot" in payload else payload
    execution_config = _field(snapshot, "execution") if isinstance(snapshot, Mapping) and "execution" in snapshot else payload
    provider = _field(execution_config, "provider")
    limits = _field(execution_config, "limits")
    prompts = _frozen_prompts(_field(payload, "prompts"))
    prompt_version_ids = tuple(str(item) for item in _field(payload, "prompt_version_ids"))
    if prompt_version_ids != tuple(prompt.prompt_version_id for prompt in prompts):
        raise ResearchPortError("research_prompt_contract_invalid")
    max_cost = (
        int(_field(_field(limits, "max_cost"), "amount_micros"))
        if isinstance(limits, Mapping) and ("max_cost" in limits or "maxCost" in limits)
        else 0
    )
    execution = ApprovedResearchExecution(
        workspace_id=str(_field(payload, "workspace_id")),
        run_id=run_id,
        execution_snapshot_id=str(_field(payload, "execution_snapshot_id")),
        snapshot_sha256=str(_field(payload, "execution_snapshot_sha256")),
        question=str(_field(payload, "question")),
        subproblems=_subproblems(payload),
        frozen_assets=_frozen_assets(payload),
        workflow_version_id=str(_field(payload, "workflow_version_id")),
        prompt_version_ids=prompt_version_ids,
        provider_config_fingerprint=str(_field(provider, "provider_config_fingerprint")),
        budget_policy_version=str(_field(payload, "budget_policy_version")),
        retry_policy_version=str(_field(payload, "retry_policy_version")),
        max_parallel_researchers=int(_field(limits, "max_parallel_researchers")),
        max_provider_calls=int(_field(limits, "max_provider_calls")),
        max_tool_calls=int(_field(limits, "max_tool_calls")),
        plan_revision_id=(str(_field(payload, "plan_revision_id")) if isinstance(payload, Mapping) and ("plan_revision_id" in payload or "planRevisionId" in payload) else None),
        max_input_tokens=int(_field(limits, "max_input_tokens")),
        max_output_tokens=int(_field(limits, "max_output_tokens")),
        max_cost_microunits=max_cost,
        retrieval_top_k=int(_field(provider, "retrieval_top_k")),
        agent_result_schema_version=str(
            execution_config.get("agentResultSchemaVersion")
            or execution_config.get("agent_result_schema_version")
            or "research-agent-results-legacy-v0"
        ) if isinstance(execution_config, Mapping) else "research-agent-results-legacy-v0",
        context_policy_version=str(
            execution_config.get("contextPolicyVersion")
            or execution_config.get("context_policy_version")
            or "research-context-policy-legacy-v0"
        ) if isinstance(execution_config, Mapping) else "research-context-policy-legacy-v0",
        compact_policy_version=str(
            execution_config.get("compactPolicyVersion")
            or execution_config.get("compact_policy_version")
            or "research-compact-policy-legacy-v0"
        ) if isinstance(execution_config, Mapping) else "research-compact-policy-legacy-v0",
        prompts=prompts,
    )
    try:
        resolve_registry(
            agent_result_schema_version=execution.agent_result_schema_version,
            context_policy_version=execution.context_policy_version,
            compact_policy_version=execution.compact_policy_version,
            for_new_run=False,
        )
    except ValueError as error:
        raise ResearchPortError("research_agent_io_version_unavailable") from error
    if not execution.workspace_id or not execution.execution_snapshot_id or len(execution.snapshot_sha256) != 64:
        raise ResearchPortError("execution_scope_invalid")
    return execution


def _lease(payload: Any) -> StepLease:
    return StepLease(
        step_id=str(_field(payload, "step_id")),
        attempt_id=str(_field(payload, "attempt_id")),
        attempt_number=int(_field(payload, "attempt_number")),
        lease_token=str(_field(payload, "lease_token")),
    )


def _evidence_handle(payload: Any) -> EvidenceHandle:
    try:
        handle_id = str(_field(payload, "id"))
    except ResearchPortError:
        handle_id = str(_field(payload, "evidence_handle"))
    excerpt = str(_field(payload, "excerpt"))
    if len(excerpt) > MAX_EVIDENCE_EXCERPT:
        raise ResearchPortError("evidence_excerpt_limit")
    return EvidenceHandle(
        id=handle_id,
        workspace_id=str(_field(payload, "workspace_id")),
        run_id=str(_field(payload, "run_id")),
        execution_snapshot_id=str(_field(payload, "execution_snapshot_id")),
        owner_step_id=str(_field(payload, "owner_step_id")),
        branch_key=str(_field(payload, "branch_key")),
        asset_id=str(_field(payload, "asset_id")),
        processing_generation=int(_field(payload, "processing_generation")),
        index_version=int(_field(payload, "index_version")),
        representation_id=str(_field(payload, "representation_id")),
        parser_version=str(_field(payload, "parser_version")),
        locator_id=str(_field(payload, "locator_id")),
        locator_kind=_field(payload, "locator_kind"),
        excerpt=excerpt,
        source_fingerprint_sha256=str(_field(payload, "source_fingerprint_sha256")),
        created_by_tool_call_id=str(_field(payload, "created_by_tool_call_id")),
    )


def _loaded_evidence(payload: Any) -> LoadedEvidence:
    content = str(_field(payload, "content"))
    if len(content) > MAX_EVIDENCE_CONTENT:
        raise ResearchPortError("evidence_content_limit")
    return LoadedEvidence(
        evidence_handle=str(_field(payload, "evidence_handle")),
        asset_id=str(_field(payload, "asset_id")),
        processing_generation=int(_field(payload, "processing_generation")),
        index_version=int(_field(payload, "index_version")),
        representation_id=str(_field(payload, "representation_id")),
        parser_version=str(_field(payload, "parser_version")),
        locator_id=str(_field(payload, "locator_id")),
        locator_kind=_field(payload, "locator_kind"),
        content=content,
        content_sha256=str(_field(payload, "content_sha256")),
        source_available=bool(_field(payload, "source_available")),
    )
