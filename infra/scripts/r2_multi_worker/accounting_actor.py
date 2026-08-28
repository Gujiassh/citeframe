"""Source-bound OS-process actor for R2 accounting race scenarios."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from citeframe_research_persistence.errors import ResearchError

from .common import (
    APP_PREFIX,
    PROCESS_TIMEOUT_SECONDS,
    candidate_source_snapshot,
    error_json,
    harness_hashes,
    session_factory,
    utcnow,
)

ACCOUNTING_SOURCE_FILES = (
    "infra/scripts/r2_multi_worker/accounting_actor.py",
    "infra/scripts/r2_multi_worker/scenarios_accounting.py",
)


@dataclass(frozen=True)
class AccountingChild:
    process: subprocess.Popen[str]
    output_path: Path
    ready_path: Path
    barrier_path: Path
    source_sha256: dict[str, str]


def accounting_source_hashes(repo_root: Path) -> dict[str, str]:
    return {
        relative: hashlib.sha256((repo_root / relative).read_bytes()).hexdigest()
        for relative in ACCOUNTING_SOURCE_FILES
    }


def _frozen_accounting_hashes(harness: Any) -> dict[str, str]:
    current = accounting_source_hashes(harness.repo_root)
    expected = getattr(harness, "_accounting_source_sha256", current)
    if current != expected:
        raise AssertionError("accounting source changed after its first child")
    harness._accounting_source_sha256 = expected
    return expected


def spawn_accounting_child(
    harness: Any,
    name: str,
    action: str,
    action_config: dict[str, Any],
) -> AccountingChild:
    harness.verify_source_snapshot()
    harness.worker_counter += 1
    child_id = harness.worker_counter
    config_path = harness.temp_path / f"accounting-{child_id}.config.json"
    output_path = harness.temp_path / f"accounting-{child_id}.result.json"
    ready_path = harness.temp_path / f"accounting-{child_id}.ready.json"
    barrier_path = harness.temp_path / f"accounting-{child_id}.go"
    source_hashes = _frozen_accounting_hashes(harness)
    config = {
        "action": action,
        "barrierPath": str(barrier_path),
        "databaseUrl": harness.args.database_url,
        "expectedAccountingSourceSha256": source_hashes,
        "expectedHarnessSourceSha256": harness.harness_source_hashes,
        "expectedHead": harness.args.expected_head,
        "expectedSourceSnapshot": harness.source_snapshot,
        "now": utcnow().isoformat(),
        "readyPath": str(ready_path),
        "repoRoot": str(harness.repo_root),
        "schema": harness.base.schema,
        "timeoutSeconds": PROCESS_TIMEOUT_SECONDS,
        "workerInstanceId": f"r2-accounting-{name}",
        **action_config,
    }
    config_path.write_text(json.dumps(config, sort_keys=True) + "\n")
    os.chmod(config_path, 0o600)
    env = os.environ.copy()
    scripts_path = str(harness.repo_root / "infra/scripts")
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        scripts_path
        if not existing_pythonpath
        else f"{scripts_path}{os.pathsep}{existing_pythonpath}"
    )
    launcher = (
        "from r2_multi_worker.accounting_actor import main; raise SystemExit(main())"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", launcher, str(config_path), str(output_path)],
        cwd=harness.repo_root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    harness.children.add(process)
    return AccountingChild(
        process=process,
        output_path=output_path,
        ready_path=ready_path,
        barrier_path=barrier_path,
        source_sha256=source_hashes,
    )


def wait_accounting_ready(child: AccountingChild) -> dict[str, Any]:
    deadline = time.monotonic() + PROCESS_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if child.ready_path.exists():
            ready = json.loads(child.ready_path.read_text())
            if ready["pid"] != child.process.pid:
                raise AssertionError("accounting child ready PID proof mismatch")
            return ready
        if child.process.poll() is not None:
            raise AssertionError(
                f"accounting child pid={child.process.pid} exited before readiness"
            )
        time.sleep(0.01)
    raise AssertionError(
        f"accounting child pid={child.process.pid} readiness timed out"
    )


def finish_accounting_child(harness: Any, child: AccountingChild) -> dict[str, Any]:
    process = child.process
    try:
        stdout, stderr = process.communicate(timeout=PROCESS_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=2)
        raise AssertionError(
            f"accounting child pid={process.pid} timed out "
            f"stdout={stdout!r} stderr={stderr!r}"
        )
    finally:
        harness.children.discard(process)
    if not child.output_path.exists():
        raise AssertionError(
            f"accounting child pid={process.pid} produced no result "
            f"stdout={stdout!r} stderr={stderr!r}"
        )
    result = json.loads(child.output_path.read_text())
    result["launcherPid"] = process.pid
    result["stdout"] = [line for line in stdout.splitlines() if line]
    result["stderr"] = [line for line in stderr.splitlines() if line]
    if process.returncode != 0 or result.get("exitStatus") != "pass":
        raise AssertionError(
            f"accounting child pid={process.pid} failed rc={process.returncode} "
            f"result={result}"
        )
    if result["pid"] != process.pid:
        raise AssertionError("accounting child PID proof mismatch")
    if (
        result["candidateSourceManifestSha256"]
        != harness.source_snapshot["candidateSourceManifestSha256"]
    ):
        raise AssertionError("accounting child source manifest differs from controller")
    if result["harnessSourceSha256"] != harness.harness_source_hashes:
        raise AssertionError(
            "accounting child harness hash proof differs from controller"
        )
    if result["accountingSourceSha256"] != child.source_sha256:
        raise AssertionError(
            "accounting child source hash proof differs from controller"
        )
    if accounting_source_hashes(harness.repo_root) != child.source_sha256:
        raise AssertionError("accounting source changed while a child was running")
    return result


def _wait_for_barrier(path: Path, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.01)
    raise TimeoutError(f"accounting child barrier timed out: {path.name}")


def _run_action(db: Any, config: dict[str, Any], result: dict[str, Any]) -> None:
    action = str(config["action"])
    now = datetime.fromisoformat(str(config["now"]))
    if action == "provider_reconcile":
        from citeframe_research_persistence.provider import reconcile_provider_call

        reconcile_provider_call(
            db,
            provider_call_id=str(config["providerCallId"]),
            status="succeeded",
            actual_input_tokens=int(config["actualInputTokens"]),
            actual_output_tokens=int(config["actualOutputTokens"]),
            usage_source="actual",
            usage_final=True,
            provider_response_id_hash=str(config["providerResponseIdHash"]),
            now=now,
        )
    elif action == "tool_complete":
        from citeframe_research_persistence.tools import complete_tool_call

        complete_tool_call(
            db,
            tool_call_id=str(config["toolCallId"]),
            status="succeeded",
            now=now,
        )
    elif action == "lease_reclaim":
        from citeframe_research_persistence.state import reclaim_expired_research_steps

        result["reclaimed"] = reclaim_expired_research_steps(db, limit=1, now=now)
    elif action == "step_complete":
        from citeframe_research_persistence.state import complete_control_step

        complete_control_step(
            db,
            attempt_id=str(config["attemptId"]),
            lease_token=str(config["leaseToken"]),
        )
    elif action == "cancel_run":
        from citeframe_research_persistence.cancellation import (
            cancel_research_run_transition,
        )

        cancel_research_run_transition(
            db,
            workspace_id=str(config["workspaceId"]),
            actor_user_id=str(config["actorUserId"]),
            actor_role=str(config["actorRole"]),
            run_id=str(config["runId"]),
            expected_state_version=int(config["expectedRunStateVersion"]),
            reason_code=str(config["reasonCode"]),
            now=now,
        )
    else:
        raise ValueError(f"unsupported accounting child action: {action}")


def main() -> int:
    config_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    config = json.loads(config_path.read_text())
    repo_root = Path(config["repoRoot"]).resolve()
    result: dict[str, Any] = {
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "workerInstanceId": config["workerInstanceId"],
        "action": config["action"],
    }
    engine = None
    return_code = 0
    try:
        source_snapshot = candidate_source_snapshot(
            repo_root, str(config["expectedHead"])
        )
        if source_snapshot != config["expectedSourceSnapshot"]:
            raise AssertionError("accounting child candidate source manifest mismatch")
        current_harness_hashes = harness_hashes(repo_root)
        if current_harness_hashes != config["expectedHarnessSourceSha256"]:
            raise AssertionError("accounting child harness source proof mismatch")
        source_hashes = accounting_source_hashes(repo_root)
        if source_hashes != config["expectedAccountingSourceSha256"]:
            raise AssertionError("accounting child source proof mismatch")
        result.update(
            {
                "sourceHead": source_snapshot["baseHead"],
                "candidateSourceManifestSha256": source_snapshot[
                    "candidateSourceManifestSha256"
                ],
                "harnessSourceSha256": current_harness_hashes,
                "accountingSourceSha256": source_hashes,
            }
        )
        engine, sessions, backend_pids = session_factory(
            str(config["databaseUrl"]),
            str(config["schema"]),
            f"{APP_PREFIX}{config['workerInstanceId']}",
        )
        with sessions() as db:
            ready = {
                "pid": os.getpid(),
                "postgresPid": backend_pids[-1],
                "action": config["action"],
            }
            ready_path = Path(config["readyPath"])
            ready_path.write_text(json.dumps(ready, sort_keys=True) + "\n")
            os.chmod(ready_path, 0o600)
            _wait_for_barrier(
                Path(config["barrierPath"]), float(config["timeoutSeconds"])
            )
            result["startedAtEpoch"] = time.time()
            try:
                _run_action(db, config, result)
                db.commit()
                result["outcome"] = "success"
            except ResearchError as error:
                db.rollback()
                result["outcome"] = "error"
                result["error"] = error_json(error)
            result["finishedAtEpoch"] = time.time()
            result["postgresPid"] = backend_pids[-1]
        result["exitStatus"] = "pass"
    except BaseException as error:  # noqa: BLE001 - always emit child evidence
        result["exitStatus"] = "fail"
        result["error"] = error_json(error)
        result["traceback"] = traceback.format_exc()
        return_code = 1
    finally:
        if engine is not None:
            engine.dispose()
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        os.chmod(output_path, 0o600)
    return return_code


__all__ = (
    "AccountingChild",
    "accounting_source_hashes",
    "finish_accounting_child",
    "main",
    "spawn_accounting_child",
    "wait_accounting_ready",
)
