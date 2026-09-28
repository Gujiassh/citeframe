"""Actual long-ancestry capture/adoption and explicit configured-cap rejection."""
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import uuid4

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from citeframe_contracts.compaction import ContextOwner, CoverageUnit, SourceReference
from citeframe_memory.compaction.guards import GuardLimits, body_hash, canonical
from citeframe_memory.compaction.policy import CompactionError
from citeframe_memory.compaction.repository import CompactionRepository
from citeframe_persistence import Base
from test_compaction_fixture import pg43, seed_chat
from test_compaction_repository import adopt


def ancestry_fixture(engine,total):
    scope=seed_chat(engine)
    now=datetime.now(UTC)
    ids=[scope.parent_id,scope.leaf_id]+[str(uuid4()) for _ in range(total-2)]
    messages=Base.metadata.tables["chat_messages"]
    sources=Base.metadata.tables["memory_sources"]
    with engine.begin() as connection:
        connection.execute(text("UPDATE chat_messages SET role='assistant' WHERE id=:id"),{"id":scope.leaf_id})
        connection.execute(messages.insert(),[
            dict(id=ids[i],workspace_id=scope.workspace_id,thread_id=scope.thread_id,parent_message_id=ids[i-1],
                 role="user" if i%2==0 else "assistant",content=f"Source {i}: only batch=8; never production.",
                 status="streaming" if i==total-1 else "completed",created_at=now) for i in range(2,total)])
        connection.execute(text("UPDATE chat_threads SET active_message_id=:leaf WHERE id=:id"),{"leaf":ids[-3],"id":scope.thread_id})
        rows={row["id"]:row for row in connection.execute(select(messages).where(messages.c.thread_id==scope.thread_id)).mappings()}
        registry=[];units=[]
        for i,id_ in enumerate(ids[:-1]):
            row=rows[id_];source_id=str(uuid4());sha=body_hash(row["content"])
            registry.append(dict(id=source_id,workspace_id=scope.workspace_id,kind="chat_message",native_id=id_,
                source_version=row["compaction_revision"],native_version=dict(messageId=id_,parentMessageId=row["parent_message_id"],
                    role=row["role"],status=row["status"],contentSha256=sha,compactionRevision=row["compaction_revision"]),
                content_sha256=sha,audience="workspace",state="current",created_at=now))
            units.append(CoverageUnit(f"message-{i}",SourceReference(source_id,row["compaction_revision"],sha),
                                      parent_message_id=row["parent_message_id"]))
        connection.execute(sources.insert(),registry)
    transactions=[]
    def sessions():
        db=Session(engine)
        started=[]
        event.listen(db,"after_begin",lambda *args:started.append(perf_counter()))
        def ended(*args):
            if started: transactions.append((perf_counter()-started.pop(0))*1000)
        event.listen(db,"after_commit",ended)
        event.listen(db,"after_rollback",ended)
        return db
    repo=CompactionRepository(sessions,clock=lambda:now)
    owner=ContextOwner(scope.workspace_id,scope.user_id,"chat",str(uuid4()),"a"*64)
    deadline=now+timedelta(hours=1)
    policy=dict(schemaVersion="compaction-policy-v1",maxCalls=100,maxInputTokens=100000,maxOutputTokens=10000,
                maxSummaryCalls=20,maxEpisodes=4,deadlineAt=deadline.isoformat())
    repo.create_chat(owner,thread_id=scope.thread_id,user_message_id=ids[-2],assistant_message_id=ids[-1],
        request_id=str(uuid4()),request_sha256="b"*64,policy=policy,deadline_at=deadline,lease_expires_at=deadline)
    transactions.clear()
    return scope,repo,owner,policy,tuple(units),transactions


@pytest.mark.parametrize("total",[128,1024])
def test_actual_long_branch_capture_and_adoption_or_explicit_manifest_limit(pg43,total):
    scope,repo,owner,policy,units,transactions=ancestry_fixture(pg43,total)
    limits=GuardLimits()
    assert limits.max_thread_rows==1024 and limits.max_manifest_bytes==131072 and limits.transaction_timeout_ms==5000
    unit_bytes=len(canonical([asdict(unit) for unit in units]).encode())
    with pg43.connect() as connection:
        native_rows=[list(row) for row in connection.execute(text("""SELECT id,compaction_revision
            FROM chat_messages WHERE thread_id=:id ORDER BY id"""),{"id":scope.thread_id})]
    native_bytes=len(canonical(native_rows).encode())
    assert len(native_rows)==total and native_bytes<=limits.max_manifest_bytes
    if unit_bytes>131072:
        with pytest.raises(CompactionError,match="context_too_large"):
            repo.capture(owner,units,policy)
        with pg43.connect() as connection:
            assert connection.execute(text("SELECT context_version,checkpoint_id FROM chat_memory_executions WHERE id=:id"),{"id":owner.owner_id}).one()==(0,None)
            for table in ("task_memory_snapshots","task_memory_coverage","memory_uses","memory_calls"):
                assert connection.scalar(text("SELECT count(*) FROM "+table))==0
        outcome="explicit_unit_manifest_limit"
    else:
        captured=repo.capture(owner,units,policy)
        receipt=adopt(repo,captured,policy,count=len(units))
        with pg43.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM task_memory_coverage WHERE snapshot_id=:id"),{"id":receipt.snapshot_id})==len(units)
            assert connection.execute(text("SELECT context_version,checkpoint_id FROM chat_memory_executions WHERE id=:id"),{"id":owner.owner_id}).one()==(1,receipt.snapshot_id)
        outcome="captured_and_adopted"
    with pg43.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM chat_messages WHERE thread_id=:id"),{"id":scope.thread_id})==total
        assert connection.scalar(text("SELECT count(*) FROM memory_sources"))==total-1
    assert transactions and all(milliseconds<5000 for milliseconds in transactions)
    print(f"long_branch_rows={total} native_tuple_bytes={native_bytes} unit_manifest_bytes={unit_bytes} "
          f"transaction_ms={[round(value,3) for value in transactions]} outcome={outcome}")

