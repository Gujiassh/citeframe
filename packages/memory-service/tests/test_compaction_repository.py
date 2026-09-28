"""Actual migrated PostgreSQL checkpoint/source/CAS proof, separate from model quality."""
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from citeframe_contracts.compaction import ContextOwner, CoverageUnit, UsageSettlement
from citeframe_memory.compaction.guards import digest
from citeframe_memory.compaction.repository import CompactionRepository
from test_compaction_call_fixture import FixtureJournal as CallJournal
from citeframe_memory.compaction.policy import CompactionError
from citeframe_memory.compaction.summary import ARRAYS, omission_findings, validate_summary
from test_compaction_fixture import pg43, seed_chat


def prepared(engine, *, fault=None, null_anchor=False):
    scope=seed_chat(engine)
    now=datetime.now(UTC); deadline=now+timedelta(hours=1)
    with engine.begin() as c:
        c.execute(text("UPDATE chat_messages SET role='assistant' WHERE id=:id"),{"id":scope.leaf_id})
    current_user,current_assistant=str(uuid4()),str(uuid4())
    with engine.begin() as c:
        from test_compaction_fixture import insert_message
        insert_message(c,scope,current_user,parent_id=scope.leaf_id,content="current request")
        insert_message(c,scope,current_assistant,parent_id=current_user,content="")
        c.execute(text("UPDATE chat_messages SET role='assistant',status='streaming' WHERE id=:id"),{"id":current_assistant})
    owner=ContextOwner(scope.workspace_id,scope.user_id,"chat",str(uuid4()),"a"*64)
    policy={"schemaVersion":"compaction-policy-v1","maxCalls":100,"maxInputTokens":100000,
            "maxOutputTokens":10000,"maxSummaryCalls":20,"maxEpisodes":4,"deadlineAt":deadline.isoformat()}
    repo=CompactionRepository(lambda:Session(engine),clock=lambda:now,fault=fault)
    if null_anchor:
        with engine.begin() as c:c.execute(text("UPDATE chat_threads SET active_message_id=NULL WHERE id=:id"),{"id":scope.thread_id})
    repo.create_chat(owner,thread_id=scope.thread_id,user_message_id=current_user,
        assistant_message_id=current_assistant,request_id=str(uuid4()),request_sha256="b"*64,
        policy=policy,deadline_at=deadline,lease_expires_at=deadline)
    first=repo.register_source(owner,"chat_message",scope.parent_id)
    second=repo.register_source(owner,"chat_message",scope.leaf_id)
    units=(CoverageUnit("first",first),CoverageUnit("second",second,parent_message_id=scope.parent_id))
    return scope,repo,owner,policy,units


def summary(units):
    result={name:[] for name in ARRAYS}
    result.update(conflicts=[],progress={"stepId":None,"stateVersion":1,"status":"running","artifactIds":[]})
    result["facts"]=[dict(key="latency",text="37.5 ms only batch=8; never production",attribution="sourced_observation",
        sourceRefs=[asdict(units[0].source)],conditions=["only batch=8"],
        quantities=[{"value":"37.5","unit":"ms","qualifier":"only batch=8"}],negated=True)]
    return result


def journal_summary_call(repo,capture,policy,*,count=1,store=None):
    repo=CompactionRepository(repo.sessions,clock=repo.clock,limits=repo.limits)
    from citeframe_contracts.compaction import UsageSettlement
    from citeframe_contracts.memory import GenerationRequest,GenerationMessage
    from citeframe_memory.compaction.policy import CompactionPolicy
    from citeframe_memory.compaction.guards import canonical
    profile=dict(schemaVersion="compaction-dispatch-profile-v1",provider="fixture",protocol="openai_responses",
        model="fixture",configFingerprint="c"*64,contextWindowTokens=100000,maxOutputTokens=2048,inputCeiling=90000,
        safetyMargin=0,counter=dict(counter_id="fixture",counter_version="fixture-v1",mode="estimated",config_fingerprint="c"*64),
        watermarks=asdict(CompactionPolicy()))
    plan=dict(schemaVersion="compaction-plan-v1",intervalStart=0,intervalEnd=count,protectedUnitKeys=[])
    descriptor=dict(schemaVersion="compaction-summary-input-v1",kind="original_units",originalUnitKeys=[u.key for u in capture.units[:count]])
    from test_compaction_call_fixture import fixture_store,fixture_summary_request
    store=store or fixture_store(capture.owner)
    value=summary(capture.units[:count]);request=fixture_summary_request(repo,capture,descriptor,store)
    request_hash=digest(asdict(request));journal=CallJournal(repo,object_store=store)
    binding=dict(dispatch_profile=profile,compaction_plan=plan,summary_input=descriptor)
    key="fixture-summary:"+digest([asdict(capture),count])
    recovered=journal.recovered_summary(capture,policy,key,request_hash,**binding)
    if recovered:return recovered[0],recovered[1],binding,request_hash
    receipt=journal.reserve(capture,policy,logical_key=key,purpose="compact_chunk",
        request_sha256=request_hash,input_tokens=1000,output_tokens=2048,provider="fixture",model="fixture",profile_fingerprint="c"*64,**binding)
    journal.archive_request(capture,policy,receipt,request,**binding)
    journal.mark_sent(capture,policy,receipt,require_archive=True,**binding)
    journal.settle(receipt,UsageSettlement("succeeded",100,50,"reported"))
    journal.save_summary(capture,policy,receipt,value)
    return receipt.call_id,value,binding,request_hash


def adopt(repo,capture,policy,*,count=1,operation=None,store=None):
    call_id,value,binding,request_hash=journal_summary_call(repo,capture,policy,count=count,store=store)
    return repo.adopt(capture,covered_count=count,summary=value,policy=policy,
        operation_key=operation or digest([capture.native_fingerprint,count]),input_sha256=digest(asdict(capture)),
        before_tokens=1000,after_tokens=200,count_source="estimated",provider_fingerprint="c"*64,counter_version="fixture-v1",
        generation_call_id=call_id,generation_request_sha256=request_hash,**binding)


def state(engine,owner):
    with engine.connect() as c:
        pointer=c.execute(text("SELECT context_version,checkpoint_id FROM chat_memory_executions WHERE id=:id"),{"id":owner.owner_id}).one()
        counts=tuple(c.scalar(text("SELECT count(*) FROM "+table+(" WHERE consumer_snapshot_id IS NOT NULL" if table=="memory_uses" else ""))) for table in
            ("task_memory_snapshots","task_memory_coverage","memory_uses"))
        return tuple(pointer),counts


def test_atomic_adoption_two_checkpoints_same_owner_and_exact_readback(pg43):
    scope,repo,owner,policy,units=prepared(pg43)
    raw=repo.read_source(owner,units[0].source)
    capture=repo.capture(owner,units,policy)
    receipt=adopt(repo,capture,policy)
    assert state(pg43,owner)==((1,receipt.snapshot_id),(1,1,1))
    assert repo.reconcile(owner,receipt.operation_key)==receipt
    second=adopt(repo,repo.capture(owner,units,policy),policy,count=2)
    assert state(pg43,owner)==((2,second.snapshot_id),(2,3,4))
    assert repo.read_source(owner,units[0].source)==raw
    assert repo.read_source(owner,units[0].source,start=3,end=9)==raw[3:9]


@pytest.mark.parametrize("stage",["snapshot","coverage","uses","pointer","before_commit"])
def test_fault_rolls_back_entire_atomic_change(pg43,stage):
    scope,repo,owner,policy,units=prepared(pg43)
    capture=repo.capture(owner,units,policy)
    def fail(current):
        if current==stage: raise RuntimeError("injected")
    repo.fault=fail
    with pytest.raises(RuntimeError,match="injected"): adopt(repo,capture,policy)
    assert state(pg43,owner)==((0,None),(0,0,0))


def test_actual_lost_commit_ack_reconciles_without_second_adoption(pg43):
    scope,repo,owner,policy,units=prepared(pg43)
    capture=repo.capture(owner,units,policy); operation="d"*64
    def fail(stage):
        if stage=="after_commit": raise RuntimeError("ack_lost")
    repo.fault=fail
    with pytest.raises(RuntimeError,match="ack_lost"): adopt(repo,capture,policy,operation=operation)
    repo.fault=lambda stage:None
    receipt=repo.reconcile(owner,operation)
    assert receipt and state(pg43,owner)==((1,receipt.snapshot_id),(1,1,1))


@pytest.mark.parametrize("mutation",["content_aba","leaf_aba","insert_without_leaf","cancel","lease","membership"])
def test_stale_or_revoked_capture_cannot_adopt(pg43,mutation):
    scope,repo,owner,policy,units=prepared(pg43)
    capture=repo.capture(owner,units,policy)
    with pg43.begin() as c:
        if mutation=="content_aba":
            body=c.scalar(text("SELECT content FROM chat_messages WHERE id=:id"),{"id":scope.parent_id})
            c.execute(text("UPDATE chat_messages SET content='changed' WHERE id=:id"),{"id":scope.parent_id})
            c.execute(text("UPDATE chat_messages SET content=:body WHERE id=:id"),{"id":scope.parent_id,"body":body})
        elif mutation=="leaf_aba":
            c.execute(text("UPDATE chat_threads SET active_message_id=:leaf WHERE id=:id"),{"leaf":scope.parent_id,"id":scope.thread_id})
            c.execute(text("UPDATE chat_threads SET active_message_id=:leaf WHERE id=:id"),{"leaf":scope.leaf_id,"id":scope.thread_id})
        elif mutation=="insert_without_leaf":
            from test_compaction_fixture import insert_message
            insert_message(c,scope,str(uuid4()))
        elif mutation=="cancel":
            c.execute(text("UPDATE chat_memory_executions SET cancel_requested_at=now() WHERE id=:id"),{"id":owner.owner_id})
        elif mutation=="lease":
            c.execute(text("UPDATE chat_memory_executions SET lease_token_hash=:hash WHERE id=:id"),{"id":owner.owner_id,"hash":"f"*64})
        else:
            c.execute(text("DELETE FROM workspace_memberships WHERE id=:id"),{"id":scope.membership_id})
    with pytest.raises(CompactionError): adopt(repo,capture,policy)
    assert state(pg43,owner)==((0,None),(0,0,0))


def test_cross_user_workspace_and_sibling_fail_closed(pg43):
    scope,repo,owner,policy,units=prepared(pg43)
    for invalid in (replace(owner,actor_user_id=scope.other_user_id),replace(owner,workspace_id=scope.other_workspace_id)):
        with pytest.raises(CompactionError): repo.read_source(invalid,units[0].source)
    sibling=str(uuid4())
    with pg43.begin() as c:
        from test_compaction_fixture import insert_message
        insert_message(c,scope,sibling,content="PRIVATE_OR_SIBLING_MARKER")
    with pytest.raises(CompactionError,match="source_branch_mismatch"):
        repo.register_source(owner,"chat_message",sibling)
    with pytest.raises(CompactionError,match="shared_source_kind_forbidden"):
        repo.register_source(owner,"memory_instruction",str(uuid4()))


def test_ordered_complete_coverage_rejects_holes(pg43):
    scope,repo,owner,policy,units=prepared(pg43)
    with pytest.raises(CompactionError,match="coverage_must_start_at_root"):
        repo.capture(owner,(units[1],),policy)
    with pytest.raises(CompactionError): repo.capture(owner,(units[1],units[0]),policy)


def test_journal_conservative_unknown_survives_cancel_and_blocks_resend(pg43):
    scope,repo,owner,policy,units=prepared(pg43)
    captured=repo.capture(owner,units,policy); journal=CallJournal(repo)
    args=dict(logical_key="chunk:1",purpose="compact_chunk",request_sha256="e"*64,
              input_tokens=100,output_tokens=20,provider="fixture",model="fixture",profile_fingerprint="f"*64)
    receipt=journal.reserve(captured,policy,**args)
    journal.mark_sent(captured,policy,receipt)
    with pg43.begin() as c:
        c.execute(text("DELETE FROM workspace_memberships WHERE id=:id"),{"id":scope.membership_id})
    settled=journal.settle(receipt,UsageSettlement("outcome_unknown",0,0,"unknown"))
    assert settled==dict(state="outcome_unknown",input_tokens=100,output_tokens=20)
    assert journal.settle(receipt,UsageSettlement("outcome_unknown",0,0,"unknown"))==settled
    with pytest.raises(CompactionError): journal.reserve(captured,policy,**args)
    assert state(pg43,owner)==((0,None),(0,0,0))


def test_no_progress_persisted_without_provider_slot_or_checkpoint(pg43):
    scope,repo,owner,policy,units=prepared(pg43)
    captured=repo.capture(owner,units,policy); journal=CallJournal(repo); key="f"*64
    assert not journal.no_progress(captured,policy,key)
    assert journal.no_progress(captured,policy,key,"no_gain")
    assert journal.no_progress(captured,policy,key)
    with pg43.connect() as c:
        assert c.execute(text("SELECT state,reserved_input,reserved_output,sent_at FROM memory_calls")).one()==("succeeded",0,0,None)
    assert state(pg43,owner)==((0,None),(0,0,0))


def test_structural_pass_does_not_hide_annotated_semantic_omissions(pg43):
    scope,repo,owner,policy,units=prepared(pg43)
    value=summary(units); quantity=value["facts"][0]["quantities"][0]
    assert validate_summary(value,units)
    value["facts"][0].update(quantities=[],conditions=[],negated=False)
    assert validate_summary(value,units)
    assert omission_findings(value,quantities=(quantity,),conditions=("only batch=8",),
        negated_keys=("latency",),conflict_keys=("unresolved-disagreement",))==(
            "quantity_omitted","condition_omitted","negation_omitted","conflict_omitted")


def test_summary_confirmation_requires_actual_action_not_model_attribution(pg43):
    scope,repo,owner,policy,units=prepared(pg43)
    value=summary(units);value["facts"][0]["attribution"]="user_explicit"
    with pytest.raises(CompactionError,match="summary_confirmation_unattributable"):
        validate_summary(value,units)


def test_summary_save_is_owner_bound_schema_checked_and_immutable(pg43):
    scope,repo,owner,policy,units=prepared(pg43);captured=repo.capture(owner,units,policy);journal=CallJournal(repo)
    call_id,value,binding,_=journal_summary_call(repo,captured,policy,count=2)
    from citeframe_persistence.models import MemoryCall
    receipt=repo.transact(lambda db:journal._receipt(db.get(MemoryCall,call_id)))
    other=replace(captured,owner=replace(owner,owner_id=str(uuid4())))
    with pytest.raises(CompactionError):journal.save_summary(other,policy,receipt,value)
    journal.save_summary(captured,policy,receipt,value)
    value["facts"][0]["text"]="a conflicting late result"
    with pytest.raises(CompactionError,match="summary_result_conflict"):
        journal.save_summary(captured,policy,receipt,value)


def test_concurrent_compactors_one_atomic_winner(pg43):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    scope,repo,owner,policy,units=prepared(pg43)
    captured=repo.capture(owner,units,policy)
    locked,release=Event(),Event()
    def pause(stage):
        if stage=="snapshot":
            locked.set()
            assert release.wait(10)
    repo.fault=pause
    rival=CompactionRepository(lambda:Session(pg43),clock=repo.clock)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(adopt,repo,captured,policy)
        assert locked.wait(10)
        try:
            with pytest.raises(CompactionError):adopt(rival,captured,policy,operation="e"*64)
        finally:release.set()
        winner=first.result(10)
    assert state(pg43,owner)==((1,winner.snapshot_id),(1,1,1))
    with pytest.raises(CompactionError):adopt(rival,captured,policy,operation="e"*64)


def test_retry_child_keeps_root_cumulative_budget(pg43):
    from test_compaction_fixture import insert_message
    scope,repo,owner,policy,units=prepared(pg43)
    first=repo.capture(owner,units,policy);journal=CallJournal(repo)
    receipt=journal.reserve(first,policy,logical_key="root-call",purpose="main",request_sha256="e"*64,
        input_tokens=60000,output_tokens=100,provider="fixture",model="fixture",profile_fingerprint="f"*64)
    journal.mark_sent(first,policy,receipt)
    journal.settle(receipt,UsageSettlement("succeeded",60000,100,"reported"))
    leaf=str(uuid4());child=replace(owner,owner_id=str(uuid4()))
    with pg43.begin() as db:
        insert_message(db,scope,leaf,parent_id=scope.parent_id)
        db.execute(text("UPDATE chat_messages SET role='assistant',status='streaming' WHERE id=:id"),{"id":leaf})
        db.execute(text("UPDATE chat_threads SET active_message_id=:leaf WHERE id=:id"),{"leaf":leaf,"id":scope.thread_id})
    deadline=datetime.fromisoformat(policy["deadlineAt"])
    repo.create_chat(child,thread_id=scope.thread_id,user_message_id=scope.parent_id,assistant_message_id=leaf,
        request_id=str(uuid4()),request_sha256="b"*64,policy=policy,deadline_at=deadline,lease_expires_at=deadline)
    with pg43.begin() as db:db.execute(text("UPDATE chat_memory_executions SET retry_of_id=:parent,attempt_number=2 WHERE id=:id"),{"parent":owner.owner_id,"id":child.owner_id})
    captured=repo.capture(child,units[:1],policy)
    with pytest.raises(CompactionError,match="context_budget_exhausted"):
        journal.reserve(captured,policy,logical_key="child-call",purpose="main",request_sha256="d"*64,
            input_tokens=45000,output_tokens=100,provider="fixture",model="fixture",profile_fingerprint="f"*64)
    with pg43.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM memory_calls"))==1
        assert db.scalar(text("SELECT actual_input FROM memory_calls"))==60000
