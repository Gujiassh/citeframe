"""Markdown-only Document ingestion adapter for V5-B.

Parse/normalize lives in document_markdown.py. This module owns typed row
persistence through the existing IngestionAdapter/IngestionResult seam.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ai_pdf_api.modalities.document import (
    DOCUMENT_FORMAT_MARKDOWN,
    DOCUMENT_NORMALIZATION_VERSION,
    DOCUMENT_PARSER_VERSION,
    stable_document_block_id,
    text_sha256,
)
from ai_pdf_api.modalities.ingestion import GeneratedObject, IngestionError, IngestionResult
from ai_pdf_api.modalities.text import estimate_token_count
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ContentUnit,
    ContentUnitEmbedding,
    DocumentBlock,
    DocumentLocatorDetail,
    DocumentNormalizedContent,
    EvidenceLocator,
)

from ai_pdf_worker.document_markdown import (
    DocumentParseResult,
    MARKDOWN_MIME,
    parse_markdown_document,
    split_document_text,
)

CHUNK_SIZE = 1_200
CHUNK_OVERLAP = 200
NORMALIZED_CONTENT_TYPE = "text/plain; charset=utf-8"

# Re-export for tests that import from the adapter module.
__all__ = [
    "DocumentIngestionAdapter",
    "delete_document_content",
    "parse_markdown_document",
    "replace_document_content",
]


def build_document_normalized_object_key(asset: Asset, processing_generation: int) -> str:
    return (
        f"workspaces/{asset.workspace_id}/assets/{asset.id}/representations/"
        f"{processing_generation}/document-normalized.txt"
    )


def replace_document_content(
    db: Session,
    *,
    asset: Asset,
    parsed: DocumentParseResult,
    processing_generation: int,
    chunk_size: int,
    created_at: datetime,
    normalized_object_key: str,
) -> None:
    if asset.asset_kind != "document":
        raise IngestionError(
            "document_asset_kind_invalid",
            "Document adapter received a non-document asset.",
        )
    # Committed generations are immutable. A retry after transaction rollback has
    # no rows for this generation and may proceed; never delete/replace materialized rows.
    _assert_generation_available(
        db,
        asset_id=asset.id,
        processing_generation=processing_generation,
    )

    source_representation = AssetRepresentation(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        representation_kind="document_source",
        processing_generation=processing_generation,
        generator_provider="document",
        generator_version=DOCUMENT_PARSER_VERSION,
        object_key=asset.object_key,
        content_sha256=parsed.source_sha256,
        created_at=created_at,
    )
    db.add(source_representation)

    normalized_representation = AssetRepresentation(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        representation_kind="document_normalized",
        processing_generation=processing_generation,
        generator_provider="document",
        generator_version=DOCUMENT_PARSER_VERSION,
        object_key=normalized_object_key,
        content_sha256=parsed.content_sha256,
        created_at=created_at,
    )
    db.add(normalized_representation)
    db.flush()

    db.add(
        DocumentNormalizedContent(
            representation_id=normalized_representation.id,
            format=DOCUMENT_FORMAT_MARKDOWN,
            parser_version=DOCUMENT_PARSER_VERSION,
            normalization_version=DOCUMENT_NORMALIZATION_VERSION,
            normalized_text=parsed.normalized_text,
            content_sha256=parsed.content_sha256,
            block_count=len(parsed.blocks),
        )
    )

    block_rows: list[DocumentBlock] = []
    for block in parsed.blocks:
        block_text_hash = text_sha256(block.text)
        block_id = stable_document_block_id(
            source_sha256=parsed.source_sha256,
            parser_version=DOCUMENT_PARSER_VERSION,
            block_order=block.block_order,
            block_kind=block.block_kind,
            heading_path=block.heading_path,
            text_sha256=block_text_hash,
        )
        block_row = DocumentBlock(
            id=str(uuid4()),
            representation_id=normalized_representation.id,
            block_id=block_id,
            block_order=block.block_order,
            block_kind=block.block_kind,
            heading_level=block.heading_level,
            heading_path=list(block.heading_path),
            char_start=block.char_start,
            char_end=block.char_end,
            text_sha256=block_text_hash,
            text_content=block.text,
            normalization_version=DOCUMENT_NORMALIZATION_VERSION,
        )
        db.add(block_row)
        block_rows.append(block_row)
    db.flush()

    # Structure is preserved on DocumentBlock rows. Only retrieval chunks become
    # ContentUnits so the shared orchestrator does not embed duplicate block vectors.
    chunk_order = 0
    for block in block_rows:
        local_chunks = split_document_text(
            block.text_content,
            chunk_size=chunk_size,
            overlap=CHUNK_OVERLAP,
        )
        if not local_chunks:
            continue
        for local_start, local_end, chunk_text in local_chunks:
            char_start = block.char_start + local_start
            char_end = block.char_start + local_end
            if parsed.normalized_text[char_start:char_end] != chunk_text:
                raise IngestionError(
                    "document_normalization_failed",
                    "Document chunk offsets do not match normalized text.",
                )
            chunk_hash = text_sha256(chunk_text)
            locator = _persist_document_locator(
                db,
                asset=asset,
                representation=normalized_representation,
                processing_generation=processing_generation,
                block_id=block.block_id,
                block_kind=block.block_kind,
                heading_path=list(block.heading_path),
                char_start=char_start,
                char_end=char_end,
                text_sha256_value=chunk_hash,
                created_at=created_at,
            )
            db.add(
                ContentUnit(
                    workspace_id=asset.workspace_id,
                    asset_id=asset.id,
                    representation_id=normalized_representation.id,
                    source_locator_id=locator.id,
                    unit_kind="document_text_chunk",
                    unit_order=chunk_order,
                    text_content=chunk_text,
                    token_count=estimate_token_count(chunk_text),
                    char_start=char_start,
                    char_end=char_end,
                    index_version=asset.current_index_version,
                    created_at=created_at,
                )
            )
            chunk_order += 1

    if chunk_order == 0:
        raise IngestionError(
            "document_normalization_failed",
            "Document produced no non-empty text chunks.",
        )
    db.flush()


def delete_document_content(db: Session, asset_id: str) -> None:
    """Asset-delete cleanup: drop retrieval units only.

    Match PDF-style historical integrity: ContentUnits and their embeddings are
    removed for reindex/delete job readiness, but representations, normalized
    content, blocks, and locator details remain for Citation/NoteSource reopen.
    Object bytes are discarded by the orchestrator; source availability is owned
    by Asset deletion/API, not by erasing immutable history rows.
    """
    # Explicit embedding delete keeps SQLite unit tests deterministic even when
    # PRAGMA foreign_keys is off; PostgreSQL CASCADE would also remove them.
    db.execute(delete(ContentUnitEmbedding).where(ContentUnitEmbedding.asset_id == asset_id))
    db.execute(delete(ContentUnit).where(ContentUnit.asset_id == asset_id))


class DocumentIngestionAdapter:
    asset_kind = "document"

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
        _validate_document_config(config_snapshot)
        if asset.mime_type != MARKDOWN_MIME:
            raise IngestionError(
                "asset_mime_mismatch",
                f"Document adapter only accepts {MARKDOWN_MIME}.",
            )
        parsed = parse_markdown_document(payload, mime_type=asset.mime_type)
        if asset.source_sha256 is not None and asset.source_sha256.lower() != parsed.source_sha256:
            raise IngestionError(
                "source_object_integrity_mismatch",
                "Document source SHA-256 does not match the asset record.",
            )
        object_key = build_document_normalized_object_key(asset, processing_generation)
        replace_document_content(
            db,
            asset=asset,
            parsed=parsed,
            processing_generation=processing_generation,
            chunk_size=_chunk_size(config_snapshot),
            created_at=created_at,
            normalized_object_key=object_key,
        )
        normalized_payload = parsed.normalized_text.encode("utf-8")
        return IngestionResult(
            generated_objects=(
                GeneratedObject(
                    object_key=object_key,
                    payload=normalized_payload,
                    content_type=NORMALIZED_CONTENT_TYPE,
                    content_sha256=parsed.content_sha256,
                ),
            )
        )

    def cleanup(self, db: Session, *, asset: Asset) -> None:
        delete_document_content(db, asset.id)


def _chunk_size(snapshot: Mapping[str, object]) -> int:
    value = snapshot.get("chunkSize", CHUNK_SIZE)
    if not isinstance(value, int) or isinstance(value, bool) or not 200 <= value <= 4000:
        raise IngestionError("invalid_chunk_size", "Ingestion job has an invalid chunk size.")
    return value


def _validate_document_config(snapshot: Mapping[str, object]) -> None:
    expected = {
        "documentFormat": DOCUMENT_FORMAT_MARKDOWN,
        "documentParserVersion": DOCUMENT_PARSER_VERSION,
        "documentNormalizationVersion": DOCUMENT_NORMALIZATION_VERSION,
    }
    for key, value in expected.items():
        if key not in snapshot or snapshot[key] != value:
            raise IngestionError(
                "document_configuration_mismatch",
                "Document parser/normalization configuration does not match the job snapshot.",
            )


def _assert_generation_available(
    db: Session,
    *,
    asset_id: str,
    processing_generation: int,
) -> None:
    existing = db.scalar(
        select(AssetRepresentation.id).where(
            AssetRepresentation.asset_id == asset_id,
            AssetRepresentation.processing_generation == processing_generation,
            AssetRepresentation.representation_kind.in_(
                ("document_source", "document_normalized")
            ),
        )
    )
    if existing is not None:
        raise IngestionError(
            "document_generation_already_exists",
            "Document processing generation is already materialized and immutable.",
        )


def _persist_document_locator(
    db: Session,
    *,
    asset: Asset,
    representation: AssetRepresentation,
    processing_generation: int,
    block_id: str,
    block_kind: str,
    heading_path: list[str],
    char_start: int,
    char_end: int,
    text_sha256_value: str,
    created_at: datetime,
) -> EvidenceLocator:
    if (
        representation.asset_id != asset.id
        or representation.processing_generation != processing_generation
        or representation.representation_kind != "document_normalized"
    ):
        raise IngestionError(
            "document_evidence_representation_invalid",
            "Document locator requires the normalized representation for this generation.",
        )
    locator = EvidenceLocator(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        locator_kind="document_anchor",
        locator_version=1,
        processing_generation_snapshot=processing_generation,
        representation_id_snapshot=representation.id,
        created_at=created_at,
    )
    db.add(locator)
    db.flush()
    db.add(
        DocumentLocatorDetail(
            locator_id=locator.id,
            block_id=block_id,
            block_kind=block_kind,
            heading_path=heading_path,
            char_start=char_start,
            char_end=char_end,
            text_sha256=text_sha256_value,
            normalization_version=DOCUMENT_NORMALIZATION_VERSION,
        )
    )
    return locator
