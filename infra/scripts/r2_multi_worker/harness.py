"""Fixture lifecycle, process control, snapshots, and event oracles for R2."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import func, select, text

from citeframe_persistence.models import (
    PromptVersion,
    ResearchBudgetLedger,
    ResearchEvent,
    ResearchExecutionPromptVersion,
    ResearchExecutionSnapshot,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
    WorkflowVersion,
)
from citeframe_research_persistence.constants import EVENT_FIELDS
from citeframe_research_persistence.events import append_research_event

from .common import (
    PROCESS_TIMEOUT_SECONDS,
    START_SHA,
    error_json,
    harness_hashes,
    load_r0,
    sha,
    candidate_source_snapshot,
    utcnow,
)


class HarnessBase:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.repo_root = args.repo_root.resolve()
        self.r0_module = load_r0(self.repo_root)
        self.base = self.r0_module.ContentionHarness(args.database_url)
        self.temp = tempfile.TemporaryDirectory(prefix="citeframe-r2-")
        self.temp_path = Path(self.temp.name)
        self.worker_counter = 0
        self.children: set[subprocess.Popen[str]] = set()
        self.deadlocks_before = 0
        self.report: dict[str, Any] = {
            "schemaVersion": "citeframe-r2-multi-worker-baseline-v1",
            "startedAt": utcnow().isoformat(),
            "immutableStart": args.expected_head,
            "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=self.repo_root, text=True).strip(),
            "commitState": "no commit created by harness",
            "pushState": "not pushed by harness",
            "postgresImage": args.postgres_image,
            "postgresImageId": args.postgres_image_id,
            "authorization": {
                "productionChanges": "owner-authorized per-Run admission candidate only",
                "perRunAdmission": "authorized uncommitted candidate under source-manifest proof",
                "decisionRequired": "none for admission; R2 module acceptance remains separate",
            },
            "evidenceClassification": (
                "expanded R2 persistence/concurrency candidate gate; "
                "not dispatcher-overlap proof or R2 ACCEPT"
            ),
            "knownEvidenceGaps": [
                "production SingleAttemptStepDispatcher handler overlap is outside this harness and not proven",
                (
                    "automatic production reconciliation for unknown publication outcomes is not claimed; "
                    "unknown classification and compensation are explicit harness actions"
                ),
            ],
            "scenarios": [],
        }

    @property
    def sessions(self) -> Any:
        return self.base.sessions

    def setup(self) -> None:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo_root, text=True).strip()
        if head != self.args.expected_head or head != START_SHA:
            raise AssertionError(f"immutable start mismatch: {head}")
        self.base.setup()
        self.report["schema"] = self.base.schema
        self.report["postgresVersion"] = self.base.report["postgresVersion"]
        self.report["pgvectorVersion"] = self.base.report["pgvectorVersion"]
        self.source_snapshot = candidate_source_snapshot(self.repo_root, self.args.expected_head)
        self.harness_source_hashes = harness_hashes(self.repo_root)
        self.report["immutableSourceProof"] = self.source_snapshot["productionFiles"]
        self.report["candidateDirty"] = self.source_snapshot["candidateDirty"]
        self.report["trackedDiffPaths"] = self.source_snapshot["trackedDiffPaths"]
        self.report["untrackedProductionPaths"] = self.source_snapshot["untrackedProductionPaths"]
        self.report["changedProductionPaths"] = self.source_snapshot["changedProductionPaths"]
        self.report["candidateSourceManifestSha256"] = self.source_snapshot[
            "candidateSourceManifestSha256"
        ]
        self.report["harnessSourceSha256"] = self.harness_source_hashes
        self.deadlocks_before = self.base.deadlock_count()

    def verify_source_snapshot(self) -> None:
        actual = candidate_source_snapshot(self.repo_root, self.args.expected_head)
        if actual != self.source_snapshot:
            raise AssertionError("candidate source manifest changed after controller snapshot")
        if harness_hashes(self.repo_root) != self.harness_source_hashes:
            raise AssertionError("harness source changed after controller snapshot")

    def cleanup(self) -> None:
        for process in tuple(self.children):
            if process.poll() is None:
                process.terminate()
        for process in tuple(self.children):
            if process.poll() is None:
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        self.children.clear()
        self.base.cleanup()
        self.temp.cleanup()

    def worker(
        self,
        action: str,
        *,
        worker_id: str | None = None,
        barrier: Path | None = None,
        handler_delay: float = 0,
        extra: dict[str, Any] | None = None,
    ) -> tuple[subprocess.Popen[str], Path, Path]:
        self.worker_counter += 1
        worker_id = worker_id or f"r2-worker-{self.worker_counter}"
        barrier = barrier or self.temp_path / f"barrier-{self.worker_counter}"
        config_path = self.temp_path / f"worker-{self.worker_counter}.config.json"
        output_path = self.temp_path / f"worker-{self.worker_counter}.result.json"
        self.verify_source_snapshot()
        config: dict[str, Any] = {
            "action": action,
            "barrier": str(barrier),
            "databaseUrl": self.args.database_url,
            "expectedHead": self.args.expected_head,
            "handlerDelay": handler_delay,
            "repoRoot": str(self.repo_root),
            "schema": self.base.schema,
            "expectedSourceSnapshot": self.source_snapshot,
            "expectedHarnessSourceSha256": self.harness_source_hashes,
            "workerInstanceId": worker_id,
            "waitForWorkSeconds": 3.0,
        }
        if extra:
            config.update(extra)
        config_path.write_text(json.dumps(config, sort_keys=True) + "\n")
        os.chmod(config_path, 0o600)
        process = subprocess.Popen(
            [sys.executable, str(self.repo_root / "infra/scripts/run-r2-multi-worker.py"), "--worker-config", str(config_path), "--worker-output", str(output_path)],
            cwd=self.repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.children.add(process)
        return process, output_path, barrier

    def finish_worker(self, item: tuple[subprocess.Popen[str], Path, Path], *, expect: int = 0) -> dict[str, Any]:
        process, output_path, _barrier = item
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
                f"worker pid={process.pid} timed out and was terminated stdout={stdout!r} stderr={stderr!r}"
            )
        finally:
            self.children.discard(process)
        if not output_path.exists():
            raise AssertionError(f"worker pid={process.pid} produced no result stdout={stdout!r} stderr={stderr!r}")
        result = json.loads(output_path.read_text())
        result["launcherPid"] = process.pid
        result["stdout"] = [line for line in stdout.splitlines() if line]
        result["stderr"] = [line for line in stderr.splitlines() if line]
        if process.returncode != expect:
            raise AssertionError(f"worker pid={process.pid} rc={process.returncode} result={result}")
        if result["pid"] != process.pid:
            raise AssertionError("worker PID proof mismatch")
        if result["sourceHashes"] != self.report["immutableSourceProof"]:
            raise AssertionError("worker candidate source proof differs from controller")
        if result["candidateSourceManifestSha256"] != self.report["candidateSourceManifestSha256"]:
            raise AssertionError("worker candidate source manifest differs from controller")
        if result["harnessSourceSha256"] != self.report["harnessSourceSha256"]:
            raise AssertionError("worker harness source proof differs from controller")
        return result

    def snapshot(self, run_id: str) -> dict[str, Any]:
        with self.sessions() as db:
            run = db.get(ResearchRun, run_id)
            steps = list(db.scalars(select(ResearchStep).where(ResearchStep.run_id == run_id).order_by(ResearchStep.id)))
            attempts = list(
                db.scalars(
                    select(ResearchStepAttempt)
                    .join(ResearchStep, ResearchStep.id == ResearchStepAttempt.step_id)
                    .where(ResearchStep.run_id == run_id)
                    .order_by(ResearchStepAttempt.started_at, ResearchStepAttempt.id)
                )
            )
            events = list(db.scalars(select(ResearchEvent).where(ResearchEvent.run_id == run_id).order_by(ResearchEvent.seq)))
            ledger = db.scalar(select(ResearchBudgetLedger).where(ResearchBudgetLedger.run_id == run_id))
            return {
                "run": None if run is None else {"id": run.id, "status": run.status, "nextEventSeq": run.next_event_seq},
                "steps": [
                    {"id": row.id, "kind": row.step_kind, "status": row.status, "attemptNumber": row.current_attempt_number}
                    for row in steps
                ],
                "attempts": [
                    {
                        "id": row.id,
                        "stepId": row.step_id,
                        "number": row.attempt_number,
                        "status": row.status,
                        "workerInstanceId": row.worker_instance_id,
                        "leaseExpiresAt": row.lease_expires_at.isoformat() if row.lease_expires_at else None,
                    }
                    for row in attempts
                ],
                "events": [
                    {
                        "seq": row.seq,
                        "type": row.event_type,
                        "stepId": row.step_id,
                        "attemptId": row.attempt_id,
                        "dedupeKey": row.dedupe_key,
                        "payloadKeys": sorted(row.payload_json),
                    }
                    for row in events
                ],
                "ledger": None
                if ledger is None
                else {
                    "reservedProviderCalls": ledger.reserved_provider_calls,
                    "actualProviderCalls": ledger.actual_provider_calls,
                    "reservedToolCalls": ledger.reserved_tool_calls,
                    "actualToolCalls": ledger.actual_tool_calls,
                    "actualInputTokens": ledger.actual_input_tokens,
                    "actualOutputTokens": ledger.actual_output_tokens,
                    "usageFinal": ledger.usage_final,
                },
            }

    @staticmethod
    def event_oracle(snapshot: dict[str, Any], *, require_terminal_run_last: bool = False) -> dict[str, Any]:
        events = snapshot["events"]
        seqs = [row["seq"] for row in events]
        contiguous = seqs == list(range(1, len(seqs) + 1))
        unique_dedupe = len({row["dedupeKey"] for row in events}) == len(events)
        per_step_legal = True
        attempt_terminal_unique = True
        retry_order_legal = True
        for step in snapshot["steps"]:
            rows = [row for row in events if row["stepId"] == step["id"]]
            started = [row["seq"] for row in rows if row["type"] == "step_started"]
            terminal = [row["seq"] for row in rows if row["type"] in {"step_succeeded", "step_failed"}]
            queued = [row["seq"] for row in rows if row["type"] == "step_queued"]
            if started and (not queued or min(started) <= min(queued)):
                per_step_legal = False
            if terminal and (not started or min(terminal) <= min(started)):
                per_step_legal = False
            if len(terminal) > len(started):
                per_step_legal = False
        for attempt in snapshot["attempts"]:
            rows = [row for row in events if row["attemptId"] == attempt["id"]]
            started = [row for row in rows if row["type"] == "step_started"]
            terminal = [row for row in rows if row["type"] in {"step_succeeded", "step_failed", "attempt_abandoned"}]
            if len(started) != 1 or len(terminal) > 1 or (terminal and terminal[0]["seq"] <= started[0]["seq"]):
                attempt_terminal_unique = False
        attempts_by_step: dict[str, list[dict[str, Any]]] = {}
        for attempt in snapshot["attempts"]:
            attempts_by_step.setdefault(attempt["stepId"], []).append(attempt)
        for step_id, attempts in attempts_by_step.items():
            ordered_attempts = sorted(attempts, key=lambda item: item["number"])
            for previous, following in zip(ordered_attempts, ordered_attempts[1:], strict=False):
                if previous["status"] != "abandoned":
                    continue
                abandoned = [
                    row["seq"]
                    for row in events
                    if row["type"] == "attempt_abandoned" and row["attemptId"] == previous["id"]
                ]
                following_started = [
                    row["seq"]
                    for row in events
                    if row["type"] == "step_started" and row["attemptId"] == following["id"]
                ]
                retry_queued = [
                    row["seq"]
                    for row in events
                    if row["type"] == "step_queued" and row["stepId"] == step_id
                ]
                if (
                    len(abandoned) != 1
                    or len(following_started) != 1
                    or not any(abandoned[0] < seq < following_started[0] for seq in retry_queued)
                ):
                    retry_order_legal = False
        terminal_types = {"run_completed", "run_failed", "run_cancelled"}
        terminal_count = sum(row["type"] in terminal_types for row in events)
        run_terminal_last = terminal_count <= 1 and (terminal_count == 0 or events[-1]["type"] in terminal_types)
        if require_terminal_run_last:
            run_terminal_last = run_terminal_last and terminal_count == 1
        payload_keys_legal = all(
            set(row["payloadKeys"]) == EVENT_FIELDS[row["type"]] for row in events
        )
        return {
            "seqStartsAtOneContiguousUnique": contiguous and len(seqs) == len(set(seqs)),
            "dedupeUnique": unique_dedupe,
            "stepStartedBeforeTerminalAndTerminalUnique": per_step_legal,
            "attemptStartedOnceAndTerminalAtMostOnce": attempt_terminal_unique,
            "abandonedBeforeRetryQueuedBeforeNextStart": retry_order_legal,
            "runTerminalLastAndUnique": run_terminal_last,
            "payloadKeysExact": payload_keys_legal,
        }

    def seed_queued_events(self, fixture: Any, *, step_ids: set[str] | None = None) -> None:
        with self.sessions() as db:
            run = db.get(ResearchRun, fixture.run_id)
            steps = list(db.scalars(select(ResearchStep).where(ResearchStep.run_id == fixture.run_id).order_by(ResearchStep.id)))
            for step in steps:
                if step_ids is not None and step.id not in step_ids:
                    continue
                run.state_version += 1
                append_research_event(
                    db,
                    run,
                    event_type="step_queued",
                    dedupe_key=f"r2-fixture-step-queued:{step.id}:0",
                    step_id=step.id,
                    data={
                        "stepId": step.id,
                        "stepKind": step.step_kind,
                        "branchKey": step.branch_key,
                        "attemptNumber": 0,
                        "stepStateVersion": step.state_version,
                        "runStateVersion": run.state_version,
                    },
                    now=step.queued_at or step.created_at,
                )
            db.commit()

    def seed_run(self, name: str, *, step_count: int = 1, queued_at: datetime | None = None) -> Any:
        fixture = self.base.seed_run(name, step_count=step_count, queued_at=queued_at)
        self.seed_queued_events(fixture)
        return fixture

    def add_scenario(self, name: str, function: Callable[[], dict[str, Any]]) -> None:
        started = time.monotonic()
        try:
            self.retire_prior_fixtures()
            evidence = function()
            status = evidence.pop("status", "pass")
        except BaseException as error:  # noqa: BLE001
            status = "fail"
            evidence = {"error": error_json(error), "traceback": traceback.format_exc()}
        evidence.update({"name": name, "status": status, "durationMs": round((time.monotonic() - started) * 1000, 3)})
        self.report["scenarios"].append(evidence)
        print(f"r2_harness scenario={name} status={status}", flush=True)

    def retire_prior_fixtures(self) -> None:
        """Keep each proof fixture isolated without imitating any production transition."""
        with self.sessions() as db:
            db.execute(
                text(
                    "UPDATE research_step_attempts SET status='abandoned', lease_expires_at=NULL, "
                    "finished_at=COALESCE(finished_at, now()) WHERE status='running'"
                )
            )
            db.execute(
                text(
                    "UPDATE research_steps SET status='cancelled', finished_at=COALESCE(finished_at, now()), "
                    "updated_at=now() WHERE status IN ('pending','queued','running','waiting')"
                )
            )
            db.execute(
                text(
                    "UPDATE research_runs SET status='cancelled', finished_at=COALESCE(finished_at, now()), "
                    "updated_at=now() WHERE status IN "
                    "('draft','planning','awaiting_plan_approval','queued','running','awaiting_human_decision',"
                    "'awaiting_retry','cancel_requested')"
                )
            )
            db.commit()


    def set_cap(self, fixture: Any, cap: int) -> None:
        with self.sessions() as db:
            snapshot = db.get(ResearchExecutionSnapshot, fixture.snapshot_id)
            snapshot.max_parallel_researchers = cap
            db.commit()

    def claim_only(self, worker_id: str) -> dict[str, Any]:
        barrier = self.temp_path / f"{worker_id}.go"
        item = self.worker("claim_only", worker_id=worker_id, barrier=barrier)
        barrier.touch()
        return self.finish_worker(item)


    def seed_prompt(self, fixture: Any, node: str) -> str:
        prompt_id = self.r0_module.uid(f"{self.base.schema}/{fixture.run_id}/{node}/prompt")
        with self.sessions() as db:
            snapshot = db.get(ResearchExecutionSnapshot, fixture.snapshot_id)
            if db.get(WorkflowVersion, snapshot.workflow_version_id) is None:
                manifest = {"schemaVersion": 1, "nodes": [node]}
                manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
                db.add(
                    WorkflowVersion(
                        id=snapshot.workflow_version_id,
                        workflow_key=f"r2-{fixture.run_id}",
                        version_number=1,
                        availability="active",
                        manifest_schema_version="1",
                        manifest_json=manifest,
                        manifest_sha256=sha(manifest_bytes),
                        created_by_user_id=self.base.user_id,
                        created_at=utcnow(),
                    )
                )
            template = f"R2 {node} proof template"
            db.add(
                PromptVersion(
                    id=prompt_id,
                    prompt_key=f"r2-{fixture.run_id}-{node}",
                    version_number=1,
                    step_kind="researcher" if node == "researchers" else node,
                    availability="active",
                    template_text=template,
                    variables_schema_version="1",
                    variables_schema_json={"type": "object"},
                    template_sha256=sha(template),
                    created_by_user_id=self.base.user_id,
                    created_at=utcnow(),
                )
            )
            db.flush()
            db.add(ResearchExecutionPromptVersion(execution_snapshot_id=fixture.snapshot_id, node_key=node, prompt_version_id=prompt_id))
            db.commit()
        return prompt_id
