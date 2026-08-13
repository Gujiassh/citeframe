"""PPTX ingestion adapter. Not production-registry enabled (S0 handoff)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ai_pdf_api.modalities.ingestion import GeneratedObject, IngestionError, IngestionResult
from ai_pdf_api.modalities.office_ooxml import OfficePackageError
from ai_pdf_api.modalities.pptx import (
    PPTX_MIME,
    PPTX_NORMALIZATION_VERSION,
    PPTX_PARSER_VERSION,
    parse_pptx_presentation,
)
from ai_pdf_api.modalities.text import estimate_token_count
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ContentUnit,
    ContentUnitEmbedding,
    EvidenceLocator,
    PptxLocatorDetail,
)


class PptxIngestionAdapter:
    asset_kind = "pptx"

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
        if config_snapshot.get("pptxParserVersion") != PPTX_PARSER_VERSION:
            raise IngestionError(
                "pptx_configuration_mismatch",
                "PPTX parser configuration does not match the job snapshot.",
            )
        if asset.mime_type != PPTX_MIME:
            raise IngestionError("asset_mime_mismatch", f"PPTX adapter only accepts {PPTX_MIME}.")
        try:
            parsed = parse_pptx_presentation(payload, mime_type=asset.mime_type)
        except OfficePackageError as error:
            raise IngestionError(error.code, str(error)) from error
        if asset.source_sha256 is not None and asset.source_sha256.lower() != parsed.source_sha256:
            raise IngestionError(
                "source_object_integrity_mismatch",
                "PPTX source SHA-256 does not match the asset record.",
            )
        existing = db.scalar(
            select(AssetRepresentation.id).where(
                AssetRepresentation.asset_id == asset.id,
                AssetRepresentation.processing_generation == processing_generation,
                AssetRepresentation.representation_kind.in_(("pptx_source", "pptx_normalized")),
            )
        )
        if existing is not None:
            raise IngestionError(
                "pptx_generation_already_exists",
                "PPTX processing generation is already materialized and immutable.",
            )
        object_key = (
            f"workspaces/{asset.workspace_id}/assets/{asset.id}/representations/"
            f"{processing_generation}/pptx-normalized.txt"
        )
        source = AssetRepresentation(
            workspace_id=asset.workspace_id,
            asset_id=asset.id,
            representation_kind="pptx_source",
            processing_generation=processing_generation,
            generator_provider="pptx",
            generator_version=PPTX_PARSER_VERSION,
            object_key=asset.object_key,
            content_sha256=parsed.source_sha256,
            created_at=created_at,
        )
        normalized = AssetRepresentation(
            workspace_id=asset.workspace_id,
            asset_id=asset.id,
            representation_kind="pptx_normalized",
            processing_generation=processing_generation,
            generator_provider="pptx",
            generator_version=PPTX_PARSER_VERSION,
            object_key=object_key,
            content_sha256=parsed.content_sha256,
            created_at=created_at,
        )
        db.add(source)
        db.add(normalized)
        db.flush()
        for order, shape in enumerate(parsed.shapes):
            locator = EvidenceLocator(
                workspace_id=asset.workspace_id,
                asset_id=asset.id,
                locator_kind="pptx_shape",
                locator_version=1,
                processing_generation_snapshot=processing_generation,
                representation_id_snapshot=normalized.id,
                created_at=created_at,
            )
            db.add(locator)
            db.flush()
            db.add(
                PptxLocatorDetail(
                    locator_id=locator.id,
                    slide_index=shape.slide_index,
                    shape_id=shape.shape_id,
                    text_sha256=shape.text_sha256,
                    displayed_text=shape.text,
                    normalization_version=PPTX_NORMALIZATION_VERSION,
                )
            )
            db.add(
                ContentUnit(
                    workspace_id=asset.workspace_id,
                    asset_id=asset.id,
                    representation_id=normalized.id,
                    source_locator_id=locator.id,
                    unit_kind="pptx_shape_text",
                    unit_order=order,
                    text_content=shape.text,
                    token_count=estimate_token_count(shape.text),
                    char_start=None,
                    char_end=None,
                    index_version=asset.current_index_version,
                    created_at=created_at,
                )
            )
        db.flush()
        return IngestionResult(
            generated_objects=(
                GeneratedObject(
                    object_key=object_key,
                    payload=parsed.normalized_text.encode("utf-8"),
                    content_type="text/plain; charset=utf-8",
                    content_sha256=parsed.content_sha256,
                ),
            )
        )

    def cleanup(self, db: Session, *, asset: Asset) -> None:
        db.execute(delete(ContentUnitEmbedding).where(ContentUnitEmbedding.asset_id == asset.id))
        db.execute(delete(ContentUnit).where(ContentUnit.asset_id == asset.id))
