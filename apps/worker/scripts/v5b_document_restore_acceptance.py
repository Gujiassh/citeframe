#!/usr/bin/env python3
"""V5-B Document restore acceptance helper.

Captures a scoped Document restore oracle for one workspace asset and verifies
before/after equality after backup/restore. Live mode requires explicit scope
identifiers plus PostgreSQL and MinIO evidence. Fixture mode remains an offline
shape check and must never be treated as a live restore pass.
"""

from __future__ import annotations

import argparse
import re
import json
import os
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

SCHEMA_VERSION = "v5b-document-restore-acceptance-v1"
EVIDENCE_MODE_LIVE = "live"
EVIDENCE_MODE_FIXTURE = "fixture-shape-only"
EVIDENCE_MODE_SKIPPED = "skipped"
EVIDENCE_MODE_BLOCKED = "blocked"

DOCUMENT_TYPED_TABLES = (
    "document_normalized_contents",
    "document_blocks",
    "document_locator_details",
)
CATALOG_TABLES = (
    "asset_types",
    "representation_types",
    "content_unit_types",
    "locator_types",
)
# Canonical catalog metadata for Document restore. Comparison is order-independent
# via sorted row projection; semantic hash always uses the canonical form below.
REQUIRED_CATALOG = {
    "asset_types": (
        {
            "kind": "document",
            "enabled": True,
            "contract_version": 1,
        },
    ),
    "representation_types": (
        {
            "kind": "document_source",
            "asset_kind": "document",
            "contract_version": 1,
        },
        {
            "kind": "document_normalized",
            "asset_kind": "document",
            "contract_version": 1,
        },
    ),
    "content_unit_types": (
        {
            "kind": "document_block",
            "asset_kind": "document",
            "contract_version": 1,
        },
        {
            "kind": "document_text_chunk",
            "asset_kind": "document",
            "contract_version": 1,
        },
    ),
    "locator_types": (
        {
            "kind": "document_anchor",
            "detail_family": "record",
            "contract_version": 1,
        },
    ),
}
DOCUMENT_ANCHOR_DETAIL_FAMILY = "record"
DOCUMENT_CONTRACT_VERSION = 1
REQUIRED_SCOPED_LINK_TABLES = (
    "message_citations",
    "note_sources",
)
# Every live restore snapshot must carry these scoped collections explicitly.
# Missing keys are not normalized to empty lists during live verification.
REQUIRED_SCOPED_ROW_COLLECTIONS = (
    "assets",
    "asset_representations",
    "document_normalized_contents",
    "document_blocks",
    "content_units",
    "content_unit_embeddings",
    "evidence_locators",
    "document_locator_details",
    "message_citations",
    "note_sources",
)
CATALOG_TABLE_FIELDS = {
    "asset_types": ("kind", "enabled", "contract_version"),
    "representation_types": ("kind", "asset_kind", "contract_version"),
    "content_unit_types": ("kind", "asset_kind", "contract_version"),
    "locator_types": ("kind", "detail_family", "contract_version"),
}

# Canonical asset object prefix used by Document modality backups.
ASSET_OBJECT_PREFIX_TEMPLATE = "workspaces/{workspace_id}/assets/{asset_id}/"

# Stable semantic fields included in the restore oracle hash. Timestamps and
# raw embedding vectors are intentionally excluded so restore equality focuses
# on durable Document identity and checksum metadata.
ASSET_FIELDS = (
    "id",
    "workspace_id",
    "asset_kind",
    "title",
    "source_filename",
    "object_key",
    "mime_type",
    "byte_size",
    "source_sha256",
    "status",
    "current_processing_generation",
    "current_index_version",
    "deleted_at",
)
REPRESENTATION_FIELDS = (
    "id",
    "workspace_id",
    "asset_id",
    "representation_kind",
    "processing_generation",
    "generator_provider",
    "generator_model",
    "generator_version",
    "object_key",
    "content_sha256",
)
NORMALIZED_CONTENT_FIELDS = (
    "representation_id",
    "format",
    "parser_version",
    "normalization_version",
    "normalized_text",
    "content_sha256",
    "block_count",
)
DOCUMENT_BLOCK_FIELDS = (
    "id",
    "representation_id",
    "block_id",
    "block_order",
    "block_kind",
    "heading_level",
    "heading_path",
    "char_start",
    "char_end",
    "text_sha256",
    "text_content",
    "normalization_version",
)
CONTENT_UNIT_FIELDS = (
    "id",
    "workspace_id",
    "asset_id",
    "representation_id",
    "source_locator_id",
    "unit_kind",
    "unit_order",
    "text_content",
    "token_count",
    "char_start",
    "char_end",
    "index_version",
)
EMBEDDING_IDENTITY_FIELDS = (
    "id",
    "workspace_id",
    "asset_id",
    "content_unit_id",
    "processing_generation",
    "index_version",
    "is_current",
    "embedding_space",
    "provider",
    "model",
    "dimensions",
    "version",
)
EVIDENCE_LOCATOR_FIELDS = (
    "id",
    "workspace_id",
    "asset_id",
    "locator_kind",
    "locator_version",
    "processing_generation_snapshot",
    "representation_id_snapshot",
)
DOCUMENT_LOCATOR_DETAIL_FIELDS = (
    "locator_id",
    "block_id",
    "block_kind",
    "heading_path",
    "char_start",
    "char_end",
    "text_sha256",
    "normalization_version",
)
CITATION_FIELDS = (
    "id",
    "workspace_id",
    "message_id",
    "evidence_locator_id",
    "asset_id",
    "citation_index",
    "asset_kind_snapshot",
    "asset_title_snapshot",
    "excerpt_snapshot",
    "processing_generation_snapshot",
    "representation_id_snapshot",
    "parser_version_snapshot",
    "index_version_snapshot",
)
NOTE_SOURCE_FIELDS = (
    "id",
    "workspace_id",
    "note_id",
    "evidence_locator_id",
    "asset_id",
    "source_order",
    "message_citation_id",
    "asset_kind_snapshot",
    "asset_title_snapshot",
    "excerpt_snapshot",
    "processing_generation_snapshot",
    "representation_id_snapshot",
    "parser_version_snapshot",
    "index_version_snapshot",
)



SCOPED_ROW_FIELD_SETS: dict[str, tuple[str, ...]] = {
    "assets": ASSET_FIELDS,
    "asset_representations": REPRESENTATION_FIELDS,
    "document_normalized_contents": NORMALIZED_CONTENT_FIELDS,
    "document_blocks": DOCUMENT_BLOCK_FIELDS,
    "content_units": CONTENT_UNIT_FIELDS,
    "content_unit_embeddings": EMBEDDING_IDENTITY_FIELDS,
    "evidence_locators": EVIDENCE_LOCATOR_FIELDS,
    "document_locator_details": DOCUMENT_LOCATOR_DETAIL_FIELDS,
    "message_citations": CITATION_FIELDS,
    "note_sources": NOTE_SOURCE_FIELDS,
}

HISTORICAL_SOURCE_VERSION_FIELDS = (
    "processing_generation_snapshot",
    "representation_id_snapshot",
    "parser_version_snapshot",
    "index_version_snapshot",
)

SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")

DOCUMENT_MARKDOWN_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs/fixtures/document-modality/markdown-note.fixture.json"
)


def _is_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and SHA256_HEX_RE.fullmatch(value) is not None


def _is_nonneg_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _row_missing_required_keys(row: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    return [field for field in fields if field not in row]


def _canonicalize_historical_evidence(evidence: dict[str, Any] | None) -> dict[str, Any]:
    """Order-independent historical evidence projection for semantic equality."""
    if not isinstance(evidence, dict):
        return {}

    def _id_list(key: str) -> list[str]:
        values = evidence.get(key)
        if not isinstance(values, list):
            return []
        return sorted(str(item) for item in values if isinstance(item, (str, int)))

    def _version_rows(key: str) -> list[dict[str, Any]]:
        values = evidence.get(key)
        if not isinstance(values, list):
            return []
        projected: list[dict[str, Any]] = []
        for row in values:
            if not isinstance(row, dict):
                continue
            projected.append(
                {
                    "id": row.get("id"),
                    **{field: row.get(field) for field in HISTORICAL_SOURCE_VERSION_FIELDS},
                }
            )
        return _sort_rows(projected)

    return {
        "sourceAvailable": evidence.get("sourceAvailable"),
        "retainedLocatorIds": _id_list("retainedLocatorIds"),
        "retainedCitationIds": _id_list("retainedCitationIds"),
        "retainedNoteSourceIds": _id_list("retainedNoteSourceIds"),
        "citationSourceVersions": _version_rows("citationSourceVersions"),
        "noteSourceSourceVersions": _version_rows("noteSourceSourceVersions"),
    }


def _build_historical_evidence(scoped_rows: dict[str, Any]) -> dict[str, Any]:
    """Derive durable historical evidence from scoped Document rows.

    sourceAvailable follows Asset.deleted_at: available only when the scoped asset
    row exists and deleted_at is null. Locator/citation/note-source IDs and source
    version snapshots remain even after soft-delete.
    """
    assets = scoped_rows.get("assets") if isinstance(scoped_rows.get("assets"), list) else []
    asset_row = next((row for row in assets if isinstance(row, dict)), None)
    source_available = bool(
        asset_row is not None and asset_row.get("deleted_at") is None
    )

    def _ids(table: str, field: str = "id") -> list[str]:
        rows = scoped_rows.get(table) if isinstance(scoped_rows.get(table), list) else []
        out: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            value = row.get(field)
            if isinstance(value, str) and value:
                out.append(value)
        return sorted(out)

    def _source_versions(table: str) -> list[dict[str, Any]]:
        rows = scoped_rows.get(table) if isinstance(scoped_rows.get(table), list) else []
        projected: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_id = row.get("id")
            if not isinstance(row_id, str) or not row_id:
                continue
            projected.append(
                {
                    "id": row_id,
                    **{field: row.get(field) for field in HISTORICAL_SOURCE_VERSION_FIELDS},
                }
            )
        return _sort_rows(projected)

    return {
        "sourceAvailable": source_available,
        "retainedLocatorIds": _ids("evidence_locators"),
        "retainedCitationIds": _ids("message_citations"),
        "retainedNoteSourceIds": _ids("note_sources"),
        "citationSourceVersions": _source_versions("message_citations"),
        "noteSourceSourceVersions": _source_versions("note_sources"),
    }


def _load_document_markdown_fixture() -> dict[str, Any]:
    return json.loads(DOCUMENT_MARKDOWN_FIXTURE_PATH.read_text(encoding="utf-8"))


def _id(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"https://citeframe.local/v5b-document/{name}"))


IDS = {
    name: _id(name)
    for name in (
        "user",
        "workspace",
        "document-asset",
        "pdf-asset",
        "image-asset",
        "normalized-representation",
        "paragraph-locator",
        "citation",
        "note-source",
    )
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="V5-B Document restore acceptance helper")
    sub = parser.add_subparsers(dest="command", required=True)

    snapshot = sub.add_parser("snapshot", help="Capture restore-oriented snapshot shape")
    snapshot.add_argument("--output", type=Path, required=True)
    snapshot.add_argument(
        "--mode",
        choices=("live", "fixture"),
        default="live",
        help="live attempts PostgreSQL/MinIO; fixture emits deterministic offline shape",
    )
    snapshot.add_argument(
        "--workspace-id",
        default=None,
        help="Scoped workspace id for live mode (or V5B_WORKSPACE_ID)",
    )
    snapshot.add_argument(
        "--asset-id",
        default=None,
        help="Scoped asset id for live mode (or V5B_ASSET_ID)",
    )

    snapshot.add_argument(
        "--allow-empty-evidence-links",
        action="store_true",
        help="Allow live assets without message_citations or note_sources",
    )

    verify = sub.add_parser("verify", help="Compare before/after live restore snapshots")
    verify.add_argument("--before", type=Path, required=True)
    verify.add_argument("--after", type=Path, required=True)
    verify.add_argument("--output", type=Path)

    tables = sub.add_parser("check-tables", help="Assert Document typed tables exist")
    tables.add_argument("--output", type=Path)
    tables.add_argument("--workspace-id", default=None)
    tables.add_argument("--asset-id", default=None)

    return parser.parse_args()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )


def _semantic_sha256(value: object) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _project_row(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: row.get(field) for field in fields}


def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda item: _canonical_bytes(item))


def _asset_object_prefix(workspace_id: str, asset_id: str) -> str:
    return ASSET_OBJECT_PREFIX_TEMPLATE.format(workspace_id=workspace_id, asset_id=asset_id)


def _resolve_scope(workspace_id: str | None, asset_id: str | None) -> tuple[str | None, str | None]:
    resolved_workspace = workspace_id or os.environ.get("V5B_WORKSPACE_ID")
    resolved_asset = asset_id or os.environ.get("V5B_ASSET_ID")
    return resolved_workspace, resolved_asset


def _catalog_kind_list(rows: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> list[str]:
    return [str(row["kind"]) for row in rows]


def _canonical_catalog_rows(
    table: str, rows: list[dict[str, Any]] | tuple[dict[str, Any], ...]
) -> list[dict[str, Any]]:
    fields = CATALOG_TABLE_FIELDS[table]
    projected = [_project_row(dict(row), fields) for row in rows]
    return _sort_rows(projected)


def _canonicalize_catalog(catalog: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize catalog metadata for order-independent semantic equality."""
    if not isinstance(catalog, dict):
        return {}

    required_in = catalog.get("requiredCatalog") or {}
    required_out: dict[str, list[dict[str, Any]]] = {}
    if isinstance(required_in, dict):
        for table, rows in required_in.items():
            if table in CATALOG_TABLE_FIELDS and isinstance(rows, list):
                required_out[table] = _canonical_catalog_rows(table, rows)
            elif isinstance(rows, list):
                required_out[table] = _sort_rows([dict(row) for row in rows if isinstance(row, dict)])
            else:
                required_out[table] = rows  # type: ignore[assignment]

    locator = catalog.get("documentLocator")
    if isinstance(locator, dict):
        locator = {
            "kind": locator.get("kind"),
            "detail_family": locator.get("detail_family"),
            "contract_version": locator.get("contract_version"),
        }
    else:
        locator = locator

    representation_kinds = catalog.get("representationKinds")
    if representation_kinds is None and "representation_types" in required_out:
        representation_kinds = _catalog_kind_list(required_out["representation_types"])
    content_unit_kinds = catalog.get("contentUnitKinds")
    if content_unit_kinds is None and "content_unit_types" in required_out:
        content_unit_kinds = _catalog_kind_list(required_out["content_unit_types"])

    return {
        "documentEnabled": catalog.get("documentEnabled"),
        "documentLocator": locator,
        "requiredCatalog": required_out,
        "representationKinds": sorted(str(kind) for kind in (representation_kinds or [])),
        "contentUnitKinds": sorted(str(kind) for kind in (content_unit_kinds or [])),
    }


def _catalogs_equal(left: Any, right: Any) -> bool:
    return _canonicalize_catalog(left if isinstance(left, dict) else {}) == _canonicalize_catalog(
        right if isinstance(right, dict) else {}
    )


def _canonical_semantic_body(payload: dict[str, Any]) -> dict[str, Any]:
    """Canonical restore equality body shared by snapshot hashing and verify.

    Missing fields stay missing (None) rather than soft-defaulting to {} / [].
    Live validation rejects incomplete payloads before equality/hash pass.
    """
    catalog = payload.get("catalog") if isinstance(payload.get("catalog"), dict) else payload.get("catalog")
    historical = payload.get("historicalEvidence")
    return {
        "workspaceId": payload.get("workspaceId"),
        "assetId": payload.get("assetId"),
        "objectPrefix": payload.get("objectPrefix"),
        "requireEvidenceLinks": payload.get("requireEvidenceLinks", True),
        "scopedRows": payload.get("scopedRows"),
        "objects": payload.get("objects"),
        "typedTables": payload.get("typedTables"),
        "catalog": _canonicalize_catalog(catalog) if isinstance(catalog, dict) else catalog,
        "historicalEvidence": (
            _canonicalize_historical_evidence(historical)
            if isinstance(historical, dict)
            else historical
        ),
    }


def _compute_semantic_sha256(payload: dict[str, Any]) -> str:
    return _semantic_sha256(_canonical_semantic_body(payload))


def _required_catalog_values() -> dict[str, list[dict[str, Any]]]:
    return {
        table: _canonical_catalog_rows(table, list(rows))
        for table, rows in REQUIRED_CATALOG.items()
    }


def _catalog_rows_match(
    table: str,
    actual: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    expected: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> bool:
    if actual is None:
        return False
    return _canonical_catalog_rows(table, list(actual)) == _canonical_catalog_rows(
        table, list(expected)
    )


def _fixture_catalog() -> dict[str, Any]:
    required = _required_catalog_values()
    return {
        "documentEnabled": True,
        "documentLocator": {
            "kind": "document_anchor",
            "detail_family": DOCUMENT_ANCHOR_DETAIL_FAMILY,
            "contract_version": DOCUMENT_CONTRACT_VERSION,
        },
        "requiredCatalog": required,
        "representationKinds": _catalog_kind_list(required["representation_types"]),
        "contentUnitKinds": _catalog_kind_list(required["content_unit_types"]),
    }


def _fixture_typed_tables(scoped_rows: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    typed: dict[str, dict[str, Any]] = {}
    for table in DOCUMENT_TYPED_TABLES:
        typed[table] = {
            "present": True,
            "rowCount": len(scoped_rows.get(table, [])),
        }
    for table in CATALOG_TABLES:
        typed[table] = {
            "present": True,
            "rowCount": len(REQUIRED_CATALOG[table]),
        }
    for table in REQUIRED_SCOPED_LINK_TABLES:
        typed[table] = {
            "present": True,
            "rowCount": len(scoped_rows.get(table, [])),
            "requiredColumnsPresent": True,
        }
    return typed


def _missing_typed_or_catalog_tables(typed: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for table in (*DOCUMENT_TYPED_TABLES, *CATALOG_TABLES, *REQUIRED_SCOPED_LINK_TABLES):
        entry = typed.get(table)
        if not (isinstance(entry, dict) and entry.get("present") is True):
            missing.append(table)
            continue
        if table in REQUIRED_SCOPED_LINK_TABLES and entry.get("requiredColumnsPresent") is not True:
            missing.append(table)
    return missing


def _catalog_requirement_mismatches(catalog: dict[str, Any]) -> list[str]:
    mismatches: list[str] = []
    if catalog.get("documentEnabled") is not True:
        mismatches.append("catalog.documentEnabled")

    locator = catalog.get("documentLocator") or {}
    if locator.get("kind") != "document_anchor":
        mismatches.append("catalog.documentLocator.kind")
    if locator.get("detail_family") != DOCUMENT_ANCHOR_DETAIL_FAMILY:
        mismatches.append("catalog.documentLocator.detail_family")
    if locator.get("contract_version") != DOCUMENT_CONTRACT_VERSION:
        mismatches.append("catalog.documentLocator.contract_version")

    required = catalog.get("requiredCatalog") or {}
    expected = _required_catalog_values()
    for table, expected_rows in expected.items():
        actual = required.get(table)
        if not _catalog_rows_match(table, actual, expected_rows):
            mismatches.append(f"catalog.requiredCatalog.{table}")
    return mismatches


def _non_empty_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _live_scope_field_mismatches(payload: dict[str, Any]) -> list[str]:
    """Reject missing/empty live identity and scoped evidence without soft defaults.

    Live verify must not treat absent workspace/asset/prefix/scopedRows/objects as
    empty-equivalent bodies that can still pass after hash recomputation.
    """
    mismatches: list[str] = []

    workspace_id = _non_empty_str(payload.get("workspaceId"))
    if workspace_id is None:
        mismatches.append("workspaceId")

    asset_id = _non_empty_str(payload.get("assetId"))
    if asset_id is None:
        mismatches.append("assetId")

    object_prefix = payload.get("objectPrefix")
    expected_prefix = (
        _asset_object_prefix(workspace_id, asset_id)
        if workspace_id is not None and asset_id is not None
        else None
    )
    if expected_prefix is None or object_prefix != expected_prefix:
        mismatches.append("objectPrefix")

    if "scopedRows" not in payload or not isinstance(payload.get("scopedRows"), dict):
        mismatches.append("scopedRows")
    else:
        scoped_rows = payload["scopedRows"]
        for table in REQUIRED_SCOPED_ROW_COLLECTIONS:
            if table not in scoped_rows or not isinstance(scoped_rows.get(table), list):
                mismatches.append(f"scopedRows.{table}")

    if "objects" not in payload or not isinstance(payload.get("objects"), list):
        mismatches.append("objects")

    if "historicalEvidence" not in payload or not isinstance(
        payload.get("historicalEvidence"), dict
    ):
        mismatches.append("historicalEvidence")

    return mismatches


def _live_scoped_rows_payload_mismatches(
    scoped_rows: dict[str, Any],
    *,
    workspace_id: str,
    asset_id: str,
    require_evidence_links: bool = True,
) -> list[str]:
    """Strict structural validation of live scoped Document rows."""
    mismatches: list[str] = []

    for table, fields in SCOPED_ROW_FIELD_SETS.items():
        if table not in scoped_rows:
            mismatches.append(f"scopedRows.{table}")
            continue
        rows = scoped_rows[table]
        if not isinstance(rows, list):
            mismatches.append(f"scopedRows.{table}")
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                mismatches.append(f"scopedRows.{table}[{index}]")
                continue
            missing = _row_missing_required_keys(row, fields)
            if missing:
                mismatches.append(f"scopedRows.{table}[{index}].fields")
                continue
            # Absent fields must not be silently projected as None for equality.
            for field in fields:
                if field in row and row[field] is None and field not in {
                    "deleted_at",
                    "generator_provider",
                    "generator_model",
                    "heading_level",
                    "source_locator_id",
                    "message_citation_id",
                    "token_count",
                }:
                    # Many optional nullable columns remain allowed as explicit None.
                    # Required identity/kind fields below are checked separately.
                    pass

    assets = scoped_rows.get("assets")
    if not isinstance(assets, list):
        return mismatches

    matching_assets = [
        row
        for row in assets
        if isinstance(row, dict)
        and row.get("id") == asset_id
        and row.get("workspace_id") == workspace_id
        and row.get("asset_kind") == "document"
    ]
    if len(assets) != 1 or len(matching_assets) != 1:
        mismatches.append("scopedRows.assets.identity")
        asset_row: dict[str, Any] | None = matching_assets[0] if matching_assets else None
    else:
        asset_row = matching_assets[0]

    asset_deleted = bool(asset_row is not None and asset_row.get("deleted_at") is not None)

    def _collect_ids(table: str, *, require_scope: bool = True) -> set[str]:
        ids: set[str] = set()
        rows = scoped_rows.get(table)
        if not isinstance(rows, list):
            return ids
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            row_id = _non_empty_str(row.get("id"))
            if row_id is None:
                mismatches.append(f"scopedRows.{table}[{index}].id")
                continue
            if require_scope:
                if row.get("workspace_id") != workspace_id or row.get("asset_id") != asset_id:
                    mismatches.append(f"scopedRows.{table}[{index}].scope")
                    continue
            ids.add(row_id)
        return ids

    representation_ids = _collect_ids("asset_representations")
    if not representation_ids:
        mismatches.append("scopedRows.asset_representations.min")

    normalized = scoped_rows.get("document_normalized_contents")
    if isinstance(normalized, list):
        if not normalized:
            mismatches.append("scopedRows.document_normalized_contents.min")
        for index, row in enumerate(normalized):
            if not isinstance(row, dict):
                continue
            if row.get("representation_id") not in representation_ids:
                mismatches.append(f"scopedRows.document_normalized_contents[{index}].parent")
            if not _is_sha256_hex(row.get("content_sha256")):
                mismatches.append(f"scopedRows.document_normalized_contents[{index}].content_sha256")

    blocks = scoped_rows.get("document_blocks")
    block_ids: set[str] = set()
    if isinstance(blocks, list):
        if not blocks:
            mismatches.append("scopedRows.document_blocks.min")
        for index, row in enumerate(blocks):
            if not isinstance(row, dict):
                continue
            if row.get("representation_id") not in representation_ids:
                mismatches.append(f"scopedRows.document_blocks[{index}].parent")
            block_id = _non_empty_str(row.get("block_id"))
            if block_id is None:
                mismatches.append(f"scopedRows.document_blocks[{index}].block_id")
            else:
                block_ids.add(block_id)
            char_start = row.get("char_start")
            char_end = row.get("char_end")
            if not (
                _is_nonneg_int(char_start)
                and _is_nonneg_int(char_end)
                and isinstance(char_start, int)
                and isinstance(char_end, int)
                and char_end >= char_start
            ):
                mismatches.append(f"scopedRows.document_blocks[{index}].range")
            if not _is_sha256_hex(row.get("text_sha256")):
                mismatches.append(f"scopedRows.document_blocks[{index}].text_sha256")
            if not _is_nonneg_int(row.get("block_order")):
                mismatches.append(f"scopedRows.document_blocks[{index}].block_order")
            if not _non_empty_str(row.get("block_kind")):
                mismatches.append(f"scopedRows.document_blocks[{index}].block_kind")

    content_units = scoped_rows.get("content_units")
    content_unit_ids: set[str] = set()
    if isinstance(content_units, list):
        if not content_units:
            mismatches.append("scopedRows.content_units.min")
        for index, row in enumerate(content_units):
            if not isinstance(row, dict):
                continue
            if row.get("workspace_id") != workspace_id or row.get("asset_id") != asset_id:
                mismatches.append(f"scopedRows.content_units[{index}].scope")
            if row.get("representation_id") not in representation_ids:
                mismatches.append(f"scopedRows.content_units[{index}].parent")
            unit_kind = row.get("unit_kind")
            if unit_kind != "document_text_chunk":
                mismatches.append(f"scopedRows.content_units[{index}].unit_kind")
            if unit_kind == "document_block":
                mismatches.append(f"scopedRows.content_units[{index}].document_block")
            unit_id = _non_empty_str(row.get("id"))
            if unit_id is not None:
                content_unit_ids.add(unit_id)
            char_start = row.get("char_start")
            char_end = row.get("char_end")
            if char_start is not None or char_end is not None:
                if not (
                    _is_nonneg_int(char_start)
                    and _is_nonneg_int(char_end)
                    and isinstance(char_start, int)
                    and isinstance(char_end, int)
                    and char_end >= char_start
                ):
                    mismatches.append(f"scopedRows.content_units[{index}].range")

    embeddings = scoped_rows.get("content_unit_embeddings")
    if isinstance(embeddings, list):
        for index, row in enumerate(embeddings):
            if not isinstance(row, dict):
                continue
            if row.get("workspace_id") != workspace_id or row.get("asset_id") != asset_id:
                mismatches.append(f"scopedRows.content_unit_embeddings[{index}].scope")
            if row.get("content_unit_id") not in content_unit_ids:
                mismatches.append(f"scopedRows.content_unit_embeddings[{index}].parent")

    locator_ids = _collect_ids("evidence_locators")
    if not locator_ids:
        mismatches.append("scopedRows.evidence_locators.min")

    details = scoped_rows.get("document_locator_details")
    if isinstance(details, list):
        if not details:
            mismatches.append("scopedRows.document_locator_details.min")
        for index, row in enumerate(details):
            if not isinstance(row, dict):
                continue
            if row.get("locator_id") not in locator_ids:
                mismatches.append(f"scopedRows.document_locator_details[{index}].parent")
            char_start = row.get("char_start")
            char_end = row.get("char_end")
            if not (
                _is_nonneg_int(char_start)
                and _is_nonneg_int(char_end)
                and isinstance(char_start, int)
                and isinstance(char_end, int)
                and char_end >= char_start
            ):
                mismatches.append(f"scopedRows.document_locator_details[{index}].range")
            if not _is_sha256_hex(row.get("text_sha256")):
                mismatches.append(f"scopedRows.document_locator_details[{index}].text_sha256")
            block_id = row.get("block_id")
            if block_ids and block_id not in block_ids:
                mismatches.append(f"scopedRows.document_locator_details[{index}].block_id")

    citations = scoped_rows.get("message_citations")
    if isinstance(citations, list):
        if require_evidence_links and not citations:
            mismatches.append("scopedRows.message_citations.min")
        for index, row in enumerate(citations):
            if not isinstance(row, dict):
                continue
            if row.get("workspace_id") != workspace_id or row.get("asset_id") != asset_id:
                mismatches.append(f"scopedRows.message_citations[{index}].scope")
            if row.get("evidence_locator_id") not in locator_ids:
                mismatches.append(f"scopedRows.message_citations[{index}].locator")
            if row.get("asset_kind_snapshot") not in (None, "document"):
                mismatches.append(f"scopedRows.message_citations[{index}].asset_kind_snapshot")

    note_sources = scoped_rows.get("note_sources")
    if isinstance(note_sources, list):
        if require_evidence_links and not note_sources:
            mismatches.append("scopedRows.note_sources.min")
        for index, row in enumerate(note_sources):
            if not isinstance(row, dict):
                continue
            if row.get("workspace_id") != workspace_id or row.get("asset_id") != asset_id:
                mismatches.append(f"scopedRows.note_sources[{index}].scope")
            if row.get("evidence_locator_id") not in locator_ids:
                mismatches.append(f"scopedRows.note_sources[{index}].locator")
            if row.get("asset_kind_snapshot") not in (None, "document"):
                mismatches.append(f"scopedRows.note_sources[{index}].asset_kind_snapshot")

    # Track deleted state for object list rules via side channel key.
    if asset_deleted:
        mismatches.append("__asset_deleted__")
    return mismatches


def _live_objects_payload_mismatches(
    objects: list[Any],
    *,
    object_prefix: str,
    asset_deleted: bool,
) -> list[str]:
    mismatches: list[str] = []
    seen_keys: set[str] = set()
    for index, item in enumerate(objects):
        if not isinstance(item, dict):
            mismatches.append(f"objects[{index}]")
            continue
        required = ("objectKey", "sha256", "byteSize", "expectedExists")
        if any(field not in item for field in required):
            mismatches.append(f"objects[{index}].fields")
            continue
        object_key = item.get("objectKey")
        if not isinstance(object_key, str) or not object_key.startswith(object_prefix):
            mismatches.append(f"objects[{index}].objectKey")
        if object_key in seen_keys:
            mismatches.append(f"objects[{index}].duplicate")
        if isinstance(object_key, str):
            seen_keys.add(object_key)
        if not _is_sha256_hex(item.get("sha256")):
            mismatches.append(f"objects[{index}].sha256")
        if not _is_nonneg_int(item.get("byteSize")):
            mismatches.append(f"objects[{index}].byteSize")
        if not isinstance(item.get("expectedExists"), bool):
            mismatches.append(f"objects[{index}].expectedExists")
    if not objects and not asset_deleted:
        mismatches.append("objects.min")
    return mismatches


def _live_historical_evidence_mismatches(
    payload: dict[str, Any],
    *,
    scoped_rows: dict[str, Any],
) -> list[str]:
    mismatches: list[str] = []
    if "historicalEvidence" not in payload or not isinstance(
        payload.get("historicalEvidence"), dict
    ):
        mismatches.append("historicalEvidence")
        return mismatches

    expected = _canonicalize_historical_evidence(_build_historical_evidence(scoped_rows))
    actual = _canonicalize_historical_evidence(payload["historicalEvidence"])
    if actual != expected:
        mismatches.append("historicalEvidence")
        # Surface sourceAvailable drift explicitly for attack tests / debugging.
        if actual.get("sourceAvailable") != expected.get("sourceAvailable"):
            mismatches.append("historicalEvidence.sourceAvailable")
    return mismatches


def _live_snapshot_integrity_mismatches(payload: dict[str, Any]) -> list[str]:
    mismatches: list[str] = []
    if payload.get("evidenceMode") != EVIDENCE_MODE_LIVE:
        mismatches.append("evidenceMode")
    if payload.get("livePostgresMinio") is not True:
        mismatches.append("livePostgresMinio")

    mismatches.extend(_live_scope_field_mismatches(payload))

    workspace_id = _non_empty_str(payload.get("workspaceId"))
    asset_id = _non_empty_str(payload.get("assetId"))
    object_prefix = payload.get("objectPrefix")
    scoped_rows = payload.get("scopedRows") if isinstance(payload.get("scopedRows"), dict) else None
    objects = payload.get("objects") if isinstance(payload.get("objects"), list) else None

    asset_deleted = False
    if (
        workspace_id is not None
        and asset_id is not None
        and isinstance(object_prefix, str)
        and scoped_rows is not None
    ):
        row_mismatches = _live_scoped_rows_payload_mismatches(
            scoped_rows,
            workspace_id=workspace_id,
            asset_id=asset_id,
            require_evidence_links=bool(payload.get("requireEvidenceLinks", True)),
        )
        asset_deleted = "__asset_deleted__" in row_mismatches
        mismatches.extend(item for item in row_mismatches if item != "__asset_deleted__")
        mismatches.extend(
            _live_historical_evidence_mismatches(payload, scoped_rows=scoped_rows)
        )

    if objects is not None and isinstance(object_prefix, str):
        mismatches.extend(
            _live_objects_payload_mismatches(
                objects, object_prefix=object_prefix, asset_deleted=asset_deleted
            )
        )

    # Live semantic verification requires explicit typedTables/catalog presence.
    # Do not accept missing keys via empty-dict defaults.
    if "typedTables" not in payload or not isinstance(payload.get("typedTables"), dict):
        mismatches.append("typedTables")
        typed: dict[str, Any] = {}
    else:
        typed = payload["typedTables"]
    missing_tables = _missing_typed_or_catalog_tables(typed)
    mismatches.extend(f"typedTables.{table}" for table in missing_tables)

    if "catalog" not in payload or not isinstance(payload.get("catalog"), dict):
        mismatches.append("catalog")
        catalog: dict[str, Any] = {}
    else:
        catalog = payload["catalog"]
    mismatches.extend(_catalog_requirement_mismatches(catalog))

    # Digest must cover the complete canonical body for the payload as stored.
    expected_sha = _compute_semantic_sha256(payload)
    if payload.get("semanticSha256") != expected_sha:
        mismatches.append("semanticSha256")
    return mismatches


def _blocked_snapshot(reason: str) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "capturedAt": datetime.now(UTC).isoformat(),
        "evidenceMode": EVIDENCE_MODE_BLOCKED,
        "livePostgresMinio": False,
        "skipReason": reason,
        "passed": False,
        "scopedRows": {},
        "objects": [],
        "typedTables": {},
        "catalog": {},
    }


def _skipped_snapshot(reason: str) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "capturedAt": datetime.now(UTC).isoformat(),
        "evidenceMode": EVIDENCE_MODE_SKIPPED,
        "livePostgresMinio": False,
        "skipReason": reason,
        "passed": False,
        "scopedRows": {},
        "objects": [],
        "typedTables": {},
        "catalog": {},
    }


def _fixture_snapshot() -> dict[str, Any]:
    """Offline deterministic shape derived from checked-in Markdown fixture facts.

    Fixture mode is never live restore evidence. Verify must skip it with
    passed=false. Semantic values (byteSize, hashes, normalized text, blocks)
    come from docs/fixtures/document-modality/markdown-note.fixture.json.
    """
    fixture = _load_document_markdown_fixture()
    workspace_id = IDS["workspace"]
    asset_id = IDS["document-asset"]
    representation_id = IDS["normalized-representation"]
    locator_id = IDS["paragraph-locator"]
    content_unit_id = _id("content-unit")
    embedding_id = _id("embedding")
    object_prefix = _asset_object_prefix(workspace_id, asset_id)

    source_sha256 = str(fixture["sourceSha256"])
    normalized_sha256 = str(fixture["normalizedContentSha256"])
    normalized_text = str(fixture["normalizedText"])
    byte_size = int(fixture["byteSize"])
    parser_version = str(fixture["parserVersion"])
    normalization_version = str(fixture["normalizationVersion"])
    blocks_in = list(fixture["blocks"])
    citation_projection = fixture["expectedCitationProjection"]
    note_projection = fixture["expectedNoteSourceProjection"]
    after_delete = fixture["historicalAfterDeleteProjection"]

    # Use the citation paragraph locator facts (sourceAvailable=true projection).
    citation_locator = citation_projection["locator"]
    citation_block_id = str(citation_locator["blockId"])
    primary_block = next(
        block for block in blocks_in if block["blockId"] == citation_block_id
    )
    # Prefer the paragraph locator for retained historical evidence.
    primary_locator_id = locator_id

    document_blocks = []
    for block in blocks_in:
        document_blocks.append(
            {
                "id": _id(f"block-{block['blockId']}"),
                "representation_id": representation_id,
                "block_id": block["blockId"],
                "block_order": int(block["blockOrder"]),
                "block_kind": block["blockKind"],
                "heading_level": block.get("headingLevel"),
                "heading_path": list(block.get("headingPath") or []),
                "char_start": int(block["charStart"]),
                "char_end": int(block["charEnd"]),
                "text_sha256": block["textSha256"],
                "text_content": block["text"],
                "normalization_version": block["normalizationVersion"],
            }
        )

    # One locator detail row for the citation paragraph, matching durable projection.
    locator_details = [
        {
            "locator_id": primary_locator_id,
            "block_id": citation_block_id,
            "block_kind": citation_locator["blockKind"],
            "heading_path": list(citation_locator.get("headingPath") or []),
            "char_start": int(citation_locator["charStart"]),
            "char_end": int(citation_locator["charEnd"]),
            "text_sha256": citation_locator["textSha256"],
            "normalization_version": citation_locator["normalizationVersion"],
        }
    ]

    scoped_rows = {
        "assets": [
            {
                "id": asset_id,
                "workspace_id": workspace_id,
                "asset_kind": "document",
                "title": str(citation_projection["assetTitle"]),
                "source_filename": str(fixture["sourceFilename"]),
                "object_key": f"{object_prefix}original.md",
                "mime_type": str(fixture["mimeType"]),
                "byte_size": byte_size,
                "source_sha256": source_sha256,
                "status": "ready",
                "current_processing_generation": 1,
                "current_index_version": 1,
                # Fixture shape models the historical after-delete oracle:
                # sourceAvailable=false while locator/citation/note-source rows remain.
                "deleted_at": "2026-08-05T00:00:00+00:00",
            }
        ],
        "asset_representations": [
            {
                "id": representation_id,
                "workspace_id": workspace_id,
                "asset_id": asset_id,
                "representation_kind": "document_normalized",
                "processing_generation": 1,
                "generator_provider": None,
                "generator_model": None,
                "generator_version": parser_version,
                "object_key": f"{object_prefix}representations/1/document_normalized.md",
                "content_sha256": normalized_sha256,
            }
        ],
        "document_normalized_contents": [
            {
                "representation_id": representation_id,
                "format": str(fixture["format"]),
                "parser_version": parser_version,
                "normalization_version": normalization_version,
                "normalized_text": normalized_text,
                "content_sha256": normalized_sha256,
                "block_count": len(document_blocks),
            }
        ],
        "document_blocks": document_blocks,
        "content_units": [
            {
                "id": content_unit_id,
                "workspace_id": workspace_id,
                "asset_id": asset_id,
                "representation_id": representation_id,
                "source_locator_id": primary_locator_id,
                "unit_kind": "document_text_chunk",
                "unit_order": 0,
                "text_content": str(primary_block["text"]),
                "token_count": max(1, len(str(primary_block["text"]).split())),
                "char_start": int(primary_block["charStart"]),
                "char_end": int(primary_block["charEnd"]),
                "index_version": 1,
            }
        ],
        "content_unit_embeddings": [
            {
                "id": embedding_id,
                "workspace_id": workspace_id,
                "asset_id": asset_id,
                "content_unit_id": content_unit_id,
                "processing_generation": 1,
                "index_version": 1,
                "is_current": True,
                "embedding_space": "text_dense_v1",
                "provider": "fixture",
                "model": "fixture-embed",
                "dimensions": 8,
                "version": "v1",
            }
        ],
        "evidence_locators": [
            {
                "id": primary_locator_id,
                "workspace_id": workspace_id,
                "asset_id": asset_id,
                "locator_kind": "document_anchor",
                "locator_version": 1,
                "processing_generation_snapshot": 1,
                "representation_id_snapshot": representation_id,
            }
        ],
        "document_locator_details": locator_details,
        "message_citations": [
            {
                "id": IDS["citation"],
                "workspace_id": workspace_id,
                "message_id": _id("message"),
                "evidence_locator_id": primary_locator_id,
                "asset_id": asset_id,
                "citation_index": 0,
                "asset_kind_snapshot": "document",
                "asset_title_snapshot": str(citation_projection["assetTitle"]),
                "excerpt_snapshot": str(citation_projection["excerpt"]),
                "processing_generation_snapshot": int(
                    citation_projection["sourceVersions"]["processingGeneration"]
                ),
                "representation_id_snapshot": representation_id,
                "parser_version_snapshot": str(
                    citation_projection["sourceVersions"]["parserVersion"]
                ),
                "index_version_snapshot": int(
                    citation_projection["sourceVersions"]["indexVersion"]
                ),
            }
        ],
        "note_sources": [
            {
                "id": IDS["note-source"],
                "workspace_id": workspace_id,
                "note_id": _id("note"),
                "evidence_locator_id": primary_locator_id,
                "asset_id": asset_id,
                "source_order": 0,
                "message_citation_id": IDS["citation"],
                "asset_kind_snapshot": "document",
                "asset_title_snapshot": str(note_projection["assetTitle"]),
                "excerpt_snapshot": str(note_projection["excerpt"]),
                "processing_generation_snapshot": int(
                    note_projection["sourceVersions"]["processingGeneration"]
                ),
                "representation_id_snapshot": representation_id,
                "parser_version_snapshot": str(
                    note_projection["sourceVersions"]["parserVersion"]
                ),
                "index_version_snapshot": int(
                    note_projection["sourceVersions"]["indexVersion"]
                ),
            }
        ],
    }

    # After-delete historical evidence: source unavailable, retained IDs/versions remain.
    historical_evidence = _build_historical_evidence(scoped_rows)
    assert historical_evidence["sourceAvailable"] is False
    assert after_delete.get("sourceAvailable") is False

    objects = [
        {
            "objectKey": f"{object_prefix}original.md",
            "sha256": source_sha256,
            "byteSize": byte_size,
            "expectedExists": True,
        }
    ]
    body = {
        "workspaceId": workspace_id,
        "assetId": asset_id,
        "objectPrefix": object_prefix,
        "scopedRows": scoped_rows,
        "objects": objects,
        "typedTables": _fixture_typed_tables(scoped_rows),
        "catalog": _fixture_catalog(),
        "historicalEvidence": historical_evidence,
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "capturedAt": datetime(2026, 8, 5, 0, 0, tzinfo=UTC).isoformat(),
        "evidenceMode": EVIDENCE_MODE_FIXTURE,
        "livePostgresMinio": False,
        "semanticSha256": _compute_semantic_sha256(body),
        **body,
    }


def _json_rows(
    connection: Any,
    query: str,
    *,
    expanding: tuple[str, ...] = (),
    **parameters: Any,
) -> list[dict[str, Any]]:
    from sqlalchemy import bindparam, text

    statement = text(f"SELECT to_jsonb(row_data)::text FROM ({query}) row_data")
    if expanding:
        statement = statement.bindparams(
            *(bindparam(name, expanding=True) for name in expanding)
        )
    payloads = connection.execute(statement, parameters).scalars()
    return [json.loads(payload) for payload in payloads]


def _minio_client_from_env() -> tuple[Any, str]:
    endpoint = (
        os.environ.get("V5B_MINIO_ENDPOINT")
        or os.environ.get("MINIO_ENDPOINT")
        or os.environ.get("MINIO_HOST")
        or os.environ.get("AI_PDF_MINIO_ENDPOINT")
    )
    access_key = (
        os.environ.get("V5B_MINIO_ACCESS_KEY")
        or os.environ.get("MINIO_ACCESS_KEY")
        or os.environ.get("MINIO_ROOT_USER")
        or os.environ.get("AI_PDF_MINIO_ACCESS_KEY")
    )
    secret_key = (
        os.environ.get("V5B_MINIO_SECRET_KEY")
        or os.environ.get("MINIO_SECRET_KEY")
        or os.environ.get("MINIO_ROOT_PASSWORD")
        or os.environ.get("AI_PDF_MINIO_SECRET_KEY")
    )
    bucket = (
        os.environ.get("V5B_MINIO_BUCKET")
        or os.environ.get("MINIO_BUCKET")
        or os.environ.get("AI_PDF_MINIO_BUCKET")
    )
    secure_raw = (
        os.environ.get("V5B_MINIO_SECURE")
        or os.environ.get("MINIO_SECURE")
        or os.environ.get("AI_PDF_MINIO_SECURE")
        or "false"
    )
    secure = secure_raw.strip().lower() in {"1", "true", "yes", "on"}

    if not endpoint or not access_key or not secret_key or not bucket:
        raise RuntimeError(
            "MinIO credentials/endpoint incomplete; require endpoint, access key, secret key, and bucket "
            "(V5B_MINIO_* or MINIO_*)"
        )

    try:
        from minio import Minio
    except Exception as error:  # pragma: no cover - environment dependent
        raise RuntimeError(f"minio package unavailable: {error}") from error

    client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
    return client, bucket


def _list_scoped_objects(workspace_id: str, asset_id: str) -> list[dict[str, Any]]:
    client, bucket = _minio_client_from_env()
    prefix = _asset_object_prefix(workspace_id, asset_id)
    objects: list[dict[str, Any]] = []
    for item in client.list_objects(bucket, prefix=prefix, recursive=True):
        object_key = item.object_name
        if not object_key:
            continue
        response = client.get_object(bucket, object_key)
        try:
            payload = response.read()
        finally:
            response.close()
            response.release_conn()
        objects.append(
            {
                "objectKey": object_key,
                "sha256": sha256(payload).hexdigest(),
                "byteSize": len(payload),
                "expectedExists": True,
            }
        )
    return sorted(objects, key=lambda entry: entry["objectKey"])


def _capture_required_catalog(
    connection: Any, existing: set[str]
) -> dict[str, list[dict[str, Any]]]:
    from sqlalchemy import bindparam, text

    captured: dict[str, list[dict[str, Any]]] = {}
    for table, expected_rows in REQUIRED_CATALOG.items():
        fields = CATALOG_TABLE_FIELDS[table]
        kinds = [row["kind"] for row in expected_rows]
        if table not in existing:
            captured[table] = []
            continue
        column_sql = ", ".join(f'"{name}"' for name in fields)
        statement = text(
            f'SELECT {column_sql} FROM "{table}" WHERE kind IN :kinds'
        ).bindparams(bindparam("kinds", expanding=True))
        raw_rows = connection.execute(statement, {"kinds": kinds}).mappings().all()
        projected = [
            {
                field: (
                    bool(row[field])
                    if field == "enabled"
                    else int(row[field])
                    if field == "contract_version"
                    else row[field]
                )
                for field in fields
            }
            for row in raw_rows
        ]
        captured[table] = _canonical_catalog_rows(table, projected)
    return captured


def _capture_scoped_rows(connection: Any, workspace_id: str, asset_id: str) -> dict[str, list[dict[str, Any]]]:
    from sqlalchemy import text

    assets = _json_rows(
        connection,
        """
        SELECT *
        FROM assets
        WHERE id = :asset_id AND workspace_id = :workspace_id
        ORDER BY id
        """,
        asset_id=asset_id,
        workspace_id=workspace_id,
    )
    if not assets:
        raise RuntimeError(f"scoped asset not found workspace_id={workspace_id} asset_id={asset_id}")

    representations = _json_rows(
        connection,
        """
        SELECT *
        FROM asset_representations
        WHERE asset_id = :asset_id AND workspace_id = :workspace_id
        ORDER BY processing_generation, representation_kind, id
        """,
        asset_id=asset_id,
        workspace_id=workspace_id,
    )
    representation_ids = [row["id"] for row in representations]

    normalized: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    if representation_ids:
        normalized = _json_rows(
            connection,
            """
            SELECT *
            FROM document_normalized_contents
            WHERE representation_id IN :representation_ids
            ORDER BY representation_id
            """,
            expanding=("representation_ids",),
            representation_ids=representation_ids,
        )
        blocks = _json_rows(
            connection,
            """
            SELECT *
            FROM document_blocks
            WHERE representation_id IN :representation_ids
            ORDER BY representation_id, block_order, id
            """,
            expanding=("representation_ids",),
            representation_ids=representation_ids,
        )

    content_units = _json_rows(
        connection,
        """
        SELECT *
        FROM content_units
        WHERE asset_id = :asset_id AND workspace_id = :workspace_id
        ORDER BY representation_id, unit_order, id
        """,
        asset_id=asset_id,
        workspace_id=workspace_id,
    )
    embeddings = _json_rows(
        connection,
        """
        SELECT id, workspace_id, asset_id, content_unit_id, processing_generation,
               index_version, is_current, embedding_space, provider, model,
               dimensions, version
        FROM content_unit_embeddings
        WHERE asset_id = :asset_id AND workspace_id = :workspace_id
        ORDER BY content_unit_id, embedding_space, provider, model, version, id
        """,
        asset_id=asset_id,
        workspace_id=workspace_id,
    )
    locators = _json_rows(
        connection,
        """
        SELECT *
        FROM evidence_locators
        WHERE asset_id = :asset_id AND workspace_id = :workspace_id
        ORDER BY id
        """,
        asset_id=asset_id,
        workspace_id=workspace_id,
    )
    locator_ids = [row["id"] for row in locators]
    locator_details: list[dict[str, Any]] = []
    if locator_ids:
        locator_details = _json_rows(
            connection,
            """
            SELECT d.*
            FROM document_locator_details d
            WHERE d.locator_id IN :locator_ids
            ORDER BY d.locator_id
            """,
            expanding=("locator_ids",),
            locator_ids=locator_ids,
        )

    def _required_projected(
        table: str,
        fields: tuple[str, ...],
        *,
        where_sql: str,
        order_fields: tuple[str, ...],
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        from sqlalchemy import inspect as sa_inspect

        existing_tables = set(sa_inspect(connection).get_table_names())
        if table not in existing_tables:
            raise RuntimeError(f"required table missing for live Document restore: {table}")
        existing_columns = {column["name"] for column in sa_inspect(connection).get_columns(table)}
        missing_columns = [field for field in fields if field not in existing_columns]
        if missing_columns:
            raise RuntimeError(
                f"required columns missing on {table}: {', '.join(missing_columns)}"
            )
        column_sql = ", ".join(f'"{name}"' for name in fields)
        order_sql = ", ".join(f'"{name}"' for name in order_fields)
        rows = _json_rows(
            connection,
            f"""
            SELECT {column_sql}
            FROM {table}
            WHERE {where_sql}
            ORDER BY {order_sql}
            """,
            **params,
        )
        return [_project_row(row, fields) for row in rows]

    citations = _required_projected(
        "message_citations",
        CITATION_FIELDS,
        where_sql="asset_id = :asset_id AND workspace_id = :workspace_id",
        order_fields=("citation_index", "id"),
        params={"asset_id": asset_id, "workspace_id": workspace_id},
    )
    note_sources = _required_projected(
        "note_sources",
        NOTE_SOURCE_FIELDS,
        where_sql="asset_id = :asset_id AND workspace_id = :workspace_id",
        order_fields=("source_order", "id"),
        params={"asset_id": asset_id, "workspace_id": workspace_id},
    )

    # Ensure the connection still has a simple capability probe path available.
    connection.execute(text("SELECT 1"))

    return {
        "assets": _sort_rows([_project_row(row, ASSET_FIELDS) for row in assets]),
        "asset_representations": _sort_rows(
            [_project_row(row, REPRESENTATION_FIELDS) for row in representations]
        ),
        "document_normalized_contents": _sort_rows(
            [_project_row(row, NORMALIZED_CONTENT_FIELDS) for row in normalized]
        ),
        "document_blocks": _sort_rows([_project_row(row, DOCUMENT_BLOCK_FIELDS) for row in blocks]),
        "content_units": _sort_rows([_project_row(row, CONTENT_UNIT_FIELDS) for row in content_units]),
        "content_unit_embeddings": _sort_rows(
            [_project_row(row, EMBEDDING_IDENTITY_FIELDS) for row in embeddings]
        ),
        "evidence_locators": _sort_rows(
            [_project_row(row, EVIDENCE_LOCATOR_FIELDS) for row in locators]
        ),
        "document_locator_details": _sort_rows(
            [_project_row(row, DOCUMENT_LOCATOR_DETAIL_FIELDS) for row in locator_details]
        ),
        "message_citations": _sort_rows(citations),
        "note_sources": _sort_rows(note_sources),
    }


def _try_live_snapshot(
    *,
    workspace_id: str | None,
    asset_id: str | None,
    require_evidence_links: bool = True,
) -> dict[str, Any]:
    resolved_workspace, resolved_asset = _resolve_scope(workspace_id, asset_id)
    if not resolved_workspace or not resolved_asset:
        return _blocked_snapshot(
            "Live Document restore evidence requires explicit V5B_WORKSPACE_ID and V5B_ASSET_ID "
            "(or --workspace-id/--asset-id)"
        )

    database_url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("V5B_DATABASE_URL")
        or os.environ.get("AI_PDF_DATABASE_URL")
    )
    if not database_url:
        return _skipped_snapshot("DATABASE_URL/V5B_DATABASE_URL is not set")

    try:
        from sqlalchemy import create_engine, inspect, text
        from sqlalchemy.engine.url import make_url
    except Exception as error:  # pragma: no cover - environment dependent
        return _skipped_snapshot(f"SQLAlchemy unavailable: {error}")

    url = make_url(database_url)
    if not url.drivername.startswith("postgresql"):
        return _skipped_snapshot("Live Document restore evidence requires PostgreSQL, not SQLite")

    try:
        engine = create_engine(database_url, future=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            existing = set(inspect(connection).get_table_names())
            typed: dict[str, dict[str, Any]] = {}
            for table in (*DOCUMENT_TYPED_TABLES, *CATALOG_TABLES):
                present = table in existing
                row_count = (
                    int(connection.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one())
                    if present
                    else 0
                )
                typed[table] = {"present": present, "rowCount": row_count}

            for table, fields in (
                ("message_citations", CITATION_FIELDS),
                ("note_sources", NOTE_SOURCE_FIELDS),
            ):
                present = table in existing
                required_columns_present = False
                row_count = 0
                if present:
                    existing_columns = {
                        column["name"] for column in inspect(connection).get_columns(table)
                    }
                    required_columns_present = all(field in existing_columns for field in fields)
                    if required_columns_present:
                        row_count = int(
                            connection.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
                        )
                typed[table] = {
                    "present": present and required_columns_present,
                    "rowCount": row_count,
                    "requiredColumnsPresent": required_columns_present,
                }

            required_catalog = _capture_required_catalog(connection, existing)
            document_row = next(
                (
                    row
                    for row in required_catalog.get("asset_types", [])
                    if row.get("kind") == "document"
                ),
                None,
            )
            document_enabled = bool(
                document_row
                and document_row.get("enabled") is True
                and document_row.get("contract_version") == DOCUMENT_CONTRACT_VERSION
            )
            locator_row = next(
                (
                    row
                    for row in required_catalog.get("locator_types", [])
                    if row.get("kind") == "document_anchor"
                ),
                None,
            )
            locator = None
            if locator_row is not None:
                locator = {
                    "kind": locator_row.get("kind"),
                    "detail_family": locator_row.get("detail_family"),
                    "contract_version": locator_row.get("contract_version"),
                }

            scoped_rows = _capture_scoped_rows(connection, resolved_workspace, resolved_asset)
        engine.dispose()
    except Exception as error:
        return _skipped_snapshot(f"PostgreSQL unavailable or scoped query failed: {error}")

    catalog = {
        "documentEnabled": document_enabled,
        "documentLocator": locator,
        "requiredCatalog": required_catalog,
        "representationKinds": _catalog_kind_list(
            required_catalog.get("representation_types") or []
        ),
        "contentUnitKinds": _catalog_kind_list(
            required_catalog.get("content_unit_types") or []
        ),
    }

    try:
        objects = _list_scoped_objects(resolved_workspace, resolved_asset)
        minio_status = "ok"
    except Exception as error:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "capturedAt": datetime.now(UTC).isoformat(),
            "evidenceMode": EVIDENCE_MODE_SKIPPED,
            "livePostgresMinio": False,
            "skipReason": f"MinIO unavailable or scoped object listing failed: {error}",
            "passed": False,
            "workspaceId": resolved_workspace,
            "assetId": resolved_asset,
            "objectPrefix": _asset_object_prefix(resolved_workspace, resolved_asset),
            "requireEvidenceLinks": require_evidence_links,
            "scopedRows": scoped_rows,
            "objects": [],
            "typedTables": typed,
            "catalog": catalog,
            "minioStatus": f"skipped:{error}",
        }

    object_prefix = _asset_object_prefix(resolved_workspace, resolved_asset)
    historical_evidence = _build_historical_evidence(scoped_rows)
    body = {
        "workspaceId": resolved_workspace,
        "assetId": resolved_asset,
        "objectPrefix": object_prefix,
        "requireEvidenceLinks": require_evidence_links,
        "scopedRows": scoped_rows,
        "objects": objects,
        "typedTables": typed,
        "catalog": catalog,
        "historicalEvidence": historical_evidence,
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "capturedAt": datetime.now(UTC).isoformat(),
        "evidenceMode": EVIDENCE_MODE_LIVE,
        "livePostgresMinio": True,
        "semanticSha256": _compute_semantic_sha256(body),
        **body,
        "minioStatus": minio_status,
        "tableCounts": {name: len(rows) for name, rows in scoped_rows.items()},
        "objectCount": len(objects),
    }


def snapshot(
    *,
    mode: str,
    workspace_id: str | None = None,
    asset_id: str | None = None,
    require_evidence_links: bool = True,
) -> dict[str, Any]:
    if mode == "fixture":
        return _fixture_snapshot()
    return _try_live_snapshot(
        workspace_id=workspace_id,
        asset_id=asset_id,
        require_evidence_links=require_evidence_links,
    )


def _is_live_snapshot(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("evidenceMode") == EVIDENCE_MODE_LIVE
        and payload.get("livePostgresMinio") is True
        and payload.get("semanticSha256")
    )


def verify(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    if before.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError(f"before schema mismatch: {before.get('schemaVersion')}")
    if after.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError(f"after schema mismatch: {after.get('schemaVersion')}")

    before_mode = before.get("evidenceMode")
    after_mode = after.get("evidenceMode")

    # Fixture-shape snapshots are offline-only. Using them for live restore
    # verification must never produce a pass.
    if before_mode == EVIDENCE_MODE_FIXTURE or after_mode == EVIDENCE_MODE_FIXTURE:
        return {
            "passed": False,
            "skipped": True,
            "reason": (
                "fixture-shape snapshots are offline checks only and cannot satisfy live restore verify"
            ),
            "mismatches": [],
            "livePostgresMinio": False,
            "schemaVersion": SCHEMA_VERSION,
        }

    if before_mode in {EVIDENCE_MODE_SKIPPED, EVIDENCE_MODE_BLOCKED} or after_mode in {
        EVIDENCE_MODE_SKIPPED,
        EVIDENCE_MODE_BLOCKED,
    }:
        return {
            "passed": False,
            "skipped": True,
            "reason": before.get("skipReason") or after.get("skipReason") or "live evidence skipped",
            "mismatches": [],
            "livePostgresMinio": False,
            "schemaVersion": SCHEMA_VERSION,
        }

    if not _is_live_snapshot(before) or not _is_live_snapshot(after):
        return {
            "passed": False,
            "skipped": True,
            "reason": "verify requires both before and after live PostgreSQL+MinIO evidence",
            "mismatches": [],
            "livePostgresMinio": False,
            "schemaVersion": SCHEMA_VERSION,
        }

    mismatches: list[str] = []
    before_integrity = _live_snapshot_integrity_mismatches(before)
    after_integrity = _live_snapshot_integrity_mismatches(after)
    mismatches.extend(f"before.{item}" for item in before_integrity)
    mismatches.extend(f"after.{item}" for item in after_integrity)

    for field in (
        "workspaceId",
        "assetId",
        "objectPrefix",
        "requireEvidenceLinks",
        "semanticSha256",
        "scopedRows",
        "objects",
        "typedTables",
        "historicalEvidence",
    ):
        if field == "historicalEvidence":
            left = _canonicalize_historical_evidence(
                before.get("historicalEvidence")
                if isinstance(before.get("historicalEvidence"), dict)
                else {}
            )
            right = _canonicalize_historical_evidence(
                after.get("historicalEvidence")
                if isinstance(after.get("historicalEvidence"), dict)
                else {}
            )
            if left != right:
                mismatches.append("historicalEvidence")
            continue
        if before.get(field) != after.get(field):
            mismatches.append(field)

    if not _catalogs_equal(before.get("catalog"), after.get("catalog")):
        mismatches.append("catalog")

    # De-duplicate while preserving order for stable test assertions.
    deduped: list[str] = []
    seen: set[str] = set()
    for item in mismatches:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)

    return {
        "passed": not deduped,
        "skipped": False,
        "mismatches": deduped,
        "livePostgresMinio": True,
        "schemaVersion": SCHEMA_VERSION,
        "beforeSemanticSha256": before.get("semanticSha256"),
        "afterSemanticSha256": after.get("semanticSha256"),
        "requiredCatalog": _required_catalog_values(),
    }


def check_tables(snapshot_payload: dict[str, Any]) -> dict[str, Any]:
    if snapshot_payload.get("evidenceMode") in {EVIDENCE_MODE_SKIPPED, EVIDENCE_MODE_BLOCKED}:
        return {
            "passed": False,
            "skipped": True,
            "reason": snapshot_payload.get("skipReason"),
            "missingTables": list(DOCUMENT_TYPED_TABLES)
            + list(CATALOG_TABLES)
            + list(REQUIRED_SCOPED_LINK_TABLES),
            "catalogMismatches": list(REQUIRED_CATALOG.keys()),
            "livePostgresMinio": False,
            "fixtureShapeOk": False,
            "offlineCatalogShapeOk": False,
        }

    typed = snapshot_payload.get("typedTables") or {}
    missing = _missing_typed_or_catalog_tables(typed if isinstance(typed, dict) else {})
    catalog = snapshot_payload.get("catalog") or {}
    catalog_mismatches = _catalog_requirement_mismatches(
        catalog if isinstance(catalog, dict) else {}
    )
    catalog_ok = not catalog_mismatches
    offline_shape_ok = not missing and catalog_ok
    live_evidence = (
        snapshot_payload.get("evidenceMode") == EVIDENCE_MODE_LIVE
        and snapshot_payload.get("livePostgresMinio") is True
    )
    # Fixture/offline shape may report offlineCatalogShapeOk, but live acceptance
    # passed requires PostgreSQL/MinIO evidence plus required catalog metadata.
    return {
        "passed": live_evidence and offline_shape_ok,
        "skipped": False,
        "missingTables": missing,
        "catalogOk": catalog_ok,
        "catalogMismatches": catalog_mismatches,
        "requiredCatalog": _required_catalog_values(),
        "livePostgresMinio": bool(snapshot_payload.get("livePostgresMinio")),
        "evidenceMode": snapshot_payload.get("evidenceMode"),
        "fixtureShapeOk": offline_shape_ok
        and snapshot_payload.get("evidenceMode") == EVIDENCE_MODE_FIXTURE,
        "offlineCatalogShapeOk": offline_shape_ok,
    }


def _write(path: Path | None, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    if path is None:
        sys.stdout.write(text)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.command == "snapshot":
        payload = snapshot(
            mode=args.mode,
            workspace_id=getattr(args, "workspace_id", None),
            asset_id=getattr(args, "asset_id", None),
            require_evidence_links=not getattr(args, "allow_empty_evidence_links", False),
        )
        _write(args.output, payload)
        if payload.get("evidenceMode") in {EVIDENCE_MODE_SKIPPED, EVIDENCE_MODE_BLOCKED}:
            return 2
        return 0
    if args.command == "verify":
        before = json.loads(args.before.read_text(encoding="utf-8"))
        after = json.loads(args.after.read_text(encoding="utf-8"))
        result = verify(before, after)
        _write(args.output, result)
        if result.get("skipped"):
            return 2
        return 0 if result.get("passed") else 1
    if args.command == "check-tables":
        live = snapshot(
            mode="live",
            workspace_id=getattr(args, "workspace_id", None),
            asset_id=getattr(args, "asset_id", None),
        )
        result = check_tables(live)
        _write(args.output, result)
        if result.get("skipped"):
            return 2
        return 0 if result.get("passed") else 1
    raise AssertionError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
