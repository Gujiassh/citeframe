"""Opt-in concurrency evidence; guarded against any non-disposable database."""
import base64
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from time import monotonic, sleep
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from ai_pdf_api.core.settings import settings
from ai_pdf_api.models import Asset, ResearchPlanRevision, ResearchProviderCall, ResearchStep, User, Workspace, WorkspaceMembership
from ai_pdf_api.schemas.model_settings import UpdateModelSettingsRequest
from ai_pdf_api.schemas.research import CreateResearchRunRequest
from ai_pdf_api.services.model_config_types import ModelConfigurationError
from ai_pdf_api.services.workspace_models import resolve_workspace_models, update_model_settings
from ai_pdf_api.services.research.research_runs import create_research_run
from ai_pdf_api.services.research.research_worker_lease import claim_specific_research_step
from ai_pdf_api.services.research import research_worker_provider as calls
from ai_pdf_api.services.research import ResearchError


@pytest.fixture
def pg(monkeypatch):
    url = os.environ.get("CITEFRAME_ISSUE36_POSTGRES_URL")
    if not url:
        pytest.skip("requires separate citeframe_issue36_test database migrated to head")
    assert make_url(url).database == "citeframe_issue36_test", "Refusing non-test database"
    engine = create_engine(url, pool_size=8, connect_args={"options": "-c lock_timeout=8000 -c statement_timeout=15000"})
    monkeypatch.setattr(settings, "model_config_encryption_key", base64.b64encode(b"t" * 32).decode())
    with Session(engine) as db:
        uid, wid = str(uuid4()), str(uuid4())
        db.add(User(id=uid, email=uid+"@test.invalid", name="Issue36", password_hash="unused", avatar_url=""))
        db.flush()
        db.add(Workspace(id=wid, name="Issue36 isolated concurrency", created_by_user_id=uid))
        db.flush()
        db.add(WorkspaceMembership(workspace_id=wid, user_id=uid, role="owner"))
        db.commit()
    yield engine, uid, wid
    engine.dispose()


def patch(revision, model="old-model", both=False):
    generation = dict(action="save", expectedRevision=revision, protocol="openai_responses", baseUrl="https://fixture.test/v1", model=model, apiKey="old-key" if model == "old-model" else "new-key")
    value = {"generation": generation}
    if both:
        value["embedding"] = {**generation, "protocol": "openai_embeddings"}
    return UpdateModelSettingsRequest.model_validate(value)


def write(engine, uid, wid, revision, model="old-model", both=False):
    with Session(engine) as db:
        update_model_settings(db, wid, uid, patch(revision, model, both))
        db.commit()


def wait_for_lock(engine, pid):
    deadline = monotonic() + 5
    while monotonic() < deadline:
        with engine.connect() as conn:
            waiting = conn.scalar(text("select wait_event_type from pg_stat_activity where pid=:pid"), {"pid": pid})
        if waiting == "Lock":
            return
        sleep(0.01)
    pytest.fail("contender did not demonstrably block on PostgreSQL lock")


def test_atomic_pair_read_interleaved_with_committed_pair_save(pg):
    engine, uid, wid = pg
    write(engine, uid, wid, 0, both=True)
    snapshot_read, release = threading.Event(), threading.Event()
    def after(conn, cursor, statement, params, context, many):
        if threading.current_thread().name.startswith("pair-reader") and statement.lstrip().startswith("SELECT") and "workspace_model_configs" in statement:
            snapshot_read.set()
            assert release.wait(5)
    event.listen(engine, "after_cursor_execute", after)
    def read():
        with Session(engine) as db:
            return resolve_workspace_models(db, wid)
    try:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="pair-reader") as pool:
            future = pool.submit(read)
            assert snapshot_read.wait(5)
            write(engine, uid, wid, 1, "new-model", both=True)
            release.set()
            pair = future.result(5)
            assert pair.generation.model == pair.embedding.model == "old-model"
        with Session(engine) as db:
            pair = resolve_workspace_models(db, wid)
            assert pair.generation.model == pair.embedding.model == "new-model"
    finally:
        release.set()
        event.remove(engine, "after_cursor_execute", after)


def test_concurrent_revision_write_blocks_then_conflicts(pg):
    engine, uid, wid = pg
    write(engine, uid, wid, 0)
    contender_started = threading.Event()
    state = {}
    def contender():
        with Session(engine) as db:
            state["pid"] = db.scalar(text("select pg_backend_pid()"))
            contender_started.set()
            with pytest.raises(ModelConfigurationError) as error:
                update_model_settings(db, wid, uid, patch(1, "losing-model"))
            assert error.value.code == "model_settings_conflict"
    with Session(engine) as first, ThreadPoolExecutor(max_workers=1) as pool:
        update_model_settings(first, wid, uid, patch(1, "winning-model"))
        future = pool.submit(contender)
        assert contender_started.wait(5)
        wait_for_lock(engine, state["pid"])
        first.commit()
        future.result(5)
    with Session(engine) as db:
        assert resolve_workspace_models(db, wid).generation.model == "winning-model"


def planner(engine, uid, wid):
    with Session(engine) as db:
        asset = Asset(workspace_id=wid, created_by_user_id=uid, asset_kind="document", title="Fixture", source_filename="fixture.md",
                      object_key=f"workspaces/{wid}/fixture.md", mime_type="text/markdown", byte_size=1, status="ready")
        db.add(asset)
        db.commit()
        _, result, _ = create_research_run(db, workspace_id=wid, actor_user_id=uid,
            payload=CreateResearchRunRequest.model_validate({"question": "What does the fixture say?", "assetScope": {"mode": "selected", "assetIds": [asset.id]}}), idempotency_key=str(uuid4()))
        run_id = result["run"]["id"]
        revision = db.scalar(select(ResearchPlanRevision).where(ResearchPlanRevision.run_id == run_id))
        fingerprint = revision.proposed_provider_config_fingerprint
        step = db.scalar(select(ResearchStep).where(ResearchStep.run_id == run_id, ResearchStep.step_kind == "planner"))
        lease = claim_specific_research_step(db, run_id=run_id, step_key=step.step_key, branch_key=None, worker_instance_id="issue36-test", lease_seconds=60)
        return lease.attempt_id, fingerprint


def reserve(db, attempt, fingerprint, key="first"):
    return calls.reserve_provider_call(db, attempt_id=attempt, logical_call_key=key, request_sha256="1" * 64,
        provider="openai", model="old-model", provider_config_fingerprint=fingerprint, reserved_input_tokens=10, reserved_output_tokens=10)


def test_save_before_reservation_blocks_then_drift_sends_nothing(pg):
    engine, uid, wid = pg
    write(engine, uid, wid, 0)
    attempt, fingerprint = planner(engine, uid, wid)
    started, state = threading.Event(), {}
    def contender():
        with Session(engine) as db:
            state["pid"] = db.scalar(text("select pg_backend_pid()"))
            started.set()
            with pytest.raises(ResearchError) as error:
                reserve(db, attempt, fingerprint)
            assert error.value.code == "research_provider_config_drift"
    with Session(engine) as saving, ThreadPoolExecutor(max_workers=1) as pool:
        update_model_settings(saving, wid, uid, patch(1, "new-model"))
        future = pool.submit(contender)
        assert started.wait(5)
        wait_for_lock(engine, state["pid"])
        saving.commit()
        future.result(5)
    with Session(engine) as db:
        assert db.scalar(select(ResearchProviderCall.id).where(ResearchProviderCall.attempt_id == attempt)) is None


def test_reserved_call_survives_save_before_mark_sent_using_captured_credentials(pg, monkeypatch):
    from ai_pdf_api.services import workspace_providers
    from ai_pdf_api.services.providers import get_generation_provider
    engine, uid, wid = pg
    write(engine, uid, wid, 0)
    attempt, fingerprint = planner(engine, uid, wid)
    with Session(engine) as db:
        captured = resolve_workspace_models(db, wid)
    entered, release, saving_started, state = threading.Event(), threading.Event(), threading.Event(), {}
    original = calls._reserve_provider_call
    def paused(*args, **kwargs):
        result = original(*args, **kwargs)
        entered.set()
        assert release.wait(5)
        return result
    monkeypatch.setattr(calls, "_reserve_provider_call", paused)
    def reservation():
        with Session(engine) as db:
            return reserve(db, attempt, fingerprint)
    def saving():
        with Session(engine) as db:
            state["pid"] = db.scalar(text("select pg_backend_pid()"))
            saving_started.set()
            update_model_settings(db, wid, uid, patch(1, "new-model"))
            db.commit()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            r = pool.submit(reservation)
            assert entered.wait(5)
            w = pool.submit(saving)
            assert saving_started.wait(5)
            wait_for_lock(engine, state["pid"])
            release.set()
            reservation_value = r.result(5)
            w.result(5)
    finally:
        release.set()
        monkeypatch.setattr(calls, "_reserve_provider_call", original)
    requests = []
    def handle(request):
        requests.append(request.headers["Authorization"])
        return httpx.Response(200, json={"status": "completed", "output_text": "fixture"})
    monkeypatch.setattr(workspace_providers, "model_client", lambda base, timeout: httpx.Client(transport=httpx.MockTransport(handle)))
    with Session(engine) as db:
        calls.mark_provider_call_sent(db, reservation_value.provider_call_id)
        assert get_generation_provider(captured.generation).generate([{"role": "user", "content": "fixture"}]) == "fixture"
        assert requests == ["Bearer old-key"]
        with pytest.raises(ResearchError) as error:
            reserve(db, attempt, fingerprint, "second")
        assert error.value.code == "research_provider_config_drift"
        row = db.get(ResearchProviderCall, reservation_value.provider_call_id)
        assert row.model == "old-model" and row.provider_config_fingerprint == fingerprint and row.status == "sent"
