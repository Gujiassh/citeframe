from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from citeframe_persistence.base import Base


class DocxNormalizedContent(Base):
    __tablename__ = "docx_normalized_contents"
    __table_args__ = (
        CheckConstraint("format = 'docx'", name="ck_docx_normalized_contents_format"),
        CheckConstraint(
            "normalization_version = 'docx-normalization-v1'",
            name="ck_docx_normalized_contents_normalization_version",
        ),
        CheckConstraint(
            "parser_version = 'docx-parser-v1'",
            name="ck_docx_normalized_contents_parser_version",
        ),
        CheckConstraint("block_count >= 0", name="ck_docx_normalized_contents_block_count"),
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


class DocxBlock(Base):
    __tablename__ = "docx_blocks"
    __table_args__ = (
        UniqueConstraint(
            "representation_id",
            "block_id",
            name="uq_docx_blocks_representation_block_id",
        ),
        UniqueConstraint(
            "representation_id",
            "block_order",
            name="uq_docx_blocks_representation_order",
        ),
        CheckConstraint(
            "block_kind IN ('heading', 'paragraph', 'list_item', 'table')",
            name="ck_docx_blocks_block_kind",
        ),
        CheckConstraint("block_order >= 0", name="ck_docx_blocks_block_order"),
        CheckConstraint("char_start >= 0", name="ck_docx_blocks_char_start"),
        CheckConstraint("char_end > char_start", name="ck_docx_blocks_char_range"),
        CheckConstraint(
            "normalization_version = 'docx-normalization-v1'",
            name="ck_docx_blocks_normalization_version",
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
