from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from time import monotonic, monotonic_ns
from typing import Literal

from ai_pdf_api.core.research_observability import (
    observe_parallel_speedup,
    observe_research_step,
    research_log,
    research_span,
)
from langgraph.graph import END, START, StateGraph

from ai_pdf_worker.research_executor_contracts import (
    ApprovedResearchExecution,
    BranchResult,
    BranchTiming,
    Critic,
    EvidenceToolPort,
    FrozenAsset,
    Planner,
    PlanSubproblemDraft,
    Researcher,
    ResearchExecutionError,
    ResearchLedger,
    ResearchState,
    ResearchStepAutoRequeued,
    ResearchSubproblem,
    StepLease,
    SynthesisSelection,
    Synthesizer,
    ToolExecutionContext,
    VerifiedClaim,
    Verifier,
)
from ai_pdf_worker.research_executor_tools import EvidenceToolRegistry, _validate_claims

logger = logging.getLogger("ai_pdf_worker.research_executor")


class _StepObservation:
    def __init__(self) -> None:
        self.evidence_count = 0
        self.outcome = "success"


@contextmanager
def _observed_step(
    execution: ApprovedResearchExecution,
    lease: StepLease,
    step_kind: str,
) -> Iterator[_StepObservation]:
    started = monotonic()
    attributes = {
        "research.run_id": execution.run_id,
        "research.workspace_id": execution.workspace_id,
        "research.execution_snapshot_id": execution.execution_snapshot_id,
        "research.step_id": lease.step_id,
        "research.attempt_id": lease.attempt_id,
        "research.step_kind": step_kind,
        "research.attempt_number": lease.attempt_number,
    }
    observation = _StepObservation()
    with research_span("research.step", attributes) as span:
        research_log(
            logger,
            tag="research_step",
            status="started",
            fields={
                "run_id": execution.run_id,
                "workspace_id": execution.workspace_id,
                "step_id": lease.step_id,
                "attempt_id": lease.attempt_id,
                "step_kind": step_kind,
                "attempt_number": lease.attempt_number,
            },
        )
        try:
            yield observation
        except Exception as error:
            duration = monotonic() - started
            observe_research_step(step_kind, "error", duration, observation.evidence_count)
            research_log(
                logger,
                tag="research_step",
                status="error",
                level=logging.ERROR,
                fields={
                    "run_id": execution.run_id,
                    "workspace_id": execution.workspace_id,
                    "step_id": lease.step_id,
                    "attempt_id": lease.attempt_id,
                    "step_kind": step_kind,
                    "attempt_number": lease.attempt_number,
                    "reason_code": type(error).__name__,
                    "duration_ms": round(duration * 1000, 3),
                },
            )
            raise
        else:
            duration = monotonic() - started
            span.set_attributes(
                {
                    "research.evidence_count": observation.evidence_count,
                    "research.outcome": observation.outcome,
                }
            )
            observe_research_step(step_kind, observation.outcome, duration, observation.evidence_count)
            research_log(
                logger,
                tag="research_step",
                status="waiting" if observation.outcome == "waiting" else "succeeded",
                fields={
                    "run_id": execution.run_id,
                    "workspace_id": execution.workspace_id,
                    "step_id": lease.step_id,
                    "attempt_id": lease.attempt_id,
                    "step_kind": step_kind,
                    "attempt_number": lease.attempt_number,
                    "duration_ms": round(duration * 1000, 3),
                    "evidence_count": observation.evidence_count,
                },
            )


def _persist_step_failure(
    ledger: ResearchLedger,
    lease: StepLease,
    error: Exception,
) -> None:
    raw_code = getattr(error, "code", None)
    error_code = raw_code if isinstance(raw_code, str) and raw_code else type(error).__name__
    disposition = ledger.step_failed(lease, error_code)
    if disposition.auto_requeued:
        raise ResearchStepAutoRequeued(disposition.reason_code) from error


class BoundedResearchExecutor:
    def __init__(
        self,
        *,
        planner: Planner,
        researcher: Researcher,
        verifier: Verifier,
        critic: Critic,
        synthesizer: Synthesizer,
        evidence_tools: EvidenceToolPort,
        ledger: ResearchLedger,
    ) -> None:
        self._planner = planner
        self._researcher = researcher
        self._verifier = verifier
        self._critic = critic
        self._synthesizer = synthesizer
        self._evidence_tools = evidence_tools
        self._ledger = ledger
        self._graph = self._build_graph()

    def propose_plan(
        self,
        *,
        question: str,
        frozen_assets: Sequence[FrozenAsset],
        lease: StepLease | None = None,
    ) -> tuple[PlanSubproblemDraft, ...]:
        drafts = tuple(self._planner(question, frozen_assets, lease))
        frozen_asset_ids = {asset.asset_id for asset in frozen_assets}
        if not 1 <= len(drafts) <= 16:
            raise ResearchExecutionError("invalid_research_plan")
        for draft in drafts:
            if not draft.question.strip() or len(draft.question) > 4000:
                raise ResearchExecutionError("invalid_research_plan")
            if len(draft.asset_ids) > 100 or len(set(draft.asset_ids)) != len(draft.asset_ids):
                raise ResearchExecutionError("invalid_research_plan")
            if not set(draft.asset_ids).issubset(frozen_asset_ids):
                raise ResearchExecutionError("invalid_research_plan")
            if len(draft.expected_evidence) > 20:
                raise ResearchExecutionError("invalid_research_plan")
        return drafts

    def execute(self, run_id: str) -> ResearchState:
        execution = self._ledger.load_approved_execution(run_id)
        self._validate_execution(execution, run_id)
        restored = self._ledger.load_execution_state(execution)
        state = restored or ResearchState(
            execution=execution,
            completed_nodes=[],
            status="running",
        )
        self._validate_restored_state(state, execution)
        return self._graph.invoke(state)

    def resume_after_conflict(
        self,
        run_id: str,
        *,
        conflict_action: Literal["exclude_conflicted_claims", "keep_as_unresolved"],
    ) -> ResearchState:
        state = self._ledger.load_conflict_resume_state(run_id, conflict_action)
        execution = self._ledger.load_approved_execution(run_id)
        self._validate_execution(execution, run_id)
        self._validate_restored_state(state, execution)
        if "conflict_decision_gate" not in state.get("completed_nodes", []):
            raise ResearchExecutionError("conflict_decision_not_committed")
        return self._graph.invoke(state)

    def _build_graph(self):
        graph = StateGraph(ResearchState)
        graph.add_node("researchers", self._run_researchers)
        graph.add_node("join", self._run_join)
        graph.add_node("verifier", self._run_verifier)
        graph.add_node("critic", self._run_critic)
        graph.add_node("conflict_decision_gate", self._run_conflict_gate)
        graph.add_node("synthesizer", self._run_synthesizer)
        graph.add_node("artifact_publisher", self._run_publisher)
        graph.add_conditional_edges(
            START,
            self._entry_node,
            {
                "researchers": "researchers",
                "join": "join",
                "verifier": "verifier",
                "critic": "critic",
                "conflict_decision_gate": "conflict_decision_gate",
                "synthesizer": "synthesizer",
                "artifact_publisher": "artifact_publisher",
                "complete": END,
            },
        )
        graph.add_edge("researchers", "join")
        graph.add_edge("join", "verifier")
        graph.add_edge("verifier", "critic")
        graph.add_edge("critic", "conflict_decision_gate")
        graph.add_conditional_edges(
            "conflict_decision_gate",
            self._after_conflict_gate,
            {"wait": END, "continue": "synthesizer"},
        )
        graph.add_edge("synthesizer", "artifact_publisher")
        graph.add_edge("artifact_publisher", END)
        return graph.compile()

    @staticmethod
    def _entry_node(state: ResearchState) -> str:
        completed = set(state.get("completed_nodes", []))
        for node in (
            "researchers",
            "join",
            "verifier",
            "critic",
            "conflict_decision_gate",
            "synthesizer",
            "artifact_publisher",
        ):
            if node not in completed:
                return node
        return "complete"

    @staticmethod
    def _with_completed(state: ResearchState, node: str, result: dict) -> dict:
        return {**result, "completed_nodes": [*state.get("completed_nodes", []), node]}

    def _run_researchers(self, state: ResearchState) -> dict:
        execution = state["execution"]

        def run_branch(subproblem: ResearchSubproblem) -> tuple[BranchResult, BranchTiming]:
            completed = self._ledger.load_completed_branch(execution, subproblem.branch_key)
            if completed is not None:
                self._validate_persisted_branch(completed, execution, subproblem)
                return completed, BranchTiming(subproblem.branch_key, 0, 0)
            lease = self._ledger.claim_step(
                execution,
                step_key=f"researcher:{subproblem.branch_key}",
                branch_key=subproblem.branch_key,
            )
            if lease.step_id != subproblem.step_id:
                raise ResearchExecutionError("researcher_step_mismatch")
            with _observed_step(execution, lease, "researcher") as observation:
                context = ToolExecutionContext(
                    workspace_id=execution.workspace_id,
                    run_id=execution.run_id,
                    execution_snapshot_id=execution.execution_snapshot_id,
                    execution_snapshot_sha256=execution.snapshot_sha256,
                    step_id=lease.step_id,
                    attempt_id=lease.attempt_id,
                    branch_key=subproblem.branch_key,
                    frozen_assets=execution.frozen_assets,
                )
                tools = EvidenceToolRegistry(self._evidence_tools, context)
                started = monotonic_ns()
                try:
                    result = self._researcher(subproblem, tools, lease)
                    tools.validate_branch_result(result)
                except Exception as error:
                    _persist_step_failure(self._ledger, lease, error)
                    raise
                finished = monotonic_ns()
                observation.evidence_count = len(result.evidence)
                self._ledger.complete_branch(lease, result)
            return result, BranchTiming(subproblem.branch_key, started, finished)

        max_workers = min(execution.max_parallel_researchers, len(execution.subproblems))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            completed = list(pool.map(run_branch, execution.subproblems))
        timed = [item[1] for item in completed if item[1].finished_ns > item[1].started_ns]
        if timed:
            serial_ns = sum(item.finished_ns - item.started_ns for item in timed)
            wall_ns = max(item.finished_ns for item in timed) - min(item.started_ns for item in timed)
            if wall_ns > 0:
                observe_parallel_speedup(max(1.0, serial_ns / wall_ns))
        return self._with_completed(
            state,
            "researchers",
            {
                "branch_results": [item[0] for item in completed],
                "branch_timings": [item[1] for item in completed],
            },
        )

    def _run_join(self, state: ResearchState) -> dict:
        lease = self._ledger.claim_step(state["execution"], step_key="join", branch_key=None)
        with _observed_step(state["execution"], lease, "join"):
            self._ledger.complete_control_step(lease)
        return self._with_completed(state, "join", {})

    def _run_verifier(self, state: ResearchState) -> dict:
        execution = state["execution"]
        lease = self._ledger.claim_step(execution, step_key="verifier", branch_key=None)
        with _observed_step(execution, lease, "verifier") as observation:
            try:
                claims = [claim for branch in state["branch_results"] for claim in branch.claims]
                evidence = [item for branch in state["branch_results"] for item in branch.evidence]
                observation.evidence_count = len(evidence)
                _validate_claims(claims, {item.id for item in evidence})
                verified = list(self._verifier(claims, evidence, lease))
                source_by_id = {claim.id: claim for claim in claims}
                if len(verified) != len(source_by_id) or {claim.id for claim in verified} != set(source_by_id):
                    raise ResearchExecutionError("verifier_claim_set_mismatch")
                if len({claim.id for claim in verified}) != len(verified):
                    raise ResearchExecutionError("duplicate_verified_claim")
                for claim in verified:
                    source = source_by_id[claim.id]
                    if claim.text != source.text or claim.evidence_handle_ids != source.evidence_handle_ids:
                        raise ResearchExecutionError("verifier_mutated_claim")
                    if claim.verification_status not in {"supported", "unsupported"} or claim.conflict_status != "none":
                        raise ResearchExecutionError("verifier_status_invalid")
            except Exception as error:
                _persist_step_failure(self._ledger, lease, error)
                raise
            self._ledger.complete_verification(lease, verified)
        return self._with_completed(state, "verifier", {"verified_claims": verified})

    def _run_critic(self, state: ResearchState) -> dict:
        execution = state["execution"]
        lease = self._ledger.claim_step(execution, step_key="critic", branch_key=None)
        with _observed_step(execution, lease, "critic"):
            try:
                claims = state["verified_claims"]
                conflicts = list(self._critic(claims, lease))
                supported_ids = {claim.id for claim in claims if claim.verification_status == "supported"}
                if len(conflicts) != len(set(conflicts)) or not set(conflicts).issubset(supported_ids):
                    raise ResearchExecutionError("critic_conflict_set_mismatch")
                conflict_ids = set(conflicts)
                updated = [
                    VerifiedClaim(
                        claim.id,
                        claim.text,
                        claim.evidence_handle_ids,
                        claim.verification_status,
                        "conflicted" if claim.id in conflict_ids else "none",
                    )
                    for claim in claims
                ]
            except Exception as error:
                _persist_step_failure(self._ledger, lease, error)
                raise
            self._ledger.complete_critique(lease, updated, conflicts)
        return self._with_completed(
            state,
            "critic",
            {"verified_claims": updated, "conflicts": conflicts, "unresolved": []},
        )

    def _run_conflict_gate(self, state: ResearchState) -> dict:
        execution = state["execution"]
        lease = self._ledger.claim_step(
            execution,
            step_key="conflict_decision_gate",
            branch_key=None,
        )
        conflicts = state.get("conflicts", [])
        with _observed_step(execution, lease, "conflict_decision_gate") as observation:
            if conflicts:
                observation.outcome = "waiting"
                with research_span(
                    "research.publish",
                    {
                        "research.run_id": execution.run_id,
                        "research.workspace_id": execution.workspace_id,
                        "research.step_id": lease.step_id,
                        "research.attempt_id": lease.attempt_id,
                        "research.node": "critic",
                    },
                ):
                    research_log(
                        logger,
                        tag="research_publish",
                        status="started",
                        fields={
                            "run_id": execution.run_id,
                            "workspace_id": execution.workspace_id,
                            "step_id": lease.step_id,
                            "attempt_id": lease.attempt_id,
                            "node": "critic",
                        },
                    )
                    self._ledger.wait_for_conflict_decision(lease, conflicts)
                    research_log(
                        logger,
                        tag="research_publish",
                        status="waiting",
                        fields={
                            "run_id": execution.run_id,
                            "workspace_id": execution.workspace_id,
                            "step_id": lease.step_id,
                            "attempt_id": lease.attempt_id,
                            "node": "critic",
                        },
                    )
                return {"status": "awaiting_human_decision"}
            self._ledger.complete_control_step(lease)
        return self._with_completed(state, "conflict_decision_gate", {"status": "running"})

    @staticmethod
    def _after_conflict_gate(state: ResearchState) -> str:
        return "wait" if state.get("status") == "awaiting_human_decision" else "continue"

    def _run_synthesizer(self, state: ResearchState) -> dict:
        execution = state["execution"]
        lease = self._ledger.claim_step(execution, step_key="synthesizer", branch_key=None)
        with _observed_step(execution, lease, "synthesizer"):
            try:
                publishable = [
                    claim
                    for claim in state["verified_claims"]
                    if claim.verification_status == "supported" and claim.conflict_status == "none"
                ]
                unresolved = [
                    claim
                    for claim in state["verified_claims"]
                    if claim.verification_status == "supported" and claim.conflict_status == "resolved_unresolved"
                ]
                selection = self._synthesizer(execution.question, publishable, unresolved, lease)
                self._validate_selection(selection, publishable, unresolved)
            except Exception as error:
                _persist_step_failure(self._ledger, lease, error)
                raise
            self._ledger.complete_synthesis(lease, selection)
        return self._with_completed(state, "synthesizer", {"synthesis": selection})

    def _run_publisher(self, state: ResearchState) -> dict:
        execution = state["execution"]
        lease = self._ledger.claim_step(execution, step_key="artifact_publisher", branch_key=None)
        with _observed_step(execution, lease, "artifact_publisher"):
            try:
                selection = state["synthesis"]
                with research_span(
                    "research.publish",
                    {
                        "research.run_id": execution.run_id,
                        "research.workspace_id": execution.workspace_id,
                        "research.execution_snapshot_id": execution.execution_snapshot_id,
                        "research.step_id": lease.step_id,
                        "research.attempt_id": lease.attempt_id,
                        "research.node": "synthesizer",
                    },
                ):
                    research_log(
                        logger,
                        tag="research_publish",
                        status="started",
                        fields={
                            "run_id": execution.run_id,
                            "workspace_id": execution.workspace_id,
                            "step_id": lease.step_id,
                            "attempt_id": lease.attempt_id,
                            "node": "synthesizer",
                        },
                    )
                    artifact_id = self._ledger.publish_final(
                        lease,
                        execution,
                        selection=selection,
                        claims=state["verified_claims"],
                    )
                    research_log(
                        logger,
                        tag="research_publish",
                        status="succeeded",
                        fields={
                            "run_id": execution.run_id,
                            "workspace_id": execution.workspace_id,
                            "step_id": lease.step_id,
                            "attempt_id": lease.attempt_id,
                            "node": "synthesizer",
                        },
                    )
            except Exception as error:
                _persist_step_failure(self._ledger, lease, error)
                raise
        return self._with_completed(
            state,
            "artifact_publisher",
            {"artifact_id": artifact_id, "status": "completed"},
        )

    @staticmethod
    def _validate_selection(
        selection: SynthesisSelection,
        publishable: Sequence[VerifiedClaim],
        unresolved: Sequence[VerifiedClaim],
    ) -> None:
        if not isinstance(selection, SynthesisSelection):
            raise ResearchExecutionError("invalid_synthesis_selection")
        if len(selection.fact_claim_ids) != len(set(selection.fact_claim_ids)):
            raise ResearchExecutionError("invalid_synthesis_selection")
        if len(selection.unresolved_claim_ids) != len(set(selection.unresolved_claim_ids)):
            raise ResearchExecutionError("invalid_synthesis_selection")
        if not set(selection.fact_claim_ids).issubset({claim.id for claim in publishable}):
            raise ResearchExecutionError("invalid_synthesis_selection")
        if not set(selection.unresolved_claim_ids).issubset({claim.id for claim in unresolved}):
            raise ResearchExecutionError("invalid_synthesis_selection")

    @staticmethod
    def _validate_persisted_branch(
        result: BranchResult,
        execution: ApprovedResearchExecution,
        subproblem: ResearchSubproblem,
    ) -> None:
        if result.branch_key != subproblem.branch_key:
            raise ResearchExecutionError("persisted_branch_mismatch")
        frozen = {asset.asset_id: asset for asset in execution.frozen_assets}
        evidence_ids: set[str] = set()
        for evidence in result.evidence:
            asset = frozen.get(evidence.asset_id)
            if (
                evidence.workspace_id != execution.workspace_id
                or evidence.run_id != execution.run_id
                or evidence.execution_snapshot_id != execution.execution_snapshot_id
                or evidence.owner_step_id != subproblem.step_id
                or evidence.branch_key != subproblem.branch_key
                or asset is None
                or evidence.processing_generation != asset.processing_generation
                or evidence.index_version != asset.index_version
                or not evidence.created_by_tool_call_id
            ):
                raise ResearchExecutionError("persisted_branch_scope_mismatch")
            evidence_ids.add(evidence.id)
        _validate_claims(result.claims, evidence_ids)

    @staticmethod
    def _validate_execution(execution: ApprovedResearchExecution, run_id: str) -> None:
        if execution.run_id != run_id or len(execution.snapshot_sha256) != 64:
            raise ResearchExecutionError("invalid_approved_execution")
        if not execution.workflow_version_id or not execution.prompt_version_ids:
            raise ResearchExecutionError("invalid_approved_execution")
        expected_prompt_nodes = ("planner", "researchers", "verifier", "critic", "synthesizer")
        if (
            tuple(prompt.node_key for prompt in execution.prompts) != expected_prompt_nodes
            or tuple(prompt.prompt_version_id for prompt in execution.prompts)
            != execution.prompt_version_ids
        ):
            raise ResearchExecutionError("invalid_approved_execution")
        if len(execution.provider_config_fingerprint) != 64:
            raise ResearchExecutionError("invalid_approved_execution")
        if not execution.budget_policy_version or not execution.retry_policy_version:
            raise ResearchExecutionError("invalid_approved_execution")
        if not 1 <= execution.max_parallel_researchers <= 3:
            raise ResearchExecutionError("invalid_parallel_researcher_limit")
        if execution.max_provider_calls < 1 or execution.max_tool_calls < 1:
            raise ResearchExecutionError("invalid_approved_execution")
        if not execution.subproblems or len(execution.subproblems) > 16:
            raise ResearchExecutionError("invalid_approved_execution")
        if not execution.frozen_assets or len(execution.frozen_assets) > 100:
            raise ResearchExecutionError("invalid_approved_execution")
        frozen_ids = [asset.asset_id for asset in execution.frozen_assets]
        if len(frozen_ids) != len(set(frozen_ids)):
            raise ResearchExecutionError("invalid_approved_execution")
        branch_keys = [item.branch_key for item in execution.subproblems]
        step_ids = [item.step_id for item in execution.subproblems]
        if len(branch_keys) != len(set(branch_keys)) or len(step_ids) != len(set(step_ids)):
            raise ResearchExecutionError("invalid_approved_execution")
        for subproblem in execution.subproblems:
            if not subproblem.question.strip() or len(subproblem.question) > 4000:
                raise ResearchExecutionError("invalid_approved_execution")
            if not set(subproblem.asset_ids).issubset(frozen_ids):
                raise ResearchExecutionError("invalid_approved_execution")

    @classmethod
    def _validate_restored_state(
        cls,
        state: ResearchState,
        execution: ApprovedResearchExecution,
    ) -> None:
        if state.get("execution") != execution:
            raise ResearchExecutionError("execution_snapshot_drift")
        completed = state.get("completed_nodes", [])
        ordered = [
            "researchers",
            "join",
            "verifier",
            "critic",
            "conflict_decision_gate",
            "synthesizer",
            "artifact_publisher",
        ]
        if completed != ordered[: len(completed)]:
            raise ResearchExecutionError("execution_checkpoint_invalid")
        if "researchers" in completed:
            results = state.get("branch_results", [])
            if len(results) != len(execution.subproblems):
                raise ResearchExecutionError("execution_checkpoint_invalid")
            by_branch = {item.branch_key: item for item in results}
            for subproblem in execution.subproblems:
                result = by_branch.get(subproblem.branch_key)
                if result is None:
                    raise ResearchExecutionError("execution_checkpoint_invalid")
                cls._validate_persisted_branch(result, execution, subproblem)
        if "verifier" in completed:
            verified = state.get("verified_claims", [])
            branch_claims = {
                claim.id: claim
                for branch in state.get("branch_results", [])
                for claim in branch.claims
            }
            if (
                not verified
                or len(verified) != len(branch_claims)
                or {claim.id for claim in verified} != set(branch_claims)
            ):
                raise ResearchExecutionError("execution_checkpoint_invalid")
            for claim in verified:
                source = branch_claims[claim.id]
                if (
                    claim.text != source.text
                    or claim.evidence_handle_ids != source.evidence_handle_ids
                    or claim.verification_status not in {"supported", "unsupported"}
                    or claim.conflict_status
                    not in {"none", "conflicted", "resolved_excluded", "resolved_unresolved"}
                ):
                    raise ResearchExecutionError("execution_checkpoint_invalid")
        if "synthesizer" in completed and "synthesis" not in state:
            raise ResearchExecutionError("execution_checkpoint_invalid")
