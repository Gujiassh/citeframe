from collections.abc import Generator, Mapping
from datetime import UTC, datetime
from typing import Literal

import pytest
from ai_pdf_api.db.base import Base
from ai_pdf_api.db.session import get_db
from ai_pdf_api.modalities.ingestion import IngestionAdapterRegistry, IngestionResult
from ai_pdf_api.modalities.pdf_ingestion import (
    PageArtifactResult,
    PageRegionResult,
    PageTextResult,
    PdfPageGeometryResult,
    delete_pdf_content,
    replace_pdf_content,
)
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ContentUnit,
    EvidenceLocator,
    PdfLocatorDetail,
    PdfPage,
    User,
    Workspace,
    WorkspaceMembership,
)
from ai_pdf_api.routers.assets import router as assets_router
from ai_pdf_api.routers.jobs import router as jobs_router
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

TEST_PDF_GEOMETRY = PdfPageGeometryResult(
    media_box_points=(0.0, 0.0, 612.0, 792.0),
    crop_box_points=(0.0, 0.0, 612.0, 792.0),
    rotation_degrees=0,
    display_width_points=612.0,
    display_height_points=792.0,
)


def parsed_page(
    page_number: int,
    text: str,
    *,
    source_kind: Literal["layout", "ocr"] = "layout",
    regions: tuple[PageRegionResult, ...] = (),
    artifacts: tuple[PageArtifactResult, ...] = (),
    ocr_blocks: list[dict[str, object]] | None = None,
) -> PageTextResult:
    return PageTextResult(
        page_number=page_number,
        text=text,
        geometry=TEST_PDF_GEOMETRY,
        source_kind=source_kind,
        regions=regions,
        artifacts=artifacts,
        ocr_blocks=ocr_blocks or [],
    )


class StaticPdfAdapter:
    asset_kind = "pdf"

    def __init__(self, pages: list[PageTextResult]) -> None:
        self.pages = pages

    def ingest(
        self,
        db: Session,
        *,
        asset: Asset,
        payload: bytes,
        processing_generation: int,
        config_snapshot: Mapping[str, object],
        created_at: datetime,
    ) -> IngestionResult:
        del payload
        chunk_size = config_snapshot.get("chunkSize", 1200)
        assert isinstance(chunk_size, int)
        replace_pdf_content(
            db,
            asset=asset,
            pages=self.pages,
            processing_generation=processing_generation,
            chunk_size=chunk_size,
            created_at=created_at,
        )
        return IngestionResult()

    def cleanup(self, db: Session, *, asset: Asset) -> None:
        delete_pdf_content(db, asset.id)


class FailingPdfAdapter(StaticPdfAdapter):
    def ingest(
        self,
        db: Session,
        *,
        asset: Asset,
        payload: bytes,
        processing_generation: int,
        config_snapshot: Mapping[str, object],
        created_at: datetime,
    ) -> IngestionResult:
        super().ingest(
            db,
            asset=asset,
            payload=payload,
            processing_generation=processing_generation,
            config_snapshot=config_snapshot,
            created_at=created_at,
        )
        raise RuntimeError("adapter failed after persistence")


def static_pdf_adapters(
    pages: list[PageTextResult] | None = None,
) -> IngestionAdapterRegistry:
    return IngestionAdapterRegistry((StaticPdfAdapter(pages or []),))


def failing_pdf_adapters(pages: list[PageTextResult]) -> IngestionAdapterRegistry:
    return IngestionAdapterRegistry((FailingPdfAdapter(pages),))


@pytest.fixture()
def asset_db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    testing_session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    Base.metadata.create_all(bind=engine)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def asset_client(
    asset_db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(assets_router)
    app.include_router(jobs_router)

    def override_get_db() -> Generator[Session, None, None]:
        yield asset_db_session

    uploaded_objects: dict[str, bytes] = {}

    def fake_upload_stream(
        object_key: str,
        payload,
        length: int,
        content_type: str,
    ) -> None:
        del content_type
        uploaded_objects[object_key] = payload.read(length)

    def fake_download_bytes(object_key: str) -> bytes:
        try:
            return uploaded_objects[object_key]
        except KeyError as error:
            raise FileNotFoundError(object_key) from error

    monkeypatch.setattr(
        "ai_pdf_api.routers.assets.upload_stream", fake_upload_stream
    )
    monkeypatch.setattr(
        "ai_pdf_api.routers.assets.download_bytes", fake_download_bytes
    )
    monkeypatch.setattr(
        "ai_pdf_api.routers.assets.object_exists", lambda object_key: True
    )

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def create_user(db_session: Session, *, email: str, name: str) -> User:
    user = User(
        email=email,
        name=name,
        password_hash="hashed",
        avatar_url=f"https://example.com/{name}.png",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def create_workspace_with_membership(
    db_session: Session,
    *,
    user: User,
    name: str,
    role: str = "owner",
) -> Workspace:
    now = datetime.now(UTC)
    workspace = Workspace(
        name=name,
        description=None,
        created_by_user_id=user.id,
        created_at=now,
        updated_at=now,
    )
    db_session.add(workspace)
    db_session.flush()
    db_session.add(
        WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=user.id,
            role=role,
        ),
    )
    db_session.commit()
    db_session.refresh(workspace)
    return workspace


def create_asset(
    db_session: Session,
    *,
    workspace: Workspace,
    user: User,
    source_filename: str = "attention.pdf",
    status: str = "uploaded",
) -> Asset:
    now = datetime.now(UTC)
    asset = Asset(
        asset_kind="pdf",
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        title="Attention Is All You Need",
        source_filename=source_filename,
        object_key=f"workspaces/{workspace.id}/assets/doc/original.pdf",
        mime_type="application/pdf",
        byte_size=1234,
        status=status,
        current_index_version=1,
        created_at=now,
        updated_at=now,
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


def create_pdf_content_unit(
    db_session: Session,
    *,
    asset: Asset,
    page_number: int,
    text: str,
    unit_order: int = 0,
    legacy_ocr_blocks: list[dict[str, object]] | None = None,
) -> ContentUnit:
    now = datetime.now(UTC)
    representation = db_session.scalar(
        select(AssetRepresentation).where(
            AssetRepresentation.asset_id == asset.id,
            AssetRepresentation.representation_kind == "pdf_text_legacy",
            AssetRepresentation.processing_generation
            == asset.current_processing_generation,
        )
    )
    if representation is None:
        representation = AssetRepresentation(
            workspace_id=asset.workspace_id,
            asset_id=asset.id,
            representation_kind="pdf_text_legacy",
            processing_generation=asset.current_processing_generation,
            generator_version="fixture-parser-v1",
            created_at=now,
        )
        db_session.add(representation)
        db_session.flush()
    page = PdfPage(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        representation_id=representation.id,
        page_number=page_number,
        extracted_text=text,
        char_count=len(text),
        legacy_ocr_blocks=legacy_ocr_blocks or [],
        created_at=now,
    )
    locator = EvidenceLocator(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        locator_kind="pdf_page",
        locator_version=1,
        processing_generation_snapshot=asset.current_processing_generation,
        representation_id_snapshot=representation.id,
        created_at=now,
    )
    db_session.add_all([page, locator])
    db_session.flush()
    db_session.add(
        PdfLocatorDetail(
            locator_id=locator.id, page_id=page.id, page_number=page_number
        )
    )
    unit = ContentUnit(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        representation_id=representation.id,
        source_locator_id=locator.id,
        unit_kind="pdf_text_chunk",
        unit_order=unit_order,
        text_content=text,
        token_count=1,
        char_start=0,
        char_end=len(text),
        index_version=asset.current_index_version,
        created_at=now,
    )
    db_session.add(unit)
    db_session.flush()
    return unit
