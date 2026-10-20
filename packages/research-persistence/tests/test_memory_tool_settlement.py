"""Real PostgreSQL old/new transaction oracles for the bounded settlement extraction.

Set CITEFRAME_ISSUE45_POSTGRES_URL to a loopback PostgreSQL database named
citeframe_issue45_settlement_test. Each test creates/drops its own schema using
unchanged native ORM tables, with all their foreign keys/checks enabled. This
suite does not establish migration, activation or shared-memory authority.
"""
from __future__ import annotations

import ast
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import hashlib
import inspect
import os
import re
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from sqlalchemy import DateTime, Integer, JSON, create_engine, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from citeframe_persistence.base import Base
from citeframe_persistence.models import (
    HumanDecision, PromptVersion, ResearchArtifact, ResearchBudgetLedger,
    ResearchExecutionSnapshot, ResearchPlanRevision, ResearchRun, ResearchStep,
    ResearchStepAttempt, ResearchToolCall, User, WorkflowVersion, Workspace,
)
from citeframe_research_persistence import tools
from citeframe_research_persistence.errors import ResearchError

NOW = datetime(2026, 9, 29, 0, 0, tzinfo=UTC)
SETTLED_AT = NOW + timedelta(seconds=17)
SHA = "a" * 64
LOCK_ORDER = ["research_runs", "research_steps", "research_step_attempts",
              "research_tool_calls", "research_budget_ledgers"]
OBSERVED = (ResearchToolCall, ResearchBudgetLedger, ResearchStepAttempt, ResearchArtifact, Workspace)

# Frozen directly from e7b3e86ae4de70764c4d17bcbe272686c1c8063a tools.py.
# Captured verbatim; the digest pins the independent pre-extraction oracle.
OLD_SOURCE = '''def complete_tool_call(
    db: Session,
    *,
    tool_call_id: str,
    status: str,
    complete: ToolResultCallback | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    now: datetime | None = None,
) -> None:
    if status not in {"succeeded", "failed", "cancelled", "abandoned"}:
        raise ValueError("invalid tool terminal status")
    call, ledger, attempt, _step, _run = _tool_call_chain(db, tool_call_id)
    if call.status not in {"requested", "running"}:
        raise ResearchError("research_state_conflict", "Research tool call cannot be completed.", 409)
    try:
        result_count = complete(db, call) if complete else 0
        call.status = status
        call.result_count = result_count
        call.error_code = error_code
        call.error_message = error_message
        call.finished_at = now or datetime.now(UTC)
        ledger.reserved_tool_calls -= 1
        ledger.actual_tool_calls += 1
        ledger.state_version += 1
        ledger.updated_at = call.finished_at
        attempt.tool_call_count += 1
        db.flush()
    except Exception:
        db.rollback()
        raise'''
OLD_SOURCE_SHA256 = 'f49a52e33fac8efa83a37db45b9c037f4a8549b8947b9be15c3e8fc45d4e12f7'


def old_public():
    assert hashlib.sha256(OLD_SOURCE.encode()).hexdigest() == OLD_SOURCE_SHA256
    namespace = dict(vars(tools))
    exec(compile(OLD_SOURCE, "<e7b3e86 complete_tool_call>", "exec"), namespace)
    return namespace["complete_tool_call"]


class ObservedSession(Session):
    """Count explicit owner commands separately from DBAPI constraint aborts."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0

    def commit(self):
        self.commits += 1
        return super().commit()

    def rollback(self):
        self.rollbacks += 1
        return super().rollback()

    def flush(self, objects=None):
        self.flushes += 1
        return super().flush(objects)


def uid(key):
    return str(uuid5(NAMESPACE_URL, "citeframe-issue45-settlement/" + key))


def dependency_tables():
    tables = set()

    def add(table):
        if table in tables:
            return
        tables.add(table)
        for fk in table.foreign_keys:
            add(fk.column.table)

    for cls in (*OBSERVED, ResearchExecutionSnapshot):
        add(cls.__table__)
    return sorted(tables, key=lambda table: table.name)


def seed(conn):
    # Required, unrelated snapshot policy columns get explicit synthetic defaults;
    # every FK points to a real row, and native CHECK constraints stay enabled.
    def insert(cls, **overrides):
        table = cls.__table__
        values = {"id": uid(table.name)}
        for col in table.columns:
            if col.name in values or col.nullable or col.default is not None or col.server_default is not None:
                continue
            if col.foreign_keys:
                values[col.name] = uid(next(iter(col.foreign_keys)).column.table.name)
            elif isinstance(col.type, DateTime):
                values[col.name] = NOW
            elif isinstance(col.type, Integer):
                values[col.name] = 10
            elif isinstance(col.type, JSON):
                values[col.name] = {}
            else:
                values[col.name] = SHA if "sha256" in col.name else "synthetic"
        values.update(overrides)
        conn.execute(table.insert().values(**values))

    insert(User, email="settlement@example.invalid")
    insert(Workspace)
    insert(Workspace, id=uid("foreign_workspace"))
    insert(WorkflowVersion, availability="active", created_by_user_id=uid("users"))
    insert(PromptVersion, step_kind="planner", availability="active", created_by_user_id=uid("users"))
    insert(ResearchRun, status="running", cost_currency="USD")
    insert(ResearchPlanRevision, scope_mode="selected", planning_cost_currency="USD", proposed_cost_currency="USD")
    insert(ResearchStep, step_kind="planner", status="succeeded", step_key="planner",
           plan_revision_id=uid("research_plan_revisions"))
    insert(ResearchStepAttempt, attempt_number=1, status="succeeded")
    insert(ResearchArtifact, artifact_kind="research_plan", visibility="user",
           retention_class="workspace_lifetime", logical_key="plan", object_key="synthetic/plan")
    insert(ResearchStep, id=uid("plan_gate"), step_kind="plan_approval_gate", step_key="plan_gate",
           status="succeeded", plan_revision_id=uid("research_plan_revisions"))
    insert(HumanDecision, gate_step_id=uid("plan_gate"), decision_origin="human", decision_type="plan_approval",
           status="submitted", action="approve", decided_by_user_id=uid("users"), decided_at=NOW)
    insert(ResearchExecutionSnapshot, scope_mode="selected", cost_currency="USD")
    insert(ResearchStep, id=uid("step"), execution_snapshot_id=uid("research_execution_snapshots"),
           step_kind="researcher", step_key="researcher:branch", branch_key="branch", status="running",
           current_attempt_number=1)
    insert(ResearchStepAttempt, id=uid("attempt"), step_id=uid("step"), attempt_number=1,
           status="running", tool_call_count=4, provider_call_count=2, input_tokens=23, output_tokens=31,
           cost_microunits=19)
    insert(ResearchBudgetLedger, execution_snapshot_id=uid("research_execution_snapshots"),
           currency="USD", reserved_tool_calls=1, actual_tool_calls=4, state_version=7,
           reserved_provider_calls=2, actual_provider_calls=3, reserved_input_tokens=11,
           reserved_output_tokens=13, actual_input_tokens=17, actual_output_tokens=19,
           reserved_cost_microunits=23, actual_cost_microunits=29)
    insert(ResearchToolCall, step_id=uid("step"), attempt_id=uid("attempt"),
           tool_name="evidence.search", tool_call_key="search:0", call_attempt_number=1,
           call_order=0, status="running", started_at=NOW)


@pytest.fixture
def pg():
    url = os.environ.get("CITEFRAME_ISSUE45_POSTGRES_URL")
    if not url:
        pytest.fail("CITEFRAME_ISSUE45_POSTGRES_URL is required; real PostgreSQL settlement tests cannot skip")
    parsed = make_url(url)
    assert parsed.drivername.startswith("postgresql")
    assert parsed.host in {"127.0.0.1", "localhost", "::1"}
    assert parsed.database == "citeframe_issue45_settlement_test", "Refusing a non-test database"
    schema = "settlement45_" + uuid4().hex
    admin = create_engine(url)
    engine = None
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        engine = create_engine(url, connect_args={"options":
            f"-c search_path={schema},public -c lock_timeout=4000 -c statement_timeout=10000"})
        with engine.begin() as conn:
            Base.metadata.create_all(conn, tables=dependency_tables())
            seed(conn)
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def snapshot(connection):
    return {cls.__tablename__: [dict(row) for row in connection.execute(
        select(cls.__table__).order_by(cls.__table__.c.id)).mappings()] for cls in OBSERVED}


def committed_snapshot(engine):
    with engine.connect() as conn:
        return snapshot(conn)


def row_from(state, cls, id_):
    return next(row for row in state[cls.__tablename__] if row["id"] == uid(id_))


def write_result(db, call):
    assert call.status in {"requested", "running"}
    db.add(ResearchArtifact(
        id=uid("result"), workspace_id=call.workspace_id, run_id=call.run_id,
        generated_by_step_id=call.step_id, generated_by_attempt_id=call.attempt_id,
        artifact_kind="evidence_bundle", visibility="internal", logical_key="tool-result",
        schema_version="1", object_key="synthetic/result", content_type="application/json",
        byte_size=3, content_sha256=SHA, workflow_version_id=uid("workflow_versions"),
        retention_class="workspace_lifetime", created_at=NOW,
    ))


@contextmanager
def observe(engine, db):
    trace = []

    def sql(conn, cursor, statement, parameters, context, executemany):
        if conn is db.connection():
            match = re.search(r"FOR UPDATE OF (\w+)", statement)
            if match:
                trace.append(("lock", match.group(1)))

    def flush(session, context, instances):
        trace.append(("flush",))

    event.listen(engine, "before_cursor_execute", sql)
    event.listen(db, "before_flush", flush)
    try:
        yield trace
    finally:
        event.remove(engine, "before_cursor_execute", sql)
        event.remove(db, "before_flush", flush)


def invoke(fn, db, **overrides):
    args = dict(tool_call_id=uid("research_tool_calls"), status="succeeded", now=SETTLED_AT,
                error_code="synthetic_code", error_message="synthetic message")
    args.update(overrides)
    return fn(db, **args)


def test_frozen_baseline_and_entry_signature():
    chain = ast.parse(inspect.getsource(tools._tool_call_chain)).body[0]
    assert hashlib.sha256(ast.dump(chain, include_attributes=False).encode()).hexdigest() == (
        "06cf0714e66fa903f5e1c0af02e3b41335bd762a7f69bc0a6bda930bcd1b1534"
    )
    old = old_public()
    assert inspect.signature(old) == inspect.signature(tools.complete_tool_call)
    assert inspect.signature(old) == inspect.signature(tools._complete_tool_call_in_transaction)
    original = ast.parse(OLD_SOURCE).body[0]
    old_body = next(node for node in original.body if isinstance(node, ast.Try)).body
    extracted = ast.parse(inspect.getsource(tools._settle_tool_call)).body[0].body[1:]
    assert ast.dump(ast.Module(body=old_body, type_ignores=[]), include_attributes=False) == ast.dump(
        ast.Module(body=extracted, type_ignores=[]), include_attributes=False)
    assert "rollback" not in inspect.getsource(tools._complete_tool_call_in_transaction).split('"""')[-1]


@pytest.mark.parametrize("status", ["succeeded", "failed", "cancelled", "abandoned"])
@pytest.mark.parametrize("count", [None, 0, 3])
@pytest.mark.parametrize("initial", ["requested", "running"])
def test_pg_old_new_exact_payload_locks_flush_and_outer_rollback(pg, status, count, initial):
    with pg.begin() as conn:
        conn.execute(ResearchToolCall.__table__.update().values(status=initial))
    baseline = committed_snapshot(pg)
    observations = []
    for fn in (old_public(), tools.complete_tool_call, tools._complete_tool_call_in_transaction):
        with ObservedSession(pg, autoflush=False) as db:
            with observe(pg, db) as trace:
                def complete(session, call):
                    trace.append(("callback", call.status))
                    write_result(session, call)
                    return count
                invoke(fn, db, status=status, complete=complete if count is not None else None)
                assert (db.commits, db.rollbacks, db.flushes) == (0, 0, 1)
                state = snapshot(db.connection())
                observations.append((state, list(trace)))
            assert committed_snapshot(pg) == baseline
            db.rollback()
        assert committed_snapshot(pg) == baseline
    assert observations[0] == observations[1] == observations[2]
    state, trace = observations[0]
    assert [entry[1] for entry in trace if entry[0] == "lock"] == LOCK_ORDER
    assert trace[-1] == ("flush",)
    if count is not None:
        assert trace[-2] == ("callback", initial)
    expected_call = {**row_from(baseline, ResearchToolCall, "research_tool_calls"),
                     "status": status, "result_count": count or 0, "error_code": "synthetic_code",
                     "error_message": "synthetic message", "finished_at": SETTLED_AT}
    assert row_from(state, ResearchToolCall, "research_tool_calls") == expected_call
    expected_ledger = {**row_from(baseline, ResearchBudgetLedger, "research_budget_ledgers"),
                       "reserved_tool_calls": 0, "actual_tool_calls": 5, "state_version": 8, "updated_at": SETTLED_AT}
    assert row_from(state, ResearchBudgetLedger, "research_budget_ledgers") == expected_ledger
    expected_attempt = {**row_from(baseline, ResearchStepAttempt, "attempt"), "tool_call_count": 5}
    assert row_from(state, ResearchStepAttempt, "attempt") == expected_attempt
    assert len(state[ResearchArtifact.__tablename__]) == 1 + (count is not None)


@pytest.mark.parametrize("fn_name", ["old", "public", "inner"])
@pytest.mark.parametrize("case", ["invalid_status", "invalid_status_terminal", "missing_chain",
                                  "foreign_chain", "foreign_terminal", "already_terminal"])
def test_pg_precondition_precedence_preserves_outer_transaction(pg, fn_name, case):
    fn = {"old": old_public(), "public": tools.complete_tool_call,
          "inner": tools._complete_tool_call_in_transaction}[fn_name]
    if case in {"foreign_chain", "foreign_terminal", "already_terminal", "invalid_status_terminal"}:
        with pg.begin() as conn:
            conn.execute(ResearchToolCall.__table__.update().values(
                **({"workspace_id": uid("foreign_workspace"), "status": "succeeded" if case == "foreign_terminal" else "running"}
                   if case.startswith("foreign") else {"status": "succeeded"})))
    baseline = committed_snapshot(pg)
    with ObservedSession(pg, autoflush=False) as db:
        db.execute(Workspace.__table__.update().where(Workspace.id == uid("workspaces")).values(description="outer write"))
        def forbidden(*args):
            pytest.fail("callback ran before precondition rejection")
        args = {"complete": forbidden}
        if case in {"invalid_status", "missing_chain"}:
            args["tool_call_id"] = uid("missing")
        if case.startswith("invalid_status"):
            args["status"] = "outcome_unknown"
        with observe(pg, db) as trace, pytest.raises((ValueError, ResearchError)) as exc:
            invoke(fn, db, **args)
        if case.startswith("invalid_status"):
            assert type(exc.value) is ValueError
            assert str(exc.value) == "invalid tool terminal status"
            assert trace == []
        else:
            assert type(exc.value) is ResearchError
            assert exc.value.code == "research_state_conflict"
            assert exc.value.message == ("Research tool call cannot be completed." if case == "already_terminal"
                                         else "Research tool call chain is invalid.")
        assert (db.commits, db.rollbacks, db.flushes) == (0, 0, 0)
        assert db.in_transaction() and db.is_active
        assert db.scalar(select(Workspace.description).where(Workspace.id == uid("workspaces"))) == "outer write"
        assert committed_snapshot(pg) == baseline
        db.rollback()
    assert committed_snapshot(pg) == baseline


@pytest.mark.parametrize("failure", ["callback", "flush", "callback_flush"])
def test_pg_old_new_failure_rollback_boundary_and_inner_owner_control(pg, failure):
    if failure == "flush":
        with pg.begin() as conn:
            conn.execute(ResearchBudgetLedger.__table__.update().values(reserved_tool_calls=0))
    baseline = committed_snapshot(pg)
    public_observations = []
    for fn in (old_public(), tools.complete_tool_call, tools._complete_tool_call_in_transaction):
        with ObservedSession(pg, autoflush=False) as db:
            db.execute(Workspace.__table__.update().where(Workspace.id == uid("workspaces")).values(description="outer write"))
            def complete(session, call):
                write_result(session, call)
                if failure == "callback_flush":
                    call.tool_name = "not_a_native_tool"
                    session.flush()
                if failure == "callback":
                    session.flush()
                    raise RuntimeError("synthetic callback failure after result flush")
                return 2
            expected = RuntimeError if failure == "callback" else IntegrityError
            with observe(pg, db) as trace, pytest.raises(expected) as exc:
                invoke(fn, db, complete=complete)
            assert db.commits == 0
            assert committed_snapshot(pg) == baseline
            if fn is tools._complete_tool_call_in_transaction:
                assert db.rollbacks == 0
                assert db.in_transaction()
                if failure == "callback":
                    assert db.get(ResearchArtifact, uid("result")) is not None
                    assert db.scalar(select(Workspace.description).where(Workspace.id == uid("workspaces"))) == "outer write"
                    assert db.get(ResearchToolCall, uid("research_tool_calls")).status == "running"
                else:
                    assert not db.is_active
                db.rollback()
            else:
                assert db.rollbacks == 1
                assert not db.in_transaction()
                public_observations.append((type(exc.value), list(trace), db.flushes))
        assert committed_snapshot(pg) == baseline
    assert public_observations[0] == public_observations[1]


def test_pg_inner_commit_owned_by_caller_and_no_double_settlement(pg):
    with ObservedSession(pg, autoflush=False) as db:
        def complete(session, call):
            write_result(session, call)
            return 2
        invoke(tools._complete_tool_call_in_transaction, db, complete=complete)
        expected = snapshot(db.connection())
        assert (db.commits, db.rollbacks) == (0, 0)
        db.commit()
    assert committed_snapshot(pg) == expected
    with ObservedSession(pg, autoflush=False) as db:
        with pytest.raises(ResearchError, match="cannot be completed"):
            invoke(tools._complete_tool_call_in_transaction, db,
                   complete=lambda *_: pytest.fail("settled callback repeated"))
        assert (db.commits, db.rollbacks) == (0, 0)
        db.rollback()
    assert committed_snapshot(pg) == expected


def test_pg_inner_holds_every_native_row_lock_until_caller_rollback(pg):
    baseline = committed_snapshot(pg)
    with ObservedSession(pg, autoflush=False) as db:
        invoke(tools._complete_tool_call_in_transaction, db)
        for table, key in zip(LOCK_ORDER, ["research_runs", "step", "attempt", "research_tool_calls",
                                          "research_budget_ledgers"], strict=True):
            with pg.connect() as contender:
                with pytest.raises(DBAPIError) as exc:
                    contender.execute(text(f'SELECT id FROM "{table}" WHERE id=:id FOR UPDATE NOWAIT'), {"id": uid(key)})
                assert exc.value.orig.sqlstate == "55P03"
                contender.rollback()
        assert db.rollbacks == db.commits == 0
        db.rollback()
    assert committed_snapshot(pg) == baseline


def test_pg_inner_refreshes_cached_rows_instead_of_trusting_caller_mutation(pg):
    with ObservedSession(pg, autoflush=False) as db:
        call = db.get(ResearchToolCall, uid("research_tool_calls"))
        call.workspace_id = uid("foreign_workspace")
        call.status = "succeeded"
        invoke(tools._complete_tool_call_in_transaction, db)
        assert call.workspace_id == uid("workspaces")
        assert call.status == "succeeded"
        assert db.get(ResearchBudgetLedger, uid("research_budget_ledgers")).actual_tool_calls == 5
        db.rollback()

@pytest.mark.parametrize("fn_name", ["old", "public", "inner"])
def test_pg_lock_failure_remains_outside_public_rollback_boundary(pg, fn_name):
    fn = {"old": old_public(), "public": tools.complete_tool_call,
          "inner": tools._complete_tool_call_in_transaction}[fn_name]
    baseline = committed_snapshot(pg)
    with pg.connect() as owner, ObservedSession(pg, autoflush=False) as db:
        owner.execute(select(ResearchRun).with_for_update())
        db.execute(text("SET LOCAL lock_timeout = '100ms'"))
        db.execute(Workspace.__table__.update().where(Workspace.id == uid("workspaces")).values(description="outer write"))
        with pytest.raises(DBAPIError) as exc:
            invoke(fn, db, complete=lambda *_: pytest.fail("callback ran without native locks"))
        assert exc.value.orig.sqlstate == "55P03"
        assert (db.commits, db.rollbacks) == (0, 0)
        assert db.in_transaction()
        db.rollback()
        owner.rollback()
    assert committed_snapshot(pg) == baseline


@pytest.mark.parametrize("fn_name", ["old", "public", "inner"])
def test_pg_precondition_autoflush_failure_does_not_expand_rollback(pg, fn_name):
    fn = {"old": old_public(), "public": tools.complete_tool_call,
          "inner": tools._complete_tool_call_in_transaction}[fn_name]
    baseline = committed_snapshot(pg)
    with ObservedSession(pg) as db:
        workspace = db.get(Workspace, uid("workspaces"))
        workspace.name = None
        with pytest.raises(IntegrityError) as exc:
            invoke(fn, db, complete=lambda *_: pytest.fail("callback ran after precondition autoflush failure"))
        assert exc.value.orig.sqlstate == "23502"
        assert (db.commits, db.rollbacks) == (0, 0)
        assert not db.is_active
        db.rollback()
    assert committed_snapshot(pg) == baseline


def test_pg_clock_default_and_null_error_fields_match_baseline(pg, monkeypatch):
    class Clock:
        calls = 0

        @classmethod
        def now(cls, tz):
            assert tz is UTC
            cls.calls += 1
            return SETTLED_AT

    monkeypatch.setattr(tools, "datetime", Clock)
    states = []
    for fn in (old_public(), tools.complete_tool_call, tools._complete_tool_call_in_transaction):
        with ObservedSession(pg, autoflush=False) as db:
            invoke(fn, db, now=None, error_code=None, error_message=None)
            states.append(snapshot(db.connection()))
            db.rollback()
    assert Clock.calls == 3
    assert states[0] == states[1] == states[2]
    call = row_from(states[0], ResearchToolCall, "research_tool_calls")
    assert call["finished_at"] == SETTLED_AT and call["error_code"] is call["error_message"] is None
