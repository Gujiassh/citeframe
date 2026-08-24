from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from citeframe_persistence.base import Base


class ImageRepresentationGeometry(Base):
    __tablename__ = "image_representation_geometry"

    representation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("asset_representations.id", ondelete="CASCADE"), primary_key=True
    )
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("assets.id"), index=True)
    width_pixels: Mapped[int] = mapped_column(Integer)
    height_pixels: Mapped[int] = mapped_column(Integer)
    orientation_applied: Mapped[bool] = mapped_column(Boolean)
