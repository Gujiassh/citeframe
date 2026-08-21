from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from citeframe_persistence.base import Base


class MessageRetrievalScope(Base):
    __tablename__ = "message_retrieval_scopes"
    __table_args__ = (
        CheckConstraint(
            "scope_mode IN ('all_ready', 'selected')",
            name="ck_message_retrieval_scopes_scope_mode",
        ),
    )

    message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_messages.id", ondelete="CASCADE"), primary_key=True
    )
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    scope_mode: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class MessageRetrievalScopeAsset(Base):
    __tablename__ = "message_retrieval_scope_assets"
    __table_args__ = (
        UniqueConstraint("message_id", "asset_order", name="uq_message_retrieval_scope_assets_order"),
    )

    message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("message_retrieval_scopes.message_id", ondelete="CASCADE"), primary_key=True
    )
    asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("assets.id"), primary_key=True)
    asset_order: Mapped[int] = mapped_column(Integer)
    asset_kind_snapshot: Mapped[str] = mapped_column(String(64))
    asset_title_snapshot: Mapped[str] = mapped_column(String(255))
