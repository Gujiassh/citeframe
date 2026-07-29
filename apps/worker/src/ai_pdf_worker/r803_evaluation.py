from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_pdf_api.core.settings import settings

from ai_pdf_worker.r803_evaluation_contract import (
    CaseExecution,
    EvaluationPackage,
    R803EvaluationError,
    build_import_report,
    canonical_bytes,
    load_evaluation_package,
)
from ai_pdf_worker.r803_evaluation_provider import (
    OpenAIRecordedProvider,
    RecordedProvider,
    quick_prompt_binding_sha256,
    research_prompt_binding_sha256,
)
from ai_pdf_worker.r803_evaluation_runtime import (
    run_quick_case,
    run_research_case,
)


@dataclass(frozen=True)
class PairedEvaluationResult:
    quick_report: dict[str, Any]
    research_report: dict[str, Any]
    paired_report: dict[str, Any]


def configured_provider(package: EvaluationPackage) -> OpenAIRecordedProvider:
    profile = package.document["providerProfile"]
    api_base = settings.openai_api_base.rstrip("/")
    if not settings.openai_api_key or not settings.openai_api_key.strip():
        raise R803EvaluationError("openai_api_key_not_configured")
    if settings.generation_provider != profile["provider"]:
        raise R803EvaluationError("provider_configuration_mismatch")
    if settings.generation_model != profile["model"]:
        raise R803EvaluationError("model_configuration_mismatch")
    if api_base != profile["apiBase"].rstrip("/"):
        raise R803EvaluationError("provider_api_base_mismatch")
    return OpenAIRecordedProvider(
        model=profile["model"],
        api_key=settings.openai_api_key,
        api_base=api_base,
        timeout_seconds=settings.generation_timeout_seconds,
        max_output_tokens=profile["maxOutputTokens"],
        structured_output_transport=package.document["structuredOutput"]["transportVersion"],
    )


def _metric_value(report: dict[str, Any], key: str) -> float | None:
    value = report["evaluation"][key]["value"]
    return float(value) if value is not None else None


def _case_artifact(execution: CaseExecution, score: dict[str, Any]) -> dict[str, Any]:
    return {
        "caseKey": execution.case_key,
        "mode": execution.mode,
        "output": execution.output,
        "observedDisposition": execution.observed_disposition,
        "evidenceIds": list(execution.evidence_ids),
        "conflictDetected": execution.conflict_detected,
        "wallTimeMs": execution.wall_time_ms,
        "providerCalls": execution.provider_calls,
        "inputTokens": execution.input_tokens,
        "outputTokens": execution.output_tokens,
        "parallelSpeedup": execution.parallel_speedup,
        "failureCode": execution.failure_code,
        "conflictResolution": execution.conflict_resolution,
        "providerCallRecords": [asdict(item) for item in execution.calls],
        "score": {
            key: score[key]
            for key in (
                "claimSupportRate",
                "evidenceRecall",
                "evidencePrecision",
                "locatorAccuracy",
                "conflictDetectionRate",
                "refusalCorrectness",
            )
        },
    }


def _comparison_keys(report: dict[str, Any]) -> dict[str, object]:
    evaluation = report["evaluation"]
    return {
        key: evaluation[key]
        for key in (
            "fixtureManifestSha256",
            "assetScopeSha256",
            "provider",
            "model",
            "providerProfileSha256",
            "scorerVersion",
        )
    }


def _paired_report(
    package: EvaluationPackage,
    quick_report: dict[str, Any],
    research_report: dict[str, Any],
    quick_executions: tuple[CaseExecution, ...],
    research_executions: tuple[CaseExecution, ...],
) -> dict[str, Any]:
    quick_keys = _comparison_keys(quick_report)
    research_keys = _comparison_keys(research_report)
    if quick_keys != research_keys:
        raise R803EvaluationError("comparison_key_mismatch")
    quick_scores = {item["caseKey"]: item for item in quick_report["cases"]}
    research_scores = {item["caseKey"]: item for item in research_report["cases"]}
    metrics = (
        "claimSupportRate",
        "evidenceRecall",
        "evidencePrecision",
        "locatorAccuracy",
        "conflictDetectionRate",
        "refusalCorrectness",
    )
    deltas: dict[str, float | None] = {}
    for key in metrics:
        quick_value = _metric_value(quick_report, key)
        research_value = _metric_value(research_report, key)
        deltas[key] = (
            research_value - quick_value
            if quick_value is not None and research_value is not None
            else None
        )
    quick_by_id = {item.case_key: item for item in quick_executions}
    research_by_id = {item.case_key: item for item in research_executions}
    return {
        "schemaVersion": "r803-paired-quality-report-v1",
        "package": {
            "path": str(package.path.relative_to(package.path.parents[2])),
            "sha256": package.sha256,
            "fixtureIds": sorted(package.assets),
            "caseCount": len(package.cases),
        },
        "comparisonKeys": quick_keys,
        "comparisonKeysMatch": True,
        "versionDimensions": {
            "quick": {
                "workflowVersionId": quick_report["evaluation"]["workflowVersionId"],
                "promptBindingSha256": quick_report["evaluation"]["promptBindingSha256"],
            },
            "research": {
                "workflowVersionId": research_report["evaluation"]["workflowVersionId"],
                "promptBindingSha256": research_report["evaluation"]["promptBindingSha256"],
            },
        },
        "sample": {
            "pairedCaseCount": len(package.cases),
            "independentExecutionsPerCaseAndMode": 1,
            "releaseThresholdDefined": False,
            "uncertainty": "One provider-backed execution per case and mode is observational evidence, not a release threshold.",
        },
        "gates": {
            "quickEngineering": quick_report["evaluation"]["engineeringGate"],
            "researchEngineering": research_report["evaluation"]["engineeringGate"],
            "modelQuality": "not_evaluable",
            "modelQualityReason": "single_sample_no_release_threshold",
            "userValue": "not_evaluable",
            "userValueReason": "m404_evidence_absent",
            "productStage": "internal_preview",
        },
        "aggregate": {
            "quick": {key: quick_report["evaluation"][key] for key in metrics},
            "research": {key: research_report["evaluation"][key] for key in metrics},
            "researchMinusQuick": deltas,
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
                "quick": _case_artifact(quick_by_id[case["id"]], quick_scores[case["id"]]),
                "research": _case_artifact(research_by_id[case["id"]], research_scores[case["id"]]),
            }
            for case in package.cases
        ],
    }


def run_paired_evaluation(
    *,
    package: EvaluationPackage | None = None,
    provider: RecordedProvider | None = None,
    baseline_evaluation_run_id: str | None = None,
) -> PairedEvaluationResult:
    frozen = package or load_evaluation_package()
    quick_binding_sha256 = quick_prompt_binding_sha256(frozen)
    research_binding_sha256 = research_prompt_binding_sha256(frozen)
    active_provider = provider or configured_provider(frozen)
    if (
        active_provider.provider != frozen.comparison_keys.provider
        or active_provider.model != frozen.comparison_keys.model
    ):
        raise R803EvaluationError("provider_profile_mismatch")

    quick_started = datetime.now(UTC)
    quick_executions = tuple(run_quick_case(frozen, case, active_provider) for case in frozen.cases)
    quick_completed = datetime.now(UTC)
    quick_report = build_import_report(
        frozen,
        mode="quick",
        executions=quick_executions,
        created_at=quick_started,
        completed_at=quick_completed,
        prompt_binding_sha256=quick_binding_sha256,
    )

    research_started = datetime.now(UTC)
    research_executions = tuple(run_research_case(frozen, case, active_provider) for case in frozen.cases)
    research_completed = datetime.now(UTC)
    research_report = build_import_report(
        frozen,
        mode="research",
        executions=research_executions,
        created_at=research_started,
        completed_at=research_completed,
        prompt_binding_sha256=research_binding_sha256,
        baseline_evaluation_run_id=baseline_evaluation_run_id,
    )
    return PairedEvaluationResult(
        quick_report=quick_report,
        research_report=research_report,
        paired_report=_paired_report(
            frozen,
            quick_report,
            research_report,
            quick_executions,
            research_executions,
        ),
    )


def write_result(result: PairedEvaluationResult, output_dir: Path) -> dict[str, str]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise R803EvaluationError("output_directory_not_empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "quick-evaluation.json": canonical_bytes(result.quick_report),
        "research-evaluation.json": canonical_bytes(result.research_report),
        "paired-quality-report.json": canonical_bytes(result.paired_report),
    }
    hashes: dict[str, str] = {}
    for name, content in artifacts.items():
        path = output_dir / name
        with path.open("xb") as target:
            target.write(content)
        hashes[name] = hashlib.sha256(content).hexdigest()
    checksum = "".join(f"{digest}  {name}\n" for name, digest in sorted(hashes.items()))
    with (output_dir / "SHA256SUMS").open("x", encoding="utf-8") as target:
        target.write(checksum)
    hashes["SHA256SUMS"] = hashlib.sha256(checksum.encode("utf-8")).hexdigest()
    return hashes
