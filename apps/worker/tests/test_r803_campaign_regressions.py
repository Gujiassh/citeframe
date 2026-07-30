from __future__ import annotations

import json
from pathlib import Path

import pytest
from ai_pdf_worker.r803_evaluation_campaign import (
    _safe_interruption_detail,
    run_or_resume_campaign,
)
from ai_pdf_worker.r803_evaluation_contract import (
    DEFAULT_PACKAGE_V5_PATH,
    R803EvaluationError,
    load_evaluation_package,
)
from r803_test_helpers import CampaignProvider, DeterministicProvider

_SECRET_CANARY = (
    "api-key=R803_TEST_CANARY_NOT_A_SECRET\n"
    "/home/private/raw-output-\u79d8\u5bc6"
)
_SAFE_R803_CODES = (
    "quality_failure_provenance_unresolved",
    "diagnostic_scope_not_approved",
    "raw_output_contains_forbidden_material",
    "duplicate_raw_output_path",
    "unsafe_raw_output_path",
    "raw_output_hash_mismatch",
    "secret_material_in_raw_output",
    "scorer_version_mismatch",
    "execution_case_set_mismatch",
    "unsupported_pricing_version",
)


class HostileCodeError(Exception):
    code = _SECRET_CANARY


class HostileR803Error(R803EvaluationError):
    @property
    def safe_code(self) -> str:
        return _SECRET_CANARY


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


@pytest.mark.parametrize("code", _SAFE_R803_CODES)
def test_r803_evaluation_error_safe_code_is_closed(code: str) -> None:
    error = R803EvaluationError(f"{code}:{_SECRET_CANARY}")

    assert str(error) == f"{code}:{_SECRET_CANARY}"
    assert error.safe_code == code
    assert _safe_interruption_detail("round_execution_exception", error) == code


def test_interruption_detail_rejects_unknown_or_hostile_codes() -> None:
    unknown = R803EvaluationError(f"unknown_internal_code:{_SECRET_CANARY}")
    mutated = R803EvaluationError("quality_failure_provenance_unresolved")
    object.__setattr__(mutated, "_safe_code_key", _SECRET_CANARY)

    assert unknown.safe_code is None
    assert mutated.safe_code is None
    assert (
        _safe_interruption_detail("round_execution_exception", unknown)
        == "R803EvaluationError"
    )
    assert (
        _safe_interruption_detail("round_execution_exception", mutated)
        == "R803EvaluationError"
    )
    assert (
        _safe_interruption_detail(
            "round_execution_exception",
            HostileR803Error("quality_failure_provenance_unresolved"),
        )
        == "R803EvaluationError"
    )
    assert (
        _safe_interruption_detail("round_execution_exception", HostileCodeError())
        == "Exception"
    )
    assert (
        _safe_interruption_detail(
            "round_execution_exception",
            RuntimeError(_SECRET_CANARY),
        )
        == "RuntimeError"
    )


def test_safe_internal_code_terminal_is_canonical_and_does_not_leak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    campaign_dir = tmp_path / "safe-internal-code"

    def fail_with_safe_code(*_args, **_kwargs):
        raise R803EvaluationError(
            f"quality_failure_provenance_unresolved:{_SECRET_CANARY}"
        )

    monkeypatch.setattr(
        "ai_pdf_worker.r803_evaluation_campaign.run_quick_case_with_diagnostics",
        fail_with_safe_code,
    )
    report = run_or_resume_campaign(
        campaign_dir=campaign_dir,
        provider=CampaignProvider(),
        package=package,
        max_new_rounds=1,
        allow_test_provider=True,
    )

    assert report["status"] == "failed"
    assert report["gates"]["engineering"] == "fail"
    assert report["gates"]["modelQuality"] == "not_evaluable"
    assert report["interruption"]["detail"] == "quality_failure_provenance_unresolved"
    assert _SECRET_CANARY not in json.dumps(report, ensure_ascii=False)
    canary_bytes = _SECRET_CANARY.encode()
    assert all(
        canary_bytes not in path.read_bytes()
        for path in campaign_dir.rglob("*")
        if path.is_file()
    )

    before = {
        path.relative_to(campaign_dir).as_posix(): (
            path.read_bytes(),
            path.stat().st_mtime_ns,
        )
        for path in campaign_dir.rglob("*")
        if path.is_file()
    }

    def provider_must_not_be_configured(*_args, **_kwargs):
        raise AssertionError("terminal resume configured a provider")

    monkeypatch.setattr(
        "ai_pdf_worker.r803_evaluation_campaign.configured_provider",
        provider_must_not_be_configured,
    )
    resumed = run_or_resume_campaign(
        campaign_dir=campaign_dir,
        package=package,
        max_new_rounds=0,
    )
    after = {
        path.relative_to(campaign_dir).as_posix(): (
            path.read_bytes(),
            path.stat().st_mtime_ns,
        )
        for path in campaign_dir.rglob("*")
        if path.is_file()
    }

    assert resumed == report
    assert after == before


def test_preflight_failure_does_not_consume_round_or_write_terminal(
    tmp_path: Path,
) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    campaign_dir = tmp_path / "preflight-failure"

    with pytest.raises(
        R803EvaluationError,
        match="injected_provider_requires_allow_test_provider",
    ):
        run_or_resume_campaign(
            campaign_dir=campaign_dir,
            provider=CampaignProvider(),
            package=package,
            max_new_rounds=1,
        )

    assert not (campaign_dir / "round-01").exists()
    assert not (campaign_dir / "campaign-report.json").exists()
    assert not (campaign_dir / "campaign-report.sha256.json").exists()


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
