from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Lock
from time import monotonic, monotonic_ns

from ai_pdf_api.services.providers import GenerationMessage, ModelProviderError
from ai_pdf_api.services.research_prompt_provenance import (
    V2_WORKFLOW_VERSION_ID,
)

from ai_pdf_worker.r803_evaluation_contract import (
    CaseExecution,
    EvaluationPackage,
    ObservedClaim,
    ProviderCallRecord,
)
from ai_pdf_worker.r803_evaluation_diagnostics import (
    AgentResultValidationError,
    DiagnosticCapture,
    OutputFailureDiagnostic,
    RawOutputRecord,
    classify_quick_payload_failure,
    validate_agent_result_with_diagnostics,
    with_failure_origin,
)
from ai_pdf_worker.r803_evaluation_provider import (
    EvaluationGeneration,
    RecordedProvider,
    frozen_v2_prompts,
)
from ai_pdf_worker.research_agent_schemas import (
    AGENT_RESULT_SCHEMAS,
    validate_agent_result,
)
from ai_pdf_worker.research_executor import (
    ApprovedResearchExecution,
    EvidenceHandle,
    FrozenAsset,
    LoadedEvidence,
    PlanSubproblemDraft,
    ResearchExecutionError,
    ResearchSubproblem,
    StepLease,
    ToolExecutionContext,
)
from ai_pdf_worker.research_executor_tools import EvidenceToolRegistry
from ai_pdf_worker.research_runtime_agents import GenerationResearchAgents


class FrozenEvidencePort:
    def __init__(self, package: EvaluationPackage) -> None:
        self._package = package
        self._issued: dict[str, tuple[EvidenceHandle, str]] = {}
        self._lock = Lock()

    def restore_handles(self, context: ToolExecutionContext) -> tuple[EvidenceHandle, ...]:
        del context
        return ()

    def search(
        self,
        context: ToolExecutionContext,
        *,
        tool_call_key: str,
        query: str,
        asset_ids: Sequence[str],
        top_k: int,
    ) -> tuple[EvidenceHandle, ...]:
        del query
        scoped_assets = set(asset_ids) if asset_ids else {item.asset_id for item in context.frozen_assets}
        items = [item for item in self._package.evidence.values() if item.asset_id in scoped_assets]
        handles: list[EvidenceHandle] = []
        for item in sorted(items, key=lambda value: value.id)[:top_k]:
            handle_id = "handle-" + hashlib.sha256(
                f"{context.step_id}:{item.id}".encode()
            ).hexdigest()[:24]
            handle = EvidenceHandle(
                id=handle_id,
                workspace_id=context.workspace_id,
                run_id=context.run_id,
                execution_snapshot_id=context.execution_snapshot_id,
                owner_step_id=context.step_id,
                branch_key=context.branch_key,
                asset_id=item.asset_id,
                processing_generation=1,
                index_version=1,
                representation_id=f"fixture:{item.asset_id}",
                parser_version="r803-evidence-v1",
                locator_id=f"fixture:{item.asset_id}:{item.locator_key}",
                locator_kind=item.locator_kind,
                excerpt=item.content,
                source_fingerprint_sha256=item.source_fingerprint_sha256,
                created_by_tool_call_id=tool_call_key,
            )
            handles.append(handle)
            with self._lock:
                self._issued[handle_id] = (handle, item.id)
        return tuple(handles)

    def load(
        self,
        context: ToolExecutionContext,
        *,
        tool_call_key: str,
        handle_ids: Sequence[str],
    ) -> tuple[LoadedEvidence, ...]:
        del context, tool_call_key
        loaded: list[LoadedEvidence] = []
        with self._lock:
            issued = dict(self._issued)
        for handle_id in handle_ids:
            handle, evidence_id = issued[handle_id]
            item = self._package.evidence[evidence_id]
            loaded.append(
                LoadedEvidence(
                    evidence_handle=handle.id,
                    asset_id=handle.asset_id,
                    processing_generation=handle.processing_generation,
                    index_version=handle.index_version,
                    representation_id=handle.representation_id,
                    parser_version=handle.parser_version,
                    locator_id=handle.locator_id,
                    locator_kind=handle.locator_kind,
                    content=item.content,
                    content_sha256=hashlib.sha256(item.content.encode("utf-8")).hexdigest(),
                    source_available=True,
                )
            )
        return tuple(loaded)

    def evidence_id(self, handle_id: str) -> str:
        with self._lock:
            return self._issued[handle_id][1]


def build_execution(package: EvaluationPackage, case: dict[str, object]) -> ApprovedResearchExecution:
    prompts = frozen_v2_prompts()
    assets = tuple(FrozenAsset(asset_id, 1, 1) for asset_id in case["assetScope"])
    return ApprovedResearchExecution(
        workspace_id="r803-evaluation",
        run_id=f"r803:{case['id']}",
        execution_snapshot_id=f"r803:{case['id']}:snapshot",
        snapshot_sha256=package.sha256,
        question=str(case["question"]),
        subproblems=(),
        frozen_assets=assets,
        workflow_version_id=V2_WORKFLOW_VERSION_ID,
        prompt_version_ids=tuple(item.prompt_version_id for item in prompts),
        provider_config_fingerprint=package.comparison_keys.provider_profile_sha256,
        budget_policy_version="budget-v1",
        retry_policy_version=package.document["executionPolicy"]["retryPolicyVersion"],
        max_parallel_researchers=3,
        max_provider_calls=32,
        max_tool_calls=32,
        max_input_tokens=100_000,
        max_output_tokens=32_000,
        max_cost_microunits=5_000_000,
        retrieval_top_k=6,
        prompts=prompts,
    )


def _validate_evaluation_agent_result(node_key: str, value: dict[str, object]) -> None:
    """Keep R803 refusal semantics separate from production role-I/O v1."""

    if node_key == "researcher" and value == {"claims": []}:
        return
    validate_agent_result(node_key, value)


def _lease(case_key: str, node_key: str, index: int = 0) -> StepLease:
    return StepLease(
        step_id=f"{case_key}:{node_key}:{index}",
        attempt_id=f"{case_key}:{node_key}:{index}:attempt",
        attempt_number=1,
    )



_SEMANTIC_NODE_FAILURES: dict[str, str] = {
    "claim_evidence_not_in_branch": "researcher",
    "claim_requires_evidence": "researcher",
    "duplicate_claim_evidence": "researcher",
    "duplicate_claim_id": "researcher",
    "duplicate_branch_evidence": "researcher",
    "unproven_branch_evidence": "researcher",
    "researcher_branch_mismatch": "researcher",
    "invalid_claim": "researcher",
    "invalid_research_plan": "planner",
    "verifier_claim_set_mismatch": "verifier",
    "verifier_mutated_claim": "verifier",
    "verifier_status_invalid": "verifier",
    "verifier_evidence_scope_mismatch": "verifier",
    "critic_conflict_set_mismatch": "critic",
    "invalid_synthesis_selection": "synthesizer",
}


def _bind_capture_record(
    diagnostic_capture: DiagnosticCapture | None,
    *,
    node_key: str | None,
    logical_call_key: str | None = None,
) -> RawOutputRecord | None:
    if diagnostic_capture is None:
        return None
    if logical_call_key:
        bound = diagnostic_capture.get_by_logical_call_key(logical_call_key)
        if bound is not None:
            return bound
    if node_key is None:
        return None
    # Exact single-node semantic failures bind the unique record for that node.
    matches = [item for item in diagnostic_capture.records if item.node_key == node_key]
    if len(matches) == 1:
        return matches[0]
    # Branch researcher failures must never silently pick "latest" when multiple
    # researcher logical calls exist without an exact key.
    if node_key == "researcher" and len(matches) != 1:
        return None
    return matches[-1] if matches else None


def _diagnostic_for_semantic_failure(
    failure_code: str,
    diagnostic_capture: DiagnosticCapture | None,
    *,
    logical_call_key: str | None = None,
) -> OutputFailureDiagnostic | None:
    node_key = _SEMANTIC_NODE_FAILURES.get(failure_code)
    if node_key is None and failure_code.endswith("_invalid_output"):
        node_key = failure_code[: -len("_invalid_output")]
    if node_key is None:
        return None
    bound = _bind_capture_record(
        diagnostic_capture,
        node_key=node_key,
        logical_call_key=logical_call_key,
    )
    return with_failure_origin(
        OutputFailureDiagnostic(
            stage="research_semantic_or_schema",
            rule=failure_code,
            path="$",
            node_key=node_key,
            logical_call_key=bound.logical_call_key if bound else logical_call_key,
            raw_output_sha256=bound.sha256 if bound else None,
            failure_code=failure_code,
        )
    )


def _safe_failure_code(error: Exception) -> str:
    """Preserve historical public wrapper codes for unknown exceptions.

    v4-compatible `run_quick_case` / `run_research_case` keep
    `type(error).__name__` for unexpected failures (e.g. RuntimeError).
    Campaign/scorer v5 still classifies unknown origins as engineering/
    integrity and modelQuality=not_evaluable at campaign gates.
    """
    if isinstance(error, json.JSONDecodeError):
        return "quick_invalid_output"
    if isinstance(error, ModelProviderError):
        return error.code
    if isinstance(error, AgentResultValidationError):
        return error.failure_code
    if isinstance(error, ResearchExecutionError):
        value = str(error).strip()
        if value and len(value) <= 96 and all(
            character.isalnum() or character in "._:-" for character in value
        ):
            return value
        return "research_execution_error"
    return type(error).__name__


def _require_final_usage(records: tuple[ProviderCallRecord, ...]) -> None:
    if any(item.status == "succeeded" and not item.usage_final for item in records):
        raise ResearchExecutionError("provider_usage_unavailable")


def _quick_messages(package: EvaluationPackage, case: dict[str, object]) -> list[GenerationMessage]:
    quick = package.document["quick"]
    scope = set(case["assetScope"])
    evidence = [item for item in package.evidence.values() if item.asset_id in scope]
    context = "\n\n".join(
        f"[{index}] evidenceId={item.id}\n{item.asset_title}, {item.locator_kind}\n{item.content}"
        for index, item in enumerate(sorted(evidence, key=lambda value: value.id), start=1)
    )
    return [
        {"role": "system", "content": f"{quick['systemPrompt']} {quick['evaluationContract']}"},
        {"role": "user", "content": f"Question:\n{case['question']}\n\nAsset evidence context:\n{context}"},
    ]



def run_quick_case_with_diagnostics(
    package: EvaluationPackage,
    case: dict[str, object],
    provider: RecordedProvider,
    *,
    diagnostic_capture: DiagnosticCapture | None = None,
) -> tuple[CaseExecution, OutputFailureDiagnostic | None]:
    started = monotonic()
    execution = build_execution(package, case)
    generation = EvaluationGeneration(provider, execution)
    try:
        logical_call_key = f"{case['id']}:quick:0:quick"
        raw = generation.generate(
            _lease(str(case["id"]), "quick"),
            node_key="quick",
            messages=_quick_messages(package, case),
        )
        if diagnostic_capture is not None:
            attempt_number = 1
            for record in reversed(generation.records_since(0)):
                if (
                    record.node_key == "quick"
                    and record.logical_call_key == logical_call_key
                    and record.status == "succeeded"
                ):
                    attempt_number = record.attempt_number
                    break
            diagnostic_capture.record(
                node_key="quick",
                logical_call_key=logical_call_key,
                attempt_number=attempt_number,
                raw_text=raw,
            )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            latest = diagnostic_capture.latest_for("quick") if diagnostic_capture else None
            diagnostic = OutputFailureDiagnostic(
                stage="quick_json_decode",
                rule="json_object",
                path="$",
                node_key="quick",
                logical_call_key=latest.logical_call_key if latest else f"{case['id']}:quick:0:quick",
                raw_output_sha256=latest.sha256 if latest else None,
                failure_code="quick_invalid_output",
            )
            raise ResearchExecutionError("quick_invalid_output") from error
        allowed_ids = {
            item.id for item in package.evidence.values() if item.asset_id in set(case["assetScope"])
        }
        if (
            not isinstance(payload, dict)
            or set(payload) != {"answer", "claims", "conflictDetected"}
            or not isinstance(payload.get("answer"), str)
            or not str(payload.get("answer")).strip()
            or not isinstance(payload.get("claims"), list)
            or not isinstance(payload.get("conflictDetected"), bool)
        ):
            diagnostic = classify_quick_payload_failure(payload)
            latest = diagnostic_capture.latest_for("quick") if diagnostic_capture else None
            if latest is not None:
                diagnostic = OutputFailureDiagnostic(
                    stage=diagnostic.stage,
                    rule=diagnostic.rule,
                    path=diagnostic.path,
                    node_key=diagnostic.node_key,
                    logical_call_key=latest.logical_call_key,
                    raw_output_sha256=latest.sha256,
                    failure_code=diagnostic.failure_code,
                )
            raise ResearchExecutionError("quick_invalid_output")
        answer = payload["answer"]
        claims = payload["claims"]
        conflict_detected = payload["conflictDetected"]
        observed_claims: list[ObservedClaim] = []
        for index, claim in enumerate(claims):
            if not isinstance(claim, dict) or set(claim) != {"text", "evidenceIds"}:
                diagnostic = OutputFailureDiagnostic(
                    stage="quick_local_schema",
                    rule="claim_closed_object",
                    path=f"$.claims[{index}]",
                    node_key="quick",
                    logical_call_key=f"{case['id']}:quick:0:quick",
                    raw_output_sha256=(
                        diagnostic_capture.latest_for("quick").sha256
                        if diagnostic_capture and diagnostic_capture.latest_for("quick")
                        else None
                    ),
                    failure_code="quick_invalid_output",
                )
                raise ResearchExecutionError("quick_invalid_output")
            text_value = claim["text"]
            claim_evidence = claim["evidenceIds"]
            if (
                not isinstance(text_value, str)
                or not text_value.strip()
                or not isinstance(claim_evidence, list)
                or not claim_evidence
                or len(claim_evidence) != len(set(claim_evidence))
                or not set(claim_evidence).issubset(allowed_ids)
            ):
                diagnostic = OutputFailureDiagnostic(
                    stage="quick_local_schema",
                    rule="claim_evidence_scope_or_shape",
                    path=f"$.claims[{index}]",
                    node_key="quick",
                    logical_call_key=f"{case['id']}:quick:0:quick",
                    raw_output_sha256=(
                        diagnostic_capture.latest_for("quick").sha256
                        if diagnostic_capture and diagnostic_capture.latest_for("quick")
                        else None
                    ),
                    failure_code="quick_invalid_output",
                )
                raise ResearchExecutionError("quick_invalid_output")
            observed_claims.append(
                ObservedClaim(text_value.strip(), tuple(claim_evidence), conflict_detected)
            )
        evidence_ids = tuple(
            dict.fromkeys(
                evidence_id
                for claim in observed_claims
                for evidence_id in claim.evidence_ids
            )
        )
        refusal_markers = ("do not contain", "insufficient", "not supported", "cannot determine", "no evidence")
        disposition = (
            "refuse"
            if not observed_claims and any(marker in answer.casefold() for marker in refusal_markers)
            else "answer"
        )
        records = generation.records_since(0)
        _require_final_usage(records)
        return (
            CaseExecution(
                case_key=str(case["id"]),
                mode="quick",
                output=answer.strip(),
                observed_disposition=disposition,
                evidence_ids=evidence_ids,
                conflict_detected=conflict_detected,
                observed_claims=tuple(observed_claims),
                wall_time_ms=int((monotonic() - started) * 1000),
                calls=records,
            ),
            None,
        )
    except Exception as error:  # noqa: BLE001 - one failed case must remain reportable
        preserved = locals().get("diagnostic")
        diagnostic = preserved if isinstance(preserved, OutputFailureDiagnostic) else None
        if diagnostic is None and isinstance(error, ResearchExecutionError) and str(error) == "quick_invalid_output":
            latest = diagnostic_capture.latest_for("quick") if diagnostic_capture else None
            diagnostic = OutputFailureDiagnostic(
                stage="quick_local_schema",
                rule="quick_invalid_output",
                path="$",
                node_key="quick",
                logical_call_key=latest.logical_call_key if latest else f"{case['id']}:quick:0:quick",
                raw_output_sha256=latest.sha256 if latest else None,
                failure_code="quick_invalid_output",
            )
        return (
            CaseExecution(
                case_key=str(case["id"]),
                mode="quick",
                output="",
                observed_disposition="not_evaluable",
                evidence_ids=(),
                conflict_detected=False,
                observed_claims=(),
                wall_time_ms=int((monotonic() - started) * 1000),
                calls=generation.records_since(0),
                failure_code=_safe_failure_code(error),
            ),
            diagnostic,
        )


def _validated_subproblems(
    drafts: tuple[PlanSubproblemDraft, ...],
    execution: ApprovedResearchExecution,
    case_key: str,
) -> tuple[ResearchSubproblem, ...]:
    if not 1 <= len(drafts) <= 16:
        raise ResearchExecutionError("invalid_research_plan")
    frozen_ids = {item.asset_id for item in execution.frozen_assets}
    subproblems: list[ResearchSubproblem] = []
    for index, draft in enumerate(drafts):
        question = draft.question.strip()
        asset_ids = tuple(draft.asset_ids)
        if (
            not question
            or len(question) > 4000
            or len(asset_ids) > 100
            or len(set(asset_ids)) != len(asset_ids)
            or not set(asset_ids).issubset(frozen_ids)
        ):
            raise ResearchExecutionError("invalid_research_plan")
        subproblems.append(
            ResearchSubproblem(
                step_id=f"{case_key}:researcher:{index}",
                branch_key=f"branch-{index + 1}",
                question=question,
                asset_ids=asset_ids,
            )
        )
    return tuple(subproblems)



def run_research_case_with_diagnostics(
    package: EvaluationPackage,
    case: dict[str, object],
    provider: RecordedProvider,
    *,
    diagnostic_capture: DiagnosticCapture | None = None,
) -> tuple[CaseExecution, OutputFailureDiagnostic | None]:
    started = monotonic()
    execution = build_execution(package, case)
    generation = EvaluationGeneration(provider, execution)

    def _observer(node_key: str, logical_call_key: str, raw: str) -> None:
        if diagnostic_capture is None:
            return
        attempt_number = 1
        for record in reversed(generation.records_since(0)):
            if record.node_key == node_key and record.logical_call_key == logical_call_key:
                attempt_number = record.attempt_number
                break
        diagnostic_capture.record(
            node_key=node_key,
            logical_call_key=logical_call_key,
            attempt_number=attempt_number,
            raw_text=raw,
        )

    validator = (
        validate_agent_result_with_diagnostics
        if diagnostic_capture is not None
        else _validate_evaluation_agent_result
    )
    agents = GenerationResearchAgents(
        generation,
        result_schemas=AGENT_RESULT_SCHEMAS,
        result_validator=validator,
        output_observer=_observer if diagnostic_capture is not None else None,
        diagnostic_mode=diagnostic_capture is not None,
        allow_empty_researcher_claims=True,
    )
    evidence_port = FrozenEvidencePort(package)
    try:
        drafts = tuple(
            agents.planner(
                execution.question,
                execution.frozen_assets,
                _lease(str(case["id"]), "planner"),
            )
        )
        subproblems = _validated_subproblems(drafts, execution, str(case["id"]))
        execution = replace(execution, subproblems=subproblems)
        generation.update_execution(execution)

        def run_branch(item: tuple[int, ResearchSubproblem]):
            index, subproblem = item
            branch_started = monotonic_ns()
            context = ToolExecutionContext(
                workspace_id=execution.workspace_id,
                run_id=execution.run_id,
                execution_snapshot_id=execution.execution_snapshot_id,
                execution_snapshot_sha256=execution.snapshot_sha256,
                step_id=subproblem.step_id,
                attempt_id=f"{subproblem.step_id}:attempt",
                branch_key=subproblem.branch_key,
                frozen_assets=execution.frozen_assets,
            )
            tools = EvidenceToolRegistry(evidence_port, context)
            lease = _lease(str(case["id"]), "researcher", index)
            result = agents.researcher(
                subproblem,
                tools,
                lease,
            )
            try:
                tools.validate_branch_result(result)
            except ResearchExecutionError as branch_error:
                # Preserve exact researcher logical-call identity for branch semantic failures.
                annotated = ResearchExecutionError(str(branch_error))
                annotated.logical_call_key = f"{lease.step_id}:researcher"
                raise annotated from branch_error
            return result, branch_started, monotonic_ns()

        max_workers = min(execution.max_parallel_researchers, len(subproblems))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            branches = list(pool.map(run_branch, enumerate(subproblems)))
        draft_claims = [claim for result, _, _ in branches for claim in result.claims]
        handles = [handle for result, _, _ in branches for handle in result.evidence]
        verified = tuple(
            agents.verifier(
                draft_claims,
                handles,
                _lease(str(case["id"]), "verifier"),
            )
        )
        conflicts = tuple(
            agents.critic(
                verified,
                _lease(str(case["id"]), "critic"),
            )
        )
        supported_ids = {item.id for item in verified if item.verification_status == "supported"}
        if len(conflicts) != len(set(conflicts)) or not set(conflicts).issubset(supported_ids):
            annotated = ResearchExecutionError("critic_conflict_set_mismatch")
            annotated.logical_call_key = f"{_lease(str(case['id']), 'critic').step_id}:critic"
            raise annotated
        resolved = tuple(
            replace(item, conflict_status="resolved_unresolved" if item.id in conflicts else "none")
            for item in verified
        )
        publishable = tuple(
            item for item in resolved if item.verification_status == "supported" and item.conflict_status == "none"
        )
        unresolved = tuple(
            item
            for item in resolved
            if item.verification_status == "supported" and item.conflict_status == "resolved_unresolved"
        )
        selection = agents.synthesizer(
            execution.question,
            publishable,
            unresolved,
            _lease(str(case["id"]), "synthesizer"),
        )
        if (
            not set(selection.fact_claim_ids).issubset({item.id for item in publishable})
            or not set(selection.unresolved_claim_ids).issubset({item.id for item in unresolved})
        ):
            annotated = ResearchExecutionError("invalid_synthesis_selection")
            annotated.logical_call_key = (
                f"{_lease(str(case['id']), 'synthesizer').step_id}:synthesizer"
            )
            raise annotated
        selected_ids = set(selection.fact_claim_ids) | set(selection.unresolved_claim_ids)
        selected = tuple(item for item in resolved if item.id in selected_ids)
        observed_claims = tuple(
            ObservedClaim(
                text=item.text,
                evidence_ids=tuple(evidence_port.evidence_id(handle_id) for handle_id in item.evidence_handle_ids),
                conflicted=item.id in conflicts,
            )
            for item in selected
        )
        evidence_ids = tuple(
            dict.fromkeys(evidence_id for item in observed_claims for evidence_id in item.evidence_ids)
        )
        if selected:
            output = "\n".join(item.text for item in selected)
            disposition = "answer"
        else:
            output = "The selected assets do not contain supporting evidence for this question."
            disposition = "refuse"
        timings = [(finished - branch_started) for _, branch_started, finished in branches]
        wall_ns = max(finished for _, _, finished in branches) - min(branch_started for _, branch_started, _ in branches)
        speedup = sum(timings) / wall_ns if wall_ns > 0 else None
        records = generation.records_since(0)
        _require_final_usage(records)
        return (
            CaseExecution(
                case_key=str(case["id"]),
                mode="research",
                output=output,
                observed_disposition=disposition,
                evidence_ids=evidence_ids,
                conflict_detected=bool(conflicts),
                observed_claims=observed_claims,
                wall_time_ms=int((monotonic() - started) * 1000),
                calls=records,
                parallel_speedup=speedup,
                conflict_resolution=("evaluation_keep_as_unresolved" if conflicts else None),
            ),
            None,
        )
    except Exception as error:  # noqa: BLE001 - one failed case must remain reportable
        diagnostic: OutputFailureDiagnostic | None = None
        if isinstance(error, AgentResultValidationError):
            bound = _bind_capture_record(
                diagnostic_capture,
                node_key=error.node_key,
                logical_call_key=error.logical_call_key,
            )
            diagnostic = with_failure_origin(
                OutputFailureDiagnostic(
                    stage="research_local_schema",
                    rule=error.rule,
                    path=error.path,
                    node_key=error.node_key,
                    logical_call_key=error.logical_call_key
                    or (bound.logical_call_key if bound else None),
                    raw_output_sha256=error.raw_output_sha256
                    or (bound.sha256 if bound else None),
                    failure_code=error.failure_code,
                )
            )
            failure_code = error.failure_code
        else:
            failure_code = _safe_failure_code(error)
            # Bind exact logical-call raw SHA for schema and non-schema semantic failures.
            # Researcher branch validation must use its exact researcher key, never latest node.
            diagnostic = _diagnostic_for_semantic_failure(
                str(failure_code),
                diagnostic_capture,
                logical_call_key=getattr(error, "logical_call_key", None),
            )
        return (
            CaseExecution(
                case_key=str(case["id"]),
                mode="research",
                output="",
                observed_disposition="not_evaluable",
                evidence_ids=(),
                conflict_detected=False,
                observed_claims=(),
                wall_time_ms=int((monotonic() - started) * 1000),
                calls=generation.records_since(0),
                failure_code=failure_code,
            ),
            diagnostic,
        )



def run_quick_case(
    package: EvaluationPackage,
    case: dict[str, object],
    provider: RecordedProvider,
) -> CaseExecution:
    execution, _diagnostic = run_quick_case_with_diagnostics(package, case, provider)
    return execution


def run_research_case(
    package: EvaluationPackage,
    case: dict[str, object],
    provider: RecordedProvider,
) -> CaseExecution:
    execution, _diagnostic = run_research_case_with_diagnostics(package, case, provider)
    return execution
