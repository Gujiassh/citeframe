from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_pdf_api.modalities.evidence import serialize_evidence_locator
from ai_pdf_api.models import (
    Asset,
    HumanDecision,
    ResearchArtifact,
    ResearchArtifactClaim,
    ResearchArtifactPromptVersion,
    ResearchBudgetLedger,
    ResearchClaim,
    ResearchClaimEvidence,
    ResearchEvidenceSnapshot,
    ResearchExecutionAsset,
    ResearchExecutionPromptVersion,
    ResearchExecutionSnapshot,
    ResearchPlanRevision,
    ResearchPlanRevisionAsset,
    ResearchProviderCall,
    ResearchStep,
    ResearchStepAttempt,
    ResearchStepDependency,
    ResearchRun,
    PromptVersion,
)
from ai_pdf_api.schemas.research import LegacyResearchPlanArtifactPayload, ResearchPlanArtifactPayload
from ai_pdf_api.services.research_evidence_provenance import (
    validate_evidence_source_fingerprint,
)
from ai_pdf_api.services.research_prompt_provenance import (
    PROMPT_NODE_ORDER,
    load_execution_prompt_dtos,
    load_planner_prompt_dto,
    prompt_version_dto,
)
from ai_pdf_api.services.storage import download_bytes


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def provider_snapshot(revision: ResearchPlanRevision) -> dict[str, object]:
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


def execution_provider_snapshot(snapshot: ResearchExecutionSnapshot) -> dict[str, object]:
    return {
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
    }


def planning_limits(revision: ResearchPlanRevision) -> dict[str, object]:
    return {
        "maxProviderCalls": revision.planning_max_provider_calls,
        "maxInputTokens": revision.planning_max_input_tokens,
        "maxOutputTokens": revision.planning_max_output_tokens,
        "plannerTimeoutSeconds": revision.planning_max_step_timeout_seconds,
        "providerTimeoutSeconds": revision.planning_max_provider_timeout_seconds,
        "maxPlannerAttempts": revision.planning_max_step_attempts,
    }


def execution_limits_from_revision(revision: ResearchPlanRevision) -> dict[str, object]:
    return {
        "maxProviderCalls": revision.proposed_max_provider_calls,
        "maxToolCalls": revision.proposed_max_tool_calls,
        "maxInputTokens": revision.proposed_max_input_tokens,
        "maxOutputTokens": revision.proposed_max_output_tokens,
        "maxParallelResearchers": revision.proposed_max_parallel_researchers,
        "runTimeoutSeconds": revision.proposed_max_run_timeout_seconds,
        "stepTimeoutSeconds": revision.proposed_max_step_timeout_seconds,
        "providerTimeoutSeconds": revision.proposed_max_provider_timeout_seconds,
        "maxAttemptsPerStep": revision.proposed_max_step_attempts,
    }


def execution_limits(snapshot: ResearchExecutionSnapshot) -> dict[str, object]:
    return {
        "maxProviderCalls": snapshot.max_provider_calls,
        "maxToolCalls": snapshot.max_tool_calls,
        "maxInputTokens": snapshot.max_input_tokens,
        "maxOutputTokens": snapshot.max_output_tokens,
        "maxParallelResearchers": snapshot.max_parallel_researchers,
        "runTimeoutSeconds": snapshot.max_run_timeout_seconds,
        "stepTimeoutSeconds": snapshot.max_step_timeout_seconds,
        "providerTimeoutSeconds": snapshot.max_provider_timeout_seconds,
        "maxAttemptsPerStep": snapshot.max_step_attempts,
    }


def _plan_assets(db: Session, revision_id: str) -> list[ResearchPlanRevisionAsset]:
    return list(
        db.scalars(
            select(ResearchPlanRevisionAsset)
            .where(ResearchPlanRevisionAsset.plan_revision_id == revision_id)
            .order_by(ResearchPlanRevisionAsset.asset_order)
        ).all()
    )


def _execution_assets(db: Session, snapshot_id: str) -> list[ResearchExecutionAsset]:
    return list(
        db.scalars(
            select(ResearchExecutionAsset)
            .where(ResearchExecutionAsset.execution_snapshot_id == snapshot_id)
            .order_by(ResearchExecutionAsset.asset_order)
        ).all()
    )


def _frozen_scope(rows: list[ResearchPlanRevisionAsset] | list[ResearchExecutionAsset], frozen_at: datetime) -> dict:
    return {
        "frozenAt": iso(frozen_at),
        "assets": [
            {
                "assetId": row.asset_id,
                "assetKind": row.asset_kind_snapshot,
                "assetTitle": row.asset_title_snapshot,
                "processingGeneration": row.processing_generation_snapshot,
                "indexVersion": row.index_version_snapshot,
            }
            for row in rows
        ],
    }


def _requested_scope(revision: ResearchPlanRevision, assets: list[ResearchPlanRevisionAsset]) -> dict:
    if revision.scope_mode == "all_ready":
        return {"mode": "all_ready"}
    return {"mode": "selected", "assetIds": [row.asset_id for row in assets]}


def planning_input_snapshot(db: Session, revision: ResearchPlanRevision) -> dict[str, object]:
    assets = _plan_assets(db, revision.id)
    prompts = list(
        db.execute(
            select(ResearchExecutionPromptVersion.node_key, ResearchExecutionPromptVersion.prompt_version_id)
            .join(
                ResearchExecutionSnapshot,
                ResearchExecutionSnapshot.id == ResearchExecutionPromptVersion.execution_snapshot_id,
            )
            .where(ResearchExecutionSnapshot.approved_plan_revision_id == revision.id)
            .order_by(ResearchExecutionPromptVersion.node_key)
        ).all()
    )
    if not prompts:
        from ai_pdf_api.models import WorkflowPromptBinding

        prompts = list(
            db.execute(
                select(WorkflowPromptBinding.node_key, WorkflowPromptBinding.prompt_version_id)
                .where(WorkflowPromptBinding.workflow_version_id == revision.proposed_workflow_version_id)
                .order_by(WorkflowPromptBinding.node_key)
            ).all()
        )
    provider = provider_snapshot(revision)
    return {
        "revisionNumber": revision.revision_number,
        "question": revision.question_text,
        "requestedAssetScope": _requested_scope(revision, assets),
        "planningAssetScope": _frozen_scope(assets, revision.created_at),
        "planningExecution": {
            "workflowVersionId": revision.proposed_workflow_version_id,
            "plannerPromptVersionId": revision.planner_prompt_version_id,
            "provider": provider,
            "budgetPolicyVersion": revision.planning_budget_policy_version,
            "retryPolicyVersion": revision.planning_retry_policy_version,
            "limits": planning_limits(revision),
            "agentResultSchemaVersion": getattr(revision, "agent_result_schema_version", None),
            "contextPolicyVersion": getattr(revision, "context_policy_version", None),
            "compactPolicyVersion": getattr(revision, "compact_policy_version", None),
        },
        "proposedResearchExecution": {
            "workflowVersionId": revision.proposed_workflow_version_id,
            "promptVersions": [
                {"nodeKey": node_key, "promptVersionId": prompt_id} for node_key, prompt_id in prompts
            ],
            "provider": provider,
            "budgetPolicyVersion": revision.proposed_budget_policy_version,
            "retryPolicyVersion": revision.proposed_retry_policy_version,
            "limits": execution_limits_from_revision(revision),
            "agentResultSchemaVersion": getattr(revision, "agent_result_schema_version", None),
            "contextPolicyVersion": getattr(revision, "context_policy_version", None),
            "compactPolicyVersion": getattr(revision, "compact_policy_version", None),
        },
        "snapshotSha256": revision.planning_snapshot_sha256,
        "frozenAt": iso(revision.created_at),
    }


def _usage(db: Session, rows: list[ResearchBudgetLedger], measured_at: datetime) -> dict[str, object]:
    ledger_ids = [row.id for row in rows]
    sources = set(
        db.scalars(
            select(ResearchProviderCall.usage_source).where(
                ResearchProviderCall.budget_ledger_id.in_(ledger_ids),
                ResearchProviderCall.usage_source.in_(("actual", "estimated")),
            )
        ).all()
        if ledger_ids
        else []
    )
    usage_source = (
        "actual"
        if sources == {"actual"}
        else "estimated"
        if sources == {"estimated"}
        else "mixed"
        if sources == {"actual", "estimated"}
        else None
    )
    return {
        "providerCalls": sum(row.actual_provider_calls for row in rows),
        "toolCalls": sum(row.actual_tool_calls for row in rows),
        "inputTokens": sum(row.actual_input_tokens for row in rows),
        "outputTokens": sum(row.actual_output_tokens for row in rows),
        "usageFinal": all(row.usage_final for row in rows) if rows else True,
        "measuredAt": iso(max((row.updated_at for row in rows), default=measured_at)),
        "usageSource": usage_source,
    }


def planning_usage(db: Session, run: ResearchRun) -> dict[str, object]:
    rows = list(
        db.scalars(
            select(ResearchBudgetLedger).where(
                ResearchBudgetLedger.run_id == run.id,
                ResearchBudgetLedger.plan_revision_id.is_not(None),
            )
        ).all()
    )
    return _usage(db, rows, run.updated_at)


def research_usage(db: Session, run: ResearchRun) -> dict[str, object] | None:
    if run.approved_execution_snapshot_id is None:
        return None
    ledger = db.scalar(
        select(ResearchBudgetLedger).where(
            ResearchBudgetLedger.execution_snapshot_id == run.approved_execution_snapshot_id
        )
    )
    return _usage(db, [ledger] if ledger else [], run.updated_at)


def _decision_dto(decision: HumanDecision) -> dict[str, object]:
    return {
        "id": decision.id,
        "runId": decision.run_id,
        "gateStepId": decision.gate_step_id,
        "type": decision.decision_type,
        "status": decision.status,
        "requestNumber": decision.request_number,
        "stateVersion": decision.state_version,
        "inputArtifactId": decision.input_artifact_id,
        "inputArtifactSha256": decision.input_artifact_sha256,
        "inputSnapshotSha256": decision.input_snapshot_sha256,
        "requestedAt": iso(decision.requested_at),
        "expiresAt": iso(decision.expires_at),
        "decidedByUserId": decision.decided_by_user_id,
        "action": decision.action,
        "comment": decision.comment_text,
        "decidedAt": iso(decision.decided_at),
    }


def _step_dto(db: Session, step: ResearchStep) -> dict[str, object]:
    dependencies = list(
        db.scalars(
            select(ResearchStepDependency.depends_on_step_id)
            .where(ResearchStepDependency.step_id == step.id)
            .order_by(ResearchStepDependency.depends_on_step_id)
        ).all()
    )
    usage = db.execute(
        select(
            func.coalesce(func.sum(ResearchStepAttempt.provider_call_count), 0),
            func.coalesce(func.sum(ResearchStepAttempt.tool_call_count), 0),
        ).where(ResearchStepAttempt.step_id == step.id)
    ).one()
    evidence_count = db.scalar(
        select(func.count()).select_from(ResearchEvidenceSnapshot).where(
            ResearchEvidenceSnapshot.captured_by_step_id == step.id
        )
    ) or 0
    failure = None
    if step.error_code:
        failure = {
            "code": step.error_code,
            "message": step.error_message or "Research step failed.",
            "retryable": step.status == "failed" and step.current_attempt_number < step.max_attempts_snapshot,
            "failedAt": iso(step.finished_at or step.updated_at),
        }
    return {
        "id": step.id,
        "runId": step.run_id,
        "kind": step.step_kind,
        "key": step.step_key,
        "branchKey": step.branch_key,
        "status": step.status,
        "stateVersion": step.state_version,
        "currentAttemptNumber": step.current_attempt_number,
        "maxAttempts": step.max_attempts_snapshot,
        "dependsOnStepIds": dependencies,
        "evidenceCount": evidence_count,
        "providerCalls": int(usage[0]),
        "toolCalls": int(usage[1]),
        "startedAt": iso(step.started_at),
        "finishedAt": iso(step.finished_at),
        "failure": failure,
    }


def execution_snapshot_dto(db: Session, snapshot: ResearchExecutionSnapshot) -> dict[str, object]:
    prompts = list(
        db.execute(
            select(ResearchExecutionPromptVersion.node_key, ResearchExecutionPromptVersion.prompt_version_id)
            .where(ResearchExecutionPromptVersion.execution_snapshot_id == snapshot.id)
            .order_by(ResearchExecutionPromptVersion.node_key)
        ).all()
    )
    assets = _execution_assets(db, snapshot.id)
    return {
        "id": snapshot.id,
        "inputVersion": snapshot.input_version,
        "approvalDecisionId": snapshot.approval_decision_id,
        "approvedPlanArtifactId": snapshot.approved_plan_artifact_id,
        "approvedPlanArtifactSha256": snapshot.approved_plan_artifact_sha256,
        "question": snapshot.question_text,
        "frozenAssetScope": _frozen_scope(assets, snapshot.created_at),
        "execution": {
            "workflowVersionId": snapshot.workflow_version_id,
            "promptVersions": [
                {"nodeKey": node_key, "promptVersionId": prompt_id} for node_key, prompt_id in prompts
            ],
            "provider": execution_provider_snapshot(snapshot),
            "budgetPolicyVersion": snapshot.budget_policy_version,
            "retryPolicyVersion": snapshot.retry_policy_version,
            "limits": execution_limits(snapshot),
            "agentResultSchemaVersion": getattr(snapshot, "agent_result_schema_version", None),
            "contextPolicyVersion": getattr(snapshot, "context_policy_version", None),
            "compactPolicyVersion": getattr(snapshot, "compact_policy_version", None),
        },
        "snapshotSha256": snapshot.execution_snapshot_sha256,
        "createdAt": iso(snapshot.created_at),
    }


def _plan_dto(db: Session, run: ResearchRun, revision: ResearchPlanRevision) -> dict[str, object] | None:
    artifact = db.scalar(
        select(ResearchArtifact)
        .join(ResearchStep, ResearchStep.id == ResearchArtifact.generated_by_step_id)
        .where(
            ResearchArtifact.run_id == run.id,
            ResearchArtifact.artifact_kind == "research_plan",
            ResearchStep.plan_revision_id == revision.id,
        )
        .order_by(ResearchArtifact.created_at.desc())
        .limit(1)
    )
    if artifact is None:
        return None
    payload = load_research_plan_artifact(artifact)
    status = "proposed"
    approved_at = None
    if run.approved_execution_snapshot_id:
        snapshot = db.get(ResearchExecutionSnapshot, run.approved_execution_snapshot_id)
        if snapshot and snapshot.approved_plan_revision_id == revision.id:
            status = "approved"
            approved_at = iso(snapshot.created_at)
        else:
            status = "superseded"
    elif run.current_plan_revision_id != revision.id:
        status = "superseded"
    ledger = db.scalar(
        select(ResearchBudgetLedger).where(ResearchBudgetLedger.plan_revision_id == revision.id)
    )
    usage = _usage(db, [ledger] if ledger else [], revision.created_at)
    return {
        "version": revision.revision_number,
        "status": status,
        "inputSnapshot": planning_input_snapshot(db, revision),
        "summary": payload.summary,
        "subproblems": [item.model_dump(mode="json", by_alias=True) for item in payload.subproblems],
        "knownGaps": payload.known_gaps,
        "estimatedProviderCalls": payload.estimated_provider_calls,
        "estimatedInputTokens": payload.estimated_input_tokens,
        "estimatedOutputTokens": payload.estimated_output_tokens,
        "planningUsage": usage,
        "createdAt": iso(artifact.created_at),
        "approvedAt": approved_at,
    }


def run_summary(db: Session, run: ResearchRun) -> dict[str, object]:
    revision = db.get(ResearchPlanRevision, run.current_plan_revision_id) if run.current_plan_revision_id else None
    assets = _plan_assets(db, revision.id) if revision else []
    plan = _plan_dto(db, run, revision) if revision else None
    return {
        "id": run.id,
        "workspaceId": run.workspace_id,
        "createdByUserId": run.created_by_user_id,
        "question": revision.question_text if revision else "",
        "status": run.status,
        "stateVersion": run.state_version,
        "requestedAssetScope": _requested_scope(revision, assets) if revision else {"mode": "all_ready"},
        "frozenAssetCount": len(assets),
        "currentPlanRevisionNumber": revision.revision_number if revision else None,
        "currentEventSeq": run.next_event_seq - 1,
        "createdAt": iso(run.created_at),
        "updatedAt": iso(run.updated_at),
        "finishedAt": iso(run.finished_at),
    }


def run_detail(db: Session, run: ResearchRun) -> dict[str, object]:
    summary = run_summary(db, run)
    revision = db.get(ResearchPlanRevision, run.current_plan_revision_id) if run.current_plan_revision_id else None
    assets = _plan_assets(db, revision.id) if revision else []
    steps = list(
        db.scalars(select(ResearchStep).where(ResearchStep.run_id == run.id).order_by(ResearchStep.created_at, ResearchStep.id)).all()
    )
    decisions = list(
        db.scalars(
            select(HumanDecision)
            .where(HumanDecision.run_id == run.id)
            .order_by(HumanDecision.requested_at, HumanDecision.id)
        ).all()
    )
    snapshot = db.get(ResearchExecutionSnapshot, run.approved_execution_snapshot_id) if run.approved_execution_snapshot_id else None
    artifact_count = db.scalar(
        select(func.count()).select_from(ResearchArtifact).where(
            ResearchArtifact.run_id == run.id,
            ResearchArtifact.visibility == "user",
        )
    ) or 0
    failure = None
    if run.failure_code:
        failure = {
            "code": run.failure_code,
            "message": run.failure_message or "Research run failed.",
            "retryable": run.status == "awaiting_retry",
            "failedAt": iso(run.finished_at or run.updated_at),
        }
    return {
        **summary,
        "frozenAssetScope": _frozen_scope(assets, revision.created_at) if revision else None,
        "plan": _plan_dto(db, run, revision) if revision else None,
        "researchExecution": execution_snapshot_dto(db, snapshot) if snapshot else None,
        "planningUsage": planning_usage(db, run),
        "researchUsage": research_usage(db, run),
        "steps": [_step_dto(db, step) for step in steps],
        "pendingDecisions": [_decision_dto(item) for item in decisions if item.status == "pending"],
        "submittedDecisions": [_decision_dto(item) for item in decisions if item.status != "pending"],
        "artifactCount": artifact_count,
        "failure": failure,
        "startedAt": iso(run.started_at),
        "cancelRequestedAt": iso(run.cancel_requested_at),
        "cancelledAt": iso(run.finished_at) if run.status == "cancelled" else None,
    }


USER_ARTIFACT_KINDS = {"research_plan", "evidence_bundle", "conflict_report", "final_report", "trace_export"}


def artifact_summary(db: Session, artifact: ResearchArtifact) -> dict[str, object]:
    evidence_count = db.scalar(
        select(func.count(func.distinct(ResearchClaimEvidence.evidence_snapshot_id)))
        .select_from(ResearchArtifactClaim)
        .join(ResearchClaimEvidence, ResearchClaimEvidence.claim_id == ResearchArtifactClaim.claim_id)
        .where(ResearchArtifactClaim.artifact_id == artifact.id)
    ) or 0
    return {
        "id": artifact.id,
        "runId": artifact.run_id,
        "stepId": artifact.generated_by_step_id,
        "kind": artifact.artifact_kind,
        "visibility": artifact.visibility,
        "logicalKey": artifact.logical_key,
        "schemaVersion": artifact.schema_version,
        "supersedesArtifactId": artifact.supersedes_artifact_id,
        "mediaType": artifact.content_type,
        "byteSize": artifact.byte_size,
        "sha256": artifact.content_sha256,
        "evidenceCount": evidence_count,
        "retentionClass": artifact.retention_class,
        "expiresAt": iso(artifact.expires_at),
        "createdAt": iso(artifact.created_at),
    }


def artifact_detail(db: Session, artifact: ResearchArtifact) -> dict[str, object]:
    run = db.get(ResearchRun, artifact.run_id)
    step = db.get(ResearchStep, artifact.generated_by_step_id)
    attempt = db.get(ResearchStepAttempt, artifact.generated_by_attempt_id)
    if (
        run is None
        or step is None
        or attempt is None
        or artifact.workspace_id != run.workspace_id
        or step.run_id != run.id
        or step.workspace_id != run.workspace_id
        or attempt.step_id != step.id
        or attempt.workspace_id != run.workspace_id
        or attempt.status != "succeeded"
        or (
            artifact.artifact_kind in {"research_plan", "conflict_report", "final_report"}
            and attempt.output_sha256 != artifact.content_sha256
        )
    ):
        raise ValueError("research_artifact_chain_invalid")
    prompt_rows = list(
        db.execute(
            select(ResearchArtifactPromptVersion, PromptVersion)
            .join(PromptVersion, PromptVersion.id == ResearchArtifactPromptVersion.prompt_version_id)
            .where(ResearchArtifactPromptVersion.artifact_id == artifact.id)
            .order_by(ResearchArtifactPromptVersion.node_key, ResearchArtifactPromptVersion.prompt_version_id)
        ).all()
    )
    artifact_prompt_by_node = {
        binding.node_key: prompt_version_dto(prompt, node_key=binding.node_key)
        for binding, prompt in prompt_rows
    }
    if len(artifact_prompt_by_node) != len(prompt_rows):
        raise ValueError("research_artifact_prompt_chain_invalid")
    snapshot = db.get(ResearchExecutionSnapshot, run.approved_execution_snapshot_id) if run.approved_execution_snapshot_id else None
    if artifact.artifact_kind == "research_plan":
        revision = db.get(ResearchPlanRevision, step.plan_revision_id) if step.plan_revision_id else None
        if (
            revision is None
            or revision.run_id != run.id
            or revision.workspace_id != run.workspace_id
            or artifact.workflow_version_id != revision.proposed_workflow_version_id
            or artifact.generation_provider != revision.proposed_generation_provider
            or artifact.generation_model != revision.proposed_generation_model
            or step.step_kind != "planner"
        ):
            raise ValueError("research_artifact_plan_chain_invalid")
        planner_prompt = load_planner_prompt_dto(db, revision)
        if (
            artifact_prompt_by_node != {"planner": planner_prompt}
            or artifact.direct_prompt_version_id != planner_prompt["promptVersionId"]
            or step.prompt_version_id != planner_prompt["promptVersionId"]
        ):
            raise ValueError("research_artifact_prompt_chain_invalid")
        provider = provider_snapshot(revision)
    else:
        if (
            snapshot is None
            or snapshot.run_id != run.id
            or snapshot.workspace_id != run.workspace_id
            or step.execution_snapshot_id != snapshot.id
            or artifact.workflow_version_id != snapshot.workflow_version_id
            or artifact.generation_provider != snapshot.generation_provider
            or artifact.generation_model != snapshot.generation_model
        ):
            raise ValueError("research_artifact_execution_chain_invalid")
        execution_prompts = load_execution_prompt_dtos(db, snapshot)
        execution_prompt_by_node = {
            str(item["nodeKey"]): item for item in execution_prompts
        }
        if artifact_prompt_by_node != execution_prompt_by_node:
            raise ValueError("research_artifact_prompt_chain_invalid")
        node_for_step_kind = {
            "researcher": "researchers",
            "verifier": "verifier",
            "critic": "critic",
            "conflict_decision_gate": "critic",
            "synthesizer": "synthesizer",
            "artifact_publisher": "synthesizer",
        }
        expected_node = node_for_step_kind.get(step.step_kind)
        prompt_by_node = {
            str(item["nodeKey"]): str(item["promptVersionId"])
            for item in execution_prompts
        }
        expected_prompt_id = prompt_by_node.get(expected_node or "")
        if (
            expected_prompt_id is None
            or step.prompt_version_id != expected_prompt_id
            or artifact.direct_prompt_version_id != expected_prompt_id
        ):
            raise ValueError("research_artifact_direct_prompt_invalid")
        provider = execution_provider_snapshot(snapshot)
    artifact_prompt_dtos = [
        artifact_prompt_by_node[node_key]
        for node_key in PROMPT_NODE_ORDER
        if node_key in artifact_prompt_by_node
    ]
    raw_artifact_claim_count = db.scalar(
        select(func.count()).select_from(ResearchArtifactClaim).where(
            ResearchArtifactClaim.artifact_id == artifact.id
        )
    ) or 0
    claim_rows = list(
        db.execute(
            select(ResearchArtifactClaim, ResearchClaim)
            .join(ResearchClaim, ResearchClaim.id == ResearchArtifactClaim.claim_id)
            .where(
                ResearchArtifactClaim.artifact_id == artifact.id,
                ResearchClaim.run_id == run.id,
                ResearchClaim.workspace_id == run.workspace_id,
            )
            .order_by(ResearchArtifactClaim.claim_order)
        ).all()
    )
    if len(claim_rows) != raw_artifact_claim_count:
        raise ValueError("research_artifact_claim_chain_invalid")
    evidence_by_id: dict[str, ResearchEvidenceSnapshot] = {}
    claims: list[dict[str, object]] = []
    for binding, claim in claim_rows:
        producer = db.get(ResearchStep, claim.produced_by_step_id)
        verifier = db.get(ResearchStep, claim.verified_by_step_id) if claim.verified_by_step_id else None
        critic = db.get(ResearchStep, claim.critic_step_id) if claim.critic_step_id else None
        if (
            producer is None
            or producer.run_id != run.id
            or producer.workspace_id != run.workspace_id
            or (snapshot is not None and producer.execution_snapshot_id != snapshot.id)
            or claim.statement_sha256
            != hashlib.sha256(claim.statement_text.encode("utf-8")).hexdigest()
        ):
            raise ValueError("research_claim_producer_chain_invalid")
        if (
            claim.verification_status not in {"supported", "unsupported"}
            or claim.verified_at is None
            or verifier is None
            or verifier.step_kind != "verifier"
            or verifier.run_id != run.id
            or verifier.workspace_id != run.workspace_id
            or (snapshot is not None and verifier.execution_snapshot_id != snapshot.id)
        ):
            raise ValueError("research_claim_verifier_chain_invalid")
        if (
            (claim.conflict_status != "none" and critic is None)
            or (
                critic is not None
                and (
                    critic.step_kind != "critic"
                    or critic.run_id != run.id
                    or critic.workspace_id != run.workspace_id
                    or (snapshot is not None and critic.execution_snapshot_id != snapshot.id)
                )
            )
        ):
            raise ValueError("research_claim_critic_chain_invalid")
        raw_link_count = db.scalar(
            select(func.count()).select_from(ResearchClaimEvidence).where(
                ResearchClaimEvidence.claim_id == claim.id
            )
        ) or 0
        links = list(
            db.execute(
                select(ResearchClaimEvidence, ResearchEvidenceSnapshot)
                .join(
                    ResearchEvidenceSnapshot,
                    ResearchEvidenceSnapshot.id == ResearchClaimEvidence.evidence_snapshot_id,
                )
                .where(
                    ResearchClaimEvidence.claim_id == claim.id,
                    ResearchEvidenceSnapshot.run_id == run.id,
                    ResearchEvidenceSnapshot.workspace_id == run.workspace_id,
                )
                .order_by(ResearchClaimEvidence.evidence_order)
            ).all()
        )
        if len(links) != raw_link_count:
            raise ValueError("research_claim_evidence_chain_invalid")
        for link, evidence in links:
            captured_by = db.get(ResearchStep, evidence.captured_by_step_id)
            assessed_by = db.get(ResearchStep, link.assessed_by_step_id)
            asset = db.get(Asset, evidence.asset_id)
            if (
                captured_by is None
                or assessed_by is None
                or asset is None
                or evidence.run_id != run.id
                or evidence.workspace_id != run.workspace_id
                or asset.workspace_id != run.workspace_id
                or captured_by.run_id != run.id
                or captured_by.workspace_id != run.workspace_id
                or captured_by.step_kind != "researcher"
                or captured_by.id != producer.id
                or assessed_by.run_id != run.id
                or assessed_by.workspace_id != run.workspace_id
                or assessed_by.step_kind != "verifier"
                or assessed_by.id != verifier.id
                or (snapshot is not None and captured_by.execution_snapshot_id != snapshot.id)
                or (snapshot is not None and assessed_by.execution_snapshot_id != snapshot.id)
            ):
                raise ValueError("research_evidence_provenance_chain_invalid")
            evidence_by_id[evidence.id] = evidence
        claims.append(
            {
                "id": claim.id,
                "text": claim.statement_text,
                "verificationStatus": claim.verification_status,
                "conflictStatus": claim.conflict_status,
                "sectionKind": binding.section_kind,
                "evidence": [
                    {
                        "evidenceLocatorId": evidence.evidence_locator_id,
                        "relationship": link.relationship,
                        "order": link.evidence_order,
                    }
                    for link, evidence in links
                ],
            }
        )
    evidence_dtos = []
    for evidence in evidence_by_id.values():
        asset = db.get(Asset, evidence.asset_id)
        if asset is None or asset.workspace_id != run.workspace_id:
            raise ValueError("research_evidence_asset_chain_invalid")
        locator = serialize_evidence_locator(
            db,
            evidence.evidence_locator_id,
            workspace_id=run.workspace_id,
            asset_id=evidence.asset_id,
            processing_generation=evidence.processing_generation_snapshot,
            representation_id=evidence.representation_id_snapshot,
        )
        validate_evidence_source_fingerprint(evidence, locator_kind=locator.kind)
        evidence_dtos.append(
            {
                "evidenceLocatorId": evidence.evidence_locator_id,
                "assetId": evidence.asset_id,
                "assetKind": evidence.asset_kind_snapshot,
                "assetTitle": evidence.asset_title_snapshot,
                "sourceAvailable": bool(
                    asset.deleted_at is None
                    and asset.status == "ready"
                    and asset.current_processing_generation == evidence.processing_generation_snapshot
                    and asset.current_index_version == evidence.index_version_snapshot
                ),
                "excerpt": evidence.excerpt_snapshot,
                "locator": locator.model_dump(),
                "sourceVersions": {
                    "parserVersion": evidence.parser_version_snapshot,
                    "processingGeneration": evidence.processing_generation_snapshot,
                    "representationId": evidence.representation_id_snapshot,
                    "indexVersion": evidence.index_version_snapshot,
                },
            }
        )
    return {
        **artifact_summary(db, artifact),
        "workflowVersionId": artifact.workflow_version_id,
        "promptVersions": [
            {"nodeKey": item["nodeKey"], "promptVersionId": item["promptVersionId"]}
            for item in artifact_prompt_dtos
        ],
        "directPromptVersionId": artifact.direct_prompt_version_id,
        "provider": provider,
        "claims": claims,
        "evidence": evidence_dtos,
    }


def verified_artifact_bytes(artifact: ResearchArtifact) -> bytes:
    payload = download_bytes(artifact.object_key)
    if len(payload) != artifact.byte_size or hashlib.sha256(payload).hexdigest() != artifact.content_sha256:
        raise ValueError("research_artifact_integrity_mismatch")
    return payload


def load_research_plan_artifact(artifact: ResearchArtifact) -> ResearchPlanArtifactPayload:
    if artifact.artifact_kind != "research_plan" or artifact.content_type != "application/json" or artifact.schema_version != "1":
        raise ValueError("research_plan_artifact_contract_mismatch")
    try:
        decoded = json.loads(verified_artifact_bytes(artifact))
        # Artifact schema version 1 has an explicit recovery reader. It accepts
        # the historical optional cost field, then projects it out of the V5-C
        # user DTO without guessing from arbitrary field names.
        legacy = LegacyResearchPlanArtifactPayload.model_validate(decoded)
        return ResearchPlanArtifactPayload.model_validate(
            legacy.model_dump(exclude={"estimated_cost"})
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("research_plan_artifact_invalid_json") from error
