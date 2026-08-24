from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from citeframe_persistence.base import Base


class AssetRepresentation(Base):
    __tablename__ = "asset_representations"
    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "representation_kind",
            "processing_generation",
            name="uq_asset_representations_asset_kind_generation",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("assets.id"), index=True)
    representation_kind: Mapped[str] = mapped_column(
        String(64), ForeignKey("representation_types.kind"), index=True
    )
    processing_generation: Mapped[int] = mapped_column(Integer)
    generator_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generator_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    generator_version: Mapped[str] = mapped_column(String(64))
    object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
