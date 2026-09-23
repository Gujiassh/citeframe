from __future__ import annotations

from pathlib import Path
from typing import Any
from citeframe_evaluation.contracts import R803EvaluationError
from citeframe_evaluation.campaign.plan import CAMPAIGN_SCHEMA_VERSION, CampaignPlan


def _public_import_report(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if not key.startswith("_")}


def _mean_ratio(rows: list[dict[str, Any]], key: str) -> dict[str, object]:
    values = [row[key] for row in rows if row[key]["value"] is not None]
    if not values:
        return {
            "value": None,
            "sampleCount": 0,
            "notEvaluableReason": "no_evaluable_samples",
        }
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
        "unsupportedClaimCount": sum(
            int(row["unsupportedClaimCount"]) for row in scored_rows
        ),
        "extraClaimCount": sum(int(row["extraClaimCount"]) for row in scored_rows),
        "negatedClaimCount": sum(int(row["negatedClaimCount"]) for row in scored_rows),
        "forbiddenAnswerCount": sum(
            int(row["forbiddenAnswerCount"]) for row in scored_rows
        ),
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
            "claimSupportRate": {
                "value": None,
                "sampleCount": 0,
                "notEvaluableReason": "no_rounds",
            },
            "evidenceRecall": {
                "value": None,
                "sampleCount": 0,
                "notEvaluableReason": "no_rounds",
            },
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
    quick_threshold = (
        _mode_semantic_gates(quick_metrics, plan.threshold) if rounds else None
    )
    research_threshold = (
        _mode_semantic_gates(research_metrics, plan.threshold) if rounds else None
    )
    if rounds:
        if (
            quick_threshold["modelQuality"] == "fail"
            or research_threshold["modelQuality"] == "fail"
        ):
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

    formal_evidence = (
        all(
            (item.get("providerAttestation") or {}).get("formalEvidence", True)
            for item in rounds
        )
        and interruption is None
    )

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
            "totalCaseExecutionsPlanned": plan.planned_rounds
            * len(plan.case_order)
            * 2,
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
