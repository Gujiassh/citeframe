from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from citeframe_persistence.base import Base

DOCUMENT_BLOCK_KINDS = (
    "heading",
    "paragraph",
    "list_item",
    "code_block",
    "quote",
    "table",
)
DOCUMENT_NORMALIZATION_VERSION = "document-normalization-v1"
DOCUMENT_PARSER_VERSION = "document-parser-v1"
DOCUMENT_FORMAT_MARKDOWN = "markdown"


class DocumentNormalizedContent(Base):
    """Normalized Markdown body for one generation-scoped representation.

    Ownership is solely via ``representation_id`` -> ``asset_representations``
    (workspace/asset/generation live on that parent row).
    """

    __tablename__ = "document_normalized_contents"
    __table_args__ = (
        CheckConstraint(
            "format = 'markdown'",
            name="ck_document_normalized_contents_format",
        ),
        CheckConstraint(
            "normalization_version = 'document-normalization-v1'",
            name="ck_document_normalized_contents_normalization_version",
        ),
        CheckConstraint(
            "parser_version = 'document-parser-v1'",
            name="ck_document_normalized_contents_parser_version",
        ),
        CheckConstraint(
            "block_count >= 0",
            name="ck_document_normalized_contents_block_count",
        ),
    )

    representation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("asset_representations.id", ondelete="CASCADE"), primary_key=True
    )
    format: Mapped[str] = mapped_column(String(32))
    parser_version: Mapped[str] = mapped_column(String(64))
    normalization_version: Mapped[str] = mapped_column(String(64))
    normalized_text: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    block_count: Mapped[int] = mapped_column(Integer)


class DocumentBlock(Base):
    """Ordered block within a generation-scoped normalized document representation."""

    __tablename__ = "document_blocks"
    __table_args__ = (
        UniqueConstraint(
            "representation_id",
            "block_id",
            name="uq_document_blocks_representation_block_id",
        ),
        UniqueConstraint(
            "representation_id",
            "block_order",
            name="uq_document_blocks_representation_order",
        ),
        CheckConstraint(
            "block_kind IN ('heading', 'paragraph', 'list_item', 'code_block', 'quote', 'table')",
            name="ck_document_blocks_block_kind",
        ),
        CheckConstraint("block_order >= 0", name="ck_document_blocks_block_order"),
        CheckConstraint("char_start >= 0", name="ck_document_blocks_char_start"),
        CheckConstraint("char_end > char_start", name="ck_document_blocks_char_range"),
        CheckConstraint(
            "normalization_version = 'document-normalization-v1'",
            name="ck_document_blocks_normalization_version",
        ),
        CheckConstraint(
            "("
            "block_kind = 'heading' AND heading_level BETWEEN 1 AND 6"
            ") OR ("
            "block_kind <> 'heading' AND heading_level IS NULL"
            ")",
            name="ck_document_blocks_heading_level",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    representation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("asset_representations.id", ondelete="CASCADE"), index=True
    )
    block_id: Mapped[str] = mapped_column(String(64))
    block_order: Mapped[int] = mapped_column(Integer)
    block_kind: Mapped[str] = mapped_column(String(32))
    # Typed heading level for heading rows only; non-heading rows must leave this null.
    heading_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Schema-validated ordered string array; codec/API reject non-list/non-string payloads.
    heading_path: Mapped[list[str]] = mapped_column(JSON)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    text_sha256: Mapped[str] = mapped_column(String(64))
    text_content: Mapped[str] = mapped_column(Text)
    normalization_version: Mapped[str] = mapped_column(String(64))
