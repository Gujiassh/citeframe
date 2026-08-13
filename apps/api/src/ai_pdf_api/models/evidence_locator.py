from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column

from ai_pdf_api.db.base import Base


class EvidenceLocator(Base):
    __tablename__ = "evidence_locators"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("assets.id"), index=True)
    locator_kind: Mapped[str] = mapped_column(String(64), ForeignKey("locator_types.kind"), index=True)
    locator_version: Mapped[int] = mapped_column(Integer)
    processing_generation_snapshot: Mapped[int] = mapped_column(Integer)
    representation_id_snapshot: Mapped[str] = mapped_column(
        String(36), ForeignKey("asset_representations.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PdfLocatorDetail(Base):
    __tablename__ = "pdf_locator_details"

    locator_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evidence_locators.id", ondelete="CASCADE"), primary_key=True
    )
    page_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("pdf_pages.id", ondelete="SET NULL"), nullable=True
    )
    page_number: Mapped[int] = mapped_column(Integer)
    coordinate_space: Mapped[str | None] = mapped_column(String(64), nullable=True)
    crop_x0_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    crop_y0_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    crop_x1_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    crop_y1_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    rotation_degrees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    display_width_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    display_height_points: Mapped[float | None] = mapped_column(Float, nullable=True)


class ImageLocatorDetail(Base):
    __tablename__ = "image_locator_details"

    locator_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evidence_locators.id", ondelete="CASCADE"), primary_key=True
    )
    coordinate_space: Mapped[str] = mapped_column(String(64))
    width_pixels: Mapped[int] = mapped_column(Integer)
    height_pixels: Mapped[int] = mapped_column(Integer)
    orientation_applied: Mapped[bool] = mapped_column(Boolean)


class SpatialLocatorRegion(Base):
    __tablename__ = "spatial_locator_regions"
    __table_args__ = (
        UniqueConstraint("locator_id", "region_order", name="uq_spatial_locator_regions_locator_order"),
        CheckConstraint("x >= 0 AND x <= 1", name="ck_spatial_locator_regions_x"),
        CheckConstraint("y >= 0 AND y <= 1", name="ck_spatial_locator_regions_y"),
        CheckConstraint("width > 0 AND width <= 1", name="ck_spatial_locator_regions_width"),
        CheckConstraint("height > 0 AND height <= 1", name="ck_spatial_locator_regions_height"),
        CheckConstraint("x + width <= 1", name="ck_spatial_locator_regions_x_width"),
        CheckConstraint("y + height <= 1", name="ck_spatial_locator_regions_y_height"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    locator_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evidence_locators.id", ondelete="CASCADE"), index=True
    )
    region_order: Mapped[int] = mapped_column(Integer)
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    width: Mapped[float] = mapped_column(Float)
    height: Mapped[float] = mapped_column(Float)

class DocumentLocatorDetail(Base):
    __tablename__ = "document_locator_details"
    __table_args__ = (
        CheckConstraint(
            "block_kind IN ('heading', 'paragraph', 'list_item', 'code_block', 'quote', 'table')",
            name="ck_document_locator_details_block_kind",
        ),
        CheckConstraint("char_start >= 0", name="ck_document_locator_details_char_start"),
        CheckConstraint("char_end > char_start", name="ck_document_locator_details_char_range"),
        CheckConstraint(
            "normalization_version = 'document-normalization-v1'",
            name="ck_document_locator_details_normalization_version",
        ),
    )

    locator_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evidence_locators.id", ondelete="CASCADE"), primary_key=True
    )
    block_id: Mapped[str] = mapped_column(String(64))
    block_kind: Mapped[str] = mapped_column(String(32))
    # Schema-validated ordered string array; codec/API reject unconstrained JSON truth.
    heading_path: Mapped[list[str]] = mapped_column(JSON)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    text_sha256: Mapped[str] = mapped_column(String(64))
    normalization_version: Mapped[str] = mapped_column(String(64))


class DocxLocatorDetail(Base):
    __tablename__ = "docx_locator_details"
    __table_args__ = (
        CheckConstraint(
            "block_kind IN ('heading', 'paragraph', 'list_item', 'table')",
            name="ck_docx_locator_details_block_kind",
        ),
        CheckConstraint("char_start >= 0", name="ck_docx_locator_details_char_start"),
        CheckConstraint("char_end > char_start", name="ck_docx_locator_details_char_range"),
        CheckConstraint(
            "normalization_version = 'docx-normalization-v1'",
            name="ck_docx_locator_details_normalization_version",
        ),
    )

    locator_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evidence_locators.id", ondelete="CASCADE"), primary_key=True
    )
    block_id: Mapped[str] = mapped_column(String(64))
    block_kind: Mapped[str] = mapped_column(String(32))
    heading_path: Mapped[list[str]] = mapped_column(JSON)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    text_sha256: Mapped[str] = mapped_column(String(64))
    normalization_version: Mapped[str] = mapped_column(String(64))


class XlsxLocatorDetail(Base):
    __tablename__ = "xlsx_locator_details"
    __table_args__ = (
        CheckConstraint("start_cell <> ''", name="ck_xlsx_locator_details_start_cell"),
        CheckConstraint("end_cell <> ''", name="ck_xlsx_locator_details_end_cell"),
        CheckConstraint(
            "normalization_version = 'xlsx-normalization-v1'",
            name="ck_xlsx_locator_details_normalization_version",
        ),
    )

    locator_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evidence_locators.id", ondelete="CASCADE"), primary_key=True
    )
    sheet_name: Mapped[str] = mapped_column(String(255))
    start_cell: Mapped[str] = mapped_column(String(32))
    end_cell: Mapped[str] = mapped_column(String(32))
    text_sha256: Mapped[str] = mapped_column(String(64))
    displayed_text: Mapped[str] = mapped_column(Text)
    normalization_version: Mapped[str] = mapped_column(String(64))


class PptxLocatorDetail(Base):
    __tablename__ = "pptx_locator_details"
    __table_args__ = (
        CheckConstraint("slide_index >= 1", name="ck_pptx_locator_details_slide_index"),
        CheckConstraint(
            "normalization_version = 'pptx-normalization-v1'",
            name="ck_pptx_locator_details_normalization_version",
        ),
    )

    locator_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evidence_locators.id", ondelete="CASCADE"), primary_key=True
    )
    slide_index: Mapped[int] = mapped_column(Integer)
    shape_id: Mapped[str] = mapped_column(String(64))
    text_sha256: Mapped[str] = mapped_column(String(64))
    displayed_text: Mapped[str] = mapped_column(Text)
    normalization_version: Mapped[str] = mapped_column(String(64))

class HtmlLocatorDetail(Base):
    __tablename__ = "html_locator_details"
    __table_args__ = (
        CheckConstraint(
            "block_kind IN ('heading', 'paragraph', 'list_item', 'code_block', 'quote', 'table')",
            name="ck_html_locator_details_block_kind",
        ),
        CheckConstraint("char_start >= 0", name="ck_html_locator_details_char_start"),
        CheckConstraint("char_end > char_start", name="ck_html_locator_details_char_range"),
        CheckConstraint(
            "normalization_version = 'html-normalization-v1'",
            name="ck_html_locator_details_normalization_version",
        ),
    )

    locator_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evidence_locators.id", ondelete="CASCADE"), primary_key=True
    )
    block_id: Mapped[str] = mapped_column(String(64))
    block_kind: Mapped[str] = mapped_column(String(32))
    heading_path: Mapped[list[str]] = mapped_column(JSON)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    text_sha256: Mapped[str] = mapped_column(String(64))
    normalization_version: Mapped[str] = mapped_column(String(64))
    css_path_hint: Mapped[str | None] = mapped_column(String(512), nullable=True)

class AudioLocatorDetail(Base):
    __tablename__ = "audio_locator_details"
    __table_args__ = (
        CheckConstraint("start_ms >= 0", name="ck_audio_locator_details_start_ms"),
        CheckConstraint("end_ms > start_ms", name="ck_audio_locator_details_time_range"),
        CheckConstraint(
            "normalization_version = 'audio-normalization-v1'",
            name="ck_audio_locator_details_normalization_version",
        ),
    )

    locator_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evidence_locators.id", ondelete="CASCADE"), primary_key=True
    )
    segment_id: Mapped[str] = mapped_column(String(64))
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    text_sha256: Mapped[str] = mapped_column(String(64))
    normalization_version: Mapped[str] = mapped_column(String(64))

