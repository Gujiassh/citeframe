from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

import fitz
import numpy as np
from sqlalchemy.orm import Session

from ai_pdf_api.modalities.image_caption import ImageCaptionProvider
from ai_pdf_api.modalities.ingestion import IngestionError, IngestionResult
from ai_pdf_api.modalities.pdf_ingestion import (
    CHUNK_SIZE,
    PageArtifactResult,
    PageRegionResult,
    PageTextExtractor,
    PageTextResult,
    SpatialRegionResult,
    delete_pdf_content,
    replace_pdf_content,
)
from ai_pdf_api.models import Asset
from ai_pdf_api.services.providers import ModelProviderError

from ai_pdf_worker.ocr import OcrTextResult, recognize_pixels
from ai_pdf_worker.pdf import (
    detect_visual_region_rects,
    extract_pdf_page_layout,
    _normalized_region,
    _rect_overlap_ratio,
)


_VISUAL_CLAIM_OVERLAP = 0.45


class _PixelOcr(Protocol):
    def __call__(self, pixels: np.ndarray) -> OcrTextResult: ...


def extract_page_texts_with_ocr(payload: bytes) -> list[PageTextResult]:
    pdf = fitz.open(stream=payload, filetype="pdf")
    try:
        page_texts: list[PageTextResult] = []
        for page_number, page in enumerate(pdf, start=1):
            pixmap = page.get_pixmap(dpi=200, alpha=False)
            pixels = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                pixmap.height,
                pixmap.width,
                pixmap.n,
            )
            recognized = recognize_pixels(pixels)
            regions = tuple(
                PageRegionResult(
                    text=region.text,
                    unit_kind="pdf_ocr_region",
                    x=region.x,
                    y=region.y,
                    width=region.width,
                    height=region.height,
                    char_start=region.char_start,
                    char_end=region.char_end,
                )
                for region in recognized.regions
            )
            page_texts.append(
                PageTextResult(
                    page_number=page_number,
                    text=recognized.text,
                    source_kind="ocr",
                    regions=regions,
                    ocr_blocks=[region.as_block() for region in recognized.regions],
                )
            )
        return page_texts
    finally:
        pdf.close()


class PdfIngestionAdapter:
    asset_kind = "pdf"

    def __init__(
        self,
        *,
        layout_extractor: PageTextExtractor = extract_pdf_page_layout,
        ocr_extractor: PageTextExtractor = extract_page_texts_with_ocr,
        caption_provider: ImageCaptionProvider | None = None,
        region_ocr: _PixelOcr = recognize_pixels,
    ) -> None:
        self._layout_extractor = layout_extractor
        self._ocr_extractor = ocr_extractor
        self._caption_provider = caption_provider
        self._region_ocr = region_ocr

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
        pages = self._parse_pages(payload)
        replace_pdf_content(
            db,
            asset=asset,
            pages=pages,
            processing_generation=processing_generation,
            chunk_size=_chunk_size(config_snapshot),
            created_at=created_at,
        )
        return IngestionResult()

    def cleanup(self, db: Session, *, asset: Asset) -> None:
        delete_pdf_content(db, asset.id)

    def _parse_pages(self, payload: bytes) -> list[PageTextResult]:
        native_pages = self._layout_extractor(payload)
        _validate_native_pages(native_pages)
        if not native_pages:
            raise IngestionError("empty_pdf", "PDF has no pages.")
        if all(page.text.strip() for page in native_pages):
            pages = native_pages
        else:
            try:
                ocr_pages = _indexed_ocr_pages(self._ocr_extractor(payload))
                expected_numbers = {page.page_number for page in native_pages}
                if set(ocr_pages) != expected_numbers:
                    raise ValueError("OCR did not return the complete PDF page set.")
                pages = [
                    page if page.text.strip() else _merge_ocr_page(page, ocr_pages[page.page_number])
                    for page in native_pages
                ]
            except Exception as error:
                raise IngestionError("ocr_failed", str(error)) from error
            if not any(page.text.strip() for page in pages):
                raise IngestionError("no_extractable_text", "PDF has no extractable text after OCR.")
        return enrich_pdf_visual_regions(
            payload,
            pages,
            caption_provider=self._caption_provider,
            region_ocr=self._region_ocr,
        )


def enrich_pdf_visual_regions(
    payload: bytes,
    pages: list[PageTextResult],
    *,
    caption_provider: ImageCaptionProvider | None = None,
    region_ocr: _PixelOcr = recognize_pixels,
) -> list[PageTextResult]:
    try:
        document = fitz.open(stream=payload, filetype="pdf")
    except Exception:
        return pages
    try:
        if len(document) != len(pages):
            return pages
        enriched: list[PageTextResult] = []
        for page, parsed in zip(document, pages, strict=True):
            enriched.append(
                _enrich_page_visual_regions(
                    page,
                    parsed,
                    caption_provider=caption_provider,
                    region_ocr=region_ocr,
                )
            )
        return enriched
    finally:
        document.close()


def _enrich_page_visual_regions(
    page: fitz.Page,
    parsed: PageTextResult,
    *,
    caption_provider: ImageCaptionProvider | None,
    region_ocr: _PixelOcr,
) -> PageTextResult:
    table_rects = [
        _artifact_source_rect(page, artifact)
        for artifact in parsed.artifacts
        if artifact.unit_kind == "pdf_table"
    ]
    claimed = [_artifact_source_rect(page, artifact) for artifact in parsed.artifacts]
    candidates = [
        rect
        for rect in detect_visual_region_rects(page, table_rects)
        if not any(_rect_overlap_ratio(rect, existing) >= _VISUAL_CLAIM_OVERLAP for existing in claimed)
    ]
    if not candidates:
        return parsed

    text = parsed.text
    artifacts = list(parsed.artifacts)
    for source_rect in candidates:
        try:
            region = _normalized_region(source_rect, page, display_space=False)
        except ValueError:
            continue
        crop_png, crop_pixels = _crop_region_png(page, region)
        try:
            ocr = region_ocr(crop_pixels)
        except Exception as error:
            raise IngestionError("pdf_visual_ocr_failed", "PDF visual region OCR failed.") from error
        ocr_text = ocr.text.strip()
        provider = caption_provider or _require_caption_provider()
        try:
            caption_text = provider.caption(crop_png, content_type="image/png").strip()
        except ModelProviderError:
            raise
        except Exception as error:
            raise IngestionError(
                "pdf_visual_caption_failed",
                "PDF visual region caption failed.",
            ) from error
        if not caption_text:
            raise IngestionError(
                "pdf_visual_caption_empty",
                "PDF visual region caption is required and was empty.",
            )
        unit_text = "\n".join(part for part in (caption_text, ocr_text) if part)
        prefix = "" if not text or text.endswith("\n") else "\n"
        start = len(text) + len(prefix)
        text = f"{text}{prefix}{unit_text}"
        artifacts.append(
            PageArtifactResult(
                text=unit_text,
                unit_kind="pdf_figure",
                regions=(region,),
                char_ranges=((start, len(text)),),
            )
        )
        claimed.append(source_rect)
    if text == parsed.text and len(artifacts) == len(parsed.artifacts):
        return parsed
    return PageTextResult(
        page_number=parsed.page_number,
        text=text,
        geometry=parsed.geometry,
        source_kind=parsed.source_kind,
        regions=parsed.regions,
        artifacts=tuple(artifacts),
        ocr_blocks=parsed.ocr_blocks,
    )


def _artifact_source_rect(page: fitz.Page, artifact: PageArtifactResult) -> fitz.Rect:
    region = artifact.regions[0]
    return fitz.Rect(
        region.x * page.rect.width,
        region.y * page.rect.height,
        (region.x + region.width) * page.rect.width,
        (region.y + region.height) * page.rect.height,
    ) * ~page.rotation_matrix


def _crop_region_png(page: fitz.Page, region: SpatialRegionResult) -> tuple[bytes, np.ndarray]:
    clip = fitz.Rect(
        region.x * page.rect.width,
        region.y * page.rect.height,
        (region.x + region.width) * page.rect.width,
        (region.y + region.height) * page.rect.height,
    )
    pixmap = page.get_pixmap(clip=clip, dpi=150, alpha=False)
    pixels = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height,
        pixmap.width,
        pixmap.n,
    )
    return pixmap.tobytes("png"), pixels


def _require_caption_provider() -> ImageCaptionProvider:
    from ai_pdf_api.modalities.image_caption import get_image_caption_provider

    try:
        return get_image_caption_provider()
    except ModelProviderError:
        raise
    except Exception as error:
        raise IngestionError(
            "pdf_visual_caption_not_configured",
            "Vision caption is required for abstract PDF figures and is not configured.",
        ) from error


def _chunk_size(snapshot: Mapping[str, object]) -> int:
    value = snapshot.get("chunkSize", CHUNK_SIZE)
    if not isinstance(value, int) or isinstance(value, bool) or not 200 <= value <= 4000:
        raise IngestionError("invalid_chunk_size", "Ingestion job has an invalid chunk size.")
    return value


def _validate_native_pages(pages: list[PageTextResult]) -> None:
    expected_numbers = list(range(1, len(pages) + 1))
    if [page.page_number for page in pages] != expected_numbers:
        raise IngestionError("pdf_page_order_invalid", "PDF parser returned invalid page ordering.")
    if any(page.geometry is None for page in pages):
        raise IngestionError("pdf_geometry_missing", "PDF parser did not return page geometry.")
    if any(page.source_kind != "layout" or page.regions for page in pages):
        raise IngestionError(
            "pdf_layout_invalid",
            "PDF layout parser returned modality content outside its contract.",
        )


def _indexed_ocr_pages(pages: list[PageTextResult]) -> dict[int, PageTextResult]:
    results: dict[int, PageTextResult] = {}
    for page in pages:
        if page.page_number in results:
            raise ValueError("OCR returned duplicate PDF page results.")
        results[page.page_number] = page
    return results


def _merge_ocr_page(native: PageTextResult, ocr: PageTextResult) -> PageTextResult:
    if ocr.source_kind != "ocr":
        raise ValueError("OCR page result has an invalid source kind.")
    return PageTextResult(
        page_number=native.page_number,
        text=ocr.text,
        geometry=native.geometry,
        source_kind="ocr",
        regions=ocr.regions,
        ocr_blocks=ocr.ocr_blocks,
    )
