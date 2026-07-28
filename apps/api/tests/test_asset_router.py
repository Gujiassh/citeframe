from collections.abc import Generator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Literal

import pytest
from ai_pdf_api.core.settings import settings
from ai_pdf_api.db.base import Base
from ai_pdf_api.db.session import get_db
from ai_pdf_api.modalities.evidence import (
    clone_evidence_locator,
    serialize_evidence_locator,
)
from ai_pdf_api.modalities.ingestion import IngestionAdapterRegistry, IngestionResult
from ai_pdf_api.modalities.pdf_ingestion import (
    PageArtifactResult,
    PageRegionResult,
    PageTextResult,
    PdfPageGeometryResult,
    SpatialRegionResult,
    delete_pdf_content,
    replace_pdf_content,
    split_page_text,
)
from ai_pdf_api.modalities.text import estimate_token_count
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ChatMessage,
    ChatThread,
    ContentUnit,
    ContentUnitEmbedding,
    EvidenceLocator,
    IngestionJob,
    MessageCitation,
    Note,
    NoteSource,
    PdfLocatorDetail,
    PdfPage,
    SpatialLocatorRegion,
    User,
    Workspace,
    WorkspaceMembership,
)
from ai_pdf_api.routers.assets import router as assets_router
from ai_pdf_api.routers.jobs import router as jobs_router
from ai_pdf_api.services.ingestion import (
    INGESTION_LEASE_TIMEOUT,
    claim_next_ingestion_job,
    process_embedding_job,
    process_ingestion_job,
)
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


def static_pdf_adapters(pages: list[PageTextResult] | None = None) -> IngestionAdapterRegistry:
    return IngestionAdapterRegistry((StaticPdfAdapter(pages or []),))


def failing_pdf_adapters(pages: list[PageTextResult]) -> IngestionAdapterRegistry:
    return IngestionAdapterRegistry((FailingPdfAdapter(pages),))


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(assets_router)
    app.include_router(jobs_router)

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    monkeypatch.setattr("ai_pdf_api.routers.assets.upload_stream", lambda *args, **kwargs: None)
    monkeypatch.setattr("ai_pdf_api.routers.assets.object_exists", lambda object_key: True)

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
            AssetRepresentation.processing_generation == asset.current_processing_generation,
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
        PdfLocatorDetail(locator_id=locator.id, page_id=page.id, page_number=page_number)
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


def test_list_assets_requires_membership(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    stranger = create_user(db_session, email="stranger@example.com", name="Stranger")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Private")
    create_asset(db_session, workspace=workspace, user=owner)

    response = client.get(f"/v1/workspaces/{workspace.id}/assets", headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": stranger.id})

    assert response.status_code == 404
    assert response.json()["detail"] == "Workspace not found."


def test_get_asset_file_streams_original_pdf_for_members(client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    member = create_user(db_session, email="member@example.com", name="Member")
    stranger = create_user(db_session, email="stranger@example.com", name="Stranger")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Private")
    db_session.add(WorkspaceMembership(workspace_id=workspace.id, user_id=member.id, role="editor"))
    db_session.commit()
    asset = create_asset(db_session, workspace=workspace, user=owner, source_filename="原始资料.pdf")
    monkeypatch.setattr(
        "ai_pdf_api.routers.assets.stream_bytes",
        lambda object_key: iter((b"%PDF-1.7\n", b"original page bytes")),
    )

    for user_id in (owner.id, member.id):
        response = client.get(
            f"/v1/workspaces/{workspace.id}/assets/{asset.id}/file",
            headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": user_id},
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["content-disposition"].startswith("inline; filename*=")
        assert response.content == b"%PDF-1.7\noriginal page bytes"

    forbidden_response = client.get(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}/file",
        headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": stranger.id},
    )
    assert forbidden_response.status_code == 404
    assert forbidden_response.json()["detail"] == "Workspace not found."


def test_create_upload_session_persists_pending_asset(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")

    response = client.post(
        f"/v1/workspaces/{workspace.id}/assets/upload-session",
        headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id},
        json={
            "sourceFilename": "attention.pdf",
            "mimeType": "application/pdf",
            "byteSize": len(b"%PDF-1.7 fake pdf bytes"),
            "title": "Attention Is All You Need",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["asset"]["workspaceId"] == workspace.id
    assert payload["asset"]["status"] == "pending_upload"
    assert payload["upload"]["method"] == "PUT"
    assert payload["upload"]["headers"]["Content-Type"] == "application/pdf"
    assert payload["upload"]["objectKey"].startswith(f"workspaces/{workspace.id}/assets/")

    asset = db_session.get(Asset, payload["asset"]["id"])
    assert asset is not None
    assert asset.status == "pending_upload"
    assert asset.object_key == payload["upload"]["objectKey"]


def test_create_upload_session_canonicalizes_mime_type(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="mime-owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")

    response = client.post(
        f"/v1/workspaces/{workspace.id}/assets/upload-session",
        headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id},
        json={
            "sourceFilename": "attention.pdf",
            "mimeType": "APPLICATION/PDF",
            "byteSize": len(b"%PDF-1.7 fake pdf bytes"),
        },
    )

    assert response.status_code == 201
    assert response.json()["asset"]["mimeType"] == "application/pdf"
    assert response.json()["upload"]["headers"] == {"Content-Type": "application/pdf"}


def test_create_upload_session_rejects_unregistered_mime_type(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")

    response = client.post(
        f"/v1/workspaces/{workspace.id}/assets/upload-session",
        headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id},
        json={
            "sourceFilename": "notes.txt",
            "mimeType": "text/plain",
            "byteSize": 12,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Unsupported MIME type: text/plain"


@pytest.mark.parametrize(
    ("source_filename", "mime_type"),
    [
        ("diagram.png", "image/png"),
        ("photo.jpg", "image/jpeg"),
        ("chart.webp", "image/webp"),
    ],
)
def test_create_upload_session_accepts_enabled_image_formats(
    client: TestClient,
    db_session: Session,
    source_filename: str,
    mime_type: str,
) -> None:
    owner = create_user(db_session, email="image-owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Images")

    response = client.post(
        f"/v1/workspaces/{workspace.id}/assets/upload-session",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
        },
        json={
            "sourceFilename": source_filename,
            "mimeType": mime_type,
            "byteSize": 128,
        },
    )

    assert response.status_code == 201
    assert response.json()["asset"]["kind"] == "image"
    assert response.json()["asset"]["mimeType"] == mime_type
    assert response.json()["upload"]["headers"] == {"Content-Type": mime_type}
    assert db_session.query(Asset).filter_by(workspace_id=workspace.id).count() == 1


def test_binary_upload_and_finalize_creates_queued_ingestion_job(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    upload_session = client.post(
        f"/v1/workspaces/{workspace.id}/assets/upload-session",
        headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id},
        json={
            "sourceFilename": "attention.pdf",
            "mimeType": "application/pdf",
            "byteSize": len(b"%PDF-1.7 fake pdf bytes"),
            "title": "Attention Is All You Need",
        },
    ).json()

    asset_id = upload_session["asset"]["id"]
    object_key = upload_session["upload"]["objectKey"]

    upload_response = client.put(
        f"/v1/workspaces/{workspace.id}/assets/{asset_id}/upload",
        headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id, "content-type": "application/pdf"},
        params={"objectKey": object_key},
        content=b"%PDF-1.7 fake pdf bytes",
    )
    assert upload_response.status_code == 204

    finalize_response = client.post(
        f"/v1/workspaces/{workspace.id}/assets/{asset_id}/finalize-upload",
        headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id},
        json={"objectKey": object_key},
    )

    assert finalize_response.status_code == 200
    payload = finalize_response.json()
    assert payload["asset"]["status"] == "uploaded"
    assert payload["job"]["jobType"] == "ingest"
    assert payload["job"]["status"] == "queued"

    asset = db_session.get(Asset, asset_id)
    assert asset is not None
    assert asset.status == "uploaded"
    assert asset.latest_ingestion_job_id == payload["job"]["id"]

    job = db_session.get(IngestionJob, payload["job"]["id"])
    assert job is not None
    assert job.asset_id == asset_id
    assert job.job_type == "ingest"


def test_binary_upload_rejects_size_mismatch(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="size-owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    upload_session = client.post(
        f"/v1/workspaces/{workspace.id}/assets/upload-session",
        headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id},
        json={"sourceFilename": "attention.pdf", "mimeType": "application/pdf", "byteSize": 99},
    ).json()

    response = client.put(
        f"/v1/workspaces/{workspace.id}/assets/{upload_session['asset']['id']}/upload",
        headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id, "content-type": "application/pdf"},
        params={"objectKey": upload_session["upload"]["objectKey"]},
        content=b"short",
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Upload size does not match the upload session."


def test_binary_upload_rejects_content_type_mismatch(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="content-type-owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    source = b"%PDF-1.7 fake pdf bytes"
    upload_session = client.post(
        f"/v1/workspaces/{workspace.id}/assets/upload-session",
        headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id},
        json={
            "sourceFilename": "attention.pdf",
            "mimeType": "application/pdf",
            "byteSize": len(source),
        },
    ).json()

    response = client.put(
        f"/v1/workspaces/{workspace.id}/assets/{upload_session['asset']['id']}/upload",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
            "content-type": "image/png",
        },
        params={"objectKey": upload_session["upload"]["objectKey"]},
        content=source,
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Upload Content-Type does not match the upload session."


def test_get_job_returns_persisted_job(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    asset = create_asset(db_session, workspace=workspace, user=owner, status="uploaded")
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="queued",
        attempt_count=1,
        config_snapshot={"source": "test"},
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    response = client.get(f"/v1/workspaces/{workspace.id}/jobs/{job.id}", headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id})

    assert response.status_code == 200
    payload = response.json()
    assert payload["job"]["id"] == job.id
    assert payload["job"]["assetId"] == asset.id


def test_ingestion_worker_persists_pages_and_chunks(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    asset = create_asset(db_session, workspace=workspace, user=owner, status="uploaded")
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="queued",
        attempt_count=1,
        config_snapshot={"source": "test"},
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.commit()

    monkeypatch.setattr("ai_pdf_api.services.ingestion.download_bytes", lambda object_key: b"pdf")

    def extract_pages(_payload: bytes):
        return [
            parsed_page(1, "Page one heading\n" + "alpha " * 300),
            parsed_page(2, "Page two body"),
        ]

    claimed_job_id = claim_next_ingestion_job(db_session)
    assert claimed_job_id == job.id
    assert db_session.get(Asset, asset.id).status == "parsing"

    process_ingestion_job(
        db_session,
        claimed_job_id,
        ingestion_adapters=static_pdf_adapters(extract_pages(b"pdf")),
    )

    refreshed_asset = db_session.get(Asset, asset.id)
    refreshed_job = db_session.get(IngestionJob, job.id)
    pages = db_session.scalars(select(PdfPage).where(PdfPage.asset_id == asset.id)).all()
    chunks = db_session.scalars(select(ContentUnit).where(ContentUnit.asset_id == asset.id)).all()
    assert refreshed_asset is not None
    assert refreshed_asset.status == "chunked"
    assert len(pages) == 2
    assert refreshed_job is not None
    assert refreshed_job.status == "succeeded"
    assert len(pages) == 2
    assert len(chunks) >= 2
    assert {chunk.index_version for chunk in chunks} == {1}
    assert all(page.crop_x0_points == 0.0 for page in pages)
    assert all(page.crop_y1_points == 792.0 for page in pages)
    assert all(page.display_width_points == 612.0 for page in pages)


def test_ingestion_worker_embeds_chunks_and_marks_asset_ready(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    asset = create_asset(db_session, workspace=workspace, user=owner, status="uploaded")
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="queued",
        attempt_count=1,
        config_snapshot={"source": "test"},
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.flush()
    asset.latest_ingestion_job_id = job.id
    db_session.commit()

    class FakeEmbeddingProvider:
        provider = "fake"
        model = "fake-embedding"
        dimensions = 3
        version = "fake-v1"

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0, 0.0] for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            return [1.0, 0.0, 0.0]

    monkeypatch.setattr("ai_pdf_api.services.ingestion.download_bytes", lambda object_key: b"pdf")

    claimed_job_id = claim_next_ingestion_job(db_session)
    process_ingestion_job(
        db_session,
        claimed_job_id,
        ingestion_adapters=static_pdf_adapters(
            [parsed_page(1, "embedding regression text")]
        ),
        embedding_provider=FakeEmbeddingProvider(),
    )

    refreshed_asset = db_session.get(Asset, asset.id)
    refreshed_job = db_session.get(IngestionJob, job.id)
    chunks = db_session.scalars(select(ContentUnit).where(ContentUnit.asset_id == asset.id)).all()
    embeddings = db_session.scalars(
        select(ContentUnitEmbedding).where(
            ContentUnitEmbedding.content_unit_id.in_([chunk.id for chunk in chunks])
        )
    ).all()
    assert refreshed_asset is not None
    assert refreshed_asset.status == "ready"
    assert refreshed_job is not None
    assert refreshed_job.status == "succeeded"
    assert chunks
    assert embeddings and embeddings[0].embedding == [1.0, 0.0, 0.0]
    assert embeddings[0].provider == "fake"
    assert embeddings[0].dimensions == 3
    assert {
        (
            embedding.asset_id,
            embedding.processing_generation,
            embedding.index_version,
            embedding.is_current,
        )
        for embedding in embeddings
    } == {(asset.id, 1, 1, True)}


def test_ingestion_persists_artifacts_without_duplicate_embedding_text(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = create_user(db_session, email="artifact-owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Artifacts")
    asset = create_asset(db_session, workspace=workspace, user=owner, status="uploaded")
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="queued",
        attempt_count=1,
        config_snapshot={"source": "artifact-fixture"},
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.flush()
    asset.latest_ingestion_job_id = job.id
    db_session.commit()

    page_text = (
        "Artifact fixture\n"
        "Model Score\n"
        "Evidence-A 91.4\n"
        "Figure 1. Trend rises after the third point.\n"
        "Unrelated page conclusion.\n"
        "Supporting caption in a separate region."
    )
    table_source = "Model Score\nEvidence-A 91.4"
    figure_source = "Figure 1. Trend rises after the third point."
    figure_support = "Supporting caption in a separate region."
    table_start = page_text.index(table_source)
    figure_start = page_text.index(figure_source)
    figure_support_start = page_text.index(figure_support)
    page_result = parsed_page(
        1,
        page_text,
        artifacts=(
            PageArtifactResult(
                text="| Model | Score |\n| --- | --- |\n| Evidence-A | 91.4 |",
                unit_kind="pdf_table",
                regions=(
                    SpatialRegionResult(x=0.1, y=0.2, width=0.7, height=0.2),
                ),
                char_ranges=((table_start, table_start + len(table_source)),),
            ),
            PageArtifactResult(
                text=f"{figure_source}\n{figure_support}",
                unit_kind="pdf_figure",
                regions=(
                    SpatialRegionResult(x=0.15, y=0.5, width=0.6, height=0.25),
                    SpatialRegionResult(x=0.15, y=0.78, width=0.5, height=0.05),
                ),
                char_ranges=(
                    (figure_start, figure_start + len(figure_source)),
                    (figure_support_start, figure_support_start + len(figure_support)),
                ),
            ),
        ),
    )

    class CapturingEmbeddingProvider:
        provider = "fake"
        model = "fake-embedding"
        dimensions = 3
        version = "fake-v1"

        def __init__(self) -> None:
            self.texts: list[str] = []

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            self.texts.extend(texts)
            return [[1.0, 0.0, 0.0] for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            return [1.0, 0.0, 0.0]

    embedding_provider = CapturingEmbeddingProvider()
    monkeypatch.setattr("ai_pdf_api.services.ingestion.download_bytes", lambda _key: b"pdf")

    claimed_job_id = claim_next_ingestion_job(db_session)
    process_ingestion_job(
        db_session,
        claimed_job_id,
        ingestion_adapters=static_pdf_adapters([page_result]),
        embedding_provider=embedding_provider,
    )

    representations = db_session.scalars(
        select(AssetRepresentation)
        .where(AssetRepresentation.asset_id == asset.id)
        .order_by(AssetRepresentation.representation_kind)
    ).all()
    units = db_session.scalars(
        select(ContentUnit)
        .where(ContentUnit.asset_id == asset.id)
        .order_by(ContentUnit.unit_kind)
    ).all()
    assert {representation.representation_kind for representation in representations} == {
        "pdf_page_layout",
        "pdf_table",
        "pdf_figure",
    }
    assert {unit.unit_kind for unit in units} == {
        "pdf_text_chunk",
        "pdf_table",
        "pdf_figure",
    }
    assert sum("Evidence-A" in unit.text_content for unit in units) == 1
    assert sum("Trend rises" in unit.text_content for unit in units) == 1
    assert sum("Supporting caption" in unit.text_content for unit in units) == 1
    assert sum("Unrelated page conclusion" in unit.text_content for unit in units) == 1
    assert len(embedding_provider.texts) == len(units)
    assert sorted(embedding_provider.texts) == sorted(unit.text_content for unit in units)
    assert sum("Evidence-A" in text for text in embedding_provider.texts) == 1
    assert sum("Trend rises" in text for text in embedding_provider.texts) == 1
    assert sum("Supporting caption" in text for text in embedding_provider.texts) == 1
    assert sum("Unrelated page conclusion" in text for text in embedding_provider.texts) == 1

    artifact_units = [unit for unit in units if unit.unit_kind != "pdf_text_chunk"]
    assert all(unit.char_start is None and unit.char_end is None for unit in artifact_units)
    text_units = [unit for unit in units if unit.unit_kind == "pdf_text_chunk"]
    assert all(unit.char_start is not None and unit.char_end is not None for unit in text_units)
    for unit, expected_regions in zip(
        sorted(artifact_units, key=lambda item: item.unit_kind),
        (
            ((0.15, 0.5, 0.6, 0.25), (0.15, 0.78, 0.5, 0.05)),
            ((0.1, 0.2, 0.7, 0.2),),
        ),
        strict=True,
    ):
        locator = db_session.get(EvidenceLocator, unit.source_locator_id)
        detail = db_session.get(PdfLocatorDetail, unit.source_locator_id)
        regions = db_session.scalars(
            select(SpatialLocatorRegion)
            .where(SpatialLocatorRegion.locator_id == unit.source_locator_id)
            .order_by(SpatialLocatorRegion.region_order)
        ).all()
        assert locator is not None and locator.locator_kind == "pdf_region"
        assert detail is not None
        assert detail.coordinate_space == "pdf_crop_box_normalized_top_left_v1"
        assert [region.region_order for region in regions] == list(range(len(expected_regions)))
        for region, expected_region in zip(regions, expected_regions, strict=True):
            assert (region.x, region.y, region.width, region.height) == pytest.approx(
                expected_region
            )


def test_failed_reprocessing_restores_previous_generation_content_and_embeddings(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = create_user(db_session, email="rollback-owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    asset = create_asset(db_session, workspace=workspace, user=owner, status="ready")
    old_unit = create_pdf_content_unit(
        db_session,
        asset=asset,
        page_number=1,
        text="stable old evidence",
    )
    old_embedding = ContentUnitEmbedding(
        workspace_id=workspace.id,
        asset_id=asset.id,
        content_unit_id=old_unit.id,
        processing_generation=asset.current_processing_generation,
        index_version=old_unit.index_version,
        is_current=True,
        embedding_space="text",
        provider="fake",
        model="fake-embedding",
        dimensions=3,
        version="fake-v1",
        embedding=[1.0, 0.0, 0.0],
        created_at=datetime.now(UTC),
    )
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="queued",
        attempt_count=1,
        config_snapshot={"source": "retry"},
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db_session.add_all([old_embedding, job])
    db_session.flush()
    asset.latest_ingestion_job_id = job.id
    db_session.commit()
    before_pages = [
        (page.id, page.representation_id, page.extracted_text)
        for page in db_session.scalars(
            select(PdfPage).where(PdfPage.asset_id == asset.id).order_by(PdfPage.id)
        ).all()
    ]
    before_units = [
        (unit.id, unit.representation_id, unit.source_locator_id, unit.text_content)
        for unit in db_session.scalars(
            select(ContentUnit).where(ContentUnit.asset_id == asset.id).order_by(ContentUnit.id)
        ).all()
    ]
    before_embeddings = [
        (embedding.id, embedding.content_unit_id, embedding.embedding)
        for embedding in db_session.scalars(
            select(ContentUnitEmbedding).order_by(ContentUnitEmbedding.id)
        ).all()
    ]
    before_representations = [
        representation.id
        for representation in db_session.scalars(
            select(AssetRepresentation)
            .where(AssetRepresentation.asset_id == asset.id)
            .order_by(AssetRepresentation.id)
        ).all()
    ]
    monkeypatch.setattr("ai_pdf_api.services.ingestion.download_bytes", lambda _key: b"pdf")

    claimed_job_id = claim_next_ingestion_job(db_session)
    process_ingestion_job(
        db_session,
        claimed_job_id,
        ingestion_adapters=failing_pdf_adapters([parsed_page(1, "new partial evidence")]),
    )

    db_session.expire_all()
    refreshed_asset = db_session.get(Asset, asset.id)
    refreshed_job = db_session.get(IngestionJob, job.id)
    assert refreshed_asset is not None
    assert refreshed_asset.current_processing_generation == 1
    assert refreshed_asset.status == "failed"
    assert refreshed_job is not None and refreshed_job.error_code == "ingestion_failed"
    assert [
        (page.id, page.representation_id, page.extracted_text)
        for page in db_session.scalars(
            select(PdfPage).where(PdfPage.asset_id == asset.id).order_by(PdfPage.id)
        ).all()
    ] == before_pages
    assert [
        (unit.id, unit.representation_id, unit.source_locator_id, unit.text_content)
        for unit in db_session.scalars(
            select(ContentUnit).where(ContentUnit.asset_id == asset.id).order_by(ContentUnit.id)
        ).all()
    ] == before_units
    assert [
        (embedding.id, embedding.content_unit_id, embedding.embedding)
        for embedding in db_session.scalars(
            select(ContentUnitEmbedding).order_by(ContentUnitEmbedding.id)
        ).all()
    ] == before_embeddings
    assert [
        representation.id
        for representation in db_session.scalars(
            select(AssetRepresentation)
            .where(AssetRepresentation.asset_id == asset.id)
            .order_by(AssetRepresentation.id)
        ).all()
    ] == before_representations


def test_successful_reprocessing_preserves_historical_citation_and_note_evidence(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = create_user(db_session, email="history-owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    asset = create_asset(db_session, workspace=workspace, user=owner, status="ready")
    old_unit = create_pdf_content_unit(
        db_session,
        asset=asset,
        page_number=4,
        text="historical region evidence",
    )
    source_locator = db_session.get(EvidenceLocator, old_unit.source_locator_id)
    source_detail = db_session.get(PdfLocatorDetail, old_unit.source_locator_id)
    assert source_locator is not None and source_detail is not None
    source_locator.locator_kind = "pdf_region"
    source_detail.coordinate_space = "pdf_crop_box_normalized_top_left_v1"
    source_detail.crop_x0_points = 0.0
    source_detail.crop_y0_points = 0.0
    source_detail.crop_x1_points = 612.0
    source_detail.crop_y1_points = 792.0
    source_detail.rotation_degrees = 0
    source_detail.display_width_points = 612.0
    source_detail.display_height_points = 792.0
    db_session.add(
        SpatialLocatorRegion(
            locator_id=source_locator.id,
            region_order=0,
            x=0.2,
            y=0.3,
            width=0.4,
            height=0.1,
        )
    )
    db_session.flush()
    now = datetime.now(UTC)
    citation_locator = clone_evidence_locator(db_session, source_locator.id, created_at=now)
    note_locator = clone_evidence_locator(db_session, citation_locator.id, created_at=now)
    thread = ChatThread(
        workspace_id=workspace.id,
        created_by_user_id=owner.id,
        title="History",
        last_message_at=now,
        created_at=now,
        updated_at=now,
    )
    db_session.add(thread)
    db_session.flush()
    message = ChatMessage(
        workspace_id=workspace.id,
        thread_id=thread.id,
        role="assistant",
        content="Historical answer.",
        status="completed",
        created_at=now,
    )
    note = Note(
        workspace_id=workspace.id,
        created_by_user_id=owner.id,
        updated_by_user_id=owner.id,
        title="History note",
        body_md="Historical note.",
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([message, note])
    db_session.flush()
    old_representation = db_session.get(AssetRepresentation, source_locator.representation_id_snapshot)
    assert old_representation is not None
    citation = MessageCitation(
        workspace_id=workspace.id,
        message_id=message.id,
        citation_index=0,
        evidence_locator_id=citation_locator.id,
        asset_id=asset.id,
        asset_kind_snapshot="pdf",
        asset_title_snapshot="Historical title",
        excerpt_snapshot="Historical excerpt.",
        processing_generation_snapshot=1,
        representation_id_snapshot=old_representation.id,
        parser_version_snapshot=old_representation.generator_version,
        index_version_snapshot=1,
        created_at=now,
    )
    db_session.add(citation)
    db_session.flush()
    note_source = NoteSource(
        workspace_id=workspace.id,
        note_id=note.id,
        source_order=0,
        message_citation_id=citation.id,
        evidence_locator_id=note_locator.id,
        asset_id=asset.id,
        asset_kind_snapshot="pdf",
        asset_title_snapshot="Historical title",
        excerpt_snapshot="Historical excerpt.",
        processing_generation_snapshot=1,
        representation_id_snapshot=old_representation.id,
        parser_version_snapshot=old_representation.generator_version,
        index_version_snapshot=1,
        created_at=now,
    )
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="queued",
        attempt_count=1,
        config_snapshot={"source": "retry"},
        requested_by_user_id=owner.id,
        queued_at=now,
        created_at=now,
    )
    db_session.add_all([note_source, job])
    db_session.flush()
    asset.latest_ingestion_job_id = job.id
    db_session.commit()
    before_citation_locator = serialize_evidence_locator(
        db_session,
        citation.evidence_locator_id,
    ).model_dump()
    before_note_locator = serialize_evidence_locator(
        db_session,
        note_source.evidence_locator_id,
    ).model_dump()
    monkeypatch.setattr("ai_pdf_api.services.ingestion.download_bytes", lambda _key: b"pdf")

    claimed_job_id = claim_next_ingestion_job(db_session)
    process_ingestion_job(
        db_session,
        claimed_job_id,
        ingestion_adapters=static_pdf_adapters([parsed_page(1, "current evidence")]),
    )

    db_session.expire_all()
    refreshed_asset = db_session.get(Asset, asset.id)
    refreshed_citation = db_session.get(MessageCitation, citation.id)
    refreshed_note_source = db_session.get(NoteSource, note_source.id)
    assert refreshed_asset is not None
    assert refreshed_asset.current_processing_generation == 2
    assert refreshed_asset.status == "chunked"
    assert db_session.scalars(
        select(ContentUnit.text_content).where(ContentUnit.asset_id == asset.id)
    ).all() == ["current evidence"]
    assert refreshed_citation is not None and refreshed_note_source is not None
    assert serialize_evidence_locator(
        db_session,
        refreshed_citation.evidence_locator_id,
    ).model_dump() == before_citation_locator
    assert serialize_evidence_locator(
        db_session,
        refreshed_note_source.evidence_locator_id,
    ).model_dump() == before_note_locator
    assert (
        refreshed_citation.asset_title_snapshot,
        refreshed_citation.excerpt_snapshot,
        refreshed_citation.processing_generation_snapshot,
        refreshed_citation.representation_id_snapshot,
        refreshed_citation.index_version_snapshot,
    ) == ("Historical title", "Historical excerpt.", 1, old_representation.id, 1)
    assert (
        refreshed_note_source.asset_title_snapshot,
        refreshed_note_source.excerpt_snapshot,
        refreshed_note_source.processing_generation_snapshot,
        refreshed_note_source.representation_id_snapshot,
        refreshed_note_source.index_version_snapshot,
    ) == ("Historical title", "Historical excerpt.", 1, old_representation.id, 1)


def test_ingestion_worker_rejects_embedding_config_drift(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    asset = create_asset(db_session, workspace=workspace, user=owner, status="uploaded")
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="queued",
        attempt_count=1,
        config_snapshot={
            "embeddingProvider": "ollama",
            "embeddingModel": "qwen3-embedding:0.6b",
            "embeddingDimensions": 1024,
            "embeddingVersion": "embedding-v1",
        },
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.flush()
    asset.latest_ingestion_job_id = job.id
    db_session.commit()

    class DifferentEmbeddingProvider:
        provider = "fake"
        model = "fake-embedding"
        dimensions = 3
        version = "fake-v1"

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0, 0.0] for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            return [1.0, 0.0, 0.0]

    monkeypatch.setattr("ai_pdf_api.services.ingestion.download_bytes", lambda object_key: b"unreachable")
    claimed_job_id = claim_next_ingestion_job(db_session)
    process_ingestion_job(
        db_session,
        claimed_job_id,
        ingestion_adapters=static_pdf_adapters(),
        embedding_provider=DifferentEmbeddingProvider(),
    )

    refreshed_asset = db_session.get(Asset, asset.id)
    refreshed_job = db_session.get(IngestionJob, job.id)
    assert refreshed_asset is not None
    assert refreshed_asset.status == "failed"
    assert refreshed_job is not None
    assert refreshed_job.status == "failed"
    assert refreshed_job.error_code == "embedding_configuration_mismatch"


def test_embedding_failure_does_not_mark_partial_index_ready(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    asset = create_asset(db_session, workspace=workspace, user=owner, status="ready")
    now = datetime.now(UTC)
    chunks = [
        create_pdf_content_unit(
            db_session,
            asset=asset,
            page_number=index,
            text=f"chunk {index}",
        )
        for index in (1, 2)
    ]
    original_embedding = ContentUnitEmbedding(
        workspace_id=workspace.id,
        asset_id=asset.id,
        content_unit_id=chunks[0].id,
        processing_generation=asset.current_processing_generation,
        index_version=chunks[0].index_version,
        is_current=True,
        embedding_space="text",
        provider="fake",
        model="fake-embedding",
        dimensions=3,
        version="fake-v1",
        embedding=[0.0, 1.0, 0.0],
        created_at=now,
    )
    db_session.add(original_embedding)
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="embed_chunks",
        status="queued",
        attempt_count=1,
        config_snapshot={
            "embeddingProvider": "fake",
            "embeddingModel": "fake-embedding",
            "embeddingDimensions": 3,
            "embeddingVersion": "fake-v1",
        },
        requested_by_user_id=owner.id,
        queued_at=now,
        created_at=now,
    )
    db_session.add(job)
    db_session.flush()
    asset.latest_ingestion_job_id = job.id
    db_session.commit()

    class FailingEmbeddingProvider:
        provider = "fake"
        model = "fake-embedding"
        dimensions = 3
        version = "fake-v1"

        def __init__(self) -> None:
            self.calls = 0

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            self.calls += 1
            if self.calls == 1:
                return [[1.0, 0.0, 0.0] for _ in texts]
            raise RuntimeError("provider stopped")

        def embed_query(self, text: str) -> list[float]:
            return [1.0, 0.0, 0.0]

    monkeypatch.setattr("ai_pdf_api.services.ingestion.settings.embedding_batch_size", 1)
    claimed_job_id = claim_next_ingestion_job(db_session)
    process_embedding_job(db_session, claimed_job_id, FailingEmbeddingProvider())

    refreshed_asset = db_session.get(Asset, asset.id)
    refreshed_job = db_session.get(IngestionJob, job.id)
    assert refreshed_asset is not None
    assert refreshed_asset.status == "chunked"
    assert refreshed_job is not None
    assert refreshed_job.status == "failed"
    persisted_embeddings = db_session.scalars(
        select(ContentUnitEmbedding).where(ContentUnitEmbedding.asset_id == asset.id)
    ).all()
    assert [embedding.id for embedding in persisted_embeddings] == [original_embedding.id]
    assert persisted_embeddings[0].is_current is True
    assert persisted_embeddings[0].embedding == [0.0, 1.0, 0.0]


def test_reindex_queues_embed_job_with_embedding_config_snapshot(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    asset = create_asset(db_session, workspace=workspace, user=owner, status="ready")
    create_pdf_content_unit(db_session, asset=asset, page_number=1, text="reindex text")
    db_session.commit()

    monkeypatch.setattr("ai_pdf_api.routers.assets.settings.embedding_provider", "fake")
    monkeypatch.setattr("ai_pdf_api.routers.assets.settings.embedding_model", "fake-embedding")
    monkeypatch.setattr("ai_pdf_api.routers.assets.settings.embedding_dimensions", 3)
    monkeypatch.setattr("ai_pdf_api.routers.assets.settings.embedding_version", "fake-v1")

    response = client.post(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}/reindex",
        headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job"]["jobType"] == "embed_chunks"
    job = db_session.get(IngestionJob, payload["job"]["id"])
    assert job is not None
    assert job.config_snapshot == {
        "source": "reindex",
        "embeddingProvider": "fake",
        "embeddingModel": "fake-embedding",
        "embeddingDimensions": 3,
        "embeddingVersion": "fake-v1",
        "chunkSize": 1200,
    }


def test_ingestion_worker_uses_ocr_for_image_only_pdf(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    asset = create_asset(db_session, workspace=workspace, user=owner, status="uploaded")
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="queued",
        attempt_count=1,
        config_snapshot={"source": "test"},
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.flush()
    asset.latest_ingestion_job_id = job.id
    db_session.commit()

    monkeypatch.setattr("ai_pdf_api.services.ingestion.download_bytes", lambda object_key: b"image-pdf")

    claimed_job_id = claim_next_ingestion_job(db_session)
    assert claimed_job_id == job.id
    process_ingestion_job(
        db_session,
        claimed_job_id,
        ingestion_adapters=static_pdf_adapters([
            parsed_page(
                1,
                "扫描件第一页",
                source_kind="ocr",
                regions=(
                    PageRegionResult(
                        text="扫描件第一页",
                        unit_kind="pdf_ocr_region",
                        x=0.1,
                        y=0.2,
                        width=0.7,
                        height=0.1,
                        char_start=0,
                        char_end=len("扫描件第一页"),
                    ),
                ),
                ocr_blocks=[{"text": "扫描件第一页", "x": 0.1, "y": 0.2, "width": 0.7, "height": 0.1}],
            ),
            parsed_page(2, "扫描件第二页", source_kind="ocr"),
        ]),
    )

    refreshed_asset = db_session.get(Asset, asset.id)
    pages = db_session.scalars(select(PdfPage).where(PdfPage.asset_id == asset.id)).all()
    assert refreshed_asset is not None
    assert refreshed_asset.status == "chunked"
    assert [page.extracted_text for page in pages] == ["扫描件第一页", "扫描件第二页"]
    assert pages[0].legacy_ocr_blocks == [
        {"text": "扫描件第一页", "x": 0.1, "y": 0.2, "width": 0.7, "height": 0.1}
    ]
    assert pages[1].legacy_ocr_blocks == []
    units = db_session.scalars(select(ContentUnit).where(ContentUnit.asset_id == asset.id)).all()
    units_by_page = {
        db_session.get(PdfLocatorDetail, unit.source_locator_id).page_number: unit
        for unit in units
    }
    assert [units_by_page[page].text_content for page in (1, 2)] == [
        "扫描件第一页",
        "扫描件第二页",
    ]
    assert [units_by_page[page].unit_kind for page in (1, 2)] == [
        "pdf_ocr_region",
        "pdf_text_chunk",
    ]
    region_locator = db_session.get(EvidenceLocator, units_by_page[1].source_locator_id)
    assert region_locator is not None and region_locator.locator_kind == "pdf_region"
    detail = db_session.get(PdfLocatorDetail, region_locator.id)
    assert detail is not None
    assert detail.coordinate_space == "pdf_crop_box_normalized_top_left_v1"
    assert detail.crop_x1_points == 612.0
    stored_regions = db_session.scalars(
        select(SpatialLocatorRegion).where(SpatialLocatorRegion.locator_id == region_locator.id)
    ).all()
    assert [(region.x, region.y, region.width, region.height) for region in stored_regions] == [
        (0.1, 0.2, 0.7, 0.1)
    ]


def test_ocr_chunk_with_unlocated_text_falls_back_to_page_evidence(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = create_user(db_session, email="partial-ocr-owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    asset = create_asset(db_session, workspace=workspace, user=owner, status="uploaded")
    now = datetime.now(UTC)
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="queued",
        attempt_count=1,
        config_snapshot={"source": "test"},
        requested_by_user_id=owner.id,
        queued_at=now,
        created_at=now,
    )
    db_session.add(job)
    db_session.flush()
    asset.latest_ingestion_job_id = job.id
    db_session.commit()
    text = "located\nunlocated"
    monkeypatch.setattr("ai_pdf_api.services.ingestion.download_bytes", lambda _key: b"pdf")

    claimed_job_id = claim_next_ingestion_job(db_session)
    process_ingestion_job(
        db_session,
        claimed_job_id,
        ingestion_adapters=static_pdf_adapters([
            parsed_page(
                1,
                text,
                source_kind="ocr",
                regions=(
                    PageRegionResult(
                        text="located",
                        unit_kind="pdf_ocr_region",
                        x=0.1,
                        y=0.2,
                        width=0.3,
                        height=0.1,
                        char_start=0,
                        char_end=len("located"),
                    ),
                ),
            )
        ]),
    )

    unit = db_session.scalar(select(ContentUnit).where(ContentUnit.asset_id == asset.id))
    assert unit is not None
    locator = db_session.get(EvidenceLocator, unit.source_locator_id)
    assert locator is not None and locator.locator_kind == "pdf_page"
    assert unit.unit_kind == "pdf_text_chunk"
    assert db_session.scalars(
        select(SpatialLocatorRegion).where(SpatialLocatorRegion.locator_id == locator.id)
    ).all() == []


def test_ingestion_worker_reclaims_stale_job(db_session: Session) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    asset = create_asset(db_session, workspace=workspace, user=owner, status="parsing")
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="running",
        attempt_count=1,
        config_snapshot={"source": "test"},
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC) - INGESTION_LEASE_TIMEOUT - timedelta(minutes=1),
        started_at=datetime.now(UTC) - INGESTION_LEASE_TIMEOUT - timedelta(minutes=1),
        created_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.flush()
    asset.latest_ingestion_job_id = job.id
    db_session.commit()

    claimed_job_id = claim_next_ingestion_job(db_session)

    refreshed_job = db_session.get(IngestionJob, job.id)
    assert claimed_job_id == job.id
    assert refreshed_job is not None
    assert refreshed_job.status == "running"
    assert refreshed_job.attempt_count == 2
    assert db_session.get(Asset, asset.id).status == "parsing"


def test_ingestion_worker_requires_pdf_adapter(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    asset = create_asset(db_session, workspace=workspace, user=owner, status="uploaded")
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="queued",
        attempt_count=1,
        config_snapshot={"source": "test"},
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.flush()
    asset.latest_ingestion_job_id = job.id
    db_session.commit()

    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.download_bytes",
        lambda _object_key: (_ for _ in ()).throw(AssertionError("download must not run")),
    )
    claimed_job_id = claim_next_ingestion_job(db_session)
    assert claimed_job_id == job.id

    process_ingestion_job(db_session, claimed_job_id)

    refreshed_asset = db_session.get(Asset, asset.id)
    refreshed_job = db_session.get(IngestionJob, job.id)
    assert refreshed_asset is not None
    assert refreshed_asset.status == "failed"
    assert refreshed_job is not None
    assert refreshed_job.status == "failed"
    assert refreshed_job.error_code == "modality_adapter_unavailable"


def test_token_count_estimate_handles_cjk_and_words() -> None:
    assert estimate_token_count("中文文本") == 4
    assert estimate_token_count("hello world") == 2


def test_pdf_region_text_must_match_its_page_character_range() -> None:
    with pytest.raises(ValueError, match="does not match"):
        parsed_page(
            1,
            "secret",
            source_kind="ocr",
            regions=(
                PageRegionResult(
                    text="WRONG",
                    unit_kind="pdf_ocr_region",
                    x=0.1,
                    y=0.2,
                    width=0.3,
                    height=0.1,
                    char_start=0,
                    char_end=6,
                ),
            ),
        )


def test_asset_detail_returns_persisted_page_text(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    asset = create_asset(db_session, workspace=workspace, user=owner, status="chunked")
    create_pdf_content_unit(
        db_session,
        asset=asset,
        page_number=1,
        text="Extracted page text.",
    )
    db_session.commit()

    response = client.get(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}",
        params={"pageNumber": 1},
        headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["asset"]["id"] == asset.id
    assert payload["detail"]["pages"] == [
        {"pageNumber": 1, "text": "Extracted page text.", "charCount": 20, "ocrBlocks": []}
    ]

    missing_page = client.get(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}",
        params={"pageNumber": 2},
        headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id},
    )
    assert missing_page.status_code == 404
    assert missing_page.json()["detail"] == "Asset page not found."


def test_asset_detail_reads_only_current_canonical_page_representation(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="canonical-owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    asset = create_asset(db_session, workspace=workspace, user=owner, status="chunked")
    asset.current_processing_generation = 2
    now = datetime.now(UTC)
    legacy = AssetRepresentation(
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_kind="pdf_text_legacy",
        processing_generation=1,
        generator_version="legacy-v1",
        created_at=now,
    )
    layout = AssetRepresentation(
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_kind="pdf_page_layout",
        processing_generation=2,
        generator_version="layout-v1",
        created_at=now,
    )
    ocr = AssetRepresentation(
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_kind="pdf_ocr",
        processing_generation=2,
        generator_version="ocr-v1",
        created_at=now,
    )
    db_session.add_all([legacy, layout, ocr])
    db_session.flush()
    db_session.add_all(
        [
            PdfPage(
                workspace_id=workspace.id,
                asset_id=asset.id,
                representation_id=legacy.id,
                page_number=1,
                extracted_text="stale generation",
                char_count=16,
                created_at=now,
            ),
            PdfPage(
                workspace_id=workspace.id,
                asset_id=asset.id,
                representation_id=layout.id,
                page_number=1,
                extracted_text="current layout",
                char_count=14,
                created_at=now,
            ),
            PdfPage(
                workspace_id=workspace.id,
                asset_id=asset.id,
                representation_id=ocr.id,
                page_number=1,
                extracted_text="non-canonical OCR row",
                char_count=21,
                created_at=now,
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}",
        params={"pageNumber": 1},
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
        },
    )

    assert response.status_code == 200
    assert response.json()["detail"] == {
        "kind": "pdf",
        "pageCount": 1,
        "pages": [
            {
                "pageNumber": 1,
                "text": "current layout",
                "charCount": 14,
                "ocrBlocks": [],
            }
        ],
    }


def test_asset_detail_returns_persisted_ocr_blocks(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    asset = create_asset(db_session, workspace=workspace, user=owner, status="chunked")
    create_pdf_content_unit(
        db_session,
        asset=asset,
        page_number=1,
        text="扫描文本",
        legacy_ocr_blocks=[
            {"text": "扫描文本", "x": 0.1, "y": 0.2, "width": 0.7, "height": 0.1}
        ],
    )
    db_session.commit()

    response = client.get(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}",
        params={"pageNumber": 1},
        headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id},
    )

    assert response.status_code == 200
    assert response.json()["detail"]["pages"][0]["ocrBlocks"] == [
        {"text": "扫描文本", "x": 0.1, "y": 0.2, "width": 0.7, "height": 0.1}
    ]


def test_delete_asset_requires_owner_and_queues_cleanup(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    member = create_user(db_session, email="member@example.com", name="Member")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    db_session.add(WorkspaceMembership(workspace_id=workspace.id, user_id=member.id, role="member"))
    db_session.commit()
    asset = create_asset(db_session, workspace=workspace, user=owner)
    create_pdf_content_unit(db_session, asset=asset, page_number=1, text="Delete me.")
    db_session.commit()

    forbidden = client.delete(f"/v1/workspaces/{workspace.id}/assets/{asset.id}", headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": member.id})
    assert forbidden.status_code == 403

    deleted = client.delete(f"/v1/workspaces/{workspace.id}/assets/{asset.id}", headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id})
    assert deleted.status_code == 202
    payload = deleted.json()
    assert payload["asset"]["status"] == "deleting"
    assert payload["job"]["jobType"] == "delete_cleanup"
    assert payload["job"]["status"] == "queued"

    refreshed = db_session.get(Asset, asset.id)
    assert refreshed is not None
    assert refreshed.deleted_at is None
    assert refreshed.status == "deleting"
    assert db_session.scalars(select(PdfPage).where(PdfPage.asset_id == asset.id)).all()
    assert db_session.scalars(select(ContentUnit).where(ContentUnit.asset_id == asset.id)).all()

    list_response = client.get(f"/v1/workspaces/{workspace.id}/assets", headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id})
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["status"] == "deleting"


def test_delete_cleanup_worker_removes_asset_artifacts(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = create_user(db_session, email="cleanup-owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    asset = create_asset(db_session, workspace=workspace, user=owner, status="deleting")
    create_pdf_content_unit(db_session, asset=asset, page_number=1, text="Delete me.")
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="delete_cleanup",
        status="queued",
        attempt_count=1,
        config_snapshot={"source": "delete_asset"},
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.flush()
    asset.latest_ingestion_job_id = job.id
    db_session.commit()
    deleted_objects: list[str] = []
    deleted_prefixes: list[str] = []
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.delete_object_if_exists",
        lambda object_key: deleted_objects.append(object_key),
    )
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.delete_objects_with_prefix",
        lambda prefix: deleted_prefixes.append(prefix),
    )

    claimed_job_id = claim_next_ingestion_job(db_session)
    assert claimed_job_id == job.id
    process_ingestion_job(
        db_session,
        claimed_job_id,
        ingestion_adapters=static_pdf_adapters(),
    )

    refreshed_asset = db_session.get(Asset, asset.id)
    refreshed_job = db_session.get(IngestionJob, job.id)
    assert refreshed_asset is not None
    assert refreshed_asset.status == "deleted"
    assert refreshed_asset.deleted_at is not None
    assert refreshed_job is not None
    assert refreshed_job.status == "succeeded"
    assert deleted_objects == [asset.object_key]
    assert deleted_prefixes == [f"workspaces/{workspace.id}/assets/{asset.id}/"]
    assert db_session.scalars(select(PdfPage).where(PdfPage.asset_id == asset.id)).all() == []
    assert db_session.scalars(select(ContentUnit).where(ContentUnit.asset_id == asset.id)).all() == []


def test_delete_cleanup_does_not_resurrect_deleted_asset(db_session: Session) -> None:
    owner = create_user(db_session, email="cleanup-deleted-owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    asset = create_asset(db_session, workspace=workspace, user=owner, status="deleted")
    asset.deleted_at = datetime.now(UTC)
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="delete_cleanup",
        status="queued",
        attempt_count=1,
        config_snapshot={"source": "delete_asset"},
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.flush()
    asset.latest_ingestion_job_id = job.id
    db_session.commit()

    claimed_job_id = claim_next_ingestion_job(db_session)

    assert claimed_job_id is None
    refreshed_asset = db_session.get(Asset, asset.id)
    refreshed_job = db_session.get(IngestionJob, job.id)
    assert refreshed_asset is not None
    assert refreshed_asset.status == "deleted"
    assert refreshed_asset.deleted_at is not None
    assert refreshed_job is not None
    assert refreshed_job.status == "cancelled"


def test_failed_delete_cleanup_can_be_retried(client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    owner = create_user(db_session, email="cleanup-retry-owner@example.com", name="Owner")
    member = create_user(db_session, email="cleanup-retry-member@example.com", name="Member")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    db_session.add(WorkspaceMembership(workspace_id=workspace.id, user_id=member.id, role="member"))
    db_session.commit()
    asset = create_asset(db_session, workspace=workspace, user=owner, status="deleting")
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="delete_cleanup",
        status="queued",
        attempt_count=1,
        config_snapshot={"source": "delete_asset"},
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.flush()
    asset.latest_ingestion_job_id = job.id
    db_session.commit()
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.delete_object_if_exists",
        lambda _object_key: (_ for _ in ()).throw(RuntimeError("storage unavailable")),
    )

    claimed_job_id = claim_next_ingestion_job(db_session)
    assert claimed_job_id == job.id
    process_ingestion_job(
        db_session,
        claimed_job_id,
        ingestion_adapters=static_pdf_adapters(),
    )
    failed_job = db_session.get(IngestionJob, job.id)
    assert failed_job is not None
    assert failed_job.status == "failed"

    forbidden = client.post(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}/delete-retry",
        headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": member.id},
    )
    assert forbidden.status_code == 403

    response = client.post(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}/delete-retry",
        headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["asset"]["status"] == "deleting"
    assert payload["job"]["jobType"] == "delete_cleanup"
    assert payload["job"]["attemptCount"] == 2
    retried_job = db_session.get(IngestionJob, payload["job"]["id"])
    assert retried_job is not None
    assert retried_job.config_snapshot == {"source": "retry_delete"}


def test_retry_failed_asset_creates_new_ingestion_job(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="retry-owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    asset = create_asset(db_session, workspace=workspace, user=owner, status="failed")
    failed_job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="failed",
        attempt_count=2,
        config_snapshot={"source": "initial"},
        error_code="ocr_failed",
        error_message="OCR provider failed.",
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db_session.add(failed_job)
    db_session.flush()
    asset.latest_ingestion_job_id = failed_job.id
    db_session.commit()

    response = client.post(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}/retry",
        headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["asset"]["status"] == "uploaded"
    assert payload["job"]["jobType"] == "ingest"
    assert payload["job"]["status"] == "queued"
    assert payload["job"]["attemptCount"] == 3
    retried_job = db_session.get(IngestionJob, payload["job"]["id"])
    refreshed_asset = db_session.get(Asset, asset.id)
    assert retried_job is not None
    assert retried_job.config_snapshot == {
        "source": "retry",
        "embeddingProvider": "ollama",
        "embeddingModel": "qwen3-embedding:0.6b",
        "embeddingDimensions": 1024,
        "embeddingVersion": "embedding-v1",
        "chunkSize": 1200,
    }
    assert refreshed_asset is not None
    assert refreshed_asset.latest_ingestion_job_id == retried_job.id
    assert refreshed_asset.last_error_code is None
    assert refreshed_asset.last_error_message is None


def test_retry_asset_rejects_a_asset_that_is_not_failed(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="retry-ready-owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Docs")
    asset = create_asset(db_session, workspace=workspace, user=owner, status="ready")

    response = client.post(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}/retry",
        headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Only failed assets can be retried."


def test_split_page_text_honors_workspace_chunk_size() -> None:
    chunks = split_page_text("word " * 300, chunk_size=200)

    assert len(chunks) > 1
    assert all(len(chunk_text) <= 200 for _start, _end, chunk_text in chunks)
