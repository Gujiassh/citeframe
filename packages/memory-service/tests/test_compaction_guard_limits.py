"""Real PostgreSQL bounds for complete native membership capture, no model calls."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from citeframe_contracts.compaction import ContextOwner
from citeframe_memory.compaction.guards import GuardLimits, NativeGuard, canonical
from citeframe_memory.compaction.policy import CompactionError
from citeframe_memory.compaction.repository import CompactionRepository
from test_compaction_fixture import insert_message, pg43, seed_chat


def registered_thread(engine, total):
    scope = seed_chat(engine)
    now = datetime.now(UTC)
    deadline = now + timedelta(hours=1)
    owner = ContextOwner(scope.workspace_id, scope.user_id, "chat", str(uuid4()), "a" * 64)
    with engine.begin() as connection:
        connection.execute(text("UPDATE chat_messages SET role='assistant',status='streaming' WHERE id=:id"), {"id": scope.leaf_id})
        connection.execute(text("UPDATE chat_threads SET active_message_id=NULL WHERE id=:id"), {"id": scope.thread_id})
        for _ in range(total - 2):
            insert_message(connection, scope, str(uuid4()), content="SIBLING_BODY_MUST_NOT_ENTER_MANIFEST")
    repository = CompactionRepository(lambda: Session(engine), clock=lambda: now)
    repository.create_chat(owner, thread_id=scope.thread_id, user_message_id=scope.parent_id,
        assistant_message_id=scope.leaf_id, request_id=str(uuid4()), request_sha256="b" * 64,
        policy={"schemaVersion": "compaction-policy-v1", "maxCalls": 100, "maxInputTokens": 100000,
                "maxOutputTokens": 10000, "maxSummaryCalls": 8, "maxEpisodes": 4,
                "deadlineAt": deadline.isoformat()}, deadline_at=deadline, lease_expires_at=deadline)
    return owner, now


def guarded_capture(engine, owner, now, limits):
    statements = []
    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(engine, "before_cursor_execute", record)
    try:
        with Session(engine) as db, db.begin():
            start = perf_counter()
            guard = NativeGuard(db, owner, limits, now)
            elapsed = (perf_counter() - start) * 1000
            manifest = guard.membership
            settings = dict(db.execute(text("""SELECT name,setting::int FROM pg_settings
                WHERE name IN ('transaction_timeout','statement_timeout','lock_timeout')""")).all())
            assert settings == {"transaction_timeout": limits.transaction_timeout_ms,
                                "statement_timeout": limits.statement_timeout_ms,
                                "lock_timeout": limits.lock_timeout_ms}
            assert all(len(row) == 2 and len(row[0]) == 36 and type(row[1]) is int for row in manifest)
            return manifest, elapsed
    finally:
        event.remove(engine, "before_cursor_execute", record)
        message_selects = [sql for sql in statements if "FROM chat_messages" in sql]
        assert len(message_selects) == 1
        assert "chat_messages.content" not in message_selects[0]
        assert "SKIP LOCKED" not in message_selects[0]
        assert "FOR UPDATE NOWAIT" in message_selects[0]


def assert_no_compaction_effects(engine, owner):
    with engine.connect() as connection:
        for table in ("memory_calls", "memory_sources", "task_memory_snapshots", "task_memory_coverage", "memory_uses"):
            assert connection.scalar(text("SELECT count(*) FROM " + table)) == 0
        assert connection.execute(text("SELECT context_version,checkpoint_id FROM chat_memory_executions WHERE id=:id"), {"id": owner.owner_id}).one() == (0, None)
        # A fresh writer can acquire all released root/message guards immediately.
        thread_id = connection.scalar(text("SELECT thread_id FROM chat_memory_executions WHERE id=:id"), {"id": owner.owner_id})
        connection.execute(text("SELECT id FROM chat_threads WHERE id=:id FOR UPDATE NOWAIT"), {"id": thread_id})
        connection.execute(text("SELECT id FROM chat_messages WHERE thread_id=:id FOR UPDATE NOWAIT"), {"id": thread_id})
        connection.rollback()


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_default_complete_uuid_manifest_row_limit(pg43, delta):
    limits = GuardLimits()
    total = limits.max_thread_rows + delta
    owner, now = registered_thread(pg43, total)
    if delta > 0:
        with pytest.raises(CompactionError, match="context_too_large"):
            guarded_capture(pg43, owner, now, limits)
    else:
        manifest, elapsed = guarded_capture(pg43, owner, now, limits)
        assert len(manifest) == total
        assert len(canonical(manifest).encode()) <= limits.max_manifest_bytes
        print(f"guard_complete_rows={total} manifest_bytes={len(canonical(manifest).encode())} guard_ms={elapsed:.3f}")
    assert_no_compaction_effects(pg43, owner)


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_exact_serialized_uuid_manifest_byte_limit(pg43, delta):
    owner, now = registered_thread(pg43, 64)
    manifest, _ = guarded_capture(pg43, owner, now, GuardLimits())
    byte_count = len(canonical(manifest).encode())
    limits = replace(GuardLimits(), max_manifest_bytes=byte_count + delta)
    if delta < 0:
        with pytest.raises(CompactionError, match="context_too_large"):
            guarded_capture(pg43, owner, now, limits)
    else:
        captured, _ = guarded_capture(pg43, owner, now, limits)
        assert captured == manifest
    assert_no_compaction_effects(pg43, owner)
