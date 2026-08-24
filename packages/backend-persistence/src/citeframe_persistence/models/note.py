from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from citeframe_persistence.base import Base


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (Index("ix_notes_workspace_updated", "workspace_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    updated_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body_md: Mapped[str] = mapped_column(Text)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
