"""Plan approval materialization: execution snapshot, DAG, and budget ledger."""

from __future__ import annotations

from datetime import datetime

from ai_pdf_api.core.settings import settings
from ai_pdf_api.models import (
    Asset,
    HumanDecision,
    PromptVersion,
    ResearchArtifact,
    ResearchBudgetLedger,
    ResearchExecutionAsset,
    ResearchExecutionPromptVersion,
    ResearchExecutionSnapshot,
    ResearchPlanRevision,
    ResearchPlanRevisionAsset,
    ResearchRun,
    ResearchStep,
    ResearchStepDependency,
    WorkflowPromptBinding,
    Workspace,
)
from ai_pdf_api.services.research_constants import (
    BUDGET_POLICY_VERSION,
    DATA_BOUNDARY_POLICY,
    PRICING_VERSION,
    PROMPT_VERSION_IDS,
    RETRY_POLICY_VERSION,
    WORKFLOW_VERSION_ID,
)
from ai_pdf_api.services.research_idempotency import ResearchError, canonical_sha256
from ai_pdf_api.services.research_agent_io_registry import resolve_registry
from ai_pdf_api.services.research_runs import (
    build_execution_snapshot_hash_payload,
    build_plan_snapshot_hash_payload,
)
from ai_pdf_api.services.research_versions_service import (
    _matches_frozen_profile_fingerprint,
    ensure_research_versions,
)
from sqlalchemy import select
from sqlalchemy.orm import Session


def _approve_plan(
    db: Session,
    run: ResearchRun,
    decision: HumanDecision,
    revision: ResearchPlanRevision,
    now: datetime,
) -> ResearchExecutionSnapshot:
    from ai_pdf_api.services.research_views import load_research_plan_artifact

    plan_artifact = db.get(ResearchArtifact, decision.input_artifact_id)
    if (
        plan_artifact is None
        or plan_artifact.run_id != run.id
        or plan_artifact.workspace_id != run.workspace_id
        or plan_artifact.content_sha256 != decision.input_artifact_sha256
    ):
        raise ResearchError("stale_plan_artifact", "The approved Research plan Artifact is invalid.", 409)
    try:
        plan_payload = load_research_plan_artifact(plan_artifact)
    except Exception as error:
        raise ResearchError(
            "research_artifact_integrity_mismatch",
            "The approved Research plan Artifact failed integrity or schema validation.",
            409,
        ) from error
    frozen_assets = list(
        db.scalars(
            select(ResearchPlanRevisionAsset)
            .where(ResearchPlanRevisionAsset.plan_revision_id == revision.id)
            .order_by(ResearchPlanRevisionAsset.asset_order)
        ).all()
    )
    current_assets = {
        item.id: item
        for item in db.scalars(select(Asset).where(Asset.id.in_([row.asset_id for row in frozen_assets]))).all()
    }
    for row in frozen_assets:
        asset = current_assets.get(row.asset_id)
        if (
            asset is None
            or asset.workspace_id != run.workspace_id
            or asset.deleted_at is not None
            or asset.status != "ready"
            or asset.current_processing_generation != row.processing_generation_snapshot
            or asset.current_index_version != row.index_version_snapshot
        ):
            raise ResearchError("stale_plan_snapshot", "A frozen Asset changed after planning.", 409)
    workflow, planner_prompt = ensure_research_versions(db)
    bindings = list(
        db.execute(
            select(WorkflowPromptBinding, PromptVersion)
            .join(PromptVersion, PromptVersion.id == WorkflowPromptBinding.prompt_version_id)
            .where(WorkflowPromptBinding.workflow_version_id == revision.proposed_workflow_version_id)
            .order_by(WorkflowPromptBinding.node_key)
        ).all()
    )
    workspace = db.get(Workspace, run.workspace_id)
    expected_policy = (
        WORKFLOW_VERSION_ID,
        PROMPT_VERSION_IDS["planner"],
        settings.generation_provider,
        settings.generation_model,
        # Fingerprint compared via dual-read below; keep placeholder slot shape stable.
        revision.proposed_provider_config_fingerprint,
        PRICING_VERSION,
        DATA_BOUNDARY_POLICY,
        settings.embedding_provider,
        settings.embedding_model,
        settings.embedding_version,
        settings.retrieval_strategy,
        workspace.retrieval_top_k if workspace else None,
        2,
        32_000,
        8_000,
        500_000,
        run.cost_currency,
        3,
        BUDGET_POLICY_VERSION,
        RETRY_POLICY_VERSION,
        300,
        120,
        3,
        3,
        32,
        64,
        250_000,
        64_000,
        5_000_000,
        run.cost_currency,
        BUDGET_POLICY_VERSION,
        RETRY_POLICY_VERSION,
        1800,
        300,
        120,
    )
    frozen_policy = (
        revision.proposed_workflow_version_id,
        revision.planner_prompt_version_id,
        revision.proposed_generation_provider,
        revision.proposed_generation_model,
        revision.proposed_provider_config_fingerprint,
        revision.proposed_pricing_version,
        revision.proposed_data_boundary_policy_version,
        revision.proposed_embedding_provider,
        revision.proposed_embedding_model,
        revision.proposed_embedding_version,
        revision.proposed_retrieval_strategy,
        revision.proposed_retrieval_top_k,
        revision.planning_max_provider_calls,
        revision.planning_max_input_tokens,
        revision.planning_max_output_tokens,
        revision.planning_max_cost_microunits,
        revision.planning_cost_currency,
        revision.planning_max_step_attempts,
        revision.planning_budget_policy_version,
        revision.planning_retry_policy_version,
        revision.planning_max_step_timeout_seconds,
        revision.planning_max_provider_timeout_seconds,
        revision.proposed_max_parallel_researchers,
        revision.proposed_max_step_attempts,
        revision.proposed_max_provider_calls,
        revision.proposed_max_tool_calls,
        revision.proposed_max_input_tokens,
        revision.proposed_max_output_tokens,
        revision.proposed_max_cost_microunits,
        revision.proposed_cost_currency,
        revision.proposed_budget_policy_version,
        revision.proposed_retry_policy_version,
        revision.proposed_max_run_timeout_seconds,
        revision.proposed_max_step_timeout_seconds,
        revision.proposed_max_provider_timeout_seconds,
    )
    if (
        workflow.id != revision.proposed_workflow_version_id
        or planner_prompt.id != revision.planner_prompt_version_id
        or frozen_policy != expected_policy
        or not _matches_frozen_profile_fingerprint(
            revision.proposed_provider_config_fingerprint,
            retrieval_top_k=revision.proposed_retrieval_top_k,
        )
        or any(prompt.availability != "active" for _binding, prompt in bindings)
        or canonical_sha256(build_plan_snapshot_hash_payload(revision, frozen_assets, bindings))
        != revision.planning_snapshot_sha256
    ):
        raise ResearchError(
            "research_execution_policy_unavailable",
            "The approved Research execution profile is no longer available.",
            422,
        )
    try:
        resolve_registry(
            agent_result_schema_version=revision.agent_result_schema_version,
            context_policy_version=revision.context_policy_version,
            compact_policy_version=revision.compact_policy_version,
            for_new_run=True,
        )
    except ValueError as error:
        raise ResearchError(
            "research_agent_io_version_unavailable",
            "The approved Research agent I/O registry version is unavailable for new execution.",
            422,
        ) from error
    snapshot_payload = build_execution_snapshot_hash_payload(revision, decision, frozen_assets, bindings)
    snapshot = ResearchExecutionSnapshot(
        workspace_id=run.workspace_id,
        run_id=run.id,
        approved_plan_revision_id=revision.id,
        approval_decision_id=decision.id,
        approved_plan_artifact_id=decision.input_artifact_id,
        approved_plan_artifact_sha256=decision.input_artifact_sha256,
        input_version=revision.revision_number,
        question_text=revision.question_text,
        scope_mode=revision.scope_mode,
        workflow_version_id=revision.proposed_workflow_version_id,
        generation_provider=revision.proposed_generation_provider,
        generation_model=revision.proposed_generation_model,
        provider_config_fingerprint=revision.proposed_provider_config_fingerprint,
        pricing_version=revision.proposed_pricing_version,
        data_boundary_policy_version=revision.proposed_data_boundary_policy_version,
        embedding_provider=revision.proposed_embedding_provider,
        embedding_model=revision.proposed_embedding_model,
        embedding_version=revision.proposed_embedding_version,
        retrieval_strategy=revision.proposed_retrieval_strategy,
        retrieval_top_k=revision.proposed_retrieval_top_k,
        max_parallel_researchers=revision.proposed_max_parallel_researchers,
        max_step_attempts=revision.proposed_max_step_attempts,
        max_provider_calls=revision.proposed_max_provider_calls,
        max_tool_calls=revision.proposed_max_tool_calls,
        max_input_tokens=revision.proposed_max_input_tokens,
        max_output_tokens=revision.proposed_max_output_tokens,
        max_cost_microunits=revision.proposed_max_cost_microunits,
        cost_currency=revision.proposed_cost_currency,
        budget_policy_version=revision.proposed_budget_policy_version,
        retry_policy_version=revision.proposed_retry_policy_version,
        max_run_timeout_seconds=revision.proposed_max_run_timeout_seconds,
        max_step_timeout_seconds=revision.proposed_max_step_timeout_seconds,
        max_provider_timeout_seconds=revision.proposed_max_provider_timeout_seconds,
        agent_result_schema_version=revision.agent_result_schema_version,
        context_policy_version=revision.context_policy_version,
        compact_policy_version=revision.compact_policy_version,
        execution_snapshot_sha256=canonical_sha256(snapshot_payload),
        created_at=now,
    )
    db.add(snapshot)
    db.flush()
    for row in frozen_assets:
        db.add(
            ResearchExecutionAsset(
                execution_snapshot_id=snapshot.id,
                workspace_id=run.workspace_id,
                asset_id=row.asset_id,
                asset_order=row.asset_order,
                asset_kind_snapshot=row.asset_kind_snapshot,
                asset_title_snapshot=row.asset_title_snapshot,
                processing_generation_snapshot=row.processing_generation_snapshot,
                index_version_snapshot=row.index_version_snapshot,
            )
        )
    for binding, prompt in bindings:
        db.add(
            ResearchExecutionPromptVersion(
                execution_snapshot_id=snapshot.id,
                node_key=binding.node_key,
                prompt_version_id=prompt.id,
            )
        )
    prompt_ids = {binding.node_key: prompt.id for binding, prompt in bindings}
    execution_steps: dict[str, ResearchStep] = {}
    frozen_asset_ids = {item.asset_id for item in frozen_assets}
    for subproblem in plan_payload.subproblems:
        if not set(subproblem.asset_ids).issubset(frozen_asset_ids):
            raise ResearchError("stale_plan_artifact", "The Research plan exceeds its frozen Asset scope.", 409)
        step = ResearchStep(
            workspace_id=run.workspace_id,
            run_id=run.id,
            execution_snapshot_id=snapshot.id,
            step_key=f"researcher:{subproblem.id}",
            step_kind="researcher",
            branch_key=subproblem.id,
            status="queued",
            prompt_version_id=prompt_ids["researchers"],
            max_attempts_snapshot=snapshot.max_step_attempts,
            queued_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(step)
        execution_steps[step.step_key] = step
    for key, kind, prompt_key in (
        ("join", "join", None),
        ("verifier", "verifier", "verifier"),
        ("critic", "critic", "critic"),
        ("conflict_decision_gate", "conflict_decision_gate", "critic"),
        ("synthesizer", "synthesizer", "synthesizer"),
        ("artifact_publisher", "artifact_publisher", "synthesizer"),
    ):
        step = ResearchStep(
            workspace_id=run.workspace_id,
            run_id=run.id,
            execution_snapshot_id=snapshot.id,
            step_key=key,
            step_kind=kind,
            status="pending",
            prompt_version_id=prompt_ids.get(prompt_key) if prompt_key else None,
            max_attempts_snapshot=snapshot.max_step_attempts,
            created_at=now,
            updated_at=now,
        )
        db.add(step)
        execution_steps[key] = step
    db.flush()
    for researcher in (step for key, step in execution_steps.items() if key.startswith("researcher:")):
        db.add(ResearchStepDependency(step_id=execution_steps["join"].id, depends_on_step_id=researcher.id))
    for step_key, dependency_key in (
        ("verifier", "join"),
        ("critic", "verifier"),
        ("conflict_decision_gate", "critic"),
        ("synthesizer", "conflict_decision_gate"),
        ("artifact_publisher", "synthesizer"),
    ):
        db.add(
            ResearchStepDependency(
                step_id=execution_steps[step_key].id,
                depends_on_step_id=execution_steps[dependency_key].id,
            )
        )
    db.add(
        ResearchBudgetLedger(
            workspace_id=run.workspace_id,
            run_id=run.id,
            plan_revision_id=None,
            execution_snapshot_id=snapshot.id,
            currency=run.cost_currency,
            updated_at=now,
        )
    )
    run.approved_execution_snapshot_id = snapshot.id
    gate = db.get(ResearchStep, decision.gate_step_id)
    if gate:
        gate.status = "succeeded"
        gate.state_version += 1
        gate.finished_at = now
        gate.updated_at = now
    return snapshot
