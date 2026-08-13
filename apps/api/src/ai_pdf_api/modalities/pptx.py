"""PPTX modality helpers: slide/shape text parse and locators."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from xml.etree import ElementTree

from ai_pdf_api.modalities.office_ooxml import (
    CONTENT_TYPES_PART,
    PPT_MAIN_CONTENT_TYPE,
    PPTX_MIME,
    OfficePackageError,
    detect_pptx_mime_type,
    inspect_office_package,
    read_zip_text,
    validate_office_upload_payload,
    write_ooxml_package,
)

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
PPTX_PARSER_VERSION = "pptx-parser-v1"
PPTX_NORMALIZATION_VERSION = "pptx-normalization-v1"

__all__ = [
    "PPTX_MIME",
    "PPTX_NORMALIZATION_VERSION",
    "PPTX_PARSER_VERSION",
    "ParsedPptxShape",
    "PptxIntegrityError",
    "PptxParseResult",
    "detect_pptx_mime_type",
    "parse_pptx_presentation",
    "text_sha256",
    "validate_pptx_shape",
    "validate_pptx_upload_payload",
]


class PptxIntegrityError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedPptxShape:
    slide_index: int
    shape_id: str
    text: str
    text_sha256: str


@dataclass(frozen=True)
class PptxParseResult:
    shapes: tuple[ParsedPptxShape, ...]
    source_sha256: str
    normalized_text: str
    content_sha256: str


def text_sha256(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def validate_pptx_upload_payload(payload: bytes) -> None:
    validate_office_upload_payload(payload, expected_kind="pptx")


def parse_pptx_presentation(payload: bytes, *, mime_type: str = PPTX_MIME) -> PptxParseResult:
    if mime_type != PPTX_MIME:
        raise OfficePackageError("asset_mime_mismatch", f"PPTX adapter only accepts {PPTX_MIME}.")
    inspect_office_package(payload, expected_kind="pptx")
    presentation = ElementTree.fromstring(read_zip_text(payload, "ppt/presentation.xml"))
    sld_id_lst = presentation.find(f"{{{P_NS}}}sldIdLst")
    slide_count = 0
    if sld_id_lst is not None:
        slide_count = len(list(sld_id_lst))
    if slide_count == 0:
        slide_count = 1
    shapes: list[ParsedPptxShape] = []
    lines: list[str] = []
    for index in range(1, slide_count + 1):
        part = f"ppt/slides/slide{index}.xml"
        try:
            slide_xml = read_zip_text(payload, part)
        except OfficePackageError:
            continue
        root = ElementTree.fromstring(slide_xml)
        for shape in root.iter(f"{{{P_NS}}}sp"):
            cnv = shape.find(f"{{{P_NS}}}nvSpPr/{{{P_NS}}}cNvPr")
            shape_id = "1"
            if cnv is not None:
                shape_id = cnv.attrib.get("id") or cnv.attrib.get("name") or "1"
            texts = [node.text or "" for node in shape.iter(f"{{{A_NS}}}t")]
            text = " ".join(part.strip() for part in texts if part and part.strip())
            if not text:
                continue
            digest = text_sha256(text)
            shapes.append(
                ParsedPptxShape(
                    slide_index=index,
                    shape_id=str(shape_id),
                    text=text,
                    text_sha256=digest,
                )
            )
            lines.append(f"slide{index}#{shape_id}={text}")
    if not shapes:
        raise OfficePackageError("office_parse_failed", "PPTX produced no non-empty shapes.")
    normalized = "\n".join(lines)
    return PptxParseResult(
        shapes=tuple(shapes),
        source_sha256=sha256(payload).hexdigest(),
        normalized_text=normalized,
        content_sha256=text_sha256(normalized),
    )


def validate_pptx_shape(
    *,
    slide_index: int,
    shape_id: str,
    text_sha256_value: str,
    expected_text: str,
) -> None:
    if slide_index < 1 or not shape_id:
        raise PptxIntegrityError("pptx_shape requires slide_index >= 1 and shape_id")
    if text_sha256_value != text_sha256(expected_text):
        raise PptxIntegrityError("pptx_shape text_sha256 does not match shape text")


def build_minimal_pptx_bytes(
    *,
    shapes: list[tuple[int, str, str]] | None = None,
    include_macro: bool = False,
    encrypted: bool = False,
) -> bytes:
    """shapes: (slide_index, shape_id, text)."""
    if encrypted:
        return write_ooxml_package(
            {
                CONTENT_TYPES_PART: _types_xml(),
                "EncryptedPackage": b"secret",
                "EncryptionInfo": b"info",
            }
        )
    items = shapes or [(1, "2", "Quarterly review")]
    slide_xml = (
        f'<p:sld xmlns:p="{P_NS}" xmlns:a="{A_NS}">'
        "<p:cSld><p:spTree>"
        + "".join(
            (
                f'<p:sp><p:nvSpPr><p:cNvPr id="{_esc(shape_id)}" name="Title {_esc(shape_id)}"/>'
                "</p:nvSpPr><p:txBody><a:p><a:r>"
                f"<a:t>{_esc(text)}</a:t></a:r></a:p></p:txBody></p:sp>"
            )
            for _slide, shape_id, text in items
        )
        + "</p:spTree></p:cSld></p:sld>"
    )
    presentation = (
        f'<p:presentation xmlns:p="{P_NS}">'
        "<p:sldIdLst><p:sldId id=\"256\" r:id=\"rId2\" "
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
        "</p:sldIdLst></p:presentation>"
    )
    parts: dict[str, bytes | str] = {
        CONTENT_TYPES_PART: _types_xml(include_macro=include_macro),
        "ppt/presentation.xml": presentation,
        "ppt/slides/slide1.xml": slide_xml,
    }
    if include_macro:
        parts["ppt/vbaProject.bin"] = b"macro"
    return write_ooxml_package(parts)


def _types_xml(*, include_macro: bool = False) -> str:
    extra = ""
    if include_macro:
        extra = (
            '<Override PartName="/ppt/vbaProject.bin" '
            'ContentType="application/vnd.ms-office.vbaProject"/>'
        )
    return (
        f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        f'<Override PartName="/ppt/presentation.xml" ContentType="{PPT_MAIN_CONTENT_TYPE}"/>'
        f"{extra}</Types>"
    )


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
