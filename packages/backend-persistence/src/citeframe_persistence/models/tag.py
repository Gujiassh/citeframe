from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from citeframe_persistence.base import Base


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_tags_workspace_slug"),
        Index("ix_tags_workspace_name", "workspace_id", "name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(128))
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
