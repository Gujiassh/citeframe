"""Direct SQL negatives against shipped deferred compaction integrity predicates."""
from dataclasses import asdict, replace
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from citeframe_memory.compaction.guards import digest
from citeframe_memory.compaction.policy import CompactionError
from citeframe_persistence import Base
from test_compaction_fixture import insert_message, pg43
from test_compaction_repository import adopt, prepared, journal_summary_call


def committed(engine, *, count=1):
    scope,repo,owner,policy,units=prepared(engine)
    receipt=adopt(repo,repo.capture(owner,units,policy),policy,count=count)
    return scope,repo,owner,policy,units,receipt


def owner_state(connection,owner):
    return connection.execute(text("SELECT context_version,checkpoint_id FROM chat_memory_executions WHERE id=:id"),{"id":owner.owner_id}).one()


def other_thread_source(engine,scope,repo,owner,policy):
    user,assistant=str(uuid4()),str(uuid4())
    with engine.begin() as connection:
        insert_message(connection,scope,user,thread_id=scope.other_thread_id)
        insert_message(connection,scope,assistant,thread_id=scope.other_thread_id,parent_id=user)
        connection.execute(text("UPDATE chat_messages SET role='assistant',status='streaming' WHERE id=:id"),{"id":assistant})
        connection.execute(text("UPDATE chat_threads SET active_message_id=NULL WHERE id=:id"),{"id":scope.other_thread_id})
    other=replace(owner,owner_id=str(uuid4()))
    deadline=datetime.fromisoformat(policy["deadlineAt"])
    repo.create_chat(other,thread_id=scope.other_thread_id,user_message_id=user,assistant_message_id=assistant,
        request_id=str(uuid4()),request_sha256="b"*64,policy=policy,deadline_at=deadline,lease_expires_at=deadline)
    return repo.register_source(other,"chat_message",user)


@pytest.mark.parametrize("column,target",[("actor_user_id","other_user_id"),("thread_id","other_thread_id"),
                                           ("workspace_id","other_workspace_id")])
def test_native_pointer_rejects_cross_actor_thread_workspace(pg43,column,target):
    scope,repo,owner,policy,units,receipt=committed(pg43)
    with pytest.raises(DBAPIError):
        with pg43.begin() as connection:
            connection.execute(text(f"UPDATE chat_memory_executions SET {column}=:value WHERE id=:id"),
                               {"value":getattr(scope,target),"id":owner.owner_id})
            connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    with pg43.connect() as connection:
        assert owner_state(connection,owner)==(1,receipt.snapshot_id)


@pytest.mark.parametrize("scope_kind",["thread","workspace"])
def test_coverage_rejects_native_source_from_other_scope(pg43,scope_kind):
    scope,repo,owner,policy,units,receipt=committed(pg43)
    if scope_kind=="thread":
        foreign=other_thread_source(pg43,scope,repo,owner,policy)
    else:
        _,_,_,_,foreign_units=prepared(pg43)
        foreign=foreign_units[0].source
    snapshots=Base.metadata.tables["task_memory_snapshots"]
    coverage=Base.metadata.tables["task_memory_coverage"]
    with pg43.connect() as connection:
        snapshot=dict(connection.execute(select(snapshots).where(snapshots.c.id==receipt.snapshot_id)).mappings().one())
    call, _, _, _ = journal_summary_call(repo, repo.capture(owner, units, policy), policy)
    snapshot.update(id=str(uuid4()),context_version=2,generation_call_id=call,operation_key=digest(["foreign-source",scope_kind]))
    with pytest.raises(DBAPIError,match="compaction_coverage_scope"):
        with pg43.begin() as connection:
            connection.execute(snapshots.insert().values(**snapshot))
            connection.execute(coverage.insert().values(snapshot_id=snapshot["id"],ordinal=0,unit_key="foreign",
                source_id=foreign.source_id,source_version=foreign.version))
            connection.execute(text("UPDATE chat_memory_executions SET checkpoint_id=:snapshot,context_version=2 WHERE id=:id"),
                               {"snapshot":snapshot["id"],"id":owner.owner_id})
            connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    with pg43.connect() as connection:
        assert connection.scalar(text("SELECT source_id FROM task_memory_coverage WHERE snapshot_id=:id"),{"id":receipt.snapshot_id})==units[0].source.source_id


@pytest.mark.parametrize("mutation",["hole","empty"])
def test_committed_coverage_is_immutable(pg43,mutation):
    *_,receipt=committed(pg43)
    with pytest.raises(DBAPIError,match="immutable_compaction_coverage"):
        with pg43.begin() as connection:
            sql="UPDATE task_memory_coverage SET ordinal=2 WHERE snapshot_id=:id" if mutation=="hole" else "DELETE FROM task_memory_coverage WHERE snapshot_id=:id"
            connection.execute(text(sql),{"id":receipt.snapshot_id})
            connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    with pg43.connect() as connection:
        assert connection.execute(text("SELECT ordinal FROM task_memory_coverage WHERE snapshot_id=:id"),{"id":receipt.snapshot_id}).scalars().all()==[0]


def test_new_snapshot_without_native_adoption_is_rejected(pg43):
    scope,repo,owner,policy,units,receipt=committed(pg43)
    snapshots=Base.metadata.tables["task_memory_snapshots"]
    coverage=Base.metadata.tables["task_memory_coverage"]
    with pg43.connect() as connection:
        snapshot=dict(connection.execute(select(snapshots).where(snapshots.c.id==receipt.snapshot_id)).mappings().one())
        covered=dict(connection.execute(select(coverage).where(coverage.c.snapshot_id==receipt.snapshot_id)).mappings().one())
    snapshot.update(id=str(uuid4()),operation_key=digest("orphan-snapshot"))
    covered["snapshot_id"]=snapshot["id"]
    with pytest.raises(DBAPIError,match="compaction_native_pointer_required"):
        with pg43.begin() as connection:
            connection.execute(snapshots.insert().values(**snapshot))
            connection.execute(coverage.insert().values(**covered))
            connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    with pg43.connect() as connection:
        assert owner_state(connection,owner)==(1,receipt.snapshot_id)
        assert connection.scalar(text("SELECT count(*) FROM task_memory_snapshots"))==1


@pytest.mark.parametrize("column,value",[("context_version",0),("checkpoint_id",None)])
def test_owner_cannot_reference_future_snapshot_or_drop_nonzero_pointer(pg43,column,value):
    scope,repo,owner,policy,units,receipt=committed(pg43)
    with pytest.raises(DBAPIError,match="compaction_(pointer_(invalid|missing)|context_regression)"):
        with pg43.begin() as connection:
            connection.execute(text(f"UPDATE chat_memory_executions SET {column}=:value WHERE id=:id"),{"value":value,"id":owner.owner_id})
            connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    with pg43.connect() as connection:
        assert owner_state(connection,owner)==(1,receipt.snapshot_id)


def test_last_good_checkpoint_can_precede_owner_version_and_native_append(pg43):
    scope,repo,owner,policy,units,receipt=committed(pg43)
    with pg43.connect() as connection:
        before=connection.scalar(text("SELECT to_jsonb(s) FROM task_memory_snapshots s WHERE id=:id"),{"id":receipt.snapshot_id})
    appended=str(uuid4())
    with pg43.begin() as connection:
        connection.execute(text("UPDATE chat_memory_executions SET context_version=2 WHERE id=:id"),{"id":owner.owner_id})
        insert_message(connection,scope,appended,parent_id=scope.leaf_id)
        connection.execute(text("UPDATE chat_threads SET active_message_id=:leaf WHERE id=:id"),{"leaf":appended,"id":scope.thread_id})
        connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    with pg43.connect() as connection:
        assert owner_state(connection,owner)==(2,receipt.snapshot_id)
        assert connection.scalar(text("SELECT to_jsonb(s) FROM task_memory_snapshots s WHERE id=:id"),{"id":receipt.snapshot_id})==before
    with pytest.raises(CompactionError, match="context_branch_changed"):
        repo.reconcile(owner, receipt.operation_key)


def test_committed_snapshot_payload_is_immutable(pg43):
    *_,receipt=committed(pg43)
    with pytest.raises(DBAPIError,match="immutable_compaction_snapshot"):
        with pg43.begin() as connection:
            connection.execute(text("UPDATE task_memory_snapshots SET summary='{}'::jsonb WHERE id=:id"),{"id":receipt.snapshot_id})


def test_historical_coverage_cannot_be_silently_tail_truncated(pg43):
    *_,receipt=committed(pg43,count=2)
    with pytest.raises(DBAPIError):
        with pg43.begin() as connection:
            connection.execute(text("DELETE FROM task_memory_coverage WHERE snapshot_id=:id AND ordinal=1"),{"id":receipt.snapshot_id})
            connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


def test_child_snapshot_cannot_regress_parent_covered_prefix(pg43):
    scope,repo,owner,policy,units,receipt=committed(pg43,count=2)
    snapshots=Base.metadata.tables["task_memory_snapshots"]
    coverage=Base.metadata.tables["task_memory_coverage"]
    with pg43.connect() as connection:
        snapshot=dict(connection.execute(select(snapshots).where(snapshots.c.id==receipt.snapshot_id)).mappings().one())
        covered=dict(connection.execute(select(coverage).where(coverage.c.snapshot_id==receipt.snapshot_id,coverage.c.ordinal==0)).mappings().one())
    call, _, _, _ = journal_summary_call(repo, repo.capture(owner, units, policy), policy, count=2)
    snapshot.update(id=str(uuid4()),parent_snapshot_id=receipt.snapshot_id,version=2,context_version=2,
                    generation_call_id=call,manifest_sha256=digest([asdict(units[0])]),operation_key=digest("regressed-snapshot"))
    covered["snapshot_id"]=snapshot["id"]
    with pytest.raises(DBAPIError):
        with pg43.begin() as connection:
            connection.execute(snapshots.insert().values(**snapshot))
            connection.execute(coverage.insert().values(**covered))
            connection.execute(text("UPDATE chat_memory_executions SET checkpoint_id=:snapshot,context_version=2 WHERE id=:id"),
                               {"snapshot":snapshot["id"],"id":owner.owner_id})
            connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    with pg43.connect() as connection:
        assert owner_state(connection,owner)==(1,receipt.snapshot_id)
        assert connection.scalar(text("SELECT count(*) FROM task_memory_snapshots"))==1



@pytest.mark.parametrize("ordinal",[None,2])
def test_new_snapshot_rejects_empty_or_gapped_coverage(pg43,ordinal):
    scope,repo,owner,policy,units,receipt=committed(pg43)
    snapshots=Base.metadata.tables["task_memory_snapshots"]
    coverage=Base.metadata.tables["task_memory_coverage"]
    with pg43.connect() as connection:
        snapshot=dict(connection.execute(select(snapshots).where(snapshots.c.id==receipt.snapshot_id)).mappings().one())
        covered=dict(connection.execute(select(coverage).where(coverage.c.snapshot_id==receipt.snapshot_id)).mappings().one())
    snapshot.update(id=str(uuid4()),parent_snapshot_id=receipt.snapshot_id,version=2,context_version=2,
                    operation_key=digest(["coverage-gap",ordinal]))
    covered.update(snapshot_id=snapshot["id"],ordinal=ordinal)
    with pytest.raises(DBAPIError,match="compaction_coverage_incomplete"):
        with pg43.begin() as connection:
            connection.execute(snapshots.insert().values(**snapshot))
            if ordinal is not None:
                connection.execute(coverage.insert().values(**covered))
            connection.execute(text("UPDATE chat_memory_executions SET checkpoint_id=:snapshot,context_version=2 WHERE id=:id"),
                               {"snapshot":snapshot["id"],"id":owner.owner_id})
            connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


@pytest.mark.parametrize("refresh", ["noop", "invalidation", "timestamp"])
def test_committed_snapshot_refresh_cannot_append_coverage(pg43, refresh):
    scope, repo, owner, policy, units, receipt = committed(pg43)
    with pg43.connect() as connection:
        before = connection.scalar(text("SELECT to_jsonb(s) FROM task_memory_snapshots s WHERE id=:id"), {"id": receipt.snapshot_id})
    updates = {
        "noop": "status=status",
        "invalidation": "status='invalidated',invalidated_at=clock_timestamp()",
        "timestamp": "invalidated_at=clock_timestamp()",
    }
    expected = "compaction_coverage_scope" if refresh == "invalidation" else "compaction_manifest_mismatch"
    with pytest.raises(DBAPIError, match=expected):
        with pg43.begin() as connection:
            connection.execute(text(f"UPDATE task_memory_snapshots SET {updates[refresh]} WHERE id=:id"), {"id": receipt.snapshot_id})
            connection.execute(text("""INSERT INTO task_memory_coverage
                (snapshot_id,ordinal,unit_key,source_id,source_version,parent_message_id)
                VALUES (:snapshot,1,:key,:source,:version,:parent)"""),
                {"snapshot": receipt.snapshot_id, "key": units[1].key,
                 "source": units[1].source.source_id, "version": units[1].source.version,
                 "parent": units[1].parent_message_id})
            connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    with pg43.connect() as connection:
        assert connection.scalar(text("SELECT to_jsonb(s) FROM task_memory_snapshots s WHERE id=:id"), {"id": receipt.snapshot_id}) == before
        assert connection.execute(text("SELECT ordinal,source_id FROM task_memory_coverage WHERE snapshot_id=:id ORDER BY ordinal"), {"id": receipt.snapshot_id}).all() == [(0, units[0].source.source_id)]
        assert owner_state(connection, owner) == (1, receipt.snapshot_id)


@pytest.mark.parametrize("key", ['Unicode: 中文😀é', 'escaped: "quote" \\ slash /', 'control: \b\f\n\r\t\x01\x1f', 'null'])
def test_manifest_digest_matches_canonical_unicode_escaping_and_null_fields(pg43, key):
    scope, repo, owner, policy, units = prepared(pg43)
    units = (replace(units[0], key=key), units[1])
    receipt = adopt(repo, repo.capture(owner, units, policy), policy, count=2)
    with pg43.connect() as connection:
        rows = connection.execute(text("SELECT unit_key,parent_message_id,tool_group_id FROM task_memory_coverage WHERE snapshot_id=:id ORDER BY ordinal"), {"id": receipt.snapshot_id}).all()
        assert rows == [(key, None, None), (units[1].key, scope.parent_id, None)]
        assert owner_state(connection, owner) == (1, receipt.snapshot_id)
    assert repo.reconcile(owner, receipt.operation_key) == receipt


def test_native_context_cannot_regress_while_pointer_remains_valid(pg43):
    scope, repo, owner, policy, units, receipt = committed(pg43)
    with pg43.begin() as connection:
        connection.execute(text("UPDATE chat_memory_executions SET context_version=3 WHERE id=:id"), {"id": owner.owner_id})
    with pytest.raises(DBAPIError, match="compaction_context_regression"):
        with pg43.begin() as connection:
            connection.execute(text("UPDATE chat_memory_executions SET context_version=2 WHERE id=:id"), {"id": owner.owner_id})
            connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    with pg43.connect() as connection:
        assert owner_state(connection, owner) == (3, receipt.snapshot_id)
