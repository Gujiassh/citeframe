from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_pdf_api.services.r100_evaluation import R100DataError, evaluate

REPO_ROOT = Path(__file__).resolve().parents[3]
CASES = REPO_ROOT / "docs/evals/r100-research-cases-v1.json"
BASELINE = REPO_ROOT / "docs/evals/r100-quick-baseline-v1.json"


def test_r100_fixture_scorer_and_quick_baseline_are_replayable() -> None:
    report = evaluate(CASES, BASELINE)
    assert report["status"] == "passed"
    assert report["engineeringGatePassed"] is True
    assert report["modelQualityEvaluated"] is False
    assert report["userValueValidated"] is False
    assert report["quickBaseline"]["replayable"] is True
    assert report["researchCaseCount"] == 6
    assert report["metrics"]["claimSupportRate"] == 1.0
    assert report["metrics"]["evidenceRecall"] == 1.0
    assert report["metrics"]["locatorAccuracy"] == 1.0
    assert report["metrics"]["conflictDetectionRate"] == 1.0
    assert report["metrics"]["refusalRate"] == 1.0


def test_r100_refusal_case_rejects_forbidden_claim_text(tmp_path: Path) -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    baseline["cases"][-1]["output"] = "The customer Atlas approved the release."
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(baseline), encoding="utf-8")
    report = evaluate(CASES, path)
    refusal = next(row for row in report["cases"] if row["caseId"] == "r100-refuse-customer")
    assert refusal["correctRefusal"] is False
    assert refusal["forbiddenMatches"] == ["\\bcustomer\\s+[A-Z][a-z]+"]


def test_r100_rejects_reference_hash_drift(tmp_path: Path) -> None:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    cases["referenceGoldenSet"]["sha256"] = "0" * 64
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases), encoding="utf-8")
    with pytest.raises(R100DataError, match="golden set hash mismatch"):
        evaluate(path, BASELINE)
