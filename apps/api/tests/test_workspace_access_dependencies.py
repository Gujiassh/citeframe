from __future__ import annotations

import importlib
import importlib.util
import json
import os
import time

import pytest
from datetime import UTC, datetime
from pathlib import Path
from typing import get_origin, get_type_hints

from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from ai_pdf_api.db.session import get_db
from ai_pdf_api.models import Asset, IngestionJob, Workspace, WorkspaceMembership
from ai_pdf_api.routers.deps import (
    WorkspaceAccess, WorkspaceRequest, require_internal_api_token,
    require_workspace_member, require_workspace_owner,
)
from test_workspace_model_settings import configured_api, headers
from test_evaluation_api import evaluation_app, evaluation_report, _import, _auth
from test_research_report_edit import ready_report
from research_router_test_support import auth

ROUTERS = ('jobs', 'model_settings', 'workspaces', 'assets', 'chat', 'notes', 'research', 'evaluation')
EVIDENCE = Path(__file__).resolve().parents[3] / 'specs/v5/post-v5-optimization/evidence/issue40'


def test_error_oracle_matches_baseline():
    spec = importlib.util.spec_from_file_location('issue40_http_oracle', EVIDENCE / 'http_oracle.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    before = json.loads((EVIDENCE / 'http-baseline.json').read_text())
    after = module.capture()
    assert len(after) == 378
    assert after == before


@pytest.mark.parametrize('local_timezone', [None, 'UTC0', 'CST-8'])
def test_oracle_workspace_fixture_preserves_utc_on_sqlite_reload(configured_api, local_timezone):
    if local_timezone is not None and not hasattr(time, 'tzset'):
        pytest.skip('Host timezone switching requires POSIX tzset; native timezone case still runs')
    previous = os.environ.get('TZ')
    spec = importlib.util.spec_from_file_location('issue40_timezone_oracle', EVIDENCE / 'http_oracle.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _, db = configured_api
    app = FastAPI()
    app.include_router(importlib.import_module('ai_pdf_api.routers.workspaces').router)
    app.dependency_overrides[get_db] = lambda: db
    try:
        if local_timezone is not None:
            os.environ['TZ'] = local_timezone
            time.tzset()
        with module.fixed_workspace_times(db):
            db.expunge_all()
            workspace = db.get(Workspace, 'w1')
            assert workspace.created_at == module.FIXTURE_TIME
            assert workspace.created_at.tzinfo is UTC
            db.expire_all()
            assert workspace.updated_at.tzinfo is UTC
            with TestClient(app) as client:
                response = client.get('/v1/workspaces/w1', headers=headers())
            assert response.status_code == 200
            assert response.json()['workspace']['createdAt'] == '2026-09-28T00:00:00+00:00'
            assert response.json()['workspace']['updatedAt'] == '2026-09-28T00:00:00+00:00'
    finally:
        if local_timezone is not None:
            if previous is None:
                os.environ.pop('TZ', None)
            else:
                os.environ['TZ'] = previous
            time.tzset()


def test_every_workspace_operation_has_typed_access_and_internal_auth_graph():
    protected = []
    def calls(dependency):
        yield dependency.call
        for child in dependency.dependencies:
            yield from calls(child)
    for name in ROUTERS:
        router = importlib.import_module('ai_pdf_api.routers.' + name).router
        for route in router.routes:
            if '{workspace_id}' not in route.path:
                continue
            graph = list(calls(route.dependant))
            assert require_internal_api_token in graph, route.path
            returns = []
            for call in graph[1:]:
                hints = get_type_hints(call if hasattr(call, '__annotations__') else call.__call__)
                returns.append(hints.get('return'))
            assert any(t is WorkspaceAccess or get_origin(t) is WorkspaceRequest for t in returns), route.path
            assert all(d.use_cache for d in route.dependant.dependencies), route.path
            protected.append((route.path, next(iter(route.methods))))
    assert len(protected) == 56


def test_member_owner_router_and_parameter_share_one_request_query(configured_api):
    _, db = configured_api
    app = FastAPI()
    router = APIRouter(dependencies=[Depends(require_workspace_member)])
    @router.get('/{workspace_id}')
    def read(access: WorkspaceAccess = Depends(require_workspace_member), owner: WorkspaceAccess = Depends(require_workspace_owner)):
        assert access is owner
        return {'userId': access.user_id, 'workspaceId': access.workspace_id, 'role': access.role}
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    statements = []
    def observe(_conn, _cursor, statement, _parameters, _context, _many):
        if 'workspace_memberships' in statement:
            statements.append(statement)
    event.listen(db.bind, 'before_cursor_execute', observe)
    try:
        with TestClient(app) as client:
            for _ in range(2):
                statements.clear()
                response = client.get('/w1', headers=headers())
                assert response.json() == {'userId': 'owner', 'workspaceId': 'w1', 'role': 'owner'}
                assert len(statements) == 1
    finally:
        event.remove(db.bind, 'before_cursor_execute', observe)


def test_revocation_and_archival_apply_on_next_request(configured_api):
    client, db = configured_api
    path = '/v1/workspaces/w1/model-settings'
    assert client.get(path, headers=headers()).status_code == 200
    membership = db.scalar(select(WorkspaceMembership).where(WorkspaceMembership.workspace_id == 'w1', WorkspaceMembership.user_id == 'owner'))
    db.delete(membership)
    db.commit()
    assert client.get(path, headers=headers()).json() == {'detail': 'Workspace not found.'}
    db.get(Workspace, 'w2').archived_at = datetime.now(UTC)
    db.commit()
    assert client.get('/v1/workspaces/w2/model-settings', headers=headers()).status_code == 404


def test_authorized_in_both_workspaces_cannot_use_b_resources_under_a(configured_api, monkeypatch, request):
    _, db = configured_api
    app = FastAPI()
    for name in ('jobs', 'assets', 'notes', 'chat', 'evaluation'):
        app.include_router(importlib.import_module('ai_pdf_api.routers.' + name).router)
    app.dependency_overrides[get_db] = lambda: db
    statements = []
    def observe(_conn, _cursor, sql, parameters, _context, _many):
        statements.append((sql, parameters))
    event.listen(db.bind, 'before_cursor_execute', observe)
    request.addfinalizer(lambda: event.remove(db.bind, 'before_cursor_execute', observe))
    def forbidden_storage():
        raise AssertionError("Cross-workspace rejection must not access object storage")
    monkeypatch.setattr('ai_pdf_api.services.storage.build_storage_client', forbidden_storage)
    asset = Asset(id='b-asset', workspace_id='w2', created_by_user_id='owner', asset_kind='pdf', title='Synthetic B', source_filename='b.pdf', object_key='synthetic-issue40/b.pdf', mime_type='application/pdf', byte_size=10, status='ready')
    db.add(asset)
    db.flush()
    job = IngestionJob(id='b-job', workspace_id='w2', asset_id=asset.id, job_type='ingest', status='queued', requested_by_user_id='owner')
    db.add(job)
    db.commit()
    with TestClient(app) as client:
        note = client.post('/v1/workspaces/w2/notes', headers=headers(), json={'bodyMd': 'Synthetic B note'}).json()['note']
        thread = client.post('/v1/workspaces/w2/threads', headers=headers(), json={'title': 'Synthetic B thread'}).json()['thread']
        for suffix, detail in ((f'assets/{asset.id}', 'Asset not found.'), (f'jobs/{job.id}', 'Job not found.'), (f'notes/{note["id"]}', 'Note not found.'), (f'threads/{thread["id"]}/messages', 'Thread not found.')):
            statements.clear()
            result = client.get('/v1/workspaces/w1/' + suffix, headers=headers())
            assert result.status_code == 404, result.text
            assert result.json() == {'detail': detail}
            table = {'assets': 'assets', 'jobs': 'ingestion_jobs', 'notes': 'notes', 'threads': 'chat_threads'}[suffix.split('/')[0]]
            assert any(f'{table}.workspace_id' in sql.partition('WHERE')[2] and 'w1' in params for sql, params in statements)
            assert sum('JOIN workspace_memberships' in sql for sql, _ in statements) == 1
        rejected = client.patch(f'/v1/workspaces/w1/notes/{note["id"]}', headers=headers(), json={'bodyMd': 'must not save'})
        assert rejected.status_code == 404
        assert client.get(f'/v1/workspaces/w2/notes/{note["id"]}', headers=headers()).json()['note']['bodyMd'] == 'Synthetic B note'
        assert client.delete('/v1/workspaces/w1/assets/b-asset', headers=headers()).status_code == 404
        assert db.get(Asset, asset.id).status == 'ready'
        assert len(db.scalars(select(IngestionJob)).all()) == 1
        # A-only member is denied before B resources can be inspected.
        assert client.get('/v1/workspaces/w2/jobs/b-job', headers=headers('member')).json() == {'detail': 'Workspace not found.'}



def test_evaluation_resources_are_scoped_for_dual_workspace_owner(evaluation_app):
    client, db, context = evaluation_app
    owner, a, b = context["owner"], context["workspace"], context["otherWorkspace"]
    db.add(WorkspaceMembership(workspace_id=b.id, user_id=owner.id, role="owner"))
    db.commit()
    result = _import(db, a, evaluation_report())
    db.commit()
    suite_id = client.get(f"/v1/workspaces/{a.id}/evaluation-suites", headers=_auth(owner)).json()["items"][0]["id"]
    for suffix in (f"evaluation-suites/{suite_id}", f"evaluations/{result.evaluation_run_id}", f"evaluations/{result.evaluation_run_id}/cases"):
        response = client.get(f"/v1/workspaces/{b.id}/{suffix}", headers=_auth(owner))
        assert response.status_code == 404, response.text


def test_research_scope_noncreator_and_sse_precedence(research_app):
    client, db, context, run, artifact = ready_report(research_app)
    owner, a, b = context["owner"], context["workspace"], context["otherWorkspace"]
    db.add(WorkspaceMembership(workspace_id=b.id, user_id=owner.id, role="owner"))
    db.commit()
    for suffix in ("", "/artifacts", f"/artifacts/{artifact.id}", f"/artifacts/{artifact.id}/content", "/report-edit"):
        result = client.get(f"/v1/workspaces/{b.id}/research-runs/{run.id}{suffix}", headers=auth(owner))
        assert result.status_code == 404, result.text
    before_objects = dict(context["objectStore"])
    from ai_pdf_api.db.base import Base
    before_rows = {t.name: [tuple(row) for row in db.execute(select(t)).all()] for t in Base.metadata.sorted_tables}
    rejected = client.put(f"/v1/workspaces/{a.id}/research-runs/{run.id}/report-edit", headers=auth(owner), json={"originalArtifactId": artifact.id, "originalSha256": artifact.content_sha256, "expectedVersion": 0, "markdown": "must not save"})
    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "research_permission_denied"
    assert context["objectStore"] == before_objects
    assert {t.name: [tuple(row) for row in db.execute(select(t)).all()] for t in Base.metadata.sorted_tables} == before_rows
    url = f"/v1/workspaces/{a.id}/research-runs/{run.id}/events"
    outsider = auth(context["stranger"])
    assert client.get(url, headers={**outsider, "Accept": "application/json"}).status_code == 406
    assert client.get(url, headers={**outsider, "Accept": "text/event-stream", "Last-Event-ID": "bad"}).status_code == 400
    assert client.get(url, headers={**outsider, "Accept": "text/event-stream"}).status_code == 404
    assert client.get(url, headers={**auth(owner), "Accept": "text/event-stream"}).status_code == 200


def test_all_workspace_operations_execute_membership_with_valid_inputs(configured_api, monkeypatch):
    import re
    from sqlalchemy.orm import sessionmaker
    from ai_pdf_api.db.base import Base
    _, db = configured_api
    app = FastAPI()
    for name in ROUTERS:
        app.include_router(importlib.import_module('ai_pdf_api.routers.' + name).router)
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr('ai_pdf_api.routers.research.RESEARCH_EVENT_SESSION_FACTORY', sessionmaker(bind=db.bind))
    decision = {'expectedStateVersion': 1, 'expectedDecisionStateVersion': 1, 'inputArtifactSha256': 'a' * 64, 'inputSnapshotSha256': 'b' * 64}
    bodies = {
        'UpdateModelSettingsRequest': {'generation': {'action': 'reset', 'expectedRevision': 0}},
        'UpdateWorkspaceSettingsRequest': {'systemPrompt': 'Synthetic', 'retrievalTopK': 6, 'chunkSize': 1200},
        'CreateUploadSessionRequest': {'sourceFilename': 'synthetic.pdf', 'mimeType': 'application/pdf', 'byteSize': 10},
        'FinalizeUploadRequest': {'objectKey': 'synthetic/key'},
        'CreateThreadRequest': {},
        'ChatStreamRequest': {'threadId': 'missing', 'question': 'Synthetic?', 'assetScope': {'mode': 'all_ready'}},
        'CreateNoteRequest': {'bodyMd': 'Synthetic'}, 'UpdateNoteRequest': {},
        'CreateTagRequest': {'name': 'Synthetic'}, 'UpdateTagRequest': {}, 'TagBindingsRequest': {'tagIds': []},
        'CreateResearchRunRequest': {'question': 'Synthetic?', 'assetScope': {'mode': 'all_ready'}},
        'CancelResearchRunRequest': {'expectedStateVersion': 1, 'reasonCode': 'user_requested'},
        'PlanDecisionRequest': {**decision, 'action': 'approve'},
        'ConflictDecisionRequest': {**decision, 'action': 'keep_as_unresolved'},
        'RetryResearchStepRequest': {'expectedStateVersion': 1, 'expectedStepStateVersion': 1, 'failedAttempt': 1},
        'SaveResearchReportEditRequest': {'originalArtifactId': 'missing', 'originalSha256': 'a' * 64, 'expectedVersion': 0, 'markdown': 'Synthetic'},
    }
    required_queries = {'part': 'fixture.png', 'processingGeneration': 1, 'evidenceRepresentationId': 'missing', 'objectKey': 'synthetic/key'}
    before = {t.name: [tuple(row) for row in db.execute(select(t)).all()] for t in Base.metadata.sorted_tables}
    queries = []
    def observe(_conn, _cursor, sql, _parameters, _context, _many):
        if 'JOIN workspace_memberships' in sql:
            queries.append(sql)
    event.listen(db.bind, 'before_cursor_execute', observe)
    try:
        count = 0
        with TestClient(app) as client:
            for path, operations in app.openapi()['paths'].items():
                if '{workspace_id}' not in path:
                    continue
                url = re.sub(r'\{[^}]+\}', 'missing', path.replace('{workspace_id}', 'w1'))
                for method, operation in operations.items():
                    kwargs = {}
                    if 'requestBody' in operation:
                        schema = operation['requestBody']['content']['application/json']['schema']['$ref'].split('/')[-1]
                        kwargs['json'] = bodies[schema]
                    params = {p['name']: required_queries[p['name']] for p in operation.get('parameters', []) if p['in'] == 'query' and p.get('required')}
                    queries.clear()
                    response = client.request(method, url, headers={**headers('outsider'), 'Accept': 'text/event-stream'}, params=params, **kwargs)
                    assert response.status_code == 404, (method, path, response.text)
                    body = response.json()
                    if '/research-runs' in path:
                        assert body['error']['code'] == 'workspace_not_found'
                    else:
                        assert body == {'detail': 'Workspace not found.'}
                    assert len(queries) == 1, (method, path)
                    count += 1
        assert count == 56
        assert {t.name: [tuple(row) for row in db.execute(select(t)).all()] for t in Base.metadata.sorted_tables} == before
    finally:
        event.remove(db.bind, 'before_cursor_execute', observe)
