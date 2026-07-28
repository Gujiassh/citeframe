from __future__ import annotations

import hashlib
import json
from collections.abc import Generator
from datetime import UTC, datetime
from uuid import uuid4

import ai_pdf_api.routers.research as research_router_module
import pytest
from ai_pdf_api.db.base import Base
from ai_pdf_api.db.session import get_db
from ai_pdf_api.models import (
    Asset,
    HumanDecision,
    ResearchArtifact,
    ResearchArtifactClaim,
    ResearchArtifactPromptVersion,
    ResearchClaim,
    ResearchExecutionPromptVersion,
    ResearchExecutionSnapshot,
    ResearchPlanRevision,
    ResearchPlanRevisionAsset,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
    User,
    Workspace,
    WorkspaceMembership,
)
from ai_pdf_api.routers.research import router
from ai_pdf_api.services.research_versions_service import (
    publish_research_versions_for_release,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def research_app(monkeypatch: pytest.MonkeyPatch) -> Generator[tuple[TestClient, Session, dict[str, object]], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    poll_session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    db = poll_session_factory()
    monkeypatch.setattr(research_router_module, "RESEARCH_EVENT_SESSION_FACTORY", poll_session_factory)
    monkeypatch.setattr(research_router_module, "RESEARCH_EVENT_POLL_SECONDS", 0)
    monkeypatch.setattr(research_router_module, "RESEARCH_EVENT_KEEPALIVE_POLLS", 1)
    monkeypatch.setattr(research_router_module, "RESEARCH_EVENT_MAX_POLLS", 1)
    now = datetime.now(UTC)
    creator = User(
        id=str(uuid4()), email="research-creator@example.com", name="Creator", password_hash="hash", avatar_url=""
    )
    member = User(
        id=str(uuid4()), email="research-member@example.com", name="Member", password_hash="hash", avatar_url=""
    )
    owner = User(
        id=str(uuid4()), email="research-owner@example.com", name="Owner", password_hash="hash", avatar_url=""
    )
    stranger = User(
        id=str(uuid4()), email="research-stranger@example.com", name="Stranger", password_hash="hash", avatar_url=""
    )
    workspace = Workspace(
        id=str(uuid4()),
        name="Research",
        created_by_user_id=owner.id,
        created_at=now,
        updated_at=now,
    )
    other_workspace = Workspace(
        id=str(uuid4()),
        name="Other",
        created_by_user_id=stranger.id,
        created_at=now,
        updated_at=now,
    )
    db.add_all([creator, member, owner, stranger, workspace, other_workspace])
    db.flush()
    db.add_all(
        [
            WorkspaceMembership(workspace_id=workspace.id, user_id=creator.id, role="member"),
            WorkspaceMembership(workspace_id=workspace.id, user_id=member.id, role="member"),
            WorkspaceMembership(workspace_id=workspace.id, user_id=owner.id, role="owner"),
            WorkspaceMembership(workspace_id=other_workspace.id, user_id=stranger.id, role="owner"),
        ]
    )
    asset = Asset(
        id=str(uuid4()),
        workspace_id=workspace.id,
        created_by_user_id=creator.id,
        asset_kind="pdf",
        title="Source",
        source_filename="source.pdf",
        object_key=f"workspaces/{workspace.id}/source.pdf",
        mime_type="application/pdf",
        byte_size=100,
        status="ready",
        current_processing_generation=2,
        current_index_version=3,
        created_at=now,
        updated_at=now,
    )
    other_asset = Asset(
        id=str(uuid4()),
        workspace_id=other_workspace.id,
        created_by_user_id=stranger.id,
        asset_kind="pdf",
        title="Other source",
        source_filename="other.pdf",
        object_key=f"workspaces/{other_workspace.id}/other.pdf",
        mime_type="application/pdf",
        byte_size=100,
        status="ready",
        created_at=now,
        updated_at=now,
    )
    db.add_all([asset, other_asset])
    db.commit()
    publish_research_versions_for_release(db, now)
    db.commit()
    object_store: dict[str, bytes] = {}
    monkeypatch.setattr(
        "ai_pdf_api.services.research_views.download_bytes",
        lambda object_key: object_store[object_key],
    )

    app = FastAPI()
    app.include_router(router)

    def override_get_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    context = {
        "creator": creator,
        "member": member,
        "owner": owner,
        "stranger": stranger,
        "workspace": workspace,
        "otherWorkspace": other_workspace,
        "asset": asset,
        "otherAsset": other_asset,
        "objectStore": object_store,
    }
    with TestClient(app) as client:
        yield client, db, context
    db.close()
    engine.dispose()


def auth(user: User, *, key: str | None = None) -> dict[str, str]:
    headers = {
        "x-ai-pdf-internal-token": "local-development-internal-token",
        "x-user-id": user.id,
    }
    if key:
        headers["Idempotency-Key"] = key
    return headers


def create_run(
    client: TestClient,
    context: dict[str, object],
    *,
    key: str = "research-create-key-0001",
    question: str = "Compare the evidence.",
) -> dict[str, object]:
    creator = context["creator"]
    workspace = context["workspace"]
    asset = context["asset"]
    assert isinstance(creator, User) and isinstance(workspace, Workspace) and isinstance(asset, Asset)
    response = client.post(
        f"/v1/workspaces/{workspace.id}/research-runs",
        headers=auth(creator, key=key),
        json={"question": question, "assetScope": {"mode": "selected", "assetIds": [asset.id]}},
    )
    assert response.status_code == 201, response.text
    return response.json()["run"]




def seed_plan_decision(db: Session, run_id: str, object_store: dict[str, bytes]) -> HumanDecision:
    run = db.get(ResearchRun, run_id)
    assert run is not None
    planner = db.scalar(select(ResearchStep).where(ResearchStep.run_id == run.id, ResearchStep.step_kind == "planner"))
    revision = db.get(ResearchPlanRevision, run.current_plan_revision_id)
    assert planner is not None and revision is not None
    now = datetime.now(UTC)
    attempt = ResearchStepAttempt(
        workspace_id=run.workspace_id,
        step_id=planner.id,
        attempt_number=1,
        status="succeeded",
        input_sha256=revision.planning_snapshot_sha256,
        output_sha256="1" * 64,
        started_at=now,
        finished_at=now,
    )
    db.add(attempt)
    db.flush()
    planner.status = "succeeded"
    planner.current_attempt_number = 1
    planner.started_at = now
    planner.finished_at = now
    planner.updated_at = now
    plan_asset = db.scalar(
        select(ResearchPlanRevisionAsset).where(ResearchPlanRevisionAsset.plan_revision_id == revision.id)
    )
    assert plan_asset is not None
    plan_bytes = json.dumps(
        {
            "summary": "Compare the frozen evidence.",
            "subproblems": [
                {
                    "id": str(uuid4()),
                    "order": 0,
                    "question": "What does the source establish?",
                    "assetIds": [plan_asset.asset_id],
                    "expectedEvidence": [],
                }
            ],
            "knownGaps": [],
            "estimatedProviderCalls": 1,
            "estimatedInputTokens": 100,
            "estimatedOutputTokens": 100,
            "estimatedCost": {"currency": run.cost_currency, "amountMicros": 1000},
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    attempt.output_sha256 = hashlib.sha256(plan_bytes).hexdigest()
    object_key = f"research/{run.id}/plan.json"
    object_store[object_key] = plan_bytes
    artifact = ResearchArtifact(
        workspace_id=run.workspace_id,
        run_id=run.id,
        generated_by_step_id=planner.id,
        generated_by_attempt_id=attempt.id,
        artifact_kind="research_plan",
        visibility="user",
        logical_key="plan:revision-1",
        schema_version="1",
        object_key=object_key,
        content_type="application/json",
        byte_size=len(plan_bytes),
        content_sha256=hashlib.sha256(plan_bytes).hexdigest(),
        workflow_version_id=revision.proposed_workflow_version_id,
        direct_prompt_version_id=revision.planner_prompt_version_id,
        generation_provider=revision.proposed_generation_provider,
        generation_model=revision.proposed_generation_model,
        retention_class="workspace_lifetime",
        created_at=now,
    )
    gate = ResearchStep(
        workspace_id=run.workspace_id,
        run_id=run.id,
        plan_revision_id=revision.id,
        step_key="revision-1:plan-gate",
        step_kind="plan_approval_gate",
        status="waiting",
        max_attempts_snapshot=1,
        created_at=now,
        updated_at=now,
    )
    db.add_all([artifact, gate])
    db.flush()
    db.add(
        ResearchArtifactPromptVersion(
            artifact_id=artifact.id,
            node_key="planner",
            prompt_version_id=revision.planner_prompt_version_id,
        )
    )
    decision = HumanDecision(
        workspace_id=run.workspace_id,
        run_id=run.id,
        gate_step_id=gate.id,
        decision_type="plan_approval",
        request_number=1,
        status="pending",
        input_artifact_id=artifact.id,
        input_artifact_sha256=artifact.content_sha256,
        input_snapshot_sha256=revision.planning_snapshot_sha256,
        requested_at=now,
    )
    db.add(decision)
    run.status = "awaiting_plan_approval"
    run.state_version += 1
    run.updated_at = now
    db.commit()
    return decision




def approve_seeded_plan(client: TestClient, db: Session, context: dict[str, object], created: dict) -> ResearchRun:
    decision = seed_plan_decision(db, created["id"], context["objectStore"])
    run = db.get(ResearchRun, created["id"])
    assert run is not None
    response = client.post(
        f"/v1/workspaces/{context['workspace'].id}/research-runs/{run.id}/plan-decisions/{decision.id}",
        headers=auth(context["creator"], key=f"approve-{run.id}"),
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
    db.refresh(run)
    return run




def seed_final_artifact_detail(
    client: TestClient,
    db: Session,
    context: dict[str, object],
) -> tuple[ResearchRun, ResearchArtifact, ResearchClaim, dict[str, ResearchStep]]:
    run = approve_seeded_plan(client, db, context, create_run(client, context))
    snapshot = db.get(ResearchExecutionSnapshot, run.approved_execution_snapshot_id)
    assert snapshot is not None
    steps = {
        kind: db.scalar(
            select(ResearchStep).where(
                ResearchStep.run_id == run.id,
                ResearchStep.step_kind == kind,
            )
        )
        for kind in ("researcher", "verifier", "critic", "artifact_publisher")
    }
    assert all(step is not None for step in steps.values())
    typed_steps = {kind: step for kind, step in steps.items() if step is not None}
    now = datetime.now(UTC)
    content = b"# Citeframe Research Report\n"
    publisher = typed_steps["artifact_publisher"]
    attempt = ResearchStepAttempt(
        workspace_id=run.workspace_id,
        step_id=publisher.id,
        attempt_number=1,
        status="succeeded",
        input_sha256=publisher.input_sha256 or snapshot.execution_snapshot_sha256,
        output_sha256=hashlib.sha256(content).hexdigest(),
        started_at=now,
        finished_at=now,
    )
    db.add(attempt)
    db.flush()
    artifact = ResearchArtifact(
        workspace_id=run.workspace_id,
        run_id=run.id,
        generated_by_step_id=publisher.id,
        generated_by_attempt_id=attempt.id,
        artifact_kind="final_report",
        visibility="user",
        logical_key="final-report",
        schema_version="1",
        object_key=f"research/{run.workspace_id}/{run.id}/final.md",
        content_type="text/markdown",
        byte_size=len(content),
        content_sha256=hashlib.sha256(content).hexdigest(),
        workflow_version_id=snapshot.workflow_version_id,
        direct_prompt_version_id=publisher.prompt_version_id,
        generation_provider=snapshot.generation_provider,
        generation_model=snapshot.generation_model,
        retention_class="workspace_lifetime",
        created_at=now,
    )
    claim = ResearchClaim(
        workspace_id=run.workspace_id,
        run_id=run.id,
        claim_key="final-detail-claim",
        claim_order=0,
        statement_text="Supported unresolved statement.",
        statement_sha256=hashlib.sha256(b"Supported unresolved statement.").hexdigest(),
        produced_by_step_id=typed_steps["researcher"].id,
        verification_status="supported",
        verified_by_step_id=typed_steps["verifier"].id,
        conflict_status="resolved_unresolved",
        critic_step_id=typed_steps["critic"].id,
        created_at=now,
        verified_at=now,
    )
    db.add_all([artifact, claim])
    db.flush()
    prompts = list(
        db.scalars(
            select(ResearchExecutionPromptVersion).where(
                ResearchExecutionPromptVersion.execution_snapshot_id == snapshot.id
            )
        ).all()
    )
    db.add_all(
        [
            ResearchArtifactPromptVersion(
                artifact_id=artifact.id,
                node_key=prompt.node_key,
                prompt_version_id=prompt.prompt_version_id,
            )
            for prompt in prompts
        ]
    )
    db.add(
        ResearchArtifactClaim(
            artifact_id=artifact.id,
            claim_id=claim.id,
            claim_order=0,
            section_kind="unresolved",
        )
    )
    db.commit()
    return run, artifact, claim, typed_steps
