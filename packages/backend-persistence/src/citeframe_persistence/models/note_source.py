from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from citeframe_persistence.base import Base


class NoteSource(Base):
    __tablename__ = "note_sources"
    __table_args__ = (
        UniqueConstraint("note_id", "message_citation_id", name="uq_note_sources_note_citation"),
        UniqueConstraint("note_id", "source_order", name="uq_note_sources_note_order"),
        CheckConstraint("source_order >= 0", name="ck_note_sources_source_order"),
        Index("ix_note_sources_note_order", "note_id", "source_order"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    note_id: Mapped[str] = mapped_column(String(36), ForeignKey("notes.id", ondelete="CASCADE"), index=True)
    source_order: Mapped[int] = mapped_column(Integer)
    message_citation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("message_citations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    evidence_locator_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evidence_locators.id"), index=True
    )
    asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("assets.id"), index=True)
    asset_kind_snapshot: Mapped[str] = mapped_column(String(64))
    asset_title_snapshot: Mapped[str] = mapped_column(String(255))
    excerpt_snapshot: Mapped[str] = mapped_column(Text)
    processing_generation_snapshot: Mapped[int] = mapped_column(Integer)
    representation_id_snapshot: Mapped[str] = mapped_column(String(36))
    parser_version_snapshot: Mapped[str] = mapped_column(String(64))
    index_version_snapshot: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
