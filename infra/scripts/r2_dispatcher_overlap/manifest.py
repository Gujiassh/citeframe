"""Source and harness provenance helpers for the dispatcher-overlap proof."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


SOURCE_FILES = (
    "apps/api/scripts/provider_r800_stub.py",
    "apps/api/src/ai_pdf_api/db/session.py",
    "apps/api/src/ai_pdf_api/services/research/research_plan_approval.py",
    "apps/api/src/ai_pdf_api/services/research/research_runs.py",
    "apps/api/src/ai_pdf_api/services/research/research_worker_evidence.py",
    "apps/api/src/ai_pdf_api/services/providers.py",
    "apps/worker/scripts/r800_research_acceptance.py",
    "apps/worker/src/ai_pdf_worker/r800_acceptance_common.py",
    "apps/worker/src/ai_pdf_worker/r800_acceptance_fixture.py",
    "apps/worker/src/ai_pdf_worker/r800_acceptance_scenarios.py",
    "apps/worker/src/ai_pdf_worker/research_executor_tools.py",
    "apps/worker/src/ai_pdf_worker/research_persistence_service.py",
    "apps/worker/src/ai_pdf_worker/research_runtime_agents.py",
    "apps/worker/src/ai_pdf_worker/research_runtime_handlers.py",
    "apps/worker/src/ai_pdf_worker/research_runtime_ports.py",
    "apps/worker/src/ai_pdf_worker/research_runtime_processor.py",
    "infra/docker/Dockerfile.python",
    "infra/docker/compose.deploy.yml",
    "infra/docker/compose.r800.yml",
    "packages/research-persistence/src/citeframe_research_persistence/admission.py",
    "packages/research-persistence/src/citeframe_research_persistence/completion.py",
    "packages/research-persistence/src/citeframe_research_persistence/lease.py",
    "packages/research-persistence/src/citeframe_research_persistence/provider.py",
    "packages/research-persistence/src/citeframe_research_persistence/tools.py",
)

HARNESS_FILES = (
    "infra/scripts/run-r2-dispatcher-overlap.sh",
    "infra/scripts/run-r2-dispatcher-overlap.compose.yml",
    "infra/scripts/r2_dispatcher_overlap/__init__.py",
    "infra/scripts/r2_dispatcher_overlap/actor.py",
    "infra/scripts/r2_dispatcher_overlap/controller.py",
    "infra/scripts/r2_dispatcher_overlap/manifest.py",
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_host_manifest(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=root, text=True
    ).strip()
    status_paths = sorted(
        line[3:] for line in subprocess.check_output(
            ["git", "status", "--short"], cwd=root, text=True
        ).splitlines()
        if len(line) >= 4
    )
    payload: dict[str, Any] = {
        "gitHead": head,
        "branch": branch,
        "dirtyPaths": status_paths,
        "sourceSha256": {relative: file_sha256(root / relative) for relative in SOURCE_FILES},
        "harnessSha256": {relative: file_sha256(root / relative) for relative in HARNESS_FILES},
    }
    payload["manifestSha256"] = manifest_sha256(payload)
    return payload


def container_path(relative: str) -> Path | None:
    if relative.startswith("apps/worker/"):
        return Path("/app") / relative
    if relative.startswith("apps/api/src/"):
        return Path("/app") / relative
    if relative.startswith("packages/"):
        return Path("/app") / relative
    return None


def mounted_harness_path(relative: str) -> Path:
    prefix = "infra/scripts/"
    if not relative.startswith(prefix):
        raise ValueError(f"unexpected harness path: {relative}")
    return Path("/opt/citeframe-infra") / relative.removeprefix(prefix)


def verify_container_manifest(expected: dict[str, Any]) -> dict[str, Any]:
    source_actual: dict[str, str] = {}
    for relative, expected_hash in expected["sourceSha256"].items():
        path = container_path(relative)
        if path is None:
            continue
        actual_hash = file_sha256(path)
        if actual_hash != expected_hash:
            raise AssertionError(
                f"container source hash mismatch: {relative} expected={expected_hash} actual={actual_hash}"
            )
        source_actual[relative] = actual_hash

    harness_actual: dict[str, str] = {}
    for relative, expected_hash in expected["harnessSha256"].items():
        path = mounted_harness_path(relative)
        actual_hash = file_sha256(path)
        if actual_hash != expected_hash:
            raise AssertionError(
                f"mounted harness hash mismatch: {relative} expected={expected_hash} actual={actual_hash}"
            )
        harness_actual[relative] = actual_hash
    return {
        "containerSourceSha256": source_actual,
        "mountedHarnessSha256": harness_actual,
        "allComparableHashesMatch": True,
    }
