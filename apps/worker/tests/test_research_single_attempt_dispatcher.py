from __future__ import annotations

import subprocess
import sys
from threading import Barrier, Event, Lock
from time import monotonic, sleep

import pytest
from citeframe_contracts import (
    ApprovedResearchExecution,
    BranchResult,
    ResearchState,
    ResearchSubproblem,
    StepLease,
    SynthesisSelection,
)

import ai_pdf_worker.main as worker_main
import ai_pdf_worker.research_runtime_handlers as handlers_module
import ai_pdf_worker.research_runtime_processor as processor_module
from ai_pdf_worker.research_runtime_core import ResearchPortError
from ai_pdf_worker.research_runtime_handlers import (
    HUMAN_OWNED_STEP_KINDS,
    PERSISTED_STEP_KINDS,
    SingleAttemptStepDispatcher,
)
from ai_pdf_worker.research_runtime_processor import ResearchWorkProcessor


LEASE = StepLease("step-1", "attempt-1", 1, "lease-token")


def approved_execution(*, branch_step_id: str = "step-1") -> ApprovedResearchExecution:
    return ApprovedResearchExecution(
        workspace_id="workspace-1",
        run_id="run-1",
        execution_snapshot_id="snapshot-1",
        snapshot_sha256="a" * 64,
        question="Question",
        subproblems=(ResearchSubproblem(branch_step_id, "branch-1", "Branch question", ()),),
        frozen_assets=(),
        workflow_version_id="workflow-1",
        prompt_version_ids=(),
        provider_config_fingerprint="b" * 64,
        budget_policy_version="budget-v1",
        retry_policy_version="retry-v1",
        max_parallel_researchers=2,
        max_provider_calls=8,
        max_tool_calls=8,
    )


class Service:
    def restore_frozen_evidence(self, _db: object, **_kwargs: object) -> list[object]:
        return []


class Sessions:
    def __call__(self) -> object:
        class Session:
            def commit(self) -> None:
                return None

            def close(self) -> None:
                return None

            def rollback(self) -> None:
                return None

        return Session()


def claimed_payload(*, step_kind: str) -> dict[str, object]:
    return {
        "workspaceId": "workspace-1",
        "runId": "run-1",
        "stepId": "step-1",
        "stepKey": "revision-1:planner" if step_kind == "planner" else "researcher:branch-1",
        "stepKind": step_kind,
        "branchKey": None if step_kind == "planner" else "branch-1",
        "attemptId": "attempt-1",
        "attemptNumber": 1,
        "leaseToken": "lease-token",
    }


class ClaimService:
    def __init__(self, step_kind: str) -> None:
        self.step_kind = step_kind

    def reclaim_expired_research_steps(self, _db: object, **_kwargs: object) -> int:
        return 0

    def claim_next_research_step(self, _db: object, **_kwargs: object) -> dict[str, object]:
        return claimed_payload(step_kind=self.step_kind)


def test_process_one_dispatches_exactly_the_outer_claimed_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executions: list[dict[str, object]] = []

    class Dispatcher:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        def execute(self, **kwargs: object) -> str:
            executions.append(dict(kwargs))
            return "success"

    monkeypatch.setattr(processor_module, "SingleAttemptStepDispatcher", Dispatcher)

    assert ResearchWorkProcessor(
        Sessions(), ClaimService("researcher"), worker_instance_id="worker-1"
    ).process_one()
    assert len(executions) == 1
    assert executions[0]["step_kind"] == "researcher"
    assert executions[0]["lease"] == LEASE


def test_process_one_keeps_planner_in_waiting_without_dispatching_another_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planner_calls: list[str] = []

    def process_planner(
        _self: ResearchWorkProcessor,
        _ledger: object,
        claimed: object,
    ) -> None:
        planner_calls.append(getattr(claimed, "step_kind"))

    class ForbiddenDispatcher:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("planner must not enter execution-step dispatcher")

    monkeypatch.setattr(ResearchWorkProcessor, "_process_planner", process_planner)
    monkeypatch.setattr(processor_module, "SingleAttemptStepDispatcher", ForbiddenDispatcher)

    assert ResearchWorkProcessor(
        Sessions(), ClaimService("planner"), worker_instance_id="worker-1"
    ).process_one()
    assert planner_calls == ["planner"]


class Ledger:
    def __init__(self, state: ResearchState) -> None:
        self.state = state
        self.calls: list[str] = []

    def load_step_handler_input(self, **_kwargs: object):
        self.calls.append("load")
        return approved_execution(), self.state

    def complete_branch(self, _lease: StepLease, _result: BranchResult) -> None:
        self.calls.append("researcher")

    def complete_control_step(self, _lease: StepLease) -> None:
        self.calls.append("control")

    def complete_verification(self, _lease: StepLease, _claims: object) -> None:
        self.calls.append("verifier")

    def complete_critique(self, _lease: StepLease, _claims: object, _conflicts: object) -> None:
        self.calls.append("critic")

    def wait_for_conflict_decision(self, _lease: StepLease, _conflicts: object) -> None:
        self.calls.append("conflict_wait")

    def complete_synthesis(self, _lease: StepLease, _selection: SynthesisSelection) -> None:
        self.calls.append("synthesizer")

    def publish_final(self, _lease: StepLease, _execution: object, **_kwargs: object) -> str:
        self.calls.append("artifact_publisher")
        return "00000000-0000-0000-0000-000000000001"

    def step_failed(self, _lease: StepLease, _error_code: str) -> object:
        raise AssertionError("happy-path handler must not fail the Attempt")


class Agents:
    def __init__(self, _generation: object) -> None:
        return None

    def researcher(self, subproblem: ResearchSubproblem, _tools: object, _lease: StepLease) -> BranchResult:
        return BranchResult(subproblem.branch_key, (), ())

    def verifier(self, _claims: object, _evidence: object, _lease: StepLease) -> tuple[()]:
        return ()

    def critic(self, _claims: object, _lease: StepLease) -> tuple[()]:
        return ()

    def synthesizer(
        self,
        _question: str,
        _claims: object,
        _unresolved: object,
        _lease: StepLease,
    ) -> SynthesisSelection:
        return SynthesisSelection((), ())


@pytest.mark.parametrize(
    ("step_kind", "state", "expected_call"),
    [
        (
            "researcher",
            ResearchState(execution=approved_execution(), completed_nodes=[], status="running"),
            "researcher",
        ),
        (
            "join",
            ResearchState(
                execution=approved_execution(), completed_nodes=["researchers"], status="running"
            ),
            "control",
        ),
        (
            "verifier",
            ResearchState(
                execution=approved_execution(),
                completed_nodes=["researchers", "join"],
                branch_results=[BranchResult("branch-1", (), ())],
                status="running",
            ),
            "verifier",
        ),
        (
            "critic",
            ResearchState(
                execution=approved_execution(),
                completed_nodes=["researchers", "join", "verifier"],
                verified_claims=[],
                status="running",
            ),
            "critic",
        ),
        (
            "conflict_decision_gate",
            ResearchState(
                execution=approved_execution(),
                completed_nodes=["researchers", "join", "verifier", "critic"],
                conflicts=[],
                status="running",
            ),
            "control",
        ),
        (
            "synthesizer",
            ResearchState(
                execution=approved_execution(),
                completed_nodes=[
                    "researchers",
                    "join",
                    "verifier",
                    "critic",
                    "conflict_decision_gate",
                ],
                verified_claims=[],
                status="running",
            ),
            "synthesizer",
        ),
        (
            "artifact_publisher",
            ResearchState(
                execution=approved_execution(),
                completed_nodes=[
                    "researchers",
                    "join",
                    "verifier",
                    "critic",
                    "conflict_decision_gate",
                    "synthesizer",
                ],
                verified_claims=[],
                synthesis=SynthesisSelection((), ()),
                status="running",
            ),
            "artifact_publisher",
        ),
    ],
)
def test_dispatcher_executes_only_the_claimed_step_kind_handler(
    monkeypatch: pytest.MonkeyPatch,
    step_kind: str,
    state: ResearchState,
    expected_call: str,
) -> None:
    monkeypatch.setattr(handlers_module, "GenerationResearchAgents", Agents)
    ledger = Ledger(state)
    dispatcher = SingleAttemptStepDispatcher(Sessions(), Service(), ledger, provider=object())  # type: ignore[arg-type]

    outcome = dispatcher.execute(
        run_id="run-1",
        workspace_id="workspace-1",
        step_key=f"researcher:branch-1" if step_kind == "researcher" else step_kind,
        step_kind=step_kind,
        branch_key="branch-1" if step_kind == "researcher" else None,
        lease=LEASE,
    )

    assert outcome == "success"
    assert ledger.calls == ["load", expected_call]


def test_conflict_gate_waits_without_executing_the_synthesizer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(handlers_module, "GenerationResearchAgents", Agents)
    state = ResearchState(
        execution=approved_execution(),
        completed_nodes=["researchers", "join", "verifier", "critic"],
        conflicts=["claim-1"],
        status="running",
    )
    ledger = Ledger(state)

    outcome = SingleAttemptStepDispatcher(
        Sessions(), Service(), ledger, provider=object()  # type: ignore[arg-type]
    ).execute(
        run_id="run-1",
        workspace_id="workspace-1",
        step_key="conflict_decision_gate",
        step_kind="conflict_decision_gate",
        branch_key=None,
        lease=LEASE,
    )

    assert outcome == "waiting"
    assert ledger.calls == ["load", "conflict_wait"]


def test_human_plan_gate_is_never_executed_by_the_worker() -> None:
    assert HUMAN_OWNED_STEP_KINDS == {"plan_approval_gate"}
    assert PERSISTED_STEP_KINDS == {
        "planner",
        "plan_approval_gate",
        "researcher",
        "join",
        "verifier",
        "critic",
        "conflict_decision_gate",
        "synthesizer",
        "artifact_publisher",
    }
    dispatcher = SingleAttemptStepDispatcher(
        Sessions(),
        Service(),
        Ledger(ResearchState()),  # type: ignore[arg-type]
        provider=None,
    )

    with pytest.raises(ResearchPortError, match="human_owned_research_step_claimed"):
        dispatcher.execute(
            run_id="run-1",
            workspace_id="workspace-1",
            step_key="plan_approval_gate",
            step_kind="plan_approval_gate",
            branch_key=None,
            lease=LEASE,
        )


def test_dispatcher_rejects_a_handler_before_its_persisted_predecessor_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(handlers_module, "GenerationResearchAgents", Agents)
    ledger = Ledger(ResearchState(execution=approved_execution(), completed_nodes=[], status="running"))

    with pytest.raises(ResearchPortError, match="research_step_dependency_not_succeeded"):
        SingleAttemptStepDispatcher(Sessions(), Service(), ledger, provider=None).execute(  # type: ignore[arg-type]
            run_id="run-1",
            workspace_id="workspace-1",
            step_key="verifier",
            step_kind="verifier",
            branch_key=None,
            lease=LEASE,
        )
    assert ledger.calls == ["load"]


def test_production_shaped_two_loop_pool_overlaps_independent_processors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop_event = Event()
    barrier = Barrier(2)
    lock = Lock()
    pending = [
        {
            **claimed_payload(step_kind="researcher"),
            "stepId": "researcher-a",
            "stepKey": "researcher:branch-a",
            "branchKey": "branch-a",
            "attemptId": "attempt-a",
        },
        {
            **claimed_payload(step_kind="researcher"),
            "stepId": "researcher-b",
            "stepKey": "researcher:branch-b",
            "branchKey": "branch-b",
            "attemptId": "attempt-b",
        },
    ]
    intervals: list[tuple[str, str, int, float, float]] = []
    session_counter = 0

    class Session:
        def __init__(self, identity: int) -> None:
            self.identity = identity

        def commit(self) -> None:
            return None

        def rollback(self) -> None:
            return None

        def close(self) -> None:
            return None

    def sessions() -> Session:
        nonlocal session_counter
        with lock:
            session_counter += 1
            return Session(session_counter)

    class ClaimService:
        def reclaim_expired_research_steps(self, _db: Session, **_kwargs: object) -> int:
            return 0

        def claim_next_research_step(
            self,
            _db: Session,
            **_kwargs: object,
        ) -> dict[str, object] | None:
            with lock:
                return pending.pop(0) if pending else None

    class Dispatcher:
        def __init__(self, received_sessions: object, *_args: object, **_kwargs: object) -> None:
            self.sessions = received_sessions

        def execute(self, **kwargs: object) -> str:
            handler_session = self.sessions()
            assert isinstance(handler_session, Session)
            started = monotonic()
            barrier.wait(timeout=2)
            sleep(0.2)
            finished = monotonic()
            lease = kwargs["lease"]
            assert isinstance(lease, StepLease)
            with lock:
                intervals.append(
                    (
                        lease.step_id,
                        lease.attempt_id,
                        handler_session.identity,
                        started,
                        finished,
                    )
                )
                if len(intervals) == 2:
                    stop_event.set()
            return "success"

    monkeypatch.setattr(processor_module, "SingleAttemptStepDispatcher", Dispatcher)
    service = ClaimService()

    def factory(loop_index: int) -> ResearchWorkProcessor:
        return ResearchWorkProcessor(
            sessions,
            service,
            worker_instance_id=f"pool-worker-{loop_index}",
        )

    started = monotonic()
    pool = worker_main.ResearchDispatcherPool(
        stop_event=stop_event,
        processor_factory=factory,
        width=2,
    )
    pool.start()
    assert stop_event.wait(timeout=2)
    pool.stop_and_join(timeout_seconds=1)
    pool.raise_if_failed()
    wall = monotonic() - started

    assert len(intervals) == 2
    assert {item[0] for item in intervals} == {"researcher-a", "researcher-b"}
    assert {item[1] for item in intervals} == {"attempt-a", "attempt-b"}
    assert len({item[2] for item in intervals}) == 2
    assert max(item[3] for item in intervals) < min(item[4] for item in intervals)
    assert pending == []
    assert wall < 0.35


def test_research_pool_shutdown_is_bounded_when_idle() -> None:
    stop_event = Event()

    class Processor:
        def process_one(self) -> bool:
            return False

    pool = worker_main.ResearchDispatcherPool(
        stop_event=stop_event,
        processor_factory=lambda _index: Processor(),  # type: ignore[arg-type]
        width=2,
    )
    pool.start()
    started = monotonic()
    pool.stop_and_join(timeout_seconds=1)

    assert monotonic() - started < 0.25


def test_research_pool_propagates_a_loop_error_and_stops_siblings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop_event = Event()

    class Processor:
        def process_one(self) -> bool:
            return False

    def fail_loop(**_kwargs: object) -> None:
        raise RuntimeError("loop failed")

    monkeypatch.setattr(worker_main, "run_worker", fail_loop)
    pool = worker_main.ResearchDispatcherPool(
        stop_event=stop_event,
        processor_factory=lambda _index: Processor(),  # type: ignore[arg-type]
        width=2,
    )
    pool.start()
    pool.stop_and_join(timeout_seconds=1)

    assert stop_event.is_set()
    with pytest.raises(BaseExceptionGroup, match="research_dispatcher_loops_failed") as caught:
        pool.raise_if_failed()
    assert len(caught.value.exceptions) == 2


def test_research_pool_rejects_serial_production_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PDF_RESEARCH_DISPATCHER_LOOPS", "1")
    with pytest.raises(ValueError, match="at least 2"):
        worker_main._research_dispatcher_width()


def test_production_runtime_import_does_not_load_langgraph() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import ai_pdf_worker.research_runtime, ai_pdf_worker.main; "
                "assert 'langgraph' not in sys.modules; "
                "assert 'ai_pdf_worker.research_executor_engine' not in sys.modules"
            ),
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert "langgraph" not in completed.stdout.lower()
