"""Architecture hardening: Chat must not import kind-specific crop modules."""

from __future__ import annotations

from pathlib import Path


def test_chat_service_does_not_import_pdf_evidence_targets() -> None:
    chat_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "ai_pdf_api"
        / "services"
        / "chat.py"
    )
    source = chat_path.read_text(encoding="utf-8")
    assert "pdf_evidence_targets" not in source
    assert "collect_visual_generation_payloads" in source
    assert "collect_retrieval_pdf_crop_payloads" not in source
