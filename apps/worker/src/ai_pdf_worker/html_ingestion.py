"""HTML ingestion adapter. Not production-enabled until S0 catalog/registry handoff."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ai_pdf_api.modalities.html import (
    HTML_FORMAT,
    HTML_MIME_TYPES,
    HTML_NORMALIZATION_VERSION,
    HTML_PARSER_VERSION,
    HTML_SANITIZER_VERSION,
    stable_html_block_id,
    text_sha256,
)
from ai_pdf_api.modalities.ingestion import GeneratedObject, IngestionError, IngestionResult
from ai_pdf_api.modalities.text import estimate_token_count
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ContentUnit,
    ContentUnitEmbedding,
    EvidenceLocator,
    HtmlBlock,
    HtmlLocatorDetail,
    HtmlNormalizedContent,
)

from ai_pdf_worker.html_parse import HtmlParseResult, parse_html_document, split_html_text

CHUNK_SIZE = 1_200
CHUNK_OVERLAP = 200
NORMALIZED_CONTENT_TYPE = "text/plain; charset=utf-8"
SANITIZED_CONTENT_TYPE = "text/html; charset=utf-8"

__all__ = [
    "HtmlIngestionAdapter",
    "delete_html_content",
    "parse_html_document",
    "replace_html_content",
]


def build_html_normalized_object_key(asset: Asset, processing_generation: int) -> str:
    return (
        f"workspaces/{asset.workspace_id}/assets/{asset.id}/representations/"
        f"{processing_generation}/html-normalized.txt"
    )


def build_html_sanitized_object_key(asset: Asset, processing_generation: int) -> str:
    return (
        f"workspaces/{asset.workspace_id}/assets/{asset.id}/representations/"
        f"{processing_generation}/html-sanitized.html"
    )


def replace_html_content(
    db: Session,
    *,
    asset: Asset,
    parsed: HtmlParseResult,
    processing_generation: int,
    chunk_size: int,
    created_at: datetime,
    normalized_object_key: str,
    sanitized_object_key: str,
) -> None:
    if asset.asset_kind != "html":
        raise IngestionError(
            "html_asset_kind_invalid",
            "HTML adapter received a non-html asset.",
        )
    _assert_generation_available(
        db,
        asset_id=asset.id,
        processing_generation=processing_generation,
    )

    source_representation = AssetRepresentation(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        representation_kind="html_source",
        processing_generation=processing_generation,
        generator_provider="html",
        generator_version=HTML_PARSER_VERSION,
        object_key=asset.object_key,
        content_sha256=parsed.source_sha256,
        created_at=created_at,
    )
    db.add(source_representation)

    normalized_representation = AssetRepresentation(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        representation_kind="html_normalized",
        processing_generation=processing_generation,
        generator_provider="html",
        generator_version=HTML_PARSER_VERSION,
        object_key=normalized_object_key,
        content_sha256=parsed.content_sha256,
        created_at=created_at,
    )
    db.add(normalized_representation)

    sanitized_representation = AssetRepresentation(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        representation_kind="html_sanitized",
        processing_generation=processing_generation,
        generator_provider="html",
        generator_version=HTML_SANITIZER_VERSION,
        object_key=sanitized_object_key,
        content_sha256=text_sha256(parsed.sanitized_html),
        created_at=created_at,
    )
    db.add(sanitized_representation)
    db.flush()

    db.add(
        HtmlNormalizedContent(
            representation_id=normalized_representation.id,
            format=HTML_FORMAT,
            parser_version=HTML_PARSER_VERSION,
            sanitizer_version=HTML_SANITIZER_VERSION,
            normalization_version=HTML_NORMALIZATION_VERSION,
            normalized_text=parsed.normalized_text,
            sanitized_html=parsed.sanitized_html,
            content_sha256=parsed.content_sha256,
            block_count=len(parsed.blocks),
        )
    )

    block_rows: list[HtmlBlock] = []
    for block in parsed.blocks:
        block_text_hash = text_sha256(block.text)
        block_id = stable_html_block_id(
            source_sha256=parsed.source_sha256,
            parser_version=HTML_PARSER_VERSION,
            sanitizer_version=HTML_SANITIZER_VERSION,
            block_order=block.block_order,
            block_kind=block.block_kind,
            heading_path=block.heading_path,
            text_sha256_value=block_text_hash,
        )
        block_row = HtmlBlock(
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
            normalization_version=HTML_NORMALIZATION_VERSION,
            css_path_hint=block.css_path_hint,
        )
        db.add(block_row)
        block_rows.append(block_row)
    db.flush()

    chunk_order = 0
    for block in block_rows:
        local_chunks = split_html_text(
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
                    "html_normalization_failed",
                    "HTML chunk offsets do not match normalized text.",
                )
            chunk_hash = text_sha256(chunk_text)
            locator = _persist_html_locator(
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
                css_path_hint=block.css_path_hint,
                created_at=created_at,
            )
            db.add(
                ContentUnit(
                    workspace_id=asset.workspace_id,
                    asset_id=asset.id,
                    representation_id=normalized_representation.id,
                    source_locator_id=locator.id,
                    unit_kind="html_text_chunk",
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
            "html_normalization_failed",
            "HTML produced no non-empty text chunks.",
        )
    db.flush()


def delete_html_content(db: Session, asset_id: str) -> None:
    db.execute(delete(ContentUnitEmbedding).where(ContentUnitEmbedding.asset_id == asset_id))
    db.execute(delete(ContentUnit).where(ContentUnit.asset_id == asset_id))


class HtmlIngestionAdapter:
    asset_kind = "html"

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
        _validate_html_config(config_snapshot)
        if asset.mime_type.lower() not in HTML_MIME_TYPES:
            raise IngestionError(
                "asset_mime_mismatch",
                f"HTML adapter only accepts {sorted(HTML_MIME_TYPES)}.",
            )
        parsed = parse_html_document(payload, mime_type=asset.mime_type)
        if asset.source_sha256 is not None and asset.source_sha256.lower() != parsed.source_sha256:
            raise IngestionError(
                "source_object_integrity_mismatch",
                "HTML source SHA-256 does not match the asset record.",
            )
        normalized_key = build_html_normalized_object_key(asset, processing_generation)
        sanitized_key = build_html_sanitized_object_key(asset, processing_generation)
        replace_html_content(
            db,
            asset=asset,
            parsed=parsed,
            processing_generation=processing_generation,
            chunk_size=_chunk_size(config_snapshot),
            created_at=created_at,
            normalized_object_key=normalized_key,
            sanitized_object_key=sanitized_key,
        )
        return IngestionResult(
            generated_objects=(
                GeneratedObject(
                    object_key=normalized_key,
                    payload=parsed.normalized_text.encode("utf-8"),
                    content_type=NORMALIZED_CONTENT_TYPE,
                    content_sha256=parsed.content_sha256,
                ),
                GeneratedObject(
                    object_key=sanitized_key,
                    payload=parsed.sanitized_html.encode("utf-8"),
                    content_type=SANITIZED_CONTENT_TYPE,
                    content_sha256=text_sha256(parsed.sanitized_html),
                ),
            )
        )

    def cleanup(self, db: Session, *, asset: Asset) -> None:
        delete_html_content(db, asset.id)


def _chunk_size(snapshot: Mapping[str, object]) -> int:
    value = snapshot.get("chunkSize", CHUNK_SIZE)
    if not isinstance(value, int) or isinstance(value, bool) or not 200 <= value <= 4000:
        raise IngestionError("invalid_chunk_size", "Ingestion job has an invalid chunk size.")
    return value


def _validate_html_config(snapshot: Mapping[str, object]) -> None:
    expected = {
        "htmlFormat": HTML_FORMAT,
        "htmlParserVersion": HTML_PARSER_VERSION,
        "htmlSanitizerVersion": HTML_SANITIZER_VERSION,
        "htmlNormalizationVersion": HTML_NORMALIZATION_VERSION,
    }
    for key, value in expected.items():
        if key not in snapshot or snapshot[key] != value:
            raise IngestionError(
                "html_configuration_mismatch",
                "HTML parser/sanitizer/normalization configuration does not match the job snapshot.",
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
                ("html_source", "html_normalized", "html_sanitized")
            ),
        )
    )
    if existing is not None:
        raise IngestionError(
            "html_generation_already_exists",
            "HTML processing generation is already materialized and immutable.",
        )


def _persist_html_locator(
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
    css_path_hint: str | None,
    created_at: datetime,
) -> EvidenceLocator:
    if (
        representation.asset_id != asset.id
        or representation.processing_generation != processing_generation
        or representation.representation_kind != "html_normalized"
    ):
        raise IngestionError(
            "html_evidence_representation_invalid",
            "HTML locator requires the normalized representation for this generation.",
        )
    locator = EvidenceLocator(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        locator_kind="html_anchor",
        locator_version=1,
        processing_generation_snapshot=processing_generation,
        representation_id_snapshot=representation.id,
        created_at=created_at,
    )
    db.add(locator)
    db.flush()
    db.add(
        HtmlLocatorDetail(
            locator_id=locator.id,
            block_id=block_id,
            block_kind=block_kind,
            heading_path=heading_path,
            char_start=char_start,
            char_end=char_end,
            text_sha256=text_sha256_value,
            normalization_version=HTML_NORMALIZATION_VERSION,
            css_path_hint=css_path_hint,
        )
    )
    return locator
