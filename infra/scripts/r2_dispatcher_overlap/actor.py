"""One-shot real ResearchWorkProcessor actor used by the overlap controller."""

from __future__ import annotations

import argparse
import json
import os
import time
import traceback
from pathlib import Path
from typing import Any

from .manifest import verify_container_manifest


def _safe_error(error: BaseException) -> dict[str, object]:
    return {"type": type(error).__name__, "message": str(error)[:500]}


def _wait_for(path: Path, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.02)
    raise TimeoutError(f"actor start barrier timeout: {path.name}")


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n")
    path.chmod(0o600)


def run(config_path: Path, output_path: Path) -> int:
    config = json.loads(config_path.read_text())
    worker_id = str(config["workerInstanceId"])
    os.environ["PGAPPNAME"] = worker_id
    result: dict[str, Any] = {
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "workerInstanceId": worker_id,
        "processOneCalls": 0,
    }
    try:
        source_manifest = json.loads(Path(config["sourceManifestPath"]).read_text())
        result["provenance"] = verify_container_manifest(source_manifest)

        # Import only after PGAPPNAME is set so every production engine connection
        # is independently attributable in pg_stat_activity.
        from sqlalchemy import select, text

        from ai_pdf_api.db.session import SessionLocal
        from citeframe_persistence.models import ResearchStep, ResearchStepAttempt
        from ai_pdf_worker.research_runtime import (
            ResearchWorkProcessor,
            build_default_research_service,
        )

        with SessionLocal() as db:
            initial = db.execute(
                text("SELECT pg_backend_pid(), current_setting('application_name')")
            ).one()
            result["initialPostgresSession"] = {
                "pid": int(initial[0]),
                "applicationName": str(initial[1]),
            }

        ready_path = Path(config["readyPath"])
        _write(
            ready_path,
            {
                "pid": result["pid"],
                "postgresSession": result["initialPostgresSession"],
                "workerInstanceId": worker_id,
            },
        )
        _wait_for(Path(config["startPath"]), float(config["startTimeoutSeconds"]))

        result["processOneStartedAtNs"] = time.time_ns()
        processor = ResearchWorkProcessor(
            SessionLocal,
            build_default_research_service(),
            worker_instance_id=worker_id,
        )
        result["processOneCalls"] = 1
        result["processOneReturned"] = bool(processor.process_one())
        result["processOneFinishedAtNs"] = time.time_ns()

        with SessionLocal() as db:
            rows = db.execute(
                select(
                    ResearchStepAttempt.id,
                    ResearchStepAttempt.step_id,
                    ResearchStepAttempt.status,
                    ResearchStepAttempt.attempt_number,
                )
                .join(ResearchStep, ResearchStep.id == ResearchStepAttempt.step_id)
                .where(
                    ResearchStep.run_id == config["runId"],
                    ResearchStepAttempt.worker_instance_id == worker_id,
                )
                .order_by(ResearchStepAttempt.started_at)
            ).all()
            final_pid = db.execute(
                text("SELECT pg_backend_pid(), current_setting('application_name')")
            ).one()
        result["attempts"] = [
            {
                "id": row.id,
                "stepId": row.step_id,
                "status": row.status,
                "attemptNumber": row.attempt_number,
            }
            for row in rows
        ]
        result["finalPostgresSession"] = {
            "pid": int(final_pid[0]),
            "applicationName": str(final_pid[1]),
        }
        if not result["processOneReturned"]:
            raise RuntimeError("one-shot process_one returned no work")
        if len(rows) != 1 or rows[0].status != "succeeded":
            raise RuntimeError("one-shot worker did not finish exactly one successful Attempt")
        result["status"] = "pass"
        return_code = 0
    except BaseException as error:  # noqa: BLE001 - actor failure is proof evidence
        result["status"] = "fail"
        result["error"] = _safe_error(error)
        result["traceback"] = traceback.format_exc(limit=12)
        return_code = 1
    _write(output_path, result)
    return return_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run(args.config, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
