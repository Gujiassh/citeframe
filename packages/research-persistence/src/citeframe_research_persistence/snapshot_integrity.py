"""Canonical Research execution snapshot payloads and persisted-graph validation."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from citeframe_persistence.models import (
    HumanDecision,
    PromptVersion,
    ResearchArtifact,
    ResearchExecutionAsset,
    ResearchExecutionPromptVersion,
    ResearchExecutionSnapshot,
    ResearchPlanRevision,
    ResearchPlanRevisionAsset,
    ResearchRun,
    ResearchStep,
    WorkflowPromptBinding,
    WorkflowVersion,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import canonical_sha256


def _snapshot_assets(assets: Sequence[Any]) -> list[dict[str, object]]:
    snapshots: list[dict[str, object]] = []
    for order, item in enumerate(assets):
        if hasattr(item, "asset_kind"):
            snapshots.append(
                {
                    "assetId": item.id,
                    "assetOrder": order,
                    "assetKind": item.asset_kind,
                    "assetTitle": item.title,
                    "processingGeneration": item.current_processing_generation,
                    "indexVersion": item.current_index_version,
                }
            )
        else:
            snapshots.append(
                {
                    "assetId": item.asset_id,
                    "assetOrder": item.asset_order,
                    "assetKind": item.asset_kind_snapshot,
                    "assetTitle": item.asset_title_snapshot,
                    "processingGeneration": item.processing_generation_snapshot,
                    "indexVersion": item.index_version_snapshot,
                }
            )
    return snapshots


def _revision_provider_payload(revision: ResearchPlanRevision) -> dict[str, object]:
    return {
        "generationProvider": revision.proposed_generation_provider,
        "generationModel": revision.proposed_generation_model,
        "embeddingProvider": revision.proposed_embedding_provider,
        "embeddingModel": revision.proposed_embedding_model,
        "embeddingVersion": revision.proposed_embedding_version,
        "retrievalStrategy": revision.proposed_retrieval_strategy,
        "retrievalTopK": revision.proposed_retrieval_top_k,
        "providerConfigFingerprint": revision.proposed_provider_config_fingerprint,
        "pricingVersion": revision.proposed_pricing_version,
        "dataBoundaryPolicyVersion": revision.proposed_data_boundary_policy_version,
    }


def _revision_execution_payload(
    revision: ResearchPlanRevision,
    prompt_versions: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "workflowVersionId": revision.proposed_workflow_version_id,
        "promptVersions": prompt_versions,
        "provider": _revision_provider_payload(revision),
        "budgetPolicyVersion": revision.proposed_budget_policy_version,
        "retryPolicyVersion": revision.proposed_retry_policy_version,
        "limits": {
            "maxProviderCalls": revision.proposed_max_provider_calls,
            "maxToolCalls": revision.proposed_max_tool_calls,
            "maxInputTokens": revision.proposed_max_input_tokens,
            "maxOutputTokens": revision.proposed_max_output_tokens,
            "maxParallelResearchers": revision.proposed_max_parallel_researchers,
            "runTimeoutSeconds": revision.proposed_max_run_timeout_seconds,
            "stepTimeoutSeconds": revision.proposed_max_step_timeout_seconds,
            "providerTimeoutSeconds": revision.proposed_max_provider_timeout_seconds,
            "maxAttemptsPerStep": revision.proposed_max_step_attempts,
        },
        "agentResultSchemaVersion": revision.agent_result_schema_version,
        "contextPolicyVersion": revision.context_policy_version,
        "compactPolicyVersion": revision.compact_policy_version,
    }


def build_plan_snapshot_hash_payload(
    revision: ResearchPlanRevision,
    assets: Sequence[Any],
    bindings: Sequence[tuple[WorkflowPromptBinding, PromptVersion]],
) -> dict[str, object]:
    """Build the canonical plan snapshot payload used by plan approval."""

    asset_rows = _snapshot_assets(assets)
    requested_scope: dict[str, object] = {"mode": revision.scope_mode}
    if revision.scope_mode == "selected":
        requested_scope["assetIds"] = [item["assetId"] for item in asset_rows]
    prompt_versions = [
        {"nodeKey": binding.node_key, "promptVersionId": prompt.id}
        for binding, prompt in bindings
    ]
    provider = _revision_provider_payload(revision)
    return {
        "revisionNumber": revision.revision_number,
        "question": revision.question_text,
        "requestedAssetScope": requested_scope,
        "planningAssetScope": {"assets": asset_rows},
        "planningExecution": {
            "workflowVersionId": revision.proposed_workflow_version_id,
            "plannerPromptVersionId": revision.planner_prompt_version_id,
            "provider": provider,
            "budgetPolicyVersion": revision.planning_budget_policy_version,
            "retryPolicyVersion": revision.planning_retry_policy_version,
            "limits": {
                "maxProviderCalls": revision.planning_max_provider_calls,
                "maxInputTokens": revision.planning_max_input_tokens,
                "maxOutputTokens": revision.planning_max_output_tokens,
                "plannerTimeoutSeconds": revision.planning_max_step_timeout_seconds,
                "providerTimeoutSeconds": revision.planning_max_provider_timeout_seconds,
                "maxPlannerAttempts": revision.planning_max_step_attempts,
            },
            "agentResultSchemaVersion": revision.agent_result_schema_version,
            "contextPolicyVersion": revision.context_policy_version,
            "compactPolicyVersion": revision.compact_policy_version,
        },
        "proposedResearchExecution": _revision_execution_payload(
            revision, prompt_versions
        ),
    }


def build_execution_snapshot_hash_payload(
    revision: ResearchPlanRevision,
    decision: HumanDecision,
    assets: Sequence[Any],
    bindings: Sequence[tuple[WorkflowPromptBinding, PromptVersion]],
) -> dict[str, object]:
    """Build the canonical execution snapshot payload from its approved sources."""

    return {
        "inputVersion": revision.revision_number,
        "approvalDecisionId": decision.id,
        "approvedPlanRevisionId": revision.id,
        "approvedPlanArtifactId": decision.input_artifact_id,
        "approvedPlanArtifactSha256": decision.input_artifact_sha256,
        "planningSnapshotSha256": revision.planning_snapshot_sha256,
        "question": revision.question_text,
        "scopeMode": revision.scope_mode,
        "frozenAssets": _snapshot_assets(assets),
        "execution": build_plan_snapshot_hash_payload(revision, assets, bindings)[
            "proposedResearchExecution"
        ],
    }


def _persisted_execution_payload(
    snapshot: ResearchExecutionSnapshot,
    prompt_rows: Sequence[ResearchExecutionPromptVersion],
) -> dict[str, object]:
    return {
        "workflowVersionId": snapshot.workflow_version_id,
        "promptVersions": [
            {"nodeKey": row.node_key, "promptVersionId": row.prompt_version_id}
            for row in prompt_rows
        ],
        "provider": {
            "generationProvider": snapshot.generation_provider,
            "generationModel": snapshot.generation_model,
            "embeddingProvider": snapshot.embedding_provider,
            "embeddingModel": snapshot.embedding_model,
            "embeddingVersion": snapshot.embedding_version,
            "retrievalStrategy": snapshot.retrieval_strategy,
            "retrievalTopK": snapshot.retrieval_top_k,
            "providerConfigFingerprint": snapshot.provider_config_fingerprint,
            "pricingVersion": snapshot.pricing_version,
            "dataBoundaryPolicyVersion": snapshot.data_boundary_policy_version,
        },
        "budgetPolicyVersion": snapshot.budget_policy_version,
        "retryPolicyVersion": snapshot.retry_policy_version,
        "limits": {
            "maxProviderCalls": snapshot.max_provider_calls,
            "maxToolCalls": snapshot.max_tool_calls,
            "maxInputTokens": snapshot.max_input_tokens,
            "maxOutputTokens": snapshot.max_output_tokens,
            "maxParallelResearchers": snapshot.max_parallel_researchers,
            "runTimeoutSeconds": snapshot.max_run_timeout_seconds,
            "stepTimeoutSeconds": snapshot.max_step_timeout_seconds,
            "providerTimeoutSeconds": snapshot.max_provider_timeout_seconds,
            "maxAttemptsPerStep": snapshot.max_step_attempts,
        },
        "agentResultSchemaVersion": snapshot.agent_result_schema_version,
        "contextPolicyVersion": snapshot.context_policy_version,
        "compactPolicyVersion": snapshot.compact_policy_version,
    }


def build_persisted_execution_snapshot_hash_payload(
    snapshot: ResearchExecutionSnapshot,
    revision: ResearchPlanRevision,
    assets: Sequence[ResearchExecutionAsset],
    prompt_rows: Sequence[ResearchExecutionPromptVersion],
) -> dict[str, object]:
    """Rebuild the hash payload from the persisted frozen snapshot rows."""

    return {
        "inputVersion": snapshot.input_version,
        "approvalDecisionId": snapshot.approval_decision_id,
        "approvedPlanRevisionId": snapshot.approved_plan_revision_id,
        "approvedPlanArtifactId": snapshot.approved_plan_artifact_id,
        "approvedPlanArtifactSha256": snapshot.approved_plan_artifact_sha256,
        "planningSnapshotSha256": revision.planning_snapshot_sha256,
        "question": snapshot.question_text,
        "scopeMode": snapshot.scope_mode,
        "frozenAssets": _snapshot_assets(assets),
        "execution": _persisted_execution_payload(snapshot, prompt_rows),
    }


def execution_snapshot_provenance_is_valid(
    db: Session,
    *,
    run: ResearchRun,
    snapshot: ResearchExecutionSnapshot,
    prompt_rows: Sequence[ResearchExecutionPromptVersion],
) -> bool:
    """Verify the snapshot hash and every source/frozen graph edge before publish."""

    revision = db.scalar(
        select(ResearchPlanRevision)
        .where(ResearchPlanRevision.id == snapshot.approved_plan_revision_id)
        .execution_options(populate_existing=True)
    )
    decision = db.scalar(
        select(HumanDecision)
        .where(HumanDecision.id == snapshot.approval_decision_id)
        .execution_options(populate_existing=True)
    )
    plan_artifact = db.scalar(
        select(ResearchArtifact)
        .where(ResearchArtifact.id == snapshot.approved_plan_artifact_id)
        .execution_options(populate_existing=True)
    )
    workflow = db.scalar(
        select(WorkflowVersion)
        .where(WorkflowVersion.id == snapshot.workflow_version_id)
        .execution_options(populate_existing=True)
    )
    if (
        revision is None
        or decision is None
        or plan_artifact is None
        or workflow is None
    ):
        return False
    plan_gate = db.scalar(
        select(ResearchStep)
        .where(ResearchStep.id == decision.gate_step_id)
        .execution_options(populate_existing=True)
    )
    revision_assets = list(
        db.scalars(
            select(ResearchPlanRevisionAsset)
            .where(ResearchPlanRevisionAsset.plan_revision_id == revision.id)
            .order_by(
                ResearchPlanRevisionAsset.asset_order,
                ResearchPlanRevisionAsset.asset_id,
            )
            .execution_options(populate_existing=True)
        ).all()
    )
    execution_assets = list(
        db.scalars(
            select(ResearchExecutionAsset)
            .where(ResearchExecutionAsset.execution_snapshot_id == snapshot.id)
            .order_by(
                ResearchExecutionAsset.asset_order,
                ResearchExecutionAsset.asset_id,
            )
            .execution_options(populate_existing=True)
        ).all()
    )
    binding_rows = list(
        db.execute(
            select(WorkflowPromptBinding, PromptVersion)
            .join(
                PromptVersion,
                PromptVersion.id == WorkflowPromptBinding.prompt_version_id,
            )
            .where(
                WorkflowPromptBinding.workflow_version_id
                == revision.proposed_workflow_version_id
            )
            .order_by(WorkflowPromptBinding.node_key)
            .execution_options(populate_existing=True)
        ).all()
    )
    ordered_prompts = sorted(prompt_rows, key=lambda row: row.node_key)
    source_prompt_ids = [
        (binding.node_key, prompt.id) for binding, prompt in binding_rows
    ]
    frozen_prompt_ids = [
        (row.node_key, row.prompt_version_id) for row in ordered_prompts
    ]
    source_payload = build_execution_snapshot_hash_payload(
        revision,
        decision,
        revision_assets,
        binding_rows,
    )
    persisted_payload = build_persisted_execution_snapshot_hash_payload(
        snapshot,
        revision,
        execution_assets,
        ordered_prompts,
    )
    plan_hash_valid = (
        canonical_sha256(
            build_plan_snapshot_hash_payload(
                revision,
                revision_assets,
                binding_rows,
            )
        )
        == revision.planning_snapshot_sha256
    )
    workflow_hash_valid = (
        canonical_sha256(workflow.manifest_json) == workflow.manifest_sha256
    )
    prompt_hashes_valid = all(
        canonical_sha256(
            {
                "template": prompt.template_text,
                "variables": prompt.variables_schema_json,
            }
        )
        == prompt.template_sha256
        for _binding, prompt in binding_rows
    )
    source_prompt_map = dict(source_prompt_ids)
    source_assets = _snapshot_assets(revision_assets)
    frozen_assets = _snapshot_assets(execution_assets)
    links_valid = (
        revision.run_id == run.id
        and revision.workspace_id == run.workspace_id
        and run.current_plan_revision_id == revision.id
        and snapshot.run_id == run.id
        and snapshot.workspace_id == run.workspace_id
        and snapshot.approved_plan_revision_id == revision.id
        and snapshot.input_version == revision.revision_number
        and snapshot.workflow_version_id == revision.proposed_workflow_version_id
        and decision.run_id == run.id
        and decision.workspace_id == run.workspace_id
        and decision.decision_type == "plan_approval"
        and decision.status == "submitted"
        and decision.action == "approve"
        and decision.input_artifact_id == plan_artifact.id
        and decision.input_artifact_sha256 == plan_artifact.content_sha256
        and decision.input_snapshot_sha256 == revision.planning_snapshot_sha256
        and snapshot.approved_plan_artifact_id == plan_artifact.id
        and snapshot.approved_plan_artifact_sha256 == plan_artifact.content_sha256
        and plan_artifact.run_id == run.id
        and plan_artifact.workspace_id == run.workspace_id
        and plan_artifact.artifact_kind == "research_plan"
        and plan_artifact.logical_key == f"plan:revision-{revision.revision_number}"
        and plan_artifact.workflow_version_id == snapshot.workflow_version_id
        and plan_gate is not None
        and plan_gate.run_id == run.id
        and plan_gate.workspace_id == run.workspace_id
        and plan_gate.plan_revision_id == revision.id
        and plan_gate.step_kind == "plan_approval_gate"
        and plan_gate.status == "succeeded"
        and workflow.id == snapshot.workflow_version_id
        and source_prompt_map.get("planner") == revision.planner_prompt_version_id
        and source_assets == frozen_assets
        and source_prompt_ids == frozen_prompt_ids
    )
    return bool(
        links_valid
        and plan_hash_valid
        and workflow_hash_valid
        and prompt_hashes_valid
        and source_payload == persisted_payload
        and canonical_sha256(source_payload) == snapshot.execution_snapshot_sha256
        and canonical_sha256(persisted_payload) == snapshot.execution_snapshot_sha256
    )


__all__ = [
    "build_execution_snapshot_hash_payload",
    "build_persisted_execution_snapshot_hash_payload",
    "build_plan_snapshot_hash_payload",
    "execution_snapshot_provenance_is_valid",
]
