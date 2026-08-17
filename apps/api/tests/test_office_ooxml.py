from dataclasses import replace

import pytest

from ai_pdf_api.modalities.docx import (
    build_minimal_docx_bytes,
    parse_docx_document,
    validate_docx_upload_payload,
)
from ai_pdf_api.modalities.office_modules import DOCX_MODULE, PPTX_MODULE, XLSX_MODULE
from ai_pdf_api.modalities.office_ooxml import (
    DOCX_MIME,
    OLECF_SIGNATURE,
    OfficePackageError,
)
from ai_pdf_api.modalities.pptx import build_minimal_pptx_bytes, parse_pptx_presentation
from ai_pdf_api.modalities.registry import (
    DOCUMENT_MODULE,
    IMAGE_MODULE,
    PDF_MODULE,
    ModalityRegistry,
    TypeRegistration,
    build_production_registry,
)
from ai_pdf_api.modalities.xlsx import build_minimal_xlsx_bytes, parse_xlsx_workbook


def test_production_registry_enables_office_kinds_after_s0() -> None:
    registry = build_production_registry()
    assert {"docx", "xlsx", "pptx"}.issubset(registry.asset_kinds)
    assert {"docx", "xlsx", "pptx"}.issubset(registry.enabled_asset_kinds)
    assert "office" not in registry.asset_kinds

def test_office_modules_exist_as_separate_kinds_and_are_enabled_for_s0() -> None:
    assert DOCX_MODULE.asset_kind == "docx"
    assert XLSX_MODULE.asset_kind == "xlsx"
    assert PPTX_MODULE.asset_kind == "pptx"
    assert DOCX_MODULE.enabled
    assert XLSX_MODULE.enabled
    assert PPTX_MODULE.enabled
    registry = ModalityRegistry(
        (PDF_MODULE, IMAGE_MODULE, DOCUMENT_MODULE, DOCX_MODULE, XLSX_MODULE, PPTX_MODULE),
        embedding_spaces=(TypeRegistration("text"),),
    )
    assert {"docx", "xlsx", "pptx"}.issubset(registry.enabled_asset_kinds)
    assert registry.for_mime_type(DOCX_MIME).asset_kind == "docx"


def test_parse_docx_is_deterministic_and_captures_blocks() -> None:
    payload = build_minimal_docx_bytes(
        paragraphs=[
            ("Heading1", "Intro"),
            ("Normal", "Hello world paragraph."),
            ("ListParagraph", "first item"),
            ("table", "Col A | Col B"),
        ]
    )
    first = parse_docx_document(payload)
    second = parse_docx_document(payload)
    assert first.normalized_text == second.normalized_text
    assert first.content_sha256 == second.content_sha256
    kinds = [block.block_kind for block in first.blocks]
    assert kinds == ["heading", "paragraph", "list_item", "table"]
    assert first.blocks[0].heading_path == ("Intro",)
    assert "Hello world paragraph." in first.normalized_text


def test_docx_rejects_macros_and_encrypted_packages() -> None:
    with pytest.raises(OfficePackageError, match="macros"):
        validate_docx_upload_payload(build_minimal_docx_bytes(include_macro=True))
    with pytest.raises(OfficePackageError, match="Encrypted"):
        validate_docx_upload_payload(build_minimal_docx_bytes(encrypted=True))
    with pytest.raises(OfficePackageError, match="Encrypted"):
        validate_docx_upload_payload(OLECF_SIGNATURE + b"rest")


def test_parse_xlsx_and_pptx_units() -> None:
    xlsx = parse_xlsx_workbook(build_minimal_xlsx_bytes())
    assert {(cell.cell_ref, cell.text) for cell in xlsx.cells} == {
        ("A1", "Revenue"),
        ("B1", "42"),
    }
    pptx = parse_pptx_presentation(build_minimal_pptx_bytes())
    assert pptx.shapes[0].slide_index == 1
    assert pptx.shapes[0].text == "Quarterly review"


def test_xlsx_pptx_reject_macros() -> None:
    with pytest.raises(OfficePackageError, match="macros"):
        parse_xlsx_workbook(build_minimal_xlsx_bytes(include_macro=True))
    with pytest.raises(OfficePackageError, match="macros"):
        parse_pptx_presentation(build_minimal_pptx_bytes(include_macro=True))


def test_disabled_office_module_can_be_enabled_only_in_test_registry() -> None:
    enabled = replace(DOCX_MODULE, enabled=True)
    registry = ModalityRegistry(
        (PDF_MODULE, IMAGE_MODULE, DOCUMENT_MODULE, enabled),
        embedding_spaces=(TypeRegistration("text"),),
    )
    payload = build_minimal_docx_bytes()
    module = registry.inspect_upload(DOCX_MIME, payload[:16])
    assert module.asset_kind == "docx"
    registry.validate_upload_payload(module, payload)
    assert {"docx", "xlsx", "pptx"}.issubset(build_production_registry().asset_kinds)


def test_parse_pptx_geometry_and_picture_layout() -> None:
    payload = build_minimal_pptx_bytes(
        shapes=[(1, "2", "Hello"), (1, "3", "World")],
        with_geometry=True,
        with_picture=True,
    )
    parsed = parse_pptx_presentation(payload)
    by_id = {shape.shape_id: shape for shape in parsed.shapes}
    assert by_id["2"].x_emu == 914400
    assert by_id["2"].has_geometry()
    assert by_id["99"].shape_kind == "picture"
    assert by_id["99"].media_part == "ppt/media/image1.png"
    layout = parsed.layout_dict()
    assert layout["layoutVersion"] == "pptx-layout-v1"
    assert layout["slideWidthEmu"] > 0
    assert any(s["shapeKind"] == "picture" for slide in layout["slides"] for s in slide["shapes"])
    # layout payload is valid JSON with normalized text
    import json
    body = json.loads(parsed.layout_payload.decode("utf-8"))
    assert "Hello" in body["normalizedText"]


def test_pptx_layout_payload_hash_matches_content_sha256() -> None:
    from hashlib import sha256

    payload = build_minimal_pptx_bytes(
        shapes=[(1, "2", "Hello")],
        with_geometry=True,
        with_picture=True,
    )
    parsed = parse_pptx_presentation(payload)
    assert parsed.layout_payload
    assert parsed.content_sha256 == sha256(parsed.layout_payload).hexdigest()
    assert parsed.text_content_sha256
    assert parsed.text_content_sha256 != parsed.content_sha256
