"""Real journal per-call support, partial-final and merge-child rejection."""
from dataclasses import asdict
import copy
import pytest
from sqlalchemy import text
from citeframe_contracts.compaction import UsageSettlement
from citeframe_memory.compaction.guards import digest
from citeframe_memory.compaction.journal import CallJournal
from citeframe_memory.compaction.policy import CompactionError
from test_compaction_call_fixture import profile,fixture_store,fixture_summary_request
from test_compaction_fixture import pg43
from test_compaction_repository import prepared,summary


def setup(repo,owner,policy,units):
    capture=repo.capture(owner,units,policy);journal=CallJournal(repo,object_store=fixture_store(owner));p=profile()
    plan=dict(schemaVersion="compaction-plan-v1",intervalStart=0,intervalEnd=len(units),protectedUnitKeys=[])
    return capture,journal,p,plan


def save(journal,capture,policy,p,plan,descriptor,value,key,purpose="compact_chunk"):
    binding=dict(dispatch_profile=p,compaction_plan=plan,summary_input=descriptor)
    request=fixture_summary_request(journal.repo,capture,descriptor,journal.object_store)
    receipt=journal.reserve(capture,policy,logical_key=key,purpose=purpose,request_sha256=digest(asdict(request)),input_tokens=100,output_tokens=2048,
        provider=p["provider"],model=p["model"],profile_fingerprint=p["configFingerprint"],**binding)
    journal.archive_request(capture,policy,receipt,request,**binding)
    journal.mark_sent(capture,policy,receipt,require_archive=True,**binding);journal.settle(receipt,UsageSettlement("succeeded",100,50,"reported"))
    journal.save_summary(capture,policy,receipt,value)
    return receipt,binding


def adopt(repo,capture,policy,receipt,binding,value):
    return repo.adopt(capture,covered_count=len(capture.units),summary=value,policy=policy,operation_key="a"*64,input_sha256="b"*64,
        before_tokens=1000,after_tokens=200,count_source="estimated",provider_fingerprint=binding["dispatch_profile"]["configFingerprint"],counter_version="v1",
        generation_call_id=receipt.call_id,generation_request_sha256=receipt.request_sha256,**binding)


def test_partial_chunk_cannot_acquire_aggregate_rendering_authority(pg43):
    scope,repo,owner,policy,units=prepared(pg43);capture,journal,p,plan=setup(repo,owner,policy,units)
    descriptor=dict(schemaVersion="compaction-summary-input-v1",kind="original_units",originalUnitKeys=[units[0].key])
    value=summary(units[:1]);receipt,binding=save(journal,capture,policy,p,plan,descriptor,value,"partial")
    with pg43.connect() as db:assert db.scalar(text("SELECT result_manifest->>'finalEligible' FROM memory_calls WHERE id=:id"),{"id":receipt.call_id})=="false"
    with pytest.raises(CompactionError,match="summary_not_final"):adopt(repo,capture,policy,receipt,binding,value)
    with pg43.connect() as db:assert db.scalar(text("SELECT count(*) FROM task_memory_snapshots"))==0


@pytest.mark.parametrize("fault",["missing","duplicate","order","hash","manifest_hash","unknown_child","sibling_support"])
def test_merge_input_provenance_and_final_eligibility(pg43,fault):
    scope,repo,owner,policy,units=prepared(pg43);capture,journal,p,plan=setup(repo,owner,policy,units)
    children=[];values=[]
    for i,unit in enumerate(units):
        descriptor=dict(schemaVersion="compaction-summary-input-v1",kind="original_units",originalUnitKeys=[unit.key])
        value=summary((unit,));value["facts"][0]["key"]="fact"+str(i)
        receipt,_=save(journal,capture,policy,p,plan,descriptor,value,"chunk"+str(i));children.append(repo.summary_child(receipt.call_id));values.append(value)
    merged=copy.deepcopy(values[0]);merged["facts"]+=values[1]["facts"]
    if fault=="missing":children=children[:1];merged=values[0]
    elif fault=="duplicate":children=[children[0],children[0]]
    elif fault=="order":children.reverse()
    elif fault=="hash":children[0]["resultSha256"]="0"*64
    elif fault=="manifest_hash":children[0]["inputManifestSha256"]="0"*64
    elif fault=="unknown_child":children[0]["callId"]="missing"
    else:children=children[:1];merged=values[1]
    descriptor=dict(schemaVersion="compaction-summary-input-v1",kind="child_results",children=children)
    if fault=="missing":
        receipt,binding=save(journal,capture,policy,p,plan,descriptor,merged,"merge","compact_merge")
        with pytest.raises(CompactionError,match="summary_not_final"):adopt(repo,capture,policy,receipt,binding,merged)
    else:
        with pytest.raises(CompactionError,match="invalid_summary|summary_payload_changed"):
            save(journal,capture,policy,p,plan,descriptor,merged,"merge","compact_merge")
    with pg43.connect() as db:assert db.scalar(text("SELECT count(*) FROM task_memory_snapshots"))==0


def test_unarchived_result_cannot_become_checkpoint_provenance(pg43):
    scope,repo,owner,policy,units=prepared(pg43);capture,journal,p,plan=setup(repo,owner,policy,units)
    descriptor=dict(schemaVersion="compaction-summary-input-v1",kind="original_units",originalUnitKeys=[u.key for u in units])
    binding=dict(dispatch_profile=p,compaction_plan=plan,summary_input=descriptor)
    receipt=journal.reserve(capture,policy,logical_key="unarchived",purpose="compact_chunk",request_sha256="a"*64,input_tokens=100,output_tokens=100,provider=p["provider"],model=p["model"],profile_fingerprint=p["configFingerprint"],**binding)
    journal.mark_sent(capture,policy,receipt,**binding);journal.settle(receipt,UsageSettlement("succeeded",100,50,"reported"))
    with pytest.raises(CompactionError,match="summary_request_archive_required"):journal.save_summary(capture,policy,receipt,summary(units))
    with pg43.connect() as db:
        assert db.scalar(text("SELECT result_state FROM memory_calls WHERE id=:id"),{"id":receipt.call_id})=="absent"
        assert db.scalar(text("SELECT count(*) FROM task_memory_snapshots"))==0


@pytest.mark.parametrize("tamper",["body","envelope_field","message_field"])
def test_archived_chunk_cannot_contain_extra_or_changed_original_payload(pg43,tamper):
    import json
    from dataclasses import replace
    from citeframe_contracts.memory import GenerationMessage
    scope,repo,owner,policy,units=prepared(pg43);capture,journal,p,plan=setup(repo,owner,policy,units)
    descriptor=dict(schemaVersion="compaction-summary-input-v1",kind="original_units",originalUnitKeys=[u.key for u in units])
    binding=dict(dispatch_profile=p,compaction_plan=plan,summary_input=descriptor)
    request=fixture_summary_request(repo,capture,descriptor,journal.object_store)
    outer=json.loads(request.messages[1].content);payload=json.loads(outer["sourceUnit"]["messages"][0]["content"])
    if tamper=="body":payload["messages"][0]["content"]="body not present in authorized original"
    elif tamper=="envelope_field":outer["unregistered"]="extra input"
    else:payload["messages"][0]["unregistered"]="extra input"
    outer["sourceUnit"]["messages"][0]["content"]=json.dumps(payload)
    request=replace(request,messages=(request.messages[0],GenerationMessage("user",json.dumps(outer)),*request.messages[2:]))
    receipt=journal.reserve(capture,policy,logical_key="changed-physical",purpose="compact_chunk",request_sha256=digest(asdict(request)),input_tokens=100,output_tokens=2048,provider=p["provider"],model=p["model"],profile_fingerprint=p["configFingerprint"],**binding)
    with pytest.raises(CompactionError,match="summary_payload_changed"):journal.archive_request(capture,policy,receipt,request,**binding)
    with pg43.connect() as db:
        assert db.execute(text("SELECT state,request_object_key FROM memory_calls WHERE id=:id"),{"id":receipt.call_id}).one()==("reserved",None)
