from datetime import UTC, datetime
from sqlalchemy import select, func
import pytest
from ai_pdf_api.models import (ResearchRun, ResearchStep, HumanDecision, ResearchExecutionSnapshot,
    ResearchExecutionAsset, ResearchBudgetLedger, ResearchEvent, WorkspaceMembership, ResearchArtifact)
from ai_pdf_api.services.research.research_worker import claim_next_research_step, publish_research_plan, PlanSubproblemDraft
from ai_pdf_api.services.research.research_idempotency import ResearchError
from research_router_test_support import create_run


def publish(client, db, ctx, *, before=None):
    run = create_run(client, ctx)
    lease = claim_next_research_step(db, worker_instance_id="autonomy-test", lease_seconds=300)
    assert lease is not None
    if before:
        before(db, ctx, run)
    store = ctx["objectStore"]
    result = publish_research_plan(db, attempt_id=lease.attempt_id, lease_token=lease.lease_token,
        summary="Bounded plan", subproblems=(PlanSubproblemDraft("Facts?", (ctx["asset"].id,)),),
        estimated_provider_calls=5,
        store_bytes=lambda key, value, _type: store.__setitem__(key, value),
        cleanup_bytes=lambda key: store.pop(key, None))
    return db.get(ResearchRun, run["id"]), result


def test_plan_auto_start_materializes_complete_frozen_execution(research_app):
    client, db, ctx = research_app
    run, result = publish(client, db, ctx)
    assert run.status == "queued"
    decision = db.get(HumanDecision, result["decisionId"])
    assert decision.status == "submitted" and decision.action == "approve"
    assert decision.decision_origin == "policy" and decision.decided_by_user_id is None
    snapshot = db.get(ResearchExecutionSnapshot, run.approved_execution_snapshot_id)
    assert snapshot.approved_plan_artifact_sha256 == result["artifactSha256"]
    assert snapshot.max_provider_calls == 32 and snapshot.max_tool_calls == 64
    assert db.scalar(select(func.count()).select_from(ResearchExecutionAsset)) == 1
    assert db.scalar(select(func.count()).select_from(ResearchBudgetLedger)) == 2
    steps = list(db.scalars(select(ResearchStep).where(ResearchStep.run_id == run.id)))
    assert len(steps) == 9
    assert next(s for s in steps if s.step_kind == "researcher").status == "queued"
    assert not db.scalar(select(HumanDecision).where(HumanDecision.status == "pending"))
    events = list(db.scalars(select(ResearchEvent).order_by(ResearchEvent.seq)))
    assert "approval_requested" not in [event.event_type for event in events]
    assert [event.seq for event in events] == list(range(1, len(events)+1))
    # Same worker sees the persisted next step without a browser or decision POST.
    lease = claim_next_research_step(db, worker_instance_id="autonomy-test", lease_seconds=300)
    assert db.get(ResearchStep, lease.step_id).step_kind == "researcher"


@pytest.mark.parametrize("mutation,code", [("asset", "stale_plan_snapshot"), ("cancel", "research_state_conflict"), ("membership", "research_permission_denied")])
def test_auto_start_retains_snapshot_cancel_membership_guards(research_app, mutation, code):
    client, db, ctx = research_app
    def before(db, ctx, value):
        if mutation == "asset":
            ctx["asset"].current_processing_generation += 1
        elif mutation == "cancel":
            run = db.get(ResearchRun, value["id"])
            run.status = "cancel_requested"
            run.cancel_requested_by_user_id = ctx["creator"].id
            run.cancel_requested_at = datetime.now(UTC)
            run.cancel_reason_code = "user_requested"
        else:
            row = db.scalar(select(WorkspaceMembership).where(WorkspaceMembership.user_id == ctx["creator"].id))
            db.delete(row)
        db.commit()
    with pytest.raises(ResearchError) as caught:
        publish(client, db, ctx, before=before)
    assert caught.value.code == code
    db.rollback()
    assert db.scalar(select(func.count()).select_from(ResearchExecutionSnapshot)) == 0
    assert not db.scalar(select(ResearchArtifact).where(ResearchArtifact.artifact_kind == "research_plan"))


def test_conflicts_are_retained_and_queue_synthesis_without_human_gate(research_worker_db):
    from ai_pdf_api.models import ResearchClaim, ResearchStepDependency, HumanDecisionClaim
    from citeframe_research_persistence.autonomy import AUTONOMOUS_WORKFLOW_ID
    from citeframe_research_persistence.publication import wait_for_conflict_decision
    from citeframe_research_persistence.publication_render import canonical_final_report
    from research_worker_test_support import lease_default_step, add_step, sha256
    f = research_worker_db
    f.snapshot.workflow_version_id = AUTONOMOUS_WORKFLOW_ID
    f.step.step_kind = "conflict_decision_gate"
    f.step.step_key = "conflict_decision_gate"
    f.step.branch_key = None
    dependent = add_step(f, step_key="synthesizer", step_kind="synthesizer")
    dependent.status = "pending"
    db = f.db
    db.add(ResearchStepDependency(step_id=dependent.id, depends_on_step_id=f.step.id))
    claim = ResearchClaim(workspace_id=f.run.workspace_id, run_id=f.run.id, claim_key="conflict",
        claim_order=0, statement_text="Contradictory evidence", statement_sha256=sha256("Contradictory evidence"),
        produced_by_step_id=f.step.id, verification_status="supported", conflict_status="conflicted", created_at=f.now)
    db.add(claim); db.commit()
    lease = lease_default_step(f)
    store = {}
    decision_id = wait_for_conflict_decision(db, attempt_id=lease.attempt_id, lease_token=lease.lease_token,
        conflict_claim_ids=[claim.id], now=f.now,
        store_bytes=lambda key, data, _type: store.__setitem__(key, data),
        cleanup_bytes=lambda key: store.pop(key, None))
    db.commit(); db.refresh(f.step); db.refresh(dependent); db.refresh(claim)
    decision = db.get(HumanDecision, decision_id)
    assert decision.status == "submitted" and decision.decision_origin == "policy"
    assert decision.action == "keep_as_unresolved" and decision.decided_by_user_id is None
    assert db.get(HumanDecisionClaim, (decision_id, claim.id)).disposition == "leave_unresolved"
    assert claim.conflict_status == "resolved_unresolved"
    assert f.step.status == "succeeded" and dependent.status == "queued"
    assert f.run.status not in {"awaiting_human_decision", "awaiting_plan_approval"}
    report = canonical_final_report(fact_claims=[], unresolved_claims=[claim]).decode()
    findings, unresolved = report.split("## Unresolved Evidence Conflicts")
    assert claim.statement_text not in findings and claim.statement_text in unresolved
    assert not db.scalar(select(HumanDecision).where(HumanDecision.status == "pending"))
    # Publication selection guards continue to reject promotion to a fact.
    from citeframe_research_persistence.completion import complete_research_synthesis
    from ai_pdf_api.services.research.research_worker import claim_specific_research_step
    lease = claim_specific_research_step(db, run_id=f.run.id, step_key="synthesizer", branch_key=None,
        worker_instance_id="test", lease_seconds=60, now=f.now)
    with pytest.raises(ResearchError, match="scope"):
        complete_research_synthesis(db, attempt_id=lease.attempt_id, lease_token=lease.lease_token,
            fact_claim_ids=[claim.id], unresolved_claim_ids=[], now=f.now,
            store_bytes=lambda *args: None, cleanup_bytes=lambda *args: None)


def install_historical_v2(db):
    from ai_pdf_api.models import WorkflowVersion, PromptVersion, WorkflowPromptBinding
    from ai_pdf_api.services.research.research_prompt_provenance import (V2_WORKFLOW_VERSION_ID,
        V2_RELEASE_ID, V2_PROMPT_VERSION_IDS, V2_PROMPT_SPECS, v2_workflow_manifest)
    from ai_pdf_api.services.research.research_idempotency import canonical_sha256
    now = datetime.now(UTC); manifest=v2_workflow_manifest()
    db.add(WorkflowVersion(id=V2_WORKFLOW_VERSION_ID, workflow_key="evidence_research", version_number=2,
        availability="active", manifest_schema_version="2", manifest_json=manifest,
        manifest_sha256=canonical_sha256(manifest), created_by_release_id=V2_RELEASE_ID, created_at=now))
    for key, spec in V2_PROMPT_SPECS.items():
        db.add(PromptVersion(id=V2_PROMPT_VERSION_IDS[key], prompt_key=spec.prompt_key, version_number=2,
            step_kind=spec.step_kind, availability="active", template_text=spec.template_text,
            variables_schema_version="2", variables_schema_json=spec.variables_schema,
            template_sha256=spec.template_sha256, created_by_release_id=V2_RELEASE_ID, created_at=now))
    db.flush()
    for key, prompt_id in V2_PROMPT_VERSION_IDS.items():
        db.add(WorkflowPromptBinding(workflow_version_id=V2_WORKFLOW_VERSION_ID, node_key=key, prompt_version_id=prompt_id))
    db.commit()


def test_historical_v2_plan_can_still_be_approved_with_v3_installed(research_app, monkeypatch):
    from ai_pdf_api.services.research import research_runs
    from ai_pdf_api.services.research.research_prompt_provenance import load_v2_release
    from ai_pdf_api.services.research.research_agent_io_registry import V1_REGISTRY
    from research_router_test_support import approve_seeded_plan
    client, db, ctx = research_app
    install_historical_v2(db)
    def frozen_v2(db, _now=None):
        workflow, prompts = load_v2_release(db)
        return workflow, prompts["planner"]
    with monkeypatch.context() as patch:
        patch.setattr(research_runs, "ensure_research_versions", frozen_v2)
        patch.setattr(research_runs, "require_current_production_registry", lambda: V1_REGISTRY)
        created=create_run(client, ctx)
    run=approve_seeded_plan(client, db, ctx, created)
    assert run.status == "queued"
    snapshot=db.get(ResearchExecutionSnapshot, run.approved_execution_snapshot_id)
    assert snapshot.agent_result_schema_version == "research-agent-results-v1"
    assert snapshot.workflow_version_id.startswith("20000000")


def test_workflow_release_rejects_cross_version_prompt_binding(research_app):
    from ai_pdf_api.models import WorkflowPromptBinding
    from ai_pdf_api.services.research.research_prompt_provenance import (load_v2_release,
        V2_PROMPT_VERSION_IDS, V3_WORKFLOW_VERSION_ID)
    _, db, _ = research_app
    install_historical_v2(db)
    from ai_pdf_api.services.research.research_versions_service import publish_research_versions_for_release
    publish_research_versions_for_release(db, datetime.now(UTC), workflow_id=V3_WORKFLOW_VERSION_ID)
    db.flush()
    binding=db.get(WorkflowPromptBinding, (V3_WORKFLOW_VERSION_ID,"researchers"))
    binding.prompt_version_id=V2_PROMPT_VERSION_IDS["researchers"]
    db.commit()
    with pytest.raises(ValueError, match="prompt_bindings"):
        load_v2_release(db, workflow_id=V3_WORKFLOW_VERSION_ID)


def test_autonomy_migration_installs_v3_and_preserves_historical_decisions():
    import importlib.util
    from pathlib import Path
    from sqlalchemy import create_engine, inspect
    from sqlalchemy.orm import Session
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from ai_pdf_api.db.base import Base
    from ai_pdf_api.services.research.research_prompt_provenance import load_v2_release, V3_WORKFLOW_VERSION_ID
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    file=Path(__file__).parents[1]/"alembic/versions/p0d1e2f3a4b5_research_autonomy.py"
    spec=importlib.util.spec_from_file_location("autonomy_migration",file)
    migration=importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    assert migration.down_revision == "o9c0d1e2f3a4"
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)) as ops:
            with ops.batch_alter_table("human_decisions") as batch:
                batch.drop_constraint("ck_human_decisions_origin", type_="check")
                batch.drop_constraint("ck_human_decisions_submitted_fields", type_="check")
                batch.drop_column("decision_origin")
                batch.create_check_constraint("ck_human_decisions_submitted_fields",
                    "(status = 'submitted' AND decided_by_user_id IS NOT NULL AND action IS NOT NULL AND decided_at IS NOT NULL) OR status <> 'submitted'")
            migration.upgrade()
    with Session(engine) as db:
        workflow,prompts=load_v2_release(db,workflow_id=V3_WORKFLOW_VERSION_ID)
        assert workflow.version_number == 3 and len(prompts) == 5
        assert "decision_origin" in {c["name"] for c in inspect(engine).get_columns("human_decisions")}
