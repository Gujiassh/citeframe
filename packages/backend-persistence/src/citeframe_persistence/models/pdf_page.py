from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from citeframe_persistence.base import Base


class PdfPage(Base):
    __tablename__ = "pdf_pages"
    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "representation_id",
            "page_number",
            name="uq_pdf_pages_asset_representation_page",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("assets.id"), index=True)
    representation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("asset_representations.id"), index=True
    )
    page_number: Mapped[int] = mapped_column(Integer)
    media_x0_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    media_y0_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    media_x1_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    media_y1_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    crop_x0_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    crop_y0_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    crop_x1_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    crop_y1_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    rotation_degrees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    display_width_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    display_height_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    extracted_text: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer)
    legacy_ocr_blocks: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
