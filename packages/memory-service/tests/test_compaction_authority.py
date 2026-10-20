"""Public journal/adoption regressions for reviewed interval and result authority."""
from dataclasses import asdict
import pytest
from sqlalchemy import text,event
from contextlib import contextmanager
from citeframe_contracts.compaction import CoverageUnit
from citeframe_memory.compaction.guards import digest
from citeframe_memory.compaction.policy import CompactionError
from test_compaction_fixture import pg43
from test_compaction_repository import prepared,summary,state
from test_compaction_provenance import setup,save


@contextmanager
def no_dml(engine):
    writes=[]
    def observe(connection,cursor,statement,parameters,context,executemany):
        if statement.lstrip().split(None,1)[0].upper() in ('INSERT','UPDATE','DELETE'):
            writes.append(statement)
    event.listen(engine,'before_cursor_execute',observe)
    try:
        yield
    finally:
        event.remove(engine,'before_cursor_execute',observe)
        assert writes==[],writes


def fixture(engine):
    scope,repo,owner,policy,units=prepared(engine)
    with engine.connect() as db:
        current=db.scalar(text('SELECT user_message_id FROM chat_memory_executions WHERE id=:id'),{'id':owner.owner_id})
    units+= (CoverageUnit('current',repo.register_source(owner,'chat_message',current),parent_message_id=scope.leaf_id),)
    return repo,owner,policy,units


def pending(repo,owner,policy,units,start,end,protected,key):
    capture,journal,p,plan=setup(repo,owner,policy,units)
    plan.update(intervalStart=start,intervalEnd=end,protectedUnitKeys=protected)
    descriptor=dict(schemaVersion='compaction-summary-input-v1',kind='original_units',originalUnitKeys=[u.key for u in units[start:end]])
    value=summary(units[start:end])
    receipt,binding=save(journal,capture,policy,p,plan,descriptor,value,key)
    return capture,journal,receipt,binding,value


def adopt(repo,policy,pending):
    capture,_,receipt,binding,value=pending
    return repo.adopt(capture,covered_count=binding['compaction_plan']['intervalEnd'],summary=value,policy=policy,
        operation_key=digest(receipt.call_id),input_sha256=digest(asdict(capture)),before_tokens=1000,after_tokens=200,
        count_source='estimated',provider_fingerprint=binding['dispatch_profile']['configFingerprint'],counter_version='v1',
        generation_call_id=receipt.call_id,generation_request_sha256=receipt.request_sha256,**binding)


@pytest.mark.parametrize('case',['removed','partial','newly_hidden'])
def test_adoption_rejects_incompatible_interval_before_dml(pg43,case):
    repo,owner,policy,units=fixture(pg43)
    first=pending(repo,owner,policy,units,0,2 if case=='partial' else 1,['second'] if case=='removed' else [],'first')
    adopt(repo,policy,first)
    next_=pending(repo,owner,policy,units,1 if case in ('partial','newly_hidden') else 0,3,['first'] if case=='newly_hidden' else [],'next')
    before=state(pg43,owner)
    with no_dml(pg43),pytest.raises(CompactionError,match='checkpoint_'):
        adopt(repo,policy,next_)
    assert state(pg43,owner)==before
    repo.checkpoint_intervals(repo.capture(owner,units,policy),policy)


@pytest.mark.parametrize('lifecycle',['invalidated','erased'])
def test_delayed_save_cannot_restore_result_authority(pg43,lifecycle):
    repo,owner,policy,units=fixture(pg43)
    capture,journal,receipt,binding,value=pending(repo,owner,policy,units,0,1,[],'summary')
    with pg43.begin() as db:
        db.execute(text("UPDATE memory_calls SET result_state=:state"+(",result_manifest=NULL,result_sha256=NULL" if lifecycle=='erased' else '')+" WHERE id=:id"),{'state':lifecycle,'id':receipt.call_id})
    with pg43.connect() as db:before=db.scalar(text('SELECT to_jsonb(c) FROM memory_calls c WHERE id=:id'),{'id':receipt.call_id})
    old=state(pg43,owner)
    with no_dml(pg43),pytest.raises(CompactionError,match='summary_call_unavailable'):
        journal.save_summary(capture,policy,receipt,value)
    with pg43.connect() as db:assert db.scalar(text('SELECT to_jsonb(c) FROM memory_calls c WHERE id=:id'),{'id':receipt.call_id})==before
    assert state(pg43,owner)==old
    assert journal.recovered_summary(capture,policy,'summary',receipt.request_sha256,**binding) is None


@pytest.mark.parametrize('kind',['containing','disjoint'])
def test_public_adoption_retains_lawful_interval_transitions(pg43,kind):
    repo,owner,policy,units=fixture(pg43)
    adopt(repo,policy,pending(repo,owner,policy,units,0,1,[],'first'))
    adopt(repo,policy,pending(repo,owner,policy,units,0 if kind=='containing' else 1,3,[],'next'))
    intervals,_,frontier=repo.checkpoint_intervals(repo.capture(owner,units,policy),policy)
    assert [(a,b) for a,b,_ in intervals]==([(0,3)] if kind=='containing' else [(0,1),(1,3)])
    assert frontier==3


@pytest.mark.parametrize('fault',['malformed','invalidated','erased'])
def test_adoption_authenticates_prior_generation_before_dml(pg43,fault):
    repo,owner,policy,units=fixture(pg43)
    first=pending(repo,owner,policy,units,0,1,[],'first');adopt(repo,policy,first)
    next_=pending(repo,owner,policy,units,1,3,[],'next')
    with pg43.begin() as db:
        clause="result_manifest=jsonb_set(result_manifest,'{finalEligible}','false'::jsonb)" if fault=='malformed' else "result_state='"+fault+"'"+(" ,result_manifest=NULL,result_sha256=NULL" if fault=='erased' else '')
        if fault=='malformed':db.execute(text("UPDATE memory_calls SET result_state='invalidated' WHERE id=:id"),{'id':first[2].call_id})
        if fault=='malformed':clause+=",result_state='valid'"
        db.execute(text('UPDATE memory_calls SET '+clause+' WHERE id=:id'),{'id':first[2].call_id})
    before=state(pg43,owner)
    with no_dml(pg43),pytest.raises(CompactionError,match='checkpoint_|summary_'):
        adopt(repo,policy,next_)
    assert state(pg43,owner)==before


@pytest.mark.parametrize('lifecycle',['invalidated','erased'])
def test_save_serializes_with_late_result_lifecycle(pg43,lifecycle):
    repo,owner,policy,units=fixture(pg43)
    capture,journal,receipt,binding,value=pending(repo,owner,policy,units,0,1,[],'summary')
    old=state(pg43,owner)
    with pg43.begin() as writer:
        writer.execute(text("UPDATE memory_calls SET result_state=:state"+(",result_manifest=NULL,result_sha256=NULL" if lifecycle=='erased' else '')+" WHERE id=:id"),{'state':lifecycle,'id':receipt.call_id})
        with no_dml(pg43),pytest.raises(CompactionError,match='context_busy'):
            journal.save_summary(capture,policy,receipt,value)
    with pg43.connect() as db:before=db.scalar(text('SELECT to_jsonb(c) FROM memory_calls c WHERE id=:id'),{'id':receipt.call_id})
    with no_dml(pg43),pytest.raises(CompactionError,match='summary_call_unavailable'):
        journal.save_summary(capture,policy,receipt,value)
    with pg43.connect() as db:assert db.scalar(text('SELECT to_jsonb(c) FROM memory_calls c WHERE id=:id'),{'id':receipt.call_id})==before
    assert state(pg43,owner)==old
    assert journal.recovered_summary(capture,policy,'summary',receipt.request_sha256,**binding) is None


def test_adoption_serializes_with_late_historical_result_change(pg43):
    repo,owner,policy,units=fixture(pg43)
    first=pending(repo,owner,policy,units,0,1,[],'first');adopt(repo,policy,first)
    next_=pending(repo,owner,policy,units,1,3,[],'next');before=state(pg43,owner)
    with pg43.begin() as writer:
        writer.execute(text("UPDATE memory_calls SET result_state='invalidated' WHERE id=:id"),{'id':first[2].call_id})
        with no_dml(pg43),pytest.raises(CompactionError,match='context_busy'):
            adopt(repo,policy,next_)
    with no_dml(pg43),pytest.raises(CompactionError,match='checkpoint_rendering_metadata_required'):
        adopt(repo,policy,next_)
    assert state(pg43,owner)==before


def test_valid_summary_repeat_is_exact_and_effect_free(pg43):
    repo,owner,policy,units=fixture(pg43)
    capture,journal,receipt,binding,value=pending(repo,owner,policy,units,0,1,[],'summary')
    with pg43.connect() as db:before=db.scalar(text('SELECT to_jsonb(c) FROM memory_calls c WHERE id=:id'),{'id':receipt.call_id})
    with no_dml(pg43):journal.save_summary(capture,policy,receipt,value)
    changed=dict(value,progress=dict(value['progress'],status='different'))
    with no_dml(pg43),pytest.raises(CompactionError,match='summary_result_conflict'):
        journal.save_summary(capture,policy,receipt,changed)
    with pg43.connect() as db:assert db.scalar(text('SELECT to_jsonb(c) FROM memory_calls c WHERE id=:id'),{'id':receipt.call_id})==before


@pytest.mark.parametrize('limit',['episodes','bytes'])
def test_proposed_chain_limits_reject_before_commit(pg43,limit):
    from dataclasses import replace
    from datetime import datetime
    from uuid import uuid4
    import copy
    from test_compaction_long_branch import ancestry_fixture
    from citeframe_memory.compaction.guards import canonical
    scope,repo,old_owner,policy,units,_=ancestry_fixture(pg43,10)
    policy=dict(policy,maxEpisodes=1 if limit=='episodes' else 12)
    owner=replace(old_owner,owner_id=str(uuid4()))
    with pg43.connect() as db:
        user,assistant=db.execute(text('SELECT user_message_id,assistant_message_id FROM chat_memory_executions WHERE id=:id'),{'id':old_owner.owner_id}).one()
    assistant=str(uuid4())
    from test_compaction_fixture import insert_message
    with pg43.begin() as db:
        insert_message(db,scope,assistant,parent_id=user,content='')
        db.execute(text("UPDATE chat_messages SET role='assistant',status='streaming' WHERE id=:id"),{'id':assistant})
    deadline=datetime.fromisoformat(policy['deadlineAt'])
    repo.create_chat(owner,thread_id=scope.thread_id,user_message_id=user,assistant_message_id=assistant,request_id=str(uuid4()),request_sha256='d'*64,policy=policy,deadline_at=deadline,lease_expires_at=deadline)
    budget=0
    for index in range(9):
        capture,journal,p,plan=setup(repo,owner,policy,units)
        plan.update(intervalStart=index,intervalEnd=index+1)
        descriptor=dict(schemaVersion='compaction-summary-input-v1',kind='original_units',originalUnitKeys=[units[index].key])
        value=summary(units[index:index+1])
        if limit=='bytes':
            p['model']='m'*115000
            atom=value['facts'][0];value['facts']=[dict(copy.deepcopy(atom),key='fact'+str(n),text='x'*1500) for n in range(60)]
        receipt,binding=save(journal,capture,policy,p,plan,descriptor,value,'limit'+str(index))
        with pg43.connect() as db:
            manifest,result=db.execute(text('SELECT input_manifest,result_manifest FROM memory_calls WHERE id=:id'),{'id':receipt.call_id}).one()
        budget+=len(canonical(manifest).encode())+len(canonical(result).encode())
        pending_=(capture,journal,receipt,binding,value)
        before=state(pg43,owner)
        if index+1>policy['maxEpisodes'] or budget>1048576:
            with no_dml(pg43),pytest.raises(CompactionError,match='checkpoint_chain_limit'):
                adopt(repo,policy,pending_)
            assert state(pg43,owner)==before
            repo.checkpoint_intervals(repo.capture(owner,units,policy),policy)
            return
        adopt(repo,policy,pending_)
    raise AssertionError('Fixture did not cross the actual unchanged chain limit')



def checkpoint_rows(engine,owner):
    with engine.connect() as db:
        rows=[db.execute(text('SELECT to_jsonb(t) FROM '+table+' t ORDER BY to_jsonb(t)::text')).scalars().all()
              for table in ('task_memory_snapshots','task_memory_coverage','memory_uses','memory_calls')]
        rows.append(db.scalar(text('SELECT to_jsonb(e) FROM chat_memory_executions e WHERE id=:id'),{'id':owner.owner_id}))
        return rows


@pytest.mark.parametrize('stage',['snapshot','coverage','uses','pointer','before_commit'])
def test_second_adoption_fault_preserves_exact_last_good_rows(pg43,stage):
    repo,owner,policy,units=fixture(pg43)
    first=pending(repo,owner,policy,units,0,1,[],'first');adopt(repo,policy,first)
    next_=pending(repo,owner,policy,units,1,3,[],'next')
    before=checkpoint_rows(pg43,owner)
    def fault(point):
        if point==stage:raise RuntimeError('injected second-adoption '+stage)
    repo.fault=fault
    with pytest.raises(RuntimeError,match='injected second-adoption'):
        adopt(repo,policy,next_)
    assert checkpoint_rows(pg43,owner)==before
    intervals,_,frontier=repo.checkpoint_intervals(repo.capture(owner,units,policy),policy)
    assert [(a,b) for a,b,_ in intervals]==[(0,1)] and frontier==1


def test_adoption_holds_prior_generation_lock_through_rollback(pg43):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.exc import OperationalError
    repo,owner,policy,units=fixture(pg43)
    first=pending(repo,owner,policy,units,0,1,[],'first');adopt(repo,policy,first)
    next_=pending(repo,owner,policy,units,1,3,[],'next');before=checkpoint_rows(pg43,owner)
    def writer():
        with pg43.begin() as db:
            db.execute(text('SET LOCAL lock_timeout=250'))
            db.execute(text("UPDATE memory_calls SET result_state='invalidated' WHERE id=:id"),{'id':first[2].call_id})
    def fault(point):
        if point=='snapshot':
            with ThreadPoolExecutor(max_workers=1) as pool:
                with pytest.raises(OperationalError) as error:
                    pool.submit(writer).result(timeout=5)
                assert error.value.orig.sqlstate=='55P03'
            raise RuntimeError('rollback after blocked lifecycle writer')
    repo.fault=fault
    with pytest.raises(RuntimeError,match='rollback after blocked'):
        adopt(repo,policy,next_)
    assert checkpoint_rows(pg43,owner)==before
    repo.checkpoint_intervals(repo.capture(owner,units,policy),policy)
    writer()
    with pg43.connect() as db:
        assert db.scalar(text('SELECT result_state FROM memory_calls WHERE id=:id'),{'id':first[2].call_id})=='invalidated'
