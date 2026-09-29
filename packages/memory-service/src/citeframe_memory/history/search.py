"""Strict query parsing and scope projection; no database or authorization decisions."""
from datetime import datetime

from citeframe_contracts.history import (
    HistoryQuery, SOURCE_KINDS, canonical_id, exact_keys, integer,
)
from citeframe_contracts.memory import MemoryError


def _time(value):
    if type(value) is not str:
        raise MemoryError("invalid_history_query")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise MemoryError("invalid_history_query") from None
    if parsed.utcoffset() is None:
        raise MemoryError("invalid_history_query")
    return parsed


def parse_query(value) -> HistoryQuery:
    exact_keys(value, ("query", "scope"), ("sourceKinds", "from", "to", "limit", "cursor"))
    if type(value["query"]) is not str or not 1 <= len(value["query"]) <= 4000:
        raise MemoryError("invalid_history_query")
    scope = value["scope"]
    if type(scope) is not dict:
        raise MemoryError("invalid_scope")
    kind = scope.get("kind")
    if kind in ("current_branch", "workspace_history"):
        exact_keys(scope, ("kind",))
    elif kind == "thread":
        exact_keys(scope, ("kind", "threadId"), ("leafId",))
        canonical_id(scope["threadId"])
        if "leafId" in scope:
            canonical_id(scope["leafId"])
    else:
        raise MemoryError("invalid_scope")
    kinds = None
    if "sourceKinds" in value:
        raw = value["sourceKinds"]
        if (type(raw) is not list or not raw or any(type(x) is not str or x not in SOURCE_KINDS for x in raw)
                or len(raw) != len(set(raw))):
            raise MemoryError("invalid_history_query")
        kinds = tuple(raw)
        if kind == "current_branch" and kinds != ("chat_message",):
            raise MemoryError("invalid_scope")
    before, after = (_time(value[k]) if k in value else None for k in ("from", "to"))
    if before and after and before > after:
        raise MemoryError("invalid_history_query")
    limit = value.get("limit", 6)
    integer(limit, 1, 20)
    cursor = value.get("cursor")
    if "cursor" in value and (type(cursor) is not str or not 1 <= len(cursor) <= 8192):
        raise MemoryError("invalid_history_query")
    return HistoryQuery(value["query"], kind, scope.get("threadId"), scope.get("leafId"),
                        kinds, before, after, limit, cursor)


def projected_kinds(query: HistoryQuery, *, enabled_kinds: tuple[str, ...]) -> tuple[str, ...]:
    """Select requested kinds from configured corpus kinds, not an ACL permit."""
    if (type(enabled_kinds) is not tuple or len(set(enabled_kinds)) != len(enabled_kinds)
            or any(kind not in SOURCE_KINDS for kind in enabled_kinds)):
        raise MemoryError("invalid_history_shape")
    permitted = tuple(k for k in enabled_kinds if query.scope != "current_branch" or k == "chat_message")
    if query.source_kinds is not None:
        if any(k not in permitted for k in query.source_kinds):
            raise MemoryError("source_kind_not_enabled")
        return query.source_kinds
    return permitted


def project_source_ids(*, corpus_source_ids: frozenset[str],
                       authorized_source_ids: frozenset[str],
                       scope_source_ids: frozenset[str]) -> frozenset[str]:
    """Set intersection only. Inputs must be supplied by the future real native issuer.

    This function neither proves the sets authorized/complete nor inspects body/DB rows.
    Time/kind filtering remains the caller's metadata projection before ranking.
    """
    if any(type(ids) is not frozenset for ids in
           (corpus_source_ids, authorized_source_ids, scope_source_ids)):
        raise MemoryError("invalid_history_shape")
    return corpus_source_ids & authorized_source_ids & scope_source_ids
