"""Shared constants, source proof, and database session helpers for the R2 harness."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

LOCK_TIMEOUT_MS = 8_000
PROCESS_TIMEOUT_SECONDS = 20.0
START_SHA = "a616eea1350b095c6f229890d2c47e5010902330"
APP_PREFIX = "citeframe-r2:"
PRODUCTION_MODULES = (
    "ai_pdf_worker.research_runtime_processor",
    "ai_pdf_worker.research_persistence_service",
    "citeframe_research_persistence.lease",
    "citeframe_research_persistence.state",
    "citeframe_research_persistence.locks",
    "citeframe_research_persistence.events",
    "citeframe_research_persistence.provider",
    "citeframe_research_persistence.tools",
    "citeframe_research_persistence.publication",
)
IMMUTABLE_SOURCE_FILES = (
    "apps/worker/src/ai_pdf_worker/main.py",
    "apps/worker/src/ai_pdf_worker/research_runtime.py",
    "apps/worker/src/ai_pdf_worker/research_runtime_core.py",
    "apps/worker/src/ai_pdf_worker/research_runtime_handlers.py",
    "apps/worker/src/ai_pdf_worker/research_runtime_ports.py",
    "apps/worker/src/ai_pdf_worker/research_runtime_processor.py",
    "apps/worker/src/ai_pdf_worker/research_persistence_service.py",
    "apps/api/src/ai_pdf_api/services/research/research_decisions.py",
    "apps/api/src/ai_pdf_api/services/research/research_worker_publication.py",
    "packages/backend-persistence/src/citeframe_persistence/models/research_artifact.py",
    "packages/backend-persistence/src/citeframe_persistence/models/research_execution.py",
    "packages/backend-persistence/src/citeframe_persistence/models/research_run.py",
    "packages/backend-persistence/src/citeframe_persistence/models/research_versions.py",
    "packages/research-persistence/src/citeframe_research_persistence/admission.py",
    "packages/research-persistence/src/citeframe_research_persistence/cancellation.py",
    "packages/research-persistence/src/citeframe_research_persistence/completion.py",
    "packages/research-persistence/src/citeframe_research_persistence/commands.py",
    "packages/research-persistence/src/citeframe_research_persistence/constants.py",
    "packages/research-persistence/src/citeframe_research_persistence/events.py",
    "packages/research-persistence/src/citeframe_research_persistence/lease.py",
    "packages/research-persistence/src/citeframe_research_persistence/locks.py",
    "packages/research-persistence/src/citeframe_research_persistence/provider.py",
    "packages/research-persistence/src/citeframe_research_persistence/publication.py",
    "packages/research-persistence/src/citeframe_research_persistence/state.py",
    "packages/research-persistence/src/citeframe_research_persistence/tools.py",
    "infra/scripts/run-r0-postgres-contention.py",
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def sqlstate(error: BaseException | None) -> str | None:
    current = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        value = getattr(current, "sqlstate", None) or getattr(current, "pgcode", None)
        if value:
            return str(value)
        current = getattr(current, "orig", None) or getattr(current, "__cause__", None)
    return None


def error_json(error: BaseException) -> dict[str, Any]:
    payload = {"type": type(error).__name__, "message": str(error), "sqlstate": sqlstate(error)}
    if getattr(error, "code", None):
        payload["code"] = error.code
    return payload


def _git_paths(repo_root: Path, *args: str) -> list[str]:
    output = subprocess.check_output(["git", *args], cwd=repo_root)
    return sorted(item.decode() for item in output.split(b"\0") if item)


def candidate_source_snapshot(repo_root: Path, expected_head: str) -> dict[str, Any]:
    root = repo_root.resolve()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if head != expected_head:
        raise AssertionError(f"candidate base HEAD changed: expected={expected_head} actual={head}")

    allowed_candidate_paths = {
        "packages/research-persistence/src/citeframe_research_persistence/admission.py",
        "packages/research-persistence/src/citeframe_research_persistence/lease.py",
    }
    tracked_diff_paths = _git_paths(root, "diff", "--name-only", "-z", expected_head, "--")
    unexpected_tracked = sorted(set(tracked_diff_paths) - allowed_candidate_paths)
    if unexpected_tracked:
        raise AssertionError(f"unexpected tracked candidate paths: {unexpected_tracked}")

    production_prefixes = (
        "apps/api/src/",
        "apps/worker/src/",
        "packages/backend-persistence/src/",
        "packages/research-persistence/src/",
    )
    untracked_production_paths = [
        path
        for path in _git_paths(root, "ls-files", "--others", "--exclude-standard", "-z", "--")
        if path.startswith(production_prefixes)
    ]
    unexpected_untracked = sorted(set(untracked_production_paths) - allowed_candidate_paths)
    if unexpected_untracked:
        raise AssertionError(f"unexpected untracked production paths: {unexpected_untracked}")

    production_files: dict[str, dict[str, Any]] = {}
    changed_production_paths: list[str] = []
    for relative in IMMUTABLE_SOURCE_FILES:
        path = (root / relative).resolve()
        if root not in path.parents or not path.is_file():
            raise AssertionError(f"candidate source missing/outside tree: {relative}")
        base = subprocess.run(
            ["git", "show", f"{expected_head}:{relative}"],
            cwd=root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if base.returncode not in {0, 128}:
            raise AssertionError(f"cannot read base Git object: {relative}")
        base_sha = hashlib.sha256(base.stdout).hexdigest() if base.returncode == 0 else None
        working_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        matches_base = base_sha == working_sha
        if not matches_base:
            changed_production_paths.append(relative)
        production_files[relative] = {
            "workingTreeSha256": working_sha,
            "immutableGitObjectSha256": base_sha,
            "matchesImmutableHead": matches_base,
        }

    unexpected_source_changes = sorted(set(changed_production_paths) - allowed_candidate_paths)
    if unexpected_source_changes:
        raise AssertionError(f"unexpected production source changes: {unexpected_source_changes}")
    manifest = {
        "baseHead": expected_head,
        "trackedDiffPaths": tracked_diff_paths,
        "untrackedProductionPaths": untracked_production_paths,
        "changedProductionPaths": sorted(changed_production_paths),
        "productionFiles": production_files,
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    manifest["candidateDirty"] = bool(changed_production_paths)
    manifest["candidateSourceManifestSha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    return manifest


def session_factory(
    database_url: str, schema: str, app_name: str
) -> tuple[Any, Callable[[], Session], list[int]]:
    options = f"-csearch_path={schema},public"
    engine = create_engine(database_url, future=True, pool_pre_ping=True, connect_args={"options": options})
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    backend_pids: list[int] = []

    def sessions() -> Session:
        db = maker()
        db.execute(text("SELECT set_config('application_name', :name, false)"), {"name": app_name})
        db.execute(text("SELECT set_config('lock_timeout', :value, false)"), {"value": f"{LOCK_TIMEOUT_MS}ms"})
        db.execute(text("SELECT set_config('statement_timeout', :value, false)"), {"value": f"{LOCK_TIMEOUT_MS + 4000}ms"})
        backend_pids.append(int(db.scalar(select(func.pg_backend_pid()))))
        return db

    return engine, sessions, backend_pids


def load_r0(repo_root: Path) -> Any:
    path = repo_root / "infra/scripts/run-r0-postgres-contention.py"
    spec = importlib.util.spec_from_file_location("citeframe_r0_harness", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load R0 harness")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


HARNESS_SOURCE_FILES = (
    "infra/scripts/run-r2-multi-worker.py",
    "infra/scripts/run-r2-multi-worker.sh",
    "infra/scripts/r2_multi_worker/__init__.py",
    "infra/scripts/r2_multi_worker/accounting_actor.py",
    "infra/scripts/r2_multi_worker/common.py",
    "infra/scripts/r2_multi_worker/controller.py",
    "infra/scripts/r2_multi_worker/harness.py",
    "infra/scripts/r2_multi_worker/scenarios_accounting.py",
    "infra/scripts/r2_multi_worker/scenarios_admission.py",
    "infra/scripts/r2_multi_worker/scenarios_publication.py",
    "infra/scripts/r2_multi_worker/scenarios_runtime.py",
    "infra/scripts/r2_multi_worker/worker_actor.py",
)


def harness_hashes(repo_root: Path) -> dict[str, str]:
    return {
        relative: hashlib.sha256((repo_root / relative).read_bytes()).hexdigest()
        for relative in HARNESS_SOURCE_FILES
    }
