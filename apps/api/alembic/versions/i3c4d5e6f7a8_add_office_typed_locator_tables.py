"""add typed office locator and representation tables

Revision ID: i3c4d5e6f7a8
Revises: h2b3c4d5e6f7
Create Date: 2026-08-13

Additive tables only. Catalog enablement for docx/xlsx/pptx is intentionally
omitted until S0 registry handoff.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "i3c4d5e6f7a8"
down_revision: str | Sequence[str] | None = "h2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "docx_normalized_contents",
        sa.Column("representation_id", sa.String(length=36), nullable=False),
        sa.Column("format", sa.String(length=32), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("normalization_version", sa.String(length=64), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("block_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("format = 'docx'", name="ck_docx_normalized_contents_format"),
        sa.CheckConstraint(
            "normalization_version = 'docx-normalization-v1'",
            name="ck_docx_normalized_contents_normalization_version",
        ),
        sa.CheckConstraint(
            "parser_version = 'docx-parser-v1'",
            name="ck_docx_normalized_contents_parser_version",
        ),
        sa.CheckConstraint(
            "block_count >= 0", name="ck_docx_normalized_contents_block_count"
        ),
        sa.ForeignKeyConstraint(
            ["representation_id"], ["asset_representations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("representation_id"),
    )
    op.create_table(
        "docx_blocks",
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
        sa.CheckConstraint(
            "block_kind IN ('heading', 'paragraph', 'list_item', 'table')",
            name="ck_docx_blocks_block_kind",
        ),
        sa.CheckConstraint("block_order >= 0", name="ck_docx_blocks_block_order"),
        sa.CheckConstraint("char_start >= 0", name="ck_docx_blocks_char_start"),
        sa.CheckConstraint("char_end > char_start", name="ck_docx_blocks_char_range"),
        sa.CheckConstraint(
            "normalization_version = 'docx-normalization-v1'",
            name="ck_docx_blocks_normalization_version",
        ),
        sa.ForeignKeyConstraint(
            ["representation_id"], ["asset_representations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "representation_id", "block_id", name="uq_docx_blocks_representation_block_id"
        ),
        sa.UniqueConstraint(
            "representation_id", "block_order", name="uq_docx_blocks_representation_order"
        ),
    )
    op.create_index(
        "ix_docx_blocks_representation_id", "docx_blocks", ["representation_id"]
    )
    op.create_table(
        "docx_locator_details",
        sa.Column("locator_id", sa.String(length=36), nullable=False),
        sa.Column("block_id", sa.String(length=64), nullable=False),
        sa.Column("block_kind", sa.String(length=32), nullable=False),
        sa.Column("heading_path", sa.JSON(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("normalization_version", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "block_kind IN ('heading', 'paragraph', 'list_item', 'table')",
            name="ck_docx_locator_details_block_kind",
        ),
        sa.CheckConstraint("char_start >= 0", name="ck_docx_locator_details_char_start"),
        sa.CheckConstraint(
            "char_end > char_start", name="ck_docx_locator_details_char_range"
        ),
        sa.CheckConstraint(
            "normalization_version = 'docx-normalization-v1'",
            name="ck_docx_locator_details_normalization_version",
        ),
        sa.ForeignKeyConstraint(
            ["locator_id"], ["evidence_locators.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("locator_id"),
    )
    op.create_table(
        "xlsx_locator_details",
        sa.Column("locator_id", sa.String(length=36), nullable=False),
        sa.Column("sheet_name", sa.String(length=255), nullable=False),
        sa.Column("start_cell", sa.String(length=32), nullable=False),
        sa.Column("end_cell", sa.String(length=32), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("displayed_text", sa.Text(), nullable=False),
        sa.Column("normalization_version", sa.String(length=64), nullable=False),
        sa.CheckConstraint("start_cell <> ''", name="ck_xlsx_locator_details_start_cell"),
        sa.CheckConstraint("end_cell <> ''", name="ck_xlsx_locator_details_end_cell"),
        sa.CheckConstraint(
            "normalization_version = 'xlsx-normalization-v1'",
            name="ck_xlsx_locator_details_normalization_version",
        ),
        sa.ForeignKeyConstraint(
            ["locator_id"], ["evidence_locators.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("locator_id"),
    )
    op.create_table(
        "pptx_locator_details",
        sa.Column("locator_id", sa.String(length=36), nullable=False),
        sa.Column("slide_index", sa.Integer(), nullable=False),
        sa.Column("shape_id", sa.String(length=64), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("displayed_text", sa.Text(), nullable=False),
        sa.Column("normalization_version", sa.String(length=64), nullable=False),
        sa.CheckConstraint("slide_index >= 1", name="ck_pptx_locator_details_slide_index"),
        sa.CheckConstraint(
            "normalization_version = 'pptx-normalization-v1'",
            name="ck_pptx_locator_details_normalization_version",
        ),
        sa.ForeignKeyConstraint(
            ["locator_id"], ["evidence_locators.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("locator_id"),
    )


def downgrade() -> None:
    op.drop_table("pptx_locator_details")
    op.drop_table("xlsx_locator_details")
    op.drop_table("docx_locator_details")
    op.drop_index("ix_docx_blocks_representation_id", table_name="docx_blocks")
    op.drop_table("docx_blocks")
    op.drop_table("docx_normalized_contents")
