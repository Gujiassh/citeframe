#!/usr/bin/env python3
"""R1.5 real-PostgreSQL admission evidence runner."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
R0_RUNNER = ROOT / "infra/scripts/run-r0-postgres-contention.py"
DEFAULT_OUTPUT = ROOT / "docs/evals/r15-postgres-admission-2026-08-31.json"
CANDIDATE_FILES = (
    "packages/research-persistence/src/citeframe_research_persistence/__init__.py",
    "packages/research-persistence/src/citeframe_research_persistence/errors.py",
    "packages/research-persistence/src/citeframe_research_persistence/lease.py",
    "apps/worker/src/ai_pdf_worker/research_runtime_processor.py",
    "apps/worker/src/ai_pdf_worker/research_runtime_core.py",
    "infra/scripts/run-r15-postgres-admission.py",
)

spec = importlib.util.spec_from_file_location("citeframe_r0_harness", R0_RUNNER)
assert spec is not None and spec.loader is not None
r0 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = r0
spec.loader.exec_module(r0)

from citeframe_persistence.models import (
    ResearchEvent,
    ResearchExecutionSnapshot,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
    WorkspaceMembership,
)
from citeframe_research_persistence.errors import (
    ResearchAdmissionDeferred,
)
from citeframe_research_persistence.lease import claim_next_research_step


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def candidate_hash() -> str:
    digest = hashlib.sha256()
    for relative in sorted(CANDIDATE_FILES):
        payload = (ROOT / relative).read_bytes()
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(payload).digest())
    return digest.hexdigest()


def candidate_diff_hash() -> str:
    diff = subprocess.check_output(
        ["git", "diff", "--binary", "HEAD", "--", *CANDIDATE_FILES], cwd=ROOT
    )
    return sha256_bytes(diff)


def row_value(row: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if isinstance(value, datetime):
            value = value.astimezone(UTC).isoformat()
        result[column.name] = value
    return result


def aggregate_snapshot(db: Any, run_id: str) -> dict[str, Any]:
    run = db.get(ResearchRun, run_id)
    steps = list(
        db.scalars(
            select(ResearchStep)
            .where(ResearchStep.run_id == run_id)
            .order_by(ResearchStep.id)
        )
    )
    step_ids = [step.id for step in steps]
    attempts = list(
        db.scalars(
            select(ResearchStepAttempt)
            .where(ResearchStepAttempt.step_id.in_(step_ids))
            .order_by(ResearchStepAttempt.id)
        )
    )
    events = list(
        db.scalars(
            select(ResearchEvent)
            .where(ResearchEvent.run_id == run_id)
            .order_by(ResearchEvent.id)
        )
    )
    memberships = list(
        db.scalars(
            select(WorkspaceMembership)
            .where(WorkspaceMembership.workspace_id == run.workspace_id)
            .order_by(WorkspaceMembership.user_id)
        )
    )
    return {
        "run": row_value(run),
        "steps": [row_value(item) for item in steps],
        "attempts": [row_value(item) for item in attempts],
        "events": [row_value(item) for item in events],
        "memberships": [row_value(item) for item in memberships],
    }


def set_cap(harness: Any, fixture: Any, cap: int) -> None:
    with harness.sessions() as db:
        db.get(
            ResearchExecutionSnapshot, fixture.snapshot_id
        ).max_parallel_researchers = cap
        db.commit()


def retire_run(harness: Any, run_id: str) -> None:
    with harness.sessions() as db:
        run = db.get(ResearchRun, run_id)
        run.status = "cancelled"
        run.finished_at = datetime.now(UTC)
        run.updated_at = run.finished_at
        db.commit()


def claim(harness: Any, worker: str, *, excluded: frozenset[str] = frozenset()) -> Any:
    with harness.sessions() as db:
        try:
            lease = claim_next_research_step(
                db,
                worker_instance_id=worker,
                lease_seconds=300,
                now=datetime.now(UTC),
                excluded_run_ids=excluded,
            )
            db.commit()
            return lease
        except ResearchAdmissionDeferred:
            db.rollback()
            raise


def scenario_cap_one_contention(harness: Any) -> dict[str, Any]:
    fixture = harness.seed_run("r15-cap-one", step_count=2)
    set_cap(harness, fixture, 1)
    first = claim(harness, "r15-cap-one-1")
    assert first is not None
    outcomes = ["claimed"]
    errors: list[str] = []

    def second_worker() -> None:
        try:
            try:
                claim(harness, "r15-cap-one-2")
                outcomes.append("unexpected-claimed")
            except ResearchAdmissionDeferred:
                outcomes.append("deferred")
        except Exception as error:  # noqa: BLE001 - thread errors are re-raised by main
            errors.append(repr(error))

    thread = threading.Thread(target=second_worker)
    thread.start()
    thread.join(timeout=10)
    assert not thread.is_alive(), "contention thread did not terminate"
    assert not errors, errors
    assert sorted(outcomes) == ["claimed", "deferred"], outcomes
    with harness.sessions() as db:
        state = aggregate_snapshot(db, fixture.run_id)
    assert len(state["attempts"]) == 1
    assert [step["status"] for step in state["steps"]].count("running") == 1
    assert [step["status"] for step in state["steps"]].count("queued") == 1
    assert len(state["events"]) == 2
    result = {
        "workerIds": 2,
        "outcomes": sorted(outcomes),
        "attemptCount": 1,
        "eventCount": 2,
    }
    retire_run(harness, fixture.run_id)
    return result


def scenario_cap_n(harness: Any) -> dict[str, Any]:
    fixture = harness.seed_run("r15-cap-n", step_count=3)
    set_cap(harness, fixture, 2)
    assert claim(harness, "cap-n-1") is not None
    assert claim(harness, "cap-n-2") is not None
    try:
        claim(harness, "cap-n-3")
        raise AssertionError("cap=N third researcher was admitted")
    except ResearchAdmissionDeferred:
        pass
    retire_run(harness, fixture.run_id)
    return {"cap": 2, "claimed": 2, "third": "deferred"}


def scenario_expired_db_time(harness: Any) -> dict[str, Any]:
    fixture = harness.seed_run("r15-expired", step_count=2)
    set_cap(harness, fixture, 1)
    first = claim(harness, "expired-1")
    with harness.sessions() as db:
        attempt = db.get(ResearchStepAttempt, first.attempt_id)
        attempt.lease_expires_at = db.scalar(select(func.now())) - timedelta(seconds=1)
        db.commit()
    second = claim(harness, "expired-2")
    assert second is not None
    result = {
        "expiredAttemptStillRunning": True,
        "secondClaimed": True,
        "clock": "database func.now()",
    }
    retire_run(harness, fixture.run_id)
    return result


def scenario_nonresearcher_bypass(harness: Any) -> dict[str, Any]:
    fixture = harness.seed_run("r15-bypass", step_count=2)
    set_cap(harness, fixture, 1)
    assert claim(harness, "bypass-1") is not None
    with harness.sessions() as db:
        queued = db.scalar(
            select(ResearchStep).where(
                ResearchStep.run_id == fixture.run_id, ResearchStep.status == "queued"
            )
        )
        queued.step_kind = "join"
        queued.branch_key = None
        db.commit()
    lease = claim(harness, "bypass-2")
    assert lease is not None and lease.step_kind == "join"
    retire_run(harness, fixture.run_id)
    return {"claimedKind": lease.step_kind}


def scenario_exclusion_and_zero_mutation(harness: Any) -> dict[str, Any]:
    full = harness.seed_run(
        "r15-full-first",
        step_count=2,
        queued_at=datetime.now(UTC) - timedelta(seconds=5),
    )
    other = harness.seed_run("r15-other", step_count=1, queued_at=datetime.now(UTC))
    set_cap(harness, full, 1)
    set_cap(harness, other, 1)
    assert claim(harness, "full-seed") is not None
    with harness.sessions() as db:
        before = aggregate_snapshot(db, full.run_id)
    try:
        claim(harness, "scan-full")
        raise AssertionError("expected cap-full deferral")
    except ResearchAdmissionDeferred as deferred:
        assert deferred.run_id == full.run_id
    with harness.sessions() as db:
        after = aggregate_snapshot(db, full.run_id)
    assert before == after, (
        "cap-full rollback mutated persisted aggregate or membership"
    )
    lease = claim(harness, "scan-other", excluded=frozenset({full.run_id}))
    assert lease is not None and lease.run_id == other.run_id
    return {"fullRunZeroMutation": True, "otherRunClaimed": other.run_id}


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database-url",
        default=os.environ.get(
            "R15_DATABASE_URL",
            "postgresql+psycopg://ai_pdf:ai_pdf_dev@127.0.0.1:5432/ai_pdf_workspace",
        ),
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    command = "uv run --project apps/worker python infra/scripts/run-r15-postgres-admission.py"
    source_url = make_url(args.database_url)
    database_name = f"citeframe_r15_{os.urandom(6).hex()}"
    admin_engine = create_engine(source_url.set(database="postgres"), future=True)
    database_created = False
    harness = None
    try:
        with admin_engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as connection:
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
        database_created = True
        isolated_url = source_url.set(database=database_name).render_as_string(
            hide_password=False
        )
        harness = r0.ContentionHarness(isolated_url)
        harness.setup()
        with harness.admin_engine.connect() as connection:
            versions = {
                "server": connection.scalar(text("SHOW server_version")),
                "vector": connection.scalar(
                    text("SELECT extversion FROM pg_extension WHERE extname='vector'")
                ),
                "pgTrgm": connection.scalar(
                    text("SELECT extversion FROM pg_extension WHERE extname='pg_trgm'")
                ),
            }
        scenarios = {
            "capOneContention": scenario_cap_one_contention(harness),
            "capN": scenario_cap_n(harness),
            "expiredDbTime": scenario_expired_db_time(harness),
            "nonresearcherBypass": scenario_nonresearcher_bypass(harness),
            "exclusionAndZeroMutation": scenario_exclusion_and_zero_mutation(harness),
        }
        report = {
            "artifactKind": "r15-postgres-admission-v2",
            "generatedAt": datetime.now(UTC).isoformat(),
            "baseSha": git("rev-parse", "HEAD"),
            "candidateProductionAndRunnerHash": candidate_hash(),
            "candidateTrackedDiffHash": candidate_diff_hash(),
            "exactCommand": command,
            "postgresql": versions,
            "temporarySchema": harness.schema,
            "scenarios": scenarios,
            "passed": True,
            "qualityEvidence": False,
        }
        payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
        report["payloadWithoutHashFieldSha256"] = sha256_bytes(payload)
        payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
        atomic_write(args.output.resolve(), payload)
        stdout = json.dumps(
            {
                "output": str(args.output),
                "artifactSha256": sha256_bytes(payload),
                "passed": True,
            },
            sort_keys=True,
        )
        print(stdout)
        return 0
    finally:
        try:
            if harness is not None:
                harness.cleanup()
        finally:
            try:
                if database_created:
                    with admin_engine.connect().execution_options(
                        isolation_level="AUTOCOMMIT"
                    ) as connection:
                        connection.execute(
                            text(
                                f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'
                            )
                        )
            finally:
                admin_engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
