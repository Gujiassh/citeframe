"""Exact reviewed product-delta admission for the integrated deployment fixture."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ARCHITECTURE_BASE = "5ed02c8b7b5f357f58d1c3fd270ead0718e7afbf"
PRODUCT_PATHS = ["apps", "packages", "tools/evaluation", "infra/docker",
                 "infra/scripts/compose-common.sh", "infra/scripts/backup-deployment.sh",
                 "infra/scripts/restore-deployment.sh", "infra/scripts/run-r800-acceptance.sh",
                 "package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml"]


def assert_exact_delta(manifest, observed):
    assert manifest["schemaVersion"] == 1
    assert manifest["architectureBase"] == ARCHITECTURE_BASE
    expected = {item["path"]: item["integratedBlob"] for item in manifest["files"]}
    assert len(expected) == len(manifest["files"]), "Duplicate admitted path"
    assert observed == expected, "Unknown, missing or altered product delta"


def verify_product_delta(source: Path, target_head: str):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=source, text=True).strip()
    path = source / "specs/v5/worker-layout/integrated-product-delta.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for ancestor in [ARCHITECTURE_BASE, *manifest["reviewedSourceHeads"]]:
        subprocess.run(["git", "merge-base", "--is-ancestor", ancestor, target_head], cwd=source, check=True)
    approved = {ARCHITECTURE_BASE, *manifest["reviewedSourceHeads"]}
    for item in manifest["files"]:
        assert item["reviewedSourceHead"] in approved, "Unapproved provenance head"
        assert git("rev-parse", item["reviewedSourceHead"] + ":" + item["reviewedSourcePath"]) == item["reviewedSourceBlob"], "Reviewed source provenance changed"
    paths = git("diff", "--name-only", ARCHITECTURE_BASE, target_head, "--", *PRODUCT_PATHS).splitlines()
    observed = {name: git("rev-parse", target_head + ":" + name) for name in paths}
    assert_exact_delta(manifest, observed)
    return manifest
