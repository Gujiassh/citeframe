"""XLSX modality helpers: sheet/cell snapshot parse and range locators."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from xml.etree import ElementTree

from ai_pdf_api.modalities.office_ooxml import (
    CONTENT_TYPES_PART,
    EXCEL_MAIN_CONTENT_TYPE,
    XLSX_MIME,
    OfficePackageError,
    detect_xlsx_mime_type,
    inspect_office_package,
    read_zip_text,
    validate_office_upload_payload,
    write_ooxml_package,
)

SS_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XLSX_PARSER_VERSION = "xlsx-parser-v1"
XLSX_NORMALIZATION_VERSION = "xlsx-normalization-v1"

__all__ = [
    "XLSX_MIME",
    "XLSX_NORMALIZATION_VERSION",
    "XLSX_PARSER_VERSION",
    "ParsedXlsxCell",
    "XlsxIntegrityError",
    "XlsxParseResult",
    "detect_xlsx_mime_type",
    "parse_xlsx_workbook",
    "text_sha256",
    "validate_xlsx_range",
    "validate_xlsx_upload_payload",
]


class XlsxIntegrityError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedXlsxCell:
    sheet_name: str
    sheet_order: int
    cell_ref: str
    text: str
    text_sha256: str


@dataclass(frozen=True)
class XlsxParseResult:
    cells: tuple[ParsedXlsxCell, ...]
    source_sha256: str
    normalized_text: str
    content_sha256: str


def text_sha256(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def validate_xlsx_upload_payload(payload: bytes) -> None:
    validate_office_upload_payload(payload, expected_kind="xlsx")


def parse_xlsx_workbook(payload: bytes, *, mime_type: str = XLSX_MIME) -> XlsxParseResult:
    if mime_type != XLSX_MIME:
        raise OfficePackageError("asset_mime_mismatch", f"XLSX adapter only accepts {XLSX_MIME}.")
    inspect_office_package(payload, expected_kind="xlsx")
    shared = _shared_strings(payload)
    workbook = ElementTree.fromstring(read_zip_text(payload, "xl/workbook.xml"))
    sheets = workbook.find(f"{{{SS_NS}}}sheets")
    if sheets is None:
        raise OfficePackageError("office_parse_failed", "xl/workbook.xml is missing sheets.")
    cells: list[ParsedXlsxCell] = []
    lines: list[str] = []
    for order, sheet in enumerate(sheets.findall(f"{{{SS_NS}}}sheet")):
        name = sheet.attrib.get("name") or f"Sheet{order + 1}"
        part = f"xl/worksheets/sheet{order + 1}.xml"
        try:
            sheet_xml = read_zip_text(payload, part)
        except OfficePackageError:
            continue
        root = ElementTree.fromstring(sheet_xml)
        for cell in root.iter(f"{{{SS_NS}}}c"):
            ref = cell.attrib.get("r")
            if not ref:
                continue
            text = _cell_text(cell, shared)
            if not text:
                continue
            digest = text_sha256(text)
            cells.append(
                ParsedXlsxCell(
                    sheet_name=name,
                    sheet_order=order,
                    cell_ref=ref,
                    text=text,
                    text_sha256=digest,
                )
            )
            lines.append(f"{name}!{ref}={text}")
    if not cells:
        raise OfficePackageError("office_parse_failed", "XLSX produced no non-empty cells.")
    normalized = "\n".join(lines)
    return XlsxParseResult(
        cells=tuple(cells),
        source_sha256=sha256(payload).hexdigest(),
        normalized_text=normalized,
        content_sha256=text_sha256(normalized),
    )


def validate_xlsx_range(
    *,
    sheet_name: str,
    start_cell: str,
    end_cell: str,
    text_sha256_value: str,
    expected_text: str,
) -> None:
    if not sheet_name or not start_cell or not end_cell:
        raise XlsxIntegrityError("xlsx_range requires sheet_name and cell refs")
    if text_sha256_value != text_sha256(expected_text):
        raise XlsxIntegrityError("xlsx_range text_sha256 does not match displayed text")


def build_minimal_xlsx_bytes(
    *,
    cells: list[tuple[str, str, str]] | None = None,
    include_macro: bool = False,
    encrypted: bool = False,
) -> bytes:
    """cells: (sheet, ref, text)."""
    if encrypted:
        return write_ooxml_package(
            {
                CONTENT_TYPES_PART: _types_xml(),
                "EncryptedPackage": b"secret",
                "EncryptionInfo": b"info",
            }
        )
    items = cells or [("Sheet1", "A1", "Revenue"), ("Sheet1", "B1", "42")]
    shared = [text for _, _, text in items]
    shared_xml = (
        f'<sst xmlns="{SS_NS}" count="{len(shared)}" uniqueCount="{len(shared)}">'
        + "".join(f"<si><t>{_esc(text)}</t></si>" for text in shared)
        + "</sst>"
    )
    sheet_cells = []
    for index, (_sheet, ref, _text) in enumerate(items):
        sheet_cells.append(f'<c r="{ref}" t="s"><v>{index}</v></c>')
    sheet_xml = (
        f'<worksheet xmlns="{SS_NS}"><sheetData><row r="1">'
        + "".join(sheet_cells)
        + "</row></sheetData></worksheet>"
    )
    workbook = (
        f'<workbook xmlns="{SS_NS}"><sheets>'
        '<sheet name="Sheet1" sheetId="1" r:id="rId1" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
        "</sheets></workbook>"
    )
    parts: dict[str, bytes | str] = {
        CONTENT_TYPES_PART: _types_xml(include_macro=include_macro),
        "xl/workbook.xml": workbook,
        "xl/sharedStrings.xml": shared_xml,
        "xl/worksheets/sheet1.xml": sheet_xml,
    }
    if include_macro:
        parts["xl/vbaProject.bin"] = b"macro"
    return write_ooxml_package(parts)


def _types_xml(*, include_macro: bool = False) -> str:
    extra = ""
    if include_macro:
        extra = (
            '<Override PartName="/xl/vbaProject.bin" '
            'ContentType="application/vnd.ms-office.vbaProject"/>'
        )
    return (
        f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        f'<Override PartName="/xl/workbook.xml" ContentType="{EXCEL_MAIN_CONTENT_TYPE}"/>'
        f"{extra}</Types>"
    )


def _shared_strings(payload: bytes) -> list[str]:
    try:
        xml = read_zip_text(payload, "xl/sharedStrings.xml")
    except OfficePackageError:
        return []
    root = ElementTree.fromstring(xml)
    values: list[str] = []
    for si in root.findall(f"{{{SS_NS}}}si"):
        texts = [node.text or "" for node in si.iter(f"{{{SS_NS}}}t")]
        values.append("".join(texts))
    return values


def _cell_text(cell: ElementTree.Element, shared: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    value = cell.find(f"{{{SS_NS}}}v")
    if cell_type == "inlineStr":
        is_node = cell.find(f"{{{SS_NS}}}is")
        if is_node is None:
            return ""
        return "".join(node.text or "" for node in is_node.iter(f"{{{SS_NS}}}t")).strip()
    if value is None or value.text is None:
        return ""
    raw = value.text
    if cell_type == "s":
        try:
            return shared[int(raw)].strip()
        except (ValueError, IndexError):
            return ""
    return raw.strip()


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
