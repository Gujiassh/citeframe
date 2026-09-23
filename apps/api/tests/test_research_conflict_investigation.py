from datetime import UTC, datetime
from sqlalchemy import select, func
from sqlalchemy.orm import Session
import pytest
from citeframe_persistence.models import ResearchConflictTurn, ResearchClaim, WorkspaceMembership
from citeframe_research_persistence.conflict_investigation import conflict_turn, investigation_view
from citeframe_research_persistence.conflict_policy import INVESTIGATION_WORKFLOW_ID
from citeframe_research_persistence.errors import ResearchError
from research_worker_test_support import lease_default_step


def gate(f):
    f.snapshot.workflow_version_id=INVESTIGATION_WORKFLOW_ID
    f.step.step_kind="conflict_decision_gate";f.step.step_key="conflict_decision_gate";f.step.branch_key=None
    f.db.commit();return lease_default_step(f)


def call(f,lease,number=0,phase="inspect",request=None,result=None):
    return conflict_turn(f.db,attempt_id=lease.attempt_id,lease_token=lease.lease_token,
        operation_number=number,phase=phase,request=request or {"sources":[]},result=result,now=f.now)


def test_operation_survives_new_session_and_replays_without_duplicate(research_worker_db):
    f=research_worker_db;lease=gate(f)
    assert call(f,lease)["status"]=="reserved"
    assert call(f,lease,result={"inspected":True})["status"]=="succeeded"
    f.db.commit()
    with Session(f.db.get_bind()) as db:
        result=conflict_turn(db,attempt_id=lease.attempt_id,lease_token=lease.lease_token,
            operation_number=0,phase="inspect",request={"sources":[]},now=f.now)
        assert result=={"status":"succeeded","result":{"inspected":True}}
        assert db.scalar(select(func.count()).select_from(ResearchConflictTurn))==1


def test_ambiguous_operation_does_not_reserve_another_call(research_worker_db):
    f=research_worker_db;lease=gate(f);call(f,lease);f.db.commit()
    assert call(f,lease)["status"]=="outcome_unknown"
    assert f.db.scalar(select(func.count()).select_from(ResearchConflictTurn))==1


def test_changed_replay_and_out_of_order_rejected(research_worker_db):
    f=research_worker_db;lease=gate(f);call(f,lease);f.db.commit()
    with pytest.raises(ResearchError):call(f,lease,request={"sources":["forged"]})
    f.db.rollback()
    with pytest.raises(ResearchError):call(f,lease,number=1)


@pytest.mark.parametrize("mutation",["cancel","permission","lease","legacy"])
def test_guards_prevent_checkpoint_writes(research_worker_db,mutation):
    f=research_worker_db;lease=gate(f)
    if mutation=="cancel":
        f.run.status="cancel_requested";f.run.cancel_requested_by_user_id=f.run.created_by_user_id
        f.run.cancel_requested_at=f.now;f.run.cancel_reason_code="user_requested"
    elif mutation=="permission":
        for row in f.db.scalars(select(WorkspaceMembership)):f.db.delete(row)
    elif mutation=="legacy":f.snapshot.workflow_version_id="30000000-0000-4000-8000-000000000001"
    else:
        from dataclasses import replace
        lease=replace(lease,lease_token="invalid")
    f.db.commit()
    with pytest.raises(ResearchError):call(f,lease)
    f.db.rollback()
    assert f.db.scalar(select(func.count()).select_from(ResearchConflictTurn))==0


def test_duplicate_queries_and_round_bounds_are_persisted(research_worker_db):
    f=research_worker_db;lease=gate(f)
    call(f,lease,phase="search",request={"query":"same query"})
    call(f,lease,phase="search",request={"query":"same query"},result={"evidence":[]});f.db.commit()
    with pytest.raises(ResearchError):call(f,lease,number=1,phase="search",request={"query":" SAME   QUERY "})
    with pytest.raises(ResearchError):call(f,lease,number=13)


def test_status_change_alone_cannot_resolve(research_worker_db):
    f=research_worker_db;lease=gate(f)
    call(f,lease,phase="finish",request={"conflictClaimIds":[]})
    with pytest.raises(ResearchError,match="verification"):
        call(f,lease,phase="finish",request={"conflictClaimIds":[]},result={"resolved":True,"originalClaims":[],"revisions":[]})
