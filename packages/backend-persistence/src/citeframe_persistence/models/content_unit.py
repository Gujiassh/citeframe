from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from citeframe_persistence.base import Base


class ContentUnit(Base):
    __tablename__ = "content_units"
    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "representation_id",
            "source_locator_id",
            "unit_order",
            "index_version",
            name="uq_content_units_asset_representation_locator_order_version",
        ),
        Index(
            "ix_content_units_text_content_trgm_gist",
            "text_content",
            postgresql_using="gist",
            postgresql_ops={"text_content": "gist_trgm_ops(siglen=64)"},
        ),
        Index(
            "ix_content_units_text_content_fts",
            "search_vector",
            postgresql_using="gin",
        ).ddl_if(dialect="postgresql"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("assets.id"), index=True)
    representation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("asset_representations.id"), index=True
    )
    source_locator_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evidence_locators.id"), index=True
    )
    unit_kind: Mapped[str] = mapped_column(String(64), ForeignKey("content_unit_types.kind"), index=True)
    unit_order: Mapped[int] = mapped_column(Integer)
    text_content: Mapped[str] = mapped_column(Text)
    # PostgreSQL materializes this value through the Alembic generated-column migration.
    # The Text fallback keeps SQLite metadata fixtures usable without PostgreSQL functions.
    search_vector: Mapped[str | None] = mapped_column(
        Text().with_variant(TSVECTOR(), "postgresql"),
        nullable=True,
        server_default=FetchedValue(),
    )
    token_count: Mapped[int] = mapped_column(Integer)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    index_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
