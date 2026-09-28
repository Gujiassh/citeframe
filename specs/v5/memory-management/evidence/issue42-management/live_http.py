"""Real mounted-app HTTP oracle; only a caller-created disposable PostgreSQL DB."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[5]
sys.path[:0] = [str(ROOT / p) for p in (
    'apps/api/src', 'packages/backend-contracts/src', 'packages/backend-persistence/src',
    'packages/research-persistence/src', 'packages/memory-service/src')]
from citeframe_contracts.memory import AccessContext, MemoryConditions, MemoryRequest, MemoryStatement
from citeframe_memory.access import WorkspaceAccess
from citeframe_memory.commands import MemoryCommands, canonical_hash
from citeframe_memory.lifecycle import invalidate_instruction
from citeframe_persistence.models import User, Workspace, WorkspaceMembership
from citeframe_persistence.models.memory import MemoryRevision

URL = os.environ['CITEFRAME_MEMORY42_POSTGRES_URL']
parsed = make_url(URL)
assert parsed.host == '127.0.0.1' and parsed.database == 'citeframe_memory42_test'
PORT = int(os.environ.get('CITEFRAME_MEMORY_HTTP_PORT', '56543'))
with socket.socket() as check:
    check.bind(('127.0.0.1', PORT))
engine = create_engine(URL)
actor, owner, outsider, workspace, second_workspace = [str(uuid4()) for _ in range(5)]
with Session(engine) as db, db.begin():
    for uid in (actor, owner, outsider):
        db.add(User(id=uid, email=uid+'@test.invalid', name='synthetic', password_hash='unused', avatar_url=''))
    db.flush()
    for wid in (workspace, second_workspace):
        db.add(Workspace(id=wid, name='management live fixture', created_by_user_id=owner))
    db.flush()
    for wid in (workspace, second_workspace):
        for uid, role in ((actor,'member'),(owner,'owner')):
            db.add(WorkspaceMembership(id=str(uuid4()),workspace_id=wid,user_id=uid,role=role))
ctx=AccessContext(actor, workspace, 'management', 'private')
def new_request():
    return MemoryRequest(str(uuid4()),str(uuid4()))
def create_body(request_id):
    return dict(requestId=request_id,kind='constraint',content='Use 37.5 ms only for batch=8; never production.',
                conditions=dict(subject='HTTP_SYNTHETIC_CONDITIONS_ONLY',applicability='Disposable integration fixture',effectiveFrom=None),
                scope=dict(kind='workspace'),pinned=True,validUntil=None,sourceRefs=[])
def seed():
    request=new_request()
    return call('create','POST','/memories',201,json=create_body(request.request_id),headers=auth(key=request.idempotency_key))
def snapshot():
    tables=('memory_instructions','memory_sources','memory_records','memory_revisions','memory_uses','memory_operations')
    with engine.connect() as db:
        return {table: sorted(json.dumps(r,sort_keys=True) for r in db.execute(text(f"SELECT to_jsonb(t) FROM {table} t")).scalars()) for table in tables}
token=secrets.token_urlsafe(32)
env={**os.environ,'AI_PDF_DATABASE_URL':URL,'AI_PDF_API_INTERNAL_TOKEN':token,
     'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':os.pathsep.join(sys.path[:5])}
runtime=ROOT/'.local-runtime/memory-management'
runtime.mkdir(parents=True,exist_ok=True)
log=(runtime/'http.log').open('w',encoding='utf-8')
process=subprocess.Popen([sys.executable,'-B','-m','uvicorn','ai_pdf_api.main:app','--host','127.0.0.1',
                         '--port',str(PORT),'--no-access-log'],cwd=ROOT,env=env,stdout=log,stderr=log,
                         creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
records=[]
base=f'http://127.0.0.1:{PORT}/v1/workspaces/{workspace}'
def auth(uid=actor, key=None):
    result={'x-user-id':uid,'x-ai-pdf-internal-token':token}
    if key: result['Idempotency-Key']=key
    return result
client=httpx.Client(timeout=20)
def call(label,method,path,status=200,code=None,**kwargs):
    headers=kwargs.pop('headers',auth())
    response=client.request(method,base+path,headers=headers,**kwargs)
    assert response.status_code==status,(label,response.status_code,response.text)
    body=response.json() if response.content else None
    if code:
        assert body['detail']['code']==code,(label,body)
        assert 'currentVersion' not in body['detail']
    records.append(dict(case=label,method=method,path=path,status=status,code=code,passed=True))
    return body
def drop_response(label, method, path, payload, request):
    body=json.dumps(payload).encode()
    wire=(f'{method} /v1/workspaces/{workspace}{path} HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n'
          f'x-user-id: {actor}\r\nx-ai-pdf-internal-token: {token}\r\nIdempotency-Key: {request.idempotency_key}\r\n'
          f'Content-Length: {len(body)}\r\nConnection: close\r\n\r\n').encode()+body
    with socket.create_connection(('127.0.0.1',PORT)) as sock:
        sock.sendall(wire)
        sock.shutdown(socket.SHUT_WR)
    for _ in range(50):
        recovery=client.get(base+'/memories/requests/'+request.request_id,headers=auth())
        if recovery.status_code==200: break
        time.sleep(.05)
    assert recovery.status_code==200
    records.append(dict(case=label,status=200,passed=True))
    return recovery.json()

try:
    for _ in range(100):
        if process.poll() is not None: raise RuntimeError('local API process exited; inspect local sanitized log')
        try:
            if client.get(f'http://127.0.0.1:{PORT}/openapi.json').status_code==200: break
        except httpx.TransportError: pass
        time.sleep(.2)
    else: raise RuntimeError('local API startup deadline')
    schema=client.get(f'http://127.0.0.1:{PORT}/openapi.json').json()
    paths={p:v for p,v in schema['paths'].items() if '/memories' in p or p.endswith('/sources/read')}
    components={}
    def collect(value):
        if isinstance(value,dict):
            if '$ref' in value:
                name=value['$ref'].rsplit('/',1)[-1]
                if name not in components:
                    components[name]=schema['components']['schemas'][name]
                    collect(components[name])
            for nested in value.values(): collect(nested)
        elif isinstance(value,list):
            for nested in value: collect(nested)
    collect(paths)
    Path(__file__).with_name('openapi.json').write_text(json.dumps(dict(openapi=schema['openapi'],
        info=schema['info'],paths=paths,components=dict(schemas=components)),indent=2)+'\n',encoding='utf-8')
    initial=call('first_use_empty','GET','/memories')
    assert initial==dict(items=[],nextCursor=None)
    unsupported=new_request()
    payload=create_body(unsupported.request_id); payload['scope']={'kind':'thread'}
    call('create_scope_refused','POST','/memories',422,'invalid_scope',json=payload,headers=auth(key=unsupported.idempotency_key))
    payload=create_body(unsupported.request_id); payload['ownerUserId']=owner
    call('create_owner_grant_refused','POST','/memories',422,'invalid_request',json=payload,headers=auth(key=unsupported.idempotency_key))
    payload=create_body(unsupported.request_id); payload['sourceRefs']=[{'sourceId':str(uuid4())}]
    call('create_source_grant_refused','POST','/memories',422,'invalid_source_ref',json=payload,headers=auth(key=unsupported.idempotency_key))
    created=seed(); mid=created['memory']['id']
    path='/memories/'+mid
    current=call('current','GET',path)['memory']
    ref=current['sourceRefs'][0]
    assert current['createdAt'].endswith('Z')
    call('exact_source','POST','/sources/read',json=dict(sourceRef=ref))
    predecessor=mid
    correction=new_request()
    correction_body=create_body(correction.request_id)
    correction_body.pop('scope'); correction_body.pop('sourceRefs')
    correction_body.update(expectedVersion=1,content='Use 12 ms only for the fixture; never production.')
    successor=call('correct','POST',path+'/corrections',201,json=correction_body,headers=auth(key=correction.idempotency_key))
    assert successor['supersededMemoryId']==predecessor and successor['memory']['id']!=predecessor
    assert call('superseded_current','GET',path)['memory']['intent']=='superseded'
    replay=call('correction_replay','POST',path+'/corrections',201,json=correction_body,headers=auth(key=correction.idempotency_key))
    assert replay['operationId']==successor['operationId']
    stale_correction=new_request()
    conflict=call('correction_cas','POST',path+'/corrections',409,json=dict(correction_body,requestId=stale_correction.request_id),headers=auth(key=stale_correction.idempotency_key))
    assert conflict['detail']['code']=='version_conflict' and conflict['detail']['currentVersion']==2
    mid=successor['memory']['id']; path='/memories/'+mid; ref=successor['memory']['sourceRefs'][0]
    source=call('corrected_source','POST','/sources/read',json=dict(sourceRef=ref))
    assert source['content']==correction_body['content']
    erase_predecessor=new_request()
    call('erase_predecessor','DELETE','/memories/'+predecessor,json=dict(requestId=erase_predecessor.request_id,expectedVersion=2),headers=auth(key=erase_predecessor.idempotency_key))
    assert call('successor_source_survives','POST','/sources/read',json=dict(sourceRef=ref))['content']==correction_body['content']

    sensitive='password=ADMISSION_SYNTHETIC_42'
    forbidden_log_values={sensitive,sha256(sensitive.encode()).hexdigest()}
    for action in ('remember','correct'):
        for field in ('content','subject','applicability'):
            request=new_request()
            bad=create_body(request.request_id)
            admission_path='/memories'
            target=None
            if action=='correct':
                target=mid
                admission_path=path+'/corrections'
                bad.pop('scope'); bad.pop('sourceRefs'); bad['expectedVersion']=1
            if field=='content': bad['content']=sensitive
            else: bad['conditions'][field]=sensitive
            statement=MemoryStatement(bad['content'],MemoryConditions(bad['conditions']['subject'],bad['conditions']['applicability']),bad['kind'],bad['pinned'])
            digest=canonical_hash(dict(method='POST',path=f"/memory/{target or ''}/{action}",expectedVersion=1 if target else None,statement=asdict(statement)))
            forbidden_log_values.add(digest)
            before=snapshot()
            error=call('admission_'+action+'_'+field,'POST',admission_path,422,'sensitive_content_unsupported',json=bad,headers=auth(key=request.idempotency_key))
            assert error['detail']['requestId']==request.request_id and error['detail']['retryable'] is False
            assert snapshot()==before
            for forbidden in (sensitive,sha256(sensitive.encode()).hexdigest(),digest):
                assert forbidden not in json.dumps(error)
            call('rejected_request_absent_'+action+'_'+field,'GET','/memories/requests/'+request.request_id,404,'operation_not_found')
    # A rejected create leaves its identities reusable for an edited explicit request.
    edit=new_request()
    bad=create_body(edit.request_id); bad['content']=sensitive
    call('admission_before_edit','POST','/memories',422,'sensitive_content_unsupported',json=bad,headers=auth(key=edit.idempotency_key))
    clean=create_body(edit.request_id)
    saved=call('edited_same_identity','POST','/memories',201,json=clean,headers=auth(key=edit.idempotency_key))
    assert call('edited_create_replay','POST','/memories',201,json=clean,headers=auth(key=edit.idempotency_key))['operationId']==saved['operationId']

    call('owner_cannot_read_member','GET',path,404,'memory_not_found',headers=auth(owner))
    call('outsider','GET',path,404,'workspace_not_found',headers=auth(outsider))
    call('missing_auth','GET',path,401,'authentication_required',headers={})
    call('malformed_before_auth','PATCH',path,422,'invalid_request',headers={'content-type':'application/json'},content='{')
    call('auth_before_missing_key','PATCH',path,401,'authentication_required',headers={},json={})
    call('workspace_before_bad_body','PATCH',path,404,'workspace_not_found',headers=auth(outsider),json={'expectedVersion':True})
    call('unsupported_scope','GET','/memories?scope=thread',422,'invalid_scope')
    call('unknown_query','GET','/memories?author=foreign',422,'invalid_request')
    call('source_version','POST','/sources/read',410,'source_version_unavailable',json=dict(sourceRef=dict(ref,sourceVersion=2)))
    call('foreign_source_version','POST','/sources/read',404,'source_not_found',headers=auth(owner),json=dict(sourceRef=dict(ref,sourceVersion=2)))
    for _ in range(2): seed()
    first=call('page1','GET','/memories?limit=1')
    page=call('page2','GET','/memories',params=dict(limit=1,cursor=first['nextCursor']))
    assert page['items'][0]['id']!=first['items'][0]['id']
    call('foreign_cursor','GET','/memories',422,'invalid_cursor',headers=auth(owner),params=dict(limit=1,cursor=first['nextCursor']))
    call('tampered_cursor','GET','/memories',422,'invalid_cursor',params=dict(limit=1,cursor=first['nextCursor']+'x'))
    other_path=f'http://127.0.0.1:{PORT}/v1/workspaces/{second_workspace}/memories/{mid}'
    assert client.get(other_path,headers=auth()).status_code==404
    records.append(dict(case='cross_workspace_id',status=404,passed=True))
    other_base=f'http://127.0.0.1:{PORT}/v1/workspaces/{second_workspace}'
    response=client.post(other_base+'/sources/read',json=dict(sourceRef=ref),headers=auth())
    assert response.status_code==404 and response.json()['detail']['code']=='source_not_found'
    records.append(dict(case='cross_workspace_source',status=404,passed=True))
    response=client.get(other_base+'/memories/requests/'+created['requestId'],headers=auth())
    assert response.status_code==404 and response.json()['detail']['code']=='operation_not_found'
    records.append(dict(case='cross_workspace_request',status=404,passed=True))
    response=client.get(other_base+'/memories/operations/'+created['operationId'],headers=auth())
    assert response.status_code==404 and response.json()['detail']['code']=='operation_not_found'
    records.append(dict(case='cross_workspace_operation',status=404,passed=True))
    request=new_request()
    payload=dict(requestId=request.request_id,expectedVersion=1,intent='inactive')
    saved=call('deactivate','PATCH',path,json=payload,headers=auth(key=request.idempotency_key))
    replay=call('same_key_replay','PATCH',path,json=payload,headers=auth(key=request.idempotency_key))
    assert replay['operationId']==saved['operationId']
    call('key_conflict','PATCH',path,409,'idempotency_conflict',json=dict(payload,expectedVersion=2),headers=auth(key=request.idempotency_key))
    stale=new_request()
    conflict=call('stale_version','PATCH',path,409,json=dict(payload,requestId=stale.request_id),headers=auth(key=stale.idempotency_key))
    assert conflict['detail']['currentVersion']==2
    with Session(engine) as db:
        invalidate_instruction(MemoryCommands(db,WorkspaceAccess(db)),ctx,ref['sourceId'])
    history=call('immutable_history','GET',path+'/revisions')['items']
    assert [(r['version'],r['validity'],r['contentAvailable']) for r in history]==[(1,'valid',False),(2,'valid',False),(3,'invalidated',False)]
    assert all('content' not in r and 'conditions' not in r and 'sourceRefs' not in r for r in history)
    poll=call('request_receipt','GET','/memories/requests/'+request.request_id)
    assert poll['currentVersion']==3 and not poll['contentAvailable']
    call('operation_receipt','GET','/memories/operations/'+poll['operationId'])
    call('invalidated_source','POST','/sources/read',410,'source_version_unavailable',json=dict(sourceRef=ref))
    lost=new_request()
    recovery=drop_response('lost_deactivate_http_ack','PATCH',path,dict(requestId=lost.request_id,expectedVersion=3,intent='inactive'),lost)
    assert recovery['currentVersion']==4
    lost_create=new_request(); lost_body=create_body(lost_create.request_id)
    recovered_create=drop_response('lost_create_http_ack','POST','/memories',lost_body,lost_create)
    assert recovered_create['currentVersion']==1
    assert call('lost_create_replay','POST','/memories',201,json=lost_body,headers=auth(key=lost_create.idempotency_key))['operationId']==recovered_create['operationId']
    lost_correct=new_request()
    lost_correct_body=create_body(lost_correct.request_id)
    lost_correct_body.pop('scope'); lost_correct_body.pop('sourceRefs'); lost_correct_body['expectedVersion']=1
    lost_correct_path='/memories/'+recovered_create['resourceId']+'/corrections'
    recovered_correct=drop_response('lost_correct_http_ack','POST',lost_correct_path,lost_correct_body,lost_correct)
    assert recovered_correct['currentVersion']==1
    assert call('lost_correct_replay','POST',lost_correct_path,201,json=lost_correct_body,headers=auth(key=lost_correct.idempotency_key))['operationId']==recovered_correct['operationId']
    duplicate=new_request(); duplicate_body=create_body(duplicate.request_id)
    def concurrent_create(_):
        return client.post(base+'/memories',headers=auth(key=duplicate.idempotency_key),json=duplicate_body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        duplicate_results=list(pool.map(concurrent_create,range(2)))
    assert all(r.status_code==201 for r in duplicate_results)
    assert duplicate_results[0].json()==duplicate_results[1].json()
    records.append(dict(case='concurrent_create_replay',statuses=[201,201],passed=True))
    duplicate_mid=duplicate_results[0].json()['memory']['id']
    def concurrent_correction(_):
        r=new_request(); payload=create_body(r.request_id)
        payload.pop('scope'); payload.pop('sourceRefs'); payload['expectedVersion']=1
        return client.post(base+'/memories/'+duplicate_mid+'/corrections',headers=auth(key=r.idempotency_key),json=payload)
    with ThreadPoolExecutor(max_workers=2) as pool:
        corrected_results=list(pool.map(concurrent_correction,range(2)))
    assert sorted(r.status_code for r in corrected_results)==[201,409]
    records.append(dict(case='concurrent_correction_cas',statuses=[201,409],passed=True))
    # Two distinct same-version commands have one winner through real socket HTTP.
    def concurrent_patch(_):
        r=new_request()
        return client.patch(base+path,headers=auth(key=r.idempotency_key),json=dict(requestId=r.request_id,expectedVersion=4,intent='inactive'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(concurrent_patch,range(2)))
    assert sorted(r.status_code for r in responses)==[200,409]
    records.append(dict(case='concurrent_cas',statuses=[200,409],passed=True))
    deletion=new_request()
    call('delete','DELETE',path,json=dict(requestId=deletion.request_id,expectedVersion=5),headers=auth(key=deletion.idempotency_key))
    call('owner_erased','GET',path,410,'erased')
    call('owner_erased_history','GET',path+'/revisions',410,'erased')
    call('foreign_erased','GET',path,404,'memory_not_found',headers=auth(owner))
    tomb=call('old_mutation_replay_after_delete','PATCH',path,json=payload,headers=auth(key=request.idempotency_key))
    assert tomb['memory']['contentAvailable'] is False and 'conditions' not in tomb['memory']
    corrected_tomb=call('correction_replay_after_erasure','POST','/memories/'+predecessor+'/corrections',201,json=correction_body,headers=auth(key=correction.idempotency_key))
    assert corrected_tomb['memory']['contentAvailable'] is False and 'conditions' not in corrected_tomb['memory']
    with Session(engine) as db:
        assert all(r.content is None and r.conditions is None and r.content_sha256 is None
                   for r in db.scalars(select(MemoryRevision).where(MemoryRevision.memory_id==mid)))
    for role in ('unknown','member'):
        with engine.begin() as db:
            db.execute(update(WorkspaceMembership).where(WorkspaceMembership.workspace_id==workspace,WorkspaceMembership.user_id==actor).values(role=role))
        call('role_'+role,'GET','/memories',404 if role=='unknown' else 200,'workspace_not_found' if role=='unknown' else None)
    with engine.begin() as db:
        db.execute(WorkspaceMembership.__table__.delete().where(WorkspaceMembership.workspace_id==workspace,WorkspaceMembership.user_id==actor))
    call('revoked','GET','/memories',404,'workspace_not_found')
    with engine.begin() as db:
        db.execute(update(Workspace).where(Workspace.id==workspace).values(archived_at=datetime.now(UTC)))
    call('archived','GET','/memories',404,'workspace_not_found',headers=auth(owner))
    captured_log=(runtime/'http.log').read_text(encoding='utf-8')
    assert all(value not in captured_log for value in forbidden_log_values)
    records.append(dict(case='admission_response_and_application_log_redaction',passed=True))
    result=dict(scope='mounted owner-private management lifecycle including shared admission',transport='live socket HTTP to ai_pdf_api.main:app',
                database='fresh disposable PostgreSQL; full Alembic head t4b5c6d7e8f9',checks=records,
                limits=['Independent API review and hosted CI remain required','No UI/BFF/shared-model acceptance','Dependency merges remain gated'])
    Path(__file__).with_name('live-http.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(f'Live HTTP: {len(records)} checks passed; sanitized evidence written.')
finally:
    client.close()
    process.terminate()
    try: process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill(); process.wait(timeout=5)
    log.close()
    engine.dispose()
