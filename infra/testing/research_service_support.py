"""Isolated migrated PostgreSQL/S3 resources shared by service acceptance tests."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]


class ServiceHarness:
    def __init__(self, directory, *, suffix=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.admin = make_url(os.environ["CITEFRAME_SERVICE_ADMIN_URL"])
        self.name = "pr28_" + (suffix or uuid4().hex[:12])
        self.url = self.admin.set(database=self.name).render_as_string(
            hide_password=False
        )
        self.env = {
            **os.environ,
            "AI_PDF_DATABASE_URL": self.url,
            "AI_PDF_MINIO_BUCKET": self.name.replace("_", "-"),
            "AI_PDF_API_INTERNAL_TOKEN": "isolated-service-fixture-token",
            "AI_PDF_EMBEDDING_PROVIDER": "ollama",
            "AI_PDF_EMBEDDING_MODEL": "qwen3-embedding:0.6b",
            "PGOPTIONS": "-c timezone=UTC",
            "PYTHONDONTWRITEBYTECODE": "1",
            "AI_PDF_OPENAI_API_KEY": "",
            "AI_PDF_DEEPSEEK_API_KEY": "",
            "AI_PDF_OPENAI_API_BASE": "http://127.0.0.1:9",
            "AI_PDF_DEEPSEEK_API_BASE": "http://127.0.0.1:9",
            "AI_PDF_OLLAMA_BASE_URL": "http://127.0.0.1:9",
        }
        paths = [
            "apps/api/src",
            "apps/worker/src",
            "packages/backend-contracts/src",
            "packages/backend-persistence/src",
            "packages/research-persistence/src",
            "infra/testing",
            "tools/evaluation/src",
        ]
        self.env["PYTHONPATH"] = os.pathsep.join(str(ROOT / p) for p in paths)
        admin = create_engine(self.admin, isolation_level="AUTOCOMMIT")
        with admin.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{self.name}"')
        admin.dispose()
        self.engine = create_engine(
            self.url, connect_args={"options": "-c timezone=UTC"}
        )
        self.processes = []

    def command(self, args, *, expect=0, env=None, name=None):
        result = subprocess.run(
            args,
            cwd=ROOT,
            env=env or self.env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=180,
            check=False,
        )
        if name:
            (self.directory / f"{name}.log").write_text(
                result.stdout + result.stderr, encoding="utf-8"
            )
        assert result.returncode == expect, result.stdout + result.stderr
        return result

    def migrate(self):
        self.command(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "apps/api/alembic.ini",
                "upgrade",
                "head",
            ],
            name="migration",
        )

    def snapshot(self, label):
        def encode(value):
            if isinstance(value, (bytes, memoryview)):
                return {
                    "sha256": hashlib.sha256(bytes(value)).hexdigest(),
                    "size": len(value),
                }
            return str(value)

        tables = [
            "research_runs",
            "research_steps",
            "research_step_attempts",
            "research_publication_intents",
            "research_artifacts",
            "research_budget_ledgers",
            "research_provider_calls",
            "research_events",
            "research_report_edits",
        ]
        with self.engine.connect() as connection:
            state = {
                table: [
                    dict(row)
                    for row in connection.execute(
                        text(
                            f"SELECT * FROM {table} ORDER BY {'run_id' if table == 'research_report_edits' else 'id'}"
                        )
                    ).mappings()
                ]
                for table in tables
            }
            state["databaseTime"] = str(
                connection.scalar(text("SELECT clock_timestamp()"))
            )
        from ai_pdf_api.services import storage

        client = storage.build_storage_client()
        bucket = self.env["AI_PDF_MINIO_BUCKET"]
        state["objects"] = []
        if client.bucket_exists(bucket):
            for obj in client.list_objects(bucket, recursive=True):
                response = client.get_object(bucket, obj.object_name)
                try:
                    payload = response.read()
                finally:
                    response.close()
                    response.release_conn()
                state["objects"].append(
                    {
                        "key": obj.object_name,
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "size": len(payload),
                    }
                )
        (self.directory / f"{label}.json").write_text(
            json.dumps(state, default=encode, indent=2), encoding="utf-8"
        )

    def worker(self, run_id, *, fault=None, mode="advance", expect=0):
        args = [
            sys.executable,
            "infra/testing/research_service_worker.py",
            run_id,
            "--mode",
            mode,
        ]
        if fault:
            args.extend(["--fault", fault])
        label = f"worker-{len(self.processes)}"
        self.snapshot(label + "-before")
        started = datetime.now(UTC).isoformat()
        process = subprocess.Popen(
            args,
            cwd=ROOT,
            env=self.env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = process.communicate(timeout=180)
        result = subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
        (self.directory / f"{label}.log").write_text(stdout + stderr, encoding="utf-8")
        self.processes.append(
            {
                "pid": process.pid,
                "started": started,
                "finished": datetime.now(UTC).isoformat(),
                "fault": fault,
                "exit": result.returncode,
                "stdout": result.stdout,
            }
        )
        self.snapshot(label + "-after")
        assert result.returncode == expect, result.stdout + result.stderr
        return result

    def restore_into(self, restored):
        dump = self.directory / "before-restore.dump"
        url = (
            make_url(self.url)
            .set(drivername="postgresql")
            .render_as_string(hide_password=False)
        )
        target = (
            make_url(restored.url)
            .set(drivername="postgresql")
            .render_as_string(hide_password=False)
        )
        self.command(
            ["pg_dump", "--format=custom", "--no-owner", "--file", str(dump), url],
            name="pg-dump",
        )
        restored.command(
            [
                "pg_restore",
                "--no-owner",
                "--exit-on-error",
                "--dbname",
                target,
                str(dump),
            ],
            name="pg-restore",
        )


def api_client(harness):
    from ai_pdf_api.core.settings import settings
    from ai_pdf_api.db.session import get_db
    from ai_pdf_api.routers.research import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    settings.database_url = harness.url
    settings.openai_api_base = harness.env["AI_PDF_OPENAI_API_BASE"]
    settings.deepseek_api_base = harness.env["AI_PDF_DEEPSEEK_API_BASE"]
    settings.ollama_base_url = harness.env["AI_PDF_OLLAMA_BASE_URL"]
    settings.openai_api_key = None
    settings.deepseek_api_key = None
    settings.minio_bucket = harness.env["AI_PDF_MINIO_BUCKET"]
    settings.api_internal_token = harness.env["AI_PDF_API_INTERNAL_TOKEN"]
    settings.embedding_provider = "ollama"
    settings.embedding_model = "qwen3-embedding:0.6b"
    sessions = sessionmaker(harness.engine, expire_on_commit=False)

    def get_session():
        with sessions() as db:
            yield db

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = get_session
    return TestClient(app), sessions


def create_run(client, key):
    from citeframe_evaluation.acceptance.common import IDS

    response = client.post(
        f"/v1/workspaces/{IDS['workspace']}/research-runs",
        headers=headers(key),
        json={
            "question": "What does the fixed source establish?",
            "assetScope": {"mode": "selected", "assetIds": [IDS["asset"]]},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["run"]["id"]


def headers(key):
    from ai_pdf_api.core.settings import settings
    from citeframe_evaluation.acceptance.common import IDS

    return {
        "x-ai-pdf-internal-token": settings.api_internal_token,
        "x-user-id": IDS["creator"],
        "Idempotency-Key": key,
    }


def to_publisher(harness, client, sessions, run_id):
    from ai_pdf_api.models import HumanDecision, ResearchRun, ResearchStep
    from citeframe_evaluation.acceptance.common import IDS
    from sqlalchemy import select

    for phase in range(3):
        harness.worker(run_id)
        with sessions() as db:
            run = db.get(ResearchRun, run_id)
            publisher = db.scalar(
                select(ResearchStep).where(
                    ResearchStep.run_id == run_id,
                    ResearchStep.step_kind == "artifact_publisher",
                )
            )
            if publisher is not None and publisher.status == "queued":
                return
            decision = db.scalar(
                select(HumanDecision).where(
                    HumanDecision.run_id == run_id, HumanDecision.status == "pending"
                )
            )
            assert decision is not None, run.status
            plan = decision.decision_type == "plan_approval"
            body = {
                "expectedStateVersion": run.state_version,
                "expectedDecisionStateVersion": decision.state_version,
                "inputArtifactSha256": decision.input_artifact_sha256,
                "inputSnapshotSha256": decision.input_snapshot_sha256,
                "action": "approve" if plan else "keep_as_unresolved",
                "comment": None,
            }
            if plan:
                body["revision"] = None
            path = "plan-decisions" if plan else "conflict-decisions"
            response = client.post(
                f"/v1/workspaces/{IDS['workspace']}/research-runs/{run_id}/{path}/{decision.id}",
                headers=headers(f"{run_id}-{phase}"),
                json=body,
            )
            assert response.status_code == 200, response.text
    raise AssertionError("Publisher was not reached")
