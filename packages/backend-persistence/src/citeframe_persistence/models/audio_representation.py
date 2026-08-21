from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from citeframe_persistence.base import Base

AUDIO_FORMAT = "audio"
AUDIO_PARSER_VERSION = "audio-parser-v1"
AUDIO_NORMALIZATION_VERSION = "audio-normalization-v1"
AUDIO_ASR_ADAPTER_VERSION = "asr-openai-transcriptions-v1"


class AudioNormalizedContent(Base):
    """Normalized audio metadata for one generation-scoped representation."""

    __tablename__ = "audio_normalized_contents"
    __table_args__ = (
        CheckConstraint("format = 'audio'", name="ck_audio_normalized_contents_format"),
        CheckConstraint(
            "normalization_version = 'audio-normalization-v1'",
            name="ck_audio_normalized_contents_normalization_version",
        ),
        CheckConstraint(
            "parser_version = 'audio-parser-v1'",
            name="ck_audio_normalized_contents_parser_version",
        ),
        CheckConstraint(
            "asr_adapter_version = 'asr-openai-transcriptions-v1'",
            name="ck_audio_normalized_contents_asr_adapter_version",
        ),
        CheckConstraint("duration_ms >= 0", name="ck_audio_normalized_contents_duration_ms"),
        CheckConstraint("segment_count >= 1", name="ck_audio_normalized_contents_segment_count"),
        CheckConstraint(
            "mime_type IN ('audio/mpeg', 'audio/wav', 'audio/mp4', 'audio/webm')",
            name="ck_audio_normalized_contents_mime_type",
        ),
    )

    representation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("asset_representations.id", ondelete="CASCADE"), primary_key=True
    )
    format: Mapped[str] = mapped_column(String(32))
    parser_version: Mapped[str] = mapped_column(String(64))
    normalization_version: Mapped[str] = mapped_column(String(64))
    asr_adapter_version: Mapped[str] = mapped_column(String(64))
    mime_type: Mapped[str] = mapped_column(String(64))
    duration_ms: Mapped[int] = mapped_column(Integer)
    content_sha256: Mapped[str] = mapped_column(String(64))
    segment_count: Mapped[int] = mapped_column(Integer)
    transcript_text: Mapped[str] = mapped_column(Text)


class AudioTranscriptSegment(Base):
    """Ordered ASR transcript segment within a generation-scoped audio representation."""

    __tablename__ = "audio_transcript_segments"
    __table_args__ = (
        UniqueConstraint(
            "representation_id",
            "segment_id",
            name="uq_audio_transcript_segments_representation_segment_id",
        ),
        UniqueConstraint(
            "representation_id",
            "segment_order",
            name="uq_audio_transcript_segments_representation_order",
        ),
        CheckConstraint("segment_order >= 0", name="ck_audio_transcript_segments_segment_order"),
        CheckConstraint("start_ms >= 0", name="ck_audio_transcript_segments_start_ms"),
        CheckConstraint("end_ms > start_ms", name="ck_audio_transcript_segments_time_range"),
        CheckConstraint(
            "normalization_version = 'audio-normalization-v1'",
            name="ck_audio_transcript_segments_normalization_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    representation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("asset_representations.id", ondelete="CASCADE"), index=True
    )
    segment_id: Mapped[str] = mapped_column(String(64))
    segment_order: Mapped[int] = mapped_column(Integer)
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str | None] = mapped_column(String(128), nullable=True)
    text_sha256: Mapped[str] = mapped_column(String(64))
    text_content: Mapped[str] = mapped_column(Text)
    normalization_version: Mapped[str] = mapped_column(String(64))
