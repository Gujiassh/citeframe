from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from ai_pdf_api.schemas.evaluation import EvaluationImportReport

from ai_pdf_worker.r803_evaluation_policy import (
    MAX_PROVIDER_ATTEMPTS,
    RETRY_BACKOFF_SECONDS,
    RETRY_POLICY_VERSION,
    RETRYABLE_PROVIDER_CODES,
)
from ai_pdf_worker.r803_structured_output import (
    QUICK_RESULT_SCHEMA_VERSION,
    STRUCTURED_OUTPUT_SCHEMA_SET_VERSION,
    STRUCTURED_OUTPUT_TRANSPORT_VERSION,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PACKAGE_PATH = REPO_ROOT / "docs/evals/r803-evaluation-package-v4.json"


class R803EvaluationError(ValueError):
    pass


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class ComparisonKeys:
    fixture_manifest_sha256: str
    asset_scope_sha256: str
    provider: str
    model: str
    provider_profile_sha256: str
    scorer_version: str

    def as_dict(self) -> dict[str, str]:
        return {
            "fixtureManifestSha256": self.fixture_manifest_sha256,
            "assetScopeSha256": self.asset_scope_sha256,
            "provider": self.provider,
            "model": self.model,
            "providerProfileSha256": self.provider_profile_sha256,
            "scorerVersion": self.scorer_version,
        }


@dataclass(frozen=True)
class EvidenceItem:
    id: str
    asset_id: str
    asset_title: str
    locator_kind: Literal["pdf_page", "pdf_region", "image_region"]
    locator_key: str
    content: str
    source_fingerprint_sha256: str


@dataclass(frozen=True)
class EvaluationPackage:
    path: Path
    sha256: str
    document: dict[str, Any]
    cases: tuple[dict[str, Any], ...]
    assets: dict[str, dict[str, Any]]
    evidence: dict[str, EvidenceItem]
    comparison_keys: ComparisonKeys


@dataclass(frozen=True)
class ProviderCallRecord:
    node_key: str
    logical_call_key: str
    attempt_number: int
    duration_ms: int
    input_tokens: int
    output_tokens: int
    usage_final: bool
    status: Literal["succeeded", "failed"]


@dataclass(frozen=True)
class ObservedClaim:
    text: str
    evidence_ids: tuple[str, ...]
    conflicted: bool = False


@dataclass(frozen=True)
class CaseExecution:
    case_key: str
    mode: Literal["quick", "research"]
    output: str
    observed_disposition: Literal["answer", "refuse", "not_evaluable"]
    evidence_ids: tuple[str, ...]
    conflict_detected: bool
    observed_claims: tuple[ObservedClaim, ...]
    wall_time_ms: int
    calls: tuple[ProviderCallRecord, ...]
    parallel_speedup: float | None = None
    failure_code: str | None = None
    conflict_resolution: str | None = None

    @property
    def provider_calls(self) -> int:
        return len(self.calls)

    @property
    def input_tokens(self) -> int:
        return sum(item.input_tokens for item in self.calls)

    @property
    def output_tokens(self) -> int:
        return sum(item.output_tokens for item in self.calls)


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise R803EvaluationError(f"cannot_load:{path}") from error
    if not isinstance(value, dict):
        raise R803EvaluationError(f"expected_object:{path}")
    return value


def _validated_repo_file(relative: str, expected_sha256: str) -> Path:
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise R803EvaluationError(f"artifact_path_outside_repository:{relative}")
    path = (REPO_ROOT / relative_path).resolve()
    if not path.is_relative_to(REPO_ROOT.resolve()):
        raise R803EvaluationError(f"artifact_path_outside_repository:{relative}")
    if not path.is_file() or file_sha256(path) != expected_sha256:
        raise R803EvaluationError(f"artifact_hash_mismatch:{relative}")
    return path


def load_evaluation_package(path: Path = DEFAULT_PACKAGE_PATH) -> EvaluationPackage:
    document = _load_object(path)
    if document.get("schemaVersion") != "r803-evaluation-package-v4":
        raise R803EvaluationError("unsupported_package_schema")
    suite = document.get("suite")
    provider = document.get("providerProfile")
    research = document.get("research")
    assets_document = document.get("assets")
    if not all(isinstance(item, dict) for item in (suite, provider, research)) or not isinstance(assets_document, list):
        raise R803EvaluationError("invalid_evaluation_package")
    quick = document.get("quick")
    structured_output = document.get("structuredOutput")
    execution_policy = document.get("executionPolicy")
    if (
        not isinstance(quick, dict)
        or not isinstance(structured_output, dict)
        or not isinstance(execution_policy, dict)
        or not isinstance(quick.get("systemPrompt"), str)
        or not quick["systemPrompt"].strip()
        or not isinstance(quick.get("evaluationContract"), str)
        or not quick["evaluationContract"].strip()
        or quick.get("resultSchemaVersion") != QUICK_RESULT_SCHEMA_VERSION
        or structured_output.get("transportVersion")
        != STRUCTURED_OUTPUT_TRANSPORT_VERSION
        or structured_output.get("schemaSetVersion")
        != STRUCTURED_OUTPUT_SCHEMA_SET_VERSION
        or execution_policy.get("retryPolicyVersion") != RETRY_POLICY_VERSION
        or execution_policy.get("maxProviderAttempts") != MAX_PROVIDER_ATTEMPTS
        or execution_policy.get("retryBackoffSeconds")
        != list(RETRY_BACKOFF_SECONDS)
        or execution_policy.get("retryableProviderCodes")
        != sorted(RETRYABLE_PROVIDER_CODES)
        or suite.get("scorerVersion") != "r100-v1"
        or provider.get("provider") != "openai"
        or provider.get("model") != "gpt-5.5"
        or provider.get("apiProtocol") != "responses-v1"
        or provider.get("pricingVersion") != "research-pricing-v1"
        or type(provider.get("maxOutputTokens")) is not int
        or provider["maxOutputTokens"] < 1
    ):
        raise R803EvaluationError("unsupported_evaluation_package")

    cases_path = _validated_repo_file(suite["caseManifestPath"], suite["caseManifestSha256"])
    _validated_repo_file(suite["goldenManifestPath"], suite["goldenManifestSha256"])
    cases_document = _load_object(cases_path)
    cases = cases_document.get("cases")
    if cases_document.get("schemaVersion") != "r100-research-cases-v1" or not isinstance(cases, list):
        raise R803EvaluationError("invalid_case_manifest")
    golden_reference = cases_document.get("referenceGoldenSet")
    if (
        not isinstance(golden_reference, dict)
        or golden_reference.get("path") != suite["goldenManifestPath"]
        or golden_reference.get("sha256") != suite["goldenManifestSha256"]
    ):
        raise R803EvaluationError("case_golden_reference_mismatch")

    assets: dict[str, dict[str, Any]] = {}
    evidence: dict[str, EvidenceItem] = {}
    scope_identity: list[dict[str, str]] = []
    for asset in assets_document:
        if not isinstance(asset, dict) or not isinstance(asset.get("id"), str) or asset["id"] in assets:
            raise R803EvaluationError("invalid_asset_manifest")
        _validated_repo_file(asset["sourcePath"], asset["sourceSha256"])
        _validated_repo_file(asset["manifestPath"], asset["manifestSha256"])
        asset_id = asset["id"]
        assets[asset_id] = asset
        scope_identity.append(
            {
                "assetId": asset_id,
                "sourceSha256": asset["sourceSha256"],
                "manifestSha256": asset["manifestSha256"],
            }
        )
        for item in asset.get("evidence", []):
            evidence_id = item.get("id") if isinstance(item, dict) else None
            if not isinstance(evidence_id, str) or evidence_id in evidence:
                raise R803EvaluationError("invalid_evidence_manifest")
            locator_kind = item.get("locatorKind")
            if locator_kind not in {"pdf_page", "pdf_region", "image_region"}:
                raise R803EvaluationError("invalid_evidence_locator")
            evidence[evidence_id] = EvidenceItem(
                id=evidence_id,
                asset_id=asset_id,
                asset_title=asset["title"],
                locator_kind=locator_kind,
                locator_key=item["locatorKey"],
                content=item["content"],
                source_fingerprint_sha256=canonical_sha256(
                    {
                        "assetId": asset_id,
                        "sourceSha256": asset["sourceSha256"],
                        "manifestSha256": asset["manifestSha256"],
                        "locatorKind": locator_kind,
                        "locatorKey": item["locatorKey"],
                        "content": item["content"],
                    }
                ),
            )

    expected_case_ids: set[str] = set()
    scoped_asset_ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str):
            raise R803EvaluationError("invalid_case_manifest")
        case_scope = case.get("assetScope")
        expected_evidence = case.get("expectedEvidenceCaseIds")
        if not isinstance(case_scope, list) or not set(case_scope).issubset(assets):
            raise R803EvaluationError(f"case_scope_mismatch:{case['id']}")
        if not isinstance(expected_evidence, list) or not set(expected_evidence).issubset(evidence):
            raise R803EvaluationError(f"case_evidence_mismatch:{case['id']}")
        if any(evidence[item].asset_id not in case_scope for item in expected_evidence):
            raise R803EvaluationError(f"case_evidence_scope_mismatch:{case['id']}")
        if case["id"] in expected_case_ids:
            raise R803EvaluationError(f"duplicate_case:{case['id']}")
        expected_case_ids.add(case["id"])
        scoped_asset_ids.update(case_scope)
    if scoped_asset_ids != set(assets):
        raise R803EvaluationError("package_asset_scope_mismatch")

    profile_identity = {
        "provider": provider["provider"],
        "model": provider["model"],
        "apiBase": provider["apiBase"].rstrip("/"),
        "apiProtocol": provider["apiProtocol"],
        "maxOutputTokens": provider["maxOutputTokens"],
        "pricingVersion": provider["pricingVersion"],
    }
    keys = ComparisonKeys(
        fixture_manifest_sha256=suite["caseManifestSha256"],
        asset_scope_sha256=canonical_sha256({"assets": sorted(scope_identity, key=lambda item: item["assetId"])}),
        provider=provider["provider"],
        model=provider["model"],
        provider_profile_sha256=canonical_sha256(profile_identity),
        scorer_version=suite["scorerVersion"],
    )
    return EvaluationPackage(
        path=path,
        sha256=file_sha256(path),
        document=document,
        cases=tuple(cases),
        assets=assets,
        evidence=evidence,
        comparison_keys=keys,
    )


def _concepts_match(output: str, required: list[list[str]]) -> bool:
    lowered = output.casefold()
    return all(any(term.casefold() in lowered for term in group) for group in required)


def _ratio(value: float | None, sample_count: int, reason: str | None = None) -> dict[str, object]:
    return {"value": value, "sampleCount": sample_count, "notEvaluableReason": reason}


def score_case(case: dict[str, Any], execution: CaseExecution) -> dict[str, Any]:
    if execution.failure_code is not None:
        unavailable = _ratio(None, 0, "case_execution_failed")
        return {
            "caseKey": case["id"],
            "caseType": case["caseType"],
            "expectedDisposition": case["expectedDisposition"],
            "observedDisposition": "not_evaluable",
            "claimSupportRate": unavailable,
            "evidenceRecall": unavailable,
            "evidencePrecision": unavailable,
            "locatorAccuracy": unavailable,
            "conflictDetectionRate": unavailable,
            "refusalCorrectness": unavailable,
            "wallTimeMs": execution.wall_time_ms,
            "providerCalls": execution.provider_calls,
            "cost": {"currency": "USD", "amountMicros": 0},
            "unsupportedClaimCount": 0,
            "humanInterventionCount": 0,
            "humanWaitMs": 0,
            "failureCode": "scorer_error",
            "claims": [],
        }

    expected_evidence = set(case["expectedEvidenceCaseIds"])
    observed_evidence = set(execution.evidence_ids)
    claim_rows: list[dict[str, object]] = []
    for expected_claim in case["claims"]:
        matches = [
            item
            for item in execution.observed_claims
            if _concepts_match(item.text, expected_claim["requiredConcepts"])
        ]
        claim_evidence = {evidence_id for item in matches for evidence_id in item.evidence_ids}
        expected_claim_evidence = set(expected_claim["supportedBy"])
        supported = bool(matches) and expected_claim_evidence.issubset(claim_evidence)
        locator_accurate = bool(matches) and claim_evidence == expected_claim_evidence
        conflict_detected = execution.conflict_detected and any(item.conflicted for item in matches)
        failure_code = None
        if not supported:
            failure_code = "evidence_missing" if matches else "unsupported_claim"
        elif not locator_accurate:
            failure_code = "locator_inaccurate"
        elif case["expectedConflict"] and not conflict_detected:
            failure_code = "conflict_missed"
        claim_rows.append(
            {
                "claimKey": expected_claim["id"],
                "supportResult": "supported" if supported else "unsupported",
                "locatorResult": "accurate" if locator_accurate else "inaccurate",
                "conflictResult": (
                    "detected"
                    if case["expectedConflict"] and conflict_detected
                    else "missed"
                    if case["expectedConflict"]
                    else "none"
                ),
                "expectedEvidenceCount": len(expected_claim_evidence),
                "observedEvidenceCount": len(claim_evidence),
                "failureCode": failure_code,
            }
        )

    claim_support = (
        _ratio(sum(row["supportResult"] == "supported" for row in claim_rows) / len(claim_rows), len(claim_rows))
        if claim_rows
        else _ratio(None, 0, "no_expected_claims")
    )
    evidence_recall = len(expected_evidence & observed_evidence) / len(expected_evidence) if expected_evidence else 1.0
    evidence_precision = len(expected_evidence & observed_evidence) / len(observed_evidence) if observed_evidence else (1.0 if not expected_evidence else 0.0)
    locator_accurate = expected_evidence == observed_evidence
    conflict_correct = execution.conflict_detected is bool(case["expectedConflict"])
    forbidden = any(re.search(pattern, execution.output) for pattern in case.get("forbiddenAnswerPatterns", []))
    is_refusal_case = case["expectedDisposition"] == "refuse"
    refusal_correct = execution.observed_disposition == "refuse" and not forbidden
    return {
        "caseKey": case["id"],
        "caseType": case["caseType"],
        "expectedDisposition": case["expectedDisposition"],
        "observedDisposition": execution.observed_disposition,
        "claimSupportRate": claim_support,
        "evidenceRecall": _ratio(evidence_recall, 1),
        "evidencePrecision": _ratio(evidence_precision, 1),
        "locatorAccuracy": _ratio(float(locator_accurate), 1),
        "conflictDetectionRate": _ratio(float(conflict_correct), 1),
        "refusalCorrectness": _ratio(float(refusal_correct), 1) if is_refusal_case else _ratio(None, 0, "not_refusal_case"),
        "wallTimeMs": execution.wall_time_ms,
        "providerCalls": execution.provider_calls,
        "cost": {"currency": "USD", "amountMicros": 0},
        "unsupportedClaimCount": sum(row["supportResult"] == "unsupported" for row in claim_rows),
        "humanInterventionCount": 0,
        "humanWaitMs": 0,
        "failureCode": None,
        "claims": claim_rows,
    }


def aggregate_ratio(rows: list[dict[str, Any]], key: str) -> dict[str, object]:
    metrics = [row[key] for row in rows if row[key]["value"] is not None]
    sample_count = sum(item["sampleCount"] for item in metrics)
    if sample_count == 0:
        return _ratio(None, 0, "no_evaluable_samples")
    weighted = sum(float(item["value"]) * int(item["sampleCount"]) for item in metrics)
    return _ratio(weighted / sample_count, sample_count)


def _evaluation_failure(executions: tuple[CaseExecution, ...]) -> dict[str, str] | None:
    failure_codes = {item.failure_code for item in executions if item.failure_code is not None}
    if not failure_codes:
        return None
    if all(code.endswith("_invalid_output") for code in failure_codes):
        return {
            "code": "schema_violation",
            "message": "One or more evaluation cases returned invalid structured output.",
        }
    if all(code.startswith("generation_") for code in failure_codes):
        return {
            "code": "provider_error",
            "message": "One or more evaluation cases failed at the generation provider.",
        }
    return {
        "code": "evaluation_internal_error",
        "message": "One or more evaluation cases did not complete.",
    }


def build_import_report(
    package: EvaluationPackage,
    *,
    mode: Literal["quick", "research"],
    executions: tuple[CaseExecution, ...],
    created_at: datetime,
    completed_at: datetime,
    prompt_binding_sha256: str,
    baseline_evaluation_run_id: str | None = None,
) -> dict[str, Any]:
    by_id = {item.case_key: item for item in executions}
    if set(by_id) != {case["id"] for case in package.cases}:
        raise R803EvaluationError("execution_case_set_mismatch")
    scored = [score_case(case, by_id[case["id"]]) for case in package.cases]
    failed = any(item.failure_code is not None for item in executions)
    input_tokens = sum(item.input_tokens for item in executions)
    output_tokens = sum(item.output_tokens for item in executions)
    provider_calls = sum(item.provider_calls for item in executions)
    pricing = package.document["providerProfile"]["pricingVersion"]
    if pricing != "research-pricing-v1":
        raise R803EvaluationError("unsupported_pricing_version")
    cost_micros = (input_tokens * 2_500_000 + output_tokens * 15_000_000 + 999_999) // 1_000_000
    for row in scored:
        execution = by_id[row["caseKey"]]
        case_cost = (execution.input_tokens * 2_500_000 + execution.output_tokens * 15_000_000 + 999_999) // 1_000_000
        row["cost"]["amountMicros"] = case_cost
    grouped_calls: dict[str, list[ProviderCallRecord]] = {}
    for execution in executions:
        for call in execution.calls:
            grouped_calls.setdefault(call.logical_call_key, []).append(call)
    retry_count = sum(max(0, len(calls) - 1) for calls in grouped_calls.values())
    retried_calls = [calls for calls in grouped_calls.values() if len(calls) > 1]
    recovered_calls = sum(calls[-1].status == "succeeded" for calls in retried_calls)
    retry_rate = _ratio(retry_count / provider_calls, provider_calls) if provider_calls else _ratio(None, 0, "no_provider_calls")
    recovery_rate = (
        _ratio(recovered_calls / len(retried_calls), len(retried_calls))
        if retried_calls
        else _ratio(None, 0, "no_recovery_scenarios")
    )
    parallel_values = [item.parallel_speedup for item in executions if item.parallel_speedup is not None]
    keys = package.comparison_keys
    report = {
        "schemaVersion": "citeframe-evaluation-report-v1",
        "suite": {
            "suiteKey": package.document["suite"]["suiteKey"],
            "version": package.document["suite"]["version"],
            "title": package.document["suite"]["title"],
            "fixtureManifestSha256": keys.fixture_manifest_sha256,
            "scorerVersion": keys.scorer_version,
            "caseCount": len(package.cases),
        },
        "evaluation": {
            "mode": mode,
            "status": "failed" if failed else "completed",
            "researchRunId": None,
            "baselineEvaluationRunId": baseline_evaluation_run_id if mode == "research" else None,
            **keys.as_dict(),
            "workflowVersionId": package.document["research"]["workflowVersionId"] if mode == "research" else None,
            "promptBindingSha256": prompt_binding_sha256,
            "sourceArtifact": None,
            "modelQualityEvidenceKind": "provider_backed",
            "userValueEvidenceRef": None,
            "wallTimeMs": int((completed_at - created_at).total_seconds() * 1000),
            "providerCalls": provider_calls,
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "cost": {"currency": "USD", "amountMicros": cost_micros},
            "parallelSpeedup": sum(parallel_values) / len(parallel_values) if parallel_values else None,
            "retryRate": retry_rate,
            "recoveryRate": recovery_rate,
            "claimSupportRate": aggregate_ratio(scored, "claimSupportRate"),
            "evidenceRecall": aggregate_ratio(scored, "evidenceRecall"),
            "evidencePrecision": aggregate_ratio(scored, "evidencePrecision"),
            "locatorAccuracy": aggregate_ratio(scored, "locatorAccuracy"),
            "conflictDetectionRate": aggregate_ratio(scored, "conflictDetectionRate"),
            "refusalCorrectness": aggregate_ratio(scored, "refusalCorrectness"),
            "engineeringGate": "fail" if failed else "pass",
            "modelQualityGate": "not_evaluable",
            "userValueGate": "not_evaluable",
            "failure": _evaluation_failure(executions),
            "createdAt": created_at.isoformat(),
            "completedAt": completed_at.isoformat(),
        },
        "cases": scored,
    }
    EvaluationImportReport.model_validate(report)
    return report
