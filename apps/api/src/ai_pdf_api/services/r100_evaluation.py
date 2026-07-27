from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_CASES = REPO_ROOT / "docs/evals/r100-research-cases-v1.json"
DEFAULT_BASELINE = REPO_ROOT / "docs/evals/r100-quick-baseline-v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "docs/evals/artifacts/r100-v1/report.json"


class R100DataError(ValueError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise R100DataError(f"Cannot load {path}: {error}") from error
    if not isinstance(value, dict):
        raise R100DataError(f"Expected object at {path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repo_path(relative: str) -> Path:
    path = REPO_ROOT / relative
    if not path.is_file():
        raise R100DataError(f"Missing repository artifact: {relative}")
    return path


def _validate_cases(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if document.get("schemaVersion") != "r100-research-cases-v1":
        raise R100DataError("Unsupported R100 research case schema")
    golden = document.get("referenceGoldenSet")
    if not isinstance(golden, dict) or _sha256(_repo_path(golden["path"])) != golden["sha256"]:
        raise R100DataError("Reference golden set hash mismatch")
    failure = document.get("referenceFailureTaxonomy")
    if not isinstance(failure, dict) or _sha256(_repo_path(failure["path"])) != failure["sha256"]:
        raise R100DataError("Reference failure taxonomy hash mismatch")
    cases = document.get("cases")
    if not isinstance(cases, list) or len(cases) < 5:
        raise R100DataError("R100 requires at least five research cases")
    indexed: dict[str, dict[str, Any]] = {}
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str):
            raise R100DataError("Every research case needs an id")
        case_id = case["id"]
        if case_id in indexed:
            raise R100DataError(f"Duplicate research case: {case_id}")
        claims = case.get("claims")
        if not isinstance(claims, list):
            raise R100DataError(f"Case {case_id} claims must be a list")
        claim_ids: set[str] = set()
        for claim in claims:
            if not isinstance(claim, dict) or not isinstance(claim.get("id"), str):
                raise R100DataError(f"Case {case_id} has an invalid claim")
            if claim["id"] in claim_ids:
                raise R100DataError(f"Duplicate claim {claim['id']} in {case_id}")
            claim_ids.add(claim["id"])
            if not claim.get("requiredConcepts") or not claim.get("supportedBy"):
                raise R100DataError(f"Claim {claim['id']} in {case_id} lacks labels")
        if case["expectedDisposition"] == "refuse" and claims:
            raise R100DataError(f"Refusal case {case_id} cannot publish claims")
        if case["expectedDisposition"] == "answer" and not claims:
            raise R100DataError(f"Answer case {case_id} needs claims")
        indexed[case_id] = case
    return indexed


def _validate_baseline(document: dict[str, Any], cases: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if document.get("schemaVersion") != "r100-quick-baseline-v1":
        raise R100DataError("Unsupported R100 Quick baseline schema")
    for key in ("sourceExecutionArtifact", "sourceGoldenAnswerOracle"):
        source = document.get(key)
        if not isinstance(source, dict) or _sha256(_repo_path(source["path"])) != source["sha256"]:
            raise R100DataError(f"{key} hash mismatch")
    entries = document.get("cases")
    if not isinstance(entries, list) or set(entry.get("researchCaseId") for entry in entries) != set(cases):
        raise R100DataError("Quick baseline must cover every R100 case exactly once")
    indexed: dict[str, dict[str, Any]] = {}
    for entry in entries:
        case_id = entry["researchCaseId"]
        if case_id in indexed or entry.get("assetScope") != cases[case_id].get("assetScope"):
            raise R100DataError(f"Baseline scope mismatch for {case_id}")
        indexed[case_id] = entry
    return indexed


def _concepts_match(output: str, required: list[list[str]]) -> bool:
    lowered = output.casefold()
    return all(any(term.casefold() in lowered for term in group) for group in required)


def _score_case(case: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    output = baseline["output"]
    claims = case["claims"]
    claim_results = []
    for claim in claims:
        concept_match = _concepts_match(output, claim["requiredConcepts"])
        evidence_match = set(claim["supportedBy"]).issubset(set(baseline["evidenceCaseIds"]))
        claim_results.append({"claimId": claim["id"], "conceptMatch": concept_match, "evidenceSupported": evidence_match, "supported": concept_match and evidence_match})
    expected_evidence = set(case["expectedEvidenceCaseIds"])
    observed_evidence = set(baseline["evidenceCaseIds"])
    refusal = case["expectedDisposition"] == "refuse"
    forbidden = [pattern for pattern in case.get("forbiddenAnswerPatterns", []) if re.search(pattern, output)]
    correct_refusal = refusal and not forbidden and not claims
    return {
        "caseId": case["id"],
        "caseType": case["caseType"],
        "expectedDisposition": case["expectedDisposition"],
        "claimResults": claim_results,
        "claimSupportRate": sum(item["supported"] for item in claim_results) / len(claim_results) if claim_results else None,
        "evidenceRecall": len(expected_evidence & observed_evidence) / len(expected_evidence) if expected_evidence else 1.0,
        "locatorAccuracy": expected_evidence == observed_evidence,
        "conflictDetectionMatch": baseline["conflictDetected"] == case["expectedConflict"],
        "correctRefusal": correct_refusal if refusal else None,
        "forbiddenMatches": forbidden,
    }


def evaluate(cases_path: Path = DEFAULT_CASES, baseline_path: Path = DEFAULT_BASELINE) -> dict[str, Any]:
    cases = _validate_cases(_load(cases_path))
    baseline = _validate_baseline(_load(baseline_path), cases)
    scored = [_score_case(cases[case_id], baseline[case_id]) for case_id in cases]
    claim_rows = [row for row in scored if row["claimSupportRate"] is not None]
    refusal_rows = [row for row in scored if row["correctRefusal"] is not None]
    report = {
        "schemaVersion": "r100-report-v1",
        "status": "passed",
        "engineeringGatePassed": True,
        "modelQualityEvaluated": False,
        "userValueValidated": False,
        "productStage": "internal_preview",
        "interpretation": "captured_reference_only; this is a fixture/scorer/replay gate, not a model-quality or user-value result",
        "researchCaseCount": len(cases),
        "quickBaseline": {"replayable": True, "provider": _load(baseline_path)["provider"], "model": _load(baseline_path)["model"], "caseCount": len(baseline)},
        "metrics": {
            "claimSupportRate": sum(row["claimSupportRate"] for row in claim_rows) / len(claim_rows) if claim_rows else None,
            "evidenceRecall": sum(row["evidenceRecall"] for row in scored) / len(scored),
            "locatorAccuracy": sum(row["locatorAccuracy"] for row in scored) / len(scored),
            "conflictDetectionRate": sum(row["conflictDetectionMatch"] for row in scored) / len(scored),
            "refusalRate": sum(row["correctRefusal"] for row in refusal_rows) / len(refusal_rows) if refusal_rows else None,
        },
        "cases": scored,
        "failureTaxonomy": _load(cases_path)["referenceFailureTaxonomy"],
        "deepResearchRun": None,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the deterministic V4 R100 fixture/scorer/Quick-baseline gate.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = evaluate(args.cases, args.baseline)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
