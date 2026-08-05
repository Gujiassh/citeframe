from __future__ import annotations

import hashlib
import shutil
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from ai_pdf_api.db.base import Base
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    EvidenceLocator,
    PdfLocatorDetail,
    ResearchBudgetLedger,
    ResearchClaim,
    ResearchEvidenceHandle,
    ResearchEvidenceSnapshot,
    ResearchExecutionAsset,
    ResearchExecutionPromptVersion,
    ResearchExecutionSnapshot,
    ResearchPlanRevision,
    ResearchPlanRevisionAsset,
    ResearchRun,
    ResearchStep,
    ResearchToolCall,
    User,
    WorkflowPromptBinding,
    Workspace,
    WorkspaceMembership,
)
from ai_pdf_api.services.research_evidence_provenance import evidence_source_fingerprint
from ai_pdf_api.services.research_idempotency import ResearchError, canonical_sha256
from ai_pdf_api.services.research_versions_service import (
    publish_research_versions_for_release,
)
from ai_pdf_api.services.research_worker import (
    claim_specific_research_step,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResearchWorkerFixture:
    db: Session
    run: ResearchRun
    snapshot: ResearchExecutionSnapshot
    ledger: ResearchBudgetLedger
    step: ResearchStep
    asset: Asset
    now: datetime


@dataclass(frozen=True)
class BranchClaimValue:
    id: str
    text: str
    evidence_handle_ids: tuple[str, ...]


@dataclass(frozen=True)
class BranchResultValue:
    branch_key: str
    claims: tuple[BranchClaimValue, ...]


@pytest.fixture()
def research_worker_db(
    tmp_path: Path,
    research_schema_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[ResearchWorkerFixture, None, None]:
    database_path = tmp_path / "research-worker.db"
    shutil.copyfile(research_schema_db, database_path)
    engine = create_engine(f"sqlite:///{database_path}", future=True)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    db = factory()
    now = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)
    user = User(
        id=str(uuid4()),
        email="research-worker@example.com",
        name="Research Worker",
        password_hash="hash",
        avatar_url="",
    )
    workspace = Workspace(
        id=str(uuid4()),
        name="Research Worker",
        created_by_user_id=user.id,
        created_at=now,
        updated_at=now,
    )
    asset = Asset(
        id=str(uuid4()),
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        asset_kind="pdf",
        title="Frozen source",
        source_filename="source.pdf",
        object_key=f"workspaces/{workspace.id}/source.pdf",
        mime_type="application/pdf",
        byte_size=100,
        source_sha256=sha256("source-bytes"),
        status="ready",
        current_processing_generation=2,
        current_index_version=3,
        created_at=now,
        updated_at=now,
    )
    run = ResearchRun(
        id=str(uuid4()),
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        status="queued",
        state_version=1,
        next_event_seq=1,
        cost_currency="USD",
        created_at=now,
        updated_at=now,
    )
    snapshot = ResearchExecutionSnapshot(
        id=str(uuid4()),
        workspace_id=workspace.id,
        run_id=run.id,
        approved_plan_revision_id=str(uuid4()),
        approval_decision_id=str(uuid4()),
        approved_plan_artifact_id=str(uuid4()),
        approved_plan_artifact_sha256=sha256("plan-artifact"),
        input_version=1,
        question_text="Compare the evidence.",
        scope_mode="selected",
        workflow_version_id=str(uuid4()),
        generation_provider="openai",
        generation_model="gpt-5.5",
        provider_config_fingerprint=sha256("provider-config"),
        pricing_version="research-pricing-v1",
        data_boundary_policy_version="test-boundary-v1",
        embedding_provider="test-embedding-provider",
        embedding_model="test-embedding-model",
        embedding_version="test-embedding-v1",
        retrieval_strategy="hybrid",
        retrieval_top_k=6,
        max_parallel_researchers=2,
        max_step_attempts=3,
        max_provider_calls=2,
        max_tool_calls=2,
        max_input_tokens=1_000,
        max_output_tokens=1_000,
        max_cost_microunits=10_000,
        cost_currency="USD",
        budget_policy_version="test-budget-v1",
        retry_policy_version="test-retry-v1",
        max_run_timeout_seconds=3_600,
        max_step_timeout_seconds=600,
        max_provider_timeout_seconds=120,
        execution_snapshot_sha256=sha256("execution-snapshot"),
        created_at=now,
    )
    run.approved_execution_snapshot_id = snapshot.id
    ledger = ResearchBudgetLedger(
        id=str(uuid4()),
        workspace_id=workspace.id,
        run_id=run.id,
        execution_snapshot_id=snapshot.id,
        currency="USD",
        state_version=1,
        reserved_provider_calls=0,
        reserved_tool_calls=0,
        reserved_input_tokens=0,
        reserved_output_tokens=0,
        actual_provider_calls=0,
        actual_tool_calls=0,
        actual_input_tokens=0,
        actual_output_tokens=0,
        usage_final=True,
        updated_at=now,
    )
    step = ResearchStep(
        id=str(uuid4()),
        workspace_id=workspace.id,
        run_id=run.id,
        execution_snapshot_id=snapshot.id,
        step_key="researcher:branch-a",
        step_kind="researcher",
        branch_key="branch-a",
        status="queued",
        state_version=1,
        max_attempts_snapshot=3,
        current_attempt_number=0,
        input_sha256=sha256("verify-input"),
        queued_at=now,
        created_at=now,
        updated_at=now,
    )
    membership = WorkspaceMembership(
        workspace_id=workspace.id,
        user_id=user.id,
        role="member",
        created_at=now,
    )
    db.add_all([user, workspace, membership, asset, run, snapshot, ledger, step])
    db.commit()
    monkeypatch.setattr(
        "ai_pdf_api.services.research_worker_provider.frozen_provider_config_matches_actual",
        lambda db, step, frozen_fingerprint: frozen_fingerprint == snapshot.provider_config_fingerprint,
    )
    yield ResearchWorkerFixture(
        db=db,
        run=run,
        snapshot=snapshot,
        ledger=ledger,
        step=step,
        asset=asset,
        now=now,
    )
    db.close()
    engine.dispose()


@pytest.fixture(scope="module")
def research_schema_db(tmp_path_factory: pytest.TempPathFactory) -> Generator[Path, None, None]:
    database_path = tmp_path_factory.mktemp("research-worker-schema") / "template.db"
    engine = create_engine(f"sqlite:///{database_path}", future=True)
    Base.metadata.create_all(engine)
    engine.dispose()
    yield database_path


def add_step(
    fixture: ResearchWorkerFixture,
    *,
    step_key: str,
    step_kind: str = "verifier",
    branch_key: str | None = None,
    queued_at: datetime | None = None,
) -> ResearchStep:
    step = ResearchStep(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        run_id=fixture.run.id,
        execution_snapshot_id=fixture.snapshot.id,
        step_key=step_key,
        step_kind=step_kind,
        branch_key=branch_key,
        status="queued",
        state_version=1,
        max_attempts_snapshot=3,
        current_attempt_number=0,
        input_sha256=sha256(f"{step_key}-input"),
        queued_at=queued_at or fixture.now,
        created_at=fixture.now,
        updated_at=fixture.now,
    )
    fixture.db.add(step)
    fixture.db.commit()
    return step


def add_execution_chain(
    fixture: ResearchWorkerFixture,
) -> tuple[ResearchRun, ResearchExecutionSnapshot]:
    run = ResearchRun(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        created_by_user_id=fixture.run.created_by_user_id,
        status="queued",
        state_version=1,
        next_event_seq=1,
        cost_currency="USD",
        created_at=fixture.now,
        updated_at=fixture.now,
    )
    values = {
        column.name: getattr(fixture.snapshot, column.name)
        for column in ResearchExecutionSnapshot.__table__.columns
    }
    values.update(
        id=str(uuid4()),
        run_id=run.id,
        approved_plan_revision_id=str(uuid4()),
        approval_decision_id=str(uuid4()),
        approved_plan_artifact_id=str(uuid4()),
    )
    snapshot = ResearchExecutionSnapshot(**values)
    run.approved_execution_snapshot_id = snapshot.id
    fixture.db.add_all([run, snapshot])
    fixture.db.commit()
    return run, snapshot


def make_planning_chain(
    fixture: ResearchWorkerFixture,
) -> tuple[ResearchPlanRevision, ResearchStep, ResearchBudgetLedger]:
    fixture.run.approved_execution_snapshot_id = None
    fixture.run.status = "planning"
    fixture.db.commit()
    fixture.db.delete(fixture.step)
    fixture.db.delete(fixture.ledger)
    fixture.db.delete(fixture.snapshot)
    fixture.db.commit()

    revision = ResearchPlanRevision(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        run_id=fixture.run.id,
        revision_number=1,
        created_by_user_id=fixture.run.created_by_user_id,
        question_text="Compare the evidence.",
        scope_mode="selected",
        proposed_workflow_version_id=str(uuid4()),
        planner_prompt_version_id=str(uuid4()),
        proposed_generation_provider="openai",
        proposed_generation_model="gpt-5.5",
        proposed_provider_config_fingerprint=sha256("provider-config"),
        proposed_pricing_version="research-pricing-v1",
        proposed_data_boundary_policy_version="test-boundary-v1",
        proposed_embedding_provider="test-embedding-provider",
        proposed_embedding_model="test-embedding-model",
        proposed_embedding_version="test-embedding-v1",
        proposed_retrieval_strategy="hybrid",
        proposed_retrieval_top_k=6,
        planning_max_provider_calls=2,
        planning_max_input_tokens=1_000,
        planning_max_output_tokens=1_000,
        planning_max_cost_microunits=10_000,
        planning_cost_currency="USD",
        planning_max_step_attempts=2,
        planning_budget_policy_version="test-budget-v1",
        planning_retry_policy_version="test-retry-v1",
        planning_max_step_timeout_seconds=600,
        planning_max_provider_timeout_seconds=120,
        proposed_max_parallel_researchers=2,
        proposed_max_step_attempts=3,
        proposed_max_provider_calls=8,
        proposed_max_tool_calls=8,
        proposed_max_input_tokens=8_000,
        proposed_max_output_tokens=4_000,
        proposed_max_cost_microunits=80_000,
        proposed_cost_currency="USD",
        proposed_budget_policy_version="test-budget-v1",
        proposed_retry_policy_version="test-retry-v1",
        proposed_max_run_timeout_seconds=3_600,
        proposed_max_step_timeout_seconds=600,
        proposed_max_provider_timeout_seconds=120,
        planning_snapshot_sha256=sha256("planning-snapshot"),
        created_at=fixture.now,
    )
    planner = ResearchStep(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        run_id=fixture.run.id,
        plan_revision_id=revision.id,
        step_key="revision-1:planner",
        step_kind="planner",
        status="queued",
        state_version=1,
        prompt_version_id=revision.planner_prompt_version_id,
        max_attempts_snapshot=2,
        current_attempt_number=0,
        input_sha256=sha256("planner-input"),
        queued_at=fixture.now,
        created_at=fixture.now,
        updated_at=fixture.now,
    )
    ledger = ResearchBudgetLedger(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        run_id=fixture.run.id,
        plan_revision_id=revision.id,
        currency="USD",
        state_version=1,
        reserved_provider_calls=0,
        reserved_tool_calls=0,
        reserved_input_tokens=0,
        reserved_output_tokens=0,
        actual_provider_calls=0,
        actual_tool_calls=0,
        actual_input_tokens=0,
        actual_output_tokens=0,
        usage_final=True,
        updated_at=fixture.now,
    )
    fixture.run.current_plan_revision_id = revision.id
    fixture.db.add_all(
        [
            revision,
            planner,
            ledger,
            ResearchPlanRevisionAsset(
                plan_revision_id=revision.id,
                asset_id=fixture.asset.id,
                workspace_id=fixture.run.workspace_id,
                asset_order=0,
                asset_kind_snapshot=fixture.asset.asset_kind,
                asset_title_snapshot=fixture.asset.title,
                processing_generation_snapshot=fixture.asset.current_processing_generation,
                index_version_snapshot=fixture.asset.current_index_version,
            ),
        ]
    )
    fixture.db.commit()
    return revision, planner, ledger


def lease_planner_step(fixture: ResearchWorkerFixture, planner: ResearchStep):
    return claim_specific_research_step(
        fixture.db,
        run_id=fixture.run.id,
        step_key=planner.step_key,
        branch_key=None,
        worker_instance_id="planner-worker",
        lease_seconds=60,
        now=fixture.now,
    )


def seed_frozen_evidence(
    fixture: ResearchWorkerFixture,
    attempt_id: str,
    *,
    query: str = "facts",
    tool_call_key: str = "search-replay",
) -> ResearchEvidenceHandle:
    representation = AssetRepresentation(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        asset_id=fixture.asset.id,
        representation_kind="pdf_page_layout",
        processing_generation=fixture.asset.current_processing_generation,
        generator_provider="test-parser",
        generator_model="test-parser-model",
        generator_version="test-parser-v1",
        object_key=f"representations/{fixture.asset.id}/pages.json",
        content_sha256=sha256("representation"),
        created_at=fixture.now,
    )
    locator = EvidenceLocator(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        asset_id=fixture.asset.id,
        locator_kind="pdf_page",
        locator_version=1,
        processing_generation_snapshot=fixture.asset.current_processing_generation,
        representation_id_snapshot=representation.id,
        created_at=fixture.now,
    )
    evidence = ResearchEvidenceSnapshot(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        run_id=fixture.run.id,
        captured_by_step_id=fixture.step.id,
        evidence_locator_id=locator.id,
        asset_id=fixture.asset.id,
        asset_kind_snapshot=fixture.asset.asset_kind,
        asset_title_snapshot=fixture.asset.title,
        excerpt_snapshot="Frozen evidence excerpt.",
        processing_generation_snapshot=fixture.asset.current_processing_generation,
        representation_id_snapshot=representation.id,
        parser_version_snapshot=representation.generator_version,
        index_version_snapshot=fixture.asset.current_index_version,
        retrieval_channel="text",
        source_fingerprint_sha256="pending",
        created_at=fixture.now,
    )
    evidence.source_fingerprint_sha256 = evidence_source_fingerprint(
        evidence,
        locator_kind=locator.locator_kind,
    )
    tool_call = ResearchToolCall(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        run_id=fixture.run.id,
        execution_snapshot_id=fixture.snapshot.id,
        step_id=fixture.step.id,
        attempt_id=attempt_id,
        tool_call_key=tool_call_key,
        call_attempt_number=1,
        call_order=0,
        tool_name="evidence.search",
        tool_version=1,
        status="succeeded",
        request_sha256=canonical_sha256(
            {"query": query, "assetIds": [fixture.asset.id], "topK": 3}
        ),
        result_count=1,
        created_at=fixture.now,
        started_at=fixture.now,
        finished_at=fixture.now,
    )
    handle = ResearchEvidenceHandle(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        run_id=fixture.run.id,
        execution_snapshot_id=fixture.snapshot.id,
        owner_step_id=fixture.step.id,
        created_by_tool_call_id=tool_call.id,
        evidence_snapshot_id=evidence.id,
        result_order=0,
        handle_fingerprint_sha256=sha256("frozen-handle"),
        created_at=fixture.now,
    )
    fixture.db.add_all(
        [
            ResearchExecutionAsset(
                execution_snapshot_id=fixture.snapshot.id,
                workspace_id=fixture.run.workspace_id,
                asset_id=fixture.asset.id,
                asset_order=0,
                asset_kind_snapshot=fixture.asset.asset_kind,
                asset_title_snapshot=fixture.asset.title,
                processing_generation_snapshot=fixture.asset.current_processing_generation,
                index_version_snapshot=fixture.asset.current_index_version,
            ),
            representation,
            locator,
            PdfLocatorDetail(locator_id=locator.id, page_number=1),
            evidence,
            tool_call,
            handle,
        ]
    )
    fixture.db.commit()
    return handle


def make_final_publication_chain(
    fixture: ResearchWorkerFixture,
) -> tuple[ResearchClaim, ResearchClaim]:
    workflow, _planner = publish_research_versions_for_release(fixture.db, fixture.now)
    fixture.db.flush()
    bindings = list(
        fixture.db.scalars(
            select(WorkflowPromptBinding).where(
                WorkflowPromptBinding.workflow_version_id == workflow.id
            )
        ).all()
    )
    prompt_ids = {binding.node_key: binding.prompt_version_id for binding in bindings}
    fixture.snapshot.workflow_version_id = workflow.id
    fixture.step.step_key = "artifact_publisher"
    fixture.step.step_kind = "artifact_publisher"
    fixture.step.branch_key = None
    fixture.step.prompt_version_id = prompt_ids["synthesizer"]
    fixture.db.add_all(
        [
            ResearchExecutionPromptVersion(
                execution_snapshot_id=fixture.snapshot.id,
                node_key=binding.node_key,
                prompt_version_id=binding.prompt_version_id,
            )
            for binding in bindings
        ]
    )
    fact = ResearchClaim(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        run_id=fixture.run.id,
        claim_key="fact-claim",
        claim_order=0,
        statement_text="Supported fact.",
        statement_sha256=sha256("Supported fact."),
        produced_by_step_id=fixture.step.id,
        verification_status="supported",
        conflict_status="none",
        created_at=fixture.now,
        verified_at=fixture.now,
    )
    unresolved = ResearchClaim(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        run_id=fixture.run.id,
        claim_key="unresolved-claim",
        claim_order=1,
        statement_text="Supported but unresolved claim.",
        statement_sha256=sha256("Supported but unresolved claim."),
        produced_by_step_id=fixture.step.id,
        verification_status="supported",
        conflict_status="resolved_unresolved",
        created_at=fixture.now,
        verified_at=fixture.now,
    )
    fixture.db.add_all([fact, unresolved])
    fixture.db.commit()
    return fact, unresolved


def lease_default_step(fixture: ResearchWorkerFixture):
    return claim_specific_research_step(
        fixture.db,
        run_id=fixture.run.id,
        step_key=fixture.step.step_key,
        branch_key=fixture.step.branch_key,
        worker_instance_id="worker-1",
        lease_seconds=60,
        now=fixture.now,
    )


def assert_research_error(error: pytest.ExceptionInfo[ResearchError], code: str, status_code: int) -> None:
    assert error.value.code == code
    assert error.value.status_code == status_code
