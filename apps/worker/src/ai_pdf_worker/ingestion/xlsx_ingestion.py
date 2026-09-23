"""XLSX ingestion adapter. Not production-registry enabled (S0 handoff)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ai_pdf_api.modalities.ingestion import GeneratedObject, IngestionError, IngestionResult
from ai_pdf_api.modalities.office_ooxml import OfficePackageError
from ai_pdf_api.modalities.text import estimate_token_count
from ai_pdf_api.modalities.xlsx import (
    XLSX_MIME,
    XLSX_NORMALIZATION_VERSION,
    XLSX_PARSER_VERSION,
    parse_xlsx_workbook,
)
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ContentUnit,
    ContentUnitEmbedding,
    EvidenceLocator,
    XlsxLocatorDetail,
)


class XlsxIngestionAdapter:
    asset_kind = "xlsx"

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
        if config_snapshot.get("xlsxParserVersion") != XLSX_PARSER_VERSION:
            raise IngestionError(
                "xlsx_configuration_mismatch",
                "XLSX parser configuration does not match the job snapshot.",
            )
        if asset.mime_type != XLSX_MIME:
            raise IngestionError("asset_mime_mismatch", f"XLSX adapter only accepts {XLSX_MIME}.")
        try:
            parsed = parse_xlsx_workbook(payload, mime_type=asset.mime_type)
        except OfficePackageError as error:
            raise IngestionError(error.code, str(error)) from error
        if asset.source_sha256 is not None and asset.source_sha256.lower() != parsed.source_sha256:
            raise IngestionError(
                "source_object_integrity_mismatch",
                "XLSX source SHA-256 does not match the asset record.",
            )
        existing = db.scalar(
            select(AssetRepresentation.id).where(
                AssetRepresentation.asset_id == asset.id,
                AssetRepresentation.processing_generation == processing_generation,
                AssetRepresentation.representation_kind.in_(("xlsx_source", "xlsx_normalized")),
            )
        )
        if existing is not None:
            raise IngestionError(
                "xlsx_generation_already_exists",
                "XLSX processing generation is already materialized and immutable.",
            )
        object_key = (
            f"workspaces/{asset.workspace_id}/assets/{asset.id}/representations/"
            f"{processing_generation}/xlsx-normalized.txt"
        )
        source = AssetRepresentation(
            workspace_id=asset.workspace_id,
            asset_id=asset.id,
            representation_kind="xlsx_source",
            processing_generation=processing_generation,
            generator_provider="xlsx",
            generator_version=XLSX_PARSER_VERSION,
            object_key=asset.object_key,
            content_sha256=parsed.source_sha256,
            created_at=created_at,
        )
        normalized = AssetRepresentation(
            workspace_id=asset.workspace_id,
            asset_id=asset.id,
            representation_kind="xlsx_normalized",
            processing_generation=processing_generation,
            generator_provider="xlsx",
            generator_version=XLSX_PARSER_VERSION,
            object_key=object_key,
            content_sha256=parsed.content_sha256,
            created_at=created_at,
        )
        db.add(source)
        db.add(normalized)
        db.flush()
        for order, cell in enumerate(parsed.cells):
            locator = EvidenceLocator(
                workspace_id=asset.workspace_id,
                asset_id=asset.id,
                locator_kind="xlsx_range",
                locator_version=1,
                processing_generation_snapshot=processing_generation,
                representation_id_snapshot=normalized.id,
                created_at=created_at,
            )
            db.add(locator)
            db.flush()
            db.add(
                XlsxLocatorDetail(
                    locator_id=locator.id,
                    sheet_name=cell.sheet_name,
                    start_cell=cell.cell_ref,
                    end_cell=cell.cell_ref,
                    text_sha256=cell.text_sha256,
                    displayed_text=cell.text,
                    normalization_version=XLSX_NORMALIZATION_VERSION,
                )
            )
            db.add(
                ContentUnit(
                    workspace_id=asset.workspace_id,
                    asset_id=asset.id,
                    representation_id=normalized.id,
                    source_locator_id=locator.id,
                    unit_kind="xlsx_cell_text",
                    unit_order=order,
                    text_content=cell.text,
                    token_count=estimate_token_count(cell.text),
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
