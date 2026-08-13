"""DOCX ingestion adapter. Not production-registry enabled (S0 handoff)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ai_pdf_api.modalities.docx import (
    DOCX_MIME,
    DOCX_NORMALIZATION_VERSION,
    DOCX_PARSER_VERSION,
    parse_docx_document,
    split_office_text,
    stable_docx_block_id,
    text_sha256,
)
from ai_pdf_api.modalities.ingestion import GeneratedObject, IngestionError, IngestionResult
from ai_pdf_api.modalities.office_ooxml import OfficePackageError
from ai_pdf_api.modalities.text import estimate_token_count
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ContentUnit,
    ContentUnitEmbedding,
    DocxBlock,
    DocxLocatorDetail,
    DocxNormalizedContent,
    EvidenceLocator,
)

CHUNK_SIZE = 1_200
CHUNK_OVERLAP = 200
NORMALIZED_CONTENT_TYPE = "text/plain; charset=utf-8"


def build_docx_normalized_object_key(asset: Asset, processing_generation: int) -> str:
    return (
        f"workspaces/{asset.workspace_id}/assets/{asset.id}/representations/"
        f"{processing_generation}/docx-normalized.txt"
    )


class DocxIngestionAdapter:
    asset_kind = "docx"

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
        _validate_docx_config(config_snapshot)
        if asset.mime_type != DOCX_MIME:
            raise IngestionError("asset_mime_mismatch", f"DOCX adapter only accepts {DOCX_MIME}.")
        try:
            parsed = parse_docx_document(payload, mime_type=asset.mime_type)
        except OfficePackageError as error:
            raise IngestionError(error.code, str(error)) from error
        if asset.source_sha256 is not None and asset.source_sha256.lower() != parsed.source_sha256:
            raise IngestionError(
                "source_object_integrity_mismatch",
                "DOCX source SHA-256 does not match the asset record.",
            )
        object_key = build_docx_normalized_object_key(asset, processing_generation)
        replace_docx_content(
            db,
            asset=asset,
            parsed=parsed,
            processing_generation=processing_generation,
            chunk_size=_chunk_size(config_snapshot),
            created_at=created_at,
            normalized_object_key=object_key,
        )
        return IngestionResult(
            generated_objects=(
                GeneratedObject(
                    object_key=object_key,
                    payload=parsed.normalized_text.encode("utf-8"),
                    content_type=NORMALIZED_CONTENT_TYPE,
                    content_sha256=parsed.content_sha256,
                ),
            )
        )

    def cleanup(self, db: Session, *, asset: Asset) -> None:
        db.execute(delete(ContentUnitEmbedding).where(ContentUnitEmbedding.asset_id == asset.id))
        db.execute(delete(ContentUnit).where(ContentUnit.asset_id == asset.id))


def replace_docx_content(
    db: Session,
    *,
    asset: Asset,
    parsed,
    processing_generation: int,
    chunk_size: int,
    created_at: datetime,
    normalized_object_key: str,
) -> None:
    if asset.asset_kind != "docx":
        raise IngestionError("docx_asset_kind_invalid", "DOCX adapter received a non-docx asset.")
    existing = db.scalar(
        select(AssetRepresentation.id).where(
            AssetRepresentation.asset_id == asset.id,
            AssetRepresentation.processing_generation == processing_generation,
            AssetRepresentation.representation_kind.in_(("docx_source", "docx_normalized")),
        )
    )
    if existing is not None:
        raise IngestionError(
            "docx_generation_already_exists",
            "DOCX processing generation is already materialized and immutable.",
        )

    source_representation = AssetRepresentation(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        representation_kind="docx_source",
        processing_generation=processing_generation,
        generator_provider="docx",
        generator_version=DOCX_PARSER_VERSION,
        object_key=asset.object_key,
        content_sha256=parsed.source_sha256,
        created_at=created_at,
    )
    db.add(source_representation)
    normalized_representation = AssetRepresentation(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        representation_kind="docx_normalized",
        processing_generation=processing_generation,
        generator_provider="docx",
        generator_version=DOCX_PARSER_VERSION,
        object_key=normalized_object_key,
        content_sha256=parsed.content_sha256,
        created_at=created_at,
    )
    db.add(normalized_representation)
    db.flush()
    db.add(
        DocxNormalizedContent(
            representation_id=normalized_representation.id,
            format="docx",
            parser_version=DOCX_PARSER_VERSION,
            normalization_version=DOCX_NORMALIZATION_VERSION,
            normalized_text=parsed.normalized_text,
            content_sha256=parsed.content_sha256,
            block_count=len(parsed.blocks),
        )
    )
    chunk_order = 0
    for block in parsed.blocks:
        block_text_hash = text_sha256(block.text)
        block_id = stable_docx_block_id(
            source_sha256=parsed.source_sha256,
            parser_version=DOCX_PARSER_VERSION,
            block_order=block.block_order,
            block_kind=block.block_kind,
            heading_path=block.heading_path,
            text_sha256_value=block_text_hash,
        )
        db.add(
            DocxBlock(
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
                normalization_version=DOCX_NORMALIZATION_VERSION,
            )
        )
        for local_start, local_end, chunk_text in split_office_text(
            block.text, chunk_size, overlap=CHUNK_OVERLAP
        ):
            char_start = block.char_start + local_start
            char_end = block.char_start + local_end
            chunk_hash = text_sha256(chunk_text)
            locator = EvidenceLocator(
                workspace_id=asset.workspace_id,
                asset_id=asset.id,
                locator_kind="docx_anchor",
                locator_version=1,
                processing_generation_snapshot=processing_generation,
                representation_id_snapshot=normalized_representation.id,
                created_at=created_at,
            )
            db.add(locator)
            db.flush()
            db.add(
                DocxLocatorDetail(
                    locator_id=locator.id,
                    block_id=block_id,
                    block_kind=block.block_kind,
                    heading_path=list(block.heading_path),
                    char_start=char_start,
                    char_end=char_end,
                    text_sha256=chunk_hash,
                    normalization_version=DOCX_NORMALIZATION_VERSION,
                )
            )
            db.add(
                ContentUnit(
                    workspace_id=asset.workspace_id,
                    asset_id=asset.id,
                    representation_id=normalized_representation.id,
                    source_locator_id=locator.id,
                    unit_kind="docx_text_chunk",
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
        raise IngestionError("office_parse_failed", "DOCX produced no non-empty text chunks.")
    db.flush()


def _chunk_size(snapshot: Mapping[str, object]) -> int:
    value = snapshot.get("chunkSize", CHUNK_SIZE)
    if not isinstance(value, int) or isinstance(value, bool) or not 200 <= value <= 4000:
        raise IngestionError("invalid_chunk_size", "Ingestion job has an invalid chunk size.")
    return value


def _validate_docx_config(snapshot: Mapping[str, object]) -> None:
    expected = {
        "docxParserVersion": DOCX_PARSER_VERSION,
        "docxNormalizationVersion": DOCX_NORMALIZATION_VERSION,
    }
    for key, value in expected.items():
        if snapshot.get(key) != value:
            raise IngestionError(
                "docx_configuration_mismatch",
                "DOCX parser/normalization configuration does not match the job snapshot.",
            )
