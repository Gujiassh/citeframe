from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from dataclasses import replace
from threading import Barrier, Lock
from time import sleep

import pytest
from ai_pdf_worker.research_executor import (
    ApprovedResearchExecution,
    BoundedResearchExecutor,
    BranchResult,
    DraftClaim,
    EvidenceHandle,
    FailureDisposition,
    FrozenAsset,
    FrozenPrompt,
    LoadedEvidence,
    PlanSubproblemDraft,
    ResearchExecutionError,
    ResearchState,
    ResearchStepAutoRequeued,
    ResearchSubproblem,
    StepLease,
    SynthesisSelection,
    ToolExecutionContext,
    ToolPolicyError,
    VerifiedClaim,
)

PROMPT_KINDS = {
    "planner": "planner",
    "researchers": "researcher",
    "verifier": "verifier",
    "critic": "critic",
    "synthesizer": "synthesizer",
}


def frozen_prompt(node_key: str) -> FrozenPrompt:
    schema = {
        "schemaVersion": 2,
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }
    template = f"Frozen {node_key} prompt"
    digest = hashlib.sha256(
        json.dumps(
            {"template": template, "variables": schema},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return FrozenPrompt(
        node_key=node_key,
        prompt_version_id=f"prompt-{node_key}",
        prompt_key=f"research.{node_key}",
        version=2,
        step_kind=PROMPT_KINDS[node_key],
        template_text=template,
        variables_schema_version="2",
        variables_schema=schema,
        template_sha256=digest,
    )


def approved_execution() -> ApprovedResearchExecution:
    prompts = tuple(
        frozen_prompt(node_key)
        for node_key in ("planner", "researchers", "verifier", "critic", "synthesizer")
    )
    return ApprovedResearchExecution(
        workspace_id="workspace-1",
        run_id="run-1",
        execution_snapshot_id="execution-1",
        snapshot_sha256="a" * 64,
        question="compare",
        subproblems=tuple(
            ResearchSubproblem(
                step_id=f"step-{index}",
                branch_key=f"branch-{index}",
                question=f"question-{index}",
                asset_ids=("asset-1",),
            )
            for index in range(3)
        ),
        frozen_assets=(FrozenAsset("asset-1", 3, 5),),
        workflow_version_id="workflow-1",
        prompt_version_ids=tuple(prompt.prompt_version_id for prompt in prompts),
        provider_config_fingerprint="b" * 64,
        budget_policy_version="budget-v1",
        retry_policy_version="retry-v1",
        max_parallel_researchers=3,
        max_provider_calls=32,
        max_tool_calls=64,
        prompts=prompts,
    )


class ToolPort:
    def __init__(self) -> None:
        self.wrong_scope = False
        self.forge_load = False
        self.handles_by_step: dict[str, dict[str, EvidenceHandle]] = {}
        self.search_calls: Counter[str] = Counter()

    def _handle(self, context: ToolExecutionContext, handle_id: str) -> EvidenceHandle:
        return EvidenceHandle(
            id=handle_id,
            workspace_id=context.workspace_id,
            run_id="other-run" if self.wrong_scope else context.run_id,
            execution_snapshot_id=context.execution_snapshot_id,
            owner_step_id=context.step_id,
            branch_key=context.branch_key,
            asset_id="asset-1",
            processing_generation=3,
            index_version=5,
            representation_id="representation-1",
            parser_version="parser-v1",
            locator_id=f"locator-{handle_id}",
            locator_kind="pdf_page",
            excerpt="evidence",
            source_fingerprint_sha256="c" * 64,
            created_by_tool_call_id=f"tool-{handle_id}",
        )

    def restore_handles(self, context):
        return tuple(self.handles_by_step.get(context.step_id, {}).values())

    def search(self, context, *, tool_call_key, query, asset_ids, top_k):
        self.search_calls[context.branch_key] += 1
        handle = self._handle(context, f"evidence-{context.branch_key}")
        self.handles_by_step.setdefault(context.step_id, {})[handle.id] = handle
        return [handle]

    def load(self, context, *, tool_call_key, handle_ids):
        rows = self.handles_by_step.get(context.step_id, {})
        return [
            LoadedEvidence(
                evidence_handle=handle_id,
                asset_id=rows[handle_id].asset_id,
                processing_generation=rows[handle_id].processing_generation,
                index_version=rows[handle_id].index_version,
                representation_id=rows[handle_id].representation_id,
                parser_version=rows[handle_id].parser_version,
                locator_id="forged-locator" if self.forge_load else rows[handle_id].locator_id,
                locator_kind=rows[handle_id].locator_kind,
                content="loaded evidence",
                content_sha256="d" * 64,
                source_available=True,
            )
            for handle_id in handle_ids
        ]


class Ledger:
    def __init__(self, execution: ApprovedResearchExecution) -> None:
        self.execution = execution
        self.events: list[tuple[str, str]] = []
        self.completed_branches: dict[str, BranchResult] = {}
        self.attempts: Counter[str] = Counter()
        self.control_completed: set[str] = set()
        self.verified: list[VerifiedClaim] | None = None
        self.conflicts: list[str] | None = None
        self.gate_waiting = False
        self.gate_completed = False
        self.selection: SynthesisSelection | None = None
        self.published = False
        self.fail_publish_once = False

    def load_approved_execution(self, run_id):
        if run_id != self.execution.run_id:
            raise ResearchExecutionError("run_not_found")
        return self.execution

    def load_execution_state(self, execution):
        completed: list[str] = []
        state = ResearchState(execution=execution, completed_nodes=completed, status="running")
        if len(self.completed_branches) == len(execution.subproblems):
            completed.append("researchers")
            state["branch_results"] = [self.completed_branches[item.branch_key] for item in execution.subproblems]
            state["branch_timings"] = []
        else:
            return None
        if "join" in self.control_completed:
            completed.append("join")
        else:
            return state
        if self.verified is not None:
            completed.append("verifier")
            state["verified_claims"] = list(self.verified)
        else:
            return state
        if self.conflicts is not None:
            completed.append("critic")
            state["conflicts"] = list(self.conflicts)
            state["unresolved"] = []
        else:
            return state
        if self.gate_waiting:
            state["status"] = "awaiting_human_decision"
            return state
        if self.gate_completed:
            completed.append("conflict_decision_gate")
        else:
            return state
        if self.selection is not None:
            completed.append("synthesizer")
            state["synthesis"] = self.selection
        else:
            return state
        if self.published:
            completed.append("artifact_publisher")
            state["artifact_id"] = "artifact-final"
            state["status"] = "completed"
        return state

    def load_conflict_resume_state(self, run_id, action):
        state = self.load_execution_state(self.execution)
        assert state is not None and self.gate_waiting and self.conflicts
        conflict_ids = set(self.conflicts)
        status = "resolved_excluded" if action == "exclude_conflicted_claims" else "resolved_unresolved"
        self.verified = [
            replace(claim, conflict_status=status if claim.id in conflict_ids else claim.conflict_status)
            for claim in self.verified or []
        ]
        self.gate_waiting = False
        self.gate_completed = True
        state = self.load_execution_state(self.execution)
        assert state is not None
        state["verified_claims"] = list(self.verified)
        state["unresolved"] = list(self.conflicts) if action == "keep_as_unresolved" else []
        state["status"] = "running"
        return state

    def claim_step(self, execution, *, step_key, branch_key):
        self.attempts[step_key] += 1
        self.events.append(("started", step_key))
        step_id = next(
            (item.step_id for item in execution.subproblems if item.branch_key == branch_key),
            f"step-{step_key}",
        )
        return StepLease(step_id, f"attempt-{step_key}-{self.attempts[step_key]}", self.attempts[step_key])

    def complete_branch(self, lease, result):
        self.events.append(("succeeded", lease.step_id))
        self.completed_branches[result.branch_key] = result

    def complete_control_step(self, lease):
        key = lease.step_id.removeprefix("step-")
        self.events.append(("succeeded", key))
        self.control_completed.add(key)
        if key == "conflict_decision_gate":
            self.gate_completed = True

    def complete_verification(self, lease, claims):
        self.events.append(("succeeded", "verifier"))
        self.verified = list(claims)

    def complete_critique(self, lease, claims, conflicts):
        self.events.append(("succeeded", "critic"))
        self.verified = list(claims)
        self.conflicts = list(conflicts)

    def wait_for_conflict_decision(self, lease, conflicts):
        self.events.append(("waiting", "conflict_decision_gate"))
        self.gate_waiting = True

    def complete_synthesis(self, lease, selection):
        self.events.append(("succeeded", "synthesizer"))
        self.selection = selection

    def step_failed(self, lease, reason_code):
        self.events.append(("failed", lease.step_id))
        retryable = reason_code == "provider_temporarily_unavailable"
        return FailureDisposition(
            reason_code=reason_code,
            retryable=retryable,
            auto_requeued=retryable,
            step_status="queued" if retryable else "failed",
            run_status="running" if retryable else "failed",
        )

    def load_completed_branch(self, execution, branch_key):
        return self.completed_branches.get(branch_key)

    def publish_final(self, lease, execution, *, selection, claims):
        if self.fail_publish_once:
            self.fail_publish_once = False
            raise RuntimeError("publish crash")
        assert set(selection.fact_claim_ids + selection.unresolved_claim_ids).issubset(
            {claim.id for claim in claims}
        )
        self.events.append(("published", execution.run_id))
        self.published = True
        return "artifact-final"


def make_executor(
    *,
    conflict: bool = False,
    unsupported: bool = False,
    evidence_free: bool = False,
    fail_branch_once: str | None = None,
    mutate_verifier: bool = False,
    invalid_selection: bool = False,
):
    execution = approved_execution()
    barrier = Barrier(3) if fail_branch_once is None else None
    active = 0
    max_active = 0
    calls: Counter[str] = Counter()
    node_calls: Counter[str] = Counter()
    lock = Lock()
    ledger = Ledger(execution)
    tools = ToolPort()

    def planner(_question, _assets, _lease=None):
        node_calls["planner"] += 1
        return [PlanSubproblemDraft("planned", ("asset-1",), ("source",))]

    def researcher(subproblem, registry, _lease=None):
        nonlocal active, max_active
        calls[subproblem.branch_key] += 1
        with lock:
            active += 1
            max_active = max(max_active, active)
        if barrier is not None:
            barrier.wait(timeout=1)
        if fail_branch_once == subproblem.branch_key and calls[subproblem.branch_key] > 1:
            handles = tuple(tools.handles_by_step[subproblem.step_id].values())
            registry.load(evidence_handles=(handles[0].id,))
        else:
            handles = registry.search(query=subproblem.question, asset_ids=subproblem.asset_ids, top_k=8)
        sleep(0.01)
        with lock:
            active -= 1
        if fail_branch_once == subproblem.branch_key and calls[subproblem.branch_key] == 1:
            error = RuntimeError("transient")
            error.code = "provider_temporarily_unavailable"
            raise error
        claim_handles = () if evidence_free else (handles[0].id,)
        return BranchResult(
            subproblem.branch_key,
            (DraftClaim(f"claim-{subproblem.branch_key}", subproblem.question, claim_handles),),
            handles,
        )

    def verifier(claims, _evidence, _lease=None):
        node_calls["verifier"] += 1
        return [
            VerifiedClaim(
                claim.id,
                "fabricated" if mutate_verifier else claim.text,
                claim.evidence_handle_ids,
                "unsupported" if unsupported and claim.id.endswith("0") else "supported",
            )
            for claim in claims
        ]

    def critic(claims, _lease=None):
        node_calls["critic"] += 1
        return [claim.id for claim in claims if conflict and claim.id.endswith("1")]

    def synthesizer(_question, claims, unresolved, _lease=None):
        node_calls["synthesizer"] += 1
        if invalid_selection:
            return SynthesisSelection(("unknown-claim",), ())
        return SynthesisSelection(
            tuple(claim.id for claim in claims),
            tuple(claim.id for claim in unresolved),
        )

    executor = BoundedResearchExecutor(
        planner=planner,
        researcher=researcher,
        verifier=verifier,
        critic=critic,
        synthesizer=synthesizer,
        evidence_tools=tools,
        ledger=ledger,
    )
    return executor, ledger, tools, calls, node_calls, lambda: max_active


def test_execution_is_loaded_from_ledger_and_does_not_rerun_planner() -> None:
    executor, _, _, _, node_calls, _ = make_executor()
    assert executor.propose_plan(question="compare", frozen_assets=approved_execution().frozen_assets)[0].question == "planned"
    state = executor.execute("run-1")
    assert state["execution"] == approved_execution()
    assert state["status"] == "completed"
    assert node_calls["planner"] == 1


def test_three_researchers_overlap_and_unsupported_claim_is_not_published() -> None:
    executor, ledger, _, _, _, max_active = make_executor(unsupported=True)
    state = executor.execute("run-1")
    assert max_active() == 3
    assert "claim-branch-0" not in state["synthesis"].fact_claim_ids
    assert state["artifact_id"] == "artifact-final"
    assert ledger.events[-1] == ("published", "run-1")


def test_evidence_free_or_mutated_claim_fails_before_publish() -> None:
    executor, ledger, _, _, _, _ = make_executor(evidence_free=True)
    with pytest.raises(ResearchExecutionError, match="claim_requires_evidence"):
        executor.execute("run-1")
    assert not ledger.published

    executor, ledger, _, _, _, _ = make_executor(mutate_verifier=True)
    with pytest.raises(ResearchExecutionError, match="verifier_mutated_claim"):
        executor.execute("run-1")
    assert not ledger.published


def test_conflict_resume_uses_committed_ledger_state_and_does_not_rerun_critic() -> None:
    executor, _, _, calls, node_calls, _ = make_executor(conflict=True)
    waiting = executor.execute("run-1")
    waiting["conflicts"] = ["claim-branch-2"]
    calls_before_resume = calls.copy()
    resumed = executor.resume_after_conflict("run-1", conflict_action="keep_as_unresolved")
    assert resumed["status"] == "completed"
    assert resumed["synthesis"].unresolved_claim_ids == ("claim-branch-1",)
    assert node_calls["critic"] == 1
    assert calls == calls_before_resume


def test_conflict_gate_observability_records_waiting_not_success(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from ai_pdf_api.core import metrics
    from ai_pdf_api.core.research_observability import install_research_tracer_for_tests
    from ai_pdf_worker.research_executor_engine import logger
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    install_research_tracer_for_tests(provider.get_tracer("test.conflict"))
    waiting_metric = metrics.RESEARCH_STEPS.labels(
        step_kind="conflict_decision_gate",
        outcome="waiting",
    )
    before = waiting_metric._value.get()

    executor, _, _, _, _, _ = make_executor(conflict=True)
    with caplog.at_level(logging.INFO, logger=logger.name):
        state = executor.execute("run-1")

    gate_spans = [
        span
        for span in exporter.get_finished_spans()
        if span.name == "research.step"
        and span.attributes.get("research.step_kind") == "conflict_decision_gate"
    ]
    assert state["status"] == "awaiting_human_decision"
    assert len(gate_spans) == 1
    assert gate_spans[0].attributes["research.outcome"] == "waiting"
    assert waiting_metric._value.get() == before + 1
    assert "tag=research_step status=waiting" in caplog.text


def test_tool_results_cannot_cross_scope_or_replace_locator_identity() -> None:
    executor, _, tools, _, _, _ = make_executor()
    tools.wrong_scope = True
    with pytest.raises(ToolPolicyError, match="tool_scope_violation"):
        executor.execute("run-1")

    executor, _, tools, _, _, _ = make_executor()
    original_load = tools.load

    def researcher_with_load(subproblem, registry, _lease=None):
        handles = registry.search(query=subproblem.question, asset_ids=subproblem.asset_ids)
        registry.load(evidence_handles=(handles[0].id,))
        return BranchResult(
            subproblem.branch_key,
            (DraftClaim(f"claim-{subproblem.branch_key}", subproblem.question, (handles[0].id,)),),
            handles,
        )

    executor._researcher = researcher_with_load
    tools.forge_load = True
    with pytest.raises(ToolPolicyError, match="tool_scope_violation"):
        executor.execute("run-1")
    tools.load = original_load


def test_foreign_persisted_branch_is_rejected() -> None:
    executor, ledger, _, _, _, _ = make_executor()
    subproblem = approved_execution().subproblems[0]
    foreign = EvidenceHandle(
        "foreign-evidence", "workspace-2", "run-2", "execution-2", subproblem.step_id,
        subproblem.branch_key, "asset-1", 3, 5, "representation-1", "parser-v1", "locator-1",
        "pdf_page", "foreign", "e" * 64, "tool-foreign",
    )
    ledger.completed_branches[subproblem.branch_key] = BranchResult(
        subproblem.branch_key,
        (DraftClaim("foreign-claim", "foreign", (foreign.id,)),),
        (foreign,),
    )
    with pytest.raises(ResearchExecutionError, match="persisted_branch_scope_mismatch"):
        executor.execute("run-1")


def test_failed_branch_retry_restores_handles_and_skips_successful_branches() -> None:
    executor, ledger, tools, calls, _, _ = make_executor(fail_branch_once="branch-1")
    with pytest.raises(ResearchStepAutoRequeued, match="provider_temporarily_unavailable"):
        executor.execute("run-1")
    state = executor.execute("run-1")
    assert state["status"] == "completed"
    assert calls == Counter({"branch-1": 2, "branch-0": 1, "branch-2": 1})
    assert tools.search_calls["branch-1"] == 1
    assert ledger.attempts["researcher:branch-0"] == 1


def test_publish_restart_resumes_after_synthesis_without_rerunning_agents() -> None:
    executor, ledger, _, calls, node_calls, _ = make_executor()
    ledger.fail_publish_once = True
    with pytest.raises(RuntimeError, match="publish crash"):
        executor.execute("run-1")
    calls_before = calls.copy()
    node_calls_before = node_calls.copy()
    state = executor.execute("run-1")
    assert state["status"] == "completed"
    assert calls == calls_before
    assert node_calls == node_calls_before
    assert ledger.attempts["artifact_publisher"] == 2


def test_synthesizer_can_only_select_verified_claim_ids() -> None:
    executor, ledger, _, _, _, _ = make_executor(invalid_selection=True)
    with pytest.raises(ResearchExecutionError, match="invalid_synthesis_selection"):
        executor.execute("run-1")
    assert not ledger.published


def test_restored_verifier_checkpoint_rejects_partial_or_pending_claims() -> None:
    executor, ledger, _, _, _, _ = make_executor()
    executor.execute("run-1")
    assert ledger.verified is not None
    ledger.verified = [replace(ledger.verified[0], verification_status="pending")]

    with pytest.raises(ResearchExecutionError, match="execution_checkpoint_invalid"):
        executor.execute("run-1")


def test_tool_inputs_reject_unknown_assets_and_duplicate_handles() -> None:
    port = ToolPort()
    execution = approved_execution()
    context = ToolExecutionContext(
        execution.workspace_id,
        execution.run_id,
        execution.execution_snapshot_id,
        execution.snapshot_sha256,
        "step-1",
        "attempt-1",
        "branch-1",
        execution.frozen_assets,
    )
    from ai_pdf_worker.research_executor import EvidenceToolRegistry

    registry = EvidenceToolRegistry(port, context)
    with pytest.raises(ToolPolicyError, match="tool_scope_violation"):
        registry.search(query="query", asset_ids=("asset-2",))
    handles = registry.search(query="query", asset_ids=("asset-1",))
    with pytest.raises(ToolPolicyError, match="tool_input_invalid"):
        registry.load(evidence_handles=(handles[0].id, handles[0].id))
