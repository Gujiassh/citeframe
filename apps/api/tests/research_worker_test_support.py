from __future__ import annotations

import hashlib
import shutil
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from ai_pdf_api.db.base import Base
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    EvidenceLocator,
    HumanDecision,
    HumanDecisionClaim,
    PdfLocatorDetail,
    PromptVersion,
    ResearchArtifact,
    ResearchArtifactClaim,
    ResearchArtifactPromptVersion,
    ResearchBudgetLedger,
    ResearchClaim,
    ResearchClaimEvidence,
    ResearchEvidenceHandle,
    ResearchEvidenceSnapshot,
    ResearchExecutionAsset,
    ResearchExecutionPromptVersion,
    ResearchExecutionSnapshot,
    ResearchPlanRevision,
    ResearchPlanRevisionAsset,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
    ResearchToolCall,
    User,
    WorkflowPromptBinding,
    Workspace,
    WorkspaceMembership,
)
from ai_pdf_api.services.research.research_evidence_provenance import (
    evidence_source_fingerprint,
)
from ai_pdf_api.services.research.research_idempotency import (
    ResearchError,
    canonical_json,
    canonical_sha256,
)
from ai_pdf_api.services.research.research_versions_service import (
    publish_research_versions_for_release,
)
from ai_pdf_api.services.research.research_worker import (
    claim_specific_research_step,
)
from citeframe_research_persistence.snapshot_integrity import (
    build_execution_snapshot_hash_payload,
    build_plan_snapshot_hash_payload,
)
from sqlalchemy import create_engine, func, select
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
    factory = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, future=True
    )
    db = factory()
    database_now = db.scalar(select(func.current_timestamp()))
    assert database_now is not None
    now = (
        database_now.replace(tzinfo=UTC)
        if database_now.tzinfo is None
        else database_now.astimezone(UTC)
    )
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
        agent_result_schema_version="research-agent-results-v1",
        context_policy_version="research-context-policy-v1",
        compact_policy_version="research-compact-policy-v1",
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
        "ai_pdf_api.services.research.research_worker_provider.frozen_provider_config_matches_actual",
        lambda db, step, frozen_fingerprint: (
            frozen_fingerprint == snapshot.provider_config_fingerprint
        ),
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
def research_schema_db(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[Path, None, None]:
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
    top_k: int = 3,
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
            {"query": query, "assetIds": [fixture.asset.id], "topK": top_k}
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
    prompts = {
        prompt.id: prompt
        for prompt in fixture.db.scalars(
            select(PromptVersion).where(
                PromptVersion.id.in_(
                    [binding.prompt_version_id for binding in bindings]
                )
            )
        ).all()
    }
    binding_pairs = [
        (binding, prompts[binding.prompt_version_id]) for binding in bindings
    ]

    # Publication finalization validates the complete immutable approval graph,
    # not just the snapshot primary key.  Seed the same revision/asset/decision
    # chain produced by plan approval so unit tests exercise the real oracle.
    revision = ResearchPlanRevision(
        id=fixture.snapshot.approved_plan_revision_id,
        workspace_id=fixture.run.workspace_id,
        run_id=fixture.run.id,
        revision_number=fixture.snapshot.input_version,
        created_by_user_id=fixture.run.created_by_user_id,
        question_text=fixture.snapshot.question_text,
        scope_mode=fixture.snapshot.scope_mode,
        proposed_workflow_version_id=workflow.id,
        planner_prompt_version_id=prompt_ids["planner"],
        proposed_generation_provider=fixture.snapshot.generation_provider,
        proposed_generation_model=fixture.snapshot.generation_model,
        proposed_provider_config_fingerprint=(
            fixture.snapshot.provider_config_fingerprint
        ),
        proposed_pricing_version=fixture.snapshot.pricing_version,
        proposed_data_boundary_policy_version=(
            fixture.snapshot.data_boundary_policy_version
        ),
        proposed_embedding_provider=fixture.snapshot.embedding_provider,
        proposed_embedding_model=fixture.snapshot.embedding_model,
        proposed_embedding_version=fixture.snapshot.embedding_version,
        proposed_retrieval_strategy=fixture.snapshot.retrieval_strategy,
        proposed_retrieval_top_k=fixture.snapshot.retrieval_top_k,
        planning_max_provider_calls=2,
        planning_max_input_tokens=1_000,
        planning_max_output_tokens=1_000,
        planning_max_cost_microunits=10_000,
        planning_cost_currency="USD",
        planning_max_step_attempts=2,
        planning_budget_policy_version="test-plan-budget-v1",
        planning_retry_policy_version="test-plan-retry-v1",
        planning_max_step_timeout_seconds=600,
        planning_max_provider_timeout_seconds=120,
        proposed_max_parallel_researchers=(fixture.snapshot.max_parallel_researchers),
        proposed_max_step_attempts=fixture.snapshot.max_step_attempts,
        proposed_max_provider_calls=fixture.snapshot.max_provider_calls,
        proposed_max_tool_calls=fixture.snapshot.max_tool_calls,
        proposed_max_input_tokens=fixture.snapshot.max_input_tokens,
        proposed_max_output_tokens=fixture.snapshot.max_output_tokens,
        proposed_max_cost_microunits=fixture.snapshot.max_cost_microunits,
        proposed_cost_currency=fixture.snapshot.cost_currency,
        proposed_budget_policy_version=fixture.snapshot.budget_policy_version,
        proposed_retry_policy_version=fixture.snapshot.retry_policy_version,
        proposed_max_run_timeout_seconds=fixture.snapshot.max_run_timeout_seconds,
        proposed_max_step_timeout_seconds=fixture.snapshot.max_step_timeout_seconds,
        proposed_max_provider_timeout_seconds=(
            fixture.snapshot.max_provider_timeout_seconds
        ),
        agent_result_schema_version=fixture.snapshot.agent_result_schema_version,
        context_policy_version=fixture.snapshot.context_policy_version,
        compact_policy_version=fixture.snapshot.compact_policy_version,
        planning_snapshot_sha256="0" * 64,
        created_at=fixture.now,
    )
    frozen_plan_asset = ResearchPlanRevisionAsset(
        plan_revision_id=revision.id,
        asset_id=fixture.asset.id,
        workspace_id=fixture.run.workspace_id,
        asset_order=0,
        asset_kind_snapshot=fixture.asset.asset_kind,
        asset_title_snapshot=fixture.asset.title,
        processing_generation_snapshot=fixture.asset.current_processing_generation,
        index_version_snapshot=fixture.asset.current_index_version,
    )
    revision.planning_snapshot_sha256 = canonical_sha256(
        build_plan_snapshot_hash_payload(
            revision,
            [frozen_plan_asset],
            binding_pairs,
        )
    )
    planner = ResearchStep(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        run_id=fixture.run.id,
        plan_revision_id=revision.id,
        prompt_version_id=prompt_ids["planner"],
        step_key="revision-1:planner",
        step_kind="planner",
        status="succeeded",
        state_version=2,
        max_attempts_snapshot=2,
        current_attempt_number=1,
        input_sha256=sha256("final-plan-input"),
        queued_at=fixture.now,
        started_at=fixture.now,
        finished_at=fixture.now,
        created_at=fixture.now,
        updated_at=fixture.now,
    )
    planner_attempt = ResearchStepAttempt(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        step_id=planner.id,
        attempt_number=1,
        status="succeeded",
        input_sha256=planner.input_sha256,
        output_sha256=sha256("final-plan-artifact"),
        provider_call_count=0,
        tool_call_count=0,
        input_tokens=0,
        output_tokens=0,
        cost_microunits=0,
        started_at=fixture.now,
        finished_at=fixture.now,
    )
    plan_gate = ResearchStep(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        run_id=fixture.run.id,
        plan_revision_id=revision.id,
        step_key="revision-1:plan-approval-gate",
        step_kind="plan_approval_gate",
        status="succeeded",
        state_version=2,
        max_attempts_snapshot=2,
        current_attempt_number=1,
        input_sha256=sha256("final-plan-gate-input"),
        queued_at=fixture.now,
        started_at=fixture.now,
        finished_at=fixture.now,
        created_at=fixture.now,
        updated_at=fixture.now,
    )
    plan_gate_attempt = ResearchStepAttempt(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        step_id=plan_gate.id,
        attempt_number=1,
        status="succeeded",
        input_sha256=plan_gate.input_sha256,
        output_sha256=planner_attempt.output_sha256,
        provider_call_count=0,
        tool_call_count=0,
        input_tokens=0,
        output_tokens=0,
        cost_microunits=0,
        started_at=fixture.now,
        finished_at=fixture.now,
    )
    plan_artifact = ResearchArtifact(
        id=fixture.snapshot.approved_plan_artifact_id,
        workspace_id=fixture.run.workspace_id,
        run_id=fixture.run.id,
        generated_by_step_id=planner.id,
        generated_by_attempt_id=planner_attempt.id,
        artifact_kind="research_plan",
        visibility="user",
        logical_key=f"plan:revision-{revision.revision_number}",
        schema_version="1",
        object_key=(
            f"research/{fixture.run.workspace_id}/{fixture.run.id}/plan/plan.json"
        ),
        content_type="application/json",
        byte_size=len(b"{}"),
        content_sha256=planner_attempt.output_sha256,
        workflow_version_id=workflow.id,
        direct_prompt_version_id=prompt_ids["planner"],
        generation_provider=fixture.snapshot.generation_provider,
        generation_model=fixture.snapshot.generation_model,
        retention_class="workspace_lifetime",
        created_at=fixture.now,
    )
    approval = HumanDecision(
        id=fixture.snapshot.approval_decision_id,
        workspace_id=fixture.run.workspace_id,
        run_id=fixture.run.id,
        gate_step_id=plan_gate.id,
        decision_type="plan_approval",
        request_number=1,
        status="submitted",
        state_version=2,
        input_artifact_id=plan_artifact.id,
        input_artifact_sha256=plan_artifact.content_sha256,
        input_snapshot_sha256=revision.planning_snapshot_sha256,
        requested_at=fixture.now,
        decided_by_user_id=fixture.run.created_by_user_id,
        action="approve",
        decided_at=fixture.now,
    )
    fixture.snapshot.approved_plan_artifact_sha256 = plan_artifact.content_sha256
    fixture.snapshot.execution_snapshot_sha256 = canonical_sha256(
        build_execution_snapshot_hash_payload(
            revision,
            approval,
            [frozen_plan_asset],
            binding_pairs,
        )
    )
    fixture.run.current_plan_revision_id = revision.id
    fixture.db.add_all(
        [
            revision,
            frozen_plan_asset,
            planner,
            planner_attempt,
            plan_gate,
            plan_gate_attempt,
            plan_artifact,
            approval,
        ]
    )
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

    def succeeded_step(
        step_key: str,
        step_kind: str,
        *,
        prompt_key: str | None,
        branch_key: str | None = None,
        tool_call_count: int = 0,
    ) -> tuple[ResearchStep, ResearchStepAttempt]:
        step = ResearchStep(
            id=str(uuid4()),
            workspace_id=fixture.run.workspace_id,
            run_id=fixture.run.id,
            execution_snapshot_id=fixture.snapshot.id,
            prompt_version_id=prompt_ids[prompt_key] if prompt_key else None,
            step_key=step_key,
            step_kind=step_kind,
            branch_key=branch_key,
            status="succeeded",
            state_version=2,
            max_attempts_snapshot=3,
            current_attempt_number=1,
            input_sha256=sha256(f"{step_key}-input"),
            queued_at=fixture.now,
            started_at=fixture.now,
            finished_at=fixture.now,
            created_at=fixture.now,
            updated_at=fixture.now,
        )
        attempt = ResearchStepAttempt(
            id=str(uuid4()),
            workspace_id=fixture.run.workspace_id,
            step_id=step.id,
            attempt_number=1,
            status="succeeded",
            input_sha256=step.input_sha256,
            output_sha256=sha256(f"{step_key}-output"),
            provider_call_count=0,
            tool_call_count=tool_call_count,
            input_tokens=0,
            output_tokens=0,
            cost_microunits=0,
            started_at=fixture.now,
            finished_at=fixture.now,
        )
        return step, attempt

    # The original fixture step is the real evidence-producing researcher.  Seed
    # its succeeded Attempt before creating the frozen evidence/handle chain.
    researcher = fixture.step
    researcher.prompt_version_id = prompt_ids["researchers"]
    researcher.status = "succeeded"
    researcher.state_version = 2
    researcher.current_attempt_number = 1
    researcher.started_at = fixture.now
    researcher.finished_at = fixture.now
    researcher.updated_at = fixture.now
    researcher_attempt = ResearchStepAttempt(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        step_id=researcher.id,
        attempt_number=1,
        status="succeeded",
        input_sha256=researcher.input_sha256,
        output_sha256=sha256("researcher-output"),
        provider_call_count=0,
        tool_call_count=1,
        input_tokens=0,
        output_tokens=0,
        cost_microunits=0,
        started_at=fixture.now,
        finished_at=fixture.now,
    )
    fixture.db.add(researcher_attempt)
    fixture.db.commit()
    evidence_handle = seed_frozen_evidence(
        fixture,
        researcher_attempt.id,
        tool_call_key="final-publication-evidence",
        top_k=fixture.snapshot.retrieval_top_k,
    )

    verifier, verifier_attempt = succeeded_step(
        "verifier",
        "verifier",
        prompt_key="verifier",
    )
    critic, critic_attempt = succeeded_step(
        "critic",
        "critic",
        prompt_key="critic",
    )
    gate, gate_attempt = succeeded_step(
        "conflict-decision-gate",
        "conflict_decision_gate",
        prompt_key=None,
    )
    decision_time = fixture.now + timedelta(minutes=5)
    # Production publishes the conflict Artifact and completes the gate Attempt
    # before waiting for a human.  Only the gate Step finishes when that later
    # decision is submitted; keeping both timestamps equal hides this lifecycle.
    gate.finished_at = decision_time
    gate.updated_at = decision_time
    synthesizer, synthesis_attempt = succeeded_step(
        "synthesizer",
        "synthesizer",
        prompt_key="synthesizer",
    )
    fixture.db.add_all(
        [
            verifier,
            verifier_attempt,
            critic,
            critic_attempt,
            gate,
            gate_attempt,
            synthesizer,
            synthesis_attempt,
        ]
    )
    fixture.db.flush()

    fact = ResearchClaim(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        run_id=fixture.run.id,
        claim_key="fact-claim",
        claim_order=0,
        statement_text="Supported fact.",
        statement_sha256=sha256("Supported fact."),
        produced_by_step_id=researcher.id,
        verification_status="supported",
        verified_by_step_id=verifier.id,
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
        produced_by_step_id=researcher.id,
        verification_status="supported",
        verified_by_step_id=verifier.id,
        conflict_status="resolved_unresolved",
        critic_step_id=critic.id,
        created_at=fixture.now,
        verified_at=fixture.now,
    )
    fixture.db.add_all([fact, unresolved])
    fixture.db.flush()

    evidence_id = evidence_handle.evidence_snapshot_id
    fixture.db.add_all(
        [
            ResearchClaimEvidence(
                claim_id=fact.id,
                evidence_snapshot_id=evidence_id,
                evidence_order=0,
                relationship="supports",
                assessed_by_step_id=verifier.id,
            ),
            ResearchClaimEvidence(
                claim_id=unresolved.id,
                evidence_snapshot_id=evidence_id,
                evidence_order=0,
                relationship="supports",
                assessed_by_step_id=verifier.id,
            ),
        ]
    )

    conflict_payload = canonical_json(
        {"schemaVersion": 1, "conflictClaimIds": [unresolved.id]}
    )
    conflict_artifact_id = str(uuid4())
    conflict_artifact = ResearchArtifact(
        id=conflict_artifact_id,
        workspace_id=fixture.run.workspace_id,
        run_id=fixture.run.id,
        generated_by_step_id=gate.id,
        generated_by_attempt_id=gate_attempt.id,
        artifact_kind="conflict_report",
        visibility="user",
        logical_key="conflict-report:1",
        schema_version="1",
        object_key=(
            f"research/{fixture.run.workspace_id}/{fixture.run.id}/"
            f"{conflict_artifact_id}/conflicts.json"
        ),
        content_type="application/json",
        byte_size=len(conflict_payload),
        content_sha256=hashlib.sha256(conflict_payload).hexdigest(),
        workflow_version_id=fixture.snapshot.workflow_version_id,
        direct_prompt_version_id=prompt_ids["critic"],
        generation_provider=fixture.snapshot.generation_provider,
        generation_model=fixture.snapshot.generation_model,
        retention_class="workspace_lifetime",
        created_at=fixture.now,
    )
    gate_attempt.output_sha256 = conflict_artifact.content_sha256
    decision = HumanDecision(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        run_id=fixture.run.id,
        gate_step_id=gate.id,
        decision_type="conflict_resolution",
        request_number=1,
        status="submitted",
        state_version=2,
        input_artifact_id=conflict_artifact.id,
        input_artifact_sha256=conflict_artifact.content_sha256,
        input_snapshot_sha256=fixture.snapshot.execution_snapshot_sha256,
        requested_at=fixture.now,
        decided_by_user_id=fixture.run.created_by_user_id,
        action="keep_as_unresolved",
        decided_at=decision_time,
    )
    fixture.db.add_all([conflict_artifact, decision])
    fixture.db.flush()
    fixture.db.add_all(
        [
            ResearchArtifactClaim(
                artifact_id=conflict_artifact.id,
                claim_id=unresolved.id,
                claim_order=0,
                section_kind="conflict",
            ),
            HumanDecisionClaim(
                decision_id=decision.id,
                claim_id=unresolved.id,
                disposition="leave_unresolved",
            ),
            *(
                ResearchArtifactPromptVersion(
                    artifact_id=conflict_artifact.id,
                    node_key=binding.node_key,
                    prompt_version_id=binding.prompt_version_id,
                )
                for binding in bindings
            ),
        ]
    )

    selection = {"factClaimIds": [fact.id], "unresolvedClaimIds": [unresolved.id]}
    synthesis_attempt.output_sha256 = canonical_sha256(selection)
    checkpoint_payload = canonical_json(
        {
            "schemaVersion": 1,
            "runId": fixture.run.id,
            "stepId": synthesizer.id,
            "attemptId": synthesis_attempt.id,
            **selection,
        }
    )
    checkpoint = ResearchArtifact(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        run_id=fixture.run.id,
        generated_by_step_id=synthesizer.id,
        generated_by_attempt_id=synthesis_attempt.id,
        artifact_kind="execution_checkpoint",
        visibility="internal",
        logical_key="checkpoint:synthesis",
        schema_version="1",
        object_key="pending",
        content_type="application/json",
        byte_size=len(checkpoint_payload),
        content_sha256=hashlib.sha256(checkpoint_payload).hexdigest(),
        workflow_version_id=fixture.snapshot.workflow_version_id,
        direct_prompt_version_id=prompt_ids["synthesizer"],
        generation_provider=fixture.snapshot.generation_provider,
        generation_model=fixture.snapshot.generation_model,
        retention_class="workspace_lifetime",
        created_at=synthesis_attempt.finished_at,
    )
    checkpoint.object_key = (
        f"research/{fixture.run.workspace_id}/{fixture.run.id}/"
        f"{checkpoint.id}/checkpoint.json"
    )
    fixture.db.add(checkpoint)
    fixture.db.flush()
    synthesis_attempt.checkpoint_artifact_id = checkpoint.id
    fixture.run.latest_checkpoint_artifact_id = checkpoint.id

    # Reuse the original fixture Step as the queued publisher only after its
    # evidence-producing identity has been durably replaced by a fresh row.
    publisher = ResearchStep(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        run_id=fixture.run.id,
        execution_snapshot_id=fixture.snapshot.id,
        prompt_version_id=prompt_ids["synthesizer"],
        step_key="artifact_publisher",
        step_kind="artifact_publisher",
        branch_key=None,
        status="queued",
        state_version=1,
        max_attempts_snapshot=3,
        current_attempt_number=0,
        input_sha256=sha256("artifact-publisher-input"),
        queued_at=fixture.now,
        created_at=fixture.now,
        updated_at=fixture.now,
    )
    fixture.db.add(publisher)
    fixture.db.commit()
    object.__setattr__(fixture, "step", publisher)
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


def assert_research_error(
    error: pytest.ExceptionInfo[ResearchError], code: str, status_code: int
) -> None:
    assert error.value.code == code
    assert error.value.status_code == status_code
