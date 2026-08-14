from __future__ import annotations

from datetime import UTC, datetime

from ai_pdf_api.core.settings import settings
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    EvidenceLocator,
    HumanDecision,
    HumanDecisionClaim,
    PdfLocatorDetail,
    ResearchArtifact,
    ResearchArtifactClaim,
    ResearchClaim,
    ResearchClaimEvidence,
    ResearchEvidenceSnapshot,
    ResearchExecutionSnapshot,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
)
from ai_pdf_api.services.research.research_evidence_provenance import evidence_source_fingerprint
from ai_pdf_api.services.research.research_prompt_provenance import (
    V2_PROMPT_VERSION_IDS,
)
from research_router_test_support import (
    approve_seeded_plan,
    auth,
    create_run,
    seed_final_artifact_detail,
)
from sqlalchemy import select


def test_final_artifact_detail_accepts_complete_canonical_chain(research_app) -> None:
    client, db, context = research_app
    run, artifact, _claim, _steps = seed_final_artifact_detail(client, db, context)

    response = client.get(
        f"/v1/workspaces/{run.workspace_id}/research-runs/{run.id}/artifacts/{artifact.id}",
        headers=auth(context["member"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["artifact"]["directPromptVersionId"] == artifact.direct_prompt_version_id


def test_final_artifact_detail_rejects_provider_prompt_and_claim_step_corruption(research_app) -> None:
    client, db, context = research_app
    run, artifact, claim, steps = seed_final_artifact_detail(client, db, context)
    path = f"/v1/workspaces/{run.workspace_id}/research-runs/{run.id}/artifacts/{artifact.id}"

    artifact.generation_model = "rogue-model"
    db.commit()
    assert client.get(path, headers=auth(context["member"])).status_code == 410
    artifact.generation_model = settings.generation_model
    artifact.direct_prompt_version_id = V2_PROMPT_VERSION_IDS["critic"]
    db.commit()
    assert client.get(path, headers=auth(context["member"])).status_code == 410
    artifact.direct_prompt_version_id = steps["artifact_publisher"].prompt_version_id
    foreign = create_run(client, context, key="research-foreign-verifier-chain")
    foreign_step = db.scalar(
        select(ResearchStep).where(ResearchStep.run_id == foreign["id"])
    )
    assert foreign_step is not None
    claim.verified_by_step_id = foreign_step.id
    db.commit()
    assert client.get(path, headers=auth(context["member"])).status_code == 410
    claim.verified_by_step_id = steps["verifier"].id
    claim.critic_step_id = foreign_step.id
    db.commit()
    assert client.get(path, headers=auth(context["member"])).status_code == 410


def test_final_artifact_detail_rejects_tampered_evidence_excerpt(research_app) -> None:
    client, db, context = research_app
    run, artifact, claim, steps = seed_final_artifact_detail(client, db, context)
    asset = context["asset"]
    assert isinstance(asset, Asset)
    now = datetime.now(UTC)
    representation = AssetRepresentation(
        workspace_id=run.workspace_id,
        asset_id=asset.id,
        representation_kind="pdf_page_layout",
        processing_generation=asset.current_processing_generation,
        generator_provider="test",
        generator_model="test",
        generator_version="test-v1",
        object_key=f"representations/{asset.id}/layout.json",
        content_sha256="1" * 64,
        created_at=now,
    )
    db.add(representation)
    db.flush()
    locator = EvidenceLocator(
        workspace_id=run.workspace_id,
        asset_id=asset.id,
        locator_kind="pdf_page",
        locator_version=1,
        processing_generation_snapshot=asset.current_processing_generation,
        representation_id_snapshot=representation.id,
        created_at=now,
    )
    db.add(locator)
    db.flush()
    db.add(PdfLocatorDetail(locator_id=locator.id, page_number=1))
    evidence = ResearchEvidenceSnapshot(
        workspace_id=run.workspace_id,
        run_id=run.id,
        captured_by_step_id=steps["researcher"].id,
        evidence_locator_id=locator.id,
        asset_id=asset.id,
        asset_kind_snapshot=asset.asset_kind,
        asset_title_snapshot=asset.title,
        excerpt_snapshot="Frozen detail excerpt.",
        processing_generation_snapshot=asset.current_processing_generation,
        representation_id_snapshot=representation.id,
        parser_version_snapshot=representation.generator_version,
        index_version_snapshot=asset.current_index_version,
        retrieval_channel="text",
        source_fingerprint_sha256="pending",
        created_at=now,
    )
    evidence.source_fingerprint_sha256 = evidence_source_fingerprint(
        evidence,
        locator_kind=locator.locator_kind,
    )
    db.add(evidence)
    db.flush()
    db.add(
        ResearchClaimEvidence(
            claim_id=claim.id,
            evidence_snapshot_id=evidence.id,
            evidence_order=0,
            relationship="supports",
            assessed_by_step_id=steps["verifier"].id,
        )
    )
    db.commit()
    path = f"/v1/workspaces/{run.workspace_id}/research-runs/{run.id}/artifacts/{artifact.id}"
    assert client.get(path, headers=auth(context["member"])).status_code == 200
    evidence.excerpt_snapshot = "Tampered detail excerpt."
    db.commit()
    assert client.get(path, headers=auth(context["member"])).status_code == 410


def test_conflict_decision_resolves_only_bound_supported_claims(research_app) -> None:
    client, db, context = research_app
    run = approve_seeded_plan(client, db, context, create_run(client, context))
    snapshot = db.get(ResearchExecutionSnapshot, run.approved_execution_snapshot_id)
    assert snapshot is not None
    now = datetime.now(UTC)
    critic = db.scalar(
        select(ResearchStep).where(ResearchStep.run_id == run.id, ResearchStep.step_kind == "critic")
    )
    gate = db.scalar(
        select(ResearchStep).where(
            ResearchStep.run_id == run.id,
            ResearchStep.step_kind == "conflict_decision_gate",
        )
    )
    assert critic is not None and gate is not None
    critic.status = "succeeded"
    critic.current_attempt_number = 1
    critic.started_at = now
    critic.finished_at = now
    critic.updated_at = now
    gate.status = "waiting"
    gate.updated_at = now
    attempt = ResearchStepAttempt(
        workspace_id=run.workspace_id,
        step_id=critic.id,
        attempt_number=1,
        status="succeeded",
        input_sha256="b" * 64,
        output_sha256="c" * 64,
        started_at=now,
        finished_at=now,
    )
    claim = ResearchClaim(
        workspace_id=run.workspace_id,
        run_id=run.id,
        claim_key="claim-conflict",
        claim_order=0,
        statement_text="Conflicted statement",
        statement_sha256="d" * 64,
        produced_by_step_id=critic.id,
        verification_status="supported",
        verified_by_step_id=critic.id,
        conflict_status="conflicted",
        critic_step_id=critic.id,
        created_at=now,
        verified_at=now,
    )
    db.add_all([attempt, claim])
    db.flush()
    artifact = ResearchArtifact(
        workspace_id=run.workspace_id,
        run_id=run.id,
        generated_by_step_id=critic.id,
        generated_by_attempt_id=attempt.id,
        artifact_kind="conflict_report",
        visibility="user",
        logical_key="conflict-report",
        schema_version="1",
        object_key=f"research/{run.id}/conflict.json",
        content_type="application/json",
        byte_size=2,
        content_sha256="e" * 64,
        workflow_version_id=snapshot.workflow_version_id,
        direct_prompt_version_id=critic.prompt_version_id,
        generation_provider=snapshot.generation_provider,
        generation_model=snapshot.generation_model,
        retention_class="workspace_lifetime",
        created_at=now,
    )
    db.add(artifact)
    db.flush()
    db.add(
        ResearchArtifactClaim(
            artifact_id=artifact.id,
            claim_id=claim.id,
            claim_order=0,
            section_kind="conflict",
        )
    )
    other_created = create_run(client, context, key="research-cross-run-conflict")
    other_run = db.get(ResearchRun, other_created["id"])
    other_planner = db.scalar(
        select(ResearchStep).where(ResearchStep.run_id == other_created["id"], ResearchStep.step_kind == "planner")
    )
    assert other_run is not None and other_planner is not None
    foreign_claim = ResearchClaim(
        workspace_id=other_run.workspace_id,
        run_id=other_run.id,
        claim_key="foreign-conflict",
        claim_order=0,
        statement_text="Foreign conflicted statement",
        statement_sha256="9" * 64,
        produced_by_step_id=other_planner.id,
        verification_status="supported",
        verified_by_step_id=other_planner.id,
        conflict_status="conflicted",
        critic_step_id=other_planner.id,
        created_at=now,
        verified_at=now,
    )
    db.add(foreign_claim)
    db.flush()
    db.add(
        ResearchArtifactClaim(
            artifact_id=artifact.id,
            claim_id=foreign_claim.id,
            claim_order=1,
            section_kind="conflict",
        )
    )
    decision = HumanDecision(
        workspace_id=run.workspace_id,
        run_id=run.id,
        gate_step_id=gate.id,
        decision_type="conflict_resolution",
        request_number=1,
        status="pending",
        input_artifact_id=artifact.id,
        input_artifact_sha256=artifact.content_sha256,
        input_snapshot_sha256=snapshot.execution_snapshot_sha256,
        requested_at=now,
    )
    db.add(decision)
    db.flush()
    run.status = "awaiting_human_decision"
    run.state_version += 1
    db.commit()

    response = client.post(
        f"/v1/workspaces/{run.workspace_id}/research-runs/{run.id}/conflict-decisions/{decision.id}",
        headers=auth(context["creator"], key="research-conflict-keep-01"),
        json={
            "expectedStateVersion": run.state_version,
            "expectedDecisionStateVersion": decision.state_version,
            "inputArtifactSha256": decision.input_artifact_sha256,
            "inputSnapshotSha256": decision.input_snapshot_sha256,
            "action": "keep_as_unresolved",
            "comment": "Keep this visible as unresolved.",
        },
    )
    assert response.status_code == 200, response.text
    db.refresh(claim)
    assert claim.conflict_status == "resolved_unresolved"
    db.refresh(foreign_claim)
    assert foreign_claim.conflict_status == "conflicted"
    assert db.get(HumanDecisionClaim, (decision.id, foreign_claim.id)) is None
    disposition = db.get(HumanDecisionClaim, (decision.id, claim.id))
    assert disposition is not None and disposition.disposition == "leave_unresolved"
    assert response.json()["run"]["status"] == "queued"
    assert response.json()["decision"]["action"] == "keep_as_unresolved"
