"""S0 enable V5-F modality catalog rows (office/html/audio/video).

Revision ID: m7a8b9c0d1e2
Revises: l6f7a8b9c0d1
Create Date: 2026-08-13

Typed tables already exist. This migration only inserts catalog rows so
``build_production_registry().validate_catalog`` matches production.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "m7a8b9c0d1e2"
down_revision: str | Sequence[str] | None = "l6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO asset_types(kind, contract_version, enabled) VALUES
          ('docx', 1, true),
          ('xlsx', 1, true),
          ('pptx', 1, true),
          ('html', 1, true),
          ('audio', 1, true),
          ('video', 1, true)
        """
    )
    op.execute(
        """
        INSERT INTO representation_types(kind, asset_kind, contract_version) VALUES
          ('docx_source', 'docx', 1),
          ('docx_normalized', 'docx', 1),
          ('xlsx_source', 'xlsx', 1),
          ('xlsx_normalized', 'xlsx', 1),
          ('pptx_source', 'pptx', 1),
          ('pptx_normalized', 'pptx', 1),
          ('html_source', 'html', 1),
          ('html_normalized', 'html', 1),
          ('html_sanitized', 'html', 1),
          ('audio_source', 'audio', 1),
          ('audio_normalized', 'audio', 1),
          ('video_source', 'video', 1),
          ('video_normalized', 'video', 1),
          ('video_keyframe_set', 'video', 1)
        """
    )
    op.execute(
        """
        INSERT INTO content_unit_types(kind, asset_kind, contract_version) VALUES
          ('docx_text_chunk', 'docx', 1),
          ('xlsx_cell_text', 'xlsx', 1),
          ('pptx_shape_text', 'pptx', 1),
          ('html_block', 'html', 1),
          ('html_text_chunk', 'html', 1),
          ('audio_transcript_segment', 'audio', 1),
          ('video_transcript_segment', 'video', 1)
        """
    )
    op.execute(
        """
        INSERT INTO locator_types(kind, contract_version, detail_family) VALUES
          ('docx_anchor', 1, 'record'),
          ('xlsx_range', 1, 'record'),
          ('pptx_shape', 1, 'record'),
          ('html_anchor', 1, 'record'),
          ('audio_range', 1, 'temporal'),
          ('video_range', 1, 'temporal'),
          ('video_frame', 1, 'temporal')
        """
    )


def downgrade() -> None:
    # Catalog-only reverse. Typed tables remain; refuse if kinds still in use is
    # handled by earlier modality table migrations on full rollback.
    op.execute(
        """
        DELETE FROM locator_types WHERE kind IN (
          'docx_anchor', 'xlsx_range', 'pptx_shape', 'html_anchor',
          'audio_range', 'video_range', 'video_frame'
        )
        """
    )
    op.execute(
        """
        DELETE FROM content_unit_types WHERE kind IN (
          'docx_text_chunk', 'xlsx_cell_text', 'pptx_shape_text',
          'html_block', 'html_text_chunk',
          'audio_transcript_segment', 'video_transcript_segment'
        )
        """
    )
    op.execute(
        """
        DELETE FROM representation_types WHERE kind IN (
          'docx_source', 'docx_normalized',
          'xlsx_source', 'xlsx_normalized',
          'pptx_source', 'pptx_normalized',
          'html_source', 'html_normalized', 'html_sanitized',
          'audio_source', 'audio_normalized',
          'video_source', 'video_normalized', 'video_keyframe_set'
        )
        """
    )
    op.execute(
        """
        DELETE FROM asset_types WHERE kind IN (
          'docx', 'xlsx', 'pptx', 'html', 'audio', 'video'
        )
        """
    )
