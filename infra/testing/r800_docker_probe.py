"""HTTP-only workload and independent live-object checks for the Docker smoke."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4


def assert_attempts(attempts: list[dict], expected_worker: str) -> None:
    assert attempts, "No persisted worker attempts"
    assert all(row["status"] == "succeeded" for row in attempts), attempts
    assert all(row["worker_instance_id"].startswith(expected_worker + ":research:")
               for row in attempts), attempts


def exercise() -> dict:
    from sqlalchemy import text
    from ai_pdf_api.db.session import SessionLocal
    from citeframe_evaluation.acceptance.common import IDS
    from citeframe_evaluation.acceptance.scenarios import (
        ResearchHttpClient, _create_run, _process_until, _submit_plan,
    )

    client = ResearchHttpClient()
    try:
        created = _create_run(client, actor_id=IDS["creator"], key=str(uuid4()),
                              question="Describe supported evidence after Docker restore.")
        run_id = created["id"]
        run, _ = _process_until(client, run_id, {"awaiting_plan_approval", "failed"},
                                timeout_seconds=180)
        assert run["status"] == "awaiting_plan_approval", run
        _submit_plan(client, run)
        run, _ = _process_until(client, run_id, {"completed", "failed", "awaiting_retry"},
                                timeout_seconds=180)
        assert run["status"] == "completed", run
        base = f"/v1/workspaces/{IDS['workspace']}/research-runs/{run_id}"
        artifacts = client.request("GET", base + "/artifacts", actor_id=IDS["creator"]).json()["items"]
        final = next(item for item in artifacts if item["kind"] == "final_report")
        response = client.request("GET", base + f"/artifacts/{final['id']}/content",
                                  actor_id=IDS["creator"])
        content = response.content
        assert content and "Citeframe Research Report" in content.decode("utf-8")
        with SessionLocal() as db:
            attempts = [dict(row) for row in db.execute(text(
                "SELECT a.id, a.status, a.worker_instance_id, a.started_at, a.finished_at "
                "FROM research_step_attempts a JOIN research_steps s ON s.id=a.step_id "
                "WHERE s.run_id=:run ORDER BY a.started_at"), {"run": run_id}).mappings()]
            artifact = db.execute(text(
                "SELECT content_sha256, object_key FROM research_artifacts WHERE id=:id"),
                {"id": final["id"]}).mappings().one()
        # PID 1 and its command are independently checked by the host harness.
        import os
        assert_attempts(attempts, os.environ["SMOKE_EXPECTED_WORKER"])
        assert sha256(content).hexdigest() == artifact["content_sha256"]
        return {"runId": run_id, "status": run["status"], "attempts": attempts,
                "artifactId": final["id"], "artifactSha256": artifact["content_sha256"],
                "objectKey": artifact["object_key"], "readableReport": content.decode("utf-8"),
                "providerScope": "deterministic local HTTP; no model quality claim"}
    finally:
        client.close()


def objects(backup: Path) -> dict:
    from ai_pdf_api.core.settings import settings
    from ai_pdf_api.services.storage import build_storage_client

    client = build_storage_client()
    rows = []
    for path in sorted(backup.rglob("*")):
        if not path.is_file():
            continue
        key = path.relative_to(backup).as_posix()
        original = path.read_bytes()
        response = client.get_object(settings.minio_bucket, key)
        try:
            restored = response.read()
        finally:
            response.close()
            response.release_conn()
        assert original == restored, key
        rows.append({"key": key, "bytes": len(original), "sha256": sha256(original).hexdigest()})
    assert rows, "Empty object backup"
    return {"passed": True, "objects": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["exercise", "objects"])
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    result = exercise() if args.mode == "exercise" else objects(args.backup)
    print(json.dumps(result, indent=2, default=str))
