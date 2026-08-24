from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field, model_validator

from ai_pdf_api.core.settings import settings
from ai_pdf_api.services.multimodal_quality import GoldenCase, GoldenSet, QualityDataError, StrictModel


class WorkerExecutionCase(StrictModel):
    case_id: str = Field(alias="caseId", min_length=1)
    layer: Literal["retrieval", "evidence", "answer"]
    modality: Literal["pdf", "image", "mixed"]
    target_count: int = Field(alias="targetCount", ge=0)
    adapter_execution_passed: bool | None = Field(alias="adapterExecutionPassed")
    retrieval_execution_passed: bool | None = Field(alias="retrievalExecutionPassed")
    chat_orchestration_passed: bool | None = Field(alias="chatOrchestrationPassed")
    generation_mode: Literal["scripted"] | None = Field(alias="generationMode")
    passed: bool


class WorkerExecution(StrictModel):
    schema_version: Literal["m402-worker-execution-v1"] = Field(alias="schemaVersion")
    golden_schema_version: Literal["multimodal-golden-v1"] = Field(alias="goldenSchemaVersion")
    test_file: str = Field(alias="testFile", min_length=1)
    test_file_sha256: str = Field(alias="testFileSha256", pattern=r"^[0-9a-f]{64}$")
    test_node: str = Field(alias="testNode", min_length=1)
    cases: list[WorkerExecutionCase]
    passed: bool


class RenderedRegion(StrictModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0)
    height: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_bounds(self) -> "RenderedRegion":
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("rendered region must stay inside normalized bounds")
        return self


class PixelMeasurement(StrictModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    unique_colors: int = Field(alias="uniqueColors", gt=1)
    non_white_samples: int = Field(alias="nonWhiteSamples", gt=0)


class ResponseStatus(StrictModel):
    method: str = Field(min_length=1)
    path: str = Field(pattern=r"^/api/")
    status: int = Field(ge=200, lt=400)


class LayoutMeasurement(StrictModel):
    panel_within_viewport: Literal[True] = Field(alias="panelWithinViewport")
    primary_separated_from_panel: bool | None = Field(alias="primarySeparatedFromPanel")
    viewer_below_panel_header: Literal[True] = Field(alias="viewerBelowPanelHeader")
    rendered_surface_within_panel: Literal[True] = Field(alias="renderedSurfaceWithinPanel")


class PlaywrightTarget(StrictModel):
    citation_id: str = Field(alias="citationId", min_length=1)
    fixture_id: str = Field(alias="fixtureId", min_length=1)
    modality: Literal["pdf", "image"]
    locator_kind: Literal["pdf_page", "pdf_region", "image_region"] = Field(alias="locatorKind")
    page_number: int | None = Field(alias="pageNumber", ge=1)
    expected_regions: list[RenderedRegion] = Field(alias="expectedRegions")
    rendered_regions: list[RenderedRegion] = Field(alias="renderedRegions")
    minimum_approved_coverage_ratio: float | None = Field(alias="minimumApprovedCoverageRatio", ge=0, le=1)
    pixel_measurement: PixelMeasurement = Field(alias="pixelMeasurement")
    screenshot_path: str = Field(alias="screenshotPath", min_length=1)
    response_statuses: list[ResponseStatus] = Field(alias="responseStatuses")
    layout: LayoutMeasurement
    passed: Literal[True]

    @model_validator(mode="after")
    def validate_regions(self) -> "PlaywrightTarget":
        if self.locator_kind == "pdf_page":
            if self.expected_regions or self.rendered_regions or self.minimum_approved_coverage_ratio is not None:
                raise ValueError("pdf_page execution must not report region overlays")
        elif not self.expected_regions or not self.rendered_regions:
            raise ValueError("region execution must report approved and rendered regions")
        elif self.minimum_approved_coverage_ratio is None or self.minimum_approved_coverage_ratio < 0.08:
            raise ValueError("rendered Evidence must overlap every approved region")
        return self


class PlaywrightCase(StrictModel):
    case_id: str = Field(alias="caseId", min_length=1)
    targets: list[PlaywrightTarget] = Field(min_length=1)
    passed: Literal[True]


class PlaywrightViewport(StrictModel):
    name: Literal["desktop", "mobile"]
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class PlaywrightExecution(StrictModel):
    schema_version: Literal["m402-playwright-evidence-v1"] = Field(alias="schemaVersion")
    run_id: str = Field(alias="runId", min_length=1)
    golden_schema_version: Literal["multimodal-golden-v1"] = Field(alias="goldenSchemaVersion")
    test_file: str = Field(alias="testFile", min_length=1)
    test_file_sha256: str = Field(alias="testFileSha256", pattern=r"^[0-9a-f]{64}$")
    viewport: PlaywrightViewport
    route_interceptions: Literal[0] = Field(alias="routeInterceptions")
    real_bff_response_count: int = Field(alias="realBffResponseCount", gt=0)
    cases: list[PlaywrightCase]
    passed: Literal[True]


class AnswerOracleCase(StrictModel):
    case_id: str = Field(alias="caseId", min_length=1)
    expected_disposition: Literal["answer", "refuse"] = Field(alias="expectedDisposition")
    answer_points: list[str] = Field(alias="answerPoints")
    accepted_complete_outputs: list[str] = Field(alias="acceptedCompleteOutputs", min_length=1)
    required_prompt_concepts: list[list[str]] = Field(alias="requiredPromptConcepts")
    forbidden_prompt_patterns: list[str] = Field(alias="forbiddenPromptPatterns")

    @model_validator(mode="after")
    def validate_disposition(self) -> "AnswerOracleCase":
        normalized_outputs = [_normalize_complete_output(item) for item in self.accepted_complete_outputs]
        if any(not item for item in normalized_outputs) or len(normalized_outputs) != len(set(normalized_outputs)):
            raise ValueError("acceptedCompleteOutputs must be non-empty and unique after normalization")
        for alternatives in self.required_prompt_concepts:
            normalized = [_normalize_answer_text(item) for item in alternatives]
            if not alternatives or any(not item for item in normalized) or len(normalized) != len(set(normalized)):
                raise ValueError("requiredPromptConcepts groups must be non-empty and unique")
        _validate_patterns("forbiddenPromptPatterns", self.forbidden_prompt_patterns)
        if self.expected_disposition == "answer":
            if not self.answer_points:
                raise ValueError("answer oracle cases require answerPoints")
        elif self.answer_points:
            raise ValueError("refusal oracle cases must not contain answerPoints")
        return self


class AnswerOracle(StrictModel):
    schema_version: Literal["multimodal-answer-oracle-v1"] = Field(alias="schemaVersion")
    golden_schema_version: Literal["multimodal-golden-v1"] = Field(alias="goldenSchemaVersion")
    system_prompt_sha256: str = Field(alias="systemPromptSha256", pattern=r"^[0-9a-f]{64}$")
    cases: list[AnswerOracleCase] = Field(min_length=1)


class RealModelGenerationMessage(StrictModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class RealModelCitationCoverage(StrictModel):
    fixture_id: str = Field(alias="fixtureId", min_length=1)
    locator_kind: Literal["pdf_page", "pdf_region", "image_region"] = Field(alias="locatorKind")
    covered: bool


class RealModelExecutionCase(StrictModel):
    case_id: str = Field(alias="caseId", min_length=1)
    question: str = Field(min_length=1)
    generation_messages: list[RealModelGenerationMessage] = Field(alias="generationMessages")
    generation_messages_sha256: str = Field(
        alias="generationMessagesSha256",
        pattern=r"^[0-9a-f]{64}$",
    )
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    output: str
    citation_coverage: list[RealModelCitationCoverage] = Field(alias="citationCoverage")
    matched_answer_points: list[str] = Field(alias="matchedAnswerPoints")
    refusal_matched: bool = Field(alias="refusalMatched")
    error: str | None
    passed: bool


class RealModelExecution(StrictModel):
    schema_version: Literal["m402-real-model-execution-v1"] = Field(alias="schemaVersion")
    golden_schema_version: Literal["multimodal-golden-v1"] = Field(alias="goldenSchemaVersion")
    test_file: str = Field(alias="testFile", min_length=1)
    test_file_sha256: str = Field(alias="testFileSha256", pattern=r"^[0-9a-f]{64}$")
    test_node: str = Field(alias="testNode", min_length=1)
    cases: list[RealModelExecutionCase]
    passed: bool


@dataclass(frozen=True)
class RealModelEvaluation:
    matched_answer_points: tuple[str, ...]
    refusal_matched: bool
    passed: bool


@dataclass(frozen=True)
class PromptEvidenceEntry:
    index: int
    asset_title: str
    locator_kind: str
    excerpt: str


class ExecutionSourceProvenanceEntry(StrictModel):
    id: str = Field(min_length=1)
    execution_schema_version: str = Field(alias="executionSchemaVersion", min_length=1)
    test_file: str = Field(alias="testFile", min_length=1)
    test_file_sha256: str = Field(alias="testFileSha256", pattern=r"^[0-9a-f]{64}$")
    execution_artifact_path: str = Field(alias="executionArtifactPath", min_length=1)
    artifact_sha256: str = Field(alias="artifactSha256", pattern=r"^[0-9a-f]{64}$")
    original_artifact_commit: str = Field(alias="originalArtifactCommit", pattern=r"^[0-9a-f]{40}$")
    original_embedded_test_file_sha256: str = Field(
        alias="originalEmbeddedTestFileSha256",
        pattern=r"^[0-9a-f]{64}$",
    )
    original_embedded_runner_commit: str = Field(
        alias="originalEmbeddedRunnerCommit",
        pattern=r"^([0-9a-f]{40}|not-attested)$",
    )
    approved_runner_commit: str = Field(alias="approvedRunnerCommit", pattern=r"^[0-9a-f]{40}$")
    identity_repin_commit: str = Field(alias="identityRepinCommit", pattern=r"^[0-9a-f]{40}$")
    approval_kind: Literal["manual_runner_identity_repin"] = Field(alias="approvalKind")
    rationale: str = Field(min_length=1)


class ExecutionSourceProvenance(StrictModel):
    schema_version: Literal["m402-execution-source-provenance-v1"] = Field(alias="schemaVersion")
    entries: list[ExecutionSourceProvenanceEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_entries(self) -> "ExecutionSourceProvenance":
        ids = [entry.id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("provenance entry ids must be unique")
        identities = [
            (
                entry.execution_schema_version,
                entry.test_file,
                entry.test_file_sha256,
                entry.execution_artifact_path,
                entry.artifact_sha256,
            )
            for entry in self.entries
        ]
        if len(identities) != len(set(identities)):
            raise ValueError(
                "provenance (schemaVersion, testFile, testFileSha256, "
                "executionArtifactPath, artifactSha256) identities must be unique"
            )
        artifact_paths = [entry.execution_artifact_path for entry in self.entries]
        if len(artifact_paths) != len(set(artifact_paths)):
            raise ValueError("provenance executionArtifactPath values must be unique")
        return self


@dataclass(frozen=True)
class LoadedExecution:
    """One execution artifact loaded from a single bytes read.

    Repository-relative paths keep their canonical posix identity. Outside-repo
    test inputs are allowed for early semantic rejection and are labeled with an
    absolute sentinel that can never match historical provenance entries.
    """

    relative_path: str
    raw_bytes: bytes
    sha256: str
    model: object
    inside_repository: bool


@dataclass(frozen=True)
class LoadedProvenance:
    """One provenance contract snapshot loaded from a single bytes read."""

    relative_path: str
    raw_bytes: bytes
    sha256: str
    model: ExecutionSourceProvenance


_OUTSIDE_REPOSITORY_ARTIFACT_PREFIX = "<outside-repository>/"

_DEFAULT_EXECUTION_SOURCE_PROVENANCE_PATH = Path(
    "docs/evals/m402-execution-source-provenance-v1.json"
)


def canonical_generation_messages_sha256(
    messages: list[RealModelGenerationMessage] | list[dict[str, object]],
) -> str:
    payload = [
        message.model_dump(mode="json") if isinstance(message, RealModelGenerationMessage) else message
        for message in messages
    ]
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def load_multimodal_answer_oracle(
    repository_root: Path,
    oracle_path: Path,
    golden: GoldenSet,
) -> AnswerOracle:
    return _load_multimodal_answer_oracle(repository_root, oracle_path, golden).model


def _load_multimodal_answer_oracle(
    repository_root: Path,
    oracle_path: Path,
    golden: GoldenSet,
) -> LoadedExecution:
    root = repository_root.resolve()
    candidate = oracle_path if oracle_path.is_absolute() else root / oracle_path
    try:
        relative_path = candidate.resolve().relative_to(root).as_posix()
    except ValueError as error:
        raise QualityDataError("M402 answer oracle must be stored inside the repository.") from error
    canonical_path = _repository_artifact(root, relative_path)
    oracle_loaded = _load_execution(root, canonical_path, AnswerOracle)
    oracle = oracle_loaded.model
    if not isinstance(oracle, AnswerOracle):
        raise QualityDataError("M402 answer oracle payload has the wrong schema.")
    if not oracle_loaded.inside_repository:
        raise QualityDataError("M402 answer oracle must be stored inside the repository.")
    expected_cases = [case for case in golden.cases if case.layer == "answer"]
    if [case.case_id for case in oracle.cases] != [case.id for case in expected_cases]:
        raise QualityDataError("M402 answer oracle must bind every golden answer case in canonical order.")
    for oracle_case, golden_case in zip(oracle.cases, expected_cases, strict=True):
        if oracle_case.expected_disposition != golden_case.expected_disposition:
            raise QualityDataError(f"M402 answer oracle disposition drifted for {golden_case.id!r}.")
        if oracle_case.answer_points != golden_case.expected_answer_points:
            raise QualityDataError(f"M402 answer oracle points drifted for {golden_case.id!r}.")
    return oracle_loaded


def evaluate_real_model_output(oracle_case: AnswerOracleCase, output: str) -> RealModelEvaluation:
    normalized_output = _normalize_complete_output(output)
    accepted_outputs = {
        _normalize_complete_output(candidate)
        for candidate in oracle_case.accepted_complete_outputs
    }
    passed = normalized_output in accepted_outputs
    matched_points = tuple(oracle_case.answer_points) if passed and oracle_case.expected_disposition == "answer" else ()
    refusal_matched = passed and oracle_case.expected_disposition == "refuse"
    return RealModelEvaluation(
        matched_answer_points=matched_points,
        refusal_matched=refusal_matched,
        passed=passed,
    )


def _normalize_answer_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE).split())


def _normalize_complete_output(value: str) -> str:
    without_citations = re.sub(r"\[\d+\]", " ", value)
    return _normalize_answer_text(without_citations)


def _contains_normalized_phrase(normalized_output: str, phrase: str) -> bool:
    normalized_phrase = _normalize_answer_text(phrase)
    return f" {normalized_phrase} " in f" {normalized_output} "


def _validate_patterns(label: str, patterns: list[str]) -> None:
    for pattern in patterns:
        if not pattern or len(pattern) > 500:
            raise ValueError(f"{label} entries must contain 1-500 characters")
        try:
            re.compile(pattern)
        except re.error as error:
            raise ValueError(f"{label} contains an invalid regular expression") from error


def _parse_prompt_evidence(question: str, messages: list[RealModelGenerationMessage]) -> list[PromptEvidenceEntry]:
    if len(messages) != 2 or messages[0].role != "system" or messages[1].role != "user":
        raise QualityDataError("M402 real-model prompt must contain one system and one user message.")
    marker = f"Question:\n{question}\n\nAsset evidence context:\n"
    if not messages[1].content.startswith(marker):
        raise QualityDataError("M402 real-model prompt does not use the production Chat prompt contract.")
    context = messages[1].content[len(marker):]
    if not context.strip():
        raise QualityDataError("M402 real-model prompt evidence context is empty.")
    blocks = re.split(r"\n\n(?=\[\d+\] )", context)
    entries: list[PromptEvidenceEntry] = []
    for expected_index, block in enumerate(blocks, start=1):
        header, separator, excerpt = block.partition("\n")
        match = re.fullmatch(r"\[(\d+)\] (.+), (pdf_page|pdf_region|image_region)", header)
        if not match or not separator or not excerpt.strip() or int(match.group(1)) != expected_index:
            raise QualityDataError("M402 real-model prompt evidence context is malformed.")
        entries.append(
            PromptEvidenceEntry(
                index=expected_index,
                asset_title=match.group(2),
                locator_kind=match.group(3),
                excerpt=excerpt.strip(),
            )
        )
    return entries


def _validate_real_model_prompt(
    golden: GoldenSet,
    golden_case: GoldenCase,
    oracle: AnswerOracle,
    oracle_case: AnswerOracleCase,
    result: RealModelExecutionCase,
) -> None:
    if result.question != golden_case.question:
        raise QualityDataError(f"M402 real-model question drifted for {golden_case.id!r}.")
    actual_prompt_sha256 = canonical_generation_messages_sha256(result.generation_messages)
    if actual_prompt_sha256 != result.generation_messages_sha256:
        raise QualityDataError(f"M402 real-model prompt hash drifted for {golden_case.id!r}.")
    entries = _parse_prompt_evidence(golden_case.question, result.generation_messages)
    system_prompt_sha256 = hashlib.sha256(result.generation_messages[0].content.encode("utf-8")).hexdigest()
    if system_prompt_sha256 != oracle.system_prompt_sha256:
        raise QualityDataError(f"M402 real-model system prompt drifted for {golden_case.id!r}.")

    fixture_by_id = {fixture.id: fixture for fixture in golden.fixtures}
    allowed_fixture_ids = (
        [fixture.id for fixture in golden.fixtures]
        if golden_case.scope.mode == "all_ready"
        else golden_case.scope.selected_fixture_ids
    )
    allowed_titles = {
        Path(fixture_by_id[fixture_id].source_path).name
        for fixture_id in allowed_fixture_ids
    }
    if any(entry.asset_title not in allowed_titles for entry in entries):
        raise QualityDataError(f"M402 real-model prompt escaped the golden asset scope for {golden_case.id!r}.")
    for target in golden_case.evidence_targets:
        expected_title = Path(fixture_by_id[target.fixture_id].source_path).name
        if not any(
            entry.asset_title == expected_title and entry.locator_kind == target.locator_kind
            for entry in entries
        ):
            raise QualityDataError(f"M402 real-model prompt omitted target Evidence for {golden_case.id!r}.")

    normalized_context = _normalize_answer_text("\n".join(entry.excerpt for entry in entries))
    if not all(
        any(_contains_normalized_phrase(normalized_context, alternative) for alternative in alternatives)
        for alternatives in oracle_case.required_prompt_concepts
    ):
        raise QualityDataError(f"M402 real-model prompt omitted required content for {golden_case.id!r}.")
    if any(re.search(pattern, normalized_context) for pattern in oracle_case.forbidden_prompt_patterns):
        raise QualityDataError(f"M402 real-model prompt contains forbidden answer evidence for {golden_case.id!r}.")


def build_multimodal_execution_report(
    repository_root: Path,
    golden: GoldenSet,
    *,
    worker_path: Path,
    desktop_path: Path,
    mobile_path: Path,
    real_model_path: Path | None = None,
    answer_oracle_path: Path | None = None,
) -> dict[str, object]:
    root = repository_root.resolve()
    oracle_path = answer_oracle_path or root / "docs/evals/multimodal-answer-oracle-v1.json"
    oracle_loaded = _load_multimodal_answer_oracle(root, oracle_path, golden)
    oracle = oracle_loaded.model
    worker_loaded = _load_execution(root, worker_path, WorkerExecution)
    desktop_loaded = _load_execution(root, desktop_path, PlaywrightExecution)
    mobile_loaded = _load_execution(root, mobile_path, PlaywrightExecution)
    real_model_loaded = (
        _load_execution(root, real_model_path, RealModelExecution)
        if real_model_path is not None
        else None
    )
    worker = worker_loaded.model
    desktop = desktop_loaded.model
    mobile = mobile_loaded.model
    real_model = real_model_loaded.model if real_model_loaded is not None else None
    if not isinstance(worker, WorkerExecution):
        raise QualityDataError("M402 Worker execution payload has the wrong schema.")
    if not isinstance(desktop, PlaywrightExecution) or not isinstance(mobile, PlaywrightExecution):
        raise QualityDataError("M402 Playwright execution payload has the wrong schema.")
    if real_model is not None and not isinstance(real_model, RealModelExecution):
        raise QualityDataError("M402 real-model execution payload has the wrong schema.")
    if not isinstance(oracle, AnswerOracle):
        raise QualityDataError("M402 answer oracle payload has the wrong schema.")

    # One provenance snapshot per report: every historical source check must use
    # the same bytes/path/SHA/model, and that exact snapshot is registered below.
    provenance_loaded = _load_execution_source_provenance(root)

    golden_by_id = {case.id: case for case in golden.cases}
    answer_cases = {case.id: case for case in golden.cases if case.layer == "answer"}
    worker_by_id = _unique_cases("worker", worker.cases)
    _validate_test_source(
        root,
        worker.test_file,
        worker.test_file_sha256,
        execution_schema_version=worker.schema_version,
        execution_artifact_path=worker_loaded.relative_path,
        execution_artifact_sha256=worker_loaded.sha256,
        execution_artifact_inside_repository=worker_loaded.inside_repository,
        provenance=provenance_loaded,
    )
    if set(worker_by_id) != set(golden_by_id) or not worker.passed:
        raise QualityDataError("M402 Worker execution must pass every golden case exactly once.")
    for case_id, result in worker_by_id.items():
        golden_case = golden_by_id[case_id]
        if (
            result.layer != golden_case.layer
            or result.modality != golden_case.modality
            or result.target_count != len(golden_case.evidence_targets)
            or not result.passed
        ):
            raise QualityDataError(f"M402 Worker result does not match golden case {case_id!r}.")
        if golden_case.evidence_targets and result.adapter_execution_passed is not True:
            raise QualityDataError(f"M402 Worker did not execute adapters for {case_id!r}.")
        if golden_case.layer == "retrieval" and result.retrieval_execution_passed is not True:
            raise QualityDataError(f"M402 Worker did not execute retrieval for {case_id!r}.")
        if golden_case.layer == "answer" and (
            result.chat_orchestration_passed is not True or result.generation_mode != "scripted"
        ):
            raise QualityDataError(f"M402 Worker did not execute scripted Chat orchestration for {case_id!r}.")

    desktop_by_id = _validate_playwright(
        root,
        golden,
        desktop_loaded,
        "desktop",
        provenance=provenance_loaded,
    )
    mobile_by_id = _validate_playwright(
        root,
        golden,
        mobile_loaded,
        "mobile",
        provenance=provenance_loaded,
    )
    if desktop.run_id != mobile.run_id:
        raise QualityDataError("M402 desktop and mobile evidence must come from the same live run.")

    real_model_by_id: dict[str, RealModelExecutionCase] = {}
    real_model_evaluations: dict[str, RealModelEvaluation] = {}
    if real_model is not None:
        assert real_model_loaded is not None
        _validate_test_source(
            root,
            real_model.test_file,
            real_model.test_file_sha256,
            execution_schema_version=real_model.schema_version,
            execution_artifact_path=real_model_loaded.relative_path,
            execution_artifact_sha256=real_model_loaded.sha256,
            execution_artifact_inside_repository=real_model_loaded.inside_repository,
            provenance=provenance_loaded,
        )
        expected_test_node = (
            "apps/worker/tests/test_multimodal_golden_execution.py::"
            "test_m402_worker_executes_every_golden_evidence_target"
        )
        if real_model.test_file != "apps/worker/tests/test_multimodal_golden_execution.py":
            raise QualityDataError("M402 real-model execution must use the approved Worker runner.")
        if real_model.test_node != expected_test_node:
            raise QualityDataError("M402 real-model execution test node drifted.")
        real_model_by_id = _unique_cases("real model", real_model.cases)
        if set(real_model_by_id) != set(answer_cases):
            raise QualityDataError("M402 real-model execution must contain every answer case exactly once.")
        oracle_by_id = {case.case_id: case for case in oracle.cases}
        for case_id, result in real_model_by_id.items():
            expected = answer_cases[case_id]
            oracle_case = oracle_by_id[case_id]
            _validate_real_model_prompt(golden, expected, oracle, oracle_case, result)
            if result.provider != settings.generation_provider or result.model != settings.generation_model:
                raise QualityDataError(f"M402 real-model provider configuration drifted for {case_id!r}.")
            expected_coverage = [
                (target.fixture_id, target.locator_kind)
                for target in expected.evidence_targets
            ]
            actual_coverage = [
                (coverage.fixture_id, coverage.locator_kind)
                for coverage in result.citation_coverage
            ]
            if actual_coverage != expected_coverage or any(
                not coverage.covered for coverage in result.citation_coverage
            ):
                raise QualityDataError(f"M402 real-model citation coverage failed for {case_id!r}.")
            evaluation = evaluate_real_model_output(oracle_case, result.output)
            if (
                not evaluation.passed
                or result.error is not None
                or not result.output.strip()
            ):
                raise QualityDataError(f"M402 real-model answer oracle failed for {case_id!r}.")
            real_model_evaluations[case_id] = evaluation

    loaded_execution_inputs = [worker_loaded, desktop_loaded, mobile_loaded, oracle_loaded]
    if real_model_loaded is not None:
        loaded_execution_inputs.append(real_model_loaded)
    for loaded in loaded_execution_inputs:
        if not loaded.inside_repository:
            raise QualityDataError(
                f"M402 report input or artifact is outside the repository: {loaded.relative_path}."
            )
    screenshot_paths = [
        root / target.screenshot_path
        for execution in (desktop, mobile)
        for case in execution.cases
        for target in case.targets
    ]
    artifacts = _merge_artifact_records(
        [_loaded_execution_artifact_record(loaded) for loaded in loaded_execution_inputs],
        [_loaded_provenance_artifact_record(provenance_loaded)],
        _artifact_records(root, screenshot_paths),
    )

    case_reports: list[dict[str, object]] = []
    for case in golden.cases:
        report: dict[str, object] = {
            "caseId": case.id,
            "layer": case.layer,
            "modality": case.modality,
            "engineeringExecution": "passed",
            "workerTestNode": worker.test_node,
        }
        if case.layer == "evidence":
            report["fullStackEvidence"] = {
                "desktopScreenshots": [target.screenshot_path for target in desktop_by_id[case.id].targets],
                "mobileScreenshots": [target.screenshot_path for target in mobile_by_id[case.id].targets],
                "status": "passed",
            }
        if case.layer == "answer":
            model_result = real_model_by_id.get(case.id)
            model_evaluation = real_model_evaluations.get(case.id)
            report["realModel"] = (
                {
                    "status": "passed",
                    "provider": model_result.provider,
                    "model": model_result.model,
                    "output": model_result.output,
                    "matchedAnswerPoints": list(model_evaluation.matched_answer_points),
                    "refusalMatched": model_evaluation.refusal_matched,
                }
                if model_result and model_evaluation
                else {"status": "pending"}
            )
        report["status"] = (
            "passed"
            if case.layer != "answer" or case.id in real_model_by_id
            else "engineering_pass_model_pending"
        )
        case_reports.append(report)

    overlap_values = [
        target.minimum_approved_coverage_ratio
        for execution in (desktop, mobile)
        for case in execution.cases
        for target in case.targets
        if target.minimum_approved_coverage_ratio is not None
    ]
    model_quality_passed = len(real_model_by_id) == len(answer_cases)
    return {
        "schemaVersion": "multimodal-execution-report-v1",
        "goldenSchemaVersion": golden.schema_version,
        "liveRunId": desktop.run_id,
        "summary": {
            "caseCount": len(golden.cases),
            "engineeringCaseCount": len(worker_by_id),
            "fullStackEvidenceCaseCount": len(desktop_by_id),
            "desktopTargetCount": sum(len(case.targets) for case in desktop.cases),
            "mobileTargetCount": sum(len(case.targets) for case in mobile.cases),
            "screenshotCount": sum(path.suffix == ".png" for path in screenshot_paths),
            "minimumApprovedCoverageRatio": min(overlap_values),
            "desktopRealBffResponseCount": desktop.real_bff_response_count,
            "mobileRealBffResponseCount": mobile.real_bff_response_count,
            "scriptedAnswerCaseCount": len(answer_cases),
            "realModelAnswerCaseCount": len(real_model_by_id),
            "engineeringExecutionPassed": True,
            "fullStackEvidencePassed": True,
            "realModelQualityPassed": model_quality_passed,
            "releaseGatePassed": model_quality_passed,
        },
        "cases": case_reports,
        "artifacts": artifacts,
        "pending": (
            []
            if model_quality_passed
            else ["Run and approve real-model snapshots for all 7 answer/refusal cases."]
        ),
    }


def _validate_playwright(
    repository_root: Path,
    golden: GoldenSet,
    loaded: LoadedExecution,
    viewport_name: Literal["desktop", "mobile"],
    *,
    provenance: LoadedProvenance | None = None,
) -> dict[str, PlaywrightCase]:
    execution = loaded.model
    if not isinstance(execution, PlaywrightExecution):
        raise QualityDataError(f"M402 {viewport_name} execution payload has the wrong schema.")
    if execution.viewport.name != viewport_name:
        raise QualityDataError(f"M402 {viewport_name} report has the wrong viewport name.")
    if viewport_name == "desktop" and execution.viewport.width < 1280:
        raise QualityDataError("M402 desktop viewport must be at least 1280 pixels wide.")
    if viewport_name == "mobile" and execution.viewport.width > 480:
        raise QualityDataError("M402 mobile viewport must be at most 480 pixels wide.")
    test_source = _validate_test_source(
        repository_root,
        execution.test_file,
        execution.test_file_sha256,
        execution_schema_version=execution.schema_version,
        execution_artifact_path=loaded.relative_path,
        execution_artifact_sha256=loaded.sha256,
        execution_artifact_inside_repository=loaded.inside_repository,
        provenance=provenance,
    )
    if re.search(r"\.\s*route\s*\(", test_source):
        raise QualityDataError("M402 Playwright execution test must not intercept routes.")
    expected = {case.id: case for case in golden.cases if case.layer == "evidence"}
    actual = _unique_cases(viewport_name, execution.cases)
    if set(actual) != set(expected):
        raise QualityDataError(f"M402 {viewport_name} execution must contain all evidence cases exactly once.")
    fixture_by_id = {fixture.id: fixture for fixture in golden.fixtures}
    for case_id, result in actual.items():
        golden_case = expected[case_id]
        if len(result.targets) != len(golden_case.evidence_targets):
            raise QualityDataError(f"M402 {viewport_name} target count mismatch for {case_id!r}.")
        for target, expected_target in zip(result.targets, golden_case.evidence_targets, strict=True):
            fixture = fixture_by_id[expected_target.fixture_id]
            if (
                target.fixture_id != expected_target.fixture_id
                or target.modality != fixture.modality
                or target.locator_kind != expected_target.locator_kind
                or target.page_number != expected_target.page_number
            ):
                raise QualityDataError(f"M402 {viewport_name} target mismatch for {case_id!r}.")
            if viewport_name == "desktop" and target.layout.primary_separated_from_panel is not True:
                raise QualityDataError(f"M402 desktop panel overlaps the primary surface for {case_id!r}.")
            if viewport_name == "mobile" and target.layout.primary_separated_from_panel is not None:
                raise QualityDataError("M402 mobile layout must record overlay separation as not applicable.")
            approved_regions = _approved_regions(repository_root, fixture, expected_target)
            if len(target.expected_regions) != len(approved_regions) or any(
                not _regions_equal(actual, approved)
                for actual, approved in zip(target.expected_regions, approved_regions, strict=True)
            ):
                raise QualityDataError(f"M402 {viewport_name} approved regions drifted for {case_id!r}.")
            if approved_regions:
                actual_overlap = min(
                    max(_approved_coverage_ratio(approved, rendered) for rendered in target.rendered_regions)
                    for approved in approved_regions
                )
                if (
                    actual_overlap < 0.08
                    or target.minimum_approved_coverage_ratio is None
                    or abs(actual_overlap - target.minimum_approved_coverage_ratio) > 0.000001
                ):
                    raise QualityDataError(f"M402 {viewport_name} overlap result drifted for {case_id!r}.")
            _repository_artifact(repository_root, target.screenshot_path)
    return actual


def _load_execution(repository_root: Path, path: Path | None, model_type) -> LoadedExecution:
    if path is None:
        raise QualityDataError("M402 execution input path is required.")
    root = repository_root.resolve()
    candidate = path.resolve()
    if not candidate.is_file():
        raise QualityDataError(f"M402 artifact is missing: {path}.")
    try:
        relative_path = candidate.relative_to(root).as_posix()
        inside_repository = True
    except ValueError:
        # Temporary/outside-repo inputs are allowed so early semantic assertions
        # can run; their identity can never match historical provenance.
        relative_path = f"{_OUTSIDE_REPOSITORY_ARTIFACT_PREFIX}{candidate.as_posix()}"
        inside_repository = False
    if inside_repository and (
        PurePosixPath(relative_path).is_absolute()
        or "\\" in relative_path
        or any(part in {".", ".."} for part in PurePosixPath(relative_path).parts)
    ):
        raise QualityDataError(f"M402 artifact path is not canonical: {relative_path!r}.")
    try:
        raw_bytes = candidate.read_bytes()
        payload = json.loads(raw_bytes.decode("utf-8"))
        model = model_type.model_validate(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise QualityDataError(f"Invalid M402 execution data {path}: {error}") from error
    return LoadedExecution(
        relative_path=relative_path,
        raw_bytes=raw_bytes,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        model=model,
        inside_repository=inside_repository,
    )


def _unique_cases(label: str, cases) -> dict[str, object]:
    result = {case.case_id: case for case in cases}
    if len(result) != len(cases):
        raise QualityDataError(f"M402 {label} execution contains duplicate case ids.")
    return result


def _repository_artifact(repository_root: Path, relative_path: str) -> Path:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or "\\" in relative_path or any(part in {".", ".."} for part in path.parts):
        raise QualityDataError(f"M402 artifact path is not canonical: {relative_path!r}.")
    candidate = (repository_root / path).resolve()
    if repository_root not in candidate.parents or not candidate.is_file():
        raise QualityDataError(f"M402 artifact is missing or outside the repository: {relative_path!r}.")
    return candidate


def _validate_test_source(
    repository_root: Path,
    relative_path: str,
    expected_sha256: str,
    *,
    execution_schema_version: str,
    execution_artifact_path: str,
    execution_artifact_sha256: str,
    execution_artifact_inside_repository: bool = True,
    provenance: LoadedProvenance | None = None,
    provenance_path: Path | None = None,
) -> str:
    """Bind an execution payload to its runner source.

    Current tree bytes always pass when expected_sha256 matches the live file.
    A non-current hash is accepted only when the exact
    (executionSchemaVersion, testFile, testFileSha256, executionArtifactPath,
    artifactSha256) identity is listed in the versioned provenance contract and
    the caller-supplied artifact path/hash (from the same bytes read used to
    parse the model) match that entry. Outside-repository execution inputs never
    take the historical route. Path-only or hash-only matches fail closed.
    """
    candidate = _repository_artifact(repository_root, relative_path)
    payload = candidate.read_bytes()
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if actual_sha256 == expected_sha256:
        return payload.decode("utf-8")
    if execution_artifact_inside_repository and _approved_historical_execution_source(
        repository_root,
        execution_schema_version=execution_schema_version,
        test_file=relative_path,
        test_file_sha256=expected_sha256,
        execution_artifact_path=execution_artifact_path,
        execution_artifact_sha256=execution_artifact_sha256,
        provenance=provenance,
        provenance_path=provenance_path,
    ):
        return payload.decode("utf-8")
    raise QualityDataError(f"M402 test source hash drifted: {relative_path!r}.")


def _resolve_provenance_path(
    repository_root: Path,
    provenance_path: Path | None = None,
) -> Path:
    relative = (
        provenance_path
        if provenance_path is not None
        else _DEFAULT_EXECUTION_SOURCE_PROVENANCE_PATH
    )
    if relative.is_absolute():
        try:
            candidate = relative.resolve()
            candidate.relative_to(repository_root.resolve())
        except ValueError as error:
            raise QualityDataError(
                "M402 execution source provenance must be stored inside the repository."
            ) from error
        if not candidate.is_file():
            raise QualityDataError(
                f"M402 execution source provenance is missing: {candidate}."
            )
        return candidate
    return _repository_artifact(repository_root, relative.as_posix())


def _load_execution_source_provenance(
    repository_root: Path,
    provenance_path: Path | None = None,
) -> LoadedProvenance:
    path = _resolve_provenance_path(repository_root, provenance_path)
    try:
        raw_bytes = path.read_bytes()
        payload = json.loads(raw_bytes.decode("utf-8"))
        model = ExecutionSourceProvenance.model_validate(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise QualityDataError(
            f"Invalid M402 execution source provenance {path}: {error}"
        ) from error
    relative_path = path.resolve().relative_to(repository_root.resolve()).as_posix()
    return LoadedProvenance(
        relative_path=relative_path,
        raw_bytes=raw_bytes,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        model=model,
    )


def _approved_historical_execution_source(
    repository_root: Path,
    *,
    execution_schema_version: str,
    test_file: str,
    test_file_sha256: str,
    execution_artifact_path: str,
    execution_artifact_sha256: str,
    provenance: LoadedProvenance | None = None,
    provenance_path: Path | None = None,
) -> bool:
    loaded = provenance or _load_execution_source_provenance(repository_root, provenance_path)
    return any(
        entry.execution_schema_version == execution_schema_version
        and entry.test_file == test_file
        and entry.test_file_sha256 == test_file_sha256
        and entry.execution_artifact_path == execution_artifact_path
        and entry.artifact_sha256 == execution_artifact_sha256
        for entry in loaded.model.entries
    )


def _approved_regions(repository_root: Path, fixture, target) -> list[RenderedRegion]:
    manifest_path = _repository_artifact(repository_root, fixture.manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise QualityDataError(f"M402 fixture manifest is invalid: {fixture.manifest_path!r}.") from error
    if fixture.modality == "image":
        regions = {item["label"]: item for item in manifest["regions"]}
        payloads = [regions[label] for label in target.region_labels]
    else:
        page = next(item for item in manifest["pages"] if item["label"] == target.page_label)
        payloads = [page["regions"][index] for index in target.region_indexes]
    return [
        RenderedRegion.model_validate(
            {field: payload[field] for field in ("x", "y", "width", "height")}
        )
        for payload in payloads
    ]


def _regions_equal(left: RenderedRegion, right: RenderedRegion) -> bool:
    return all(
        abs(getattr(left, field) - getattr(right, field)) <= 0.000001
        for field in ("x", "y", "width", "height")
    )


def _approved_coverage_ratio(approved: RenderedRegion, rendered: RenderedRegion) -> float:
    width = max(
        0.0,
        min(approved.x + approved.width, rendered.x + rendered.width) - max(approved.x, rendered.x),
    )
    height = max(
        0.0,
        min(approved.y + approved.height, rendered.y + rendered.height) - max(approved.y, rendered.y),
    )
    approved_area = approved.width * approved.height
    return min(1.0, width * height / approved_area) if approved_area > 0 else 0.0


def _loaded_execution_artifact_record(loaded: LoadedExecution) -> dict[str, object]:
    return {
        "path": loaded.relative_path,
        "sha256": loaded.sha256,
        "byteSize": len(loaded.raw_bytes),
    }


def _loaded_provenance_artifact_record(loaded: LoadedProvenance) -> dict[str, object]:
    return {
        "path": loaded.relative_path,
        "sha256": loaded.sha256,
        "byteSize": len(loaded.raw_bytes),
    }


def _merge_artifact_records(
    *record_groups: list[dict[str, object]],
) -> list[dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    for group in record_groups:
        for record in group:
            path = record["path"]
            if not isinstance(path, str):
                raise QualityDataError("M402 artifact record path must be a string.")
            if path in records:
                raise QualityDataError(
                    f"M402 artifact path collision: duplicate artifact path {path!r}."
                )
            records[path] = record
    return [records[key] for key in sorted(records)]


def _artifact_records(repository_root: Path, paths: list[Path]) -> list[dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    for path in paths:
        candidate = path.resolve()
        if repository_root not in candidate.parents or not candidate.is_file():
            raise QualityDataError(f"M402 report input or artifact is outside the repository: {path}.")
        relative = candidate.relative_to(repository_root).as_posix()
        if relative in records:
            raise QualityDataError(
                f"M402 artifact path collision: duplicate artifact path {relative!r}."
            )
        payload = candidate.read_bytes()
        records[relative] = {
            "path": relative,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "byteSize": len(payload),
        }
    return [records[key] for key in sorted(records)]
