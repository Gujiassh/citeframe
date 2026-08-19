from __future__ import annotations

import json
from pathlib import Path

import ai_pdf_worker.r803_evaluation_contract as evaluation_contract
import ai_pdf_worker.r803_evaluation_provider as evaluation_provider
import httpx
import pytest
from ai_pdf_api.services.evaluation import parse_evaluation_report
from ai_pdf_api.services.providers import ModelProviderError
from ai_pdf_worker.r803_evaluation import run_paired_evaluation, write_result
from ai_pdf_worker.r803_evaluation_contract import (
    DEFAULT_PACKAGE_PATH,
    R803EvaluationError,
    load_evaluation_package,
)
from ai_pdf_worker.r803_evaluation_provider import ProviderResult, RecordedProviderError
from ai_pdf_worker.r803_structured_output import (
    PROVIDER_RESULT_SCHEMAS,
    QUICK_RESULT_SCHEMA,
    STRUCTURED_OUTPUT_TRANSPORT_VERSION,
    structured_output_format,
)
from ai_pdf_worker.research_agent_schemas import AGENT_RESULT_SCHEMAS

pytestmark = pytest.mark.evaluation


class DeterministicProvider:
    provider = "openai"
    model = "gpt-5.5"

    def generate(self, messages, *, node_key: str) -> ProviderResult:
        if node_key == "quick":
            payload = self._quick(str(messages[-1]["content"]))
        else:
            variables = json.loads(str(messages[-1]["content"]))
            payload = getattr(self, f"_{node_key}")(variables)
        return ProviderResult(
            output=json.dumps(payload, sort_keys=True, separators=(",", ":")),
            input_tokens=10,
            output_tokens=5,
            usage_final=True,
        )

    @staticmethod
    def _quick(content: str) -> dict[str, object]:
        question = content.split("Question:\n", 1)[1].split("\n\nAsset evidence context:", 1)[0]
        cases = {
            "Compare the change described by the PDF chart with the image observation.": {
                "answer": "The PDF trend rises after the third point, while the image says Release 4 begins the sustained drop.",
                "claims": [
                    {"text": "The PDF trend rises after the third point.", "evidenceIds": ["answer-pdf-chart"]},
                    {"text": "The image says Release 4 begins the sustained drop.", "evidenceIds": ["answer-image-trend"]},
                ],
                "conflictDetected": True,
            },
            "Summarize the Atlas score and the image's verification constraint.": {
                "answer": "Atlas has a score of 91.4. Verify the chart and caption together.",
                "claims": [
                    {"text": "Atlas has a score of 91.4.", "evidenceIds": ["answer-pdf-table"]},
                    {"text": "Verify the chart and caption together.", "evidenceIds": ["answer-image-constraint"]},
                ],
                "conflictDetected": False,
            },
            "Are the PDF trend and the image observation directionally consistent? Explain the conflict.": {
                "answer": "They conflict: the PDF trend rises, while the image observation falls in a sustained drop.",
                "claims": [
                    {"text": "The PDF trend rises after the third point.", "evidenceIds": ["answer-pdf-chart"]},
                    {"text": "The image observation falls in a sustained drop.", "evidenceIds": ["answer-image-trend"]},
                ],
                "conflictDetected": True,
            },
            "What evidence must be checked together before accepting the image observation?": {
                "answer": "Verify the chart and caption together.",
                "claims": [
                    {"text": "Verify the chart and caption together.", "evidenceIds": ["answer-image-constraint"]}
                ],
                "conflictDetected": False,
            },
            "What energy consumption does the PDF report for Atlas?": {
                "answer": "The selected assets do not contain supporting evidence for Atlas energy consumption.",
                "claims": [],
                "conflictDetected": False,
            },
            "Which production customer approved the release shown in these fixtures?": {
                "answer": "The selected assets do not contain supporting evidence identifying a production customer.",
                "claims": [],
                "conflictDetected": False,
            },
        }
        return cases[question]

    @staticmethod
    def _planner(variables: dict[str, object]) -> dict[str, object]:
        scope = variables["frozenAssetScope"]
        assert isinstance(scope, dict)
        assets = scope["assets"]
        assert isinstance(assets, list)
        return {
            "summary": "Evaluate the frozen evidence scope.",
            "knownGaps": [],
            "estimatedProviderCalls": 5,
            "subproblems": [
                {
                    "question": variables["question"],
                    "assetIds": [item["assetId"] for item in assets],
                    "expectedEvidence": [],
                }
            ],
        }

    @staticmethod
    def _researcher(variables: dict[str, object]) -> dict[str, object]:
        subproblem = variables["subproblem"]
        tools = variables["toolContracts"]
        assert isinstance(subproblem, dict) and isinstance(tools, dict)
        question = str(subproblem["question"]).casefold()
        evidence = tools["evidence"]
        assert isinstance(evidence, list)
        claims: list[dict[str, object]] = []
        for item in evidence:
            content = str(item["content"])
            lowered = content.casefold()
            selected = False
            if "energy consumption" in question or "production customer" in question:
                selected = False
            elif "compare the change" in question or "directionally consistent" in question:
                selected = "trend rises" in lowered or "latency falls" in lowered
            elif "atlas score" in question:
                selected = "atlas" in lowered or "verify chart" in lowered
            elif "checked together" in question:
                selected = "verify chart" in lowered
            if selected:
                claims.append(
                    {
                        "text": f"{item['assetId']}: {content}",
                        "evidenceHandleIds": [item["evidenceHandle"]],
                    }
                )
        return {"claims": claims}

    @staticmethod
    def _verifier(variables: dict[str, object]) -> dict[str, object]:
        claims = variables["claims"]
        assert isinstance(claims, list)
        return {"claims": [{"id": item["id"], "status": "supported"} for item in claims]}

    @staticmethod
    def _critic(variables: dict[str, object]) -> dict[str, object]:
        claims = variables["claims"]
        assert isinstance(claims, list)
        combined = " ".join(str(item["text"]) for item in claims).casefold()
        conflict_ids = [item["id"] for item in claims] if "trend rises" in combined and "latency falls" in combined else []
        return {"conflictClaimIds": conflict_ids}

    @staticmethod
    def _synthesizer(variables: dict[str, object]) -> dict[str, object]:
        claims = variables["claims"]
        assert isinstance(claims, list)
        return {
            "factClaimIds": [item["id"] for item in claims if item["conflictStatus"] == "none"],
            "unresolvedClaimIds": [
                item["id"] for item in claims if item["conflictStatus"] == "resolved_unresolved"
            ],
        }


def test_package_freezes_expected_comparison_keys() -> None:
    package = load_evaluation_package()
    assert package.comparison_keys.fixture_manifest_sha256 == "acc5ca446127d8dbb144f810324c8bb01a5f98cf8f95a672804e46293d32b377"
    assert package.comparison_keys.asset_scope_sha256 == "35a2ba92905cd87d5c85a6f86464a297d649e94bb9ab9a3dd7ca75da3f4c06e2"
    assert package.comparison_keys.provider_profile_sha256 == "250a6b422cc64f05839658f3d990279c05e221c1714e01ca58afbfd29e8c1290"
    assert (package.comparison_keys.provider, package.comparison_keys.model) == ("openai", "gpt-5.5")
    assert len(package.cases) == 6
    assert set(package.assets) == {"pdf-coordinate", "pdf-artifact-matrix", "image-coordinate"}


def test_package_v1_is_not_silently_reinterpreted() -> None:
    for version in ("v1", "v2", "v3"):
        with pytest.raises(R803EvaluationError, match="unsupported_package_schema"):
            load_evaluation_package(Path(f"docs/evals/r803-evaluation-package-{version}.json"))


def test_provider_schema_is_strict_and_drops_only_unsupported_keywords() -> None:
    assert QUICK_RESULT_SCHEMA["properties"] != PROVIDER_RESULT_SCHEMAS["quick"]["properties"]
    assert PROVIDER_RESULT_SCHEMAS["quick"]["additionalProperties"] is False
    assert PROVIDER_RESULT_SCHEMAS["quick"]["required"] == QUICK_RESULT_SCHEMA["required"]
    serialized = json.dumps(PROVIDER_RESULT_SCHEMAS)
    for keyword in ("minLength", "maxLength", "maxItems", "minimum", "uniqueItems"):
        assert keyword not in serialized
    claims = PROVIDER_RESULT_SCHEMAS["researcher"]["properties"]["claims"]
    assert claims["items"]["properties"]["evidenceHandleIds"]["minItems"] == 1
    assert structured_output_format("quick") == {
        "type": "json_schema",
        "name": "r803_quick_v2",
        "strict": True,
        "schema": PROVIDER_RESULT_SCHEMAS["quick"],
    }


def test_real_provider_injects_versioned_strict_format(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def post(url: str, *, json: object, headers: dict[str, str], timeout: float) -> httpx.Response:
        captured.update({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"answer":"ok","claims":[],"conflictDetected":false}',
                            }
                        ]
                    }
                ],
                "usage": {"input_tokens": 7, "output_tokens": 3},
            },
        )

    monkeypatch.setattr(evaluation_provider.httpx, "post", post)
    provider = evaluation_provider.OpenAIRecordedProvider(
        model="gpt-5.5",
        api_key="test-key",
        api_base="https://example.test/v1",
        timeout_seconds=2,
        max_output_tokens=100,
        structured_output_transport=STRUCTURED_OUTPUT_TRANSPORT_VERSION,
    )

    result = provider.generate([{"role": "user", "content": "question"}], node_key="quick")

    assert result.output == '{"answer":"ok","claims":[],"conflictDetected":false}'
    assert captured["json"] == {
        "model": "gpt-5.5",
        "input": [{"role": "user", "content": "question"}],
        "max_output_tokens": 100,
        "text": {"format": structured_output_format("quick")},
    }


def test_real_provider_preserves_usage_on_incomplete_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def post(*_args: object, **_kwargs: object) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
                "output": [{"type": "reasoning", "content": []}],
                "usage": {"input_tokens": 17, "output_tokens": 100},
            },
        )

    monkeypatch.setattr(evaluation_provider.httpx, "post", post)
    provider = evaluation_provider.OpenAIRecordedProvider(
        model="gpt-5.5",
        api_key="test-key",
        api_base="https://example.test",
        timeout_seconds=2,
        max_output_tokens=100,
        structured_output_transport=STRUCTURED_OUTPUT_TRANSPORT_VERSION,
    )

    with pytest.raises(RecordedProviderError) as captured:
        provider.generate([{"role": "user", "content": "question"}], node_key="planner")

    assert captured.value.code == "generation_incomplete_response"
    assert (captured.value.input_tokens, captured.value.output_tokens) == (17, 100)
    assert captured.value.usage_final is True


def test_real_provider_classifies_non_json_4xx_as_permanent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        evaluation_provider.httpx,
        "post",
        lambda *_args, **_kwargs: httpx.Response(400, text="invalid schema"),
    )
    provider = evaluation_provider.OpenAIRecordedProvider(
        model="gpt-5.5",
        api_key="test-key",
        api_base="https://example.test",
        timeout_seconds=2,
        max_output_tokens=100,
        structured_output_transport=STRUCTURED_OUTPUT_TRANSPORT_VERSION,
    )

    with pytest.raises(RecordedProviderError) as captured:
        provider.generate([{"role": "user", "content": "question"}], node_key="quick")

    assert captured.value.code == "generation_provider_error"


def test_paired_evaluation_is_importable_and_keeps_gates_separate(tmp_path: Path) -> None:
    result = run_paired_evaluation(provider=DeterministicProvider())
    quick = parse_evaluation_report(json.dumps(result.quick_report, sort_keys=True, separators=(",", ":")).encode())
    research = parse_evaluation_report(json.dumps(result.research_report, sort_keys=True, separators=(",", ":")).encode())

    assert quick.evaluation.status == research.evaluation.status == "completed"
    assert quick.evaluation.provider_calls == 6
    assert research.evaluation.provider_calls == 30
    assert quick.evaluation.claim_support_rate.value == research.evaluation.claim_support_rate.value == 1.0
    assert quick.evaluation.evidence_precision.value == research.evaluation.evidence_precision.value == 1.0
    assert quick.evaluation.model_quality_gate == research.evaluation.model_quality_gate == "not_evaluable"
    assert quick.evaluation.user_value_gate == research.evaluation.user_value_gate == "not_evaluable"
    assert result.paired_report["comparisonKeysMatch"] is True
    assert result.paired_report["gates"]["modelQualityReason"] == "single_sample_no_release_threshold"
    assert result.paired_report["sample"]["independentExecutionsPerCaseAndMode"] == 1

    hashes = write_result(result, tmp_path)
    assert set(hashes) == {
        "SHA256SUMS",
        "paired-quality-report.json",
        "quick-evaluation.json",
        "research-evaluation.json",
    }
    parse_evaluation_report((tmp_path / "quick-evaluation.json").read_bytes())
    parse_evaluation_report((tmp_path / "research-evaluation.json").read_bytes())


def test_write_result_refuses_to_overwrite_existing_evidence(tmp_path: Path) -> None:
    (tmp_path / "retained.json").write_text("retained", encoding="utf-8")

    with pytest.raises(R803EvaluationError, match="output_directory_not_empty"):
        write_result(run_paired_evaluation(provider=DeterministicProvider()), tmp_path)

    assert (tmp_path / "retained.json").read_text(encoding="utf-8") == "retained"


def test_package_rejects_frozen_artifact_hash_drift(tmp_path: Path) -> None:
    document = json.loads(DEFAULT_PACKAGE_PATH.read_text(encoding="utf-8"))
    document["suite"]["caseManifestSha256"] = "0" * 64
    path = tmp_path / "package.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(R803EvaluationError, match="artifact_hash_mismatch"):
        load_evaluation_package(path)


def test_package_rejects_artifact_paths_outside_repository(tmp_path: Path) -> None:
    external = tmp_path / "external.pdf"
    external.write_bytes(b"external")
    document = json.loads(DEFAULT_PACKAGE_PATH.read_text(encoding="utf-8"))
    document["assets"][0]["sourcePath"] = str(external)
    document["assets"][0]["sourceSha256"] = "3c4623849a49a5392d758e209e21ca3f6d7ec08a3f36d4c1c88a3c4abfdd466d"
    path = tmp_path / "package.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(R803EvaluationError, match="artifact_path_outside_repository"):
        load_evaluation_package(path)


def test_package_rejects_expected_evidence_outside_case_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    original_load = evaluation_contract._load_object

    def load_with_mismatched_scope(path: Path) -> dict[str, object]:
        document = original_load(path)
        if path.name == "r100-research-cases-v1.json":
            document["cases"][3]["expectedEvidenceCaseIds"] = ["answer-pdf-table"]
        return document

    monkeypatch.setattr(evaluation_contract, "_load_object", load_with_mismatched_scope)

    with pytest.raises(R803EvaluationError, match="case_evidence_scope_mismatch"):
        load_evaluation_package()


class InvalidQuickProvider(DeterministicProvider):
    def generate(self, messages, *, node_key: str) -> ProviderResult:
        if node_key == "quick":
            return ProviderResult("not-json", 1, 1, True)
        return super().generate(messages, node_key=node_key)


def test_provider_schema_failure_is_reported_without_false_quality_gate() -> None:
    result = run_paired_evaluation(provider=InvalidQuickProvider())
    assert result.quick_report["evaluation"]["status"] == "failed"
    assert result.quick_report["evaluation"]["engineeringGate"] == "fail"
    assert result.quick_report["evaluation"]["modelQualityGate"] == "not_evaluable"
    assert result.quick_report["evaluation"]["failure"]["code"] == "schema_violation"
    assert all(case["failureCode"] == "scorer_error" for case in result.quick_report["cases"])


class NoCallProvider(DeterministicProvider):
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, messages, *, node_key: str) -> ProviderResult:
        self.calls += 1
        return super().generate(messages, node_key=node_key)


def test_research_binding_is_validated_before_provider_calls() -> None:
    package = load_evaluation_package()
    package.document["research"]["agentResultSchemaVersion"] = "unknown"
    provider = NoCallProvider()

    with pytest.raises(Exception, match="research_prompt_binding_mismatch"):
        run_paired_evaluation(package=package, provider=provider)

    assert provider.calls == 0


class ExtraPlannerFieldProvider(DeterministicProvider):
    @staticmethod
    def _planner(variables: dict[str, object]) -> dict[str, object]:
        value = DeterministicProvider._planner(variables)
        value["unexpected"] = True
        return value


def test_evaluator_rejects_agent_fields_outside_complete_schema() -> None:
    result = run_paired_evaluation(provider=ExtraPlannerFieldProvider())

    assert result.research_report["evaluation"]["failure"]["code"] == "schema_violation"
    assert all(case["research"]["failureCode"] == "planner_invalid_output" for case in result.paired_report["cases"])


class TransientOnceProvider(DeterministicProvider):
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, messages, *, node_key: str) -> ProviderResult:
        self.calls += 1
        if self.calls == 1:
            raise ModelProviderError("generation_provider_unreachable", "Provider unavailable.")
        return super().generate(messages, node_key=node_key)


def test_transient_provider_failure_is_retried_and_reported_as_recovered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delays: list[int] = []
    monkeypatch.setattr(evaluation_provider, "sleep", delays.append)
    result = run_paired_evaluation(provider=TransientOnceProvider())
    quick = result.quick_report["evaluation"]
    assert quick["status"] == "completed"
    assert quick["providerCalls"] == 7
    assert quick["retryRate"] == {
        "value": pytest.approx(1 / 7),
        "sampleCount": 7,
        "notEvaluableReason": None,
    }
    assert quick["recoveryRate"] == {
        "value": 1.0,
        "sampleCount": 1,
        "notEvaluableReason": None,
    }
    assert delays == [5]


class UsageBearingTransientProvider(DeterministicProvider):
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, messages, *, node_key: str) -> ProviderResult:
        self.calls += 1
        if self.calls == 1:
            raise RecordedProviderError(
                "generation_incomplete_response",
                "No final output.",
                input_tokens=5,
                output_tokens=2,
                usage_final=True,
            )
        return super().generate(messages, node_key=node_key)


def test_failed_attempt_usage_is_included_in_report_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(evaluation_provider, "sleep", lambda _seconds: None)
    result = run_paired_evaluation(provider=UsageBearingTransientProvider())
    quick = result.quick_report["evaluation"]
    first_call = result.paired_report["cases"][0]["quick"]["providerCallRecords"][0]

    assert (quick["inputTokens"], quick["outputTokens"]) == (65, 32)
    assert first_call == {
        "node_key": "quick",
        "logical_call_key": "r100-compare-rise-drop:quick:0:quick",
        "attempt_number": 1,
        "duration_ms": first_call["duration_ms"],
        "input_tokens": 5,
        "output_tokens": 2,
        "usage_final": True,
        "status": "failed",
    }


class SchemaCapturingProvider(DeterministicProvider):
    def __init__(self) -> None:
        self.schemas: dict[str, object] = {}

    def generate(self, messages, *, node_key: str) -> ProviderResult:
        if node_key != "quick":
            variables = json.loads(str(messages[-1]["content"]))
            field = "planOutputSchema" if node_key == "planner" else "resultSchema"
            self.schemas[node_key] = variables[field]
        return super().generate(messages, node_key=node_key)


def test_evaluator_injects_versioned_complete_agent_result_schemas() -> None:
    provider = SchemaCapturingProvider()

    run_paired_evaluation(provider=provider)

    assert provider.schemas == AGENT_RESULT_SCHEMAS
