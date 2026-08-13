"""additive html locator and representation tables (catalog enable is S0)

Revision ID: j4d5e6f7a8b9
Revises: i3c4d5e6f7a8
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "j4d5e6f7a8b9"
down_revision: str | Sequence[str] | None = "i3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HTML_DOWNGRADE_REFUSAL = (
    "Refusing irreversible HTML modality downgrade while populated "
    "html representations, blocks, or html_anchor locators still exist"
)


def _count_scalar(connection, statement: str) -> int:
    return int(connection.execute(text(statement)).scalar_one())


def assert_html_modality_downgrade_safe(connection) -> None:
    checks = (
        "SELECT COUNT(*) FROM assets WHERE asset_kind = 'html'",
        (
            "SELECT COUNT(*) FROM asset_representations "
            "WHERE representation_kind IN ('html_source', 'html_normalized', 'html_sanitized')"
        ),
        (
            "SELECT COUNT(*) FROM content_units "
            "WHERE unit_kind IN ('html_block', 'html_text_chunk')"
        ),
        "SELECT COUNT(*) FROM evidence_locators WHERE locator_kind = 'html_anchor'",
        "SELECT COUNT(*) FROM html_normalized_contents",
        "SELECT COUNT(*) FROM html_blocks",
        "SELECT COUNT(*) FROM html_locator_details",
    )
    for statement in checks:
        if _count_scalar(connection, statement) > 0:
            raise RuntimeError(HTML_DOWNGRADE_REFUSAL)


def upgrade() -> None:
    op.create_table(
        "html_normalized_contents",
        sa.Column("representation_id", sa.String(length=36), nullable=False),
        sa.Column("format", sa.String(length=32), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("sanitizer_version", sa.String(length=64), nullable=False),
        sa.Column("normalization_version", sa.String(length=64), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("sanitized_html", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("block_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("format = 'html'", name="ck_html_normalized_contents_format"),
        sa.CheckConstraint(
            "normalization_version = 'html-normalization-v1'",
            name="ck_html_normalized_contents_normalization_version",
        ),
        sa.CheckConstraint(
            "parser_version = 'html-parser-v1'",
            name="ck_html_normalized_contents_parser_version",
        ),
        sa.CheckConstraint(
            "sanitizer_version = 'html-sanitizer-v1'",
            name="ck_html_normalized_contents_sanitizer_version",
        ),
        sa.CheckConstraint("block_count >= 0", name="ck_html_normalized_contents_block_count"),
        sa.ForeignKeyConstraint(
            ["representation_id"], ["asset_representations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("representation_id"),
    )

    op.create_table(
        "html_blocks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("representation_id", sa.String(length=36), nullable=False),
        sa.Column("block_id", sa.String(length=64), nullable=False),
        sa.Column("block_order", sa.Integer(), nullable=False),
        sa.Column("block_kind", sa.String(length=32), nullable=False),
        sa.Column("heading_level", sa.Integer(), nullable=True),
        sa.Column("heading_path", sa.JSON(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=False),
        sa.Column("normalization_version", sa.String(length=64), nullable=False),
        sa.Column("css_path_hint", sa.String(length=512), nullable=True),
        sa.CheckConstraint(
            "block_kind IN ('heading', 'paragraph', 'list_item', 'code_block', 'quote', 'table')",
            name="ck_html_blocks_block_kind",
        ),
        sa.CheckConstraint("block_order >= 0", name="ck_html_blocks_block_order"),
        sa.CheckConstraint("char_start >= 0", name="ck_html_blocks_char_start"),
        sa.CheckConstraint("char_end > char_start", name="ck_html_blocks_char_range"),
        sa.CheckConstraint(
            "normalization_version = 'html-normalization-v1'",
            name="ck_html_blocks_normalization_version",
        ),
        sa.CheckConstraint(
            "("
            "block_kind = 'heading' AND heading_level BETWEEN 1 AND 6"
            ") OR ("
            "block_kind <> 'heading' AND heading_level IS NULL"
            ")",
            name="ck_html_blocks_heading_level",
        ),
        sa.ForeignKeyConstraint(
            ["representation_id"], ["asset_representations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "representation_id",
            "block_id",
            name="uq_html_blocks_representation_block_id",
        ),
        sa.UniqueConstraint(
            "representation_id",
            "block_order",
            name="uq_html_blocks_representation_order",
        ),
    )
    op.create_index("ix_html_blocks_representation_id", "html_blocks", ["representation_id"])

    op.create_table(
        "html_locator_details",
        sa.Column("locator_id", sa.String(length=36), nullable=False),
        sa.Column("block_id", sa.String(length=64), nullable=False),
        sa.Column("block_kind", sa.String(length=32), nullable=False),
        sa.Column("heading_path", sa.JSON(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("normalization_version", sa.String(length=64), nullable=False),
        sa.Column("css_path_hint", sa.String(length=512), nullable=True),
        sa.CheckConstraint(
            "block_kind IN ('heading', 'paragraph', 'list_item', 'code_block', 'quote', 'table')",
            name="ck_html_locator_details_block_kind",
        ),
        sa.CheckConstraint("char_start >= 0", name="ck_html_locator_details_char_start"),
        sa.CheckConstraint("char_end > char_start", name="ck_html_locator_details_char_range"),
        sa.CheckConstraint(
            "normalization_version = 'html-normalization-v1'",
            name="ck_html_locator_details_normalization_version",
        ),
        sa.ForeignKeyConstraint(["locator_id"], ["evidence_locators.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("locator_id"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    assert_html_modality_downgrade_safe(connection)
    op.drop_table("html_locator_details")
    op.drop_index("ix_html_blocks_representation_id", table_name="html_blocks")
    op.drop_table("html_blocks")
    op.drop_table("html_normalized_contents")
