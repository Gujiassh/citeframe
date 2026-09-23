from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from citeframe_evaluation.contracts import (
    DEFAULT_PACKAGE_V5_PATH,
    REPO_ROOT,
    EvaluationPackage,
    R803EvaluationError,
    canonical_sha256,
    file_sha256,
    load_evaluation_package,
)
from citeframe_evaluation.integrity import (
    compute_evaluator_closure,
    scorer_implementation_sha256,
)
from citeframe_evaluation.provider import (
    quick_prompt_binding_sha256,
    research_prompt_binding_sha256,
)
from citeframe_evaluation.scoring import SCORER_VERSION


CAMPAIGN_SCHEMA_VERSION = "r803-campaign-report-v1"


ROUND_SCHEMA_VERSION = "r803-campaign-round-v1"


THRESHOLD_SCHEMA_VERSION = "r803-release-threshold-v1"


PROGRESS_SCHEMA_VERSION = "r803-campaign-progress-v1"


ROUND_MANIFEST_SCHEMA_VERSION = "r803-campaign-round-manifest-v1"


ROUND_START_SCHEMA_VERSION = "r803-campaign-round-start-v1"


PLAN_SCHEMA_VERSION = "r803-campaign-plan-v1"


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
        "structuredOutputTransport": frozen.document["structuredOutput"][
            "transportVersion"
        ],
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
