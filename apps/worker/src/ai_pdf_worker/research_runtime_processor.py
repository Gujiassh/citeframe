"""Production Research orchestration ports.

The worker owns orchestration and provider adapters.  The API owns the Research
ledger and the transaction boundaries.  This module deliberately contains no
SQLAlchemy model imports: a missing or incomplete API port is a hard failure.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from time import monotonic

from ai_pdf_api.core.research_observability import (
    observe_research_recovery,
    observe_research_step,
    research_log,
    research_run_finished,
    research_run_started,
    research_span,
)
from ai_pdf_api.services.providers import (
    GenerationProvider,
)

from ai_pdf_worker.research_executor import (
    ApprovedResearchExecution,
    BoundedResearchExecutor,
    StepLease,
)
from ai_pdf_worker.research_runtime_agents import GenerationResearchAgents
from ai_pdf_worker.research_runtime_core import (
    LEASE_SECONDS,
    ResearchPortError,
    ResearchWorkerService,
    SessionFactory,
    _ApiPort,
    _field,
    _lease,
    _now,
    _persist_step_failure,
    _planning_runtime_payload,
    logger,
)
from ai_pdf_worker.research_runtime_ports import (
    LedgeredGeneration,
    SqlEvidenceToolPort,
    SqlResearchLedgerAdapter,
)


@dataclass(frozen=True)
class ClaimedResearchWork:
    workspace_id: str
    step_key: str
    step_kind: str
    branch_key: str | None
    lease: StepLease
    run_id: str


class ResearchWorkProcessor(_ApiPort):
    """Claims and executes one Research step while preserving ingestion work."""

    def __init__(self, sessions: SessionFactory, service: ResearchWorkerService, *, worker_instance_id: str | None = None, provider: GenerationProvider | None = None) -> None:
        super().__init__(sessions, service)
        self._worker_instance_id = worker_instance_id or os.environ.get("AI_PDF_WORKER_INSTANCE_ID") or f"worker-{os.getpid()}"
        self._provider = provider

    def claim(self) -> ClaimedResearchWork | None:
        reclaimed = self._call(
            "reclaim_expired_research_steps",
            write=True,
            now=_now(),
        )
        if isinstance(reclaimed, int) and reclaimed > 0:
            observe_research_recovery("abandoned", reclaimed)
            observe_research_recovery("timeout", reclaimed)
            research_log(
                logger,
                tag="research_recovery",
                status="recovered",
                fields={"reclaimed_count": reclaimed},
            )
        result = self._call("claim_next_research_step", write=True, worker_instance_id=self._worker_instance_id, lease_seconds=LEASE_SECONDS, now=_now())
        if result is None:
            return None
        run_id = str(_field(result, "run_id"))
        step_key = str(_field(result, "step_key"))
        step_kind = str(_field(result, "step_kind"))
        workspace_id = str(_field(result, "workspace_id"))
        if not run_id or not step_key or not step_kind or not workspace_id:
            raise ResearchPortError("claimed_step_scope_invalid")
        lease = _lease(result)
        if lease.attempt_number > 1:
            observe_research_recovery("retry")
            observe_research_recovery("recovered")
        return ClaimedResearchWork(workspace_id, step_key, step_kind, _field(result, "branch_key"), lease, run_id)

    def process_one(self) -> bool:
        claimed = self.claim()
        if claimed is None:
            return False
        ledger = SqlResearchLedgerAdapter(self._sessions, self._service, worker_instance_id=self._worker_instance_id)
        with ledger._claimed_lock:
            ledger._claimed[(claimed.step_key, claimed.branch_key)] = claimed.lease
        run_attributes = {
            "research.run_id": claimed.run_id,
            "research.workspace_id": claimed.workspace_id,
            "research.step_id": claimed.lease.step_id,
            "research.attempt_id": claimed.lease.attempt_id,
            "research.step_kind": claimed.step_kind,
            "research.attempt_number": claimed.lease.attempt_number,
        }
        research_run_started()
        with research_span("research.run", run_attributes) as run_span:
            research_log(
                logger,
                tag="research_run",
                status="started",
                fields={
                    "run_id": claimed.run_id,
                    "workspace_id": claimed.workspace_id,
                    "step_id": claimed.lease.step_id,
                    "attempt_id": claimed.lease.attempt_id,
                    "step_kind": claimed.step_kind,
                    "attempt_number": claimed.lease.attempt_number,
                },
            )
            try:
                if claimed.step_kind == "planner":
                    self._process_planner(ledger, claimed)
                    run_outcome = "waiting"
                else:
                    execution = ledger.load_approved_execution(claimed.run_id)
                    if execution.workspace_id != claimed.workspace_id:
                        raise ResearchPortError("claimed_workspace_scope_mismatch")
                    generation = LedgeredGeneration(self._sessions, self._service, execution, self._provider, ledger)
                    agents = GenerationResearchAgents(generation)
                    executor = BoundedResearchExecutor(planner=agents.planner, researcher=agents.researcher, verifier=agents.verifier, critic=agents.critic, synthesizer=agents.synthesizer, evidence_tools=SqlEvidenceToolPort(self._sessions, self._service), ledger=ledger)
                    state = executor.execute(claimed.run_id)
                    run_outcome = "waiting" if state.get("status") == "awaiting_human_decision" else "success"
            except Exception as error:
                research_run_finished("error")
                research_log(
                    logger,
                    tag="research_run",
                    status="error",
                    level=logging.ERROR,
                    fields={
                        "run_id": claimed.run_id,
                        "workspace_id": claimed.workspace_id,
                        "step_id": claimed.lease.step_id,
                        "attempt_id": claimed.lease.attempt_id,
                        "step_kind": claimed.step_kind,
                        "attempt_number": claimed.lease.attempt_number,
                        "reason_code": type(error).__name__,
                    },
                )
                raise
            run_span.set_attributes({"research.outcome": run_outcome})
            research_run_finished(run_outcome)
            research_log(
                logger,
                tag="research_run",
                status="waiting" if run_outcome == "waiting" else "succeeded",
                fields={
                    "run_id": claimed.run_id,
                    "workspace_id": claimed.workspace_id,
                    "step_id": claimed.lease.step_id,
                    "attempt_id": claimed.lease.attempt_id,
                    "step_kind": claimed.step_kind,
                    "attempt_number": claimed.lease.attempt_number,
                },
            )
        return True

    def _process_planner(self, ledger: SqlResearchLedgerAdapter, claimed: ClaimedResearchWork) -> None:
        started = monotonic()
        attributes = {
            "research.run_id": claimed.run_id,
            "research.workspace_id": claimed.workspace_id,
            "research.step_id": claimed.lease.step_id,
            "research.attempt_id": claimed.lease.attempt_id,
            "research.step_kind": "planner",
            "research.attempt_number": claimed.lease.attempt_number,
        }
        with research_span("research.step", attributes) as step_span:
            research_log(
                logger,
                tag="research_step",
                status="started",
                fields={
                    "run_id": claimed.run_id,
                    "workspace_id": claimed.workspace_id,
                    "step_id": claimed.lease.step_id,
                    "attempt_id": claimed.lease.attempt_id,
                    "step_kind": "planner",
                    "attempt_number": claimed.lease.attempt_number,
                },
            )
            try:
                self._process_planner_inner(ledger, claimed)
            except Exception as error:
                duration = monotonic() - started
                observe_research_step("planner", "error", duration)
                research_log(
                    logger,
                    tag="research_step",
                    status="error",
                    level=logging.ERROR,
                    fields={
                        "run_id": claimed.run_id,
                        "workspace_id": claimed.workspace_id,
                        "step_id": claimed.lease.step_id,
                        "attempt_id": claimed.lease.attempt_id,
                        "step_kind": "planner",
                        "attempt_number": claimed.lease.attempt_number,
                        "reason_code": type(error).__name__,
                        "duration_ms": round(duration * 1000, 3),
                    },
                )
                raise
            duration = monotonic() - started
            step_span.set_attributes({"research.outcome": "waiting"})
            observe_research_step("planner", "waiting", duration)
            research_log(
                logger,
                tag="research_step",
                status="waiting",
                fields={
                    "run_id": claimed.run_id,
                    "workspace_id": claimed.workspace_id,
                    "step_id": claimed.lease.step_id,
                    "attempt_id": claimed.lease.attempt_id,
                    "step_kind": "planner",
                    "attempt_number": claimed.lease.attempt_number,
                    "duration_ms": round(duration * 1000, 3),
                },
            )

    def _process_planner_inner(self, ledger: SqlResearchLedgerAdapter, claimed: ClaimedResearchWork) -> None:
        raw_payload = self._call("load_planning_input", run_id=claimed.run_id)
        if str(_field(raw_payload, "workspace_id")) != claimed.workspace_id:
            raise ResearchPortError("claimed_workspace_scope_mismatch")
        payload = _planning_runtime_payload(raw_payload, run_id=claimed.run_id)
        assets = tuple(payload["frozen_assets"])
        execution = ApprovedResearchExecution(
            workspace_id=str(payload["workspace_id"]),
            run_id=claimed.run_id,
            execution_snapshot_id="planning",
            snapshot_sha256=str(payload["snapshot_sha256"]),
            question=str(payload["question"]),
            subproblems=(),
            frozen_assets=assets,
            workflow_version_id=str(payload["workflow_version_id"]),
            prompt_version_ids=(str(payload["planner_prompt_version_id"]),),
            provider_config_fingerprint=str(payload["provider_config_fingerprint"]),
            budget_policy_version=str(payload["budget_policy_version"]),
            retry_policy_version=str(payload["retry_policy_version"]),
            max_parallel_researchers=int(payload["max_parallel_researchers"]),
            max_provider_calls=int(payload["max_provider_calls"]),
            max_tool_calls=int(payload["max_tool_calls"]),
            plan_revision_id=str(payload["plan_revision_id"]),
            max_input_tokens=int(payload["max_input_tokens"]),
            max_output_tokens=int(payload["max_output_tokens"]),
            max_cost_microunits=int(payload["max_cost_microunits"]),
            prompts=tuple(payload["prompts"]),
        )
        generation = LedgeredGeneration(self._sessions, self._service, execution, self._provider, ledger)
        agents = GenerationResearchAgents(generation)
        try:
            drafts = BoundedResearchExecutor(planner=agents.planner, researcher=agents.researcher, verifier=agents.verifier, critic=agents.critic, synthesizer=agents.synthesizer, evidence_tools=SqlEvidenceToolPort(self._sessions, self._service), ledger=ledger).propose_plan(question=execution.question, frozen_assets=execution.frozen_assets, lease=claimed.lease)
            if agents.plan_summary is None or agents.plan_estimated_provider_calls is None:
                raise ResearchPortError("planner_metadata_missing")
            if agents.plan_estimated_provider_calls > int(payload["proposed_max_provider_calls"]):
                raise ResearchPortError("planner_estimate_exceeds_budget")
        except Exception as error:
            _persist_step_failure(ledger, claimed.lease, error)
            raise
        with research_span(
            "research.publish",
            {
                "research.run_id": claimed.run_id,
                "research.workspace_id": claimed.workspace_id,
                "research.step_id": claimed.lease.step_id,
                "research.attempt_id": claimed.lease.attempt_id,
                "research.node": "planner",
            },
        ):
            research_log(
                logger,
                tag="research_publish",
                status="started",
                fields={
                    "run_id": claimed.run_id,
                    "workspace_id": claimed.workspace_id,
                    "step_id": claimed.lease.step_id,
                    "attempt_id": claimed.lease.attempt_id,
                    "node": "planner",
                },
            )
            try:
                published = self._call("publish_research_plan", write=True, attempt_id=claimed.lease.attempt_id, lease_token=claimed.lease.lease_token, summary=agents.plan_summary, subproblems=drafts, known_gaps=agents.plan_known_gaps, estimated_provider_calls=agents.plan_estimated_provider_calls, now=_now())
            except Exception as error:
                research_log(
                    logger,
                    tag="research_publish",
                    status="error",
                    level=logging.ERROR,
                    fields={
                        "run_id": claimed.run_id,
                        "workspace_id": claimed.workspace_id,
                        "step_id": claimed.lease.step_id,
                        "attempt_id": claimed.lease.attempt_id,
                        "node": "planner",
                        "reason_code": type(error).__name__,
                    },
                )
                _persist_step_failure(ledger, claimed.lease, error)
                raise
            research_log(
                logger,
                tag="research_publish",
                status="succeeded",
                fields={
                    "run_id": claimed.run_id,
                    "workspace_id": claimed.workspace_id,
                    "step_id": claimed.lease.step_id,
                    "attempt_id": claimed.lease.attempt_id,
                    "node": "planner",
                },
            )
        artifact_id = str(_field(published, "artifact_id"))
        artifact_sha256 = str(_field(published, "artifact_sha256"))
        published_subproblems = _field(published, "subproblems")
        expected_bytes = json.dumps(
            {
                "estimatedCost": None,
                "estimatedInputTokens": None,
                "estimatedOutputTokens": None,
                "estimatedProviderCalls": agents.plan_estimated_provider_calls,
                "knownGaps": list(agents.plan_known_gaps),
                "subproblems": published_subproblems,
                "summary": agents.plan_summary,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if not artifact_id or hashlib.sha256(expected_bytes).hexdigest() != artifact_sha256 or len(published_subproblems) != len(drafts):
            raise ResearchPortError("plan_publish_integrity_mismatch")


def build_default_research_service() -> ResearchWorkerService:
    """Load the API port lazily so ingestion-only worker tests stay isolated."""

    from ai_pdf_api.services import research_worker

    return research_worker
