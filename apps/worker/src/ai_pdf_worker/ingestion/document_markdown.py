"""Markdown parse + normalize for Document modality (document-parser-v1).

Uses markdown-it-py CommonMark + GFM tables. Pure functions only; no ORM/I/O.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256

from markdown_it import MarkdownIt
from markdown_it.token import Token

from ai_pdf_api.modalities.document import (
    DOCUMENT_BLOCK_KINDS,
    DOCUMENT_HEADING_LEVELS,
    text_sha256,
)
from ai_pdf_api.modalities.ingestion import IngestionError

MARKDOWN_MIME = "text/markdown"
_HEADING_TAG = re.compile(r"^h([1-6])$")
_WHITESPACE_RUN = re.compile(r"[ \t]+")


@dataclass(frozen=True)
class ParsedDocumentBlock:
    block_order: int
    block_kind: str
    heading_level: int | None
    heading_path: tuple[str, ...]
    text: str
    char_start: int
    char_end: int

    def __post_init__(self) -> None:
        if self.block_kind not in DOCUMENT_BLOCK_KINDS:
            raise ValueError(f"Unsupported document block_kind: {self.block_kind}")
        if self.block_order < 0:
            raise ValueError("block_order must be non-negative")
        if self.char_start < 0 or self.char_end <= self.char_start:
            raise ValueError("block character range must be non-empty")
        if not self.text:
            raise ValueError("block text must not be empty")
        if self.block_kind == "heading":
            if self.heading_level not in DOCUMENT_HEADING_LEVELS:
                raise ValueError("heading blocks require heading_level in 1..6")
        elif self.heading_level is not None:
            raise ValueError("non-heading document blocks must not set heading_level")


@dataclass(frozen=True)
class DocumentParseResult:
    normalized_text: str
    content_sha256: str
    blocks: tuple[ParsedDocumentBlock, ...]
    source_sha256: str


def decode_markdown_payload(payload: bytes, *, mime_type: str) -> tuple[str, str]:
    """UTF-8 canonical decode with fail-closed MIME and binary guards."""
    if mime_type != MARKDOWN_MIME:
        raise IngestionError(
            "asset_mime_mismatch",
            f"Document adapter only accepts {MARKDOWN_MIME}.",
        )
    if not payload:
        raise IngestionError("asset_bytes_invalid", "Document source bytes are empty.")
    if _looks_like_foreign_binary(payload):
        raise IngestionError(
            "asset_bytes_invalid",
            "Document source bytes match a non-Markdown binary signature.",
        )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise IngestionError(
            "asset_encoding_unsupported",
            "Document source is not valid UTF-8.",
        ) from error
    if text.startswith("\ufeff"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text, sha256(payload).hexdigest()


def parse_markdown_document(
    payload: bytes,
    *,
    mime_type: str = MARKDOWN_MIME,
) -> DocumentParseResult:
    source_text, source_sha = decode_markdown_payload(payload, mime_type=mime_type)
    try:
        tokens = _markdown_parser().parse(source_text)
        raw_blocks = _tokens_to_raw_blocks(tokens)
    except IngestionError:
        raise
    except Exception as error:
        raise IngestionError(
            "document_parse_failed",
            "Markdown document could not be parsed.",
        ) from error

    if not raw_blocks:
        raise IngestionError(
            "document_parse_failed",
            "Markdown document produced no non-empty blocks.",
        )

    normalized_parts: list[str] = []
    blocks: list[ParsedDocumentBlock] = []
    cursor = 0
    for order, (kind, heading_level, heading_path, text) in enumerate(raw_blocks):
        if order > 0:
            normalized_parts.append("\n")
            cursor += 1
        char_start = cursor
        char_end = char_start + len(text)
        normalized_parts.append(text)
        cursor = char_end
        blocks.append(
            ParsedDocumentBlock(
                block_order=order,
                block_kind=kind,
                heading_level=heading_level,
                heading_path=tuple(heading_path),
                text=text,
                char_start=char_start,
                char_end=char_end,
            )
        )

    normalized_text = "".join(normalized_parts)
    if normalized_text and not normalized_text.endswith("\n"):
        normalized_text = f"{normalized_text}\n"
    if not normalized_text.strip():
        raise IngestionError(
            "document_normalization_failed",
            "Markdown normalization produced empty content.",
        )
    for block in blocks:
        if normalized_text[block.char_start : block.char_end] != block.text:
            raise IngestionError(
                "document_normalization_failed",
                "Block character offsets do not match normalized text.",
            )
        if text_sha256(block.text) != text_sha256(
            normalized_text[block.char_start : block.char_end]
        ):
            raise IngestionError(
                "document_normalization_failed",
                "Block text hash does not match normalized substring.",
            )
    return DocumentParseResult(
        normalized_text=normalized_text,
        content_sha256=text_sha256(normalized_text),
        blocks=tuple(blocks),
        source_sha256=source_sha,
    )


def split_document_text(text: str, chunk_size: int, *, overlap: int) -> list[tuple[int, int, str]]:
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


def _markdown_parser() -> MarkdownIt:
    # CommonMark core + GFM pipe tables (with or without outer pipes).
    return MarkdownIt("commonmark", {"html": False}).enable("table")


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


def _tokens_to_raw_blocks(
    tokens: Sequence[Token],
) -> list[tuple[str, int | None, list[str], str]]:
    blocks: list[tuple[str, int | None, list[str], str]] = []
    heading_stack: list[tuple[int, str]] = []
    index = 0
    list_stack: list[dict[str, object]] = []

    def current_path() -> list[str]:
        return [text for _, text in heading_stack]

    while index < len(tokens):
        token = tokens[index]
        token_type = token.type

        if token_type == "heading_open":
            level = _heading_level(token.tag)
            inline = _require_inline(tokens, index + 1)
            text = _normalize_inline_text(inline.content)
            if not text:
                raise IngestionError(
                    "document_parse_failed",
                    "Markdown heading text is empty.",
                )
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, text))
            blocks.append(("heading", level, current_path(), text))
            index = _skip_close(tokens, index, "heading_close")
            continue

        if token_type == "paragraph_open":
            # Paragraphs nested inside lists/blockquotes are handled by those collectors.
            if token.level > 0:
                index += 1
                continue
            inline = _require_inline(tokens, index + 1)
            text = _normalize_inline_text(inline.content)
            if text:
                blocks.append(("paragraph", None, current_path(), text))
            index = _skip_close(tokens, index, "paragraph_close")
            continue

        if token_type == "fence" or token_type == "code_block":
            if token.level > 0:
                index += 1
                continue
            text = _normalize_code_text(token.content, info=token.info or "")
            if text:
                blocks.append(("code_block", None, current_path(), text))
            index += 1
            continue

        if token_type == "blockquote_open" and token.level == 0:
            close_at = _find_matching_close(tokens, index, "blockquote_open", "blockquote_close")
            text = _collect_blockquote_text(tokens[index + 1 : close_at])
            if text:
                blocks.append(("quote", None, current_path(), text))
            index = close_at + 1
            continue

        if token_type == "table_open" and token.level == 0:
            close_at = _find_matching_close(tokens, index, "table_open", "table_close")
            text = _collect_table_text(tokens[index + 1 : close_at])
            if text:
                blocks.append(("table", None, current_path(), text))
            index = close_at + 1
            continue

        if token_type in {"bullet_list_open", "ordered_list_open"}:
            ordered = token_type == "ordered_list_open"
            list_stack.append(
                {
                    "ordered": ordered,
                    "marker": token.markup or ("." if ordered else "-"),
                    "depth": len(list_stack),
                }
            )
            index += 1
            continue

        if token_type in {"bullet_list_close", "ordered_list_close"}:
            if list_stack:
                list_stack.pop()
            index += 1
            continue

        if token_type == "list_item_open":
            close_at = _find_matching_close(tokens, index, "list_item_open", "list_item_close")
            item_tokens = tokens[index + 1 : close_at]
            # Emit only this item's direct text. Nested list_item_open tokens are
            # visited later (do not jump past the item close).
            direct_text = _collect_list_item_direct_text(item_tokens)
            if direct_text and list_stack:
                frame = list_stack[-1]
                depth = int(frame["depth"])
                ordered = bool(frame["ordered"])
                marker = str(frame["marker"])
                if ordered:
                    number = token.info or "1"
                    prefix = f"{number}{marker}"
                else:
                    prefix = marker if marker else "-"
                indent = "  " * max(depth - 1, 0)
                text = _normalize_inline_text(f"{indent}{prefix} {direct_text}")
                if text:
                    blocks.append(("list_item", None, current_path(), text))
            index += 1
            continue

        if token_type == "list_item_close":
            index += 1
            continue

        # Skip thematic breaks, html (disabled), tight/soft wrappers, etc.
        index += 1

    return blocks


def _heading_level(tag: str) -> int:
    match = _HEADING_TAG.match(tag or "")
    if match is None:
        raise IngestionError("document_parse_failed", "Unsupported heading tag.")
    return int(match.group(1))


def _require_inline(tokens: Sequence[Token], index: int) -> Token:
    if index >= len(tokens) or tokens[index].type != "inline":
        raise IngestionError(
            "document_parse_failed",
            "Markdown structure is missing inline content.",
        )
    return tokens[index]


def _skip_close(tokens: Sequence[Token], open_index: int, close_type: str) -> int:
    index = open_index + 1
    while index < len(tokens):
        if tokens[index].type == close_type:
            return index + 1
        index += 1
    raise IngestionError("document_parse_failed", f"Markdown missing {close_type}.")


def _find_matching_close(
    tokens: Sequence[Token],
    open_index: int,
    open_type: str,
    close_type: str,
) -> int:
    depth = 0
    for index in range(open_index, len(tokens)):
        token_type = tokens[index].type
        if token_type == open_type:
            depth += 1
        elif token_type == close_type:
            depth -= 1
            if depth == 0:
                return index
    raise IngestionError(
        "document_parse_failed",
        f"Markdown missing matching {close_type}.",
    )


def _collect_blockquote_text(tokens: Sequence[Token]) -> str:
    parts: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.type == "paragraph_open":
            inline = _require_inline(tokens, index + 1)
            text = _normalize_inline_text(inline.content)
            if text:
                parts.append(text)
            index = _skip_close(tokens, index, "paragraph_close")
            continue
        if token.type == "fence" or token.type == "code_block":
            text = _normalize_code_text(token.content, info=token.info or "")
            if text:
                parts.append(text)
            index += 1
            continue
        if token.type == "blockquote_open":
            close_at = _find_matching_close(tokens, index, "blockquote_open", "blockquote_close")
            nested = _collect_blockquote_text(tokens[index + 1 : close_at])
            if nested:
                parts.append(nested)
            index = close_at + 1
            continue
        index += 1
    return "\n".join(parts).strip()


def _collect_table_text(tokens: Sequence[Token]) -> str:
    rows: list[str] = []
    current_cells: list[str] = []
    for token in tokens:
        if token.type in {"th_open", "td_open"}:
            current_cells.append("")
            continue
        if token.type == "inline" and current_cells is not None:
            # Attach to the latest open cell placeholder.
            if current_cells and current_cells[-1] == "":
                current_cells[-1] = _normalize_inline_text(token.content)
            continue
        if token.type == "tr_close":
            if any(cell for cell in current_cells):
                rows.append(" | ".join(current_cells))
            current_cells = []
            continue
    return "\n".join(rows).strip()


def _collect_list_item_direct_text(tokens: Sequence[Token]) -> str:
    parts: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.type in {"bullet_list_open", "ordered_list_open"}:
            # Nested list is represented by its own list_item blocks.
            close_type = (
                "bullet_list_close"
                if token.type == "bullet_list_open"
                else "ordered_list_close"
            )
            index = _find_matching_close(tokens, index, token.type, close_type) + 1
            continue
        if token.type == "paragraph_open":
            inline = _require_inline(tokens, index + 1)
            text = _normalize_inline_text(inline.content)
            if text:
                parts.append(text)
            index = _skip_close(tokens, index, "paragraph_close")
            continue
        if token.type == "fence" or token.type == "code_block":
            text = _normalize_code_text(token.content, info=token.info or "")
            if text:
                parts.append(text)
            index += 1
            continue
        if token.type == "inline" and token.level == 0:
            text = _normalize_inline_text(token.content)
            if text:
                parts.append(text)
            index += 1
            continue
        index += 1
    return "\n".join(parts).strip()


def _normalize_code_text(content: str, *, info: str) -> str:
    body = (content or "").replace("\r\n", "\n").replace("\r", "\n")
    if body.endswith("\n"):
        body = body[:-1]
    info_text = (info or "").strip()
    if info_text and body:
        return f"{info_text}\n{body}"
    if info_text:
        return info_text
    return body


def _normalize_inline_text(text: str) -> str:
    text = (text or "").replace("\u00a0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WHITESPACE_RUN.sub(" ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
