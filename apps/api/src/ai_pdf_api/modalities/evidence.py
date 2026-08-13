from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_pdf_api.modalities.document import (
    DOCUMENT_NORMALIZATION_VERSION,
    DocumentIntegrityError,
    validate_document_anchor_range,
    validate_document_normalized_content,
)
from ai_pdf_api.modalities.docx import (
    DocxIntegrityError,
    validate_docx_anchor_range,
    validate_docx_normalized_content,
)
from ai_pdf_api.modalities.pptx import PptxIntegrityError, validate_pptx_shape
from ai_pdf_api.modalities.xlsx import XlsxIntegrityError, validate_xlsx_range
from ai_pdf_api.modalities.html import (
    HtmlIntegrityError,
    validate_html_anchor_range,
    validate_html_normalized_content,
)
from ai_pdf_api.modalities.audio import (
    AudioIntegrityError,
    validate_audio_normalized_content,
    validate_audio_range,
    validate_audio_transcript_segment,
)
from ai_pdf_api.modalities.video import (
    VideoIntegrityError,
    validate_video_frame,
    validate_video_normalized_content,
    validate_video_range,
    validate_video_transcript_segment,
)
from ai_pdf_api.models import (
    AssetRepresentation,
    DocumentBlock,
    DocumentLocatorDetail,
    DocumentNormalizedContent,
    DocxBlock,
    DocxLocatorDetail,
    DocxNormalizedContent,
    EvidenceLocator,
    AudioLocatorDetail,
    AudioNormalizedContent,
    AudioTranscriptSegment,
    VideoFrameLocatorDetail,
    VideoLocatorDetail,
    VideoNormalizedContent,
    VideoTranscriptSegment,
    HtmlBlock,
    HtmlLocatorDetail,
    HtmlNormalizedContent,
    ImageLocatorDetail,
    PdfLocatorDetail,
    PptxLocatorDetail,
    SpatialLocatorRegion,
    XlsxLocatorDetail,
)
from ai_pdf_api.schemas.chat import (
    DocumentAnchorLocator,
    DocxAnchorLocator,
    EvidenceLocatorDto,
    AudioRangeLocator,
    VideoFrameLocator,
    VideoRangeLocator,
    HtmlAnchorLocator,
    ImageRegionLocator,
    PageGeometry,
    PdfPageLocator,
    PdfRegionLocator,
    PptxShapeLocator,
    SpatialRegion,
    XlsxRangeLocator,
)

TypedLocatorDetail = (
    PdfLocatorDetail
    | ImageLocatorDetail
    | DocumentLocatorDetail
    | HtmlLocatorDetail
    | AudioLocatorDetail
    | VideoLocatorDetail
    | VideoFrameLocatorDetail
    | DocxLocatorDetail
    | XlsxLocatorDetail
    | PptxLocatorDetail
    | None
)

PDF_COORDINATE_SPACE = "pdf_crop_box_normalized_top_left_v1"
IMAGE_COORDINATE_SPACE = "image_normalized_top_left_v1"


class EvidenceContractError(RuntimeError):
    pass


class LocatorCodec(Protocol):
    kinds: frozenset[str]
    representation_kinds: frozenset[str]

    def clone_details(
        self,
        db: Session,
        source: EvidenceLocator,
        target: EvidenceLocator,
    ) -> None: ...

    def serialize(self, db: Session, locator: EvidenceLocator) -> EvidenceLocatorDto: ...

    def serialize_loaded(
        self,
        db: Session,
        locator: EvidenceLocator,
        detail: TypedLocatorDetail,
        regions: list[SpatialLocatorRegion],
    ) -> EvidenceLocatorDto: ...

    def retrieval_key(
        self,
        locator: EvidenceLocator,
        serialized: EvidenceLocatorDto,
    ) -> str: ...


def _regions(db: Session, locator_id: str) -> list[SpatialLocatorRegion]:
    return db.scalars(
        select(SpatialLocatorRegion)
        .where(SpatialLocatorRegion.locator_id == locator_id)
        .order_by(SpatialLocatorRegion.region_order)
    ).all()


def _region_dtos(regions: Iterable[SpatialLocatorRegion]) -> list[SpatialRegion]:
    return [
        SpatialRegion(x=region.x, y=region.y, width=region.width, height=region.height)
        for region in regions
    ]


def _clone_regions(
    db: Session,
    source_locator_id: str,
    target_locator_id: str,
) -> None:
    db.add_all(
        [
            SpatialLocatorRegion(
                locator_id=target_locator_id,
                region_order=region.region_order,
                x=region.x,
                y=region.y,
                width=region.width,
                height=region.height,
            )
            for region in _regions(db, source_locator_id)
        ]
    )


class PdfLocatorCodec:
    kinds = frozenset({"pdf_page", "pdf_region"})
    representation_kinds = frozenset(
        {"pdf_text_legacy", "pdf_page_layout", "pdf_ocr", "pdf_table", "pdf_figure"}
    )

    def clone_details(self, db: Session, source: EvidenceLocator, target: EvidenceLocator) -> None:
        detail = db.get(PdfLocatorDetail, source.id)
        if detail is None:
            raise EvidenceContractError(f"PDF locator {source.id} has no typed detail")
        if source.locator_kind == "pdf_region" and detail.coordinate_space != PDF_COORDINATE_SPACE:
            raise EvidenceContractError("pdf_region locator has an unsupported coordinate space")
        db.add(
            PdfLocatorDetail(
                locator_id=target.id,
                page_id=detail.page_id,
                page_number=detail.page_number,
                coordinate_space=detail.coordinate_space,
                crop_x0_points=detail.crop_x0_points,
                crop_y0_points=detail.crop_y0_points,
                crop_x1_points=detail.crop_x1_points,
                crop_y1_points=detail.crop_y1_points,
                rotation_degrees=detail.rotation_degrees,
                display_width_points=detail.display_width_points,
                display_height_points=detail.display_height_points,
            )
        )
        _clone_regions(db, source.id, target.id)

    def serialize(self, db: Session, locator: EvidenceLocator) -> EvidenceLocatorDto:
        detail = db.get(PdfLocatorDetail, locator.id)
        return self.serialize_loaded(db, locator, detail, _regions(db, locator.id))

    def serialize_loaded(
        self,
        db: Session,
        locator: EvidenceLocator,
        detail: TypedLocatorDetail,
        regions: list[SpatialLocatorRegion],
    ) -> EvidenceLocatorDto:
        del db
        if not isinstance(detail, PdfLocatorDetail):
            raise EvidenceContractError(f"PDF locator {locator.id} has no typed detail")
        if locator.locator_kind == "pdf_page":
            if regions:
                raise EvidenceContractError("pdf_page locator must not contain regions")
            return PdfPageLocator(
                kind="pdf_page",
                version=locator.locator_version,
                pageNumber=detail.page_number,
            )

        geometry_values = (
            detail.crop_x0_points,
            detail.crop_y0_points,
            detail.crop_x1_points,
            detail.crop_y1_points,
            detail.rotation_degrees,
            detail.display_width_points,
            detail.display_height_points,
        )
        if detail.coordinate_space != PDF_COORDINATE_SPACE:
            raise EvidenceContractError("pdf_region locator has an unsupported coordinate space")
        if any(value is None for value in geometry_values):
            raise EvidenceContractError("pdf_region locator requires coordinate and page geometry snapshots")
        region_dtos = _region_dtos(regions)
        if not region_dtos:
            raise EvidenceContractError("pdf_region locator requires at least one region")
        crop_x0, crop_y0, crop_x1, crop_y1, rotation, display_width, display_height = geometry_values
        return PdfRegionLocator(
            kind="pdf_region",
            version=locator.locator_version,
            pageNumber=detail.page_number,
            coordinateSpace=detail.coordinate_space,
            pageGeometry=PageGeometry(
                cropBoxPoints=[crop_x0, crop_y0, crop_x1, crop_y1],
                rotationDegrees=rotation,
                displayWidthPoints=display_width,
                displayHeightPoints=display_height,
            ),
            regions=region_dtos,
        )

    def retrieval_key(
        self,
        locator: EvidenceLocator,
        serialized: EvidenceLocatorDto,
    ) -> str:
        if isinstance(serialized, PdfPageLocator):
            return f"pdf_page:{serialized.pageNumber}"
        return locator.id


class ImageLocatorCodec:
    kinds = frozenset({"image_region"})
    representation_kinds = frozenset({"image_ocr", "image_caption"})

    def clone_details(self, db: Session, source: EvidenceLocator, target: EvidenceLocator) -> None:
        detail = db.get(ImageLocatorDetail, source.id)
        if detail is None:
            raise EvidenceContractError(f"Image locator {source.id} has no typed detail")
        if detail.coordinate_space != IMAGE_COORDINATE_SPACE:
            raise EvidenceContractError("image_region locator has an unsupported coordinate space")
        db.add(
            ImageLocatorDetail(
                locator_id=target.id,
                coordinate_space=detail.coordinate_space,
                width_pixels=detail.width_pixels,
                height_pixels=detail.height_pixels,
                orientation_applied=detail.orientation_applied,
            )
        )
        _clone_regions(db, source.id, target.id)

    def serialize(self, db: Session, locator: EvidenceLocator) -> EvidenceLocatorDto:
        detail = db.get(ImageLocatorDetail, locator.id)
        return self.serialize_loaded(db, locator, detail, _regions(db, locator.id))

    def serialize_loaded(
        self,
        db: Session,
        locator: EvidenceLocator,
        detail: TypedLocatorDetail,
        regions: list[SpatialLocatorRegion],
    ) -> EvidenceLocatorDto:
        del db
        if not isinstance(detail, ImageLocatorDetail):
            raise EvidenceContractError(f"Image locator {locator.id} has no typed detail")
        region_dtos = _region_dtos(regions)
        if not region_dtos:
            raise EvidenceContractError("image_region locator requires at least one region")
        if detail.coordinate_space != IMAGE_COORDINATE_SPACE:
            raise EvidenceContractError("image_region locator has an unsupported coordinate space")
        return ImageRegionLocator(
            kind="image_region",
            version=locator.locator_version,
            coordinateSpace=detail.coordinate_space,
            widthPixels=detail.width_pixels,
            heightPixels=detail.height_pixels,
            orientationApplied=detail.orientation_applied,
            regions=region_dtos,
        )

    def retrieval_key(
        self,
        locator: EvidenceLocator,
        serialized: EvidenceLocatorDto,
    ) -> str:
        del serialized
        return locator.id



def _load_document_anchor_context(
    db: Session,
    locator: EvidenceLocator,
    detail: DocumentLocatorDetail,
) -> tuple[DocumentNormalizedContent, DocumentBlock, str]:
    representation = db.get(AssetRepresentation, locator.representation_id_snapshot)
    if representation is None:
        raise EvidenceContractError(
            f"document_anchor {locator.id} representation is missing"
        )
    if (
        representation.id != locator.representation_id_snapshot
        or representation.workspace_id != locator.workspace_id
        or representation.asset_id != locator.asset_id
        or representation.processing_generation != locator.processing_generation_snapshot
        or representation.representation_kind != "document_normalized"
    ):
        raise EvidenceContractError(
            f"document_anchor {locator.id} representation snapshot is inconsistent"
        )

    normalized = db.get(DocumentNormalizedContent, representation.id)
    if normalized is None:
        raise EvidenceContractError(
            f"document_anchor {locator.id} normalized content is missing"
        )
    try:
        normalized_text = validate_document_normalized_content(normalized)
    except DocumentIntegrityError as error:
        raise EvidenceContractError(
            f"document_anchor {locator.id} normalized content is invalid: {error}"
        ) from error

    block = db.scalar(
        select(DocumentBlock).where(
            DocumentBlock.representation_id == representation.id,
            DocumentBlock.block_id == detail.block_id,
        )
    )
    if block is None:
        raise EvidenceContractError(
            f"document_anchor {locator.id} block {detail.block_id} is missing"
        )
    return normalized, block, normalized_text


def _validate_document_detail(
    detail: DocumentLocatorDetail,
    *,
    block: DocumentBlock,
    normalized_text: str,
) -> list[str]:
    try:
        return validate_document_anchor_range(
            block_id=detail.block_id,
            block_kind=detail.block_kind,
            heading_path=detail.heading_path,
            char_start=detail.char_start,
            char_end=detail.char_end,
            text_sha256_value=detail.text_sha256,
            normalization_version=detail.normalization_version,
            block=block,
            normalized_text=normalized_text,
        )
    except DocumentIntegrityError as error:
        raise EvidenceContractError(str(error)) from error


class DocumentLocatorCodec:
    kinds = frozenset({"document_anchor"})
    representation_kinds = frozenset({"document_normalized"})

    def clone_details(self, db: Session, source: EvidenceLocator, target: EvidenceLocator) -> None:
        detail = db.get(DocumentLocatorDetail, source.id)
        if detail is None:
            raise EvidenceContractError(f"Document locator {source.id} has no typed detail")
        _normalized, block, normalized_text = _load_document_anchor_context(db, source, detail)
        heading_path = _validate_document_detail(
            detail, block=block, normalized_text=normalized_text
        )
        db.add(
            DocumentLocatorDetail(
                locator_id=target.id,
                block_id=detail.block_id,
                block_kind=detail.block_kind,
                heading_path=heading_path,
                char_start=detail.char_start,
                char_end=detail.char_end,
                text_sha256=detail.text_sha256,
                normalization_version=detail.normalization_version,
            )
        )

    def serialize(self, db: Session, locator: EvidenceLocator) -> EvidenceLocatorDto:
        detail = db.get(DocumentLocatorDetail, locator.id)
        return self.serialize_loaded(db, locator, detail, [])

    def serialize_loaded(
        self,
        db: Session,
        locator: EvidenceLocator,
        detail: TypedLocatorDetail,
        regions: list[SpatialLocatorRegion],
    ) -> EvidenceLocatorDto:
        del regions
        if not isinstance(detail, DocumentLocatorDetail):
            raise EvidenceContractError(f"Document locator {locator.id} has no typed detail")
        _normalized, block, normalized_text = _load_document_anchor_context(db, locator, detail)
        heading_path = _validate_document_detail(
            detail, block=block, normalized_text=normalized_text
        )
        return DocumentAnchorLocator(
            kind="document_anchor",
            version=locator.locator_version,
            blockId=detail.block_id,
            blockKind=detail.block_kind,  # type: ignore[arg-type]
            headingPath=heading_path,
            charStart=detail.char_start,
            charEnd=detail.char_end,
            textSha256=detail.text_sha256,
            normalizationVersion=detail.normalization_version,  # type: ignore[arg-type]
        )

    def retrieval_key(
        self,
        locator: EvidenceLocator,
        serialized: EvidenceLocatorDto,
    ) -> str:
        if isinstance(serialized, DocumentAnchorLocator):
            return (
                f"document_anchor:{serialized.blockId}:"
                f"{serialized.charStart}:{serialized.charEnd}"
            )
        return locator.id




def _load_html_anchor_context(
    db: Session,
    locator: EvidenceLocator,
    detail: HtmlLocatorDetail,
) -> tuple[HtmlNormalizedContent, HtmlBlock, str]:
    representation = db.get(AssetRepresentation, locator.representation_id_snapshot)
    if representation is None:
        raise EvidenceContractError(f"html_anchor {locator.id} representation is missing")
    if (
        representation.id != locator.representation_id_snapshot
        or representation.workspace_id != locator.workspace_id
        or representation.asset_id != locator.asset_id
        or representation.processing_generation != locator.processing_generation_snapshot
        or representation.representation_kind != "html_normalized"
    ):
        raise EvidenceContractError(
            f"html_anchor {locator.id} representation snapshot is inconsistent"
        )
    normalized = db.get(HtmlNormalizedContent, representation.id)
    if normalized is None:
        raise EvidenceContractError(f"html_anchor {locator.id} normalized content is missing")
    try:
        normalized_text = validate_html_normalized_content(normalized)
    except HtmlIntegrityError as error:
        raise EvidenceContractError(
            f"html_anchor {locator.id} normalized content is invalid: {error}"
        ) from error
    block = db.scalar(
        select(HtmlBlock).where(
            HtmlBlock.representation_id == representation.id,
            HtmlBlock.block_id == detail.block_id,
        )
    )
    if block is None:
        raise EvidenceContractError(
            f"html_anchor {locator.id} block {detail.block_id} is missing"
        )
    return normalized, block, normalized_text


def _validate_html_detail(
    detail: HtmlLocatorDetail,
    *,
    block: HtmlBlock,
    normalized_text: str,
) -> list[str]:
    try:
        return validate_html_anchor_range(
            block_id=detail.block_id,
            block_kind=detail.block_kind,
            heading_path=detail.heading_path,
            char_start=detail.char_start,
            char_end=detail.char_end,
            text_sha256_value=detail.text_sha256,
            normalization_version=detail.normalization_version,
            css_path_hint=detail.css_path_hint,
            block=block,
            normalized_text=normalized_text,
        )
    except HtmlIntegrityError as error:
        raise EvidenceContractError(str(error)) from error


class HtmlLocatorCodec:
    kinds = frozenset({"html_anchor"})
    representation_kinds = frozenset({"html_normalized"})

    def clone_details(self, db: Session, source: EvidenceLocator, target: EvidenceLocator) -> None:
        detail = db.get(HtmlLocatorDetail, source.id)
        if detail is None:
            raise EvidenceContractError(f"HTML locator {source.id} has no typed detail")
        _normalized, block, normalized_text = _load_html_anchor_context(db, source, detail)
        heading_path = _validate_html_detail(detail, block=block, normalized_text=normalized_text)
        db.add(
            HtmlLocatorDetail(
                locator_id=target.id,
                block_id=detail.block_id,
                block_kind=detail.block_kind,
                heading_path=heading_path,
                char_start=detail.char_start,
                char_end=detail.char_end,
                text_sha256=detail.text_sha256,
                normalization_version=detail.normalization_version,
                css_path_hint=detail.css_path_hint,
            )
        )

    def serialize(self, db: Session, locator: EvidenceLocator) -> EvidenceLocatorDto:
        detail = db.get(HtmlLocatorDetail, locator.id)
        return self.serialize_loaded(db, locator, detail, [])

    def serialize_loaded(
        self,
        db: Session,
        locator: EvidenceLocator,
        detail: TypedLocatorDetail,
        regions: list[SpatialLocatorRegion],
    ) -> EvidenceLocatorDto:
        del regions
        if not isinstance(detail, HtmlLocatorDetail):
            raise EvidenceContractError(f"HTML locator {locator.id} has no typed detail")
        _normalized, block, normalized_text = _load_html_anchor_context(db, locator, detail)
        heading_path = _validate_html_detail(detail, block=block, normalized_text=normalized_text)
        return HtmlAnchorLocator(
            kind="html_anchor",
            version=locator.locator_version,
            blockId=detail.block_id,
            blockKind=detail.block_kind,  # type: ignore[arg-type]
            headingPath=heading_path,
            charStart=detail.char_start,
            charEnd=detail.char_end,
            textSha256=detail.text_sha256,
            normalizationVersion=detail.normalization_version,  # type: ignore[arg-type]
            cssPathHint=detail.css_path_hint,
        )

    def retrieval_key(
        self,
        locator: EvidenceLocator,
        serialized: EvidenceLocatorDto,
    ) -> str:
        if isinstance(serialized, HtmlAnchorLocator):
            return (
                f"html_anchor:{serialized.blockId}:"
                f"{serialized.charStart}:{serialized.charEnd}"
            )
        return locator.id


def _load_docx_anchor_context(
    db: Session,
    locator: EvidenceLocator,
    detail: DocxLocatorDetail,
) -> tuple[DocxNormalizedContent, DocxBlock, str]:
    representation = db.get(AssetRepresentation, locator.representation_id_snapshot)
    if representation is None:
        raise EvidenceContractError(f"docx_anchor {locator.id} representation is missing")
    if (
        representation.id != locator.representation_id_snapshot
        or representation.workspace_id != locator.workspace_id
        or representation.asset_id != locator.asset_id
        or representation.processing_generation != locator.processing_generation_snapshot
        or representation.representation_kind != "docx_normalized"
    ):
        raise EvidenceContractError(
            f"docx_anchor {locator.id} representation snapshot is inconsistent"
        )
    normalized = db.get(DocxNormalizedContent, representation.id)
    if normalized is None:
        raise EvidenceContractError(f"docx_anchor {locator.id} normalized content is missing")
    try:
        normalized_text = validate_docx_normalized_content(normalized)
    except DocxIntegrityError as error:
        raise EvidenceContractError(
            f"docx_anchor {locator.id} normalized content is invalid: {error}"
        ) from error
    block = db.scalar(
        select(DocxBlock).where(
            DocxBlock.representation_id == representation.id,
            DocxBlock.block_id == detail.block_id,
        )
    )
    if block is None:
        raise EvidenceContractError(
            f"docx_anchor {locator.id} block {detail.block_id} is missing"
        )
    return normalized, block, normalized_text


class DocxLocatorCodec:
    kinds = frozenset({"docx_anchor"})
    representation_kinds = frozenset({"docx_normalized"})

    def clone_details(self, db: Session, source: EvidenceLocator, target: EvidenceLocator) -> None:
        detail = db.get(DocxLocatorDetail, source.id)
        if detail is None:
            raise EvidenceContractError(f"DOCX locator {source.id} has no typed detail")
        _normalized, block, normalized_text = _load_docx_anchor_context(db, source, detail)
        heading_path = validate_docx_anchor_range(
            block_id=detail.block_id,
            block_kind=detail.block_kind,
            heading_path=detail.heading_path,
            char_start=detail.char_start,
            char_end=detail.char_end,
            text_sha256_value=detail.text_sha256,
            normalization_version=detail.normalization_version,
            block=block,
            normalized_text=normalized_text,
        )
        db.add(
            DocxLocatorDetail(
                locator_id=target.id,
                block_id=detail.block_id,
                block_kind=detail.block_kind,
                heading_path=heading_path,
                char_start=detail.char_start,
                char_end=detail.char_end,
                text_sha256=detail.text_sha256,
                normalization_version=detail.normalization_version,
            )
        )

    def serialize(self, db: Session, locator: EvidenceLocator) -> EvidenceLocatorDto:
        detail = db.get(DocxLocatorDetail, locator.id)
        return self.serialize_loaded(db, locator, detail, [])

    def serialize_loaded(
        self,
        db: Session,
        locator: EvidenceLocator,
        detail: TypedLocatorDetail,
        regions: list[SpatialLocatorRegion],
    ) -> EvidenceLocatorDto:
        del regions
        if not isinstance(detail, DocxLocatorDetail):
            raise EvidenceContractError(f"DOCX locator {locator.id} has no typed detail")
        _normalized, block, normalized_text = _load_docx_anchor_context(db, locator, detail)
        heading_path = validate_docx_anchor_range(
            block_id=detail.block_id,
            block_kind=detail.block_kind,
            heading_path=detail.heading_path,
            char_start=detail.char_start,
            char_end=detail.char_end,
            text_sha256_value=detail.text_sha256,
            normalization_version=detail.normalization_version,
            block=block,
            normalized_text=normalized_text,
        )
        return DocxAnchorLocator(
            kind="docx_anchor",
            version=locator.locator_version,
            blockId=detail.block_id,
            blockKind=detail.block_kind,  # type: ignore[arg-type]
            headingPath=heading_path,
            charStart=detail.char_start,
            charEnd=detail.char_end,
            textSha256=detail.text_sha256,
            normalizationVersion=detail.normalization_version,  # type: ignore[arg-type]
        )

    def retrieval_key(
        self,
        locator: EvidenceLocator,
        serialized: EvidenceLocatorDto,
    ) -> str:
        if isinstance(serialized, DocxAnchorLocator):
            return (
                f"docx_anchor:{serialized.blockId}:"
                f"{serialized.charStart}:{serialized.charEnd}"
            )
        return locator.id


class XlsxLocatorCodec:
    kinds = frozenset({"xlsx_range"})
    representation_kinds = frozenset({"xlsx_normalized"})

    def clone_details(self, db: Session, source: EvidenceLocator, target: EvidenceLocator) -> None:
        detail = db.get(XlsxLocatorDetail, source.id)
        if detail is None:
            raise EvidenceContractError(f"XLSX locator {source.id} has no typed detail")
        try:
            validate_xlsx_range(
                sheet_name=detail.sheet_name,
                start_cell=detail.start_cell,
                end_cell=detail.end_cell,
                text_sha256_value=detail.text_sha256,
                expected_text=detail.displayed_text,
            )
        except XlsxIntegrityError as error:
            raise EvidenceContractError(str(error)) from error
        db.add(
            XlsxLocatorDetail(
                locator_id=target.id,
                sheet_name=detail.sheet_name,
                start_cell=detail.start_cell,
                end_cell=detail.end_cell,
                text_sha256=detail.text_sha256,
                displayed_text=detail.displayed_text,
                normalization_version=detail.normalization_version,
            )
        )

    def serialize(self, db: Session, locator: EvidenceLocator) -> EvidenceLocatorDto:
        return self.serialize_loaded(db, locator, db.get(XlsxLocatorDetail, locator.id), [])

    def serialize_loaded(
        self,
        db: Session,
        locator: EvidenceLocator,
        detail: TypedLocatorDetail,
        regions: list[SpatialLocatorRegion],
    ) -> EvidenceLocatorDto:
        del db, regions
        if not isinstance(detail, XlsxLocatorDetail):
            raise EvidenceContractError(f"XLSX locator {locator.id} has no typed detail")
        try:
            validate_xlsx_range(
                sheet_name=detail.sheet_name,
                start_cell=detail.start_cell,
                end_cell=detail.end_cell,
                text_sha256_value=detail.text_sha256,
                expected_text=detail.displayed_text,
            )
        except XlsxIntegrityError as error:
            raise EvidenceContractError(str(error)) from error
        return XlsxRangeLocator(
            kind="xlsx_range",
            version=locator.locator_version,
            sheetName=detail.sheet_name,
            startCell=detail.start_cell,
            endCell=detail.end_cell,
            textSha256=detail.text_sha256,
            displayedText=detail.displayed_text,
            normalizationVersion=detail.normalization_version,  # type: ignore[arg-type]
        )

    def retrieval_key(
        self,
        locator: EvidenceLocator,
        serialized: EvidenceLocatorDto,
    ) -> str:
        if isinstance(serialized, XlsxRangeLocator):
            return (
                f"xlsx_range:{serialized.sheetName}:"
                f"{serialized.startCell}:{serialized.endCell}"
            )
        return locator.id


class PptxLocatorCodec:
    kinds = frozenset({"pptx_shape"})
    representation_kinds = frozenset({"pptx_normalized"})

    def clone_details(self, db: Session, source: EvidenceLocator, target: EvidenceLocator) -> None:
        detail = db.get(PptxLocatorDetail, source.id)
        if detail is None:
            raise EvidenceContractError(f"PPTX locator {source.id} has no typed detail")
        try:
            validate_pptx_shape(
                slide_index=detail.slide_index,
                shape_id=detail.shape_id,
                text_sha256_value=detail.text_sha256,
                expected_text=detail.displayed_text,
            )
        except PptxIntegrityError as error:
            raise EvidenceContractError(str(error)) from error
        db.add(
            PptxLocatorDetail(
                locator_id=target.id,
                slide_index=detail.slide_index,
                shape_id=detail.shape_id,
                text_sha256=detail.text_sha256,
                displayed_text=detail.displayed_text,
                normalization_version=detail.normalization_version,
            )
        )

    def serialize(self, db: Session, locator: EvidenceLocator) -> EvidenceLocatorDto:
        return self.serialize_loaded(db, locator, db.get(PptxLocatorDetail, locator.id), [])

    def serialize_loaded(
        self,
        db: Session,
        locator: EvidenceLocator,
        detail: TypedLocatorDetail,
        regions: list[SpatialLocatorRegion],
    ) -> EvidenceLocatorDto:
        del db, regions
        if not isinstance(detail, PptxLocatorDetail):
            raise EvidenceContractError(f"PPTX locator {locator.id} has no typed detail")
        try:
            validate_pptx_shape(
                slide_index=detail.slide_index,
                shape_id=detail.shape_id,
                text_sha256_value=detail.text_sha256,
                expected_text=detail.displayed_text,
            )
        except PptxIntegrityError as error:
            raise EvidenceContractError(str(error)) from error
        return PptxShapeLocator(
            kind="pptx_shape",
            version=locator.locator_version,
            slideIndex=detail.slide_index,
            shapeId=detail.shape_id,
            textSha256=detail.text_sha256,
            displayedText=detail.displayed_text,
            normalizationVersion=detail.normalization_version,  # type: ignore[arg-type]
        )

    def retrieval_key(
        self,
        locator: EvidenceLocator,
        serialized: EvidenceLocatorDto,
    ) -> str:
        if isinstance(serialized, PptxShapeLocator):
            return f"pptx_shape:{serialized.slideIndex}:{serialized.shapeId}"
        return locator.id




def _load_audio_range_context(
    db: Session,
    locator: EvidenceLocator,
    detail: AudioLocatorDetail,
) -> tuple[AudioNormalizedContent, AudioTranscriptSegment]:
    representation = db.get(AssetRepresentation, locator.representation_id_snapshot)
    if representation is None:
        raise EvidenceContractError(f"audio_range {locator.id} representation is missing")
    if (
        representation.id != locator.representation_id_snapshot
        or representation.workspace_id != locator.workspace_id
        or representation.asset_id != locator.asset_id
        or representation.processing_generation != locator.processing_generation_snapshot
        or representation.representation_kind != "audio_normalized"
    ):
        raise EvidenceContractError(
            f"audio_range {locator.id} representation snapshot is inconsistent"
        )
    normalized = db.get(AudioNormalizedContent, representation.id)
    if normalized is None:
        raise EvidenceContractError(f"audio_range {locator.id} normalized content is missing")
    try:
        validate_audio_normalized_content(normalized)
    except AudioIntegrityError as error:
        raise EvidenceContractError(
            f"audio_range {locator.id} normalized content is invalid: {error}"
        ) from error
    segment = db.scalar(
        select(AudioTranscriptSegment).where(
            AudioTranscriptSegment.representation_id == representation.id,
            AudioTranscriptSegment.segment_id == detail.segment_id,
        )
    )
    if segment is None:
        raise EvidenceContractError(
            f"audio_range {locator.id} segment {detail.segment_id} is missing"
        )
    try:
        validate_audio_transcript_segment(segment)
    except AudioIntegrityError as error:
        raise EvidenceContractError(
            f"audio_range {locator.id} segment is invalid: {error}"
        ) from error
    return normalized, segment


def _validate_audio_detail(
    detail: AudioLocatorDetail,
    *,
    segment: AudioTranscriptSegment,
) -> None:
    try:
        validate_audio_range(
            start_ms=detail.start_ms,
            end_ms=detail.end_ms,
            text_sha256_value=detail.text_sha256,
            segment=segment,
        )
    except AudioIntegrityError as error:
        raise EvidenceContractError(str(error)) from error


class AudioLocatorCodec:
    kinds = frozenset({"audio_range"})
    representation_kinds = frozenset({"audio_normalized"})

    def clone_details(self, db: Session, source: EvidenceLocator, target: EvidenceLocator) -> None:
        detail = db.get(AudioLocatorDetail, source.id)
        if detail is None:
            raise EvidenceContractError(f"Audio locator {source.id} has no typed detail")
        _normalized, segment = _load_audio_range_context(db, source, detail)
        _validate_audio_detail(detail, segment=segment)
        db.add(
            AudioLocatorDetail(
                locator_id=target.id,
                segment_id=detail.segment_id,
                start_ms=detail.start_ms,
                end_ms=detail.end_ms,
                text_sha256=detail.text_sha256,
                normalization_version=detail.normalization_version,
            )
        )

    def serialize(self, db: Session, locator: EvidenceLocator) -> EvidenceLocatorDto:
        detail = db.get(AudioLocatorDetail, locator.id)
        return self.serialize_loaded(db, locator, detail, [])

    def serialize_loaded(
        self,
        db: Session,
        locator: EvidenceLocator,
        detail: TypedLocatorDetail,
        regions: list[SpatialLocatorRegion],
    ) -> EvidenceLocatorDto:
        del regions
        if not isinstance(detail, AudioLocatorDetail):
            raise EvidenceContractError(f"Audio locator {locator.id} has no typed detail")
        _normalized, segment = _load_audio_range_context(db, locator, detail)
        _validate_audio_detail(detail, segment=segment)
        return AudioRangeLocator(
            kind="audio_range",
            version=locator.locator_version,
            startMs=detail.start_ms,
            endMs=detail.end_ms,
            textSha256=detail.text_sha256,
            segmentId=detail.segment_id,
            normalizationVersion=detail.normalization_version,  # type: ignore[arg-type]
        )

    def retrieval_key(
        self,
        locator: EvidenceLocator,
        serialized: EvidenceLocatorDto,
    ) -> str:
        if isinstance(serialized, AudioRangeLocator):
            return (
                f"audio_range:{serialized.segmentId}:"
                f"{serialized.startMs}:{serialized.endMs}"
            )
        return locator.id




def _load_video_range_context(
    db: Session,
    locator: EvidenceLocator,
    detail: VideoLocatorDetail,
) -> tuple[VideoNormalizedContent, VideoTranscriptSegment]:
    representation = db.get(AssetRepresentation, locator.representation_id_snapshot)
    if representation is None:
        raise EvidenceContractError(f"video_range {locator.id} representation is missing")
    if (
        representation.id != locator.representation_id_snapshot
        or representation.workspace_id != locator.workspace_id
        or representation.asset_id != locator.asset_id
        or representation.processing_generation != locator.processing_generation_snapshot
        or representation.representation_kind != "video_normalized"
    ):
        raise EvidenceContractError(
            f"video_range {locator.id} representation snapshot is inconsistent"
        )
    normalized = db.get(VideoNormalizedContent, representation.id)
    if normalized is None:
        raise EvidenceContractError(f"video_range {locator.id} normalized content is missing")
    try:
        validate_video_normalized_content(normalized)
    except VideoIntegrityError as error:
        raise EvidenceContractError(
            f"video_range {locator.id} normalized content is invalid: {error}"
        ) from error
    segment = db.scalar(
        select(VideoTranscriptSegment).where(
            VideoTranscriptSegment.representation_id == representation.id,
            VideoTranscriptSegment.segment_id == detail.segment_id,
        )
    )
    if segment is None:
        raise EvidenceContractError(
            f"video_range {locator.id} segment {detail.segment_id} is missing"
        )
    try:
        validate_video_transcript_segment(segment)
    except VideoIntegrityError as error:
        raise EvidenceContractError(
            f"video_range {locator.id} segment is invalid: {error}"
        ) from error
    return normalized, segment


def _validate_video_detail(
    detail: VideoLocatorDetail,
    *,
    segment: VideoTranscriptSegment,
) -> None:
    try:
        validate_video_range(
            start_ms=detail.start_ms,
            end_ms=detail.end_ms,
            text_sha256_value=detail.text_sha256,
            segment=segment,
        )
    except VideoIntegrityError as error:
        raise EvidenceContractError(str(error)) from error


class VideoLocatorCodec:
    kinds = frozenset({"video_range"})
    representation_kinds = frozenset({"video_normalized"})

    def clone_details(self, db: Session, source: EvidenceLocator, target: EvidenceLocator) -> None:
        detail = db.get(VideoLocatorDetail, source.id)
        if detail is None:
            raise EvidenceContractError(f"Video locator {source.id} has no typed detail")
        _normalized, segment = _load_video_range_context(db, source, detail)
        _validate_video_detail(detail, segment=segment)
        db.add(
            VideoLocatorDetail(
                locator_id=target.id,
                segment_id=detail.segment_id,
                start_ms=detail.start_ms,
                end_ms=detail.end_ms,
                text_sha256=detail.text_sha256,
                normalization_version=detail.normalization_version,
            )
        )

    def serialize(self, db: Session, locator: EvidenceLocator) -> EvidenceLocatorDto:
        detail = db.get(VideoLocatorDetail, locator.id)
        return self.serialize_loaded(db, locator, detail, [])

    def serialize_loaded(
        self,
        db: Session,
        locator: EvidenceLocator,
        detail: TypedLocatorDetail,
        regions: list[SpatialLocatorRegion],
    ) -> EvidenceLocatorDto:
        del regions
        if not isinstance(detail, VideoLocatorDetail):
            raise EvidenceContractError(f"Video locator {locator.id} has no typed detail")
        _normalized, segment = _load_video_range_context(db, locator, detail)
        _validate_video_detail(detail, segment=segment)
        return VideoRangeLocator(
            kind="video_range",
            version=locator.locator_version,
            startMs=detail.start_ms,
            endMs=detail.end_ms,
            textSha256=detail.text_sha256,
            segmentId=detail.segment_id,
            normalizationVersion=detail.normalization_version,  # type: ignore[arg-type]
        )

    def retrieval_key(
        self,
        locator: EvidenceLocator,
        serialized: EvidenceLocatorDto,
    ) -> str:
        if isinstance(serialized, VideoRangeLocator):
            return (
                f"video_range:{serialized.segmentId}:"
                f"{serialized.startMs}:{serialized.endMs}"
            )
        return locator.id


class VideoFrameLocatorCodec:
    """Codec for optional keyframe locators. Ingestion may leave keyframes deferred."""

    kinds = frozenset({"video_frame"})
    representation_kinds = frozenset({"video_normalized", "video_keyframe_set", "video_source"})

    def clone_details(self, db: Session, source: EvidenceLocator, target: EvidenceLocator) -> None:
        detail = db.get(VideoFrameLocatorDetail, source.id)
        if detail is None:
            raise EvidenceContractError(f"Video frame locator {source.id} has no typed detail")
        try:
            validate_video_frame(
                timestamp_ms=detail.timestamp_ms,
                frame_index=detail.frame_index,
                keyframe_object_key=detail.keyframe_object_key,
            )
        except VideoIntegrityError as error:
            raise EvidenceContractError(str(error)) from error
        db.add(
            VideoFrameLocatorDetail(
                locator_id=target.id,
                timestamp_ms=detail.timestamp_ms,
                frame_index=detail.frame_index,
                keyframe_object_key=detail.keyframe_object_key,
                normalization_version=detail.normalization_version,
            )
        )

    def serialize(self, db: Session, locator: EvidenceLocator) -> EvidenceLocatorDto:
        detail = db.get(VideoFrameLocatorDetail, locator.id)
        return self.serialize_loaded(db, locator, detail, [])

    def serialize_loaded(
        self,
        db: Session,
        locator: EvidenceLocator,
        detail: TypedLocatorDetail,
        regions: list[SpatialLocatorRegion],
    ) -> EvidenceLocatorDto:
        del regions
        if not isinstance(detail, VideoFrameLocatorDetail):
            raise EvidenceContractError(f"Video frame locator {locator.id} has no typed detail")
        try:
            validate_video_frame(
                timestamp_ms=detail.timestamp_ms,
                frame_index=detail.frame_index,
                keyframe_object_key=detail.keyframe_object_key,
            )
        except VideoIntegrityError as error:
            raise EvidenceContractError(str(error)) from error
        return VideoFrameLocator(
            kind="video_frame",
            version=locator.locator_version,
            timestampMs=detail.timestamp_ms,
            frameIndex=detail.frame_index,
            keyframeObjectKey=detail.keyframe_object_key,
            normalizationVersion=detail.normalization_version,  # type: ignore[arg-type]
        )

    def retrieval_key(
        self,
        locator: EvidenceLocator,
        serialized: EvidenceLocatorDto,
    ) -> str:
        if isinstance(serialized, VideoFrameLocator):
            return (
                f"video_frame:{serialized.timestampMs}:{serialized.frameIndex}:"
                f"{serialized.keyframeObjectKey or ''}"
            )
        return locator.id


class LocatorCodecRegistry:
    def __init__(self, codecs: Iterable[LocatorCodec]) -> None:
        self._by_kind: dict[str, LocatorCodec] = {}
        for codec in codecs:
            for kind in codec.kinds:
                if kind in self._by_kind:
                    raise EvidenceContractError(f"Duplicate locator codec: {kind}")
                self._by_kind[kind] = codec

    @property
    def kinds(self) -> frozenset[str]:
        return frozenset(self._by_kind)

    def get(self, kind: str) -> LocatorCodec:
        try:
            return self._by_kind[kind]
        except KeyError as error:
            raise EvidenceContractError(f"Unsupported locator kind: {kind}") from error


PRODUCTION_LOCATOR_CODECS = LocatorCodecRegistry(
    (
        PdfLocatorCodec(),
        ImageLocatorCodec(),
        DocumentLocatorCodec(),
        HtmlLocatorCodec(),
        DocxLocatorCodec(),
        XlsxLocatorCodec(),
        PptxLocatorCodec(),
        AudioLocatorCodec(),
        VideoLocatorCodec(),
        VideoFrameLocatorCodec(),
    )
)


@dataclass(frozen=True)
class EvidenceRetrievalSource:
    locator: EvidenceLocator
    representation: AssetRepresentation
    workspace_id: str
    asset_id: str
    processing_generation: int
    representation_id: str


def _validate_locator_version(locator: EvidenceLocator) -> None:
    if locator.locator_version != 1:
        raise EvidenceContractError(
            f"Unsupported locator version for {locator.locator_kind}: {locator.locator_version}"
        )


def _validate_locator_representation(
    db: Session,
    locator: EvidenceLocator,
    codec: LocatorCodec,
) -> AssetRepresentation:
    representation = db.get(AssetRepresentation, locator.representation_id_snapshot)
    if representation is None:
        raise EvidenceContractError(
            f"Evidence locator {locator.id} representation is missing"
        )
    return _validate_locator_representation_value(locator, codec, representation)


def _validate_locator_representation_value(
    locator: EvidenceLocator,
    codec: LocatorCodec,
    representation: AssetRepresentation,
) -> AssetRepresentation:
    if (
        representation.id != locator.representation_id_snapshot
        or representation.workspace_id != locator.workspace_id
        or representation.asset_id != locator.asset_id
        or representation.processing_generation != locator.processing_generation_snapshot
    ):
        raise EvidenceContractError(
            f"Evidence locator {locator.id} representation snapshot is inconsistent"
        )
    if representation.representation_kind not in codec.representation_kinds:
        raise EvidenceContractError(
            f"Evidence locator {locator.id} has an invalid representation kind"
        )
    return representation


def _validate_expected_snapshot(
    locator: EvidenceLocator,
    *,
    workspace_id: str | None,
    asset_id: str | None,
    processing_generation: int | None,
    representation_id: str | None,
) -> None:
    expected = (
        ("workspace", workspace_id, locator.workspace_id),
        ("asset", asset_id, locator.asset_id),
        (
            "processing generation",
            processing_generation,
            locator.processing_generation_snapshot,
        ),
        ("representation", representation_id, locator.representation_id_snapshot),
    )
    for label, expected_value, actual_value in expected:
        if expected_value is not None and expected_value != actual_value:
            raise EvidenceContractError(
                f"Evidence locator {locator.id} does not match the {label} snapshot"
            )


def _serialize_with_codec(
    db: Session,
    locator: EvidenceLocator,
    codec: LocatorCodec,
) -> EvidenceLocatorDto:
    try:
        return codec.serialize(db, locator)
    except EvidenceContractError:
        raise
    except ValueError as error:
        raise EvidenceContractError(
            f"Evidence locator {locator.id} contains invalid typed details"
        ) from error


def clone_evidence_locator(
    db: Session,
    source_locator_id: str,
    *,
    created_at: datetime,
    workspace_id: str | None = None,
    asset_id: str | None = None,
    processing_generation: int | None = None,
    representation_id: str | None = None,
) -> EvidenceLocator:
    source = db.get(EvidenceLocator, source_locator_id)
    if source is None:
        raise EvidenceContractError(f"Evidence locator not found: {source_locator_id}")
    _validate_locator_version(source)
    _validate_expected_snapshot(
        source,
        workspace_id=workspace_id,
        asset_id=asset_id,
        processing_generation=processing_generation,
        representation_id=representation_id,
    )
    codec = PRODUCTION_LOCATOR_CODECS.get(source.locator_kind)
    _validate_locator_representation(db, source, codec)
    _serialize_with_codec(db, source, codec)
    target = EvidenceLocator(
        id=str(uuid4()),
        workspace_id=source.workspace_id,
        asset_id=source.asset_id,
        locator_kind=source.locator_kind,
        locator_version=source.locator_version,
        processing_generation_snapshot=source.processing_generation_snapshot,
        representation_id_snapshot=source.representation_id_snapshot,
        created_at=created_at,
    )
    db.add(target)
    db.flush()
    codec.clone_details(db, source, target)
    db.flush()
    return target


def serialize_evidence_locator(
    db: Session,
    locator_id: str,
    *,
    workspace_id: str | None = None,
    asset_id: str | None = None,
    processing_generation: int | None = None,
    representation_id: str | None = None,
) -> EvidenceLocatorDto:
    locator = db.get(EvidenceLocator, locator_id)
    if locator is None:
        raise EvidenceContractError(f"Evidence locator not found: {locator_id}")
    _validate_locator_version(locator)
    _validate_expected_snapshot(
        locator,
        workspace_id=workspace_id,
        asset_id=asset_id,
        processing_generation=processing_generation,
        representation_id=representation_id,
    )
    codec = PRODUCTION_LOCATOR_CODECS.get(locator.locator_kind)
    _validate_locator_representation(db, locator, codec)
    return _serialize_with_codec(db, locator, codec)


def evidence_retrieval_key(
    db: Session,
    locator: EvidenceLocator,
    *,
    workspace_id: str,
    asset_id: str,
    processing_generation: int,
    representation_id: str,
) -> tuple[str, str]:
    representation = db.get(AssetRepresentation, representation_id)
    if representation is None:
        raise EvidenceContractError(
            f"Evidence locator {locator.id} representation is missing"
        )
    return evidence_retrieval_keys(
        db,
        (
            EvidenceRetrievalSource(
                locator=locator,
                representation=representation,
                workspace_id=workspace_id,
                asset_id=asset_id,
                processing_generation=processing_generation,
                representation_id=representation_id,
            ),
        ),
    )[locator.id]


def evidence_retrieval_keys(
    db: Session,
    sources: Iterable[EvidenceRetrievalSource],
) -> dict[str, tuple[str, str]]:
    source_list = list(sources)
    if not source_list:
        return {}

    codecs: dict[str, LocatorCodec] = {}
    for source in source_list:
        locator = source.locator
        _validate_locator_version(locator)
        _validate_expected_snapshot(
            locator,
            workspace_id=source.workspace_id,
            asset_id=source.asset_id,
            processing_generation=source.processing_generation,
            representation_id=source.representation_id,
        )
        codec = PRODUCTION_LOCATOR_CODECS.get(locator.locator_kind)
        _validate_locator_representation_value(
            locator,
            codec,
            source.representation,
        )
        codecs[locator.id] = codec

    locator_ids = list(dict.fromkeys(source.locator.id for source in source_list))
    pdf_ids = [
        source.locator.id
        for source in source_list
        if source.locator.locator_kind in PdfLocatorCodec.kinds
    ]
    image_ids = [
        source.locator.id
        for source in source_list
        if source.locator.locator_kind in ImageLocatorCodec.kinds
    ]
    document_ids = [
        source.locator.id
        for source in source_list
        if source.locator.locator_kind in DocumentLocatorCodec.kinds
    ]
    html_ids = [
        source.locator.id
        for source in source_list
        if source.locator.locator_kind in HtmlLocatorCodec.kinds
    ]
    docx_ids = [
        source.locator.id
        for source in source_list
        if source.locator.locator_kind in DocxLocatorCodec.kinds
    ]
    xlsx_ids = [
        source.locator.id
        for source in source_list
        if source.locator.locator_kind in XlsxLocatorCodec.kinds
    ]
    pptx_ids = [
        source.locator.id
        for source in source_list
        if source.locator.locator_kind in PptxLocatorCodec.kinds
    ]
    audio_ids = [
        source.locator.id
        for source in source_list
        if source.locator.locator_kind in AudioLocatorCodec.kinds
    ]
    video_ids = [
        source.locator.id
        for source in source_list
        if source.locator.locator_kind in VideoLocatorCodec.kinds
    ]
    video_frame_ids = [
        source.locator.id
        for source in source_list
        if source.locator.locator_kind in VideoFrameLocatorCodec.kinds
    ]
    details: dict[str, TypedLocatorDetail] = {}
    if pdf_ids:
        details.update(
            (detail.locator_id, detail)
            for detail in db.scalars(
                select(PdfLocatorDetail).where(PdfLocatorDetail.locator_id.in_(pdf_ids))
            )
        )
    if image_ids:
        details.update(
            (detail.locator_id, detail)
            for detail in db.scalars(
                select(ImageLocatorDetail).where(ImageLocatorDetail.locator_id.in_(image_ids))
            )
        )
    if document_ids:
        details.update(
            (detail.locator_id, detail)
            for detail in db.scalars(
                select(DocumentLocatorDetail).where(
                    DocumentLocatorDetail.locator_id.in_(document_ids)
                )
            )
        )
    if html_ids:
        details.update(
            (detail.locator_id, detail)
            for detail in db.scalars(
                select(HtmlLocatorDetail).where(HtmlLocatorDetail.locator_id.in_(html_ids))
            )
        )
    if docx_ids:
        details.update(
            (detail.locator_id, detail)
            for detail in db.scalars(
                select(DocxLocatorDetail).where(DocxLocatorDetail.locator_id.in_(docx_ids))
            )
        )
    if xlsx_ids:
        details.update(
            (detail.locator_id, detail)
            for detail in db.scalars(
                select(XlsxLocatorDetail).where(XlsxLocatorDetail.locator_id.in_(xlsx_ids))
            )
        )
    if pptx_ids:
        details.update(
            (detail.locator_id, detail)
            for detail in db.scalars(
                select(PptxLocatorDetail).where(PptxLocatorDetail.locator_id.in_(pptx_ids))
            )
        )
    if audio_ids:
        details.update(
            (detail.locator_id, detail)
            for detail in db.scalars(
                select(AudioLocatorDetail).where(AudioLocatorDetail.locator_id.in_(audio_ids))
            )
        )
    if video_ids:
        details.update(
            (detail.locator_id, detail)
            for detail in db.scalars(
                select(VideoLocatorDetail).where(VideoLocatorDetail.locator_id.in_(video_ids))
            )
        )
    if video_frame_ids:
        details.update(
            (detail.locator_id, detail)
            for detail in db.scalars(
                select(VideoFrameLocatorDetail).where(
                    VideoFrameLocatorDetail.locator_id.in_(video_frame_ids)
                )
            )
        )
    regions_by_locator: dict[str, list[SpatialLocatorRegion]] = {
        locator_id: [] for locator_id in locator_ids
    }
    for region in db.scalars(
        select(SpatialLocatorRegion)
        .where(SpatialLocatorRegion.locator_id.in_(locator_ids))
        .order_by(SpatialLocatorRegion.locator_id, SpatialLocatorRegion.region_order)
    ):
        regions_by_locator[region.locator_id].append(region)

    keys: dict[str, tuple[str, str]] = {}
    for source in source_list:
        locator = source.locator
        codec = codecs[locator.id]
        try:
            serialized = codec.serialize_loaded(
                db,
                locator,
                details.get(locator.id),
                regions_by_locator[locator.id],
            )
        except EvidenceContractError:
            raise
        except ValueError as error:
            raise EvidenceContractError(
                f"Evidence locator {locator.id} contains invalid typed details"
            ) from error
        keys[locator.id] = (
            source.asset_id,
            codec.retrieval_key(locator, serialized),
        )
    return keys
