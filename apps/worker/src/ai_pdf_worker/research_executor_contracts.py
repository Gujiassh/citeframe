from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, TypedDict

if TYPE_CHECKING:
    from ai_pdf_worker.research_executor_tools import EvidenceToolRegistry


class ResearchExecutionError(RuntimeError):
    pass


class ToolPolicyError(ResearchExecutionError):
    pass


class ResearchStepAutoRequeued(ResearchExecutionError):
    pass


@dataclass(frozen=True)
class PlanSubproblemDraft:
    question: str
    asset_ids: tuple[str, ...] = ()
    expected_evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResearchSubproblem:
    step_id: str
    branch_key: str
    question: str
    asset_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class FrozenAsset:
    asset_id: str
    processing_generation: int
    index_version: int


@dataclass(frozen=True)
class FrozenPrompt:
    node_key: str
    prompt_version_id: str
    prompt_key: str
    version: int
    step_kind: str
    template_text: str
    variables_schema_version: str
    variables_schema: dict[str, object]
    template_sha256: str


@dataclass(frozen=True)
class FailureDisposition:
    reason_code: str
    retryable: bool
    auto_requeued: bool
    step_status: str
    run_status: str


@dataclass(frozen=True)
class ApprovedResearchExecution:
    workspace_id: str
    run_id: str
    execution_snapshot_id: str
    snapshot_sha256: str
    question: str
    subproblems: tuple[ResearchSubproblem, ...]
    frozen_assets: tuple[FrozenAsset, ...]
    workflow_version_id: str
    prompt_version_ids: tuple[str, ...]
    provider_config_fingerprint: str
    budget_policy_version: str
    retry_policy_version: str
    max_parallel_researchers: int
    max_provider_calls: int
    max_tool_calls: int
    plan_revision_id: str | None = None
    max_input_tokens: int = 0
    max_output_tokens: int = 0
    max_cost_microunits: int = 0
    prompts: tuple[FrozenPrompt, ...] = ()


@dataclass(frozen=True)
class StepLease:
    step_id: str
    attempt_id: str
    attempt_number: int
    lease_token: str | None = None


@dataclass(frozen=True)
class ToolExecutionContext:
    workspace_id: str
    run_id: str
    execution_snapshot_id: str
    execution_snapshot_sha256: str
    step_id: str
    attempt_id: str
    branch_key: str
    frozen_assets: tuple[FrozenAsset, ...]


@dataclass(frozen=True)
class EvidenceHandle:
    id: str
    workspace_id: str
    run_id: str
    execution_snapshot_id: str
    owner_step_id: str
    branch_key: str
    asset_id: str
    processing_generation: int
    index_version: int
    representation_id: str
    parser_version: str
    locator_id: str
    locator_kind: Literal["pdf_page", "pdf_region", "image_region"]
    excerpt: str
    source_fingerprint_sha256: str
    created_by_tool_call_id: str


@dataclass(frozen=True)
class LoadedEvidence:
    evidence_handle: str
    asset_id: str
    processing_generation: int
    index_version: int
    representation_id: str
    parser_version: str
    locator_id: str
    locator_kind: Literal["pdf_page", "pdf_region", "image_region"]
    content: str
    content_sha256: str
    source_available: bool


@dataclass(frozen=True)
class DraftClaim:
    id: str
    text: str
    evidence_handle_ids: tuple[str, ...]


@dataclass(frozen=True)
class VerifiedClaim:
    id: str
    text: str
    evidence_handle_ids: tuple[str, ...]
    verification_status: Literal["supported", "unsupported"]
    conflict_status: Literal[
        "none",
        "conflicted",
        "resolved_excluded",
        "resolved_unresolved",
    ] = "none"


@dataclass(frozen=True)
class BranchResult:
    branch_key: str
    claims: tuple[DraftClaim, ...]
    evidence: tuple[EvidenceHandle, ...]


@dataclass(frozen=True)
class BranchTiming:
    branch_key: str
    started_ns: int
    finished_ns: int


@dataclass(frozen=True)
class SynthesisSelection:
    fact_claim_ids: tuple[str, ...]
    unresolved_claim_ids: tuple[str, ...]


class Planner(Protocol):
    def __call__(
        self,
        question: str,
        frozen_assets: Sequence[FrozenAsset],
        lease: StepLease | None = None,
    ) -> Sequence[PlanSubproblemDraft]: ...


class Researcher(Protocol):
    def __call__(
        self,
        subproblem: ResearchSubproblem,
        tools: EvidenceToolRegistry,
        lease: StepLease | None = None,
    ) -> BranchResult: ...


class Verifier(Protocol):
    def __call__(
        self,
        claims: Sequence[DraftClaim],
        evidence: Sequence[EvidenceHandle],
        lease: StepLease | None = None,
    ) -> Sequence[VerifiedClaim]: ...


class Critic(Protocol):
    def __call__(self, claims: Sequence[VerifiedClaim], lease: StepLease | None = None) -> Sequence[str]: ...


class Synthesizer(Protocol):
    def __call__(
        self,
        question: str,
        claims: Sequence[VerifiedClaim],
        unresolved: Sequence[VerifiedClaim],
        lease: StepLease | None = None,
    ) -> SynthesisSelection: ...


class EvidenceToolPort(Protocol):
    def restore_handles(self, context: ToolExecutionContext) -> Sequence[EvidenceHandle]: ...

    def search(
        self,
        context: ToolExecutionContext,
        *,
        tool_call_key: str,
        query: str,
        asset_ids: Sequence[str],
        top_k: int,
    ) -> Sequence[EvidenceHandle]: ...

    def load(
        self,
        context: ToolExecutionContext,
        *,
        tool_call_key: str,
        handle_ids: Sequence[str],
    ) -> Sequence[LoadedEvidence]: ...


class ResearchState(TypedDict, total=False):
    execution: ApprovedResearchExecution
    completed_nodes: list[str]
    branch_results: list[BranchResult]
    branch_timings: list[BranchTiming]
    verified_claims: list[VerifiedClaim]
    conflicts: list[str]
    unresolved: list[str]
    synthesis: SynthesisSelection
    artifact_id: str
    status: str


class ResearchLedger(Protocol):
    def load_approved_execution(self, run_id: str) -> ApprovedResearchExecution: ...

    def load_execution_state(
        self,
        execution: ApprovedResearchExecution,
    ) -> ResearchState | None: ...

    def load_conflict_resume_state(
        self,
        run_id: str,
        action: Literal["exclude_conflicted_claims", "keep_as_unresolved"],
    ) -> ResearchState: ...

    def claim_step(
        self,
        execution: ApprovedResearchExecution,
        *,
        step_key: str,
        branch_key: str | None,
    ) -> StepLease: ...

    def complete_branch(self, lease: StepLease, result: BranchResult) -> None: ...

    def complete_control_step(self, lease: StepLease) -> None: ...

    def complete_verification(
        self,
        lease: StepLease,
        claims: Sequence[VerifiedClaim],
    ) -> None: ...

    def complete_critique(
        self,
        lease: StepLease,
        claims: Sequence[VerifiedClaim],
        conflicts: Sequence[str],
    ) -> None: ...

    def wait_for_conflict_decision(
        self,
        lease: StepLease,
        conflicts: Sequence[str],
    ) -> None: ...

    def complete_synthesis(
        self,
        lease: StepLease,
        selection: SynthesisSelection,
    ) -> None: ...

    def step_failed(self, lease: StepLease, error_code: str) -> FailureDisposition: ...

    def load_completed_branch(
        self,
        execution: ApprovedResearchExecution,
        branch_key: str,
    ) -> BranchResult | None: ...

    def publish_final(
        self,
        lease: StepLease,
        execution: ApprovedResearchExecution,
        *,
        selection: SynthesisSelection,
        claims: Sequence[VerifiedClaim],
    ) -> str: ...
