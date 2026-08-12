from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from ai_pdf_api.db.base import Base
from ai_pdf_api.models import (
    Asset,
    ResearchBudgetLedger,
    ResearchExecutionSnapshot,
    ResearchProviderCall,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
    User,
    Workspace,
    WorkspaceMembership,
)
from ai_pdf_api.core.settings import settings
from ai_pdf_api.services import research_worker
from ai_pdf_api.services.capabilities import current_execution_profile_fingerprint
from ai_pdf_api.services.research_constants import DATA_BOUNDARY_POLICY, PRICING_VERSION
from ai_pdf_worker.research_executor import (
    ApprovedResearchExecution,
    FrozenAsset,
)
from ai_pdf_worker.research_runtime import (
    LedgeredGeneration,
    ResearchWorkProcessor,
    SqlResearchLedgerAdapter,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@pytest.fixture()
def runtime_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'worker-runtime.db'}", future=True)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    now = datetime.now(UTC)
    user = User(
        id=str(uuid4()),
        email="worker-runtime@example.com",
        name="Worker Runtime",
        password_hash="hash",
        avatar_url="",
    )
    workspace = Workspace(
        id=str(uuid4()),
        name="Worker Runtime",
        created_by_user_id=user.id,
        created_at=now,
        updated_at=now,
    )
    asset = Asset(
        id=str(uuid4()),
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        asset_kind="pdf",
        title="Source",
        source_filename="source.pdf",
        object_key="source.pdf",
        mime_type="application/pdf",
        byte_size=100,
        status="ready",
        current_processing_generation=2,
        current_index_version=3,
        created_at=now,
        updated_at=now,
    )
    run = ResearchRun(
        id=str(uuid4()),
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        status="queued",
        state_version=1,
        next_event_seq=1,
        cost_currency="USD",
        created_at=now,
        updated_at=now,
    )
    provider_config_fingerprint = current_execution_profile_fingerprint(retrieval_top_k=6)
    snapshot = ResearchExecutionSnapshot(
        id=str(uuid4()),
        workspace_id=workspace.id,
        run_id=run.id,
        approved_plan_revision_id=str(uuid4()),
        approval_decision_id=str(uuid4()),
        approved_plan_artifact_id=str(uuid4()),
        approved_plan_artifact_sha256=sha256("plan"),
        input_version=1,
        question_text="Question",
        scope_mode="selected",
        workflow_version_id=str(uuid4()),
        generation_provider=settings.generation_provider,
        generation_model=settings.generation_model,
        provider_config_fingerprint=provider_config_fingerprint,
        pricing_version=PRICING_VERSION,
        data_boundary_policy_version=DATA_BOUNDARY_POLICY,
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model,
        embedding_version=settings.embedding_version,
        retrieval_strategy=settings.retrieval_strategy,
        retrieval_top_k=6,
        max_parallel_researchers=2,
        max_step_attempts=3,
        max_provider_calls=8,
        max_tool_calls=8,
        max_input_tokens=10_000,
        max_output_tokens=10_000,
        max_cost_microunits=100_000,
        cost_currency="USD",
        budget_policy_version="budget-v1",
        retry_policy_version="retry-v1",
        max_run_timeout_seconds=3600,
        max_step_timeout_seconds=600,
        max_provider_timeout_seconds=120,
        execution_snapshot_sha256=sha256("execution"),
        created_at=now,
    )
    run.approved_execution_snapshot_id = snapshot.id
    ledger = ResearchBudgetLedger(
        id=str(uuid4()),
        workspace_id=workspace.id,
        run_id=run.id,
        execution_snapshot_id=snapshot.id,
        currency="USD",
        updated_at=now,
    )
    step = ResearchStep(
        id=str(uuid4()),
        workspace_id=workspace.id,
        run_id=run.id,
        execution_snapshot_id=snapshot.id,
        step_key="researcher:branch-1",
        step_kind="researcher",
        branch_key="branch-1",
        status="queued",
        state_version=1,
        max_attempts_snapshot=3,
        current_attempt_number=0,
        input_sha256=sha256("input"),
        queued_at=now,
        created_at=now,
        updated_at=now,
    )
    with sessions() as db:
        db.add_all([user, workspace])
        db.flush()
        db.add(WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role="owner"))
        db.add_all([asset, run, snapshot, ledger, step])
        db.commit()
    yield sessions, workspace.id, run.id, snapshot.id, step.id, asset.id
    engine.dispose()


def execution(workspace_id: str, run_id: str, snapshot_id: str, step_id: str, asset_id: str) -> ApprovedResearchExecution:
    return ApprovedResearchExecution(
        workspace_id,
        run_id,
        snapshot_id,
        sha256("execution"),
        "Question",
        (),
        (FrozenAsset(asset_id, 2, 3),),
        "workflow-unused",
        ("prompt-unused",),
        current_execution_profile_fingerprint(retrieval_top_k=6),
        "budget-v1",
        "retry-v1",
        2,
        8,
        8,
        None,
        10_000,
        10_000,
        100_000,
    )


def test_real_ledger_lease_and_provider_reconcile(runtime_db) -> None:
    sessions, workspace_id, run_id, snapshot_id, step_id, asset_id = runtime_db
    adapter = SqlResearchLedgerAdapter(sessions, research_worker, worker_instance_id="worker-1")
    lease = adapter.claim_step(
        execution(workspace_id, run_id, snapshot_id, step_id, asset_id),
        step_key="researcher:branch-1",
        branch_key="branch-1",
    )

    class Provider:
        provider = settings.generation_provider
        model = settings.generation_model
        max_output_tokens: int | None = None

        def generate(
            self,
            _messages: list[dict[str, object]],
            *,
            max_output_tokens: int,
        ) -> str:
            self.max_output_tokens = max_output_tokens
            return '{"claims":[]}'

    provider = Provider()
    result = LedgeredGeneration(
        sessions,
        research_worker,
        execution(workspace_id, run_id, snapshot_id, step_id, asset_id),
        provider,
    ).generate(lease, node_key="researcher", messages=[{"role": "user", "content": "Question"}])

    with sessions() as db:
        provider_call = db.scalar(select(ResearchProviderCall))
        attempt = db.get(ResearchStepAttempt, lease.attempt_id)
        assert provider_call is not None and provider_call.status == "succeeded"
        assert provider_call.usage_source == "estimated" and provider_call.usage_final is False
        assert attempt is not None and attempt.provider_call_count == 1
    assert result == '{"claims":[]}'
    assert provider.max_output_tokens == 10_000


def test_legacy_provider_without_output_cap_is_not_retried(runtime_db) -> None:
    sessions, workspace_id, run_id, snapshot_id, step_id, asset_id = runtime_db
    adapter = SqlResearchLedgerAdapter(sessions, research_worker, worker_instance_id="worker-1")
    lease = adapter.claim_step(
        execution(workspace_id, run_id, snapshot_id, step_id, asset_id),
        step_key="researcher:branch-1",
        branch_key="branch-1",
    )
    calls = 0

    class LegacyProvider:
        provider = settings.generation_provider
        model = settings.generation_model

        def generate(self, _messages: list[dict[str, object]]) -> str:
            nonlocal calls
            calls += 1
            return '{"claims":[]}'

    with pytest.raises(TypeError):
        LedgeredGeneration(
            sessions,
            research_worker,
            execution(workspace_id, run_id, snapshot_id, step_id, asset_id),
            LegacyProvider(),
        ).generate(lease, node_key="researcher", messages=[{"role": "user", "content": "Question"}])

    assert calls == 0
    with sessions() as db:
        provider_call = db.scalar(select(ResearchProviderCall))
        assert provider_call is not None and provider_call.status == "outcome_unknown"


def test_real_send_rejection_cancels_reservation_without_calling_provider(runtime_db) -> None:
    sessions, workspace_id, run_id, snapshot_id, step_id, asset_id = runtime_db
    adapter = SqlResearchLedgerAdapter(sessions, research_worker, worker_instance_id="worker-1")
    lease = adapter.claim_step(
        execution(workspace_id, run_id, snapshot_id, step_id, asset_id),
        step_key="researcher:branch-1",
        branch_key="branch-1",
    )

    class CancelAfterReserve:
        def __getattr__(self, name: str):
            return getattr(research_worker, name)

        def reserve_provider_call(self, db, **kwargs):
            reservation = research_worker.reserve_provider_call(db, **kwargs)
            run = db.get(ResearchRun, run_id)
            assert run is not None
            run.status = "cancel_requested"
            run.cancel_requested_by_user_id = run.created_by_user_id
            run.cancel_requested_at = datetime.now(UTC)
            db.commit()
            return reservation

    class Provider:
        provider = settings.generation_provider
        model = settings.generation_model

        def generate(
            self,
            _messages: list[dict[str, object]],
            *,
            max_output_tokens: int,
        ) -> str:
            del max_output_tokens
            raise AssertionError("provider must not be called")

    with pytest.raises(Exception, match="Provider reservation cannot be sent"):
        LedgeredGeneration(
            sessions,
            CancelAfterReserve(),
            execution(workspace_id, run_id, snapshot_id, step_id, asset_id),
            Provider(),
        ).generate(lease, node_key="researcher", messages=[{"role": "user", "content": "Question"}])

    with sessions() as db:
        provider_call = db.scalar(select(ResearchProviderCall))
        assert provider_call is not None and provider_call.status == "cancelled"


def test_real_expired_lease_is_abandoned_and_reclaimed(runtime_db) -> None:
    sessions, workspace_id, run_id, snapshot_id, step_id, asset_id = runtime_db
    adapter = SqlResearchLedgerAdapter(sessions, research_worker, worker_instance_id="worker-1")
    lease = adapter.claim_step(
        execution(workspace_id, run_id, snapshot_id, step_id, asset_id),
        step_key="researcher:branch-1",
        branch_key="branch-1",
    )
    with sessions() as db:
        attempt = db.get(ResearchStepAttempt, lease.attempt_id)
        assert attempt is not None
        attempt.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

    claimed = ResearchWorkProcessor(
        sessions,
        research_worker,
        worker_instance_id="worker-2",
    ).claim()

    assert claimed is not None and claimed.lease.attempt_number == 2
    with sessions() as db:
        expired = db.get(ResearchStepAttempt, lease.attempt_id)
        assert expired is not None and expired.status == "abandoned"
