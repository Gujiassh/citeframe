"""Real PostgreSQL pre-write, precedence and exact-source admission oracles."""
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import UTC, datetime
from hashlib import sha256
import json
import logging
from uuid import uuid4

import pytest
from sqlalchemy import event, select, text, update
from sqlalchemy.orm import Session

from citeframe_contracts.memory import (
    AccessDenied, IdempotencyConflict, MemoryError, MemoryRequest, VersionConflict,
)
import citeframe_memory.commands as commands
from citeframe_persistence.models import Workspace, WorkspaceMembership
from citeframe_persistence.models.memory import MemoryInstruction, MemoryRevision
from test_admission import placed
from test_instruction_memory import MIGRATION, command, pg, request, statement

SENSITIVE = "password=ADMISSION_SYNTHETIC_42"


def snapshot(engine):
    with engine.connect() as conn:
        return {
            table: sorted(json.dumps(row, sort_keys=True) for row in
                          conn.execute(text(f"SELECT to_jsonb(t) FROM {table} t")).scalars())
            for table in MIGRATION.TABLES
        }


@contextmanager
def observe_dml(engine):
    writes = []

    def observe(conn, cursor, sql, parameters, context, executemany):
        if sql.lstrip().split(None, 1)[0].upper() in ("INSERT", "UPDATE", "DELETE"):
            writes.append(sql)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        yield writes
    finally:
        event.remove(engine, "before_cursor_execute", observe)


@pytest.mark.parametrize("action", ("remember", "correct"))
@pytest.mark.parametrize("field", ("content", "subject", "applicability"))
def test_rejected_submission_has_no_dml_or_six_table_change(pg, action, field, caplog, monkeypatch):
    engine, ctx, _ = pg
    first = command(engine, "remember", ctx, request(), statement())
    req = request()
    bad = placed(SENSITIVE, field)
    target = (first.resource.memory_id, 1) if action == "correct" else ()
    before = snapshot(engine)
    digest = commands.canonical_hash({
        "method": "POST", "path": f"/memory/{first.resource.memory_id if target else ''}/{action}",
        "expectedVersion": 1 if target else None, "statement": asdict(bad),
    })
    caplog.set_level(logging.DEBUG, logger="sqlalchemy.engine.Engine")

    def forbidden_instruction(*args, **kwargs):
        pytest.fail("Instruction constructed before rejection")

    with monkeypatch.context() as patch:
        patch.setattr(commands, "MemoryInstruction", forbidden_instruction)
        with observe_dml(engine) as writes, pytest.raises(MemoryError) as exc:
            command(engine, action, ctx, req, *target, bad)
    assert type(exc.value) is MemoryError
    assert exc.value.args == ("sensitive_content_unsupported",)
    assert str(exc.value) == "sensitive_content_unsupported"
    assert repr(exc.value) == "MemoryError('sensitive_content_unsupported')"
    assert exc.value.__cause__ is None and exc.value.__context__ is None
    assert writes == []
    assert snapshot(engine) == before
    assert command(engine, "reconcile", ctx, req.request_id) is None
    for forbidden in (SENSITIVE, sha256(SENSITIVE.encode()).hexdigest(), digest):
        assert forbidden not in caplog.text
    caplog.set_level(logging.WARNING, logger="sqlalchemy.engine.Engine")

    # Rejection leaves both identities unconsumed; a clean edit can reuse them.
    clean = placed("Exact safe text \t café\n第二行", field)
    receipt = command(engine, action, ctx, req, *target, clean)
    assert receipt.resource.statement == clean
    assert command(engine, action, ctx, req, *target, clean) == receipt
    assert command(engine, "reconcile", ctx, req.request_id) == receipt


@pytest.mark.parametrize("case,code,error", (
    ("invalid_request", "badly formed hexadecimal UUID string", ValueError),
    ("invalid_key", "invalid_idempotency_key", ValueError),
    ("invalid_version", "invalid_expected_version", ValueError),
    ("shared", "private_management_only", AccessDenied),
    ("purpose", "private_management_only", AccessDenied),
    ("nonowner", "memory_unavailable", AccessDenied),
    ("member_missing", "membership_required", AccessDenied),
    ("archive", "workspace_unavailable", AccessDenied),
    ("stale", "version_conflict", VersionConflict),
    ("terminal", "terminal_memory", VersionConflict),
    ("superseded", "terminal_memory", VersionConflict),
    ("conflict", "idempotency_conflict", IdempotencyConflict),
))
def test_existing_error_precedence_before_admission(pg, case, code, error, monkeypatch):
    engine, ctx, other = pg
    initial_req = request()
    first = command(engine, "remember", ctx, initial_req, statement())
    req, version, actor = request(), 1, ctx
    action = "correct"
    if case == "invalid_request":
        req = MemoryRequest("invalid", str(uuid4()))
    elif case == "invalid_key":
        req = MemoryRequest(str(uuid4()), "short")
    elif case == "invalid_version":
        version = 0
    elif case == "shared":
        actor = replace(ctx, output_audience="workspace")
    elif case == "purpose":
        actor = replace(ctx, purpose="chat")
    elif case == "nonowner":
        actor = replace(ctx, actor_user_id=other)
    elif case == "member_missing":
        with engine.begin() as conn:
            conn.execute(WorkspaceMembership.__table__.delete().where(
                WorkspaceMembership.user_id == ctx.actor_user_id))
    elif case == "archive":
        with engine.begin() as conn:
            conn.execute(update(Workspace).values(archived_at=datetime.now(UTC)))
    elif case == "stale":
        version = 2
    elif case == "terminal":
        command(engine, "delete", ctx, request(), first.resource.memory_id, 1)
        version = 2
    elif case == "superseded":
        command(engine, "correct", ctx, request(), first.resource.memory_id, 1, statement("next"))
        version = 2
    elif case == "conflict":
        req, action = initial_req, "remember"

    def admission_must_not_run(value):
        pytest.fail("Admission masked existing error precedence")

    monkeypatch.setattr(commands, "admit_statement", admission_must_not_run)
    before = snapshot(engine)
    args = (req, first.resource.memory_id, version) if action == "correct" else (req,)
    with observe_dml(engine) as writes, pytest.raises(error) as exc:
        command(engine, action, actor, *args, placed(SENSITIVE, "content"))
    assert str(exc.value) == code
    assert not writes
    assert snapshot(engine) == before


def test_exact_source_conditions_hash_and_correction(pg):
    engine, ctx, _ = pg
    clean = placed("  public key discussion: café e\u0301\nKeep \\n literal.  ", "content")
    clean = replace(clean, conditions=replace(
        clean.conditions, subject="  项目 \t scope  ", applicability="Manual only\n  unchanged ",
        effective_from=datetime(2026, 9, 28, tzinfo=UTC)))
    first_req = request()
    first = command(engine, "remember", ctx, first_req, clean)
    next_statement = replace(clean, content=clean.content + "\nSecond exact version.")
    next_req = request()
    corrected = command(engine, "correct", ctx, next_req, first.resource.memory_id, 1, next_statement)
    for receipt, expected in ((first, clean), (corrected, next_statement)):
        source = command(engine, "read_source", ctx, receipt.resource.confirmation_source_id)
        assert source.content == expected.content
        assert source.actor_user_id == ctx.actor_user_id
        with Session(engine) as db:
            revision = db.scalar(select(MemoryRevision).where(
                MemoryRevision.revision_id == receipt.resource.revision_id))
            instruction = db.get(MemoryInstruction, revision.instruction_id)
            assert instruction.content == expected.content
            assert instruction.content_sha256 == sha256(expected.content.encode()).hexdigest()
            assert revision.content == expected.content
            assert revision.conditions == commands.conditions_json(expected)
    assert command(engine, "correct", ctx, next_req, first.resource.memory_id, 1, next_statement) == corrected
    assert command(engine, "reconcile", ctx, next_req.request_id) == corrected
    assert command(engine, "read", ctx, first.resource.memory_id).intent == "superseded"
    assert command(engine, "read", ctx, corrected.resource.memory_id).statement == next_statement


@pytest.mark.parametrize("action", ("remember", "correct"))
def test_committed_historical_replay_delete_reconcile_do_not_scan(pg, monkeypatch, action):
    engine, ctx, _ = pg
    req = request()
    legacy = placed(SENSITIVE, "content")
    target = ()
    if action == "correct":
        prior = command(engine, "remember", ctx, request(), statement())
        target = (prior.resource.memory_id, 1)
    # Simulate a committed pre-admission row using the unchanged command contract.
    with monkeypatch.context() as patch:
        patch.setattr(commands, "admit_statement", lambda value: None)
        first = command(engine, action, ctx, req, *target, legacy)

    def no_scan(value):
        pytest.fail("Historical or non-writing flow scanned source")

    monkeypatch.setattr(commands, "admit_statement", no_scan)
    with observe_dml(engine) as writes:
        assert command(engine, action, ctx, req, *target, legacy) == first
        assert command(engine, "reconcile", ctx, req.request_id) == first
    assert not writes
    inactive = command(engine, "deactivate", ctx, request(), first.resource.memory_id, 1)
    deleted = command(engine, "delete", ctx, request(), first.resource.memory_id, inactive.resource.version)
    assert deleted.resource.erased
    assert command(engine, action, ctx, req, *target, legacy).resource.erased


def test_rejected_and_clean_corrections_race_preserves_single_successor(pg):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    engine, ctx, _ = pg
    first = command(engine, "remember", ctx, request(), statement())
    barrier = Barrier(2)
    bad_req, clean_req = request(), request()

    def contender(bad):
        barrier.wait()
        try:
            value = placed(SENSITIVE, "applicability") if bad else statement("clean successor")
            return command(engine, "correct", ctx, bad_req if bad else clean_req,
                           first.resource.memory_id, 1, value)
        except (MemoryError, VersionConflict) as exc:
            return str(exc)

    with ThreadPoolExecutor(2) as pool:
        bad, good = list(pool.map(contender, (True, False)))
    assert bad in ("sensitive_content_unsupported", "version_conflict")
    assert good.resource.statement == statement("clean successor")
    assert command(engine, "reconcile", ctx, bad_req.request_id) is None
    assert command(engine, "reconcile", ctx, clean_req.request_id) == good
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM memory_records WHERE supersedes_id=:id"),
                           {"id": first.resource.memory_id}) == 1
    assert all(SENSITIVE not in row for rows in snapshot(engine).values() for row in rows)
