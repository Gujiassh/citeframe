"""Document modality helpers for stable block identity and validation.

Worker owns Markdown parse/normalize persistence. API uses these helpers for
codec validation, fixture construction, upload payload checks, and generation-
scoped block lookup.
"""

from __future__ import annotations

from hashlib import sha256
from typing import Iterable, Protocol

DOCUMENT_FORMAT_MARKDOWN = "markdown"
DOCUMENT_PARSER_VERSION = "document-parser-v1"
DOCUMENT_NORMALIZATION_VERSION = "document-normalization-v1"
DOCUMENT_BLOCK_KINDS = frozenset(
    {"heading", "paragraph", "list_item", "code_block", "quote", "table"}
)
DOCUMENT_HEADING_LEVELS = frozenset({1, 2, 3, 4, 5, 6})


class DocumentIntegrityError(ValueError):
    """Raised when persisted document normalized content or blocks are corrupt."""


class DocumentNormalizedLike(Protocol):
    format: str
    parser_version: str
    normalization_version: str
    normalized_text: str
    content_sha256: str
    block_count: int


class DocumentBlockLike(Protocol):
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


def validate_heading_path(heading_path: object) -> list[str]:
    if not isinstance(heading_path, list):
        raise ValueError("heading_path must be a list of strings")
    if any(not isinstance(part, str) or not part for part in heading_path):
        raise ValueError("heading_path must be an ordered array of non-empty strings")
    return list(heading_path)


def validate_heading_level(*, block_kind: str, heading_level: int | None) -> int | None:
    if block_kind == "heading":
        if heading_level not in DOCUMENT_HEADING_LEVELS:
            raise ValueError("heading blocks require heading_level in 1..6")
        return heading_level
    if heading_level is not None:
        raise ValueError("non-heading document blocks must not set heading_level")
    return None


def stable_document_block_id(
    *,
    source_sha256: str,
    parser_version: str,
    block_order: int,
    block_kind: str,
    heading_path: Iterable[str],
    text_sha256: str,
) -> str:
    """Derive a stable block_id from source SHA + parser version + canonical identity."""
    if parser_version != DOCUMENT_PARSER_VERSION:
        raise ValueError(f"Unsupported document parser version: {parser_version}")
    if block_kind not in DOCUMENT_BLOCK_KINDS:
        raise ValueError(f"Unsupported document block_kind: {block_kind}")
    if block_order < 0:
        raise ValueError("block_order must be non-negative")
    path = validate_heading_path(list(heading_path))
    material = "\n".join(
        [
            source_sha256,
            parser_version,
            str(block_order),
            block_kind,
            "/".join(path),
            text_sha256,
        ]
    )
    digest = sha256(material.encode("utf-8")).hexdigest()
    return f"docblk_{digest[:32]}"


def text_sha256(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def validate_hex_sha256(value: object, *, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise DocumentIntegrityError(
            f"document requires a lowercase hex SHA-256 {field_name}"
        )
    return value


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


def detect_markdown_mime_type(header: bytes) -> str | None:
    """Header-level probe used by the registry MIME map.

    Full payload validation still happens for document uploads via
    ``validate_markdown_upload_payload``.
    """
    if not header:
        return None
    if _looks_like_foreign_binary(header):
        return None
    return "text/markdown"


def validate_markdown_upload_payload(payload: bytes) -> None:
    """Validate the complete bounded upload body as UTF-8 Markdown.

    Rejects foreign binary signatures (PDF/PNG/JPEG/WEBP/ZIP/ELF), embedded NUL,
    and non-UTF-8 payloads. Does not inspect filenames.
    """
    if not payload:
        raise ValueError("Markdown upload body is empty")
    if _looks_like_foreign_binary(payload):
        raise ValueError(
            "File signature does not match declared MIME type: text/markdown"
        )
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Markdown upload must be valid UTF-8 text") from error


def validate_document_normalized_content(
    normalized: DocumentNormalizedLike,
) -> str:
    """Validate generation-scoped normalized content and return normalized_text."""
    if normalized.format != DOCUMENT_FORMAT_MARKDOWN:
        raise DocumentIntegrityError("document normalized content format is invalid")
    if normalized.parser_version != DOCUMENT_PARSER_VERSION:
        raise DocumentIntegrityError("document normalized content parser_version is invalid")
    if normalized.normalization_version != DOCUMENT_NORMALIZATION_VERSION:
        raise DocumentIntegrityError(
            "document normalized content normalization_version is invalid"
        )
    if not isinstance(normalized.normalized_text, str):
        raise DocumentIntegrityError("document normalized_text is invalid")
    if normalized.block_count < 0:
        raise DocumentIntegrityError("document block_count is invalid")
    content_digest = validate_hex_sha256(
        normalized.content_sha256, field_name="content_sha256"
    )
    actual_digest = text_sha256(normalized.normalized_text)
    if actual_digest != content_digest:
        raise DocumentIntegrityError(
            "document content_sha256 does not match normalized_text"
        )
    return normalized.normalized_text


def validate_document_block_against_text(
    block: DocumentBlockLike,
    *,
    normalized_text: str,
) -> list[str]:
    """Validate one stored block against Python code-point normalized text."""
    if not block.block_id:
        raise DocumentIntegrityError("document block requires a stable block_id")
    if block.block_kind not in DOCUMENT_BLOCK_KINDS:
        raise DocumentIntegrityError("document block_kind is unsupported")
    if block.normalization_version != DOCUMENT_NORMALIZATION_VERSION:
        raise DocumentIntegrityError("document block normalization_version is invalid")
    if block.block_order < 0:
        raise DocumentIntegrityError("document block_order is invalid")
    try:
        heading_path = validate_heading_path(block.heading_path)
        validate_heading_level(
            block_kind=block.block_kind, heading_level=block.heading_level
        )
    except ValueError as error:
        raise DocumentIntegrityError(str(error)) from error
    if block.char_start < 0 or block.char_end <= block.char_start:
        raise DocumentIntegrityError("document block range is invalid")
    if block.char_end > len(normalized_text):
        raise DocumentIntegrityError(
            "document block range exceeds normalized document length"
        )
    expected_text = normalized_text[block.char_start:block.char_end]
    if not isinstance(block.text_content, str) or not block.text_content:
        raise DocumentIntegrityError("document block text_content is invalid")
    if block.text_content != expected_text:
        raise DocumentIntegrityError(
            "document block text_content does not match normalized substring"
        )
    digest = validate_hex_sha256(block.text_sha256, field_name="text_sha256")
    if digest != text_sha256(block.text_content):
        raise DocumentIntegrityError(
            "document block text_sha256 does not match block text_content"
        )
    return heading_path


def validate_document_blocks_against_text(
    blocks: Iterable[DocumentBlockLike],
    *,
    normalized_text: str,
    expected_block_count: int | None = None,
) -> list[DocumentBlockLike]:
    """Validate every block in representation order and fail closed on corruption."""
    ordered = list(blocks)
    if expected_block_count is not None and len(ordered) != expected_block_count:
        raise DocumentIntegrityError(
            "document block_count does not match persisted blocks"
        )
    seen_orders: set[int] = set()
    seen_ids: set[str] = set()
    for block in ordered:
        if block.block_order in seen_orders:
            raise DocumentIntegrityError("document block_order is not unique")
        if block.block_id in seen_ids:
            raise DocumentIntegrityError("document block_id is not unique")
        seen_orders.add(block.block_order)
        seen_ids.add(block.block_id)
        validate_document_block_against_text(block, normalized_text=normalized_text)
    return ordered


def validate_document_anchor_range(
    *,
    block_id: str,
    block_kind: str,
    heading_path: object,
    char_start: int,
    char_end: int,
    text_sha256_value: str,
    normalization_version: str,
    block: DocumentBlockLike,
    normalized_text: str,
) -> list[str]:
    """Validate a single document_anchor range against its block and normalized text."""
    if normalization_version != DOCUMENT_NORMALIZATION_VERSION:
        raise DocumentIntegrityError(
            "document_anchor has an unsupported normalization_version"
        )
    if not block_id:
        raise DocumentIntegrityError("document_anchor requires a stable block_id")
    if block_kind not in DOCUMENT_BLOCK_KINDS:
        raise DocumentIntegrityError("document_anchor has an unsupported block_kind")
    if char_start < 0 or char_end <= char_start:
        raise DocumentIntegrityError(
            "document_anchor requires a single non-empty char range"
        )
    try:
        path = validate_heading_path(heading_path)
    except ValueError as error:
        raise DocumentIntegrityError(f"document_anchor {error}") from error
    digest = validate_hex_sha256(text_sha256_value, field_name="text_sha256")

    block_path = validate_document_block_against_text(
        block, normalized_text=normalized_text
    )
    if block.block_id != block_id:
        raise DocumentIntegrityError("document_anchor block_id does not match stored block")
    if block.block_kind != block_kind:
        raise DocumentIntegrityError(
            "document_anchor block_kind does not match stored block"
        )
    if block.normalization_version != normalization_version:
        raise DocumentIntegrityError(
            "document_anchor normalization_version does not match stored block"
        )
    if block_path != path:
        raise DocumentIntegrityError(
            "document_anchor heading_path does not match stored block"
        )
    if char_start < block.char_start or char_end > block.char_end:
        raise DocumentIntegrityError(
            "document_anchor range is outside the stored block bounds"
        )
    if char_end > len(normalized_text):
        raise DocumentIntegrityError(
            "document_anchor range exceeds normalized document length"
        )
    range_text = normalized_text[char_start:char_end]
    if not range_text:
        raise DocumentIntegrityError("document_anchor range resolves to empty text")
    if digest != text_sha256(range_text):
        raise DocumentIntegrityError(
            "document_anchor text_sha256 does not match normalized substring"
        )
    if char_start == block.char_start and char_end == block.char_end:
        if digest != block.text_sha256:
            raise DocumentIntegrityError(
                "document_anchor text_sha256 does not match full block text"
            )
    return path


def validate_document_normalized_bundle(
    normalized: DocumentNormalizedLike,
    blocks: Iterable[DocumentBlockLike],
) -> tuple[str, list[DocumentBlockLike]]:
    """Validate normalized content + all blocks as one fail-closed integrity bundle."""
    normalized_text = validate_document_normalized_content(normalized)
    validated_blocks = validate_document_blocks_against_text(
        blocks,
        normalized_text=normalized_text,
        expected_block_count=normalized.block_count,
    )
    return normalized_text, validated_blocks
