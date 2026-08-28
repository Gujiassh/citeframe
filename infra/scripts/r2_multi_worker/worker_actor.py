"""Real OS worker actor used by the R2 multi-worker proof."""
from __future__ import annotations

import json
import os
import subprocess
import time
import traceback
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from citeframe_persistence.models import ResearchExecutionPromptVersion, ResearchExecutionSnapshot
from citeframe_research_persistence.errors import ResearchError
from citeframe_research_persistence.publication import publish_final_report, wait_for_conflict_decision
from citeframe_research_persistence.state import complete_control_step
from ai_pdf_worker.research_runtime import ResearchWorkProcessor, build_default_research_service

from .common import APP_PREFIX, candidate_source_snapshot, error_json, harness_hashes, session_factory, sha

def wait_until(path: Path, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.01)
    raise TimeoutError(f"barrier timeout: {path.name}")


def worker_main(config_path: Path, output_path: Path) -> int:
    config = json.loads(config_path.read_text())
    repo_root = Path(config["repoRoot"]).resolve()
    source_snapshot = candidate_source_snapshot(repo_root, config["expectedHead"])
    harness_source_hashes = harness_hashes(repo_root)
    expected_snapshot = config["expectedSourceSnapshot"]
    expected_snapshot_json = json.dumps(expected_snapshot, sort_keys=True, separators=(",", ":"))
    actual_snapshot_json = json.dumps(source_snapshot, sort_keys=True, separators=(",", ":"))
    if actual_snapshot_json != expected_snapshot_json:
        raise AssertionError("worker candidate source manifest differs byte-for-byte from controller")
    if harness_source_hashes != config["expectedHarnessSourceSha256"]:
        raise AssertionError("worker harness source proof differs from controller")
    result: dict[str, Any] = {
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "workerInstanceId": config["workerInstanceId"],
        "sourceHead": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip(),
        "sourceHashes": source_snapshot["productionFiles"],
        "candidateSourceManifestSha256": source_snapshot["candidateSourceManifestSha256"],
        "harnessSourceSha256": harness_source_hashes,
        "action": config["action"],
    }
    engine, sessions, backend_pids = session_factory(
        config["databaseUrl"], config["schema"], f"{APP_PREFIX}{config['workerInstanceId']}"
    )
    try:
        if result["sourceHead"] != config["expectedHead"]:
            raise AssertionError("worker source HEAD changed")
        barrier = Path(config["barrier"])
        wait_until(barrier)
        started = time.time()
        processor = ResearchWorkProcessor(
            sessions,
            build_default_research_service(),
            worker_instance_id=config["workerInstanceId"],
        )
        claim_deadline = time.monotonic() + float(config.get("waitForWorkSeconds", 3.0))
        claimed = processor.claim()
        while claimed is None and time.monotonic() < claim_deadline:
            time.sleep(0.05)
            claimed = processor.claim()
        result["startedAtEpoch"] = started
        if claimed is None:
            result["claim"] = None
            result["status"] = "no_work"
        else:
            result["claim"] = {
                "runId": claimed.run_id,
                "stepId": claimed.lease.step_id,
                "attemptId": claimed.lease.attempt_id,
                "attemptNumber": claimed.lease.attempt_number,
            }
            with sessions() as db:
                result["postgresPid"] = int(db.scalar(select(func.pg_backend_pid())))
                action = config["action"]
                if action == "claim_complete":
                    handler_started = time.time()
                    time.sleep(float(config.get("handlerDelay", 0)))
                    complete_control_step(
                        db,
                        attempt_id=claimed.lease.attempt_id,
                        lease_token=claimed.lease.lease_token,
                    )
                    db.commit()
                    result["handlerStartedAtEpoch"] = handler_started
                    result["handlerFinishedAtEpoch"] = time.time()
                    result["status"] = "completed"
                elif action == "claim_late_complete":
                    handler_started = time.time()
                    time.sleep(float(config["handlerDelay"]))
                    try:
                        complete_control_step(
                            db,
                            attempt_id=claimed.lease.attempt_id,
                            lease_token=claimed.lease.lease_token,
                        )
                        db.commit()
                        result["lateCompletion"] = "unexpected_success"
                    except ResearchError as error:
                        db.rollback()
                        result["lateCompletion"] = "fenced"
                        result["lateCompletionError"] = error_json(error)
                    result["handlerStartedAtEpoch"] = handler_started
                    result["handlerFinishedAtEpoch"] = time.time()
                    result["status"] = "completed"
                elif action == "claim_only":
                    result["status"] = "claimed"
                elif action == "conflict_wait":
                    storage = Path(config["storage"])
                    storage.mkdir(parents=True, exist_ok=True)

                    def store_bytes(key: str, data: bytes, _content_type: str) -> None:
                        target = storage / sha(key)
                        target.write_bytes(data)

                    def cleanup_bytes(key: str) -> None:
                        (storage / sha(key)).unlink(missing_ok=True)

                    decision_id = wait_for_conflict_decision(
                        db,
                        attempt_id=claimed.lease.attempt_id,
                        lease_token=claimed.lease.lease_token,
                        conflict_claim_ids=config["claimIds"],
                        store_bytes=store_bytes,
                        cleanup_bytes=cleanup_bytes,
                    )
                    db.commit()
                    result["decisionId"] = decision_id
                    result["status"] = "waiting"
                elif action == "publish_final":
                    storage = Path(config["storage"])
                    storage.mkdir(parents=True, exist_ok=True)

                    def store_bytes(key: str, data: bytes, _content_type: str) -> None:
                        (storage / sha(key)).write_bytes(data)

                    def cleanup_bytes(key: str) -> None:
                        (storage / sha(key)).unlink(missing_ok=True)

                    def prompt_loader(db_session: Session, snapshot: ResearchExecutionSnapshot) -> list[dict[str, object]]:
                        rows = db_session.scalars(
                            select(ResearchExecutionPromptVersion).where(
                                ResearchExecutionPromptVersion.execution_snapshot_id == snapshot.id
                            )
                        ).all()
                        return [{"nodeKey": row.node_key, "promptVersionId": row.prompt_version_id} for row in rows]

                    artifact_id = publish_final_report(
                        db,
                        attempt_id=claimed.lease.attempt_id,
                        lease_token=claimed.lease.lease_token,
                        fact_claim_ids=[],
                        unresolved_claim_ids=[],
                        store_bytes=store_bytes,
                        cleanup_bytes=cleanup_bytes,
                        committed_session_factory=sessions,
                        prompt_loader=prompt_loader,
                    )
                    result["artifactId"] = artifact_id
                    result["status"] = "published"
                else:
                    raise ValueError(f"unsupported worker action: {action}")
        result["finishedAtEpoch"] = time.time()
        result["postgresSessionPids"] = backend_pids
        result["exitStatus"] = "pass"
        return_code = 0
    except BaseException as error:  # noqa: BLE001
        result["exitStatus"] = "fail"
        result["error"] = error_json(error)
        result["traceback"] = traceback.format_exc()
        return_code = 1
    finally:
        engine.dispose()
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        os.chmod(output_path, 0o600)
    return return_code
