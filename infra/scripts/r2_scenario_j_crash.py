"""R2-J real-OS-crash and lease-recovery proof against PostgreSQL.

This module is proof-only.  It invokes the accepted production claim, reclaim, and
completion commands from independent interpreters and never edits a lease expiry or a
production row directly.  The first claim holder is killed while its committed lease and
PostgreSQL backend are live; database ``clock_timestamp()`` is the expiry oracle.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

from citeframe_persistence.models import ResearchStep, ResearchStepDependency
from sqlalchemy import select, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
CLAIM_WORKER = ROOT / "infra/scripts/r2_scenario_j_crash_worker.py"


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _read_ready(
    path: Path,
    process: subprocess.Popen[str],
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.is_file():
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("phase") == "failed":
                raise AssertionError(
                    f"R2-J claim child failed before its barrier: {record.get('errorType')}"
                )
            return record
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            raise AssertionError(
                "R2-J claim child exited before publishing a ready record "
                f"(status={process.returncode}, stdoutEmpty={not stdout}, stderrEmpty={not stderr})"
            )
        time.sleep(0.02)
    raise TimeoutError("R2-J claim child did not publish its ready barrier")


def _read_secret_once(path: Path) -> str:
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise AssertionError("R2-J secret IPC contained no lease token")
    path.unlink()
    path.parent.rmdir()
    return value


def _windows_parent_chain(child_pid: int) -> tuple[int | None, list[int]]:
    import ctypes
    from ctypes import wintypes

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessEntry32W),
    ]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessEntry32W),
    ]
    kernel32.Process32NextW.restype = wintypes.BOOL
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    invalid_handle = ctypes.c_void_p(-1).value
    snapshot_value = ctypes.cast(snapshot, ctypes.c_void_p).value
    if snapshot_value in {None, invalid_handle}:
        raise OSError("Windows process snapshot failed for R2-J identity proof")
    parents: dict[int, int] = {}
    try:
        entry = ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(ProcessEntry32W)
        has_entry = bool(kernel32.Process32FirstW(snapshot, ctypes.byref(entry)))
        while has_entry:
            parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            has_entry = bool(kernel32.Process32NextW(snapshot, ctypes.byref(entry)))
    finally:
        kernel32.CloseHandle(snapshot)
    direct_parent = parents.get(child_pid)
    chain: list[int] = []
    current = child_pid
    seen: set[int] = set()
    while current in parents and current not in seen:
        seen.add(current)
        parent = parents[current]
        if parent == 0:
            break
        chain.append(parent)
        current = parent
    return direct_parent, chain


def _windows_process_identity(handle: int, child_pid: int) -> dict[str, Any]:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    native_handle = wintypes.HANDLE(handle)
    exit_code = wintypes.DWORD()
    if not kernel32.GetExitCodeProcess(native_handle, ctypes.byref(exit_code)):
        raise OSError("Windows GetExitCodeProcess failed for R2-J interpreter")
    buffer = ctypes.create_unicode_buffer(32768)
    buffer_size = wintypes.DWORD(len(buffer))
    if not kernel32.QueryFullProcessImageNameW(
        native_handle,
        0,
        buffer,
        ctypes.byref(buffer_size),
    ):
        raise OSError("Windows QueryFullProcessImageNameW failed for R2-J interpreter")
    creation = wintypes.FILETIME()
    exit_time = wintypes.FILETIME()
    kernel = wintypes.FILETIME()
    user = wintypes.FILETIME()
    if not kernel32.GetProcessTimes(
        native_handle,
        ctypes.byref(creation),
        ctypes.byref(exit_time),
        ctypes.byref(kernel),
        ctypes.byref(user),
    ):
        raise OSError("Windows GetProcessTimes failed for R2-J interpreter")
    creation_ticks = (int(creation.dwHighDateTime) << 32) | int(
        creation.dwLowDateTime
    )
    creation_time = datetime(1601, 1, 1, tzinfo=UTC) + timedelta(
        microseconds=creation_ticks // 10
    )
    executable = Path(buffer.value).resolve()
    return {
        "interpreterPid": child_pid,
        "exitCode": int(exit_code.value),
        "alive": int(exit_code.value) == 259,
        "executablePath": str(executable),
        "executableSha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "creationTimeFiletime100ns": creation_ticks,
        "creationTimeUtc": creation_time.isoformat(),
    }


class _WindowsCrashTarget:
    def __init__(
        self,
        *,
        handle: int,
        child_pid: int,
        open_identity: dict[str, Any],
    ) -> None:
        self.handle = handle
        self.child_pid = child_pid
        self.open_identity = open_identity
        self.closed = False

    def snapshot(self) -> dict[str, Any]:
        if self.closed:
            raise RuntimeError("R2-J Windows process handle was already closed")
        return _windows_process_identity(self.handle, self.child_pid)

    def terminate(self, timeout_seconds: float) -> dict[str, Any]:
        import ctypes
        from ctypes import wintypes

        before_terminate = self.snapshot()
        stable_keys = (
            "interpreterPid",
            "executablePath",
            "executableSha256",
            "creationTimeFiletime100ns",
        )
        identity_stable = all(
            before_terminate[key] == self.open_identity[key] for key in stable_keys
        )
        if not before_terminate["alive"] or not identity_stable:
            raise AssertionError("R2-J interpreter identity changed before strong kill")
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        if not kernel32.TerminateProcess(wintypes.HANDLE(self.handle), 137):
            raise OSError("Windows TerminateProcess failed for R2-J interpreter")
        wait_result = kernel32.WaitForSingleObject(
            wintypes.HANDLE(self.handle),
            max(1, int(timeout_seconds * 1000)),
        )
        if wait_result != 0:
            raise TimeoutError("Windows TerminateProcess target did not exit")
        return {
            "identityImmediatelyBeforeTerminate": before_terminate,
            "identityStableBeforeTerminate": identity_stable,
            "sameHandleUsedForAliveCheckAndTerminate": True,
        }

    def close(self) -> None:
        if self.closed:
            return
        import ctypes
        from ctypes import wintypes

        ctypes.windll.kernel32.CloseHandle(  # type: ignore[attr-defined]
            wintypes.HANDLE(self.handle)
        )
        self.closed = True


def _open_windows_crash_target(
    process: subprocess.Popen[str],
    child_pid: int,
) -> tuple[_WindowsCrashTarget | None, dict[str, Any]]:
    if os.name != "nt":
        return None, {
            "method": "subprocess_process_handle_poll",
            "popenPid": process.pid,
            "interpreterPid": child_pid,
            "launcherIsAncestor": child_pid == process.pid,
            "alive": process.poll() is None,
        }
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    access = 0x0001 | 0x1000 | 0x00100000
    native_handle = kernel32.OpenProcess(
        access,
        False,
        child_pid,
    )
    if not native_handle:
        raise OSError("Windows OpenProcess failed for R2-J interpreter")
    handle = int(ctypes.cast(native_handle, ctypes.c_void_p).value or 0)
    target = _WindowsCrashTarget(
        handle=handle,
        child_pid=child_pid,
        open_identity=_windows_process_identity(handle, child_pid),
    )
    direct_parent, parent_chain = _windows_parent_chain(child_pid)
    expected_executable = Path(
        getattr(sys, "_base_executable", sys.executable)
    ).resolve()
    expected_hash = hashlib.sha256(expected_executable.read_bytes()).hexdigest()
    launcher_is_ancestor = process.pid in parent_chain
    executable_matches = (
        target.open_identity["executableSha256"] == expected_hash
    )
    evidence = {
        **target.open_identity,
        "method": "one persistent Windows process handle",
        "popenPid": process.pid,
        "interpreterParentPid": direct_parent,
        "interpreterParentChain": parent_chain,
        "launcherIsAncestor": launcher_is_ancestor,
        "expectedExecutablePath": str(expected_executable),
        "expectedExecutableSha256": expected_hash,
        "executableMatchesExpectedPython": executable_matches,
        "sameHandleReservedForTerminate": True,
    }
    if (
        child_pid == process.pid
        or child_pid == os.getpid()
        or not launcher_is_ancestor
        or not executable_matches
        or not target.open_identity["alive"]
    ):
        target.close()
        raise AssertionError("R2-J rejected an invalid Windows interpreter target")
    return target, evidence


def _strong_kill(
    process: subprocess.Popen[str],
    child_pid: int,
    windows_target: _WindowsCrashTarget | None,
    timeout_seconds: float,
) -> tuple[str, dict[str, Any]]:
    """Kill the interpreter that owns the committed lease, not a venv redirector."""
    if os.name != "nt":
        if child_pid != process.pid:
            raise AssertionError("POSIX R2-J child PID did not match the Popen PID")
        process.kill()
        return "subprocess.Popen.kill -> POSIX SIGKILL", {
            "identityStableBeforeTerminate": True,
            "sameHandleUsedForAliveCheckAndTerminate": True,
        }
    if windows_target is None or windows_target.child_pid != child_pid:
        raise AssertionError("R2-J has no verified persistent Windows interpreter handle")
    try:
        kill_evidence = windows_target.terminate(timeout_seconds)
    finally:
        windows_target.close()
    return (
        "Windows TerminateProcess through the same verified interpreter handle",
        kill_evidence,
    )


def _observe_attempt_backend(
    harness: Any,
    *,
    attempt_id: str,
    backend_pid: int,
) -> dict[str, Any]:
    with harness.monitor_engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT
                    attempt.id AS "attemptId",
                    attempt.attempt_number AS "attemptNumber",
                    attempt.status AS "attemptStatus",
                    attempt.error_code AS "attemptErrorCode",
                    attempt.lease_expires_at AS "leaseExpiresAt",
                    step.id AS "stepId",
                    step.status AS "stepStatus",
                    step.current_attempt_number AS "currentAttemptNumber",
                    clock_timestamp() AS "dbNow",
                    clock_timestamp() >= attempt.lease_expires_at AS "leaseExpired"
                FROM research_step_attempts AS attempt
                JOIN research_steps AS step ON step.id = attempt.step_id
                WHERE attempt.id = :attempt_id
                """
            ),
            {"attempt_id": attempt_id},
        ).mappings().one()
        activity = connection.execute(
            text(
                """
                SELECT pid AS "pgBackendPid", datname, application_name AS "applicationName",
                       state, wait_event_type AS "waitEventType", wait_event AS "waitEvent"
                FROM pg_stat_activity
                WHERE pid = :pid AND datname = current_database()
                """
            ),
            {"pid": backend_pid},
        ).mappings().one_or_none()
        locks = connection.execute(
            text(
                """
                SELECT locktype AS "lockType", mode, granted,
                       CASE WHEN relation IS NULL THEN NULL ELSE relation::regclass::text END AS relation
                FROM pg_locks
                WHERE pid = :pid
                ORDER BY locktype, mode, granted, relation
                """
            ),
            {"pid": backend_pid},
        ).mappings().all()
    return _json_value(
        {
            "attemptAndStep": dict(row),
            "backend": dict(activity) if activity is not None else None,
            "locks": [dict(lock) for lock in locks],
        }
    )


def _wait_backend_absent(
    harness: Any,
    backend_pid: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    polls = 0
    while time.monotonic() < deadline:
        polls += 1
        with harness.monitor_engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT clock_timestamp() AS "dbNow",
                           EXISTS(
                               SELECT 1 FROM pg_stat_activity
                               WHERE pid = :pid AND datname = current_database()
                           ) AS "backendExists"
                    """
                ),
                {"pid": backend_pid},
            ).mappings().one()
        if not row.backendExists:
            return _json_value({"pollCount": polls, **dict(row)})
        time.sleep(0.02)
    raise TimeoutError("killed R2-J child PostgreSQL backend did not disappear")


def _wait_for_database_expiry(
    harness: Any,
    attempt_id: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    first: dict[str, Any] | None = None
    last: dict[str, Any] | None = None
    polls = 0
    while time.monotonic() < deadline:
        polls += 1
        with harness.monitor_engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT clock_timestamp() AS "dbNow", lease_expires_at AS "leaseExpiresAt",
                           clock_timestamp() >= lease_expires_at AS "expiredByDatabaseClock"
                    FROM research_step_attempts
                    WHERE id = :attempt_id
                    """
                ),
                {"attempt_id": attempt_id},
            ).mappings().one()
        sample = _json_value(dict(row))
        first = first or sample
        last = sample
        if row.expiredByDatabaseClock:
            return {
                "oracle": "PostgreSQL clock_timestamp() >= persisted lease_expires_at",
                "pollCount": polls,
                "first": first,
                "last": last,
                "expired": True,
            }
        time.sleep(0.05)
    raise TimeoutError(f"R2-J lease did not expire by database clock; last={last}")


def _production_hashes(module_names: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for module_name in module_names:
        module_path = Path(importlib.import_module(module_name).__file__).resolve()
        result[module_name] = hashlib.sha256(module_path.read_bytes()).hexdigest()
    return result


def seed_crash_fixture(harness: Any) -> Any:
    fixture = harness.seed_run("r2-j-crash", step_count=2)
    with harness.sessions() as db:
        dependent = db.get(ResearchStep, fixture.step_ids[1])
        if dependent is None:
            raise AssertionError("R2-J dependent fixture Step was not created")
        dependent.status = "pending"
        dependent.queued_at = None
        dependent.started_at = None
        dependent.finished_at = None
        db.add(
            ResearchStepDependency(
                step_id=dependent.id,
                depends_on_step_id=fixture.step_ids[0],
            )
        )
        db.commit()
    return fixture


def full_projection(
    harness: Any,
    run_id: str,
    projection: Callable[[Any, str], dict[str, Any]],
) -> dict[str, Any]:
    state = projection(harness, run_id)
    with harness.sessions() as db:
        dependencies = db.execute(
            select(
                ResearchStepDependency.step_id,
                ResearchStepDependency.depends_on_step_id,
            )
            .join(ResearchStep, ResearchStep.id == ResearchStepDependency.step_id)
            .where(ResearchStep.run_id == run_id)
            .order_by(
                ResearchStepDependency.step_id,
                ResearchStepDependency.depends_on_step_id,
            )
        ).all()
    state["dependencies"] = [
        {
            "step_id": row.step_id,
            "depends_on_step_id": row.depends_on_step_id,
        }
        for row in dependencies
    ]
    return state


def dependent_stage_oracle(
    stages: dict[str, dict[str, Any]],
    *,
    upstream_step_id: str,
    dependent_step_id: str,
) -> dict[str, Any]:
    expected_dependency = [
        {
            "step_id": dependent_step_id,
            "depends_on_step_id": upstream_step_id,
        }
    ]
    precompletion_names = (
        "oldClaimCommitted",
        "afterKill",
        "afterDatabaseExpiry",
        "afterReclaim",
        "replacementClaimCommitted",
        "afterLateOldCompletion",
    )
    stage_results: dict[str, dict[str, Any]] = {}
    for name, state in stages.items():
        dependent = next(
            (item for item in state["steps"] if item["id"] == dependent_step_id),
            None,
        )
        attempts = [
            item for item in state["attempts"] if item["step_id"] == dependent_step_id
        ]
        queued_events = [
            item
            for item in state["events"]
            if item["event_type"] == "step_queued"
            and item.get("step_id") == dependent_step_id
        ]
        expected_status = "queued" if name == "afterReplacementCompletion" else "pending"
        expected_queue_events = 1 if name == "afterReplacementCompletion" else 0
        stage_results[name] = {
            "status": dependent["status"] if dependent is not None else None,
            "attemptCount": len(attempts),
            "queuedEventCount": len(queued_events),
            "dependencyExact": state.get("dependencies") == expected_dependency,
            "valid": (
                dependent is not None
                and dependent["status"] == expected_status
                and len(attempts) == 0
                and len(queued_events) == expected_queue_events
                and state.get("dependencies") == expected_dependency
            ),
        }
    return {
        "precompletionStageNames": list(precompletion_names),
        "stages": stage_results,
        "dependencyExactAtEveryStage": all(
            item["dependencyExact"] for item in stage_results.values()
        ),
        "dependentPendingWithoutAttemptBeforeReplacementCompletion": all(
            stage_results[name]["valid"] for name in precompletion_names
        ),
        "dependentQueuedExactlyOnceAfterReplacementCompletion": stage_results.get(
            "afterReplacementCompletion", {}
        ).get("valid", False),
        "valid": all(item["valid"] for item in stage_results.values()),
    }


def derive_process_lock_diagnostics(
    process_records: list[dict[str, Any]],
) -> dict[str, Any]:
    settings = [record.get("lockTimeoutSetting") for record in process_records]
    sqlstates = [record.get("sqlState") for record in process_records]
    all_settings_observed = all(isinstance(value, str) and value for value in settings)
    disabled_settings = all(
        re.fullmatch(r"0(?:\.0+)?(?:ms|s|min|h|d)?", str(value).strip()) is not None
        for value in settings
    )
    lock_timeout_records = [
        record
        for record in process_records
        if str(record.get("sqlState") or "") == "55P03"
    ]
    unexpected_sqlstates = sorted(
        {
            str(value)
            for value in sqlstates
            if value not in {None, "", "55P03"}
        }
    )
    return {
        "evidenceSource": "each child process SHOW lock_timeout plus caught DBAPI SQLSTATE",
        "processCount": len(process_records),
        "lockTimeoutSettings": settings,
        "sqlStates": sqlstates,
        "allLockTimeoutSettingsObserved": all_settings_observed,
        "allLockTimeoutSettingsDisabled": disabled_settings,
        "lockTimeoutsObserved": len(lock_timeout_records),
        "lockTimeoutWorkerInstanceIds": [
            item.get("workerInstanceId") for item in lock_timeout_records
        ],
        "unexpectedSqlStates": unexpected_sqlstates,
        "valid": (
            bool(process_records)
            and all_settings_observed
            and disabled_settings
            and not lock_timeout_records
            and not unexpected_sqlstates
        ),
    }


def _start_claim_child(
    *,
    operation: str,
    database_url: str,
    harness: Any,
    fixture: Any,
    worker_instance_id: str,
    lease_seconds: int,
    directory: Path,
    attempt_id: str | None = None,
    lease_token: str | None = None,
    output_sha256: str | None = None,
) -> tuple[subprocess.Popen[str], dict[str, Path]]:
    paths = {
        "ready": directory / f"{worker_instance_id}.ready.json",
        "secret": directory
        / f".{worker_instance_id}.lease-secret-{os.urandom(8).hex()}"
        / "lease.secret",
        "release": directory / f"{worker_instance_id}.release",
        "cleanup": directory / f"{worker_instance_id}.normal-cleanup",
        "result": directory / f"{worker_instance_id}.result.json",
    }
    environment = os.environ.copy()
    environment.update(
        {
            "CITEFRAME_R2_DATABASE_URL": database_url,
            "CITEFRAME_R2_J_SCHEMA": harness.schema,
            "CITEFRAME_R2_J_RUN_ID": fixture.run_id,
            "CITEFRAME_R2_J_STEP_KEY": fixture.step_keys[0],
            "CITEFRAME_R2_J_BRANCH_KEY": fixture.branch_keys[0],
            "CITEFRAME_R2_J_WORKER_INSTANCE_ID": worker_instance_id,
            "CITEFRAME_R2_J_LEASE_SECONDS": str(lease_seconds),
            "CITEFRAME_R2_J_READY_FILE": str(paths["ready"]),
            "CITEFRAME_R2_J_LEASE_SECRET_FILE": str(paths["secret"]),
            "CITEFRAME_R2_J_RELEASE_FILE": str(paths["release"]),
            "CITEFRAME_R2_J_CLEANUP_FILE": str(paths["cleanup"]),
            "CITEFRAME_R2_J_RESULT_FILE": str(paths["result"]),
        }
    )
    if attempt_id is not None:
        environment["CITEFRAME_R2_J_ATTEMPT_ID"] = attempt_id
    if lease_token is not None:
        environment["CITEFRAME_R2_J_LEASE_TOKEN"] = lease_token
    if output_sha256 is not None:
        environment["CITEFRAME_R2_J_OUTPUT_SHA256"] = output_sha256
    command = [sys.executable, str(CLAIM_WORKER), "--operation", operation]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )
    return process, paths


def _finish_released_claim_child(
    process: subprocess.Popen[str],
    paths: dict[str, Path],
    ready: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    paths["release"].write_text("release\n", encoding="utf-8")
    stdout, stderr = process.communicate(timeout=timeout_seconds)
    if process.returncode != 0 or stdout or stderr or not paths["cleanup"].is_file():
        raise AssertionError(
            "R2-J replacement claim child did not exit cleanly and silently "
            f"(status={process.returncode}, stdoutEmpty={not stdout}, stderrEmpty={not stderr})"
        )
    if not paths["result"].is_file():
        raise AssertionError("R2-J child published no final result IPC")
    result = json.loads(paths["result"].read_text(encoding="utf-8"))
    return {
        **ready,
        **result,
        "controllerObservedExitStatus": process.returncode,
        "stdoutWasEmpty": True,
        "stderrWasEmpty": True,
        "normalCleanupMarkerPresent": True,
    }


def launch_j_action(
    *,
    operation: str,
    database_url: str,
    harness: Any,
    fixture: Any,
    worker_instance_id: str,
    timeout_seconds: float,
    directory: Path,
    observe_ready_worker_backends: Callable[
        [str, list[dict[str, Any]]], dict[str, Any]
    ],
    attempt_id: str | None = None,
    lease_token: str | None = None,
    output_sha256: str | None = None,
) -> dict[str, Any]:
    process, paths = _start_claim_child(
        operation=operation,
        database_url=database_url,
        harness=harness,
        fixture=fixture,
        worker_instance_id=worker_instance_id,
        lease_seconds=120,
        directory=directory,
        attempt_id=attempt_id,
        lease_token=lease_token,
        output_sha256=output_sha256,
    )
    ready = _read_ready(paths["ready"], process, timeout_seconds)
    observation = observe_ready_worker_backends(database_url, [ready])
    record = _finish_released_claim_child(process, paths, ready, timeout_seconds)
    return {
        "readyRecords": [ready],
        "readyBarrierBackendObservation": observation,
        "processRecords": [record],
        "workerCommands": [record["argv"]],
    }


def _event(
    state: dict[str, Any],
    *,
    event_type: str,
    step_id: str,
    attempt_id: str | None,
) -> list[dict[str, Any]]:
    return [
        item
        for item in state["events"]
        if item["event_type"] == event_type
        and item.get("step_id") == step_id
        and item.get("attempt_id") == attempt_id
    ]


def crash_event_oracle(
    state: dict[str, Any],
    *,
    step_id: str,
    dependent_step_id: str,
    old_attempt_id: str,
    replacement_attempt_id: str,
    expected_output_sha256: str,
) -> dict[str, Any]:
    sequences = [int(item["seq"]) for item in state["events"]]
    dedupe_keys = [item.get("dedupe_key") for item in state["events"]]
    lifecycle = {
        "oldStarted": _event(
            state,
            event_type="step_started",
            step_id=step_id,
            attempt_id=old_attempt_id,
        ),
        "oldAbandoned": _event(
            state,
            event_type="attempt_abandoned",
            step_id=step_id,
            attempt_id=old_attempt_id,
        ),
        "requeued": _event(
            state,
            event_type="step_queued",
            step_id=step_id,
            attempt_id=None,
        ),
        "replacementStarted": _event(
            state,
            event_type="step_started",
            step_id=step_id,
            attempt_id=replacement_attempt_id,
        ),
        "replacementSucceeded": _event(
            state,
            event_type="step_succeeded",
            step_id=step_id,
            attempt_id=replacement_attempt_id,
        ),
        "dependentQueued": _event(
            state,
            event_type="step_queued",
            step_id=dependent_step_id,
            attempt_id=None,
        ),
    }
    exactly_once = all(len(items) == 1 for items in lifecycle.values())
    lifecycle_seq = {
        name: int(items[0]["seq"]) if len(items) == 1 else None
        for name, items in lifecycle.items()
    }
    ordered_values = list(lifecycle_seq.values())
    strict_order = exactly_once and all(
        left is not None and right is not None and left < right
        for left, right in pairwise(ordered_values)
    )
    attempts = sorted(state["attempts"], key=lambda item: int(item["attempt_number"]))
    old_attempt = next(
        (item for item in attempts if item["id"] == old_attempt_id), None
    )
    replacement_attempt = next(
        (item for item in attempts if item["id"] == replacement_attempt_id), None
    )
    step = next((item for item in state["steps"] if item["id"] == step_id), None)
    dependent_step = next(
        (item for item in state["steps"] if item["id"] == dependent_step_id), None
    )
    attempt_fields = {
        "attempt_number",
        "checkpoint_artifact_id",
        "cost_microunits",
        "error_code",
        "error_message",
        "finished_at",
        "heartbeat_at",
        "id",
        "input_sha256",
        "input_tokens",
        "lease_expires_at",
        "lease_token_hash",
        "output_sha256",
        "output_tokens",
        "provider_call_count",
        "started_at",
        "status",
        "step_id",
        "tool_call_count",
        "worker_instance_id",
        "workspace_id",
    }

    def attempt_timestamps_valid(attempt: dict[str, Any]) -> bool:
        try:
            started = datetime.fromisoformat(str(attempt["started_at"]))
            heartbeat = datetime.fromisoformat(str(attempt["heartbeat_at"]))
            finished = datetime.fromisoformat(str(attempt["finished_at"]))
        except (TypeError, ValueError):
            return False
        return started <= heartbeat <= finished

    common_attempt_values = (
        step is not None
        and old_attempt is not None
        and replacement_attempt is not None
        and set(old_attempt) == attempt_fields
        and set(replacement_attempt) == attempt_fields
        and old_attempt["workspace_id"] == step["workspace_id"]
        and replacement_attempt["workspace_id"] == step["workspace_id"]
        and old_attempt["step_id"] == step_id
        and replacement_attempt["step_id"] == step_id
        and old_attempt["input_sha256"] == step["input_sha256"]
        and replacement_attempt["input_sha256"] == step["input_sha256"]
        and old_attempt["lease_token_hash"] == "[redacted]"
        and replacement_attempt["lease_token_hash"] == "[redacted]"
        and old_attempt["lease_expires_at"] is None
        and replacement_attempt["lease_expires_at"] is None
        and all(
            item[field] == 0
            for item in (old_attempt, replacement_attempt)
            for field in (
                "provider_call_count",
                "tool_call_count",
                "input_tokens",
                "output_tokens",
                "cost_microunits",
            )
        )
        and old_attempt["checkpoint_artifact_id"] is None
        and replacement_attempt["checkpoint_artifact_id"] is None
        and attempt_timestamps_valid(old_attempt)
        and attempt_timestamps_valid(replacement_attempt)
    )
    attempt_lifecycle = (
        len(attempts) == 2
        and common_attempt_values
        and old_attempt["attempt_number"] == 1
        and old_attempt["status"] == "abandoned"
        and old_attempt["error_code"] == "lease_expired"
        and old_attempt["error_message"] == "Research Attempt lease expired."
        and old_attempt["output_sha256"] is None
        and old_attempt["worker_instance_id"] == "j-crash-holder"
        and replacement_attempt["attempt_number"] == 2
        and replacement_attempt["status"] == "succeeded"
        and replacement_attempt["error_code"] is None
        and replacement_attempt["error_message"] is None
        and replacement_attempt["output_sha256"] == expected_output_sha256
        and replacement_attempt["worker_instance_id"] == "j-replacement-claimer"
        and step["status"] == "succeeded"
        and step["current_attempt_number"] == 2
        and step["state_version"] == 6
        and dependent_step is not None
        and dependent_step["status"] == "queued"
        and dependent_step["state_version"] == 2
        and not any(item["step_id"] == dependent_step_id for item in attempts)
        and not any(item["status"] == "running" for item in attempts)
    )
    terminal_events = [
        item
        for item in state["events"]
        if item.get("step_id") == step_id
        and item["event_type"]
        in {"step_succeeded", "step_failed", "step_cancelled"}
    ]
    unique_terminal = (
        len(terminal_events) == 1
        and terminal_events[0]["event_type"] == "step_succeeded"
        and terminal_events[0].get("attempt_id") == replacement_attempt_id
    )
    expected_event_types = [
        "run_status_changed",
        "step_started",
        "attempt_abandoned",
        "step_queued",
        "step_started",
        "step_succeeded",
        "step_queued",
    ]
    expected_event_step_ids = [
        None,
        step_id,
        step_id,
        step_id,
        step_id,
        step_id,
        dependent_step_id,
    ]
    expected_event_attempt_ids = [
        None,
        old_attempt_id,
        old_attempt_id,
        None,
        replacement_attempt_id,
        replacement_attempt_id,
        None,
    ]
    expected_dedupe = [
        f"worker-run-started:{old_attempt_id}",
        f"step-started:{old_attempt_id}",
        f"attempt-abandoned:{old_attempt_id}",
        f"step-queued:{step_id}:1",
        f"step-started:{replacement_attempt_id}",
        f"step-succeeded:{replacement_attempt_id}",
        f"step-queued:{dependent_step_id}:0",
    ]
    event_rows_exact = (
        step is not None
        and dependent_step is not None
        and [item["event_type"] for item in state["events"]] == expected_event_types
        and [item.get("step_id") for item in state["events"]]
        == expected_event_step_ids
        and [item.get("attempt_id") for item in state["events"]]
        == expected_event_attempt_ids
        and dedupe_keys == expected_dedupe
        and all(item["event_schema_version"] == "1" for item in state["events"])
        and all(item["run_id"] == step["run_id"] for item in state["events"])
        and all(
            item["workspace_id"] == step["workspace_id"] for item in state["events"]
        )
    )
    expected_payloads = [
        {
            "previousStatus": "queued",
            "status": "running",
            "runStateVersion": 2,
            "reasonCode": None,
        },
        {
            "stepId": step_id,
            "stepKind": step["step_kind"] if step is not None else None,
            "branchKey": step["branch_key"] if step is not None else None,
            "attemptId": old_attempt_id,
            "attemptNumber": 1,
            "stepStateVersion": 2,
            "runStateVersion": 3,
        },
        {
            "stepId": step_id,
            "attemptId": old_attempt_id,
            "attemptNumber": 1,
            "reasonCode": "lease_expired",
            "stepStateVersion": 3,
            "runStateVersion": 4,
        },
        {
            "stepId": step_id,
            "stepKind": step["step_kind"] if step is not None else None,
            "branchKey": step["branch_key"] if step is not None else None,
            "attemptNumber": 1,
            "stepStateVersion": 4,
            "runStateVersion": 5,
        },
        {
            "stepId": step_id,
            "stepKind": step["step_kind"] if step is not None else None,
            "branchKey": step["branch_key"] if step is not None else None,
            "attemptId": replacement_attempt_id,
            "attemptNumber": 2,
            "stepStateVersion": 5,
            "runStateVersion": 6,
        },
        {
            "stepId": step_id,
            "stepKind": step["step_kind"] if step is not None else None,
            "attemptId": replacement_attempt_id,
            "attemptNumber": 2,
            "evidenceCount": 0,
            "artifactIds": [],
            "stepStateVersion": 6,
            "runStateVersion": 7,
        },
        {
            "stepId": dependent_step_id,
            "stepKind": (
                dependent_step["step_kind"] if dependent_step is not None else None
            ),
            "branchKey": (
                dependent_step["branch_key"] if dependent_step is not None else None
            ),
            "attemptNumber": 0,
            "stepStateVersion": 2,
            "runStateVersion": 8,
        },
    ]
    event_payloads_exact = (
        len(state["events"]) == len(expected_payloads)
        and [item["payload_json"] for item in state["events"]] == expected_payloads
    )
    event_timestamps_ordered = False
    try:
        event_times = [
            datetime.fromisoformat(str(item["created_at"])) for item in state["events"]
        ]
        event_timestamps_ordered = all(
            left <= right for left, right in pairwise(event_times)
        )
    except (TypeError, ValueError):
        pass
    run_versions_exact = (
        state["run"]["state_version"] == 8
        and state["run"]["next_event_seq"] == 8
        and state["run"]["status"] == "running"
    )
    return {
        "eventSequences": sequences,
        "sequencesContiguousFromOne": sequences
        == list(range(1, len(sequences) + 1)),
        "dedupeKeysUnique": (
            all(isinstance(key, str) and key for key in dedupe_keys)
            and len(dedupe_keys) == len(set(dedupe_keys))
        ),
        "eventCounts": {name: len(items) for name, items in lifecycle.items()},
        "eventSequenceByFact": lifecycle_seq,
        "strictCrashRecoveryOrder": strict_order,
        "attemptLifecycleValid": attempt_lifecycle,
        "attemptFieldsExact": common_attempt_values,
        "uniqueReplacementTerminal": unique_terminal,
        "eventRowsExact": event_rows_exact,
        "eventPayloadsExact": event_payloads_exact,
        "eventTimestampsOrdered": event_timestamps_ordered,
        "runAndStepStateVersionsExact": run_versions_exact,
    }


def _projection_digest(state: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _assert_secret_scrub(payload: dict[str, Any], secrets: set[str]) -> None:
    serialized = json.dumps(payload, sort_keys=True)
    leaked = [secret for secret in secrets if secret and secret in serialized]
    if leaked:
        raise AssertionError("R2-J result leaked a connection or lease secret")


def run_scenario(
    harness: Any,
    database_url: str,
    timeout_seconds: float,
    *,
    launch_workers: Callable[..., dict[str, Any]],
    projection: Callable[[Any, str], dict[str, Any]],
    observe_ready_worker_backends: Callable[
        [str, list[dict[str, Any]]], dict[str, Any]
    ],
) -> dict[str, Any]:
    _ = launch_workers  # Main-runner compatibility; J uses its richer isolated child.
    fixture = seed_crash_fixture(harness)
    step_id = fixture.step_ids[0]
    dependent_step_id = fixture.step_ids[1]
    production_before = dict(harness.report["productionSourceSha256"])
    deadlocks_before = harness.deadlock_count()
    holder: subprocess.Popen[str] | None = None
    holder_child_pid: int | None = None
    windows_target: _WindowsCrashTarget | None = None
    old_token = ""
    replacement_token = ""

    with tempfile.TemporaryDirectory(prefix="citeframe-r2-j-") as temporary:
        directory = Path(temporary)
        try:
            holder, holder_paths = _start_claim_child(
                operation="hold_claim",
                database_url=database_url,
                harness=harness,
                fixture=fixture,
                worker_instance_id="j-crash-holder",
                lease_seconds=4,
                directory=directory,
            )
            holder_ready = _read_ready(
                holder_paths["ready"], holder, timeout_seconds
            )
            holder_child_pid = int(holder_ready["osPid"])
            old_attempt_id = str(holder_ready["attemptId"])
            old_token = _read_secret_once(holder_paths["secret"])
            holder_backend_pid = int(holder_ready["pgBackendPid"])
            windows_target, os_alive = _open_windows_crash_target(
                holder, holder_child_pid
            )
            before_kill = _observe_attempt_backend(
                harness,
                attempt_id=old_attempt_id,
                backend_pid=holder_backend_pid,
            )
            old_claim_state = full_projection(
                harness, fixture.run_id, projection
            )
            expected_application_name = "citeframe-r2-j:j-crash-holder"
            if not os_alive["alive"]:
                raise AssertionError("R2-J holder was not OS-alive before strong kill")
            if holder.poll() is not None or (
                os.name != "nt" and holder_child_pid != holder.pid
            ):
                raise AssertionError(
                    "R2-J holder Popen identity was not live "
                    f"(popenPid={holder.pid}, childPid={holder_ready['osPid']}, "
                    f"poll={holder.poll()})"
                )
            if (
                before_kill["attemptAndStep"]["attemptStatus"] != "running"
                or before_kill["attemptAndStep"]["stepStatus"] != "running"
                or before_kill["attemptAndStep"]["leaseExpired"]
            ):
                raise AssertionError("R2-J did not observe a committed live lease before kill")
            if before_kill["backend"] is None:
                raise AssertionError("R2-J holder PostgreSQL backend was not live")
            if (
                holder_ready["applicationName"] != expected_application_name
                or before_kill["backend"]["applicationName"]
                != expected_application_name
            ):
                raise AssertionError("R2-J holder application_name identity was not exact")
            holder_acl = holder_ready.get("secretIpcAcl")
            if (
                not isinstance(holder_acl, dict)
                or not holder_acl.get("verifiedBeforeSecretWrite")
                or (os.name == "nt" and not holder_acl.get("daclProtected"))
            ):
                raise AssertionError("R2-J holder secret IPC ACL was not verified")
            if not any(
                lock["lockType"] == "advisory" and lock["granted"]
                for lock in before_kill["locks"]
            ):
                raise AssertionError("R2-J holder exposed no live PostgreSQL advisory lock")

            # On Windows subprocess.Popen.kill delegates to TerminateProcess.  On POSIX it
            # is SIGKILL.  Neither path runs Python finally/engine disposal in the child.
            termination_method, termination_evidence = _strong_kill(
                holder, holder_child_pid, windows_target, timeout_seconds
            )
            stdout, stderr = holder.communicate(timeout=timeout_seconds)
            if holder.returncode == 0:
                raise AssertionError("R2-J strong-killed child reported a normal exit")
            if stdout or stderr:
                raise AssertionError("R2-J crash holder emitted stdout/stderr")
            holder_process = {
                **holder_ready,
                "terminationMethod": termination_method,
                "exitStatus": holder.returncode,
                "controllerObservedExitStatus": holder.returncode,
                "nonNormalExit": True,
                "stdoutWasEmpty": True,
                "stderrWasEmpty": True,
                "normalCleanupMarkerPresent": holder_paths["cleanup"].exists(),
                "processIdentity": {**os_alive, **termination_evidence},
            }
            if holder_paths["cleanup"].exists():
                raise AssertionError("strong-killed R2-J child ran normal cleanup")

            backend_after_kill = _wait_backend_absent(
                harness, holder_backend_pid, timeout_seconds
            )
            after_kill = _observe_attempt_backend(
                harness,
                attempt_id=old_attempt_id,
                backend_pid=holder_backend_pid,
            )
            after_kill_state = full_projection(
                harness, fixture.run_id, projection
            )
            if (
                after_kill["backend"] is not None
                or after_kill["attemptAndStep"]["attemptStatus"] != "running"
                or after_kill["attemptAndStep"]["stepStatus"] != "running"
            ):
                raise AssertionError(
                    "R2-J crash did not leave the committed lease running after backend loss"
                )

            expiry = _wait_for_database_expiry(
                harness,
                old_attempt_id,
                max(timeout_seconds, 10.0),
            )
            after_expiry_state = full_projection(
                harness, fixture.run_id, projection
            )
            before_reclaim = after_expiry_state
            reclaim = launch_j_action(
                operation="reclaim",
                database_url=database_url,
                harness=harness,
                fixture=fixture,
                worker_instance_id="j-independent-reclaimer",
                timeout_seconds=timeout_seconds,
                directory=directory,
                observe_ready_worker_backends=observe_ready_worker_backends,
            )
            reclaim_record = reclaim["processRecords"][0]
            if (
                reclaim_record["outcome"] != "reclaimed"
                or reclaim_record["reclaimedCount"] != 1
            ):
                raise AssertionError("R2-J production reclaimer did not reclaim one lease")
            after_reclaim = full_projection(harness, fixture.run_id, projection)
            old_attempt = next(
                item for item in after_reclaim["attempts"] if item["id"] == old_attempt_id
            )
            reclaimed_step = next(
                item for item in after_reclaim["steps"] if item["id"] == step_id
            )
            if (
                old_attempt["status"] != "abandoned"
                or old_attempt["error_code"] != "lease_expired"
                or old_attempt["lease_expires_at"] is not None
                or reclaimed_step["status"] != "queued"
            ):
                raise AssertionError("R2-J reclaim facts did not match production semantics")

            replacement, replacement_paths = _start_claim_child(
                operation="claim_export",
                database_url=database_url,
                harness=harness,
                fixture=fixture,
                worker_instance_id="j-replacement-claimer",
                lease_seconds=120,
                directory=directory,
            )
            replacement_ready = _read_ready(
                replacement_paths["ready"], replacement, timeout_seconds
            )
            replacement_token = _read_secret_once(replacement_paths["secret"])
            replacement_acl = replacement_ready.get("secretIpcAcl")
            if (
                not isinstance(replacement_acl, dict)
                or not replacement_acl.get("verifiedBeforeSecretWrite")
                or (os.name == "nt" and not replacement_acl.get("daclProtected"))
            ):
                raise AssertionError("R2-J replacement secret IPC ACL was not verified")
            replacement_observation = observe_ready_worker_backends(
                database_url, [replacement_ready]
            )
            replacement_process = _finish_released_claim_child(
                replacement,
                replacement_paths,
                replacement_ready,
                timeout_seconds,
            )
            replacement_attempt_id = str(replacement_ready["attemptId"])
            if int(replacement_ready["attemptNumber"]) != 2:
                raise AssertionError("R2-J replacement attempt number was not old+1")

            before_late = full_projection(harness, fixture.run_id, projection)
            before_late_digest = _projection_digest(before_late)
            late_completion = launch_j_action(
                operation="complete",
                database_url=database_url,
                harness=harness,
                fixture=fixture,
                worker_instance_id="j-old-token-late-completer",
                timeout_seconds=timeout_seconds,
                directory=directory,
                observe_ready_worker_backends=observe_ready_worker_backends,
                attempt_id=old_attempt_id,
                lease_token=old_token,
                output_sha256=sha("r2-j-old-late-output"),
            )
            if (
                late_completion["processRecords"][0]["outcome"] != "fenced"
                or late_completion["processRecords"][0]["errorCode"]
                != "research_state_conflict"
            ):
                raise AssertionError("R2-J late old-token completion was not fenced")
            after_late = full_projection(harness, fixture.run_id, projection)
            after_late_digest = _projection_digest(after_late)
            if before_late_digest != after_late_digest:
                raise AssertionError("R2-J fenced late completion mutated persisted state")

            expected_replacement_output = sha("r2-j-replacement-output")
            replacement_completion = launch_j_action(
                operation="complete",
                database_url=database_url,
                harness=harness,
                fixture=fixture,
                worker_instance_id="j-replacement-completer",
                timeout_seconds=timeout_seconds,
                directory=directory,
                observe_ready_worker_backends=observe_ready_worker_backends,
                attempt_id=replacement_attempt_id,
                lease_token=replacement_token,
                output_sha256=expected_replacement_output,
            )
            if replacement_completion["processRecords"][0]["outcome"] != "completed":
                raise AssertionError("R2-J replacement completion did not succeed")
            final = full_projection(harness, fixture.run_id, projection)
            event_oracle = crash_event_oracle(
                final,
                step_id=step_id,
                dependent_step_id=dependent_step_id,
                old_attempt_id=old_attempt_id,
                replacement_attempt_id=replacement_attempt_id,
                expected_output_sha256=expected_replacement_output,
            )
            if not all(
                (
                    event_oracle["sequencesContiguousFromOne"],
                    event_oracle["dedupeKeysUnique"],
                    event_oracle["strictCrashRecoveryOrder"],
                    event_oracle["attemptLifecycleValid"],
                    event_oracle["uniqueReplacementTerminal"],
                    event_oracle["eventRowsExact"],
                    event_oracle["eventPayloadsExact"],
                    event_oracle["eventTimestampsOrdered"],
                    event_oracle["runAndStepStateVersionsExact"],
                )
            ):
                raise AssertionError(f"R2-J event/attempt oracle failed: {event_oracle}")

            deadlocks_after = harness.deadlock_count()
            if deadlocks_after != deadlocks_before:
                raise AssertionError("R2-J observed a PostgreSQL deadlock")
            process_records = [
                holder_process,
                reclaim["processRecords"][0],
                replacement_process,
                late_completion["processRecords"][0],
                replacement_completion["processRecords"][0],
            ]
            lock_diagnostics = derive_process_lock_diagnostics(process_records)
            if not lock_diagnostics["valid"]:
                raise AssertionError(
                    f"R2-J process-derived lock diagnostics failed: {lock_diagnostics}"
                )
            stage_oracle = dependent_stage_oracle(
                {
                    "oldClaimCommitted": old_claim_state,
                    "afterKill": after_kill_state,
                    "afterDatabaseExpiry": after_expiry_state,
                    "afterReclaim": after_reclaim,
                    "replacementClaimCommitted": before_late,
                    "afterLateOldCompletion": after_late,
                    "afterReplacementCompletion": final,
                },
                upstream_step_id=step_id,
                dependent_step_id=dependent_step_id,
            )
            if not stage_oracle["valid"]:
                raise AssertionError(f"R2-J dependent stage oracle failed: {stage_oracle}")
            production_after = _production_hashes(sorted(production_before))
            if production_after != production_before:
                raise AssertionError("R2-J production source changed during proof execution")

            result = {
                "beforeCrash": before_kill,
                "oldClaimCommittedProjection": old_claim_state,
                "crashedProcess": holder_process,
                "osProcessAliveBeforeKill": os_alive,
                "backendAfterKill": backend_after_kill,
                "persistedStateAfterKill": after_kill,
                "afterKillProjection": after_kill_state,
                "databaseClockExpiry": expiry,
                "afterDatabaseExpiryProjection": after_expiry_state,
                "beforeReclaim": before_reclaim,
                "reclaim": reclaim,
                "afterReclaim": after_reclaim,
                "replacementClaim": {
                    "process": replacement_process,
                    "readyBarrierBackendObservation": replacement_observation,
                },
                "beforeLateCompletion": before_late,
                "lateOldTokenCompletion": late_completion,
                "afterLateCompletion": after_late,
                "lateCompletionZeroMutation": {
                    "beforeSha256": before_late_digest,
                    "afterSha256": after_late_digest,
                    "equal": True,
                },
                "replacementCompletion": replacement_completion,
                "after": final,
                "eventOracle": event_oracle,
                "dependentStageOracle": stage_oracle,
                "locks": {
                    "holderLiveLocks": before_kill["locks"],
                    "replacementLiveObservation": replacement_observation,
                },
                "databaseDiagnostics": {
                    "deadlocksBefore": deadlocks_before,
                    "deadlocksAfter": deadlocks_after,
                    "deadlocksObserved": deadlocks_after - deadlocks_before,
                    "processDerivedLockTimeoutEvidence": lock_diagnostics,
                },
                "productionSourceSha256Before": production_before,
                "productionSourceSha256After": production_after,
                "security": {
                    "leaseTokensPassedOnlyThroughEnvironmentOrSecretIpc": True,
                    "leaseTokensAbsentFromArgvStdoutAndScenarioArtifact": True,
                    "secretIpcFilesDeletedAfterRead": (
                        not holder_paths["secret"].exists()
                        and not replacement_paths["secret"].exists()
                    ),
                    "secretIpcDirectoriesDeletedAfterRead": (
                        not holder_paths["secret"].parent.exists()
                        and not replacement_paths["secret"].parent.exists()
                    ),
                    "strongKilledChildNormalCleanupMarkerAbsent": True,
                    "secretIpcAclEvidence": {
                        "holder": holder_acl,
                        "replacement": replacement_acl,
                    },
                },
                "assertions": {
                    "holderOsProcessAliveBeforeKill": True,
                    "holderBackendAndLocksLiveBeforeKill": True,
                    "leaseCommittedAndRunningBeforeKill": True,
                    "strongKillWasNonNormalExit": True,
                    "backendDisappearedAfterKill": True,
                    "databaseRowsRemainedRunningAfterKill": True,
                    "expiryObservedOnlyByDatabaseClock": True,
                    "productionReclaimAbandonedOldAttempt": True,
                    "oldAttemptErrorLeaseExpired": True,
                    "stepRequeuedAfterReclaim": True,
                    "replacementAttemptNumberIncremented": True,
                    "oldTokenLateCompletionFenced": True,
                    "lateCompletionPersistedZeroMutation": True,
                    "replacementCompletedNormally": True,
                    "eventSequenceContiguousAndDedupeUnique": True,
                    "strictCrashRecoveryEventOrder": True,
                    "uniqueReplacementTerminal": True,
                    "attemptFieldsAndOutputHashExact": True,
                    "eventRowsPayloadsAndStateVersionsExact": True,
                    "dependentPendingUntilReplacementCompletion": True,
                    "dependentQueuedExactlyOnceAfterReplacementCompletion": True,
                    "dependencyProjectionNeverDrifted": True,
                    "sameWindowsProcessHandleUsedForIdentityAndTerminate": (
                        termination_evidence[
                            "sameHandleUsedForAliveCheckAndTerminate"
                        ]
                    ),
                    "processLockTimeoutEvidenceDerivedFromShowAndSqlstate": True,
                    "productionSourceNoChange": True,
                    "secretsScrubbed": True,
                },
            }
            parsed_url = make_url(database_url)
            secrets = {database_url, old_token, replacement_token}
            if parsed_url.password:
                secrets.add(parsed_url.password)
            _assert_secret_scrub(result, secrets)
            if not (
                result["security"]["secretIpcFilesDeletedAfterRead"]
                and result["security"]["secretIpcDirectoriesDeletedAfterRead"]
            ):
                raise AssertionError(
                    "R2-J did not delete lease-token secret IPC files/directories"
                )
            return result
        finally:
            if holder is not None and holder.poll() is None:
                if (
                    holder_child_pid is not None
                    and windows_target is not None
                    and not windows_target.closed
                ):
                    _strong_kill(holder, holder_child_pid, windows_target, 5)
                elif os.name == "nt":
                    subprocess.run(
                        [
                            "taskkill.exe",
                            "/PID",
                            str(holder.pid),
                            "/T",
                            "/F",
                        ],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                else:
                    holder.kill()
                holder.communicate(timeout=5)
            for secret_path in (
                holder_paths["secret"] if holder_paths else None,
                replacement_paths["secret"] if replacement_paths else None,
            ):
                if secret_path is None:
                    continue
                try:
                    secret_path.unlink(missing_ok=True)
                except OSError:
                    pass
                try:
                    secret_path.parent.rmdir()
                except OSError:
                    pass
