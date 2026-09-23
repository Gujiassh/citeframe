from __future__ import annotations

from citeframe_contracts.validation import AgentResultValidationError
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from time import monotonic, monotonic_ns
from citeframe_evaluation.contracts import (
    CaseExecution,
    EvaluationPackage,
    ObservedClaim,
)
from citeframe_evaluation.diagnostics import (
    DiagnosticCapture,
    OutputFailureDiagnostic,
    validate_agent_result_with_diagnostics,
    with_failure_origin,
)
from citeframe_evaluation.provider import EvaluationGeneration, RecordedProvider
from ai_pdf_worker.research.schemas import AGENT_RESULT_SCHEMAS, validate_agent_result
from ai_pdf_worker.research.executor import (
    ApprovedResearchExecution,
    PlanSubproblemDraft,
    ResearchExecutionError,
    ResearchSubproblem,
    ToolExecutionContext,
)
from ai_pdf_worker.research.tools import EvidenceToolRegistry
from ai_pdf_worker.research.agents import GenerationResearchAgents
from citeframe_evaluation.runtime.failures import (
    _bind_capture_record,
    _diagnostic_for_semantic_failure,
    _require_final_usage,
    _safe_failure_code,
)
from citeframe_evaluation.runtime.fixtures import (
    FrozenEvidencePort,
    _lease,
    build_execution,
)


def _validate_evaluation_agent_result(node_key: str, value: dict[str, object]) -> None:
    """Keep R803 refusal semantics separate from production role-I/O v1."""

    if node_key == "researcher" and value == {"claims": []}:
        return
    validate_agent_result(node_key, value)


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
            if (
                record.node_key == node_key
                and record.logical_call_key == logical_call_key
            ):
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
        supported_ids = {
            item.id for item in verified if item.verification_status == "supported"
        }
        if len(conflicts) != len(set(conflicts)) or not set(conflicts).issubset(
            supported_ids
        ):
            annotated = ResearchExecutionError("critic_conflict_set_mismatch")
            annotated.logical_call_key = (
                f"{_lease(str(case['id']), 'critic').step_id}:critic"
            )
            raise annotated
        resolved = tuple(
            replace(
                item,
                conflict_status="resolved_unresolved"
                if item.id in conflicts
                else "none",
            )
            for item in verified
        )
        publishable = tuple(
            item
            for item in resolved
            if item.verification_status == "supported"
            and item.conflict_status == "none"
        )
        unresolved = tuple(
            item
            for item in resolved
            if item.verification_status == "supported"
            and item.conflict_status == "resolved_unresolved"
        )
        selection = agents.synthesizer(
            execution.question,
            publishable,
            unresolved,
            _lease(str(case["id"]), "synthesizer"),
        )
        if not set(selection.fact_claim_ids).issubset(
            {item.id for item in publishable}
        ) or not set(selection.unresolved_claim_ids).issubset(
            {item.id for item in unresolved}
        ):
            annotated = ResearchExecutionError("invalid_synthesis_selection")
            annotated.logical_call_key = (
                f"{_lease(str(case['id']), 'synthesizer').step_id}:synthesizer"
            )
            raise annotated
        selected_ids = set(selection.fact_claim_ids) | set(
            selection.unresolved_claim_ids
        )
        selected = tuple(item for item in resolved if item.id in selected_ids)
        observed_claims = tuple(
            ObservedClaim(
                text=item.text,
                evidence_ids=tuple(
                    evidence_port.evidence_id(handle_id)
                    for handle_id in item.evidence_handle_ids
                ),
                conflicted=item.id in conflicts,
            )
            for item in selected
        )
        evidence_ids = tuple(
            dict.fromkeys(
                evidence_id
                for item in observed_claims
                for evidence_id in item.evidence_ids
            )
        )
        if selected:
            output = "\n".join(item.text for item in selected)
            disposition = "answer"
        else:
            output = "The selected assets do not contain supporting evidence for this question."
            disposition = "refuse"
        timings = [
            (finished - branch_started) for _, branch_started, finished in branches
        ]
        wall_ns = max(finished for _, _, finished in branches) - min(
            branch_started for _, branch_started, _ in branches
        )
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
                conflict_resolution=(
                    "evaluation_keep_as_unresolved" if conflicts else None
                ),
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


def run_research_case(
    package: EvaluationPackage,
    case: dict[str, object],
    provider: RecordedProvider,
) -> CaseExecution:
    execution, _diagnostic = run_research_case_with_diagnostics(package, case, provider)
    return execution
