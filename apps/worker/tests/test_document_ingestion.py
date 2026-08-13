from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from ai_pdf_api.db.base import Base
from ai_pdf_api.modalities.document import (
    DOCUMENT_NORMALIZATION_VERSION,
    DOCUMENT_PARSER_VERSION,
    stable_document_block_id,
    text_sha256,
)
from ai_pdf_api.modalities.ingestion import IngestionAdapterRegistry, IngestionError
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ContentUnit,
    ContentUnitEmbedding,
    DocumentBlock,
    DocumentLocatorDetail,
    DocumentNormalizedContent,
    EvidenceLocator,
    IngestionJob,
)
from ai_pdf_api.services.ingestion import process_ingestion_job
from ai_pdf_worker.document_ingestion import (
    DocumentIngestionAdapter,
    delete_document_content,
    parse_markdown_document,
)
from ai_pdf_worker.document_markdown import parse_markdown_document as parse_from_markdown_module
from ai_pdf_worker.pdf_ingestion import PdfIngestionAdapter
import ai_pdf_worker.main as worker_main
from ai_pdf_worker.research_executor_contracts import (
    EvidenceHandle,
    FrozenAsset,
    LoadedEvidence,
    ToolExecutionContext,
)
from ai_pdf_worker.research_executor_contracts import ToolPolicyError
from ai_pdf_worker.research_executor_tools import EvidenceToolRegistry

MARKDOWN_FIXTURE = """# Intro

Hello world paragraph.

## Nested

- first item
  - nested item
1. ordered item

```python
print("hi")
```

> quoted text

| Col A | Col B |
| ----- | ----- |
| 1     | 2     |
"""

SETEXT_FIXTURE = """Title
=====

Body paragraph.

Subtitle
--------

More body.
"""


class StaticEmbeddingProvider:
    provider = "test-embedding"
    model = "test-embedding-model"
    dimensions = 3
    version = "test-embedding-v1"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(index + 1), float(len(text)), 1.0] for index, text in enumerate(texts)]

    def embed_query(self, _text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )


def _document_config() -> dict[str, object]:
    return {
        "documentFormat": "markdown",
        "documentParserVersion": DOCUMENT_PARSER_VERSION,
        "documentNormalizationVersion": DOCUMENT_NORMALIZATION_VERSION,
        "chunkSize": 1200,
        "embeddingProvider": StaticEmbeddingProvider.provider,
        "embeddingModel": StaticEmbeddingProvider.model,
        "embeddingDimensions": StaticEmbeddingProvider.dimensions,
        "embeddingVersion": StaticEmbeddingProvider.version,
    }


def _make_asset(
    db: Session,
    *,
    payload: bytes,
    mime_type: str = "text/markdown",
    asset_kind: str = "document",
    workspace_id: str = "workspace-document",
) -> Asset:
    now = datetime.now(UTC)
    asset = Asset(
        workspace_id=workspace_id,
        created_by_user_id="user-document",
        asset_kind=asset_kind,
        title="Markdown note",
        source_filename="note.md",
        object_key=f"workspaces/{workspace_id}/assets/source/original.md",
        mime_type=mime_type,
        byte_size=len(payload),
        source_sha256=sha256(payload).hexdigest(),
        status="parsing",
        current_processing_generation=1,
        current_index_version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(asset)
    db.flush()
    return asset


def _blocks_for_asset(db: Session, asset_id: str) -> list[DocumentBlock]:
    representation_ids = db.scalars(
        select(AssetRepresentation.id).where(AssetRepresentation.asset_id == asset_id)
    ).all()
    if not representation_ids:
        return []
    return list(
        db.scalars(
            select(DocumentBlock)
            .where(DocumentBlock.representation_id.in_(representation_ids))
            .order_by(DocumentBlock.block_order)
        ).all()
    )


def _blocks_for_generation(
    db: Session, asset_id: str, processing_generation: int
) -> list[DocumentBlock]:
    representation_ids = db.scalars(
        select(AssetRepresentation.id).where(
            AssetRepresentation.asset_id == asset_id,
            AssetRepresentation.processing_generation == processing_generation,
            AssetRepresentation.representation_kind == "document_normalized",
        )
    ).all()
    if not representation_ids:
        return []
    return list(
        db.scalars(
            select(DocumentBlock)
            .where(DocumentBlock.representation_id.in_(representation_ids))
            .order_by(DocumentBlock.block_order)
        ).all()
    )


def test_parse_exports_are_shared_between_modules() -> None:
    assert parse_markdown_document is parse_from_markdown_module


def test_parse_markdown_deterministic_blocks_offsets_kinds_and_heading_levels() -> None:
    payload = MARKDOWN_FIXTURE.encode("utf-8")
    first = parse_markdown_document(payload)
    second = parse_markdown_document(payload)

    assert first.normalized_text == second.normalized_text
    assert first.content_sha256 == second.content_sha256
    assert first.source_sha256 == sha256(payload).hexdigest()
    assert [(b.block_kind, b.text, b.heading_path, b.heading_level) for b in first.blocks] == [
        (b.block_kind, b.text, b.heading_path, b.heading_level) for b in second.blocks
    ]

    kinds = {block.block_kind for block in first.blocks}
    assert kinds == {
        "heading",
        "paragraph",
        "list_item",
        "code_block",
        "quote",
        "table",
    }

    for block in first.blocks:
        assert first.normalized_text[block.char_start : block.char_end] == block.text
        assert block.char_end > block.char_start
        assert text_sha256(block.text) == text_sha256(
            first.normalized_text[block.char_start : block.char_end]
        )
        if block.block_kind == "heading":
            assert block.heading_level in {1, 2, 3, 4, 5, 6}
        else:
            assert block.heading_level is None

    intro = next(block for block in first.blocks if block.text == "Intro")
    assert intro.block_kind == "heading" and intro.heading_level == 1
    nested_heading = next(block for block in first.blocks if block.text == "Nested")
    assert nested_heading.block_kind == "heading" and nested_heading.heading_level == 2
    nested = next(block for block in first.blocks if "nested item" in block.text)
    assert nested.block_kind == "list_item"
    assert nested.heading_path == ("Intro", "Nested")
    code = next(block for block in first.blocks if block.block_kind == "code_block")
    assert "print(\"hi\")" in code.text
    table = next(block for block in first.blocks if block.block_kind == "table")
    assert "Col A" in table.text and "1" in table.text


def test_parse_supports_setext_headings_and_gfm_tables_without_outer_pipes() -> None:
    parsed = parse_markdown_document(SETEXT_FIXTURE.encode("utf-8"))
    headings = [block for block in parsed.blocks if block.block_kind == "heading"]
    assert [(block.text, block.heading_level) for block in headings] == [
        ("Title", 1),
        ("Subtitle", 2),
    ]

    table_source = b"Col C | Col D\n----- | -----\n3 | 4\n"
    table_parsed = parse_markdown_document(table_source)
    table = next(block for block in table_parsed.blocks if block.block_kind == "table")
    assert "Col C" in table.text and "3" in table.text


def test_parse_rejects_invalid_encoding_bytes_and_mime() -> None:
    with pytest.raises(IngestionError) as encoding:
        parse_markdown_document(b"\xff\xfe not utf8")
    assert encoding.value.code == "asset_encoding_unsupported"

    with pytest.raises(IngestionError) as nul:
        parse_markdown_document(b"hello\x00world")
    assert nul.value.code == "asset_bytes_invalid"

    with pytest.raises(IngestionError) as binary:
        parse_markdown_document(b"%PDF-1.7 fake")
    assert binary.value.code == "asset_bytes_invalid"

    with pytest.raises(IngestionError) as mime:
        parse_markdown_document(b"# ok\n", mime_type="text/html")
    assert mime.value.code == "asset_mime_mismatch"

    with pytest.raises(IngestionError) as empty:
        parse_markdown_document(b"")
    assert empty.value.code == "asset_bytes_invalid"


def test_document_adapter_persists_blocks_locators_chunks_only_and_generated_object() -> None:
    engine = _engine()
    Base.metadata.create_all(bind=engine)
    payload = MARKDOWN_FIXTURE.encode("utf-8")
    now = datetime.now(UTC)
    try:
        with Session(engine) as db:
            asset = _make_asset(db, payload=payload)
            adapter = DocumentIngestionAdapter()
            result = adapter.ingest(
                db,
                asset=asset,
                payload=payload,
                processing_generation=1,
                config_snapshot=_document_config(),
                created_at=now,
            )
            db.flush()

            assert len(result.generated_objects) == 1
            generated = result.generated_objects[0]
            assert generated.object_key.endswith("/representations/1/document-normalized.txt")
            assert generated.content_type.startswith("text/plain")
            assert sha256(generated.payload).hexdigest() == generated.content_sha256

            representations = db.scalars(
                select(AssetRepresentation)
                .where(AssetRepresentation.asset_id == asset.id)
                .order_by(AssetRepresentation.representation_kind)
            ).all()
            kinds = {item.representation_kind for item in representations}
            assert kinds == {"document_source", "document_normalized"}
            normalized = next(
                item for item in representations if item.representation_kind == "document_normalized"
            )
            assert normalized.object_key == generated.object_key
            assert normalized.content_sha256 == generated.content_sha256
            assert normalized.generator_version == DOCUMENT_PARSER_VERSION

            content = db.get(DocumentNormalizedContent, normalized.id)
            assert content is not None
            assert content.format == "markdown"
            assert content.parser_version == DOCUMENT_PARSER_VERSION
            assert content.normalization_version == DOCUMENT_NORMALIZATION_VERSION
            assert content.normalized_text == generated.payload.decode("utf-8")
            assert content.block_count > 0

            blocks = _blocks_for_generation(db, asset.id, 1)
            assert len(blocks) == content.block_count
            for block in blocks:
                expected_id = stable_document_block_id(
                    source_sha256=asset.source_sha256 or "",
                    parser_version=DOCUMENT_PARSER_VERSION,
                    block_order=block.block_order,
                    block_kind=block.block_kind,
                    heading_path=block.heading_path,
                    text_sha256=block.text_sha256,
                )
                assert block.block_id == expected_id
                assert content.normalized_text[block.char_start : block.char_end] == block.text_content
                assert block.text_sha256 == text_sha256(block.text_content)
                assert block.normalization_version == DOCUMENT_NORMALIZATION_VERSION
                if block.block_kind == "heading":
                    assert block.heading_level in {1, 2, 3, 4, 5, 6}
                else:
                    assert block.heading_level is None

            units = db.scalars(
                select(ContentUnit)
                .where(ContentUnit.asset_id == asset.id)
                .order_by(ContentUnit.unit_order)
            ).all()
            assert units
            assert {unit.unit_kind for unit in units} == {"document_text_chunk"}
            assert not any(unit.unit_kind == "document_block" for unit in units)
            for unit in units:
                assert unit.representation_id == normalized.id
                locator = db.get(EvidenceLocator, unit.source_locator_id)
                assert locator is not None
                assert locator.locator_kind == "document_anchor"
                assert locator.locator_version == 1
                assert locator.processing_generation_snapshot == 1
                assert locator.representation_id_snapshot == normalized.id
                detail = db.get(DocumentLocatorDetail, locator.id)
                assert detail is not None
                assert detail.normalization_version == DOCUMENT_NORMALIZATION_VERSION
                assert detail.char_end > detail.char_start
                assert content.normalized_text[detail.char_start : detail.char_end]
                assert unit.char_start == detail.char_start
                assert unit.char_end == detail.char_end
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_document_retry_preserves_historical_generations_and_gen1_locators() -> None:
    engine = _engine()
    Base.metadata.create_all(bind=engine)
    payload = MARKDOWN_FIXTURE.encode("utf-8")
    now = datetime.now(UTC)
    try:
        with Session(engine) as db:
            asset = _make_asset(db, payload=payload)
            adapter = DocumentIngestionAdapter()
            first = adapter.ingest(
                db,
                asset=asset,
                payload=payload,
                processing_generation=1,
                config_snapshot=_document_config(),
                created_at=now,
            )
            db.flush()
            gen1_blocks = [
                (block.block_id, block.block_order, block.block_kind, block.text_sha256, block.heading_level)
                for block in _blocks_for_generation(db, asset.id, 1)
            ]
            gen1_locators = db.scalars(
                select(EvidenceLocator).where(
                    EvidenceLocator.asset_id == asset.id,
                    EvidenceLocator.processing_generation_snapshot == 1,
                    EvidenceLocator.locator_kind == "document_anchor",
                )
            ).all()
            gen1_locator_ids = {locator.id for locator in gen1_locators}
            assert gen1_locator_ids
            gen1_key = first.generated_objects[0].object_key

            second = adapter.ingest(
                db,
                asset=asset,
                payload=payload,
                processing_generation=2,
                config_snapshot=_document_config(),
                created_at=now,
            )
            db.flush()
            gen2_blocks = [
                (block.block_id, block.block_order, block.block_kind, block.text_sha256, block.heading_level)
                for block in _blocks_for_generation(db, asset.id, 2)
            ]
            # Stable block ids across generations, and gen-1 rows remain.
            assert gen1_blocks == gen2_blocks
            assert _blocks_for_generation(db, asset.id, 1)
            assert _blocks_for_generation(db, asset.id, 2)
            assert first.generated_objects[0].content_sha256 == second.generated_objects[0].content_sha256
            assert gen1_key.endswith("/representations/1/document-normalized.txt")
            assert second.generated_objects[0].object_key.endswith(
                "/representations/2/document-normalized.txt"
            )

            remaining_gen1 = db.scalars(
                select(EvidenceLocator).where(EvidenceLocator.id.in_(gen1_locator_ids))
            ).all()
            assert {locator.id for locator in remaining_gen1} == gen1_locator_ids
            for locator in remaining_gen1:
                detail = db.get(DocumentLocatorDetail, locator.id)
                assert detail is not None
                assert locator.processing_generation_snapshot == 1
                assert locator.locator_kind == "document_anchor"

            unit_kinds = {
                unit.unit_kind
                for unit in db.scalars(select(ContentUnit).where(ContentUnit.asset_id == asset.id))
            }
            assert unit_kinds == {"document_text_chunk"}
            # Current retrieval units target gen-2 representations only after rewrite of same asset
            # content units for the new generation; gen-1 content units remain for historical gen.
            gen1_rep_ids = set(
                db.scalars(
                    select(AssetRepresentation.id).where(
                        AssetRepresentation.asset_id == asset.id,
                        AssetRepresentation.processing_generation == 1,
                    )
                ).all()
            )
            gen2_rep_ids = set(
                db.scalars(
                    select(AssetRepresentation.id).where(
                        AssetRepresentation.asset_id == asset.id,
                        AssetRepresentation.processing_generation == 2,
                    )
                ).all()
            )
            assert gen1_rep_ids and gen2_rep_ids
            assert db.scalars(
                select(ContentUnit).where(ContentUnit.representation_id.in_(gen1_rep_ids))
            ).all()
            assert db.scalars(
                select(ContentUnit).where(ContentUnit.representation_id.in_(gen2_rep_ids))
            ).all()
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_same_generation_retry_fails_closed_and_preserves_serializable_locators() -> None:
    engine = _engine()
    Base.metadata.create_all(bind=engine)
    payload = MARKDOWN_FIXTURE.encode("utf-8")
    now = datetime.now(UTC)
    try:
        with Session(engine) as db:
            asset = _make_asset(db, payload=payload)
            adapter = DocumentIngestionAdapter()
            adapter.ingest(
                db,
                asset=asset,
                payload=payload,
                processing_generation=1,
                config_snapshot=_document_config(),
                created_at=now,
            )
            db.flush()
            first_blocks = _blocks_for_generation(db, asset.id, 1)
            first_block_ids = [block.id for block in first_blocks]
            first_unit_ids = [
                unit.id
                for unit in db.scalars(
                    select(ContentUnit).where(ContentUnit.asset_id == asset.id)
                ).all()
            ]
            first_locators = db.scalars(
                select(EvidenceLocator).where(
                    EvidenceLocator.asset_id == asset.id,
                    EvidenceLocator.processing_generation_snapshot == 1,
                    EvidenceLocator.locator_kind == "document_anchor",
                )
            ).all()
            assert first_block_ids and first_unit_ids and first_locators
            locator_snapshot = [
                {
                    "id": locator.id,
                    "representation_id_snapshot": locator.representation_id_snapshot,
                    "processing_generation_snapshot": locator.processing_generation_snapshot,
                    "locator_kind": locator.locator_kind,
                    "locator_version": locator.locator_version,
                    "detail": {
                        "block_id": detail.block_id,
                        "block_kind": detail.block_kind,
                        "heading_path": list(detail.heading_path),
                        "char_start": detail.char_start,
                        "char_end": detail.char_end,
                        "text_sha256": detail.text_sha256,
                        "normalization_version": detail.normalization_version,
                    },
                }
                for locator in first_locators
                for detail in [db.get(DocumentLocatorDetail, locator.id)]
                if detail is not None
            ]
            assert locator_snapshot
            # Prove locator representation FK targets still resolve before/after fail-closed retry.
            for item in locator_snapshot:
                assert db.get(AssetRepresentation, item["representation_id_snapshot"]) is not None

            with pytest.raises(IngestionError) as captured:
                adapter.ingest(
                    db,
                    asset=asset,
                    payload=payload,
                    processing_generation=1,
                    config_snapshot=_document_config(),
                    created_at=now,
                )
            assert captured.value.code == "document_generation_already_exists"
            db.flush()

            assert [block.id for block in _blocks_for_generation(db, asset.id, 1)] == first_block_ids
            assert [
                unit.id
                for unit in db.scalars(
                    select(ContentUnit).where(ContentUnit.asset_id == asset.id)
                ).all()
            ] == first_unit_ids
            remaining_by_id = {
                locator.id: locator
                for locator in db.scalars(
                    select(EvidenceLocator).where(
                        EvidenceLocator.id.in_([item["id"] for item in locator_snapshot])
                    )
                ).all()
            }
            assert set(remaining_by_id) == {item["id"] for item in locator_snapshot}
            remaining_snapshot = []
            for item in locator_snapshot:
                locator = remaining_by_id[item["id"]]
                detail = db.get(DocumentLocatorDetail, locator.id)
                assert detail is not None
                remaining_snapshot.append(
                    {
                        "id": locator.id,
                        "representation_id_snapshot": locator.representation_id_snapshot,
                        "processing_generation_snapshot": locator.processing_generation_snapshot,
                        "locator_kind": locator.locator_kind,
                        "locator_version": locator.locator_version,
                        "detail": {
                            "block_id": detail.block_id,
                            "block_kind": detail.block_kind,
                            "heading_path": list(detail.heading_path),
                            "char_start": detail.char_start,
                            "char_end": detail.char_end,
                            "text_sha256": detail.text_sha256,
                            "normalization_version": detail.normalization_version,
                        },
                    }
                )
            assert remaining_snapshot == locator_snapshot
            for item in remaining_snapshot:
                representation = db.get(AssetRepresentation, item["representation_id_snapshot"])
                assert representation is not None
                assert representation.processing_generation == 1
                assert representation.representation_kind == "document_normalized"
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_document_job_uploads_generated_object_and_embeds_chunks(monkeypatch) -> None:
    engine = _engine()
    Base.metadata.create_all(bind=engine)
    payload = MARKDOWN_FIXTURE.encode("utf-8")
    stored: dict[str, bytes] = {}
    now = datetime.now(UTC)
    try:
        with Session(engine, expire_on_commit=False) as db:
            asset = _make_asset(db, payload=payload, workspace_id="workspace-document-job")
            job = IngestionJob(
                workspace_id=asset.workspace_id,
                asset_id=asset.id,
                job_type="ingest",
                status="running",
                attempt_count=1,
                config_snapshot=_document_config(),
                requested_by_user_id=asset.created_by_user_id,
                queued_at=now,
                started_at=now,
                created_at=now,
            )
            db.add(job)
            db.flush()
            asset.latest_ingestion_job_id = job.id
            db.commit()

            monkeypatch.setattr(
                "ai_pdf_api.services.ingestion.download_bytes",
                lambda key: payload if key == asset.object_key else b"",
            )
            monkeypatch.setattr(
                "ai_pdf_api.services.ingestion.upload_bytes",
                lambda key, body, _content_type: stored.__setitem__(key, body),
            )
            monkeypatch.setattr(
                "ai_pdf_api.services.ingestion.delete_object_if_exists",
                lambda key: stored.pop(key, None),
            )

            process_ingestion_job(
                db,
                job.id,
                ingestion_adapters=IngestionAdapterRegistry((DocumentIngestionAdapter(),)),
                embedding_provider=StaticEmbeddingProvider(),
            )

            assert asset.status == "ready"
            assert asset.current_processing_generation == 1
            assert job.status == "succeeded"
            units = db.scalars(select(ContentUnit).where(ContentUnit.asset_id == asset.id)).all()
            embeddings = db.scalars(select(ContentUnitEmbedding)).all()
            assert units
            assert {unit.unit_kind for unit in units} == {"document_text_chunk"}
            assert len(embeddings) == len(units)
            normalized = db.scalar(
                select(AssetRepresentation).where(
                    AssetRepresentation.asset_id == asset.id,
                    AssetRepresentation.representation_kind == "document_normalized",
                )
            )
            assert normalized is not None
            assert set(stored) == {normalized.object_key}
            assert sha256(stored[normalized.object_key]).hexdigest() == normalized.content_sha256
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_document_generated_object_cleaned_up_on_persistence_failure(monkeypatch) -> None:
    engine = _engine()
    Base.metadata.create_all(bind=engine)
    payload = MARKDOWN_FIXTURE.encode("utf-8")
    stored: dict[str, bytes] = {}
    deleted: list[str] = []
    now = datetime.now(UTC)
    try:
        with Session(engine, expire_on_commit=False) as db:
            asset = _make_asset(db, payload=payload, workspace_id="workspace-document-cleanup")
            job = IngestionJob(
                workspace_id=asset.workspace_id,
                asset_id=asset.id,
                job_type="ingest",
                status="running",
                attempt_count=1,
                config_snapshot=_document_config(),
                requested_by_user_id=asset.created_by_user_id,
                queued_at=now,
                started_at=now,
                created_at=now,
            )
            db.add(job)
            db.flush()
            asset.latest_ingestion_job_id = job.id
            db.commit()

            monkeypatch.setattr(
                "ai_pdf_api.services.ingestion.download_bytes",
                lambda key: payload if key == asset.object_key else b"",
            )

            def upload(key: str, body: bytes, _content_type: str) -> None:
                stored[key] = body

            def delete_object(key: str) -> None:
                deleted.append(key)
                stored.pop(key, None)

            monkeypatch.setattr("ai_pdf_api.services.ingestion.upload_bytes", upload)
            monkeypatch.setattr(
                "ai_pdf_api.services.ingestion.delete_object_if_exists",
                delete_object,
            )

            class BoomEmbedding(StaticEmbeddingProvider):
                def embed_documents(self, texts: list[str]) -> list[list[float]]:
                    raise RuntimeError("embedding boom")

            process_ingestion_job(
                db,
                job.id,
                ingestion_adapters=IngestionAdapterRegistry((DocumentIngestionAdapter(),)),
                embedding_provider=BoomEmbedding(),
            )

            assert job.status == "failed"
            assert stored == {}
            assert deleted  # generated normalized object was cleaned up
            assert any(key.endswith("document-normalized.txt") for key in deleted)
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_asset_delete_cleanup_removes_content_units_but_keeps_history() -> None:
    engine = _engine()
    Base.metadata.create_all(bind=engine)
    payload = MARKDOWN_FIXTURE.encode("utf-8")
    now = datetime.now(UTC)
    try:
        with Session(engine) as db:
            asset = _make_asset(db, payload=payload, workspace_id="workspace-document-delete")
            adapter = DocumentIngestionAdapter()
            adapter.ingest(
                db,
                asset=asset,
                payload=payload,
                processing_generation=1,
                config_snapshot=_document_config(),
                created_at=now,
            )
            adapter.ingest(
                db,
                asset=asset,
                payload=payload,
                processing_generation=2,
                config_snapshot=_document_config(),
                created_at=now,
            )
            db.flush()

            units = list(
                db.scalars(select(ContentUnit).where(ContentUnit.asset_id == asset.id)).all()
            )
            assert units
            for unit in units:
                db.add(
                    ContentUnitEmbedding(
                        content_unit_id=unit.id,
                        workspace_id=asset.workspace_id,
                        asset_id=asset.id,
                        embedding_space="text",
                        provider=StaticEmbeddingProvider.provider,
                        model=StaticEmbeddingProvider.model,
                        version=StaticEmbeddingProvider.version,
                        dimensions=StaticEmbeddingProvider.dimensions,
                        processing_generation=1,
                        index_version=asset.current_index_version,
                        is_current=True,
                        embedding=[1.0, 2.0, 3.0],
                        created_at=now,
                    )
                )
            db.flush()
            embedding_ids = [
                row.id for row in db.scalars(select(ContentUnitEmbedding)).all()
            ]
            assert embedding_ids

            representations_before = list(
                db.scalars(
                    select(AssetRepresentation).where(AssetRepresentation.asset_id == asset.id)
                ).all()
            )
            blocks_before = _blocks_for_asset(db, asset.id)
            normalized_before = list(db.scalars(select(DocumentNormalizedContent)).all())
            locators_before = list(
                db.scalars(
                    select(EvidenceLocator).where(EvidenceLocator.asset_id == asset.id)
                ).all()
            )
            details_before = [
                db.get(DocumentLocatorDetail, locator.id) for locator in locators_before
            ]
            assert representations_before and blocks_before and normalized_before
            assert locators_before and all(detail is not None for detail in details_before)
            representation_ids = {item.id for item in representations_before}
            block_ids = {block.id for block in blocks_before}
            locator_ids = {locator.id for locator in locators_before}

            adapter.cleanup(db, asset=asset)
            db.flush()

            assert (
                db.scalars(select(ContentUnit).where(ContentUnit.asset_id == asset.id)).all() == []
            )
            assert (
                db.scalars(
                    select(ContentUnitEmbedding).where(
                        ContentUnitEmbedding.id.in_(embedding_ids)
                    )
                ).all()
                == []
            )
            assert (
                db.scalars(
                    select(ContentUnitEmbedding).where(
                        ContentUnitEmbedding.asset_id == asset.id
                    )
                ).all()
                == []
            )

            representations_after = list(
                db.scalars(
                    select(AssetRepresentation).where(AssetRepresentation.asset_id == asset.id)
                ).all()
            )
            blocks_after = _blocks_for_asset(db, asset.id)
            normalized_after = list(db.scalars(select(DocumentNormalizedContent)).all())
            locators_after = list(
                db.scalars(
                    select(EvidenceLocator).where(EvidenceLocator.asset_id == asset.id)
                ).all()
            )
            assert {item.id for item in representations_after} == representation_ids
            assert {block.id for block in blocks_after} == block_ids
            assert {item.representation_id for item in normalized_after} == {
                item.representation_id for item in normalized_before
            }
            assert {locator.id for locator in locators_after} == locator_ids
            for locator in locators_after:
                assert db.get(DocumentLocatorDetail, locator.id) is not None
                assert db.get(AssetRepresentation, locator.representation_id_snapshot) is not None

            # cleanup helper remains idempotent for delete-job path
            delete_document_content(db, asset.id)
            assert (
                db.scalars(select(ContentUnit).where(ContentUnit.asset_id == asset.id)).all() == []
            )
            assert {item.id for item in db.scalars(
                select(AssetRepresentation).where(AssetRepresentation.asset_id == asset.id)
            ).all()} == representation_ids
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_dispatch_selects_document_only_for_markdown_registry_and_not_pdf_image() -> None:
    assert worker_main.INGESTION_ADAPTERS.asset_kinds == frozenset(
        {"pdf", "image", "document", "docx", "xlsx", "pptx", "audio"}
    )
    document = worker_main.INGESTION_ADAPTERS.get("document")
    assert document.asset_kind == "document"
    pdf = worker_main.INGESTION_ADAPTERS.get("pdf")
    image = worker_main.INGESTION_ADAPTERS.get("image")
    assert pdf.asset_kind == "pdf"
    assert image.asset_kind == "image"
    assert worker_main.INGESTION_ADAPTERS.get("audio").asset_kind == "audio"


def test_pdf_image_dispatch_regression_document_adapter_rejects_non_document_asset() -> None:
    engine = _engine()
    Base.metadata.create_all(bind=engine)
    payload = b"%PDF-1.4 minimal"
    now = datetime.now(UTC)
    try:
        with Session(engine) as db:
            asset = _make_asset(
                db,
                payload=payload,
                mime_type="application/pdf",
                asset_kind="pdf",
                workspace_id="workspace-pdf-regression",
            )
            adapter = DocumentIngestionAdapter()
            with pytest.raises(IngestionError) as captured:
                adapter.ingest(
                    db,
                    asset=asset,
                    payload=payload,
                    processing_generation=1,
                    config_snapshot=_document_config(),
                    created_at=now,
                )
            assert captured.value.code in {
                "asset_mime_mismatch",
                "document_asset_kind_invalid",
                "asset_bytes_invalid",
            }
            assert PdfIngestionAdapter().asset_kind == "pdf"
            assert worker_main.INGESTION_ADAPTERS.get("pdf").asset_kind == "pdf"
            assert worker_main.INGESTION_ADAPTERS.get("image").asset_kind == "image"
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_document_adapter_requires_all_three_config_keys() -> None:
    engine = _engine()
    Base.metadata.create_all(bind=engine)
    payload = MARKDOWN_FIXTURE.encode("utf-8")
    now = datetime.now(UTC)
    try:
        with Session(engine) as db:
            asset = _make_asset(db, payload=payload)
            adapter = DocumentIngestionAdapter()
            base = _document_config()
            for missing_key in (
                "documentFormat",
                "documentParserVersion",
                "documentNormalizationVersion",
            ):
                snapshot = dict(base)
                snapshot.pop(missing_key)
                with pytest.raises(IngestionError) as captured:
                    adapter.ingest(
                        db,
                        asset=asset,
                        payload=payload,
                        processing_generation=1,
                        config_snapshot=snapshot,
                        created_at=now,
                    )
                assert captured.value.code == "document_configuration_mismatch"

            with pytest.raises(IngestionError) as wrong_parser:
                adapter.ingest(
                    db,
                    asset=asset,
                    payload=payload,
                    processing_generation=1,
                    config_snapshot={
                        **base,
                        "documentParserVersion": "document-parser-v0",
                    },
                    created_at=now,
                )
            assert wrong_parser.value.code == "document_configuration_mismatch"
            assert (
                db.scalars(
                    select(AssetRepresentation).where(AssetRepresentation.asset_id == asset.id)
                ).all()
                == []
            )
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _research_context() -> ToolExecutionContext:
    return ToolExecutionContext(
        workspace_id="workspace-1",
        run_id="run-1",
        execution_snapshot_id="execution-1",
        execution_snapshot_sha256="a" * 64,
        step_id="step-1",
        attempt_id="attempt-1",
        branch_key="branch-0",
        frozen_assets=(
            FrozenAsset(
                asset_id="asset-doc",
                processing_generation=1,
                index_version=1,
            ),
        ),
    )


class _DocumentAnchorToolPort:
    def restore_handles(self, context: ToolExecutionContext):
        return ()

    def search(self, context, *, tool_call_key, query, asset_ids, top_k):
        raise AssertionError("search should not run in unit scope test")

    def load(self, context, *, tool_call_key, handle_ids):
        raise AssertionError("load should not run in unit scope test")


def test_research_scope_accepts_document_anchor_and_rejects_unknown_locator_kind() -> None:
    context = _research_context()
    registry = EvidenceToolRegistry(_DocumentAnchorToolPort(), context)

    accepted = EvidenceHandle(
        id="evidence-doc-1",
        workspace_id=context.workspace_id,
        run_id=context.run_id,
        execution_snapshot_id=context.execution_snapshot_id,
        owner_step_id=context.step_id,
        branch_key=context.branch_key,
        asset_id="asset-doc",
        processing_generation=1,
        index_version=1,
        representation_id="representation-doc",
        parser_version=DOCUMENT_PARSER_VERSION,
        locator_id="locator-doc-1",
        locator_kind="document_anchor",
        excerpt="Intro",
        source_fingerprint_sha256="b" * 64,
        created_by_tool_call_id="tool-doc-1",
    )
    registry._accept_scoped_handles([accepted])
    assert registry._issued[accepted.id] == accepted

    rejected = EvidenceHandle(
        id="evidence-bad",
        workspace_id=context.workspace_id,
        run_id=context.run_id,
        execution_snapshot_id=context.execution_snapshot_id,
        owner_step_id=context.step_id,
        branch_key=context.branch_key,
        asset_id="asset-doc",
        processing_generation=1,
        index_version=1,
        representation_id="representation-doc",
        parser_version=DOCUMENT_PARSER_VERSION,
        locator_id="locator-bad",
        locator_kind="html_anchor",  # type: ignore[arg-type]
        excerpt="bad",
        source_fingerprint_sha256="c" * 64,
        created_by_tool_call_id="tool-bad",
    )
    with pytest.raises(ToolPolicyError, match="tool_scope_violation"):
        registry._accept_scoped_handles([rejected])

    # LoadedEvidence type union also accepts document_anchor at construction time.
    loaded = LoadedEvidence(
        evidence_handle=accepted.id,
        asset_id=accepted.asset_id,
        processing_generation=accepted.processing_generation,
        index_version=accepted.index_version,
        representation_id=accepted.representation_id,
        parser_version=accepted.parser_version,
        locator_id=accepted.locator_id,
        locator_kind="document_anchor",
        content="Intro",
        content_sha256="d" * 64,
        source_available=True,
    )
    assert loaded.locator_kind == "document_anchor"
