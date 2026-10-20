"""Authenticated owner-private management through the shared instruction commands."""
from __future__ import annotations

import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from citeframe_contracts.memory import MemoryError
from ai_pdf_api.core.settings import settings
from ai_pdf_api.db.session import get_db
from ai_pdf_api.routers.deps import WorkspaceAccess, require_workspace_member
from ai_pdf_api.schemas.memory import (
    CorrectionReceipt, CorrectionRequest, CreateRequest, DeactivateRequest, DeleteReceipt, DeleteRequest,
    Identifier, InstructionSourceDto, MemoryErrorResponse, MemoryPage, MemoryResponse, MutationReceipt,
    OperationDto, SourceReadRequest,
)
from ai_pdf_api.services.memory_management import MemoryManagement

ERRORS = {
    "authentication_required": (401, "Authentication required.", False),
    "workspace_not_found": (404, "Workspace not found.", False),
    "memory_not_found": (404, "Memory not found.", False),
    "source_not_found": (404, "Source not found.", False),
    "operation_not_found": (404, "Operation not found.", False),
    "version_conflict": (409, "Memory version changed.", False),
    "terminal_memory": (409, "Memory cannot be changed by this operation.", False),
    "idempotency_conflict": (409, "Request identity conflicts with an existing operation.", False),
    "operation_in_progress": (409, "Operation has not settled. Poll using the original request ID.", True),
    "erased": (410, "Memory content has been erased.", False),
    "source_version_unavailable": (410, "Source version is unavailable.", False),
    "invalid_request": (422, "Invalid request.", False),
    "invalid_scope": (422, "Memory scope is unsupported.", False),
    "invalid_source_ref": (422, "Source reference is unsupported.", False),
    "invalid_cursor": (422, "Cursor is invalid or expired.", False),
    "unsupported_operation": (422, "Memory operation is unsupported.", False),
    "sensitive_content_unsupported": (422, "Submitted content contains an unsupported credential pattern.", False),
    "temporarily_unavailable": (503, "Memory service is temporarily unavailable. Retry using the original request identity.", True),
    "outcome_unknown": (503, "Operation outcome is unknown. Poll using the original request ID.", True),
}
UUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def validation_code(error, request):
    errors = error.errors()
    categories = set()
    for item in errors:
        location = item["loc"]
        if item["type"] == "missing":
            metadata_patch = (request.method == "PATCH" and location == ("body", "intent")
                              and isinstance(error.body, dict)
                              and bool({"pinned", "validUntil"} & error.body.keys()))
            if metadata_patch:
                categories.add("unsupported_operation")
                continue
            return "invalid_request"
        if item["type"] in ("model_attributes_type", "model_type", "list_type"):
            return "invalid_request"
        if (location[:2] == ("body", "scope") or location == ("query", "scope")) and item["type"] == "literal_error":
            categories.add("invalid_scope")
        elif (location[:2] == ("body", "sourceRefs") or location == ("body", "sourceRef", "span")
              or request.url.path.endswith("/sources/read") and location in (("body", "before"), ("body", "after"), ("body", "cursor"))):
            categories.add("invalid_source_ref")
        elif location == ("query", "cursor"):
            categories.add("invalid_cursor")
        elif request.method == "PATCH" and location in (("body", "intent"), ("body", "pinned"), ("body", "validUntil")):
            categories.add("unsupported_operation")
        else:
            return "invalid_request"
    return next((c for c in ("invalid_scope", "invalid_source_ref", "unsupported_operation", "invalid_cursor") if c in categories), "invalid_request")


async def error_request_id(request):
    request_id = None
    if getattr(request.state, "memory_dependency_passed", False):
        if request.method in ("POST", "PATCH", "DELETE") and not request.url.path.endswith("/sources/read"):
            try:
                body = await request.json()
                request_id = body.get("requestId") if isinstance(body, dict) else None
            except ValueError:
                pass
        elif "request_id" in request.path_params:
            request_id = request.path_params["request_id"]
    if not isinstance(request_id, str) or UUID_PATTERN.fullmatch(request_id) is None:
        request_id = None
    return request_id


def error_response(request_id, code, version=None):
    code = {"workspace_unavailable": "workspace_not_found", "membership_required": "workspace_not_found",
            "memory_unavailable": "memory_not_found", "source_unavailable": "source_version_unavailable"}.get(code, code)
    if code not in ERRORS:
        code = "temporarily_unavailable"
    status, message, retryable = ERRORS[code]
    detail = dict(code=code, message=message, retryable=retryable, requestId=request_id)
    if version is not None and code in ("version_conflict", "terminal_memory"):
        detail["currentVersion"] = version
    return JSONResponse(status_code=status, content=dict(detail=detail))


class PrivateMemoryRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request):
            code, version = None, None
            try:
                return await original(request)
            except RequestValidationError as error:
                code = validation_code(error, request)
            except HTTPException as error:
                code = "authentication_required" if error.status_code == 401 else "workspace_not_found"
            except MemoryError as error:
                code = str(error)
                version = getattr(error, "current_version", None)
            except SQLAlchemyError:
                code = "temporarily_unavailable"
            return error_response(await error_request_id(request), code, version)
        return handler


router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["memories"], route_class=PrivateMemoryRoute,
    responses={status: {"model": MemoryErrorResponse} for status in (401, 404, 409, 410, 422, 503)})


async def management(request: Request, access: WorkspaceAccess = Depends(require_workspace_member),
               db: Session = Depends(get_db)):
    request.state.memory_dependency_passed = True
    allowed_query = ({"status", "scope", "limit", "cursor"} if request.url.path.endswith("/memories")
                     else {"limit", "cursor"} if request.url.path.endswith("/revisions") else set())
    if set(request.query_params) - allowed_query:
        raise MemoryError("invalid_request")
    request_id = await error_request_id(request)
    return MemoryManagement(db.get_bind(), access.user_id, access.workspace_id, settings.api_internal_token,
                            lambda error: error_response(request_id, str(error), getattr(error, "current_version", None)))


Service = Annotated[MemoryManagement, Depends(management)]
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128, pattern=r"^[!-~]+$")]
Limit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[str | None, Query(max_length=4096)]


@router.get("/memories", response_model=MemoryPage)
def list_memories(service: Service,
                  status: Literal["active", "inactive", "superseded", "invalidated", "expired", "deleted", "all"] = "active",
                  scope: Literal["workspace"] = "workspace", limit: Limit = 30, cursor: Cursor = None):
    return service.list(status, limit, cursor)


@router.get("/memories/requests/{request_id}", response_model=OperationDto)
def request_receipt(request_id: Identifier, service: Service):
    return service.operation(request_id, by_request=True)


@router.get("/memories/operations/{operation_id}", response_model=OperationDto)
def operation_receipt(operation_id: Identifier, service: Service):
    return service.operation(operation_id)


@router.post("/sources/read", response_model=InstructionSourceDto)
def read_source(payload: SourceReadRequest, service: Service):
    return service.source(payload.sourceRef)


@router.get("/memories/{memory_id}", response_model=MemoryResponse)
def current_memory(memory_id: Identifier, service: Service):
    return service.current(memory_id)


@router.get("/memories/{memory_id}/revisions", response_model=MemoryPage)
def history(memory_id: Identifier, service: Service, limit: Limit = 30, cursor: Cursor = None):
    return service.history(memory_id, limit, cursor)


@router.patch("/memories/{memory_id}", response_model=MutationReceipt)
def deactivate(memory_id: Identifier, payload: DeactivateRequest, service: Service, key: Key):
    return service.mutate("deactivate", payload, key, memory_id)


@router.delete("/memories/{memory_id}", response_model=DeleteReceipt)
def delete(memory_id: Identifier, payload: DeleteRequest, service: Service, key: Key):
    return service.mutate("delete", payload, key, memory_id)


@router.post("/memories", response_model=MutationReceipt, status_code=201)
def create(payload: CreateRequest, service: Service, key: Key):
    return service.mutate("remember", payload, key)


@router.post("/memories/{memory_id}/corrections", response_model=CorrectionReceipt, status_code=201)
def correct(memory_id: Identifier, payload: CorrectionRequest, service: Service, key: Key):
    return service.mutate("correct", payload, key, memory_id)
