"""Transaction-bound workspace and member guards for private management."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from citeframe_contracts.memory import AccessContext, AccessDenied
from citeframe_persistence.models import Workspace, WorkspaceMembership


def require_private_management(context: AccessContext, owner_user_id: str) -> None:
    if (context.purpose != "management" or context.output_audience != "private"
            or context.actor_user_id != owner_user_id):
        raise AccessDenied("private_management_only")


class WorkspaceAccess:
    def __init__(self, session: Session):
        self.session = session

    def authorize(self, context: AccessContext, *, owner_user_id: str) -> None:
        require_private_management(context, owner_user_id)
        workspace = self.session.scalar(select(Workspace).where(
            Workspace.id == context.workspace_id).with_for_update())
        if workspace is None or workspace.archived_at is not None:
            raise AccessDenied("workspace_unavailable")
        member = self.session.scalar(select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == context.workspace_id,
            WorkspaceMembership.user_id == context.actor_user_id).with_for_update())
        if member is None or member.role not in ("owner", "member"):
            raise AccessDenied("membership_required")
