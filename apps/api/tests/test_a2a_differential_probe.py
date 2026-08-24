from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import threading
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

OUTPUT = os.environ.get("A2A_DIFFERENTIAL_PROBE_OUTPUT")
pytestmark = pytest.mark.skipif(not OUTPUT, reason="executed only by the A2a differential runner")
NOW = datetime(2026, 8, 24, 4, 0, tzinfo=UTC)


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is not None else NOW.replace(tzinfo=None)

    @classmethod
    def utcnow(cls):
        return NOW.replace(tzinfo=None)


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def _sha(value: str | bytes) -> str:
    payload = value.encode() if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def _raw_json_value(value: object) -> object:
    if is_dataclass(value):
        return _raw_json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _raw_json_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_raw_json_value(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"bytesBase64": base64.b64encode(value).decode()}
    return value


def _raw_bytes_b64(value: object) -> str:
    return base64.b64encode(_canonical(_raw_json_value(value))).decode()


def _id(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"citeframe/a2a-differential/{name}"))


class _Normalizer:
    """Normalize only the proven process worker-instance runtime identity."""

    def value(self, value: object) -> object:
        if is_dataclass(value):
            return self.value(asdict(value))
        if isinstance(value, dict):
            normalized = {}
            for key, item in sorted(value.items()):
                name = str(key)
                if name == "worker_instance_id":
                    assert item is None or isinstance(item, str), (name, type(item).__name__)
                    if isinstance(item, str) and re.fullmatch(r"worker-[0-9]+", item):
                        normalized[name] = "<process-worker-instance-id>"
                    else:
                        normalized[name] = item
                elif name == "payload_json" and isinstance(item, str):
                    normalized[name] = _canonical(self.value(json.loads(item))).decode()
                else:
                    normalized[name] = self.value(item)
            return normalized
        if isinstance(value, (list, tuple)):
            return [self.value(item) for item in value]
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, bytes):
            return {"bytesBase64": base64.b64encode(value).decode()}
        return value

    def bytes_b64(self, value: object) -> str:
        return base64.b64encode(_canonical(self.value(value))).decode()


def _install_determinism() -> None:
    lock = threading.Lock()
    uuid_counter = 0
    token_counter = 0

    def deterministic_uuid4() -> UUID:
        nonlocal uuid_counter
        with lock:
            uuid_counter += 1
            return uuid5(NAMESPACE_URL, f"citeframe/a2a-differential/generated/{uuid_counter}")

    def deterministic_token(_size: int = 32) -> str:
        nonlocal token_counter
        with lock:
            token_counter += 1
            return f"a2a-lease-token-{token_counter:03d}"

    import secrets

    secrets.token_urlsafe = deterministic_token
    for module in tuple(sys.modules.values()):
        if not isinstance(module, ModuleType):
            continue
        allowed = (
            "ai_pdf_api",
            "ai_pdf_worker",
            "citeframe_persistence",
            "citeframe_research_persistence",
        )
        if module.__name__.startswith(allowed) and hasattr(module, "uuid4"):
            setattr(module, "uuid4", deterministic_uuid4)
        module_datetime = getattr(module, "datetime", None)
        if (
            module.__name__.startswith(allowed)
            and isinstance(module_datetime, type)
            and issubclass(module_datetime, datetime)
        ):
            setattr(module, "datetime", _FixedDateTime)


def _plain_error(error: BaseException) -> dict[str, object]:
    return {
        "type": type(error).__name__,
        "code": getattr(error, "code", None),
        "statusCode": getattr(error, "status_code", None),
        "message": str(error),
    }


def _simple_database(path: Path):
    from ai_pdf_api.db.base import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    _install_determinism()
    del path
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True)
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def _seed_simple(db: Any, name: str, *, status: str = "queued", max_attempts: int = 3) -> dict[str, object]:
    from ai_pdf_api.models import (
        Asset,
        ResearchBudgetLedger,
        ResearchExecutionSnapshot,
        ResearchRun,
        ResearchStep,
        User,
        Workspace,
        WorkspaceMembership,
    )

    user = User(
        id=_id(f"{name}/creator"),
        email=f"{name}@example.com",
        name=f"A2a {name}",
        password_hash="hash",
        avatar_url="",
        created_at=NOW,
        updated_at=NOW,
    )
    member = User(
        id=_id(f"{name}/member"),
        email=f"{name}-member@example.com",
        name=f"A2a {name} Member",
        password_hash="hash",
        avatar_url="",
        created_at=NOW,
        updated_at=NOW,
    )
    workspace = Workspace(
        id=_id(f"{name}/workspace"),
        name=f"A2a {name}",
        created_by_user_id=user.id,
        created_at=NOW,
        updated_at=NOW,
    )
    asset = Asset(
        id=_id(f"{name}/asset"),
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        asset_kind="pdf",
        title="Frozen source",
        source_filename="source.pdf",
        object_key=f"workspaces/{workspace.id}/source.pdf",
        mime_type="application/pdf",
        byte_size=100,
        source_sha256=_sha("source"),
        status="ready",
        current_processing_generation=2,
        current_index_version=3,
        created_at=NOW,
        updated_at=NOW,
    )
    run = ResearchRun(
        id=_id(f"{name}/run"),
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        status=status,
        state_version=1,
        next_event_seq=1,
        cost_currency="USD",
        created_at=NOW,
        updated_at=NOW,
    )
    snapshot = ResearchExecutionSnapshot(
        id=_id(f"{name}/snapshot"),
        workspace_id=workspace.id,
        run_id=run.id,
        approved_plan_revision_id=_id(f"{name}/revision"),
        approval_decision_id=_id(f"{name}/decision"),
        approved_plan_artifact_id=_id(f"{name}/artifact"),
        approved_plan_artifact_sha256=_sha("plan"),
        input_version=1,
        question_text="Compare the evidence.",
        scope_mode="selected",
        workflow_version_id=_id(f"{name}/workflow"),
        generation_provider="openai",
        generation_model="gpt-5.5",
        provider_config_fingerprint=_sha("provider"),
        pricing_version="research-pricing-v1",
        data_boundary_policy_version="boundary-v1",
        embedding_provider="ollama",
        embedding_model="qwen3-embedding:0.6b",
        embedding_version="embedding-v1",
        retrieval_strategy="hybrid",
        retrieval_top_k=6,
        max_parallel_researchers=2,
        max_step_attempts=max_attempts,
        max_provider_calls=8,
        max_tool_calls=8,
        max_input_tokens=10_000,
        max_output_tokens=10_000,
        max_cost_microunits=100_000,
        cost_currency="USD",
        budget_policy_version="budget-v1",
        retry_policy_version="retry-v1",
        max_run_timeout_seconds=3_600,
        max_step_timeout_seconds=600,
        max_provider_timeout_seconds=120,
        agent_result_schema_version="research-agent-results-v1",
        context_policy_version="research-context-policy-v1",
        compact_policy_version="research-compact-policy-v1",
        execution_snapshot_sha256=_sha("execution"),
        created_at=NOW,
    )
    run.approved_execution_snapshot_id = snapshot.id
    ledger = ResearchBudgetLedger(
        id=_id(f"{name}/ledger"),
        workspace_id=workspace.id,
        run_id=run.id,
        execution_snapshot_id=snapshot.id,
        currency="USD",
        state_version=1,
        usage_final=True,
        updated_at=NOW,
    )
    step = ResearchStep(
        id=_id(f"{name}/step"),
        workspace_id=workspace.id,
        run_id=run.id,
        execution_snapshot_id=snapshot.id,
        step_key="researcher:branch-a",
        step_kind="researcher",
        branch_key="branch-a",
        status="queued",
        state_version=1,
        max_attempts_snapshot=max_attempts,
        current_attempt_number=0,
        input_sha256=_sha("input"),
        queued_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    db.add_all([user, member, workspace])
    db.flush()
    db.add_all(
        [
            WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role="member", created_at=NOW),
            WorkspaceMembership(workspace_id=workspace.id, user_id=member.id, role="member", created_at=NOW),
            asset,
            run,
            snapshot,
            ledger,
            step,
        ]
    )
    db.commit()
    return {"creator": user, "member": member, "workspace": workspace, "run": run, "snapshot": snapshot, "step": step}


def _event_row(event: Any) -> dict[str, object]:
    return {
        "id": event.id,
        "workspaceId": event.workspace_id,
        "runId": event.run_id,
        "seq": event.seq,
        "type": event.event_type,
        "schemaVersion": event.event_schema_version,
        "stepId": event.step_id,
        "attemptId": event.attempt_id,
        "dedupeKey": event.dedupe_key,
        "payload": event.payload_json,
        "createdAt": event.created_at,
    }


def _lease_retry_cancel_reclaim(path: Path, normalizer: _Normalizer) -> dict[str, object]:
    print("a2a_probe stage=transitions_start", flush=True)
    from ai_pdf_api.models import ResearchEvent, ResearchRun, ResearchStep, ResearchStepAttempt
    from ai_pdf_api.schemas.research import RetryResearchStepRequest
    from ai_pdf_api.services import research_worker
    from ai_pdf_api.services.research.research_recovery import retry_research_step
    from ai_pdf_api.services.research.research_runs import cancel_research_run
    from sqlalchemy import select

    engine, sessions = _simple_database(path)
    results: dict[str, object] = {}
    with sessions() as db:
        lease_fixture = _seed_simple(db, "lease")
        lease = research_worker.claim_specific_research_step(
            db,
            run_id=lease_fixture["run"].id,
            step_key=lease_fixture["step"].step_key,
            branch_key=lease_fixture["step"].branch_key,
            worker_instance_id="worker-a",
            lease_seconds=60,
            now=NOW,
        )
        assert lease is not None
        db.commit()
        try:
            research_worker.heartbeat_research_step(
                db,
                attempt_id=lease.attempt_id,
                lease_token="wrong-token",
                lease_seconds=60,
                now=NOW + timedelta(seconds=1),
            )
        except Exception as error:  # noqa: BLE001 - error is oracle output
            fencing = _plain_error(error)
            db.rollback()
        else:
            raise AssertionError("wrong lease token was accepted")
        try:
            research_worker.complete_research_step(
                db,
                attempt_id=lease.attempt_id,
                lease_token="wrong-token",
                output_sha256=_sha("wrong-token-output"),
                now=NOW + timedelta(seconds=1),
            )
        except Exception as error:  # noqa: BLE001 - error is oracle output
            wrong_completion = _plain_error(error)
            db.rollback()
        else:
            raise AssertionError("wrong lease token completed work")
        heartbeat = research_worker.heartbeat_research_step(
            db,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            lease_seconds=60,
            now=NOW + timedelta(seconds=2),
        )
        db.commit()
        research_worker.complete_research_step(
            db,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            output_sha256=_sha("lease-output"),
            now=NOW + timedelta(seconds=3),
        )
        db.commit()
        try:
            research_worker.complete_research_step(
                db,
                attempt_id=lease.attempt_id,
                lease_token=lease.lease_token,
                output_sha256=_sha("repeat-output"),
                now=NOW + timedelta(seconds=4),
            )
        except Exception as error:  # noqa: BLE001 - error is oracle output
            repeated_completion = _plain_error(error)
            db.rollback()
        else:
            raise AssertionError("terminal attempt completed twice")

        late_fixture = _seed_simple(db, "late")
        late = research_worker.claim_specific_research_step(
            db,
            run_id=late_fixture["run"].id,
            step_key=late_fixture["step"].step_key,
            branch_key=late_fixture["step"].branch_key,
            worker_instance_id="worker-late",
            lease_seconds=1,
            now=NOW,
        )
        db.commit()
        try:
            research_worker.complete_research_step(
                db,
                attempt_id=late.attempt_id,
                lease_token=late.lease_token,
                output_sha256=_sha("late-output"),
                now=NOW + timedelta(seconds=2),
            )
        except Exception as error:  # noqa: BLE001 - error is oracle output
            late_completion = _plain_error(error)
            db.rollback()
        else:
            raise AssertionError("expired lease completed work")
        results["leaseFencing"] = normalizer.value(
            {
                "claim": lease,
                "wrongHeartbeat": fencing,
                "wrongCompletion": wrong_completion,
                "heartbeat": heartbeat,
                "repeatedCompletion": repeated_completion,
                "lateCompletion": late_completion,
            }
        )
        results["exactPayloadBytes"] = {
            "leaseClaim": _raw_bytes_b64(lease),
            "leaseHeartbeat": _raw_bytes_b64(heartbeat),
        }

        retry_fixture = _seed_simple(db, "retry")
        first = research_worker.claim_specific_research_step(
            db,
            run_id=retry_fixture["run"].id,
            step_key=retry_fixture["step"].step_key,
            branch_key=retry_fixture["step"].branch_key,
            worker_instance_id="worker-retry",
            lease_seconds=60,
            now=NOW,
        )
        assert first is not None
        db.commit()
        disposition = research_worker.fail_research_step(
            db,
            attempt_id=first.attempt_id,
            lease_token=first.lease_token,
            error_code="provider_temporarily_unavailable",
            now=NOW + timedelta(seconds=1),
        )
        db.commit()
        second = research_worker.claim_specific_research_step(
            db,
            run_id=retry_fixture["run"].id,
            step_key=retry_fixture["step"].step_key,
            branch_key=retry_fixture["step"].branch_key,
            worker_instance_id="worker-retry-2",
            lease_seconds=60,
            now=NOW + timedelta(seconds=2),
        )
        assert second is not None
        db.commit()

        manual_fixture = _seed_simple(db, "manual-retry")
        manual_run = manual_fixture["run"]
        manual_step = manual_fixture["step"]
        manual_run.status = "awaiting_retry"
        manual_run.state_version = 2
        manual_step.status = "failed"
        manual_step.state_version = 2
        manual_step.current_attempt_number = 1
        manual_step.error_code = "provider_temporarily_unavailable"
        manual_attempt = ResearchStepAttempt(
            id=_id("manual-retry/attempt"),
            workspace_id=manual_run.workspace_id,
            step_id=manual_step.id,
            attempt_number=1,
            status="failed",
            input_sha256=manual_step.input_sha256,
            error_code="provider_temporarily_unavailable",
            started_at=NOW,
            finished_at=NOW,
        )
        db.add(manual_attempt)
        db.commit()
        retry_request = RetryResearchStepRequest(
            expectedStateVersion=manual_run.state_version,
            expectedStepStateVersion=manual_step.state_version,
            failedAttempt=1,
        )
        manual_status, manual_payload, manual_replayed = retry_research_step(
            db,
            workspace_id=manual_run.workspace_id,
            actor_user_id=manual_fixture["creator"].id,
            run_id=manual_run.id,
            step_id=manual_step.id,
            payload=retry_request,
            idempotency_key="a2a-manual-retry-0001",
        )
        db.commit()

        manual_permission_fixture = _seed_simple(db, "manual-retry-permission")
        denied_run = manual_permission_fixture["run"]
        denied_step = manual_permission_fixture["step"]
        denied_run.status = "awaiting_retry"
        denied_run.state_version = 2
        denied_step.status = "failed"
        denied_step.state_version = 2
        denied_step.current_attempt_number = 1
        denied_step.error_code = "provider_temporarily_unavailable"
        db.add(
            ResearchStepAttempt(
                id=_id("manual-retry-permission/attempt"),
                workspace_id=denied_run.workspace_id,
                step_id=denied_step.id,
                attempt_number=1,
                status="failed",
                input_sha256=denied_step.input_sha256,
                error_code="provider_temporarily_unavailable",
                started_at=NOW,
                finished_at=NOW,
            )
        )
        db.commit()
        denied_request = RetryResearchStepRequest(
            expectedStateVersion=denied_run.state_version,
            expectedStepStateVersion=denied_step.state_version,
            failedAttempt=1,
        )
        try:
            retry_research_step(
                db,
                workspace_id=denied_run.workspace_id,
                actor_user_id=manual_permission_fixture["member"].id,
                run_id=denied_run.id,
                step_id=denied_step.id,
                payload=denied_request,
                idempotency_key="a2a-manual-retry-permission-0001",
            )
        except Exception as error:  # noqa: BLE001 - error is oracle output
            retry_permission = _plain_error(error)
            db.rollback()
        else:
            raise AssertionError("foreign member retried a run")

        reclaim_fixture = _seed_simple(db, "reclaim")
        abandoned = research_worker.claim_specific_research_step(
            db,
            run_id=reclaim_fixture["run"].id,
            step_key=reclaim_fixture["step"].step_key,
            branch_key=reclaim_fixture["step"].branch_key,
            worker_instance_id="worker-expired",
            lease_seconds=1,
            now=NOW,
        )
        assert abandoned is not None
        db.commit()
        reclaimed_count = research_worker.reclaim_expired_research_steps(db, now=NOW + timedelta(seconds=2))
        db.commit()
        recovered = research_worker.claim_specific_research_step(
            db,
            run_id=reclaim_fixture["run"].id,
            step_key=reclaim_fixture["step"].step_key,
            branch_key=reclaim_fixture["step"].branch_key,
            worker_instance_id="worker-recovered",
            lease_seconds=60,
            now=NOW + timedelta(seconds=3),
        )
        assert recovered is not None
        db.commit()

        cancel_fixture = _seed_simple(db, "cancel")
        cancel_status, cancel_payload, cancel_replayed = cancel_research_run(
            db,
            workspace_id=cancel_fixture["workspace"].id,
            actor_user_id=cancel_fixture["creator"].id,
            actor_role="member",
            run_id=cancel_fixture["run"].id,
            expected_state_version=cancel_fixture["run"].state_version,
            reason_code="user_requested",
            idempotency_key="a2a-cancel-key-0001",
        )

        permission_fixture = _seed_simple(db, "permission")
        try:
            cancel_research_run(
                db,
                workspace_id=permission_fixture["workspace"].id,
                actor_user_id=permission_fixture["member"].id,
                actor_role="member",
                run_id=permission_fixture["run"].id,
                expected_state_version=permission_fixture["run"].state_version,
                reason_code="user_requested",
                idempotency_key="a2a-permission-key-0001",
            )
        except Exception as error:  # noqa: BLE001 - error is oracle output
            permission = _plain_error(error)
            db.rollback()
        else:
            raise AssertionError("foreign member cancelled a run")

        original = db.get(ResearchStepAttempt, abandoned.attempt_id)
        retry_step = db.get(ResearchStep, retry_fixture["step"].id)
        cancel_run = db.get(ResearchRun, cancel_fixture["run"].id)
        results["retryCancelReclaimRecovery"] = normalizer.value(
            {
                "retryDisposition": disposition,
                "retryAttemptNumbers": [first.attempt_number, second.attempt_number],
                "retryStepStatus": retry_step.status if retry_step else None,
                "manualRetryHttpStatus": manual_status,
                "manualRetryReplayed": manual_replayed,
                "manualRetryRunStatus": manual_payload["run"]["status"],
                "manualRetryStepStatus": manual_payload["step"]["status"],
                "reclaimedCount": reclaimed_count,
                "abandonedStatus": original.status if original else None,
                "recoveredAttemptNumber": recovered.attempt_number,
                "cancelHttpStatus": cancel_status,
                "cancelReplayed": cancel_replayed,
                "cancelStatus": cancel_run.status if cancel_run else None,
                "cancelPayloadStatus": cancel_payload["run"]["status"],
            }
        )
        results["permission"] = normalizer.value(
            {"cancel": permission, "manualRetry": retry_permission}
        )
        results["exactPayloadBytes"]["manualRetry"] = _raw_bytes_b64(
            {"status": manual_status, "payload": manual_payload, "replayed": manual_replayed}
        )
        events = list(db.scalars(select(ResearchEvent).order_by(ResearchEvent.run_id, ResearchEvent.seq)).all())
        results["exactEventBytes"] = {
            "transitions": [_raw_bytes_b64(_event_row(event)) for event in events]
        }
        results["_transitionDbRows"] = _database_rows(db, _Normalizer())
    engine.dispose()
    print("a2a_probe stage=transitions_done", flush=True)
    return results


def _database_rows(session: Any, normalizer: _Normalizer) -> dict[str, object]:
    from sqlalchemy import inspect, text

    inspector = inspect(session.bind)
    names = {
        name
        for name in inspector.get_table_names()
        if name.startswith("research_") or name.startswith("human_decision")
    }
    rows: dict[str, object] = {}
    for table in sorted(names & set(inspector.get_table_names())):
        columns = [column["name"] for column in inspector.get_columns(table)]
        result = session.execute(text(f'SELECT * FROM "{table}"')).mappings().all()
        normalized = [normalizer.value({column: row[column] for column in columns}) for row in result]
        rows[table] = sorted(normalized, key=lambda item: _canonical(item))
    return rows


def _process_one_flow(path: Path, normalizer: _Normalizer) -> dict[str, object]:
    print("a2a_probe stage=process_setup", flush=True)
    import ai_pdf_api.routers.research as router_module
    from ai_pdf_api.core.settings import settings
    from ai_pdf_api.db.base import Base
    from ai_pdf_api.db.session import get_db
    from ai_pdf_api.models import HumanDecision, ResearchRun
    from ai_pdf_api.routers.research import router
    from ai_pdf_api.services import research_worker
    from ai_pdf_api.services.research.research_versions_service import publish_research_versions_for_release
    from ai_pdf_worker.r800_acceptance_common import IDS
    from ai_pdf_worker.r800_acceptance_fixture import seed_state
    from ai_pdf_worker.research_runtime import (
        ResearchWorkProcessor,
        build_default_research_service,
    )
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    _install_determinism()
    normalizer = _Normalizer()
    del path
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    objects: dict[str, bytes] = {}
    from ai_pdf_api.services.research import research_views
    research_views.download_bytes = lambda key: objects[key]
    seed_state(
        sessions,
        uploader=lambda key, payload, _media: objects.__setitem__(key, payload),
        cleanup=lambda key: objects.pop(key, None),
    )
    with sessions() as db:
        publish_research_versions_for_release(db, NOW)
        db.commit()

    from ai_pdf_api.models import Asset, ContentUnit, EvidenceLocator
    from ai_pdf_api.services.retrieval import RetrievedContent
    from ai_pdf_api.services.research import research_worker_evidence

    def deterministic_retrieve(db: Any, _workspace_id: str, _query: str, _embedding: object, **_kwargs: object):
        unit = db.get(ContentUnit, IDS["unit"])
        asset = db.get(Asset, IDS["asset"])
        locator = db.get(EvidenceLocator, IDS["locator"])
        assert unit is not None and asset is not None and locator is not None
        return [RetrievedContent(unit, asset, locator, "text", 0.0, (asset.id, "pdf_page:1"))]

    research_worker_evidence.retrieve_query_content = deterministic_retrieve
    router_module.RESEARCH_EVENT_SESSION_FACTORY = sessions
    app = FastAPI()
    app.include_router(router)

    def override_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db

    class Embedding:
        provider = settings.embedding_provider
        model = settings.embedding_model
        version = settings.embedding_version
        dimensions = 1024

        def embed_query(self, _query: str) -> list[float]:
            return [1.0, *([0.0] * 1023)]

    class Provider:
        provider = settings.generation_provider
        model = settings.generation_model
        calls: list[str]

        def __init__(self) -> None:
            self.calls = []

        def generate(self, messages: list[dict[str, object]], *, max_output_tokens: int) -> str:
            assert max_output_tokens > 0
            variables = json.loads(str(messages[-1]["content"]))
            if "planOutputSchema" in variables:
                node = "planner"
                asset_id = variables["frozenAssetScope"]["assets"][0]["assetId"]
                value = {
                    "summary": "Deterministic one-branch plan.",
                    "subproblems": [
                        {"question": "What does the source establish?", "assetIds": [asset_id], "expectedEvidence": []}
                    ],
                    "knownGaps": [],
                    "estimatedProviderCalls": 5,
                }
            elif "toolContracts" in variables:
                node = "researcher"
                handle = variables["toolContracts"]["evidence"][0]["evidenceHandle"]
                value = {
                    "claims": [
                        {
                            "text": "The fixture preserves immutable evidence.",
                            "evidenceHandleIds": [handle],
                        }
                    ]
                }
            elif "reasonTaxonomy" in variables:
                node = "verifier"
                value = {"claims": [{"id": item["id"], "status": "supported"} for item in variables["claims"]]}
            elif "conflictClaimIds" in variables.get("resultSchema", {}).get("properties", {}):
                node = "critic"
                value = {"conflictClaimIds": [item["id"] for item in variables["claims"]]}
            else:
                node = "synthesizer"
                value = {
                    "factClaimIds": [],
                    "unresolvedClaimIds": [item["id"] for item in variables["claims"]],
                }
            self.calls.append(node)
            return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))

    store_bytes = lambda key, payload, _media: objects.__setitem__(key, payload)
    cleanup_bytes = lambda key: objects.pop(key, None)

    production_search_frozen_evidence = research_worker.search_frozen_evidence

    def injected_search(db: Any, **kwargs: object) -> object:
        return production_search_frozen_evidence(
            db,
            **kwargs,
            embedding_provider=Embedding(),
        )

    def set_keyword_defaults(function: Any, **values: object) -> None:
        defaults = dict(function.__kwdefaults__ or {})
        defaults.update(values)
        function.__kwdefaults__ = defaults

    uow_enters = {"count": 0}
    try:
        from ai_pdf_worker import research_persistence_service as composition
    except ImportError:
        composition = None

    if composition is None:
        # Baseline production composition is the API Research facade.
        research_worker.search_frozen_evidence = injected_search
        for function in (
            research_worker.publish_research_plan,
            research_worker.complete_research_branch,
            research_worker.complete_research_synthesis,
            research_worker.wait_for_conflict_decision,
        ):
            set_keyword_defaults(
                function,
                store_bytes=store_bytes,
                cleanup_bytes=cleanup_bytes,
            )
        set_keyword_defaults(
            research_worker.publish_final_report,
            store_bytes=store_bytes,
            cleanup_bytes=cleanup_bytes,
            committed_session_factory=sessions,
        )
        service = build_default_research_service()
        assert service is research_worker
        composition_kind = "baseline-api-research-worker"
    else:
        # Candidate production composition keeps only capability adapters outside neutral persistence.
        composition.upload_bytes = store_bytes
        composition.delete_object_if_exists = cleanup_bytes
        composition.SessionLocal = sessions
        composition.search_frozen_evidence = injected_search
        service = build_default_research_service()

        from ai_pdf_worker import research_runtime_core

        original_enter = research_runtime_core.ResearchUnitOfWork.__enter__

        def observed_enter(unit_of_work: Any) -> Any:
            uow_enters["count"] += 1
            return original_enter(unit_of_work)

        research_runtime_core.ResearchUnitOfWork.__enter__ = observed_enter
        if os.environ.get("A2A_DIFFERENTIAL_MUTATION") == "candidate-api-facade":
            service = research_worker
        assert service is not research_worker, (
            "candidate production composition must not use API research_worker facade",
            type(service).__name__,
        )
        assert type(service).__name__ == "SimpleNamespace", type(service).__name__
        command_module = service.claim_next_research_step.__module__
        assert command_module.startswith("citeframe_research_persistence"), (
            "candidate production composition must expose neutral commands",
            command_module,
        )
        composition_kind = "candidate-neutral-research-uow"

    provider = Provider()
    processor = ResearchWorkProcessor(
        sessions,
        service,
        provider=provider,
    )
    api_payload_bytes: list[str] = []
    headers = {
        "x-ai-pdf-internal-token": settings.api_internal_token,
        "x-user-id": IDS["creator"],
        "Idempotency-Key": "a2a-process-create-0001",
    }
    with TestClient(app) as client:
        response = client.post(
            f"/v1/workspaces/{IDS['workspace']}/research-runs",
            headers=headers,
            json={
                "question": "What does the fixed fixture establish?",
                "assetScope": {"mode": "selected", "assetIds": [IDS["asset"]]},
            },
        )
        assert response.status_code == 201, response.text
        api_payload_bytes.append(base64.b64encode(response.content).decode())
        run_id = response.json()["run"]["id"]
        print("a2a_probe stage=process_planner", flush=True)
        outputs = [processor.process_one()]
        print("a2a_probe stage=process_planner_done", flush=True)
        with sessions() as db:
            run = db.get(ResearchRun, run_id)
            decision = db.scalar(
                select(HumanDecision).where(
                    HumanDecision.run_id == run_id,
                    HumanDecision.decision_type == "plan_approval",
                    HumanDecision.status == "pending",
                )
            )
            assert run is not None and decision is not None
            plan_request = {
                "expectedStateVersion": run.state_version,
                "expectedDecisionStateVersion": decision.state_version,
                "inputArtifactSha256": decision.input_artifact_sha256,
                "inputSnapshotSha256": decision.input_snapshot_sha256,
                "action": "approve",
                "comment": None,
                "revision": None,
            }
            decision_id = decision.id
        response = client.post(
            f"/v1/workspaces/{IDS['workspace']}/research-runs/{run_id}/plan-decisions/{decision_id}",
            headers={**headers, "Idempotency-Key": "a2a-process-plan-0001"},
            json=plan_request,
        )
        assert response.status_code == 200, response.text
        api_payload_bytes.append(base64.b64encode(response.content).decode())
        print("a2a_probe stage=process_graph", flush=True)
        outputs.append(processor.process_one())
        print("a2a_probe stage=process_graph_done", flush=True)
        with sessions() as db:
            run = db.get(ResearchRun, run_id)
            decision = db.scalar(
                select(HumanDecision).where(
                    HumanDecision.run_id == run_id,
                    HumanDecision.decision_type == "conflict_resolution",
                    HumanDecision.status == "pending",
                )
            )
            assert run is not None and decision is not None
            conflict_request = {
                "expectedStateVersion": run.state_version,
                "expectedDecisionStateVersion": decision.state_version,
                "inputArtifactSha256": decision.input_artifact_sha256,
                "inputSnapshotSha256": decision.input_snapshot_sha256,
                "action": "keep_as_unresolved",
                "comment": "Preserve the conflict as unresolved.",
            }
            decision_id = decision.id
        response = client.post(
            f"/v1/workspaces/{IDS['workspace']}/research-runs/{run_id}/conflict-decisions/{decision_id}",
            headers={**headers, "Idempotency-Key": "a2a-process-conflict-0001"},
            json=conflict_request,
        )
        assert response.status_code == 200, response.text
        api_payload_bytes.append(base64.b64encode(response.content).decode())
        print("a2a_probe stage=process_resume", flush=True)
        outputs.extend([processor.process_one(), processor.process_one()])
        print("a2a_probe stage=process_resume_done", flush=True)

    with sessions() as db:
        run = db.get(ResearchRun, run_id)
        assert run is not None
        rows = _database_rows(db, normalizer)
        event_types = [row["event_type"] for row in rows["research_events"]]
        step_kinds = [row["step_kind"] for row in rows["research_steps"]]
        from ai_pdf_api.models import ResearchEvent
        process_events = list(
            db.scalars(
                select(ResearchEvent)
                .where(ResearchEvent.run_id == run_id)
                .order_by(ResearchEvent.seq)
            ).all()
        )
        process_event_bytes = [_raw_bytes_b64(_event_row(event)) for event in process_events]
        object_payload_bytes = {
            key: base64.b64encode(payload).decode()
            for key, payload in sorted(objects.items())
            if key.startswith("research/")
        }
        final = {
            "processOneOutputs": outputs,
            "providerNodes": provider.calls,
            "runStatus": run.status,
            "stepKinds": step_kinds,
            "eventTypes": event_types,
            "objectPayloads": {
                str(normalizer.value(key)): normalizer.bytes_b64(
                    json.loads(payload) if key.endswith(".json") else payload.decode("utf-8")
                )
                for key, payload in sorted(objects.items())
                if key.startswith("research/")
            },
        }
    engine.dispose()
    return {
        "normalizedDbRows": rows,
        "fixedMultiStepProcessOne": normalizer.value(final),
        "_processExactEventBytes": process_event_bytes,
        "_processExactPayloadBytes": {
            "apiResponses": api_payload_bytes,
            "objectPayloads": object_payload_bytes,
        },
        "_composition": {
            "kind": composition_kind,
            "commandModule": service.claim_next_research_step.__module__,
            "uowEnterCount": uow_enters["count"],
        },
    }


def test_generate_executable_differential_report(tmp_path: Path) -> None:
    assert OUTPUT is not None
    # Import the complete API/Worker surface before replacing module-level uuid4 seams.
    import ai_pdf_api.services.research.research_worker_evidence  # noqa: F401
    import ai_pdf_worker.research_runtime  # noqa: F401

    _install_determinism()
    normalizer = _Normalizer()
    semantics = _lease_retry_cancel_reclaim(tmp_path / "transitions.db", normalizer)
    process = _process_one_flow(tmp_path / "process-one.db", normalizer)
    transition_rows = semantics.pop("_transitionDbRows")
    process_rows = process.pop("normalizedDbRows")
    composition = process.pop("_composition")
    semantics["normalizedDbRows"] = {
        "transitions": transition_rows,
        "processOne": process_rows,
    }
    semantics["exactEventBytes"]["processOne"] = process.pop("_processExactEventBytes")
    semantics["exactPayloadBytes"]["processOne"] = process.pop("_processExactPayloadBytes")
    semantics.update(process)
    required = {
        "normalizedDbRows",
        "exactPayloadBytes",
        "exactEventBytes",
        "leaseFencing",
        "retryCancelReclaimRecovery",
        "permission",
        "fixedMultiStepProcessOne",
    }
    assert set(semantics) == required
    report = {
        "schemaVersion": "citeframe-a2a-probe-v1",
        "label": os.environ.get("A2A_DIFFERENTIAL_LABEL"),
        "composition": composition,
        "semantics": semantics,
    }
    Path(OUTPUT).write_bytes(_canonical(report) + b"\n")
