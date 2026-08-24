from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Barrier, Lock

import ai_pdf_worker.main as worker_main
import pytest
from ai_pdf_api.services.research.research_prompt_provenance import (
    PROMPT_NODE_ORDER,
    V2_PROMPT_SPECS,
    V2_PROMPT_VERSION_IDS,
)
from ai_pdf_api.services.research.research_agent_io_registry import (
    AGENT_RESULT_SCHEMA_VERSION,
    COMPACT_POLICY_VERSION,
    CONTEXT_POLICY_VERSION,
)
from ai_pdf_worker.research_executor import (
    EvidenceHandle,
    FailureDisposition,
    FrozenAsset,
    FrozenPrompt,
    LoadedEvidence,
    ResearchExecutionError,
    ResearchStepAutoRequeued,
    ResearchSubproblem,
    StepLease,
    ToolExecutionContext,
)
from ai_pdf_worker.research_runtime import (
    GenerationResearchAgents,
    LedgeredGeneration,
    ResearchPortError,
    ResearchWorkProcessor,
    SqlEvidenceToolPort,
    SqlResearchLedgerAdapter,
    as_approved_execution,
)
from ai_pdf_worker.research_runtime_core import (
    _ApiPort,
    _evidence_handle,
    _persist_step_failure,
    _planning_runtime_payload,
)


def prompt_dto(node_key: str) -> dict[str, object]:
    spec = V2_PROMPT_SPECS[node_key]
    return {
        "nodeKey": node_key,
        "promptVersionId": V2_PROMPT_VERSION_IDS[node_key],
        "promptKey": spec.prompt_key,
        "version": 2,
        "stepKind": spec.step_kind,
        "template": spec.template_text,
        "variablesSchemaVersion": "2",
        "variablesSchema": spec.variables_schema,
        "templateSha256": spec.template_sha256,
    }


def frozen_prompt(node_key: str) -> FrozenPrompt:
    value = prompt_dto(node_key)
    return FrozenPrompt(
        node_key=node_key,
        prompt_version_id=str(value["promptVersionId"]),
        prompt_key=str(value["promptKey"]),
        version=int(value["version"]),
        step_kind=str(value["stepKind"]),
        template_text=str(value["template"]),
        variables_schema_version=str(value["variablesSchemaVersion"]),
        variables_schema=dict(value["variablesSchema"]),
        template_sha256=str(value["templateSha256"]),
    )


class Session:
    def __init__(self, number: int) -> None:
        self.number = number
        self.committed = False
        self.closed = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class SessionFactory:
    def __init__(self) -> None:
        self._next = 0
        self._lock = Lock()
        self.created: list[Session] = []

    def __call__(self) -> Session:
        with self._lock:
            self._next += 1
            session = Session(self._next)
            self.created.append(session)
            return session


class EvidenceService:
    def __init__(self) -> None:
        self.barrier = Barrier(2)
        self.session_numbers: list[int] = []
        self._lock = Lock()

    def restore_frozen_evidence(self, db: Session, **_kwargs: object) -> list[object]:
        with self._lock:
            self.session_numbers.append(db.number)
        self.barrier.wait(timeout=2)
        return []



def test_api_port_write_call_uses_research_uow_commit_and_close() -> None:
    class Db:
        committed = 0
        rolled_back = 0
        closed = 0

        def commit(self) -> None:
            self.committed += 1

        def rollback(self) -> None:
            self.rolled_back += 1

        def close(self) -> None:
            self.closed += 1

    class Service:
        def mutate(self, db: Db, *, value: str) -> str:
            assert db is session
            return value

    session = Db()
    port = _ApiPort(lambda: session, Service())

    assert port._call("mutate", write=True, value="persisted") == "persisted"
    assert (session.committed, session.rolled_back, session.closed) == (1, 0, 1)


def test_api_port_write_call_rolls_back_and_closes_on_failure() -> None:
    class Db:
        committed = 0
        rolled_back = 0
        closed = 0

        def commit(self) -> None:
            self.committed += 1

        def rollback(self) -> None:
            self.rolled_back += 1

        def close(self) -> None:
            self.closed += 1

    class Service:
        def mutate(self, _db: Db) -> None:
            raise RuntimeError("write failed")

    session = Db()
    port = _ApiPort(lambda: session, Service())

    with pytest.raises(RuntimeError, match="write failed"):
        port._call("mutate", write=True)
    assert (session.committed, session.rolled_back, session.closed) == (0, 1, 1)

def test_evidence_port_uses_independent_sessions_for_parallel_branches() -> None:
    factory = SessionFactory()
    service = EvidenceService()
    port = SqlEvidenceToolPort(factory, service)
    context = ToolExecutionContext(
        workspace_id="workspace-1",
        run_id="run-1",
        execution_snapshot_id="execution-1",
        execution_snapshot_sha256="a" * 64,
        step_id="step-1",
        attempt_id="attempt-1",
        branch_key="branch-1",
        frozen_assets=(FrozenAsset("asset-1", 3, 5),),
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(port.restore_handles, (context, context)))

    assert results == [(), ()]
    assert len(service.session_numbers) == 2
    assert len(set(service.session_numbers)) == 2
    assert all(session.committed is False for session in factory.created)
    assert all(session.closed for session in factory.created)


def test_evidence_port_rejects_foreign_handle_before_executor_accepts_it() -> None:
    factory = SessionFactory()

    class ForeignService:
        def restore_frozen_evidence(self, db: Session, **_kwargs: object) -> list[dict[str, object]]:
            return [
                {
                    "id": "handle-1",
                    "workspace_id": "other-workspace",
                    "run_id": "run-1",
                    "execution_snapshot_id": "execution-1",
                    "owner_step_id": "step-1",
                    "branch_key": "branch-1",
                    "asset_id": "asset-1",
                    "processing_generation": 3,
                    "index_version": 5,
                    "representation_id": "representation-1",
                    "parser_version": "parser-1",
                    "locator_id": "locator-1",
                    "locator_kind": "pdf_page",
                    "excerpt": "excerpt",
                    "source_fingerprint_sha256": "b" * 64,
                    "created_by_tool_call_id": "tool-1",
                }
            ]

    port = SqlEvidenceToolPort(factory, ForeignService())
    context = ToolExecutionContext("workspace-1", "run-1", "execution-1", "a" * 64, "step-1", "attempt-1", "branch-1", (FrozenAsset("asset-1", 3, 5),))
    with pytest.raises(ResearchPortError, match="evidence_handle_scope_mismatch"):
        port.restore_handles(context)


def test_frozen_evidence_excerpt_limit_fails_closed_without_truncation() -> None:
    payload = {
        "id": "handle-1",
        "workspaceId": "workspace-1",
        "runId": "run-1",
        "executionSnapshotId": "execution-1",
        "ownerStepId": "step-1",
        "branchKey": "branch-1",
        "assetId": "asset-1",
        "processingGeneration": 1,
        "indexVersion": 1,
        "representationId": "representation-1",
        "parserVersion": "parser-1",
        "locatorId": "locator-1",
        "locatorKind": "pdf_page",
        "excerpt": "x" * 2001,
        "sourceFingerprintSha256": "a" * 64,
        "createdByToolCallId": "tool-1",
    }

    with pytest.raises(ResearchPortError, match="evidence_excerpt_limit"):
        _evidence_handle(payload)


def test_planner_failure_uses_api_auto_retry_disposition() -> None:
    class Ledger:
        received: str | None = None

        def step_failed(self, _lease: StepLease, error_code: str) -> FailureDisposition:
            self.received = error_code
            return FailureDisposition(
                reason_code="provider_temporarily_unavailable",
                retryable=True,
                auto_requeued=True,
                step_status="queued",
                run_status="planning",
            )

    class ProviderError(RuntimeError):
        code = "generation_provider_error"

    ledger = Ledger()
    with pytest.raises(ResearchStepAutoRequeued, match="provider_temporarily_unavailable"):
        _persist_step_failure(
            ledger,
            StepLease("step-1", "attempt-1", 1, "lease-token"),
            ProviderError("transient"),
        )

    assert ledger.received == "generation_provider_error"


def test_generation_agents_require_a_ledger_lease() -> None:
    class NoCallGeneration:
        def generate(self, *_args: object, **_kwargs: object) -> str:
            raise AssertionError("provider must not run without lease")

    agents = GenerationResearchAgents(NoCallGeneration())
    with pytest.raises(Exception, match="planner_lease_required"):
        agents.planner("question", (FrozenAsset("asset-1", 1, 1),))


def test_researcher_rejects_model_supplied_claim_identifier() -> None:
    class Generation:
        execution = type("Execution", (), {"retrieval_top_k": 1})()

        def __init__(self) -> None:
            self.messages: list[dict[str, object]] | None = None

        def prompt(self, node_key: str) -> FrozenPrompt:
            assert node_key == "researcher"
            return frozen_prompt("researchers")

        def generate(self, *_args: object, **kwargs: object) -> str:
            self.messages = kwargs["messages"]
            return '{"claims":[{"id":"../../not-a-uuid","text":"Supported fact","evidenceHandleIds":["handle-1"]}]}'

    handle = EvidenceHandle(
        "handle-1", "workspace-1", "run-1", "execution-1", "step-1", "branch-1",
        "asset-1", 1, 1, "representation-1", "parser-1", "locator-1", "pdf_page",
        "excerpt", "a" * 64, "tool-1",
    )

    class Tools:
        def search(self, **_kwargs: object) -> tuple[EvidenceHandle, ...]:
            return (handle,)

        def load(self, **_kwargs: object) -> tuple[LoadedEvidence, ...]:
            return (
                LoadedEvidence(
                    "handle-1", "asset-1", 1, 1, "representation-1", "parser-1",
                    "locator-1", "pdf_page", "evidence", "b" * 64, True,
                ),
            )

    generation = Generation()
    with pytest.raises(ResearchExecutionError, match="researcher_invalid_output"):
        GenerationResearchAgents(generation).researcher(
            ResearchSubproblem("step-1", "branch-1", "question", ("asset-1",)),
            Tools(),
            StepLease("step-1", "attempt-1", 1, "lease-token"),
        )
    assert generation.messages is not None
    assert generation.messages[0] == {
        "role": "system",
        "content": V2_PROMPT_SPECS["researchers"].template_text,
    }
    variables = json.loads(str(generation.messages[1]["content"]))
    assert variables["resultSchema"]["required"] == ["claims"]
    assert variables["resultSchema"]["additionalProperties"] is False
    assert "FrozenAssetScope" not in str(generation.messages[0])


def approved_execution_payload() -> dict[str, object]:
    return {
        "runId": "run-1",
        "workspaceId": "workspace-1",
        "executionSnapshotId": "execution-1",
        "executionSnapshotSha256": "a" * 64,
        "question": "Compare",
        "workflowVersionId": "workflow-1",
        "promptVersionIds": [V2_PROMPT_VERSION_IDS[node] for node in PROMPT_NODE_ORDER],
        "prompts": [prompt_dto(node) for node in PROMPT_NODE_ORDER],
        "budgetPolicyVersion": "budget-v1",
        "retryPolicyVersion": "retry-v1",
        "frozenAssets": [
            {"assetId": "asset-1", "processingGeneration": 2, "indexVersion": 3}
        ],
        "subproblems": [
            {
                "stepId": "step-1",
                "branchKey": "branch-1",
                "question": "Subproblem",
                "assetIds": ["asset-1"],
            }
        ],
        "snapshot": {
            "snapshotSha256": "a" * 64,
            "execution": {
                "provider": {
                    "providerConfigFingerprint": "b" * 64,
                    "retrievalTopK": 6,
                },
                "limits": {
                    "maxParallelResearchers": 3,
                    "maxProviderCalls": 32,
                    "maxToolCalls": 64,
                    "maxInputTokens": 10000,
                    "maxOutputTokens": 4000,
                    "maxCost": {"amountMicros": 5000000},
                },
                "agentResultSchemaVersion": "research-agent-results-v1",
                "contextPolicyVersion": "research-context-policy-v1",
                "compactPolicyVersion": "research-compact-policy-v1",
            },
        },
    }


def planning_input_payload() -> dict[str, object]:
    return {
        "runId": "run-1",
        "workspaceId": "workspace-1",
        "revisionId": "revision-1",
        "plannerPrompt": prompt_dto("planner"),
        "inputSnapshot": {
            "question": "Compare",
            "snapshotSha256": "a" * 64,
            "planningAssetScope": {
                "assets": [
                    {
                        "assetId": "asset-1",
                        "processingGeneration": 2,
                        "indexVersion": 3,
                    }
                ]
            },
            "planningExecution": {
                "workflowVersionId": "workflow-1",
                "plannerPromptVersionId": V2_PROMPT_VERSION_IDS["planner"],
                "agentResultSchemaVersion": AGENT_RESULT_SCHEMA_VERSION,
                "contextPolicyVersion": CONTEXT_POLICY_VERSION,
                "compactPolicyVersion": COMPACT_POLICY_VERSION,
                "provider": {"providerConfigFingerprint": "b" * 64},
                "budgetPolicyVersion": "planning-budget-v1",
                "retryPolicyVersion": "planning-retry-v1",
                "limits": {
                    "maxProviderCalls": 2,
                    "maxInputTokens": 32000,
                    "maxOutputTokens": 8000,
                    "maxCost": {"amountMicros": 500000},
                },
            },
            "proposedResearchExecution": {
                "limits": {
                    "maxParallelResearchers": 3,
                    "maxProviderCalls": 32,
                }
            },
        },
    }


def test_planning_adapter_separates_planner_usage_from_proposed_research_budget() -> None:
    payload = _planning_runtime_payload(
        planning_input_payload(),
        run_id="run-1",
    )

    assert payload["max_provider_calls"] == 2
    assert payload["proposed_max_provider_calls"] == 32
    assert payload["max_parallel_researchers"] == 3
    assert payload["agent_result_schema_version"] == AGENT_RESULT_SCHEMA_VERSION
    assert payload["context_policy_version"] == CONTEXT_POLICY_VERSION
    assert payload["compact_policy_version"] == COMPACT_POLICY_VERSION


def test_approved_execution_adapter_reads_the_frozen_api_dto() -> None:
    payload = approved_execution_payload()

    execution = as_approved_execution(payload, expected_run_id="run-1")

    assert execution.workspace_id == "workspace-1"
    assert execution.frozen_assets == (FrozenAsset("asset-1", 2, 3),)
    assert execution.subproblems[0].step_id == "step-1"
    assert execution.max_cost_microunits == 5000000
    assert tuple(prompt.node_key for prompt in execution.prompts) == PROMPT_NODE_ORDER


def test_approved_execution_rejects_frozen_prompt_hash_drift() -> None:
    payload = approved_execution_payload()
    prompts = list(payload["prompts"])
    prompts[2] = {**prompts[2], "template": "tampered verifier prompt"}
    payload["prompts"] = prompts

    with pytest.raises(ResearchPortError, match="research_prompt_contract_invalid"):
        as_approved_execution(payload, expected_run_id="run-1")


def test_approved_execution_rejects_unknown_agent_io_registry_version() -> None:
    payload = approved_execution_payload()
    payload["snapshot"] = {
        **payload["snapshot"],
        "execution": {
            **payload["snapshot"]["execution"],
            "agentResultSchemaVersion": "research-agent-results-unknown",
        },
    }

    with pytest.raises(ResearchPortError, match="research_agent_io_version_unavailable"):
        as_approved_execution(payload, expected_run_id="run-1")


def test_provider_call_reserve_send_reconcile_use_separate_sessions() -> None:
    factory = SessionFactory()

    @dataclass(frozen=True)
    class Reservation:
        provider_call_id: str = "provider-call-1"
        budget_ledger_id: str = "ledger-1"

    class Service:
        def __init__(self) -> None:
            self.sessions: list[int] = []
            self.reserved: dict[str, object] | None = None
            self.reconciled: dict[str, object] | None = None

        def reserve_provider_call(self, db: Session, **kwargs: object) -> Reservation:
            self.sessions.append(db.number)
            self.reserved = kwargs
            return Reservation()

        def mark_provider_call_sent(self, db: Session, **_kwargs: object) -> None:
            self.sessions.append(db.number)

        def reconcile_provider_call(self, db: Session, **kwargs: object) -> None:
            self.sessions.append(db.number)
            self.reconciled = kwargs

    class Provider:
        provider = "openai"
        model = "model-1"
        max_output_tokens: int | None = None

        def generate(
            self,
            _messages: list[dict[str, object]],
            *,
            max_output_tokens: int,
        ) -> str:
            self.max_output_tokens = max_output_tokens
            return '{"ok":true}'

    from ai_pdf_worker.research_executor import ApprovedResearchExecution

    execution = ApprovedResearchExecution(
        "workspace-1", "run-1", "execution-1", "a" * 64, "question", (),
        (FrozenAsset("asset-1", 1, 1),), "workflow-1", ("prompt-1",), "b" * 64,
        "budget-v1", "retry-v1", 1, 8, 8, None, 1000, 100, 1000,
    )
    service = Service()
    generation = LedgeredGeneration(factory, service, execution, Provider())

    result = generation.generate(
        StepLease("step-1", "attempt-1", 1, "lease-token"),
        node_key="researcher",
        messages=[{"role": "user", "content": "question"}],
    )

    assert result == '{"ok":true}'
    assert generation._provider.max_output_tokens == 100
    assert service.reserved is not None
    assert "reserved_cost_microunits" not in service.reserved
    assert service.reconciled is not None and service.reconciled["status"] == "succeeded"
    assert "actual_cost_microunits" not in service.reconciled
    assert len(service.sessions) == 3
    assert len(set(service.sessions)) == 3


def test_provider_mark_sent_failure_releases_the_reservation() -> None:
    factory = SessionFactory()

    @dataclass(frozen=True)
    class Reservation:
        provider_call_id: str = "provider-call-1"
        budget_ledger_id: str = "ledger-1"

    class Service:
        cancelled = False

        def reserve_provider_call(self, _db: Session, **_kwargs: object) -> Reservation:
            return Reservation()

        def mark_provider_call_sent(self, _db: Session, **_kwargs: object) -> None:
            raise RuntimeError("database unavailable")

        def cancel_provider_reservation(self, _db: Session, **_kwargs: object) -> None:
            self.cancelled = True

    class Provider:
        provider = "openai"
        model = "model-1"

        def generate(
            self,
            _messages: list[dict[str, object]],
            *,
            max_output_tokens: int,
        ) -> str:
            del max_output_tokens
            raise AssertionError("provider must not be called")

    from ai_pdf_worker.research_executor import ApprovedResearchExecution

    execution = ApprovedResearchExecution(
        "workspace-1", "run-1", "execution-1", "a" * 64, "question", (),
        (FrozenAsset("asset-1", 1, 1),), "workflow-1", ("prompt-1",), "b" * 64,
        "budget-v1", "retry-v1", 1, 8, 8, None, 1000, 100, 1000,
    )
    service = Service()
    generation = LedgeredGeneration(factory, service, execution, Provider())

    with pytest.raises(RuntimeError, match="database unavailable"):
        generation.generate(
            StepLease("step-1", "attempt-1", 1, "lease-token"),
            node_key="researcher",
            messages=[{"role": "user", "content": "question"}],
        )

    assert service.cancelled is True


def test_step_failure_uses_only_api_owned_retry_disposition() -> None:
    class Service:
        received: dict[str, object] | None = None

        def fail_research_step(self, _db: Session, **kwargs: object) -> dict[str, object]:
            self.received = kwargs
            return {
                "reasonCode": "provider_temporarily_unavailable",
                "retryable": True,
                "autoRequeued": True,
                "stepStatus": "queued",
                "runStatus": "running",
            }

    service = Service()
    adapter = SqlResearchLedgerAdapter(SessionFactory(), service, worker_instance_id="worker-1")
    disposition = adapter.step_failed(
        StepLease("step-1", "attempt-1", 1, "lease-token"),
        "generation_provider_error",
    )

    assert disposition.auto_requeued is True
    assert disposition.reason_code == "provider_temporarily_unavailable"
    assert service.received is not None
    assert service.received["error_code"] == "generation_provider_error"
    assert "retryable" not in service.received
    assert "message" not in service.received


def test_outer_claim_is_reused_without_a_second_lease() -> None:
    factory = SessionFactory()

    class Service:
        specific_calls = 0

        def claim_specific_research_step(self, _db: Session, **kwargs: object) -> dict[str, object]:
            self.specific_calls += 1
            return {
                "stepId": "step-2",
                "stepKey": kwargs["step_key"],
                "branchKey": kwargs["branch_key"],
                "runId": kwargs["run_id"],
                "workspaceId": "workspace-1",
                "attemptId": "attempt-2",
                "attemptNumber": 1,
                "leaseToken": "lease-2",
            }

    from ai_pdf_worker.research_executor import ApprovedResearchExecution

    execution = ApprovedResearchExecution(
        "workspace-1", "run-1", "execution-1", "a" * 64, "question", (),
        (FrozenAsset("asset-1", 1, 1),), "workflow-1", ("prompt-1",), "b" * 64,
        "budget-v1", "retry-v1", 1, 8, 8,
    )
    service = Service()
    adapter = SqlResearchLedgerAdapter(factory, service, worker_instance_id="worker-1")
    adapter.remember_claim(
        {
            "stepId": "step-1",
            "stepKey": "researcher:branch-1",
            "branchKey": "branch-1",
            "attemptId": "attempt-1",
            "attemptNumber": 1,
            "leaseToken": "lease-1",
        }
    )

    reused = adapter.claim_step(execution, step_key="researcher:branch-1", branch_key="branch-1")
    claimed = adapter.claim_step(execution, step_key="researcher:branch-2", branch_key="branch-2")

    assert reused.attempt_id == "attempt-1"
    assert claimed.attempt_id == "attempt-2"
    assert service.specific_calls == 1


def test_reclaim_runs_before_each_outer_claim() -> None:
    factory = SessionFactory()

    class Service:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def reclaim_expired_research_steps(self, _db: Session, **_kwargs: object) -> None:
            self.calls.append("reclaim")

        def claim_next_research_step(self, _db: Session, **_kwargs: object) -> None:
            self.calls.append("claim")

    service = Service()
    processor = ResearchWorkProcessor(factory, service, worker_instance_id="worker-1")

    assert processor.claim() is None
    assert service.calls == ["reclaim", "claim"]


def test_claimed_workspace_must_match_planning_payload() -> None:
    factory = SessionFactory()

    class Service:
        def reclaim_expired_research_steps(self, _db: Session, **_kwargs: object) -> None:
            return None

        def claim_next_research_step(self, _db: Session, **_kwargs: object) -> dict[str, object]:
            return {
                "workspaceId": "workspace-1",
                "runId": "run-1",
                "stepId": "step-1",
                "stepKey": "revision-1:planner",
                "stepKind": "planner",
                "branchKey": None,
                "attemptId": "attempt-1",
                "attemptNumber": 1,
                "leaseToken": "lease-1",
            }

        def load_planning_input(self, _db: Session, **_kwargs: object) -> dict[str, object]:
            return {"workspaceId": "workspace-2"}

    with pytest.raises(ResearchPortError, match="claimed_workspace_scope_mismatch"):
        ResearchWorkProcessor(factory, Service(), worker_instance_id="worker-1").process_one()


def test_worker_fair_lane_prefers_alternating_successful_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    class DbContext:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *_args: object) -> None:
            return None

    class Research:
        def process_one(self) -> bool:
            calls.append("research")
            return True

    calls: list[str] = []
    monkeypatch.setattr(worker_main, "SessionLocal", DbContext)
    monkeypatch.setattr(worker_main, "RESEARCH_PROCESSOR_FACTORY", Research)
    monkeypatch.setattr(worker_main, "_PREFER_RESEARCH", False)
    monkeypatch.setattr(worker_main, "_process_ingestion_job", lambda _db: calls.append("ingestion") or True)

    assert worker_main.process_one_job() is True
    assert worker_main.process_one_job() is True
    assert calls == ["ingestion", "research"]


def test_main_injects_sessionlocal_factory_into_research_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[object] = []

    class Processor:
        def __init__(self, sessions: object, _service: object, **_kwargs: object) -> None:
            captured.append(sessions)

        def process_one(self) -> bool:
            return True

    def session_factory() -> None:
        return None

    def fake_run_worker(**_kwargs: object) -> None:
        monkeypatch.setattr(worker_main, "_PREFER_RESEARCH", True)
        assert worker_main.process_one_job() is True

    monkeypatch.setattr(worker_main, "SessionLocal", session_factory)
    monkeypatch.setattr(worker_main, "ResearchWorkProcessor", Processor)
    monkeypatch.setattr(worker_main, "build_default_research_service", lambda: object())
    monkeypatch.setattr(worker_main, "run_worker", fake_run_worker)
    monkeypatch.setattr(worker_main, "start_metrics_server", lambda *_args: None)
    monkeypatch.setattr(worker_main, "_install_signal_handlers", lambda _event: None)

    worker_main.main()

    assert captured == [session_factory]


def test_research_lane_does_not_open_an_ingestion_session(monkeypatch: pytest.MonkeyPatch) -> None:
    class Research:
        def process_one(self) -> bool:
            return True

    def forbidden_session() -> None:
        raise AssertionError("Research must not hold an ingestion session")

    monkeypatch.setattr(worker_main, "SessionLocal", forbidden_session)
    monkeypatch.setattr(worker_main, "RESEARCH_PROCESSOR_FACTORY", Research)
    monkeypatch.setattr(worker_main, "_PREFER_RESEARCH", True)

    assert worker_main.process_one_job() is True


def test_api_research_worker_exposes_the_production_runtime_contract() -> None:
    from ai_pdf_api.services import research_worker

    required = {
        "cancel_provider_reservation",
        "claim_next_research_step",
        "claim_specific_research_step",
        "complete_control_step",
        "complete_research_branch",
        "complete_research_critique",
        "complete_research_synthesis",
        "complete_research_verification",
        "fail_research_step",
        "heartbeat_research_step",
        "load_approved_execution",
        "load_completed_branch",
        "load_conflict_resume_state",
        "load_execution_state",
        "load_frozen_evidence",
        "load_planning_input",
        "mark_provider_call_sent",
        "publish_final_report",
        "publish_research_plan",
        "reclaim_expired_research_steps",
        "reconcile_provider_call",
        "reserve_provider_call",
        "restore_frozen_evidence",
        "search_frozen_evidence",
        "wait_for_conflict_decision",
    }

    assert {name for name in required if not callable(getattr(research_worker, name, None))} == set()


def test_final_publish_rejects_noncanonical_uppercase_uuid() -> None:
    from ai_pdf_worker.research_executor import (
        ApprovedResearchExecution,
        SynthesisSelection,
    )

    class Service:
        published: dict[str, object] | None = None

        def publish_final_report(self, _db: Session, **_kwargs: object) -> str:
            self.published = dict(_kwargs)
            return "A3E8E1A4-0A7A-4A17-8CA8-6F8A4D130AA1"

    service = Service()
    adapter = SqlResearchLedgerAdapter(SessionFactory(), service, worker_instance_id="worker-1")
    execution = ApprovedResearchExecution(
        "workspace-1", "run-1", "execution-1", "a" * 64, "question", (),
        (FrozenAsset("asset-1", 1, 1),), "workflow-1", ("prompt-1",), "b" * 64,
        "budget-v1", "retry-v1", 1, 8, 8,
    )

    with pytest.raises(ResearchPortError, match="final_publish_identifier_invalid"):
        adapter.publish_final(
            StepLease("step-1", "attempt-1", 1, "lease-token"),
            execution,
            selection=SynthesisSelection((), ()),
            claims=(),
        )
    assert service.published is not None
    assert "report_bytes" not in service.published
