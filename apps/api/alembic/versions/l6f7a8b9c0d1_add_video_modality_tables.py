"""additive video locator and representation tables (catalog enable is S0)

Revision ID: l6f7a8b9c0d1
Revises: k5e6f7a8b9c0
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "l6f7a8b9c0d1"
down_revision: str | Sequence[str] | None = "k5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VIDEO_DOWNGRADE_REFUSAL = (
    "Refusing irreversible video modality downgrade while populated "
    "video representations, transcript segments, or video locators still exist"
)


def _count_scalar(connection, statement: str) -> int:
    return int(connection.execute(text(statement)).scalar_one())


def assert_video_modality_downgrade_safe(connection) -> None:
    checks = (
        "SELECT COUNT(*) FROM assets WHERE asset_kind = 'video'",
        (
            "SELECT COUNT(*) FROM asset_representations "
            "WHERE representation_kind IN "
            "('video_source', 'video_normalized', 'video_keyframe_set')"
        ),
        (
            "SELECT COUNT(*) FROM content_units "
            "WHERE unit_kind = 'video_transcript_segment'"
        ),
        (
            "SELECT COUNT(*) FROM evidence_locators "
            "WHERE locator_kind IN ('video_range', 'video_frame')"
        ),
        "SELECT COUNT(*) FROM video_normalized_contents",
        "SELECT COUNT(*) FROM video_transcript_segments",
        "SELECT COUNT(*) FROM video_locator_details",
        "SELECT COUNT(*) FROM video_frame_locator_details",
    )
    for statement in checks:
        if _count_scalar(connection, statement) > 0:
            raise RuntimeError(VIDEO_DOWNGRADE_REFUSAL)


def upgrade() -> None:
    op.create_table(
        "video_normalized_contents",
        sa.Column("representation_id", sa.String(length=36), nullable=False),
        sa.Column("format", sa.String(length=32), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("normalization_version", sa.String(length=64), nullable=False),
        sa.Column("asr_adapter_version", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("segment_count", sa.Integer(), nullable=False),
        sa.Column("keyframe_count", sa.Integer(), nullable=False),
        sa.Column("transcript_text", sa.Text(), nullable=False),
        sa.CheckConstraint("format = 'video'", name="ck_video_normalized_contents_format"),
        sa.CheckConstraint(
            "normalization_version = 'video-normalization-v1'",
            name="ck_video_normalized_contents_normalization_version",
        ),
        sa.CheckConstraint(
            "parser_version = 'video-parser-v1'",
            name="ck_video_normalized_contents_parser_version",
        ),
        sa.CheckConstraint(
            "asr_adapter_version = 'asr-openai-transcriptions-v1'",
            name="ck_video_normalized_contents_asr_adapter_version",
        ),
        sa.CheckConstraint("duration_ms >= 0", name="ck_video_normalized_contents_duration_ms"),
        sa.CheckConstraint(
            "segment_count >= 1", name="ck_video_normalized_contents_segment_count"
        ),
        sa.CheckConstraint(
            "keyframe_count >= 0", name="ck_video_normalized_contents_keyframe_count"
        ),
        sa.CheckConstraint(
            "mime_type IN ('video/mp4', 'video/webm')",
            name="ck_video_normalized_contents_mime_type",
        ),
        sa.ForeignKeyConstraint(
            ["representation_id"], ["asset_representations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("representation_id"),
    )

    op.create_table(
        "video_transcript_segments",
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
            "segment_order >= 0", name="ck_video_transcript_segments_segment_order"
        ),
        sa.CheckConstraint("start_ms >= 0", name="ck_video_transcript_segments_start_ms"),
        sa.CheckConstraint(
            "end_ms > start_ms", name="ck_video_transcript_segments_time_range"
        ),
        sa.CheckConstraint(
            "normalization_version = 'video-normalization-v1'",
            name="ck_video_transcript_segments_normalization_version",
        ),
        sa.ForeignKeyConstraint(
            ["representation_id"], ["asset_representations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "representation_id",
            "segment_id",
            name="uq_video_transcript_segments_representation_segment_id",
        ),
        sa.UniqueConstraint(
            "representation_id",
            "segment_order",
            name="uq_video_transcript_segments_representation_order",
        ),
    )
    op.create_index(
        "ix_video_transcript_segments_representation_id",
        "video_transcript_segments",
        ["representation_id"],
    )

    op.create_table(
        "video_locator_details",
        sa.Column("locator_id", sa.String(length=36), nullable=False),
        sa.Column("segment_id", sa.String(length=64), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("normalization_version", sa.String(length=64), nullable=False),
        sa.CheckConstraint("start_ms >= 0", name="ck_video_locator_details_start_ms"),
        sa.CheckConstraint("end_ms > start_ms", name="ck_video_locator_details_time_range"),
        sa.CheckConstraint(
            "normalization_version = 'video-normalization-v1'",
            name="ck_video_locator_details_normalization_version",
        ),
        sa.ForeignKeyConstraint(["locator_id"], ["evidence_locators.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("locator_id"),
    )

    op.create_table(
        "video_frame_locator_details",
        sa.Column("locator_id", sa.String(length=36), nullable=False),
        sa.Column("timestamp_ms", sa.Integer(), nullable=True),
        sa.Column("frame_index", sa.Integer(), nullable=True),
        sa.Column("keyframe_object_key", sa.String(length=512), nullable=True),
        sa.Column("normalization_version", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "timestamp_ms IS NOT NULL OR frame_index IS NOT NULL",
            name="ck_video_frame_locator_details_anchor",
        ),
        sa.CheckConstraint(
            "timestamp_ms IS NULL OR timestamp_ms >= 0",
            name="ck_video_frame_locator_details_timestamp_ms",
        ),
        sa.CheckConstraint(
            "frame_index IS NULL OR frame_index >= 0",
            name="ck_video_frame_locator_details_frame_index",
        ),
        sa.CheckConstraint(
            "normalization_version = 'video-normalization-v1'",
            name="ck_video_frame_locator_details_normalization_version",
        ),
        sa.ForeignKeyConstraint(["locator_id"], ["evidence_locators.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("locator_id"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    assert_video_modality_downgrade_safe(connection)
    op.drop_table("video_frame_locator_details")
    op.drop_table("video_locator_details")
    op.drop_index(
        "ix_video_transcript_segments_representation_id",
        table_name="video_transcript_segments",
    )
    op.drop_table("video_transcript_segments")
    op.drop_table("video_normalized_contents")
