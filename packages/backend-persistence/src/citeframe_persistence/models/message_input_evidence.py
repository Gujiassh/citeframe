from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from citeframe_persistence.base import Base


class MessageInputEvidence(Base):
    __tablename__ = "message_input_evidence"
    __table_args__ = (
        UniqueConstraint("message_id", "target_order", name="uq_message_input_evidence_order"),
        UniqueConstraint("evidence_locator_id", name="uq_message_input_evidence_locator"),
        CheckConstraint("target_order >= 0", name="ck_message_input_evidence_target_order"),
        Index("ix_message_input_evidence_message_order", "message_id", "target_order"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_messages.id", ondelete="CASCADE"), index=True
    )
    target_order: Mapped[int] = mapped_column(Integer)
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
