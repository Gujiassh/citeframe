from dataclasses import replace

import pytest
from ai_pdf_api.modalities.registry import (
    IMAGE_MODULE,
    PDF_MODULE,
    CatalogSnapshot,
    ModalityContractError,
    ModalityModule,
    ModalityRegistry,
    RetrievalChannelRegistration,
    TypeRegistration,
    build_production_registry,
)


def test_production_registry_enables_pdf_and_image_ingestion() -> None:
    registry = build_production_registry()

    assert registry.asset_kinds == frozenset({"pdf", "image"})
    assert registry.enabled_asset_kinds == frozenset({"pdf", "image"})
    assert registry.inspect_upload("application/pdf", b"%PDF-1.7").asset_kind == "pdf"
    assert registry.inspect_upload("image/png", b"\x89PNG\r\n\x1a\n").asset_kind == "image"


def test_registry_rejects_mime_and_signature_mismatches() -> None:
    registry = build_production_registry()

    with pytest.raises(ModalityContractError, match="Unsupported MIME type"):
        registry.inspect_upload("audio/wav", b"RIFF")
    with pytest.raises(ModalityContractError, match="File signature"):
        registry.inspect_upload("application/pdf", b"not-a-pdf")


@pytest.mark.parametrize(
    ("declared_mime_type", "header", "matches"),
    [
        ("image/png", b"\x89PNG\r\n\x1a\nrest", True),
        ("image/jpeg", b"\xff\xd8\xff\xe0rest", True),
        ("image/webp", b"RIFF\x10\x00\x00\x00WEBPVP8 ", True),
        ("image/png", b"\xff\xd8\xff\xe0rest", False),
        ("image/png", b"RIFF\x10\x00\x00\x00WEBPVP8 ", False),
        ("image/jpeg", b"\x89PNG\r\n\x1a\nrest", False),
        ("image/jpeg", b"RIFF\x10\x00\x00\x00WEBPVP8L", False),
        ("image/webp", b"\x89PNG\r\n\x1a\nrest", False),
        ("image/webp", b"\xff\xd8\xff\xe0rest", False),
        ("image/webp", b"RIFF\x10\x00\x00\x00WEBP", False),
    ],
)
def test_image_signature_must_match_declared_mime_type(
    declared_mime_type: str,
    header: bytes,
    matches: bool,
) -> None:
    registry = build_production_registry()

    if matches:
        assert registry.inspect_upload(declared_mime_type, header).asset_kind == "image"
    else:
        with pytest.raises(ModalityContractError, match="declared MIME type"):
            registry.inspect_upload(declared_mime_type, header)


def test_catalog_must_exactly_match_deployment_registry() -> None:
    registry = build_production_registry()
    expected = registry.expected_catalog()

    registry.validate_catalog(expected)
    with pytest.raises(ModalityContractError, match="does not match"):
        registry.validate_catalog(
            CatalogSnapshot(
                enabled_assets=expected.enabled_assets | {("audio", 1)},
                representations=expected.representations,
                content_units=expected.content_units,
                locators=expected.locators,
                embedding_spaces=expected.embedding_spaces,
            )
        )


def test_test_only_modality_extends_protocol_without_changing_production_modules() -> None:
    test_module = ModalityModule(
        asset_kind="test_timeline",
        contract_version=1,
        enabled=True,
        supported_mime_types=frozenset({"application/x-test-timeline"}),
        byte_inspector=lambda header: (
            "application/x-test-timeline" if header.startswith(b"TIMELINE") else None
        ),
        representation_types=(TypeRegistration("test_timeline_source"),),
        content_unit_types=(TypeRegistration("test_timeline_segment"),),
        locator_types=(
            TypeRegistration("test_timeline_range", detail_family="temporal"),
        ),
        retrieval_channels=(
            RetrievalChannelRegistration(
                kind="text",
                embedding_space="text",
                type_signatures=frozenset(
                    {("test_timeline_segment", "test_timeline_source", "test_timeline_range")}
                ),
            ),
        ),
        metrics_namespace="test_timeline",
        ingestion_config_snapshot=lambda: {"timelineParserVersion": "test-v1"},
    )
    registry = ModalityRegistry(
        (PDF_MODULE, IMAGE_MODULE, test_module),
        embedding_spaces=(TypeRegistration("text"),),
    )

    assert registry.get("test_timeline") is test_module
    assert registry.inspect_upload(
        "application/x-test-timeline", b"TIMELINE\x00"
    ) is test_module
    assert registry.ingestion_config_snapshot("test_timeline") == {
        "timelineParserVersion": "test-v1"
    }
    assert build_production_registry().asset_kinds == frozenset({"pdf", "image"})


def test_image_module_owns_caption_job_config_without_changing_shared_registry() -> None:
    registry = build_production_registry()

    assert registry.ingestion_config_snapshot("image") == {
        "imageCaptionProvider": "openai",
        "imageCaptionModel": "gpt-5.5",
        "imageCaptionVersion": "image-caption-v1",
        "imageCaptionDetail": "high",
        "imageCaptionMaxOutputTokens": 320,
    }
    assert registry.ingestion_config_snapshot("pdf") == {}


def test_text_retrieval_channel_registers_exact_pdf_and_image_type_signatures() -> None:
    channel = build_production_registry().retrieval_channel_scope("text")

    assert channel.embedding_space == "text"
    assert channel.type_signatures == frozenset(
        {
            ("pdf", "pdf_text_chunk", "pdf_text_legacy", "pdf_page"),
            ("pdf", "pdf_text_chunk", "pdf_page_layout", "pdf_page"),
            ("pdf", "pdf_text_chunk", "pdf_ocr", "pdf_page"),
            ("pdf", "pdf_ocr_region", "pdf_ocr", "pdf_region"),
            ("pdf", "pdf_table", "pdf_table", "pdf_region"),
            ("pdf", "pdf_figure", "pdf_figure", "pdf_region"),
            ("image", "image_ocr_region", "image_ocr", "image_region"),
            ("image", "image_caption", "image_caption", "image_region"),
        }
    )


def test_modality_ingestion_config_cannot_override_shared_job_fields() -> None:
    invalid_module = replace(
        PDF_MODULE,
        ingestion_config_snapshot=lambda: {"embeddingModel": "modality-owned"},
    )
    registry = ModalityRegistry(
        (invalid_module,),
        embedding_spaces=(TypeRegistration("text"),),
    )

    with pytest.raises(ModalityContractError, match="overrides shared keys"):
        registry.ingestion_config_snapshot("pdf")


def test_retrieval_channel_requires_a_registered_embedding_space() -> None:
    invalid_module = replace(
        PDF_MODULE,
        retrieval_channels=(
            replace(PDF_MODULE.retrieval_channels[0], embedding_space="visual"),
        ),
    )

    with pytest.raises(ModalityContractError, match="unregistered embedding space"):
        ModalityRegistry(
            (invalid_module,),
            embedding_spaces=(TypeRegistration("text"),),
        )
