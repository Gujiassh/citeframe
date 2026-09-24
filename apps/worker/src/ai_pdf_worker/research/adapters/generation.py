from __future__ import annotations

import logging
from time import monotonic
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
from ai_pdf_api.services.research.research_agent_io_registry import (
    resolve_registry,
    resolve_role_contract,
)
from citeframe_contracts import ApprovedResearchExecution, FrozenPrompt, StepLease
from ai_pdf_worker.research.core import (
    ResearchPortError,
    ResearchWorkerService,
    SessionFactory,
    _ApiPort,
    _failure_code,
    _field,
    _hash_json,
    _now,
    _prompt_for,
    _token_estimate,
    lease_heartbeat,
    logger,
)
from ai_pdf_worker.research.adapters.ledger import SqlResearchLedgerAdapter


class LedgeredGeneration(_ApiPort):
    """Provider adapter that reserves and reconciles every external call."""

    def __init__(
        self,
        sessions: SessionFactory,
        service: ResearchWorkerService,
        execution: ApprovedResearchExecution,
        provider: GenerationProvider | None = None,
        ledger: SqlResearchLedgerAdapter | None = None,
    ) -> None:
        super().__init__(sessions, service)
        self._execution = execution
        self._resolved_models = None
        self._provider = provider
        self._provider_sessions = sessions
        self._ledger = ledger

    def _ensure_provider(self):
        if self._provider is None:
            from ai_pdf_api.services.workspace_models import resolve_workspace_models
            with self._provider_sessions() as db:
                self._resolved_models = resolve_workspace_models(db, self._execution.workspace_id)
            self._provider = get_generation_provider(self._resolved_models.generation)
        return self._provider

    @property
    def provider(self) -> str:
        return self._ensure_provider().provider

    @property
    def model(self) -> str:
        return self._ensure_provider().model

    @property
    def execution(self) -> ApprovedResearchExecution:
        return self._execution

    def conflict_turn(self, lease, operation, phase, request, result=None):
        return self._call("conflict_turn", write=True, attempt_id=lease.attempt_id,
            lease_token=lease.lease_token, operation_number=operation, phase=phase,
            request=request, result=result, now=_now())

    def adaptive_turn(self, lease: StepLease, turn: int, request: dict, result: dict | None = None):
        return self._call("adaptive_turn", write=True, attempt_id=lease.attempt_id,
                          lease_token=lease.lease_token, turn_number=turn,
                          request=request, result=result, now=_now())


    def generate(
        self, lease: StepLease, *, node_key: str, messages: list[GenerationMessage]
    ) -> str:
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

    def _generate(
        self, lease: StepLease, *, node_key: str, messages: list[GenerationMessage]
    ) -> str:
        self._ensure_provider()
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
                    user_payload = (
                        parsed if isinstance(parsed, dict) else {"content": raw_user}
                    )
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
            {"role": str(item["role"]), "content": item["content"]}
            for item in packed.messages
        ]
        request_sha256 = _hash_json(
            {
                "nodeKey": node_key,
                "messages": packed_messages,
                "maxOutputTokens": packed.max_output_tokens,
            }
        )
        reserved_input = packed.request_tokens
        reserved_output = max(1, packed.max_output_tokens)
        if self._resolved_models is not None:
            from ai_pdf_api.services.capabilities import connection_profile, matches_frozen_execution_fingerprint
            if self._provider.config_fingerprint != connection_profile(self._resolved_models.generation).config_fingerprint:
                raise ResearchPortError("research_provider_config_drift")
            if not matches_frozen_execution_fingerprint(self._execution.provider_config_fingerprint,
                    retrieval_top_k=self._execution.retrieval_top_k, models=self._resolved_models):
                raise ResearchPortError("research_provider_config_drift")
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
            self._call(
                "mark_provider_call_sent",
                write=True,
                provider_call_id=call_id,
                now=_now(),
            )
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
                status=(
                    "failed"
                    if failure_code == "research_provider_output_incomplete"
                    else "outcome_unknown"
                ),
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
            raise ResearchPortError(
                "research_agent_role_version_unavailable"
            ) from error
