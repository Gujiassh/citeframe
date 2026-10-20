"""Whole-profile equality at durable admission, recovery and final adoption."""
from dataclasses import asdict,replace
import copy
import pytest
from sqlalchemy import text
from citeframe_contracts.memory import GenerationMessage,GenerationRequest
from citeframe_memory.compaction.guards import digest
from citeframe_memory.compaction.journal import CallJournal
from citeframe_memory.compaction.policy import CompactionError
from test_compaction_call_fixture import profile
from test_compaction_fixture import pg43
from test_compaction_gate import Files
from test_compaction_repository import prepared,journal_summary_call


FIELDS=("provider","protocol","model","configFingerprint","contextWindowTokens","maxOutputTokens","inputCeiling","safetyMargin","counter_id","counter_version","mode","watermarks")


def drift(value,field):
    value=copy.deepcopy(value)
    if field in ("counter_id","counter_version"):value["counter"][field]+="-changed"
    elif field=="mode":value["counter"][field]="exact"
    elif field=="watermarks":value[field]["min_gain_tokens"]+=1
    elif field=="configFingerprint":value[field]+="-changed";value["counter"]["config_fingerprint"]=value[field]
    elif isinstance(value[field],int):value[field]+=1
    else:value[field]+="-changed"
    return value


@pytest.mark.parametrize("field",FIELDS)
@pytest.mark.parametrize("boundary",["reserve","archive","send","recovery","adopt"])
def test_profile_drift_rejects_same_request_hash_at_every_boundary(pg43,tmp_path,field,boundary):
    scope,repo,owner,policy,units=prepared(pg43);captured=repo.capture(owner,units,policy)
    journal=CallJournal(repo,object_store=Files(tmp_path));request=GenerationRequest((GenerationMessage("system","trusted"),),100)
    if boundary in ("recovery","adopt"):
        call_id,value,binding,request_hash=journal_summary_call(repo,captured,policy)
        changed=binding|{"dispatch_profile":drift(binding["dispatch_profile"],field)}
        with pg43.connect() as db:key=db.scalar(text("SELECT logical_key FROM memory_calls WHERE id=:id"),{"id":call_id})
        action=(lambda:journal.recovered_summary(captured,policy,key,request_hash,**changed)) if boundary=="recovery" else (lambda:repo.adopt(captured,
            covered_count=1,summary=value,policy=policy,operation_key="a"*64,input_sha256="b"*64,before_tokens=1000,after_tokens=200,
            count_source="estimated",provider_fingerprint="c"*64,counter_version="fixture-v1",generation_call_id=call_id,generation_request_sha256=request_hash,**changed))
    else:
        original=profile();changed=drift(original,field)
        args=dict(logical_key="main",purpose="main",request_sha256=digest(asdict(request)),input_tokens=10,output_tokens=100,
                  provider="fixture",model="fixture",profile_fingerprint="f"*64)
        receipt=journal.reserve(captured,policy,**args,dispatch_profile=original)
        if boundary=="reserve":action=lambda:journal.reserve(captured,policy,**args,dispatch_profile=changed)
        elif boundary=="archive":action=lambda:journal.archive_request(captured,policy,receipt,request,dispatch_profile=changed)
        else:action=lambda:journal.mark_sent(captured,policy,receipt,dispatch_profile=changed)
    with pg43.connect() as db:before=db.execute(text("SELECT to_jsonb(c) FROM memory_calls c ORDER BY id")).scalars().all()
    with pytest.raises(CompactionError,match="binding_changed|idempotency_conflict"):action()
    with pg43.connect() as db:
        assert before==db.execute(text("SELECT to_jsonb(c) FROM memory_calls c ORDER BY id")).scalars().all()
        assert db.scalar(text("SELECT count(*) FROM task_memory_snapshots"))==0
    assert not list(tmp_path.rglob("*"))


def test_missing_dispatch_profile_is_not_a_legacy_send_path(pg43):
    scope,repo,owner,policy,units=prepared(pg43);captured=repo.capture(owner,units,policy)
    with pytest.raises(CompactionError,match="dispatch_profile_required"):
        CallJournal(repo).reserve(captured,policy,logical_key="missing",purpose="main",request_sha256="a"*64,input_tokens=10,output_tokens=10,provider="fixture",model="fixture",profile_fingerprint="f"*64)
    with pg43.connect() as db:assert db.scalar(text("SELECT count(*) FROM memory_calls"))==0
