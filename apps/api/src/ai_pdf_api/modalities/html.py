"""HTML modality helpers: sanitizer policy, stable blocks, locator validation.

OD-B5 policy is implemented here. Viewer and persistence must consume sanitized
output only. Script execution is never enabled.
"""

from __future__ import annotations

import html
import re
from hashlib import sha256
from html.parser import HTMLParser
from typing import Iterable, Protocol
from urllib.parse import urlparse

HTML_FORMAT = "html"
HTML_PARSER_VERSION = "html-parser-v1"
HTML_NORMALIZATION_VERSION = "html-normalization-v1"
HTML_SANITIZER_VERSION = "html-sanitizer-v1"
HTML_MIME_TYPES = frozenset({"text/html", "application/xhtml+xml"})

HTML_BLOCK_KINDS = frozenset(
    {"heading", "paragraph", "list_item", "code_block", "quote", "table"}
)
HTML_HEADING_LEVELS = frozenset({1, 2, 3, 4, 5, 6})

# OD-B5 allowlist. Anything else is dropped, including script/style/iframe.
ALLOWED_TAGS = frozenset(
    {
        "a",
        "b",
        "blockquote",
        "br",
        "code",
        "div",
        "em",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "i",
        "img",
        "li",
        "ol",
        "p",
        "pre",
        "span",
        "strong",
        "table",
        "tbody",
        "td",
        "th",
        "thead",
        "tr",
        "ul",
    }
)
VOID_TAGS = frozenset({"br", "hr", "img"})
ALLOWED_ATTRS = {
    "a": frozenset({"href", "title"}),
    "img": frozenset({"src", "alt"}),
    "td": frozenset({"colspan", "rowspan"}),
    "th": frozenset({"colspan", "rowspan"}),
}
SAFE_HREF_SCHEMES = frozenset({"http", "https", "mailto"})
SAFE_DATA_IMAGE = re.compile(r"^data:image/(png|jpeg|jpg|gif|webp);base64,[a-z0-9+/=\s]+$", re.I)
EVENT_ATTR = re.compile(r"^on", re.I)
_HEADING_TAG = re.compile(r"^h([1-6])$")
_WHITESPACE_RUN = re.compile(r"[ \t]+")


class HtmlIntegrityError(ValueError):
    """Raised when persisted HTML normalized content or blocks are corrupt."""


class HtmlNormalizedLike(Protocol):
    format: str
    parser_version: str
    normalization_version: str
    sanitizer_version: str
    normalized_text: str
    sanitized_html: str
    content_sha256: str
    block_count: int


class HtmlBlockLike(Protocol):
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
    css_path_hint: str | None


def text_sha256(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def validate_heading_path(heading_path: object) -> list[str]:
    if not isinstance(heading_path, list):
        raise ValueError("heading_path must be a list of strings")
    if any(not isinstance(part, str) or not part for part in heading_path):
        raise ValueError("heading_path must be an ordered array of non-empty strings")
    return list(heading_path)


def validate_heading_level(*, block_kind: str, heading_level: int | None) -> int | None:
    if block_kind == "heading":
        if heading_level not in HTML_HEADING_LEVELS:
            raise ValueError("heading blocks require heading_level in 1..6")
        return heading_level
    if heading_level is not None:
        raise ValueError("non-heading HTML blocks must not set heading_level")
    return None


def validate_hex_sha256(value: object, *, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise HtmlIntegrityError(f"html requires a lowercase hex SHA-256 {field_name}")
    return value


def validate_css_path_hint(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 512:
        raise HtmlIntegrityError("html css_path_hint must be a non-empty string <= 512 chars")
    if any(ch in value for ch in ("\x00", "<", ">")):
        raise HtmlIntegrityError("html css_path_hint contains forbidden characters")
    return value


def stable_html_block_id(
    *,
    source_sha256: str,
    parser_version: str,
    sanitizer_version: str,
    block_order: int,
    block_kind: str,
    heading_path: Iterable[str],
    text_sha256_value: str,
) -> str:
    if parser_version != HTML_PARSER_VERSION:
        raise ValueError(f"Unsupported HTML parser version: {parser_version}")
    if sanitizer_version != HTML_SANITIZER_VERSION:
        raise ValueError(f"Unsupported HTML sanitizer version: {sanitizer_version}")
    if block_kind not in HTML_BLOCK_KINDS:
        raise ValueError(f"Unsupported HTML block_kind: {block_kind}")
    if block_order < 0:
        raise ValueError("block_order must be non-negative")
    path = validate_heading_path(list(heading_path))
    material = "\n".join(
        [
            source_sha256,
            parser_version,
            sanitizer_version,
            str(block_order),
            block_kind,
            "/".join(path),
            text_sha256_value,
        ]
    )
    digest = sha256(material.encode("utf-8")).hexdigest()
    return f"htmlblk_{digest[:32]}"


def _looks_like_foreign_binary(payload: bytes) -> bool:
    if not payload:
        return True
    if payload.startswith(b"%PDF-"):
        return True
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if payload.startswith(b"\xff\xd8\xff"):
        return True
    if len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return True
    if payload.startswith(b"PK\x03\x04") or payload.startswith(b"PK\x05\x06"):
        return True
    if payload.startswith(b"\x7fELF"):
        return True
    if b"\x00" in payload:
        return True
    return False


def detect_html_mime_type(header: bytes) -> str | None:
    if not header or _looks_like_foreign_binary(header):
        return None
    sample = header[:4096].lstrip().lower()
    if sample.startswith(b"<!doctype html") or sample.startswith(b"<html"):
        return "text/html"
    if b"<html" in sample or b"<p" in sample or b"<div" in sample or b"<h1" in sample:
        return "text/html"
    return None


def validate_html_upload_payload(payload: bytes) -> None:
    if not payload:
        raise ValueError("HTML upload body is empty")
    if _looks_like_foreign_binary(payload):
        raise ValueError("File signature does not match declared MIME type: text/html")
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("HTML upload must be valid UTF-8 text") from error


def _safe_href(value: str) -> str | None:
    raw = value.strip()
    if not raw or raw.startswith("#"):
        return raw or None
    lowered = raw.lower()
    if lowered.startswith("javascript:") or lowered.startswith("vbscript:") or lowered.startswith("data:"):
        return None
    parsed = urlparse(raw)
    if parsed.scheme:
        if parsed.scheme.lower() not in SAFE_HREF_SCHEMES:
            return None
        return raw
    if raw.startswith("//"):
        return None
    return raw


def _safe_img_src(value: str) -> str | None:
    raw = value.strip()
    if not raw:
        return None
    lowered = raw.lower()
    if lowered.startswith("javascript:") or lowered.startswith("vbscript:"):
        return None
    if lowered.startswith("data:"):
        compact = re.sub(r"\s+", "", raw)
        if SAFE_DATA_IMAGE.match(compact):
            return compact
        return None
    parsed = urlparse(raw)
    if parsed.scheme or raw.startswith("//"):
        return None
    if ".." in raw.split("/"):
        return None
    return raw


def _sanitize_attr(tag: str, name: str, value: str | None) -> tuple[str, str] | None:
    if value is None or EVENT_ATTR.match(name) or name.lower() in {"style", "srcset", "srcdoc"}:
        return None
    allowed = ALLOWED_ATTRS.get(tag, frozenset())
    if name.lower() not in allowed:
        return None
    if tag == "a" and name.lower() == "href":
        href = _safe_href(value)
        return ("href", href) if href else None
    if tag == "img" and name.lower() == "src":
        src = _safe_img_src(value)
        return ("src", src) if src else None
    if name.lower() in {"colspan", "rowspan"}:
        if value.isdigit() and 1 <= int(value) <= 100:
            return (name.lower(), value)
        return None
    cleaned = html.escape(value, quote=True)
    return (name.lower(), cleaned)


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "iframe", "object", "embed", "form", "input", "textarea", "svg", "math", "link", "meta", "base"}:
            self._skip += 1
            return
        if self._skip or tag not in ALLOWED_TAGS:
            return
        safe_attrs: list[str] = []
        for name, value in attrs:
            item = _sanitize_attr(tag, name, value)
            if item is None:
                continue
            safe_attrs.append(f'{item[0]}="{html.escape(item[1], quote=True)}"')
        attr_text = (" " + " ".join(safe_attrs)) if safe_attrs else ""
        if tag in VOID_TAGS:
            self.parts.append(f"<{tag}{attr_text}>")
            return
        self.parts.append(f"<{tag}{attr_text}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "iframe", "object", "embed", "form", "input", "textarea", "svg", "math", "link", "meta", "base"}:
            if self._skip:
                self._skip -= 1
            return
        if self._skip or tag not in ALLOWED_TAGS or tag in VOID_TAGS:
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        self.parts.append(html.escape(data, quote=False))

    def handle_comment(self, _data: str) -> None:
        return

    def handle_pi(self, _data: str) -> None:
        return

    def handle_decl(self, _decl: str) -> None:
        return

    def unknown_decl(self, _data: str) -> None:
        return


def sanitize_html(source: str) -> str:
    """Return allowlisted static HTML. Never emits script or event handlers."""
    parser = _Sanitizer()
    parser.feed(source)
    parser.close()
    return "".join(parser.parts)


class _BlockExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, int | None, list[str], str, str | None]] = []
        self._heading_stack: list[tuple[int, str]] = []
        self._text_stack: list[list[str]] = []
        self._kind_stack: list[str] = []
        self._path_index: list[int] = []
        self._in_pre = 0
        self._in_table = 0
        self._table_cells: list[str] = []
        self._cell_parts: list[str] = []
        self._in_cell = False

    def _heading_path(self) -> list[str]:
        return [title for _level, title in self._heading_stack]

    def _open_text(self, kind: str) -> None:
        self._kind_stack.append(kind)
        self._text_stack.append([])

    def _close_text(self, kind: str, heading_level: int | None = None) -> None:
        if not self._kind_stack or self._kind_stack[-1] != kind:
            return
        self._kind_stack.pop()
        text = _normalize_block_text("".join(self._text_stack.pop()), preserve_newlines=kind == "code_block")
        if not text:
            return
        path = self._heading_path()
        hint = f"{kind}:{len(self.blocks)}"
        if kind == "heading" and heading_level is not None:
            self._heading_stack = [item for item in self._heading_stack if item[0] < heading_level]
            self._heading_stack.append((heading_level, text))
            path = self._heading_path()[:-1]
        self.blocks.append((kind, heading_level, path, text, hint))

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        heading = _HEADING_TAG.match(tag)
        if heading:
            self._open_text("heading")
            return
        if tag == "p":
            self._open_text("paragraph")
            return
        if tag == "li":
            self._open_text("list_item")
            return
        if tag == "blockquote":
            self._open_text("quote")
            return
        if tag == "pre":
            self._in_pre += 1
            self._open_text("code_block")
            return
        if tag == "table":
            self._in_table += 1
            self._table_cells = []
            return
        if tag in {"td", "th"} and self._in_table:
            self._in_cell = True
            self._cell_parts = []
            return

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        heading = _HEADING_TAG.match(tag)
        if heading:
            self._close_text("heading", heading_level=int(heading.group(1)))
            return
        if tag == "p":
            self._close_text("paragraph")
            return
        if tag == "li":
            self._close_text("list_item")
            return
        if tag == "blockquote":
            self._close_text("quote")
            return
        if tag == "pre":
            if self._in_pre:
                self._in_pre -= 1
            self._close_text("code_block")
            return
        if tag in {"td", "th"} and self._in_table:
            cell = _normalize_block_text("".join(self._cell_parts), preserve_newlines=False)
            if cell:
                self._table_cells.append(cell)
            self._in_cell = False
            self._cell_parts = []
            return
        if tag == "table" and self._in_table:
            self._in_table -= 1
            text = " | ".join(self._table_cells)
            text = _normalize_block_text(text, preserve_newlines=False)
            if text:
                self.blocks.append(("table", None, self._heading_path(), text, f"table:{len(self.blocks)}"))
            self._table_cells = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_parts.append(data)
            return
        if self._text_stack:
            self._text_stack[-1].append(data)


def _normalize_block_text(text: str, *, preserve_newlines: bool) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if preserve_newlines:
        lines = [_WHITESPACE_RUN.sub(" ", line).rstrip() for line in text.split("\n")]
        return "\n".join(lines).strip()
    collapsed = _WHITESPACE_RUN.sub(" ", text.replace("\n", " "))
    return collapsed.strip()


def extract_html_blocks(sanitized_html: str) -> list[tuple[str, int | None, list[str], str, str | None]]:
    extractor = _BlockExtractor()
    extractor.feed(sanitized_html)
    extractor.close()
    if extractor.blocks:
        return extractor.blocks
    fallback = _normalize_block_text(
        re.sub(r"<[^>]+>", " ", sanitized_html),
        preserve_newlines=False,
    )
    if not fallback:
        return []
    return [("paragraph", None, [], fallback, "paragraph:0")]


def validate_html_normalized_content(normalized: HtmlNormalizedLike) -> str:
    if normalized.format != HTML_FORMAT:
        raise HtmlIntegrityError("html normalized content format is invalid")
    if normalized.parser_version != HTML_PARSER_VERSION:
        raise HtmlIntegrityError("html normalized content parser_version is invalid")
    if normalized.normalization_version != HTML_NORMALIZATION_VERSION:
        raise HtmlIntegrityError("html normalized content normalization_version is invalid")
    if getattr(normalized, "sanitizer_version", None) != HTML_SANITIZER_VERSION:
        raise HtmlIntegrityError("html normalized content sanitizer_version is invalid")
    if not isinstance(normalized.normalized_text, str):
        raise HtmlIntegrityError("html normalized_text is invalid")
    if not isinstance(normalized.sanitized_html, str):
        raise HtmlIntegrityError("html sanitized_html is invalid")
    if _contains_active_html(normalized.sanitized_html):
        raise HtmlIntegrityError("html sanitized_html contains forbidden active content")
    if normalized.block_count < 0:
        raise HtmlIntegrityError("html block_count is invalid")
    content_digest = validate_hex_sha256(normalized.content_sha256, field_name="content_sha256")
    if text_sha256(normalized.normalized_text) != content_digest:
        raise HtmlIntegrityError("html content_sha256 does not match normalized_text")
    return normalized.normalized_text


def _contains_active_html(sanitized: str) -> bool:
    lowered = sanitized.lower()
    if "<script" in lowered or "</script" in lowered:
        return True
    if "<style" in lowered or "javascript:" in lowered:
        return True
    if re.search(r"\son[a-z]+\s*=", lowered):
        return True
    return False


def validate_html_block_against_text(block: HtmlBlockLike, *, normalized_text: str) -> list[str]:
    if not block.block_id:
        raise HtmlIntegrityError("html block requires a stable block_id")
    if block.block_kind not in HTML_BLOCK_KINDS:
        raise HtmlIntegrityError("html block_kind is unsupported")
    if block.normalization_version != HTML_NORMALIZATION_VERSION:
        raise HtmlIntegrityError("html block normalization_version is invalid")
    if block.block_order < 0:
        raise HtmlIntegrityError("html block_order is invalid")
    try:
        heading_path = validate_heading_path(block.heading_path)
        validate_heading_level(block_kind=block.block_kind, heading_level=block.heading_level)
        validate_css_path_hint(block.css_path_hint)
    except ValueError as error:
        raise HtmlIntegrityError(str(error)) from error
    if block.char_start < 0 or block.char_end <= block.char_start:
        raise HtmlIntegrityError("html block range is invalid")
    if block.char_end > len(normalized_text):
        raise HtmlIntegrityError("html block range exceeds normalized document length")
    expected_text = normalized_text[block.char_start : block.char_end]
    if not isinstance(block.text_content, str) or not block.text_content:
        raise HtmlIntegrityError("html block text_content is invalid")
    if block.text_content != expected_text:
        raise HtmlIntegrityError("html block text_content does not match normalized substring")
    digest = validate_hex_sha256(block.text_sha256, field_name="text_sha256")
    if digest != text_sha256(block.text_content):
        raise HtmlIntegrityError("html block text_sha256 does not match block text_content")
    return heading_path


def validate_html_blocks_against_text(
    blocks: Iterable[HtmlBlockLike],
    *,
    normalized_text: str,
    expected_block_count: int | None = None,
) -> list[HtmlBlockLike]:
    ordered = list(blocks)
    if expected_block_count is not None and len(ordered) != expected_block_count:
        raise HtmlIntegrityError("html block_count does not match persisted blocks")
    seen_orders: set[int] = set()
    seen_ids: set[str] = set()
    for block in ordered:
        if block.block_order in seen_orders:
            raise HtmlIntegrityError("html block_order is not unique")
        if block.block_id in seen_ids:
            raise HtmlIntegrityError("html block_id is not unique")
        seen_orders.add(block.block_order)
        seen_ids.add(block.block_id)
        validate_html_block_against_text(block, normalized_text=normalized_text)
    return ordered


def validate_html_anchor_range(
    *,
    block_id: str,
    block_kind: str,
    heading_path: object,
    char_start: int,
    char_end: int,
    text_sha256_value: str,
    normalization_version: str,
    css_path_hint: str | None,
    block: HtmlBlockLike,
    normalized_text: str,
) -> list[str]:
    if normalization_version != HTML_NORMALIZATION_VERSION:
        raise HtmlIntegrityError("html_anchor has an unsupported normalization_version")
    if not block_id:
        raise HtmlIntegrityError("html_anchor requires a stable block_id")
    if block_kind not in HTML_BLOCK_KINDS:
        raise HtmlIntegrityError("html_anchor has an unsupported block_kind")
    if char_start < 0 or char_end <= char_start:
        raise HtmlIntegrityError("html_anchor requires a single non-empty char range")
    try:
        path = validate_heading_path(heading_path)
        validate_css_path_hint(css_path_hint)
    except ValueError as error:
        raise HtmlIntegrityError(f"html_anchor {error}") from error
    digest = validate_hex_sha256(text_sha256_value, field_name="text_sha256")
    block_path = validate_html_block_against_text(block, normalized_text=normalized_text)
    if block.block_id != block_id:
        raise HtmlIntegrityError("html_anchor block_id does not match stored block")
    if block.block_kind != block_kind:
        raise HtmlIntegrityError("html_anchor block_kind does not match stored block")
    if block.normalization_version != normalization_version:
        raise HtmlIntegrityError("html_anchor normalization_version does not match stored block")
    if block_path != path:
        raise HtmlIntegrityError("html_anchor heading_path does not match stored block")
    if char_start < block.char_start or char_end > block.char_end:
        raise HtmlIntegrityError("html_anchor range is outside the stored block bounds")
    range_text = normalized_text[char_start:char_end]
    if not range_text:
        raise HtmlIntegrityError("html_anchor range resolves to empty text")
    if digest != text_sha256(range_text):
        raise HtmlIntegrityError("html_anchor text_sha256 does not match normalized substring")
    return path


def validate_html_normalized_bundle(
    normalized: HtmlNormalizedLike,
    blocks: Iterable[HtmlBlockLike],
) -> tuple[str, list[HtmlBlockLike]]:
    normalized_text = validate_html_normalized_content(normalized)
    validated_blocks = validate_html_blocks_against_text(
        blocks,
        normalized_text=normalized_text,
        expected_block_count=normalized.block_count,
    )
    return normalized_text, validated_blocks
