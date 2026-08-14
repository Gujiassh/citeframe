from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import ai_pdf_api.routers.research as research_router_module
import pytest
from ai_pdf_api.core.settings import settings
from ai_pdf_api.modalities.evidence import clone_evidence_locator
from ai_pdf_api.models import (
    AssetRepresentation,
    EvidenceLocator,
    PdfLocatorDetail,
    PromptVersion,
    ResearchArtifact,
    ResearchEvent,
    ResearchEvidenceSnapshot,
    ResearchExecutionSnapshot,
    ResearchIdempotencyRecord,
    ResearchPlanRevision,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
    ResearchStepRetryRequest,
    WorkflowPromptBinding,
    WorkflowVersion,
    WorkspaceMembership,
)
from ai_pdf_api.services.research.research_events import append_research_event
from ai_pdf_api.services.research.research_views import load_research_plan_artifact
from research_router_test_support import (
    approve_seeded_plan,
    auth,
    create_run,
    seed_final_artifact_detail,
    seed_plan_decision,
)
from sqlalchemy import delete, func, select


def test_manual_retry_requeues_same_step_without_fabricating_attempt(research_app) -> None:
    client, db, context = research_app
    run = approve_seeded_plan(client, db, context, create_run(client, context))
    snapshot = db.get(ResearchExecutionSnapshot, run.approved_execution_snapshot_id)
    assert snapshot is not None
    now = datetime.now(UTC)
    step = ResearchStep(
        workspace_id=run.workspace_id,
        run_id=run.id,
        execution_snapshot_id=snapshot.id,
        step_key="researcher:branch-1",
        step_kind="researcher",
        branch_key="branch-1",
        status="failed",
        max_attempts_snapshot=3,
        current_attempt_number=1,
        error_code="provider_timeout",
        error_message="Provider timed out.",
        created_at=now,
        updated_at=now,
        started_at=now,
        finished_at=now,
    )
    db.add(step)
    db.flush()
    db.add(
        ResearchStepAttempt(
            workspace_id=run.workspace_id,
            step_id=step.id,
            attempt_number=1,
            status="timed_out",
            input_sha256="f" * 64,
            error_code="provider_timeout",
            error_message="Provider timed out.",
            started_at=now,
            finished_at=now,
        )
    )
    run.status = "awaiting_retry"
    run.state_version += 1
    db.commit()

    response = client.post(
        f"/v1/workspaces/{run.workspace_id}/research-runs/{run.id}/steps/{step.id}/retry",
        headers=auth(context["creator"], key="research-manual-retry-01"),
        json={
            "expectedStateVersion": run.state_version,
            "expectedStepStateVersion": step.state_version,
            "failedAttempt": 1,
        },
    )
    assert response.status_code == 202, response.text
    assert response.json()["step"]["status"] == "queued"
    assert response.json()["step"]["currentAttemptNumber"] == 1
    assert db.scalar(select(func.count()).select_from(ResearchStepAttempt).where(ResearchStepAttempt.step_id == step.id)) == 1
    assert db.scalar(select(func.count()).select_from(ResearchStepRetryRequest).where(ResearchStepRetryRequest.step_id == step.id)) == 1


def test_artifact_list_and_detail_hide_internal_ledger_rows(research_app) -> None:
    client, db, context = research_app
    created = create_run(client, context)
    decision = seed_plan_decision(db, created["id"], context["objectStore"])
    artifact = db.get(ResearchArtifact, decision.input_artifact_id)
    assert artifact is not None
    workspace = context["workspace"]
    member = context["member"]
    listing = client.get(
        f"/v1/workspaces/{workspace.id}/research-runs/{created['id']}/artifacts",
        headers=auth(member),
    )
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["items"]] == [artifact.id]
    detail = client.get(
        f"/v1/workspaces/{workspace.id}/research-runs/{created['id']}/artifacts/{artifact.id}",
        headers=auth(member),
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["artifact"]["kind"] == "research_plan"
    assert detail.json()["artifact"]["visibility"] == "user"


def test_sse_replays_persisted_events_and_rejects_ahead_cursor(
    research_app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _db, context = research_app
    observations = []
    monkeypatch.setattr(research_router_module, "observe_research_sse", observations.append)
    run = create_run(client, context)
    member = context["member"]
    workspace = context["workspace"]

    replay = client.get(
        f"/v1/workspaces/{workspace.id}/research-runs/{run['id']}/events",
        headers={**auth(member), "Accept": "text/event-stream", "Last-Event-ID": "1"},
    )
    assert replay.status_code == 200
    assert "id: 2\nevent: step_queued\n" in replay.text
    assert "\": keepalive" not in replay.text
    assert replay.text.endswith(": keepalive\n\n")

    ahead = client.get(
        f"/v1/workspaces/{workspace.id}/research-runs/{run['id']}/events",
        headers={**auth(member), "Accept": "text/event-stream", "Last-Event-ID": "999"},
    )
    assert ahead.status_code == 409
    assert ahead.json()["error"]["code"] == "research_state_conflict"
    assert observations == ["reconnect", "reconnect"]


def test_sse_observes_unavailable_history_without_changing_error_contract(
    research_app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db, context = research_app
    run = create_run(client, context)
    member = context["member"]
    workspace = context["workspace"]
    first_event = db.scalar(
        select(ResearchEvent).where(ResearchEvent.run_id == run["id"], ResearchEvent.seq == 1)
    )
    assert first_event is not None
    db.delete(first_event)
    db.commit()
    observations = []
    monkeypatch.setattr(research_router_module, "observe_research_sse", observations.append)

    response = client.get(
        f"/v1/workspaces/{workspace.id}/research-runs/{run['id']}/events",
        headers={**auth(member), "Accept": "text/event-stream", "Last-Event-ID": "0"},
    )

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "research_event_history_unavailable"
    assert observations == ["reconnect", "history_unavailable"]


def test_sse_tail_polls_new_persisted_events(research_app) -> None:
    _client, db, context = research_app
    created = create_run(_client, context)
    run = db.get(ResearchRun, created["id"])
    assert run is not None

    def publish_increment(_seconds: float) -> None:
        run.state_version += 1
        append_research_event(
            db,
            run,
            event_type="run_status_changed",
            dedupe_key="sse-tail-increment",
            data={
                "previousStatus": "planning",
                "status": "planning",
                "runStateVersion": run.state_version,
                "reasonCode": None,
            },
        )
        db.commit()

    frames = list(
        research_router_module.iter_research_event_tail(
            workspace_id=run.workspace_id,
            run_id=run.id,
            user_id=context["member"].id,
            cursor=run.next_event_seq - 1,
            initial_frames=[],
            initial_status=run.status,
            session_factory=research_router_module.RESEARCH_EVENT_SESSION_FACTORY,
            sleep=publish_increment,
            poll_seconds=0,
            keepalive_polls=1,
            max_polls=1,
        )
    )

    assert len(frames) == 1
    assert "event: run_status_changed\n" in frames[0]
    assert "sse-tail-increment" not in frames[0]


def test_sse_tail_closes_when_workspace_membership_is_removed(research_app) -> None:
    client, db, context = research_app
    created = create_run(client, context)
    run = db.get(ResearchRun, created["id"])
    member = context["member"]
    assert run is not None

    def revoke_membership(_seconds: float) -> None:
        db.execute(
            delete(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == run.workspace_id,
                WorkspaceMembership.user_id == member.id,
            )
        )
        db.commit()

    frames = list(
        research_router_module.iter_research_event_tail(
            workspace_id=run.workspace_id,
            run_id=run.id,
            user_id=member.id,
            cursor=run.next_event_seq - 1,
            initial_frames=[],
            initial_status=run.status,
            session_factory=research_router_module.RESEARCH_EVENT_SESSION_FACTORY,
            sleep=revoke_membership,
            poll_seconds=0,
            keepalive_polls=1,
            max_polls=1,
        )
    )

    assert frames == []


def test_artifact_content_verifies_hash_before_return(research_app, monkeypatch: pytest.MonkeyPatch) -> None:
    client, db, context = research_app
    created = create_run(client, context)
    decision = seed_plan_decision(db, created["id"], context["objectStore"])
    artifact = db.get(ResearchArtifact, decision.input_artifact_id)
    assert artifact is not None
    payload = b"{}"
    artifact.byte_size = len(payload)
    artifact.content_sha256 = hashlib.sha256(payload).hexdigest()
    decision.input_artifact_sha256 = artifact.content_sha256
    db.commit()
    monkeypatch.setattr("ai_pdf_api.services.research.research_views.download_bytes", lambda _key: payload)
    member = context["member"]
    workspace = context["workspace"]

    response = client.get(
        f"/v1/workspaces/{workspace.id}/research-runs/{created['id']}/artifacts/{artifact.id}/content",
        headers=auth(member),
    )
    assert response.status_code == 200
    assert response.content == payload
    assert response.headers["etag"] == artifact.content_sha256

    monkeypatch.setattr("ai_pdf_api.services.research.research_views.download_bytes", lambda _key: b"tampered")
    unavailable = client.get(
        f"/v1/workspaces/{workspace.id}/research-runs/{created['id']}/artifacts/{artifact.id}/content",
        headers=auth(member),
    )
    assert unavailable.status_code == 410
    assert unavailable.json()["error"]["code"] == "research_artifact_unavailable"


def test_legacy_plan_reader_strips_cost_only_from_projection(research_app) -> None:
    client, db, context = research_app
    created = create_run(client, context)
    decision = seed_plan_decision(db, created["id"], context["objectStore"])
    artifact = db.get(ResearchArtifact, decision.input_artifact_id)
    assert artifact is not None

    legacy_bytes = context["objectStore"][artifact.object_key]
    assert isinstance(legacy_bytes, bytes)
    payload = __import__("json").loads(legacy_bytes)
    payload["estimatedCost"] = {"currency": "USD", "amountMicros": 1234}
    projected_bytes = __import__("json").dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    context["objectStore"][artifact.object_key] = projected_bytes
    artifact.byte_size = len(projected_bytes)
    artifact.content_sha256 = hashlib.sha256(projected_bytes).hexdigest()
    db.commit()

    plan = load_research_plan_artifact(artifact)

    assert plan.estimated_provider_calls == 1
    assert "estimatedCost" not in plan.model_dump(mode="json", by_alias=True)
    assert context["objectStore"][artifact.object_key] == projected_bytes
    assert artifact.content_sha256 == hashlib.sha256(projected_bytes).hexdigest()


def test_cross_workspace_asset_scope_fails_without_partial_run(research_app) -> None:
    client, db, context = research_app
    creator = context["creator"]
    workspace = context["workspace"]
    other_asset = context["otherAsset"]
    response = client.post(
        f"/v1/workspaces/{workspace.id}/research-runs",
        headers=auth(creator, key="research-invalid-scope-01"),
        json={"question": "Use another workspace.", "assetScope": {"mode": "selected", "assetIds": [other_asset.id]}},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_asset_scope"
    assert db.scalar(select(func.count()).select_from(ResearchRun)) == 0
    failed = db.scalar(select(ResearchIdempotencyRecord))
    assert failed is not None and failed.status == "failed"


def test_question_is_trimmed_and_blank_question_is_rejected(research_app) -> None:
    client, db, context = research_app
    creator = context["creator"]
    workspace = context["workspace"]
    asset = context["asset"]
    blank = client.post(
        f"/v1/workspaces/{workspace.id}/research-runs",
        headers=auth(creator, key="research-blank-question-01"),
        json={"question": "   ", "assetScope": {"mode": "selected", "assetIds": [asset.id]}},
    )
    assert blank.status_code == 422
    assert blank.json()["error"]["code"] == "invalid_research_request"
    assert db.scalar(select(func.count()).select_from(ResearchRun)) == 0

    created = create_run(
        client,
        context,
        key="research-trim-question-01",
        question="  Trim this question.  ",
    )
    assert created["question"] == "Trim this question."


def test_plan_hash_covers_retrieval_configuration(research_app) -> None:
    client, db, context = research_app
    first = create_run(client, context, key="research-hash-topk-01", question="Same question")
    first_run = db.get(ResearchRun, first["id"])
    assert first_run is not None
    first_revision = db.get(ResearchPlanRevision, first_run.current_plan_revision_id)
    assert first_revision is not None
    workspace = context["workspace"]
    workspace.retrieval_top_k = 9
    db.commit()
    second = create_run(client, context, key="research-hash-topk-02", question="Same question")
    second_run = db.get(ResearchRun, second["id"])
    assert second_run is not None
    second_revision = db.get(ResearchPlanRevision, second_run.current_plan_revision_id)
    assert second_revision is not None
    assert first_revision.planning_snapshot_sha256 != second_revision.planning_snapshot_sha256


def test_each_run_uses_an_independent_locator_clone_for_the_same_source(research_app) -> None:
    client, db, context = research_app
    first = create_run(client, context, key="research-locator-clone-01")
    second = create_run(client, context, key="research-locator-clone-02")
    asset = context["asset"]
    now = datetime.now(UTC)
    representation = AssetRepresentation(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        representation_kind="pdf_text_legacy",
        processing_generation=asset.current_processing_generation,
        generator_version="parser-v1",
        created_at=now,
    )
    db.add(representation)
    db.flush()
    source = EvidenceLocator(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        locator_kind="pdf_page",
        locator_version=1,
        processing_generation_snapshot=asset.current_processing_generation,
        representation_id_snapshot=representation.id,
        created_at=now,
    )
    db.add(source)
    db.flush()
    db.add(PdfLocatorDetail(locator_id=source.id, page_number=1))
    db.flush()
    snapshots = []
    for created in (first, second):
        run = db.get(ResearchRun, created["id"])
        step = db.scalar(select(ResearchStep).where(ResearchStep.run_id == run.id))
        assert run is not None and step is not None
        cloned = clone_evidence_locator(
            db,
            source.id,
            created_at=now,
            workspace_id=run.workspace_id,
            asset_id=asset.id,
            processing_generation=asset.current_processing_generation,
            representation_id=representation.id,
        )
        snapshot = ResearchEvidenceSnapshot(
            workspace_id=run.workspace_id,
            run_id=run.id,
            captured_by_step_id=step.id,
            evidence_locator_id=cloned.id,
            asset_id=asset.id,
            asset_kind_snapshot=asset.asset_kind,
            asset_title_snapshot=asset.title,
            excerpt_snapshot="Shared source excerpt.",
            processing_generation_snapshot=asset.current_processing_generation,
            representation_id_snapshot=representation.id,
            parser_version_snapshot=representation.generator_version,
            index_version_snapshot=asset.current_index_version,
            retrieval_channel="dense",
            source_fingerprint_sha256="f" * 64,
            created_at=now,
        )
        db.add(snapshot)
        snapshots.append(snapshot)
    db.commit()
    assert snapshots[0].evidence_locator_id != snapshots[1].evidence_locator_id
    assert snapshots[0].source_fingerprint_sha256 == snapshots[1].source_fingerprint_sha256
    assert db.scalar(select(func.count()).select_from(ResearchEvidenceSnapshot)) == 2


@pytest.mark.parametrize("drift", ["provider", "budget"])
def test_plan_approval_fails_closed_when_frozen_execution_policy_drifts(
    research_app,
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    client, db, context = research_app
    created = create_run(client, context)
    decision = seed_plan_decision(db, created["id"], context["objectStore"])
    run = db.get(ResearchRun, created["id"])
    revision = db.get(ResearchPlanRevision, run.current_plan_revision_id)
    assert run is not None and revision is not None
    if drift == "provider":
        monkeypatch.setattr(settings, "generation_model", "drifted-model")
    else:
        revision.proposed_max_tool_calls += 1
        db.commit()
    response = client.post(
        f"/v1/workspaces/{run.workspace_id}/research-runs/{run.id}/plan-decisions/{decision.id}",
        headers=auth(context["creator"], key=f"research-policy-drift-{drift}"),
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
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "research_execution_policy_unavailable"
    assert db.scalar(select(ResearchExecutionSnapshot).where(ResearchExecutionSnapshot.run_id == run.id)) is None
    db.refresh(decision)
    assert decision.status == "pending"


def test_plan_approval_rejects_tampered_artifact_bytes(research_app) -> None:
    client, db, context = research_app
    created = create_run(client, context)
    decision = seed_plan_decision(db, created["id"], context["objectStore"])
    run = db.get(ResearchRun, created["id"])
    artifact = db.get(ResearchArtifact, decision.input_artifact_id)
    assert run is not None and artifact is not None
    context["objectStore"][artifact.object_key] = b"{" + b" " * (artifact.byte_size - 1)

    response = client.post(
        f"/v1/workspaces/{run.workspace_id}/research-runs/{run.id}/plan-decisions/{decision.id}",
        headers=auth(context["creator"], key="research-tampered-plan"),
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

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "research_artifact_integrity_mismatch"
    db.refresh(run)
    assert run.status == "awaiting_plan_approval"
    assert run.approved_execution_snapshot_id is None


def test_unexpected_mutation_error_is_frozen_for_idempotent_replay(
    research_app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db, context = research_app

    def fail_revision(*_args, **_kwargs):
        raise RuntimeError("unexpected create failure")

    monkeypatch.setattr("ai_pdf_api.services.research.research_runs._add_revision", fail_revision)
    workspace = context["workspace"]
    creator = context["creator"]
    asset = context["asset"]
    request = {
        "question": "Trigger a durable failure.",
        "assetScope": {"mode": "selected", "assetIds": [asset.id]},
    }
    headers = auth(creator, key="research-unexpected-failure")
    first = client.post(f"/v1/workspaces/{workspace.id}/research-runs", headers=headers, json=request)

    replay = client.post(f"/v1/workspaces/{workspace.id}/research-runs", headers=headers, json=request)
    assert first.status_code == 500
    assert replay.status_code == 500
    first_error = first.json()["error"]
    replay_error = replay.json()["error"]
    assert first_error["code"] == "research_internal_error"
    assert first.content == replay.content
    assert first_error == replay_error
    assert first_error["requestId"]
    record = db.scalar(
        select(ResearchIdempotencyRecord).where(
            ResearchIdempotencyRecord.idempotency_key == "research-unexpected-failure"
        )
    )
    assert record is not None and record.status == "failed"
    assert record.response_json == first.json()


def test_create_fails_closed_without_deployment_published_versions(research_app) -> None:
    client, db, context = research_app
    db.execute(delete(WorkflowPromptBinding))
    db.execute(delete(PromptVersion))
    db.execute(delete(WorkflowVersion))
    db.commit()
    creator = context["creator"]
    workspace = context["workspace"]
    asset = context["asset"]
    response = client.post(
        f"/v1/workspaces/{workspace.id}/research-runs",
        headers=auth(creator, key="research-missing-release-01"),
        json={"question": "Should fail closed.", "assetScope": {"mode": "selected", "assetIds": [asset.id]}},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "research_provider_not_configured"
    assert db.scalar(select(func.count()).select_from(WorkflowVersion)) == 0
    assert db.scalar(select(func.count()).select_from(ResearchRun)) == 0


def test_f5_historical_final_artifact_bytes_survive_retry_and_recovery(
    research_app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F5 residual: finished final_report bytes/hashes stay immutable across retry.

    Simulates a pre-V5-C-style finished artifact (legacy agent I/O registry on the
    execution snapshot when columns exist) and proves manual step retry / recovery
    requeue does not rewrite object bytes, content_sha256, or byte_size.
    Does not call a paid provider.
    """
    from ai_pdf_api.services.research.research_agent_io_registry import (
        AGENT_RESULT_SCHEMA_VERSION_LEGACY,
        COMPACT_POLICY_VERSION_LEGACY,
        CONTEXT_POLICY_VERSION_LEGACY,
    )

    client, db, context = research_app
    run, artifact, _claim, steps = seed_final_artifact_detail(client, db, context)
    snapshot = db.get(ResearchExecutionSnapshot, run.approved_execution_snapshot_id)
    assert snapshot is not None
    if hasattr(snapshot, "agent_result_schema_version"):
        snapshot.agent_result_schema_version = AGENT_RESULT_SCHEMA_VERSION_LEGACY
        snapshot.context_policy_version = CONTEXT_POLICY_VERSION_LEGACY
        snapshot.compact_policy_version = COMPACT_POLICY_VERSION_LEGACY

    content = b"# Citeframe Research Report\n"
    assert artifact.byte_size == len(content)
    expected_sha = hashlib.sha256(content).hexdigest()
    assert artifact.content_sha256 == expected_sha
    object_store = context["objectStore"]
    assert isinstance(object_store, dict)
    object_store[artifact.object_key] = content
    object_key = artifact.object_key
    artifact_id = artifact.id
    run_id = run.id
    workspace_id = run.workspace_id

    # Capture pre-retry identity oracle.
    before = {
        "artifactId": artifact_id,
        "objectKey": object_key,
        "byteSize": artifact.byte_size,
        "contentSha256": artifact.content_sha256,
        "objectBytesSha256": hashlib.sha256(object_store[object_key]).hexdigest(),
        "agentResultSchemaVersion": getattr(snapshot, "agent_result_schema_version", None),
    }

    # Add a failed branch step (same pattern as manual-retry oracle) and requeue it.
    # Final report identity must remain untouched by recovery bookkeeping.
    now = datetime.now(UTC)
    failed_step = ResearchStep(
        workspace_id=workspace_id,
        run_id=run_id,
        execution_snapshot_id=snapshot.id,
        step_key="researcher:f5-branch",
        step_kind="researcher",
        branch_key="f5-branch",
        status="failed",
        max_attempts_snapshot=3,
        current_attempt_number=1,
        error_code="provider_timeout",
        error_message="Provider timed out.",
        created_at=now,
        updated_at=now,
        started_at=now,
        finished_at=now,
    )
    db.add(failed_step)
    db.flush()
    db.add(
        ResearchStepAttempt(
            workspace_id=workspace_id,
            step_id=failed_step.id,
            attempt_number=1,
            status="timed_out",
            input_sha256="a" * 64,
            error_code="provider_timeout",
            error_message="Provider timed out.",
            started_at=now,
            finished_at=now,
        )
    )
    run.status = "awaiting_retry"
    run.state_version += 1
    db.commit()
    db.refresh(run)
    db.refresh(failed_step)

    response = client.post(
        f"/v1/workspaces/{workspace_id}/research-runs/{run_id}/steps/{failed_step.id}/retry",
        headers=auth(context["creator"], key="research-f5-legacy-retry-01"),
        json={
            "expectedStateVersion": run.state_version,
            "expectedStepStateVersion": failed_step.state_version,
            "failedAttempt": 1,
        },
    )
    assert response.status_code == 202, response.text

    db.refresh(artifact)
    after_bytes = object_store[object_key]
    after = {
        "artifactId": artifact.id,
        "objectKey": artifact.object_key,
        "byteSize": artifact.byte_size,
        "contentSha256": artifact.content_sha256,
        "objectBytesSha256": hashlib.sha256(after_bytes).hexdigest(),
        "agentResultSchemaVersion": getattr(
            db.get(ResearchExecutionSnapshot, run.approved_execution_snapshot_id),
            "agent_result_schema_version",
            None,
        ),
    }
    assert after == before
    assert after_bytes == content

    monkeypatch.setattr(
        "ai_pdf_api.services.research.research_views.download_bytes",
        lambda key: object_store[key],
    )
    content_response = client.get(
        f"/v1/workspaces/{workspace_id}/research-runs/{run_id}/artifacts/{artifact_id}/content",
        headers=auth(context["member"]),
    )
    assert content_response.status_code == 200
    assert content_response.content == content
    assert content_response.headers["etag"] == expected_sha

    # Recovery projection: detail still serves the same identity.
    detail = client.get(
        f"/v1/workspaces/{workspace_id}/research-runs/{run_id}/artifacts/{artifact_id}",
        headers=auth(context["member"]),
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()["artifact"]
    assert body["id"] == artifact_id
    assert body["sha256"] == expected_sha
    assert body["byteSize"] == len(content)
