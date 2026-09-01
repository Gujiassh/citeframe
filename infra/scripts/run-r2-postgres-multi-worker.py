#!/usr/bin/env python3
"""Run the currently implemented R2 PostgreSQL process-proof scenarios."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
WORKER_ENTRY = ROOT / "infra/scripts/r2_worker_entry.py"
R15_RUNNER = ROOT / "infra/scripts/run-r15-postgres-admission.py"
H_JOIN_SCENARIO = ROOT / "infra/scripts/r2_scenario_h_join.py"
I_CONFLICT_SCENARIO = ROOT / "infra/scripts/r2_scenario_i_conflict.py"
J_CRASH_SCENARIO = ROOT / "infra/scripts/r2_scenario_j_crash.py"
L_BUDGET_SCENARIO = ROOT / "infra/scripts/r2_scenario_l_budget.py"
CANDIDATE_FILES = (
    WORKER_ENTRY,
    Path(__file__).resolve(),
    H_JOIN_SCENARIO,
    I_CONFLICT_SCENARIO,
    ROOT / "infra/scripts/r2_scenario_i_worker.py",
    J_CRASH_SCENARIO,
    ROOT / "infra/scripts/r2_scenario_j_crash_worker.py",
    L_BUDGET_SCENARIO,
    ROOT / "infra/scripts/r2_scenario_l_worker.py",
    ROOT / "packages/research-persistence/src/citeframe_research_persistence/lease.py",
    ROOT / "apps/worker/src/ai_pdf_worker/research_runtime_processor.py",
    ROOT / "apps/worker/src/ai_pdf_worker/research_persistence_service.py",
)
SCENARIOS = (
    "identity_probe",
    "a_same_step_claim",
    "b_processor_exclusion",
    "c_cap_n",
    "d_step_id_tiebreak",
    "e_lease_reclaim_late_completion",
    "f_cancel_races",
    "g_provider_reconcile",
    "h_join_readiness",
    "i_conflict_decision_resume",
    "j_crash_recovery",
    "l_budget_exhaustion_reconcile",
)
BLOCKED_SCENARIOS = ("k_publication_outcome_unknown",)


def load_r15() -> Any:
    spec = importlib.util.spec_from_file_location("citeframe_r2_r15", R15_RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_h_join() -> Any:
    spec = importlib.util.spec_from_file_location("citeframe_r2_h_join", H_JOIN_SCENARIO)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_i_conflict() -> Any:
    spec = importlib.util.spec_from_file_location(
        "citeframe_r2_i_conflict", I_CONFLICT_SCENARIO
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_j_crash() -> Any:
    spec = importlib.util.spec_from_file_location(
        "citeframe_r2_j_crash", J_CRASH_SCENARIO
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_l_budget() -> Any:
    spec = importlib.util.spec_from_file_location(
        "citeframe_r2_l_budget", L_BUDGET_SCENARIO
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


r15 = load_r15()
r0 = r15.r0
h_join = load_h_join()
i_conflict = load_i_conflict()
j_crash = load_j_crash()
l_budget = load_l_budget()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def redacted_cli_command(arguments: list[str]) -> list[str]:
    redacted: list[str] = []
    hide_next = False
    for argument in arguments:
        if hide_next:
            redacted.append("[redacted]")
            hide_next = False
            continue
        redacted.append(argument)
        if argument in {"--database-url", "--lease-token"}:
            hide_next = True
    return redacted


def redact_sensitive_payload(value: Any, secrets: set[str]) -> Any:
    if isinstance(value, dict):
        return {key: redact_sensitive_payload(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_sensitive_payload(item, secrets) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive_payload(item, secrets) for item in value]
    if isinstance(value, str):
        redacted = value
        for secret in sorted((secret for secret in secrets if secret), key=len, reverse=True):
            redacted = redacted.replace(secret, "[redacted]")
        return redacted
    return value


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def candidate_file_hashes() -> dict[str, str]:
    return {
        path.relative_to(ROOT).as_posix(): sha256_bytes(path.read_bytes())
        for path in sorted(CANDIDATE_FILES)
    }


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def read_ready_records(paths: list[Path], timeout_seconds: float) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if all(path.is_file() for path in paths):
            return [json.loads(path.read_text(encoding="utf-8")) for path in paths]
        time.sleep(0.02)
    missing = [str(path) for path in paths if not path.is_file()]
    raise TimeoutError(f"workers did not become ready: {missing}")


def observe_ready_worker_backends(
    database_url: str, ready_records: list[dict[str, Any]]
) -> dict[str, Any]:
    """Capture live pg_stat_activity/pg_locks rows while child processes await release."""
    backend_pids = [int(record["pgBackendPid"]) for record in ready_records]
    parameters = {f"pid_{index}": pid for index, pid in enumerate(backend_pids)}
    placeholders = ", ".join(f":pid_{index}" for index in range(len(backend_pids)))
    engine = create_engine(database_url, future=True)
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    f"""
                    SELECT
                        activity.pid AS "pgBackendPid",
                        activity.state,
                        activity.wait_event_type AS "waitEventType",
                        activity.wait_event AS "waitEvent",
                        locks.locktype AS "lockType",
                        locks.mode,
                        locks.granted,
                        CASE
                            WHEN locks.relation IS NULL THEN NULL
                            ELSE locks.relation::regclass::text
                        END AS relation
                    FROM pg_stat_activity AS activity
                    LEFT JOIN pg_locks AS locks ON locks.pid = activity.pid
                    WHERE activity.pid IN ({placeholders})
                    ORDER BY activity.pid, locks.locktype, locks.mode, locks.relation
                    """
                ),
                parameters,
            ).mappings()
            records = [dict(row) for row in rows]
    finally:
        engine.dispose()
    if {record["pgBackendPid"] for record in records} != set(backend_pids):
        raise AssertionError("not every released child had live PostgreSQL barrier evidence")
    return {
        "evidenceKind": "live_worker_backends_at_ready_barrier",
        "phase": "before_release",
        "backendPids": backend_pids,
        "records": records,
    }


def parse_worker_output(process: subprocess.Popen[str]) -> dict[str, Any]:
    stdout, stderr = process.communicate(timeout=25)
    lines = [line for line in stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise AssertionError(f"worker {process.pid} emitted {len(lines)} JSON records: {stderr!r}")
    record = json.loads(lines[0])
    if not isinstance(record, dict):
        raise TypeError(f"worker {process.pid} JSON record was not an object")
    record["controllerObservedExitStatus"] = process.returncode
    record["stderr"] = stderr
    return record


def terminate_workers(workers: list[subprocess.Popen[str]]) -> None:
    for worker in workers:
        if worker.poll() is None:
            worker.terminate()
    for worker in workers:
        if worker.poll() is None:
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=5)


def validate_process_records(
    records: list[dict[str, Any]], expected_argv: dict[str, list[str]], scenario: str
) -> None:
    if len(records) != len(expected_argv):
        raise AssertionError(f"expected {len(expected_argv)} worker records, got {len(records)}")
    if {record.get("workerInstanceId") for record in records} != set(expected_argv):
        raise AssertionError("worker instance ids did not match launched subprocesses")
    if len({record.get("osPid") for record in records}) != len(records):
        raise AssertionError("R2 proof requires distinct OS subprocess PIDs")
    if len({record.get("pgBackendPid") for record in records}) != len(records):
        raise AssertionError("R2 proof requires distinct PostgreSQL backend PIDs")
    for record in records:
        worker_id = str(record["workerInstanceId"])
        if record.get("scenario") != scenario:
            raise AssertionError(f"wrong scenario from {worker_id}: {record.get('scenario')}")
        if record.get("exitStatus") != 0 or record.get("controllerObservedExitStatus") != 0:
            raise AssertionError(f"worker {worker_id} did not exit cleanly: {record}")
        if record.get("argv") != expected_argv[worker_id]:
            raise AssertionError(f"worker {worker_id} argv did not match controller command")
        if not isinstance(record.get("osPid"), int) or not isinstance(record.get("pgBackendPid"), int):
            raise TypeError(f"worker {worker_id} did not report integer process identities")


def launch_workers(
    *,
    scenario: str,
    database_url: str,
    schema: str | None,
    worker_specs: list[dict[str, str]],
    timeout_seconds: float,
) -> dict[str, Any]:
    workers: list[subprocess.Popen[str]] = []
    commands: dict[str, list[str]] = {}
    try:
        with tempfile.TemporaryDirectory(prefix="citeframe-r2-") as directory:
            temporary = Path(directory)
            ready_files = [temporary / f"ready-{index}.json" for index in range(len(worker_specs))]
            release_files = [temporary / f"release-{index}" for index in range(len(worker_specs))]
            for index, spec in enumerate(worker_specs):
                worker_id = spec["workerInstanceId"]
                command = [
                    sys.executable,
                    str(WORKER_ENTRY),
                    "--scenario", scenario,
                    "--operation", spec["operation"],
                    "--database-url-env", "CITEFRAME_R2_DATABASE_URL",
                    "--worker-instance-id", worker_id,
                    "--ready-file", str(ready_files[index]),
                    "--release-file", str(release_files[index]),
                    "--wait-timeout-seconds", str(timeout_seconds),
                ]
                if schema is not None:
                    command.extend(("--schema", schema))
                if "retryNoneSeconds" in spec:
                    command.extend(("--retry-none-seconds", spec["retryNoneSeconds"]))
                option_names = {
                    "runId": "--run-id",
                    "stepKey": "--step-key",
                    "branchKey": "--branch-key",
                    "attemptId": "--attempt-id",
                    "outputSha256": "--output-sha256",
                    "workspaceId": "--workspace-id",
                    "actorUserId": "--actor-user-id",
                    "expectedStateVersion": "--expected-state-version",
                    "providerCallId": "--provider-call-id",
                    "logicalCallKey": "--logical-call-key",
                    "requestSha256": "--request-sha256",
                    "toolCallId": "--tool-call-id",
                    "toolCallKey": "--tool-call-key",
                    "toolName": "--tool-name",
                    "toolStatus": "--tool-status",
                }
                for key, option_name in option_names.items():
                    if key in spec:
                        command.extend((option_name, spec[key]))
                child_environment = os.environ.copy()
                child_environment["CITEFRAME_R2_DATABASE_URL"] = database_url
                if "leaseToken" in spec:
                    child_environment["CITEFRAME_R2_LEASE_TOKEN"] = spec["leaseToken"]
                    command.extend(("--lease-token-env", "CITEFRAME_R2_LEASE_TOKEN"))
                commands[worker_id] = command
                workers.append(
                    subprocess.Popen(
                        command,
                        cwd=ROOT,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env=child_environment,
                    )
                )
            try:
                ready = read_ready_records(ready_files, timeout_seconds)
            except TimeoutError as error:
                failed = []
                for worker in workers:
                    if worker.poll() is not None:
                        stdout, stderr = worker.communicate(timeout=1)
                        failed.append({"pid": worker.pid, "returncode": worker.returncode, "stdout": stdout, "stderr": stderr})
                raise TimeoutError(f"{error}; exited workers={failed}") from error
            ready_barrier = observe_ready_worker_backends(database_url, ready)
            for release in release_files:
                release.write_text("release\n", encoding="utf-8")
            records = [parse_worker_output(worker) for worker in workers]
            validate_process_records(records, {key: value[2:] for key, value in commands.items()}, scenario)
            return {
                "readyRecords": ready,
                "readyBarrierBackendObservation": ready_barrier,
                "processRecords": records,
                "workerCommands": commands,
            }
    finally:
        terminate_workers(workers)


def projection(harness: Any, run_id: str) -> dict[str, Any]:
    with harness.sessions() as db:
        state = r15.aggregate_snapshot(db, run_id)
        # R2's persisted replay oracle is sequence ordered, not surrogate-id ordered.
        state["events"] = sorted(state["events"], key=lambda event: int(event["seq"]))
        for attempt in state["attempts"]:
            if attempt.get("lease_token_hash") is not None:
                attempt["lease_token_hash"] = "[redacted]"
        from citeframe_persistence.models import (
            ResearchBudgetLedger,
            ResearchProviderCall,
            ResearchToolCall,
        )
        from sqlalchemy import select

        state["budgetLedgers"] = [
            r15.row_value(row)
            for row in db.scalars(
                select(ResearchBudgetLedger)
                .where(ResearchBudgetLedger.run_id == run_id)
                .order_by(ResearchBudgetLedger.id)
            )
        ]
        state["providerCalls"] = [
            r15.row_value(row)
            for row in db.scalars(
                select(ResearchProviderCall)
                .where(ResearchProviderCall.run_id == run_id)
                .order_by(ResearchProviderCall.id)
            )
        ]
        state["toolCalls"] = [
            r15.row_value(row)
            for row in db.scalars(
                select(ResearchToolCall)
                .where(ResearchToolCall.run_id == run_id)
                .order_by(ResearchToolCall.id)
            )
        ]
        return state


def lock_projection(harness: Any) -> dict[str, Any]:
    with harness.monitor_engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT locktype, mode, granted, relation::regclass::text AS relation
                FROM pg_locks
                WHERE pid = pg_backend_pid() AND relation IS NOT NULL
                ORDER BY locktype, mode, relation
                """
            )
        ).mappings()
        return {
            "evidenceKind": "controller_monitor_connection_diagnostic",
            "notWorkerContentionEvidence": True,
            "records": [dict(row) for row in rows],
        }


def scenario_identity(database_url: str, timeout_seconds: float) -> dict[str, Any]:
    evidence = launch_workers(
        scenario="identity_probe",
        database_url=database_url,
        schema=None,
        worker_specs=[
            {"workerInstanceId": "identity-1", "operation": "identity"},
            {"workerInstanceId": "identity-2", "operation": "identity"},
        ],
        timeout_seconds=timeout_seconds,
    )
    return {**evidence, "assertions": {"distinctOsPids": True, "distinctPgBackendPids": True}}


def scenario_a_same_step(harness: Any, database_url: str, timeout_seconds: float) -> dict[str, Any]:
    fixture = harness.seed_run("r2-a", step_count=1)
    evidence = launch_workers(
        scenario="a_same_step_claim",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[
            {
                "workerInstanceId": "a-1",
                "operation": "claim_specific",
                "runId": fixture.run_id,
                "stepKey": fixture.step_keys[0],
                "branchKey": fixture.branch_keys[0] or "",
            },
            {
                "workerInstanceId": "a-2",
                "operation": "claim_specific",
                "runId": fixture.run_id,
                "stepKey": fixture.step_keys[0],
                "branchKey": fixture.branch_keys[0] or "",
            },
        ],
        timeout_seconds=timeout_seconds,
    )
    state = projection(harness, fixture.run_id)
    claimed = [record for record in evidence["processRecords"] if record["outcome"] == "claimed"]
    conflicts = [record for record in evidence["processRecords"] if record["outcome"] == "conflict"]
    assert len(claimed) == 1 and len(conflicts) == 1
    assert len(state["attempts"]) == 1
    assert state["attempts"][0]["worker_instance_id"] == claimed[0]["workerInstanceId"]
    assert state["steps"][0]["status"] == "running"
    return {
        **evidence,
        "dbProjection": state,
        "locks": lock_projection(harness),
        "assertions": {"exactlyOneAttempt": True, "exactlyOneLeaseOwner": True},
    }


def scenario_b_processor_exclusion(harness: Any, database_url: str, timeout_seconds: float) -> dict[str, Any]:
    full = harness.seed_run("r2-b-full", step_count=2, queued_at=datetime.now(UTC) - timedelta(seconds=5))
    other = harness.seed_run("r2-b-other", step_count=1, queued_at=datetime.now(UTC))
    r15.set_cap(harness, full, 1)
    assert r15.claim(harness, "b-seed") is not None
    before = projection(harness, full.run_id)
    evidence = launch_workers(
        scenario="b_processor_exclusion",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[{"workerInstanceId": "b-processor", "operation": "processor_claim"}],
        timeout_seconds=timeout_seconds,
    )
    record = evidence["processRecords"][0]
    after = projection(harness, full.run_id)
    other_state = projection(harness, other.run_id)
    assert record["outcome"] == "claimed" and record["claimedRunId"] == other.run_id
    assert before == after, "cap-full run changed while processor advanced its local exclusion set"
    assert len(other_state["attempts"]) == 1
    r15.retire_run(harness, full.run_id)
    r15.retire_run(harness, other.run_id)
    return {
        **evidence,
        "capFullBefore": before,
        "capFullAfter": after,
        "otherRunProjection": other_state,
        "locks": lock_projection(harness),
        "assertions": {"processorCalled": True, "advancedAfterAdmissionDeferred": True, "capFullZeroMutation": True},
    }


def scenario_c_cap_n(harness: Any, database_url: str, timeout_seconds: float) -> dict[str, Any]:
    cap = 2
    fixture = harness.seed_run("r2-c", step_count=cap + 1)
    r15.set_cap(harness, fixture, cap)
    evidence = launch_workers(
        scenario="c_cap_n",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[
            {"workerInstanceId": f"c-{index}", "operation": "claim_next", "retryNoneSeconds": "5"}
            for index in range(1, cap + 2)
        ],
        timeout_seconds=timeout_seconds,
    )
    state = projection(harness, fixture.run_id)
    claimed = [record for record in evidence["processRecords"] if record["outcome"] == "claimed"]
    deferred = [record for record in evidence["processRecords"] if record["outcome"] == "deferred"]
    assert len(claimed) == cap and len(deferred) == 1
    assert len(state["attempts"]) == cap
    assert len({record["lease"]["stepId"] for record in claimed}) == cap
    r15.retire_run(harness, fixture.run_id)
    return {
        **evidence,
        "dbProjection": state,
        "locks": lock_projection(harness),
        "assertions": {"cap": cap, "exactlyCapClaimed": True, "nthPlusOneDeferred": True},
    }


def scenario_e_lease_reclaim_late_completion(harness: Any, database_url: str, timeout_seconds: float) -> dict[str, Any]:
    fixture = harness.seed_run("r2-e", step_count=1)
    old_lease = harness.claim_specific(fixture, 0, "e-old")
    with harness.sessions() as db:
        attempt = db.get(r15.ResearchStepAttempt, old_lease.attempt_id)
        assert attempt is not None
        attempt.lease_expires_at = datetime.now(UTC) - timedelta(seconds=2)
        db.commit()
    before = projection(harness, fixture.run_id)
    reclaim_evidence = launch_workers(
        scenario="e_lease_reclaim_late_completion",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[{"workerInstanceId": "e-reclaim", "operation": "reclaim"}],
        timeout_seconds=timeout_seconds,
    )
    assert reclaim_evidence["processRecords"][0]["reclaimedCount"] == 1
    replacement_evidence = launch_workers(
        scenario="e_lease_reclaim_late_completion",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[{"workerInstanceId": "e-new", "operation": "claim_next", "retryNoneSeconds": "5"}],
        timeout_seconds=timeout_seconds,
    )
    late_evidence = launch_workers(
        scenario="e_lease_reclaim_late_completion",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[{
            "workerInstanceId": "e-late",
            "operation": "complete",
            "attemptId": old_lease.attempt_id,
            "leaseToken": old_lease.lease_token,
            "outputSha256": r0.sha("r2-e-late-output"),
        }],
        timeout_seconds=timeout_seconds,
    )
    after = projection(harness, fixture.run_id)
    attempts = after["attempts"]
    assert late_evidence["processRecords"][0]["outcome"] == "fenced"
    assert len(attempts) == 2
    assert sum(item["status"] == "abandoned" for item in attempts) == 1
    assert sum(item["status"] == "running" for item in attempts) == 1
    assert sum(item["event_type"] == "step_succeeded" for item in after["events"]) == 0
    return {
        "reclaim": reclaim_evidence,
        "replacement": replacement_evidence,
        "lateCompletion": late_evidence,
        "before": before,
        "after": after,
        "locks": lock_projection(harness),
        "assertions": {"expiredOldAttemptAbandoned": True, "newAttemptClaimed": True, "lateCompletionFenced": True, "noDuplicateTerminalEvent": True},
    }

def _only_process(evidence: dict[str, Any]) -> dict[str, Any]:
    records = evidence["processRecords"]
    assert len(records) == 1
    return records[0]


def _expire_attempt(harness: Any, attempt_id: str) -> None:
    with harness.sessions() as db:
        attempt = db.get(r15.ResearchStepAttempt, attempt_id)
        assert attempt is not None
        attempt.lease_expires_at = datetime.now(UTC) - timedelta(seconds=2)
        db.commit()


def _cancel_active_run(
    harness: Any,
    database_url: str,
    timeout_seconds: float,
    *,
    run_id: str,
    worker_instance_id: str,
) -> dict[str, Any]:
    current = projection(harness, run_id)
    evidence = launch_workers(
        scenario="g_provider_reconcile",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[{
            "workerInstanceId": worker_instance_id,
            "operation": "cancel",
            "runId": run_id,
            "workspaceId": harness.workspace_id,
            "actorUserId": harness.user_id,
            "expectedStateVersion": str(current["run"]["state_version"]),
        }],
        timeout_seconds=timeout_seconds,
    )
    assert _only_process(evidence)["outcome"] == "cancelled"
    return evidence


def _reserve_provider_process(
    harness: Any,
    database_url: str,
    timeout_seconds: float,
    *,
    attempt_id: str,
    key: str,
) -> tuple[str, dict[str, Any]]:
    evidence = launch_workers(
        scenario="g_provider_reconcile",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[{
            "workerInstanceId": f"{key}-reserve",
            "operation": "reserve_provider",
            "attemptId": attempt_id,
            "logicalCallKey": key,
            "requestSha256": r0.sha(key),
        }],
        timeout_seconds=timeout_seconds,
    )
    record = _only_process(evidence)
    assert record["outcome"] == "reserved"
    return str(record["providerCallId"]), evidence


def _begin_tool_process(
    harness: Any,
    database_url: str,
    timeout_seconds: float,
    *,
    attempt_id: str,
    key: str,
) -> tuple[str, dict[str, Any]]:
    evidence = launch_workers(
        scenario="g_provider_reconcile",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[{
            "workerInstanceId": f"{key}-begin",
            "operation": "begin_tool",
            "attemptId": attempt_id,
            "toolCallKey": key,
            "toolName": "evidence.search",
            "requestSha256": r0.sha(key),
        }],
        timeout_seconds=timeout_seconds,
    )
    record = _only_process(evidence)
    assert record["outcome"] == "running"
    return str(record["toolCallId"]), evidence


def _assert_single_accounting(
    state: dict[str, Any],
    *,
    provider_calls: int = 0,
    tool_calls: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    assert len(state["budgetLedgers"]) == 1
    ledger = state["budgetLedgers"][0]
    attempt = state["attempts"][0]
    assert ledger["reserved_provider_calls"] == 0
    assert ledger["reserved_tool_calls"] == 0
    assert ledger["actual_provider_calls"] == provider_calls
    assert ledger["actual_tool_calls"] == tool_calls
    assert ledger["actual_input_tokens"] == input_tokens
    assert ledger["actual_output_tokens"] == output_tokens
    assert attempt["provider_call_count"] == provider_calls
    assert attempt["tool_call_count"] == tool_calls
    assert attempt["input_tokens"] == input_tokens
    assert attempt["output_tokens"] == output_tokens
    if provider_calls:
        assert len(state["providerCalls"]) == provider_calls
        call = state["providerCalls"][0]
        assert call["actual_input_tokens"] == input_tokens
        assert call["actual_output_tokens"] == output_tokens
        assert ledger["actual_cost_microunits"] == call["actual_cost_microunits"]
        assert attempt["cost_microunits"] == call["actual_cost_microunits"]


def scenario_g_provider_reconcile(
    harness: Any, database_url: str, timeout_seconds: float
) -> dict[str, Any]:
    # Reserved-but-unsent calls cannot cross a cancellation boundary. Reclaim performs
    # the production reservation compensation exactly once.
    reserved_fixture = harness.seed_run("r2-g-reserved")
    reserved_lease = harness.claim_specific(reserved_fixture, 0, "g-reserved-owner")
    reserved_id, reserved = _reserve_provider_process(
        harness,
        database_url,
        timeout_seconds,
        attempt_id=reserved_lease.attempt_id,
        key="g-reserved",
    )
    reserved_before = projection(harness, reserved_fixture.run_id)
    reserved_cancel = _cancel_active_run(
        harness,
        database_url,
        timeout_seconds,
        run_id=reserved_fixture.run_id,
        worker_instance_id="g-reserved-cancel",
    )
    reserved_send = launch_workers(
        scenario="g_provider_reconcile",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[{
            "workerInstanceId": "g-reserved-send-fenced",
            "operation": "mark_sent",
            "providerCallId": reserved_id,
        }],
        timeout_seconds=timeout_seconds,
    )
    _expire_attempt(harness, reserved_lease.attempt_id)
    reserved_reclaim = launch_workers(
        scenario="g_provider_reconcile",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[{"workerInstanceId": "g-reserved-reclaim", "operation": "reclaim"}],
        timeout_seconds=timeout_seconds,
    )
    reserved_after = projection(harness, reserved_fixture.run_id)
    assert _only_process(reserved_send)["outcome"] == "fenced"
    assert _only_process(reserved_reclaim)["reclaimedCount"] == 1
    assert reserved_after["providerCalls"][0]["status"] == "cancelled"
    _assert_single_accounting(reserved_after)

    # A sent call remains billable after cancellation. Two independent processes run the
    # same production reconciliation concurrently; the Call row fence permits one write.
    sent_fixture = harness.seed_run("r2-g-sent-cancel")
    sent_lease = harness.claim_specific(sent_fixture, 0, "g-sent-owner")
    sent_id, sent_reserve = _reserve_provider_process(
        harness,
        database_url,
        timeout_seconds,
        attempt_id=sent_lease.attempt_id,
        key="g-sent",
    )
    sent_mark = launch_workers(
        scenario="g_provider_reconcile",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[{
            "workerInstanceId": "g-sent-mark",
            "operation": "mark_sent",
            "providerCallId": sent_id,
        }],
        timeout_seconds=timeout_seconds,
    )
    assert _only_process(sent_mark)["outcome"] == "sent"
    sent_before_cancel = projection(harness, sent_fixture.run_id)
    assert sent_before_cancel["providerCalls"][0]["status"] == "sent"
    sent_cancel = _cancel_active_run(
        harness,
        database_url,
        timeout_seconds,
        run_id=sent_fixture.run_id,
        worker_instance_id="g-sent-cancel",
    )
    sent_before_reconcile = projection(harness, sent_fixture.run_id)
    assert sent_before_reconcile["providerCalls"][0]["status"] == "sent"
    sent_reconcile = launch_workers(
        scenario="g_provider_reconcile",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[
            {
                "workerInstanceId": "g-sent-reconcile-1",
                "operation": "reconcile",
                "providerCallId": sent_id,
            },
            {
                "workerInstanceId": "g-sent-reconcile-2",
                "operation": "reconcile",
                "providerCallId": sent_id,
            },
        ],
        timeout_seconds=timeout_seconds,
    )
    sent_after_reconcile = projection(harness, sent_fixture.run_id)
    reconcile_records = sent_reconcile["processRecords"]
    assert sorted(record["outcome"] for record in reconcile_records) == ["fenced", "reconciled"]
    fenced_reconcile = next(record for record in reconcile_records if record["outcome"] == "fenced")
    assert fenced_reconcile["errorCode"] == "research_state_conflict"
    sent_call = sent_after_reconcile["providerCalls"][0]
    assert sent_call["status"] == "outcome_unknown"
    assert sent_call["usage_source"] == "estimated"
    assert sent_call["usage_final"] is False
    _assert_single_accounting(
        sent_after_reconcile,
        provider_calls=1,
        input_tokens=10,
        output_tokens=10,
    )
    _expire_attempt(harness, sent_lease.attempt_id)
    sent_reclaim = launch_workers(
        scenario="g_provider_reconcile",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[{"workerInstanceId": "g-sent-reclaim", "operation": "reclaim"}],
        timeout_seconds=timeout_seconds,
    )
    sent_after = projection(harness, sent_fixture.run_id)
    assert _only_process(sent_reclaim)["reclaimedCount"] == 1
    _assert_single_accounting(sent_after, provider_calls=1, input_tokens=10, output_tokens=10)

    # Lease recovery owns the sent -> outcome_unknown transition too. A later attempt to
    # reconcile the already recovered call is fenced and cannot charge usage twice.
    reclaim_fixture = harness.seed_run("r2-g-sent-reclaim")
    reclaim_lease = harness.claim_specific(reclaim_fixture, 0, "g-reclaim-owner")
    reclaim_provider_id, reclaim_reserve = _reserve_provider_process(
        harness,
        database_url,
        timeout_seconds,
        attempt_id=reclaim_lease.attempt_id,
        key="g-reclaim-provider",
    )
    reclaim_mark = launch_workers(
        scenario="g_provider_reconcile",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[{
            "workerInstanceId": "g-reclaim-mark",
            "operation": "mark_sent",
            "providerCallId": reclaim_provider_id,
        }],
        timeout_seconds=timeout_seconds,
    )
    assert _only_process(reclaim_mark)["outcome"] == "sent"
    reclaim_before = projection(harness, reclaim_fixture.run_id)
    _expire_attempt(harness, reclaim_lease.attempt_id)
    reclaim_process = launch_workers(
        scenario="g_provider_reconcile",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[{"workerInstanceId": "g-provider-expiry-reclaim", "operation": "reclaim"}],
        timeout_seconds=timeout_seconds,
    )
    reclaim_after_transition = projection(harness, reclaim_fixture.run_id)
    assert _only_process(reclaim_process)["reclaimedCount"] == 1
    assert reclaim_after_transition["providerCalls"][0]["status"] == "outcome_unknown"
    _assert_single_accounting(
        reclaim_after_transition,
        provider_calls=1,
        input_tokens=10,
        output_tokens=10,
    )
    reclaim_late = launch_workers(
        scenario="g_provider_reconcile",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[
            {
                "workerInstanceId": "g-provider-late-reconcile-1",
                "operation": "reconcile",
                "providerCallId": reclaim_provider_id,
            },
            {
                "workerInstanceId": "g-provider-late-reconcile-2",
                "operation": "reconcile",
                "providerCallId": reclaim_provider_id,
            },
        ],
        timeout_seconds=timeout_seconds,
    )
    reclaim_after = projection(harness, reclaim_fixture.run_id)
    assert {record["outcome"] for record in reclaim_late["processRecords"]} == {"fenced"}
    assert {
        record["errorCode"] for record in reclaim_late["processRecords"]
    } == {"research_state_conflict"}
    _assert_single_accounting(reclaim_after, provider_calls=1, input_tokens=10, output_tokens=10)

    # Tool calls have no provider-style outcome_unknown terminal. Their analogous durable
    # recovery is a single terminal complete after cancellation, or abandoned on reclaim.
    tool_fixture = harness.seed_run("r2-g-tool-cancel")
    tool_lease = harness.claim_specific(tool_fixture, 0, "g-tool-owner")
    tool_id, tool_begin = _begin_tool_process(
        harness,
        database_url,
        timeout_seconds,
        attempt_id=tool_lease.attempt_id,
        key="g-tool-cancel",
    )
    tool_before_cancel = projection(harness, tool_fixture.run_id)
    tool_cancel = _cancel_active_run(
        harness,
        database_url,
        timeout_seconds,
        run_id=tool_fixture.run_id,
        worker_instance_id="g-tool-cancel-run",
    )
    tool_before_complete = projection(harness, tool_fixture.run_id)
    tool_complete = launch_workers(
        scenario="g_provider_reconcile",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[
            {
                "workerInstanceId": "g-tool-complete-1",
                "operation": "complete_tool",
                "toolCallId": tool_id,
                "toolStatus": "abandoned",
            },
            {
                "workerInstanceId": "g-tool-complete-2",
                "operation": "complete_tool",
                "toolCallId": tool_id,
                "toolStatus": "abandoned",
            },
        ],
        timeout_seconds=timeout_seconds,
    )
    tool_after_complete = projection(harness, tool_fixture.run_id)
    assert sorted(record["outcome"] for record in tool_complete["processRecords"]) == [
        "completed",
        "fenced",
    ]
    assert tool_after_complete["toolCalls"][0]["status"] == "abandoned"
    _assert_single_accounting(tool_after_complete, tool_calls=1)
    _expire_attempt(harness, tool_lease.attempt_id)
    tool_reclaim_finish = launch_workers(
        scenario="g_provider_reconcile",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[{"workerInstanceId": "g-tool-cancel-reclaim", "operation": "reclaim"}],
        timeout_seconds=timeout_seconds,
    )
    tool_after = projection(harness, tool_fixture.run_id)
    assert _only_process(tool_reclaim_finish)["reclaimedCount"] == 1
    _assert_single_accounting(tool_after, tool_calls=1)

    tool_reclaim_fixture = harness.seed_run("r2-g-tool-reclaim")
    tool_reclaim_lease = harness.claim_specific(tool_reclaim_fixture, 0, "g-tool-reclaim-owner")
    tool_reclaim_id, tool_reclaim_begin = _begin_tool_process(
        harness,
        database_url,
        timeout_seconds,
        attempt_id=tool_reclaim_lease.attempt_id,
        key="g-tool-reclaim",
    )
    tool_reclaim_before = projection(harness, tool_reclaim_fixture.run_id)
    _expire_attempt(harness, tool_reclaim_lease.attempt_id)
    tool_reclaim_process = launch_workers(
        scenario="g_provider_reconcile",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[{"workerInstanceId": "g-tool-expiry-reclaim", "operation": "reclaim"}],
        timeout_seconds=timeout_seconds,
    )
    tool_reclaim_after_transition = projection(harness, tool_reclaim_fixture.run_id)
    assert _only_process(tool_reclaim_process)["reclaimedCount"] == 1
    assert tool_reclaim_after_transition["toolCalls"][0]["status"] == "abandoned"
    _assert_single_accounting(tool_reclaim_after_transition, tool_calls=1)
    tool_reclaim_late = launch_workers(
        scenario="g_provider_reconcile",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[
            {
                "workerInstanceId": "g-tool-late-complete-1",
                "operation": "complete_tool",
                "toolCallId": tool_reclaim_id,
                "toolStatus": "abandoned",
            },
            {
                "workerInstanceId": "g-tool-late-complete-2",
                "operation": "complete_tool",
                "toolCallId": tool_reclaim_id,
                "toolStatus": "abandoned",
            },
        ],
        timeout_seconds=timeout_seconds,
    )
    tool_reclaim_after = projection(harness, tool_reclaim_fixture.run_id)
    assert {record["outcome"] for record in tool_reclaim_late["processRecords"]} == {"fenced"}
    assert {
        record["errorCode"] for record in tool_reclaim_late["processRecords"]
    } == {"research_state_conflict"}
    _assert_single_accounting(tool_reclaim_after, tool_calls=1)

    relevant_states = (
        reserved_after,
        sent_after,
        reclaim_after,
        tool_after,
        tool_reclaim_after,
    )
    assert all(event_sequence_oracle(state)["unique"] for state in relevant_states)
    assert all(event_sequence_oracle(state)["strictlyOrdered"] for state in relevant_states)
    return {
        "reservedUnsent": {
            "reserve": reserved,
            "before": reserved_before,
            "cancel": reserved_cancel,
            "send": reserved_send,
            "reclaim": reserved_reclaim,
            "after": reserved_after,
        },
        "sentCancelDualReconcile": {
            "reserve": sent_reserve,
            "markSent": sent_mark,
            "beforeCancel": sent_before_cancel,
            "cancel": sent_cancel,
            "beforeReconcile": sent_before_reconcile,
            "reconcile": sent_reconcile,
            "afterReconcile": sent_after_reconcile,
            "reclaim": sent_reclaim,
            "after": sent_after,
        },
        "sentLeaseReclaim": {
            "reserve": reclaim_reserve,
            "markSent": reclaim_mark,
            "before": reclaim_before,
            "reclaim": reclaim_process,
            "afterTransition": reclaim_after_transition,
            "lateReconcile": reclaim_late,
            "after": reclaim_after,
        },
        "toolCancelDualComplete": {
            "begin": tool_begin,
            "beforeCancel": tool_before_cancel,
            "cancel": tool_cancel,
            "beforeComplete": tool_before_complete,
            "complete": tool_complete,
            "afterComplete": tool_after_complete,
            "reclaim": tool_reclaim_finish,
            "after": tool_after,
        },
        "toolLeaseReclaim": {
            "begin": tool_reclaim_begin,
            "before": tool_reclaim_before,
            "reclaim": tool_reclaim_process,
            "afterTransition": tool_reclaim_after_transition,
            "lateComplete": tool_reclaim_late,
            "after": tool_reclaim_after,
        },
        "locks": lock_projection(harness),
        "assertions": {
            "reservedSendFencedAfterCancel": True,
            "sentCallReconciledExactlyOnceAfterCancel": True,
            "sentCallReclaimedToOutcomeUnknownExactlyOnce": True,
            "providerUsageNotDuplicated": True,
            "toolCallCompletedExactlyOnceAfterCancel": True,
            "toolCallReclaimedToAbandonedExactlyOnce": True,
            "toolAccountingNotDuplicated": True,
            "eventSequencesUniqueAndContiguous": True,
        },
    }

def event_sequence_oracle(state: dict[str, Any]) -> dict[str, object]:
    sequences = [int(event["seq"]) for event in state["events"]]
    return {
        "eventSequences": sequences,
        "unique": len(sequences) == len(set(sequences)),
        "strictlyOrdered": sequences == list(range(1, len(sequences) + 1)),
    }


def scenario_f_cancel_races(harness: Any, database_url: str, timeout_seconds: float) -> dict[str, Any]:
    claim_fixture = harness.seed_run("r2-f-claim")
    claim_before = projection(harness, claim_fixture.run_id)
    claim_race = launch_workers(
        scenario="f_cancel_races", database_url=database_url, schema=harness.schema,
        worker_specs=[
            {"workerInstanceId": "f-claim", "operation": "claim_next", "retryNoneSeconds": "2"},
            {"workerInstanceId": "f-cancel", "operation": "cancel", "runId": claim_fixture.run_id, "workspaceId": harness.workspace_id, "actorUserId": harness.user_id, "expectedStateVersion": "1"},
        ], timeout_seconds=timeout_seconds,
    )
    claim_after = projection(harness, claim_fixture.run_id)
    cancel_record = next(record for record in claim_race["processRecords"] if record["operation"] == "cancel")
    no_work = None
    if cancel_record["outcome"] == "cancelled":
        no_work = launch_workers(
            scenario="f_cancel_races", database_url=database_url, schema=harness.schema,
            worker_specs=[{"workerInstanceId": "f-after-cancel", "operation": "claim_next"}], timeout_seconds=timeout_seconds,
        )
        assert no_work["processRecords"][0]["outcome"] == "none"
    assert event_sequence_oracle(claim_after)["unique"]
    assert event_sequence_oracle(claim_after)["strictlyOrdered"]

    complete_fixture = harness.seed_run("r2-f-complete")
    active = harness.claim_specific(complete_fixture, 0, "f-active")
    complete_before = projection(harness, complete_fixture.run_id)
    complete_race = launch_workers(
        scenario="f_cancel_races", database_url=database_url, schema=harness.schema,
        worker_specs=[
            {"workerInstanceId": "f-complete", "operation": "complete", "attemptId": active.attempt_id, "leaseToken": active.lease_token, "outputSha256": r0.sha("r2-f-complete")},
            {"workerInstanceId": "f-cancel-complete", "operation": "cancel", "runId": complete_fixture.run_id, "workspaceId": harness.workspace_id, "actorUserId": harness.user_id, "expectedStateVersion": "3"},
        ], timeout_seconds=timeout_seconds,
    )
    complete_after = projection(harness, complete_fixture.run_id)
    terminal_events = [event for event in complete_after["events"] if event["event_type"] == "step_succeeded"]
    assert len(terminal_events) <= 1
    assert event_sequence_oracle(complete_after)["unique"]
    assert event_sequence_oracle(complete_after)["strictlyOrdered"]
    reclaim_fixture = harness.seed_run("r2-f-reclaim")
    old_lease = harness.claim_specific(reclaim_fixture, 0, "f-reclaim-old")
    with harness.sessions() as db:
        old_attempt = db.get(r15.ResearchStepAttempt, old_lease.attempt_id)
        assert old_attempt is not None
        old_attempt.lease_expires_at = datetime.now(UTC) - timedelta(seconds=2)
        db.commit()
    reclaim_before = projection(harness, reclaim_fixture.run_id)
    reclaim_race = launch_workers(
        scenario="f_cancel_races", database_url=database_url, schema=harness.schema,
        worker_specs=[
            {"workerInstanceId": "f-reclaim", "operation": "reclaim"},
            {"workerInstanceId": "f-cancel-reclaim", "operation": "cancel", "runId": reclaim_fixture.run_id, "workspaceId": harness.workspace_id, "actorUserId": harness.user_id, "expectedStateVersion": "3"},
        ], timeout_seconds=timeout_seconds,
    )
    reclaim_after_race = projection(harness, reclaim_fixture.run_id)
    reclaim_cancel = next(record for record in reclaim_race["processRecords"] if record["operation"] == "cancel")
    cancel_finish = None
    if reclaim_cancel["outcome"] != "cancelled":
        cancel_finish = launch_workers(
            scenario="f_cancel_races", database_url=database_url, schema=harness.schema,
            worker_specs=[{"workerInstanceId": "f-cancel-reclaim-finish", "operation": "cancel", "runId": reclaim_fixture.run_id, "workspaceId": harness.workspace_id, "actorUserId": harness.user_id, "expectedStateVersion": str(reclaim_after_race["run"]["state_version"])}], timeout_seconds=timeout_seconds,
        )
        assert cancel_finish["processRecords"][0]["outcome"] == "cancelled"
    reclaim_after = projection(harness, reclaim_fixture.run_id)
    reclaim_finish = None
    if reclaim_after["run"]["status"] != "cancelled":
        reclaim_finish = launch_workers(
            scenario="f_cancel_races", database_url=database_url, schema=harness.schema,
            worker_specs=[{"workerInstanceId": "f-reclaim-finish", "operation": "reclaim"}], timeout_seconds=timeout_seconds,
        )
        reclaim_after = projection(harness, reclaim_fixture.run_id)
    assert reclaim_after["run"]["status"] == "cancelled"
    assert all(attempt["status"] != "running" for attempt in reclaim_after["attempts"])
    assert sum(attempt["status"] == "abandoned" for attempt in reclaim_after["attempts"]) <= 1
    late_old = launch_workers(
        scenario="f_cancel_races", database_url=database_url, schema=harness.schema,
        worker_specs=[{"workerInstanceId": "f-reclaim-late", "operation": "complete", "attemptId": old_lease.attempt_id, "leaseToken": old_lease.lease_token, "outputSha256": r0.sha("r2-f-reclaim-late")}], timeout_seconds=timeout_seconds,
    )
    no_active = launch_workers(
        scenario="f_cancel_races", database_url=database_url, schema=harness.schema,
        worker_specs=[{"workerInstanceId": "f-reclaim-post-cancel", "operation": "claim_next"}], timeout_seconds=timeout_seconds,
    )
    assert late_old["processRecords"][0]["outcome"] == "fenced"
    assert no_active["processRecords"][0]["outcome"] == "none"
    assert event_sequence_oracle(reclaim_after)["unique"]
    assert event_sequence_oracle(reclaim_after)["strictlyOrdered"]
    return {
        "claimVsCancel": {"before": claim_before, "after": claim_after, "process": claim_race, "postCancelClaim": no_work, "eventSequence": event_sequence_oracle(claim_after)},
        "completeVsCancel": {"before": complete_before, "after": complete_after, "process": complete_race, "eventSequence": event_sequence_oracle(complete_after)},
        "reclaimVsCancel": {"before": reclaim_before, "after": reclaim_after, "process": reclaim_race, "cancellationFinish": cancel_finish, "reclaimFinish": reclaim_finish, "raceAfter": reclaim_after_race, "lateOldToken": late_old, "postCancelClaim": no_active, "eventSequence": event_sequence_oracle(reclaim_after)},
        "locks": lock_projection(harness),
        "assertions": {"legalSingleTerminal": True, "noPostCancelWork": True, "noNewActiveLeaseAfterCancellation": True, "oldTokenFenced": True, "noDuplicateTerminalEvents": True},
    }

def scenario_d_step_id_tiebreak(harness: Any, database_url: str, timeout_seconds: float) -> dict[str, Any]:
    fixture = harness.seed_run("r2-d", step_count=2)
    equal_time = datetime.now(UTC) - timedelta(seconds=1)
    with harness.sessions() as db:
        for step_id in fixture.step_ids:
            step = db.get(r15.ResearchStep, step_id)
            assert step is not None
            step.queued_at = equal_time
            step.created_at = equal_time
        db.commit()
    expected_step_id = min(fixture.step_ids)
    evidence = launch_workers(
        scenario="d_step_id_tiebreak",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[{"workerInstanceId": "d-1", "operation": "claim_next"}],
        timeout_seconds=timeout_seconds,
    )
    record = evidence["processRecords"][0]
    state = projection(harness, fixture.run_id)
    assert record["outcome"] == "claimed"
    assert record["lease"]["stepId"] == expected_step_id
    return {
        **evidence,
        "expectedStepId": expected_step_id,
        "dbProjection": state,
        "locks": lock_projection(harness),
        "assertions": {"queuedAtEqual": True, "createdAtEqual": True, "strictStepIdTiebreak": True},
    }


def run_scenario(name: str, database_url: str, timeout_seconds: float) -> dict[str, Any]:
    if name == "identity_probe":
        return scenario_identity(database_url, timeout_seconds)
    harness = r0.ContentionHarness(database_url)
    harness.setup()
    try:
        if name == "a_same_step_claim":
            return scenario_a_same_step(harness, database_url, timeout_seconds)
        if name == "b_processor_exclusion":
            return scenario_b_processor_exclusion(harness, database_url, timeout_seconds)
        if name == "c_cap_n":
            return scenario_c_cap_n(harness, database_url, timeout_seconds)
        if name == "d_step_id_tiebreak":
            return scenario_d_step_id_tiebreak(harness, database_url, timeout_seconds)
        if name == "e_lease_reclaim_late_completion":
            return scenario_e_lease_reclaim_late_completion(harness, database_url, timeout_seconds)
        if name == "f_cancel_races":
            return scenario_f_cancel_races(harness, database_url, timeout_seconds)
        if name == "g_provider_reconcile":
            return scenario_g_provider_reconcile(harness, database_url, timeout_seconds)
        if name == "h_join_readiness":
            return h_join.run_scenario(
                harness,
                database_url,
                timeout_seconds,
                launch_workers=launch_workers,
                projection=projection,
                lock_projection=lock_projection,
            )
        if name == "i_conflict_decision_resume":
            return i_conflict.run_scenario(
                harness,
                database_url,
                timeout_seconds,
                projection=projection,
                lock_projection=lock_projection,
                observe_ready_worker_backends=observe_ready_worker_backends,
            )
        if name == "j_crash_recovery":
            return j_crash.run_scenario(
                harness,
                database_url,
                timeout_seconds,
                launch_workers=launch_workers,
                projection=projection,
                observe_ready_worker_backends=observe_ready_worker_backends,
            )
        if name == "l_budget_exhaustion_reconcile":
            return l_budget.run_scenario(harness, database_url, timeout_seconds)
        raise AssertionError(f"unsupported scenario: {name}")
    finally:
        harness.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=("all", *SCENARIOS), default="all")
    parser.add_argument("--database-url-env", default="R2_DATABASE_URL")
    parser.add_argument("--database-url", help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ready-timeout-seconds", type=float, default=25.0)
    args = parser.parse_args()

    database_url = os.environ.get(args.database_url_env) or args.database_url
    if not database_url:
        parser.error(
            f"database URL environment variable is missing: {args.database_url_env}"
        )
    source_url = make_url(database_url)
    database_name = f"citeframe_r2_{os.urandom(6).hex()}"
    isolated_url = source_url.set(database=database_name).render_as_string(hide_password=False)
    admin_engine = create_engine(source_url.set(database="postgres"), future=True)
    database_created = False
    cleanup: dict[str, object] = {"temporaryDatabase": database_name, "forceDropAttempted": False, "forceDropSucceeded": False}
    report: dict[str, Any] = {
        "artifactKind": "r2-postgres-process-concurrency-v2",
        "schemaVersion": "2",
        "generatedAt": datetime.now(UTC).isoformat(),
        "baseSha": git("rev-parse", "HEAD"),
        "candidateHeadSha": git("rev-parse", "HEAD"),
        "candidateFileHashes": candidate_file_hashes(),
        "exactCommand": redacted_cli_command(
            [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]
        ),
        "environment": {"pythonExecutable": sys.executable, "platform": sys.platform},
        "coverage": {
            "implementedScenarios": list(SCENARIOS),
            "blockedScenarios": list(BLOCKED_SCENARIOS),
            "r2Complete": False,
        },
        "scenarios": {},
        "cleanup": cleanup,
        "qualityEvidence": False,
        "passed": False,
    }
    exit_status = 1
    try:
        with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
        database_created = True
        with admin_engine.connect() as connection:
            report["postgresql"] = {"serverVersion": connection.scalar(text("SHOW server_version"))}
        scenario_names = SCENARIOS if args.scenario == "all" else (args.scenario,)
        for scenario_name in scenario_names:
            report["scenarios"][scenario_name] = run_scenario(
                scenario_name, isolated_url, args.ready_timeout_seconds
            )
        report["passed"] = True
        exit_status = 0
    except Exception as error:  # noqa: BLE001 - artifact captures failure evidence too
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        try:
            if database_created:
                cleanup["forceDropAttempted"] = True
                with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                    connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))
                cleanup["forceDropSucceeded"] = True
        except Exception as error:  # noqa: BLE001 - cleanup outcome is evidence
            cleanup["error"] = f"{type(error).__name__}: {error}"
            report["passed"] = False
            exit_status = 1
        finally:
            admin_engine.dispose()
        secrets = {database_url}
        if source_url.password:
            secrets.add(source_url.password)
        report = redact_sensitive_payload(report, secrets)
        canonical = (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode()
        report["payloadWithoutHashFieldSha256"] = sha256_bytes(canonical)
        payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
        atomic_write(args.output.resolve(), payload)
        print(json.dumps({"output": str(args.output), "passed": report["passed"], "artifactSha256": sha256_bytes(payload)}, sort_keys=True))
    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())
