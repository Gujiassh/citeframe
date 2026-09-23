#!/usr/bin/env python3
"""Run the A2a Research behavior probe against the frozen baseline and candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from a2a_r2_delta import compare
from a2a_feature_history_oracle import compare_historical_feature

BASELINE_REF = "d1b5945e977445e4db6bf56ef54cf61607ead2e2"
BASELINE_ARCHIVE_PATHS = (
    "apps/api",
    "apps/worker",
)
REQUIRED_AREAS = {
    "normalizedDbRows",
    "exactPayloadBytes",
    "exactEventBytes",
    "leaseFencing",
    "retryCancelReclaimRecovery",
    "permission",
    "terminalProcessSemantics",
}


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def _run_probe(
    *,
    root: Path,
    probe: Path,
    output: Path,
    uv: Path,
    label: str,
    mutation: str | None = None,
    historical_state: Path | None = None,
    current_scenario: bool = False,
    stored_approvals: bool = False,
) -> None:
    paths = [
        root / "apps/api/src",
        root / "apps/worker/src",
        root / "tools/evaluation/src",
        root / "packages/backend-contracts/src",
        root / "packages/backend-persistence/src",
        root / "packages/research-persistence/src",
    ]
    env = os.environ.copy()
    env.update(
        {
            "A2A_DIFFERENTIAL_PROBE_OUTPUT": str(output),
            "A2A_DIFFERENTIAL_LABEL": label,
            "PYTHONPATH": os.pathsep.join(str(path) for path in paths if path.exists()),
            "PYTHONNOUSERSITE": "1",
            "AI_PDF_EMBEDDING_PROVIDER": "openai",
            "AI_PDF_EMBEDDING_MODEL": "text-embedding-3-small",
            "AI_PDF_EMBEDDING_DIMENSIONS": "1024",
            "AI_PDF_EMBEDDING_VERSION": "embedding-v1",
            "AI_PDF_OPENAI_API_BASE": "https://api.openai.com/v1",
            "AI_PDF_CAPABILITY_FINGERPRINT_PEPPER": "local-development-capability-fingerprint-pepper",
            "AI_PDF_GENERATION_PROVIDER": "openai",
            "AI_PDF_GENERATION_MODEL": "gpt-5.5",
            "AI_PDF_RETRIEVAL_STRATEGY": "hybrid",
        }
    )
    env.pop("AI_PDF_WORKER_INSTANCE_ID", None)
    for inherited in (
        "PYTEST_ADDOPTS",
        "PYTEST_PLUGINS",
        "UV_INEXACT",
        "UV_NO_SYNC",
        "UV_PROJECT_ENVIRONMENT",
        "VIRTUAL_ENV",
    ):
        env.pop(inherited, None)
    for key in ("A2A_HISTORICAL_STATE", "A2A_CURRENT_SCENARIO", "A2A_STORED_APPROVALS"):
        env.pop(key, None)
    if stored_approvals:
        env["A2A_STORED_APPROVALS"] = "1"
    if historical_state is not None:
        env["A2A_HISTORICAL_STATE"] = str(historical_state)
    if current_scenario:
        env["A2A_CURRENT_SCENARIO"] = "1"
    if mutation is not None:
        env["A2A_DIFFERENTIAL_MUTATION"] = mutation
    worker_project = root / "apps/worker"
    completed = subprocess.run(
        [
            str(uv),
            "run",
            "--project",
            str(worker_project),
            "--frozen",
            "--exact",
            "--python",
            "3.12",
            "python",
            "-m",
            "pytest",
            "-q",
            "-s",
            str(probe),
        ],
        cwd=root / "apps/api",
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=300,
    )
    if completed.returncode:
        raise RuntimeError(f"{label} probe failed ({completed.returncode})\n{completed.stdout}")
    if not output.is_file():
        raise RuntimeError(f"{label} probe produced no report\n{completed.stdout}")


def _resolve_baseline(root: Path, baseline_ref: str) -> str:
    command = ["git", "rev-parse", f"{baseline_ref}^{{commit}}"]
    resolved = subprocess.run(command, cwd=root, text=True, capture_output=True)
    if resolved.returncode:
        print(f"a2a_differential baseline_fetch ref={baseline_ref}", file=sys.stderr)
        subprocess.run(
            ["git", "fetch", "--no-tags", "--depth=1", "origin", baseline_ref],
            cwd=root,
            check=True,
            timeout=120,
        )
        resolved = subprocess.run(command, cwd=root, text=True, capture_output=True)
    if resolved.returncode:
        raise RuntimeError(f"baseline unavailable: {baseline_ref}: {resolved.stderr.strip()}")
    value = resolved.stdout.strip()
    if value != baseline_ref:
        raise RuntimeError(f"baseline ref drifted: expected={baseline_ref} actual={value}")
    return value


def _fingerprint(
    root: Path,
    *,
    diff_paths: tuple[str, ...] | None,
    untracked_prefixes: tuple[str, ...],
) -> tuple[str, bool]:
    digest = hashlib.sha256()
    command = ["git", "diff", "--binary", "HEAD"]
    if diff_paths is not None:
        command.extend(("--", *diff_paths))
    diff = subprocess.check_output(command, cwd=root)
    digest.update(diff)
    untracked = [
        item
        for item in subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=root,
        ).split(b"\0")
        if item and item.decode().startswith(untracked_prefixes)
    ]
    for raw_path in sorted(untracked):
        path = root / raw_path.decode()
        digest.update(raw_path + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest(), bool(diff or untracked)


def _historical_probe_source(source: str) -> str:
    """Bind the current oracle to the frozen pre-layout A2a baseline module paths."""
    replacements = {
        "citeframe_evaluation.acceptance.common": "ai_pdf_worker.r800_acceptance_common",
        "citeframe_evaluation.acceptance.fixture": "ai_pdf_worker.r800_acceptance_fixture",
        "ai_pdf_worker.research.runtime": "ai_pdf_worker.research_runtime",
        "from ai_pdf_worker.research import persistence as composition":
            "from ai_pdf_worker import research_persistence_service as composition",
        "from ai_pdf_worker.research import core as research_runtime_core":
            "from ai_pdf_worker import research_runtime_core",
    }
    for current, historical in replacements.items():
        source = source.replace(current, historical)
    return source


def _semantic_fingerprint(root: Path) -> tuple[str, bool]:
    return _fingerprint(
        root,
        diff_paths=("apps/api", "apps/worker", "packages", "infra/scripts", "tools/evaluation"),
        untracked_prefixes=("apps/api/", "apps/worker/", "packages/", "infra/scripts/", "tools/evaluation/"),
    )


def _repair_snapshot_fingerprint(root: Path) -> tuple[str, bool]:
    return _fingerprint(
        root,
        diff_paths=None,
        untracked_prefixes=(
            ".github/",
            "apps/",
            "docs/",
            "infra/scripts/",
            "packages/",
            "specs/",
            "tools/evaluation/",
        ),
    )


def _validate_composition(label: str, payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} probe has no composition evidence")
    kind = payload.get("kind")
    command_module = payload.get("commandModule")
    uow_enters = payload.get("uowEnterCount")
    if label == "baseline":
        if (
            kind != "baseline-api-research-worker"
            or not isinstance(command_module, str)
            or not command_module.startswith("ai_pdf_api.services.research")
            or uow_enters != 0
        ):
            raise RuntimeError(f"baseline production composition invalid: {payload}")
    elif (
        kind != "candidate-neutral-research-uow"
        or not isinstance(command_module, str)
        or not command_module.startswith("citeframe_research_persistence")
        or not isinstance(uow_enters, int)
        or uow_enters < 1
    ):
        raise RuntimeError(f"candidate production composition invalid: {payload}")
    return payload


def _validate_worker_environment(
    label: str,
    payload: object,
    *,
    expected_root: Path,
) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} probe has no Worker environment evidence")
    executable = payload.get("pythonExecutable")
    python_prefix = payload.get("pythonPrefix")
    langgraph_module = payload.get("langgraphModule")
    worker_module = payload.get("workerModule")
    if not all(
        isinstance(value, str)
        for value in (executable, python_prefix, langgraph_module, worker_module)
    ):
        raise RuntimeError(f"{label} probe Worker environment fields are invalid: {payload}")
    expected_prefix = (expected_root / "apps/worker/.venv").absolute()
    expected_worker_source = (expected_root / "apps/worker/src").absolute()
    prefix_path = Path(python_prefix).absolute()
    executable_path = Path(executable).absolute()
    langgraph_path = Path(langgraph_module).absolute()
    worker_path = Path(worker_module).absolute()
    if (
        prefix_path != expected_prefix
        or not executable_path.is_relative_to(prefix_path)
        or not langgraph_path.is_relative_to(prefix_path)
        or not worker_path.is_relative_to(expected_worker_source)
    ):
        raise RuntimeError(
            f"{label} probe did not use its snapshot Worker environment: {payload}"
        )
    return payload


def _validate_scheduler_evidence(label: str, payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} probe has no scheduler evidence")
    outputs = payload.get("processOneOutputs")
    handled = payload.get("handledAttemptCount")
    if (
        not isinstance(outputs, list)
        or len(outputs) < 2
        or outputs[-1] is not False
        or any(item is not True for item in outputs[:-1])
        or handled != len(outputs) - 1 - payload.get("maintenanceCallCount", 0)
    ):
        raise RuntimeError(f"{label} scheduler evidence is invalid: {payload}")
    return payload


def run(
    root: Path,
    *,
    baseline_ref: str,
    output: Path | None,
    candidate_mutation: str | None = None,
) -> dict[str, object]:
    root = root.resolve()
    probe = root / "apps/api/tests/test_a2a_differential_probe.py"
    if not probe.is_file():
        raise RuntimeError(f"probe not found: {probe}")
    uv_value = shutil.which("uv")
    if uv_value is None:
        raise RuntimeError("uv executable is required for frozen Worker probe environments")
    uv = Path(uv_value).resolve()
    resolved = _resolve_baseline(root, baseline_ref)
    semantic_before, semantic_dirty = _semantic_fingerprint(root)
    repair_before, repair_dirty = _repair_snapshot_fingerprint(root)

    with tempfile.TemporaryDirectory(prefix="citeframe-a2a-differential-") as temp_value:
        temp = Path(temp_value)
        baseline_root = temp / "baseline"
        baseline_root.mkdir()
        archive = temp / "baseline.tar"
        with archive.open("wb") as stream:
            subprocess.run(
                [
                    "git",
                    "archive",
                    "--format=tar",
                    resolved,
                    *BASELINE_ARCHIVE_PATHS,
                ],
                cwd=root,
                check=True,
                stdout=stream,
            )
        with tarfile.open(archive) as bundle:
            bundle.extractall(baseline_root, filter="data")
        baseline_probe = baseline_root / "apps/api/tests/test_a2a_differential_probe.py"
        baseline_probe.parent.mkdir(parents=True, exist_ok=True)
        baseline_probe.write_text(
            _historical_probe_source(probe.read_text(encoding="utf-8")), encoding="utf-8"
        )
        helper = "a2a_historical_state.py"
        (baseline_probe.parent / helper).write_bytes((probe.parent / helper).read_bytes())

        baseline_report = temp / "baseline.json"
        candidate_report = temp / "candidate.json"
        _run_probe(
            root=baseline_root,
            probe=baseline_probe,
            output=baseline_report,
            uv=uv,
            label="baseline",
        )
        _run_probe(
            root=root,
            probe=probe,
            output=candidate_report,
            uv=uv,
            label="candidate",
            mutation=candidate_mutation,
            historical_state=baseline_report,
        )
        current_report = temp / "current.json"
        stored_report = temp / "stored.json"
        _run_probe(root=root, probe=probe, output=current_report, uv=uv, label="candidate", current_scenario=True)
        _run_probe(root=root, probe=probe, output=stored_report, uv=uv, label="candidate",
                   historical_state=baseline_report, stored_approvals=True)
        current = json.loads(current_report.read_text(encoding="utf-8"))
        stored = json.loads(stored_report.read_text(encoding="utf-8"))
        baseline = json.loads(baseline_report.read_text(encoding="utf-8"))
        candidate = json.loads(candidate_report.read_text(encoding="utf-8"))
        parser_evidence = []
        for name, report, schema, origin in (("legacy", baseline, "1", "human"),
                ("restored-new-human", candidate, "2", "human"), ("stored-replay", stored, "1", "human"),
                ("current-default", current, "2", "policy")):
            wire = temp / f"{name}.sse"
            wire.write_text(report["productionSseWire"], encoding="utf-8")
            parsed = subprocess.run([shutil.which("node"), "--import", "tsx", "scripts/check-research-history-sse.mjs",
                str(wire), schema, origin], cwd=root / "apps/web", capture_output=True, text=True)
            if parsed.returncode:
                raise RuntimeError(f"{name} production Web parser failed: {parsed.stdout} {parsed.stderr}")
            parser_evidence.append({"scenario": name, **json.loads(parsed.stdout)})

    semantic_after, _ = _semantic_fingerprint(root)
    repair_after, _ = _repair_snapshot_fingerprint(root)
    if semantic_after != semantic_before:
        raise RuntimeError(
            "candidate semantic worktree changed during probe: "
            f"before={semantic_before} after={semantic_after}"
        )
    if repair_after != repair_before:
        raise RuntimeError(
            "repair snapshot changed during probe: "
            f"before={repair_before} after={repair_after}"
        )
    baseline_composition = _validate_composition("baseline", baseline.get("composition"))
    candidate_composition = _validate_composition("candidate", candidate.get("composition"))
    baseline_environment = _validate_worker_environment(
        "baseline",
        baseline.get("workerEnvironment"),
        expected_root=baseline_root,
    )
    candidate_environment = _validate_worker_environment(
        "candidate",
        candidate.get("workerEnvironment"),
        expected_root=root,
    )
    baseline_scheduler = _validate_scheduler_evidence(
        "baseline", baseline.get("schedulerEvidence")
    )
    candidate_scheduler = _validate_scheduler_evidence(
        "candidate", candidate.get("schedulerEvidence")
    )
    baseline_semantics = baseline.get("semantics")
    candidate_semantics = candidate.get("semantics")
    if not isinstance(baseline_semantics, dict) or not isinstance(candidate_semantics, dict):
        raise RuntimeError("probe report has no semantics object")
    missing = REQUIRED_AREAS - set(baseline_semantics)
    if missing:
        raise RuntimeError(f"probe coverage missing: {sorted(missing)}")
    comparison = compare_historical_feature(baseline, candidate)
    stored_comparison = compare_historical_feature(baseline, stored, stored_responses=True)
    equal = _canonical(baseline_semantics) == _canonical(candidate_semantics)
    require_current = current["workflowEvidence"]["result"] == "completed" and current["scenario"] == "B-current-default"
    comparison["accepted"] = comparison["accepted"] and stored_comparison["accepted"] and require_current
    candidate_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    result: dict[str, object] = {
        "schemaVersion": "citeframe-a2a-r2-explicit-differential-v2",
        **comparison,
        "baselineRef": resolved,
        "rawBaselineReport": baseline,
        "rawCandidateReport": candidate,
        "f1ProjectedCandidateSha256": comparison.get("rawCandidateSha256"),
        "rawBaselineSha256": hashlib.sha256(_canonical(baseline)).hexdigest(),
        "rawCandidateSha256": hashlib.sha256(_canonical(candidate)).hexdigest(),
        "rawStoredReplaySha256": hashlib.sha256(_canonical(stored)).hexdigest(),
        "rawCurrentDefaultSha256": hashlib.sha256(_canonical(current)).hexdigest(),
        "rawStoredReplayReport": stored,
        "rawCurrentDefaultReport": current,
        "historicalStoredReplay": stored_comparison,
        "productionConsumerEvidence": parser_evidence,
        "workflowScenarios": {name: {**report["workflowEvidence"], "candidateHead": candidate_head}
                              for name, report in (("A", candidate), ("AStored", stored), ("B", current))},
        "historicalRecoveryExecution": {"newProviderCalls": stored["semantics"]["terminalProcessSemantics"]["providerNodes"],
            "scheduler": stored["schedulerEvidence"], "replayedResponsesUnchanged": True},
        "candidateHead": candidate_head,
        "candidateSemanticWorktreeSha256": semantic_before,
        "candidateSemanticDirty": semantic_dirty,
        "repairSnapshotSha256": repair_before,
        "repairSnapshotDirty": repair_dirty,
        "baselineComposition": baseline_composition,
        "candidateComposition": candidate_composition,
        "probeExecution": "uv-worker-frozen-exact",
        "baselineWorkerEnvironment": baseline_environment,
        "candidateWorkerEnvironment": candidate_environment,
        "schedulerDelta": {
            "allowed": True,
            "rule": "one attempt per call plus one identified R2 terminal sweep; approved intent/key/event-ID deltas only",
            "baseline": baseline_scheduler,
            "candidate": candidate_scheduler,
        },
        "coverage": sorted(REQUIRED_AREAS),
        "equal": equal,
        "baseline": baseline_semantics,
        "candidate": candidate_semantics,
    }
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(_canonical(result) + b"\n")
    if not equal:
        baseline_pretty = json.dumps(baseline_semantics, ensure_ascii=True, sort_keys=True, indent=2).splitlines()
        candidate_pretty = json.dumps(candidate_semantics, ensure_ascii=True, sort_keys=True, indent=2).splitlines()
        import difflib

        result["diff"] = "\n".join(
            difflib.unified_diff(
                baseline_pretty,
                candidate_pretty,
                fromfile=f"baseline:{resolved}",
                tofile="candidate:worktree",
                lineterm="",
            )
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--baseline-ref", default=BASELINE_REF)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--candidate-mutation",
        choices=("candidate-api-facade",),
    )
    args = parser.parse_args()
    try:
        result = run(
            args.root,
            baseline_ref=args.baseline_ref,
            output=args.output,
            candidate_mutation=args.candidate_mutation,
        )
    except Exception as error:  # noqa: BLE001 - CLI must preserve child evidence
        print(f"a2a_differential status=error detail={error}", file=sys.stderr)
        return 2
    print(
        "a2a_differential "
        f"status={'pass' if result['accepted'] else 'fail'} "
        f"baseline={result['baselineRef']} candidate={result['candidateHead']} "
        f"semantic={result['candidateSemanticWorktreeSha256']} "
        f"repair={result['repairSnapshotSha256']} "
        f"dirty={str(result['repairSnapshotDirty']).lower()} "
        f"coverage={len(result['coverage'])}"
    )
    if not result["accepted"]:
        print(result.get("diff", ""), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
