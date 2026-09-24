from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from citeframe_persistence.base import Base


class WorkspaceModelConfig(Base):
    __tablename__ = "workspace_model_configs"
    __table_args__ = (
        CheckConstraint("capability IN ('generation', 'embedding')", name="ck_model_config_capability"),
        CheckConstraint("mode IN ('inherit', 'override')", name="ck_model_config_mode"),
        CheckConstraint("revision >= 1", name="ck_model_config_revision"),
    )

    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), primary_key=True)
    capability: Mapped[str] = mapped_column(String(16), primary_key=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    protocol: Mapped[str | None] = mapped_column(String(40), nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
