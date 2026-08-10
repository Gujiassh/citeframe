"""enable markdown document modality catalog and typed tables

Revision ID: f9a1b2c3d4e5
Revises: e8f1a2b3c4d5
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "f9a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "e8f1a2b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DOCUMENT_DOWNGRADE_REFUSAL = (
    "Refusing irreversible document modality downgrade while populated "
    "document assets, representations, content units, or document_anchor "
    "locators still exist"
)


def _count_scalar(connection, statement: str) -> int:
    return int(connection.execute(text(statement)).scalar_one())


def assert_document_modality_downgrade_safe(connection) -> None:
    """Refuse downgrade when any live document modality rows would be destroyed."""
    checks = (
        "SELECT COUNT(*) FROM assets WHERE asset_kind = 'document'",
        (
            "SELECT COUNT(*) FROM asset_representations "
            "WHERE representation_kind IN ('document_source', 'document_normalized')"
        ),
        (
            "SELECT COUNT(*) FROM content_units "
            "WHERE unit_kind IN ('document_block', 'document_text_chunk')"
        ),
        (
            "SELECT COUNT(*) FROM evidence_locators "
            "WHERE locator_kind = 'document_anchor'"
        ),
        "SELECT COUNT(*) FROM document_normalized_contents",
        "SELECT COUNT(*) FROM document_blocks",
        "SELECT COUNT(*) FROM document_locator_details",
    )
    for statement in checks:
        if _count_scalar(connection, statement) > 0:
            raise RuntimeError(DOCUMENT_DOWNGRADE_REFUSAL)


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO asset_types(kind, contract_version, enabled)
        VALUES ('document', 1, true)
        """
    )
    op.execute(
        """
        INSERT INTO representation_types(kind, asset_kind, contract_version) VALUES
          ('document_source', 'document', 1),
          ('document_normalized', 'document', 1)
        """
    )
    op.execute(
        """
        INSERT INTO content_unit_types(kind, asset_kind, contract_version) VALUES
          ('document_block', 'document', 1),
          ('document_text_chunk', 'document', 1)
        """
    )
    op.execute(
        """
        INSERT INTO locator_types(kind, contract_version, detail_family)
        VALUES ('document_anchor', 1, 'record')
        """
    )

    op.create_table(
        "document_normalized_contents",
        sa.Column("representation_id", sa.String(length=36), nullable=False),
        sa.Column("format", sa.String(length=32), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("normalization_version", sa.String(length=64), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("block_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("format = 'markdown'", name="ck_document_normalized_contents_format"),
        sa.CheckConstraint(
            "normalization_version = 'document-normalization-v1'",
            name="ck_document_normalized_contents_normalization_version",
        ),
        sa.CheckConstraint(
            "parser_version = 'document-parser-v1'",
            name="ck_document_normalized_contents_parser_version",
        ),
        sa.CheckConstraint(
            "block_count >= 0",
            name="ck_document_normalized_contents_block_count",
        ),
        sa.ForeignKeyConstraint(
            ["representation_id"], ["asset_representations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("representation_id"),
    )

    op.create_table(
        "document_blocks",
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
            "block_kind IN ('heading', 'paragraph', 'list_item', 'code_block', 'quote', 'table')",
            name="ck_document_blocks_block_kind",
        ),
        sa.CheckConstraint("block_order >= 0", name="ck_document_blocks_block_order"),
        sa.CheckConstraint("char_start >= 0", name="ck_document_blocks_char_start"),
        sa.CheckConstraint("char_end > char_start", name="ck_document_blocks_char_range"),
        sa.CheckConstraint(
            "normalization_version = 'document-normalization-v1'",
            name="ck_document_blocks_normalization_version",
        ),
        sa.CheckConstraint(
            "("
            "block_kind = 'heading' AND heading_level BETWEEN 1 AND 6"
            ") OR ("
            "block_kind <> 'heading' AND heading_level IS NULL"
            ")",
            name="ck_document_blocks_heading_level",
        ),
        sa.ForeignKeyConstraint(
            ["representation_id"], ["asset_representations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "representation_id",
            "block_id",
            name="uq_document_blocks_representation_block_id",
        ),
        sa.UniqueConstraint(
            "representation_id",
            "block_order",
            name="uq_document_blocks_representation_order",
        ),
    )
    op.create_index(
        "ix_document_blocks_representation_id", "document_blocks", ["representation_id"]
    )

    op.create_table(
        "document_locator_details",
        sa.Column("locator_id", sa.String(length=36), nullable=False),
        sa.Column("block_id", sa.String(length=64), nullable=False),
        sa.Column("block_kind", sa.String(length=32), nullable=False),
        sa.Column("heading_path", sa.JSON(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("normalization_version", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "block_kind IN ('heading', 'paragraph', 'list_item', 'code_block', 'quote', 'table')",
            name="ck_document_locator_details_block_kind",
        ),
        sa.CheckConstraint("char_start >= 0", name="ck_document_locator_details_char_start"),
        sa.CheckConstraint(
            "char_end > char_start", name="ck_document_locator_details_char_range"
        ),
        sa.CheckConstraint(
            "normalization_version = 'document-normalization-v1'",
            name="ck_document_locator_details_normalization_version",
        ),
        sa.ForeignKeyConstraint(
            ["locator_id"], ["evidence_locators.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("locator_id"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    assert_document_modality_downgrade_safe(connection)

    op.drop_table("document_locator_details")
    op.drop_index("ix_document_blocks_representation_id", table_name="document_blocks")
    op.drop_table("document_blocks")
    op.drop_table("document_normalized_contents")
    op.execute("DELETE FROM locator_types WHERE kind = 'document_anchor'")
    op.execute(
        "DELETE FROM content_unit_types WHERE kind IN ('document_block', 'document_text_chunk')"
    )
    op.execute(
        "DELETE FROM representation_types WHERE kind IN ('document_source', 'document_normalized')"
    )
    op.execute("DELETE FROM asset_types WHERE kind = 'document'")
