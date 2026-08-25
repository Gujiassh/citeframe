from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from ai_pdf_api.models import (
    HumanDecision,
    ResearchArtifact,
    ResearchClaim,
    ResearchEvent,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
)
from ai_pdf_api.services import (
    research_worker_plan,
)
from ai_pdf_api.services.research.research_idempotency import ResearchError
from ai_pdf_api.services.research.research_worker import (
    PlanSubproblemDraft,
    claim_next_research_step,
    claim_specific_research_step,
    complete_research_step,
    heartbeat_research_step,
    load_approved_execution,
    publish_research_plan,
)
from research_worker_test_support import (
    add_execution_chain,
    add_step,
    assert_research_error,
    lease_default_step,
    lease_planner_step,
    make_planning_chain,
    sha256,
)
from sqlalchemy import select
from sqlalchemy.orm import Session


def test_claim_next_leases_oldest_queued_step_and_records_attempt_and_events(research_worker_db) -> None:
    fixture = research_worker_db
    fixture.step.queued_at = fixture.now + timedelta(seconds=5)
    older = add_step(
        fixture,
        step_key="join",
        step_kind="join",
        queued_at=fixture.now - timedelta(seconds=5),
    )

    lease = claim_next_research_step(
        fixture.db,
        worker_instance_id="global-worker",
        lease_seconds=90,
        now=fixture.now,
    )

    assert lease is not None
    assert lease.step_id == older.id
    assert lease.attempt_number == 1
    assert lease.lease_expires_at == fixture.now + timedelta(seconds=90)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert attempt is not None
    assert attempt.worker_instance_id == "global-worker"
    assert attempt.lease_token_hash == sha256(lease.lease_token)
    assert attempt.status == "running"
    fixture.db.refresh(older)
    fixture.db.refresh(fixture.step)
    fixture.db.refresh(fixture.run)
    assert older.status == "running"
    assert fixture.step.status == "queued"
    assert fixture.run.status == "running"
    events = list(
        fixture.db.scalars(
            select(ResearchEvent).where(ResearchEvent.run_id == fixture.run.id).order_by(ResearchEvent.seq)
        ).all()
    )
    assert [event.event_type for event in events] == ["run_status_changed", "step_started"]
    assert [event.seq for event in events] == [1, 2]


def test_claim_specific_matches_branch_and_rejects_wrong_branch(research_worker_db) -> None:
    fixture = research_worker_db
    researcher = add_step(
        fixture,
        step_key="research-branch-a",
        step_kind="researcher",
        branch_key="branch-a",
    )

    with pytest.raises(ResearchError) as error:
        claim_specific_research_step(
            fixture.db,
            run_id=fixture.run.id,
            step_key=researcher.step_key,
            branch_key="branch-b",
            worker_instance_id="worker-1",
            now=fixture.now,
        )
    assert_research_error(error, "research_resource_not_found", 404)
    fixture.db.rollback()

    lease = claim_specific_research_step(
        fixture.db,
        run_id=fixture.run.id,
        step_key=researcher.step_key,
        branch_key="branch-a",
        worker_instance_id="worker-1",
        now=fixture.now,
    )
    assert lease.step_id == researcher.id
    assert lease.branch_key == "branch-a"


def test_load_and_claim_reject_cross_run_execution_chains(research_worker_db) -> None:
    fixture = research_worker_db
    other_run, other_snapshot = add_execution_chain(fixture)
    other_run.approved_execution_snapshot_id = None
    fixture.db.commit()
    fixture.run.approved_execution_snapshot_id = other_snapshot.id
    fixture.db.commit()

    with pytest.raises(ResearchError):
        load_approved_execution(fixture.db, fixture.run.id)
    fixture.db.rollback()

    fixture.run.approved_execution_snapshot_id = fixture.snapshot.id
    fixture.step.execution_snapshot_id = other_snapshot.id
    fixture.db.commit()
    with pytest.raises(ResearchError):
        claim_specific_research_step(
            fixture.db,
            run_id=fixture.run.id,
            step_key=fixture.step.step_key,
            branch_key=fixture.step.branch_key,
            worker_instance_id="worker-1",
            now=fixture.now,
        )
    fixture.db.rollback()
    fixture.db.refresh(fixture.step)
    assert fixture.step.status == "queued"
    assert (
        fixture.db.scalar(
            select(ResearchStepAttempt).where(ResearchStepAttempt.step_id == fixture.step.id)
        )
        is None
    )


def test_wrong_token_and_expired_lease_cannot_heartbeat_or_complete(research_worker_db) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)

    with pytest.raises(ResearchError) as wrong_token:
        heartbeat_research_step(
            fixture.db,
            attempt_id=lease.attempt_id,
            lease_token="wrong-token",
            now=fixture.now + timedelta(seconds=1),
        )
    assert_research_error(wrong_token, "research_state_conflict", 409)
    fixture.db.rollback()

    with pytest.raises(ResearchError) as expired:
        complete_research_step(
            fixture.db,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            output_sha256=sha256("late-output"),
            now=lease.lease_expires_at,
        )
    assert_research_error(expired, "research_state_conflict", 409)
    fixture.db.rollback()
    fixture.db.refresh(fixture.step)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert fixture.step.status == "running"
    assert attempt is not None and attempt.status == "running"
    assert attempt.output_sha256 is None


def test_complete_step_commits_callback_state_status_and_event_together(research_worker_db) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    artifact_ids = [str(uuid4()), str(uuid4())]
    claim_id = str(uuid4())

    def persist_result(db: Session, run: ResearchRun, step: ResearchStep, _attempt: ResearchStepAttempt):
        db.add(
            ResearchClaim(
                id=claim_id,
                workspace_id=run.workspace_id,
                run_id=run.id,
                claim_key="claim-1",
                claim_order=0,
                statement_text="The evidence supports the conclusion.",
                statement_sha256=sha256("The evidence supports the conclusion."),
                produced_by_step_id=step.id,
                verification_status="pending",
                conflict_status="none",
                created_at=fixture.now + timedelta(seconds=1),
            )
        )
        return 2, artifact_ids

    complete_research_step(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        output_sha256=sha256("step-output"),
        complete=persist_result,
        now=fixture.now + timedelta(seconds=1),
    )

    fixture.db.expire_all()
    step = fixture.db.get(ResearchStep, fixture.step.id)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    event = fixture.db.scalar(
        select(ResearchEvent).where(
            ResearchEvent.run_id == fixture.run.id,
            ResearchEvent.event_type == "step_succeeded",
        )
    )
    assert fixture.db.get(ResearchClaim, claim_id) is not None
    assert step is not None and step.status == "succeeded"
    assert attempt is not None and attempt.status == "succeeded"
    assert attempt.output_sha256 == sha256("step-output")
    assert attempt.lease_expires_at is None
    assert event is not None
    assert event.payload_json["evidenceCount"] == 2
    assert event.payload_json["artifactIds"] == artifact_ids


def test_complete_step_callback_failure_does_not_commit_partial_state(research_worker_db) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    claim_id = str(uuid4())

    def fail_after_write(db: Session, run: ResearchRun, step: ResearchStep, _attempt: ResearchStepAttempt):
        db.add(
            ResearchClaim(
                id=claim_id,
                workspace_id=run.workspace_id,
                run_id=run.id,
                claim_key="partial-claim",
                claim_order=0,
                statement_text="This write must roll back.",
                statement_sha256=sha256("This write must roll back."),
                produced_by_step_id=step.id,
                verification_status="pending",
                conflict_status="none",
                created_at=fixture.now + timedelta(seconds=1),
            )
        )
        raise RuntimeError("callback failed")

    with pytest.raises(RuntimeError, match="callback failed"):
        complete_research_step(
            fixture.db,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            output_sha256=sha256("uncommitted-output"),
            complete=fail_after_write,
            now=fixture.now + timedelta(seconds=1),
        )
    fixture.db.rollback()

    fixture.db.expire_all()
    step = fixture.db.get(ResearchStep, fixture.step.id)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert fixture.db.get(ResearchClaim, claim_id) is None
    assert step is not None and step.status == "running"
    assert attempt is not None and attempt.status == "running"
    assert attempt.output_sha256 is None
    assert (
        fixture.db.scalar(
            select(ResearchEvent).where(
                ResearchEvent.run_id == fixture.run.id,
                ResearchEvent.event_type == "step_succeeded",
            )
        )
        is None
    )


def test_publish_plan_commits_artifact_approval_gate_and_events_without_execution_dag(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    _revision, planner, _planning_ledger = make_planning_chain(fixture)
    lease = lease_planner_step(fixture, planner)
    stored: dict[str, tuple[bytes, str]] = {}

    result = publish_research_plan(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        summary="Compare the frozen source.",
        subproblems=(
            PlanSubproblemDraft(
                question="What does the source establish?",
                asset_ids=(fixture.asset.id,),
                expected_evidence=("Direct statement",),
            ),
        ),
        known_gaps=("No independent corroboration",),
        estimated_provider_calls=4,
        estimated_input_tokens=500,
        estimated_output_tokens=250,
        store_bytes=lambda key, content, content_type: stored.__setitem__(
            key, (content, content_type)
        ),
        now=fixture.now + timedelta(seconds=1),
    )

    fixture.db.expire_all()
    artifact = fixture.db.get(ResearchArtifact, result["artifactId"])
    decision = fixture.db.get(HumanDecision, result["decisionId"])
    assert artifact is not None and artifact.artifact_kind == "research_plan"
    assert decision is not None and decision.status == "pending"
    assert decision.input_artifact_id == artifact.id
    assert decision.input_artifact_sha256 == artifact.content_sha256
    gate = fixture.db.get(ResearchStep, decision.gate_step_id)
    assert gate is not None and gate.status == "waiting"
    assert gate.step_kind == "plan_approval_gate"
    assert gate.plan_revision_id == planner.plan_revision_id
    assert list(stored) == [artifact.object_key]
    artifact_bytes, content_type = stored[artifact.object_key]
    assert content_type == "application/json"
    assert hashlib.sha256(artifact_bytes).hexdigest() == artifact.content_sha256
    payload = json.loads(artifact_bytes)
    assert payload["summary"] == "Compare the frozen source."
    assert payload["subproblems"] == result["subproblems"]
    assert payload["subproblems"][0]["assetIds"] == [fixture.asset.id]

    steps = list(
        fixture.db.scalars(
            select(ResearchStep).where(ResearchStep.run_id == fixture.run.id).order_by(ResearchStep.created_at)
        ).all()
    )
    assert [step.step_kind for step in steps] == ["planner", "plan_approval_gate"]
    events = list(
        fixture.db.scalars(
            select(ResearchEvent).where(ResearchEvent.run_id == fixture.run.id).order_by(ResearchEvent.seq)
        ).all()
    )
    assert [event.event_type for event in events] == [
        "run_status_changed",
        "step_started",
        "step_succeeded",
        "artifact_published",
        "step_waiting",
        "approval_requested",
        "run_status_changed",
    ]
    run = fixture.db.get(ResearchRun, fixture.run.id)
    assert run is not None and run.status == "awaiting_plan_approval"


def test_worker_claims_leave_a_malformed_queued_plan_gate_unchanged(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    _revision, planner, _planning_ledger = make_planning_chain(fixture)
    planner_lease = lease_planner_step(fixture, planner)
    stored: dict[str, bytes] = {}
    result = publish_research_plan(
        fixture.db,
        attempt_id=planner_lease.attempt_id,
        lease_token=planner_lease.lease_token,
        summary="Human-owned gate claim probe.",
        subproblems=(
            PlanSubproblemDraft(
                question="What does the source establish?",
                asset_ids=(fixture.asset.id,),
            ),
        ),
        estimated_provider_calls=2,
        store_bytes=lambda key, content, _content_type: stored.__setitem__(key, content),
        now=fixture.now + timedelta(seconds=1),
    )
    decision = fixture.db.get(HumanDecision, result["decisionId"])
    assert decision is not None
    gate = fixture.db.get(ResearchStep, decision.gate_step_id)
    run = fixture.db.get(ResearchRun, fixture.run.id)
    assert gate is not None and run is not None

    # Model a corrupted queue transition without granting the Worker authority over the gate.
    gate.status = "queued"
    gate.queued_at = fixture.now + timedelta(seconds=2)
    run.status = "queued"
    fixture.db.commit()

    def row_snapshot(row: object) -> tuple[tuple[str, object], ...]:
        table = getattr(row, "__table__")
        return tuple((column.name, getattr(row, column.name)) for column in table.columns)

    fixture.db.refresh(run)
    fixture.db.refresh(gate)
    fixture.db.refresh(decision)
    before = {
        "run": row_snapshot(run),
        "gate": row_snapshot(gate),
        "decision": row_snapshot(decision),
        "attempts": len(
            fixture.db.scalars(
                select(ResearchStepAttempt).where(ResearchStepAttempt.step_id == gate.id)
            ).all()
        ),
        "events": len(
            fixture.db.scalars(
                select(ResearchEvent).where(ResearchEvent.run_id == run.id)
            ).all()
        ),
    }

    assert (
        claim_next_research_step(
            fixture.db,
            worker_instance_id="human-gate-probe",
            now=fixture.now + timedelta(seconds=3),
        )
        is None
    )
    with pytest.raises(ResearchError) as error:
        claim_specific_research_step(
            fixture.db,
            run_id=run.id,
            step_key=gate.step_key,
            branch_key=None,
            worker_instance_id="human-gate-specific-probe",
            now=fixture.now + timedelta(seconds=3),
        )
    assert_research_error(error, "research_state_conflict", 409)

    fixture.db.expire_all()
    persisted_run = fixture.db.get(ResearchRun, run.id)
    persisted_gate = fixture.db.get(ResearchStep, gate.id)
    persisted_decision = fixture.db.get(HumanDecision, decision.id)
    assert persisted_run is not None and persisted_gate is not None and persisted_decision is not None
    after = {
        "run": row_snapshot(persisted_run),
        "gate": row_snapshot(persisted_gate),
        "decision": row_snapshot(persisted_decision),
        "attempts": len(
            fixture.db.scalars(
                select(ResearchStepAttempt).where(ResearchStepAttempt.step_id == gate.id)
            ).all()
        ),
        "events": len(
            fixture.db.scalars(
                select(ResearchEvent).where(ResearchEvent.run_id == run.id)
            ).all()
        ),
    }
    assert after == before


def test_publish_plan_rolls_back_ledger_and_cleans_bytes_when_event_write_fails(
    research_worker_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = research_worker_db
    _revision, planner, _planning_ledger = make_planning_chain(fixture)
    lease = lease_planner_step(fixture, planner)
    stored_keys: list[str] = []
    cleaned_keys: list[str] = []

    def fail_event(*_args, **_kwargs):
        raise RuntimeError("event write failed")

    monkeypatch.setattr(research_worker_plan, "append_research_event", fail_event)
    with pytest.raises(RuntimeError, match="event write failed"):
        publish_research_plan(
            fixture.db,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            summary="Plan that must roll back.",
            subproblems=(
                PlanSubproblemDraft(
                    question="What does the source establish?",
                    asset_ids=(fixture.asset.id,),
                ),
            ),
            estimated_provider_calls=1,
            store_bytes=lambda key, _content, _content_type: stored_keys.append(key),
            cleanup_bytes=cleaned_keys.append,
            now=fixture.now + timedelta(seconds=1),
        )

    fixture.db.expire_all()
    assert cleaned_keys == stored_keys
    assert len(cleaned_keys) == 1
    assert fixture.db.scalar(select(ResearchArtifact).where(ResearchArtifact.run_id == fixture.run.id)) is None
    assert fixture.db.scalar(select(HumanDecision).where(HumanDecision.run_id == fixture.run.id)) is None
    assert (
        fixture.db.scalar(
            select(ResearchStep).where(
                ResearchStep.run_id == fixture.run.id,
                ResearchStep.step_kind == "plan_approval_gate",
            )
        )
        is None
    )
    persisted_planner = fixture.db.get(ResearchStep, planner.id)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert persisted_planner is not None and persisted_planner.status == "running"
    assert attempt is not None and attempt.status == "running"
