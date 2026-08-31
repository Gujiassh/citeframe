from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from ai_pdf_worker.r803_evaluation import _case_artifact, configured_provider
from ai_pdf_worker.r803_evaluation_contract import (
    DEFAULT_PACKAGE_V5_PATH,
    REPO_ROOT,
    CaseExecution,
    EvaluationPackage,
    R803EvaluationError,
    canonical_bytes,
    canonical_sha256,
    file_sha256,
    load_evaluation_package,
)
from ai_pdf_worker.r803_evaluation_diagnostics import (
    DiagnosticCapture,
    OutputFailureDiagnostic,
    secret_scan_text,
    write_raw_output_bundle,
)
from ai_pdf_worker.r803_evaluation_integrity import (
    compute_evaluator_closure,
    list_regular_files_relative,
    scorer_implementation_sha256,
    verify_checksums_exact,
    write_checksums,
)
from ai_pdf_worker.r803_evaluation_provider import (
    RecordedProvider,
    quick_prompt_binding_sha256,
    research_prompt_binding_sha256,
)
from ai_pdf_worker.r803_evaluation_runtime import (
    run_quick_case_with_diagnostics,
    run_research_case_with_diagnostics,
)
from ai_pdf_worker.r803_evaluation_scorer_v2 import (
    SCORER_VERSION,
    assert_quality_failure_diagnostic_bound,
    build_import_report_v2,
    resolve_successful_quality_failure_diagnostic,
    score_case_v2,
)

CAMPAIGN_SCHEMA_VERSION = "r803-campaign-report-v1"
ROUND_SCHEMA_VERSION = "r803-campaign-round-v1"
THRESHOLD_SCHEMA_VERSION = "r803-release-threshold-v1"
PROGRESS_SCHEMA_VERSION = "r803-campaign-progress-v1"
ROUND_MANIFEST_SCHEMA_VERSION = "r803-campaign-round-manifest-v1"
ROUND_START_SCHEMA_VERSION = "r803-campaign-round-start-v1"
PLAN_SCHEMA_VERSION = "r803-campaign-plan-v1"

_IS_WINDOWS = os.name == "nt"


@dataclass(frozen=True)
class CampaignPlan:
    package: EvaluationPackage
    threshold: dict[str, Any]
    threshold_sha256: str
    package_sha256: str
    scorer_version: str
    scorer_implementation_sha256: str
    quick_prompt_binding_sha256: str
    research_prompt_binding_sha256: str
    evaluator_closure_sha256: str
    evaluator_closure_modules: dict[str, str]
    provider_profile_fingerprint: dict[str, object]
    planned_rounds: int
    case_order: tuple[str, ...]
    mode_order: tuple[Literal["quick", "research"], ...]
    plan_sha256: str
    plan_document: dict[str, Any]


def load_threshold(package: EvaluationPackage) -> tuple[dict[str, Any], str]:
    suite = package.document["suite"]
    path = package.path.parents[2] / suite["thresholdPath"]
    digest = file_sha256(path)
    if digest != suite["thresholdSha256"]:
        raise R803EvaluationError("threshold_hash_mismatch")
    threshold = json.loads(path.read_text(encoding="utf-8"))
    if threshold.get("schemaVersion") != THRESHOLD_SCHEMA_VERSION:
        raise R803EvaluationError("unsupported_threshold_schema")
    return threshold, digest


def freeze_campaign_plan(package: EvaluationPackage | None = None) -> CampaignPlan:
    frozen = package or load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    if frozen.document.get("schemaVersion") != "r803-evaluation-package-v5":
        raise R803EvaluationError("campaign_requires_package_v5")
    if frozen.comparison_keys.scorer_version != SCORER_VERSION:
        raise R803EvaluationError("campaign_requires_scorer_v2")
    threshold, threshold_sha256 = load_threshold(frozen)
    planned_rounds = int(threshold["samplePlan"]["prospectivePairedRounds"])
    if planned_rounds != 5:
        raise R803EvaluationError("campaign_requires_five_rounds")
    case_order = tuple(case["id"] for case in frozen.cases)
    mode_order: tuple[Literal["quick", "research"], ...] = ("quick", "research")
    repo_root = frozen.path.parents[2]
    if repo_root.resolve() != REPO_ROOT.resolve():
        # Packages may live under temporary copies in tests; always hash from real repo root.
        repo_root = REPO_ROOT
    closure = compute_evaluator_closure(repo_root)
    scorer_sha = scorer_implementation_sha256(repo_root)
    quick_binding = quick_prompt_binding_sha256(frozen)
    research_binding = research_prompt_binding_sha256(frozen)
    profile = frozen.document["providerProfile"]
    provider_profile_fingerprint = {
        "provider": profile["provider"],
        "model": profile["model"],
        "apiBase": str(profile["apiBase"]).rstrip("/"),
        "apiProtocol": profile["apiProtocol"],
        "maxOutputTokens": profile["maxOutputTokens"],
        "pricingVersion": profile["pricingVersion"],
        "providerProfileSha256": frozen.comparison_keys.provider_profile_sha256,
        "structuredOutputTransport": frozen.document["structuredOutput"]["transportVersion"],
        "schemaSetVersion": frozen.document["structuredOutput"]["schemaSetVersion"],
    }
    plan_body = {
        "packagePath": str(frozen.path.relative_to(frozen.path.parents[2])),
        "packageSha256": frozen.sha256,
        "thresholdPath": frozen.document["suite"]["thresholdPath"],
        "thresholdSha256": threshold_sha256,
        "scorerVersion": SCORER_VERSION,
        "scorerImplementationSha256": scorer_sha,
        "quickPromptBindingSha256": quick_binding,
        "researchPromptBindingSha256": research_binding,
        "evaluatorClosureSha256": closure["closureSha256"],
        "evaluatorClosureModules": closure["modules"],
        "evaluatorClosureStrategy": closure["strategy"],
        "evaluatorClosureRoots": closure["roots"],
        "providerProfileFingerprint": provider_profile_fingerprint,
        "plannedRounds": planned_rounds,
        "caseOrder": list(case_order),
        "modeOrder": list(mode_order),
        "comparisonKeys": frozen.comparison_keys.as_dict(),
    }
    plan_sha256 = canonical_sha256(plan_body)
    plan_document = {
        "schemaVersion": PLAN_SCHEMA_VERSION,
        **plan_body,
        "planSha256": plan_sha256,
    }
    return CampaignPlan(
        package=frozen,
        threshold=threshold,
        threshold_sha256=threshold_sha256,
        package_sha256=frozen.sha256,
        scorer_version=SCORER_VERSION,
        scorer_implementation_sha256=scorer_sha,
        quick_prompt_binding_sha256=quick_binding,
        research_prompt_binding_sha256=research_binding,
        evaluator_closure_sha256=str(closure["closureSha256"]),
        evaluator_closure_modules=dict(closure["modules"]),  # type: ignore[arg-type]
        provider_profile_fingerprint=provider_profile_fingerprint,
        planned_rounds=planned_rounds,
        case_order=case_order,
        mode_order=mode_order,
        plan_sha256=plan_sha256,
        plan_document=plan_document,
    )


def _public_import_report(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if not key.startswith("_")}


def _fsync_directory(directory: Path) -> None:
    try:
        dir_fd = os.open(str(directory), os.O_RDONLY)
    except PermissionError as error:
        # Windows' CRT cannot open directory handles through os.open. This is a
        # platform capability gap, not permission to suppress arbitrary I/O errors.
        if (
            _IS_WINDOWS
            and error.errno == errno.EACCES
            and directory.is_dir()
            and not directory.is_symlink()
            # Python 3.12 reports Windows directory junctions separately from
            # symlinks. They are reparse points rather than the real directory
            # for which this narrow CRT capability exception is intended.
            and not directory.is_junction()
        ):
            return
        raise
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _write_exclusive_bytes(path: Path, content: bytes) -> str:
    """Exclusive create with file data + parent directory durability."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as target:
        target.write(content)
        target.flush()
        os.fsync(target.fileno())
    _fsync_directory(path.parent)
    return hashlib.sha256(content).hexdigest()


def _write_immutable_json(path: Path, value: object) -> str:
    return _write_exclusive_bytes(path, canonical_bytes(value))


def _atomic_write_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = canonical_bytes(value)
    digest = hashlib.sha256(content).hexdigest()
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return digest


def _mean_ratio(rows: list[dict[str, Any]], key: str) -> dict[str, object]:
    values = [row[key] for row in rows if row[key]["value"] is not None]
    if not values:
        return {"value": None, "sampleCount": 0, "notEvaluableReason": "no_evaluable_samples"}
    sample_count = sum(int(item["sampleCount"]) for item in values)
    weighted = sum(float(item["value"]) * int(item["sampleCount"]) for item in values)
    return {
        "value": weighted / sample_count,
        "sampleCount": sample_count,
        "notEvaluableReason": None,
    }


def _aggregate_mode_metrics(scored_rows: list[dict[str, Any]]) -> dict[str, Any]:
    denominator = len(scored_rows)
    quality_failures = sum(1 for row in scored_rows if row["qualityFailure"])
    engineering_failures = sum(1 for row in scored_rows if row["engineeringFailure"])
    return {
        "denominatorCaseCount": denominator,
        "qualityFailureCount": quality_failures,
        "engineeringFailureCount": engineering_failures,
        "qualityPassRate": 0.0 if quality_failures else 1.0,
        "engineeringPassRate": 0.0 if engineering_failures else 1.0,
        "unsupportedClaimCount": sum(int(row["unsupportedClaimCount"]) for row in scored_rows),
        "extraClaimCount": sum(int(row["extraClaimCount"]) for row in scored_rows),
        "negatedClaimCount": sum(int(row["negatedClaimCount"]) for row in scored_rows),
        "forbiddenAnswerCount": sum(int(row["forbiddenAnswerCount"]) for row in scored_rows),
        "claimSupportRate": _mean_ratio(scored_rows, "claimSupportRate"),
        "evidenceRecall": _mean_ratio(scored_rows, "evidenceRecall"),
        "evidencePrecision": _mean_ratio(scored_rows, "evidencePrecision"),
        "evidenceTargetExactness": _mean_ratio(scored_rows, "evidenceTargetExactness"),
        "conflictDetectionRate": _mean_ratio(scored_rows, "conflictDetectionRate"),
        "refusalCorrectness": _mean_ratio(scored_rows, "refusalCorrectness"),
    }


def _mode_semantic_gates(
    metrics: dict[str, Any],
    threshold: dict[str, Any],
) -> dict[str, Any]:
    """Campaign/round semantic gates; never copy R700 import engineeringGate."""
    primary = threshold["qualityGates"]["primaryRates"]
    forbidden = threshold["qualityGates"]["forbiddenCounts"]
    rate_failures: list[str] = []
    for key, required in primary.items():
        value = metrics[key]["value"]
        if value is None or float(value) < float(required):
            rate_failures.append(key)
    count_failures: list[str] = []
    for key, maximum in forbidden.items():
        if int(metrics[key]) > int(maximum):
            count_failures.append(key)
    engineering_fail = int(metrics["engineeringFailureCount"]) > 0
    quality_metric_fail = (
        bool(rate_failures)
        or bool(count_failures)
        or int(metrics["qualityFailureCount"]) > 0
    )
    if engineering_fail:
        engineering = "fail"
        model_quality = "not_evaluable"
        model_reason = "engineering_or_provider_failure"
        quality_pass = False
    elif quality_metric_fail:
        engineering = "pass"
        model_quality = "fail"
        model_reason = "zero_tolerance_quality_failure"
        quality_pass = False
    else:
        engineering = "pass"
        model_quality = "pass"
        model_reason = "zero_tolerance_quality_pass"
        quality_pass = True
    return {
        "engineering": engineering,
        "modelQuality": model_quality,
        "modelQualityReason": model_reason,
        "qualityPass": quality_pass,
        "engineeringPass": engineering == "pass",
        "rateFailures": rate_failures,
        "countFailures": count_failures,
        "requiredPrimaryRates": primary,
        "requiredForbiddenCounts": forbidden,
    }


def _plan_provenance_fields(plan: CampaignPlan) -> dict[str, object]:
    return {
        "packageSha256": plan.package_sha256,
        "thresholdSha256": plan.threshold_sha256,
        "planSha256": plan.plan_sha256,
        "scorerVersion": plan.scorer_version,
        "scorerImplementationSha256": plan.scorer_implementation_sha256,
        "quickPromptBindingSha256": plan.quick_prompt_binding_sha256,
        "researchPromptBindingSha256": plan.research_prompt_binding_sha256,
        "evaluatorClosureSha256": plan.evaluator_closure_sha256,
        "providerProfileFingerprint": plan.provider_profile_fingerprint,
    }


def _verify_campaign_plan_file(plan_path: Path, plan: CampaignPlan) -> None:
    if not plan_path.is_file():
        raise R803EvaluationError("missing_campaign_plan")
    existing = json.loads(plan_path.read_text(encoding="utf-8"))
    expected = plan.plan_document
    if existing != expected:
        raise R803EvaluationError("campaign_plan_mutated")
    body = {
        key: value
        for key, value in existing.items()
        if key not in {"schemaVersion", "planSha256"}
    }
    recomputed = canonical_sha256(body)
    if existing.get("planSha256") != plan.plan_sha256 or recomputed != plan.plan_sha256:
        raise R803EvaluationError("campaign_plan_hash_drift")
    companion = plan_path.parent / "campaign-plan.sha256.json"
    if not companion.is_file():
        raise R803EvaluationError("missing_campaign_plan_companion")
    companion_doc = json.loads(companion.read_text(encoding="utf-8"))
    if companion_doc.get("sha256") != file_sha256(plan_path):
        raise R803EvaluationError("campaign_plan_companion_hash_drift")


def _test_provider_attestation(
    plan: CampaignPlan,
    provider: RecordedProvider,
) -> dict[str, object]:
    profile = plan.provider_profile_fingerprint
    matches_profile = (
        provider.provider == profile["provider"] and provider.model == profile["model"]
    )
    return {
        "formalEvidence": False,
        "evidenceClass": "non_formal_test_provider",
        "provider": provider.provider,
        "model": provider.model,
        "matchesFrozenProfile": matches_profile,
        "frozenProfile": profile,
        "allowTestProvider": True,
    }


def _formal_configured_attestation(
    plan: CampaignPlan,
    provider: RecordedProvider,
) -> dict[str, object]:
    """Only the formal campaign path may call this after configured_provider()."""
    profile = plan.provider_profile_fingerprint
    matches_profile = (
        provider.provider == profile["provider"] and provider.model == profile["model"]
    )
    if not matches_profile:
        raise R803EvaluationError("provider_profile_mismatch")
    return {
        "formalEvidence": True,
        "evidenceClass": "formal_configured_provider",
        "provider": provider.provider,
        "model": provider.model,
        "matchesFrozenProfile": True,
        "frozenProfile": profile,
        "allowTestProvider": False,
    }



_SAFE_INTERRUPTION_DETAILS = frozenset(
    {
        "started_or_partial_round_not_closed",
        "round_execution_exception",
        "RuntimeError",
        "R803EvaluationError",
        "OSError",
        "ValueError",
        "TypeError",
        "KeyError",
        "FileExistsError",
        "FileNotFoundError",
        "PermissionError",
        "TimeoutError",
        "JSONDecodeError",
        "AgentResultValidationError",
        "ModelProviderError",
        "ResearchExecutionError",
        "Exception",
    }
)


def _safe_interruption_detail(reason: str, error: BaseException | None = None) -> str:
    """Store only allowlisted class/code tokens; never raw exception text."""
    if error is None:
        token = reason
        if token in _SAFE_INTERRUPTION_DETAILS:
            return token
        return "round_execution_exception"
    if type(error) is R803EvaluationError:
        return error.safe_code or "R803EvaluationError"
    if isinstance(error, R803EvaluationError):
        return "R803EvaluationError"
    name = type(error).__name__
    if name in _SAFE_INTERRUPTION_DETAILS:
        return name
    return "Exception"


def _write_round_start_marker(
    round_dir: Path,
    plan: CampaignPlan,
    *,
    round_index: int,
    attestation: dict[str, object],
) -> str:
    marker = {
        "schemaVersion": ROUND_START_SCHEMA_VERSION,
        "roundIndex": round_index,
        **_plan_provenance_fields(plan),
        "providerAttestation": attestation,
        "startedAt": datetime.now(UTC).isoformat(),
        "status": "started",
    }
    path = round_dir / "round-start.json"
    digest = _write_immutable_json(path, marker)
    _write_immutable_json(round_dir / "round-start.sha256.json", {"sha256": digest})
    return digest


def _round_is_complete(round_dir: Path) -> bool:
    return (round_dir / "SHA256SUMS").is_file() and (round_dir / "round-report.json").is_file()


def _round_is_started(round_dir: Path) -> bool:
    return (round_dir / "round-start.json").is_file() or (
        round_dir.exists() and any(round_dir.iterdir())
    )


def _partial_round_file_hashes(round_dir: Path) -> dict[str, str]:
    return {
        name: file_sha256(round_dir / name)
        for name in list_regular_files_relative(
            round_dir,
            include_checksum_manifest=True,
        )
    }


def run_campaign_round(
    plan: CampaignPlan,
    *,
    round_index: int,
    provider: RecordedProvider,
    output_dir: Path,
    baseline_evaluation_run_id: str | None = None,
    allow_test_provider: bool = False,
) -> dict[str, Any]:
    """Public low-level round API is always explicitly test-only / non-formal.

    Direct callers cannot mint formal configured attestation. Formal evidence is
    only produced by run_or_resume_campaign(provider=None) via the internal
    configured-provider path.
    """
    if not allow_test_provider:
        raise R803EvaluationError("injected_provider_requires_allow_test_provider")
    attestation = _test_provider_attestation(plan, provider)
    return _run_campaign_round_with_attestation(
        plan,
        round_index=round_index,
        provider=provider,
        output_dir=output_dir,
        baseline_evaluation_run_id=baseline_evaluation_run_id,
        attestation=attestation,
    )


def _run_campaign_round_with_attestation(
    plan: CampaignPlan,
    *,
    round_index: int,
    provider: RecordedProvider,
    output_dir: Path,
    attestation: dict[str, object],
    baseline_evaluation_run_id: str | None = None,
) -> dict[str, Any]:
    if output_dir.is_symlink():
        raise R803EvaluationError("round_symlink_forbidden:.")
    if output_dir.exists() and not output_dir.is_dir():
        raise R803EvaluationError("round_directory_invalid_state:not_directory")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise R803EvaluationError("round_directory_not_empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise R803EvaluationError("round_symlink_forbidden:.")
    # Durable start consumes the round index before the first provider call.
    _write_round_start_marker(
        output_dir,
        plan,
        round_index=round_index,
        attestation=attestation,
    )

    package = plan.package
    quick_binding = plan.quick_prompt_binding_sha256
    research_binding = plan.research_prompt_binding_sha256
    captures: list[DiagnosticCapture] = []
    diagnostics: dict[str, dict[str, OutputFailureDiagnostic | None]] = {
        "quick": {},
        "research": {},
    }
    quick_executions: list[CaseExecution] = []
    research_executions: list[CaseExecution] = []
    cases_by_id = {case["id"]: case for case in package.cases}

    quick_started = datetime.now(UTC)
    for case_id in plan.case_order:
        case = cases_by_id[case_id]
        capture = DiagnosticCapture(case_key=case_id, mode="quick")
        execution, diagnostic = run_quick_case_with_diagnostics(
            package,
            case,
            provider,
            diagnostic_capture=capture,
        )
        captures.append(capture)
        diagnostics["quick"][case_id] = diagnostic
        quick_executions.append(execution)
    quick_completed = datetime.now(UTC)

    research_started = datetime.now(UTC)
    for case_id in plan.case_order:
        case = cases_by_id[case_id]
        capture = DiagnosticCapture(case_key=case_id, mode="research")
        execution, diagnostic = run_research_case_with_diagnostics(
            package,
            case,
            provider,
            diagnostic_capture=capture,
        )
        captures.append(capture)
        diagnostics["research"][case_id] = diagnostic
        research_executions.append(execution)
    research_completed = datetime.now(UTC)

    # Preliminarily score successful-transport cases, resolve exact raw provenance for
    # scorer quality failures, then build public reports with resolved diagnostics only.
    captures_by_mode_case: dict[tuple[str, str], DiagnosticCapture] = {}
    for capture in captures:
        captures_by_mode_case[(capture.mode, capture.case_key)] = capture

    quick_by_id = {item.case_key: item for item in quick_executions}
    research_by_id = {item.case_key: item for item in research_executions}

    for case in package.cases:
        case_id = case["id"]
        for mode, execution in (
            ("quick", quick_by_id[case_id]),
            ("research", research_by_id[case_id]),
        ):
            capture = captures_by_mode_case.get((mode, case_id))
            existing = diagnostics[mode].get(case_id)
            # Runtime schema/semantic diagnostics already bound for failed executions.
            if execution.failure_code is not None:
                assert_quality_failure_diagnostic_bound(
                    mode=mode,
                    case_key=case_id,
                    score=score_case_v2(case, execution, diagnostic=existing),
                    diagnostic=existing,
                    capture=capture,
                )
                continue
            prelim = score_case_v2(case, execution, diagnostic=None)
            if not prelim.get("qualityFailure"):
                continue
            try:
                resolved = resolve_successful_quality_failure_diagnostic(
                    prelim,
                    execution,
                    capture,
                )
            except R803EvaluationError as error:
                detail = str(error)
                if detail.startswith("quality_failure_provenance_unresolved"):
                    raise R803EvaluationError(
                        f"quality_failure_provenance_unresolved:{mode}:{case_id}"
                    ) from error
                raise
            if resolved is None:
                raise R803EvaluationError(
                    f"quality_failure_provenance_unresolved:{mode}:{case_id}"
                )
            diagnostics[mode][case_id] = resolved
            assert_quality_failure_diagnostic_bound(
                mode=mode,
                case_key=case_id,
                score=prelim,
                diagnostic=resolved,
                capture=capture,
            )

    quick_report = build_import_report_v2(
        package,
        mode="quick",
        executions=tuple(quick_executions),
        created_at=quick_started,
        completed_at=quick_completed,
        prompt_binding_sha256=quick_binding,
        diagnostics=diagnostics["quick"],
    )
    research_report = build_import_report_v2(
        package,
        mode="research",
        executions=tuple(research_executions),
        created_at=research_started,
        completed_at=research_completed,
        prompt_binding_sha256=research_binding,
        diagnostics=diagnostics["research"],
        baseline_evaluation_run_id=baseline_evaluation_run_id,
    )

    quick_scores = {
        case["id"]: score_case_v2(
            case,
            next(item for item in quick_executions if item.case_key == case["id"]),
            diagnostic=diagnostics["quick"].get(case["id"]),
        )
        for case in package.cases
    }
    research_scores = {
        case["id"]: score_case_v2(
            case,
            next(item for item in research_executions if item.case_key == case["id"]),
            diagnostic=diagnostics["research"].get(case["id"]),
        )
        for case in package.cases
    }
    # Strip private scorer hints before any artifact construction.
    for scores in (quick_scores, research_scores):
        for row in scores.values():
            row.pop("_quality_failure_provenance_hints", None)

    quick_metrics = _aggregate_mode_metrics(list(quick_scores.values()))
    research_metrics = _aggregate_mode_metrics(list(research_scores.values()))
    quick_threshold = _mode_semantic_gates(quick_metrics, plan.threshold)
    research_threshold = _mode_semantic_gates(research_metrics, plan.threshold)

    # Paired v2 semantic gates: engineering failure forces modelQuality=not_evaluable.
    # R700 import engineeringGate is compatibility-only and nested separately.
    paired = {
        "schemaVersion": "r803-paired-quality-report-v2",
        "package": {
            "path": str(package.path.relative_to(package.path.parents[2])),
            "sha256": package.sha256,
            "fixtureIds": sorted(package.assets),
            "caseCount": len(package.cases),
            "thresholdSha256": plan.threshold_sha256,
            "scorerVersion": plan.scorer_version,
            "scorerImplementationSha256": plan.scorer_implementation_sha256,
            "evaluatorClosureSha256": plan.evaluator_closure_sha256,
        },
        "comparisonKeys": package.comparison_keys.as_dict(),
        "comparisonKeysMatch": True,
        "providerAttestation": attestation,
        "promptBindings": {
            "quickPromptBindingSha256": quick_binding,
            "researchPromptBindingSha256": research_binding,
        },
        "sample": {
            "pairedCaseCount": len(package.cases),
            "independentExecutionsPerCaseAndMode": 1,
            "releaseThresholdDefined": True,
            "thresholdSha256": plan.threshold_sha256,
            "campaignRoundIndex": round_index,
        },
        "gates": {
            "quickEngineering": quick_threshold["engineering"],
            "researchEngineering": research_threshold["engineering"],
            "quickModelQuality": quick_threshold["modelQuality"],
            "researchModelQuality": research_threshold["modelQuality"],
            "engineering": (
                "fail"
                if quick_threshold["engineering"] == "fail"
                or research_threshold["engineering"] == "fail"
                else "pass"
            ),
            "modelQuality": (
                "not_evaluable"
                if quick_threshold["engineering"] == "fail"
                or research_threshold["engineering"] == "fail"
                else (
                    "fail"
                    if quick_threshold["modelQuality"] == "fail"
                    or research_threshold["modelQuality"] == "fail"
                    else "pass"
                )
            ),
            "userValue": "not_evaluable",
            "userValueReason": "m404_evidence_absent",
            "productStage": "internal_preview",
        },
        "r700ImportCompatibility": {
            "note": (
                "Public R700 v1 import schema cannot express campaign gate separation. "
                "Its engineeringGate collapses model semantic failures into engineering=fail "
                "and keeps modelQualityGate=not_evaluable. Campaign semantic gates above are authoritative."
            ),
            "quickEngineeringGate": quick_report["evaluation"]["engineeringGate"],
            "researchEngineeringGate": research_report["evaluation"]["engineeringGate"],
            "quickModelQualityGate": quick_report["evaluation"]["modelQualityGate"],
            "researchModelQualityGate": research_report["evaluation"]["modelQualityGate"],
        },
        "aggregate": {
            "quick": quick_metrics,
            "research": research_metrics,
            "quickWallTimeMs": quick_report["evaluation"]["wallTimeMs"],
            "researchWallTimeMs": research_report["evaluation"]["wallTimeMs"],
            "quickProviderCalls": quick_report["evaluation"]["providerCalls"],
            "researchProviderCalls": research_report["evaluation"]["providerCalls"],
            "quickCost": quick_report["evaluation"]["cost"],
            "researchCost": research_report["evaluation"]["cost"],
            "researchParallelSpeedup": research_report["evaluation"]["parallelSpeedup"],
        },
        "cases": [
            {
                "caseKey": case["id"],
                "quick": {
                    **_case_artifact(
                        next(item for item in quick_executions if item.case_key == case["id"]),
                        {
                            **quick_scores[case["id"]],
                            "locatorAccuracy": quick_scores[case["id"]]["locatorAccuracy"],
                        },
                    ),
                    "score": {
                        key: quick_scores[case["id"]][key]
                        for key in (
                            "claimSupportRate",
                            "evidenceRecall",
                            "evidencePrecision",
                            "evidenceTargetExactness",
                            "locatorAccuracy",
                            "conflictDetectionRate",
                            "refusalCorrectness",
                        )
                    },
                    "diagnostic": quick_scores[case["id"]]["diagnostic"],
                    "qualityFailure": quick_scores[case["id"]]["qualityFailure"],
                    "engineeringFailure": quick_scores[case["id"]]["engineeringFailure"],
                    "extraClaimCount": quick_scores[case["id"]]["extraClaimCount"],
                    "negatedClaimCount": quick_scores[case["id"]]["negatedClaimCount"],
                    "forbiddenAnswerCount": quick_scores[case["id"]]["forbiddenAnswerCount"],
                },
                "research": {
                    **_case_artifact(
                        next(item for item in research_executions if item.case_key == case["id"]),
                        {
                            **research_scores[case["id"]],
                            "locatorAccuracy": research_scores[case["id"]]["locatorAccuracy"],
                        },
                    ),
                    "score": {
                        key: research_scores[case["id"]][key]
                        for key in (
                            "claimSupportRate",
                            "evidenceRecall",
                            "evidencePrecision",
                            "evidenceTargetExactness",
                            "locatorAccuracy",
                            "conflictDetectionRate",
                            "refusalCorrectness",
                        )
                    },
                    "diagnostic": research_scores[case["id"]]["diagnostic"],
                    "qualityFailure": research_scores[case["id"]]["qualityFailure"],
                    "engineeringFailure": research_scores[case["id"]]["engineeringFailure"],
                    "extraClaimCount": research_scores[case["id"]]["extraClaimCount"],
                    "negatedClaimCount": research_scores[case["id"]]["negatedClaimCount"],
                    "forbiddenAnswerCount": research_scores[case["id"]]["forbiddenAnswerCount"],
                },
            }
            for case in package.cases
        ],
    }

    # Single-pass evidence graph:
    # leaf artifacts -> round-report -> round-manifest -> SHA256SUMS (not self)
    leaf_hashes: dict[str, str] = {}
    leaf_hashes["round-start.json"] = file_sha256(output_dir / "round-start.json")
    leaf_hashes["round-start.sha256.json"] = file_sha256(output_dir / "round-start.sha256.json")
    leaf_hashes["quick-evaluation.json"] = _write_immutable_json(
        output_dir / "quick-evaluation.json",
        _public_import_report(quick_report),
    )
    leaf_hashes["research-evaluation.json"] = _write_immutable_json(
        output_dir / "research-evaluation.json",
        _public_import_report(research_report),
    )
    leaf_hashes["paired-quality-report.json"] = _write_immutable_json(
        output_dir / "paired-quality-report.json",
        paired,
    )
    raw_hashes = write_raw_output_bundle(output_dir, captures)
    leaf_hashes.update(raw_hashes)
    for relative in raw_hashes:
        if relative.endswith(".txt"):
            text = (output_dir / relative).read_text(encoding="utf-8")
            if text and secret_scan_text(text):
                raise R803EvaluationError(f"secret_material_in_raw_output:{relative}")

    engineering_fail = (
        quick_threshold["engineering"] == "fail" or research_threshold["engineering"] == "fail"
    )
    if engineering_fail:
        model_quality = "not_evaluable"
    elif quick_threshold["modelQuality"] == "fail" or research_threshold["modelQuality"] == "fail":
        model_quality = "fail"
    else:
        model_quality = "pass"
    quality_fail = model_quality == "fail"

    round_report = {
        "schemaVersion": ROUND_SCHEMA_VERSION,
        "roundIndex": round_index,
        **_plan_provenance_fields(plan),
        "providerAttestation": attestation,
        "leafArtifactHashes": dict(sorted(leaf_hashes.items())),
        "gates": {
            "quickEngineering": quick_threshold["engineering"],
            "researchEngineering": research_threshold["engineering"],
            "quickModelQuality": quick_threshold["modelQuality"],
            "researchModelQuality": research_threshold["modelQuality"],
            "engineering": "fail" if engineering_fail else "pass",
            "modelQuality": model_quality,
            "userValue": "not_evaluable",
            "productStage": "internal_preview",
        },
        "thresholdEvaluation": {
            "quick": quick_threshold,
            "research": research_threshold,
        },
        "stop": {
            "qualityFailure": quality_fail,
            "engineeringFailure": engineering_fail,
            "freezeCampaign": quality_fail or engineering_fail,
        },
        "metrics": {
            "quick": quick_metrics,
            "research": research_metrics,
        },
        "cost": {
            "quick": quick_report["evaluation"]["cost"],
            "research": research_report["evaluation"]["cost"],
        },
        "usage": {
            "quickProviderCalls": quick_report["evaluation"]["providerCalls"],
            "researchProviderCalls": research_report["evaluation"]["providerCalls"],
            "quickInputTokens": quick_report["evaluation"]["inputTokens"],
            "quickOutputTokens": quick_report["evaluation"]["outputTokens"],
            "researchInputTokens": research_report["evaluation"]["inputTokens"],
            "researchOutputTokens": research_report["evaluation"]["outputTokens"],
            "quickWallTimeMs": quick_report["evaluation"]["wallTimeMs"],
            "researchWallTimeMs": research_report["evaluation"]["wallTimeMs"],
        },
    }
    round_report_sha256 = _write_immutable_json(output_dir / "round-report.json", round_report)

    round_manifest = {
        "schemaVersion": ROUND_MANIFEST_SCHEMA_VERSION,
        "roundIndex": round_index,
        **_plan_provenance_fields(plan),
        "roundReportSha256": round_report_sha256,
        "leafArtifactHashes": dict(sorted(leaf_hashes.items())),
        "artifactHashes": dict(
            sorted(
                {
                    **leaf_hashes,
                    "round-report.json": round_report_sha256,
                }.items()
            )
        ),
    }
    round_manifest_sha256 = _write_immutable_json(output_dir / "round-manifest.json", round_manifest)

    all_hashes = {
        **leaf_hashes,
        "round-report.json": round_report_sha256,
        "round-manifest.json": round_manifest_sha256,
    }
    write_checksums(output_dir, all_hashes)

    return {
        "roundReport": {
            **round_report,
            "roundReportSha256": round_report_sha256,
            "roundManifestSha256": round_manifest_sha256,
        },
        "hashes": all_hashes,
        "quickReport": quick_report,
        "researchReport": research_report,
        "pairedReport": paired,
    }


def _load_existing_round(round_dir: Path, plan: CampaignPlan, round_index: int) -> dict[str, Any]:
    hashes = verify_checksums_exact(round_dir)
    required = {
        "quick-evaluation.json",
        "research-evaluation.json",
        "paired-quality-report.json",
        "round-report.json",
        "round-manifest.json",
        "round-start.json",
        "round-start.sha256.json",
        "raw-outputs/manifest.json",
    }
    missing = sorted(name for name in required if name not in hashes)
    if missing:
        raise R803EvaluationError(f"missing_round_artifacts:{','.join(missing)}")

    manifest = json.loads((round_dir / "round-manifest.json").read_text(encoding="utf-8"))
    report = json.loads((round_dir / "round-report.json").read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != ROUND_MANIFEST_SCHEMA_VERSION:
        raise R803EvaluationError("unsupported_round_manifest_schema")
    if report.get("schemaVersion") != ROUND_SCHEMA_VERSION:
        raise R803EvaluationError("unsupported_round_report_schema")
    if manifest.get("roundIndex") != round_index or report.get("roundIndex") != round_index:
        raise R803EvaluationError("round_index_mismatch")
    if hashes["round-report.json"] != manifest.get("roundReportSha256"):
        raise R803EvaluationError("round_report_hash_drift")
    if report.get("leafArtifactHashes") != manifest.get("leafArtifactHashes"):
        raise R803EvaluationError("round_leaf_hash_set_mismatch")
    for name, digest in report.get("leafArtifactHashes", {}).items():
        if hashes.get(name) != digest:
            raise R803EvaluationError(f"round_leaf_hash_drift:{name}")
    for name, digest in manifest.get("artifactHashes", {}).items():
        if name == "round-manifest.json":
            continue
        if hashes.get(name) != digest:
            raise R803EvaluationError(f"round_manifest_artifact_drift:{name}")
    for source in (report, manifest):
        if (
            source.get("packageSha256") != plan.package_sha256
            or source.get("thresholdSha256") != plan.threshold_sha256
            or source.get("planSha256") != plan.plan_sha256
            or source.get("scorerVersion") != plan.scorer_version
            or source.get("scorerImplementationSha256") != plan.scorer_implementation_sha256
            or source.get("quickPromptBindingSha256") != plan.quick_prompt_binding_sha256
            or source.get("researchPromptBindingSha256") != plan.research_prompt_binding_sha256
            or source.get("evaluatorClosureSha256") != plan.evaluator_closure_sha256
        ):
            raise R803EvaluationError("round_plan_hash_drift")
    return {
        **report,
        "roundReportSha256": hashes["round-report.json"],
        "roundManifestSha256": hashes["round-manifest.json"],
        "checksumTargets": hashes,
    }


def _fold_mode_metrics(rounds: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    rows = [item["metrics"][mode] for item in rounds]
    if not rows:
        return {
            "denominatorCaseCount": 0,
            "qualityFailureCount": 0,
            "engineeringFailureCount": 0,
            "qualityPassRate": None,
            "engineeringPassRate": None,
            "unsupportedClaimCount": 0,
            "extraClaimCount": 0,
            "negatedClaimCount": 0,
            "forbiddenAnswerCount": 0,
            "claimSupportRate": {"value": None, "sampleCount": 0, "notEvaluableReason": "no_rounds"},
            "evidenceRecall": {"value": None, "sampleCount": 0, "notEvaluableReason": "no_rounds"},
            "evidencePrecision": {
                "value": None,
                "sampleCount": 0,
                "notEvaluableReason": "no_rounds",
            },
            "evidenceTargetExactness": {
                "value": None,
                "sampleCount": 0,
                "notEvaluableReason": "no_rounds",
            },
            "conflictDetectionRate": {
                "value": None,
                "sampleCount": 0,
                "notEvaluableReason": "no_rounds",
            },
            "refusalCorrectness": {
                "value": None,
                "sampleCount": 0,
                "notEvaluableReason": "no_rounds",
            },
        }
    denominator = sum(int(row["denominatorCaseCount"]) for row in rows)
    quality_failures = sum(int(row["qualityFailureCount"]) for row in rows)
    engineering_failures = sum(int(row["engineeringFailureCount"]) for row in rows)
    return {
        "denominatorCaseCount": denominator,
        "qualityFailureCount": quality_failures,
        "engineeringFailureCount": engineering_failures,
        "qualityPassRate": 0.0 if quality_failures else 1.0,
        "engineeringPassRate": 0.0 if engineering_failures else 1.0,
        "unsupportedClaimCount": sum(int(row["unsupportedClaimCount"]) for row in rows),
        "extraClaimCount": sum(int(row["extraClaimCount"]) for row in rows),
        "negatedClaimCount": sum(int(row["negatedClaimCount"]) for row in rows),
        "forbiddenAnswerCount": sum(int(row["forbiddenAnswerCount"]) for row in rows),
        "claimSupportRate": _mean_ratio(rows, "claimSupportRate"),
        "evidenceRecall": _mean_ratio(rows, "evidenceRecall"),
        "evidencePrecision": _mean_ratio(rows, "evidencePrecision"),
        "evidenceTargetExactness": _mean_ratio(rows, "evidenceTargetExactness"),
        "conflictDetectionRate": _mean_ratio(rows, "conflictDetectionRate"),
        "refusalCorrectness": _mean_ratio(rows, "refusalCorrectness"),
    }


def build_campaign_report(
    plan: CampaignPlan,
    *,
    campaign_dir: Path,
    rounds: list[dict[str, Any]],
    interruption: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if len(rounds) > plan.planned_rounds:
        raise R803EvaluationError("too_many_rounds")
    quality_failed = any(item["gates"]["modelQuality"] == "fail" for item in rounds)
    engineering_failed = any(item["gates"]["engineering"] == "fail" for item in rounds)
    complete = len(rounds) == plan.planned_rounds and interruption is None
    quick_metrics = _fold_mode_metrics(rounds, "quick")
    research_metrics = _fold_mode_metrics(rounds, "research")
    quick_threshold = _mode_semantic_gates(quick_metrics, plan.threshold) if rounds else None
    research_threshold = (
        _mode_semantic_gates(research_metrics, plan.threshold) if rounds else None
    )
    if rounds:
        if quick_threshold["modelQuality"] == "fail" or research_threshold["modelQuality"] == "fail":
            quality_failed = True
        if (
            quick_threshold["engineering"] == "fail"
            or research_threshold["engineering"] == "fail"
        ):
            engineering_failed = True
    if interruption is not None:
        engineering_failed = True

    if engineering_failed:
        model_quality = "not_evaluable"
        model_reason = (
            "campaign_interrupted"
            if interruption is not None
            else "engineering_or_provider_failure"
        )
        engineering = "fail"
        status = "failed"
    elif quality_failed:
        model_quality = "fail"
        model_reason = "zero_tolerance_quality_failure"
        engineering = "pass"
        status = "failed"
    elif complete:
        model_quality = "pass"
        model_reason = "five_round_zero_tolerance_pass"
        engineering = "pass"
        status = "completed"
    else:
        model_quality = "not_evaluable"
        model_reason = "campaign_incomplete"
        engineering = "pass" if rounds else "not_evaluable"
        status = "running"

    formal_evidence = all(
        (item.get("providerAttestation") or {}).get("formalEvidence", True) for item in rounds
    ) and interruption is None

    return {
        "schemaVersion": CAMPAIGN_SCHEMA_VERSION,
        "status": status,
        "package": {
            "path": str(plan.package.path.relative_to(plan.package.path.parents[2])),
            "sha256": plan.package_sha256,
            "thresholdSha256": plan.threshold_sha256,
            "planSha256": plan.plan_sha256,
            "scorerVersion": plan.scorer_version,
            "scorerImplementationSha256": plan.scorer_implementation_sha256,
            "quickPromptBindingSha256": plan.quick_prompt_binding_sha256,
            "researchPromptBindingSha256": plan.research_prompt_binding_sha256,
            "evaluatorClosureSha256": plan.evaluator_closure_sha256,
            "providerProfileFingerprint": plan.provider_profile_fingerprint,
        },
        "sample": {
            "plannedRounds": plan.planned_rounds,
            "completedRounds": len(rounds),
            "totalCaseExecutionsPlanned": plan.planned_rounds * len(plan.case_order) * 2,
            "totalCaseExecutionsCompleted": len(rounds) * len(plan.case_order) * 2,
            "independentJudgmentPerMode": True,
            "automaticWinnerSelection": False,
            "formalCampaignStatus": status,
            "formalEvidence": formal_evidence and status in {"completed", "failed"},
        },
        "gates": {
            "engineering": engineering,
            "modelQuality": model_quality,
            "modelQualityReason": model_reason,
            "userValue": "not_evaluable",
            "userValueReason": "m404_evidence_absent",
            "productStage": "internal_preview",
            "quick": quick_metrics,
            "research": research_metrics,
            "thresholdEvaluation": {
                "quick": quick_threshold,
                "research": research_threshold,
            },
        },
        "rounds": [
            {
                "roundIndex": item["roundIndex"],
                "roundReportSha256": item.get("roundReportSha256"),
                "roundManifestSha256": item.get("roundManifestSha256"),
                "gates": item["gates"],
                "metrics": item["metrics"],
                "cost": item["cost"],
                "usage": item["usage"],
                "thresholdEvaluation": item.get("thresholdEvaluation"),
                "providerAttestation": item.get("providerAttestation"),
            }
            for item in rounds
        ],
        "interruption": interruption,
        "claimBoundary": plan.threshold["claimBoundary"],
        "observationsOnly": plan.threshold["observationsOnly"],
        "budgetEstimate": plan.threshold["budgetEstimate"],
        "campaignDir": str(campaign_dir),
    }


def _write_progress_snapshot(campaign_dir: Path, report: dict[str, Any]) -> None:
    progress = {
        "schemaVersion": PROGRESS_SCHEMA_VERSION,
        "mutable": True,
        "status": report["status"],
        "sample": report["sample"],
        "gates": {
            "engineering": report["gates"]["engineering"],
            "modelQuality": report["gates"]["modelQuality"],
            "modelQualityReason": report["gates"]["modelQualityReason"],
            "userValue": report["gates"]["userValue"],
            "productStage": report["gates"]["productStage"],
        },
        "completedRoundIndexes": [item["roundIndex"] for item in report["rounds"]],
        "updatedAt": datetime.now(UTC).isoformat(),
    }
    _atomic_write_json(campaign_dir / "campaign-progress.json", progress)


def _supersede_progress_if_present(campaign_dir: Path, terminal_digest: str) -> None:
    progress_path = campaign_dir / "campaign-progress.json"
    if not progress_path.exists():
        return
    existing = json.loads(progress_path.read_text(encoding="utf-8"))
    superseded = {
        **existing,
        "mutable": False,
        "supersededBy": "campaign-report.json",
        "supersededBySha256": terminal_digest,
        "supersededAt": datetime.now(UTC).isoformat(),
        "status": "superseded",
    }
    _atomic_write_json(progress_path, superseded)


def _write_terminal_campaign_report(campaign_dir: Path, report: dict[str, Any]) -> str:
    if report["status"] not in {"completed", "failed"}:
        raise R803EvaluationError("campaign_report_requires_terminal_status")
    report_path = campaign_dir / "campaign-report.json"
    digest = _write_immutable_json(report_path, report)
    companion_path = campaign_dir / "campaign-report.sha256.json"
    if not companion_path.exists():
        _write_immutable_json(companion_path, {"sha256": digest})
    else:
        existing = json.loads(companion_path.read_text(encoding="utf-8"))
        if existing.get("sha256") != digest:
            raise R803EvaluationError("campaign_report_companion_conflict")
    _supersede_progress_if_present(campaign_dir, digest)
    return digest



def _verify_partial_interrupted_round(
    round_dir: Path,
    plan: CampaignPlan,
    *,
    round_index: int,
    interruption: dict[str, Any],
) -> None:
    if int(interruption.get("roundIndex", -1)) != round_index:
        raise R803EvaluationError("interruption_round_index_mismatch")
    if not round_dir.is_dir() or not any(round_dir.iterdir()):
        raise R803EvaluationError(f"terminal_missing_partial_round:{round_index}")
    if _round_is_complete(round_dir):
        raise R803EvaluationError(f"terminal_partial_round_unexpectedly_complete:{round_index}")
    start_path = round_dir / "round-start.json"
    companion = round_dir / "round-start.sha256.json"
    if not start_path.is_file():
        raise R803EvaluationError(f"terminal_partial_missing_round_start:{round_index}")
    if not companion.is_file():
        raise R803EvaluationError(f"terminal_partial_missing_round_start_companion:{round_index}")
    start = json.loads(start_path.read_text(encoding="utf-8"))
    if start.get("schemaVersion") != ROUND_START_SCHEMA_VERSION:
        raise R803EvaluationError("unsupported_round_start_schema")
    if int(start.get("roundIndex", -1)) != round_index:
        raise R803EvaluationError("partial_round_start_index_mismatch")
    if (
        start.get("packageSha256") != plan.package_sha256
        or start.get("thresholdSha256") != plan.threshold_sha256
        or start.get("planSha256") != plan.plan_sha256
        or start.get("scorerVersion") != plan.scorer_version
        or start.get("scorerImplementationSha256") != plan.scorer_implementation_sha256
        or start.get("quickPromptBindingSha256") != plan.quick_prompt_binding_sha256
        or start.get("researchPromptBindingSha256") != plan.research_prompt_binding_sha256
        or start.get("evaluatorClosureSha256") != plan.evaluator_closure_sha256
    ):
        raise R803EvaluationError("partial_round_start_plan_hash_drift")
    companion_doc = json.loads(companion.read_text(encoding="utf-8"))
    if companion_doc.get("sha256") != file_sha256(start_path):
        raise R803EvaluationError("partial_round_start_companion_hash_drift")

    stored_hashes = interruption.get("partialRoundFileHashes")
    if not isinstance(stored_hashes, dict) or not stored_hashes:
        raise R803EvaluationError("interruption_partial_file_hashes_missing")
    if not all(
        isinstance(name, str)
        and isinstance(digest, str)
        and len(digest) == 64
        for name, digest in stored_hashes.items()
    ):
        raise R803EvaluationError("interruption_partial_file_hashes_invalid")
    actual_hashes = _partial_round_file_hashes(round_dir)
    if set(actual_hashes) != set(stored_hashes):
        raise R803EvaluationError("partial_round_file_set_drift")
    for name, digest in actual_hashes.items():
        if stored_hashes.get(name) != digest:
            raise R803EvaluationError(f"partial_round_file_hash_drift:{name}")
    closure_sha256 = canonical_sha256(actual_hashes)
    if interruption.get("partialRoundClosureSha256") != closure_sha256:
        raise R803EvaluationError("partial_round_closure_hash_drift")

    # Interruption provenance must match the frozen plan.
    for key in (
        "packageSha256",
        "thresholdSha256",
        "planSha256",
        "scorerVersion",
        "scorerImplementationSha256",
        "quickPromptBindingSha256",
        "researchPromptBindingSha256",
        "evaluatorClosureSha256",
    ):
        expected = {
            "packageSha256": plan.package_sha256,
            "thresholdSha256": plan.threshold_sha256,
            "planSha256": plan.plan_sha256,
            "scorerVersion": plan.scorer_version,
            "scorerImplementationSha256": plan.scorer_implementation_sha256,
            "quickPromptBindingSha256": plan.quick_prompt_binding_sha256,
            "researchPromptBindingSha256": plan.research_prompt_binding_sha256,
            "evaluatorClosureSha256": plan.evaluator_closure_sha256,
        }[key]
        if interruption.get(key) != expected:
            raise R803EvaluationError(f"interruption_plan_hash_drift:{key}")
    if interruption.get("partialRoundPreserved") is not True:
        raise R803EvaluationError("interruption_partial_not_preserved")


def _recompute_and_verify_terminal(
    campaign_dir: Path,
    plan: CampaignPlan,
    stored: dict[str, Any],
) -> dict[str, Any]:
    companion = campaign_dir / "campaign-report.sha256.json"
    if not companion.is_file():
        raise R803EvaluationError("missing_campaign_report_companion")
    companion_doc = json.loads(companion.read_text(encoding="utf-8"))
    report_path = campaign_dir / "campaign-report.json"
    if companion_doc.get("sha256") != file_sha256(report_path):
        raise R803EvaluationError("campaign_report_companion_hash_drift")

    claimed = int(stored.get("sample", {}).get("completedRounds", -1))
    if claimed < 0:
        raise R803EvaluationError("campaign_report_completed_rounds_invalid")

    interruption = stored.get("interruption")
    allowed_partial: int | None = None
    if interruption is not None:
        if not isinstance(interruption, dict):
            raise R803EvaluationError("invalid_interruption_record")
        allowed_partial = int(interruption.get("roundIndex", -1))
        if allowed_partial < 1 or allowed_partial > plan.planned_rounds:
            raise R803EvaluationError("interruption_round_index_invalid")
        if allowed_partial != claimed + 1:
            raise R803EvaluationError("interruption_round_not_contiguous")

    # Validate the full global inventory first so out-of-range/malformed
    # nonempty directories (e.g. round-06) reject terminal resume.
    discovered = _validate_round_inventory(campaign_dir, plan)
    expected_indexes = list(range(1, claimed + 1))
    if allowed_partial is not None:
        expected_indexes.append(allowed_partial)
    actual_indexes = [index for index, _path in discovered]
    if actual_indexes != expected_indexes:
        unexpected = [index for index in actual_indexes if index not in expected_indexes]
        if unexpected:
            raise R803EvaluationError(
                f"terminal_extra_round_directory:{unexpected[0]}"
            )
        missing = [index for index in expected_indexes if index not in actual_indexes]
        if missing:
            raise R803EvaluationError(f"terminal_missing_round:{missing[0]}")
        raise R803EvaluationError("terminal_round_inventory_mismatch")

    rounds: list[dict[str, Any]] = []
    for round_index in range(1, claimed + 1):
        round_dir = campaign_dir / f"round-{round_index:02d}"
        if not round_dir.exists():
            raise R803EvaluationError(f"terminal_missing_round:{round_index}")
        rounds.append(_load_existing_round(round_dir, plan, round_index))

    if allowed_partial is not None:
        assert interruption is not None  # for type checkers
        partial_dir = campaign_dir / f"round-{allowed_partial:02d}"
        _verify_partial_interrupted_round(
            partial_dir,
            plan,
            round_index=allowed_partial,
            interruption=interruption,
        )

    recomputed = build_campaign_report(
        plan,
        campaign_dir=campaign_dir,
        rounds=rounds,
        interruption=interruption,
    )
    # Canonical equality against stored terminal report body.
    if recomputed != stored:
        raise R803EvaluationError("campaign_report_recompute_mismatch")
    if len(stored.get("rounds", [])) != claimed:
        raise R803EvaluationError("campaign_report_round_entry_count_mismatch")
    for index, item in enumerate(stored.get("rounds", []), start=1):
        if item.get("roundIndex") != index:
            raise R803EvaluationError("campaign_report_round_entry_order_mismatch")
        if item.get("roundReportSha256") != rounds[index - 1].get("roundReportSha256"):
            raise R803EvaluationError("campaign_report_round_hash_mismatch")
    return stored


def _load_terminal_campaign_report(campaign_dir: Path, plan: CampaignPlan) -> dict[str, Any] | None:
    report_path = campaign_dir / "campaign-report.json"
    if not report_path.is_file():
        return None
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("schemaVersion") != CAMPAIGN_SCHEMA_VERSION:
        raise R803EvaluationError("unsupported_campaign_report_schema")
    if report.get("status") not in {"completed", "failed"}:
        raise R803EvaluationError("campaign_report_not_terminal")
    package = report.get("package") or {}
    if (
        package.get("sha256") != plan.package_sha256
        or package.get("thresholdSha256") != plan.threshold_sha256
        or package.get("planSha256") != plan.plan_sha256
        or package.get("scorerVersion") != plan.scorer_version
        or package.get("scorerImplementationSha256") != plan.scorer_implementation_sha256
        or package.get("quickPromptBindingSha256") != plan.quick_prompt_binding_sha256
        or package.get("researchPromptBindingSha256") != plan.research_prompt_binding_sha256
        or package.get("evaluatorClosureSha256") != plan.evaluator_closure_sha256
    ):
        raise R803EvaluationError("campaign_report_plan_hash_drift")
    return _recompute_and_verify_terminal(campaign_dir, plan, report)


def _freeze_interruption(
    campaign_dir: Path,
    plan: CampaignPlan,
    rounds: list[dict[str, Any]],
    *,
    round_index: int,
    reason: str,
    detail: str,
    error: BaseException | None = None,
) -> dict[str, Any]:
    safe_detail = _safe_interruption_detail(detail if error is None else reason, error)
    partial_dir = campaign_dir / f"round-{round_index:02d}"
    partial_hashes = _partial_round_file_hashes(partial_dir)
    interruption = {
        "roundIndex": round_index,
        "reason": reason,
        "detail": safe_detail,
        "partialRoundPreserved": True,
        "partialRoundFileHashes": partial_hashes,
        "partialRoundClosureSha256": canonical_sha256(partial_hashes),
        "packageSha256": plan.package_sha256,
        "thresholdSha256": plan.threshold_sha256,
        "planSha256": plan.plan_sha256,
        "scorerVersion": plan.scorer_version,
        "scorerImplementationSha256": plan.scorer_implementation_sha256,
        "quickPromptBindingSha256": plan.quick_prompt_binding_sha256,
        "researchPromptBindingSha256": plan.research_prompt_binding_sha256,
        "evaluatorClosureSha256": plan.evaluator_closure_sha256,
        "recordedAt": datetime.now(UTC).isoformat(),
    }
    # Fail closed before minting terminal evidence: existing incomplete rounds must
    # already carry a plan-matching start marker + companion. Exception-path freezes
    # after run_campaign_round wrote the marker; resume freezes of pre-existing
    # partials must not emit a terminal that only fails on next resume.
    _verify_partial_interrupted_round(
        partial_dir,
        plan,
        round_index=round_index,
        interruption=interruption,
    )
    report = build_campaign_report(
        plan,
        campaign_dir=campaign_dir,
        rounds=rounds,
        interruption=interruption,
    )
    _write_terminal_campaign_report(campaign_dir, report)
    return report


_ROUND_DIR_RE = re.compile(r"^round-(\d{2})$")


def _discover_nonempty_round_dirs(campaign_dir: Path) -> list[tuple[int, Path]]:
    """Return sorted nonempty round directories; reject malformed/out-of-band names.

    Any round-* entry that is a symlink or not a real directory is rejected,
    including empty symlink roots.
    """
    found: list[tuple[int, Path]] = []
    if not campaign_dir.exists():
        return found
    for entry in sorted(campaign_dir.iterdir(), key=lambda item: item.name):
        if not entry.name.startswith("round-"):
            continue
        match = _ROUND_DIR_RE.fullmatch(entry.name)
        if match is None:
            raise R803EvaluationError(f"malformed_round_directory:{entry.name}")
        if entry.is_symlink():
            raise R803EvaluationError(f"round_symlink_forbidden:{entry.name}")
        if not entry.is_dir():
            raise R803EvaluationError(f"round_directory_invalid_state:{entry.name}")
        # Empty real directories are ignored; empty/nonempty symlink already rejected.
        if not any(entry.iterdir()):
            continue
        index = int(match.group(1))
        found.append((index, entry))
    return found


def _validate_round_inventory(
    campaign_dir: Path,
    plan: CampaignPlan,
) -> list[tuple[int, Path]]:
    """Validate all nonempty round-* directories before resume/freeze/provider work."""
    discovered = _discover_nonempty_round_dirs(campaign_dir)
    for index, _path in discovered:
        if index < 1 or index > plan.planned_rounds:
            raise R803EvaluationError(f"round_index_out_of_range:{index}")
    if not discovered:
        return []
    indexes = [index for index, _path in discovered]
    expected = list(range(1, max(indexes) + 1))
    if indexes != expected:
        missing = sorted(set(expected) - set(indexes))
        if missing:
            raise R803EvaluationError(
                f"round_order_violation:gap_before_{missing[0]}"
            )
        raise R803EvaluationError("round_order_violation")
    return discovered


def _scan_existing_rounds(
    campaign_dir: Path,
    plan: CampaignPlan,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Load contiguous complete rounds; freeze on incomplete started round.

    Global nonempty round inventory is validated first so gaps, out-of-range
    directories (e.g. round-06), and post-partial leftovers are rejected before
    any interruption freeze or provider configuration.
    """
    discovered = _validate_round_inventory(campaign_dir, plan)
    rounds: list[dict[str, Any]] = []
    for position, (round_index, round_dir) in enumerate(discovered):
        if _round_is_complete(round_dir):
            report = _load_existing_round(round_dir, plan, round_index)
            rounds.append(report)
            if report["stop"]["freezeCampaign"]:
                # No nonempty later rounds after a freeze (inventory already contiguous,
                # so any later entry is a violation).
                if position + 1 < len(discovered):
                    later_index = discovered[position + 1][0]
                    raise R803EvaluationError(
                        f"round_order_violation:after_freeze_{later_index}"
                    )
                break
            continue
        # Started but incomplete: freeze terminal engineering fail; never reuse.
        if _round_is_started(round_dir):
            if position + 1 < len(discovered):
                later_index = discovered[position + 1][0]
                raise R803EvaluationError(
                    f"round_order_violation:after_partial_{later_index}"
                )
            return rounds, {
                "roundIndex": round_index,
                "reason": "round_incomplete",
                "detail": "started_or_partial_round_not_closed",
            }
        raise R803EvaluationError(f"round_directory_invalid_state:{round_index}")
    return rounds, None


def run_or_resume_campaign(
    *,
    campaign_dir: Path,
    provider: RecordedProvider | None = None,
    package: EvaluationPackage | None = None,
    max_new_rounds: int | None = None,
    baseline_evaluation_run_id: str | None = None,
    allow_test_provider: bool = False,
) -> dict[str, Any]:
    if max_new_rounds is not None and max_new_rounds < 0:
        raise R803EvaluationError("max_new_rounds_must_be_non_negative")

    plan = freeze_campaign_plan(package)
    campaign_dir.mkdir(parents=True, exist_ok=True)
    plan_path = campaign_dir / "campaign-plan.json"
    if plan_path.exists():
        _verify_campaign_plan_file(plan_path, plan)
    else:
        digest = _write_immutable_json(plan_path, plan.plan_document)
        _write_immutable_json(campaign_dir / "campaign-plan.sha256.json", {"sha256": digest})

    terminal = _load_terminal_campaign_report(campaign_dir, plan)
    if terminal is not None:
        return terminal

    # Verify existing evidence first; do not configure/instantiate a provider yet.
    rounds, incomplete = _scan_existing_rounds(campaign_dir, plan)
    if incomplete is not None:
        return _freeze_interruption(
            campaign_dir,
            plan,
            rounds,
            round_index=int(incomplete["roundIndex"]),
            reason=str(incomplete["reason"]),
            detail=str(incomplete["detail"]),
        )

    campaign_report = build_campaign_report(plan, campaign_dir=campaign_dir, rounds=rounds)
    if campaign_report["status"] in {"completed", "failed"}:
        _write_terminal_campaign_report(campaign_dir, campaign_report)
        return campaign_report

    remaining_new = plan.planned_rounds if max_new_rounds is None else max_new_rounds
    if remaining_new == 0 or (rounds and rounds[-1]["stop"]["freezeCampaign"]):
        _write_progress_snapshot(campaign_dir, campaign_report)
        return campaign_report

    # Provider only immediately before a new formal/test round.
    # Formal evidence: only provider=None may call configured_provider().
    # Any explicit provider argument requires allow_test_provider=True and is non-formal.
    if provider is not None:
        if not allow_test_provider:
            raise R803EvaluationError("injected_provider_requires_allow_test_provider")
        active_provider = provider
        formal_attestation = None
    else:
        if allow_test_provider:
            raise R803EvaluationError("allow_test_provider_requires_injected_provider")
        active_provider = configured_provider(plan.package)
        formal_attestation = _formal_configured_attestation(plan, active_provider)

    next_round_index = len(rounds) + 1
    while next_round_index <= plan.planned_rounds and remaining_new > 0:
        if rounds and rounds[-1]["stop"]["freezeCampaign"]:
            break
        # Re-validate inventory each iteration before any new work.
        _validate_round_inventory(campaign_dir, plan)
        for later in range(next_round_index + 1, plan.planned_rounds + 1):
            later_dir = campaign_dir / f"round-{later:02d}"
            if later_dir.exists() and any(later_dir.iterdir()):
                raise R803EvaluationError("round_order_violation")
        round_dir = campaign_dir / f"round-{next_round_index:02d}"
        try:
            if formal_attestation is not None:
                result = _run_campaign_round_with_attestation(
                    plan,
                    round_index=next_round_index,
                    provider=active_provider,
                    output_dir=round_dir,
                    baseline_evaluation_run_id=baseline_evaluation_run_id,
                    attestation=formal_attestation,
                )
            else:
                result = run_campaign_round(
                    plan,
                    round_index=next_round_index,
                    provider=active_provider,
                    output_dir=round_dir,
                    baseline_evaluation_run_id=baseline_evaluation_run_id,
                    allow_test_provider=True,
                )
        except Exception as error:  # noqa: BLE001 - freeze incomplete formal round
            # Do not delete/replace the partial round; freeze terminal engineering fail.
            return _freeze_interruption(
                campaign_dir,
                plan,
                rounds,
                round_index=next_round_index,
                reason="round_execution_exception",
                detail="round_execution_exception",
                error=error,
            )
        report = result["roundReport"]
        rounds.append(report)
        remaining_new -= 1
        next_round_index += 1
        if report["stop"]["freezeCampaign"]:
            break

    campaign_report = build_campaign_report(plan, campaign_dir=campaign_dir, rounds=rounds)
    if campaign_report["status"] in {"completed", "failed"}:
        _write_terminal_campaign_report(campaign_dir, campaign_report)
    else:
        _write_progress_snapshot(campaign_dir, campaign_report)
    return campaign_report
