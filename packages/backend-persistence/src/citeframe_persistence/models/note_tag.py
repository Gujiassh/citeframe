from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from citeframe_persistence.base import Base


class NoteTag(Base):
    __tablename__ = "note_tags"
    __table_args__ = (UniqueConstraint("note_id", "tag_id", name="uq_note_tags_note_tag"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    note_id: Mapped[str] = mapped_column(String(36), ForeignKey("notes.id", ondelete="CASCADE"), index=True)
    tag_id: Mapped[str] = mapped_column(String(36), ForeignKey("tags.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
