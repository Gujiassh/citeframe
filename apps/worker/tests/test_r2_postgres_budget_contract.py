"""Source and adversarial pure-oracle contracts for the R2-L PostgreSQL proof."""

from __future__ import annotations

import copy
import importlib.util
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCENARIO = ROOT / "infra/scripts/r2_scenario_l_budget.py"
WORKER = ROOT / "infra/scripts/r2_scenario_l_worker.py"
PROVIDER_REQUEST_SHA = "1" * 64
TOOL_REQUEST_SHA = "2" * 64


def load_scenario():
    spec = importlib.util.spec_from_file_location("r2_l_budget_contract", SCENARIO)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def valid_state() -> dict[str, object]:
    state = {
        "run": {"id": "run", "workspace_id": "ws", "created_by_user_id": "actor", "status": "running"},
        "snapshots": [{"id": "snapshot", "workspace_id": "ws", "run_id": "run", "max_provider_calls": 2, "max_tool_calls": 2}],
        "steps": [{"id": "step", "workspace_id": "ws", "run_id": "run", "execution_snapshot_id": "snapshot", "step_kind": "researcher", "branch_key": "branch", "status": "running"}],
        "attempts": [{"id": "attempt", "workspace_id": "ws", "step_id": "step", "attempt_number": 1, "status": "running", "provider_call_count": 1, "tool_call_count": 1, "input_tokens": 4, "output_tokens": 3, "cost_microunits": 55}],
        "budgetLedgers": [{"id": "ledger", "workspace_id": "ws", "run_id": "run", "plan_revision_id": None, "execution_snapshot_id": "snapshot", "reserved_provider_calls": 0, "actual_provider_calls": 1, "reserved_tool_calls": 0, "actual_tool_calls": 1, "reserved_input_tokens": 0, "actual_input_tokens": 4, "reserved_output_tokens": 0, "actual_output_tokens": 3, "reserved_cost_microunits": 0, "actual_cost_microunits": 55, "usage_final": True}],
        "providerCalls": [{"id": "provider", "workspace_id": "ws", "run_id": "run", "budget_ledger_id": "ledger", "step_id": "step", "attempt_id": "attempt", "status": "succeeded", "reserved_input_tokens": 9, "reserved_output_tokens": 8, "reserved_cost_microunits": 143, "actual_input_tokens": 4, "actual_output_tokens": 3, "actual_cost_microunits": 55, "usage_source": "actual", "usage_final": True, "error_code": None}],
        "toolCalls": [{"id": "tool", "workspace_id": "ws", "run_id": "run", "execution_snapshot_id": "snapshot", "step_id": "step", "attempt_id": "attempt", "status": "succeeded", "error_code": None}],
        "events": [
            {"workspace_id": "ws", "run_id": "run", "seq": 1, "event_type": "run_status_changed", "event_schema_version": "1", "step_id": None, "attempt_id": None, "dedupe_key": "worker-run-started:attempt", "payload_json": {"previousStatus": "queued", "status": "running", "runStateVersion": 2, "reasonCode": None}},
            {"workspace_id": "ws", "run_id": "run", "seq": 2, "event_type": "step_started", "event_schema_version": "1", "step_id": "step", "attempt_id": "attempt", "dedupe_key": "step-started:attempt", "payload_json": {"stepId": "step", "stepKind": "researcher", "branchKey": "branch", "attemptId": "attempt", "attemptNumber": 1, "stepStateVersion": 2, "runStateVersion": 3}},
        ],
    }
    state["run"].update(
        state_version=3,
        next_event_seq=3,
        cost_currency="USD",
        failure_code=None,
        failure_message=None,
        cancel_reason_code=None,
        cancel_requested_at=None,
        finished_at=None,
    )
    state["snapshots"][0]["cost_currency"] = "USD"
    state["snapshots"][0].update(
        generation_provider="openai",
        generation_model="gpt-5.5",
        provider_config_fingerprint="f" * 64,
    )
    state["steps"][0].update(
        state_version=2,
        current_attempt_number=1,
        error_code=None,
        error_message=None,
        finished_at=None,
    )
    state["attempts"][0].update(
        error_code=None,
        error_message=None,
        started_at="2026-01-01T00:00:00+00:00",
        finished_at=None,
        lease_expires_at="2026-01-01T00:10:00+00:00",
    )
    state["budgetLedgers"][0].update(
        currency="USD",
        state_version=6,
        updated_at="2026-01-01T00:04:00+00:00",
    )
    state["providerCalls"][0].update(
        logical_call_key="provider-key",
        provider="openai",
        model="gpt-5.5",
        provider_config_fingerprint="f" * 64,
        request_sha256=PROVIDER_REQUEST_SHA,
        send_attempt=1,
        reserved_at="2026-01-01T00:01:00+00:00",
        sent_at="2026-01-01T00:02:00+00:00",
        finished_at="2026-01-01T00:03:00+00:00",
    )
    state["toolCalls"][0].update(
        tool_call_key="tool-key",
        tool_name="evidence.search",
        tool_version=1,
        request_sha256=TOOL_REQUEST_SHA,
        call_attempt_number=1,
        call_order=0,
        created_at="2026-01-01T00:01:00+00:00",
        started_at="2026-01-01T00:01:00+00:00",
        finished_at="2026-01-01T00:02:00+00:00",
        error_message=None,
    )
    return state


def oracle(scenario, state):
    return scenario.accounting_oracle(
        state,
        expected_provider_statuses=["succeeded"],
        expected_tool_statuses=["succeeded"],
        expected_attempt_status="running",
        expected_run_status="running",
        event_mode="active",
        expected_provider_requests={"provider-key": PROVIDER_REQUEST_SHA},
        expected_tool_requests={"tool-key": TOOL_REQUEST_SHA},
    )


def cancel_state() -> dict[str, object]:
    state = valid_state()
    state["run"].update(status="cancelled", state_version=6, next_event_seq=6, finished_at="2026-01-01T00:08:00+00:00", cancel_reason_code="user_requested", cancel_requested_at="2026-01-01T00:07:00+00:00")
    state["steps"][0].update(status="cancelled", state_version=3, error_code="lease_expired", error_message="expired", finished_at="2026-01-01T00:08:00+00:00")
    state["attempts"][0].update(status="abandoned", provider_call_count=0, tool_call_count=0, input_tokens=0, output_tokens=0, cost_microunits=0, error_code="lease_expired", error_message="expired", finished_at="2026-01-01T00:08:00+00:00", lease_expires_at=None)
    state["providerCalls"] = []
    state["toolCalls"] = []
    state["budgetLedgers"][0].update(actual_provider_calls=0, actual_tool_calls=0, actual_input_tokens=0, actual_output_tokens=0, actual_cost_microunits=0, state_version=1)
    state["events"].extend([
        {"workspace_id": "ws", "run_id": "run", "seq": 3, "event_type": "cancel_requested", "event_schema_version": "1", "step_id": None, "attempt_id": None, "dedupe_key": "cancel-requested:4", "payload_json": {"actorUserId": "actor", "reasonCode": "user_requested", "runStateVersion": 4}},
        {"workspace_id": "ws", "run_id": "run", "seq": 4, "event_type": "attempt_abandoned", "event_schema_version": "1", "step_id": "step", "attempt_id": "attempt", "dedupe_key": "attempt-abandoned:attempt", "payload_json": {"stepId": "step", "attemptId": "attempt", "attemptNumber": 1, "reasonCode": "lease_expired", "stepStateVersion": 3, "runStateVersion": 5}},
        {"workspace_id": "ws", "run_id": "run", "seq": 5, "event_type": "run_cancelled", "event_schema_version": "1", "step_id": None, "attempt_id": None, "dedupe_key": "run-cancelled:run", "payload_json": {"status": "cancelled", "reasonCode": "user_requested", "runStateVersion": 6}},
    ])
    return state


def requeue_state() -> dict[str, object]:
    state = valid_state()
    state["run"].update(state_version=5, next_event_seq=5)
    state["steps"][0].update(status="queued", state_version=4, error_code="lease_expired", error_message="expired", finished_at=None)
    state["attempts"][0].update(status="abandoned", provider_call_count=0, input_tokens=0, output_tokens=0, cost_microunits=0, error_code="lease_expired", error_message="expired", finished_at="2026-01-01T00:08:00+00:00", lease_expires_at=None)
    state["providerCalls"] = []
    state["toolCalls"][0].update(status="abandoned", error_code="lease_expired", error_message="expired", finished_at="2026-01-01T00:08:00+00:00")
    state["budgetLedgers"][0].update(actual_provider_calls=0, actual_input_tokens=0, actual_output_tokens=0, actual_cost_microunits=0, state_version=3)
    state["events"].extend([
        {"workspace_id": "ws", "run_id": "run", "seq": 3, "event_type": "attempt_abandoned", "event_schema_version": "1", "step_id": "step", "attempt_id": "attempt", "dedupe_key": "attempt-abandoned:attempt", "payload_json": {"stepId": "step", "attemptId": "attempt", "attemptNumber": 1, "reasonCode": "lease_expired", "stepStateVersion": 3, "runStateVersion": 4}},
        {"workspace_id": "ws", "run_id": "run", "seq": 4, "event_type": "step_queued", "event_schema_version": "1", "step_id": "step", "attempt_id": None, "dedupe_key": "step-queued:step:1", "payload_json": {"stepId": "step", "stepKind": "researcher", "branchKey": "branch", "attemptNumber": 1, "stepStateVersion": 4, "runStateVersion": 5}},
    ])
    return state


def test_process_isolated_production_transitions_and_short_claim() -> None:
    scenario_source = SCENARIO.read_text(encoding="utf-8")
    worker = WORKER.read_text(encoding="utf-8")
    for production_call in ("claim_specific_research_step(", "reserve_provider_call(", "mark_provider_call_sent(", "cancel_provider_reservation(", "reconcile_provider_call(", "begin_tool_call(", "complete_tool_call(", "cancel_research_run_transition(", "reclaim_expired_research_steps("):
        assert production_call in worker
    assert "subprocess.Popen(" in scenario_source
    assert 'environment["CITEFRAME_R2_DATABASE_URL"] = database_url' in scenario_source
    assert '"--database-url"' not in scenario_source + worker
    assert '"leaseToken"' not in worker
    assert "session_replication_role" not in scenario_source + worker


def test_runtime_entrypoint_and_exact_source_boundary() -> None:
    scenario = load_scenario()
    assert list(inspect.signature(scenario.run_scenario).parameters) == ["runtime", "database_url", "timeout_seconds"]
    assert len(scenario.PRODUCTION_SOURCE_FILES) == 17
    assert set(scenario.PRODUCTION_SOURCE_FILES) == {
        "packages/research-persistence/src/citeframe_research_persistence/provider.py", "packages/research-persistence/src/citeframe_research_persistence/tools.py", "packages/research-persistence/src/citeframe_research_persistence/state.py", "packages/research-persistence/src/citeframe_research_persistence/cancellation.py", "packages/research-persistence/src/citeframe_research_persistence/lease.py", "packages/research-persistence/src/citeframe_research_persistence/locks.py", "packages/research-persistence/src/citeframe_research_persistence/events.py", "packages/research-persistence/src/citeframe_research_persistence/errors.py", "packages/research-persistence/src/citeframe_research_persistence/membership.py", "packages/research-persistence/src/citeframe_research_persistence/policy.py", "packages/research-persistence/src/citeframe_research_persistence/types.py", "packages/research-persistence/src/citeframe_research_persistence/constants.py", "packages/backend-persistence/src/citeframe_persistence/models/__init__.py", "packages/backend-persistence/src/citeframe_persistence/models/research_execution.py", "packages/backend-persistence/src/citeframe_persistence/models/research_run.py", "packages/backend-persistence/src/citeframe_persistence/models/workspace.py", "packages/backend-persistence/src/citeframe_persistence/models/workspace_membership.py",
    }


def test_source_proof_matches_head_and_dirty_blob_fails_closed() -> None:
    scenario = load_scenario()
    proof = scenario.production_source_proof()
    assert proof["matchesBaseSha"] is True
    assert set(proof["productionSourceSha256"]) == set(scenario.PRODUCTION_SOURCE_FILES)
    assert all(len(value) == 64 for value in proof["productionSourceSha256"].values())
    assert all(len(value) == 40 for value in proof["productionSourceGitBlobIds"].values())

    def dirty(*args: str) -> bytes:
        if args == ("rev-parse", "HEAD"):
            return b"base\n"
        if args[0] == "rev-parse":
            return b"expected\n"
        if args[0] == "hash-object":
            return b"dirty\n"
        raise AssertionError(args)

    with pytest.raises(AssertionError, match="production source differs"):
        scenario.production_source_proof(git_reader=dirty, source_files=(scenario.PRODUCTION_SOURCE_FILES[0],))


@pytest.mark.parametrize("source", ["attempt.lease_expires_at = now", "attempt.lease_expires_at += delta", "SQL = '''UPDATE research_step_attempts SET lease_expires_at = now()'''"])
def test_manual_expiry_guard_rejects_assignment_and_raw_sql(source: str) -> None:
    assert load_scenario().manual_lease_expiry_violations(source)


def test_current_sources_have_no_manual_expiry_mutation() -> None:
    scenario = load_scenario()
    assert not scenario.manual_lease_expiry_violations(SCENARIO.read_text(encoding="utf-8"))
    assert not scenario.manual_lease_expiry_violations(WORKER.read_text(encoding="utf-8"))


def test_real_operation_contention_is_worker_owned_not_identity_evidence() -> None:
    source = SCENARIO.read_text(encoding="utf-8")
    assert '"identity_only_pre_operation"' in source
    assert '"worker_operation_contention"' in source
    assert 'row["lockType"] == "transactionid" and row["granted"] is False' in source
    assert 'row["lockType"] == "relation"' in source
    assert "controllerLockNotCountedAsWorkerEvidence" in source
    assert source.count('operation_blocker={"runId": fixture.run_id}') == 4


def test_natural_expiry_is_pg_clock_with_zero_mutation_precheck() -> None:
    source = SCENARIO.read_text(encoding="utf-8")
    assert "clock_timestamp()" in source
    assert "wait_for_pg_lease_expiry(" in source
    assert source.count('assert only_process(pre_expiry_reclaim)["reclaimedCount"] == 0') == 2
    assert "after_pre_expiry_reclaim == before_pre_expiry_reclaim" in source
    assert "after_pre_expiry_reclaim == before" in source


def test_accounting_oracle_accepts_complete_bidirectional_fixture() -> None:
    result = oracle(load_scenario(), valid_state())
    assert result["providerLedgerMatchesCalls"]
    assert result["attemptProviderUsageMatchesCalls"]
    assert result["toolLedgerAndAttemptMatchCalls"]
    assert result["eventOracle"]["exactRowsAndPayloads"]
    assert result["snapshotCallBindingsValid"]
    assert result["passed"]


@pytest.mark.parametrize(
    "mutation",
    [
        "active_step_queued",
        "run_state_version_999",
        "step_state_version_999",
        "running_attempt_lease_error",
        "succeeded_provider_reserved_usage",
        "provider_send_attempt_zero",
        "succeeded_tool_lease_error",
        "ledger_currency_eur",
        "ledger_state_version_negative",
        "provider_wrong",
        "model_wrong",
        "fingerprint_wrong",
        "provider_request_not_sha",
        "provider_request_synchronized_drift",
        "tool_shell_exec",
        "tool_version_999",
        "tool_request_not_sha",
        "tool_request_synchronized_drift",
    ],
)
def test_exact_oracle_rejects_auditor_final_state_lifecycle_and_currency_counterexamples(
    mutation: str,
) -> None:
    scenario = load_scenario()
    state = valid_state()
    if mutation == "active_step_queued":
        state["steps"][0]["status"] = "queued"
    elif mutation == "run_state_version_999":
        state["run"]["state_version"] = 999
    elif mutation == "step_state_version_999":
        state["steps"][0]["state_version"] = 999
    elif mutation == "running_attempt_lease_error":
        state["attempts"][0]["error_code"] = "lease_expired"
    elif mutation == "succeeded_provider_reserved_usage":
        state["providerCalls"][0]["usage_source"] = "reserved"
    elif mutation == "provider_send_attempt_zero":
        state["providerCalls"][0]["send_attempt"] = 0
    elif mutation == "succeeded_tool_lease_error":
        state["toolCalls"][0].update(
            error_code="lease_expired", error_message="expired"
        )
    elif mutation == "ledger_currency_eur":
        state["budgetLedgers"][0]["currency"] = "EUR"
    elif mutation == "ledger_state_version_negative":
        state["budgetLedgers"][0]["state_version"] = -1
    elif mutation == "provider_wrong":
        state["providerCalls"][0]["provider"] = "wrong"
    elif mutation == "model_wrong":
        state["providerCalls"][0]["model"] = "wrong"
    elif mutation == "fingerprint_wrong":
        state["providerCalls"][0]["provider_config_fingerprint"] = "0" * 64
    elif mutation == "provider_request_not_sha":
        state["providerCalls"][0]["request_sha256"] = "not-sha"
    elif mutation == "provider_request_synchronized_drift":
        state["providerCalls"][0].update(
            logical_call_key="drifted-provider", request_sha256="3" * 64
        )
    elif mutation == "tool_shell_exec":
        state["toolCalls"][0]["tool_name"] = "shell.exec"
    elif mutation == "tool_version_999":
        state["toolCalls"][0]["tool_version"] = 999
    elif mutation == "tool_request_not_sha":
        state["toolCalls"][0]["request_sha256"] = "not-sha"
    else:
        state["toolCalls"][0].update(
            tool_call_key="drifted-tool", request_sha256="4" * 64
        )
    assert oracle(scenario, state)["passed"] is False


@pytest.mark.parametrize(
    "status",
    ["reserved", "sent", "succeeded", "failed", "outcome_unknown", "cancelled"],
)
def test_provider_accounting_covers_every_persisted_status(status: str) -> None:
    scenario = load_scenario()
    state = valid_state()
    state["toolCalls"] = []
    state["budgetLedgers"][0]["actual_tool_calls"] = 0
    state["attempts"][0]["tool_call_count"] = 0
    call = state["providerCalls"][0]
    ledger = state["budgetLedgers"][0]
    attempt = state["attempts"][0]
    call["status"] = status
    if status in {"reserved", "sent", "cancelled"}:
        call.update(actual_input_tokens=None, actual_output_tokens=None, actual_cost_microunits=None)
        attempt.update(provider_call_count=0, input_tokens=0, output_tokens=0, cost_microunits=0)
        ledger.update(actual_input_tokens=0, actual_output_tokens=0, actual_cost_microunits=0)
    ledger["reserved_provider_calls"] = int(status == "reserved")
    ledger["actual_provider_calls"] = int(status in {"sent", "succeeded", "failed", "outcome_unknown"})
    reserved = status in {"reserved", "sent"}
    ledger.update(
        reserved_input_tokens=9 if reserved else 0,
        reserved_output_tokens=8 if reserved else 0,
        reserved_cost_microunits=143 if reserved else 0,
    )
    call["usage_source"] = (
        "estimated" if status == "outcome_unknown" else
        "actual" if status in {"succeeded", "failed"} else "reserved"
    )
    call["usage_final"] = status in {"succeeded", "failed", "cancelled"}
    call["error_code"] = (
        "provider_failed" if status == "failed" else
        "provider_outcome_unknown" if status == "outcome_unknown" else None
    )
    call["sent_at"] = (
        "2026-01-01T00:02:00+00:00"
        if status in {"sent", "succeeded", "failed", "outcome_unknown"}
        else None
    )
    call["finished_at"] = (
        "2026-01-01T00:03:00+00:00"
        if status in {"succeeded", "failed", "outcome_unknown", "cancelled"}
        else None
    )
    ledger["usage_final"] = status != "outcome_unknown"
    ledger["state_version"] = 1 + {
        "reserved": 1, "sent": 2, "succeeded": 3, "failed": 3,
        "outcome_unknown": 3, "cancelled": 2,
    }[status]
    result = scenario.accounting_oracle(
        state,
        expected_provider_statuses=[status],
        expected_tool_statuses=[],
        expected_attempt_status="running",
        expected_run_status="running",
        event_mode="active",
        expected_provider_requests={"provider-key": PROVIDER_REQUEST_SHA},
        expected_tool_requests={},
    )
    assert result["passed"] is True


@pytest.mark.parametrize(
    "status", ["requested", "running", "succeeded", "failed", "cancelled", "abandoned"]
)
def test_tool_accounting_covers_every_persisted_status(status: str) -> None:
    scenario = load_scenario()
    state = valid_state()
    state["providerCalls"] = []
    ledger = state["budgetLedgers"][0]
    attempt = state["attempts"][0]
    ledger.update(
        reserved_provider_calls=0,
        actual_provider_calls=0,
        reserved_input_tokens=0,
        actual_input_tokens=0,
        reserved_output_tokens=0,
        actual_output_tokens=0,
        reserved_cost_microunits=0,
        actual_cost_microunits=0,
    )
    attempt.update(provider_call_count=0, input_tokens=0, output_tokens=0, cost_microunits=0)
    state["toolCalls"][0]["status"] = status
    state["toolCalls"][0]["error_code"] = (
        "lease_expired" if status == "abandoned" else
        "tool_failed" if status == "failed" else None
    )
    state["toolCalls"][0]["error_message"] = (
        "failed" if status in {"failed", "abandoned"} else None
    )
    state["toolCalls"][0]["started_at"] = (
        None if status == "requested" else "2026-01-01T00:01:00+00:00"
    )
    state["toolCalls"][0]["finished_at"] = (
        "2026-01-01T00:02:00+00:00"
        if status in {"succeeded", "failed", "cancelled", "abandoned"}
        else None
    )
    terminal = status in {"succeeded", "failed", "cancelled", "abandoned"}
    ledger["reserved_tool_calls"] = int(not terminal)
    ledger["actual_tool_calls"] = int(terminal)
    attempt["tool_call_count"] = int(terminal)
    ledger["state_version"] = 1 + (2 if terminal else 1)
    result = scenario.accounting_oracle(
        state,
        expected_provider_statuses=[],
        expected_tool_statuses=[status],
        expected_attempt_status="running",
        expected_run_status="running",
        event_mode="active",
        expected_provider_requests={},
        expected_tool_requests={"tool-key": TOOL_REQUEST_SHA},
    )
    assert result["passed"] is True


@pytest.mark.parametrize("mutation", [
    "extra_provider", "extra_tool", "extra_ledger", "extra_attempt",
    "provider_ledger", "provider_attempt", "provider_step", "provider_run", "provider_workspace",
    "tool_snapshot", "tool_attempt", "tool_step", "tool_run", "tool_workspace",
    "duplicate_ledger_usage", "duplicate_attempt_usage", "negative_ledger",
    "wrong_reserved", "wrong_actual", "extra_event", "wrong_event_attempt", "wrong_payload_attempt",
])
def test_oracle_rejects_extras_scope_drift_duplicate_usage_and_events(mutation: str) -> None:
    scenario = load_scenario()
    state = copy.deepcopy(valid_state())
    if mutation == "extra_provider": state["providerCalls"].append(copy.deepcopy(state["providerCalls"][0]))
    elif mutation == "extra_tool": state["toolCalls"].append(copy.deepcopy(state["toolCalls"][0]))
    elif mutation == "extra_ledger": state["budgetLedgers"].append(copy.deepcopy(state["budgetLedgers"][0]))
    elif mutation == "extra_attempt": state["attempts"].append(copy.deepcopy(state["attempts"][0]))
    elif mutation.startswith("provider_"):
        field = {"provider_ledger": "budget_ledger_id", "provider_attempt": "attempt_id", "provider_step": "step_id", "provider_run": "run_id", "provider_workspace": "workspace_id"}[mutation]
        state["providerCalls"][0][field] = "wrong"
    elif mutation.startswith("tool_"):
        field = {"tool_snapshot": "execution_snapshot_id", "tool_attempt": "attempt_id", "tool_step": "step_id", "tool_run": "run_id", "tool_workspace": "workspace_id"}[mutation]
        state["toolCalls"][0][field] = "wrong"
    elif mutation == "duplicate_ledger_usage": state["budgetLedgers"][0]["actual_input_tokens"] = 8
    elif mutation == "duplicate_attempt_usage": state["attempts"][0]["input_tokens"] = 8
    elif mutation == "negative_ledger": state["budgetLedgers"][0]["reserved_tool_calls"] = -1
    elif mutation == "wrong_reserved": state["budgetLedgers"][0]["reserved_input_tokens"] = 9
    elif mutation == "wrong_actual": state["budgetLedgers"][0]["actual_cost_microunits"] = 110
    elif mutation == "extra_event": state["events"].append(copy.deepcopy(state["events"][-1]))
    elif mutation == "wrong_event_attempt": state["events"][1]["attempt_id"] = "wrong"
    else: state["events"][1]["payload_json"]["attemptId"] = "wrong"
    assert oracle(scenario, state)["passed"] is False


def test_outcome_unknown_usage_final_is_rejected() -> None:
    scenario = load_scenario()
    state = valid_state()
    state["providerCalls"][0]["status"] = "outcome_unknown"
    result = scenario.accounting_oracle(state, expected_provider_statuses=["outcome_unknown"], expected_tool_statuses=["succeeded"], expected_attempt_status="running", expected_run_status="running", event_mode="active", expected_provider_requests={"provider-key": PROVIDER_REQUEST_SHA}, expected_tool_requests={"tool-key": TOOL_REQUEST_SHA})
    assert result["usageStatusValid"] is False
    assert result["passed"] is False


def test_abandoned_tool_without_lease_expired_is_rejected() -> None:
    scenario = load_scenario()
    state = requeue_state()
    state["toolCalls"][0]["error_code"] = None
    result = scenario.accounting_oracle(state, expected_provider_statuses=[], expected_tool_statuses=["abandoned"], expected_attempt_status="abandoned", expected_run_status="running", event_mode="requeue_reclaim", expected_provider_requests={}, expected_tool_requests={"tool-key": TOOL_REQUEST_SHA})
    assert result["toolLedgerAndAttemptMatchCalls"] is False
    assert result["passed"] is False


def test_cancel_event_oracle_accepts_exact_order_and_terminal_event() -> None:
    scenario = load_scenario()
    result = scenario.accounting_oracle(cancel_state(), expected_provider_statuses=[], expected_tool_statuses=[], expected_attempt_status="abandoned", expected_run_status="cancelled", event_mode="cancel_reclaim", expected_provider_requests={}, expected_tool_requests={})
    assert result["eventOracle"]["cancelOrderAndTerminal"]
    assert result["passed"]


@pytest.mark.parametrize("mutation", ["order", "not_last", "reason"])
def test_cancel_event_oracle_rejects_order_terminal_and_reason(mutation: str) -> None:
    scenario = load_scenario()
    state = cancel_state()
    if mutation == "order": state["events"][2], state["events"][3] = state["events"][3], state["events"][2]
    elif mutation == "not_last": state["events"][3], state["events"][4] = state["events"][4], state["events"][3]
    else: state["events"][4]["payload_json"]["reasonCode"] = "wrong"
    result = scenario.accounting_oracle(state, expected_provider_statuses=[], expected_tool_statuses=[], expected_attempt_status="abandoned", expected_run_status="cancelled", event_mode="cancel_reclaim", expected_provider_requests={}, expected_tool_requests={})
    assert result["passed"] is False


def test_secret_scrubber_removes_database_url_and_password() -> None:
    scenario = load_scenario()
    url = "postgresql+psycopg://user:super-secret@localhost/database"
    scrubbed = scenario.scrub_secrets({"command": [url], "error": "super-secret", "nested": {"value": url}}, {url, "super-secret"})
    rendered = repr(scrubbed)
    assert url not in rendered and "super-secret" not in rendered
    assert rendered.count("[redacted]") == 3
