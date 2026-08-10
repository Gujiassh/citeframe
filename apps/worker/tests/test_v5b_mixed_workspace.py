"""Cross-layer V5-B mixed workspace / document lifecycle integration tests.

Ownership: B-INT-MIXED only. Uses production worker INGESTION_ADAPTERS (real
DocumentIngestionAdapter) plus shared claim/process/delete/retrieval seams and
an in-memory object store (no MinIO).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_pdf_api.db.base import Base
from ai_pdf_api.modalities.document import (
    DOCUMENT_NORMALIZATION_VERSION,
    DOCUMENT_PARSER_VERSION,
)
from ai_pdf_api.modalities.evidence import clone_evidence_locator
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ChatMessage,
    ChatThread,
    ContentUnit,
    ContentUnitEmbedding,
    DocumentBlock,
    DocumentLocatorDetail,
    DocumentNormalizedContent,
    EvidenceLocator,
    ImageLocatorDetail,
    ImageRepresentationGeometry,
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
from ai_pdf_api.routers.assets import build_ingest_job, delete_asset
from ai_pdf_api.routers.chat import to_citation
from ai_pdf_api.services.capabilities import embedding_profile_snapshot_fields
from ai_pdf_api.services.chat import active_message_path
from ai_pdf_api.services.ingestion import (
    claim_next_ingestion_job,
    process_delete_cleanup,
    process_ingestion_job,
)
from ai_pdf_api.services.notes import _to_source_dto_with_db
from ai_pdf_api.services.retrieval import retrieve_content, retrieve_lexical_content
from ai_pdf_worker.document_ingestion import DocumentIngestionAdapter
from ai_pdf_worker.main import INGESTION_ADAPTERS

ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = ROOT / "docs/fixtures/document-modality"
SOURCE_PATH = FIXTURE_DIR / "markdown-note.md"
FIXTURE_PATH = FIXTURE_DIR / "markdown-note.fixture.json"
GENERATOR_PATH = FIXTURE_DIR / "generate_fixture.py"
RESTORE_SCRIPT = ROOT / "apps/worker/scripts/v5b_document_restore_acceptance.py"
BACKUP_SCRIPT = ROOT / "infra/scripts/backup-deployment.sh"
RESTORE_DEPLOY_SCRIPT = ROOT / "infra/scripts/restore-deployment.sh"

# Align the deterministic test embedding provider with production job snapshots.
_EMBEDDING_PROFILE = embedding_profile_snapshot_fields()


class StaticEmbeddingProvider:
    provider = str(_EMBEDDING_PROFILE["embeddingProvider"])
    model = str(_EMBEDDING_PROFILE["embeddingModel"])
    dimensions = int(_EMBEDDING_PROFILE["embeddingDimensions"])
    version = str(_EMBEDDING_PROFILE["embeddingVersion"])
    config_fingerprint = str(_EMBEDDING_PROFILE["embeddingProfileFingerprint"])

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        dims = self.dimensions
        return [[float(i + 1)] + [0.0] * (dims - 1) for i, _ in enumerate(texts)]

    def embed_query(self, _text: str) -> list[float]:
        return [1.0] + [0.0] * (self.dimensions - 1)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True, expire_on_commit=False
    )()


def _patch_store(
    monkeypatch: pytest.MonkeyPatch,
    objects: dict[str, bytes],
    *,
    upload_error: Exception | None = None,
) -> None:
    def download(key: str) -> bytes:
        return objects[key]

    def upload(key: str, payload: bytes, _content_type: str) -> None:
        objects[key] = payload
        if upload_error is not None:
            raise upload_error

    def delete_one(key: str) -> None:
        objects.pop(key, None)

    def delete_prefix(prefix: str) -> None:
        for key in [k for k in objects if k.startswith(prefix)]:
            objects.pop(key, None)

    monkeypatch.setattr("ai_pdf_api.services.ingestion.download_bytes", download)
    monkeypatch.setattr("ai_pdf_api.services.ingestion.upload_bytes", upload)
    monkeypatch.setattr("ai_pdf_api.services.ingestion.delete_object_if_exists", delete_one)
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.delete_objects_with_prefix", delete_prefix
    )


def _user_workspace(db: Session, *, label: str = "mixed") -> tuple[User, Workspace]:
    now = datetime.now(UTC)
    user = User(
        email=f"{label}-{uuid4().hex}@example.com",
        name=f"{label} owner",
        password_hash="hashed",
        avatar_url=f"https://example.com/{label}.png",
    )
    db.add(user)
    db.flush()
    workspace = Workspace(
        name=f"{label} workspace",
        description=None,
        created_by_user_id=user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role="owner"))
    db.commit()
    return user, workspace


def _queue_document(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    objects: dict[str, bytes],
    payload: bytes | None = None,
    title: str = "Markdown Note",
    source: str = "upload",
    asset: Asset | None = None,
) -> tuple[Asset, IngestionJob]:
    """Queue an ingest job via production build_ingest_job.

    Source identity is immutable after asset creation: existing assets may only be
    reprocessed against the same object_key/byte_size/source_sha256/object bytes.
    """
    now = datetime.now(UTC)
    if asset is None:
        source_bytes = SOURCE_PATH.read_bytes() if payload is None else payload
        asset_id = str(uuid4())
        object_key = f"workspaces/{workspace.id}/assets/{asset_id}/original.md"
        asset = Asset(
            id=asset_id,
            workspace_id=workspace.id,
            created_by_user_id=user.id,
            asset_kind="document",
            title=title,
            source_filename=SOURCE_PATH.name,
            object_key=object_key,
            mime_type="text/markdown",
            byte_size=len(source_bytes),
            source_sha256=sha256(source_bytes).hexdigest(),
            status="uploaded",
            current_processing_generation=1,
            current_index_version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(asset)
        db.flush()
        objects[object_key] = source_bytes
    else:
        if payload is not None:
            raise ValueError(
                "existing asset source identity is immutable; "
                "do not replace object_key/source_sha256/byte_size/object bytes"
            )
        # Reprocess only: preserve source identity and object bytes.
        # After delete cleanup the source object may already be gone; late queued
        # jobs must still be cancellable without recreating source identity.
        if asset.deleted_at is None and asset.object_key not in objects:
            raise ValueError("existing asset source object is missing from the object store")
        if asset.deleted_at is None:
            asset.status = "uploaded"
        asset.updated_at = now
    job = build_ingest_job(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        asset_kind="document",
        user_id=user.id,
        chunk_size=workspace.chunk_size,
        source=source,
        now=now,
    )
    db.add(job)
    db.flush()
    asset.latest_ingestion_job_id = job.id
    db.commit()
    return asset, job


def _claim_process(
    db: Session,
    objects: dict[str, bytes],
    monkeypatch: pytest.MonkeyPatch,
    *,
    upload_error: Exception | None = None,
    job_id: str | None = None,
) -> str | None:
    _patch_store(monkeypatch, objects, upload_error=upload_error)
    resolved = job_id if job_id is not None else claim_next_ingestion_job(db)
    if resolved is None:
        return None
    process_ingestion_job(
        db,
        resolved,
        ingestion_adapters=INGESTION_ADAPTERS,
        embedding_provider=StaticEmbeddingProvider(),
    )
    return resolved


def _ready_document(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    objects: dict[str, bytes],
    monkeypatch: pytest.MonkeyPatch,
    title: str = "Markdown Note",
) -> Asset:
    asset, _ = _queue_document(
        db, user=user, workspace=workspace, objects=objects, title=title
    )
    assert _claim_process(db, objects, monkeypatch) is not None
    db.refresh(asset)
    assert asset.status == "ready"
    return asset


def _seed_pdf(db: Session, *, user: User, workspace: Workspace) -> Asset:
    now = datetime.now(UTC)
    asset = Asset(
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        asset_kind="pdf",
        title="PDF Fixture",
        source_filename="fixture.pdf",
        object_key=f"workspaces/{workspace.id}/assets/{uuid4()}/original.pdf",
        mime_type="application/pdf",
        byte_size=32,
        source_sha256="p" * 64,
        status="ready",
        current_processing_generation=1,
        current_index_version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(asset)
    db.flush()
    rep = AssetRepresentation(
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_kind="pdf_text_legacy",
        processing_generation=1,
        generator_version="pdf-parser-v1",
        created_at=now,
    )
    db.add(rep)
    db.flush()
    page = PdfPage(
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_id=rep.id,
        page_number=1,
        extracted_text="Hello world from pdf mixed evidence",
        char_count=35,
        legacy_ocr_blocks=[],
        created_at=now,
    )
    db.add(page)
    db.flush()
    locator = EvidenceLocator(
        workspace_id=workspace.id,
        asset_id=asset.id,
        locator_kind="pdf_page",
        locator_version=1,
        processing_generation_snapshot=1,
        representation_id_snapshot=rep.id,
        created_at=now,
    )
    db.add(locator)
    db.flush()
    db.add(PdfLocatorDetail(locator_id=locator.id, page_id=page.id, page_number=1))
    db.add(
        ContentUnit(
            workspace_id=workspace.id,
            asset_id=asset.id,
            representation_id=rep.id,
            source_locator_id=locator.id,
            unit_kind="pdf_text_chunk",
            unit_order=0,
            text_content="Hello world from pdf mixed evidence",
            token_count=6,
            index_version=1,
            created_at=now,
        )
    )
    db.commit()
    return asset


def _seed_image(db: Session, *, user: User, workspace: Workspace) -> Asset:
    now = datetime.now(UTC)
    asset = Asset(
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        asset_kind="image",
        title="Image Fixture",
        source_filename="fixture.png",
        object_key=f"workspaces/{workspace.id}/assets/{uuid4()}/original.png",
        mime_type="image/png",
        byte_size=32,
        source_sha256="i" * 64,
        status="ready",
        current_processing_generation=1,
        current_index_version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(asset)
    db.flush()
    oriented = AssetRepresentation(
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_kind="image_oriented",
        processing_generation=1,
        generator_version="pillow-canonical-png-v1",
        object_key=(
            f"workspaces/{workspace.id}/assets/{asset.id}/"
            "representations/1/image-oriented.png"
        ),
        content_sha256="o" * 64,
        created_at=now,
    )
    caption = AssetRepresentation(
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_kind="image_caption",
        processing_generation=1,
        generator_version="image-caption-v1",
        created_at=now,
    )
    db.add_all([oriented, caption])
    db.flush()
    db.add(
        ImageRepresentationGeometry(
            representation_id=oriented.id,
            workspace_id=workspace.id,
            asset_id=asset.id,
            width_pixels=1200,
            height_pixels=800,
            orientation_applied=True,
        )
    )
    locator = EvidenceLocator(
        workspace_id=workspace.id,
        asset_id=asset.id,
        locator_kind="image_region",
        locator_version=1,
        processing_generation_snapshot=1,
        representation_id_snapshot=caption.id,
        created_at=now,
    )
    db.add(locator)
    db.flush()
    db.add(
        ImageLocatorDetail(
            locator_id=locator.id,
            coordinate_space="image_normalized_top_left_v1",
            width_pixels=1200,
            height_pixels=800,
            orientation_applied=True,
        )
    )
    db.add(
        SpatialLocatorRegion(
            locator_id=locator.id, region_order=0, x=0.1, y=0.2, width=0.3, height=0.4
        )
    )
    db.add(
        ContentUnit(
            workspace_id=workspace.id,
            asset_id=asset.id,
            representation_id=caption.id,
            source_locator_id=locator.id,
            unit_kind="image_caption",
            unit_order=0,
            text_content="Hello world from image mixed evidence",
            token_count=6,
            index_version=1,
            created_at=now,
        )
    )
    db.commit()
    return asset


def _primary_unit(
    db: Session, asset: Asset
) -> tuple[ContentUnit, EvidenceLocator, AssetRepresentation]:
    unit = db.scalar(
        select(ContentUnit)
        .where(
            ContentUnit.asset_id == asset.id,
            ContentUnit.unit_kind == "document_text_chunk",
        )
        .order_by(ContentUnit.unit_order)
    )
    assert unit is not None
    locator = db.get(EvidenceLocator, unit.source_locator_id)
    rep = db.get(AssetRepresentation, unit.representation_id)
    assert locator is not None and rep is not None
    return unit, locator, rep


def _citation_note(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    asset: Asset,
    locator: EvidenceLocator,
    representation: AssetRepresentation,
    excerpt: str,
) -> tuple[MessageCitation, NoteSource]:
    now = datetime.now(UTC)
    citation_locator = clone_evidence_locator(db, locator.id, created_at=now)
    note_locator = clone_evidence_locator(db, citation_locator.id, created_at=now)
    thread = ChatThread(
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        title="Document history",
        last_message_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(thread)
    db.flush()
    message = ChatMessage(
        workspace_id=workspace.id,
        thread_id=thread.id,
        role="assistant",
        content="Document answer.",
        status="completed",
        created_at=now,
    )
    note = Note(
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        updated_by_user_id=user.id,
        title="Document note",
        body_md=excerpt,
        created_at=now,
        updated_at=now,
    )
    db.add_all([message, note])
    db.flush()
    # Production chat listing walks thread.active_message_id; leave it unset and
    # active_message_path raises invalid_message_graph, so browser E2E cannot
    # render the Citation created by this fixture.
    thread.active_message_id = message.id
    citation = MessageCitation(
        workspace_id=workspace.id,
        message_id=message.id,
        citation_index=0,
        evidence_locator_id=citation_locator.id,
        asset_id=asset.id,
        asset_kind_snapshot="document",
        asset_title_snapshot=asset.title,
        excerpt_snapshot=excerpt,
        processing_generation_snapshot=locator.processing_generation_snapshot,
        representation_id_snapshot=representation.id,
        parser_version_snapshot=DOCUMENT_PARSER_VERSION,
        index_version_snapshot=asset.current_index_version,
        created_at=now,
    )
    db.add(citation)
    db.flush()
    note_source = NoteSource(
        workspace_id=workspace.id,
        note_id=note.id,
        source_order=0,
        message_citation_id=citation.id,
        evidence_locator_id=note_locator.id,
        asset_id=asset.id,
        asset_kind_snapshot="document",
        asset_title_snapshot=asset.title,
        excerpt_snapshot=excerpt,
        processing_generation_snapshot=locator.processing_generation_snapshot,
        representation_id_snapshot=representation.id,
        parser_version_snapshot=DOCUMENT_PARSER_VERSION,
        index_version_snapshot=asset.current_index_version,
        created_at=now,
    )
    db.add(note_source)
    db.commit()
    db.refresh(thread)
    path = active_message_path(db, thread)
    assert [item.id for item in path] == [message.id]
    assert path[0].id == citation.message_id
    return citation, note_source


def _count(db: Session, model, **filters) -> int:
    statement = select(func.count()).select_from(model)
    for key, value in filters.items():
        statement = statement.where(getattr(model, key) == value)
    return int(db.scalar(statement) or 0)


def _normalized_key(asset: Asset, generation: int) -> str:
    return (
        f"workspaces/{asset.workspace_id}/assets/{asset.id}/"
        f"representations/{generation}/document-normalized.txt"
    )


def test_document_ingestion_uses_real_adapter_and_retrieval_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert isinstance(INGESTION_ADAPTERS.get("document"), DocumentIngestionAdapter)
    fixture = _json(FIXTURE_PATH)
    db = _session()
    objects: dict[str, bytes] = {}
    user, workspace = _user_workspace(db, label="ingest")
    asset = _ready_document(
        db, user=user, workspace=workspace, objects=objects, monkeypatch=monkeypatch
    )
    job = db.scalar(
        select(IngestionJob)
        .where(IngestionJob.asset_id == asset.id)
        .order_by(IngestionJob.created_at.desc())
    )
    assert job is not None and job.status == "succeeded"
    assert job.config_snapshot["embeddingProfileFingerprint"] == (
        StaticEmbeddingProvider.config_fingerprint
    )
    assert asset.status == "ready" and asset.current_processing_generation == 1

    reps = db.scalars(
        select(AssetRepresentation).where(AssetRepresentation.asset_id == asset.id)
    ).all()
    assert {r.representation_kind for r in reps} == {
        "document_source",
        "document_normalized",
    }
    assert len(reps) == 2
    normalized = next(r for r in reps if r.representation_kind == "document_normalized")
    content = db.get(DocumentNormalizedContent, normalized.id)
    assert content is not None
    assert "workspace_id" not in DocumentNormalizedContent.__table__.c
    assert "asset_id" not in DocumentNormalizedContent.__table__.c
    assert content.normalized_text == fixture["normalizedText"]
    assert content.content_sha256 == fixture["normalizedContentSha256"]

    blocks = db.scalars(
        select(DocumentBlock)
        .where(DocumentBlock.representation_id == normalized.id)
        .order_by(DocumentBlock.block_order)
    ).all()
    assert "workspace_id" not in DocumentBlock.__table__.c
    assert "asset_id" not in DocumentBlock.__table__.c
    assert len(blocks) == len(fixture["blocks"])
    for block, expected in zip(blocks, fixture["blocks"], strict=True):
        assert block.block_kind == expected["blockKind"]
        assert block.heading_level == expected["headingLevel"]
        assert block.block_id == expected["blockId"]
        assert block.text_content == expected["text"]

    units = db.scalars(
        select(ContentUnit)
        .where(ContentUnit.asset_id == asset.id)
        .order_by(ContentUnit.unit_order)
    ).all()
    assert units and {u.unit_kind for u in units} == {"document_text_chunk"}
    assert not any(u.unit_kind == "document_block" for u in units)
    embeddings = db.scalars(
        select(ContentUnitEmbedding).where(ContentUnitEmbedding.asset_id == asset.id)
    ).all()
    assert len(embeddings) == len(units) and all(e.is_current for e in embeddings)

    lexical = retrieve_lexical_content(
        db, workspace.id, "Hello world paragraph", asset_ids=[asset.id], limit=8
    )
    dense = retrieve_content(
        db,
        workspace.id,
        StaticEmbeddingProvider().embed_query("Hello world paragraph"),
        asset_ids=[asset.id],
        embedding_provider=StaticEmbeddingProvider(),
        limit=8,
    )
    for hits in (lexical, dense):
        assert hits
        assert {h.asset.id for h in hits} == {asset.id}
        assert {h.asset.workspace_id for h in hits} == {workspace.id}
        assert {h.locator.locator_kind for h in hits} == {"document_anchor"}
        assert {h.content_unit.unit_kind for h in hits} == {"document_text_chunk"}
        assert len({h.location_key for h in hits}) == len(hits)


def test_mixed_workspace_does_not_leak_document_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    objects: dict[str, bytes] = {}
    user1, ws1 = _user_workspace(db, label="ws1")
    user2, ws2 = _user_workspace(db, label="ws2")
    doc1 = _ready_document(
        db,
        user=user1,
        workspace=ws1,
        objects=objects,
        monkeypatch=monkeypatch,
        title="Doc One",
    )
    doc2 = _ready_document(
        db,
        user=user2,
        workspace=ws2,
        objects=objects,
        monkeypatch=monkeypatch,
        title="Doc Two",
    )
    pdf = _seed_pdf(db, user=user1, workspace=ws1)
    image = _seed_image(db, user=user1, workspace=ws1)

    mixed = retrieve_lexical_content(db, ws1.id, "Hello world", asset_ids=None, limit=16)
    kinds = {h.asset.asset_kind for h in mixed}
    asset_ids = {h.asset.id for h in mixed}
    assert {"document", "pdf", "image"} <= kinds
    assert {doc1.id, pdf.id, image.id} <= asset_ids
    assert all(h.asset.workspace_id == ws1.id for h in mixed)
    assert doc2.id not in asset_ids

    doc_only = retrieve_lexical_content(
        db, ws1.id, "Hello world", asset_ids=[doc1.id], limit=8
    )
    assert doc_only and {h.asset.id for h in doc_only} == {doc1.id}
    assert {h.content_unit.unit_kind for h in doc_only} == {"document_text_chunk"}

    assert not retrieve_lexical_content(
        db, ws1.id, "Hello world", asset_ids=[doc2.id], limit=8
    )
    ws2_hits = retrieve_lexical_content(db, ws2.id, "Hello world", asset_ids=None, limit=8)
    assert ws2_hits and {h.asset.id for h in ws2_hits} == {doc2.id}

    dense = retrieve_content(
        db,
        ws1.id,
        StaticEmbeddingProvider().embed_query("Hello world paragraph"),
        asset_ids=[doc1.id],
        embedding_provider=StaticEmbeddingProvider(),
        limit=8,
    )
    assert dense and {h.asset.id for h in dense} == {doc1.id}

    unit, locator, rep = _primary_unit(db, doc1)
    citation, note_source = _citation_note(
        db,
        user=user1,
        workspace=ws1,
        asset=doc1,
        locator=locator,
        representation=rep,
        excerpt=unit.text_content,
    )
    citation_dto = to_citation(db, citation).model_dump()
    note_dto = _to_source_dto_with_db(db, note_source).model_dump()
    assert citation_dto["sourceAvailable"] is True
    assert citation_dto["locator"]["kind"] == "document_anchor"
    assert citation_dto["assetKind"] == "document"
    assert citation_dto["excerpt"] == unit.text_content
    assert note_dto["sourceAvailable"] is True
    assert note_dto["locator"]["kind"] == "document_anchor"
    assert note_dto["locator"]["blockId"]
    assert note_dto["assetTitle"] == "Doc One"


def test_generation_retry_preserves_history_and_failed_attempt_cleans_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _json(FIXTURE_PATH)
    db = _session()
    objects: dict[str, bytes] = {}
    user, workspace = _user_workspace(db, label="retry")
    asset = _ready_document(
        db, user=user, workspace=workspace, objects=objects, monkeypatch=monkeypatch
    )
    gen1_source_key = asset.object_key
    gen1_source_bytes = objects[gen1_source_key]
    gen1_source_sha256 = asset.source_sha256
    gen1_byte_size = asset.byte_size
    gen1_reps = {
        r.id
        for r in db.scalars(
            select(AssetRepresentation).where(
                AssetRepresentation.asset_id == asset.id,
                AssetRepresentation.processing_generation == 1,
            )
        )
    }
    gen1_source_rep = db.scalar(
        select(AssetRepresentation).where(
            AssetRepresentation.asset_id == asset.id,
            AssetRepresentation.processing_generation == 1,
            AssetRepresentation.representation_kind == "document_source",
        )
    )
    assert gen1_source_rep is not None
    assert gen1_source_rep.object_key == gen1_source_key
    gen1_source_content_sha256 = gen1_source_rep.content_sha256
    gen1_blocks = {
        b.id
        for b in db.scalars(
            select(DocumentBlock).where(
                DocumentBlock.representation_id.in_(
                    select(AssetRepresentation.id).where(
                        AssetRepresentation.asset_id == asset.id,
                        AssetRepresentation.processing_generation == 1,
                        AssetRepresentation.representation_kind == "document_normalized",
                    )
                )
            )
        )
    }
    gen1_locators = {
        loc.id
        for loc in db.scalars(
            select(EvidenceLocator).where(
                EvidenceLocator.asset_id == asset.id,
                EvidenceLocator.processing_generation_snapshot == 1,
            )
        )
    }
    assert gen1_reps and gen1_blocks and gen1_locators

    # Immutable source reprocess: same object key/bytes/hash, new processing generation.
    with pytest.raises(ValueError, match="source identity is immutable"):
        _queue_document(
            db,
            user=user,
            workspace=workspace,
            objects=objects,
            payload=b"# mutated source must be rejected\n",
            source="reject-source-mutation",
            asset=asset,
        )
    asset, job2 = _queue_document(
        db,
        user=user,
        workspace=workspace,
        objects=objects,
        source="retry-gen2",
        asset=asset,
    )
    assert asset.object_key == gen1_source_key
    assert asset.source_sha256 == gen1_source_sha256
    assert asset.byte_size == gen1_byte_size
    assert objects[gen1_source_key] == gen1_source_bytes
    assert _claim_process(db, objects, monkeypatch) == job2.id
    db.refresh(asset)
    assert asset.status == "ready" and asset.current_processing_generation == 2
    assert asset.object_key == gen1_source_key
    assert asset.source_sha256 == gen1_source_sha256
    assert asset.byte_size == gen1_byte_size
    assert objects[gen1_source_key] == gen1_source_bytes
    assert gen1_reps <= {
        r.id
        for r in db.scalars(
            select(AssetRepresentation).where(AssetRepresentation.asset_id == asset.id)
        )
    }
    assert gen1_blocks <= {b.id for b in db.scalars(select(DocumentBlock))}
    assert gen1_locators <= {loc.id for loc in db.scalars(select(EvidenceLocator))}
    db.refresh(gen1_source_rep)
    assert gen1_source_rep.object_key == gen1_source_key
    assert gen1_source_rep.content_sha256 == gen1_source_content_sha256
    assert objects[gen1_source_key] == gen1_source_bytes
    gen2 = db.scalar(
        select(AssetRepresentation).where(
            AssetRepresentation.asset_id == asset.id,
            AssetRepresentation.processing_generation == 2,
            AssetRepresentation.representation_kind == "document_normalized",
        )
    )
    assert gen2 is not None and gen2.object_key in objects
    gen2_source = db.scalar(
        select(AssetRepresentation).where(
            AssetRepresentation.asset_id == asset.id,
            AssetRepresentation.processing_generation == 2,
            AssetRepresentation.representation_kind == "document_source",
        )
    )
    assert gen2_source is not None
    assert gen2_source.object_key == gen1_source_key
    assert gen2_source.content_sha256 == gen1_source_content_sha256

    # Invalid config fails before GeneratedObject materialization (source identity intact).
    # Start from production build_ingest_job snapshot, then force a document config mismatch.
    before_cfg_reps = _count(db, AssetRepresentation)
    asset, cfg_job = _queue_document(
        db,
        user=user,
        workspace=workspace,
        objects=objects,
        source="fail-config",
        asset=asset,
    )
    cfg_job.config_snapshot = {
        **dict(cfg_job.config_snapshot or {}),
        "documentParserVersion": "document-parser-not-this-build",
    }
    db.commit()
    assert asset.object_key == gen1_source_key
    assert objects[gen1_source_key] == gen1_source_bytes
    unit, locator, rep = _primary_unit(db, asset)
    citation, note_source = _citation_note(
        db,
        user=user,
        workspace=workspace,
        asset=asset,
        locator=locator,
        representation=rep,
        excerpt=unit.text_content,
    )
    before_citation = to_citation(db, citation).model_dump()
    before_note = _to_source_dto_with_db(db, note_source).model_dump()
    assert before_citation["sourceAvailable"] is True
    assert before_note["sourceAvailable"] is True

    assert _claim_process(db, objects, monkeypatch) == cfg_job.id
    db.refresh(cfg_job)
    db.refresh(asset)
    assert cfg_job.status == "failed"
    assert cfg_job.error_code == "document_configuration_mismatch"
    # Prior committed generation stays ready/retrievable; job still records failure.
    assert asset.status == "ready"
    assert asset.last_error_code == "document_configuration_mismatch"
    assert asset.last_error_message is not None
    assert asset.current_processing_generation == 2
    assert asset.object_key == gen1_source_key
    assert asset.source_sha256 == gen1_source_sha256
    assert _count(db, AssetRepresentation) == before_cfg_reps
    assert (
        _count(db, AssetRepresentation, asset_id=asset.id, processing_generation=3) == 0
    )
    lexical_after_cfg = retrieve_lexical_content(
        db, workspace.id, "Hello world paragraph", asset_ids=[asset.id], limit=8
    )
    dense_after_cfg = retrieve_content(
        db,
        workspace.id,
        StaticEmbeddingProvider().embed_query("Hello world paragraph"),
        asset_ids=[asset.id],
        embedding_provider=StaticEmbeddingProvider(),
        limit=8,
    )
    assert lexical_after_cfg and {h.asset.id for h in lexical_after_cfg} == {asset.id}
    assert dense_after_cfg and {h.asset.id for h in dense_after_cfg} == {asset.id}
    assert to_citation(db, citation).model_dump() == before_citation
    assert _to_source_dto_with_db(db, note_source).model_dump() == before_note

    # Valid same-source reprocess reaches GeneratedObject upload, then shared process cleans it.
    before_upload_reps = _count(db, AssetRepresentation)
    before_blocks = _count(db, DocumentBlock)
    before_norms = _count(db, DocumentNormalizedContent)
    asset, upload_job = _queue_document(
        db,
        user=user,
        workspace=workspace,
        objects=objects,
        source="fail-upload",
        asset=asset,
    )
    gen3_key = _normalized_key(asset, 3)
    assert asset.object_key == gen1_source_key
    assert objects[gen1_source_key] == gen1_source_bytes
    assert _claim_process(
        db, objects, monkeypatch, upload_error=RuntimeError("forced upload failure")
    ) == upload_job.id
    db.refresh(upload_job)
    db.refresh(asset)
    assert upload_job.status == "failed"
    assert upload_job.error_code == "ingestion_failed"
    assert asset.status == "ready"
    assert asset.last_error_code == "ingestion_failed"
    assert asset.last_error_message is not None
    assert asset.current_processing_generation == 2
    assert asset.object_key == gen1_source_key
    assert asset.source_sha256 == gen1_source_sha256
    assert asset.byte_size == gen1_byte_size
    assert objects[gen1_source_key] == gen1_source_bytes
    assert _count(db, AssetRepresentation) == before_upload_reps
    assert _count(db, DocumentBlock) == before_blocks
    assert _count(db, DocumentNormalizedContent) == before_norms
    assert (
        _count(db, AssetRepresentation, asset_id=asset.id, processing_generation=3) == 0
    )
    assert gen3_key not in objects
    lexical_after_upload = retrieve_lexical_content(
        db, workspace.id, "Hello world paragraph", asset_ids=[asset.id], limit=8
    )
    dense_after_upload = retrieve_content(
        db,
        workspace.id,
        StaticEmbeddingProvider().embed_query("Hello world paragraph"),
        asset_ids=[asset.id],
        embedding_provider=StaticEmbeddingProvider(),
        limit=8,
    )
    assert lexical_after_upload and {h.asset.id for h in lexical_after_upload} == {
        asset.id
    }
    assert dense_after_upload and {h.asset.id for h in dense_after_upload} == {asset.id}
    assert to_citation(db, citation).model_dump() == before_citation
    assert _to_source_dto_with_db(db, note_source).model_dump() == before_note
    gen1_norm = db.scalar(
        select(AssetRepresentation).where(
            AssetRepresentation.asset_id == asset.id,
            AssetRepresentation.processing_generation == 1,
            AssetRepresentation.representation_kind == "document_normalized",
        )
    )
    assert gen1_norm is not None
    gen1_content = db.get(DocumentNormalizedContent, gen1_norm.id)
    assert gen1_content is not None
    assert gen1_content.content_sha256 == fixture["normalizedContentSha256"]
    db.refresh(gen1_source_rep)
    assert gen1_source_rep.object_key == gen1_source_key
    assert gen1_source_rep.content_sha256 == gen1_source_content_sha256
    assert objects[gen1_source_key] == gen1_source_bytes

    # Initial ingest failure with no committed generation still leaves Asset failed.
    fail_user, fail_workspace = _user_workspace(db, label="initial-fail")
    fail_objects: dict[str, bytes] = {}
    fail_asset, fail_job = _queue_document(
        db,
        user=fail_user,
        workspace=fail_workspace,
        objects=fail_objects,
        source="initial-fail",
    )
    assert fail_asset.current_processing_generation == 1
    assert (
        _count(
            db,
            AssetRepresentation,
            asset_id=fail_asset.id,
            processing_generation=1,
        )
        == 0
    )
    assert _claim_process(
        db,
        fail_objects,
        monkeypatch,
        upload_error=RuntimeError("initial upload failure"),
    ) == fail_job.id
    db.refresh(fail_job)
    db.refresh(fail_asset)
    assert fail_job.status == "failed"
    assert fail_job.error_code == "ingestion_failed"
    assert fail_asset.status == "failed"
    assert fail_asset.last_error_code == "ingestion_failed"
    assert fail_asset.current_processing_generation == 1
    assert (
        _count(
            db,
            AssetRepresentation,
            asset_id=fail_asset.id,
            processing_generation=1,
        )
        == 0
    )
    assert not retrieve_lexical_content(
        db,
        fail_workspace.id,
        "Hello world paragraph",
        asset_ids=[fail_asset.id],
        limit=8,
    )


def test_delete_route_cleanup_and_late_ingest_cannot_resurrect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    objects: dict[str, bytes] = {}
    user, workspace = _user_workspace(db, label="delete")
    asset = _ready_document(
        db, user=user, workspace=workspace, objects=objects, monkeypatch=monkeypatch
    )
    unit, locator, rep = _primary_unit(db, asset)
    citation, note_source = _citation_note(
        db,
        user=user,
        workspace=workspace,
        asset=asset,
        locator=locator,
        representation=rep,
        excerpt=unit.text_content,
    )
    before_citation = to_citation(db, citation).model_dump()
    before_note = _to_source_dto_with_db(db, note_source).model_dump()
    assert before_citation["sourceAvailable"] is True
    assert before_note["sourceAvailable"] is True
    rep_n = _count(db, AssetRepresentation, asset_id=asset.id)
    block_n = _count(db, DocumentBlock)
    loc_n = _count(db, EvidenceLocator, asset_id=asset.id)
    norm_n = _count(db, DocumentNormalizedContent)
    detail_n = _count(db, DocumentLocatorDetail)
    assert rep_n and block_n and loc_n and norm_n and detail_n and objects

    # Superseded-running: claim a fresh same-source ingest, then delete, then process running job.
    asset, race_job = _queue_document(
        db,
        user=user,
        workspace=workspace,
        objects=objects,
        source="race-before-delete",
        asset=asset,
    )
    race_job_id = claim_next_ingestion_job(db)
    assert race_job_id == race_job.id
    db.refresh(race_job)
    assert race_job.status == "running"
    delete_asset(workspace.id, asset.id, user.id, db)
    db.refresh(asset)
    assert asset.status == "deleting"
    assert asset.latest_ingestion_job_id != race_job.id
    _claim_process(db, objects, monkeypatch, job_id=race_job.id)
    db.refresh(race_job)
    assert race_job.status == "cancelled"
    assert race_job.error_code == "ingestion_job_superseded"
    assert (
        _count(db, AssetRepresentation, asset_id=asset.id, processing_generation=2) == 0
    )
    # Gen1 units still present until delete cleanup; race must not have committed gen2.
    assert _count(db, ContentUnit, asset_id=asset.id) > 0
    assert asset.current_processing_generation == 1
    assert _normalized_key(asset, 2) not in objects

    delete_job_id = claim_next_ingestion_job(db)
    assert delete_job_id is not None
    _patch_store(monkeypatch, objects)
    process_delete_cleanup(db, delete_job_id, INGESTION_ADAPTERS)
    db.refresh(asset)
    assert asset.status == "deleted" and asset.deleted_at is not None
    assert _count(db, ContentUnit, asset_id=asset.id) == 0
    assert _count(db, ContentUnitEmbedding, asset_id=asset.id) == 0
    assert _count(db, AssetRepresentation, asset_id=asset.id) == rep_n
    assert _count(db, DocumentBlock) == block_n
    assert _count(db, EvidenceLocator, asset_id=asset.id) == loc_n
    assert _count(db, DocumentNormalizedContent) == norm_n
    assert _count(db, DocumentLocatorDetail) == detail_n
    assert objects == {}

    after_citation = to_citation(db, citation).model_dump()
    after_note = _to_source_dto_with_db(db, note_source).model_dump()
    assert after_citation["sourceAvailable"] is False
    assert after_citation["excerpt"] == before_citation["excerpt"]
    assert after_citation["locator"] == before_citation["locator"]
    assert after_citation["sourceVersions"] == before_citation["sourceVersions"]
    assert after_note["sourceAvailable"] is False
    assert after_note["excerpt"] == before_note["excerpt"]
    assert after_note["locator"] == before_note["locator"]
    assert after_note["sourceVersions"] == before_note["sourceVersions"]

    _, late = _queue_document(
        db,
        user=user,
        workspace=workspace,
        objects=objects,
        source="late-after-delete",
        asset=asset,
    )
    assert claim_next_ingestion_job(db) is None
    db.refresh(late)
    assert late.status == "cancelled"
    assert _count(db, ContentUnit, asset_id=asset.id) == 0
    assert _count(db, AssetRepresentation, asset_id=asset.id) == rep_n
    assert objects == {}


def test_document_fixture_and_v2_restore_contract() -> None:
    generator = _load_module("document_modality_generate_fixture", GENERATOR_PATH)
    checked_in = _json(FIXTURE_PATH)
    regenerated = generator.build_fixture(source_path=SOURCE_PATH)
    assert regenerated["sourceSha256"] == checked_in["sourceSha256"]
    assert regenerated["normalizedContentSha256"] == checked_in["normalizedContentSha256"]
    assert regenerated["normalizedText"] == checked_in["normalizedText"]
    for actual, expected in zip(regenerated["blocks"], checked_in["blocks"], strict=True):
        assert actual["blockId"] == expected["blockId"]
        assert actual["headingLevel"] == expected["headingLevel"]
        assert actual["textSha256"] == expected["textSha256"]
        assert actual["blockKind"] == expected["blockKind"]
        assert actual["charStart"] == expected["charStart"]
        assert actual["charEnd"] == expected["charEnd"]
    assert regenerated["locatorSnapshots"] == checked_in["locatorSnapshots"]

    restore = _load_module("v5b_document_restore_acceptance", RESTORE_SCRIPT)
    before = restore.snapshot(mode="fixture")
    result = restore.verify(before, json.loads(json.dumps(before)))
    assert result["skipped"] is True and result["passed"] is False
    assert "fixture-shape" in result["reason"]
    assert result["livePostgresMinio"] is False

    env = pytest.MonkeyPatch()
    try:
        for key in ("DATABASE_URL", "V5B_DATABASE_URL", "V5B_WORKSPACE_ID", "V5B_ASSET_ID"):
            env.delenv(key, raising=False)
        blocked = restore.snapshot(mode="live")
        assert blocked["evidenceMode"] in {"blocked", "skipped"}
        assert blocked["livePostgresMinio"] is False
        assert blocked.get("passed") is not True
        live = restore.verify(blocked, blocked)
        assert live["skipped"] is True and live["passed"] is False
    finally:
        env.undo()

    backup = BACKUP_SCRIPT.read_text(encoding="utf-8")
    restore_sh = RESTORE_DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert "FORMAT_VERSION=2" in backup
    assert "BACKUP_CONTRACT=document-modality-v1" in backup
    assert (
        "DOCUMENT_TYPED_TABLES=document_normalized_contents,document_blocks,document_locator_details"
        in backup
    )
    assert "DOCUMENT_OBJECT_LAYOUT=workspaces/{workspace_id}/assets/{asset_id}/" in backup
    assert "DOCUMENT_TYPED_TABLES" in restore_sh
    assert "DOCUMENT_OBJECT_LAYOUT" in restore_sh
    assert "required=2" in restore_sh
