from __future__ import annotations

from collections.abc import Callable, Coroutine, Iterator
import time
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from ai_pdf_api.core.research_observability import observe_research_sse
from ai_pdf_api.db.session import SessionLocal, get_db
from ai_pdf_api.routers.deps import get_accessible_workspace, require_user_id
from ai_pdf_api.schemas.research import (
    CancelResearchRunRequest,
    CancelResearchRunResponse,
    ConflictDecisionRequest,
    ConflictDecisionResponse,
    CreateResearchRunRequest,
    CreateResearchRunResponse,
    PlanDecisionRequest,
    PlanDecisionResponse,
    ResearchArtifactDetailResponse,
    ResearchArtifactListResponse,
    ResearchRunDetailResponse,
    ResearchRunListResponse,
    RetryResearchStepRequest,
    RetryResearchStepResponse,
)
from ai_pdf_api.services.research import (
    ResearchError,
    cancel_research_run,
    create_research_run,
    decide_conflict,
    decide_plan,
    get_artifact,
    get_artifact_detail,
    get_research_run,
    list_artifacts,
    list_events_after,
    list_research_runs,
    retry_research_step,
    serialize_sse_event,
)
from ai_pdf_api.services.research_views import run_detail, verified_artifact_bytes


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    error: dict[str, object] = {
        "code": code,
        "message": message,
        "requestId": request_id or str(uuid4()),
        "retryable": status_code == 503,
    }
    if details:
        error["details"] = details
    return JSONResponse(status_code=status_code, content={"error": error})


class ResearchAPIRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except ResearchError as error:
                return _error_response(
                    status_code=error.status_code,
                    code=error.code,
                    message=error.message,
                    details=error.details,
                    request_id=error.request_id,
                )
            except RequestValidationError as error:
                first = error.errors()[0] if error.errors() else {}
                location = first.get("loc", ())
                field = ".".join(str(item) for item in location if item not in {"body", "query", "header"})
                return _error_response(
                    status_code=422,
                    code="invalid_research_request",
                    message="Research request validation failed.",
                    details={"field": field} if field else None,
                )
            except HTTPException as error:
                mapping = {
                    401: ("auth_required", "Authentication is required."),
                    403: ("research_permission_denied", "Research action is not permitted."),
                    404: ("workspace_not_found", "Workspace not found."),
                }
                code, message = mapping.get(error.status_code, ("invalid_research_request", str(error.detail)))
                return _error_response(status_code=error.status_code, code=code, message=message)

        return handler


router = APIRouter(
    prefix="/v1/workspaces/{workspace_id}/research-runs",
    tags=["research"],
    route_class=ResearchAPIRoute,
)

RESEARCH_EVENT_SESSION_FACTORY: Callable[[], Session] = SessionLocal
RESEARCH_EVENT_POLL_SECONDS = 1.0
RESEARCH_EVENT_KEEPALIVE_POLLS = 15
RESEARCH_EVENT_MAX_POLLS: int | None = None
TERMINAL_RESEARCH_STATUSES = {"completed", "failed", "cancelled"}


def iter_research_event_tail(
    *,
    workspace_id: str,
    run_id: str,
    user_id: str,
    cursor: int,
    initial_frames: list[str],
    initial_status: str,
    session_factory: Callable[[], Session],
    sleep: Callable[[float], None] = time.sleep,
    poll_seconds: float = RESEARCH_EVENT_POLL_SECONDS,
    keepalive_polls: int = RESEARCH_EVENT_KEEPALIVE_POLLS,
    max_polls: int | None = None,
) -> Iterator[str]:
    yield from initial_frames
    if initial_status in TERMINAL_RESEARCH_STATUSES:
        return
    poll_count = 0
    while max_polls is None or poll_count < max_polls:
        sleep(poll_seconds)
        poll_count += 1
        with session_factory() as poll_db:
            try:
                get_accessible_workspace(poll_db, user_id, workspace_id)
                run = get_research_run(poll_db, workspace_id, run_id)
            except (HTTPException, ResearchError):
                return
            try:
                events = list_events_after(poll_db, run, cursor)
            except ResearchError as error:
                if error.code == "research_event_history_unavailable":
                    observe_research_sse("history_unavailable")
                raise
            for event in events:
                cursor = event.seq
                yield serialize_sse_event(event)
            if run.status in TERMINAL_RESEARCH_STATUSES:
                return
        if not events and poll_count % keepalive_polls == 0:
            yield ": keepalive\n\n"


@router.post("", response_model=CreateResearchRunResponse)
def create_run(
    workspace_id: str,
    payload: CreateResearchRunRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    get_accessible_workspace(db, user_id, workspace_id)
    status_code, result, replayed = create_research_run(
        db,
        workspace_id=workspace_id,
        actor_user_id=user_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    response.status_code = status_code
    response.headers["Location"] = f"/v1/workspaces/{workspace_id}/research-runs/{result['run']['id']}"
    if replayed:
        response.headers["Idempotency-Replayed"] = "true"
    return result


@router.get("", response_model=ResearchRunListResponse)
def list_runs(
    workspace_id: str,
    status_filter: str | None = Query(default=None, alias="status"),
    created_by: Literal["me", "all"] = Query(default="all", alias="createdBy"),
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    get_accessible_workspace(db, user_id, workspace_id)
    return list_research_runs(
        db,
        workspace_id=workspace_id,
        actor_user_id=user_id,
        status_filter=status_filter,
        created_by=created_by,
        cursor=cursor,
        limit=limit,
    )


@router.get("/{run_id}", response_model=ResearchRunDetailResponse)
def read_run(
    workspace_id: str,
    run_id: str,
    response: Response,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    get_accessible_workspace(db, user_id, workspace_id)
    run = get_research_run(db, workspace_id, run_id)
    response.headers["ETag"] = f'"run-{run.id}-v{run.state_version}"'
    return {"run": run_detail(db, run)}


@router.post("/{run_id}/cancel", response_model=CancelResearchRunResponse)
def cancel_run(
    workspace_id: str,
    run_id: str,
    payload: CancelResearchRunRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _workspace, role = get_accessible_workspace(db, user_id, workspace_id)
    status_code, result, replayed = cancel_research_run(
        db,
        workspace_id=workspace_id,
        actor_user_id=user_id,
        actor_role=role,
        run_id=run_id,
        expected_state_version=payload.expected_state_version,
        reason_code=payload.reason_code,
        idempotency_key=idempotency_key,
    )
    response.status_code = status_code
    if replayed:
        response.headers["Idempotency-Replayed"] = "true"
    return result


@router.post("/{run_id}/plan-decisions/{decision_id}", response_model=PlanDecisionResponse)
def submit_plan_decision(
    workspace_id: str,
    run_id: str,
    decision_id: str,
    payload: PlanDecisionRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    get_accessible_workspace(db, user_id, workspace_id)
    status_code, result, replayed = decide_plan(
        db,
        workspace_id=workspace_id,
        actor_user_id=user_id,
        run_id=run_id,
        decision_id=decision_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    response.status_code = status_code
    if replayed:
        response.headers["Idempotency-Replayed"] = "true"
    return result


@router.post("/{run_id}/conflict-decisions/{decision_id}", response_model=ConflictDecisionResponse)
def submit_conflict_decision(
    workspace_id: str,
    run_id: str,
    decision_id: str,
    payload: ConflictDecisionRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    get_accessible_workspace(db, user_id, workspace_id)
    status_code, result, replayed = decide_conflict(
        db,
        workspace_id=workspace_id,
        actor_user_id=user_id,
        run_id=run_id,
        decision_id=decision_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    response.status_code = status_code
    if replayed:
        response.headers["Idempotency-Replayed"] = "true"
    return result


@router.post("/{run_id}/steps/{step_id}/retry", response_model=RetryResearchStepResponse)
def retry_step(
    workspace_id: str,
    run_id: str,
    step_id: str,
    payload: RetryResearchStepRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    get_accessible_workspace(db, user_id, workspace_id)
    status_code, result, replayed = retry_research_step(
        db,
        workspace_id=workspace_id,
        actor_user_id=user_id,
        run_id=run_id,
        step_id=step_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    response.status_code = status_code
    if replayed:
        response.headers["Idempotency-Replayed"] = "true"
    return result


@router.get("/{run_id}/artifacts", response_model=ResearchArtifactListResponse)
def read_artifacts(
    workspace_id: str,
    run_id: str,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    get_accessible_workspace(db, user_id, workspace_id)
    return list_artifacts(db, workspace_id, run_id)


@router.get("/{run_id}/artifacts/{artifact_id}", response_model=ResearchArtifactDetailResponse)
def read_artifact(
    workspace_id: str,
    run_id: str,
    artifact_id: str,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    get_accessible_workspace(db, user_id, workspace_id)
    return get_artifact_detail(db, workspace_id, run_id, artifact_id)


@router.get("/{run_id}/artifacts/{artifact_id}/content")
def read_artifact_content(
    workspace_id: str,
    run_id: str,
    artifact_id: str,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> Response:
    get_accessible_workspace(db, user_id, workspace_id)
    artifact = get_artifact(db, workspace_id, run_id, artifact_id)
    try:
        content = verified_artifact_bytes(artifact)
    except Exception as error:
        raise ResearchError("research_artifact_unavailable", "Research artifact content is unavailable.", 410) from error
    return Response(
        content=content,
        media_type=None,
        headers={
            "Content-Type": artifact.content_type,
            "Content-Length": str(artifact.byte_size),
            "ETag": artifact.content_sha256,
            "Cache-Control": "private, immutable",
        },
    )


@router.get("/{run_id}/events")
def stream_events(
    workspace_id: str,
    run_id: str,
    accept: str | None = Header(default=None, alias="Accept"),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    user_id: str = Depends(require_user_id),
) -> StreamingResponse:
    if accept is not None and "text/event-stream" not in accept:
        raise ResearchError("invalid_research_request", "Accept must allow text/event-stream.", 406)
    if last_event_id is None:
        cursor = 0
    elif not last_event_id.isdecimal() or len(last_event_id) > 19:
        raise ResearchError("invalid_event_cursor", "Last-Event-ID must be a non-negative decimal integer.", 400)
    else:
        cursor = int(last_event_id)
        if cursor > 9_223_372_036_854_775_807:
            raise ResearchError("invalid_event_cursor", "Last-Event-ID is outside the supported range.", 400)
        observe_research_sse("reconnect")
    with RESEARCH_EVENT_SESSION_FACTORY() as initial_db:
        get_accessible_workspace(initial_db, user_id, workspace_id)
        run = get_research_run(initial_db, workspace_id, run_id)
        try:
            events = list_events_after(initial_db, run, cursor)
        except ResearchError as error:
            if error.code == "research_event_history_unavailable":
                observe_research_sse("history_unavailable")
            raise
        initial_frames = [serialize_sse_event(event) for event in events]
        initial_status = run.status
        if events:
            cursor = events[-1].seq

    return StreamingResponse(
        iter_research_event_tail(
            workspace_id=workspace_id,
            run_id=run_id,
            user_id=user_id,
            cursor=cursor,
            initial_frames=initial_frames,
            initial_status=initial_status,
            session_factory=RESEARCH_EVENT_SESSION_FACTORY,
            poll_seconds=RESEARCH_EVENT_POLL_SECONDS,
            keepalive_polls=RESEARCH_EVENT_KEEPALIVE_POLLS,
            max_polls=RESEARCH_EVENT_MAX_POLLS,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
