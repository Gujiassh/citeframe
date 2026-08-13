"""additive audio locator and representation tables (catalog enable is S0)

Revision ID: k5e6f7a8b9c0
Revises: j4d5e6f7a8b9
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "k5e6f7a8b9c0"
down_revision: str | Sequence[str] | None = "j4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUDIO_DOWNGRADE_REFUSAL = (
    "Refusing irreversible audio modality downgrade while populated "
    "audio representations, transcript segments, or audio_range locators still exist"
)


def _count_scalar(connection, statement: str) -> int:
    return int(connection.execute(text(statement)).scalar_one())


def assert_audio_modality_downgrade_safe(connection) -> None:
    checks = (
        "SELECT COUNT(*) FROM assets WHERE asset_kind = 'audio'",
        (
            "SELECT COUNT(*) FROM asset_representations "
            "WHERE representation_kind IN ('audio_source', 'audio_normalized')"
        ),
        (
            "SELECT COUNT(*) FROM content_units "
            "WHERE unit_kind = 'audio_transcript_segment'"
        ),
        "SELECT COUNT(*) FROM evidence_locators WHERE locator_kind = 'audio_range'",
        "SELECT COUNT(*) FROM audio_normalized_contents",
        "SELECT COUNT(*) FROM audio_transcript_segments",
        "SELECT COUNT(*) FROM audio_locator_details",
    )
    for statement in checks:
        if _count_scalar(connection, statement) > 0:
            raise RuntimeError(AUDIO_DOWNGRADE_REFUSAL)


def upgrade() -> None:
    op.create_table(
        "audio_normalized_contents",
        sa.Column("representation_id", sa.String(length=36), nullable=False),
        sa.Column("format", sa.String(length=32), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("normalization_version", sa.String(length=64), nullable=False),
        sa.Column("asr_adapter_version", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("segment_count", sa.Integer(), nullable=False),
        sa.Column("transcript_text", sa.Text(), nullable=False),
        sa.CheckConstraint("format = 'audio'", name="ck_audio_normalized_contents_format"),
        sa.CheckConstraint(
            "normalization_version = 'audio-normalization-v1'",
            name="ck_audio_normalized_contents_normalization_version",
        ),
        sa.CheckConstraint(
            "parser_version = 'audio-parser-v1'",
            name="ck_audio_normalized_contents_parser_version",
        ),
        sa.CheckConstraint(
            "asr_adapter_version = 'asr-openai-transcriptions-v1'",
            name="ck_audio_normalized_contents_asr_adapter_version",
        ),
        sa.CheckConstraint("duration_ms >= 0", name="ck_audio_normalized_contents_duration_ms"),
        sa.CheckConstraint(
            "segment_count >= 1", name="ck_audio_normalized_contents_segment_count"
        ),
        sa.CheckConstraint(
            "mime_type IN ('audio/mpeg', 'audio/wav', 'audio/mp4', 'audio/webm')",
            name="ck_audio_normalized_contents_mime_type",
        ),
        sa.ForeignKeyConstraint(
            ["representation_id"], ["asset_representations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("representation_id"),
    )

    op.create_table(
        "audio_transcript_segments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("representation_id", sa.String(length=36), nullable=False),
        sa.Column("segment_id", sa.String(length=64), nullable=False),
        sa.Column("segment_order", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.String(length=128), nullable=True),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=False),
        sa.Column("normalization_version", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "segment_order >= 0", name="ck_audio_transcript_segments_segment_order"
        ),
        sa.CheckConstraint("start_ms >= 0", name="ck_audio_transcript_segments_start_ms"),
        sa.CheckConstraint(
            "end_ms > start_ms", name="ck_audio_transcript_segments_time_range"
        ),
        sa.CheckConstraint(
            "normalization_version = 'audio-normalization-v1'",
            name="ck_audio_transcript_segments_normalization_version",
        ),
        sa.ForeignKeyConstraint(
            ["representation_id"], ["asset_representations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "representation_id",
            "segment_id",
            name="uq_audio_transcript_segments_representation_segment_id",
        ),
        sa.UniqueConstraint(
            "representation_id",
            "segment_order",
            name="uq_audio_transcript_segments_representation_order",
        ),
    )
    op.create_index(
        "ix_audio_transcript_segments_representation_id",
        "audio_transcript_segments",
        ["representation_id"],
    )

    op.create_table(
        "audio_locator_details",
        sa.Column("locator_id", sa.String(length=36), nullable=False),
        sa.Column("segment_id", sa.String(length=64), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("normalization_version", sa.String(length=64), nullable=False),
        sa.CheckConstraint("start_ms >= 0", name="ck_audio_locator_details_start_ms"),
        sa.CheckConstraint("end_ms > start_ms", name="ck_audio_locator_details_time_range"),
        sa.CheckConstraint(
            "normalization_version = 'audio-normalization-v1'",
            name="ck_audio_locator_details_normalization_version",
        ),
        sa.ForeignKeyConstraint(["locator_id"], ["evidence_locators.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("locator_id"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    assert_audio_modality_downgrade_safe(connection)
    op.drop_table("audio_locator_details")
    op.drop_index(
        "ix_audio_transcript_segments_representation_id",
        table_name="audio_transcript_segments",
    )
    op.drop_table("audio_transcript_segments")
    op.drop_table("audio_normalized_contents")
