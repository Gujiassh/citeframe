"""Bounded real-PostgreSQL issue40 safety evidence. No provider calls.

Run from repo root with apps/api/.venv/Scripts/python.exe <this file>.
Requires the ignored isolated runtime credentials/run.py and loopback PG/MinIO.
Creates a NEW database per run; never mutates acceptance A/B fixtures.
"""
from pathlib import Path
import hashlib
import json
import os
import runpy
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO
from threading import Barrier, Event
from time import monotonic, sleep
from uuid import uuid4

REPO = Path(__file__).resolve().parents[5]
RUNTIME = REPO / '.local-runtime/artifacts/issue40-dev/runtime'
sys.argv = ['run.py', 'inspect']
runtime = runpy.run_path(str(RUNTIME / 'run.py'))
credentials = runtime['c']
import psycopg
from psycopg import sql
name = 'issue40_safety_' + uuid4().hex[:12]
with psycopg.connect(host='127.0.0.1', port=18432, user=credentials['database_user'],
                      password=credentials['database_password'], dbname='postgres', autocommit=True) as admin:
    admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
os.environ['AI_PDF_DATABASE_URL'] = os.environ['AI_PDF_DATABASE_URL'].rsplit('/', 1)[0] + '/' + name
sys.path.insert(0, str(REPO / 'apps/api/tests'))
from alembic import command
from alembic.config import Config
command.upgrade(Config(str(REPO / 'apps/api/alembic.ini')), 'head')
from sqlalchemy import delete, event, func, select, text
from sqlalchemy.orm import sessionmaker
from ai_pdf_api.db.session import SessionLocal
from ai_pdf_api.models import (WorkspaceMembership, ResearchRun, ResearchStepAttempt,
    ResearchArtifact, ResearchEvent, ResearchPublicationIntent, ResearchReportEdit)
from ai_pdf_api.services.research.research_worker import (
    claim_specific_research_step, heartbeat_research_step)
from ai_pdf_api.services.research import ResearchError
from ai_pdf_api.services.research.research_report_edit import save_report_edit
from ai_pdf_api.schemas.research_report_edit import SaveResearchReportEditRequest
from ai_pdf_api.services.storage import build_storage_client
from ai_pdf_api.core.settings import settings
import research_worker_test_support as support

engine = SessionLocal.kw['bind']
@event.listens_for(engine, 'connect')
def timeouts(connection, _):
    with connection.cursor() as cursor:
        cursor.execute("SET statement_timeout = '20s'")
        cursor.execute("SET lock_timeout = '15s'")
engine.dispose()
results = {'database': name, 'dialect': engine.dialect.name, 'checks': []}
assert engine.dialect.name == 'postgresql'
with SessionLocal() as db:
    results['postgresVersion'] = db.scalar(text('SHOW server_version'))
    results['migration'] = db.scalar(text('SELECT version_num FROM alembic_version'))

storage = build_storage_client()
from fastapi.testclient import TestClient
from ai_pdf_api.main import app
from ai_pdf_api.models import User, Workspace, Asset, ResearchStep, ResearchExecutionSnapshot, ResearchBudgetLedger
from research_router_test_support import create_run, approve_seeded_plan
from datetime import UTC, datetime

class StoredFixtures(dict):
    def __setitem__(self, key, value):
        storage.put_object(settings.minio_bucket, key, BytesIO(value), len(value), content_type='application/json')
        super().__setitem__(key, value)

client = TestClient(app)
def fixture():
    db = SessionLocal()
    now = datetime.now(UTC)
    user = User(email='issue40-synthetic-' + uuid4().hex + '@example.invalid',
        name='Synthetic Issue40 PG safety', password_hash='not-a-login-password', avatar_url='')
    db.add(user); db.flush()
    workspace = Workspace(name='Synthetic Issue40 PG safety', created_by_user_id=user.id)
    db.add(workspace); db.flush()
    db.add(WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role='owner'))
    asset = Asset(workspace_id=workspace.id, created_by_user_id=user.id, asset_kind='pdf',
        title='Synthetic safety source', source_filename='synthetic.pdf',
        object_key=f'workspaces/{workspace.id}/synthetic.pdf', mime_type='application/pdf',
        byte_size=100, status='ready', current_processing_generation=1, current_index_version=1)
    db.add(asset); db.commit()
    support.publish_research_versions_for_release(db, now); db.commit()
    context = dict(creator=user, owner=user, workspace=workspace, asset=asset, objectStore=StoredFixtures())
    run = approve_seeded_plan(client, db, context, create_run(client, context))
    snapshot = db.get(ResearchExecutionSnapshot, run.approved_execution_snapshot_id)
    step = db.scalar(select(ResearchStep).where(ResearchStep.run_id == run.id, ResearchStep.step_kind == 'researcher'))
    ledger = db.scalar(select(ResearchBudgetLedger).where(ResearchBudgetLedger.execution_snapshot_id == snapshot.id))
    return support.ResearchWorkerFixture(db=db, run=run, snapshot=snapshot, ledger=ledger, step=step, asset=asset, now=now)

def revoke(f):
    with SessionLocal() as db:
        db.execute(delete(WorkspaceMembership).where(WorkspaceMembership.workspace_id == f.run.workspace_id,
                    WorkspaceMembership.user_id == f.run.created_by_user_id))
        db.commit()

def denied(call, code, status=403):
    try:
        call()
    except ResearchError as error:
        assert (error.code, error.status_code) == (code, status)
        return {'status': error.status_code, 'code': error.code}
    raise AssertionError('Expected rejection')

for active in (False, True):
    f = fixture()
    lease = support.lease_default_step(f) if active else None
    revoke(f)
    if active:
        rejection = denied(lambda: heartbeat_research_step(f.db, attempt_id=lease.attempt_id,
            lease_token=lease.lease_token, now=f.now + timedelta(seconds=1)), 'research_permission_denied')
    else:
        rejection = denied(lambda: claim_specific_research_step(f.db, run_id=f.run.id,
            step_key=f.step.step_key, branch_key=f.step.branch_key, worker_instance_id='issue40-synthetic-revoked',
            now=f.now), 'research_permission_denied')
    f.db.expire_all()
    assert f.run.status == ('cancel_requested' if active else 'cancelled')
    assert f.run.cancel_reason_code == 'creator_membership_removed'
    attempts = list(f.db.scalars(select(ResearchStepAttempt).where(ResearchStepAttempt.step_id == f.step.id)))
    assert len(attempts) == (1 if active else 0)
    if active: assert attempts[0].status == 'running'
    results['checks'].append({'case': 'worker_heartbeat_revoked' if active else 'worker_claim_revoked',
        **rejection, 'runStatus': f.run.status, 'attemptCount': len(attempts)})
    f.db.close()

# Exercise the actual adoption finalizer after a synthetic upload and revocation.
# This narrow schedule starts at the durable intent boundary; it does not claim
# to cover publication preparation or a multi-Worker reconciliation race.
from citeframe_research_persistence.publication_finalize import _finalize
from citeframe_research_persistence.publication_saga_support import _claim_from_intent, _verify_frozen_intent
from citeframe_research_persistence.events import append_research_event
from ai_pdf_api.services.research.research_idempotency import canonical_sha256
f = fixture()
publisher = f.db.scalar(select(ResearchStep).where(ResearchStep.run_id == f.run.id, ResearchStep.step_kind == 'artifact_publisher'))
publisher.status = 'running'; publisher.current_attempt_number = 1; publisher.started_at = f.now
f.run.status = 'running'
attempt_token = uuid4().hex
attempt = ResearchStepAttempt(workspace_id=f.run.workspace_id, step_id=publisher.id, attempt_number=1,
    status='running', input_sha256=publisher.input_sha256 or f.snapshot.execution_snapshot_sha256,
    lease_token_hash=hashlib.sha256(attempt_token.encode()).hexdigest(), lease_expires_at=datetime.now(UTC) + timedelta(seconds=60),
    worker_instance_id='issue40-synthetic-adoption', heartbeat_at=f.now, started_at=f.now)
f.db.add(attempt); f.db.commit()
# The adoption lock/revocation branch runs before successful-output provenance.
# Label this explicitly as an adoption-boundary fixture, not a generated report.
now = datetime.now(UTC)
artifact_id = str(uuid4())
prefix = f'research/{f.run.workspace_id}/{f.run.id}/{artifact_id}'
content = b'# Synthetic Issue40 adoption-boundary fixture\n'
selection = dict(factClaimIds=[], unresolvedClaimIds=[])
token = uuid4().hex
intent = ResearchPublicationIntent(workspace_id=f.run.workspace_id, run_id=f.run.id,
    step_id=publisher.id, attempt_id=attempt.id, execution_snapshot_id=f.snapshot.id,
    logical_key='final-report', artifact_id=artifact_id, object_prefix=prefix,
    current_object_generation=1, current_object_key=prefix + '/publication/1/final.md',
    payload_bytes=content, byte_size=len(content), content_sha256=hashlib.sha256(content).hexdigest(),
    selection_json=selection, selection_sha256=canonical_sha256(selection), status='uploaded',
    claim_generation=1, claim_owner='issue40-synthetic-adoption', claim_token_hash=hashlib.sha256(token.encode()).hexdigest(),
    claim_expires_at=now + timedelta(seconds=60), claim_heartbeat_at=now,
    next_reconcile_at=now, created_at=now, updated_at=now)
f.db.add(intent); f.db.commit()
_verify_frozen_intent(intent)
claim = _claim_from_intent(intent, token, requires_attempt_lease=True,
    attempt_lease_token_hash=hashlib.sha256(attempt_token.encode()).hexdigest())
storage.put_object(settings.minio_bucket, claim.object_key, BytesIO(content), len(content), content_type='text/markdown')
revoke(f)
def unexpected_prompt_loader(*args):
    raise AssertionError('Revoked adoption must stop before output provenance evaluation')
_finalizer_result = _finalize(f.db, claim, append_event=append_research_event,
    session_factory=sessionmaker(bind=engine, expire_on_commit=False), prompt_loader=unexpected_prompt_loader)
f.db.expire_all()
assert intent.status == 'compensating' and f.run.status == 'cancel_requested'
assert f.run.cancel_reason_code == 'creator_membership_removed'
assert f.db.scalar(select(func.count()).select_from(ResearchArtifact).where(
    ResearchArtifact.run_id == f.run.id, ResearchArtifact.artifact_kind == 'final_report')) == 0
assert f.db.scalar(select(func.count()).select_from(ResearchEvent).where(
    ResearchEvent.run_id == f.run.id, ResearchEvent.event_type == 'run_completed')) == 0
response = storage.get_object(settings.minio_bucket, claim.object_key)
try: assert response.read() == content
finally:
    response.close(); response.release_conn()
results['checks'].append({'case': 'publication_adoption_revoked_after_upload', 'intentStatus': intent.status,
    'runStatus': f.run.status, 'finalArtifacts': 0, 'completionEvents': 0,
    'objectInvariant': 'Existing upload unchanged; compensation remains pending (no adoption side effect)'})
f.db.close()

# Report concurrency uses genuine object bytes and the unchanged write service.
f = fixture()
f.run.status = 'completed'; f.run.finished_at = datetime.now(UTC)
content = b'# Synthetic Issue40 PostgreSQL report concurrency\n'
digest = hashlib.sha256(content).hexdigest()
key = f'workspaces/{f.run.workspace_id}/issue40-safety/report.md'
storage.put_object(settings.minio_bucket, key, BytesIO(content), len(content), content_type='text/markdown')
publisher = f.db.scalar(select(ResearchStep).where(ResearchStep.run_id == f.run.id, ResearchStep.step_kind == 'artifact_publisher'))
attempt = ResearchStepAttempt(workspace_id=f.run.workspace_id, step_id=publisher.id, attempt_number=1,
    status='succeeded', input_sha256=publisher.input_sha256 or f.snapshot.execution_snapshot_sha256, output_sha256=digest, started_at=f.now, finished_at=f.now)
f.db.add(attempt); f.db.flush()
artifact = ResearchArtifact(workspace_id=f.run.workspace_id, run_id=f.run.id,
    generated_by_step_id=publisher.id, generated_by_attempt_id=attempt.id, logical_key='final-report',
    schema_version='1', workflow_version_id=f.snapshot.workflow_version_id, direct_prompt_version_id=publisher.prompt_version_id,
    generation_provider=f.snapshot.generation_provider, generation_model=f.snapshot.generation_model,
    retention_class='workspace_lifetime', created_at=f.now,
    artifact_kind='final_report', visibility='user', object_key=key, content_type='text/markdown',
    byte_size=len(content), content_sha256=digest)
f.db.add(artifact); f.db.commit()
workspace_id, run_id, creator_id, artifact_id = f.run.workspace_id, f.run.id, f.run.created_by_user_id, artifact.id
f.db.close()

def payload(version, markdown):
    return SaveResearchReportEditRequest(originalArtifactId=artifact_id, originalSha256=digest,
        expectedVersion=version, markdown=markdown)

waiting_pids = []
def save(version, markdown, barrier=None, ready=None):
    with SessionLocal() as db:
        if ready is not None:
            # Real request-layer permission read before the write service's recheck.
            assert db.scalar(select(WorkspaceMembership.id).where(WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == creator_id)) is not None
            waiting_pids.append(db.scalar(text('SELECT pg_backend_pid()')))
            ready.set()
        if barrier is not None: barrier.wait(timeout=10)
        try:
            value = save_report_edit(db, workspace_id=workspace_id, run_id=run_id,
                user_id=creator_id, payload=payload(version, markdown))
            return {'status': 200, 'version': value['version']}
        except ResearchError as error:
            db.rollback()
            return {'status': error.status_code, 'code': error.code}

for version in (0, 1):
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(save, version, f'# Synthetic issue40 competing save {version}/{i}', barrier) for i in range(2)]
        outcomes = [future.result(timeout=30) for future in futures]
    assert sorted(x['status'] for x in outcomes) == [200, 409]
    assert next(x for x in outcomes if x['status'] == 409)['code'] == 'report_edit_version_conflict'
    with SessionLocal() as db: assert db.get(ResearchReportEdit, run_id).version == version + 1
    results['checks'].append({'case': 'report_expectedVersion_' + str(version), 'outcomes': outcomes,
        'persistedVersion': version + 1})

with SessionLocal() as db:
    before_edit = tuple(db.execute(select(ResearchReportEdit.__table__).where(ResearchReportEdit.run_id == run_id)).one())

# Hold the run lock so revocation commits after the preliminary permission read
# and before the write service can acquire its lock and recheck membership.
with SessionLocal() as blocker:
    blocker.scalar(select(ResearchRun).where(ResearchRun.id == run_id).with_for_update())
    ready = Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(save, 2, '# Must never persist', None, ready)
        assert ready.wait(10)
        deadline = monotonic() + 10
        observed_lock_wait = False
        while monotonic() < deadline:
            with SessionLocal() as observer:
                observed_lock_wait = observer.scalar(text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"),
                    {'pid': waiting_pids[-1]})
            if observed_lock_wait: break
            sleep(0.02)
        assert observed_lock_wait, 'Save did not reach the blocked PostgreSQL run lock'
        revoke(f)
        blocker.commit()
        outcome = future.result(timeout=30)
    assert outcome == {'status': 403, 'code': 'research_permission_denied'}
with SessionLocal() as db:
    edit = db.get(ResearchReportEdit, run_id)
    assert edit.version == 2 and edit.markdown != '# Must never persist'
    assert tuple(db.execute(select(ResearchReportEdit.__table__).where(ResearchReportEdit.run_id == run_id)).one()) == before_edit
response = storage.get_object(settings.minio_bucket, key)
try: assert hashlib.sha256(response.read()).hexdigest() == digest
finally:
    response.close(); response.release_conn()
results['checks'].append({'case': 'report_revoked_after_precheck_before_locked_save', **outcome,
    'persistedVersion': 2, 'originalObjectHashUnchanged': True, 'editRowUnchanged': True, 'postgresLockWaitObserved': True})
results['limits'] = ['Adoption finalizer only, with a seeded uploaded intent; no end-to-end publication preparation, compensation sweep, multi-Worker stress or crash/restart schedule.',
    'Two concurrent report saves tested at first save and subsequent save; one coordinated revocation schedule.',
    'Worker-facing persistence entrypoints invoked directly; no provider call or long-running Worker process.',
    'Existing deterministic fixture builders seed state; report byte/hash check is real, not full report-view provenance acceptance.']
output = Path(__file__).with_name('postgres-safety.json')
output.write_text(json.dumps(results, indent=2))
print(json.dumps(results, indent=2))
