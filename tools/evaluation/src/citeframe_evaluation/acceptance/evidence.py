"""Raw persisted facts for acceptance oracles; no writes or inferred identifiers."""
from datetime import datetime
from sqlalchemy import select
from ai_pdf_api.models import (
    ResearchRun, ResearchStep, ResearchStepAttempt, ResearchExecutionSnapshot,
    ResearchBudgetLedger, ResearchProviderCall, ResearchToolCall,
    ResearchArtifact, WorkspaceMembership, ResearchPlanRevision, HumanDecision,
    ResearchExecutionAsset, ResearchExecutionPromptVersion,
)


def row(value):
    return {column.key: (item.isoformat() if isinstance(item, datetime) else item)
            for column in value.__table__.columns
            for item in (getattr(value, column.key),)}


def execution_facts(session_factory, run_id):
    with session_factory() as db:
        run = db.get(ResearchRun, run_id)
        assert run is not None
        result = {"run": row(run)}
        for name, model in (("steps", ResearchStep), ("snapshots", ResearchExecutionSnapshot),
                            ("plans", ResearchPlanRevision),
                            ("ledgers", ResearchBudgetLedger), ("providerCalls", ResearchProviderCall),
                            ("toolCalls", ResearchToolCall)):
            result[name] = [row(r) for r in db.scalars(select(model).where(model.run_id == run_id))]
        result["attempts"] = [row(r) for r in db.scalars(select(ResearchStepAttempt).join(
            ResearchStep, ResearchStep.id == ResearchStepAttempt.step_id).where(ResearchStep.run_id == run_id))]
        result["finals"] = [row(r) for r in db.scalars(select(ResearchArtifact).where(
            ResearchArtifact.run_id == run_id, ResearchArtifact.artifact_kind == "final_report"))]
        result["memberships"] = [row(r) for r in db.scalars(select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == run.workspace_id))]
        return result


def reclaim_facts(session_factory, step_id):
    with session_factory() as db:
        step = db.get(ResearchStep, step_id)
        assert step is not None
        snapshot = db.get(ResearchExecutionSnapshot, step.execution_snapshot_id)
        assert snapshot is not None
        return {"step": row(step), "snapshot": row(snapshot), "snapshotProof": snapshot_proof(db, snapshot), "attempts": [row(r) for r in db.scalars(
            select(ResearchStepAttempt).where(ResearchStepAttempt.step_id == step_id)
            .order_by(ResearchStepAttempt.attempt_number))]}


def snapshot_proof(db, snapshot):
    return {
        "revision": row(db.get(ResearchPlanRevision, snapshot.approved_plan_revision_id)),
        "decision": row(db.get(HumanDecision, snapshot.approval_decision_id)),
        "assets": [row(r) for r in db.scalars(select(ResearchExecutionAsset).where(
            ResearchExecutionAsset.execution_snapshot_id == snapshot.id).order_by(ResearchExecutionAsset.asset_order))],
        "prompts": [row(r) for r in db.scalars(select(ResearchExecutionPromptVersion).where(
            ResearchExecutionPromptVersion.execution_snapshot_id == snapshot.id).order_by(ResearchExecutionPromptVersion.node_key))],
    }
