from __future__ import annotations

import threading
from collections.abc import Mapping, Sequence
from typing import Any, Literal
from uuid import UUID
from citeframe_contracts import (
    ApprovedResearchExecution,
    BranchResult,
    DraftClaim,
    FailureDisposition,
    PublicationResult,
    ResearchLedger,
    ResearchState,
    StepLease,
    SynthesisSelection,
    VerifiedClaim,
)
from ai_pdf_worker.research.core import (
    LEASE_SECONDS,
    ResearchPortError,
    ResearchWorkerService,
    SessionFactory,
    VerificationRecord,
    _ApiPort,
    _evidence_handle,
    _field,
    _hash_json,
    _lease,
    _now,
    as_approved_execution,
)


class SqlResearchLedgerAdapter(_ApiPort, ResearchLedger):
    """Adapter over ``ai_pdf_api.services.research.research_worker``.

    The service module is injected to make the boundary explicit and to keep
    unit tests independent from a database.  No ORM object is accepted here.
    """

    def __init__(
        self,
        sessions: SessionFactory,
        service: ResearchWorkerService,
        *,
        worker_instance_id: str,
    ) -> None:
        super().__init__(sessions, service)
        self._worker_instance_id = worker_instance_id
        self._claimed: dict[tuple[str, str | None], StepLease] = {}
        self._claimed_lock = threading.Lock()

    def load_approved_execution(self, run_id: str) -> ApprovedResearchExecution:
        return as_approved_execution(
            self._call("load_approved_execution", run_id=run_id), expected_run_id=run_id
        )

    def load_execution_state(
        self, execution: ApprovedResearchExecution
    ) -> ResearchState | None:
        payload = self._call("load_execution_state", run_id=execution.run_id)
        if payload is None:
            return None
        return self._decode_execution_state(execution, payload)

    def load_step_handler_input(
        self,
        *,
        run_id: str,
        workspace_id: str,
        step_id: str,
        attempt_id: str,
        attempt_number: int,
        lease_token: str,
        step_key: str,
        step_kind: str,
        branch_key: str | None,
    ) -> tuple[ApprovedResearchExecution, ResearchState]:
        payload = self._call(
            "load_step_handler_input",
            run_id=run_id,
            step_id=step_id,
            attempt_id=attempt_id,
            lease_token=lease_token,
            now=_now(),
        )
        execution = as_approved_execution(
            _field(payload, "execution"),
            expected_run_id=run_id,
        )
        step = _field(payload, "step")
        attempt = _field(payload, "attempt")
        if (
            execution.workspace_id != workspace_id
            or str(_field(step, "id")) != step_id
            or str(_field(step, "key")) != step_key
            or str(_field(step, "kind")) != step_kind
            or _field(step, "branch_key") != branch_key
            or str(_field(attempt, "id")) != attempt_id
            or int(_field(attempt, "number")) != attempt_number
        ):
            raise ResearchPortError("claimed_step_scope_mismatch")
        state_payload = _field(payload, "state")
        state = self._decode_execution_state(execution, state_payload)
        if state is None:
            raise ResearchPortError("execution_state_missing")
        return execution, state

    def _decode_execution_state(
        self,
        execution: ApprovedResearchExecution,
        payload: Any,
    ) -> ResearchState:
        if isinstance(payload, Mapping):
            supplied = payload.get("execution")
            if (
                supplied is not None
                and as_approved_execution(supplied, expected_run_id=execution.run_id)
                != execution
            ):
                raise ResearchPortError("execution_state_scope_mismatch")
            completed = [str(item) for item in _field(payload, "completed_nodes")]
            state = ResearchState(
                execution=execution,
                completed_nodes=completed,
                status=str(_field(payload, "status")),
            )
            if "researchers" in completed:
                branches = [
                    self.load_completed_branch(execution, item.branch_key)
                    for item in execution.subproblems
                ]
                if any(item is None for item in branches):
                    raise ResearchPortError("execution_state_branch_missing")
                state["branch_results"] = [
                    item for item in branches if item is not None
                ]
                state["branch_timings"] = []
            claims_payload = _field(payload, "claims")
            if "verifier" in completed:
                state["verified_claims"] = [
                    VerifiedClaim(
                        str(_field(item, "id")),
                        str(_field(item, "text")),
                        tuple(
                            str(value) for value in _field(item, "evidence_handle_ids")
                        ),
                        _field(item, "verification_status"),
                        _field(item, "conflict_status"),
                    )
                    for item in claims_payload
                ]
            if "critic" in completed:
                state["conflicts"] = [
                    str(_field(item, "id"))
                    for item in claims_payload
                    if _field(item, "conflict_status") == "conflicted"
                ]
                state["unresolved"] = [
                    str(_field(item, "id"))
                    for item in claims_payload
                    if _field(item, "conflict_status") == "resolved_unresolved"
                ]
            selection = payload.get("synthesisSelection")
            if selection is not None:
                state["synthesis"] = SynthesisSelection(
                    tuple(str(item) for item in _field(selection, "fact_claim_ids")),
                    tuple(
                        str(item) for item in _field(selection, "unresolved_claim_ids")
                    ),
                )
            artifact_id = payload.get("finalArtifactId")
            if artifact_id is not None:
                state["artifact_id"] = str(artifact_id)
            return state
        raise ResearchPortError("execution_state_invalid")

    def load_conflict_resume_state(
        self,
        run_id: str,
        action: Literal["exclude_conflicted_claims", "keep_as_unresolved"],
    ) -> ResearchState:
        payload = self._call("load_conflict_resume_state", run_id=run_id, action=action)
        if (
            str(_field(_field(payload, "execution"), "run_id")) != run_id
            or _field(payload, "conflict_action") != action
        ):
            raise ResearchPortError("conflict_resume_scope_mismatch")
        execution = self.load_approved_execution(run_id)
        state = self.load_execution_state(execution)
        if state is None:
            raise ResearchPortError("conflict_resume_state_missing")
        return state

    def claim_step(
        self,
        execution: ApprovedResearchExecution,
        *,
        step_key: str,
        branch_key: str | None,
    ) -> StepLease:
        key = (step_key, branch_key)
        with self._claimed_lock:
            claimed = self._claimed.pop(key, None)
        if claimed is not None:
            return claimed
        result = self._call(
            "claim_specific_research_step",
            write=True,
            run_id=execution.run_id,
            step_key=step_key,
            branch_key=branch_key,
            worker_instance_id=self._worker_instance_id,
            lease_seconds=LEASE_SECONDS,
            now=_now(),
        )
        if result is None:
            raise ResearchPortError("step_not_claimable")
        if (
            str(_field(result, "run_id")) != execution.run_id
            or str(_field(result, "workspace_id")) != execution.workspace_id
            or str(_field(result, "step_key")) != step_key
            or _field(result, "branch_key") != branch_key
        ):
            raise ResearchPortError("claimed_step_scope_mismatch")
        lease = _lease(result)
        expected = next(
            (item for item in execution.subproblems if item.branch_key == branch_key),
            None,
        )
        if expected is not None and expected.step_id != lease.step_id:
            raise ResearchPortError("claimed_step_identifier_mismatch")
        return lease

    def remember_claim(self, result: Any) -> tuple[str, str | None]:
        lease = _lease(result)
        key = (str(_field(result, "step_key")), _field(result, "branch_key"))
        with self._claimed_lock:
            self._claimed[key] = lease
        return key

    def heartbeat(self, lease: StepLease) -> None:
        self._call(
            "heartbeat_research_step",
            write=True,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            lease_seconds=LEASE_SECONDS,
            now=_now(),
        )

    def complete_branch(self, lease: StepLease, result: BranchResult) -> None:
        self._call(
            "complete_research_branch",
            write=True,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            result=result,
            output_sha256=_hash_json(result),
            now=_now(),
        )

    def complete_control_step(self, lease: StepLease) -> None:
        self._call(
            "complete_control_step",
            write=True,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
        )

    def complete_verification(
        self, lease: StepLease, claims: Sequence[VerifiedClaim]
    ) -> None:
        self._call(
            "complete_research_verification",
            write=True,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            results=tuple(
                VerificationRecord(claim.id, claim.verification_status)
                for claim in claims
            ),
            now=_now(),
        )

    def complete_critique(
        self,
        lease: StepLease,
        claims: Sequence[VerifiedClaim],
        conflicts: Sequence[str],
    ) -> None:
        del claims
        self._call(
            "complete_research_critique",
            write=True,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            conflict_claim_ids=tuple(conflicts),
            now=_now(),
        )

    def wait_for_conflict_decision(
        self, lease: StepLease, conflicts: Sequence[str]
    ) -> None:
        self._call(
            "wait_for_conflict_decision",
            write=True,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            conflict_claim_ids=tuple(conflicts),
            now=_now(),
        )

    def complete_synthesis(
        self, lease: StepLease, selection: SynthesisSelection
    ) -> None:
        self._call(
            "complete_research_synthesis",
            write=True,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            fact_claim_ids=selection.fact_claim_ids,
            unresolved_claim_ids=selection.unresolved_claim_ids,
            now=_now(),
        )

    def step_failed(self, lease: StepLease, error_code: str) -> FailureDisposition:
        result = self._call(
            "fail_research_step",
            write=True,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            error_code=error_code,
            now=_now(),
        )
        disposition = FailureDisposition(
            reason_code=str(_field(result, "reason_code")),
            retryable=bool(_field(result, "retryable")),
            auto_requeued=bool(_field(result, "auto_requeued")),
            step_status=str(_field(result, "step_status")),
            run_status=str(_field(result, "run_status")),
        )
        if (
            not disposition.reason_code
            or disposition.auto_requeued
            != (disposition.retryable and disposition.step_status == "queued")
            or disposition.step_status not in {"queued", "failed", "cancelled"}
            or disposition.run_status
            not in {"planning", "running", "failed", "cancel_requested", "cancelled"}
        ):
            raise ResearchPortError("research_failure_disposition_invalid")
        return disposition

    def load_completed_branch(
        self, execution: ApprovedResearchExecution, branch_key: str
    ) -> BranchResult | None:
        payload = self._call(
            "load_completed_branch", run_id=execution.run_id, branch_key=branch_key
        )
        if payload is None:
            return None
        step_id = str(_field(payload, "step_id"))
        expected = next(
            (item for item in execution.subproblems if item.branch_key == branch_key),
            None,
        )
        if (
            expected is None
            or expected.step_id != step_id
            or str(_field(payload, "branch_key")) != branch_key
        ):
            raise ResearchPortError("completed_branch_scope_mismatch")
        branch_claims = _field(payload, "claims")
        rows = self._call(
            "restore_frozen_evidence",
            run_id=execution.run_id,
            execution_snapshot_id=execution.execution_snapshot_id,
            owner_step_id=step_id,
        )
        evidence = tuple(_evidence_handle(item) for item in rows)
        evidence_ids = {item.id for item in evidence}
        if evidence_ids != {
            str(item) for item in _field(payload, "evidence_handle_ids")
        }:
            raise ResearchPortError("completed_branch_evidence_scope_mismatch")
        if any(
            not {str(value) for value in _field(item, "evidence_handle_ids")}.issubset(
                evidence_ids
            )
            for item in branch_claims
        ):
            raise ResearchPortError("completed_branch_claim_scope_mismatch")
        return BranchResult(
            branch_key=branch_key,
            claims=tuple(
                DraftClaim(
                    str(_field(item, "id")),
                    str(_field(item, "text")),
                    tuple(str(value) for value in _field(item, "evidence_handle_ids")),
                )
                for item in branch_claims
            ),
            evidence=evidence,
        )

    def publish_final(
        self,
        lease: StepLease,
        execution: ApprovedResearchExecution,
        *,
        selection: SynthesisSelection,
        claims: Sequence[VerifiedClaim],
    ) -> PublicationResult:
        del execution, claims
        result = self._call_saga(
            "publish_final_report",
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            fact_claim_ids=selection.fact_claim_ids,
            unresolved_claim_ids=selection.unresolved_claim_ids,
            now=_now(),
        )
        if not isinstance(result, PublicationResult):
            try:
                result = PublicationResult(
                    kind=str(_field(result, "kind")),
                    artifact_id=_field(result, "artifact_id"),
                    intent_id=_field(result, "intent_id"),
                )
            except Exception as error:
                raise ResearchPortError("final_publish_result_invalid") from error
        identifier = result.artifact_id if result.kind == "committed" else result.intent_id
        if (
            result.kind not in {"committed", "reconcile_pending"}
            or not isinstance(identifier, str)
            or (result.kind == "committed") != (result.artifact_id is not None)
            or (result.kind == "reconcile_pending") != (result.intent_id is not None)
        ):
            raise ResearchPortError("final_publish_result_invalid")
        try:
            if str(UUID(identifier)) != identifier:
                raise ValueError
        except ValueError as error:
            raise ResearchPortError("final_publish_identifier_invalid") from error
        return result

    def _complete(
        self,
        lease: StepLease,
        *,
        output_sha256: str,
        evidence_count: int,
        artifact_ids: Sequence[str],
    ) -> None:
        if evidence_count or artifact_ids:
            raise ResearchPortError("research_atomic_completion_port_required")
        self._call(
            "complete_research_step",
            write=True,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            output_sha256=output_sha256,
            now=_now(),
        )
