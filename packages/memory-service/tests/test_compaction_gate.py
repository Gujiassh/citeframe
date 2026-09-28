"""Deterministic provider with real journals/checkpoints; no live model or app integration."""
from dataclasses import asdict, replace
import json
from pathlib import Path

import pytest
from sqlalchemy import text
from citeframe_contracts.compaction import CoverageUnit
from citeframe_contracts.memory import GenerationMessage,GenerationRequest,ModelConnectionSnapshot,TextDelta,TokenCount,TurnComplete,Usage,ToolCall
from citeframe_memory.compaction.archive import ToolArchive
from citeframe_memory.compaction.gate import DispatchGate
from citeframe_memory.compaction.journal import CallJournal
from citeframe_memory.compaction.policy import CompactionError,CompactionPolicy,CounterIdentity
from citeframe_memory.compaction.units import ContextUnit
from test_compaction_fixture import pg43
from test_compaction_repository import prepared,summary


class Counter:
    def count(self,request,connection):
        return TokenCount(sum(len(m.content)+10 for m in request.messages)+20,"estimated","fixture","v1",connection.config_fingerprint)


class Provider:
    def __init__(self,result):self.result=result;self.calls=[]
    def stream_turn(self,request):
        self.calls.append(request)
        yield TextDelta(json.dumps(self.result));yield Usage(100,200,"reported");yield TurnComplete("answer")


class Files:
    def __init__(self,path):self.path=path
    def put(self,key,body):
        p=self.path/key;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body)
    def get(self,key):return (self.path/key).read_bytes()
    def delete(self,key):(self.path/key).unlink()


def prepared_main(engine, **kwargs):
    scope, repo, owner, policy, units = prepared(engine, **kwargs)
    with engine.connect() as db:
        current = db.scalar(text("SELECT user_message_id FROM chat_memory_executions WHERE id=:id"), {"id": owner.owner_id})
    source = repo.register_source(owner, "chat_message", current)
    return scope, repo, owner, policy, units + (CoverageUnit("current", source, parent_message_id=scope.leaf_id),)


def test_automatic_gate_compacts_and_gates_continuation_role_resume(pg43,tmp_path):
    scope,repo,owner,policy,units=prepared_main(pg43)
    with pg43.begin() as c:
        c.execute(text("UPDATE chat_messages SET content=:body WHERE id=:id"),{"body":"37.5 ms never production only batch=8. "*400,"id":scope.parent_id})
    units=(replace(units[0],source=repo.register_source(owner,"chat_message",scope.parent_id)),*units[1:])
    provider=Provider(summary(units));journal=CallJournal(repo,object_store=Files(tmp_path))
    connection=ModelConnectionSnapshot("openai_responses","https://fixture.invalid","fixture","unused",10,"f"*64,25000,2048)
    gate=DispatchGate(repo,journal,provider,Counter(),connection,CounterIdentity("fixture","v1","estimated","f"*64),
        input_ceiling=22000,policy=CompactionPolicy(soft_ratio=.6,target_ratio=.4,min_new_tokens=1,min_gain_tokens=1))
    template=GenerationRequest((GenerationMessage("system","trusted"),),2048)
    permit=gate.prepare_main_dispatch(owner,template,units,policy,expected_context_version=0,logical_key="main0",recent_units=1)
    assert permit.disposition=="compacted" and permit.checkpoint_id
    assert all(r.purpose in ("compact_chunk","compact_merge") and not r.tools for r in provider.calls)
    assert gate.authorize_send(permit,policy)==permit.request
    for mode in ("continuation","role","resume"):
        next_=gate.prepare_main_dispatch(owner,template,units,policy,expected_context_version=1,logical_key=mode,mode=mode)
        assert next_.captured.owner==owner and next_.checkpoint_id==permit.checkpoint_id
        gate.authorize_send(next_,policy)
    assert len(provider.calls)==1
    with pg43.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM memory_calls WHERE purpose='main' AND state='sent'"))==4
        assert c.scalar(text("SELECT count(*) FROM task_memory_snapshots"))==1
        assert c.scalar(text("SELECT count(*) FROM chat_memory_executions"))==1


def test_tool_archive_exact_oversized_original_and_atomic_raw_uses(pg43,tmp_path):
    scope,repo,owner,policy,units=prepared(pg43);capture=repo.capture(owner,units,policy)
    archive=ToolArchive(repo,Files(tmp_path))
    tail="precise tail否定37.5ms";body="x"*10000+tail
    group=ContextUnit("group","tool_group",(GenerationMessage("assistant","",(ToolCall("a","read_source","{}"),ToolCall("b","read_source","{}"))),
        GenerationMessage("tool",body,tool_call_id="a"),GenerationMessage("tool","failed",tool_call_id="b")),("succeeded","failed"))
    id_=archive.persist(capture,policy,group,(units[0].source,))
    assert archive.read_range(owner,id_,"a",start=10000,end=len(body))==tail
    assert archive.read(owner,id_)==group
    coverage=units+(CoverageUnit("group",tool_group_id=id_),)
    updated=repo.capture(owner,coverage,policy)
    from test_compaction_repository import adopt
    receipt=adopt(repo,updated,policy,count=3,store=Files(tmp_path))
    with pg43.connect() as c:
        targets=c.execute(text("SELECT source_id,used_tool_call_id FROM memory_uses WHERE consumer_snapshot_id=:id"),{"id":receipt.snapshot_id}).all()
        assert (units[0].source.source_id,None) in targets and (None,id_) in targets
    assert archive.persist(repo.capture(owner,coverage,policy),policy,group,(units[0].source,))==id_


def test_archive_failure_and_size_bounds_never_commit_complete_group(pg43,tmp_path):
    scope,repo,owner,policy,units=prepared(pg43);capture=repo.capture(owner,units,policy)
    group=ContextUnit("group","tool_group",(GenerationMessage("assistant","",(ToolCall("a","read_source","{}"),)),
        GenerationMessage("tool","original",tool_call_id="a")),("succeeded",))
    class Broken(Files):
        def get(self,key):return b"corrupt"
    archive=ToolArchive(repo,Broken(tmp_path))
    with pytest.raises(CompactionError,match="tool_archive_failed"):archive.persist(capture,policy,group,(units[0].source,))
    with pg43.connect() as c:
        assert c.execute(text("SELECT state,result_state FROM memory_calls")).one()==("failed","absent")
    with pytest.raises(CompactionError,match="tool_archive_limit"):
        ToolArchive(repo,Files(tmp_path),max_result_bytes=10).persist(capture,policy,group,(units[0].source,))



@pytest.mark.parametrize("failure",["invalid","unknown","no_gain"])
def test_failed_or_no_gain_frontier_is_durable_and_not_repeated(pg43,failure,tmp_path):
    scope,repo,owner,policy,units=prepared_main(pg43)
    with pg43.begin() as c:
        c.execute(text("UPDATE chat_messages SET content=:body WHERE id=:id"),{"body":"history "*1700,"id":scope.parent_id})
    units=(replace(units[0],source=repo.register_source(owner,"chat_message",scope.parent_id)),*units[1:])
    value=summary(units)
    if failure=="invalid":value={"not":"task-memory-v2"}
    if failure=="no_gain":
        value["facts"]=[]
        for index in range(10):
            atom=summary(units)["facts"][0];atom["key"]=str(index);atom["text"]="x"*1800;value["facts"].append(atom)
    class Failing(Provider):
        def stream_turn(self,request):
            self.calls.append(request)
            yield TextDelta(json.dumps(self.result))
            if failure!="unknown":yield TurnComplete("answer")
    provider=Failing(value)
    connection=ModelConnectionSnapshot("openai_responses","https://fixture.invalid","fixture","unused",10,"f"*64,25000,2048)
    gate=DispatchGate(repo,CallJournal(repo,object_store=Files(tmp_path)),provider,Counter(),connection,CounterIdentity("fixture","v1","estimated","f"*64),
        input_ceiling=22000,policy=CompactionPolicy(soft_ratio=.6,target_ratio=.4,min_new_tokens=1,min_gain_tokens=1))
    template=GenerationRequest((GenerationMessage("system","trusted"),),2048)
    one=gate.prepare_main_dispatch(owner,template,units,policy,expected_context_version=0,logical_key="first")
    assert one.checkpoint_id is None and one.disposition!="compacted"
    two=gate.prepare_main_dispatch(owner,template,units,policy,expected_context_version=0,logical_key="second",mode="resume")
    assert two.checkpoint_id is None and len(provider.calls)==1
    with pg43.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM task_memory_snapshots"))==0
        assert c.scalar(text("SELECT count(*) FROM memory_calls WHERE no_progress_boundary_sha256 IS NOT NULL"))==1


def test_hard_overflow_and_cancel_never_emit_main_permit(pg43,tmp_path):
    scope,repo,owner,policy,units=prepared_main(pg43)
    connection=ModelConnectionSnapshot("openai_responses","https://fixture.invalid","fixture","unused",10,"f"*64,1000,100)
    provider=Provider(summary(units))
    gate=DispatchGate(repo,CallJournal(repo,object_store=Files(tmp_path)),provider,Counter(),connection,CounterIdentity("fixture","v1","estimated","f"*64),input_ceiling=800)
    template=GenerationRequest((GenerationMessage("system","mandatory"*150),),100)
    with pytest.raises(CompactionError,match="context_limit_exceeded"):
        gate.prepare_main_dispatch(owner,template,units,policy,expected_context_version=0,logical_key="main")
    assert not provider.calls
    gate.cancelled=lambda:True
    with pytest.raises(CompactionError,match="context_cancelled"):
        gate.prepare_main_dispatch(owner,GenerationRequest((),100),units,policy,expected_context_version=0,logical_key="cancel")
    with pg43.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM memory_calls WHERE purpose='main'"))==0


@pytest.mark.parametrize("change",["membership","source_delete","cancel"])
def test_inflight_generation_revocation_never_adopts_or_reserves_main(pg43,change,tmp_path):
    scope,repo,owner,policy,units=prepared_main(pg43)
    with pg43.begin() as db:
        db.execute(text("UPDATE chat_messages SET content=:body WHERE id=:id"),{"body":"history "*1700,"id":scope.parent_id})
    units=(replace(units[0],source=repo.register_source(owner,"chat_message",scope.parent_id)),*units[1:])
    class Revoker(Provider):
        def stream_turn(self,request):
            self.calls.append(request)
            with pg43.begin() as db:
                if change=="membership":db.execute(text("DELETE FROM workspace_memberships WHERE id=:id"),{"id":scope.membership_id})
                elif change=="cancel":db.execute(text("UPDATE chat_memory_executions SET cancel_requested_at=now() WHERE id=:id"),{"id":owner.owner_id})
                else:db.execute(text("UPDATE memory_sources SET state='stale',invalidated_at=now() WHERE id=:id"),{"id":units[0].source.source_id})
            yield TextDelta(json.dumps(self.result));yield Usage(100,200,"reported");yield TurnComplete("answer")
    provider=Revoker(summary(units))
    connection=ModelConnectionSnapshot("openai_responses","https://fixture.invalid","fixture","unused",10,"f"*64,25000,2048)
    gate=DispatchGate(repo,CallJournal(repo,object_store=Files(tmp_path)),provider,Counter(),connection,CounterIdentity("fixture","v1","estimated","f"*64),
        input_ceiling=22000,policy=CompactionPolicy(soft_ratio=.6,target_ratio=.4,min_new_tokens=1,min_gain_tokens=1))
    with pytest.raises(CompactionError):gate.prepare_main_dispatch(owner,GenerationRequest((),2048),units,policy,expected_context_version=0,logical_key="denied")
    with pg43.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM task_memory_snapshots"))==0
        assert db.scalar(text("SELECT count(*) FROM memory_calls WHERE purpose='main'"))==0
        assert db.execute(text("SELECT state,actual_input,actual_output FROM memory_calls WHERE purpose='compact_chunk'")).one()==("succeeded",100,200)


@pytest.mark.parametrize("protocol",["openai_responses","openai_chat_completions","anthropic"])
@pytest.mark.parametrize("change",["physical_context","output_reserve","configured_ceiling"])
def test_native_send_rechecks_current_physical_and_configured_capacity(pg43,tmp_path,protocol,change):
    from test_compaction_native_packing import native_counter
    scope,repo,owner,policy,units=prepared_main(pg43)
    connection,counter,identity=native_counter(protocol,context=8000,output=1000)
    journal=CallJournal(repo,object_store=Files(tmp_path))
    gate=DispatchGate(repo,journal,Provider(summary(units)),counter,connection,identity,input_ceiling=7000)
    permit=gate.prepare_main_dispatch(owner,GenerationRequest((GenerationMessage("system","mandatory trusted prefix "+"x"*300),),100),units,policy,
        expected_context_version=0,logical_key="bound-main")
    newer,newcounter,newidentity=native_counter(protocol,context=120 if change=="physical_context" else 8000,
        output=50 if change=="output_reserve" else 1000)
    changed=DispatchGate(repo,journal,Provider(summary(units)),newcounter,newer,newidentity,
        input_ceiling=20 if change=="configured_ceiling" else 7000)
    with pytest.raises(CompactionError,match="invalid_capacity_reserve" if change=="output_reserve" else "context_limit_exceeded"):
        changed.authorize_send(permit,policy)
    with pg43.connect() as db:assert db.execute(text("SELECT state,request_object_key FROM memory_calls WHERE id=:id"),{"id":permit.receipt.call_id}).one()==("reserved",None)
    assert not list(tmp_path.rglob("*"))
