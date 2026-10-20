"""Pure history shapes. None of these values establishes native read authority."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

from .compaction import SourceReference
from .memory import MemoryError

SOURCE_KINDS = ("chat_message", "note", "content_unit", "research_artifact")
RUNTIME_MEMBERS = frozenset((
    "schemaVersion", "maxCalls", "maxInputTokens", "maxOutputTokens",
    "maxSummaryCalls", "maxEpisodes", "deadlineAt",
))


def exact_keys(value, required, optional=()):
    if type(value) is not dict or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise MemoryError("invalid_history_shape")


def canonical_id(value):
    if type(value) is not str:
        raise MemoryError("invalid_source_ref")
    try:
        valid = str(UUID(value)) == value
    except ValueError:
        valid = False
    if not valid:
        raise MemoryError("invalid_source_ref")


def digest_shape(value):
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise MemoryError("invalid_source_ref")


def integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise MemoryError("invalid_history_range")


@dataclass(frozen=True)
class TextSpan:
    start: int
    end: int
    kind: Literal["text"] = field(default="text", init=False)

    def __post_init__(self):
        integer(self.start, 0, 2**63 - 1)
        integer(self.end, self.start + 1, 2**63 - 1)


@dataclass(frozen=True)
class LocatorSpan:
    locator_id: str
    kind: Literal["locator"] = field(default="locator", init=False)

    def __post_init__(self):
        canonical_id(self.locator_id)


@dataclass(frozen=True)
class SourceSelection:
    reference: SourceReference
    span: TextSpan | LocatorSpan | None = None

    def __post_init__(self):
        if type(self.reference) is not SourceReference:
            raise MemoryError("invalid_source_ref")
        canonical_id(self.reference.source_id)
        integer(self.reference.version, 1, 2**63 - 1)
        digest_shape(self.reference.sha256)
        if self.span is not None and type(self.span) not in (TextSpan, LocatorSpan):
            raise MemoryError("invalid_source_ref")


@dataclass(frozen=True)
class HistoryPolicy:
    enabled: bool
    allowed_scopes: tuple[str, ...] = ()
    source_kinds: tuple[str, ...] = ()


def parse_history_policy(value) -> HistoryPolicy:
    if type(value) is not dict or type(value.get("enabled")) is not bool:
        raise MemoryError("invalid_history_shape")
    if not value["enabled"]:
        exact_keys(value, ("schemaVersion", "enabled"))
        scopes = kinds = ()
    else:
        exact_keys(value, ("schemaVersion", "enabled", "audience", "allowedScopes", "sourceKinds", "policyVersion"))
        if value["audience"] != "workspace" or value["policyVersion"] != "history-runtime-v1":
            raise MemoryError("invalid_history_shape")
        scopes = _choices(value["allowedScopes"], ("current_branch", "workspace_history"))
        kinds = _choices(value["sourceKinds"], SOURCE_KINDS)
    if value["schemaVersion"] != "history-policy-v1":
        raise MemoryError("invalid_history_shape")
    return HistoryPolicy(value["enabled"], scopes, kinds)


def _choices(value, allowed):
    if (type(value) is not list or not value or any(type(x) is not str or x not in allowed for x in value)
            or len(set(value)) != len(value)):
        raise MemoryError("invalid_history_shape")
    return tuple(value)


def history_member_from_runtime_shape(value) -> HistoryPolicy:
    """Project exact parent/member shape only; #43 still validates runtime scalar values.

    Budget/deadline validity, owner, policy freezing and authorization are deliberately
    not decided here. A successful projection is not a valid runtime-policy receipt.
    """
    if type(value) is not dict:
        raise MemoryError("invalid_history_shape")
    version = value.get("schemaVersion")
    if version == "compaction-policy-v1":
        exact_keys(value, RUNTIME_MEMBERS)
        return HistoryPolicy(False)
    if version == "compaction-policy-v2":
        exact_keys(value, RUNTIME_MEMBERS | {"history"})
        return parse_history_policy(value["history"])
    raise MemoryError("invalid_history_shape")


@dataclass(frozen=True)
class HistoryQuery:
    query: str
    scope: Literal["current_branch", "workspace_history", "thread"]
    thread_id: str | None
    leaf_id: str | None
    source_kinds: tuple[str, ...] | None
    from_time: datetime | None
    to_time: datetime | None
    limit: int
    cursor: str | None


@dataclass(frozen=True)
class SourcePage:
    selection: SourceSelection
    content: str
    start: int
    end: int
    window_end: int
    next_cursor: str | None
