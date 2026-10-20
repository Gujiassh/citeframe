"""Explicit deterministic dispatch profiles for low-level journal accounting oracles."""
from dataclasses import asdict
from citeframe_memory.compaction.journal import CallJournal
from citeframe_memory.compaction.policy import CompactionPolicy


def profile(provider="fixture",model="fixture",fingerprint="f"*64):
    return dict(schemaVersion="compaction-dispatch-profile-v1",provider=provider,protocol="openai_responses",model=model,
        configFingerprint=fingerprint,contextWindowTokens=100000,maxOutputTokens=10000,inputCeiling=90000,safetyMargin=0,
        counter=dict(counter_id="fixture",counter_version="v1",mode="estimated",config_fingerprint=fingerprint),watermarks=asdict(CompactionPolicy()))


class FixtureJournal(CallJournal):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.bindings={}

    def reserve(self,captured,policy,**kwargs):
        kwargs.setdefault("dispatch_profile",profile(kwargs["provider"],kwargs["model"],kwargs["profile_fingerprint"]))
        if kwargs["purpose"] in ("compact_chunk","compact_merge") and "compaction_plan" not in kwargs:
            kwargs["compaction_plan"]=dict(schemaVersion="compaction-plan-v1",intervalStart=0,intervalEnd=len(captured.units),protectedUnitKeys=[])
            kwargs["summary_input"]=dict(schemaVersion="compaction-summary-input-v1",kind="original_units",originalUnitKeys=[u.key for u in captured.units])
        receipt=super().reserve(captured,policy,**kwargs)
        self.bindings[receipt.call_id]={k:kwargs[k] for k in ("dispatch_profile","compaction_plan","summary_input") if k in kwargs}
        return receipt

    def mark_sent(self,captured,policy,receipt,**kwargs):
        return super().mark_sent(captured,policy,receipt,**(self.bindings.get(receipt.call_id,{})|kwargs))

    def archive_request(self,captured,policy,receipt,request,**kwargs):
        return super().archive_request(captured,policy,receipt,request,**(self.bindings.get(receipt.call_id,{})|kwargs))


def fixture_store(owner):
    from pathlib import Path
    from test_compaction_gate import Files
    return Files(Path(__file__).resolve().parents[3]/".local-runtime"/"summary-fixtures"/owner.owner_id)


def fixture_summary_request(repo,capture,descriptor,store):
    from citeframe_contracts.memory import GenerationMessage,GenerationRequest
    from citeframe_memory.compaction.guards import canonical
    from citeframe_memory.compaction.packing import summary_request
    from citeframe_memory.compaction.units import ContextUnit
    from citeframe_memory.compaction.archive import ToolArchive
    from citeframe_persistence.models import MemorySource,MemoryCall
    if descriptor["kind"]=="child_results":
        values=repo.transact(lambda db:[row.result_manifest["summary"] if (row:=db.get(MemoryCall,entry["callId"])) else {} for entry in descriptor["children"]])
        return GenerationRequest((GenerationMessage("system","fixture"),GenerationMessage("user",canonical({"chunkSummaries":values}))),2048,purpose="compact_merge")
    originals={u.key:u for u in capture.units};projected=[]
    for key in descriptor["originalUnitKeys"]:
        unit=originals[key]
        if unit.source:
            body=repo.read_source(capture.owner,unit.source)
            role=repo.transact(lambda db:db.get(MemorySource,unit.source.source_id).native_version.get("role","user"))
            messages=(GenerationMessage(role,body),);states=()
        else:
            raw=ToolArchive(repo,store).read(capture.owner,unit.tool_group_id);messages=raw.messages;states=raw.result_states
        payload=canonical({"original":asdict(unit),"messages":[asdict(m) for m in messages],"resultStates":list(states)})
        projected.append(ContextUnit(key,"messages",(GenerationMessage("user",payload),)))
    return summary_request(GenerationRequest((GenerationMessage("system","fixture"),),2048,purpose="compact_chunk"),tuple(projected))
