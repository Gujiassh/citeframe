"""Exercise the deployment journal projection with real persisted models."""
from contextlib import nullcontext
import json
from uuid import uuid4

import pytest
from sqlalchemy import select
from citeframe_persistence.models import ResearchConflictTurn, ResearchStep, ResearchStepAttempt, ResearchExecutionSnapshot, ResearchRun, Workspace
from citeframe_evaluation.acceptance.evidence import execution_facts, row
from citeframe_evaluation.acceptance.conflicts import assert_fixture_investigation, assert_role_step
from research_worker_test_support import research_worker_db, research_schema_db
from test_research_conflict_publication import test_v4_journal_survives_final_publication_adoption as publish_fixture


def observe(f):
    return execution_facts(lambda: nullcontext(f.db), f.run.id)


def test_actual_model_projection_without_journal(research_worker_db):
    facts = observe(research_worker_db)
    assert facts["conflictTurns"] == []
    assert_fixture_investigation(facts, required=False)


def test_actual_v4_journal_retains_raw_columns_and_checked_role(research_worker_db):
    f = research_worker_db
    publish_fixture(f, False, False)
    facts = observe(f)
    turns = assert_fixture_investigation(facts, required=True)
    persisted = list(f.db.scalars(select(ResearchConflictTurn).order_by(ResearchConflictTurn.operation_number)))
    assert turns == [row(t) for t in persisted]
    assert all(set(t) == set(ResearchConflictTurn.__table__.columns.keys()) for t in turns)
    step = next(s for s in facts["steps"] if s["id"] == turns[0]["step_id"])
    attempt = next(a for a in facts["attempts"] if a["id"] == turns[0]["created_by_attempt_id"])
    body = {"input": [{"role": "user", "content": json.dumps({"investigation": turns[0]["request_json"]})}]}
    assert_role_step(facts, step, attempt, "investigator", body)


def clone(db, value, **changes):
    item = type(value)(**{c.key: getattr(value, c.key) for c in value.__table__.columns})
    item.id = str(uuid4())
    for key, value in changes.items():
        setattr(item, key, value)
    db.add(item)
    db.flush()
    return item


@pytest.mark.parametrize("mutation", ["step_run", "step_workspace", "snapshot_run", "snapshot_workspace", "turn_snapshot", "turn_attempt", "attempt_workspace", "attempt_input"])
def test_actual_journal_rejects_foreign_relations(research_worker_db, mutation):
    f = research_worker_db
    publish_fixture(f, False, False)
    assert_fixture_investigation(observe(f), required=True)
    turn = f.db.scalar(select(ResearchConflictTurn).where(ResearchConflictTurn.phase == "inspect"))
    step = f.db.get(ResearchStep, turn.step_id)
    snapshot = f.db.get(ResearchExecutionSnapshot, turn.execution_snapshot_id)
    attempt = f.db.get(ResearchStepAttempt, turn.created_by_attempt_id)
    if mutation.endswith("_run"):
        foreign = clone(f.db, f.run, approved_execution_snapshot_id=None, current_plan_revision_id=None)
        (step if mutation == "step_run" else snapshot).run_id = foreign.id
    elif mutation.endswith("_workspace"):
        workspace = clone(f.db, f.db.get(Workspace, f.run.workspace_id))
        target = {"step_workspace": step, "snapshot_workspace": snapshot, "attempt_workspace": attempt}[mutation]
        target.workspace_id = workspace.id
    elif mutation == "turn_snapshot":
        turn.execution_snapshot_id = str(uuid4())
    elif mutation == "turn_attempt":
        other = f.db.scalar(select(ResearchStepAttempt).where(ResearchStepAttempt.step_id != step.id))
        assert other is not None
        turn.created_by_attempt_id = other.id
    else:
        attempt.input_sha256 = "0" * 64
    f.db.commit()
    with pytest.raises(AssertionError):
        assert_fixture_investigation(observe(f), required=True)
