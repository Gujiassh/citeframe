"""Offline HTTP contract oracle using a fresh synthetic database for every case."""
import importlib
import json
import re
import sys
from datetime import UTC, datetime
from contextlib import contextmanager
from pathlib import Path

sys.path[:0] = ['apps/api/tests', 'apps/api/src', 'packages/backend-contracts/src', 'packages/backend-persistence/src', 'packages/research-persistence/src']
if __name__ == '__main__' and len(sys.argv) > 2:
    sys.path.insert(0, sys.argv[2])

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, inspect, select
from sqlalchemy.orm.attributes import set_committed_value
from test_workspace_model_settings import configured_api, headers
from ai_pdf_api.db.session import get_db
from ai_pdf_api.models import Workspace


FIXTURE_TIME = datetime(2026, 9, 28, tzinfo=UTC)


@contextmanager
def fixed_workspace_times(db):
    # SQLite drops timezone metadata. Restore this fixture's known UTC input on
    # ORM loads/refreshes so DTO astimezone() never interprets it as host-local.
    def restore(workspace, *args):
        if inspect(workspace).session is not db:
            return
        for field in ('created_at', 'updated_at'):
            value = getattr(workspace, field)
            if value == FIXTURE_TIME.replace(tzinfo=None):
                set_committed_value(workspace, field, FIXTURE_TIME)

    event.listen(Workspace, 'load', restore)
    event.listen(Workspace, 'refresh', restore)
    try:
        for workspace in db.scalars(select(Workspace)):
            workspace.created_at = workspace.updated_at = FIXTURE_TIME
        db.commit()
        yield
    finally:
        event.remove(Workspace, 'load', restore)
        event.remove(Workspace, 'refresh', restore)


def capture():
    app = FastAPI()
    for name in ('jobs', 'model_settings', 'workspaces', 'assets', 'chat', 'notes', 'research', 'evaluation'):
        app.include_router(importlib.import_module('ai_pdf_api.routers.' + name).router)
    cases = []
    for path, operations in app.openapi()['paths'].items():
        if '{workspace_id}' not in path:
            continue
        url = re.sub(r'\{[^}]+\}', 'missing-resource', path.replace('{workspace_id}', 'w1'))
        for method, operation in operations.items():
            if method not in ('get', 'post', 'patch', 'put', 'delete'):
                continue
            for actor in ('owner', 'member', 'outsider', 'unknown', 'missing-internal', 'missing-user'):
                auth = headers(actor)
                if actor == 'missing-internal':
                    auth = {'x-user-id': 'owner'}
                if actor == 'missing-user':
                    auth = {k: v for k, v in headers().items() if k != 'x-user-id'}
                variants = [('default', {})]
                queries = [p for p in operation.get('parameters', []) if p['in'] == 'query']
                if queries:
                    variants.append(('invalid-query', {p['name']: '!' for p in queries}))
                for variant, params in variants:
                    patch = pytest.MonkeyPatch()
                    fixture = configured_api.__wrapped__(patch)
                    _, db = next(fixture)
                    try:
                        app.dependency_overrides[get_db] = lambda: db
                        # Header-precedence cases do not open the independent SSE database.
                        request_headers = {**auth, 'Accept': 'application/json'} if path.endswith('/events') else auth
                        with fixed_workspace_times(db), TestClient(app) as client:
                            result = client.request(method, url, headers=request_headers, params=params, **({'json': {}} if 'requestBody' in operation else {}))
                        body = result.json() if result.content else None
                        if isinstance(body, dict) and 'error' in body:
                            body['error'].pop('requestId', None)
                        if result.status_code == 201 and path.endswith('/threads'):
                            # Successful creation generates an ID and wall-clock fields.
                            for key in ('id', 'createdAt', 'lastMessageAt'):
                                body['thread'][key] = '<generated>'
                        cases.append({'method': method, 'path': path, 'actor': actor, 'variant': variant, 'status': result.status_code, 'body': body})
                    finally:
                        fixture.close()
                        patch.undo()
    return cases


if __name__ == '__main__':
    result = capture()
    Path(sys.argv[1]).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f'{len(result)} isolated HTTP cases captured')
