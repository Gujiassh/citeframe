from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_pdf_api.schemas.chat import EvidenceLocatorDto, SourceVersions


ResearchRunStatus = Literal[
    "planning",
    "awaiting_plan_approval",
    "queued",
    "running",
    "awaiting_human_decision",
    "awaiting_retry",
    "cancel_requested",
    "completed",
    "failed",
    "cancelled",
]
ResearchStepKind = Literal[
    "planner",
    "plan_approval_gate",
    "researcher",
    "join",
    "verifier",
    "critic",
    "conflict_decision_gate",
    "synthesizer",
    "artifact_publisher",
]
ResearchStepStatus = Literal[
    "pending", "queued", "running", "waiting", "succeeded", "failed", "cancelled", "skipped"
]


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


class ResearchModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="forbid",
        from_attributes=True,
    )


class AllReadyScope(ResearchModel):
    mode: Literal["all_ready"]


class SelectedScope(ResearchModel):
    mode: Literal["selected"]
    asset_ids: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_asset_ids(self) -> "SelectedScope":
        if len(self.asset_ids) != len(set(self.asset_ids)):
            raise ValueError("assetIds must be unique")
        return self


AssetScopeRequest = Annotated[AllReadyScope | SelectedScope, Field(discriminator="mode")]


class FrozenAsset(ResearchModel):
    asset_id: str
    asset_kind: str
    asset_title: str
    processing_generation: int = Field(ge=1)
    index_version: int = Field(ge=1)


class FrozenAssetScope(ResearchModel):
    frozen_at: datetime
    assets: list[FrozenAsset]


class BudgetUsage(ResearchModel):
    provider_calls: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    usage_final: bool
    measured_at: datetime
    usage_source: Literal["actual", "estimated", "mixed"] | None = None


class ProviderSnapshot(ResearchModel):
    generation_provider: str
    generation_model: str
    embedding_provider: str
    embedding_model: str
    embedding_version: str
    retrieval_strategy: str
    retrieval_top_k: int = Field(ge=1)
    provider_config_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    pricing_version: str | None
    data_boundary_policy_version: str


class BudgetLimits(ResearchModel):
    max_provider_calls: int = Field(ge=1)
    max_tool_calls: int = Field(ge=1)
    max_input_tokens: int = Field(ge=1)
    max_output_tokens: int = Field(ge=1)
    max_parallel_researchers: int = Field(ge=1)
    run_timeout_seconds: int = Field(ge=1)
    step_timeout_seconds: int = Field(ge=1)
    provider_timeout_seconds: int = Field(ge=1)
    max_attempts_per_step: int = Field(ge=1)


class PlanningBudgetLimits(ResearchModel):
    max_provider_calls: int = Field(ge=1)
    max_input_tokens: int = Field(ge=1)
    max_output_tokens: int = Field(ge=1)
    planner_timeout_seconds: int = Field(ge=1)
    provider_timeout_seconds: int = Field(ge=1)
    max_planner_attempts: int = Field(ge=1)


class PromptVersionRef(ResearchModel):
    node_key: str
    prompt_version_id: str


class ExecutionConfigSnapshot(ResearchModel):
    workflow_version_id: str
    prompt_versions: list[PromptVersionRef]
    provider: ProviderSnapshot
    budget_policy_version: str
    retry_policy_version: str
    limits: BudgetLimits
    agent_result_schema_version: str | None = None
    context_policy_version: str | None = None
    compact_policy_version: str | None = None


class PlanningExecutionSnapshot(ResearchModel):
    workflow_version_id: str
    planner_prompt_version_id: str
    provider: ProviderSnapshot
    budget_policy_version: str
    retry_policy_version: str
    limits: PlanningBudgetLimits
    agent_result_schema_version: str | None = None
    context_policy_version: str | None = None
    compact_policy_version: str | None = None


class PlanningInputSnapshot(ResearchModel):
    revision_number: int = Field(ge=1)
    question: str
    requested_asset_scope: AssetScopeRequest
    planning_asset_scope: FrozenAssetScope
    planning_execution: PlanningExecutionSnapshot
    proposed_research_execution: ExecutionConfigSnapshot
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frozen_at: datetime


class ApprovedResearchExecutionSnapshot(ResearchModel):
    id: str
    input_version: int = Field(ge=1)
    approval_decision_id: str
    approved_plan_artifact_id: str
    approved_plan_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    question: str
    frozen_asset_scope: FrozenAssetScope
    execution: ExecutionConfigSnapshot
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime


class SafeFailure(ResearchModel):
    code: str
    message: str
    retryable: bool
    failed_at: datetime


class ResearchPlanSubproblem(ResearchModel):
    id: str
    order: int = Field(ge=0)
    question: str = Field(min_length=1, max_length=4000)
    asset_ids: list[str] = Field(max_length=100)
    expected_evidence: list[str] = Field(max_length=20)

    @model_validator(mode="after")
    def validate_plan_subproblem(self) -> "ResearchPlanSubproblem":
        if not self.question.strip():
            raise ValueError("question must not be blank")
        if len(self.asset_ids) != len(set(self.asset_ids)):
            raise ValueError("assetIds must be unique")
        if len(self.expected_evidence) != len(set(self.expected_evidence)):
            raise ValueError("expectedEvidence must be unique")
        if any(not label.strip() or len(label) > 1000 for label in self.expected_evidence):
            raise ValueError("expectedEvidence labels must contain 1 to 1000 characters")
        return self


class ResearchPlanArtifactPayload(ResearchModel):
    summary: str = Field(min_length=1, max_length=4000)
    subproblems: list[ResearchPlanSubproblem] = Field(min_length=1, max_length=16)
    known_gaps: list[str] = Field(max_length=20)
    estimated_provider_calls: int = Field(ge=1)
    estimated_input_tokens: int | None = Field(default=None, ge=0)
    estimated_output_tokens: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_plan_payload(self) -> "ResearchPlanArtifactPayload":
        if not self.summary.strip():
            raise ValueError("summary must not be blank")
        if len({item.id for item in self.subproblems}) != len(self.subproblems):
            raise ValueError("subproblem ids must be unique")
        if len({item.order for item in self.subproblems}) != len(self.subproblems):
            raise ValueError("subproblem orders must be unique")
        if sorted(item.order for item in self.subproblems) != list(range(len(self.subproblems))):
            raise ValueError("subproblem orders must be contiguous from zero")
        if any(not gap.strip() or len(gap) > 1000 for gap in self.known_gaps):
            raise ValueError("knownGaps must contain 1 to 1000 characters")
        return self


class LegacyResearchPlanArtifactPayload(ResearchPlanArtifactPayload):
    """Schema-v1 recovery reader for the historical optional cost field."""

    estimated_cost: dict[str, object] | None = None


class ResearchPlan(ResearchModel):
    version: int = Field(ge=1)
    status: Literal["proposed", "approved", "superseded"]
    input_snapshot: PlanningInputSnapshot
    summary: str = Field(min_length=1, max_length=4000)
    subproblems: list[ResearchPlanSubproblem] = Field(min_length=1, max_length=16)
    known_gaps: list[str] = Field(max_length=20)
    estimated_provider_calls: int = Field(ge=1)
    estimated_input_tokens: int | None = Field(default=None, ge=0)
    estimated_output_tokens: int | None = Field(default=None, ge=0)
    planning_usage: BudgetUsage
    created_at: datetime
    approved_at: datetime | None


class ResearchStepDto(ResearchModel):
    id: str
    run_id: str
    kind: ResearchStepKind = Field(alias="kind")
    key: str
    branch_key: str | None
    status: ResearchStepStatus
    state_version: int
    current_attempt_number: int
    max_attempts: int = Field(alias="maxAttempts")
    depends_on_step_ids: list[str]
    evidence_count: int
    provider_calls: int
    tool_calls: int
    started_at: datetime | None
    finished_at: datetime | None
    failure: SafeFailure | None


class HumanDecisionDto(ResearchModel):
    id: str
    run_id: str
    gate_step_id: str
    type: Literal["plan_approval", "conflict_resolution"] = Field(alias="type")
    status: Literal["pending", "submitted", "expired", "cancelled", "superseded"]
    request_number: int
    state_version: int
    input_artifact_id: str
    input_artifact_sha256: str
    input_snapshot_sha256: str
    requested_at: datetime
    expires_at: datetime | None
    decided_by_user_id: str | None
    action: Literal[
        "approve",
        "request_revision",
        "cancel_run",
        "exclude_conflicted_claims",
        "keep_as_unresolved",
    ] | None
    comment: str | None = Field(default=None, alias="comment")
    decided_at: datetime | None


class ResearchRunSummary(ResearchModel):
    id: str
    workspace_id: str
    created_by_user_id: str
    question: str
    status: ResearchRunStatus
    state_version: int
    requested_asset_scope: AssetScopeRequest
    frozen_asset_count: int
    current_plan_revision_number: int | None
    current_event_seq: int
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None


class ResearchRunDetail(ResearchRunSummary):
    frozen_asset_scope: FrozenAssetScope | None
    plan: ResearchPlan | None
    research_execution: ApprovedResearchExecutionSnapshot | None
    planning_usage: BudgetUsage
    research_usage: BudgetUsage | None
    steps: list[ResearchStepDto]
    pending_decisions: list[HumanDecisionDto]
    submitted_decisions: list[HumanDecisionDto]
    artifact_count: int
    failure: SafeFailure | None
    started_at: datetime | None
    cancel_requested_at: datetime | None
    cancelled_at: datetime | None


class CreateResearchRunRequest(ResearchModel):
    question: str = Field(min_length=1, max_length=12000)
    asset_scope: AssetScopeRequest

    @field_validator("question")
    @classmethod
    def trim_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be blank")
        return value


class CreateResearchRunResponse(ResearchModel):
    run: ResearchRunDetail


class ResearchRunListResponse(ResearchModel):
    items: list[ResearchRunSummary]
    next_cursor: str | None


class ResearchRunDetailResponse(ResearchModel):
    run: ResearchRunDetail


class CancelResearchRunRequest(ResearchModel):
    expected_state_version: int = Field(ge=1)
    reason_code: Literal["user_requested", "cost", "security", "other"]


class CancelResearchRunResponse(ResearchModel):
    run: ResearchRunDetail


class PlanRevisionInput(ResearchModel):
    question: str = Field(min_length=1, max_length=12000)
    asset_scope: AssetScopeRequest

    @field_validator("question")
    @classmethod
    def trim_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be blank")
        return value


class PlanDecisionRequest(ResearchModel):
    expected_state_version: int = Field(ge=1)
    expected_decision_state_version: int = Field(ge=1)
    input_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: Literal["approve", "request_revision", "cancel_run"]
    comment: str | None = Field(default=None, max_length=4000)
    revision: PlanRevisionInput | None = None

    @model_validator(mode="after")
    def validate_revision(self) -> "PlanDecisionRequest":
        if self.action == "request_revision" and (self.revision is None or not self.comment):
            raise ValueError("request_revision requires comment and revision")
        if self.action != "request_revision" and self.revision is not None:
            raise ValueError("revision is only valid for request_revision")
        return self


class PlanDecisionResponse(ResearchModel):
    decision: HumanDecisionDto
    run: ResearchRunDetail


class ConflictDecisionRequest(ResearchModel):
    expected_state_version: int = Field(ge=1)
    expected_decision_state_version: int = Field(ge=1)
    input_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: Literal["exclude_conflicted_claims", "keep_as_unresolved", "cancel_run"]
    comment: str | None = Field(default=None, max_length=4000)


class ConflictDecisionResponse(ResearchModel):
    decision: HumanDecisionDto
    run: ResearchRunDetail


class RetryResearchStepRequest(ResearchModel):
    expected_state_version: int = Field(ge=1)
    expected_step_state_version: int = Field(ge=1)
    failed_attempt: int = Field(ge=1)


class RetryResearchStepResponse(ResearchModel):
    run: ResearchRunDetail
    step: ResearchStepDto


class ResearchArtifactSummary(ResearchModel):
    id: str
    run_id: str
    step_id: str
    kind: Literal["research_plan", "evidence_bundle", "conflict_report", "final_report", "trace_export"]
    visibility: Literal["user"]
    logical_key: str
    schema_version: str
    supersedes_artifact_id: str | None
    media_type: Literal["text/markdown", "application/json"]
    byte_size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_count: int = Field(ge=0)
    retention_class: Literal["workspace_lifetime", "time_limited_diagnostics"]
    expires_at: datetime | None
    created_at: datetime


class ArtifactClaimEvidenceRef(ResearchModel):
    evidence_locator_id: str
    relationship: Literal["supports", "contradicts"]
    order: int = Field(ge=0)


class ArtifactClaim(ResearchModel):
    id: str
    text: str
    verification_status: Literal["supported", "unsupported"]
    conflict_status: Literal["none", "conflicted", "resolved_excluded", "resolved_unresolved"]
    section_kind: Literal["fact", "conclusion", "unresolved", "conflict"]
    evidence: list[ArtifactClaimEvidenceRef]


class ArtifactEvidenceRef(ResearchModel):
    evidence_locator_id: str
    asset_id: str
    asset_kind: str
    asset_title: str
    source_available: bool
    excerpt: str
    locator: EvidenceLocatorDto
    source_versions: SourceVersions


class ResearchArtifactDetail(ResearchArtifactSummary):
    workflow_version_id: str
    prompt_versions: list[PromptVersionRef]
    direct_prompt_version_id: str | None
    provider: ProviderSnapshot | None
    claims: list[ArtifactClaim]
    evidence: list[ArtifactEvidenceRef]


class ResearchArtifactDetailResponse(ResearchModel):
    artifact: ResearchArtifactDetail


class ResearchArtifactListResponse(ResearchModel):
    items: list[ResearchArtifactSummary]


class ResearchEventDto(ResearchModel):
    id: str
    run_id: str
    seq: int
    event_type: str
    event_schema_version: str
    payload: dict[str, object]
    created_at: datetime
