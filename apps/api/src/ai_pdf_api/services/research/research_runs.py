"""Research run lifecycle: plan snapshots, revisions, create/get/list/cancel."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

from ai_pdf_api.core.settings import settings
from ai_pdf_api.models import (
    Asset,
    PromptVersion,
    ResearchBudgetLedger,
    ResearchPlanRevision,
    ResearchPlanRevisionAsset,
    ResearchRun,
    ResearchStep,
    WorkflowPromptBinding,
    Workspace,
)
from ai_pdf_api.schemas.research import CreateResearchRunRequest
from ai_pdf_api.services.research.research_agent_io_registry import (
    registry_snapshot_fields,
    require_current_production_registry,
)
from ai_pdf_api.services.research.research_constants import (
    BUDGET_POLICY_VERSION,
    DATA_BOUNDARY_POLICY,
    PRICING_VERSION,
    RETRY_POLICY_VERSION,
    TERMINAL_RUN_STATUSES,
)
from ai_pdf_api.services.research.research_events import append_research_event
from ai_pdf_api.services.research.research_idempotency import (
    ResearchError,
    _idempotent_mutation,
    canonical_json,
    canonical_sha256,
    validate_idempotency_key,
)
from ai_pdf_api.services.research.research_versions_service import (
    _profile_fingerprint,
    ensure_research_versions,
)
from ai_pdf_api.services.research.research_views import iso, run_detail, run_summary
from citeframe_research_persistence import membership as _membership
from citeframe_research_persistence.cancellation import cancel_research_run_transition
from citeframe_research_persistence.snapshot_integrity import (
    build_plan_snapshot_hash_payload,
)
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session

finalize_cancel_if_idle = _membership.finalize_cancel_if_idle


def _resolve_assets(db: Session, workspace_id: str, scope: object) -> list[Asset]:
    mode = scope.mode
    if mode == "all_ready":
        assets = list(
            db.scalars(
                select(Asset)
                .where(
                    Asset.workspace_id == workspace_id,
                    Asset.deleted_at.is_(None),
                    Asset.status == "ready",
                )
                .order_by(Asset.created_at, Asset.id)
            ).all()
        )
    else:
        requested_ids = list(scope.asset_ids)
        by_id = {
            asset.id: asset
            for asset in db.scalars(
                select(Asset).where(
                    Asset.workspace_id == workspace_id,
                    Asset.id.in_(requested_ids),
                    Asset.deleted_at.is_(None),
                    Asset.status == "ready",
                )
            ).all()
        }
        assets = [by_id[asset_id] for asset_id in requested_ids if asset_id in by_id]
        if len(assets) != len(requested_ids):
            raise ResearchError(
                "invalid_asset_scope",
                "Every selected Asset must be ready in this Workspace.",
                422,
            )
    if not assets:
        raise ResearchError(
            "invalid_asset_scope", "Research requires at least one ready Asset.", 422
        )
    return assets


def _add_revision(
    db: Session,
    *,
    run: ResearchRun,
    actor_user_id: str,
    question: str,
    scope: object,
    revision_number: int,
    supersedes_revision_id: str | None,
    now: datetime,
) -> tuple[ResearchPlanRevision, ResearchStep]:
    workflow, planner_prompt = ensure_research_versions(db, now)
    if workflow.availability != "active" or planner_prompt.availability != "active":
        raise ResearchError(
            "research_version_unavailable", "Research versions are not active.", 422
        )
    assets = _resolve_assets(db, run.workspace_id, scope)
    workspace = db.get(Workspace, run.workspace_id)
    if workspace is None:
        raise ResearchError("workspace_not_found", "Workspace not found.", 404)
    bindings = list(
        db.execute(
            select(WorkflowPromptBinding, PromptVersion)
            .join(
                PromptVersion,
                PromptVersion.id == WorkflowPromptBinding.prompt_version_id,
            )
            .where(WorkflowPromptBinding.workflow_version_id == workflow.id)
            .order_by(WorkflowPromptBinding.node_key)
        ).all()
    )
    from ai_pdf_api.services.workspace_models import resolve_workspace_models
    models = resolve_workspace_models(db, run.workspace_id)
    revision = ResearchPlanRevision(
        workspace_id=run.workspace_id,
        run_id=run.id,
        revision_number=revision_number,
        supersedes_revision_id=supersedes_revision_id,
        created_by_user_id=actor_user_id,
        question_text=question.strip(),
        scope_mode=scope.mode,
        proposed_workflow_version_id=workflow.id,
        planner_prompt_version_id=planner_prompt.id,
        proposed_generation_provider=models.generation.provider,
        proposed_generation_model=models.generation.model,
        proposed_provider_config_fingerprint=_profile_fingerprint(
            retrieval_top_k=workspace.retrieval_top_k, models=models
        ),
        proposed_pricing_version=PRICING_VERSION,
        proposed_data_boundary_policy_version=DATA_BOUNDARY_POLICY,
        proposed_embedding_provider=models.embedding.provider,
        proposed_embedding_model=models.embedding.model,
        proposed_embedding_version=models.embedding.version,
        proposed_retrieval_strategy=settings.retrieval_strategy,
        proposed_retrieval_top_k=workspace.retrieval_top_k,
        planning_max_provider_calls=2,
        planning_max_input_tokens=32_000,
        planning_max_output_tokens=8_000,
        planning_max_cost_microunits=500_000,
        planning_cost_currency=run.cost_currency,
        planning_max_step_attempts=3,
        planning_budget_policy_version=BUDGET_POLICY_VERSION,
        planning_retry_policy_version=RETRY_POLICY_VERSION,
        planning_max_step_timeout_seconds=300,
        planning_max_provider_timeout_seconds=120,
        proposed_max_parallel_researchers=3,
        proposed_max_step_attempts=3,
        proposed_max_provider_calls=32,
        proposed_max_tool_calls=64,
        proposed_max_input_tokens=250_000,
        proposed_max_output_tokens=64_000,
        proposed_max_cost_microunits=5_000_000,
        proposed_cost_currency=run.cost_currency,
        proposed_budget_policy_version=BUDGET_POLICY_VERSION,
        proposed_retry_policy_version=RETRY_POLICY_VERSION,
        proposed_max_run_timeout_seconds=1800,
        proposed_max_step_timeout_seconds=300,
        proposed_max_provider_timeout_seconds=120,
        agent_result_schema_version=registry_snapshot_fields(
            require_current_production_registry()
        )["agentResultSchemaVersion"],
        context_policy_version=registry_snapshot_fields(
            require_current_production_registry()
        )["contextPolicyVersion"],
        compact_policy_version=registry_snapshot_fields(
            require_current_production_registry()
        )["compactPolicyVersion"],
        planning_snapshot_sha256="0" * 64,
        created_at=now,
    )
    revision.planning_snapshot_sha256 = canonical_sha256(
        build_plan_snapshot_hash_payload(revision, assets, bindings)
    )
    db.add(revision)
    db.flush()
    for order, asset in enumerate(assets):
        db.add(
            ResearchPlanRevisionAsset(
                plan_revision_id=revision.id,
                workspace_id=run.workspace_id,
                asset_id=asset.id,
                asset_order=order,
                asset_kind_snapshot=asset.asset_kind,
                asset_title_snapshot=asset.title,
                processing_generation_snapshot=asset.current_processing_generation,
                index_version_snapshot=asset.current_index_version,
            )
        )
    db.add(
        ResearchBudgetLedger(
            workspace_id=run.workspace_id,
            run_id=run.id,
            plan_revision_id=revision.id,
            execution_snapshot_id=None,
            currency=run.cost_currency,
            updated_at=now,
        )
    )
    step = ResearchStep(
        workspace_id=run.workspace_id,
        run_id=run.id,
        plan_revision_id=revision.id,
        execution_snapshot_id=None,
        step_key=f"revision-{revision_number}:planner",
        step_kind="planner",
        branch_key=None,
        status="queued",
        prompt_version_id=planner_prompt.id,
        max_attempts_snapshot=revision.planning_max_step_attempts,
        input_sha256=revision.planning_snapshot_sha256,
        queued_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(step)
    db.flush()
    run.current_plan_revision_id = revision.id
    return revision, step


def create_research_run(
    db: Session,
    *,
    workspace_id: str,
    actor_user_id: str,
    payload: CreateResearchRunRequest,
    idempotency_key: str,
) -> tuple[int, dict[str, object], bool]:
    key = validate_idempotency_key(idempotency_key)
    body = payload.model_dump(mode="json", by_alias=True)
    path = f"/v1/workspaces/{workspace_id}/research-runs"

    def execute() -> tuple[int, dict[str, object], str]:
        if db.get_bind().dialect.name == "postgresql":
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:scope))"),
                {"scope": f"research-create:{workspace_id}"},
            )
        active = tuple(TERMINAL_RUN_STATUSES)
        user_count = (
            db.scalar(
                select(func.count())
                .select_from(ResearchRun)
                .where(
                    ResearchRun.workspace_id == workspace_id,
                    ResearchRun.created_by_user_id == actor_user_id,
                    ResearchRun.status.not_in(active),
                )
            )
            or 0
        )
        workspace_count = (
            db.scalar(
                select(func.count())
                .select_from(ResearchRun)
                .where(
                    ResearchRun.workspace_id == workspace_id,
                    ResearchRun.status.not_in(active),
                )
            )
            or 0
        )
        if user_count >= 2 or workspace_count >= 10:
            raise ResearchError(
                "research_concurrency_limit",
                "The active Research run limit has been reached.",
                429,
            )
        now = datetime.now(UTC)
        run = ResearchRun(
            workspace_id=workspace_id,
            created_by_user_id=actor_user_id,
            status="planning",
            state_version=1,
            next_event_seq=1,
            cost_currency="USD",
            created_at=now,
            updated_at=now,
        )
        db.add(run)
        db.flush()
        append_research_event(
            db,
            run,
            event_type="run_created",
            dedupe_key="run-created",
            data={
                "status": "planning",
                "createdByUserId": actor_user_id,
                "runStateVersion": 1,
            },
            now=now,
        )
        _revision, planner_step = _add_revision(
            db,
            run=run,
            actor_user_id=actor_user_id,
            question=payload.question,
            scope=payload.asset_scope,
            revision_number=1,
            supersedes_revision_id=None,
            now=now,
        )
        run.state_version += 1
        run.updated_at = now
        append_research_event(
            db,
            run,
            event_type="step_queued",
            dedupe_key=f"step-queued:{planner_step.id}:0",
            step_id=planner_step.id,
            data={
                "stepId": planner_step.id,
                "stepKind": planner_step.step_kind,
                "branchKey": None,
                "attemptNumber": 0,
                "stepStateVersion": planner_step.state_version,
                "runStateVersion": run.state_version,
            },
            now=now,
        )
        db.flush()
        return 201, {"run": run_detail(db, run)}, run.id

    return _idempotent_mutation(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        operation="create_run",
        resource_path=path,
        key=key,
        request_body=body,
        execute=execute,
    )


def get_research_run(db: Session, workspace_id: str, run_id: str) -> ResearchRun:
    run = db.scalar(
        select(ResearchRun).where(
            ResearchRun.id == run_id, ResearchRun.workspace_id == workspace_id
        )
    )
    if run is None:
        raise ResearchError("research_run_not_found", "Research run not found.", 404)
    return run


def _get_research_run_for_update(
    db: Session, workspace_id: str, run_id: str
) -> ResearchRun:
    from citeframe_research_persistence.locks import lock_run

    run = lock_run(db, run_id, workspace_id=workspace_id)
    if run is None:
        raise ResearchError("research_run_not_found", "Research run not found.", 404)
    return run


def _encode_cursor(run: ResearchRun) -> str:
    payload = canonical_json({"createdAt": iso(run.created_at), "id": run.id})
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        payload = json.loads(
            base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        )
        created_at = datetime.fromisoformat(payload["createdAt"])
        return created_at, str(payload["id"])
    except Exception as error:
        raise ResearchError(
            "invalid_cursor", "Research cursor is invalid.", 400
        ) from error


def list_research_runs(
    db: Session,
    *,
    workspace_id: str,
    actor_user_id: str,
    status_filter: str | None,
    created_by: str,
    cursor: str | None,
    limit: int,
) -> dict[str, object]:
    query = select(ResearchRun).where(
        ResearchRun.workspace_id == workspace_id, ResearchRun.archived_at.is_(None)
    )
    if status_filter:
        query = query.where(ResearchRun.status == status_filter)
    if created_by == "me":
        query = query.where(ResearchRun.created_by_user_id == actor_user_id)
    if cursor:
        created_at, run_id = _decode_cursor(cursor)
        query = query.where(
            or_(
                ResearchRun.created_at < created_at,
                and_(ResearchRun.created_at == created_at, ResearchRun.id < run_id),
            )
        )
    runs = list(
        db.scalars(
            query.order_by(ResearchRun.created_at.desc(), ResearchRun.id.desc()).limit(
                limit + 1
            )
        ).all()
    )
    has_more = len(runs) > limit
    runs = runs[:limit]
    return {
        "items": [run_summary(db, run) for run in runs],
        "nextCursor": _encode_cursor(runs[-1]) if has_more and runs else None,
    }


def cancel_research_run(
    db: Session,
    *,
    workspace_id: str,
    actor_user_id: str,
    actor_role: str,
    run_id: str,
    expected_state_version: int,
    reason_code: str,
    idempotency_key: str,
) -> tuple[int, dict[str, object], bool]:
    key = validate_idempotency_key(idempotency_key)
    body = {"expectedStateVersion": expected_state_version, "reasonCode": reason_code}
    path = f"/v1/workspaces/{workspace_id}/research-runs/{run_id}/cancel"

    def execute() -> tuple[int, dict[str, object], str]:
        run = cancel_research_run_transition(
            db,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            run_id=run_id,
            expected_state_version=expected_state_version,
            reason_code=reason_code,
            now=datetime.now(UTC),
        )
        return 202, {"run": run_detail(db, run)}, run.id

    return _idempotent_mutation(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        operation="cancel_run",
        resource_path=path,
        key=key,
        request_body=body,
        execute=execute,
    )
