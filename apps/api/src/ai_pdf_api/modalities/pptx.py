"""PPTX modality helpers: slide/shape text, geometry, and locators."""

from __future__ import annotations

import base64
import json
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
    read_zip_bytes,
    read_zip_text,
    validate_office_upload_payload,
    write_ooxml_package,
)

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

# Default 16:9 slide when sldSz is absent (EMU).
DEFAULT_SLIDE_CX_EMU = 12192000
DEFAULT_SLIDE_CY_EMU = 6858000

PPTX_PARSER_VERSION = "pptx-parser-v1"
PPTX_NORMALIZATION_VERSION = "pptx-normalization-v1"
# Structured layout payload stored as normalized object (additive).
PPTX_LAYOUT_VERSION = "pptx-layout-v1"

__all__ = [
    "DEFAULT_SLIDE_CX_EMU",
    "DEFAULT_SLIDE_CY_EMU",
    "PPTX_LAYOUT_VERSION",
    "PPTX_MIME",
    "PPTX_NORMALIZATION_VERSION",
    "PPTX_PARSER_VERSION",
    "ParsedPptxShape",
    "PptxIntegrityError",
    "PptxParseResult",
    "build_minimal_pptx_bytes",
    "detect_pptx_mime_type",
    "parse_pptx_layout_payload",
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
    shape_kind: str = "text"  # text | picture | shape
    x_emu: int | None = None
    y_emu: int | None = None
    cx_emu: int | None = None
    cy_emu: int | None = None
    media_part: str | None = None
    media_content_type: str | None = None

    def has_geometry(self) -> bool:
        return (
            self.x_emu is not None
            and self.y_emu is not None
            and self.cx_emu is not None
            and self.cy_emu is not None
        )


@dataclass(frozen=True)
class PptxParseResult:
    shapes: tuple[ParsedPptxShape, ...]
    source_sha256: str
    normalized_text: str
    content_sha256: str
    slide_width_emu: int = DEFAULT_SLIDE_CX_EMU
    slide_height_emu: int = DEFAULT_SLIDE_CY_EMU
    layout_payload: bytes = b""
    # Digest of normalized text lines (locator text contract). Distinct from
    # content_sha256 when the stored object is layout JSON (payload byte hash).
    text_content_sha256: str = ""

    def layout_dict(self) -> dict:
        slides: dict[int, list[dict]] = {}
        for shape in self.shapes:
            slides.setdefault(shape.slide_index, []).append(
                {
                    "shapeId": shape.shape_id,
                    "shapeKind": shape.shape_kind,
                    "text": shape.text,
                    "textSha256": shape.text_sha256,
                    "xEmu": shape.x_emu,
                    "yEmu": shape.y_emu,
                    "cxEmu": shape.cx_emu,
                    "cyEmu": shape.cy_emu,
                    "mediaPart": shape.media_part,
                    "mediaContentType": shape.media_content_type,
                }
            )
        text_digest = self.text_content_sha256 or text_sha256(self.normalized_text)
        return {
            "layoutVersion": PPTX_LAYOUT_VERSION,
            "normalizationVersion": PPTX_NORMALIZATION_VERSION,
            "parserVersion": PPTX_PARSER_VERSION,
            "slideWidthEmu": self.slide_width_emu,
            "slideHeightEmu": self.slide_height_emu,
            "normalizedText": self.normalized_text,
            "textContentSha256": text_digest,
            "slides": [
                {"slideIndex": index, "shapes": slides[index]}
                for index in sorted(slides)
            ],
        }


def text_sha256(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def validate_pptx_upload_payload(payload: bytes) -> None:
    validate_office_upload_payload(payload, expected_kind="pptx")


def _int_attr(element: ElementTree.Element | None, name: str) -> int | None:
    if element is None:
        return None
    raw = element.attrib.get(name)
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _xfrm_box(parent: ElementTree.Element) -> tuple[int | None, int | None, int | None, int | None]:
    """Read a:xfrm off/ext under spPr or pic spPr (EMU)."""
    xfrm = parent.find(f".//{{{A_NS}}}xfrm")
    if xfrm is None:
        return None, None, None, None
    off = xfrm.find(f"{{{A_NS}}}off")
    ext = xfrm.find(f"{{{A_NS}}}ext")
    return (
        _int_attr(off, "x"),
        _int_attr(off, "y"),
        _int_attr(ext, "cx"),
        _int_attr(ext, "cy"),
    )


def _slide_rel_map(payload: bytes, slide_index: int) -> dict[str, str]:
    """Map rId -> target part path relative to package root (normalized under ppt/)."""
    import posixpath

    rel_part = f"ppt/slides/_rels/slide{slide_index}.xml.rels"
    try:
        rel_xml = read_zip_text(payload, rel_part)
    except OfficePackageError:
        return {}
    root = ElementTree.fromstring(rel_xml)
    mapping: dict[str, str] = {}
    for rel in root:
        if not rel.tag.endswith("Relationship"):
            continue
        rid = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        if not rid or not target:
            continue
        if target.startswith("/"):
            part = target.lstrip("/")
        else:
            part = posixpath.normpath(f"ppt/slides/{target}")
        if ".." in part.split("/"):
            continue
        if not part.startswith("ppt/"):
            continue
        mapping[rid] = part
    return mapping


def guess_pptx_media_content_type(part: str) -> str:
    lower = part.lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return "image/jpeg"
    if lower.endswith(".gif"):
        return "image/gif"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".emf"):
        return "image/emf"
    if lower.endswith(".wmf"):
        return "image/wmf"
    return "application/octet-stream"


def _presentation_slide_size(presentation: ElementTree.Element) -> tuple[int, int]:
    sld_sz = presentation.find(f"{{{P_NS}}}sldSz")
    if sld_sz is None:
        return DEFAULT_SLIDE_CX_EMU, DEFAULT_SLIDE_CY_EMU
    cx = _int_attr(sld_sz, "cx") or DEFAULT_SLIDE_CX_EMU
    cy = _int_attr(sld_sz, "cy") or DEFAULT_SLIDE_CY_EMU
    return cx, cy


def parse_pptx_presentation(payload: bytes, *, mime_type: str = PPTX_MIME) -> PptxParseResult:
    if mime_type != PPTX_MIME:
        raise OfficePackageError("asset_mime_mismatch", f"PPTX adapter only accepts {PPTX_MIME}.")
    inspect_office_package(payload, expected_kind="pptx")
    presentation = ElementTree.fromstring(read_zip_text(payload, "ppt/presentation.xml"))
    slide_width, slide_height = _presentation_slide_size(presentation)
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
        rels = _slide_rel_map(payload, index)

        for shape in root.iter(f"{{{P_NS}}}sp"):
            cnv = shape.find(f"{{{P_NS}}}nvSpPr/{{{P_NS}}}cNvPr")
            shape_id = "1"
            if cnv is not None:
                shape_id = cnv.attrib.get("id") or cnv.attrib.get("name") or "1"
            texts = [node.text or "" for node in shape.iter(f"{{{A_NS}}}t")]
            text = " ".join(part.strip() for part in texts if part and part.strip())
            x, y, cx, cy = _xfrm_box(shape)
            if not text and not (x is not None and y is not None):
                continue
            digest = text_sha256(text) if text else text_sha256("")
            shapes.append(
                ParsedPptxShape(
                    slide_index=index,
                    shape_id=str(shape_id),
                    text=text,
                    text_sha256=digest,
                    shape_kind="text" if text else "shape",
                    x_emu=x,
                    y_emu=y,
                    cx_emu=cx,
                    cy_emu=cy,
                )
            )
            if text:
                lines.append(f"slide{index}#{shape_id}={text}")

        for pic in root.iter(f"{{{P_NS}}}pic"):
            cnv = pic.find(f"{{{P_NS}}}nvPicPr/{{{P_NS}}}cNvPr")
            shape_id = "pic"
            if cnv is not None:
                shape_id = cnv.attrib.get("id") or cnv.attrib.get("name") or "pic"
            x, y, cx, cy = _xfrm_box(pic)
            blip = pic.find(f".//{{{A_NS}}}blip")
            media_part = None
            media_ct = None
            if blip is not None:
                rid = blip.attrib.get(f"{{{R_NS}}}embed") or blip.attrib.get("r:embed")
                if rid and rid in rels:
                    media_part = rels[rid]
                    media_ct = guess_pptx_media_content_type(media_part)
            name_hint = ""
            if cnv is not None:
                name_hint = (cnv.attrib.get("name") or "").strip()
            # Include pictures even without text so layout/canvas can show them.
            digest = text_sha256(name_hint or media_part or str(shape_id))
            shapes.append(
                ParsedPptxShape(
                    slide_index=index,
                    shape_id=str(shape_id),
                    text=name_hint,
                    text_sha256=digest,
                    shape_kind="picture",
                    x_emu=x,
                    y_emu=y,
                    cx_emu=cx,
                    cy_emu=cy,
                    media_part=media_part,
                    media_content_type=media_ct,
                )
            )
            if name_hint:
                lines.append(f"slide{index}#{shape_id}={name_hint}")

    text_shapes = [s for s in shapes if s.text]
    if not text_shapes and not shapes:
        raise OfficePackageError("office_parse_failed", "PPTX produced no non-empty shapes.")
    # Content units still require text; pictures-only decks keep layout but need at least one unit.
    if not text_shapes:
        # Synthesize a placeholder line so ingestion can create a content unit.
        first = shapes[0]
        placeholder = f"[slide {first.slide_index} visual]"
        lines.append(f"slide{first.slide_index}#{first.shape_id}={placeholder}")
        shapes = [
            ParsedPptxShape(
                slide_index=first.slide_index,
                shape_id=first.shape_id,
                text=placeholder,
                text_sha256=text_sha256(placeholder),
                shape_kind=first.shape_kind,
                x_emu=first.x_emu,
                y_emu=first.y_emu,
                cx_emu=first.cx_emu,
                cy_emu=first.cy_emu,
                media_part=first.media_part,
                media_content_type=first.media_content_type,
            ),
            *shapes[1:],
        ]
    normalized = "\n".join(lines)
    text_digest = text_sha256(normalized)
    # GeneratedObject integrity requires content_sha256 == sha256(payload bytes).
    # Text digest lives in layout JSON as textContentSha256.
    draft = PptxParseResult(
        shapes=tuple(shapes),
        source_sha256=sha256(payload).hexdigest(),
        normalized_text=normalized,
        content_sha256=text_digest,
        slide_width_emu=slide_width,
        slide_height_emu=slide_height,
        text_content_sha256=text_digest,
    )
    layout_bytes = json.dumps(draft.layout_dict(), ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return PptxParseResult(
        shapes=draft.shapes,
        source_sha256=draft.source_sha256,
        normalized_text=draft.normalized_text,
        content_sha256=sha256(layout_bytes).hexdigest(),
        slide_width_emu=draft.slide_width_emu,
        slide_height_emu=draft.slide_height_emu,
        layout_payload=layout_bytes,
        text_content_sha256=text_digest,
    )



def parse_pptx_layout_payload(payload: bytes) -> dict | None:
    """Parse stored normalized object: layout JSON or legacy plain text lines."""
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return None
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(body, dict):
            return None
        if body.get("layoutVersion") != PPTX_LAYOUT_VERSION:
            # Still accept if it has slides + normalizedText
            if "normalizedText" not in body and "slides" not in body:
                return None
        return body
    # Legacy plain text
    return {
        "layoutVersion": "pptx-layout-legacy-text",
        "normalizationVersion": PPTX_NORMALIZATION_VERSION,
        "parserVersion": PPTX_PARSER_VERSION,
        "slideWidthEmu": DEFAULT_SLIDE_CX_EMU,
        "slideHeightEmu": DEFAULT_SLIDE_CY_EMU,
        "normalizedText": text,
        "slides": None,
    }


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
    with_geometry: bool = False,
    with_picture: bool = False,
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
    shape_xml_parts: list[str] = []
    for order, (_slide, shape_id, text) in enumerate(items):
        xfrm = ""
        if with_geometry:
            x = 914400 + order * 200000
            y = 914400 + order * 400000
            cx = 5486400
            cy = 914400
            xfrm = (
                f"<p:spPr><a:xfrm>"
                f'<a:off x="{x}" y="{y}"/>'
                f'<a:ext cx="{cx}" cy="{cy}"/>'
                f"</a:xfrm></p:spPr>"
            )
        else:
            xfrm = "<p:spPr/>"
        shape_xml_parts.append(
            f'<p:sp><p:nvSpPr><p:cNvPr id="{_esc(shape_id)}" name="Title {_esc(shape_id)}"/>'
            f"</p:nvSpPr>{xfrm}<p:txBody><a:p><a:r>"
            f"<a:t>{_esc(text)}</a:t></a:r></a:p></p:txBody></p:sp>"
        )
    pic_xml = ""
    rels_xml = ""
    media_parts: dict[str, bytes | str] = {}
    if with_picture:
        # 1x1 PNG
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        media_parts["ppt/media/image1.png"] = png
        pic_xml = (
            f'<p:pic><p:nvPicPr><p:cNvPr id="99" name="Photo"/>'
            f"</p:nvPicPr><p:blipFill><a:blip r:embed=\"rIdImage\" "
            f'xmlns:r="{R_NS}"/></p:blipFill>'
            f"<p:spPr><a:xfrm>"
            f'<a:off x="1000000" y="2000000"/>'
            f'<a:ext cx="3000000" cy="2000000"/>'
            f"</a:xfrm></p:spPr></p:pic>"
        )
        rels_xml = (
            f'<Relationships xmlns="{REL_NS}">'
            f'<Relationship Id="rIdImage" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
            f'Target="../media/image1.png"/>'
            f"</Relationships>"
        )
    slide_xml = (
        f'<p:sld xmlns:p="{P_NS}" xmlns:a="{A_NS}" xmlns:r="{R_NS}">'
        "<p:cSld><p:spTree>"
        + "".join(shape_xml_parts)
        + pic_xml
        + "</p:spTree></p:cSld></p:sld>"
    )
    presentation = (
        f'<p:presentation xmlns:p="{P_NS}">'
        f'<p:sldSz cx="{DEFAULT_SLIDE_CX_EMU}" cy="{DEFAULT_SLIDE_CY_EMU}"/>'
        "<p:sldIdLst><p:sldId id=\"256\" r:id=\"rId2\" "
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
        "</p:sldIdLst></p:presentation>"
    )
    parts: dict[str, bytes | str] = {
        CONTENT_TYPES_PART: _types_xml(include_macro=include_macro),
        "ppt/presentation.xml": presentation,
        "ppt/slides/slide1.xml": slide_xml,
        **media_parts,
    }
    if rels_xml:
        parts["ppt/slides/_rels/slide1.xml.rels"] = rels_xml
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
