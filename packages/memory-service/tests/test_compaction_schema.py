"""Real shipped-schema proof of the selected native row-local/FK fence.

These oracles do not establish application every-dispatch integration.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from citeframe_persistence import Base
import citeframe_persistence.models  # noqa: F401
from test_compaction_fixture import (
    HEAD, PREVIOUS, disposable_database, insert_message, migrate, pg43, seed_chat,
)


THREAD_FIELDS = {
    "id", "workspace_id", "created_by_user_id", "title", "active_message_id",
    "archived_at", "last_message_at", "created_at", "updated_at",
}
MESSAGE_FIELDS = {
    "id", "workspace_id", "thread_id", "parent_message_id", "role", "content", "status",
    "model_provider", "model_name", "prompt_version_id", "input_tokens", "output_tokens", "created_at",
}


def revision(connection, table, id_):
    assert table in {"chat_messages", "chat_threads"}
    return connection.scalar(text(f"SELECT compaction_revision FROM {table} WHERE id=:id"), {"id": id_})


def root_lock(connection, scope):
    return connection.execute(text("SELECT id FROM chat_threads WHERE id=:id FOR UPDATE NOWAIT"),
                              {"id": scope.thread_id}).scalar_one()


def complete_manifest(connection, scope):
    return connection.execute(text("""SELECT id,compaction_revision FROM chat_messages
        WHERE thread_id=:id ORDER BY id FOR UPDATE NOWAIT"""), {"id": scope.thread_id}).all()


def locked_error(action):
    with pytest.raises(DBAPIError) as error:
        action()
    assert error.value.orig.sqlstate == "55P03"


def test_full_chain_native_catalog_and_metadata_parity(pg43):
    changed = {"chat_threads", "chat_messages", "research_step_attempts", "memory_sources", "memory_uses",
               "chat_memory_executions", "memory_calls", "task_memory_snapshots", "task_memory_coverage"}
    with pg43.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
        assert connection.scalar(text("SHOW transaction_isolation")) == "read committed"
        fks = connection.execute(text("""SELECT conname,condeferrable,condeferred,convalidated,
            pg_get_constraintdef(oid) FROM pg_constraint
            WHERE conrelid='chat_messages'::regclass AND contype='f'""")).all()
        thread_fk = [row for row in fks if "FOREIGN KEY (thread_id)" in row[4]]
        assert len(thread_fk) == 1
        assert thread_fk[0][1:4] == (False, False, True)
        assert "ON DELETE SET NULL" in next(row[4] for row in fks if "(parent_message_id)" in row[4])
        assert {c.name for c in Base.metadata.tables["chat_messages"].columns} == MESSAGE_FIELDS | {"compaction_revision"}
        assert {c.name for c in Base.metadata.tables["chat_threads"].columns} == THREAD_FIELDS | {"compaction_revision"}
        context = MigrationContext.configure(connection, opts={
            "compare_type": True, "compare_server_default": True,
            "include_object": lambda obj, name, type_, reflected, compare_to: type_ != "table" or name in changed,
        })
        assert compare_metadata(context, Base.metadata) == []


@pytest.mark.parametrize("table", ["chat_messages", "chat_threads"])
def test_every_native_field_changes_stamp_and_spoof_is_ignored(pg43, table):
    scope = seed_chat(pg43)
    if table == "chat_messages":
        id_ = str(uuid4())
        with pg43.begin() as connection:
            insert_message(connection, scope, id_)
        changes = {
            "id": "'" + str(uuid4()) + "'", "workspace_id": "'" + scope.other_workspace_id + "'",
            "thread_id": "'" + scope.other_thread_id + "'", "parent_message_id": "'" + scope.parent_id + "'",
            "role": "'assistant'", "content": "'changed'", "status": "'failed'", "model_provider": "'fixture'",
            "model_name": "'fixture'", "prompt_version_id": "'fixture'", "input_tokens": "1", "output_tokens": "2",
            "created_at": "created_at + interval '1 second'",
        }
    else:
        id_ = scope.other_thread_id
        changes = {
            "id": "'" + str(uuid4()) + "'", "workspace_id": "'" + scope.other_workspace_id + "'",
            "created_by_user_id": "'" + scope.other_user_id + "'", "title": "'changed'",
            "active_message_id": "'" + scope.parent_id + "'", "archived_at": "now()",
            "last_message_at": "last_message_at + interval '1 second'",
            "created_at": "created_at + interval '1 second'", "updated_at": "updated_at + interval '1 second'",
        }
    assert set(changes) == (MESSAGE_FIELDS if table == "chat_messages" else THREAD_FIELDS)
    for field, expression in changes.items():
        with pg43.connect() as connection:
            before = revision(connection, table, id_)
            after = connection.scalar(text(f"UPDATE {table} SET {field}={expression},compaction_revision=1 WHERE id=:id RETURNING compaction_revision"), {"id": id_})
            assert after > before, field
            connection.rollback()
    with pg43.begin() as connection:
        before = revision(connection, table, id_)
        connection.execute(text(f"UPDATE {table} SET compaction_revision=1 WHERE id=:id"), {"id": id_})
        assert revision(connection, table, id_) == before


def test_content_leaf_aba_and_same_id_recreation(pg43):
    scope = seed_chat(pg43)
    with pg43.begin() as connection:
        message_before = revision(connection, "chat_messages", scope.leaf_id)
        thread_before = revision(connection, "chat_threads", scope.thread_id)
        original = connection.scalar(text("SELECT content FROM chat_messages WHERE id=:id"), {"id": scope.leaf_id})
        for content in ("changed", original):
            connection.execute(text("UPDATE chat_messages SET content=:content WHERE id=:id"), {"content": content, "id": scope.leaf_id})
        for leaf in (scope.parent_id, scope.leaf_id):
            connection.execute(text("UPDATE chat_threads SET active_message_id=:leaf WHERE id=:id"), {"leaf": leaf, "id": scope.thread_id})
        assert revision(connection, "chat_messages", scope.leaf_id) > message_before
        assert revision(connection, "chat_threads", scope.thread_id) > thread_before
        old = revision(connection, "chat_messages", scope.leaf_id)
        connection.execute(text("DELETE FROM chat_messages WHERE id=:id"), {"id": scope.leaf_id})
        insert_message(connection, scope, scope.leaf_id, parent_id=scope.parent_id, content=original)
        assert revision(connection, "chat_messages", scope.leaf_id) > old
        old = revision(connection, "chat_threads", scope.other_thread_id)
        connection.execute(text("DELETE FROM chat_threads WHERE id=:id"), {"id": scope.other_thread_id})
        connection.execute(text("""INSERT INTO chat_threads
            (id,workspace_id,created_by_user_id,title,last_message_at,created_at,updated_at,compaction_revision)
            VALUES (:id,:workspace,:user,'fixture',now(),now(),now(),1)"""),
            {"id": scope.other_thread_id, "workspace": scope.workspace_id, "user": scope.user_id})
        assert revision(connection, "chat_threads", scope.other_thread_id) > old


@pytest.mark.parametrize("mutation", ["insert", "reparent_in"])
@pytest.mark.parametrize("commit", [False, True])
def test_fk_keyshare_before_root_rejects_nowait(pg43, mutation, commit):
    scope = seed_chat(pg43)
    id_ = str(uuid4())
    if mutation == "reparent_in":
        with pg43.begin() as connection:
            insert_message(connection, scope, id_, thread_id=scope.other_thread_id)
    with pg43.connect() as writer, pg43.connect() as compactor:
        if mutation == "insert":
            insert_message(writer, scope, id_)
        else:
            writer.execute(text("UPDATE chat_messages SET thread_id=:thread WHERE id=:id"), {"thread": scope.thread_id, "id": id_})
        locked_error(lambda: root_lock(compactor, scope))
        compactor.rollback()
        writer.commit() if commit else writer.rollback()
        root_lock(compactor, scope)
        ids = {row.id for row in complete_manifest(compactor, scope)}
        assert (id_ in ids) is commit
        compactor.rollback()


def wait_for_blocker(connection, waiter_pid, blocker_pid):
    deadline = monotonic() + 3
    while monotonic() < deadline:
        blockers = connection.scalar(text("SELECT pg_blocking_pids(:pid)"), {"pid": waiter_pid})
        if blocker_pid in blockers:
            return
        sleep(0.01)
    pytest.fail("writer did not demonstrably block on the guarded thread")


@pytest.mark.parametrize("commit", [False, True])
def test_root_before_insert_serializes_and_next_manifest_observes_result(pg43, commit):
    scope = seed_chat(pg43)
    id_, pids, started = str(uuid4()), [], Event()
    def writer():
        with pg43.connect() as connection:
            pids.append(connection.scalar(text("SELECT pg_backend_pid()")))
            started.set()
            insert_message(connection, scope, id_)
            connection.commit() if commit else connection.rollback()
    with pg43.connect() as compactor, ThreadPoolExecutor(max_workers=1) as pool:
        root_lock(compactor, scope)
        before = complete_manifest(compactor, scope)
        blocker_pid = compactor.scalar(text("SELECT pg_backend_pid()"))
        future = pool.submit(writer)
        try:
            assert started.wait(2)
            wait_for_blocker(compactor, pids[0], blocker_pid)
            assert complete_manifest(compactor, scope) == before
        finally:
            compactor.rollback()
        future.result(timeout=5)
        root_lock(compactor, scope)
        assert (id_ in {row.id for row in complete_manifest(compactor, scope)}) is commit
        compactor.rollback()


@pytest.mark.parametrize("mutation", ["content", "reparent_out", "delete"])
def test_complete_manifest_lock_catches_native_message_first_writer(pg43, mutation):
    scope = seed_chat(pg43)
    with pg43.connect() as writer, pg43.connect() as compactor, pg43.connect() as observer:
        if mutation == "content":
            writer.execute(text("UPDATE chat_messages SET content='changed' WHERE id=:id"), {"id": scope.parent_id})
        elif mutation == "reparent_out":
            writer.execute(text("UPDATE chat_messages SET thread_id=:thread WHERE id=:id"), {"thread": scope.other_thread_id, "id": scope.parent_id})
        else:
            # The parent has a child but is not the active leaf.
            writer.execute(text("DELETE FROM chat_messages WHERE id=:id"), {"id": scope.parent_id})
        root_lock(compactor, scope)
        locked_error(lambda: complete_manifest(compactor, scope))
        compactor.rollback()
        root_lock(observer, scope)
        observer.rollback()
        writer.rollback()


def test_native_parent_leaf_set_null_and_cascade_are_preserved(pg43):
    scope = seed_chat(pg43)
    with pg43.begin() as connection:
        connection.execute(text("UPDATE chat_threads SET active_message_id=:parent WHERE id=:id"), {"parent": scope.parent_id, "id": scope.thread_id})
        connection.execute(text("""INSERT INTO message_retrieval_scopes
            (message_id,workspace_id,scope_mode,created_at) VALUES (:id,:workspace,'all_ready',now())"""),
            {"id": scope.parent_id, "workspace": scope.workspace_id})
        child_before = revision(connection, "chat_messages", scope.leaf_id)
        thread_before = revision(connection, "chat_threads", scope.thread_id)
        connection.execute(text("DELETE FROM chat_messages WHERE id=:id"), {"id": scope.parent_id})
        assert connection.scalar(text("SELECT parent_message_id FROM chat_messages WHERE id=:id"), {"id": scope.leaf_id}) is None
        assert connection.scalar(text("SELECT active_message_id FROM chat_threads WHERE id=:id"), {"id": scope.thread_id}) is None
        assert revision(connection, "chat_messages", scope.leaf_id) > child_before
        assert revision(connection, "chat_threads", scope.thread_id) > thread_before
        assert connection.scalar(text("SELECT count(*) FROM message_retrieval_scopes")) == 0


def originals(connection, tables):
    return {table: connection.execute(text(f"SELECT to_jsonb(t) FROM {table} t ORDER BY to_jsonb(t)::text")).scalars().all() for table in tables}


def test_populated_originals_preserved_and_empty_successor_downgrades():
    from citeframe_contracts.memory import AccessContext, MemoryConditions, MemoryRequest, MemoryStatement
    from citeframe_memory.access import WorkspaceAccess
    from citeframe_memory.commands import MemoryCommands
    from sqlalchemy.orm import Session
    with disposable_database() as engine:
        scope = seed_chat(engine)
        with Session(engine) as db:
            MemoryCommands(db, WorkspaceAccess(db)).remember(
                AccessContext(scope.user_id, scope.workspace_id, "management", "private"),
                MemoryRequest(str(uuid4()), str(uuid4())),
                MemoryStatement("37.5 ms; never production", MemoryConditions("batch=8", "test only"), "constraint", True),
            )
        migrate(engine, PREVIOUS, downgrade=True)
        tables = ["chat_threads", "chat_messages", "memory_instructions", "memory_sources", "memory_records", "memory_revisions", "memory_uses", "memory_operations"]
        with engine.connect() as connection:
            before = originals(connection, tables)
        migrate(engine, HEAD)
        with engine.connect() as connection:
            after = originals(connection, tables)
            for table in ("chat_messages", "chat_threads"):
                for row in after[table]:
                    assert row.pop("compaction_revision") > 0
            for table in tables:
                after[table] = [{key: row[key] for key in before[table][0]} for row in after[table]] if before[table] else after[table]
            assert after == before
        migrate(engine, PREVIOUS, downgrade=True)
        with engine.connect() as connection:
            assert originals(connection, tables) == before
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == PREVIOUS


def test_sequence_not_owned_and_truncate_restart_does_not_recycle(pg43):
    scope = seed_chat(pg43)
    with pg43.begin() as connection:
        before = revision(connection, "chat_messages", scope.leaf_id)
        assert connection.scalar(text("SELECT seqcycle FROM pg_sequence WHERE seqrelid='chat_compaction_revision_seq'::regclass")) is False
        assert connection.scalar(text("""SELECT count(*) FROM pg_depend
            WHERE objid='chat_compaction_revision_seq'::regclass AND deptype IN ('a','i')""")) == 0
        connection.execute(text("TRUNCATE chat_messages,chat_threads RESTART IDENTITY CASCADE"))
        connection.execute(text("""INSERT INTO chat_threads
            (id,workspace_id,created_by_user_id,title,last_message_at,created_at,updated_at)
            VALUES (:id,:workspace,:user,'fixture',now(),now(),now())"""),
            {"id": scope.thread_id, "workspace": scope.workspace_id, "user": scope.user_id})
        insert_message(connection, scope, scope.leaf_id)
        assert revision(connection, "chat_messages", scope.leaf_id) > before



def seed_shared_source(connection, scope):
    id_ = str(uuid4())
    connection.execute(text("""INSERT INTO memory_sources
        (id,workspace_id,kind,native_id,source_version,native_version,content_sha256,audience,state,created_at)
        SELECT :source,workspace_id,'chat_message',id,1,
            jsonb_build_object('messageId',id,'parentMessageId',parent_message_id,'role',role,
                'status',status,'contentSha256',encode(sha256(convert_to(content,'UTF8')),'hex'),
                'compactionRevision',compaction_revision),
            encode(sha256(convert_to(content,'UTF8')),'hex'),'workspace','current',now()
        FROM chat_messages WHERE id=:message"""), {"source": id_, "message": scope.parent_id})
    return id_


@pytest.mark.parametrize("kind", ["source", "execution"])
def test_downgrade_refuses_populated_successor_without_partial_ddl(pg43, kind):
    scope = seed_chat(pg43)
    with pg43.begin() as connection:
        if kind == "source":
            seed_shared_source(connection, scope)
        else:
            connection.execute(text("""INSERT INTO chat_memory_executions
                (id,workspace_id,actor_user_id,thread_id,user_message_id,assistant_message_id,
                 request_id,request_sha256,attempt_number,state,version,context_version,anchor_leaf_id,
                 policy,deadline_at,created_at)
                VALUES (:id,:workspace,:actor,:thread,:parent,:leaf,:request,:sha,1,'prepared',1,0,
                        :leaf,'{}'::jsonb,now()+interval '1 hour',now())"""),
                {"id": str(uuid4()), "workspace": scope.workspace_id, "actor": scope.user_id,
                 "thread": scope.thread_id, "parent": scope.parent_id, "leaf": scope.leaf_id,
                 "request": str(uuid4()), "sha": "a" * 64})
    with pytest.raises(RuntimeError, match="compaction_data_present"):
        migrate(pg43, PREVIOUS, downgrade=True)
    with pg43.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
        assert revision(connection, "chat_threads", scope.thread_id) > 0
        assert connection.scalar(text("SELECT to_regclass('task_memory_coverage')")) is not None
        assert connection.scalar(text("SELECT count(*) FROM " + ("memory_sources" if kind == "source" else "chat_memory_executions"))) == 1


def test_private_revision_cannot_use_null_owned_shared_source(pg43):
    from citeframe_contracts.memory import AccessContext, MemoryConditions, MemoryRequest, MemoryStatement
    from citeframe_memory.access import WorkspaceAccess
    from citeframe_memory.commands import MemoryCommands
    from sqlalchemy.orm import Session
    scope = seed_chat(pg43)
    with Session(pg43) as db:
        MemoryCommands(db, WorkspaceAccess(db)).remember(
            AccessContext(scope.user_id, scope.workspace_id, "management", "private"),
            MemoryRequest(str(uuid4()), str(uuid4())),
            MemoryStatement("private fixture", MemoryConditions("batch=8", "test"), "constraint", True))
    with pg43.begin() as connection:
        source_id = seed_shared_source(connection, scope)
    with pytest.raises(DBAPIError, match="memory_revision_support_required"):
        with pg43.begin() as connection:
            connection.execute(text("""INSERT INTO memory_uses
                (id,workspace_id,consumer_revision_id,source_id,use_mode,atom_key,support_group,relation)
                SELECT :id,workspace_id,revision_id,:source,'support','foreign','fixture','supports'
                FROM memory_revisions"""), {"id": str(uuid4()), "source": source_id})
    with pg43.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM memory_uses WHERE source_id=:source"), {"source": source_id}) == 0


def test_native_child_writer_and_waiting_parent_delete_complete_without_cross_row_trigger_cycle(pg43):
    scope = seed_chat(pg43)
    with pg43.begin() as connection:
        connection.execute(text("UPDATE chat_threads SET active_message_id=:parent WHERE id=:thread"),
                           {"parent": scope.parent_id, "thread": scope.thread_id})
    pids, started = [], Event()
    def delete_parent():
        with pg43.begin() as connection:
            pids.append(connection.scalar(text("SELECT pg_backend_pid()")))
            started.set()
            connection.execute(text("DELETE FROM chat_messages WHERE id=:id"), {"id": scope.parent_id})
    with pg43.connect() as child_writer, ThreadPoolExecutor(max_workers=1) as pool:
        child_writer.execute(text("SELECT id FROM chat_messages WHERE id=:id FOR UPDATE"), {"id": scope.leaf_id})
        blocker_pid = child_writer.scalar(text("SELECT pg_backend_pid()"))
        future = pool.submit(delete_parent)
        try:
            assert started.wait(2)
            wait_for_blocker(child_writer, pids[0], blocker_pid)
            child_writer.execute(text("UPDATE chat_messages SET content='child changed' WHERE id=:id"), {"id": scope.leaf_id})
            child_writer.commit()
        finally:
            child_writer.rollback()
        future.result(timeout=5)
    with pg43.connect() as connection:
        child = connection.execute(text("SELECT content,parent_message_id FROM chat_messages WHERE id=:id"), {"id": scope.leaf_id}).one()
        assert child == ("child changed", None)
        assert connection.scalar(text("SELECT active_message_id FROM chat_threads WHERE id=:id"), {"id": scope.thread_id}) is None



def test_private_instruction_source_rejects_null_owner(pg43):
    scope = seed_chat(pg43)
    with pg43.begin() as connection:
        instruction, request = str(uuid4()), str(uuid4())
        connection.execute(text("""INSERT INTO memory_instructions
            (id,workspace_id,actor_user_id,operation,request_id,content,content_sha256,created_at)
            VALUES (:id,:workspace,:actor,'remember',:request,'fixture',
                encode(sha256(convert_to('fixture','UTF8')),'hex'),now())"""),
            {"id": instruction, "workspace": scope.workspace_id, "actor": scope.user_id, "request": request})
    with pytest.raises(DBAPIError, match="ck_source_identity"):
        with pg43.begin() as connection:
            connection.execute(text("""INSERT INTO memory_sources
                (id,workspace_id,kind,native_id,instruction_id,source_version,native_version,
                 content_sha256,actor_user_id,audience,owner_user_id,state,created_at)
                VALUES (:id,:workspace,'memory_instruction',:instruction,:instruction,1,
                    jsonb_build_object('instructionId',CAST(:instruction AS varchar),'requestId',CAST(:request AS varchar)),
                    encode(sha256(convert_to('fixture','UTF8')),'hex'),:actor,'private',NULL,'current',now())"""),
                {"id": str(uuid4()), "workspace": scope.workspace_id, "instruction": instruction,
                 "request": request, "actor": scope.user_id})


def reject_null_native_field(engine, source_id, field):
    table = Base.metadata.tables["memory_sources"]
    with engine.connect() as connection:
        values = dict(connection.execute(select(table).where(table.c.id == source_id)).mappings().one())
    values.update(id=str(uuid4()), source_version=2, state="stale")
    values["native_version"] = {**values["native_version"], field: None}
    with pytest.raises(DBAPIError, match="ck_source_native_version"):
        with engine.begin() as connection:
            connection.execute(table.insert().values(**values))


@pytest.mark.parametrize("field", ["messageId", "role", "status", "contentSha256", "compactionRevision"])
def test_chat_native_version_rejects_json_null(pg43, field):
    scope = seed_chat(pg43)
    with pg43.begin() as connection:
        source_id = seed_shared_source(connection, scope)
    reject_null_native_field(pg43, source_id, field)


@pytest.mark.parametrize("field", ["runId", "executionSnapshotId", "evidenceSnapshotId", "evidenceHandleId", "sourceFingerprintSha256"])
def test_research_native_version_rejects_json_null(pg43, field):
    from datetime import UTC, datetime
    scope = seed_chat(pg43)
    source_id, handle = str(uuid4()), str(uuid4())
    with pg43.begin() as connection:
        connection.execute(Base.metadata.tables["memory_sources"].insert().values(
            id=source_id, workspace_id=scope.workspace_id, kind="research_evidence", native_id=handle,
            source_version=1, native_version={"runId": str(uuid4()), "executionSnapshotId": str(uuid4()),
                "evidenceSnapshotId": str(uuid4()), "evidenceHandleId": handle, "sourceFingerprintSha256": "a" * 64},
            content_sha256="a" * 64, audience="workspace", state="current", created_at=datetime.now(UTC)))
    reject_null_native_field(pg43, source_id, field)
