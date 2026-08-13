"""Worker module import must not require vision/caption secrets.

CI runs worker tests without OPENAI keys. Image caption must resolve lazily
at image ingest time, not at import of ai_pdf_worker.main.
"""

from __future__ import annotations

import os

import pytest


def test_import_worker_main_without_openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("AI_PDF_OPENAI_API_KEY", "")
    # Drop cached settings/module so empty env is observed if reloaded later.
    import ai_pdf_api.core.settings as settings_mod
    import importlib

    # Ensure empty key is what settings would see for a fresh process: we only
    # assert import of worker main does not call get_image_caption_provider.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AI_PDF_OPENAI_API_KEY", raising=False)

    import ai_pdf_worker.main as worker_main

    importlib.reload(worker_main)

    assert "image" in worker_main.INGESTION_ADAPTERS.asset_kinds
    adapter = worker_main.INGESTION_ADAPTERS.get("image")
    # Provider not required until ingest.
    assert getattr(adapter, "_caption_provider", "missing") is None
