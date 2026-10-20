"""Registration FK prelocks versus actual native DELETE/SET NULL, on real PG."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from time import monotonic, sleep
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from citeframe_contracts.compaction import ContextOwner
from citeframe_memory.compaction.policy import CompactionError
from citeframe_memory.compaction.repository import CompactionRepository
from test_compaction_fixture import insert_message, pg43, seed_chat


def registration_fixture(engine, null_anchor):
    scope = seed_chat(engine)
    current_user, assistant = str(uuid4()), str(uuid4())
    with engine.begin() as db:
        db.execute(text("UPDATE chat_messages SET role='assistant' WHERE id=:id"), {"id": scope.leaf_id})
        insert_message(db, scope, current_user, parent_id=None if null_anchor else scope.leaf_id)
        insert_message(db, scope, assistant, parent_id=current_user)
        db.execute(text("UPDATE chat_messages SET role='assistant',status='streaming',content='' WHERE id=:id"), {"id": assistant})
        if null_anchor:
            db.execute(text("UPDATE chat_threads SET active_message_id=NULL WHERE id=:id"), {"id": scope.thread_id})
    now = datetime.now(UTC); deadline = now + timedelta(hours=1)
    owner = ContextOwner(scope.workspace_id, scope.user_id, "chat", str(uuid4()), "a" * 64)
    policy = dict(schemaVersion="compaction-policy-v1", maxCalls=100, maxInputTokens=100000,
        maxOutputTokens=10000, maxSummaryCalls=8, maxEpisodes=4, deadlineAt=deadline.isoformat())
    repo = CompactionRepository(lambda: Session(engine), clock=lambda: now)
    def register():
        return repo.create_chat(owner, thread_id=scope.thread_id, user_message_id=current_user,
            assistant_message_id=assistant, request_id=str(uuid4()), request_sha256="b" * 64,
            policy=policy, deadline_at=deadline, lease_expires_at=deadline)
    target = current_user if null_anchor else scope.leaf_id
    return scope, owner, current_user, assistant, target, register


def assert_waiting_for_lock(engine, pid, future):
    deadline = monotonic() + 3
    while monotonic() < deadline:
        assert not future.done(), "Native writer finished before registration released its FK target"
        with engine.connect() as db:
            waiting = db.scalar(text("SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid"), {"pid": pid})
        if waiting == "Lock":
            return
        sleep(.01)
    pytest.fail("Native writer never reached the expected FK-target lock barrier")


@pytest.mark.parametrize("null_anchor", [False, True])
def test_native_writer_first_registration_aborts_and_releases_pair(pg43, null_anchor):
    scope, owner, user, assistant, target, register = registration_fixture(pg43, null_anchor)
    ready = Event()
    attempts = []
    def observe(connection, cursor, statement, parameters, context, executemany):
        if "FROM workspaces" in statement and "FOR UPDATE NOWAIT" in statement:
            attempts.append(statement)
        if "FROM chat_messages" in statement and "FOR UPDATE NOWAIT" in statement and assistant in repr(parameters):
            ready.set()
    event.listen(pg43, "after_cursor_execute", observe)
    try:
        with pg43.connect() as writer:
            writer.execute(text("SET LOCAL deadlock_timeout='10ms'"))
            writer.execute(text("SELECT id FROM chat_messages WHERE id=:id FOR UPDATE"), {"id": target})
            def registering():
                try:
                    register()
                    return "committed"
                except CompactionError as error:
                    return str(error)
                finally:
                    ready.set()
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(registering)
                assert ready.wait(3), "Registration did not reach or reject the guarded pair"
                started = monotonic()
                writer.execute(text("DELETE FROM chat_messages WHERE id=:id"), {"id": target})
                assert future.result(timeout=3) == "context_busy"
                writer.commit()
                assert monotonic() - started < 3
        assert len(attempts) == 2
    finally:
        event.remove(pg43, "after_cursor_execute", observe)
    with pg43.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM chat_memory_executions WHERE id=:id"), {"id": owner.owner_id}) == 0
        assert db.scalar(text("SELECT count(*) FROM chat_messages WHERE id=:id"), {"id": target}) == 0
        child = assistant if null_anchor else user
        assert db.scalar(text("SELECT parent_message_id FROM chat_messages WHERE id=:id"), {"id": child}) is None
        db.execute(text("SELECT id FROM chat_threads WHERE id=:id FOR UPDATE NOWAIT"), {"id": scope.thread_id})
        db.execute(text("SELECT id FROM chat_messages WHERE id=:id FOR UPDATE NOWAIT"), {"id": child})


@pytest.mark.parametrize("null_anchor", [False, True])
def test_registration_first_native_delete_waits_then_retention_rejects(pg43, null_anchor):
    scope, owner, user, assistant, target, register = registration_fixture(pg43, null_anchor)
    before_insert, release = Event(), Event()
    def pause(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO chat_memory_executions"):
            before_insert.set()
            assert release.wait(3), "Registration barrier not released"
    event.listen(pg43, "before_cursor_execute", pause)
    try:
        with pg43.connect() as writer, ThreadPoolExecutor(max_workers=2) as executor:
            writer.execute(text("SET LOCAL deadlock_timeout='10ms'"))
            pid = writer.scalar(text("SELECT pg_backend_pid()"))
            registration = executor.submit(register)
            assert before_insert.wait(3)
            def deleting():
                try:
                    writer.execute(text("DELETE FROM chat_messages WHERE id=:id"), {"id": target})
                    writer.commit()
                    return "committed"
                except DBAPIError as error:
                    writer.rollback()
                    return error.orig.sqlstate
            deletion = executor.submit(deleting)
            try:
                assert_waiting_for_lock(pg43, pid, deletion)
            finally:
                release.set()
            assert registration.result(timeout=3) == owner.owner_id
            assert deletion.result(timeout=3) == "23503"
    finally:
        release.set()
        event.remove(pg43, "before_cursor_execute", pause)
    with pg43.connect() as db:
        assert db.execute(text("SELECT anchor_leaf_id,context_version,checkpoint_id FROM chat_memory_executions WHERE id=:id"), {"id": owner.owner_id}).one() == (None if null_anchor else target, 0, None)
        assert db.scalar(text("SELECT parent_message_id FROM chat_messages WHERE id=:id"), {"id": assistant}) == user
        assert db.scalar(text("SELECT count(*) FROM chat_messages WHERE id=:id"), {"id": target}) == 1
