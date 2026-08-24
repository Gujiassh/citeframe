"""Database-authoritative single-attempt Research step handlers."""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from time import monotonic

from ai_pdf_api.core.research_observability import observe_research_step, research_log, research_span
from ai_pdf_api.services.providers import GenerationProvider
from citeframe_contracts import (
    ApprovedResearchExecution,
    ResearchExecutionError,
    ResearchState,
    StepLease,
    SynthesisSelection,
    ToolExecutionContext,
    VerifiedClaim,
)

from ai_pdf_worker.research_executor_tools import EvidenceToolRegistry, _validate_claims
from ai_pdf_worker.research_runtime_agents import GenerationResearchAgents
from ai_pdf_worker.research_runtime_core import (
    ResearchPortError,
    ResearchWorkerService,
    SessionFactory,
    _persist_step_failure,
)
from ai_pdf_worker.research_runtime_ports import (
    LedgeredGeneration,
    SqlEvidenceToolPort,
    SqlResearchLedgerAdapter,
)


EXECUTION_STEP_KINDS = frozenset(
    {
        "researcher",
        "join",
        "verifier",
        "critic",
        "conflict_decision_gate",
        "synthesizer",
        "artifact_publisher",
    }
)
PERSISTED_STEP_KINDS = frozenset({"planner", "plan_approval_gate", *EXECUTION_STEP_KINDS})
HUMAN_OWNED_STEP_KINDS = frozenset({"plan_approval_gate"})

_REQUIRED_PREDECESSOR = {
    "join": "researchers",
    "verifier": "join",
    "critic": "verifier",
    "conflict_decision_gate": "critic",
    "synthesizer": "conflict_decision_gate",
    "artifact_publisher": "synthesizer",
}

logger = logging.getLogger("ai_pdf_worker.research_runtime")


class _StepObservation:
    outcome = "success"
    evidence_count = 0


@contextmanager
def _observed_step(
    execution: ApprovedResearchExecution,
    lease: StepLease,
    step_kind: str,
) -> Iterator[_StepObservation]:
    started = monotonic()
    fields = {
        "run_id": execution.run_id,
        "workspace_id": execution.workspace_id,
        "step_id": lease.step_id,
        "attempt_id": lease.attempt_id,
        "step_kind": step_kind,
        "attempt_number": lease.attempt_number,
    }
    observation = _StepObservation()
    with research_span(
        "research.step",
        {
            **{f"research.{key}": value for key, value in fields.items()},
            "research.execution_snapshot_id": execution.execution_snapshot_id,
        },
    ) as span:
        research_log(logger, tag="research_step", status="started", fields=fields)
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
                    **fields,
                    "reason_code": type(error).__name__,
                    "duration_ms": round(duration * 1000, 3),
                },
            )
            raise
        else:
            duration = monotonic() - started
            span.set_attributes({"research.outcome": observation.outcome})
            observe_research_step(
                step_kind,
                observation.outcome,
                duration,
                observation.evidence_count,
            )
            research_log(
                logger,
                tag="research_step",
                status="waiting" if observation.outcome == "waiting" else "succeeded",
                fields={**fields, "duration_ms": round(duration * 1000, 3)},
            )


class SingleAttemptStepDispatcher:
    """Execute only the handler associated with an already-claimed Attempt."""

    def __init__(
        self,
        sessions: SessionFactory,
        service: ResearchWorkerService,
        ledger: SqlResearchLedgerAdapter,
        *,
        provider: GenerationProvider | None,
    ) -> None:
        self._sessions = sessions
        self._service = service
        self._ledger = ledger
        self._provider = provider

    def execute(
        self,
        *,
        run_id: str,
        workspace_id: str,
        step_key: str,
        step_kind: str,
        branch_key: str | None,
        lease: StepLease,
    ) -> str:
        if step_kind not in PERSISTED_STEP_KINDS:
            raise ResearchPortError("unsupported_research_step_kind")
        if step_kind in HUMAN_OWNED_STEP_KINDS:
            raise ResearchPortError("human_owned_research_step_claimed")
        if step_kind not in EXECUTION_STEP_KINDS:
            raise ResearchPortError("unsupported_research_step_kind")

        execution, state = self._ledger.load_step_handler_input(
            run_id=run_id,
            workspace_id=workspace_id,
            step_id=lease.step_id,
            attempt_id=lease.attempt_id,
            attempt_number=lease.attempt_number,
            lease_token=lease.lease_token,
            step_key=step_key,
            step_kind=step_kind,
            branch_key=branch_key,
        )
        self._require_predecessor(state, step_kind)
        generation = LedgeredGeneration(
            self._sessions,
            self._service,
            execution,
            self._provider,
            self._ledger,
        )
        agents = GenerationResearchAgents(generation)

        handlers = {
            "researcher": self._researcher,
            "join": self._join,
            "verifier": self._verifier,
            "critic": self._critic,
            "conflict_decision_gate": self._conflict_gate,
            "synthesizer": self._synthesizer,
            "artifact_publisher": self._artifact_publisher,
        }
        with _observed_step(execution, lease, step_kind) as observation:
            outcome, evidence_count = handlers[step_kind](
                execution,
                state,
                agents,
                lease,
                branch_key,
            )
            observation.outcome = outcome
            observation.evidence_count = evidence_count
            return outcome

    @staticmethod
    def _require_predecessor(state: ResearchState, step_kind: str) -> None:
        predecessor = _REQUIRED_PREDECESSOR.get(step_kind)
        if predecessor is not None and predecessor not in state.get("completed_nodes", []):
            raise ResearchPortError("research_step_dependency_not_succeeded")

    def _researcher(
        self,
        execution: ApprovedResearchExecution,
        _state: ResearchState,
        agents: GenerationResearchAgents,
        lease: StepLease,
        branch_key: str | None,
    ) -> tuple[str, int]:
        subproblem = next(
            (item for item in execution.subproblems if item.branch_key == branch_key),
            None,
        )
        if subproblem is None or subproblem.step_id != lease.step_id:
            raise ResearchPortError("researcher_step_mismatch")
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
        tools = EvidenceToolRegistry(
            SqlEvidenceToolPort(self._sessions, self._service),
            context,
        )
        try:
            result = agents.researcher(subproblem, tools, lease)
            tools.validate_branch_result(result)
        except Exception as error:
            _persist_step_failure(self._ledger, lease, error)
            raise
        self._ledger.complete_branch(lease, result)
        return "success", len(result.evidence)

    def _join(
        self,
        _execution: ApprovedResearchExecution,
        _state: ResearchState,
        _agents: GenerationResearchAgents,
        lease: StepLease,
        _branch_key: str | None,
    ) -> tuple[str, int]:
        self._ledger.complete_control_step(lease)
        return "success", 0

    def _verifier(
        self,
        _execution: ApprovedResearchExecution,
        state: ResearchState,
        agents: GenerationResearchAgents,
        lease: StepLease,
        _branch_key: str | None,
    ) -> tuple[str, int]:
        branches = state.get("branch_results")
        if branches is None:
            raise ResearchPortError("research_branch_state_missing")
        claims = [claim for branch in branches for claim in branch.claims]
        evidence = [item for branch in branches for item in branch.evidence]
        try:
            _validate_claims(claims, {item.id for item in evidence})
            verified = list(agents.verifier(claims, evidence, lease))
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
        return "success", len(evidence)

    def _critic(
        self,
        _execution: ApprovedResearchExecution,
        state: ResearchState,
        agents: GenerationResearchAgents,
        lease: StepLease,
        _branch_key: str | None,
    ) -> tuple[str, int]:
        claims = state.get("verified_claims")
        if claims is None:
            raise ResearchPortError("research_verified_claim_state_missing")
        try:
            conflicts = list(agents.critic(claims, lease))
            supported_ids = {
                claim.id for claim in claims if claim.verification_status == "supported"
            }
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
        return "success", 0

    def _conflict_gate(
        self,
        _execution: ApprovedResearchExecution,
        state: ResearchState,
        _agents: GenerationResearchAgents,
        lease: StepLease,
        _branch_key: str | None,
    ) -> tuple[str, int]:
        conflicts = state.get("conflicts")
        if conflicts is None:
            raise ResearchPortError("research_conflict_state_missing")
        if conflicts:
            self._ledger.wait_for_conflict_decision(lease, conflicts)
            return "waiting", 0
        self._ledger.complete_control_step(lease)
        return "success", 0

    def _synthesizer(
        self,
        execution: ApprovedResearchExecution,
        state: ResearchState,
        agents: GenerationResearchAgents,
        lease: StepLease,
        _branch_key: str | None,
    ) -> tuple[str, int]:
        claims = state.get("verified_claims")
        if claims is None:
            raise ResearchPortError("research_verified_claim_state_missing")
        publishable = [
            claim
            for claim in claims
            if claim.verification_status == "supported" and claim.conflict_status == "none"
        ]
        unresolved = [
            claim
            for claim in claims
            if claim.verification_status == "supported"
            and claim.conflict_status == "resolved_unresolved"
        ]
        try:
            selection = agents.synthesizer(
                execution.question,
                publishable,
                unresolved,
                lease,
            )
            self._validate_selection(selection, publishable, unresolved)
        except Exception as error:
            _persist_step_failure(self._ledger, lease, error)
            raise
        self._ledger.complete_synthesis(lease, selection)
        return "success", 0

    def _artifact_publisher(
        self,
        execution: ApprovedResearchExecution,
        state: ResearchState,
        _agents: GenerationResearchAgents,
        lease: StepLease,
        _branch_key: str | None,
    ) -> tuple[str, int]:
        selection = state.get("synthesis")
        claims = state.get("verified_claims")
        if selection is None or claims is None:
            raise ResearchPortError("research_synthesis_checkpoint_missing")
        try:
            self._ledger.publish_final(
                lease,
                execution,
                selection=selection,
                claims=claims,
            )
        except Exception as error:
            _persist_step_failure(self._ledger, lease, error)
            raise
        return "success", 0

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
