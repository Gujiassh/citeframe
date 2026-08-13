from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_pdf_api.core.settings import settings
from ai_pdf_api.db.base import Base
from ai_pdf_api.db.session import get_db
from ai_pdf_api.modalities.document import (
    DOCUMENT_NORMALIZATION_VERSION,
    DOCUMENT_PARSER_VERSION,
    stable_document_block_id,
    text_sha256,
    validate_markdown_upload_payload,
)
from ai_pdf_api.modalities.evidence import (
    EvidenceContractError,
    clone_evidence_locator,
    evidence_retrieval_key,
    serialize_evidence_locator,
)
from ai_pdf_api.modalities.registry import build_production_registry
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    DocumentBlock,
    DocumentLocatorDetail,
    DocumentNormalizedContent,
    EvidenceLocator,
    User,
    Workspace,
    WorkspaceMembership,
)
from ai_pdf_api.routers.assets import router as assets_router
from ai_pdf_api.schemas.chat import DocumentAnchorLocator, ImageRegionLocator, PdfPageLocator


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def _create_user_workspace(session: Session) -> tuple[User, Workspace]:
    now = datetime.now(UTC)
    user = User(
        email=f"doc-{uuid4().hex}@example.com",
        name="Document Owner",
        password_hash="hashed",
        avatar_url="https://example.com/doc.png",
    )
    session.add(user)
    session.flush()
    workspace = Workspace(
        name="Document Workspace",
        description=None,
        created_by_user_id=user.id,
        created_at=now,
        updated_at=now,
    )
    session.add(workspace)
    session.flush()
    session.add(
        WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role="owner")
    )
    session.commit()
    return user, workspace


def _seed_document_asset(
    session: Session,
    *,
    user: User,
    workspace: Workspace,
    status: str = "ready",
) -> tuple[Asset, AssetRepresentation, EvidenceLocator, DocumentBlock]:
    now = datetime.now(UTC)
    source_bytes = b"# Intro\n\nHello world paragraph.\n"
    source_sha = sha256(source_bytes).hexdigest()
    normalized_text = "Intro\nHello world paragraph.\n"
    block_text = "Hello world paragraph."
    block_text_hash = text_sha256(block_text)
    heading_path = ["Intro"]
    block_id = stable_document_block_id(
        source_sha256=source_sha,
        parser_version=DOCUMENT_PARSER_VERSION,
        block_order=1,
        block_kind="paragraph",
        heading_path=heading_path,
        text_sha256=block_text_hash,
    )
    asset = Asset(
        asset_kind="document",
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        title="Markdown Note",
        source_filename="note.md",
        object_key=f"workspaces/{workspace.id}/assets/{uuid4()}/original.md",
        mime_type="text/markdown",
        byte_size=len(source_bytes),
        source_sha256=source_sha,
        status=status,
        current_processing_generation=1,
        current_index_version=1,
        created_at=now,
        updated_at=now,
    )
    session.add(asset)
    session.flush()
    representation = AssetRepresentation(
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_kind="document_normalized",
        processing_generation=1,
        generator_version=DOCUMENT_PARSER_VERSION,
        content_sha256=text_sha256(normalized_text),
        created_at=now,
    )
    session.add(representation)
    session.flush()
    session.add(
        DocumentNormalizedContent(
            representation_id=representation.id,
            format="markdown",
            parser_version=DOCUMENT_PARSER_VERSION,
            normalization_version=DOCUMENT_NORMALIZATION_VERSION,
            normalized_text=normalized_text,
            content_sha256=text_sha256(normalized_text),
            block_count=2,
        )
    )
    heading_text = "Intro"
    heading_hash = text_sha256(heading_text)
    heading_block_id = stable_document_block_id(
        source_sha256=source_sha,
        parser_version=DOCUMENT_PARSER_VERSION,
        block_order=0,
        block_kind="heading",
        heading_path=heading_path,
        text_sha256=heading_hash,
    )
    heading_block = DocumentBlock(
        id=str(uuid4()),
        representation_id=representation.id,
        block_id=heading_block_id,
        block_order=0,
        block_kind="heading",
        heading_level=1,
        heading_path=heading_path,
        char_start=0,
        char_end=5,
        text_sha256=heading_hash,
        text_content=heading_text,
        normalization_version=DOCUMENT_NORMALIZATION_VERSION,
    )
    paragraph_block = DocumentBlock(
        id=str(uuid4()),
        representation_id=representation.id,
        block_id=block_id,
        block_order=1,
        block_kind="paragraph",
        heading_level=None,
        heading_path=heading_path,
        char_start=6,
        char_end=6 + len(block_text),
        text_sha256=block_text_hash,
        text_content=block_text,
        normalization_version=DOCUMENT_NORMALIZATION_VERSION,
    )
    session.add_all([heading_block, paragraph_block])
    locator = EvidenceLocator(
        id=str(uuid4()),
        workspace_id=workspace.id,
        asset_id=asset.id,
        locator_kind="document_anchor",
        locator_version=1,
        processing_generation_snapshot=1,
        representation_id_snapshot=representation.id,
        created_at=now,
    )
    session.add(locator)
    session.flush()
    session.add(
        DocumentLocatorDetail(
            locator_id=locator.id,
            block_id=block_id,
            block_kind="paragraph",
            heading_path=heading_path,
            char_start=6,
            char_end=6 + len(block_text),
            text_sha256=block_text_hash,
            normalization_version=DOCUMENT_NORMALIZATION_VERSION,
        )
    )
    session.commit()
    return asset, representation, locator, paragraph_block


def test_document_registry_catalog_exact_match() -> None:
    expected = build_production_registry().expected_catalog()
    assert ("document", 1) in expected.enabled_assets
    assert ("document", "document_source", 1) in expected.representations
    assert ("document", "document_normalized", 1) in expected.representations
    assert ("document", "document_block", 1) in expected.content_units
    assert ("document", "document_text_chunk", 1) in expected.content_units
    assert ("document_anchor", 1, "record") in expected.locators
    assert ("text", 1) in expected.embedding_spaces


def test_document_anchor_schema_accepts_single_range() -> None:
    locator = DocumentAnchorLocator.model_validate(
        {
            "kind": "document_anchor",
            "version": 1,
            "blockId": "docblk_abc",
            "blockKind": "paragraph",
            "headingPath": ["Section", "Subsection"],
            "charStart": 10,
            "charEnd": 20,
            "textSha256": "a" * 64,
            "normalizationVersion": DOCUMENT_NORMALIZATION_VERSION,
        }
    )
    assert locator.charEnd == 20
    assert locator.headingPath == ["Section", "Subsection"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"charEnd": 5, "charStart": 10},
        {"headingPath": [""]},
        {"headingPath": [1]},
        {"blockKind": "css_selector"},
        {"normalizationVersion": "document-normalization-v2"},
        {"version": 2},
        {"textSha256": "not-a-hash"},
    ],
)
def test_document_anchor_schema_rejects_invalid_payloads(overrides: dict) -> None:
    payload = {
        "kind": "document_anchor",
        "version": 1,
        "blockId": "docblk_abc",
        "blockKind": "paragraph",
        "headingPath": ["Section"],
        "charStart": 10,
        "charEnd": 20,
        "textSha256": "a" * 64,
        "normalizationVersion": DOCUMENT_NORMALIZATION_VERSION,
    }
    payload.update(overrides)
    with pytest.raises((ValidationError, ValueError)):
        DocumentAnchorLocator.model_validate(payload)


def test_document_locator_serialize_clone_and_fail_closed() -> None:
    session = _session()
    user, workspace = _create_user_workspace(session)
    asset, representation, locator, block = _seed_document_asset(
        session, user=user, workspace=workspace
    )

    serialized = serialize_evidence_locator(session, locator.id)
    assert serialized.model_dump() == {
        "kind": "document_anchor",
        "version": 1,
        "blockId": block.block_id,
        "blockKind": "paragraph",
        "headingPath": ["Intro"],
        "charStart": block.char_start,
        "charEnd": block.char_end,
        "textSha256": block.text_sha256,
        "normalizationVersion": DOCUMENT_NORMALIZATION_VERSION,
    }

    cloned = clone_evidence_locator(session, locator.id, created_at=datetime.now(UTC))
    session.commit()
    assert cloned.id != locator.id
    assert serialize_evidence_locator(session, cloned.id).model_dump() == serialized.model_dump()

    key = evidence_retrieval_key(
        session,
        locator,
        workspace_id=workspace.id,
        asset_id=asset.id,
        processing_generation=1,
        representation_id=representation.id,
    )
    assert key == (
        asset.id,
        f"document_anchor:{block.block_id}:{block.char_start}:{block.char_end}",
    )

    detail = session.get(DocumentLocatorDetail, locator.id)
    assert detail is not None
    detail.heading_path = {"bad": "shape"}  # unconstrained JSON is not accepted
    session.commit()
    with pytest.raises(EvidenceContractError, match="heading_path"):
        serialize_evidence_locator(session, locator.id)

    detail.heading_path = ["Intro"]
    detail.text_sha256 = "a" * 64  # plausible shape, wrong content
    session.commit()
    with pytest.raises(EvidenceContractError, match="text_sha256"):
        serialize_evidence_locator(session, locator.id)

    detail.text_sha256 = block.text_sha256
    detail.char_end = block.char_end + 5
    session.commit()
    with pytest.raises(EvidenceContractError, match="outside the stored block"):
        serialize_evidence_locator(session, locator.id)

    detail.char_end = block.char_end
    session.get(DocumentBlock, block.id).text_content = "tampered"
    session.commit()
    with pytest.raises(EvidenceContractError, match="text_content|text_sha256"):
        serialize_evidence_locator(session, locator.id)

    # restore block text, then corrupt content_sha256 on normalized content
    session.get(DocumentBlock, block.id).text_content = block.text_content
    normalized = session.get(DocumentNormalizedContent, representation.id)
    assert normalized is not None
    normalized.content_sha256 = "a" * 64
    session.commit()
    with pytest.raises(EvidenceContractError, match="content_sha256|normalized content"):
        serialize_evidence_locator(session, locator.id)

    locator.locator_version = 2
    session.commit()
    with pytest.raises(EvidenceContractError, match="Unsupported locator version"):
        serialize_evidence_locator(session, locator.id)


def test_document_locator_rejects_unknown_kind_for_pdf_image_union() -> None:
    # Existing PDF/Image DTO still validates; document is additive via discriminator.
    PdfPageLocator.model_validate({"kind": "pdf_page", "version": 1, "pageNumber": 1})
    ImageRegionLocator.model_validate(
        {
            "kind": "image_region",
            "version": 1,
            "coordinateSpace": "image_normalized_top_left_v1",
            "widthPixels": 10,
            "heightPixels": 10,
            "orientationApplied": True,
            "regions": [{"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}],
        }
    )


def test_document_detail_and_normalized_content_authorization() -> None:
    session = _session()
    user, workspace = _create_user_workspace(session)
    outsider = User(
        email=f"outsider-{uuid4().hex}@example.com",
        name="Outsider",
        password_hash="hashed",
        avatar_url="https://example.com/out.png",
    )
    session.add(outsider)
    session.commit()
    asset, representation, _locator, _block = _seed_document_asset(
        session, user=user, workspace=workspace
    )

    app = FastAPI()
    app.include_router(assets_router)

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    ok = client.get(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": user.id,
        },
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["detail"]["kind"] == "document"
    assert body["detail"]["format"] == "markdown"
    assert body["detail"]["blockCount"] == 2
    assert body["detail"]["parserVersion"] == DOCUMENT_PARSER_VERSION
    assert body["detail"]["normalizationVersion"] == DOCUMENT_NORMALIZATION_VERSION
    assert body["detail"]["representationId"] == representation.id
    assert body["detail"]["headings"][0]["text"] == "Intro"
    assert body["detail"]["headings"][0]["level"] == 1

    content = client.get(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}/representations/{representation.id}/content",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": user.id,
        },
    )
    assert content.status_code == 200
    content_body = content.json()
    assert content_body["assetId"] == asset.id
    assert content_body["representationId"] == representation.id
    assert content_body["processingGeneration"] == 1
    assert content_body["normalizedText"].startswith("Intro")
    assert len(content_body["blocks"]) == 2
    assert content_body["blocks"][0]["blockKind"] == "heading"
    assert content_body["blocks"][0]["headingLevel"] == 1
    assert content_body["blocks"][1]["blockKind"] == "paragraph"
    assert content_body["blocks"][1]["headingLevel"] is None

    forbidden = client.get(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}/representations/{representation.id}/content",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": outsider.id,
        },
    )
    assert forbidden.status_code in {403, 404}

    # Deleted source is not accessible via asset detail/content endpoints.
    asset.deleted_at = datetime.now(UTC)
    asset.status = "deleted"
    session.commit()
    deleted = client.get(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": user.id,
        },
    )
    assert deleted.status_code == 404
    deleted_content = client.get(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}/representations/{representation.id}/content",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": user.id,
        },
    )
    assert deleted_content.status_code == 404


def test_document_upload_session_accepts_markdown_mime() -> None:
    session = _session()
    user, workspace = _create_user_workspace(session)
    app = FastAPI()
    app.include_router(assets_router)

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    response = client.post(
        f"/v1/workspaces/{workspace.id}/assets/upload-session",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": user.id,
        },
        json={
            "sourceFilename": "notes.md",
            "mimeType": "text/markdown",
            "byteSize": 32,
            "title": "Notes",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["asset"]["kind"] == "document"
    assert payload["asset"]["mimeType"] == "text/markdown"
    assert payload["upload"]["headers"]["Content-Type"] == "text/markdown"

    # HTML is production-enabled at S0; reject an unknown MIME instead.
    rejected = client.post(
        f"/v1/workspaces/{workspace.id}/assets/upload-session",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": user.id,
        },
        json={
            "sourceFilename": "blob.bin",
            "mimeType": "application/x-unknown-blob",
            "byteSize": 32,
        },
    )
    assert rejected.status_code == 422


def test_document_second_put_rejects_source_identity_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session()
    user, workspace = _create_user_workspace(session)
    app = FastAPI()
    app.include_router(assets_router)

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    original_bytes = b"# Original markdown source v1\n"
    replacement_bytes = b"# Replaced markdown source v2\n"
    assert len(original_bytes) == len(replacement_bytes)
    assert original_bytes != replacement_bytes
    original_sha = sha256(original_bytes).hexdigest()
    uploaded_payloads: list[bytes] = []
    uploaded_objects: dict[str, bytes] = {}

    def capture_upload(object_key: str, payload, length: int, content_type: str) -> None:
        del content_type
        body = payload.read(length)
        uploaded_payloads.append(body)
        uploaded_objects[object_key] = body

    monkeypatch.setattr("ai_pdf_api.routers.assets.upload_stream", capture_upload)
    monkeypatch.setattr(
        "ai_pdf_api.routers.assets.download_bytes",
        lambda object_key: uploaded_objects[object_key],
    )
    monkeypatch.setattr("ai_pdf_api.routers.assets.object_exists", lambda object_key: True)

    client = TestClient(app)
    headers = {
        "x-ai-pdf-internal-token": settings.api_internal_token,
        "x-user-id": user.id,
    }
    session_response = client.post(
        f"/v1/workspaces/{workspace.id}/assets/upload-session",
        headers=headers,
        json={
            "sourceFilename": "notes.md",
            "mimeType": "text/markdown",
            "byteSize": len(original_bytes),
            "title": "Notes",
        },
    )
    assert session_response.status_code == 201, session_response.text
    upload_session = session_response.json()
    asset_id = upload_session["asset"]["id"]
    object_key = upload_session["upload"]["objectKey"]

    first_put = client.put(
        f"/v1/workspaces/{workspace.id}/assets/{asset_id}/upload",
        headers={**headers, "content-type": "text/markdown"},
        params={"objectKey": object_key},
        content=original_bytes,
    )
    assert first_put.status_code == 204

    asset = session.get(Asset, asset_id)
    assert asset is not None
    assert asset.status == "pending_upload"
    assert asset.source_sha256 == original_sha
    assert uploaded_payloads == [original_bytes]

    second_put = client.put(
        f"/v1/workspaces/{workspace.id}/assets/{asset_id}/upload",
        headers={**headers, "content-type": "text/markdown"},
        params={"objectKey": object_key},
        content=replacement_bytes,
    )
    assert second_put.status_code == 409
    assert second_put.json()["detail"] == "Asset source object is immutable after upload."

    session.expire_all()
    asset = session.get(Asset, asset_id)
    assert asset is not None
    assert asset.status == "pending_upload"
    assert asset.source_sha256 == original_sha
    assert asset.object_key == object_key
    assert uploaded_payloads == [original_bytes]

    finalize_response = client.post(
        f"/v1/workspaces/{workspace.id}/assets/{asset_id}/finalize-upload",
        headers=headers,
        json={"objectKey": object_key},
    )
    assert finalize_response.status_code == 200, finalize_response.text
    finalize_payload = finalize_response.json()
    assert finalize_payload["asset"]["status"] == "uploaded"
    assert finalize_payload["job"]["jobType"] == "ingest"
    assert finalize_payload["job"]["status"] == "queued"

    session.expire_all()
    asset = session.get(Asset, asset_id)
    assert asset is not None
    assert asset.status == "uploaded"
    assert asset.source_sha256 == original_sha
    assert asset.latest_ingestion_job_id == finalize_payload["job"]["id"]


@pytest.mark.parametrize(
    "payload",
    [
        b"# ok markdown\n",
        b"plain text without nulls",
    ],
)
def test_validate_markdown_upload_payload_accepts_utf8_text(payload: bytes) -> None:
    validate_markdown_upload_payload(payload)


@pytest.mark.parametrize(
    "payload",
    [
        b"%PDF-1.7 trailing markdown",
        b"\x89PNG\r\n\x1a\n" + b"# not really markdown",
        b"PK\x03\x04" + b"0" * 32,  # ZIP beyond 16-byte header
        b"\x7fELF" + b"0" * 32,  # ELF beyond 16-byte header
        b"# title\n" + b"\x00" + b"later null",
        b"\xff\xfe invalid utf-8",
    ],
)
def test_validate_markdown_upload_payload_rejects_binary_and_invalid_utf8(
    payload: bytes,
) -> None:
    with pytest.raises(ValueError):
        validate_markdown_upload_payload(payload)


def test_stable_block_id_is_deterministic() -> None:
    first = stable_document_block_id(
        source_sha256="a" * 64,
        parser_version=DOCUMENT_PARSER_VERSION,
        block_order=0,
        block_kind="heading",
        heading_path=["A"],
        text_sha256="b" * 64,
    )
    second = stable_document_block_id(
        source_sha256="a" * 64,
        parser_version=DOCUMENT_PARSER_VERSION,
        block_order=0,
        block_kind="heading",
        heading_path=["A"],
        text_sha256="b" * 64,
    )
    assert first == second
    assert first.startswith("docblk_")


def test_document_modality_downgrade_refuses_populated_rows() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "f9a1b2c3d4e5_enable_document_modality.py"
    )
    spec = spec_from_file_location("document_modality_migration", migration_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    class _Result:
        def __init__(self, value: int) -> None:
            self._value = value

        def scalar_one(self) -> int:
            return self._value

    class _Connection:
        def __init__(self, counts: dict[str, int]) -> None:
            self.counts = counts

        def execute(self, statement):  # noqa: ANN001
            sql = str(statement)
            for key, value in self.counts.items():
                if key in sql:
                    return _Result(value)
            return _Result(0)

    module.assert_document_modality_downgrade_safe(
        _Connection(
            {
                "FROM assets": 0,
                "FROM asset_representations": 0,
                "FROM content_units": 0,
                "FROM evidence_locators": 0,
                "FROM document_normalized_contents": 0,
                "FROM document_blocks": 0,
                "FROM document_locator_details": 0,
            }
        )
    )
    with pytest.raises(RuntimeError, match="irreversible document modality downgrade"):
        module.assert_document_modality_downgrade_safe(
            _Connection({"FROM assets": 1})
        )
    with pytest.raises(RuntimeError, match="irreversible document modality downgrade"):
        module.assert_document_modality_downgrade_safe(
            _Connection(
                {
                    "FROM assets": 0,
                    "FROM evidence_locators": 2,
                }
            )
        )


def test_document_normalized_content_rejects_corrupt_rows() -> None:
    session = _session()
    user, workspace = _create_user_workspace(session)
    asset, representation, _locator, block = _seed_document_asset(
        session, user=user, workspace=workspace
    )
    app = FastAPI()
    app.include_router(assets_router)

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    headers = {
        "x-ai-pdf-internal-token": settings.api_internal_token,
        "x-user-id": user.id,
    }
    content_url = (
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}/representations/"
        f"{representation.id}/content"
    )

    ok = client.get(content_url, headers=headers)
    assert ok.status_code == 200

    normalized = session.get(DocumentNormalizedContent, representation.id)
    assert normalized is not None
    normalized.content_sha256 = "b" * 64
    session.commit()
    corrupt_hash = client.get(content_url, headers=headers)
    assert corrupt_hash.status_code == 500
    assert "corrupt" in corrupt_hash.json()["detail"].lower()

    normalized.content_sha256 = text_sha256(normalized.normalized_text)
    session.get(DocumentBlock, block.id).text_content = "not-the-substring"
    session.commit()
    corrupt_block = client.get(content_url, headers=headers)
    assert corrupt_block.status_code == 500
    assert "corrupt" in corrupt_block.json()["detail"].lower()

    session.get(DocumentBlock, block.id).text_content = block.text_content
    session.get(DocumentBlock, block.id).char_end = block.char_end + 1
    session.commit()
    corrupt_range = client.get(content_url, headers=headers)
    assert corrupt_range.status_code == 500
    assert "corrupt" in corrupt_range.json()["detail"].lower()



def test_document_block_helper_rejects_heading_level_corruption() -> None:
    from types import SimpleNamespace
    from ai_pdf_api.modalities.document import (
        DocumentIntegrityError,
        validate_document_block_against_text,
        validate_document_normalized_content,
    )

    normalized_text = "Intro\nHello"
    content = SimpleNamespace(
        format="markdown",
        parser_version=DOCUMENT_PARSER_VERSION,
        normalization_version=DOCUMENT_NORMALIZATION_VERSION,
        normalized_text=normalized_text,
        content_sha256=text_sha256(normalized_text),
        block_count=1,
    )
    assert validate_document_normalized_content(content) == normalized_text

    paragraph = SimpleNamespace(
        block_id="docblk_x",
        block_order=0,
        block_kind="paragraph",
        heading_level=2,  # non-heading must not pretend a level
        heading_path=["Intro"],
        char_start=6,
        char_end=11,
        text_sha256=text_sha256("Hello"),
        text_content="Hello",
        normalization_version=DOCUMENT_NORMALIZATION_VERSION,
    )
    with pytest.raises(DocumentIntegrityError, match="heading_level"):
        validate_document_block_against_text(paragraph, normalized_text=normalized_text)

    heading = SimpleNamespace(
        block_id="docblk_h",
        block_order=0,
        block_kind="heading",
        heading_level=None,
        heading_path=["Intro"],
        char_start=0,
        char_end=5,
        text_sha256=text_sha256("Intro"),
        text_content="Intro",
        normalization_version=DOCUMENT_NORMALIZATION_VERSION,
    )
    with pytest.raises(DocumentIntegrityError, match="heading_level"):
        validate_document_block_against_text(heading, normalized_text=normalized_text)
