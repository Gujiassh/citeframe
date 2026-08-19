from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from ai_pdf_api.services import multimodal_execution as multimodal_execution_service
from ai_pdf_api.services.multimodal_execution import build_multimodal_execution_report
from ai_pdf_api.services.multimodal_execution import (
    _validate_test_source,
    canonical_generation_messages_sha256,
    evaluate_real_model_output,
    load_multimodal_answer_oracle,
)
from ai_pdf_api.services.multimodal_quality import QualityDataError, load_multimodal_quality_suite


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = REPOSITORY_ROOT / "docs/evals/artifacts/m402-v1"
SYSTEM_PROMPT = (
    "Answer only from supplied evidence. If it does not support the question, "
    "state that the selected assets do not contain supporting evidence."
)


def _golden():
    golden, _failures, _report = load_multimodal_quality_suite(
        REPOSITORY_ROOT,
        REPOSITORY_ROOT / "docs/evals/multimodal-golden-v1.json",
        REPOSITORY_ROOT / "docs/evals/multimodal-failures-v1.json",
    )
    return golden


def _real_model_payload() -> dict[str, object]:
    golden = _golden()
    oracle = load_multimodal_answer_oracle(
        REPOSITORY_ROOT,
        REPOSITORY_ROOT / "docs/evals/multimodal-answer-oracle-v1.json",
        golden,
    )
    golden_by_id = {case.id: case for case in golden.cases if case.layer == "answer"}
    fixture_by_id = {fixture.id: fixture for fixture in golden.fixtures}
    cases = []
    for oracle_case in oracle.cases:
        golden_case = golden_by_id[oracle_case.case_id]
        prompt_targets = [
            (target.fixture_id, target.locator_kind)
            for target in golden_case.evidence_targets
        ]
        if not prompt_targets:
            fixture_id = (
                golden_case.scope.selected_fixture_ids[0]
                if golden_case.scope.mode == "selected"
                else golden.fixtures[0].id
            )
            fixture = fixture_by_id[fixture_id]
            prompt_targets = [
                (fixture_id, "pdf_page" if fixture.modality == "pdf" else "image_region")
            ]
        prompt_concepts = " ".join(
            alternatives[0]
            for alternatives in oracle_case.required_prompt_concepts
        ) or "Synthetic fixture contains no answer for this question."
        context_blocks = [
            (
                f"[{index}] {Path(fixture_by_id[fixture_id].source_path).name}, "
                f"{locator_kind}\n"
                f"{prompt_concepts if index == 1 else 'Supporting target evidence.'}"
            )
            for index, (fixture_id, locator_kind) in enumerate(prompt_targets, start=1)
        ]
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Question:\n{golden_case.question}\n\n"
                    f"Asset evidence context:\n{'\n\n'.join(context_blocks)}"
                ),
            },
        ]
        output = (
            " ".join(golden_case.expected_answer_points)
            if golden_case.expected_disposition == "answer"
            else "The selected assets do not contain supporting evidence for that claim."
        )
        evaluation = evaluate_real_model_output(oracle_case, output)
        cases.append(
            {
                "caseId": golden_case.id,
                "question": golden_case.question,
                "generationMessages": messages,
                "generationMessagesSha256": canonical_generation_messages_sha256(messages),
                "provider": "openai",
                "model": "gpt-5.5",
                "output": output,
                "citationCoverage": [
                    {
                        "fixtureId": target.fixture_id,
                        "locatorKind": target.locator_kind,
                        "covered": True,
                    }
                    for target in golden_case.evidence_targets
                ],
                "matchedAnswerPoints": list(evaluation.matched_answer_points),
                "refusalMatched": evaluation.refusal_matched,
                "error": None,
                "passed": evaluation.passed,
            }
        )
    test_file = REPOSITORY_ROOT / "apps/worker/tests/test_multimodal_golden_execution.py"
    return {
        "schemaVersion": "m402-real-model-execution-v1",
        "goldenSchemaVersion": golden.schema_version,
        "testFile": test_file.relative_to(REPOSITORY_ROOT).as_posix(),
        "testFileSha256": sha256(test_file.read_bytes()).hexdigest(),
        "testNode": (
            "apps/worker/tests/test_multimodal_golden_execution.py::"
            "test_m402_worker_executes_every_golden_evidence_target"
        ),
        "cases": cases,
        "passed": True,
    }


def _write_payload(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def repository_real_model_path(tmp_path: Path):
    suffix = sha256(str(tmp_path).encode("utf-8")).hexdigest()[:12]
    path = ARTIFACT_ROOT / f".pytest-real-model-{suffix}.json"
    yield path
    path.unlink(missing_ok=True)


def test_m402_canonical_execution_report_matches_controlled_generator() -> None:
    report = build_multimodal_execution_report(
        REPOSITORY_ROOT,
        _golden(),
        worker_path=ARTIFACT_ROOT / "worker-execution.json",
        desktop_path=ARTIFACT_ROOT / "playwright-desktop.json",
        mobile_path=ARTIFACT_ROOT / "playwright-mobile.json",
        real_model_path=ARTIFACT_ROOT / "real-model-execution.json",
    )
    canonical_path = REPOSITORY_ROOT / "docs/evals/multimodal-execution-v1.json"
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    rendered = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
    assert rendered == canonical_path.read_text(encoding="utf-8")
    assert report["summary"]["releaseGatePassed"] is True
    assert len(report["artifacts"]) == 22
    assert {
        item["path"]: (item["sha256"], item["byteSize"]) for item in report["artifacts"]
    } == {
        item["path"]: (item["sha256"], item["byteSize"]) for item in canonical["artifacts"]
    }


def test_m402_execution_report_accepts_worker_and_real_bff_artifacts() -> None:
    report = build_multimodal_execution_report(
        REPOSITORY_ROOT,
        _golden(),
        worker_path=ARTIFACT_ROOT / "worker-execution.json",
        desktop_path=ARTIFACT_ROOT / "playwright-desktop.json",
        mobile_path=ARTIFACT_ROOT / "playwright-mobile.json",
    )

    summary = report["summary"]
    assert {
        key: summary[key]
        for key in (
            "caseCount",
            "engineeringCaseCount",
            "fullStackEvidenceCaseCount",
            "desktopTargetCount",
            "mobileTargetCount",
            "screenshotCount",
            "scriptedAnswerCaseCount",
            "realModelAnswerCaseCount",
            "engineeringExecutionPassed",
            "fullStackEvidencePassed",
            "realModelQualityPassed",
            "releaseGatePassed",
        )
    } == {
        "caseCount": 21,
        "engineeringCaseCount": 21,
        "fullStackEvidenceCaseCount": 7,
        "desktopTargetCount": 8,
        "mobileTargetCount": 8,
        "screenshotCount": 16,
        "scriptedAnswerCaseCount": 7,
        "realModelAnswerCaseCount": 0,
        "engineeringExecutionPassed": True,
        "fullStackEvidencePassed": True,
        "realModelQualityPassed": False,
        "releaseGatePassed": False,
    }
    assert summary["minimumApprovedCoverageRatio"] >= 0.08
    assert summary["desktopRealBffResponseCount"] >= 20
    assert summary["mobileRealBffResponseCount"] >= 20
    assert len(report["cases"]) == 21
    assert len(report["artifacts"]) == 21
    assert any(
        item["path"] == "docs/evals/m402-execution-source-provenance-v1.json"
        for item in report["artifacts"]
    )
    assert report["pending"] == [
        "Run and approve real-model snapshots for all 7 answer/refusal cases."
    ]


def test_m402_execution_report_rejects_playwright_route_interception(tmp_path: Path) -> None:
    payload = json.loads((ARTIFACT_ROOT / "playwright-desktop.json").read_text(encoding="utf-8"))
    payload["routeInterceptions"] = 1
    tampered = tmp_path / "playwright-desktop.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(QualityDataError, match="routeInterceptions"):
        build_multimodal_execution_report(
            REPOSITORY_ROOT,
            _golden(),
            worker_path=ARTIFACT_ROOT / "worker-execution.json",
            desktop_path=tampered,
            mobile_path=ARTIFACT_ROOT / "playwright-mobile.json",
        )


def test_m402_execution_report_rejects_stale_test_source_hash(tmp_path: Path) -> None:
    payload = json.loads((ARTIFACT_ROOT / "playwright-desktop.json").read_text(encoding="utf-8"))
    payload["testFileSha256"] = "0" * 64
    tampered = tmp_path / "playwright-desktop.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(QualityDataError, match="test source hash drifted"):
        build_multimodal_execution_report(
            REPOSITORY_ROOT,
            _golden(),
            worker_path=ARTIFACT_ROOT / "worker-execution.json",
            desktop_path=tampered,
            mobile_path=ARTIFACT_ROOT / "playwright-mobile.json",
        )


def test_m402_execution_report_rejects_mocked_playwright_source(tmp_path: Path) -> None:
    payload = json.loads((ARTIFACT_ROOT / "playwright-desktop.json").read_text(encoding="utf-8"))
    mocked_test = REPOSITORY_ROOT / "apps/web/e2e/image-region-evidence.spec.ts"
    payload["testFile"] = mocked_test.relative_to(REPOSITORY_ROOT).as_posix()
    payload["testFileSha256"] = sha256(mocked_test.read_bytes()).hexdigest()
    tampered = tmp_path / "playwright-desktop.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(QualityDataError, match="must not intercept routes"):
        build_multimodal_execution_report(
            REPOSITORY_ROOT,
            _golden(),
            worker_path=ARTIFACT_ROOT / "worker-execution.json",
            desktop_path=tampered,
            mobile_path=ARTIFACT_ROOT / "playwright-mobile.json",
        )


def test_m402_execution_report_recomputes_golden_overlap(tmp_path: Path) -> None:
    payload = json.loads((ARTIFACT_ROOT / "playwright-desktop.json").read_text(encoding="utf-8"))
    target = payload["cases"][1]["targets"][0]
    target["renderedRegions"] = [{"x": 0.8, "y": 0.8, "width": 0.1, "height": 0.1}]
    target["minimumApprovedCoverageRatio"] = 1.0
    tampered = tmp_path / "playwright-desktop.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(QualityDataError, match="overlap result drifted"):
        build_multimodal_execution_report(
            REPOSITORY_ROOT,
            _golden(),
            worker_path=ARTIFACT_ROOT / "worker-execution.json",
            desktop_path=tampered,
            mobile_path=ARTIFACT_ROOT / "playwright-mobile.json",
        )


def test_m402_execution_report_independently_accepts_real_model_outputs(
    repository_real_model_path: Path,
) -> None:
    real_model_path = _write_payload(repository_real_model_path, _real_model_payload())

    report = build_multimodal_execution_report(
        REPOSITORY_ROOT,
        _golden(),
        worker_path=ARTIFACT_ROOT / "worker-execution.json",
        desktop_path=ARTIFACT_ROOT / "playwright-desktop.json",
        mobile_path=ARTIFACT_ROOT / "playwright-mobile.json",
        real_model_path=real_model_path,
    )

    assert report["summary"]["realModelAnswerCaseCount"] == 7
    assert report["summary"]["realModelQualityPassed"] is True
    assert report["summary"]["releaseGatePassed"] is True
    assert report["pending"] == []


def test_m402_execution_report_ignores_stale_runner_semantic_diagnostics(
    repository_real_model_path: Path,
) -> None:
    payload = _real_model_payload()
    payload["passed"] = False
    for case in payload["cases"]:
        case["matchedAnswerPoints"] = []
        case["refusalMatched"] = False
        case["passed"] = False
    real_model_path = _write_payload(repository_real_model_path, payload)

    report = build_multimodal_execution_report(
        REPOSITORY_ROOT,
        _golden(),
        worker_path=ARTIFACT_ROOT / "worker-execution.json",
        desktop_path=ARTIFACT_ROOT / "playwright-desktop.json",
        mobile_path=ARTIFACT_ROOT / "playwright-mobile.json",
        real_model_path=real_model_path,
    )

    assert report["summary"]["realModelAnswerCaseCount"] == 7
    assert report["summary"]["releaseGatePassed"] is True


@pytest.mark.parametrize(
    ("case_id", "forged_output"),
    [
        ("answer-pdf-table", "Atlas does not have a score of 91.4."),
        ("answer-pdf-chart", "The trend does not rise after the third point."),
        ("answer-image-trend", "Release 4 begins a sustained increase, not a sustained drop."),
        ("answer-image-constraint", "Verify the chart and caption separately, not together."),
        (
            "answer-mixed-compare",
            "The PDF says Release 4 begins a sustained drop. The image trend rises after the third point.",
        ),
        (
            "answer-refuse-pdf",
            "Atlas consumes 42 kWh, although that value is not mentioned in the fixtures.",
        ),
        (
            "answer-refuse-mixed",
            "The approving production customer was Acme, although it is not mentioned in the fixtures.",
        ),
    ],
)
def test_m402_execution_report_rejects_semantically_opposite_outputs(
    repository_real_model_path: Path,
    case_id: str,
    forged_output: str,
) -> None:
    payload = _real_model_payload()
    forged = next(case for case in payload["cases"] if case["caseId"] == case_id)
    golden_case = next(case for case in _golden().cases if case.id == case_id)
    forged["output"] = forged_output
    forged["matchedAnswerPoints"] = list(golden_case.expected_answer_points)
    forged["refusalMatched"] = golden_case.expected_disposition == "refuse"
    forged["passed"] = True
    real_model_path = _write_payload(repository_real_model_path, payload)

    with pytest.raises(QualityDataError, match="answer oracle failed"):
        build_multimodal_execution_report(
            REPOSITORY_ROOT,
            _golden(),
            worker_path=ARTIFACT_ROOT / "worker-execution.json",
            desktop_path=ARTIFACT_ROOT / "playwright-desktop.json",
            mobile_path=ARTIFACT_ROOT / "playwright-mobile.json",
            real_model_path=real_model_path,
        )


def test_m402_execution_report_rejects_nonproduction_prompt_fixture(
    repository_real_model_path: Path,
) -> None:
    payload = _real_model_payload()
    case = payload["cases"][0]
    case["generationMessages"] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Question: {case['question']}"},
    ]
    case["generationMessagesSha256"] = canonical_generation_messages_sha256(
        case["generationMessages"]
    )
    real_model_path = _write_payload(repository_real_model_path, payload)

    with pytest.raises(QualityDataError, match="production Chat prompt contract"):
        build_multimodal_execution_report(
            REPOSITORY_ROOT,
            _golden(),
            worker_path=ARTIFACT_ROOT / "worker-execution.json",
            desktop_path=ARTIFACT_ROOT / "playwright-desktop.json",
            mobile_path=ARTIFACT_ROOT / "playwright-mobile.json",
            real_model_path=real_model_path,
        )


def test_m402_execution_report_rejects_provider_configuration_drift(
    repository_real_model_path: Path,
) -> None:
    payload = _real_model_payload()
    payload["cases"][0]["provider"] = "scripted"
    real_model_path = _write_payload(repository_real_model_path, payload)

    with pytest.raises(QualityDataError, match="provider configuration drifted"):
        build_multimodal_execution_report(
            REPOSITORY_ROOT,
            _golden(),
            worker_path=ARTIFACT_ROOT / "worker-execution.json",
            desktop_path=ARTIFACT_ROOT / "playwright-desktop.json",
            mobile_path=ARTIFACT_ROOT / "playwright-mobile.json",
            real_model_path=real_model_path,
        )


def test_m402_execution_report_rejects_forged_prompt_hash(
    repository_real_model_path: Path,
) -> None:
    payload = _real_model_payload()
    payload["cases"][0]["generationMessagesSha256"] = "0" * 64
    real_model_path = _write_payload(repository_real_model_path, payload)

    with pytest.raises(QualityDataError, match="prompt hash drifted"):
        build_multimodal_execution_report(
            REPOSITORY_ROOT,
            _golden(),
            worker_path=ARTIFACT_ROOT / "worker-execution.json",
            desktop_path=ARTIFACT_ROOT / "playwright-desktop.json",
            mobile_path=ARTIFACT_ROOT / "playwright-mobile.json",
            real_model_path=real_model_path,
        )


def test_m402_complete_output_allowlist_rejects_every_unreviewed_suffix() -> None:
    golden = _golden()
    oracle = load_multimodal_answer_oracle(
        REPOSITORY_ROOT,
        REPOSITORY_ROOT / "docs/evals/multimodal-answer-oracle-v1.json",
        golden,
    )

    for oracle_case in oracle.cases:
        approved = oracle_case.accepted_complete_outputs[0]
        accepted = evaluate_real_model_output(oracle_case, f"{approved} [1]")
        rejected = evaluate_real_model_output(
            oracle_case,
            f"{approved} An additional unreviewed claim follows.",
        )

        assert accepted.passed is True, oracle_case.case_id
        assert rejected.passed is False, oracle_case.case_id


FROZEN_WORKER_TEST_FILE = "apps/worker/tests/test_multimodal_golden_execution.py"
FROZEN_WORKER_TEST_SHA256 = (
    "fb59ffdeed4122f71f0677772b875009cc439353d7eb57a489ba8274dfe9502c"
)
FROZEN_WORKER_ARTIFACT_PATH = "docs/evals/artifacts/m402-v1/worker-execution.json"
FROZEN_WORKER_ARTIFACT_SHA256 = (
    "10f59a464ba216e959cefa067295ba13f1346b13023f62aa7951341d7dbb58a6"
)
FROZEN_REAL_MODEL_ARTIFACT_PATH = "docs/evals/artifacts/m402-v1/real-model-execution.json"
FROZEN_REAL_MODEL_ARTIFACT_SHA256 = (
    "55d0a545ac8add011d7e16e0f422b2c224636c03d509e5297c951e6d5d6e5ea8"
)


def _provenance_entry(
    *,
    entry_id: str,
    execution_schema_version: str,
    test_file: str,
    test_file_sha256: str,
    execution_artifact_path: str,
    artifact_sha256: str,
) -> dict[str, object]:
    return {
        "id": entry_id,
        "executionSchemaVersion": execution_schema_version,
        "testFile": test_file,
        "testFileSha256": test_file_sha256,
        "executionArtifactPath": execution_artifact_path,
        "artifactSha256": artifact_sha256,
        "originalArtifactCommit": "9aa3bf27ec97a9c0da14cf9e57db38ca0e5a5c3c",
        "originalEmbeddedTestFileSha256": "e6237a76d04a45d71d525121aa3b78f018f2b556b93c1ed98899ad31c61f0f60",
        "originalEmbeddedRunnerCommit": "not-attested",
        "approvedRunnerCommit": "51779de913af094881802056ddd9a4e51c5444d1",
        "identityRepinCommit": "85305e5a447d0c40ed5e4ea9590adb681df827cf",
        "approvalKind": "manual_runner_identity_repin",
        "rationale": "Synthetic provenance fixture for fail-closed regression coverage.",
    }


@pytest.fixture
def repository_scratch_path(tmp_path: Path):
    suffix = sha256(str(tmp_path).encode("utf-8")).hexdigest()[:12]
    path = ARTIFACT_ROOT / f".pytest-scratch-{suffix}.json"
    yield path
    path.unlink(missing_ok=True)


@pytest.fixture
def repository_provenance_path(tmp_path: Path):
    suffix = sha256(str(tmp_path).encode("utf-8")).hexdigest()[:12]
    path = ARTIFACT_ROOT / f".pytest-provenance-{suffix}.json"
    yield path
    path.unlink(missing_ok=True)


def test_m402_frozen_worker_artifact_accepted_via_provenance_contract() -> None:
    report = build_multimodal_execution_report(
        REPOSITORY_ROOT,
        _golden(),
        worker_path=ARTIFACT_ROOT / "worker-execution.json",
        desktop_path=ARTIFACT_ROOT / "playwright-desktop.json",
        mobile_path=ARTIFACT_ROOT / "playwright-mobile.json",
    )
    assert report["summary"]["engineeringExecutionPassed"] is True
    worker_bytes = (ARTIFACT_ROOT / "worker-execution.json").read_bytes()
    worker = json.loads(worker_bytes.decode("utf-8"))
    assert worker["testFileSha256"] == FROZEN_WORKER_TEST_SHA256
    assert sha256(worker_bytes).hexdigest() == FROZEN_WORKER_ARTIFACT_SHA256
    assert worker["testFileSha256"] != sha256(
        (REPOSITORY_ROOT / FROZEN_WORKER_TEST_FILE).read_bytes()
    ).hexdigest()


def test_m402_frozen_real_model_artifact_accepted_via_provenance_contract() -> None:
    report = build_multimodal_execution_report(
        REPOSITORY_ROOT,
        _golden(),
        worker_path=ARTIFACT_ROOT / "worker-execution.json",
        desktop_path=ARTIFACT_ROOT / "playwright-desktop.json",
        mobile_path=ARTIFACT_ROOT / "playwright-mobile.json",
        real_model_path=ARTIFACT_ROOT / "real-model-execution.json",
    )
    assert report["summary"]["realModelQualityPassed"] is True
    assert report["summary"]["releaseGatePassed"] is True
    real_bytes = (ARTIFACT_ROOT / "real-model-execution.json").read_bytes()
    real_model = json.loads(real_bytes.decode("utf-8"))
    assert real_model["testFileSha256"] == FROZEN_WORKER_TEST_SHA256
    assert sha256(real_bytes).hexdigest() == FROZEN_REAL_MODEL_ARTIFACT_SHA256


def test_m402_current_generated_real_model_payload_uses_live_source_hash(
    repository_real_model_path: Path,
) -> None:
    payload = _real_model_payload()
    current_hash = sha256((REPOSITORY_ROOT / FROZEN_WORKER_TEST_FILE).read_bytes()).hexdigest()
    assert payload["testFileSha256"] == current_hash
    assert payload["testFileSha256"] != FROZEN_WORKER_TEST_SHA256
    real_model_path = _write_payload(repository_real_model_path, payload)

    report = build_multimodal_execution_report(
        REPOSITORY_ROOT,
        _golden(),
        worker_path=ARTIFACT_ROOT / "worker-execution.json",
        desktop_path=ARTIFACT_ROOT / "playwright-desktop.json",
        mobile_path=ARTIFACT_ROOT / "playwright-mobile.json",
        real_model_path=real_model_path,
    )
    assert report["summary"]["realModelQualityPassed"] is True
    assert report["summary"]["releaseGatePassed"] is True


def test_m402_report_rejects_screenshot_path_colliding_with_execution_artifact(
    repository_scratch_path: Path,
) -> None:
    payload = json.loads((ARTIFACT_ROOT / "playwright-desktop.json").read_text(encoding="utf-8"))
    payload["cases"][0]["targets"][0]["screenshotPath"] = FROZEN_WORKER_ARTIFACT_PATH
    repository_scratch_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(QualityDataError, match="duplicate artifact path|artifact path collision"):
        build_multimodal_execution_report(
            REPOSITORY_ROOT,
            _golden(),
            worker_path=ARTIFACT_ROOT / "worker-execution.json",
            desktop_path=repository_scratch_path,
            mobile_path=ARTIFACT_ROOT / "playwright-mobile.json",
        )


def test_m402_report_binds_execution_artifact_to_first_parsed_bytes(
    repository_real_model_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _real_model_payload()
    first_bytes = json.dumps(payload).encode("utf-8")
    first_sha = sha256(first_bytes).hexdigest()
    repository_real_model_path.write_bytes(first_bytes)
    target = repository_real_model_path.resolve()
    read_count = {"value": 0}
    original_read_bytes = Path.read_bytes

    def tracked_read_bytes(self: Path) -> bytes:
        payload_bytes = original_read_bytes(self)
        if self.resolve() == target:
            read_count["value"] += 1
            if read_count["value"] == 1:
                replacement = json.loads(payload_bytes.decode("utf-8"))
                replacement["cases"][0]["provider"] = "scripted"
                replacement["cases"][0]["output"] = "tampered-after-first-read"
                self.write_bytes(json.dumps(replacement).encode("utf-8"))
        return payload_bytes

    monkeypatch.setattr(Path, "read_bytes", tracked_read_bytes)

    report = build_multimodal_execution_report(
        REPOSITORY_ROOT,
        _golden(),
        worker_path=ARTIFACT_ROOT / "worker-execution.json",
        desktop_path=ARTIFACT_ROOT / "playwright-desktop.json",
        mobile_path=ARTIFACT_ROOT / "playwright-mobile.json",
        real_model_path=repository_real_model_path,
    )

    relative = repository_real_model_path.relative_to(REPOSITORY_ROOT).as_posix()
    record = next(item for item in report["artifacts"] if item["path"] == relative)
    assert read_count["value"] == 1
    assert record["sha256"] == first_sha
    assert record["byteSize"] == len(first_bytes)
    assert report["summary"]["realModelQualityPassed"] is True
    assert report["summary"]["releaseGatePassed"] is True
    assert report["cases"][14]["realModel"]["provider"] != "scripted"
    assert report["cases"][14]["realModel"]["output"] != "tampered-after-first-read"
    assert len(report["artifacts"]) == 22
    assert any(
        item["path"] == "docs/evals/m402-execution-source-provenance-v1.json"
        for item in report["artifacts"]
    )


def test_m402_report_rejects_alternating_provenance_snapshot_splicing(
    repository_provenance_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker_only = {
        "schemaVersion": "m402-execution-source-provenance-v1",
        "entries": [
            _provenance_entry(
                entry_id="worker-only",
                execution_schema_version="m402-worker-execution-v1",
                test_file=FROZEN_WORKER_TEST_FILE,
                test_file_sha256=FROZEN_WORKER_TEST_SHA256,
                execution_artifact_path=FROZEN_WORKER_ARTIFACT_PATH,
                artifact_sha256=FROZEN_WORKER_ARTIFACT_SHA256,
            )
        ],
    }
    real_model_only = {
        "schemaVersion": "m402-execution-source-provenance-v1",
        "entries": [
            _provenance_entry(
                entry_id="real-model-only",
                execution_schema_version="m402-real-model-execution-v1",
                test_file=FROZEN_WORKER_TEST_FILE,
                test_file_sha256=FROZEN_WORKER_TEST_SHA256,
                execution_artifact_path=FROZEN_REAL_MODEL_ARTIFACT_PATH,
                artifact_sha256=FROZEN_REAL_MODEL_ARTIFACT_SHA256,
            )
        ],
    }
    snapshots = [worker_only, real_model_only]
    read_count = {"value": 0}
    original_read_bytes = Path.read_bytes
    target = repository_provenance_path.resolve()

    def alternating_read_bytes(self: Path) -> bytes:
        if self.resolve() == target:
            read_count["value"] += 1
            index = min(read_count["value"] - 1, len(snapshots) - 1)
            return json.dumps(snapshots[index]).encode("utf-8")
        return original_read_bytes(self)

    # Seed a real file so path resolution succeeds; bytes come from the monkeypatch.
    repository_provenance_path.write_text(json.dumps(worker_only), encoding="utf-8")
    monkeypatch.setattr(Path, "read_bytes", alternating_read_bytes)
    monkeypatch.setattr(
        multimodal_execution_service,
        "_DEFAULT_EXECUTION_SOURCE_PROVENANCE_PATH",
        repository_provenance_path.relative_to(REPOSITORY_ROOT),
    )

    with pytest.raises(QualityDataError, match="test source hash drifted"):
        build_multimodal_execution_report(
            REPOSITORY_ROOT,
            _golden(),
            worker_path=ARTIFACT_ROOT / "worker-execution.json",
            desktop_path=ARTIFACT_ROOT / "playwright-desktop.json",
            mobile_path=ARTIFACT_ROOT / "playwright-mobile.json",
            real_model_path=ARTIFACT_ROOT / "real-model-execution.json",
        )
    assert read_count["value"] == 1


def test_m402_spoofed_approved_runner_hash_on_new_artifact_rejected_before_semantics(
    repository_real_model_path: Path,
) -> None:
    payload = _real_model_payload()
    payload["testFileSha256"] = FROZEN_WORKER_TEST_SHA256
    payload["cases"][0]["provider"] = "scripted"
    real_model_path = _write_payload(repository_real_model_path, payload)

    with pytest.raises(QualityDataError, match="test source hash drifted"):
        build_multimodal_execution_report(
            REPOSITORY_ROOT,
            _golden(),
            worker_path=ARTIFACT_ROOT / "worker-execution.json",
            desktop_path=ARTIFACT_ROOT / "playwright-desktop.json",
            mobile_path=ARTIFACT_ROOT / "playwright-mobile.json",
            real_model_path=real_model_path,
        )


def test_m402_copied_frozen_artifact_path_rejected(
    repository_scratch_path: Path,
) -> None:
    original = (ARTIFACT_ROOT / "worker-execution.json").read_bytes()
    repository_scratch_path.write_bytes(original)
    assert sha256(original).hexdigest() == FROZEN_WORKER_ARTIFACT_SHA256

    with pytest.raises(QualityDataError, match="test source hash drifted"):
        build_multimodal_execution_report(
            REPOSITORY_ROOT,
            _golden(),
            worker_path=repository_scratch_path,
            desktop_path=ARTIFACT_ROOT / "playwright-desktop.json",
            mobile_path=ARTIFACT_ROOT / "playwright-mobile.json",
        )


def test_m402_tampered_frozen_artifact_bytes_rejected(
    repository_scratch_path: Path,
) -> None:
    payload = json.loads((ARTIFACT_ROOT / "worker-execution.json").read_text(encoding="utf-8"))
    payload["cases"][0]["passed"] = False
    repository_scratch_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(QualityDataError, match="test source hash drifted"):
        _validate_test_source(
            REPOSITORY_ROOT,
            FROZEN_WORKER_TEST_FILE,
            FROZEN_WORKER_TEST_SHA256,
            execution_schema_version="m402-worker-execution-v1",
            execution_artifact_path=FROZEN_WORKER_ARTIFACT_PATH,
            execution_artifact_sha256=sha256(repository_scratch_path.read_bytes()).hexdigest(),
        )


def test_m402_wrong_artifact_hash_at_approved_path_rejected() -> None:
    with pytest.raises(QualityDataError, match="test source hash drifted"):
        _validate_test_source(
            REPOSITORY_ROOT,
            FROZEN_WORKER_TEST_FILE,
            FROZEN_WORKER_TEST_SHA256,
            execution_schema_version="m402-worker-execution-v1",
            execution_artifact_path=FROZEN_WORKER_ARTIFACT_PATH,
            execution_artifact_sha256="0" * 64,
        )


def test_m402_provenance_rejects_cross_schema_historical_hash() -> None:
    with pytest.raises(QualityDataError, match="test source hash drifted"):
        _validate_test_source(
            REPOSITORY_ROOT,
            FROZEN_WORKER_TEST_FILE,
            FROZEN_WORKER_TEST_SHA256,
            execution_schema_version="m402-playwright-evidence-v1",
            execution_artifact_path=FROZEN_WORKER_ARTIFACT_PATH,
            execution_artifact_sha256=FROZEN_WORKER_ARTIFACT_SHA256,
        )


def test_m402_provenance_rejects_path_only_historical_match(
    repository_provenance_path: Path,
) -> None:
    contract = {
        "schemaVersion": "m402-execution-source-provenance-v1",
        "entries": [
            _provenance_entry(
                entry_id="wrong-runner-path",
                execution_schema_version="m402-worker-execution-v1",
                test_file="apps/web/e2e/multimodal-fullstack.spec.ts",
                test_file_sha256=FROZEN_WORKER_TEST_SHA256,
                execution_artifact_path=FROZEN_WORKER_ARTIFACT_PATH,
                artifact_sha256=FROZEN_WORKER_ARTIFACT_SHA256,
            )
        ],
    }
    repository_provenance_path.write_text(json.dumps(contract), encoding="utf-8")

    with pytest.raises(QualityDataError, match="test source hash drifted"):
        _validate_test_source(
            REPOSITORY_ROOT,
            FROZEN_WORKER_TEST_FILE,
            FROZEN_WORKER_TEST_SHA256,
            execution_schema_version="m402-worker-execution-v1",
            execution_artifact_path=FROZEN_WORKER_ARTIFACT_PATH,
            execution_artifact_sha256=FROZEN_WORKER_ARTIFACT_SHA256,
            provenance_path=repository_provenance_path,
        )


def test_m402_provenance_rejects_hash_only_schema_mismatch(
    repository_provenance_path: Path,
) -> None:
    contract = {
        "schemaVersion": "m402-execution-source-provenance-v1",
        "entries": [
            _provenance_entry(
                entry_id="hash-only",
                execution_schema_version="m402-real-model-execution-v1",
                test_file=FROZEN_WORKER_TEST_FILE,
                test_file_sha256=FROZEN_WORKER_TEST_SHA256,
                execution_artifact_path=FROZEN_WORKER_ARTIFACT_PATH,
                artifact_sha256=FROZEN_WORKER_ARTIFACT_SHA256,
            )
        ],
    }
    repository_provenance_path.write_text(json.dumps(contract), encoding="utf-8")

    with pytest.raises(QualityDataError, match="test source hash drifted"):
        _validate_test_source(
            REPOSITORY_ROOT,
            FROZEN_WORKER_TEST_FILE,
            FROZEN_WORKER_TEST_SHA256,
            execution_schema_version="m402-worker-execution-v1",
            execution_artifact_path=FROZEN_WORKER_ARTIFACT_PATH,
            execution_artifact_sha256=FROZEN_WORKER_ARTIFACT_SHA256,
            provenance_path=repository_provenance_path,
        )


def test_m402_provenance_missing_contract_fail_closed() -> None:
    missing = ARTIFACT_ROOT / ".pytest-provenance-missing-does-not-exist.json"
    with pytest.raises(QualityDataError, match="provenance|missing|outside"):
        _validate_test_source(
            REPOSITORY_ROOT,
            FROZEN_WORKER_TEST_FILE,
            FROZEN_WORKER_TEST_SHA256,
            execution_schema_version="m402-worker-execution-v1",
            execution_artifact_path=FROZEN_WORKER_ARTIFACT_PATH,
            execution_artifact_sha256=FROZEN_WORKER_ARTIFACT_SHA256,
            provenance_path=missing,
        )


def test_m402_provenance_malformed_contract_fail_closed(
    repository_provenance_path: Path,
) -> None:
    repository_provenance_path.write_text(
        json.dumps(
            {
                "schemaVersion": "m402-execution-source-provenance-v1",
                "entries": [
                    {
                        "id": "incomplete",
                        "executionSchemaVersion": "m402-worker-execution-v1",
                        "testFile": FROZEN_WORKER_TEST_FILE,
                        "testFileSha256": FROZEN_WORKER_TEST_SHA256,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(QualityDataError, match="Invalid M402 execution source provenance"):
        _validate_test_source(
            REPOSITORY_ROOT,
            FROZEN_WORKER_TEST_FILE,
            FROZEN_WORKER_TEST_SHA256,
            execution_schema_version="m402-worker-execution-v1",
            execution_artifact_path=FROZEN_WORKER_ARTIFACT_PATH,
            execution_artifact_sha256=FROZEN_WORKER_ARTIFACT_SHA256,
            provenance_path=repository_provenance_path,
        )


def test_m402_provenance_rejects_invalid_json_contract(
    repository_provenance_path: Path,
) -> None:
    repository_provenance_path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(QualityDataError, match="Invalid M402 execution source provenance"):
        _validate_test_source(
            REPOSITORY_ROOT,
            FROZEN_WORKER_TEST_FILE,
            FROZEN_WORKER_TEST_SHA256,
            execution_schema_version="m402-worker-execution-v1",
            execution_artifact_path=FROZEN_WORKER_ARTIFACT_PATH,
            execution_artifact_sha256=FROZEN_WORKER_ARTIFACT_SHA256,
            provenance_path=repository_provenance_path,
        )


def _assert_invalid_provenance_contract(
    repository_provenance_path: Path,
    contract: dict[str, object],
) -> None:
    repository_provenance_path.write_text(json.dumps(contract), encoding="utf-8")
    with pytest.raises(QualityDataError, match="Invalid M402 execution source provenance"):
        _validate_test_source(
            REPOSITORY_ROOT,
            FROZEN_WORKER_TEST_FILE,
            FROZEN_WORKER_TEST_SHA256,
            execution_schema_version="m402-worker-execution-v1",
            execution_artifact_path=FROZEN_WORKER_ARTIFACT_PATH,
            execution_artifact_sha256=FROZEN_WORKER_ARTIFACT_SHA256,
            provenance_path=repository_provenance_path,
        )


def test_m402_provenance_rejects_unknown_top_level_field(
    repository_provenance_path: Path,
) -> None:
    _assert_invalid_provenance_contract(
        repository_provenance_path,
        {
            "schemaVersion": "m402-execution-source-provenance-v1",
            "entries": [
                _provenance_entry(
                    entry_id="ok",
                    execution_schema_version="m402-worker-execution-v1",
                    test_file=FROZEN_WORKER_TEST_FILE,
                    test_file_sha256=FROZEN_WORKER_TEST_SHA256,
                    execution_artifact_path=FROZEN_WORKER_ARTIFACT_PATH,
                    artifact_sha256=FROZEN_WORKER_ARTIFACT_SHA256,
                )
            ],
            "unexpectedTopLevel": True,
        },
    )


def test_m402_provenance_rejects_unknown_entry_field(
    repository_provenance_path: Path,
) -> None:
    entry = _provenance_entry(
        entry_id="ok",
        execution_schema_version="m402-worker-execution-v1",
        test_file=FROZEN_WORKER_TEST_FILE,
        test_file_sha256=FROZEN_WORKER_TEST_SHA256,
        execution_artifact_path=FROZEN_WORKER_ARTIFACT_PATH,
        artifact_sha256=FROZEN_WORKER_ARTIFACT_SHA256,
    )
    entry["unexpectedEntryField"] = "nope"
    _assert_invalid_provenance_contract(
        repository_provenance_path,
        {
            "schemaVersion": "m402-execution-source-provenance-v1",
            "entries": [entry],
        },
    )


def test_m402_provenance_rejects_duplicate_entry_id(
    repository_provenance_path: Path,
) -> None:
    _assert_invalid_provenance_contract(
        repository_provenance_path,
        {
            "schemaVersion": "m402-execution-source-provenance-v1",
            "entries": [
                _provenance_entry(
                    entry_id="dup-id",
                    execution_schema_version="m402-worker-execution-v1",
                    test_file=FROZEN_WORKER_TEST_FILE,
                    test_file_sha256=FROZEN_WORKER_TEST_SHA256,
                    execution_artifact_path=FROZEN_WORKER_ARTIFACT_PATH,
                    artifact_sha256=FROZEN_WORKER_ARTIFACT_SHA256,
                ),
                _provenance_entry(
                    entry_id="dup-id",
                    execution_schema_version="m402-real-model-execution-v1",
                    test_file=FROZEN_WORKER_TEST_FILE,
                    test_file_sha256=FROZEN_WORKER_TEST_SHA256,
                    execution_artifact_path=FROZEN_REAL_MODEL_ARTIFACT_PATH,
                    artifact_sha256=FROZEN_REAL_MODEL_ARTIFACT_SHA256,
                ),
            ],
        },
    )


def test_m402_provenance_rejects_duplicate_complete_identity(
    repository_provenance_path: Path,
) -> None:
    entry = _provenance_entry(
        entry_id="identity-a",
        execution_schema_version="m402-worker-execution-v1",
        test_file=FROZEN_WORKER_TEST_FILE,
        test_file_sha256=FROZEN_WORKER_TEST_SHA256,
        execution_artifact_path=FROZEN_WORKER_ARTIFACT_PATH,
        artifact_sha256=FROZEN_WORKER_ARTIFACT_SHA256,
    )
    duplicate = dict(entry)
    duplicate["id"] = "identity-b"
    _assert_invalid_provenance_contract(
        repository_provenance_path,
        {
            "schemaVersion": "m402-execution-source-provenance-v1",
            "entries": [entry, duplicate],
        },
    )


def test_m402_provenance_rejects_duplicate_execution_artifact_path(
    repository_provenance_path: Path,
) -> None:
    _assert_invalid_provenance_contract(
        repository_provenance_path,
        {
            "schemaVersion": "m402-execution-source-provenance-v1",
            "entries": [
                _provenance_entry(
                    entry_id="path-a",
                    execution_schema_version="m402-worker-execution-v1",
                    test_file=FROZEN_WORKER_TEST_FILE,
                    test_file_sha256=FROZEN_WORKER_TEST_SHA256,
                    execution_artifact_path=FROZEN_WORKER_ARTIFACT_PATH,
                    artifact_sha256=FROZEN_WORKER_ARTIFACT_SHA256,
                ),
                _provenance_entry(
                    entry_id="path-b",
                    execution_schema_version="m402-real-model-execution-v1",
                    test_file=FROZEN_WORKER_TEST_FILE,
                    test_file_sha256=FROZEN_WORKER_TEST_SHA256,
                    execution_artifact_path=FROZEN_WORKER_ARTIFACT_PATH,
                    artifact_sha256="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                ),
            ],
        },
    )
