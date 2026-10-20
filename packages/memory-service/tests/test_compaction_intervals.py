"""Repeated same-task interval adoption, exact reload and actual-input provenance."""
from dataclasses import asdict,replace
import copy,json
from sqlalchemy import text
from sqlalchemy.orm import Session
import pytest
from citeframe_contracts.compaction import CoverageUnit,UsageSettlement
from citeframe_contracts.memory import GenerationMessage,GenerationRequest,TextDelta,TurnComplete,Usage,ToolCall,ToolDefinition
from citeframe_memory.compaction.archive import ToolArchive
from citeframe_memory.compaction.gate import DispatchGate
from citeframe_memory.compaction.guards import canonical,digest
from citeframe_memory.compaction.journal import CallJournal
from citeframe_memory.compaction.policy import CompactionError
from citeframe_memory.compaction.repository import CompactionRepository
from citeframe_memory.compaction.summary import ARRAYS
from citeframe_memory.compaction.units import ContextUnit
from test_compaction_fixture import pg43
from test_compaction_gate import Files
from test_compaction_main_question import gate_fixture


class ScopedProvider:
    def __init__(self):self.calls=[]
    def stream_turn(self,request):
        self.calls.append(request)
        value={name:[] for name in ARRAYS};value.update(conflicts=[],progress={})
        if request.purpose=="compact_chunk":
            originals=[json.loads(json.loads(m.content)["sourceUnit"]["messages"][0]["content"])["original"] for m in request.messages[1:]]
            for original in originals:
                ref=original["source"] or {"tool_group_id":original["tool_group_id"]}
                value["facts"].append(dict(key=original["key"],text="37.5 ms; never production; only batch=8",attribution="sourced_observation",sourceRefs=[ref],conditions=["only batch=8"],quantities=[dict(value="37.5",unit="ms",qualifier="only batch=8")],negated=True))
        else:
            chunks=json.loads(request.messages[1].content)["chunkSummaries"]
            value["facts"]=[fact for chunk in chunks for fact in chunk["facts"]]
        yield TextDelta(json.dumps(value));yield Usage(100,200,"reported");yield TurnComplete("answer")


def add_groups(repo,owner,policy,units,archive,start=0,number=2,size=16000):
    for index in range(start,start+number):
        group=ContextUnit("group-"+str(index),"tool_group",(GenerationMessage("assistant","",(ToolCall("call-"+str(index),"read_source","{}"),)),
            GenerationMessage("tool","37.5 ms never production only batch=8 "+"x"*size,tool_call_id="call-"+str(index))), ("succeeded",))
        group_id=archive.persist(repo.capture(owner,units,policy),policy,group,(units[0].source,))
        units=units+(CoverageUnit(group.key,tool_group_id=group_id),)
    return units


def process_reload(engine,repo,owner,policy,units,template,path,protocol,version):
    import os,subprocess,sys
    from pathlib import Path
    with engine.connect() as db:schema=db.scalar(text("SELECT current_schema()"))
    payload=dict(schema=schema,owner=asdict(owner),policy=policy,units=[asdict(u) for u in units],
        template=asdict(template),path=str(path),protocol=protocol,now=repo.clock().isoformat(),version=version)
    script=r"""
import json,sys,os
from pathlib import Path
from dataclasses import asdict
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from citeframe_contracts.compaction import ContextOwner,CoverageUnit,SourceReference
from citeframe_contracts.memory import GenerationRequest,GenerationMessage,ToolDefinition
from citeframe_memory.compaction.repository import CompactionRepository
from citeframe_memory.compaction.gate import DispatchGate
from citeframe_memory.compaction.journal import CallJournal
from citeframe_memory.compaction.archive import ToolArchive
from citeframe_memory.compaction.policy import CompactionPolicy
from citeframe_memory.compaction.guards import canonical
from test_compaction_native_packing import native_counter
from test_compaction_gate import Files
p=json.load(sys.stdin)
e=create_engine(os.environ['CITEFRAME_MEMORY43_POSTGRES_URL'],connect_args={'options':'-c search_path='+p['schema']+',public'})
r=CompactionRepository(lambda:Session(e),clock=lambda:datetime.fromisoformat(p['now']))
owner=ContextOwner(**p['owner']);units=tuple(CoverageUnit(u['key'],SourceReference(**u['source']) if u['source'] else None,u['tool_group_id'],u['parent_message_id']) for u in p['units'])
t=p['template'];request=GenerationRequest(tuple(GenerationMessage(**m) for m in t['messages']),t['max_output_tokens'],tools=tuple(ToolDefinition(**tool) for tool in t['tools']))
connection,counter,identity=native_counter(p['protocol'],context=8000,output=1000)
class Forbidden:
 def stream_turn(self,request):raise AssertionError('reload replayed provider')
store=Files(Path(p['path']));gate=DispatchGate(r,CallJournal(r,object_store=store),Forbidden(),counter,connection,identity,input_ceiling=5500,archive=ToolArchive(r,store),policy=CompactionPolicy(min_new_tokens=1,min_gain_tokens=1,soft_ratio=.6,target_ratio=.4))
permit=gate.prepare_main_dispatch(owner,request,units,p['policy'],expected_context_version=p['version'],logical_key='process-resume',mode='resume',recent_units=0)
gate.authorize_send(permit,p['policy'])
print(canonical(asdict(permit.request)))
e.dispose()
"""
    env=os.environ.copy();env['PYTHONPATH']=env.get('PYTHONPATH','')+os.pathsep+str(Path(__file__).parent)
    result=subprocess.run([sys.executable,'-c',script],input=json.dumps(payload),text=True,capture_output=True,env=env,timeout=60)
    assert result.returncode==0,result.stderr
    return result.stdout.strip()


@pytest.mark.parametrize("protocol",["openai_responses","openai_chat_completions","anthropic"])
def test_same_question_two_tool_episodes_exact_reloaded_rendering(pg43,tmp_path,protocol):
    scope,repo,owner,policy,units,gate,_,archive=gate_fixture(pg43,tmp_path,protocol)
    originals=[repo.read_source(owner,u.source) for u in units]
    provider=ScopedProvider();gate.generation=provider
    units=add_groups(repo,owner,policy,units,archive)
    template=GenerationRequest((GenerationMessage("system","trusted"),),1000,tools=(ToolDefinition("read_source","Read",'{"type":"object"}'),))
    first=gate.prepare_main_dispatch(owner,template,units,policy,expected_context_version=0,logical_key="episode1",recent_units=0)
    assert first.disposition=="compacted"
    gate.authorize_send(first,policy);gate.journal.settle(first.receipt,UsageSettlement("succeeded",50,20,"reported"))
    units=add_groups(repo,owner,policy,units,archive,start=2)
    second=gate.prepare_main_dispatch(owner,template,units,policy,expected_context_version=1,logical_key="episode2",recent_units=0)
    assert second.disposition=="compacted"
    assert second.request.messages[:4]==first.request.messages[:4]
    assert second.request.messages[3]==GenerationMessage("user","current request")
    assert len(provider.calls)>=3 and provider.calls[-1].purpose=="compact_merge"
    before=canonical(asdict(second.request))
    assert process_reload(pg43,repo,owner,policy,units,template,tmp_path,protocol,2)==before
    fresh=CompactionRepository(lambda:Session(pg43),clock=repo.clock)
    journal=CallJournal(fresh,object_store=Files(tmp_path))
    restored=DispatchGate(fresh,journal,provider,gate.counter,gate.connection,gate.identity,
        policy=gate.policy,input_ceiling=gate.ceiling,archive=ToolArchive(fresh,Files(tmp_path)))
    count=len(provider.calls)
    resumed=restored.prepare_main_dispatch(owner,template,units,policy,expected_context_version=2,logical_key="resume",recent_units=0,mode="resume")
    assert canonical(asdict(resumed.request))==before and len(provider.calls)==count
    restored.authorize_send(resumed,policy)
    with pg43.connect() as db:
        rows=db.execute(text("SELECT ordinal,unit_key FROM task_memory_coverage WHERE snapshot_id=:id ORDER BY ordinal"),{"id":second.checkpoint_id}).all()
        assert rows==list(enumerate(u.key for u in units))
        calls=db.execute(text("SELECT input_manifest,result_manifest FROM memory_calls WHERE purpose IN ('compact_chunk','compact_merge') AND result_state='valid' ORDER BY created_at")).all()
        assert all(c[0]["compactionPlan"]["intervalStart"]==3 for c in calls)
        assert any(not c[1]["finalEligible"] for c in calls)
    assert [repo.read_source(owner,u.source) for u in units[:3]]==originals


@pytest.mark.parametrize("bad_ref",["protected","sibling_chunk"])
def test_chunk_support_cannot_use_prefix_or_sibling(pg43,tmp_path,bad_ref):
    scope,repo,owner,policy,units,gate,_,archive=gate_fixture(pg43,tmp_path)
    units=add_groups(repo,owner,policy,units,archive)
    class Invalid(ScopedProvider):
        def stream_turn(self,request):
            for event in super().stream_turn(request):
                if isinstance(event,TextDelta):
                    value=json.loads(event.text)
                    value["facts"][0]["sourceRefs"]=[asdict(units[2].source)] if bad_ref=="protected" else [{"tool_group_id":units[-1].tool_group_id}]
                    yield TextDelta(json.dumps(value))
                else:yield event
    gate.generation=Invalid()
    with pytest.raises(CompactionError,match="context_limit_exceeded"):
        gate.prepare_main_dispatch(owner,GenerationRequest((GenerationMessage("system","trusted"),),1000,tools=(ToolDefinition("read_source","Read",'{"type":"object"}'),)),units,policy,expected_context_version=0,logical_key="bad",recent_units=0)
    with pg43.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM task_memory_snapshots"))==0
        assert db.scalar(text("SELECT count(*) FROM memory_calls WHERE purpose='main'"))==0


def test_disjoint_intervals_keep_interior_protected_complete_group_on_process_reload(pg43,tmp_path):
    scope,repo,owner,policy,units,gate,_,archive=gate_fixture(pg43,tmp_path)
    gate.generation=ScopedProvider()
    template=GenerationRequest((GenerationMessage("system","trusted"),),1000,tools=(ToolDefinition("read_source","Read",'{"type":"object"}'),))
    units=add_groups(repo,owner,policy,units,archive)
    first=gate.prepare_main_dispatch(owner,template,units,policy,expected_context_version=0,logical_key="disjoint1",recent_units=0)
    assert first.disposition=="compacted"
    units=add_groups(repo,owner,policy,units,archive,start=2,number=1,size=50)
    anchor=units[-1]
    units=add_groups(repo,owner,policy,units,archive,start=3)
    second=gate.prepare_main_dispatch(owner,template,units,policy,expected_context_version=1,logical_key="disjoint2",recent_units=0,protected_keys=frozenset((anchor.key,)))
    assert second.disposition=="compacted"
    intervals,protected,frontier=repo.checkpoint_intervals(second.captured,policy)
    assert [(a,b) for a,b,_ in intervals]==[(3,5),(6,8)] and frontier==8 and anchor.key in protected
    assert second.request.messages[4]==first.request.messages[4]
    assert second.request.messages[5:7]==archive.read(owner,anchor.tool_group_id).messages
    assert process_reload(pg43,repo,owner,policy,units,template,tmp_path,"openai_responses",2)==canonical(asdict(second.request))


def test_no_progress_is_profile_specific_without_replaying_known_call(pg43,tmp_path):
    scope,repo,owner,policy,units,gate,provider,archive=gate_fixture(pg43,tmp_path)
    with pg43.begin() as db:db.execute(text("UPDATE chat_messages SET content=:body WHERE id=:id"),{"id":scope.parent_id,"body":"history "*2000})
    units=(replace(units[0],source=repo.register_source(owner,"chat_message",scope.parent_id)),*units[1:])
    original=provider.result["facts"][0];original["sourceRefs"]=[asdict(units[0].source)]
    provider.result["facts"]=[dict(copy.deepcopy(original),key="fact"+str(i),text="z"*1800) for i in range(8)]
    template=GenerationRequest((GenerationMessage("system","trusted"),),1000)
    first=gate.prepare_main_dispatch(owner,template,units,policy,expected_context_version=0,logical_key="no-gain1",recent_units=0)
    assert first.disposition=="target_not_reached" and len(provider.calls)==1
    second=gate.prepare_main_dispatch(owner,template,units,policy,expected_context_version=0,logical_key="no-gain2",recent_units=0)
    assert len(provider.calls)==1
    gate.ceiling+=1
    third=gate.prepare_main_dispatch(owner,template,units,policy,expected_context_version=0,logical_key="new-profile",recent_units=0)
    assert third.disposition=="dispatch_binding_changed" and len(provider.calls)==1
    with pg43.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM memory_calls WHERE no_progress_boundary_sha256 IS NOT NULL"))==2
        assert db.scalar(text("SELECT count(*) FROM memory_calls WHERE purpose='compact_chunk' AND result_state='valid'"))==1


def test_committed_history_retains_generation_profile_and_recounts_new_request(pg43,tmp_path):
    scope,repo,owner,policy,units,gate,_,archive=gate_fixture(pg43,tmp_path)
    provider=ScopedProvider();gate.generation=provider
    units=add_groups(repo,owner,policy,units,archive)
    template=GenerationRequest((GenerationMessage("system","trusted"),),1000,tools=(ToolDefinition("read_source","Read",'{"type":"object"}'),))
    first=gate.prepare_main_dispatch(owner,template,units,policy,expected_context_version=0,logical_key="old-profile",recent_units=0)
    assert first.disposition=="compacted"
    with pg43.connect() as db:old=db.scalar(text("SELECT input_manifest FROM memory_calls WHERE id=(SELECT generation_call_id FROM task_memory_snapshots WHERE id=:id)"),{"id":first.checkpoint_id})
    calls=len(provider.calls);gate.ceiling+=50
    resumed=gate.prepare_main_dispatch(owner,template,units,policy,expected_context_version=1,logical_key="new-current-profile",recent_units=0)
    gate.authorize_send(resumed,policy)
    assert len(provider.calls)==calls and resumed.request==first.request
    with pg43.connect() as db:
        assert old==db.scalar(text("SELECT input_manifest FROM memory_calls WHERE id=(SELECT generation_call_id FROM task_memory_snapshots WHERE id=:id)"),{"id":first.checkpoint_id})
        current=db.scalar(text("SELECT input_manifest FROM memory_calls WHERE id=:id"),{"id":resumed.receipt.call_id})
        assert current["dispatchProfile"]["inputCeiling"]==old["dispatchProfile"]["inputCeiling"]+50


def test_profile_drift_cannot_replay_unknown_summary(pg43,tmp_path):
    scope,repo,owner,policy,units,gate,provider,archive=gate_fixture(pg43,tmp_path)
    with pg43.begin() as db:db.execute(text("UPDATE chat_messages SET content=:body WHERE id=:id"),{"id":scope.parent_id,"body":"history "*2000})
    units=(replace(units[0],source=repo.register_source(owner,"chat_message",scope.parent_id)),*units[1:])
    calls=[]
    class Unknown:
        def stream_turn(self,request):
            calls.append(request)
            raise RuntimeError("transport lost after remote acceptance")
    gate.generation=Unknown();template=GenerationRequest((GenerationMessage("system","trusted"),),1000)
    first=gate.prepare_main_dispatch(owner,template,units,policy,expected_context_version=0,logical_key="unknown1",recent_units=0)
    assert first.disposition=="summary_outcome_unknown" and len(calls)==1
    gate.ceiling+=1
    changed=gate.prepare_main_dispatch(owner,template,units,policy,expected_context_version=0,logical_key="unknown2",recent_units=0)
    assert changed.disposition=="dispatch_binding_changed" and len(calls)==1
    with pg43.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM memory_calls WHERE purpose='compact_chunk' AND state='outcome_unknown'"))==1
        assert db.scalar(text("SELECT count(*) FROM task_memory_snapshots"))==0


def test_missing_result_provenance_refuses_live_reload_without_new_effects(pg43,tmp_path):
    scope,repo,owner,policy,units,gate,_,archive=gate_fixture(pg43,tmp_path)
    gate.generation=ScopedProvider();units=add_groups(repo,owner,policy,units,archive)
    template=GenerationRequest((GenerationMessage("system","trusted"),),1000,tools=(ToolDefinition("read_source","Read",'{"type":"object"}'),))
    first=gate.prepare_main_dispatch(owner,template,units,policy,expected_context_version=0,logical_key="committed",recent_units=0)
    assert first.disposition=="compacted"
    with pg43.begin() as db:
        db.execute(text("UPDATE memory_calls SET result_state='erased',result_manifest=NULL,result_sha256=NULL WHERE id=(SELECT generation_call_id FROM task_memory_snapshots WHERE id=:id)"),{"id":first.checkpoint_id})
        assert db.scalar(text("SELECT compaction_snapshot_chat_owner(:id)"),{"id":first.checkpoint_id})==owner.owner_id
        before=db.scalar(text("SELECT count(*) FROM memory_calls"))
    with pytest.raises(CompactionError,match="checkpoint_rendering_metadata_required"):
        gate.prepare_main_dispatch(owner,template,units,policy,expected_context_version=1,logical_key="no-provenance",recent_units=0,mode="resume")
    with pg43.connect() as db:assert db.scalar(text("SELECT count(*) FROM memory_calls"))==before
