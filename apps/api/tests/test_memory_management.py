"""Real PostgreSQL consumer tests; TestClient transport is not live-HTTP evidence."""
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ai_pdf_api.core.settings import settings
from ai_pdf_api.db.session import get_db
from ai_pdf_api.routers.memories import router
from citeframe_contracts.memory import MemoryRequest
from citeframe_memory.lifecycle import invalidate_instruction
from citeframe_persistence.models import Workspace, WorkspaceMembership
from citeframe_persistence.models.memory import MemoryOperation, MemoryRevision

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("memory_core_test_support", ROOT / "packages/memory-service/tests/test_instruction_memory.py")
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)
pg = core.pg
CASES = json.loads((Path(__file__).parent / "fixtures/memory/management_contract_cases.json").read_text())


@pytest.fixture
def api(pg):
    engine, context, other = pg
    app = FastAPI()
    app.include_router(router)
    def sessions():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db] = sessions
    with TestClient(app) as client:
        yield client, engine, context, other


def headers(actor, key=None):
    value = {"x-user-id": actor, "x-ai-pdf-internal-token": settings.api_internal_token}
    if key:
        value["Idempotency-Key"] = key
    return value


def seed(api):
    _, engine, context, _ = api
    return core.command(engine, "remember", context, core.request(), core.statement())


def base(context):
    return f"/v1/workspaces/{context.workspace_id}"


def assert_error(response, status, code, request_id=None, retry=False):
    assert response.status_code == status, response.text
    detail = response.json()["detail"]
    assert detail["code"] == code
    assert detail["retryable"] is retry
    assert detail["requestId"] == request_id
    assert "currentVersion" not in detail


def test_actual_dependency_and_mounted_openapi(api):
    client, engine, ctx, _ = api
    paths = client.app.openapi()["paths"]
    assert set(paths['/v1/workspaces/{workspace_id}/memories']) == {'get','post'}
    assert 'post' in paths['/v1/workspaces/{workspace_id}/memories/{memory_id}/corrections']
    assert_error(client.post(base(ctx) + '/memories', headers=headers(ctx.actor_user_id), json=CASES['baseBody']),422,'invalid_request',CASES['requestId'])
    assert client.get(base(ctx) + '/memories', headers=headers(ctx.actor_user_id)).json() == dict(items=[], nextCursor=None)


def test_current_source_history_invalidation_truth_table(api):
    client, engine, ctx, other = api
    receipt = seed(api)
    url = base(ctx) + '/memories/' + receipt.resource.memory_id
    auth = headers(ctx.actor_user_id)
    current = client.get(url, headers=auth).json()['memory']
    assert current['contentAvailable'] is True
    source = client.post(base(ctx) + '/sources/read', headers=auth, json=dict(sourceRef=current['sourceRefs'][0]))
    assert source.status_code == 200 and source.json()['content'] == core.statement().content
    foreign = client.get(url, headers=headers(other))
    assert_error(foreign, 404, 'memory_not_found')
    rid = str(uuid4())
    result = client.patch(url, headers=headers(ctx.actor_user_id, rid), json=dict(requestId=rid, expectedVersion=1, intent='inactive'))
    assert result.status_code == 200, result.text
    with Session(engine) as db:
        invalidate_instruction(core.MemoryCommands(db, core.WorkspaceAccess(db)), ctx, current['sourceRefs'][0]['sourceId'])
    history = client.get(url + '/revisions', headers=auth).json()['items']
    for actual, expected in zip(history, CASES['readabilitySequence']['historyExpected'], strict=True):
        for key, value in expected.items():
            assert actual[key] == value
        assert set(actual).isdisjoint(CASES['readabilitySequence']['forbiddenResponseKeys'])
    for status in CASES['readabilitySequence']['listIncludedStatus']:
        assert len(client.get(base(ctx) + '/memories', params=dict(status=status), headers=auth).json()['items']) == 1
    for status in CASES['readabilitySequence']['listExcludedStatus']:
        assert client.get(base(ctx) + '/memories', params=dict(status=status), headers=auth).json()['items'] == []
    poll = client.get(base(ctx) + '/memories/requests/' + receipt.request_id, headers=auth).json()
    assert poll['contentAvailable'] is False and poll['currentVersion'] == 3
    with Session(engine) as db:
        rows = list(db.execute(select(MemoryRevision.version, MemoryRevision.intent, MemoryRevision.validity).order_by(MemoryRevision.version)))
        assert [list(row) for row in rows] == CASES['readabilitySequence']['persistedOracle']
    assert_error(client.post(base(ctx) + '/sources/read', headers=auth, json=dict(sourceRef=current['sourceRefs'][0])), 410, 'source_version_unavailable')
    assert_error(client.post(base(ctx) + '/sources/read', headers=headers(other), json=dict(sourceRef=current['sourceRefs'][0])), 404, 'source_not_found')


def test_delete_replay_erasure_and_cas(api):
    client, engine, ctx, other = api
    receipt = seed(api)
    url = base(ctx) + '/memories/' + receipt.resource.memory_id
    rid = str(uuid4())
    payload = dict(requestId=rid, expectedVersion=1, intent='inactive')
    response = client.patch(url, json=payload, headers=headers(ctx.actor_user_id, rid))
    assert response.status_code == 200
    assert client.patch(url, json=payload, headers=headers(ctx.actor_user_id, rid)).json() == response.json()
    changed = dict(payload, expectedVersion=2)
    assert_error(client.patch(url, json=changed, headers=headers(ctx.actor_user_id, rid)), 409, 'idempotency_conflict', rid)
    stale_id = str(uuid4())
    conflict = client.patch(url, json=dict(payload, requestId=stale_id), headers=headers(ctx.actor_user_id, stale_id))
    assert conflict.status_code == 409 and conflict.json()['detail']['currentVersion'] == 2
    deletion = str(uuid4())
    response = client.request('DELETE', url, json=dict(requestId=deletion, expectedVersion=2), headers=headers(ctx.actor_user_id, deletion))
    assert response.status_code == 200 and response.json()['cleanupState'] == 'completed'
    assert_error(client.get(url, headers=headers(ctx.actor_user_id)), 410, 'erased')
    assert_error(client.get(url + '/revisions', headers=headers(ctx.actor_user_id)), 410, 'erased')
    assert_error(client.get(url, headers=headers(other)), 404, 'memory_not_found')
    replay = client.patch(url, json=payload, headers=headers(ctx.actor_user_id, rid)).json()
    assert replay['memory']['contentAvailable'] is False
    assert replay['memory']['reason'] == 'erased'
    with Session(engine) as db:
        assert all(r.content is None and r.conditions is None and r.content_sha256 is None for r in db.scalars(select(MemoryRevision)))


def test_signed_paging_sources_and_scope(api, monkeypatch):
    client, _, ctx, other = api
    for _ in range(3):
        seed(api)
    auth = headers(ctx.actor_user_id)
    url = base(ctx) + '/memories'
    first = client.get(url, params=dict(limit=1), headers=auth).json()
    second = client.get(url, params=dict(limit=1, cursor=first['nextCursor']), headers=auth).json()
    assert first['items'][0]['id'] != second['items'][0]['id']
    for params, actor in [(dict(limit=2, cursor=first['nextCursor']),ctx.actor_user_id),
                          (dict(limit=1, cursor=first['nextCursor']+'x'),ctx.actor_user_id),
                          (dict(limit=1, cursor=first['nextCursor']),other)]:
        assert_error(client.get(url, params=params, headers=headers(actor)),422,'invalid_cursor')
    import ai_pdf_api.services.memory_management as service
    now = service.time.time()
    monkeypatch.setattr(service.time, 'time', lambda: now + 901)
    assert_error(client.get(url,params=dict(limit=1,cursor=first['nextCursor']),headers=auth),422,'invalid_cursor')
    assert_error(client.get(url,params=dict(scope='thread'),headers=auth),422,'invalid_scope')
    ref = first['items'][0]['sourceRefs'][0]
    for version in (0,True,'1'):
        assert_error(client.post(base(ctx)+'/sources/read',headers=auth,json=dict(sourceRef=dict(ref,sourceVersion=version))),422,'invalid_request')
    assert_error(client.post(base(ctx)+'/sources/read',headers=auth,json=dict(sourceRef=dict(ref,sourceVersion=2))),410,'source_version_unavailable')


ERROR_CASES = [c for c in CASES['errorCases'] if not c['id'].startswith('admission_') and c['race'] is None]
@pytest.mark.parametrize('case', ERROR_CASES, ids=lambda c:c['id'])
def test_error_fixture_precedence(api, case):
    client, engine, ctx, other = api
    receipt = seed(api)
    url = base(ctx) + '/memories/' + receipt.resource.memory_id
    rid = CASES['requestId']
    payload = dict(requestId=rid,expectedVersion=1,intent='inactive')
    actor = other if case['auth'] == 'workspace_owner' else ctx.actor_user_id
    if case['auth'] in ('nonmember','unknown_user'):
        actor = str(uuid4())
    auth = headers(actor, rid)
    if case['auth'] == 'missing':
        auth = {}
    if case['auth'] == 'invalid_token':
        auth['x-ai-pdf-internal-token'] = 'synthetic-invalid'
    if case['auth'] in ('archived','unknown_role'):
        with engine.begin() as db:
            if case['auth'] == 'archived':
                db.execute(update(Workspace).where(Workspace.id==ctx.workspace_id).values(archived_at=core.datetime.now(core.UTC)))
            else:
                db.execute(update(WorkspaceMembership).where(WorkspaceMembership.user_id==ctx.actor_user_id).values(role='unknown'))
    if case['payload'] == 'invalid_schema':
        payload['expectedVersion'] = True
    if case['payload'] == 'valid_body_missing_key':
        auth.pop('Idempotency-Key',None)
    if case['payload'] == 'invalid_json':
        response=client.patch(url,headers={**auth,'content-type':'application/json'},content='{')
    else:
        response=client.patch(url,headers=auth,json=payload)
    e=case['expected']
    assert_error(response,e['status'],e['code'],e['requestId'],e['retryable'])


@pytest.mark.parametrize('change', ['remove','role','archive'])
def test_revocation_after_actual_dependency_select(api, change):
    client, engine, ctx, _=api
    receipt=seed(api)
    fired=[]
    def revoke(conn,cursor,statement,parameters,context,many):
        if not fired and 'workspace_memberships.role' in statement and 'FOR UPDATE' not in statement:
            fired.append(True)
            with engine.begin() as db:
                if change=='remove':
                    db.execute(WorkspaceMembership.__table__.delete().where(WorkspaceMembership.user_id==ctx.actor_user_id))
                elif change=='role':
                    db.execute(update(WorkspaceMembership).where(WorkspaceMembership.user_id==ctx.actor_user_id).values(role='unknown'))
                else:
                    db.execute(update(Workspace).where(Workspace.id==ctx.workspace_id).values(archived_at=core.datetime.now(core.UTC)))
    event.listen(engine,'after_cursor_execute',revoke)
    rid=CASES['requestId']
    try:
        response=client.patch(base(ctx)+'/memories/'+receipt.resource.memory_id,headers=headers(ctx.actor_user_id,rid),json=dict(requestId=rid,expectedVersion=1,intent='inactive'))
        assert fired
        assert_error(response,404,'workspace_not_found',rid)
    finally:
        event.remove(engine,'after_cursor_execute',revoke)
    with Session(engine) as db:
        assert db.scalar(select(MemoryRevision.version).order_by(MemoryRevision.version.desc()).limit(1))==1


@pytest.mark.parametrize('action',['deactivate','remember','correct'])
def test_lost_database_ack_recovery(api,action):
    client,engine,ctx,_=api
    receipt=seed(api)
    rid=CASES['requestId']
    fired=[]
    def mark(session, flush_context):
        if any(isinstance(row,MemoryOperation) and row.request_id==rid for row in session.new):
            session.info['lose_ack']=True
    def lose(session):
        if session.info.get('lose_ack') and not fired:
            fired.append(True)
            raise SQLAlchemyError('synthetic_ack_loss')
    event.listen(Session,'after_flush',mark)
    event.listen(Session,'after_commit',lose)
    url=base(ctx)+'/memories/'+receipt.resource.memory_id
    payload=dict(requestId=rid,expectedVersion=1,intent='inactive')
    method='PATCH'; expected=2
    if action in ('remember','correct'):
        payload={**CASES['baseBody'],'requestId':rid}
        method='POST'; expected=1
        if action=='remember': url=base(ctx)+'/memories'
        else:
            url+='/corrections'; payload.pop('scope'); payload.pop('sourceRefs'); payload['expectedVersion']=1
    try:
        response=client.request(method,url,headers=headers(ctx.actor_user_id,rid),json=payload)
        assert_error(response,503,'outcome_unknown',rid,True)
    finally:
        event.remove(Session,'after_flush',mark)
        event.remove(Session,'after_commit',lose)
    poll=client.get(base(ctx)+'/memories/requests/'+rid,headers=headers(ctx.actor_user_id))
    assert poll.status_code==200 and poll.json()['currentVersion']==expected
    assert client.request(method,url,headers=headers(ctx.actor_user_id,rid),json=payload).json()['operationId']==poll.json()['operationId']


@pytest.mark.parametrize('change', ['remove','role'])
def test_conflict_metadata_reauthorizes_after_rollback(api, change):
    client, engine, ctx, _ = api
    receipt = seed(api)
    core.command(engine, 'deactivate', ctx, core.request(), receipt.resource.memory_id, 1)
    fired = []
    def alter(session, previous):
        if fired:
            return
        fired.append(True)
        with engine.begin() as db:
            predicate=WorkspaceMembership.user_id==ctx.actor_user_id
            if change=='remove':
                db.execute(WorkspaceMembership.__table__.delete().where(predicate))
            else:
                db.execute(update(WorkspaceMembership).where(predicate).values(role='unknown'))
    event.listen(Session,'after_soft_rollback',alter)
    rid=CASES['requestId']
    try:
        response=client.patch(base(ctx)+'/memories/'+receipt.resource.memory_id,
            headers=headers(ctx.actor_user_id,rid),json=dict(requestId=rid,expectedVersion=1,intent='inactive'))
        assert fired
        assert_error(response,404,'workspace_not_found',rid)
    finally:
        event.remove(Session,'after_soft_rollback',alter)
    with Session(engine) as db:
        assert db.scalar(select(MemoryRevision.version).order_by(MemoryRevision.version.desc()).limit(1))==2


def test_one_surviving_support_cannot_expose_history(api):
    from citeframe_persistence.models.memory import MemorySource, MemoryUse
    client, engine, ctx, _=api
    first,second=seed(api),seed(api)
    with Session(engine) as db,db.begin():
        db.add(MemoryUse(id=str(uuid4()),workspace_id=ctx.workspace_id,
            consumer_revision_id=first.resource.revision_id,source_id=second.resource.confirmation_source_id,
            use_mode='support',atom_key='additional',support_group='instruction',relation='supports'))
        db.execute(update(MemorySource).where(MemorySource.id==second.resource.confirmation_source_id).values(state='stale'))
    url=base(ctx)+'/memories/'+first.resource.memory_id
    value=client.get(url,headers=headers(ctx.actor_user_id)).json()['memory']
    assert value['validity']=='valid' and value['displayStatus']=='invalidated'
    assert value['contentAvailable'] is False and 'content' not in value
    listed=client.get(base(ctx)+'/memories',params=dict(status='invalidated'),headers=headers(ctx.actor_user_id)).json()['items']
    assert len(listed)==2 and all(not x['contentAvailable'] for x in listed)


def test_concurrent_replay_and_cas(api):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    client,_,ctx,_=api
    receipt=seed(api)
    url=base(ctx)+'/memories/'+receipt.resource.memory_id
    rid=str(uuid4())
    barrier=Barrier(2)
    def patch(request_id,version):
        barrier.wait()
        return client.patch(url,headers=headers(ctx.actor_user_id,request_id),
            json=dict(requestId=request_id,expectedVersion=version,intent='inactive'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        a,b=[f.result() for f in [pool.submit(patch,rid,1),pool.submit(patch,rid,1)]]
    assert a.status_code==b.status_code==200 and a.json()['operationId']==b.json()['operationId']
    barrier=Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=[f.result() for f in [pool.submit(patch,str(uuid4()),2),pool.submit(patch,str(uuid4()),2)]]
    assert sorted(r.status_code for r in results)==[200,409]


@pytest.mark.parametrize('delta', [
    {'confirmation':'user_confirmed'}, {'ownerUserId':str(uuid4())},
    {'scope':{'kind':'thread'}}, {'pinned':1}, {'validUntil':1234567},
    {'validUntil':'1234567'}, {'validUntil':'2026-09-28T01:00:00'},
    {'conditions':{'subject':'fixture','applicability':'test','effectiveFrom':123}},
    {'sourceRefs':[{'sourceId':str(uuid4())}]},
])
def test_proposition_dtos_strict(delta):
    from pydantic import ValidationError
    from ai_pdf_api.schemas.memory import CreateRequest
    with pytest.raises(ValidationError):
        CreateRequest.model_validate({**CASES['baseBody'],**delta})


def test_history_cursor_and_source_unicode_tail(api):
    client,engine,ctx,_=api
    content='字' * 3992 + '😀END尾部'
    receipt=core.command(engine,'remember',ctx,core.request(),core.MemoryStatement(content,core.MemoryConditions('tail','fixture')))
    mid=receipt.resource.memory_id
    core.command(engine,'deactivate',ctx,core.request(),mid,1)
    core.command(engine,'deactivate',ctx,core.request(),mid,2)
    url=base(ctx)+'/memories/'+mid
    first=client.get(url+'/revisions',params=dict(limit=1),headers=headers(ctx.actor_user_id)).json()
    second=client.get(url+'/revisions',params=dict(limit=1,cursor=first['nextCursor']),headers=headers(ctx.actor_user_id)).json()
    third=client.get(url+'/revisions',params=dict(limit=1,cursor=second['nextCursor']),headers=headers(ctx.actor_user_id)).json()
    assert [x['items'][0]['version'] for x in (first,second,third)]==[1,2,3]
    assert third['nextCursor'] is None
    another=seed(api).resource.memory_id
    assert_error(client.get(base(ctx)+'/memories/'+another+'/revisions',params=dict(limit=1,cursor=first['nextCursor']),headers=headers(ctx.actor_user_id)),422,'invalid_cursor')
    source=client.post(base(ctx)+'/sources/read',headers=headers(ctx.actor_user_id),json=dict(sourceRef=first['items'][0]['sourceRefs'][0]))
    assert source.status_code==200 and source.json()['content']==content
    assert source.json()['truncated'] is False


def test_reserved_fields_and_source_expansion_errors(api):
    client,_,ctx,_=api
    receipt=seed(api)
    url=base(ctx)+'/memories/'+receipt.resource.memory_id
    rid=str(uuid4())
    for field,value,code in [('author','foreign','invalid_request'),('confirmation','user_confirmed','invalid_request'),('pinned',False,'unsupported_operation')]:
        response=client.patch(url,headers=headers(ctx.actor_user_id,rid),json=dict(requestId=rid,expectedVersion=1,intent='inactive',**{field:value}))
        assert_error(response,422,code,rid)
    assert_error(client.get(base(ctx)+'/memories',params=dict(cursor='x'*4097),headers=headers(ctx.actor_user_id)),422,'invalid_cursor')
    current=client.get(url,headers=headers(ctx.actor_user_id)).json()['memory']
    assert_error(client.post(base(ctx)+'/sources/read',headers=headers(ctx.actor_user_id),json=dict(sourceRef=current['sourceRefs'][0],before=1)),422,'invalid_source_ref')


SENSITIVE = "password=ADMISSION_SYNTHETIC_42"


def table_snapshot(engine):
    with engine.connect() as db:
        return {table: sorted(json.dumps(row,sort_keys=True) for row in
                db.execute(text(f"SELECT to_jsonb(t) FROM {table} t")).scalars())
                for table in core.MIGRATION.TABLES}


@pytest.mark.parametrize('action', ['remember','correct'])
@pytest.mark.parametrize('field', ['content','subject','applicability'])
def test_http_admission_three_fields_no_write_and_clean_recovery(api, action, field, caplog):
    import copy
    from dataclasses import asdict
    from hashlib import sha256
    import logging
    from citeframe_memory.commands import canonical_hash
    client,engine,ctx,_=api
    first=seed(api)
    request_id=CASES['requestId']
    payload=copy.deepcopy(CASES['baseBody'])
    payload['requestId']=request_id
    url=base(ctx)+'/memories'
    target=None
    if action=='correct':
        target=first.resource.memory_id
        url+='/'+target+'/corrections'
        payload.pop('scope'); payload.pop('sourceRefs')
        payload['expectedVersion']=1
    if field=='content': payload['content']=SENSITIVE
    else: payload['conditions'][field]=SENSITIVE
    before=table_snapshot(engine)
    writes=[]
    def observe(conn,cursor,sql,params,context,many):
        if sql.lstrip().split(None,1)[0].upper() in ('INSERT','UPDATE','DELETE'):
            writes.append(sql)
    caplog.set_level(logging.DEBUG)
    event.listen(engine,'before_cursor_execute',observe)
    try:
        response=client.post(url,json=payload,headers=headers(ctx.actor_user_id,request_id))
    finally:
        event.remove(engine,'before_cursor_execute',observe)
    assert_error(response,422,'sensitive_content_unsupported',request_id)
    assert not writes and table_snapshot(engine)==before
    statement=core.MemoryStatement(payload['content'],core.MemoryConditions(payload['conditions']['subject'],payload['conditions']['applicability']),payload['kind'],payload['pinned'])
    digest=canonical_hash(dict(method='POST',path=f"/memory/{target or ''}/{action}",expectedVersion=1 if target else None,statement=asdict(statement)))
    for forbidden in (SENSITIVE,sha256(SENSITIVE.encode()).hexdigest(),digest):
        assert forbidden not in response.text and forbidden not in caplog.text
    assert_error(client.get(base(ctx)+'/memories/requests/'+request_id,headers=headers(ctx.actor_user_id)),404,'operation_not_found',request_id)
    caplog.set_level(logging.WARNING)
    if field=='content': payload['content']='Edited safe project instruction.'
    else: payload['conditions'][field]='Edited safe condition.'
    saved=client.post(url,json=payload,headers=headers(ctx.actor_user_id,request_id))
    assert saved.status_code==201,saved.text
    replay=client.post(url,json=payload,headers=headers(ctx.actor_user_id,request_id))
    assert replay.json()==saved.json()


def test_full_http_create_correct_source_delete_recovery(api):
    client,_,ctx,other=api
    request_id=str(uuid4())
    payload={**CASES['baseBody'],'requestId':request_id}
    url=base(ctx)+'/memories'
    created=client.post(url,json=payload,headers=headers(ctx.actor_user_id,request_id))
    assert created.status_code==201,created.text
    first=created.json(); mid=first['memory']['id']
    assert first['memory']['confirmation']=='explicit_remember'
    correction=str(uuid4())
    corrected=dict(requestId=correction,expectedVersion=1,content='Use 12 ms only in the fixture.',kind='constraint',conditions=payload['conditions'],pinned=True)
    response=client.post(url+'/'+mid+'/corrections',json=corrected,headers=headers(ctx.actor_user_id,correction))
    assert response.status_code==201,response.text
    successor=response.json()
    assert successor['supersededMemoryId']==mid and successor['memory']['id']!=mid
    predecessor=client.get(url+'/'+mid,headers=headers(ctx.actor_user_id)).json()['memory']
    assert predecessor['intent']=='superseded' and predecessor['version']==2
    history=client.get(url+'/'+mid+'/revisions',headers=headers(ctx.actor_user_id)).json()['items']
    assert [x['intent'] for x in history]==['active','superseded']
    source=client.post(base(ctx)+'/sources/read',headers=headers(ctx.actor_user_id),json=dict(sourceRef=successor['memory']['sourceRefs'][0]))
    assert source.json()['content']==corrected['content']
    foreign=str(uuid4())
    assert_error(client.post(url+'/'+mid+'/corrections',json=dict(corrected,requestId=foreign),headers=headers(other,foreign)),404,'memory_not_found',foreign)
    deletion=str(uuid4())
    erased=client.request('DELETE',url+'/'+mid,json=dict(requestId=deletion,expectedVersion=2),headers=headers(ctx.actor_user_id,deletion))
    assert erased.status_code==200
    assert client.post(base(ctx)+'/sources/read',json=dict(sourceRef=successor['memory']['sourceRefs'][0]),headers=headers(ctx.actor_user_id)).json()['content']==corrected['content']
    replay=client.post(url,json=payload,headers=headers(ctx.actor_user_id,request_id)).json()
    assert replay['memory']['contentAvailable'] is False
    assert client.post(url+'/'+mid+'/corrections',json=corrected,headers=headers(ctx.actor_user_id,correction)).json()['memory']['id']==successor['memory']['id']
    poll=client.get(url+'/requests/'+correction,headers=headers(ctx.actor_user_id)).json()
    assert poll['resourceId']==successor['memory']['id'] and 'content' not in poll


def test_create_replay_and_correction_race_through_api(api):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    client,engine,ctx,_=api
    url=base(ctx)+'/memories'
    rid=str(uuid4()); body={**CASES['baseBody'],'requestId':rid}
    barrier=Barrier(2)
    def create():
        barrier.wait()
        return client.post(url,json=body,headers=headers(ctx.actor_user_id,rid))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=[f.result() for f in (pool.submit(create),pool.submit(create))]
    assert all(r.status_code==201 for r in responses)
    assert responses[0].json()==responses[1].json()
    mid=responses[0].json()['memory']['id']
    barrier=Barrier(2)
    def correct():
        request_id=str(uuid4())
        payload={k:v for k,v in body.items() if k not in ('scope','sourceRefs')}
        payload.update(requestId=request_id,expectedVersion=1,content='One accepted correction.')
        barrier.wait()
        return client.post(url+'/'+mid+'/corrections',json=payload,headers=headers(ctx.actor_user_id,request_id))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=[f.result() for f in (pool.submit(correct),pool.submit(correct))]
    assert sorted(r.status_code for r in results)==[201,409]
    with engine.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM memory_records WHERE supersedes_id=:mid'),dict(mid=mid))==1
        assert db.scalar(text('SELECT count(*) FROM memory_operations'))==2


def test_create_missing_fields_are_structural_before_unsupported_scope(api):
    client,_,ctx,_=api
    rid=str(uuid4())
    body={**CASES['baseBody'],'requestId':rid}
    body.pop('scope')
    assert_error(client.post(base(ctx)+'/memories',json=body,headers=headers(ctx.actor_user_id,rid)),422,'invalid_request',rid)
    assert_error(client.post(base(ctx)+'/memories',json={**body,'scope':7},headers=headers(ctx.actor_user_id,rid)),422,'invalid_request',rid)
    assert_error(client.post(base(ctx)+'/memories',json={**body,'scope':{'kind':'workspace'},'sourceRefs':7},headers=headers(ctx.actor_user_id,rid)),422,'invalid_request',rid)
    assert_error(client.post(base(ctx)+'/memories',json={**CASES['baseBody'],'requestId':rid,'scope':{'kind':'thread'}},headers=headers(ctx.actor_user_id,rid)),422,'invalid_scope',rid)
    body['scope']={'kind':'thread'}; body.pop('content')
    assert_error(client.post(base(ctx)+'/memories',json=body,headers=headers(ctx.actor_user_id,rid)),422,'invalid_request',rid)


def test_response_bytes_render_under_authorization_transaction(api, monkeypatch):
    from fastapi.responses import JSONResponse
    client,engine,ctx,_=api
    guards=[]; rendered=[]
    def guard(conn,cursor,sql,params,context,many):
        if 'workspace_memberships' in sql and 'FOR UPDATE' in sql:
            guards.append(conn)
    original=JSONResponse.render
    def render(response,content):
        assert guards and not guards[-1].closed and guards[-1].in_transaction()
        rendered.append(True)
        return original(response,content)
    event.listen(engine,'after_cursor_execute',guard)
    monkeypatch.setattr(JSONResponse,'render',render)
    try:
        rid=str(uuid4())
        created=client.post(base(ctx)+'/memories',json={**CASES['baseBody'],'requestId':rid},headers=headers(ctx.actor_user_id,rid))
        assert created.status_code==201
        current=client.get(base(ctx)+'/memories/'+created.json()['memory']['id'],headers=headers(ctx.actor_user_id))
        assert current.status_code==200 and len(rendered)==2
    finally:
        event.remove(engine,'after_cursor_execute',guard)


def test_cross_workspace_record_source_operation_and_cursor(api):
    client,engine,ctx,other=api
    receipt=seed(api); seed(api)
    original=base(ctx)
    current=client.get(original+'/memories/'+receipt.resource.memory_id,headers=headers(ctx.actor_user_id)).json()['memory']
    page=client.get(original+'/memories',params=dict(limit=1),headers=headers(ctx.actor_user_id)).json()
    wid=str(uuid4())
    with Session(engine) as db,db.begin():
        db.add(Workspace(id=wid,name='second synthetic workspace',created_by_user_id=other)); db.flush()
        db.add(WorkspaceMembership(id=str(uuid4()),workspace_id=wid,user_id=ctx.actor_user_id,role='member'))
    other_base='/v1/workspaces/'+wid
    assert_error(client.get(other_base+'/memories/'+receipt.resource.memory_id,headers=headers(ctx.actor_user_id)),404,'memory_not_found')
    assert_error(client.post(other_base+'/sources/read',json=dict(sourceRef=current['sourceRefs'][0]),headers=headers(ctx.actor_user_id)),404,'source_not_found')
    assert_error(client.get(other_base+'/memories/requests/'+receipt.request_id,headers=headers(ctx.actor_user_id)),404,'operation_not_found',receipt.request_id)
    assert_error(client.get(other_base+'/memories/operations/'+receipt.operation_id,headers=headers(ctx.actor_user_id)),404,'operation_not_found')
    assert_error(client.get(other_base+'/memories',params=dict(limit=1,cursor=page['nextCursor']),headers=headers(ctx.actor_user_id)),422,'invalid_cursor')


@pytest.mark.parametrize('scenario', ['conflict', 'terminal', 'current', 'history', 'source'])
@pytest.mark.parametrize('revoke_before_read', [False, True])
def test_owner_error_serialization_holds_guards_until_bytes(api, monkeypatch, scenario, revoke_before_read):
    from fastapi.responses import JSONResponse
    client, engine, ctx, _ = api
    receipt = seed(api)
    mid = receipt.resource.memory_id
    url = base(ctx) + '/memories/' + mid
    ref = client.get(url, headers=headers(ctx.actor_user_id)).json()['memory']['sourceRefs'][0]
    if scenario == 'conflict':
        core.command(engine, 'deactivate', ctx, core.request(), mid, 1)
    else:
        core.command(engine, 'delete', ctx, core.request(), mid, 1)
    rid = str(uuid4())
    code = {'conflict': 'version_conflict', 'terminal': 'terminal_memory',
            'current': 'erased', 'history': 'erased', 'source': 'source_version_unavailable'}[scenario]
    guards, rendered, sent, revoked = [], [], [], []

    def revoke():
        with engine.begin() as db:
            db.execute(text('DELETE FROM workspace_memberships WHERE workspace_id=:w AND user_id=:u'),
                       dict(w=ctx.workspace_id, u=ctx.actor_user_id))
        revoked.append(True)

    def observe(conn, cursor, sql, params, context, many):
        if 'workspace_memberships' in sql and 'FOR UPDATE' in sql:
            guards.append(conn)
        elif (revoke_before_read and not revoked and 'workspace_memberships.role' in sql
              and 'FOR UPDATE' not in sql):
            revoke()

    original_render, original_send = JSONResponse.render, JSONResponse.__call__

    def render(response, content):
        if content.get('detail', {}).get('code') == code:
            assert not revoke_before_read
            assert guards and not guards[-1].closed and guards[-1].in_transaction()
            with pytest.raises(SQLAlchemyError) as blocked:
                with engine.begin() as db:
                    db.execute(text("SET LOCAL lock_timeout='100ms'"))
                    db.execute(text('DELETE FROM workspace_memberships WHERE workspace_id=:w AND user_id=:u'),
                               dict(w=ctx.workspace_id, u=ctx.actor_user_id))
            assert blocked.value.orig.sqlstate == '55P03'
            value = original_render(response, content)
            assert guards[-1].in_transaction()
            rendered.append(value)
            return value
        return original_render(response, content)

    async def send(response, scope, receive, send):
        if rendered and not sent:
            assert guards[-1].closed or not guards[-1].in_transaction()
            assert response.body == rendered[-1]
            revoke()
            sent.append(True)
        return await original_send(response, scope, receive, send)

    event.listen(engine, 'after_cursor_execute', observe)
    monkeypatch.setattr(JSONResponse, 'render', render)
    monkeypatch.setattr(JSONResponse, '__call__', send)
    try:
        if scenario in ('conflict', 'terminal'):
            response = client.patch(url, json=dict(requestId=rid, expectedVersion=1 if scenario == 'conflict' else 2,
                                                   intent='inactive'), headers=headers(ctx.actor_user_id, rid))
        elif scenario == 'source':
            response = client.post(base(ctx) + '/sources/read', json=dict(sourceRef=ref), headers=headers(ctx.actor_user_id))
        else:
            response = client.get(url + ('/revisions' if scenario == 'history' else ''), headers=headers(ctx.actor_user_id))
        if revoke_before_read:
            assert_error(response, 404, 'workspace_not_found', rid if scenario in ('conflict', 'terminal') else None)
            assert not rendered and not sent and revoked
        else:
            assert response.status_code == (409 if scenario in ('conflict', 'terminal') else 410)
            assert response.json()['detail']['code'] == code
            if scenario in ('conflict', 'terminal'):
                assert response.json()['detail']['currentVersion'] == 2
            assert rendered and sent and revoked
        assert_error(client.get(url, headers=headers(ctx.actor_user_id)), 404, 'workspace_not_found')
    finally:
        event.remove(engine, 'after_cursor_execute', observe)
