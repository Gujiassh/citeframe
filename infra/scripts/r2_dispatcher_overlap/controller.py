"""Run a faithful R800-backed two-process dispatcher-overlap proof."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

os.environ.setdefault("PGAPPNAME", "citeframe-r2-overlap-controller")

from sqlalchemy import select, text

from ai_pdf_api.core.settings import settings
from ai_pdf_api.db.session import SessionLocal
from ai_pdf_api.services.storage import object_exists
from citeframe_persistence.models import (
    ResearchArtifact,
    ResearchBudgetLedger,
    ResearchClaim,
    ResearchEvent,
    ResearchEvidenceHandle,
    ResearchProviderCall,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
    ResearchToolCall,
)
from ai_pdf_worker.r800_acceptance_common import IDS
from ai_pdf_worker.r800_acceptance_scenarios import (
    ResearchHttpClient,
    _create_run,
    _provider_request,
    _submit_plan,
)
from ai_pdf_worker.research_runtime import ResearchWorkProcessor, build_default_research_service

from .manifest import verify_container_manifest


WORKER_IDS = (
    "citeframe-r2-overlap-worker-a",
    "citeframe-r2-overlap-worker-b",
)
ACTOR_TIMEOUT_SECONDS = 90.0
OVERLAP_TIMEOUT_SECONDS = 45.0


def _json_default(value: object) -> object:
    if hasattr(value, "isoformat"):
        return value.isoformat()  # type: ignore[union-attr]
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _safe_error(error: BaseException) -> dict[str, object]:
    message = str(error)[:1000]
    message = re.sub(r"postgres(?:ql)?(?:\+psycopg)?://[^\s/@:]+:[^\s/@]+@", "postgresql://<redacted>@", message)
    return {"type": type(error).__name__, "message": message}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True, default=_json_default) + "\n"
    )
    path.chmod(0o600)


def _wait_for_file(path: Path, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.exists():
            return json.loads(path.read_text())
        time.sleep(0.02)
    raise TimeoutError(f"actor readiness timeout: {path.name}")


def _wait_for_run(client: ResearchHttpClient, run_id: str, status: str, timeout_seconds: float) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        run = client.run(run_id)
        if run.get("status") == status:
            return run
        time.sleep(0.1)
    raise TimeoutError(f"run status timeout: run={run_id} expected={status}")


def _pg_activity() -> list[dict[str, object]]:
    with SessionLocal() as db:
        rows = db.execute(
            text(
                "SELECT pid, application_name, state, wait_event_type, wait_event, "
                "backend_start, xact_start, query_start "
                "FROM pg_stat_activity WHERE application_name = ANY(:names) "
                "ORDER BY application_name, pid"
            ),
            {"names": list(WORKER_IDS)},
        ).mappings().all()
    return [dict(row) for row in rows]


def _running_attempts(run_id: str) -> list[dict[str, object]]:
    with SessionLocal() as db:
        rows = db.execute(
            select(
                ResearchStepAttempt.id,
                ResearchStepAttempt.step_id,
                ResearchStepAttempt.worker_instance_id,
                ResearchStepAttempt.status,
                ResearchStepAttempt.started_at,
                ResearchStep.branch_key,
            )
            .join(ResearchStep, ResearchStep.id == ResearchStepAttempt.step_id)
            .where(
                ResearchStep.run_id == run_id,
                ResearchStep.step_kind == "researcher",
                ResearchStepAttempt.status == "running",
                ResearchStepAttempt.worker_instance_id.in_(WORKER_IDS),
            )
            .order_by(ResearchStepAttempt.worker_instance_id)
        ).mappings().all()
    return [dict(row) for row in rows]


def _wait_for_overlap(run_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + OVERLAP_TIMEOUT_SECONDS
    last_timeline: dict[str, Any] = {}
    last_attempts: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        last_timeline = _provider_request("GET", "/__r800__/control/timeline")
        in_flight = [
            row for row in last_timeline.get("inFlight", []) if row.get("node") == "researcher"
        ]
        last_attempts = _running_attempts(run_id)
        if len(in_flight) >= 2 and len(last_attempts) == 2:
            return {
                "capturedAtNs": time.time_ns(),
                "providerTimeline": last_timeline,
                "runningAttempts": last_attempts,
                "postgresSessions": _pg_activity(),
            }
        time.sleep(0.05)
    raise TimeoutError(
        f"provider/Attempt overlap timeout: timeline={last_timeline!r} attempts={last_attempts!r}"
    )


def _launch_actors(temp_root: Path, run_id: str, source_manifest_path: Path) -> tuple[list[subprocess.Popen[str]], list[dict[str, Any]], Path]:
    start_path = temp_root / "actors.start"
    processes: list[subprocess.Popen[str]] = []
    records: list[dict[str, Any]] = []
    for worker_id in WORKER_IDS:
        suffix = worker_id.rsplit("-", 1)[-1]
        config_path = temp_root / f"actor-{suffix}.config.json"
        ready_path = temp_root / f"actor-{suffix}.ready.json"
        output_path = temp_root / f"actor-{suffix}.output.json"
        config = {
            "runId": run_id,
            "workerInstanceId": worker_id,
            "readyPath": str(ready_path),
            "startPath": str(start_path),
            "startTimeoutSeconds": 30.0,
            "sourceManifestPath": str(source_manifest_path),
        }
        _write_json(config_path, config)
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "r2_dispatcher_overlap.actor",
                "--config",
                str(config_path),
                "--output",
                str(output_path),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        processes.append(process)
        records.append(
            {
                "workerInstanceId": worker_id,
                "process": process,
                "readyPath": ready_path,
                "outputPath": output_path,
            }
        )
    readiness = [_wait_for_file(item["readyPath"], 30.0) for item in records]
    for item, ready in zip(records, readiness, strict=True):
        item["ready"] = ready
    start_path.touch(mode=0o600)
    return processes, records, start_path


def _finish_actors(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    deadline = time.monotonic() + ACTOR_TIMEOUT_SECONDS
    for item in records:
        process: subprocess.Popen[str] = item["process"]
        remaining = max(0.1, deadline - time.monotonic())
        try:
            stdout, stderr = process.communicate(timeout=remaining)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=5)
            raise TimeoutError(f"actor process timeout: {item['workerInstanceId']}")
        output_path: Path = item["outputPath"]
        payload = json.loads(output_path.read_text()) if output_path.exists() else {}
        payload.update(
            {
                "controllerObservedPid": process.pid,
                "exitCode": process.returncode,
                "stdout": stdout[-1000:],
                "stderr": stderr[-4000:],
                "ready": item["ready"],
            }
        )
        results.append(payload)
    return results


def _stop_children(processes: list[subprocess.Popen[str]]) -> dict[str, object]:
    terminated: list[int] = []
    killed: list[int] = []
    for process in processes:
        if process.poll() is None:
            process.terminate()
            terminated.append(process.pid)
    deadline = time.monotonic() + 5
    for process in processes:
        if process.poll() is None:
            try:
                process.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                process.kill()
                killed.append(process.pid)
                process.wait(timeout=5)
    return {
        "terminatedPids": terminated,
        "killedPids": killed,
        "allExited": all(process.poll() is not None for process in processes),
    }


def _final_database_evidence(run_id: str) -> dict[str, Any]:
    with SessionLocal() as db:
        run = db.get(ResearchRun, run_id)
        _require(run is not None and run.approved_execution_snapshot_id is not None, "approved Run missing")
        snapshot_id = run.approved_execution_snapshot_id
        attempt_rows = db.execute(
            select(ResearchStepAttempt, ResearchStep)
            .join(ResearchStep, ResearchStep.id == ResearchStepAttempt.step_id)
            .where(
                ResearchStep.run_id == run_id,
                ResearchStep.step_kind == "researcher",
                ResearchStepAttempt.worker_instance_id.in_(WORKER_IDS),
            )
            .order_by(ResearchStepAttempt.worker_instance_id)
        ).all()
        attempts = [row[0] for row in attempt_rows]
        steps = [row[1] for row in attempt_rows]
        attempt_ids = [row.id for row in attempts]
        step_ids = [row.id for row in steps]
        provider_rows = list(
            db.scalars(
                select(ResearchProviderCall)
                .where(ResearchProviderCall.attempt_id.in_(attempt_ids))
                .order_by(ResearchProviderCall.attempt_id, ResearchProviderCall.send_attempt)
            ).all()
        )
        tool_rows = list(
            db.scalars(
                select(ResearchToolCall)
                .where(ResearchToolCall.attempt_id.in_(attempt_ids))
                .order_by(ResearchToolCall.attempt_id, ResearchToolCall.call_order)
            ).all()
        )
        handle_rows = db.execute(
            select(ResearchEvidenceHandle, ResearchToolCall.attempt_id)
            .join(ResearchToolCall, ResearchToolCall.id == ResearchEvidenceHandle.created_by_tool_call_id)
            .where(ResearchToolCall.attempt_id.in_(attempt_ids))
            .order_by(ResearchToolCall.attempt_id, ResearchEvidenceHandle.result_order)
        ).all()
        claims = list(
            db.scalars(
                select(ResearchClaim)
                .where(ResearchClaim.produced_by_step_id.in_(step_ids))
                .order_by(ResearchClaim.produced_by_step_id, ResearchClaim.claim_order)
            ).all()
        )
        checkpoints = list(
            db.scalars(
                select(ResearchArtifact)
                .where(
                    ResearchArtifact.generated_by_attempt_id.in_(attempt_ids),
                    ResearchArtifact.artifact_kind == "execution_checkpoint",
                )
                .order_by(ResearchArtifact.generated_by_attempt_id)
            ).all()
        )
        events = list(
            db.scalars(
                select(ResearchEvent)
                .where(ResearchEvent.run_id == run_id)
                .order_by(ResearchEvent.seq)
            ).all()
        )
        ledger = db.scalar(
            select(ResearchBudgetLedger).where(
                ResearchBudgetLedger.execution_snapshot_id == snapshot_id
            )
        )
        _require(ledger is not None, "execution budget ledger missing")

        provider_by_attempt: dict[str, list[ResearchProviderCall]] = defaultdict(list)
        for row in provider_rows:
            provider_by_attempt[row.attempt_id].append(row)
        tools_by_attempt: dict[str, list[ResearchToolCall]] = defaultdict(list)
        for row in tool_rows:
            tools_by_attempt[row.attempt_id].append(row)
        handles_by_attempt = Counter(attempt_id for _row, attempt_id in handle_rows)
        claims_by_step = Counter(row.produced_by_step_id for row in claims)
        checkpoints_by_attempt = Counter(row.generated_by_attempt_id for row in checkpoints)
        started_events = Counter(
            row.attempt_id for row in events if row.event_type == "step_started" and row.attempt_id in attempt_ids
        )
        succeeded_events = Counter(
            row.attempt_id for row in events if row.event_type == "step_succeeded" and row.attempt_id in attempt_ids
        )

        attempt_evidence: list[dict[str, Any]] = []
        for attempt, step in attempt_rows:
            providers = provider_by_attempt[attempt.id]
            tools = tools_by_attempt[attempt.id]
            attempt_evidence.append(
                {
                    "attemptId": attempt.id,
                    "attemptNumber": attempt.attempt_number,
                    "workerInstanceId": attempt.worker_instance_id,
                    "stepId": step.id,
                    "branchKey": step.branch_key,
                    "stepStatus": step.status,
                    "attemptStatus": attempt.status,
                    "providerCallCount": attempt.provider_call_count,
                    "toolCallCount": attempt.tool_call_count,
                    "inputTokens": attempt.input_tokens,
                    "outputTokens": attempt.output_tokens,
                    "checkpointArtifactId": attempt.checkpoint_artifact_id,
                    "providerRows": [
                        {
                            "id": row.id,
                            "status": row.status,
                            "provider": row.provider,
                            "model": row.model,
                            "usageSource": row.usage_source,
                            "usageFinal": row.usage_final,
                            "actualInputTokens": row.actual_input_tokens,
                            "actualOutputTokens": row.actual_output_tokens,
                        }
                        for row in providers
                    ],
                    "toolRows": [
                        {
                            "id": row.id,
                            "name": row.tool_name,
                            "status": row.status,
                            "callOrder": row.call_order,
                            "resultCount": row.result_count,
                        }
                        for row in tools
                    ],
                    "evidenceHandleCount": handles_by_attempt[attempt.id],
                    "claimCount": claims_by_step[step.id],
                    "checkpointCount": checkpoints_by_attempt[attempt.id],
                    "stepStartedEventCount": started_events[attempt.id],
                    "stepSucceededEventCount": succeeded_events[attempt.id],
                }
            )

        provider_input = sum(int(row.actual_input_tokens or 0) for row in provider_rows)
        provider_output = sum(int(row.actual_output_tokens or 0) for row in provider_rows)
        provider_costs = [row.actual_cost_microunits for row in provider_rows]
        expected_cost = None if any(value is None for value in provider_costs) else sum(int(value) for value in provider_costs)
        ledger_payload = {
            "id": ledger.id,
            "reservedProviderCalls": ledger.reserved_provider_calls,
            "reservedToolCalls": ledger.reserved_tool_calls,
            "reservedInputTokens": ledger.reserved_input_tokens,
            "reservedOutputTokens": ledger.reserved_output_tokens,
            "reservedCostMicrounits": ledger.reserved_cost_microunits,
            "actualProviderCalls": ledger.actual_provider_calls,
            "actualToolCalls": ledger.actual_tool_calls,
            "actualInputTokens": ledger.actual_input_tokens,
            "actualOutputTokens": ledger.actual_output_tokens,
            "actualCostMicrounits": ledger.actual_cost_microunits,
            "usageFinal": ledger.usage_final,
        }
        event_payload = [
            {
                "id": row.id,
                "seq": row.seq,
                "type": row.event_type,
                "stepId": row.step_id,
                "attemptId": row.attempt_id,
                "dedupeKey": row.dedupe_key,
            }
            for row in events
        ]

    checkpoint_objects = {
        row.id: object_exists(row.object_key) for row in checkpoints
    }
    per_attempt_rows_ok = all(
        row["attemptStatus"] == "succeeded"
        and row["stepStatus"] == "succeeded"
        and row["providerCallCount"] == 1
        and row["toolCallCount"] == 2
        and len(row["providerRows"]) == 1
        and row["providerRows"][0]["status"] == "succeeded"
        and {tool["name"] for tool in row["toolRows"]} == {"evidence.search", "evidence.load"}
        and len(row["toolRows"]) == 2
        and all(tool["status"] == "succeeded" and tool["resultCount"] > 0 for tool in row["toolRows"])
        and row["evidenceHandleCount"] > 0
        and row["claimCount"] == 1
        and row["checkpointCount"] == 1
        and row["checkpointArtifactId"] is not None
        and row["stepStartedEventCount"] == 1
        and row["stepSucceededEventCount"] == 1
        for row in attempt_evidence
    )
    aggregate_ok = (
        len(attempt_evidence) == 2
        and len({row["attemptId"] for row in attempt_evidence}) == 2
        and len({row["stepId"] for row in attempt_evidence}) == 2
        and len({row["workerInstanceId"] for row in attempt_evidence}) == 2
        and len(claims) == len({row.id for row in claims}) == 2
        and len(checkpoints) == len({row.id for row in checkpoints}) == 2
        and all(checkpoint_objects.values())
        and len({row.seq for row in events}) == len(events)
        and len({row.dedupe_key for row in events}) == len(events)
        and [row.seq for row in events] == list(range(1, len(events) + 1))
    )
    ledger_ok = (
        ledger_payload["reservedProviderCalls"] == 0
        and ledger_payload["reservedToolCalls"] == 0
        and ledger_payload["reservedInputTokens"] == 0
        and ledger_payload["reservedOutputTokens"] == 0
        and ledger_payload["actualProviderCalls"] == 2
        and ledger_payload["actualToolCalls"] == 4
        and ledger_payload["actualInputTokens"] == provider_input
        and ledger_payload["actualOutputTokens"] == provider_output
        and ledger_payload["actualCostMicrounits"] == expected_cost
    )
    return {
        "runId": run_id,
        "attempts": attempt_evidence,
        "claims": [
            {"id": row.id, "stepId": row.produced_by_step_id, "claimOrder": row.claim_order}
            for row in claims
        ],
        "checkpoints": [
            {
                "id": row.id,
                "attemptId": row.generated_by_attempt_id,
                "stepId": row.generated_by_step_id,
                "contentSha256": row.content_sha256,
                "objectExists": checkpoint_objects[row.id],
            }
            for row in checkpoints
        ],
        "events": event_payload,
        "ledger": ledger_payload,
        "derivedLedgerOracle": {
            "providerRows": len(provider_rows),
            "toolRows": len(tool_rows),
            "providerInputTokens": provider_input,
            "providerOutputTokens": provider_output,
            "providerCostMicrounits": expected_cost,
        },
        "checks": {
            "perAttemptRealHandlerRows": per_attempt_rows_ok,
            "uniqueClaimsCheckpointsAndEvents": aggregate_ok,
            "exactLedgerCounters": ledger_ok,
        },
    }


def _resources(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    started_ns = time.time_ns()
    source_manifest = json.loads(args.source_manifest.read_text())
    report: dict[str, Any] = {
        "schemaVersion": "citeframe-r2-dispatcher-overlap-proof-v1",
        "evidenceClassification": "R2 dispatcher overlap proof only; not R2 ACCEPT",
        "acceptanceClaim": "none",
        "startedAtNs": started_ns,
        "source": source_manifest,
        "pinnedResources": _resources(args.resources),
        "checks": {},
    }
    client = ResearchHttpClient()
    processes: list[subprocess.Popen[str]] = []
    actor_records: list[dict[str, Any]] = []
    barrier_configured = False
    child_cleanup: dict[str, object] = {"allExited": True, "terminatedPids": [], "killedPids": []}
    try:
        report["containerProvenance"] = verify_container_manifest(source_manifest)
        _provider_request("POST", "/__r800__/control/reset", payload={})
        created = _create_run(
            client,
            actor_id=IDS["creator"],
            key="r2-dispatcher-overlap-create-v1",
            question="Prove two real dispatcher processes overlap on frozen R800 evidence.",
        )
        run_id = str(created["id"])
        planner_id = "citeframe-r2-overlap-planner"
        planner = ResearchWorkProcessor(
            SessionLocal,
            build_default_research_service(),
            worker_instance_id=planner_id,
        )
        planner_handled = bool(planner.process_one())
        awaiting = _wait_for_run(client, run_id, "awaiting_plan_approval", 30.0)
        approved = _submit_plan(client, awaiting)
        _require(approved.get("status") == "queued", "plan approval did not queue Research execution")
        report["r800Flow"] = {
            "workspaceId": IDS["workspace"],
            "assetId": IDS["asset"],
            "runId": run_id,
            "createStatus": created.get("status"),
            "plannerWorkerInstanceId": planner_id,
            "plannerProcessOneReturned": planner_handled,
            "preApprovalStatus": awaiting.get("status"),
            "postApprovalStatus": approved.get("status"),
            "approvedExecutionSnapshotId": approved.get("approvedExecutionSnapshotId"),
        }

        _provider_request("POST", "/__r800__/control/reset", payload={})
        _provider_request(
            "POST",
            "/__r800__/control/configure",
            payload={"node": "researcher", "barrier": True},
        )
        barrier_configured = True
        with tempfile.TemporaryDirectory(prefix="citeframe-r2-dispatcher-overlap-") as temp:
            temp_root = Path(temp)
            local_manifest = temp_root / "source-manifest.json"
            _write_json(local_manifest, source_manifest)
            processes, actor_records, _start_path = _launch_actors(temp_root, run_id, local_manifest)
            overlap = _wait_for_overlap(run_id)
            report["overlap"] = overlap
            _provider_request(
                "POST",
                "/__r800__/control/release",
                payload={"node": "researcher"},
            )
            report["actors"] = _finish_actors(actor_records)
            child_cleanup = _stop_children(processes)

        final_timeline = _provider_request("GET", "/__r800__/control/timeline")
        database = _final_database_evidence(run_id)
        report["finalProviderTimeline"] = final_timeline
        report["database"] = database
        actors = report["actors"]
        actor_pids = [row.get("pid") for row in actors]
        controller_pids = [row.get("controllerObservedPid") for row in actors]
        initial_pg_pids = [row.get("initialPostgresSession", {}).get("pid") for row in actors]
        overlap_workers = {row.get("worker_instance_id") for row in overlap["runningAttempts"]}
        pg_names = {row.get("application_name") for row in overlap["postgresSessions"]}
        researcher_in_flight = [
            row for row in overlap["providerTimeline"].get("inFlight", []) if row.get("node") == "researcher"
        ]
        researcher_entries = [
            row for row in final_timeline.get("entries", []) if row.get("node") == "researcher"
        ]
        checks = {
            "r800CreatePlannerApprove": (
                planner_handled
                and awaiting.get("status") == "awaiting_plan_approval"
                and approved.get("status") == "queued"
            ),
            "twoUniqueOneShotOsProcesses": (
                len(actors) == 2
                and len(set(actor_pids)) == 2
                and actor_pids == controller_pids
                and all(row.get("processOneCalls") == 1 for row in actors)
                and all(row.get("processOneReturned") is True for row in actors)
                and all(row.get("exitCode") == 0 and row.get("status") == "pass" for row in actors)
            ),
            "uniqueWorkerIdsAndPostgresSessions": (
                {row.get("workerInstanceId") for row in actors} == set(WORKER_IDS)
                and len(set(initial_pg_pids)) == 2
                and pg_names == set(WORKER_IDS)
                and overlap_workers == set(WORKER_IDS)
            ),
            "providerTimelineOverlap": (
                int(overlap["providerTimeline"].get("maxActive", 0)) >= 2
                and len(researcher_in_flight) == 2
                and len(researcher_entries) == 2
                and all(row.get("result") == "succeeded" and row.get("httpStatus") == 200 for row in researcher_entries)
            ),
            "simultaneousRunningAttempts": (
                len(overlap["runningAttempts"]) == 2
                and len({row.get("id") for row in overlap["runningAttempts"]}) == 2
                and overlap_workers == set(WORKER_IDS)
            ),
            **database["checks"],
            "childProcessCleanup": child_cleanup.get("allExited") is True,
        }
        report["checks"] = checks
        report["childProcessCleanup"] = child_cleanup
        report["status"] = "pass" if all(checks.values()) else "fail"
        exit_code = 0 if report["status"] == "pass" else 1
    except BaseException as error:  # noqa: BLE001 - aggregate proof must preserve failure evidence
        report["status"] = "fail"
        report["fatalError"] = _safe_error(error)
        report["fatalTraceback"] = traceback.format_exc(limit=15)
        exit_code = 1
    finally:
        if barrier_configured:
            try:
                _provider_request(
                    "POST",
                    "/__r800__/control/release",
                    payload={"node": "researcher"},
                )
            except Exception:
                pass
        if processes:
            child_cleanup = _stop_children(processes)
            report["childProcessCleanup"] = child_cleanup
            if not child_cleanup.get("allExited"):
                report["status"] = "fail"
                exit_code = 1
        client.close()
    report["finishedAtNs"] = time.time_ns()
    serialized = json.dumps(
        report, ensure_ascii=True, indent=2, sort_keys=True, default=_json_default
    ) + "\n"
    secret_values = [
        value
        for name, value in os.environ.items()
        if name in {
            "POSTGRES_PASSWORD",
            "MINIO_ROOT_USER",
            "MINIO_ROOT_PASSWORD",
            "AI_PDF_API_INTERNAL_TOKEN",
            "AI_PDF_SESSION_SECRET",
            "AI_PDF_OPENAI_API_KEY",
        }
        and value
    ]
    if any(value in serialized for value in secret_values):
        report["status"] = "fail"
        report["controllerSecretScan"] = {"status": "fail", "matchedValueCount": 1}
        serialized = json.dumps(
            report, ensure_ascii=True, indent=2, sort_keys=True, default=_json_default
        ) + "\n"
        exit_code = 1
    else:
        report["controllerSecretScan"] = {"status": "pass", "matchedValueCount": 0}
        serialized = json.dumps(
            report, ensure_ascii=True, indent=2, sort_keys=True, default=_json_default
        ) + "\n"
    print(serialized, end="")
    return report, exit_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--resources", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    _report, exit_code = run(parse_args())
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
