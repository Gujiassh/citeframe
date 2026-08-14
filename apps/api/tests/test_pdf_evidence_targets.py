"""PV-4: PDF region evidence targets crop to PNG for generation."""

from __future__ import annotations

import fitz
import pytest

from ai_pdf_api.modalities.evidence_targets import EvidenceTargetError
from ai_pdf_api.modalities.pdf_evidence_targets import (
    collect_retrieval_pdf_crop_payloads,
    crop_pdf_regions_png,
)
from ai_pdf_api.schemas.chat import PdfRegionEvidenceTarget, SpatialRegion, ChatStreamRequest
from ai_pdf_api.services.evidence_targets import PRODUCTION_EVIDENCE_TARGET_RESOLVERS


def _minimal_pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page(width=300, height=400)
    page.insert_text((50, 80), "Hello PDF crop fixture")
    page.draw_rect(fitz.Rect(40, 100, 200, 220), color=(0, 0, 1), width=2)
    payload = document.tobytes()
    document.close()
    return payload


def test_crop_pdf_regions_png_returns_png_bytes() -> None:
    pdf = _minimal_pdf_bytes()
    crops = crop_pdf_regions_png(
        pdf,
        page_number=1,
        regions=[SpatialRegion(x=0.1, y=0.2, width=0.5, height=0.3)],
    )
    assert len(crops) == 1
    assert crops[0].startswith(b"\x89PNG")


def test_crop_pdf_regions_rejects_out_of_range_page() -> None:
    pdf = _minimal_pdf_bytes()
    with pytest.raises(EvidenceTargetError) as error:
        crop_pdf_regions_png(
            pdf,
            page_number=9,
            regions=[SpatialRegion(x=0.1, y=0.1, width=0.2, height=0.2)],
        )
    assert error.value.code == "evidence_target_page_invalid"


def test_chat_stream_accepts_pdf_region_evidence_target() -> None:
    payload = ChatStreamRequest.model_validate(
        {
            "threadId": "thread-1",
            "question": "What is in the figure?",
            "assetScope": {"mode": "all_ready"},
            "evidenceTargets": [
                {
                    "kind": "pdf_region",
                    "assetId": "asset-1",
                    "processingGeneration": 1,
                    "pageNumber": 1,
                    "coordinateSpace": "pdf_crop_box_normalized_top_left_v1",
                    "regions": [{"x": 0.1, "y": 0.1, "width": 0.4, "height": 0.4}],
                }
            ],
        }
    )
    assert len(payload.evidenceTargets) == 1
    assert payload.evidenceTargets[0].kind == "pdf_region"


def test_production_resolvers_register_pdf_and_image() -> None:
    kinds = set(PRODUCTION_EVIDENCE_TARGET_RESOLVERS._by_kind)
    assert kinds == {"image_region", "pdf_region"}


def test_pdf_region_target_model() -> None:
    target = PdfRegionEvidenceTarget(
        kind="pdf_region",
        assetId="a",
        processingGeneration=1,
        pageNumber=2,
        coordinateSpace="pdf_crop_box_normalized_top_left_v1",
        regions=[SpatialRegion(x=0, y=0, width=1, height=1)],
    )
    assert target.pageNumber == 2


def test_collect_retrieval_pdf_crop_empty_when_no_hits() -> None:
    class _DB:
        def get(self, *_a, **_k):
            return None

        def scalars(self, *_a, **_k):
            class _S:
                def all(self):
                    return []
            return _S()

    assert collect_retrieval_pdf_crop_payloads(_DB(), [], image_bytes_loader=lambda _k: b"") == ()
