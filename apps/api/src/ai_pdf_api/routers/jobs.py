from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_pdf_api.db.session import get_db
from ai_pdf_api.models import IngestionJob
from ai_pdf_api.routers.deps import WorkspaceAccess, require_workspace_member
from ai_pdf_api.routers.assets import to_job_status
from ai_pdf_api.schemas.job import JobDetailResponse

router = APIRouter(prefix="/v1/workspaces/{workspace_id}/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobDetailResponse)
def get_job(
    workspace_id: str,
    job_id: str,
    access: WorkspaceAccess = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> JobDetailResponse:
    job = db.scalar(
        select(IngestionJob).where(
            IngestionJob.id == job_id,
            IngestionJob.workspace_id == workspace_id,
        ),
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return JobDetailResponse(job=to_job_status(job))
