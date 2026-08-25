"""Production Research orchestration ports.

The worker owns orchestration and provider adapters.  The API owns the Research
ledger and the transaction boundaries.  This module deliberately contains no
SQLAlchemy model imports: a missing or incomplete API port is a hard failure.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Mapping, Sequence
from time import monotonic
from typing import Any, Literal
from uuid import UUID

from ai_pdf_api.core.research_observability import (
    observe_research_provider,
    research_log,
    research_span,
)
from ai_pdf_api.services.providers import (
    GenerationMessage,
    GenerationProvider,
    get_generation_provider,
)
from ai_pdf_api.services.research.research_context_policy import (
    ResearchContextLimitExceeded,
    ResearchProviderOutputIncomplete,
    assert_provider_output_complete,
    pack_provider_messages,
)
from ai_pdf_api.services.research.research_agent_io_registry import resolve_registry, resolve_role_contract

from citeframe_contracts import (
    ApprovedResearchExecution,
    BranchResult,
    DraftClaim,
    EvidenceHandle,
    EvidenceToolPort,
    FailureDisposition,
    FrozenPrompt,
    LoadedEvidence,
    ResearchLedger,
    ResearchState,
    StepLease,
    SynthesisSelection,
    ToolExecutionContext,
    VerifiedClaim,
)
from ai_pdf_worker.research_runtime_core import (
    LEASE_SECONDS,
    ResearchPortError,
    ResearchWorkerService,
    SessionFactory,
    VerificationRecord,
    _ApiPort,
    _evidence_handle,
    _failure_code,
    _field,
    _hash_json,
    _lease,
    _loaded_evidence,
    _now,
    _observed_tool,
    _prompt_for,
    _token_estimate,
    as_approved_execution,
    lease_heartbeat,
    logger,
)


class SqlResearchLedgerAdapter(_ApiPort, ResearchLedger):
    """Adapter over ``ai_pdf_api.services.research.research_worker``.

    The service module is injected to make the boundary explicit and to keep
    unit tests independent from a database.  No ORM object is accepted here.
    """

    def __init__(self, sessions: SessionFactory, service: ResearchWorkerService, *, worker_instance_id: str) -> None:
        super().__init__(sessions, service)
        self._worker_instance_id = worker_instance_id
        self._claimed: dict[tuple[str, str | None], StepLease] = {}
        self._claimed_lock = threading.Lock()

    def load_approved_execution(self, run_id: str) -> ApprovedResearchExecution:
        return as_approved_execution(self._call("load_approved_execution", run_id=run_id), expected_run_id=run_id)

    def load_execution_state(self, execution: ApprovedResearchExecution) -> ResearchState | None:
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
            if supplied is not None and as_approved_execution(supplied, expected_run_id=execution.run_id) != execution:
                raise ResearchPortError("execution_state_scope_mismatch")
            completed = [str(item) for item in _field(payload, "completed_nodes")]
            state = ResearchState(execution=execution, completed_nodes=completed, status=str(_field(payload, "status")))
            if "researchers" in completed:
                branches = [self.load_completed_branch(execution, item.branch_key) for item in execution.subproblems]
                if any(item is None for item in branches):
                    raise ResearchPortError("execution_state_branch_missing")
                state["branch_results"] = [item for item in branches if item is not None]
                state["branch_timings"] = []
            claims_payload = _field(payload, "claims")
            if "verifier" in completed:
                state["verified_claims"] = [
                    VerifiedClaim(
                        str(_field(item, "id")),
                        str(_field(item, "text")),
                        tuple(str(value) for value in _field(item, "evidence_handle_ids")),
                        _field(item, "verification_status"),
                        _field(item, "conflict_status"),
                    )
                    for item in claims_payload
                ]
            if "critic" in completed:
                state["conflicts"] = [str(_field(item, "id")) for item in claims_payload if _field(item, "conflict_status") == "conflicted"]
                state["unresolved"] = [str(_field(item, "id")) for item in claims_payload if _field(item, "conflict_status") == "resolved_unresolved"]
            selection = payload.get("synthesisSelection")
            if selection is not None:
                state["synthesis"] = SynthesisSelection(tuple(str(item) for item in _field(selection, "fact_claim_ids")), tuple(str(item) for item in _field(selection, "unresolved_claim_ids")))
            artifact_id = payload.get("finalArtifactId")
            if artifact_id is not None:
                state["artifact_id"] = str(artifact_id)
            return state
        raise ResearchPortError("execution_state_invalid")

    def load_conflict_resume_state(self, run_id: str, action: Literal["exclude_conflicted_claims", "keep_as_unresolved"]) -> ResearchState:
        payload = self._call("load_conflict_resume_state", run_id=run_id, action=action)
        if str(_field(_field(payload, "execution"), "run_id")) != run_id or _field(payload, "conflict_action") != action:
            raise ResearchPortError("conflict_resume_scope_mismatch")
        execution = self.load_approved_execution(run_id)
        state = self.load_execution_state(execution)
        if state is None:
            raise ResearchPortError("conflict_resume_state_missing")
        return state

    def claim_step(self, execution: ApprovedResearchExecution, *, step_key: str, branch_key: str | None) -> StepLease:
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
        expected = next((item for item in execution.subproblems if item.branch_key == branch_key), None)
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
        self._call("heartbeat_research_step", write=True, attempt_id=lease.attempt_id, lease_token=lease.lease_token, lease_seconds=LEASE_SECONDS, now=_now())

    def complete_branch(self, lease: StepLease, result: BranchResult) -> None:
        self._call("complete_research_branch", write=True, attempt_id=lease.attempt_id, lease_token=lease.lease_token, result=result, output_sha256=_hash_json(result), now=_now())

    def complete_control_step(self, lease: StepLease) -> None:
        self._call("complete_control_step", write=True, attempt_id=lease.attempt_id, lease_token=lease.lease_token)

    def complete_verification(self, lease: StepLease, claims: Sequence[VerifiedClaim]) -> None:
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

    def complete_critique(self, lease: StepLease, claims: Sequence[VerifiedClaim], conflicts: Sequence[str]) -> None:
        del claims
        self._call("complete_research_critique", write=True, attempt_id=lease.attempt_id, lease_token=lease.lease_token, conflict_claim_ids=tuple(conflicts), now=_now())

    def wait_for_conflict_decision(self, lease: StepLease, conflicts: Sequence[str]) -> None:
        self._call("wait_for_conflict_decision", write=True, attempt_id=lease.attempt_id, lease_token=lease.lease_token, conflict_claim_ids=tuple(conflicts), now=_now())

    def complete_synthesis(self, lease: StepLease, selection: SynthesisSelection) -> None:
        self._call("complete_research_synthesis", write=True, attempt_id=lease.attempt_id, lease_token=lease.lease_token, fact_claim_ids=selection.fact_claim_ids, unresolved_claim_ids=selection.unresolved_claim_ids, now=_now())

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
            or disposition.auto_requeued != (
                disposition.retryable and disposition.step_status == "queued"
            )
            or disposition.step_status not in {"queued", "failed", "cancelled"}
            or disposition.run_status
            not in {"planning", "running", "failed", "cancel_requested", "cancelled"}
        ):
            raise ResearchPortError("research_failure_disposition_invalid")
        return disposition

    def load_completed_branch(self, execution: ApprovedResearchExecution, branch_key: str) -> BranchResult | None:
        payload = self._call("load_completed_branch", run_id=execution.run_id, branch_key=branch_key)
        if payload is None:
            return None
        step_id = str(_field(payload, "step_id"))
        expected = next((item for item in execution.subproblems if item.branch_key == branch_key), None)
        if expected is None or expected.step_id != step_id or str(_field(payload, "branch_key")) != branch_key:
            raise ResearchPortError("completed_branch_scope_mismatch")
        branch_claims = _field(payload, "claims")
        rows = self._call("restore_frozen_evidence", run_id=execution.run_id, execution_snapshot_id=execution.execution_snapshot_id, owner_step_id=step_id)
        evidence = tuple(_evidence_handle(item) for item in rows)
        evidence_ids = {item.id for item in evidence}
        if evidence_ids != {str(item) for item in _field(payload, "evidence_handle_ids")}:
            raise ResearchPortError("completed_branch_evidence_scope_mismatch")
        if any(
            not {str(value) for value in _field(item, "evidence_handle_ids")}.issubset(evidence_ids)
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
    ) -> str:
        del execution, claims
        result = self._call(
            "publish_final_report",
            write=True,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            fact_claim_ids=selection.fact_claim_ids,
            unresolved_claim_ids=selection.unresolved_claim_ids,
            now=_now(),
        )
        artifact_id = str(result)
        try:
            if str(UUID(artifact_id)) != artifact_id:
                raise ValueError
        except ValueError as error:
            raise ResearchPortError("final_publish_identifier_invalid") from error
        return artifact_id

    def _complete(self, lease: StepLease, *, output_sha256: str, evidence_count: int, artifact_ids: Sequence[str]) -> None:
        if evidence_count or artifact_ids:
            raise ResearchPortError("research_atomic_completion_port_required")
        self._call("complete_research_step", write=True, attempt_id=lease.attempt_id, lease_token=lease.lease_token, output_sha256=output_sha256, now=_now())


class SqlEvidenceToolPort(_ApiPort, EvidenceToolPort):
    """Evidence-only port backed by frozen API retrieval and handle ledgers."""

    def __init__(self, sessions: SessionFactory, service: ResearchWorkerService) -> None:
        super().__init__(sessions, service)

    def restore_handles(self, context: ToolExecutionContext) -> Sequence[EvidenceHandle]:
        rows = self._call("restore_frozen_evidence", run_id=context.run_id, execution_snapshot_id=context.execution_snapshot_id, owner_step_id=context.step_id)
        handles = tuple(_evidence_handle(item) for item in rows)
        self._validate_handles(context, handles)
        return handles

    def search(self, context: ToolExecutionContext, *, tool_call_key: str, query: str, asset_ids: Sequence[str], top_k: int) -> Sequence[EvidenceHandle]:
        with _observed_tool(context, "evidence.search") as observation:
            rows = self._call("search_frozen_evidence", write=True, run_id=context.run_id, execution_snapshot_id=context.execution_snapshot_id, step_id=context.step_id, attempt_id=context.attempt_id, branch_key=context.branch_key, tool_call_key=tool_call_key, query=query, asset_ids=tuple(asset_ids), top_k=top_k, now=_now())
            handles = tuple(_evidence_handle(item) for item in rows)
            self._validate_handles(context, handles)
            observation.evidence_count = len(handles)
            return handles

    def load(self, context: ToolExecutionContext, *, tool_call_key: str, handle_ids: Sequence[str]) -> Sequence[LoadedEvidence]:
        with _observed_tool(context, "evidence.load") as observation:
            rows = self._call("load_frozen_evidence", write=True, run_id=context.run_id, execution_snapshot_id=context.execution_snapshot_id, step_id=context.step_id, attempt_id=context.attempt_id, branch_key=context.branch_key, tool_call_key=tool_call_key, evidence_handle_ids=tuple(handle_ids), now=_now())
            items = tuple(_loaded_evidence(item) for item in rows)
            if [item.evidence_handle for item in items] != list(handle_ids):
                raise ResearchPortError("evidence_load_order_mismatch")
            observation.evidence_count = len(items)
            return items

    @staticmethod
    def _validate_handles(context: ToolExecutionContext, handles: Sequence[EvidenceHandle]) -> None:
        frozen = {item.asset_id: item for item in context.frozen_assets}
        for handle in handles:
            asset = frozen.get(handle.asset_id)
            if (
                handle.workspace_id != context.workspace_id
                or handle.run_id != context.run_id
                or handle.execution_snapshot_id != context.execution_snapshot_id
                or handle.owner_step_id != context.step_id
                or handle.branch_key != context.branch_key
                or asset is None
                or handle.processing_generation != asset.processing_generation
                or handle.index_version != asset.index_version
                or len(handle.source_fingerprint_sha256) != 64
                or not handle.created_by_tool_call_id
            ):
                raise ResearchPortError("evidence_handle_scope_mismatch")


class LedgeredGeneration(_ApiPort):
    """Provider adapter that reserves and reconciles every external call."""

    def __init__(self, sessions: SessionFactory, service: ResearchWorkerService, execution: ApprovedResearchExecution, provider: GenerationProvider | None = None, ledger: SqlResearchLedgerAdapter | None = None) -> None:
        super().__init__(sessions, service)
        self._execution = execution
        self._provider = provider or get_generation_provider()
        self._ledger = ledger

    @property
    def provider(self) -> str:
        return self._provider.provider

    @property
    def model(self) -> str:
        return self._provider.model

    @property
    def execution(self) -> ApprovedResearchExecution:
        return self._execution

    def generate(self, lease: StepLease, *, node_key: str, messages: list[GenerationMessage]) -> str:
        started = monotonic()
        attributes = {
            "research.run_id": self._execution.run_id,
            "research.workspace_id": self._execution.workspace_id,
            "research.execution_snapshot_id": self._execution.execution_snapshot_id,
            "research.step_id": lease.step_id,
            "research.attempt_id": lease.attempt_id,
            "research.node": node_key,
            "research.attempt_number": lease.attempt_number,
        }
        with research_span("research.provider", attributes) as span:
            research_log(
                logger,
                tag="research_provider",
                status="started",
                fields={
                    "run_id": self._execution.run_id,
                    "workspace_id": self._execution.workspace_id,
                    "step_id": lease.step_id,
                    "attempt_id": lease.attempt_id,
                    "node": node_key,
                    "attempt_number": lease.attempt_number,
                },
            )
            try:
                output = self._generate(lease, node_key=node_key, messages=messages)
            except Exception as error:
                duration = monotonic() - started
                observe_research_provider(node_key, "error", duration)
                research_log(
                    logger,
                    tag="research_provider",
                    status="error",
                    level=logging.ERROR,
                    fields={
                        "run_id": self._execution.run_id,
                        "workspace_id": self._execution.workspace_id,
                        "step_id": lease.step_id,
                        "attempt_id": lease.attempt_id,
                        "node": node_key,
                        "attempt_number": lease.attempt_number,
                        "reason_code": type(error).__name__,
                        "duration_ms": round(duration * 1000, 3),
                    },
                )
                raise
            input_tokens, output_tokens = _token_estimate(messages, output)
            duration = monotonic() - started
            span.set_attributes(
                {
                    "research.input_tokens": input_tokens,
                    "research.output_tokens": output_tokens,
                }
            )
            observe_research_provider(
                node_key,
                "success",
                duration,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            research_log(
                logger,
                tag="research_provider",
                status="succeeded",
                fields={
                    "run_id": self._execution.run_id,
                    "workspace_id": self._execution.workspace_id,
                    "step_id": lease.step_id,
                    "attempt_id": lease.attempt_id,
                    "node": node_key,
                    "attempt_number": lease.attempt_number,
                    "duration_ms": round(duration * 1000, 3),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            )
            return output

    def _generate(self, lease: StepLease, *, node_key: str, messages: list[GenerationMessage]) -> str:
        # Enforce frozen production/legacy registry for this execution snapshot.
        try:
            registry = resolve_registry(
                agent_result_schema_version=self._execution.agent_result_schema_version,
                context_policy_version=self._execution.context_policy_version,
                compact_policy_version=self._execution.compact_policy_version,
                for_new_run=False,
            )
            role = resolve_role_contract(registry, node_key)
            expected_adapter = (
                "research-runtime-adapter.legacy-v0"
                if registry.agent_result_schema_version.endswith("legacy-v0")
                else "research-runtime-adapter.v1"
            )
            if role.runtime_adapter_key != expected_adapter:
                raise ValueError("runtime adapter mapping mismatch")
        except ValueError as error:
            raise ResearchPortError("research_agent_io_version_unavailable") from error

        system_text = ""
        user_payload: dict[str, object] = {}
        if messages and messages[0].get("role") == "system":
            system_text = str(messages[0].get("content") or "")
        if len(messages) > 1 and messages[1].get("role") == "user":
            raw_user = messages[1].get("content")
            if isinstance(raw_user, str):
                import json
                try:
                    parsed = json.loads(raw_user)
                    user_payload = parsed if isinstance(parsed, dict) else {"content": raw_user}
                except json.JSONDecodeError:
                    user_payload = {"content": raw_user}
            elif isinstance(raw_user, dict):
                user_payload = raw_user
            else:
                user_payload = {"content": raw_user}

        try:
            packed = pack_provider_messages(
                system_text=system_text,
                user_payload=user_payload,
                max_input_tokens=max(1, self._execution.max_input_tokens),
                max_output_tokens=max(1, self._execution.max_output_tokens),
                context_policy_version=self._execution.context_policy_version,
                compact_policy_version=self._execution.compact_policy_version,
            )
        except ResearchContextLimitExceeded as error:
            raise ResearchPortError("research_context_limit_exceeded") from error

        packed_messages: list[GenerationMessage] = [
            {"role": str(item["role"]), "content": item["content"]} for item in packed.messages
        ]
        request_sha256 = _hash_json({"nodeKey": node_key, "messages": packed_messages, "maxOutputTokens": packed.max_output_tokens})
        reserved_input = packed.request_tokens
        reserved_output = max(1, packed.max_output_tokens)
        reservation = self._call(
            "reserve_provider_call",
            write=True,
            attempt_id=lease.attempt_id,
            logical_call_key=f"{node_key}:{request_sha256}",
            request_sha256=request_sha256,
            provider=self.provider,
            model=self.model,
            provider_config_fingerprint=self._execution.provider_config_fingerprint,
            reserved_input_tokens=reserved_input,
            reserved_output_tokens=reserved_output,
            now=_now(),
        )
        call_id = str(_field(reservation, "provider_call_id"))
        if not call_id or not str(_field(reservation, "budget_ledger_id")):
            raise ResearchPortError("provider_reservation_invalid")
        try:
            self._call("mark_provider_call_sent", write=True, provider_call_id=call_id, now=_now())
        except Exception:
            self._call(
                "cancel_provider_reservation",
                write=True,
                provider_call_id=call_id,
                now=_now(),
            )
            raise
        try:
            # The frozen per-call output cap is part of the provider contract.
            # A provider adapter that cannot accept it is a hard failure; never
            # retry without the cap.
            if self._ledger is None:
                output = self._provider.generate(
                    packed_messages,
                    max_output_tokens=reserved_output,
                )
            else:
                with lease_heartbeat(self._ledger, lease):
                    output = self._provider.generate(
                        packed_messages,
                        max_output_tokens=reserved_output,
                    )
        except Exception as error:
            failure_code = _failure_code(error)
            self._call(
                "reconcile_provider_call",
                write=True,
                provider_call_id=call_id,
                status=("failed" if failure_code == "research_provider_output_incomplete" else "outcome_unknown"),
                error_code=failure_code,
                actual_input_tokens=reserved_input,
                actual_output_tokens=reserved_output,
                usage_source="estimated",
                usage_final=False,
                now=_now(),
            )
            raise
        try:
            assert_provider_output_complete(output, max_output_tokens=reserved_output)
        except ResearchProviderOutputIncomplete as error:
            self._call(
                "reconcile_provider_call",
                write=True,
                provider_call_id=call_id,
                status="failed",
                error_code="research_provider_output_incomplete",
                actual_input_tokens=reserved_input,
                actual_output_tokens=reserved_output,
                usage_source="estimated",
                usage_final=False,
                now=_now(),
            )
            raise ResearchPortError("research_provider_output_incomplete") from error
        input_tokens, output_tokens = _token_estimate(packed_messages, output)
        if input_tokens > reserved_input or output_tokens > reserved_output:
            self._call(
                "reconcile_provider_call",
                write=True,
                provider_call_id=call_id,
                status="failed",
                error_code="research_provider_output_incomplete",
                actual_input_tokens=reserved_input,
                actual_output_tokens=reserved_output,
                usage_source="estimated",
                usage_final=False,
                now=_now(),
            )
            raise ResearchPortError("research_provider_output_incomplete")
        self._call(
            "reconcile_provider_call",
            write=True,
            provider_call_id=call_id,
            status="succeeded",
            actual_input_tokens=input_tokens,
            actual_output_tokens=output_tokens,
            usage_source="estimated",
            usage_final=False,
            now=_now(),
        )
        return output

    def prompt(self, node_key: str) -> FrozenPrompt:
        try:
            registry = resolve_registry(
                agent_result_schema_version=self._execution.agent_result_schema_version,
                context_policy_version=self._execution.context_policy_version,
                compact_policy_version=self._execution.compact_policy_version,
                for_new_run=False,
            )
            role = resolve_role_contract(registry, node_key)
            prompt = _prompt_for(self._execution, node_key)
            if (
                prompt.node_key != role.prompt_node_key
                or prompt.prompt_key != role.prompt_key
            ):
                raise ValueError("prompt mapping mismatch")
            return prompt
        except ValueError as error:
            raise ResearchPortError("research_agent_role_version_unavailable") from error
