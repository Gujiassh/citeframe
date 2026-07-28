from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


class EvaluationModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="forbid",
        from_attributes=True,
        allow_inf_nan=False,
    )


Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
CanonicalUuid = Annotated[
    str,
    Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
]
EvaluationGate = Literal["not_evaluable", "pass", "fail"]
EvaluationMode = Literal["quick", "research"]
EvaluationStatus = Literal["not_evaluable", "completed", "failed"]
Disposition = Literal["answer", "refuse", "not_evaluable"]
EvaluationFailureCode = Literal[
    "budget_exhausted",
    "evaluation_internal_error",
    "provider_error",
    "schema_violation",
    "source_unavailable",
    "timeout",
]
ClaimFailureCode = Literal[
    "conflict_missed",
    "evidence_missing",
    "insufficient_evidence",
    "locator_inaccurate",
    "scorer_error",
    "unsupported_claim",
]


class RatioMetric(EvaluationModel):
    value: float | None
    sample_count: int = Field(ge=0, le=2_147_483_647)
    not_evaluable_reason: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    )

    @model_validator(mode="after")
    def validate_evaluable_state(self) -> "RatioMetric":
        if self.value is None:
            if self.not_evaluable_reason is None:
                raise ValueError("notEvaluableReason is required when value is null")
            return self
        if self.not_evaluable_reason is not None:
            raise ValueError("notEvaluableReason must be null when value is present")
        if self.sample_count < 1:
            raise ValueError("sampleCount must be positive when value is present")
        if not 0 <= self.value <= 1:
            raise ValueError("ratio value must be between zero and one")
        return self


class EvaluationCost(EvaluationModel):
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    amount_micros: int = Field(ge=0, le=9_007_199_254_740_991)


class EvaluationFailure(EvaluationModel):
    code: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=500)

    @field_validator("message")
    @classmethod
    def safe_single_line_message(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("failure message must be trimmed, printable, and single-line")
        return value


class EvaluationSuiteDto(EvaluationModel):
    id: str
    suite_key: str
    version: int
    title: str
    fixture_manifest_sha256: Sha256
    scorer_version: str
    case_count: int
    created_at: datetime


class EvaluationRunSummary(EvaluationModel):
    id: str
    workspace_id: str
    suite_id: str
    mode: EvaluationMode
    status: EvaluationStatus
    research_run_id: str | None
    baseline_evaluation_run_id: str | None
    fixture_manifest_sha256: Sha256
    asset_scope_sha256: Sha256
    provider: str
    model: str
    provider_profile_sha256: Sha256
    scorer_version: str
    workflow_version_id: str | None
    prompt_binding_sha256: Sha256 | None
    wall_time_ms: int | None
    provider_calls: int
    input_tokens: int
    output_tokens: int
    cost: EvaluationCost
    parallel_speedup: float | None
    retry_rate: RatioMetric
    recovery_rate: RatioMetric
    claim_support_rate: RatioMetric
    evidence_recall: RatioMetric
    evidence_precision: RatioMetric
    locator_accuracy: RatioMetric
    conflict_detection_rate: RatioMetric
    refusal_correctness: RatioMetric
    engineering_gate: EvaluationGate
    model_quality_gate: EvaluationGate
    user_value_gate: EvaluationGate
    source_report_sha256: Sha256
    created_at: datetime
    completed_at: datetime | None
    failure: EvaluationFailure | None


class EvaluationCaseSummary(EvaluationModel):
    id: str
    case_key: str
    case_type: str
    expected_disposition: Disposition
    observed_disposition: Disposition
    claim_support_rate: RatioMetric
    evidence_recall: RatioMetric
    evidence_precision: RatioMetric
    locator_accuracy: RatioMetric
    conflict_detection_rate: RatioMetric
    refusal_correctness: RatioMetric
    wall_time_ms: int | None
    provider_calls: int
    cost: EvaluationCost
    unsupported_claim_count: int
    human_intervention_count: int
    human_wait_ms: int
    failure_code: str | None


class EvaluationClaimResult(EvaluationModel):
    id: str
    claim_key: str
    support_result: Literal["supported", "unsupported", "not_evaluable"]
    locator_result: Literal["accurate", "inaccurate", "not_evaluable"]
    conflict_result: Literal["none", "detected", "missed", "not_evaluable"]
    expected_evidence_count: int
    observed_evidence_count: int
    failure_code: str | None


class EvaluationCaseDetail(EvaluationCaseSummary):
    claims: list[EvaluationClaimResult]


class EvaluationSuiteListResponse(EvaluationModel):
    items: list[EvaluationSuiteDto]


class EvaluationSuiteResponse(EvaluationModel):
    suite: EvaluationSuiteDto


class EvaluationRunListResponse(EvaluationModel):
    items: list[EvaluationRunSummary]
    next_cursor: str | None


class EvaluationRunResponse(EvaluationModel):
    evaluation: EvaluationRunSummary


class EvaluationCaseListResponse(EvaluationModel):
    items: list[EvaluationCaseSummary]


class EvaluationCaseResponse(EvaluationModel):
    case_result: EvaluationCaseDetail = Field(alias="case")


class EvaluationSuiteImport(EvaluationModel):
    suite_key: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    )
    version: int = Field(ge=1, le=2_147_483_647)
    title: str = Field(min_length=1, max_length=255)
    fixture_manifest_sha256: Sha256
    scorer_version: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    case_count: int = Field(ge=0, le=100_000)

    @field_validator("title")
    @classmethod
    def safe_title(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("title must be trimmed, printable, and single-line")
        return value


class EvaluationSourceArtifactImport(EvaluationModel):
    artifact_id: CanonicalUuid
    sha256: Sha256


class EvaluationRunImport(EvaluationModel):
    mode: EvaluationMode
    status: EvaluationStatus
    research_run_id: CanonicalUuid | None = None
    baseline_evaluation_run_id: CanonicalUuid | None = None
    fixture_manifest_sha256: Sha256
    asset_scope_sha256: Sha256
    provider: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    model: str = Field(min_length=1, max_length=128)
    provider_profile_sha256: Sha256
    scorer_version: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    workflow_version_id: CanonicalUuid | None = None
    prompt_binding_sha256: Sha256 | None = None
    source_artifact: EvaluationSourceArtifactImport | None = None
    model_quality_evidence_kind: Literal["scripted", "provider_backed"]
    user_value_evidence_ref: str | None = Field(
        default=None,
        min_length=7,
        max_length=255,
        pattern=r"^m404:[A-Za-z0-9._:/-]+$",
    )
    wall_time_ms: int | None = Field(default=None, ge=0, le=9_007_199_254_740_991)
    provider_calls: int = Field(ge=0, le=2_147_483_647)
    input_tokens: int = Field(ge=0, le=9_007_199_254_740_991)
    output_tokens: int = Field(ge=0, le=9_007_199_254_740_991)
    cost: EvaluationCost
    parallel_speedup: float | None = Field(default=None, ge=0)
    retry_rate: RatioMetric
    recovery_rate: RatioMetric
    claim_support_rate: RatioMetric
    evidence_recall: RatioMetric
    evidence_precision: RatioMetric
    locator_accuracy: RatioMetric
    conflict_detection_rate: RatioMetric
    refusal_correctness: RatioMetric
    engineering_gate: EvaluationGate
    model_quality_gate: EvaluationGate
    user_value_gate: EvaluationGate
    failure: EvaluationFailure | None = None
    created_at: datetime
    completed_at: datetime | None = None

    @field_validator("created_at", "completed_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("evaluation timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_run_rules(self) -> "EvaluationRunImport":
        if self.mode == "quick" and (self.research_run_id or self.baseline_evaluation_run_id):
            raise ValueError("Quick evaluations cannot reference Research runs or baselines")
        if self.source_artifact is not None and self.research_run_id is None:
            raise ValueError("sourceArtifact requires researchRunId")
        if self.model_quality_evidence_kind == "scripted" and self.model_quality_gate != "not_evaluable":
            raise ValueError("scripted evidence cannot pass or fail model quality")
        if self.user_value_evidence_ref is None and self.user_value_gate != "not_evaluable":
            raise ValueError("user value requires an M404 evidence reference")
        if self.status == "completed" and self.failure is not None:
            raise ValueError("completed evaluations cannot contain a failure")
        if self.status == "failed":
            if self.failure is None:
                raise ValueError("failed evaluations require a safe failure")
            if self.engineering_gate != "fail":
                raise ValueError("failed evaluations require engineeringGate=fail")
            if self.model_quality_gate != "not_evaluable" or self.user_value_gate != "not_evaluable":
                raise ValueError("failed evaluations cannot decide quality or user-value gates")
        if self.status == "not_evaluable" and any(
            gate != "not_evaluable"
            for gate in (self.engineering_gate, self.model_quality_gate, self.user_value_gate)
        ):
            raise ValueError("not-evaluable runs cannot pass or fail evidence gates")
        if self.status in {"completed", "failed"} and self.completed_at is None:
            raise ValueError("terminal evaluations require completedAt")
        if self.completed_at is not None and self.completed_at < self.created_at:
            raise ValueError("completedAt cannot precede createdAt")
        return self


class EvaluationClaimImport(EvaluationModel):
    claim_key: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    support_result: Literal["supported", "unsupported", "not_evaluable"]
    locator_result: Literal["accurate", "inaccurate", "not_evaluable"]
    conflict_result: Literal["none", "detected", "missed", "not_evaluable"]
    expected_evidence_count: int = Field(ge=0, le=2_147_483_647)
    observed_evidence_count: int = Field(ge=0, le=2_147_483_647)
    failure_code: ClaimFailureCode | None = None


class EvaluationCaseImport(EvaluationModel):
    case_key: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    case_type: str = Field(min_length=1, max_length=96, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    expected_disposition: Disposition
    observed_disposition: Disposition
    claim_support_rate: RatioMetric
    evidence_recall: RatioMetric
    evidence_precision: RatioMetric
    locator_accuracy: RatioMetric
    conflict_detection_rate: RatioMetric
    refusal_correctness: RatioMetric
    wall_time_ms: int | None = Field(default=None, ge=0, le=9_007_199_254_740_991)
    provider_calls: int = Field(ge=0, le=2_147_483_647)
    cost: EvaluationCost
    unsupported_claim_count: int = Field(ge=0, le=2_147_483_647)
    human_intervention_count: int = Field(ge=0, le=2_147_483_647)
    human_wait_ms: int = Field(ge=0, le=9_007_199_254_740_991)
    failure_code: ClaimFailureCode | None = None
    claims: list[EvaluationClaimImport] = Field(max_length=10_000)

    @model_validator(mode="after")
    def validate_case_rules(self) -> "EvaluationCaseImport":
        claim_keys = [claim.claim_key for claim in self.claims]
        if len(claim_keys) != len(set(claim_keys)):
            raise ValueError("claim keys must be unique within a case")
        if self.expected_disposition == "refuse" and self.claims:
            raise ValueError("refusal fixtures cannot define claim results")
        unsupported = sum(claim.support_result == "unsupported" for claim in self.claims)
        if unsupported != self.unsupported_claim_count:
            raise ValueError("unsupportedClaimCount must match claim results")
        return self


class EvaluationImportReport(EvaluationModel):
    schema_version: Literal["citeframe-evaluation-report-v1"]
    suite: EvaluationSuiteImport
    evaluation: EvaluationRunImport
    cases: list[EvaluationCaseImport] = Field(max_length=100_000)

    @model_validator(mode="after")
    def validate_report_rules(self) -> "EvaluationImportReport":
        if len(self.cases) != self.suite.case_count:
            raise ValueError("suite caseCount must match imported cases")
        case_keys = [case.case_key for case in self.cases]
        if len(case_keys) != len(set(case_keys)):
            raise ValueError("case keys must be unique")
        if self.evaluation.fixture_manifest_sha256 != self.suite.fixture_manifest_sha256:
            raise ValueError("evaluation fixture manifest must match suite")
        if self.evaluation.scorer_version != self.suite.scorer_version:
            raise ValueError("evaluation scorer version must match suite")
        if any(case.cost.currency != self.evaluation.cost.currency for case in self.cases):
            raise ValueError("case currencies must match the evaluation currency")
        return self
