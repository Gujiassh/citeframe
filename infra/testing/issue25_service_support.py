"""Process and HTTP harness for isolated PostgreSQL/S3 issue-25 acceptance."""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "infra/testing/issue25_runtime.py"
LEGACY = "cfc0e728fb3dca82a097088a0dc5038cd833b926"
TOKEN = "issue25-isolated-fixture-internal"


def archive_legacy(target):
    payload = subprocess.check_output(
        ["git", "-c", "core.autocrlf=false", "archive", LEGACY], cwd=ROOT
    )
    target.mkdir()
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        archive.extractall(target, filter="data")
    return target


def legacy_runtime_source(source):
    """Translate only test-driver imports when running the pinned cfc archive."""
    replacements = {
        "from ai_pdf_worker.research import persistence as composition": "from ai_pdf_worker import research_persistence_service as composition",
        "from citeframe_evaluation.acceptance import fixture": "from ai_pdf_worker import r800_acceptance_fixture as fixture",
        "citeframe_evaluation.acceptance.common": "ai_pdf_worker.r800_acceptance_common",
        "ai_pdf_worker.research.adapters.generation": "ai_pdf_worker.research_runtime_ports",
        "from ai_pdf_worker.research.adapters import ledger as research_runtime_ports": "from ai_pdf_worker import research_runtime_ports",
        "from ai_pdf_worker.research import processor as research_runtime_processor": "from ai_pdf_worker import research_runtime_processor",
        "ai_pdf_worker.research.runtime": "ai_pdf_worker.research_runtime",
    }
    for current, historical in replacements.items():
        source = source.replace(current, historical)
    return source


class Deployment:
    def __init__(self, directory, base_url):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        url = make_url(base_url)
        assert url.drivername.startswith("postgresql") and url.host in {
            "127.0.0.1",
            "localhost",
        }
        self.database = "pr25_" + uuid4().hex
        self.admin = create_engine(
            url.set(database="postgres"), isolation_level="AUTOCOMMIT"
        )
        with self.admin.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{self.database}"')
            connection.exec_driver_sql(
                f"ALTER DATABASE \"{self.database}\" SET timezone TO 'UTC'"
            )
        self.url = url.set(database=self.database).render_as_string(hide_password=False)
        self.engine = create_engine(self.url)
        self.server = None
        self.counter = 0
        self.root = ROOT
        self.capture(
            "source",
            {
                "head": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "trackedDelta": subprocess.check_output(
                    ["git", "diff", "--name-only", "HEAD"], cwd=ROOT, text=True
                ).splitlines(),
                "legacyRef": LEGACY,
            },
        )
        self.env = os.environ.copy()
        # Explicit loopback fixture settings prevent accidental remote provider calls.
        for key in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "AI_PDF_DEEPSEEK_API_KEY"):
            self.env.pop(key, None)
        self.env.update(
            AI_PDF_DATABASE_URL=self.url,
            AI_PDF_MINIO_BUCKET=os.environ.get(
                "CITEFRAME_TEST_S3_BUCKET", f"pr25-services-{os.getpid()}"
            ),
            AI_PDF_API_INTERNAL_TOKEN=TOKEN,
            AI_PDF_OPENAI_API_KEY="fixture-only-not-a-valid-key",
            AI_PDF_OPENAI_API_BASE="http://127.0.0.1:9/v1",
            AI_PDF_GENERATION_PROVIDER="openai",
            AI_PDF_GENERATION_MODEL="gpt-5.5",
            AI_PDF_EMBEDDING_PROVIDER="ollama",
            AI_PDF_EMBEDDING_MODEL="qwen3-embedding:0.6b",
            AI_PDF_EMBEDDING_DIMENSIONS="1024",
            AI_PDF_EMBEDDING_VERSION="embedding-v1",
            PYTHONUTF8="1",
            PYTHONDONTWRITEBYTECODE="1",
        )

    def environment(self, root=None):
        root = root or self.root
        env = self.env.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            str(p)
            for p in [
                root / "apps/api/src",
                root / "apps/worker/src",
                root / "tools/evaluation/src",
                *(p / "src" for p in (root / "packages").iterdir() if p.is_dir()),
            ]
        )
        return env

    def command(self, args, *, root=None, expected=0, timeout=180):
        source = root or self.root
        if source != ROOT and args[0] == RUNTIME:
            driver = self.directory / "archived-layout-runtime.py"
            driver.write_text(legacy_runtime_source(RUNTIME.read_text(encoding="utf-8")), encoding="utf-8")
            args = [driver, *args[1:]]
        self.counter += 1
        log = self.directory / f"command-{self.counter}.log"
        with log.open("wb") as stream:
            result = subprocess.run(
                [sys.executable, *map(str, args)],
                env=self.environment(root),
                cwd=self.directory,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
        assert result.returncode == expected, (
            args,
            result.returncode,
            log.read_text(encoding="utf-8")[-18000:],
        )
        return log

    def migrate(self, root=ROOT, revision="head"):
        self.command(
            ["-m", "alembic", "-c", root / "apps/api/alembic.ini", "upgrade", revision],
            root=root,
        )
        self.root = root

    def start_api(self):
        self.stop_api()
        log = self.directory / f"api-{uuid4().hex}.log"
        self.server_log = log.open("wb")
        self.server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "ai_pdf_api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "0",
            ],
            env=self.environment(),
            cwd=self.directory,
            stdout=self.server_log,
            stderr=subprocess.STDOUT,
        )
        for _ in range(150):
            assert self.server.poll() is None, "API exited; inspect API log"
            bound = re.search(
                r"Uvicorn running on (http://127\.0\.0\.1:\d+)",
                log.read_text(encoding="utf-8"),
            )
            if bound:
                self.api = bound.group(1)
                try:
                    if (
                        httpx.get(self.api + "/openapi.json", timeout=1).status_code
                        == 200
                    ):
                        return
                except httpx.HTTPError:
                    pass
            time.sleep(0.2)
        raise AssertionError("API startup timeout")

    def seed(self):
        from citeframe_evaluation.acceptance.common import IDS

        self.command([RUNTIME, "seed"])
        self.workspace, self.user, self.asset = (
            IDS["workspace"],
            IDS["creator"],
            IDS["asset"],
        )
        self.prefix = f"/v1/workspaces/{self.workspace}/research-runs"
        login = self.request(
            "POST",
            "/v1/auth/login",
            json={
                "email": "issue25@example.com",
                "password": "issue25-local-fixture-only",
            },
        ).json()
        assert login["user"]["id"] == self.user
        self.capture("login", {"status": 200, "userId": self.user})

    def request(self, method, path, *, expected=200, **kwargs):
        response = httpx.request(
            method,
            self.api + path,
            timeout=40,
            headers={
                "x-ai-pdf-internal-token": TOKEN,
                "x-user-id": self.user,
                "Idempotency-Key": "issue25-" + uuid4().hex,
            },
            **kwargs,
        )
        assert response.status_code == expected, (
            method,
            path,
            response.status_code,
            response.text,
        )
        return response

    def create(self, label):
        response = self.request(
            "POST",
            self.prefix,
            expected=201,
            json={
                "question": label,
                "assetScope": {"mode": "selected", "assetIds": [self.asset]},
            },
        )
        assert response.json()["run"]["createdByUserId"] == self.user
        self.run = response.json()["run"]["id"]
        self.path = f"{self.prefix}/{self.run}"
        return response.json()

    def work(
        self,
        mode="resolved",
        *,
        steps=32,
        until_gate=False,
        crash=None,
        expected=0,
        exhaust_tools=False,
    ):
        args = [RUNTIME, "work", "--mode", mode, "--steps", str(steps)]
        if exhaust_tools:
            args.append("--exhaust-tools")
        if until_gate:
            args.append("--until-gate")
        if crash:
            args += ["--crash", crash, "--marker", self.directory / "crash.json"]
        return self.command(args, expected=86 if crash else expected)

    def rows(self, table):
        assert table.replace("_", "").isalnum()
        with self.engine.connect() as connection:
            rows = [
                dict(row)
                for row in connection.execute(
                    text(f'SELECT * FROM "{table}"')
                ).mappings()
            ]
            return sorted(
                rows,
                key=lambda row: str(
                    row.get("id", (row.get("step_id"), row.get("operation_number")))
                ),
            )

    def binding(self):
        snapshots = self.rows("research_execution_snapshots")
        assert len(snapshots) == 1
        snapshot = snapshots[0]
        return {
            "snapshot": snapshot,
            "prompts": sorted(
                self.rows("research_execution_prompt_versions"),
                key=lambda r: r["node_key"],
            ),
            "assets": self.rows("research_execution_assets"),
            "approval": [
                row
                for row in self.rows("human_decisions")
                if row["decision_type"] == "plan_approval"
            ],
        }

    def capture(self, name, value):
        (self.directory / (name + ".json")).write_text(
            json.dumps(value, default=str, indent=2), encoding="utf-8"
        )

    def stop_api(self):
        if self.server:
            self.server.terminate()
            self.server.wait(timeout=30)
            self.server_log.close()
            self.server = None

    def close(self):
        self.stop_api()
        self.engine.dispose()
        with self.admin.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=:name AND pid<>pg_backend_pid()"
                ),
                {"name": self.database},
            )
            connection.exec_driver_sql(f'DROP DATABASE "{self.database}"')
        self.admin.dispose()
