from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from io import BytesIO
from typing import Protocol

import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from ai_pdf_api.modalities.image_ingestion import (
    IMAGE_ORIENTED_CONTENT_TYPE,
    ImageAnalysisResult,
    ImageNormalizationResult,
    ImageOcrRegionResult,
    build_image_oriented_object_key,
    delete_image_content,
    persist_image_analysis,
    persist_image_orientation,
)
from ai_pdf_api.modalities.image_caption import ImageCaptionProvider
from ai_pdf_api.modalities.ingestion import GeneratedObject, IngestionError, IngestionResult
from ai_pdf_api.models import Asset
from ai_pdf_api.services.providers import ModelProviderError

from ai_pdf_worker.image import normalize_image
from ai_pdf_worker.ocr import OcrTextResult, recognize_pixels


def extract_image_text_with_ocr(payload: bytes) -> OcrTextResult:
    with Image.open(BytesIO(payload)) as image:
        image.load()
        with image.convert("RGB") as rgb:
            return recognize_pixels(np.asarray(rgb))


class ImageNormalizer(Protocol):
    def __call__(
        self,
        payload: bytes,
        *,
        expected_mime_type: str,
    ) -> ImageNormalizationResult: ...


class ImageOcrExtractor(Protocol):
    def __call__(self, payload: bytes) -> OcrTextResult: ...


class ImageIngestionAdapter:
    asset_kind = "image"

    def __init__(
        self,
        *,
        caption_provider: ImageCaptionProvider,
        normalizer: ImageNormalizer = normalize_image,
        ocr_extractor: ImageOcrExtractor = extract_image_text_with_ocr,
    ) -> None:
        self._caption_provider = caption_provider
        self._normalizer = normalizer
        self._ocr_extractor = ocr_extractor

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
        _validate_caption_config(config_snapshot, self._caption_provider)
        normalized = self._normalizer(payload, expected_mime_type=asset.mime_type)
        try:
            ocr = self._ocr_extractor(normalized.payload)
        except Exception as error:
            raise IngestionError("image_ocr_failed", "Image OCR processing failed.") from error
        caption = self._caption_provider.caption(
            normalized.payload,
            content_type=IMAGE_ORIENTED_CONTENT_TYPE,
        )
        object_key = build_image_oriented_object_key(asset, processing_generation)
        oriented_representation = persist_image_orientation(
            db,
            asset=asset,
            result=normalized,
            object_key=object_key,
            processing_generation=processing_generation,
            created_at=created_at,
        )
        persist_image_analysis(
            db,
            asset=asset,
            oriented_representation=oriented_representation,
            geometry=normalized,
            result=ImageAnalysisResult(
                ocr_regions=tuple(
                    ImageOcrRegionResult(
                        text=region.text,
                        x=region.x,
                        y=region.y,
                        width=region.width,
                        height=region.height,
                        char_start=region.char_start,
                        char_end=region.char_end,
                    )
                    for region in ocr.regions
                ),
                caption=caption,
                caption_provider=self._caption_provider.provider,
                caption_model=self._caption_provider.model,
                caption_version=self._caption_provider.version,
            ),
            processing_generation=processing_generation,
            created_at=created_at,
        )
        return IngestionResult(
            generated_objects=(
                GeneratedObject(
                    object_key=object_key,
                    payload=normalized.payload,
                    content_type=IMAGE_ORIENTED_CONTENT_TYPE,
                    content_sha256=normalized.content_sha256,
                ),
            )
        )

    def cleanup(self, db: Session, *, asset: Asset) -> None:
        delete_image_content(db, asset.id)


def _validate_caption_config(
    snapshot: Mapping[str, object],
    provider: ImageCaptionProvider,
) -> None:
    from ai_pdf_api.services.capabilities import require_matching_snapshot_fingerprint

    expected = {
        "imageCaptionProvider": provider.provider,
        "imageCaptionModel": provider.model,
        "imageCaptionVersion": provider.version,
        "imageCaptionDetail": provider.detail,
        "imageCaptionMaxOutputTokens": provider.max_output_tokens,
    }
    if any(snapshot.get(key) != value for key, value in expected.items()):
        raise ModelProviderError(
            "image_caption_configuration_mismatch",
            "Image caption provider configuration does not match the job snapshot.",
        )
    require_matching_snapshot_fingerprint(
        snapshot,
        field_name="imageCaptionProfileFingerprint",
        actual_fingerprint=getattr(provider, "config_fingerprint", None),
        error_code="image_caption_configuration_mismatch",
        error_message="Image caption provider configuration does not match the job snapshot.",
        error_cls=ModelProviderError,
    )
