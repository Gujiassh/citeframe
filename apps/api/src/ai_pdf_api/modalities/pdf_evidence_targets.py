"""Resolve explicit PDF region Evidence targets into generation image crops (PV-4)."""

from __future__ import annotations

from datetime import datetime

import fitz
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_pdf_api.modalities.evidence import PDF_COORDINATE_SPACE
from ai_pdf_api.modalities.evidence_targets import (
    EvidenceTargetError,
    ImageBytesLoader,
    ResolvedEvidenceTarget,
)
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ContentUnit,
    EvidenceLocator,
    PdfLocatorDetail,
    SpatialLocatorRegion,
)
from ai_pdf_api.schemas.chat import EvidenceTargetRequest, PdfRegionEvidenceTarget, SpatialRegion

_MAX_CROP_EDGE_PX = 1280
_CROP_DPI = 150


class PdfRegionEvidenceTargetResolver:
    kind = "pdf_region"

    def resolve(
        self,
        db: Session,
        *,
        workspace_id: str,
        target: EvidenceTargetRequest,
        created_at: datetime,
        image_bytes_loader: ImageBytesLoader,
        include_image_payloads: bool,
    ) -> ResolvedEvidenceTarget:
        if not isinstance(target, PdfRegionEvidenceTarget):
            raise EvidenceTargetError(
                "evidence_target_kind_invalid",
                "The PDF Evidence target has an invalid payload.",
            )
        return _resolve_pdf_region_target(
            db,
            workspace_id=workspace_id,
            target=target,
            created_at=created_at,
            image_bytes_loader=image_bytes_loader,
            include_image_payloads=include_image_payloads,
        )


def _resolve_pdf_region_target(
    db: Session,
    *,
    workspace_id: str,
    target: PdfRegionEvidenceTarget,
    created_at: datetime,
    image_bytes_loader: ImageBytesLoader,
    include_image_payloads: bool,
) -> ResolvedEvidenceTarget:
    asset = db.scalar(
        select(Asset).where(
            Asset.id == target.assetId,
            Asset.workspace_id == workspace_id,
            Asset.asset_kind == "pdf",
            Asset.status == "ready",
            Asset.deleted_at.is_(None),
        )
    )
    if asset is None:
        raise EvidenceTargetError(
            "evidence_target_asset_unavailable",
            "The selected PDF is not available in this workspace.",
            404,
        )
    if asset.current_processing_generation != target.processingGeneration:
        raise EvidenceTargetError(
            "evidence_target_generation_changed",
            "The PDF changed after the region was selected. Select the region again.",
            409,
        )
    if not asset.object_key:
        raise EvidenceTargetError(
            "evidence_target_source_missing",
            "The PDF source object is unavailable.",
            409,
        )

    representation = db.scalar(
        select(AssetRepresentation)
        .where(
            AssetRepresentation.workspace_id == workspace_id,
            AssetRepresentation.asset_id == asset.id,
            AssetRepresentation.processing_generation == target.processingGeneration,
        )
        .order_by(AssetRepresentation.created_at.desc())
        .limit(1)
    )
    if representation is None:
        raise EvidenceTargetError(
            "evidence_target_display_missing",
            "No PDF representation exists for the selected processing generation.",
            409,
        )

    excerpt = _excerpt_for_page(
        db,
        asset_id=asset.id,
        page_number=target.pageNumber,
    )
    if not excerpt:
        excerpt = f"PDF page {target.pageNumber} region selection"

    try:
        pdf_bytes = image_bytes_loader(asset.object_key)
    except Exception as error:
        raise EvidenceTargetError(
            "evidence_target_source_missing",
            "The PDF source object could not be loaded.",
            409,
        ) from error
    if asset.source_sha256 and sha256_hex(pdf_bytes) != asset.source_sha256.lower():
        raise EvidenceTargetError(
            "evidence_target_source_mismatch",
            "The PDF source bytes do not match the asset snapshot.",
            409,
        )

    page_geometry = _page_geometry(pdf_bytes, target.pageNumber)
    crops: tuple[bytes, ...] = ()
    if include_image_payloads:
        try:
            crops = crop_pdf_regions_png(
                pdf_bytes,
                page_number=target.pageNumber,
                regions=target.regions,
            )
        except EvidenceTargetError:
            raise
        except Exception as error:
            raise EvidenceTargetError(
                "evidence_target_pdf_crop_failed",
                "Failed to render the selected PDF region.",
                409,
            ) from error
        if not crops:
            raise EvidenceTargetError(
                "evidence_target_region_empty",
                "The selected PDF region has no pixels.",
                422,
            )

    locator = EvidenceLocator(
        workspace_id=workspace_id,
        asset_id=asset.id,
        locator_kind="pdf_region",
        locator_version=1,
        processing_generation_snapshot=target.processingGeneration,
        representation_id_snapshot=representation.id,
        created_at=created_at,
    )
    db.add(locator)
    db.flush()
    db.add(
        PdfLocatorDetail(
            locator_id=locator.id,
            page_number=target.pageNumber,
            coordinate_space=PDF_COORDINATE_SPACE,
            crop_x0_points=page_geometry["crop_x0"],
            crop_y0_points=page_geometry["crop_y0"],
            crop_x1_points=page_geometry["crop_x1"],
            crop_y1_points=page_geometry["crop_y1"],
            rotation_degrees=page_geometry["rotation"],
            display_width_points=page_geometry["display_width"],
            display_height_points=page_geometry["display_height"],
        )
    )
    db.add_all(
        [
            SpatialLocatorRegion(
                locator_id=locator.id,
                region_order=index,
                x=region.x,
                y=region.y,
                width=region.width,
                height=region.height,
            )
            for index, region in enumerate(target.regions)
        ]
    )
    db.flush()

    return ResolvedEvidenceTarget(
        asset=asset,
        locator=locator,
        representation=representation,
        excerpt=excerpt[:4000],
        image_payloads=crops,
    )


def sha256_hex(payload: bytes) -> str:
    from hashlib import sha256

    return sha256(payload).hexdigest()


def _excerpt_for_page(db: Session, *, asset_id: str, page_number: int) -> str:
    units = db.scalars(
        select(ContentUnit)
        .where(
            ContentUnit.asset_id == asset_id,
            ContentUnit.unit_kind.in_(("pdf_text_chunk", "pdf_ocr_region", "pdf_figure", "pdf_table")),
        )
        .order_by(ContentUnit.unit_order)
        .limit(32)
    ).all()
    # Prefer units whose locator is this page when join available; otherwise first non-empty.
    texts = [u.text_content.strip() for u in units if u.text_content and u.text_content.strip()]
    if not texts:
        return ""
    return texts[0][:2000]


def _page_geometry(pdf_bytes: bytes, page_number: int) -> dict[str, float | int]:
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if page_number < 1 or page_number > len(document):
            raise EvidenceTargetError(
                "evidence_target_page_invalid",
                "The selected PDF page is out of range.",
                422,
            )
        page = document[page_number - 1]
        crop = page.cropbox
        rotation = int(page.rotation) % 360
        width = float(crop.width)
        height = float(crop.height)
        if rotation in {90, 270}:
            display_width, display_height = height, width
        else:
            display_width, display_height = width, height
        return {
            "crop_x0": float(crop.x0),
            "crop_y0": float(crop.y0),
            "crop_x1": float(crop.x1),
            "crop_y1": float(crop.y1),
            "rotation": rotation,
            "display_width": display_width,
            "display_height": display_height,
        }
    finally:
        document.close()


def crop_pdf_regions_png(
    pdf_bytes: bytes,
    *,
    page_number: int,
    regions: list[SpatialRegion],
) -> tuple[bytes, ...]:
    """Crop normalized top-left regions from a PDF page to PNG bytes."""
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if page_number < 1 or page_number > len(document):
            raise EvidenceTargetError(
                "evidence_target_page_invalid",
                "The selected PDF page is out of range.",
                422,
            )
        page = document[page_number - 1]
        rect = page.cropbox
        crops: list[bytes] = []
        for region in regions:
            if region.width <= 0 or region.height <= 0:
                raise EvidenceTargetError(
                    "evidence_target_region_empty",
                    "The selected PDF region has no area.",
                    422,
                )
            clip = fitz.Rect(
                rect.x0 + region.x * rect.width,
                rect.y0 + region.y * rect.height,
                rect.x0 + (region.x + region.width) * rect.width,
                rect.y0 + (region.y + region.height) * rect.height,
            )
            clip = clip & rect
            if clip.is_empty or clip.width < 0.5 or clip.height < 0.5:
                raise EvidenceTargetError(
                    "evidence_target_region_empty",
                    "The selected PDF region has no pixels.",
                    422,
                )
            pixmap = page.get_pixmap(clip=clip, dpi=_CROP_DPI, alpha=False)
            # Downscale if longest edge exceeds cap.
            scale = 1.0
            longest = max(pixmap.width, pixmap.height)
            if longest > _MAX_CROP_EDGE_PX:
                scale = _MAX_CROP_EDGE_PX / float(longest)
                matrix = fitz.Matrix(scale, scale)
                pixmap = page.get_pixmap(clip=clip, matrix=fitz.Matrix(_CROP_DPI / 72, _CROP_DPI / 72) * matrix, alpha=False)
            crops.append(pixmap.tobytes("png"))
        return tuple(crops)
    finally:
        document.close()
