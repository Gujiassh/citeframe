from __future__ import annotations

from uuid import uuid4

from ai_pdf_api.models import (
    PromptVersion,
    ResearchArtifact,
    ResearchArtifactPromptVersion,
    ResearchBudgetLedger,
    ResearchExecutionSnapshot,
    ResearchPlanRevision,
    ResearchPlanRevisionAsset,
    ResearchRun,
    ResearchStep,
    WorkflowPromptBinding,
    WorkflowVersion,
)
from ai_pdf_api.services.research import (
    build_execution_snapshot_hash_payload,
)
from ai_pdf_api.services.research_idempotency import canonical_sha256
from ai_pdf_api.services.research_prompt_provenance import (
    PROMPT_NODE_ORDER,
    V2_PROMPT_SPECS,
    V2_PROMPT_VERSION_IDS,
    V2_WORKFLOW_VERSION_ID,
    prompt_contract_sha256,
    v2_workflow_manifest,
)
from ai_pdf_api.services.research_worker import (
    load_approved_execution,
)
from research_router_test_support import (
    auth,
    create_run,
    seed_plan_decision,
)
from sqlalchemy import func, select


def test_plan_approval_copies_immutable_execution_snapshot(research_app) -> None:
    client, db, context = research_app
    created = create_run(client, context)
    decision = seed_plan_decision(db, created["id"], context["objectStore"])
    run = db.get(ResearchRun, created["id"])
    assert run is not None
    creator = context["creator"]
    workspace = context["workspace"]

    response = client.post(
        f"/v1/workspaces/{workspace.id}/research-runs/{run.id}/plan-decisions/{decision.id}",
        headers=auth(creator, key="research-plan-approve-01"),
        json={
            "expectedStateVersion": run.state_version,
            "expectedDecisionStateVersion": decision.state_version,
            "inputArtifactSha256": decision.input_artifact_sha256,
            "inputSnapshotSha256": decision.input_snapshot_sha256,
            "action": "approve",
            "comment": None,
            "revision": None,
        },
    )

    assert response.status_code == 200, response.text
    detail = response.json()["run"]
    assert detail["status"] == "queued"
    assert detail["researchExecution"]["inputVersion"] == 1
    assert detail["researchExecution"]["frozenAssetScope"]["assets"] == detail["frozenAssetScope"]["assets"]
    snapshot = db.scalar(select(ResearchExecutionSnapshot).where(ResearchExecutionSnapshot.run_id == run.id))
    assert snapshot is not None
    assert snapshot.approval_decision_id == decision.id
    assert snapshot.max_provider_calls == 32
    assert snapshot.max_tool_calls == 64
    assert snapshot.max_cost_microunits == 5_000_000
    revision = db.get(ResearchPlanRevision, snapshot.approved_plan_revision_id)
    assert revision is not None
    frozen_assets = list(
        db.scalars(
            select(ResearchPlanRevisionAsset)
            .where(ResearchPlanRevisionAsset.plan_revision_id == revision.id)
            .order_by(ResearchPlanRevisionAsset.asset_order)
        ).all()
    )
    bindings = list(
        db.execute(
            select(WorkflowPromptBinding, PromptVersion)
            .join(PromptVersion, PromptVersion.id == WorkflowPromptBinding.prompt_version_id)
            .where(WorkflowPromptBinding.workflow_version_id == revision.proposed_workflow_version_id)
            .order_by(WorkflowPromptBinding.node_key)
        ).all()
    )
    assert snapshot.execution_snapshot_sha256 == canonical_sha256(
        build_execution_snapshot_hash_payload(revision, decision, frozen_assets, bindings)
    )
    assert db.scalar(
        select(func.count()).select_from(ResearchBudgetLedger).where(
            ResearchBudgetLedger.execution_snapshot_id == snapshot.id
        )
    ) == 1
    execution_steps = list(
        db.scalars(
            select(ResearchStep)
            .where(ResearchStep.execution_snapshot_id == snapshot.id)
            .order_by(ResearchStep.created_at, ResearchStep.id)
        ).all()
    )
    assert [step.step_kind for step in execution_steps].count("researcher") == 1
    assert {step.step_key for step in execution_steps} == {
        next(step.step_key for step in execution_steps if step.step_kind == "researcher"),
        "join",
        "verifier",
        "critic",
        "conflict_decision_gate",
        "synthesizer",
        "artifact_publisher",
    }
    execution = load_approved_execution(db, run.id)
    assert [item["nodeKey"] for item in execution["prompts"]] == list(PROMPT_NODE_ORDER)
    assert execution["promptVersionIds"] == [item["promptVersionId"] for item in execution["prompts"]]


def test_v2_prompt_release_specs_have_real_templates_and_closed_hashes() -> None:
    assert tuple(V2_PROMPT_SPECS) == PROMPT_NODE_ORDER
    for spec in V2_PROMPT_SPECS.values():
        assert len(spec.template_text) > 200
        assert spec.variables_schema["additionalProperties"] is False
        assert spec.variables_schema["required"]
        assert spec.template_sha256 == prompt_contract_sha256(spec.template_text, spec.variables_schema)


def test_create_rejects_same_content_rogue_prompt_identity(research_app) -> None:
    client, db, context = research_app
    canonical = db.get(PromptVersion, V2_PROMPT_VERSION_IDS["planner"])
    binding = db.get(WorkflowPromptBinding, (V2_WORKFLOW_VERSION_ID, "planner"))
    assert canonical is not None and binding is not None
    rogue = PromptVersion(
        id=str(uuid4()),
        prompt_key="rogue.planner",
        version_number=99,
        step_kind=canonical.step_kind,
        availability="active",
        template_text=canonical.template_text,
        variables_schema_version=canonical.variables_schema_version,
        variables_schema_json=canonical.variables_schema_json,
        template_sha256=canonical.template_sha256,
        created_by_release_id=canonical.created_by_release_id,
        created_at=canonical.created_at,
    )
    db.add(rogue)
    db.flush()
    binding.prompt_version_id = rogue.id
    db.commit()

    response = client.post(
        f"/v1/workspaces/{context['workspace'].id}/research-runs",
        headers=auth(context["creator"], key="research-rogue-prompt-identity"),
        json={
            "question": "Reject the rogue Prompt identity.",
            "assetScope": {"mode": "selected", "assetIds": [context["asset"].id]},
        },
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "research_provider_not_configured"


def test_create_rejects_same_content_rogue_workflow_identity(research_app) -> None:
    client, db, context = research_app
    canonical = db.get(WorkflowVersion, V2_WORKFLOW_VERSION_ID)
    bindings = list(
        db.scalars(
            select(WorkflowPromptBinding).where(
                WorkflowPromptBinding.workflow_version_id == V2_WORKFLOW_VERSION_ID
            )
        ).all()
    )
    assert canonical is not None and len(bindings) == 5
    prompt_bindings = [(binding.node_key, binding.prompt_version_id) for binding in bindings]
    for binding in bindings:
        db.delete(binding)
    db.delete(canonical)
    db.flush()
    rogue = WorkflowVersion(
        id=str(uuid4()),
        workflow_key="evidence_research",
        version_number=2,
        availability="active",
        manifest_schema_version="2",
        manifest_json=v2_workflow_manifest(),
        manifest_sha256=canonical_sha256(v2_workflow_manifest()),
        created_by_release_id="citeframe-research-v2",
        created_at=canonical.created_at,
    )
    db.add(rogue)
    db.flush()
    db.add_all(
        [
            WorkflowPromptBinding(
                workflow_version_id=rogue.id,
                node_key=node_key,
                prompt_version_id=prompt_id,
            )
            for node_key, prompt_id in prompt_bindings
        ]
    )
    db.commit()

    response = client.post(
        f"/v1/workspaces/{context['workspace'].id}/research-runs",
        headers=auth(context["creator"], key="research-rogue-workflow-identity"),
        json={
            "question": "Reject the rogue Workflow identity.",
            "assetScope": {"mode": "selected", "assetIds": [context["asset"].id]},
        },
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "research_provider_not_configured"


def test_artifact_detail_fails_closed_when_prompt_binding_is_corrupted(research_app) -> None:
    client, db, context = research_app
    created = create_run(client, context)
    decision = seed_plan_decision(db, created["id"], context["objectStore"])
    artifact = db.get(ResearchArtifact, decision.input_artifact_id)
    binding = db.scalar(
        select(ResearchArtifactPromptVersion).where(
            ResearchArtifactPromptVersion.artifact_id == decision.input_artifact_id
        )
    )
    critic_prompt = db.scalar(select(PromptVersion).where(PromptVersion.step_kind == "critic"))
    assert artifact is not None and binding is not None and critic_prompt is not None
    binding.prompt_version_id = critic_prompt.id
    db.commit()

    response = client.get(
        f"/v1/workspaces/{artifact.workspace_id}/research-runs/{artifact.run_id}/artifacts/{artifact.id}",
        headers=auth(context["member"]),
    )
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "research_artifact_unavailable"
