from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_pdf_api.models import ResearchArtifact, ResearchReportEdit, ResearchRun, WorkspaceMembership
from ai_pdf_api.schemas.research_report_edit import SaveResearchReportEditRequest
from ai_pdf_api.services.research import ResearchError
from ai_pdf_api.services.research.research_views import verified_artifact_bytes

MAX_MARKDOWN_BYTES = 1_000_000


def _final_report(db: Session, run: ResearchRun) -> ResearchArtifact:
    if run.status != "completed":
        raise ResearchError("report_edit_not_ready", "The final report is not complete.", 409)
    artifact = db.scalar(
        select(ResearchArtifact).where(
            ResearchArtifact.workspace_id == run.workspace_id,
            ResearchArtifact.run_id == run.id,
            ResearchArtifact.artifact_kind == "final_report",
            ResearchArtifact.visibility == "user",
        ).execution_options(populate_existing=True).with_for_update(read=True).order_by(ResearchArtifact.created_at.desc(), ResearchArtifact.id.desc()).limit(1)
    )
    if artifact is None or artifact.content_type.split(";", 1)[0] != "text/markdown":
        raise ResearchError("report_edit_not_ready", "The final Markdown report is unavailable.", 409)
    try:
        verified_artifact_bytes(artifact).decode("utf-8")
    except Exception as error:
        raise ResearchError("research_artifact_unavailable", "The original report failed integrity validation.", 410) from error
    return artifact


def _response(artifact: ResearchArtifact, edit: ResearchReportEdit | None) -> dict[str, object]:
    return {
        "originalArtifactId": artifact.id,
        "originalSha256": artifact.content_sha256,
        "version": edit.version if edit else 0,
        "markdown": edit.markdown if edit else None,
        "actorUserId": edit.actor_user_id if edit else None,
        "updatedAt": edit.updated_at if edit else None,
        "verificationStatus": "unverified",
    }


def read_report_edit(db: Session, run: ResearchRun) -> dict[str, object]:
    artifact = _final_report(db, run)
    edit = db.get(ResearchReportEdit, run.id)
    if edit and (edit.base_artifact_id != artifact.id or edit.base_artifact_sha256 != artifact.content_sha256):
        raise ResearchError("report_edit_base_conflict", "The original report has changed.", 409)
    return _response(artifact, edit)


def save_report_edit(
    db: Session,
    *,
    workspace_id: str,
    run_id: str,
    user_id: str,
    payload: SaveResearchReportEditRequest,
) -> dict[str, object]:
    # The run lock serializes first-save creation and later version checks.
    with db.begin_nested():
        run = db.scalar(select(ResearchRun).where(
            ResearchRun.id == run_id, ResearchRun.workspace_id == workspace_id,
        ).with_for_update().execution_options(populate_existing=True))
        if run is None:
            raise ResearchError("research_run_not_found", "Research run not found.", 404)
        if run.created_by_user_id != user_id:
            raise ResearchError("research_permission_denied", "Only the run creator can edit this report.", 403)
        membership = db.scalar(select(WorkspaceMembership.id).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        ).with_for_update(read=True))
        if membership is None:
            raise ResearchError("research_permission_denied", "Workspace membership is required.", 403)
        artifact = _final_report(db, run)
        if (payload.originalArtifactId != artifact.id
                or payload.originalSha256 != artifact.content_sha256):
            raise ResearchError("report_edit_base_conflict", "The original report has changed. Copy your draft before reloading the run.", 409)
        edit = db.scalar(select(ResearchReportEdit).where(ResearchReportEdit.run_id == run.id)
                         .execution_options(populate_existing=True))
        if edit and (edit.base_artifact_id != artifact.id or edit.base_artifact_sha256 != artifact.content_sha256):
            raise ResearchError("report_edit_base_conflict", "The original report has changed.", 409)
        current_version = edit.version if edit else 0
        if payload.expectedVersion != current_version:
            raise ResearchError(
                "report_edit_version_conflict", "The report was edited in another session.", 409,
                details={"currentVersion": current_version},
            )
        markdown = payload.markdown
        if not markdown.strip() or len(markdown.encode("utf-8")) > MAX_MARKDOWN_BYTES:
            raise ResearchError("invalid_report_edit", "Report text must be non-empty and at most 1 MB.", 422)
        now = datetime.now(UTC)
        if edit is None:
            edit = ResearchReportEdit(
                run_id=run.id, workspace_id=workspace_id, version=1,
                actor_user_id=user_id, base_artifact_id=artifact.id,
                base_artifact_sha256=artifact.content_sha256,
                markdown=markdown, updated_at=now,
            )
            db.add(edit)
        else:
            edit.version += 1
            edit.actor_user_id = user_id
            edit.markdown = markdown
            edit.updated_at = now
        db.flush()
        result = _response(artifact, edit)
    db.commit()
    return result
