"""Application-independent memory and provider contracts (P1a)."""
from __future__ import annotations

import base64
import binascii
from zlib import crc32

from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol, TypeAlias


class MemoryError(RuntimeError):
    """Errors contain stable codes only, never source bodies."""


class AccessDenied(MemoryError):
    pass


class VersionConflict(MemoryError):
    pass


class IdempotencyConflict(MemoryError):
    pass


class SourceUnavailable(MemoryError):
    pass


class ProtocolError(MemoryError):
    pass


@dataclass(frozen=True)
class AccessContext:
    actor_user_id: str
    workspace_id: str
    purpose: Literal["management", "chat", "research_planning", "research_task"]
    output_audience: Literal["private", "workspace"]


class AccessPort(Protocol):
    def authorize(self, context: AccessContext, *, owner_user_id: str) -> None:
        """Raise AccessDenied unless current membership and exact private owner allow access.

        Implementations retain transaction-scoped workspace/member guards through commit.
        """
        ...


@dataclass(frozen=True)
class ModelConnectionSnapshot:
    protocol: Literal["openai_responses", "openai_chat_completions", "anthropic"]
    endpoint: str
    model: str
    api_key: str = field(repr=False)
    timeout_seconds: float
    config_fingerprint: str
    context_window_tokens: int
    max_output_tokens: int

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0 or self.context_window_tokens <= 0 or self.max_output_tokens <= 0:
            raise ValueError("invalid_model_capacity")
        if not self.endpoint or not self.model or not self.config_fingerprint:
            raise ValueError("invalid_model_connection")


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters_json: str


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments_json: str


GENERATION_IMAGE_STRUCTURE_VERSION = "generation-image-structure-v1"
GENERATION_IMAGE_MAX_DECODED_BYTES = 4_194_304
GENERATION_IMAGE_MAX_ENCODED_CHARS = 5_592_408
GENERATION_MESSAGE_MAX_IMAGES = 8
GENERATION_IMAGE_MAX_DIMENSION = 2_147_483_647
_IMAGE_BASE64_ALPHABET = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
)
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8),
               4: (8, 16), 6: (8, 16)}


def _image_ascii(value: str) -> bytes:
    return value.encode("ascii")


def _validate_generation_image(image: GenerationImage) -> None:
    code = "generation_input_unsupported"
    if (type(image.media_type) is not str or type(image.data_base64) is not str
            or type(image.detail) is not str
            or type(image.width) is not int or type(image.height) is not int):
        raise ProtocolError(code)
    if (image.media_type != "image/png" or image.detail != "high"
            or not 1 <= image.width <= GENERATION_IMAGE_MAX_DIMENSION
            or not 1 <= image.height <= GENERATION_IMAGE_MAX_DIMENSION):
        raise ProtocolError(code)
    value = image.data_base64
    size = len(value)
    if not 44 <= size <= GENERATION_IMAGE_MAX_ENCODED_CHARS or size % 4:
        raise ProtocolError(code)
    padding = int(value[-1] == "=") + int(value[-2] == "=")
    decoded_size = 3 * (size // 4) - padding
    if not 33 <= decoded_size <= GENERATION_IMAGE_MAX_DECODED_BYTES:
        raise ProtocolError(code)
    boundary = size - padding
    for index, char in enumerate(value):
        if (index < boundary and char not in _IMAGE_BASE64_ALPHABET
                or index >= boundary and char != "="):
            raise ProtocolError(code)
    try:
        encoded = _image_ascii(value)
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) != decoded_size or base64.b64encode(raw) != encoded:
            raise ProtocolError(code)
    except (ValueError, binascii.Error):
        raise ProtocolError(code) from None
    # Only the fixed IHDR is inspected; native admission owns complete PNG validity.
    header = raw[:33]
    if (header[:8] != _PNG_SIGNATURE or header[8:12] != b"\x00\x00\x00\x0d"
            or header[12:16] != b"IHDR"
            or int.from_bytes(header[16:20], "big") != image.width
            or int.from_bytes(header[20:24], "big") != image.height
            or header[24] not in _PNG_DEPTHS.get(header[25], ())
            or header[26] != 0 or header[27] != 0 or header[28] not in (0, 1)
            or crc32(header[12:29]) != int.from_bytes(header[29:33], "big")):
        raise ProtocolError(code)


@dataclass(frozen=True)
class GenerationImage:
    """Bounded PNG structure value; source authority and native decoding are external."""

    media_type: Literal["image/png"]
    data_base64: str = field(repr=False)
    width: int
    height: int
    detail: Literal["high"] = "high"

    def __post_init__(self) -> None:
        _validate_generation_image(self)


@dataclass(frozen=True)
class GenerationMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True)
class GenerationRequest:
    messages: tuple[GenerationMessage, ...]
    max_output_tokens: int
    purpose: Literal["main", "compact_chunk", "compact_merge"] = "main"
    tools: tuple[ToolDefinition, ...] = ()
    temperature: float | None = None

    def __post_init__(self) -> None:
        if self.max_output_tokens <= 0:
            raise ValueError("invalid_output_capacity")
        if self.purpose != "main" and self.tools:
            raise ValueError("compaction_tools_forbidden")


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ToolCallDelta:
    index: int
    arguments_delta: str
    call_id: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class ToolCallComplete:
    call: ToolCall


@dataclass(frozen=True)
class Usage:
    """Input tokens include uncached, cache-read and cache-creation tokens; unknown totals stay None."""

    input_tokens: int | None
    output_tokens: int | None
    source: Literal["reported", "estimated", "unknown"] = "reported"


@dataclass(frozen=True)
class TurnComplete:
    reason: Literal["answer", "tool_calls"]


GenerationEvent: TypeAlias = TextDelta | ToolCallDelta | ToolCallComplete | Usage | TurnComplete


class GenerationPort(Protocol):
    def stream_turn(self, request: GenerationRequest) -> Iterator[GenerationEvent]: ...


class HTTPResponse(Protocol):
    status_code: int
    def iter_lines(self) -> Iterator[str]: ...
    def read(self) -> bytes: ...


class HTTPTransport(Protocol):
    def stream(self, method: str, url: str, *, headers: Mapping[str, str],
               json: Mapping[str, object], timeout: float,
               follow_redirects: bool) -> AbstractContextManager[HTTPResponse]: ...


@dataclass(frozen=True)
class TokenCount:
    tokens: int
    mode: Literal["exact", "estimated"]
    counter_id: str
    counter_version: str
    config_fingerprint: str


class TokenCounter(Protocol):
    def count(self, request: GenerationRequest, connection: ModelConnectionSnapshot) -> TokenCount: ...


class GenerationObserver(Protocol):
    def __call__(self, event: Literal["started", "completed", "failed"], *,
                 config_fingerprint: str, error_code: str | None = None) -> None: ...


class EmbeddingPort(Protocol):
    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


class ObjectStorePort(Protocol):
    def put(self, key: str, body: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True)
class MemoryConditions:
    subject: str
    applicability: str
    effective_from: datetime | None = None

    def __post_init__(self) -> None:
        if not 1 <= len(self.subject) <= 256 or not 1 <= len(self.applicability) <= 2000:
            raise ValueError("invalid_conditions")
        if self.effective_from is not None and self.effective_from.utcoffset() is None:
            raise ValueError("timezone_required")


@dataclass(frozen=True)
class MemoryStatement:
    content: str
    conditions: MemoryConditions
    kind: Literal["preference", "constraint", "fact", "decision"] = "fact"
    pinned: bool = False
    valid_until: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content, str) or not 1 <= len(self.content) <= 4000:
            raise ValueError("invalid_content")
        if self.kind not in ("preference", "constraint", "fact", "decision"):
            raise ValueError("invalid_kind")
        if type(self.pinned) is not bool or (self.pinned and self.kind not in ("constraint", "decision")):
            raise ValueError("invalid_pinned")
        if self.valid_until is not None and self.valid_until.utcoffset() is None:
            raise ValueError("timezone_required")


@dataclass(frozen=True)
class MemoryRequest:
    request_id: str
    idempotency_key: str


@dataclass(frozen=True)
class MemoryView:
    memory_id: str
    version: int
    revision_id: str
    intent: Literal["active", "inactive", "superseded", "deleted"]
    validity: Literal["valid", "invalidated"]
    statement: MemoryStatement | None
    confirmation_source_id: str
    erased: bool


@dataclass(frozen=True)
class MemoryReceipt:
    operation_id: str
    request_id: str
    result_version: int
    resource: MemoryView


@dataclass(frozen=True)
class InstructionSourceView:
    source_id: str
    instruction_id: str
    actor_user_id: str
    content: str
    content_sha256: str
    created_at: datetime


__all__ = [
    "MemoryConditions", "MemoryStatement", "MemoryRequest", "MemoryView", "MemoryReceipt", "InstructionSourceView",
    "AccessContext", "AccessDenied", "AccessPort", "Clock", "EmbeddingPort",
    "GenerationImage", "GenerationEvent", "GenerationMessage", "GenerationObserver", "GenerationPort",
    "GenerationRequest", "HTTPResponse", "HTTPTransport", "IdempotencyConflict",
    "MemoryError", "ModelConnectionSnapshot", "ObjectStorePort", "ProtocolError",
    "SourceUnavailable", "TextDelta", "TokenCount", "TokenCounter", "ToolCall",
    "ToolCallComplete", "ToolCallDelta", "ToolDefinition", "TurnComplete", "Usage",
    "VersionConflict",
]
