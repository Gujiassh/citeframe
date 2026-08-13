"""HTML parse + sanitize + normalize (html-parser-v1 / html-sanitizer-v1)."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from ai_pdf_api.modalities.html import (
    HTML_BLOCK_KINDS,
    HTML_HEADING_LEVELS,
    HTML_MIME_TYPES,
    extract_html_blocks,
    sanitize_html,
    text_sha256,
)
from ai_pdf_api.modalities.ingestion import IngestionError

HTML_MIME = "text/html"


@dataclass(frozen=True)
class ParsedHtmlBlock:
    block_order: int
    block_kind: str
    heading_level: int | None
    heading_path: tuple[str, ...]
    text: str
    char_start: int
    char_end: int
    css_path_hint: str | None

    def __post_init__(self) -> None:
        if self.block_kind not in HTML_BLOCK_KINDS:
            raise ValueError(f"Unsupported HTML block_kind: {self.block_kind}")
        if self.block_order < 0:
            raise ValueError("block_order must be non-negative")
        if self.char_start < 0 or self.char_end <= self.char_start:
            raise ValueError("block character range must be non-empty")
        if not self.text:
            raise ValueError("block text must not be empty")
        if self.block_kind == "heading":
            if self.heading_level not in HTML_HEADING_LEVELS:
                raise ValueError("heading blocks require heading_level in 1..6")
        elif self.heading_level is not None:
            raise ValueError("non-heading HTML blocks must not set heading_level")


@dataclass(frozen=True)
class HtmlParseResult:
    normalized_text: str
    sanitized_html: str
    content_sha256: str
    blocks: tuple[ParsedHtmlBlock, ...]
    source_sha256: str


def decode_html_payload(payload: bytes, *, mime_type: str) -> tuple[str, str]:
    if mime_type.lower() not in HTML_MIME_TYPES:
        raise IngestionError(
            "asset_mime_mismatch",
            f"HTML adapter only accepts {sorted(HTML_MIME_TYPES)}.",
        )
    if not payload:
        raise IngestionError("asset_bytes_invalid", "HTML source bytes are empty.")
    if _looks_like_foreign_binary(payload):
        raise IngestionError(
            "asset_bytes_invalid",
            "HTML source bytes match a non-HTML binary signature.",
        )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise IngestionError(
            "asset_encoding_unsupported",
            "HTML source is not valid UTF-8.",
        ) from error
    if text.startswith("\ufeff"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text, sha256(payload).hexdigest()


def parse_html_document(payload: bytes, *, mime_type: str = HTML_MIME) -> HtmlParseResult:
    source_text, source_sha = decode_html_payload(payload, mime_type=mime_type)
    try:
        sanitized = sanitize_html(source_text)
        raw_blocks = extract_html_blocks(sanitized)
    except IngestionError:
        raise
    except Exception as error:
        raise IngestionError("html_parse_failed", "HTML document could not be parsed.") from error

    if not raw_blocks:
        raise IngestionError("html_parse_failed", "HTML document produced no non-empty blocks.")

    normalized_parts: list[str] = []
    blocks: list[ParsedHtmlBlock] = []
    cursor = 0
    for order, (kind, heading_level, heading_path, text, hint) in enumerate(raw_blocks):
        if order > 0:
            normalized_parts.append("\n")
            cursor += 1
        char_start = cursor
        char_end = char_start + len(text)
        normalized_parts.append(text)
        cursor = char_end
        blocks.append(
            ParsedHtmlBlock(
                block_order=order,
                block_kind=kind,
                heading_level=heading_level,
                heading_path=tuple(heading_path),
                text=text,
                char_start=char_start,
                char_end=char_end,
                css_path_hint=hint,
            )
        )

    normalized_text = "".join(normalized_parts)
    if normalized_text and not normalized_text.endswith("\n"):
        normalized_text = f"{normalized_text}\n"
    if not normalized_text.strip():
        raise IngestionError(
            "html_normalization_failed",
            "HTML normalization produced empty content.",
        )
    for block in blocks:
        if normalized_text[block.char_start : block.char_end] != block.text:
            raise IngestionError(
                "html_normalization_failed",
                "Block character offsets do not match normalized text.",
            )
    return HtmlParseResult(
        normalized_text=normalized_text,
        sanitized_html=sanitized,
        content_sha256=text_sha256(normalized_text),
        blocks=tuple(blocks),
        source_sha256=source_sha,
    )


def split_html_text(text: str, chunk_size: int, *, overlap: int) -> list[tuple[int, int, str]]:
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


def _looks_like_foreign_binary(payload: bytes) -> bool:
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
