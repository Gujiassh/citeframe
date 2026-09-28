"""Prepared-pair authority and native metadata races on real migrated PostgreSQL."""
from dataclasses import asdict
from uuid import uuid4
import pytest
from sqlalchemy import event,text
from citeframe_contracts.memory import GenerationMessage,GenerationRequest
from citeframe_memory.compaction.guards import digest
from test_compaction_call_fixture import FixtureJournal as CallJournal
from citeframe_memory.compaction.policy import CompactionError
from test_compaction_fixture import pg43,insert_message
from test_compaction_repository import prepared,adopt,state


def pair(engine,owner):
    with engine.connect() as db:return db.execute(text("SELECT user_message_id,assistant_message_id FROM chat_memory_executions WHERE id=:id"),{"id":owner.owner_id}).one()


@pytest.mark.parametrize("malformation",["user_role","user_status","assistant_role","assistant_status","assistant_parent","user_workspace","user_thread","cycle"])
def test_invalid_designated_pair_and_ancestry_deny_before_body_reads(pg43,malformation):
    scope,repo,owner,policy,units=prepared(pg43);user,assistant=pair(pg43,owner)
    with pg43.begin() as db:
        if malformation=="user_role":db.execute(text("UPDATE chat_messages SET role='assistant' WHERE id=:id"),{"id":user})
        elif malformation=="user_status":db.execute(text("UPDATE chat_messages SET status='failed' WHERE id=:id"),{"id":user})
        elif malformation=="assistant_role":db.execute(text("UPDATE chat_messages SET role='user' WHERE id=:id"),{"id":assistant})
        elif malformation=="assistant_status":db.execute(text("UPDATE chat_messages SET status='completed' WHERE id=:id"),{"id":assistant})
        elif malformation=="assistant_parent":db.execute(text("UPDATE chat_messages SET parent_message_id=:parent WHERE id=:id"),{"id":assistant,"parent":scope.parent_id})
        elif malformation=="user_workspace":db.execute(text("UPDATE chat_messages SET workspace_id=:other WHERE id=:id"),{"id":user,"other":scope.other_workspace_id})
        elif malformation=="user_thread":db.execute(text("UPDATE chat_messages SET thread_id=:other WHERE id=:id"),{"id":user,"other":scope.other_thread_id})
        else:db.execute(text("UPDATE chat_messages SET parent_message_id=:parent WHERE id=:id"),{"id":scope.parent_id,"parent":user})
    statements=[]
    def track(conn,cursor,statement,params,context,many):statements.append(statement)
    event.listen(pg43,"before_cursor_execute",track)
    try:
        with pytest.raises(CompactionError):repo.register_source(owner,"chat_message",user)
    finally:event.remove(pg43,"before_cursor_execute",track)
    assert not any("chat_messages.content" in statement for statement in statements)
    assert state(pg43,owner)==((0,None),(0,0,0))


@pytest.mark.parametrize("null_anchor",[False,True])
def test_switch_before_first_capture_cannot_rebind_execution(pg43,null_anchor):
    scope,repo,owner,policy,units=prepared(pg43,null_anchor=null_anchor)
    with pg43.begin() as db:db.execute(text("UPDATE chat_threads SET active_message_id=:leaf WHERE id=:id"),{"id":scope.thread_id,"leaf":scope.leaf_id if null_anchor else None})
    with pytest.raises(CompactionError,match="context_branch_changed"):repo.capture(owner,units,policy)
    assert state(pg43,owner)==((0,None),(0,0,0))


@pytest.mark.parametrize("mutation",["null_to_id","id_to_null","leaf_aba","reparent","user_body","assistant_body","assistant_status"])
@pytest.mark.parametrize("stage",["adopt","send"])
def test_native_races_deny_atomic_adoption_and_presend(pg43,mutation,stage):
    scope,repo,owner,policy,units=prepared(pg43,null_anchor=mutation=="null_to_id")
    captured=repo.capture(owner,units,policy);user,assistant=pair(pg43,owner)
    journal=CallJournal(repo)
    if stage=="send":
        receipt=journal.reserve(captured,policy,logical_key="before-race",purpose="main",request_sha256="e"*64,
            input_tokens=20,output_tokens=20,provider="fixture",model="fixture",profile_fingerprint="f"*64)
    with pg43.begin() as db:
        if mutation=="null_to_id":db.execute(text("UPDATE chat_threads SET active_message_id=:leaf WHERE id=:id"),{"id":scope.thread_id,"leaf":scope.leaf_id})
        elif mutation=="id_to_null":db.execute(text("UPDATE chat_threads SET active_message_id=NULL WHERE id=:id"),{"id":scope.thread_id})
        elif mutation=="leaf_aba":
            for leaf in (scope.parent_id,scope.leaf_id):db.execute(text("UPDATE chat_threads SET active_message_id=:leaf WHERE id=:id"),{"id":scope.thread_id,"leaf":leaf})
        elif mutation=="reparent":db.execute(text("UPDATE chat_messages SET parent_message_id=:parent WHERE id=:id"),{"id":user,"parent":scope.parent_id})
        elif mutation=="user_body":db.execute(text("UPDATE chat_messages SET content='changed current question' WHERE id=:id"),{"id":user})
        elif mutation=="assistant_body":db.execute(text("UPDATE chat_messages SET content='STREAMING_BODY_MUST_NOT_ENTER_CONTEXT' WHERE id=:id"),{"id":assistant})
        else:db.execute(text("UPDATE chat_messages SET status='failed' WHERE id=:id"),{"id":assistant})
    with pytest.raises(CompactionError):
        if stage=="adopt":adopt(repo,captured,policy)
        else:journal.mark_sent(captured,policy,receipt)
    with pg43.connect() as db:
        assert db.execute(text("SELECT context_version,checkpoint_id FROM chat_memory_executions WHERE id=:id"),{"id":owner.owner_id}).one()==(0,None)
        assert db.scalar(text("SELECT count(*) FROM task_memory_snapshots"))==0
        assert db.scalar(text("SELECT count(*) FROM memory_calls WHERE state='sent'"))==0


def test_other_pending_pair_and_streaming_assistant_are_metadata_only(pg43):
    scope,repo,owner,policy,units=prepared(pg43);user,assistant=pair(pg43,owner)
    other_user,other_assistant=str(uuid4()),str(uuid4())
    with pg43.begin() as db:
        insert_message(db,scope,other_user,parent_id=scope.leaf_id,content="OTHER_REQUEST_PRIVATE_MARKER")
        insert_message(db,scope,other_assistant,parent_id=other_user,content="OTHER_STREAM_MARKER")
        db.execute(text("UPDATE chat_messages SET role='assistant',status='streaming' WHERE id=:id"),{"id":other_assistant})
        db.execute(text("UPDATE chat_messages SET content='CURRENT_STREAM_MARKER' WHERE id=:id"),{"id":assistant})
    statements=[]
    def track(conn,cursor,statement,params,context,many):statements.append(statement)
    event.listen(pg43,"before_cursor_execute",track)
    try:
        for id_ in (other_user,other_assistant,assistant):
            with pytest.raises(CompactionError,match="source_branch_mismatch"):repo.register_source(owner,"chat_message",id_)
    finally:event.remove(pg43,"before_cursor_execute",track)
    assert not any("chat_messages.content" in statement for statement in statements)
    assert repo.read_source(owner,units[0].source)
