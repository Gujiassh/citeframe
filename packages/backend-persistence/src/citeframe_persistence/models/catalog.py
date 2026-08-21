from sqlalchemy import Boolean, ForeignKey, Integer, String, true
from sqlalchemy.orm import Mapped, mapped_column

from citeframe_persistence.base import Base


class AssetType(Base):
    __tablename__ = "asset_types"

    kind: Mapped[str] = mapped_column(String(64), primary_key=True)
    contract_version: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)


class RepresentationType(Base):
    __tablename__ = "representation_types"

    kind: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset_kind: Mapped[str] = mapped_column(String(64), ForeignKey("asset_types.kind"), index=True)
    contract_version: Mapped[int] = mapped_column(Integer)


class ContentUnitType(Base):
    __tablename__ = "content_unit_types"

    kind: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset_kind: Mapped[str] = mapped_column(String(64), ForeignKey("asset_types.kind"), index=True)
    contract_version: Mapped[int] = mapped_column(Integer)


class LocatorType(Base):
    __tablename__ = "locator_types"

    kind: Mapped[str] = mapped_column(String(64), primary_key=True)
    contract_version: Mapped[int] = mapped_column(Integer)
    detail_family: Mapped[str] = mapped_column(String(32))


class EmbeddingSpace(Base):
    __tablename__ = "embedding_spaces"

    kind: Mapped[str] = mapped_column(String(64), primary_key=True)
    contract_version: Mapped[int] = mapped_column(Integer)
