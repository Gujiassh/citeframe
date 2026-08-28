"""Budget accounting and terminal-transition races for the R2 harness."""

from __future__ import annotations

import time
from datetime import timedelta
from typing import Any

from citeframe_persistence.models import (
    ResearchBudgetLedger,
    ResearchEvent,
    ResearchExecutionSnapshot,
    ResearchProviderCall,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
    ResearchStepDependency,
    ResearchToolCall,
)
from citeframe_research_persistence.errors import ResearchError
from citeframe_research_persistence.provider import (
    mark_provider_call_sent,
    reserve_provider_call,
)
from citeframe_research_persistence.tools import begin_tool_call
from sqlalchemy import select, text

from .accounting_actor import (
    AccountingChild,
    finish_accounting_child,
    spawn_accounting_child,
    wait_accounting_ready,
)
from .common import PROCESS_TIMEOUT_SECONDS, error_json, sha, utcnow


class AccountingScenarios:
    """Real-process accounting and terminal-transition scenarios for ``R2Harness``."""

    def _wait_accounting_blocked(
        self,
        postgres_pid: int,
        blocker_pid: int,
        *,
        label: str,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + PROCESS_TIMEOUT_SECONDS
        last = None
        while time.monotonic() < deadline:
            last = self.base.activity(postgres_pid)
            if (
                last is not None
                and last["wait_event_type"] == "Lock"
                and blocker_pid in list(last["blocking_pids"] or [])
            ):
                return last
            time.sleep(0.02)
        raise AssertionError(
            f"accounting child did not block label={label} "
            f"postgres_pid={postgres_pid} blocker_pid={blocker_pid} activity={last}"
        )

    def _capture_accounting_locks(self) -> list[dict[str, Any]]:
        with self.base.monitor_engine.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    text(
                        "SELECT a.pid, a.application_name, a.wait_event_type, a.wait_event, "
                        "pg_blocking_pids(a.pid) AS blocking_pids, l.locktype, l.mode, l.granted, "
                        "CASE WHEN l.relation IS NULL THEN NULL ELSE l.relation::regclass::text END AS relation "
                        "FROM pg_stat_activity a JOIN pg_locks l ON l.pid=a.pid "
                        "WHERE a.application_name LIKE 'citeframe-r2:r2-accounting-%' "
                        "ORDER BY a.pid,l.granted,l.locktype,l.mode,relation"
                    )
                ).mappings()
            ]

    def _run_gated_accounting_pair(
        self,
        *,
        label: str,
        gate_table: str,
        gate_row_id: str,
        first: tuple[str, str, dict[str, Any]],
        second: tuple[str, str, dict[str, Any]],
    ) -> dict[str, Any]:
        gate_name = f"citeframe-r0:r2-{label}:gate"
        gate = self.r0_module.RowGate(
            self.base,
            gate_name,
            gate_table,
            gate_row_id,
        )
        children: list[AccountingChild] = []
        first_blocked = None
        second_blocked = None
        lock_sample = None
        stage_error: BaseException | None = None
        try:
            first_child = spawn_accounting_child(self, *first)
            children.append(first_child)
            first_ready = wait_accounting_ready(first_child)
            first_child.barrier_path.touch()
            first_blocked = self._wait_accounting_blocked(
                first_ready["postgresPid"],
                gate.pid,
                label=f"{label}:first-on-gate",
            )

            second_child = spawn_accounting_child(self, *second)
            children.append(second_child)
            second_ready = wait_accounting_ready(second_child)
            second_child.barrier_path.touch()
            second_blocked = self._wait_accounting_blocked(
                second_ready["postgresPid"],
                first_ready["postgresPid"],
                label=f"{label}:second-on-first",
            )
            lock_sample = self._capture_accounting_locks()
        except BaseException as error:  # noqa: BLE001 - reap children before surfacing proof failure
            stage_error = error
        finally:
            for child in children:
                child.barrier_path.touch(exist_ok=True)
            gate.release()

        results = []
        finish_error: BaseException | None = None
        for child in children:
            try:
                results.append(finish_accounting_child(self, child))
            except BaseException as error:  # noqa: BLE001 - finish every sibling before failing
                if finish_error is None:
                    finish_error = error
        if stage_error is not None:
            raise stage_error
        if finish_error is not None:
            raise finish_error
        if len(results) != 2:
            raise AssertionError(f"accounting pair did not start two children: {label}")
        process_isolation = (
            len({row["pid"] for row in results}) == 2
            and len({row["postgresPid"] for row in results}) == 2
        )
        return {
            "processes": results,
            "processIsolation": process_isolation,
            "firstBlocked": first_blocked,
            "secondBlocked": second_blocked,
            "lockSample": lock_sample,
        }

    @staticmethod
    def _iso(value: Any) -> str | None:
        return value.isoformat() if value is not None else None

    def _accounting_snapshot(self, run_id: str) -> dict[str, Any]:
        with self.sessions() as db:
            run = db.get(ResearchRun, run_id)
            steps = list(
                db.scalars(
                    select(ResearchStep)
                    .where(ResearchStep.run_id == run_id)
                    .order_by(ResearchStep.id)
                )
            )
            attempts = list(
                db.scalars(
                    select(ResearchStepAttempt)
                    .join(ResearchStep, ResearchStep.id == ResearchStepAttempt.step_id)
                    .where(ResearchStep.run_id == run_id)
                    .order_by(ResearchStepAttempt.id)
                )
            )
            ledger = db.scalar(
                select(ResearchBudgetLedger).where(
                    ResearchBudgetLedger.run_id == run_id
                )
            )
            provider_calls = list(
                db.scalars(
                    select(ResearchProviderCall)
                    .where(ResearchProviderCall.run_id == run_id)
                    .order_by(ResearchProviderCall.id)
                )
            )
            tool_calls = list(
                db.scalars(
                    select(ResearchToolCall)
                    .where(ResearchToolCall.run_id == run_id)
                    .order_by(ResearchToolCall.id)
                )
            )
            events = list(
                db.scalars(
                    select(ResearchEvent)
                    .where(ResearchEvent.run_id == run_id)
                    .order_by(ResearchEvent.seq)
                )
            )
            dependencies = list(
                db.execute(
                    select(
                        ResearchStepDependency.step_id,
                        ResearchStepDependency.depends_on_step_id,
                    )
                    .join(
                        ResearchStep, ResearchStep.id == ResearchStepDependency.step_id
                    )
                    .where(ResearchStep.run_id == run_id)
                    .order_by(
                        ResearchStepDependency.step_id,
                        ResearchStepDependency.depends_on_step_id,
                    )
                )
            )
            return {
                "run": None
                if run is None
                else {
                    "id": run.id,
                    "status": run.status,
                    "stateVersion": run.state_version,
                    "nextEventSeq": run.next_event_seq,
                    "finishedAt": self._iso(run.finished_at),
                    "updatedAt": self._iso(run.updated_at),
                },
                "steps": [
                    {
                        "id": row.id,
                        "status": row.status,
                        "stateVersion": row.state_version,
                        "currentAttemptNumber": row.current_attempt_number,
                        "finishedAt": self._iso(row.finished_at),
                        "updatedAt": self._iso(row.updated_at),
                    }
                    for row in steps
                ],
                "attempts": [
                    {
                        "id": row.id,
                        "stepId": row.step_id,
                        "status": row.status,
                        "providerCallCount": row.provider_call_count,
                        "toolCallCount": row.tool_call_count,
                        "inputTokens": row.input_tokens,
                        "outputTokens": row.output_tokens,
                        "finishedAt": self._iso(row.finished_at),
                    }
                    for row in attempts
                ],
                "ledger": None
                if ledger is None
                else {
                    "stateVersion": ledger.state_version,
                    "reservedProviderCalls": ledger.reserved_provider_calls,
                    "actualProviderCalls": ledger.actual_provider_calls,
                    "reservedToolCalls": ledger.reserved_tool_calls,
                    "actualToolCalls": ledger.actual_tool_calls,
                    "reservedInputTokens": ledger.reserved_input_tokens,
                    "reservedOutputTokens": ledger.reserved_output_tokens,
                    "actualInputTokens": ledger.actual_input_tokens,
                    "actualOutputTokens": ledger.actual_output_tokens,
                    "usageFinal": ledger.usage_final,
                    "updatedAt": self._iso(ledger.updated_at),
                },
                "providerCalls": [
                    {
                        "id": row.id,
                        "status": row.status,
                        "sendAttempt": row.send_attempt,
                        "actualInputTokens": row.actual_input_tokens,
                        "actualOutputTokens": row.actual_output_tokens,
                        "usageSource": row.usage_source,
                        "usageFinal": row.usage_final,
                        "finishedAt": self._iso(row.finished_at),
                    }
                    for row in provider_calls
                ],
                "toolCalls": [
                    {
                        "id": row.id,
                        "status": row.status,
                        "callAttemptNumber": row.call_attempt_number,
                        "resultCount": row.result_count,
                        "finishedAt": self._iso(row.finished_at),
                    }
                    for row in tool_calls
                ],
                "events": [
                    {
                        "seq": row.seq,
                        "type": row.event_type,
                        "stepId": row.step_id,
                        "attemptId": row.attempt_id,
                        "dedupeKey": row.dedupe_key,
                    }
                    for row in events
                ],
                "dependencies": [
                    {"stepId": row.step_id, "dependsOnStepId": row.depends_on_step_id}
                    for row in dependencies
                ],
            }

    def scenario_provider_budget_exactly_once(self) -> dict[str, Any]:
        fixture = self.seed_run("r2-provider-budget")
        with self.sessions() as db:
            snapshot = db.get(ResearchExecutionSnapshot, fixture.snapshot_id)
            snapshot.max_provider_calls = 1
            profile = {
                "provider": snapshot.generation_provider,
                "model": snapshot.generation_model,
                "fingerprint": snapshot.provider_config_fingerprint,
            }
            db.commit()
        lease = self.base.claim_specific(fixture, 0, "r2-provider-budget-owner")
        with self.sessions() as db:
            reservation = reserve_provider_call(
                db,
                attempt_id=lease.attempt_id,
                logical_call_key="r2-provider-budget:first",
                request_sha256=sha("r2-provider-budget:first-request"),
                provider=profile["provider"],
                model=profile["model"],
                provider_config_fingerprint=profile["fingerprint"],
                reserved_input_tokens=11,
                reserved_output_tokens=13,
                now=utcnow(),
                provider_config_matcher=lambda _db, _step, _fingerprint: True,
            )
            mark_provider_call_sent(db, reservation.provider_call_id, now=utcnow())
            db.commit()

        reconciled_at = utcnow()
        action = {
            "actualInputTokens": 7,
            "actualOutputTokens": 5,
            "now": reconciled_at.isoformat(),
            "providerCallId": reservation.provider_call_id,
            "providerResponseIdHash": sha("r2-provider-budget:response"),
        }
        race = self._run_gated_accounting_pair(
            label="provider",
            gate_table="research_provider_calls",
            gate_row_id=reservation.provider_call_id,
            first=("provider-first", "provider_reconcile", action),
            second=("provider-second", "provider_reconcile", action),
        )
        after_reconcile = self._accounting_snapshot(fixture.run_id)
        before_second_reservation = after_reconcile
        with self.sessions() as db:
            try:
                reserve_provider_call(
                    db,
                    attempt_id=lease.attempt_id,
                    logical_call_key="r2-provider-budget:second",
                    request_sha256=sha("r2-provider-budget:second-request"),
                    provider=profile["provider"],
                    model=profile["model"],
                    provider_config_fingerprint=profile["fingerprint"],
                    reserved_input_tokens=1,
                    reserved_output_tokens=1,
                    now=utcnow(),
                    provider_config_matcher=lambda _db, _step, _fingerprint: True,
                )
            except ResearchError as error:
                second_reservation_error = error_json(error)
                db.rollback()
            else:
                second_reservation_error = None
                db.rollback()
        after_second_reservation = self._accounting_snapshot(fixture.run_id)
        compact = self.snapshot(fixture.run_id)
        oracle = self.event_oracle(compact)
        outcomes = [row["outcome"] for row in race["processes"]]
        errors = [row.get("error", {}).get("code") for row in race["processes"]]
        ledger = after_reconcile["ledger"]
        attempt = after_reconcile["attempts"][0]
        exactly_once = (
            outcomes == ["success", "error"]
            and errors == [None, "research_state_conflict"]
            and len(after_reconcile["providerCalls"]) == 1
            and after_reconcile["providerCalls"][0]["status"] == "succeeded"
            and ledger["reservedProviderCalls"] == 0
            and ledger["actualProviderCalls"] == 1
            and ledger["reservedInputTokens"] == 0
            and ledger["reservedOutputTokens"] == 0
            and ledger["actualInputTokens"] == 7
            and ledger["actualOutputTokens"] == 5
            and attempt["providerCallCount"] == 1
            and attempt["inputTokens"] == 7
            and attempt["outputTokens"] == 5
        )
        zero_mutation = before_second_reservation == after_second_reservation
        passed = (
            race["processIsolation"]
            and exactly_once
            and second_reservation_error is not None
            and second_reservation_error.get("code") == "research_budget_limit"
            and zero_mutation
            and all(oracle.values())
        )
        return {
            "status": "pass" if passed else "fail",
            "processRace": race,
            "exactlyOnce": exactly_once,
            "secondReservation": {
                "error": second_reservation_error,
                "zeroMutation": zero_mutation,
            },
            "eventOracle": oracle,
            "snapshot": after_second_reservation,
        }

    def scenario_tool_completion_vs_lease_reclaim(self) -> dict[str, Any]:
        fixture = self.seed_run("r2-tool-accounting")
        lease = self.base.claim_specific(fixture, 0, "r2-tool-accounting-owner")
        with self.sessions() as db:
            reservation = begin_tool_call(
                db,
                attempt_id=lease.attempt_id,
                tool_call_key="r2-tool-accounting:call",
                tool_name="evidence.search",
                request_sha256=sha("r2-tool-accounting:request"),
                now=utcnow(),
            )
            db.commit()
        reclaim_at = utcnow()
        with self.sessions() as db:
            attempt = db.get(ResearchStepAttempt, lease.attempt_id)
            attempt.lease_expires_at = reclaim_at - timedelta(seconds=1)
            db.commit()

        race = self._run_gated_accounting_pair(
            label="tool",
            gate_table="research_tool_calls",
            gate_row_id=reservation.tool_call_id,
            first=(
                "tool-reclaim",
                "lease_reclaim",
                {"now": reclaim_at.isoformat()},
            ),
            second=(
                "tool-complete",
                "tool_complete",
                {
                    "now": (reclaim_at + timedelta(milliseconds=1)).isoformat(),
                    "toolCallId": reservation.tool_call_id,
                },
            ),
        )
        state = self._accounting_snapshot(fixture.run_id)
        compact = self.snapshot(fixture.run_id)
        oracle = self.event_oracle(compact)
        reclaim, completion = race["processes"]
        ledger = state["ledger"]
        attempt = state["attempts"][0]
        abandoned_events = [
            row
            for row in state["events"]
            if row["type"] == "attempt_abandoned"
            and row["attemptId"] == lease.attempt_id
        ]
        exactly_once = (
            reclaim["outcome"] == "success"
            and reclaim.get("reclaimed") == 1
            and completion["outcome"] == "error"
            and completion.get("error", {}).get("code") == "research_state_conflict"
            and len(state["toolCalls"]) == 1
            and state["toolCalls"][0]["status"] == "abandoned"
            and ledger["reservedToolCalls"] == 0
            and ledger["actualToolCalls"] == 1
            and attempt["status"] == "abandoned"
            and attempt["toolCallCount"] == 1
            and len(abandoned_events) == 1
        )
        passed = race["processIsolation"] and exactly_once and all(oracle.values())
        return {
            "status": "pass" if passed else "fail",
            "processRace": race,
            "terminalOutcomeExactlyOnce": exactly_once,
            "eventOracle": oracle,
            "snapshot": state,
        }

    def scenario_step_completion_vs_cancel(self) -> dict[str, Any]:
        fixture = self.base.seed_run("r2-step-cancel", step_count=2)
        owner_step_id, dependent_step_id = fixture.step_ids
        with self.sessions() as db:
            dependent = db.get(ResearchStep, dependent_step_id)
            dependent.status = "pending"
            dependent.queued_at = None
            db.add(
                ResearchStepDependency(
                    step_id=dependent_step_id,
                    depends_on_step_id=owner_step_id,
                )
            )
            db.commit()
        self.seed_queued_events(fixture, step_ids={owner_step_id})
        lease = self.base.claim_specific(fixture, 0, "r2-step-cancel-owner")
        with self.sessions() as db:
            expected_run_version = db.get(ResearchRun, fixture.run_id).state_version
        race_at = utcnow()
        race = self._run_gated_accounting_pair(
            label="step-cancel",
            gate_table="research_steps",
            gate_row_id=dependent_step_id,
            first=(
                "step-complete",
                "step_complete",
                {
                    "attemptId": lease.attempt_id,
                    "leaseToken": lease.lease_token,
                    "now": race_at.isoformat(),
                },
            ),
            second=(
                "run-cancel",
                "cancel_run",
                {
                    "actorRole": "owner",
                    "actorUserId": self.base.user_id,
                    "expectedRunStateVersion": expected_run_version,
                    "now": (race_at + timedelta(milliseconds=1)).isoformat(),
                    "reasonCode": "user_requested",
                    "runId": fixture.run_id,
                    "workspaceId": self.base.workspace_id,
                },
            ),
        )
        state = self._accounting_snapshot(fixture.run_id)
        compact = self.snapshot(fixture.run_id)
        oracle = self.event_oracle(compact)
        completion, cancellation = race["processes"]
        steps = {row["id"]: row for row in state["steps"]}
        parent_terminal = [
            row
            for row in state["events"]
            if row["type"] == "step_succeeded" and row["stepId"] == owner_step_id
        ]
        dependent_queued = [
            row
            for row in state["events"]
            if row["type"] == "step_queued" and row["stepId"] == dependent_step_id
        ]
        cancel_events = [
            row for row in state["events"] if row["type"] == "cancel_requested"
        ]
        single_winner = (
            completion["outcome"] == "success"
            and cancellation["outcome"] == "error"
            and cancellation.get("error", {}).get("code") == "stale_state_version"
        )
        single_mutation = (
            state["run"]["status"] == "running"
            and steps[owner_step_id]["status"] == "succeeded"
            and steps[dependent_step_id]["status"] == "queued"
            and state["attempts"][0]["status"] == "succeeded"
            and len(parent_terminal) == 1
            and len(dependent_queued) == 1
            and not cancel_events
            and state["dependencies"]
            == [
                {
                    "stepId": dependent_step_id,
                    "dependsOnStepId": owner_step_id,
                }
            ]
        )
        passed = (
            race["processIsolation"]
            and single_winner
            and single_mutation
            and all(oracle.values())
        )
        return {
            "status": "pass" if passed else "fail",
            "processRace": race,
            "singleWinnerLoserFenced": single_winner,
            "terminalAndDependentMutationExactlyOnce": single_mutation,
            "eventOracle": oracle,
            "snapshot": state,
        }


__all__ = ("AccountingScenarios",)
