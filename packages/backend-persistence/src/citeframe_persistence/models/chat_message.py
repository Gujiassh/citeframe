from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from citeframe_persistence.base import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_thread_created", "thread_id", "created_at"),
        Index("ix_chat_messages_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    thread_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_threads.id"), index=True)
    parent_message_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("chat_messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="completed")
    model_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
