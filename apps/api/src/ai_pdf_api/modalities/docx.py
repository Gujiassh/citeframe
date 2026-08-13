"""DOCX modality helpers: parse, normalize, locator validation.

Parser lives here so API upload validation and worker ingest share one
fail-closed contract. Production registry enablement is intentionally
out of this module (see S0_HANDOFF.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable, Protocol
from xml.etree import ElementTree

from ai_pdf_api.modalities.office_ooxml import (
    CONTENT_TYPES_PART,
    DOCX_MIME,
    WORD_MAIN_CONTENT_TYPE,
    OfficePackageError,
    detect_docx_mime_type,
    inspect_office_package,
    read_zip_text,
    validate_office_upload_payload,
    write_ooxml_package,
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DOCX_PARSER_VERSION = "docx-parser-v1"
DOCX_NORMALIZATION_VERSION = "docx-normalization-v1"
DOCX_BLOCK_KINDS = frozenset({"heading", "paragraph", "list_item", "table"})
DOCX_HEADING_LEVELS = frozenset({1, 2, 3, 4, 5, 6})

__all__ = [
    "DOCX_MIME",
    "DOCX_NORMALIZATION_VERSION",
    "DOCX_PARSER_VERSION",
    "DocxIntegrityError",
    "DocxParseResult",
    "ParsedDocxBlock",
    "detect_docx_mime_type",
    "parse_docx_document",
    "split_office_text",
    "stable_docx_block_id",
    "text_sha256",
    "validate_docx_anchor_range",
    "validate_docx_upload_payload",
]


class DocxIntegrityError(ValueError):
    pass


class DocxNormalizedLike(Protocol):
    format: str
    parser_version: str
    normalization_version: str
    normalized_text: str
    content_sha256: str
    block_count: int


class DocxBlockLike(Protocol):
    block_id: str
    block_order: int
    block_kind: str
    heading_level: int | None
    heading_path: object
    char_start: int
    char_end: int
    text_sha256: str
    text_content: str
    normalization_version: str


@dataclass(frozen=True)
class ParsedDocxBlock:
    block_order: int
    block_kind: str
    heading_level: int | None
    heading_path: tuple[str, ...]
    text: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class DocxParseResult:
    normalized_text: str
    content_sha256: str
    blocks: tuple[ParsedDocxBlock, ...]
    source_sha256: str


def text_sha256(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def validate_docx_upload_payload(payload: bytes) -> None:
    validate_office_upload_payload(payload, expected_kind="docx")


def parse_docx_document(payload: bytes, *, mime_type: str = DOCX_MIME) -> DocxParseResult:
    if mime_type != DOCX_MIME:
        raise OfficePackageError("asset_mime_mismatch", f"DOCX adapter only accepts {DOCX_MIME}.")
    inspect_office_package(payload, expected_kind="docx")
    document_xml = read_zip_text(payload, "word/document.xml")
    try:
        root = ElementTree.fromstring(document_xml)
    except ElementTree.ParseError as error:
        raise OfficePackageError(
            "office_parse_failed",
            "word/document.xml is not well-formed XML.",
        ) from error
    body = root.find(f"{{{W_NS}}}body")
    if body is None:
        raise OfficePackageError("office_parse_failed", "word/document.xml is missing w:body.")

    raw_blocks: list[tuple[str, int | None, list[str], str]] = []
    heading_stack: list[tuple[int, str]] = []
    for child in list(body):
        tag = _local(child.tag)
        if tag == "p":
            text = _paragraph_text(child)
            if not text:
                continue
            style = _paragraph_style(child)
            heading_level = _heading_level(style)
            if heading_level is not None:
                while heading_stack and heading_stack[-1][0] >= heading_level:
                    heading_stack.pop()
                heading_stack.append((heading_level, text))
                path = [part for _, part in heading_stack]
                raw_blocks.append(("heading", heading_level, path, text))
                continue
            path = [part for _, part in heading_stack]
            kind = "list_item" if _is_list_item(child) else "paragraph"
            raw_blocks.append((kind, None, path, text))
            continue
        if tag == "tbl":
            text = _table_text(child)
            if text:
                raw_blocks.append(("table", None, [part for _, part in heading_stack], text))

    if not raw_blocks:
        raise OfficePackageError(
            "office_parse_failed",
            "DOCX produced no non-empty text blocks.",
        )

    pieces: list[str] = []
    parsed: list[ParsedDocxBlock] = []
    cursor = 0
    for order, (kind, heading_level, heading_path, text) in enumerate(raw_blocks):
        if order:
            pieces.append("\n\n")
            cursor += 2
        start = cursor
        pieces.append(text)
        cursor += len(text)
        parsed.append(
            ParsedDocxBlock(
                block_order=order,
                block_kind=kind,
                heading_level=heading_level,
                heading_path=tuple(heading_path),
                text=text,
                char_start=start,
                char_end=cursor,
            )
        )
    normalized = "".join(pieces)
    return DocxParseResult(
        normalized_text=normalized,
        content_sha256=text_sha256(normalized),
        blocks=tuple(parsed),
        source_sha256=sha256(payload).hexdigest(),
    )


def stable_docx_block_id(
    *,
    source_sha256: str,
    parser_version: str,
    block_order: int,
    block_kind: str,
    heading_path: Iterable[str],
    text_sha256_value: str,
) -> str:
    if parser_version != DOCX_PARSER_VERSION:
        raise ValueError(f"Unsupported docx parser version: {parser_version}")
    if block_kind not in DOCX_BLOCK_KINDS:
        raise ValueError(f"Unsupported docx block_kind: {block_kind}")
    material = "\n".join(
        [
            source_sha256,
            parser_version,
            str(block_order),
            block_kind,
            "/".join(list(heading_path)),
            text_sha256_value,
        ]
    )
    digest = sha256(material.encode("utf-8")).hexdigest()
    return f"docxblk_{digest[:32]}"


def validate_hex_sha256(value: object, *, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise DocxIntegrityError(f"docx requires a lowercase hex SHA-256 {field_name}")
    return value


def validate_heading_path(heading_path: object) -> list[str]:
    if not isinstance(heading_path, list):
        raise ValueError("heading_path must be a list of strings")
    if any(not isinstance(part, str) or not part for part in heading_path):
        raise ValueError("heading_path must be an ordered array of non-empty strings")
    return list(heading_path)


def validate_docx_normalized_content(normalized: DocxNormalizedLike) -> str:
    if normalized.format != "docx":
        raise DocxIntegrityError("docx normalized content format is invalid")
    if normalized.parser_version != DOCX_PARSER_VERSION:
        raise DocxIntegrityError("docx parser_version is invalid")
    if normalized.normalization_version != DOCX_NORMALIZATION_VERSION:
        raise DocxIntegrityError("docx normalization_version is invalid")
    digest = validate_hex_sha256(normalized.content_sha256, field_name="content_sha256")
    if digest != text_sha256(normalized.normalized_text):
        raise DocxIntegrityError("docx content_sha256 does not match normalized_text")
    return normalized.normalized_text


def validate_docx_block_against_text(block: DocxBlockLike, *, normalized_text: str) -> list[str]:
    if block.block_kind not in DOCX_BLOCK_KINDS:
        raise DocxIntegrityError("docx block_kind is unsupported")
    if block.normalization_version != DOCX_NORMALIZATION_VERSION:
        raise DocxIntegrityError("docx block normalization_version is invalid")
    path = validate_heading_path(block.heading_path)
    if block.char_start < 0 or block.char_end <= block.char_start:
        raise DocxIntegrityError("docx block range is invalid")
    expected = normalized_text[block.char_start:block.char_end]
    if block.text_content != expected:
        raise DocxIntegrityError("docx block text_content does not match normalized substring")
    digest = validate_hex_sha256(block.text_sha256, field_name="text_sha256")
    if digest != text_sha256(block.text_content):
        raise DocxIntegrityError("docx block text_sha256 does not match block text_content")
    return path


def validate_docx_anchor_range(
    *,
    block_id: str,
    block_kind: str,
    heading_path: object,
    char_start: int,
    char_end: int,
    text_sha256_value: str,
    normalization_version: str,
    block: DocxBlockLike,
    normalized_text: str,
) -> list[str]:
    if normalization_version != DOCX_NORMALIZATION_VERSION:
        raise DocxIntegrityError("docx_anchor has an unsupported normalization_version")
    if not block_id:
        raise DocxIntegrityError("docx_anchor requires a stable block_id")
    if block_kind not in DOCX_BLOCK_KINDS:
        raise DocxIntegrityError("docx_anchor has an unsupported block_kind")
    if char_start < 0 or char_end <= char_start:
        raise DocxIntegrityError("docx_anchor requires a single non-empty char range")
    path = validate_heading_path(heading_path)
    digest = validate_hex_sha256(text_sha256_value, field_name="text_sha256")
    block_path = validate_docx_block_against_text(block, normalized_text=normalized_text)
    if block.block_id != block_id or block.block_kind != block_kind:
        raise DocxIntegrityError("docx_anchor does not match stored block")
    if block_path != path:
        raise DocxIntegrityError("docx_anchor heading_path does not match stored block")
    if char_start < block.char_start or char_end > block.char_end:
        raise DocxIntegrityError("docx_anchor range is outside the stored block bounds")
    range_text = normalized_text[char_start:char_end]
    if digest != text_sha256(range_text):
        raise DocxIntegrityError("docx_anchor text_sha256 does not match normalized substring")
    return path


def split_office_text(text: str, chunk_size: int, *, overlap: int) -> list[tuple[int, int, str]]:
    chunks: list[tuple[int, int, str]] = []
    start = 0
    text_length = len(text)
    effective_overlap = min(overlap, max(1, chunk_size // 2))
    while start < text_length:
        end = min(start + chunk_size, text_length)
        if end < text_length:
            boundary = text.rfind("\n", start + chunk_size // 2, end)
            if boundary <= start:
                boundary = text.rfind(" ", start + chunk_size // 2, end)
            if boundary > start:
                end = boundary
        chunk_text = text[start:end]
        stripped = chunk_text.strip()
        if stripped:
            leading = len(chunk_text) - len(chunk_text.lstrip())
            trailing = len(chunk_text) - len(chunk_text.rstrip())
            chunk_start = start + leading
            chunk_end = end - trailing
            chunks.append((chunk_start, chunk_end, text[chunk_start:chunk_end]))
        if end == text_length:
            break
        start = max(end - effective_overlap, start + 1)
    return chunks


def build_minimal_docx_bytes(
    *,
    paragraphs: list[tuple[str, str]] | None = None,
    include_macro: bool = False,
    encrypted: bool = False,
) -> bytes:
    """Fixture helper. paragraphs: list of (style_or_kind, text)."""
    if encrypted:
        return write_ooxml_package(
            {
                CONTENT_TYPES_PART: _content_types_xml(),
                "EncryptedPackage": b"secret",
                "EncryptionInfo": b"info",
            }
        )
    items = paragraphs or [("Heading1", "Intro"), ("Normal", "Hello world paragraph.")]
    body_xml: list[str] = []
    for style, text in items:
        if style == "table":
            body_xml.append(
                "<w:tbl><w:tr><w:tc><w:p><w:r>"
                f"<w:t>{_xml_escape(text)}</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
            )
            continue
        ppr = f'<w:pPr><w:pStyle w:val="{_xml_escape(style)}"/></w:pPr>'
        if style == "ListParagraph":
            ppr = (
                "<w:pPr><w:pStyle w:val=\"ListParagraph\"/>"
                "<w:numPr><w:ilvl w:val=\"0\"/><w:numId w:val=\"1\"/></w:numPr></w:pPr>"
            )
        body_xml.append(
            f"<w:p>{ppr}<w:r><w:t>{_xml_escape(text)}</w:t></w:r></w:p>"
        )
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<w:document xmlns:w="{W_NS}"><w:body>'
        + "".join(body_xml)
        + "</w:body></w:document>"
    )
    parts: dict[str, bytes | str] = {
        CONTENT_TYPES_PART: _content_types_xml(include_macro=include_macro),
        "word/document.xml": document,
    }
    if include_macro:
        parts["word/vbaProject.bin"] = b"macro-bytes"
    return write_ooxml_package(parts)


def _content_types_xml(*, include_macro: bool = False) -> str:
    extras = ""
    if include_macro:
        extras = (
            '<Override PartName="/word/vbaProject.bin" '
            'ContentType="application/vnd.ms-office.vbaProject"/>'
        )
    return (
        f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        f'<Override PartName="/word/document.xml" ContentType="{WORD_MAIN_CONTENT_TYPE}"/>'
        f"{extras}</Types>"
    )


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _qn(name: str) -> str:
    return f"{{{W_NS}}}{name}"


def _paragraph_style(paragraph: ElementTree.Element) -> str:
    style = paragraph.find(f"{_qn('pPr')}/{_qn('pStyle')}")
    if style is None:
        return "Normal"
    return style.attrib.get(_qn("val"), "Normal")


def _heading_level(style: str) -> int | None:
    lowered = style.lower().replace(" ", "")
    for level in range(1, 7):
        if lowered in {f"heading{level}", f"titel{level}"}:
            return level
    return None


def _is_list_item(paragraph: ElementTree.Element) -> bool:
    return paragraph.find(f"{_qn('pPr')}/{_qn('numPr')}") is not None


def _paragraph_text(paragraph: ElementTree.Element) -> str:
    parts: list[str] = []
    for node in paragraph.iter():
        if _local(node.tag) in {"t", "instrText"} and node.text:
            parts.append(node.text)
        if _local(node.tag) == "tab":
            parts.append(" ")
    return _collapse_ws("".join(parts))


def _table_text(table: ElementTree.Element) -> str:
    rows: list[str] = []
    for row in table.findall(_qn("tr")):
        cells: list[str] = []
        for cell in row.findall(_qn("tc")):
            cell_parts = [_paragraph_text(p) for p in cell.findall(_qn("p"))]
            cells.append(" ".join(part for part in cell_parts if part))
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def _collapse_ws(text: str) -> str:
    return " ".join(text.split())


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
