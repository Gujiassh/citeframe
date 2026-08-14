"""Modality-agnostic visual enrichment for generation messages.

Chat orchestration must not import kind-specific crop helpers. Register
enrichers here (or compose PRODUCTION_VISUAL_ENRICHERS) instead.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Protocol

from sqlalchemy.orm import Session

from ai_pdf_api.modalities.evidence_targets import ImageBytesLoader
from ai_pdf_api.modalities.pdf_evidence_targets import collect_retrieval_pdf_crop_payloads
from ai_pdf_api.services.retrieval import RetrievedContent

logger = logging.getLogger(__name__)

DEFAULT_MAX_VISUAL_IMAGES = 4


class VisualEvidenceEnricher(Protocol):
    """Attach optional PNG (or other image) bytes for multimodal generation."""

    def enrich(
        self,
        db: Session,
        retrieved: Sequence[RetrievedContent],
        *,
        image_bytes_loader: ImageBytesLoader,
        max_images: int = DEFAULT_MAX_VISUAL_IMAGES,
    ) -> tuple[bytes, ...]:
        """Return image payloads; failures must soft-skip (return partial/empty)."""
        ...


class RetrievalPdfRegionCropEnricher:
    """P1: crop retrieved pdf_region hits into generation input images."""

    def enrich(
        self,
        db: Session,
        retrieved: Sequence[RetrievedContent],
        *,
        image_bytes_loader: ImageBytesLoader,
        max_images: int = DEFAULT_MAX_VISUAL_IMAGES,
    ) -> tuple[bytes, ...]:
        return collect_retrieval_pdf_crop_payloads(
            db,
            list(retrieved),
            image_bytes_loader=image_bytes_loader,
            max_images=max_images,
        )


PRODUCTION_VISUAL_ENRICHERS: tuple[VisualEvidenceEnricher, ...] = (
    RetrievalPdfRegionCropEnricher(),
)


def collect_visual_generation_payloads(
    db: Session,
    retrieved: Sequence[RetrievedContent],
    *,
    image_bytes_loader: ImageBytesLoader,
    enrichers: Sequence[VisualEvidenceEnricher] | None = None,
    max_images: int = DEFAULT_MAX_VISUAL_IMAGES,
) -> tuple[bytes, ...]:
    """Run registered enrichers with a global image cap (soft-skip per enricher)."""
    if max_images < 1 or not retrieved:
        return ()
    active = enrichers if enrichers is not None else PRODUCTION_VISUAL_ENRICHERS
    collected: list[bytes] = []
    remaining = max_images
    for enricher in active:
        if remaining < 1:
            break
        try:
            part = enricher.enrich(
                db,
                retrieved,
                image_bytes_loader=image_bytes_loader,
                max_images=remaining,
            )
        except Exception as error:
            logger.info(
                "visual_enrich skip reason=enricher_error enricher=%s error=%s",
                type(enricher).__name__,
                type(error).__name__,
            )
            continue
        for payload in part:
            if remaining < 1:
                break
            collected.append(payload)
            remaining -= 1
    return tuple(collected)


__all__ = [
    "DEFAULT_MAX_VISUAL_IMAGES",
    "PRODUCTION_VISUAL_ENRICHERS",
    "RetrievalPdfRegionCropEnricher",
    "VisualEvidenceEnricher",
    "collect_visual_generation_payloads",
]
