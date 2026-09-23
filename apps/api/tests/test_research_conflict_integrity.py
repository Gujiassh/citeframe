from datetime import timedelta
from uuid import uuid4

import pytest
from citeframe_persistence.models import (
    ResearchConflictTurn,
    ResearchStepAttempt,
)
from citeframe_research_persistence.conflict_investigation import (
    conflict_turn,
    investigation_details,
    investigation_outcome,
    investigation_view,
)
from citeframe_research_persistence.errors import ResearchError, canonical_sha256
from research_worker_test_support import add_step, sha256
from sqlalchemy import select
from test_research_conflict_investigation import call, gate
from test_research_conflict_publication import (
    test_v4_journal_survives_final_publication_adoption as publish_fixture,
)


@pytest.mark.parametrize(
    "mutation",
    [
        "foreign_step",
        "wrong_origin_input",
        "wrong_current_input",
        "workspace",
        "future",
    ],
)
def test_journal_rejects_invalid_attempt_lineage(research_worker_db, mutation):
    f = research_worker_db
    lease = gate(f)
    call(f, lease)
    call(f, lease, result={"inspected": True})
    f.db.commit()
    row = f.db.get(ResearchConflictTurn, (f.step.id, 0))
    current = f.db.get(ResearchStepAttempt, lease.attempt_id)
    origin = current
    origin.status, origin.finished_at = "failed", f.now
    successor = ResearchStepAttempt(
        id=str(uuid4()),
        workspace_id=f.step.workspace_id,
        step_id=f.step.id,
        attempt_number=2,
        status="running",
        input_sha256=origin.input_sha256,
        started_at=f.now,
        lease_token_hash=sha256("restarted"),
        lease_expires_at=f.now + timedelta(seconds=60),
    )
    f.db.add(successor)
    f.step.current_attempt_number = 2
    from dataclasses import replace

    lease = replace(
        lease, attempt_id=successor.id, lease_token="restarted", attempt_number=2
    )
    if mutation == "wrong_current_input":
        successor.input_sha256 = sha256("changed")
    elif mutation == "wrong_origin_input":
        origin.input_sha256 = sha256("changed")
    elif mutation == "workspace":
        origin.workspace_id = str(uuid4())
    elif mutation == "future":
        future = ResearchStepAttempt(
            id=str(uuid4()),
            workspace_id=f.step.workspace_id,
            step_id=f.step.id,
            attempt_number=3,
            status="failed",
            input_sha256=origin.input_sha256,
            started_at=f.now,
            finished_at=f.now,
        )
        f.db.add(future)
        row.created_by_attempt_id = future.id
    else:
        other = add_step(
            f, step_key="foreign", step_kind="researcher", branch_key="foreign"
        )
        origin.step_id = other.id
    f.db.commit()
    with pytest.raises(ResearchError):
        call(f, lease)
    f.db.rollback()
    with pytest.raises(ResearchError):
        investigation_details(f.db, f.run.id)


@pytest.mark.parametrize("status", ["failed", "timed_out", "abandoned"])
@pytest.mark.parametrize("nullable", [False, True])
def test_completed_journal_replays_from_legal_prior_attempt(
    research_worker_db, status, nullable
):
    f = research_worker_db
    if nullable:
        f.step.input_sha256 = None
        f.db.commit()
    lease = gate(f)
    call(f, lease)
    call(f, lease, result={"inspected": True})
    origin = f.db.get(ResearchStepAttempt, lease.attempt_id)
    origin.status, origin.finished_at = status, f.now
    current = ResearchStepAttempt(
        id=str(uuid4()),
        workspace_id=f.step.workspace_id,
        step_id=f.step.id,
        attempt_number=2,
        status="running",
        input_sha256=origin.input_sha256,
        started_at=f.now,
        lease_token_hash=sha256("restarted"),
        lease_expires_at=f.now + timedelta(seconds=60),
    )
    f.db.add(current)
    f.step.current_attempt_number = 2
    f.db.commit()
    result = conflict_turn(
        f.db,
        attempt_id=current.id,
        lease_token="restarted",
        operation_number=0,
        phase="inspect",
        request={"sources": []},
        now=f.now,
    )
    assert result == {"status": "succeeded", "result": {"inspected": True}}
    assert investigation_details(f.db, f.run.id)[0]["attemptId"] == origin.id


@pytest.mark.parametrize("mutation", ["omit_fact", "replace_fact", "foreign_origin"])
def test_final_outcome_and_api_view_reject_combined_review_tampering(
    research_worker_db, mutation
):
    f = research_worker_db
    publish_fixture(f, True, False)
    row = f.db.scalar(
        select(ResearchConflictTurn).where(ResearchConflictTurn.phase == "critic")
    )
    assert len(row.request_json["claims"]) == 2
    if mutation == "foreign_origin":
        foreign = f.db.scalar(
            select(ResearchStepAttempt).where(
                ResearchStepAttempt.step_id != row.step_id
            )
        )
        row.created_by_attempt_id = foreign.id
    else:
        claims = list(row.request_json["claims"])
        if mutation == "omit_fact":
            claims.pop(0)
        else:
            claims[0] = {**claims[0], "text": "Substituted fact"}
        row.request_json = {"claims": claims}
        row.request_sha256 = canonical_sha256(row.request_json)
    f.db.commit()
    with pytest.raises(ResearchError):
        investigation_outcome(f.db, f.run.id)
    with pytest.raises(ResearchError):
        investigation_view(f.db, f.run.id, "completed")
