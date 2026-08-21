from datetime import UTC, datetime
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, literal_column, text
from sqlalchemy.orm import Mapped, mapped_column

from citeframe_persistence.base import Base


class ContentUnitEmbedding(Base):
    __tablename__ = "content_unit_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "content_unit_id",
            "embedding_space",
            "provider",
            "model",
            "version",
            name="uq_content_unit_embeddings_unit_space_model_version",
        ),
        Index(
            "ix_content_unit_embeddings_current_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"ef_construction": 512},
            postgresql_where=text("is_current IS TRUE"),
        ),
        CheckConstraint("processing_generation >= 0", name="ck_content_unit_embeddings_processing_generation"),
        CheckConstraint("index_version >= 0", name="ck_content_unit_embeddings_index_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("assets.id"), index=True)
    content_unit_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("content_units.id", ondelete="CASCADE"), index=True
    )
    processing_generation: Mapped[int] = mapped_column(Integer)
    index_version: Mapped[int] = mapped_column(Integer)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"), index=True)
    embedding_space: Mapped[str] = mapped_column(
        String(64), ForeignKey("embedding_spaces.kind"), index=True
    )
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    dimensions: Mapped[int] = mapped_column(Integer)
    version: Mapped[str] = mapped_column(String(64))
    embedding: Mapped[list[float]] = mapped_column(Vector(1024).with_variant(JSON(), "sqlite"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


_binary_hnsw_index = Index(
    "ix_content_unit_embeddings_current_embedding_binary_hnsw",
    literal_column("(binary_quantize(embedding)::bit(1024))").label(
        "embedding_binary"
    ),
    postgresql_using="hnsw",
    postgresql_ops={"embedding_binary": "bit_hamming_ops"},
    postgresql_with={"ef_construction": 64},
    postgresql_where=text("is_current IS TRUE"),
).ddl_if(dialect="postgresql")
ContentUnitEmbedding.__table__.append_constraint(_binary_hnsw_index)
