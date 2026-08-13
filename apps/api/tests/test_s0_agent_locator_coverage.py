"""F-AGENT / F-MIX closeout: all S0-enabled kinds are research-searchable and codec-backed."""

from __future__ import annotations

from ai_pdf_api.modalities.evidence import PRODUCTION_LOCATOR_CODECS
from ai_pdf_api.modalities.registry import build_production_registry


def test_production_registry_exposes_all_s0_kinds_to_text_retrieval() -> None:
    registry = build_production_registry()
    expected_kinds = frozenset(
        {
            "pdf",
            "image",
            "document",
            "docx",
            "xlsx",
            "pptx",
            "html",
            "audio",
            "video",
        }
    )
    assert registry.asset_kinds == expected_kinds
    assert registry.enabled_asset_kinds == expected_kinds

    channel = registry.retrieval_channel_scope("text")
    kinds_in_channel = {signature[0] for signature in channel.type_signatures}
    # Image uses image channel signatures too; text channel must cover document-like + AV transcript.
    assert {
        "pdf",
        "image",
        "document",
        "docx",
        "xlsx",
        "pptx",
        "html",
        "audio",
        "video",
    }.issubset(kinds_in_channel)


def test_production_locator_codecs_cover_all_s0_locator_kinds() -> None:
    registry = build_production_registry()
    catalog = registry.expected_catalog()
    locator_kinds = {kind for kind, _version, _family in catalog.locators}
    # Codec registry maps by kind string
    for kind in locator_kinds:
        PRODUCTION_LOCATOR_CODECS.get(kind)


def test_expected_catalog_matches_enabled_modules_exactly() -> None:
    registry = build_production_registry()
    catalog = registry.expected_catalog()
    registry.validate_catalog(catalog)
    assert {kind for kind, _version in catalog.enabled_assets} == registry.enabled_asset_kinds
