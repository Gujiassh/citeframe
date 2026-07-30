from __future__ import annotations

import json
from pathlib import Path

import pytest
from ai_pdf_worker.r803_evaluation_campaign import run_or_resume_campaign
from ai_pdf_worker.r803_evaluation_contract import (
    DEFAULT_PACKAGE_V5_PATH,
    R803EvaluationError,
    load_evaluation_package,
)
from r803_test_helpers import CampaignProvider, DeterministicProvider


class PartialResearchSelectionProvider(CampaignProvider):
    @staticmethod
    def _synthesizer(variables: dict[str, object]) -> dict[str, object]:
        payload = DeterministicProvider._synthesizer(variables)
        if "Atlas score" not in str(variables["question"]):
            return payload
        fact_ids = payload["factClaimIds"]
        assert isinstance(fact_ids, list) and len(fact_ids) >= 2
        return {
            "factClaimIds": fact_ids[:1],
            "unresolvedClaimIds": payload["unresolvedClaimIds"],
        }


def test_partial_research_selection_is_model_quality_failure(tmp_path: Path) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    campaign_dir = tmp_path / "partial-selection"

    report = run_or_resume_campaign(
        campaign_dir=campaign_dir,
        provider=PartialResearchSelectionProvider(),
        package=package,
        max_new_rounds=1,
        allow_test_provider=True,
    )

    assert report["status"] == "failed"
    assert report["gates"]["engineering"] == "pass"
    assert report["gates"]["modelQuality"] == "fail"
    assert report["sample"]["completedRounds"] == 1
    assert report["sample"]["totalCaseExecutionsCompleted"] == 12
    assert report["interruption"] is None

    paired = json.loads(
        (campaign_dir / "round-01/paired-quality-report.json").read_text(
            encoding="utf-8"
        )
    )
    target = next(
        item
        for item in paired["cases"]
        if item["caseKey"] == "r100-synthesize-table-constraint"
    )
    research = target["research"]
    assert research["qualityFailure"] is True
    assert research["engineeringFailure"] is False
    assert research["diagnostic"]["nodeKey"] == "synthesizer"
    assert research["diagnostic"]["rule"] == "missing_expected_claim"
    assert research["diagnostic"]["failureOrigin"] == "model_or_workflow_quality"


@pytest.mark.parametrize(
    "mutation",
    [
        "add",
        "modify",
        "delete",
        "add-checksum",
        "modify-checksum",
        "delete-checksum",
    ],
)
def test_terminal_interruption_binds_partial_round_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    campaign_dir = tmp_path / mutation
    round_dir = campaign_dir / "round-01"
    partial_path = round_dir / "partial-provider-output.json"
    checksum_path = round_dir / "SHA256SUMS"

    def interrupt_after_partial_write(*_args, **_kwargs):
        partial_path.write_text('{"partial":true}\n', encoding="utf-8")
        if mutation in {"modify-checksum", "delete-checksum"}:
            checksum_path.write_text("partial checksum manifest\n", encoding="utf-8")
        raise RuntimeError("simulated interruption")

    monkeypatch.setattr(
        "ai_pdf_worker.r803_evaluation_campaign.run_quick_case_with_diagnostics",
        interrupt_after_partial_write,
    )
    report = run_or_resume_campaign(
        campaign_dir=campaign_dir,
        provider=CampaignProvider(),
        package=package,
        max_new_rounds=1,
        allow_test_provider=True,
    )

    interruption = report["interruption"]
    assert interruption["partialRoundPreserved"] is True
    assert interruption["partialRoundFileHashes"]["partial-provider-output.json"]
    if mutation in {"modify-checksum", "delete-checksum"}:
        assert interruption["partialRoundFileHashes"]["SHA256SUMS"]
    assert len(interruption["partialRoundClosureSha256"]) == 64

    if mutation == "add":
        (round_dir / "added-after-freeze.txt").write_text("tampered\n", encoding="utf-8")
    elif mutation == "modify":
        partial_path.write_text('{"partial":false}\n', encoding="utf-8")
    elif mutation == "delete":
        partial_path.unlink()
    elif mutation == "add-checksum":
        checksum_path.write_text("added after freeze\n", encoding="utf-8")
    elif mutation == "modify-checksum":
        checksum_path.write_text("modified after freeze\n", encoding="utf-8")
    else:
        checksum_path.unlink()

    with pytest.raises(
        R803EvaluationError,
        match="partial_round_file_(set|hash)_drift",
    ):
        run_or_resume_campaign(
            campaign_dir=campaign_dir,
            package=package,
            max_new_rounds=0,
        )
