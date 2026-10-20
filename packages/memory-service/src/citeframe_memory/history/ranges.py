"""Exact text windows and per-request budgets, without native authority or storage."""
import base64
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import hmac
import json
from collections.abc import Callable

from citeframe_contracts.compaction import SourceReference
from citeframe_contracts.history import (
    SourcePage, SourceSelection, TextSpan, digest_shape, exact_keys, integer,
)
from citeframe_contracts.memory import (
    GenerationRequest, MemoryError, ModelConnectionSnapshot, TokenCount, TokenCounter,
)
from citeframe_memory.compaction.policy import (
    Capacity, CounterIdentity, count_request, validate_capacity,
)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def request_hash(request: GenerationRequest) -> str:
    return sha256(_json(asdict(request)).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TextWindow:
    selection: SourceSelection
    body_length: int
    before: int
    after: int
    next_start: int

    def __post_init__(self):
        if type(self.selection) is not SourceSelection:
            raise MemoryError("invalid_source_ref")
        integer(self.body_length, 0, 2**63 - 1)
        integer(self.before, 0, 2000)
        integer(self.after, 0, 2000)
        span = self.selection.span
        if span is None:
            if self.before or self.after:
                raise MemoryError("invalid_history_range")
        elif type(span) is not TextSpan or span.end > self.body_length:
            raise MemoryError("invalid_history_range")
        integer(self.next_start, self.start, self.end)

    @property
    def start(self):
        span = self.selection.span
        return max(0, span.start - self.before) if span else 0

    @property
    def end(self):
        span = self.selection.span
        return min(self.body_length, span.end + self.after) if span else self.body_length


def _body_matches(content: str, selection: SourceSelection):
    if type(content) is not str or type(selection) is not SourceSelection:
        raise MemoryError("invalid_source_ref")
    try:
        digest = sha256(content.encode("utf-8")).hexdigest()
    except UnicodeEncodeError:
        raise MemoryError("invalid_source_ref") from None
    if digest != selection.reference.sha256:
        raise MemoryError("source_version_unavailable")


def open_window(content: str, selection: SourceSelection, *, before=0, after=0) -> TextWindow:
    _body_matches(content, selection)
    start = max(0, selection.span.start - before) if type(selection.span) is TextSpan and type(before) is int else 0
    return TextWindow(selection, len(content), before, after, start)


def _key(key):
    if type(key) is not bytes or len(key) < 32:
        raise MemoryError("invalid_cursor_key")


def _payload(window, binding, expires_at):
    digest_shape(binding)
    integer(expires_at, 1, 2**63 - 1)
    return dict(version=1, binding=binding, expiresAt=expires_at,
                reference=asdict(window.selection.reference),
                span=asdict(window.selection.span) if window.selection.span else None,
                bodyLength=window.body_length, before=window.before, after=window.after,
                nextStart=window.next_start)


def encode_cursor(window: TextWindow, *, binding: str, expires_at: int, key: bytes) -> str:
    """Sign range data only. Binding must come from the future native issuer."""
    _key(key)
    raw = _json(_payload(window, binding, expires_at)).encode("utf-8")
    signature = hmac.digest(key, raw, "sha256")
    return base64.urlsafe_b64encode(raw + signature).decode("ascii").rstrip("=")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def decode_cursor(cursor: str, *, binding: str, key: bytes, now: int) -> tuple[TextWindow, int]:
    """Validate MAC/binding/range, NOT source permissions, owner state or native scope."""
    _key(key)
    digest_shape(binding)
    integer(now, 0, 2**63 - 1)
    if type(cursor) is not str or not 1 <= len(cursor) <= 4096:
        raise MemoryError("invalid_history_cursor")
    try:
        raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        data, signature = raw[:-32], raw[-32:]
        if not hmac.compare_digest(signature, hmac.digest(key, data, "sha256")):
            raise ValueError()
        value = json.loads(data, object_pairs_hook=_unique_object)
        exact_keys(value, ("version", "binding", "expiresAt", "reference", "span",
                           "bodyLength", "before", "after", "nextStart"))
        if type(value["version"]) is not int or value["version"] != 1 or value["binding"] != binding:
            raise ValueError()
        integer(value["expiresAt"], now + 1, now + 900)
        exact_keys(value["reference"], ("source_id", "version", "sha256"))
        span = value["span"]
        if span is not None:
            exact_keys(span, ("kind", "start", "end"))
            if span["kind"] != "text":
                raise ValueError()
            span = TextSpan(span["start"], span["end"])
        selection = SourceSelection(SourceReference(**value["reference"]), span)
        window = TextWindow(selection, value["bodyLength"], value["before"],
                            value["after"], value["nextStart"])
        if window.next_start >= window.end:
            raise ValueError()
        if encode_cursor(window, binding=binding, expires_at=value["expiresAt"], key=key) != cursor:
            raise ValueError()
        return window, value["expiresAt"]
    except (ValueError, TypeError, KeyError, UnicodeError, MemoryError, RecursionError):
        raise MemoryError("invalid_history_cursor") from None


@dataclass(frozen=True)
class CountedPage:
    page: SourcePage
    request: GenerationRequest
    count: TokenCount
    baseline_count: TokenCount
    request_sha256: str
    tool_call_id: str
    counting_profile_sha256: str


def _target_index(request: GenerationRequest, call_id: str) -> int:
    if (type(request) is not GenerationRequest or request.purpose != "main"
            or type(call_id) is not str or not call_id):
        raise MemoryError("invalid_history_framing")
    matches = [i for i, m in enumerate(request.messages) if m.role == "tool" and m.tool_call_id == call_id]
    if len(matches) != 1:
        raise MemoryError("invalid_history_framing")
    index = matches[0]
    first = index
    while first > 0 and request.messages[first - 1].role == "tool":
        first -= 1
    assistant = request.messages[first - 1] if first else None
    end = index + 1
    while end < len(request.messages) and request.messages[end].role == "tool":
        end += 1
    ids = tuple(m.tool_call_id for m in request.messages[first:end])
    if (assistant is None or assistant.role != "assistant" or not assistant.tool_calls
            or tuple(c.call_id for c in assistant.tool_calls) != ids
            or any(m.tool_calls for m in request.messages[first:end])
            or any(type(x) is not str or not x for x in ids)
            or len(set(ids)) != len(ids)):
        raise MemoryError("invalid_history_framing")
    return index


def fit_page(content: str, window: TextWindow, *, request: GenerationRequest,
             tool_call_id: str, render: Callable[[SourcePage], str],
             connection: ModelConnectionSnapshot, counter: TokenCounter,
             identity: CounterIdentity, capacity: Capacity,
             binding: str, expires_at: int, key: bytes, now: int,
             safety_margin: int = 0, page_token_limit: int = 2000) -> CountedPage:
    """Budget exact current complete framing; caller must authorize before/after.

    Nothing here hydrates a source, issues authority, dispatches or archives a result.
    The returned request/hash is the exact candidate the owner must revalidate/adopt.
    """
    integer(page_token_limit, 1, 2000)
    integer(now, 0, 2**63 - 1)
    integer(expires_at, now + 1, now + 900)
    _key(key)
    digest_shape(binding)
    if type(window) is not TextWindow:
        raise MemoryError("invalid_history_range")
    _body_matches(content, window.selection)
    if len(content) != window.body_length:
        raise MemoryError("source_version_unavailable")
    if window.next_start == window.end and window.body_length:
        raise MemoryError("history_window_complete")
    index = _target_index(request, tool_call_id)
    validate_capacity(capacity, connection, request, safety_margin=safety_margin)
    length = min(16000, window.end - window.next_start)
    while True:
        stop = window.next_start + length
        cursor = (encode_cursor(replace(window, next_start=stop), binding=binding,
                                expires_at=expires_at, key=key) if stop < window.end else None)
        page = SourcePage(window.selection, content[window.next_start:stop],
                          window.next_start, stop, window.end, cursor)
        rendered, empty = render(page), render(replace(page, content=""))
        if type(rendered) is not str or type(empty) is not str:
            raise MemoryError("invalid_history_framing")

        def assemble(body):
            messages = list(request.messages)
            messages[index] = replace(messages[index], content=body)
            return replace(request, messages=tuple(messages))

        candidate, baseline = assemble(rendered), assemble(empty)
        count = count_request(candidate, connection, counter, identity)
        baseline_count = count_request(baseline, connection, counter, identity)
        if (count.tokens <= capacity.hard
                and max(0, count.tokens - baseline_count.tokens) <= page_token_limit):
            profile = dict(
                framing_schema="history-page-framing-v1",
                protocol=connection.protocol, model=connection.model,
                config_fingerprint=connection.config_fingerprint,
                context_window_tokens=connection.context_window_tokens,
                connection_max_output_tokens=connection.max_output_tokens,
                request_max_output_tokens=candidate.max_output_tokens,
                counter=asdict(identity), capacity=asdict(capacity),
                safety_margin=safety_margin, page_token_limit=page_token_limit,
            )
            profile_hash = sha256(_json(profile).encode("utf-8")).hexdigest()
            return CountedPage(page, candidate, count, baseline_count,
                               request_hash(candidate), tool_call_id, profile_hash)
        if length <= 1:
            raise MemoryError("context_capacity_too_small")
        length = max(1, length // 2)
