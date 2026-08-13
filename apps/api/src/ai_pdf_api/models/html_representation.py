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

from ai_pdf_api.db.base import Base

HTML_BLOCK_KINDS = (
    "heading",
    "paragraph",
    "list_item",
    "code_block",
    "quote",
    "table",
)
HTML_NORMALIZATION_VERSION = "html-normalization-v1"
HTML_PARSER_VERSION = "html-parser-v1"
HTML_SANITIZER_VERSION = "html-sanitizer-v1"
HTML_FORMAT = "html"


class HtmlNormalizedContent(Base):
    """Sanitized + normalized HTML body for one generation-scoped representation."""

    __tablename__ = "html_normalized_contents"
    __table_args__ = (
        CheckConstraint("format = 'html'", name="ck_html_normalized_contents_format"),
        CheckConstraint(
            "normalization_version = 'html-normalization-v1'",
            name="ck_html_normalized_contents_normalization_version",
        ),
        CheckConstraint(
            "parser_version = 'html-parser-v1'",
            name="ck_html_normalized_contents_parser_version",
        ),
        CheckConstraint(
            "sanitizer_version = 'html-sanitizer-v1'",
            name="ck_html_normalized_contents_sanitizer_version",
        ),
        CheckConstraint("block_count >= 0", name="ck_html_normalized_contents_block_count"),
    )

    representation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("asset_representations.id", ondelete="CASCADE"), primary_key=True
    )
    format: Mapped[str] = mapped_column(String(32))
    parser_version: Mapped[str] = mapped_column(String(64))
    sanitizer_version: Mapped[str] = mapped_column(String(64))
    normalization_version: Mapped[str] = mapped_column(String(64))
    normalized_text: Mapped[str] = mapped_column(Text)
    sanitized_html: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    block_count: Mapped[int] = mapped_column(Integer)


class HtmlBlock(Base):
    """Ordered block within a generation-scoped sanitized HTML representation."""

    __tablename__ = "html_blocks"
    __table_args__ = (
        UniqueConstraint(
            "representation_id",
            "block_id",
            name="uq_html_blocks_representation_block_id",
        ),
        UniqueConstraint(
            "representation_id",
            "block_order",
            name="uq_html_blocks_representation_order",
        ),
        CheckConstraint(
            "block_kind IN ('heading', 'paragraph', 'list_item', 'code_block', 'quote', 'table')",
            name="ck_html_blocks_block_kind",
        ),
        CheckConstraint("block_order >= 0", name="ck_html_blocks_block_order"),
        CheckConstraint("char_start >= 0", name="ck_html_blocks_char_start"),
        CheckConstraint("char_end > char_start", name="ck_html_blocks_char_range"),
        CheckConstraint(
            "normalization_version = 'html-normalization-v1'",
            name="ck_html_blocks_normalization_version",
        ),
        CheckConstraint(
            "("
            "block_kind = 'heading' AND heading_level BETWEEN 1 AND 6"
            ") OR ("
            "block_kind <> 'heading' AND heading_level IS NULL"
            ")",
            name="ck_html_blocks_heading_level",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    representation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("asset_representations.id", ondelete="CASCADE"), index=True
    )
    block_id: Mapped[str] = mapped_column(String(64))
    block_order: Mapped[int] = mapped_column(Integer)
    block_kind: Mapped[str] = mapped_column(String(32))
    heading_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heading_path: Mapped[list[str]] = mapped_column(JSON)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    text_sha256: Mapped[str] = mapped_column(String(64))
    text_content: Mapped[str] = mapped_column(Text)
    normalization_version: Mapped[str] = mapped_column(String(64))
    css_path_hint: Mapped[str | None] = mapped_column(String(512), nullable=True)
