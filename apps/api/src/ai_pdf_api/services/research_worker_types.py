from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from ai_pdf_api.models import ResearchRun, ResearchStep, ResearchStepAttempt
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ResearchStepLease:
    workspace_id: str
    run_id: str
    step_id: str
    step_key: str
    step_kind: str
    branch_key: str | None
    attempt_id: str
    attempt_number: int
    lease_token: str
    lease_expires_at: datetime


@dataclass(frozen=True)
class ProviderReservation:
    provider_call_id: str
    budget_ledger_id: str


@dataclass(frozen=True)
class ToolCallReservation:
    tool_call_id: str
    budget_ledger_id: str


@dataclass(frozen=True)
class PlanSubproblemDraft:
    question: str
    asset_ids: tuple[str, ...] = ()
    expected_evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class FrozenEvidence:
    evidence_handle: str
    workspace_id: str
    run_id: str
    execution_snapshot_id: str
    owner_step_id: str
    branch_key: str
    asset_id: str
    asset_kind: str
    asset_title: str
    excerpt: str
    processing_generation: int
    index_version: int
    representation_id: str
    parser_version: str
    locator_id: str
    locator_kind: str
    source_fingerprint_sha256: str
    created_by_tool_call_id: str
    score: float


@dataclass(frozen=True)
class LoadedFrozenEvidence:
    evidence_handle: str
    asset_id: str
    asset_kind: str
    asset_title: str
    source_available: bool
    content: str
    content_sha256: str
    processing_generation: int
    index_version: int
    representation_id: str
    parser_version: str
    locator_id: str
    locator_kind: str


StepCompletionCallback = Callable[
    [Session, ResearchRun, ResearchStep, ResearchStepAttempt],
    tuple[int, list[str]],
]
