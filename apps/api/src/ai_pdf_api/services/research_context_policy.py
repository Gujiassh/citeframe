"""Per-call Research context packing and deterministic compact/batch policy."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ai_pdf_api.services.research_agent_io_registry import (
    AGENT_RESULT_SCHEMA_VERSION,
    AGENT_RESULT_SCHEMA_VERSION_LEGACY,
    COMPACT_POLICY_VERSION,
    CONTEXT_POLICY_VERSION,
    estimate_json_tokens,
    estimate_text_tokens,
    resolve_registry,
    soft_compact_threshold,
)


class ResearchContextLimitExceeded(ValueError):
    code = "research_context_limit_exceeded"

    def __init__(self, message: str = "Assembled Research context exceeds the frozen per-call limit.") -> None:
        super().__init__(message)
        self.reason_code = self.code


class ResearchProviderOutputIncomplete(ValueError):
    code = "research_provider_output_incomplete"

    def __init__(self, message: str = "Provider response is truncated or incomplete.") -> None:
        super().__init__(message)
        self.reason_code = self.code


@dataclass(frozen=True)
class CompactDecision:
    compact_policy_version: str
    context_policy_version: str
    applied: bool
    mode: str
    original_tokens: int
    compacted_tokens: int
    batches: int
    preserved_claim_ids: tuple[str, ...]
    preserved_evidence_handle_ids: tuple[str, ...]


@dataclass(frozen=True)
class PackedProviderContext:
    messages: list[dict[str, object]]
    request_tokens: int
    max_input_tokens: int
    max_output_tokens: int
    compact: CompactDecision


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, (str, int))]


def extract_mandatory_ids(payload: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    claim_ids: list[str] = []
    evidence_ids: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            if "id" in node and isinstance(node["id"], str):
                claim_ids.append(node["id"])
            if "claimId" in node and isinstance(node["claimId"], str):
                claim_ids.append(node["claimId"])
            for key in ("claimIds", "factClaimIds", "unresolvedClaimIds", "conflictClaimIds"):
                claim_ids.extend(_as_string_list(node.get(key)))
            for key in ("evidenceHandleIds", "evidenceHandles", "handleIds"):
                evidence_ids.extend(_as_string_list(node.get(key)))
            for key in ("evidenceHandle", "evidenceHandleId"):
                handle = node.get(key)
                if isinstance(handle, str):
                    evidence_ids.append(handle)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    # Preserve first-seen order while de-duplicating.
    return list(dict.fromkeys(claim_ids)), list(dict.fromkeys(evidence_ids))


def _batch_list(items: Sequence[Any], *, batch_size: int) -> list[list[Any]]:
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    return [list(items[index : index + batch_size]) for index in range(0, len(items), batch_size)]


COMPACT_FORMAT = "research-typed-batches-v1"
COMPACT_CONTEXT_INSTRUCTION = (
    "Decode research-typed-batches-v1: orderedPayload keeps the input shape; for "
    "each typedBatches fieldPath, map row values to orderedPayload columns in "
    "startIndex order. Return only resultSchema JSON."
)
_COMPACTABLE_FIELDS = {"claims", "subproblems", "evidence"}


def _compact_path_key(path: Sequence[str]) -> str:
    return "/".join(path)


def _columns_fingerprint(columns: Sequence[str]) -> str:
    encoded = json.dumps(list(columns), ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:12]


def _batch_items(
    items: Sequence[Mapping[str, Any]],
    *,
    field_path: tuple[str, ...],
    typed_batches: list[dict[str, Any]],
    column_sets: dict[str, list[str]],
) -> dict[str, Any]:
    columns = sorted({str(field) for item in items for field in item})
    batches = _batch_list(items, batch_size=8)
    leaf = field_path[-1]
    column_set_key = _compact_path_key(field_path)
    column_sets[column_set_key] = _columns_fingerprint(columns)
    for batch_index, batch in enumerate(batches):
        batch_payload: dict[str, Any] = {
            "field": leaf,
            "batchIndex": batch_index,
            "startIndex": batch_index * 8,
            "rows": [[item.get(column) for column in columns] for item in batch],
        }
        if len(field_path) > 1:
            batch_payload["fieldPath"] = list(field_path)
        typed_batches.append(batch_payload)
    metadata: dict[str, Any] = {
        "encoding": "columnar",
        "batchCount": len(batches),
        "columns": columns,
    }
    if len(field_path) > 1:
        metadata["fieldPath"] = list(field_path)
    return metadata


def _compact_value(
    value: Any,
    *,
    field_path: tuple[str, ...],
    typed_batches: list[dict[str, Any]],
    column_sets: dict[str, list[str]],
) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key in value:
            child_path = (*field_path, str(key))
            child = value[key]
            if (
                str(key) in _COMPACTABLE_FIELDS
                and isinstance(child, list)
                and len(child) > 8
                and all(isinstance(item, Mapping) for item in child)
            ):
                result[str(key)] = _batch_items(
                    [dict(item) for item in child],
                    field_path=child_path,
                    typed_batches=typed_batches,
                    column_sets=column_sets,
                )
            else:
                result[str(key)] = _compact_value(
                    child,
                    field_path=child_path,
                    typed_batches=typed_batches,
                    column_sets=column_sets,
                )
        return result
    if isinstance(value, list):
        return [
            _compact_value(
                item,
                field_path=field_path,
                typed_batches=typed_batches,
                column_sets=column_sets,
            )
            for item in value
        ]
    return value


def _compact_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Encode complete context in a deterministic, recursively decodable form."""

    typed_batches: list[dict[str, Any]] = []
    column_sets: dict[str, list[str]] = {}
    ordered = _compact_value(
        payload,
        field_path=(),
        typed_batches=typed_batches,
        column_sets=column_sets,
    )
    compacted: dict[str, Any] = {
        "format": COMPACT_FORMAT,
        "schemaFields": sorted(str(key) for key in payload.keys()),
        "branchScope": dict(payload["branchScope"]) if isinstance(payload.get("branchScope"), Mapping) else {},
        "orderedPayload": ordered,
        "typedBatches": typed_batches,
        "columnSets": column_sets,
    }
    if not compacted["branchScope"] and isinstance(payload.get("subproblem"), Mapping):
        subproblem = payload["subproblem"]
        compacted["branchScope"] = {
            "question": subproblem.get("question"),
            "assetIds": subproblem.get("assetIds"),
        }
    if isinstance(payload.get("sourceFingerprints"), list):
        compacted["sourceFingerprints"] = list(payload["sourceFingerprints"])
    return compacted


def _set_field_path(root: dict[str, Any], path: Sequence[str], value: Any) -> None:
    if not path:
        raise ValueError("compact field path is empty")
    parent: Any = root
    for key in path[:-1]:
        if not isinstance(parent, dict) or key not in parent:
            raise ValueError("compact field path is invalid")
        parent = parent[key]
    if not isinstance(parent, dict):
        raise ValueError("compact field path is invalid")
    parent[path[-1]] = value


def _is_nonnegative_int(value: object) -> bool:
    return type(value) is int and value >= 0


def _collect_column_metadata(
    value: Any,
    *,
    path: tuple[str, ...] = (),
    result: dict[tuple[str, ...], Mapping[str, Any]] | None = None,
) -> dict[tuple[str, ...], Mapping[str, Any]]:
    metadata = result if result is not None else {}
    if isinstance(value, Mapping):
        if value.get("encoding") == "columnar":
            if not path or path in metadata:
                raise ValueError("compact metadata path duplicated")
            metadata[path] = value
            return metadata
        for key, child in value.items():
            _collect_column_metadata(child, path=(*path, str(key)), result=metadata)
    return metadata


def decode_compact_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstruct typed compact context only after validating all metadata."""

    if payload.get("format") != COMPACT_FORMAT:
        raise ValueError("compact format mismatch")
    ordered = payload.get("orderedPayload")
    batches = payload.get("typedBatches")
    column_sets = payload.get("columnSets")
    if not isinstance(ordered, dict) or not isinstance(batches, list) or not isinstance(column_sets, Mapping):
        raise ValueError("compact payload malformed")
    decoded = json.loads(json.dumps(ordered, ensure_ascii=True))
    metadata_by_path = _collect_column_metadata(decoded)
    expected_column_set_keys = {_compact_path_key(path) for path in metadata_by_path}
    actual_column_set_keys = set(column_sets)
    if actual_column_set_keys != expected_column_set_keys or any(
        not isinstance(value, str) for value in column_sets.values()
    ):
        raise ValueError("compact column sets mismatch")

    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for path, metadata in metadata_by_path.items():
        allowed_metadata_keys = {"encoding", "batchCount", "columns"}
        if len(path) > 1:
            allowed_metadata_keys.add("fieldPath")
        if set(metadata) != allowed_metadata_keys:
            raise ValueError("compact metadata malformed")
        if metadata.get("encoding") != "columnar":
            raise ValueError("compact metadata malformed")
        batch_count = metadata.get("batchCount")
        columns = metadata.get("columns")
        if not _is_nonnegative_int(batch_count) or batch_count < 1:
            raise ValueError("compact batch count malformed")
        if not isinstance(columns, list) or not all(isinstance(item, str) for item in columns):
            raise ValueError("compact batch columns malformed")
        if len(columns) != len(set(columns)):
            raise ValueError("compact batch columns malformed")
        if len(path) > 1 and metadata.get("fieldPath") != list(path):
            raise ValueError("compact metadata path malformed")
        if len(path) == 1 and "fieldPath" in metadata:
            raise ValueError("compact metadata path malformed")
        column_set_key = _compact_path_key(path)
        encoded_columns = column_sets.get(column_set_key)
        if encoded_columns != _columns_fingerprint(columns):
            raise ValueError("compact column sets mismatch")
        grouped[path] = []

    for batch in batches:
        if not isinstance(batch, Mapping):
            raise ValueError("compact batch malformed")
        field = batch.get("field")
        field_path = batch.get("fieldPath")
        if field_path is None:
            path = (field,) if isinstance(field, str) else None
        else:
            path = tuple(field_path) if isinstance(field_path, list) else None
        if not path or not all(isinstance(item, str) for item in path):
            raise ValueError("compact batch path malformed")
        if path not in metadata_by_path or field != path[-1]:
            raise ValueError("compact batch path malformed")
        expected_batch_keys = {"field", "batchIndex", "startIndex", "rows"}
        if len(path) > 1:
            expected_batch_keys.add("fieldPath")
        if set(batch) != expected_batch_keys:
            raise ValueError("compact batch metadata malformed")
        batch_index = batch.get("batchIndex")
        start_index = batch.get("startIndex")
        rows = batch.get("rows")
        if not _is_nonnegative_int(batch_index) or not _is_nonnegative_int(start_index):
            raise ValueError("compact batch index malformed")
        if not isinstance(rows, list) or not rows:
            raise ValueError("compact batch rows malformed")
        columns = metadata_by_path[path].get("columns")
        if not isinstance(columns, list):
            raise ValueError("compact batch columns malformed")
        if any(not isinstance(row, list) for row in rows):
            raise ValueError("compact batch rows malformed")
        if any(len(row) != len(columns) for row in rows):
            raise ValueError("compact batch row width malformed")
        grouped[path].append(
            {
                "batchIndex": batch_index,
                "startIndex": start_index,
                "rows": rows,
            }
        )

    decoded_values: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for path, path_batches in grouped.items():
        metadata = metadata_by_path[path]
        batch_count = metadata["batchCount"]
        if len(path_batches) != batch_count:
            raise ValueError("compact batch count mismatch")
        indexes = [item["batchIndex"] for item in path_batches]
        if sorted(indexes) != list(range(batch_count)):
            raise ValueError("compact batch index sequence malformed")
        ordered_batches = sorted(path_batches, key=lambda item: item["batchIndex"])
        expected_start = 0
        values: list[dict[str, Any]] = []
        columns = metadata["columns"]
        for batch_index, batch in enumerate(ordered_batches):
            rows = batch["rows"]
            if batch["startIndex"] != expected_start:
                raise ValueError("compact batch start sequence malformed")
            if batch_index < batch_count - 1 and len(rows) != 8:
                raise ValueError("compact batch width malformed")
            if len(rows) > 8:
                raise ValueError("compact batch width malformed")
            values.extend(dict(zip(columns, row, strict=True)) for row in rows)
            expected_start += len(rows)
        decoded_values[path] = values

    for path, values in decoded_values.items():
        _set_field_path(decoded, path, values)
    return decoded


def pack_provider_messages(
    *,
    system_text: str,
    user_payload: Mapping[str, Any],
    max_input_tokens: int,
    max_output_tokens: int,
    context_policy_version: str = CONTEXT_POLICY_VERSION,
    compact_policy_version: str = COMPACT_POLICY_VERSION,
) -> PackedProviderContext:
    if max_input_tokens < 1 or max_output_tokens < 1:
        raise ValueError("per-call token limits must be >= 1")

    resolve_registry(
        agent_result_schema_version=(
            AGENT_RESULT_SCHEMA_VERSION
            if context_policy_version == CONTEXT_POLICY_VERSION
            else AGENT_RESULT_SCHEMA_VERSION_LEGACY
        ),
        context_policy_version=context_policy_version,
        compact_policy_version=compact_policy_version,
        for_new_run=False,
    )

    original_tokens = estimate_text_tokens(system_text) + estimate_json_tokens(user_payload)
    claim_ids, evidence_ids = extract_mandatory_ids(user_payload)
    payload: Mapping[str, Any] = user_payload
    packed_system_text = system_text
    applied = False
    mode = "none"
    batches = 1
    threshold = soft_compact_threshold(max_input_tokens, policy_version=context_policy_version)

    if original_tokens > threshold:
        candidate = _compact_payload(user_payload)
        candidate_system_text = f"{system_text.rstrip()}\n\n{COMPACT_CONTEXT_INSTRUCTION}"
        candidate_tokens = estimate_text_tokens(candidate_system_text) + estimate_json_tokens(candidate)
        # Compaction is an optimization, never a reason to reject an input that
        # fit before. If the typed wrapper expands it, send the original shape.
        if candidate_tokens < original_tokens:
            payload = candidate
            packed_system_text = candidate_system_text
            applied = True
            mode = "typed_compact"
            batches = len(candidate.get("typedBatches", ())) or 1

    packed_tokens = estimate_text_tokens(packed_system_text) + estimate_json_tokens(payload)
    if packed_tokens > max_input_tokens:
        raise ResearchContextLimitExceeded(
            f"Assembled context uses {packed_tokens} tokens against maxInputTokens={max_input_tokens}."
        )

    messages: list[dict[str, object]] = [
        {"role": "system", "content": packed_system_text},
        {"role": "user", "content": payload if isinstance(payload, dict) else dict(payload)},
    ]
    if not isinstance(messages[1]["content"], str):
        messages[1]["content"] = json.dumps(
            messages[1]["content"],
            ensure_ascii=True,
            separators=(",", ":"),
        )

    decision = CompactDecision(
        compact_policy_version=compact_policy_version,
        context_policy_version=context_policy_version,
        applied=applied,
        mode=mode,
        original_tokens=original_tokens,
        compacted_tokens=packed_tokens,
        batches=batches,
        preserved_claim_ids=tuple(claim_ids),
        preserved_evidence_handle_ids=tuple(evidence_ids),
    )
    return PackedProviderContext(
        messages=messages,
        request_tokens=packed_tokens,
        max_input_tokens=max_input_tokens,
        max_output_tokens=max_output_tokens,
        compact=decision,
    )


def assert_provider_output_complete(
    output: str,
    *,
    max_output_tokens: int,
    finish_reason: str | None = None,
    incomplete: bool | None = None,
) -> None:
    if incomplete is True:
        raise ResearchProviderOutputIncomplete()
    if finish_reason in {"length", "max_tokens", "max_output_tokens", "incomplete"}:
        raise ResearchProviderOutputIncomplete()
    tokens = estimate_text_tokens(output)
    if tokens > max_output_tokens:
        raise ResearchProviderOutputIncomplete(
            f"Provider output uses {tokens} tokens against maxOutputTokens={max_output_tokens}."
        )
    # Empty output is invalid but not an incomplete truncation signal; callers map that separately.
