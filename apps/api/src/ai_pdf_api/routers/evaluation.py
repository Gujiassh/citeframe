from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ai_pdf_api.db.session import get_db
from ai_pdf_api.routers.deps import (
    WorkspaceAccess,
    WorkspaceRequest,
    require_user_id,
    require_workspace_member,
    require_workspace_owner,
)
from ai_pdf_api.schemas.evaluation import (
    EvaluationCaseListResponse,
    EvaluationCaseResponse,
    EvaluationRunListResponse,
    EvaluationRunResponse,
    EvaluationSuiteListResponse,
    EvaluationSuiteResponse,
)
from ai_pdf_api.services.evaluation import (
    EvaluationReadError,
    case_response,
    get_suite,
    list_cases,
    list_runs,
    list_suites,
    run_response,
)


router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["evaluation"])


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _read_error(error: EvaluationReadError) -> HTTPException:
    status_code = (
        status.HTTP_422_UNPROCESSABLE_CONTENT
        if error.code == "invalid_evaluation_cursor"
        else status.HTTP_404_NOT_FOUND
    )
    return HTTPException(status_code=status_code, detail=error.message)


@router.get("/evaluation-suites", response_model=EvaluationSuiteListResponse)
def read_evaluation_suites(
    workspace_id: str,
    response: Response,
    access: WorkspaceAccess = Depends(require_workspace_owner),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _no_store(response)
    return list_suites(db, workspace_id=workspace_id)


@router.get("/evaluation-suites/{suite_id}", response_model=EvaluationSuiteResponse)
def read_evaluation_suite(
    workspace_id: str,
    suite_id: str,
    response: Response,
    access: WorkspaceAccess = Depends(require_workspace_owner),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _no_store(response)
    try:
        return get_suite(db, workspace_id=workspace_id, suite_id=suite_id)
    except EvaluationReadError as error:
        raise _read_error(error) from error


def require_read_evaluations_access(
    workspace_id: str,
    suite_id: str | None = Query(default=None, alias='suiteId'),
    mode: Literal['quick', 'research'] | None = None,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> WorkspaceRequest[tuple[str | None, Literal['quick', 'research'] | None, str | None, int]]:
    access = require_workspace_member(workspace_id, user_id, db)
    access = require_workspace_owner.check(access)
    return WorkspaceRequest(access, (suite_id, mode, cursor, limit))


@router.get("/evaluations", response_model=EvaluationRunListResponse)
def read_evaluations(
    workspace_id: str,
    response: Response,
    workspace_request: WorkspaceRequest[tuple[str | None, Literal['quick', 'research'] | None, str | None, int]] = Depends(require_read_evaluations_access),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    suite_id, mode, cursor, limit = workspace_request.payload
    _no_store(response)
    try:
        return list_runs(
            db,
            workspace_id=workspace_id,
            suite_id=suite_id,
            mode=mode,
            cursor=cursor,
            limit=limit,
        )
    except EvaluationReadError as error:
        raise _read_error(error) from error


@router.get("/evaluations/{evaluation_run_id}", response_model=EvaluationRunResponse)
def read_evaluation(
    workspace_id: str,
    evaluation_run_id: str,
    response: Response,
    access: WorkspaceAccess = Depends(require_workspace_owner),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _no_store(response)
    try:
        return run_response(db, workspace_id=workspace_id, evaluation_run_id=evaluation_run_id)
    except EvaluationReadError as error:
        raise _read_error(error) from error


@router.get("/evaluations/{evaluation_run_id}/cases", response_model=EvaluationCaseListResponse)
def read_evaluation_cases(
    workspace_id: str,
    evaluation_run_id: str,
    response: Response,
    access: WorkspaceAccess = Depends(require_workspace_owner),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _no_store(response)
    try:
        return list_cases(db, workspace_id=workspace_id, evaluation_run_id=evaluation_run_id)
    except EvaluationReadError as error:
        raise _read_error(error) from error


@router.get(
    "/evaluations/{evaluation_run_id}/cases/{case_key}",
    response_model=EvaluationCaseResponse,
)
def read_evaluation_case(
    workspace_id: str,
    evaluation_run_id: str,
    case_key: str,
    response: Response,
    access: WorkspaceAccess = Depends(require_workspace_owner),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _no_store(response)
    try:
        return case_response(
            db,
            workspace_id=workspace_id,
            evaluation_run_id=evaluation_run_id,
            case_key=case_key,
        )
    except EvaluationReadError as error:
        raise _read_error(error) from error
