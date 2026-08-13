"""Shared OOXML package inspection for Office kinds.

Owns ZIP/OLE signature checks, encrypted-package detection, and macro
part detection. No modality-specific parse or registry enablement.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree

OLECF_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_LOCAL_SIGNATURE = b"PK\x03\x04"
ZIP_EMPTY_SIGNATURE = b"PK\x05\x06"
CONTENT_TYPES_PART = "[Content_Types].xml"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

WORD_MAIN_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
EXCEL_MAIN_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
)
PPT_MAIN_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"
)
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

_MACRO_CONTENT_MARKERS = (
    "vnd.ms-office.vbaProject",
    "vnd.ms-word.document.macroEnabled",
    "vnd.ms-excel.sheet.macroEnabled",
    "vnd.ms-powerpoint.presentation.macroEnabled",
    "macroEnabled.main+xml",
)
_MACRO_PART_MARKERS = (
    "vbaproject.bin",
    "vbaData.xml",
    "vbaProject.bin",
)
_ENCRYPTED_PARTS = frozenset({"encryptedpackage", "encryptioninfo"})


class OfficePackageError(ValueError):
    """Fail-closed OOXML package error with a stable ingestion code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class OfficePackage:
    names: frozenset[str]
    content_types: tuple[str, ...]
    kind: str
    declared_mime: str


def looks_like_zip(payload: bytes) -> bool:
    return payload.startswith(ZIP_LOCAL_SIGNATURE) or payload.startswith(ZIP_EMPTY_SIGNATURE)


def looks_like_olecf(payload: bytes) -> bool:
    return payload.startswith(OLECF_SIGNATURE)


def inspect_office_package(payload: bytes, *, expected_kind: str) -> OfficePackage:
    if not payload:
        raise OfficePackageError("asset_bytes_invalid", "Office package is empty.")
    if looks_like_olecf(payload):
        raise OfficePackageError(
            "office_encrypted_unsupported",
            "Encrypted or OLE-compound Office files are rejected.",
        )
    if not looks_like_zip(payload):
        raise OfficePackageError(
            "asset_bytes_invalid",
            "Office package is not a ZIP/OOXML container.",
        )
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as error:
        raise OfficePackageError(
            "asset_bytes_invalid",
            "Office package ZIP header is invalid.",
        ) from error
    with archive:
        names = frozenset(archive.namelist())
        lowered = {name.lower() for name in names}
        if any(part in lowered for part in _ENCRYPTED_PARTS):
            raise OfficePackageError(
                "office_encrypted_unsupported",
                "Encrypted OOXML packages are rejected.",
            )
        if any(marker.lower() in name for name in lowered for marker in _MACRO_PART_MARKERS):
            raise OfficePackageError(
                "office_macros_unsupported",
                "Office packages that contain macros are rejected.",
            )
        content_types = _read_content_types(archive)
        joined = " ".join(content_types)
        if any(marker.lower() in joined.lower() for marker in _MACRO_CONTENT_MARKERS):
            raise OfficePackageError(
                "office_macros_unsupported",
                "Office packages that declare macro-enabled content types are rejected.",
            )
        kind, mime = _classify_package(content_types, names)
        if kind != expected_kind:
            raise OfficePackageError(
                "asset_bytes_invalid",
                f"OOXML package kind is {kind}, expected {expected_kind}.",
            )
        return OfficePackage(
            names=names,
            content_types=content_types,
            kind=kind,
            declared_mime=mime,
        )


def read_zip_text(payload: bytes, part_name: str) -> str:
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as error:
        raise OfficePackageError(
            "asset_bytes_invalid",
            "Office package ZIP header is invalid.",
        ) from error
    with archive:
        try:
            data = archive.read(part_name)
        except KeyError as error:
            raise OfficePackageError(
                "office_parse_failed",
                f"Office package is missing required part {part_name}.",
            ) from error
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise OfficePackageError(
            "office_parse_failed",
            f"Office part {part_name} is not valid UTF-8.",
        ) from error


def detect_docx_mime_type(header: bytes) -> str | None:
    return DOCX_MIME if looks_like_zip(header) else None


def detect_xlsx_mime_type(header: bytes) -> str | None:
    return XLSX_MIME if looks_like_zip(header) else None


def detect_pptx_mime_type(header: bytes) -> str | None:
    return PPTX_MIME if looks_like_zip(header) else None


def validate_office_upload_payload(payload: bytes, *, expected_kind: str) -> None:
    inspect_office_package(payload, expected_kind=expected_kind)


def write_ooxml_package(parts: dict[str, bytes | str]) -> bytes:
    """Test/fixture helper: write a minimal OOXML ZIP."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in parts.items():
            payload = body.encode("utf-8") if isinstance(body, str) else body
            archive.writestr(name, payload)
    return buffer.getvalue()


def _read_content_types(archive: zipfile.ZipFile) -> tuple[str, ...]:
    try:
        raw = archive.read(CONTENT_TYPES_PART)
    except KeyError as error:
        raise OfficePackageError(
            "office_parse_failed",
            "Office package is missing [Content_Types].xml.",
        ) from error
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as error:
        raise OfficePackageError(
            "office_parse_failed",
            "Office [Content_Types].xml is not well-formed XML.",
        ) from error
    types: list[str] = []
    for element in root.iter():
        content_type = element.attrib.get("ContentType")
        if content_type:
            types.append(content_type)
    if not types:
        raise OfficePackageError(
            "office_parse_failed",
            "Office [Content_Types].xml declares no content types.",
        )
    return tuple(types)


def _classify_package(
    content_types: tuple[str, ...], names: frozenset[str]
) -> tuple[str, str]:
    joined = " ".join(content_types)
    if WORD_MAIN_CONTENT_TYPE in joined or "word/document.xml" in names:
        return "docx", DOCX_MIME
    if EXCEL_MAIN_CONTENT_TYPE in joined or "xl/workbook.xml" in names:
        return "xlsx", XLSX_MIME
    if PPT_MAIN_CONTENT_TYPE in joined or "ppt/presentation.xml" in names:
        return "pptx", PPTX_MIME
    raise OfficePackageError(
        "asset_bytes_invalid",
        "OOXML package does not declare a supported Word/Excel/PowerPoint main part.",
    )
