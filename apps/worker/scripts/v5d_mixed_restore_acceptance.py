#!/usr/bin/env python3
"""V5-D mixed PDF+Image+Document restore snapshot/verify helper.

Live mode freezes durable identity for one Workspace that contains ready PDF,
Image, and Document assets (plus their historical citations/note sources).
Fixture mode is shape-only and must never be treated as a live restore pass.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "v5d-mixed-restore-acceptance-v1"
EVIDENCE_MODE_LIVE = "live"
EVIDENCE_MODE_FIXTURE = "fixture-shape-only"

REQUIRED_KINDS = ("pdf", "image", "document")

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
NORMALIZED_CONTENT_FIELDS = (
    "representation_id",
    "format",
    "parser_version",
    "normalization_version",
    "normalized_text",
    "content_sha256",
    "block_count",
)
PDF_LOCATOR_DETAIL_FIELDS = (
    "locator_id",
    "page_id",
    "page_number",
    "coordinate_space",
    "crop_x0_points",
    "crop_y0_points",
    "crop_x1_points",
    "crop_y1_points",
    "rotation_degrees",
    "display_width_points",
    "display_height_points",
)
IMAGE_LOCATOR_DETAIL_FIELDS = (
    "locator_id",
    "coordinate_space",
    "width_pixels",
    "height_pixels",
    "orientation_applied",
)
SPATIAL_REGION_FIELDS = (
    "id",
    "locator_id",
    "region_order",
    "x",
    "y",
    "width",
    "height",
)

SCOPED_ROW_FIELD_SETS: dict[str, tuple[str, ...]] = {
    "assets": ASSET_FIELDS,
    "asset_representations": REPRESENTATION_FIELDS,
    "content_units": CONTENT_UNIT_FIELDS,
    "content_unit_embeddings": EMBEDDING_IDENTITY_FIELDS,
    "evidence_locators": EVIDENCE_LOCATOR_FIELDS,
    "message_citations": CITATION_FIELDS,
    "note_sources": NOTE_SOURCE_FIELDS,
    "document_normalized_contents": NORMALIZED_CONTENT_FIELDS,
    "document_blocks": DOCUMENT_BLOCK_FIELDS,
    "document_locator_details": DOCUMENT_LOCATOR_DETAIL_FIELDS,
    "pdf_locator_details": PDF_LOCATOR_DETAIL_FIELDS,
    "image_locator_details": IMAGE_LOCATOR_DETAIL_FIELDS,
    "spatial_locator_regions": SPATIAL_REGION_FIELDS,
}


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")


def _semantic_sha256(value: object) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: _canonical_bytes(row))


def _project_row(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    for field in fields:
        value = getattr(row, field, None)
        if isinstance(value, datetime):
            projected[field] = value.astimezone(UTC).isoformat()
        else:
            projected[field] = value
    return projected


def _project_rows(rows: list[Any], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    return _sort_rows([_project_row(row, fields) for row in rows])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="V5-D mixed restore acceptance helper")
    sub = parser.add_subparsers(dest="command", required=True)

    snapshot = sub.add_parser("snapshot", help="Capture mixed workspace restore snapshot")
    snapshot.add_argument("--output", type=Path, required=True)
    snapshot.add_argument("--mode", choices=("live", "fixture"), default="live")
    snapshot.add_argument("--workspace-id", default=None)

    verify = sub.add_parser("verify", help="Compare before/after mixed restore snapshots")
    verify.add_argument("--before", type=Path, required=True)
    verify.add_argument("--after", type=Path, required=True)
    verify.add_argument("--output", type=Path)

    return parser.parse_args()


def _fixture_snapshot() -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "evidenceMode": EVIDENCE_MODE_FIXTURE,
        "workspaceId": "fixture-workspace",
        "requiredKinds": list(REQUIRED_KINDS),
        "assetsByKind": {
            "pdf": {"id": "fixture-pdf", "asset_kind": "pdf", "status": "ready"},
            "image": {"id": "fixture-image", "asset_kind": "image", "status": "ready"},
            "document": {
                "id": "fixture-document",
                "asset_kind": "document",
                "status": "ready",
            },
        },
        "scopedRows": {key: [] for key in SCOPED_ROW_FIELD_SETS},
        "objectKeys": [],
        "semanticSha256": "0" * 64,
        "liveIdentity": {
            "assetKinds": list(REQUIRED_KINDS),
            "citationKinds": list(REQUIRED_KINDS),
            "sourceAvailableByKind": {kind: True for kind in REQUIRED_KINDS},
        },
        "note": "fixture-shape-only; not a live restore pass",
    }


def _live_snapshot(workspace_id: str) -> dict[str, Any]:
    from sqlalchemy import select

    from ai_pdf_api.db.session import SessionLocal
    from ai_pdf_api.models import (
        Asset,
        AssetRepresentation,
        ContentUnit,
        ContentUnitEmbedding,
        DocumentBlock,
        DocumentLocatorDetail,
        DocumentNormalizedContent,
        EvidenceLocator,
        ImageLocatorDetail,
        MessageCitation,
        NoteSource,
        PdfLocatorDetail,
        SpatialLocatorRegion,
    )
    from ai_pdf_api.services.storage import object_exists

    with SessionLocal() as db:
        assets = list(
            db.scalars(
                select(Asset).where(
                    Asset.workspace_id == workspace_id,
                    Asset.deleted_at.is_(None),
                )
            )
        )
        by_kind: dict[str, Asset] = {}
        for asset in assets:
            if asset.asset_kind in REQUIRED_KINDS and asset.asset_kind not in by_kind:
                by_kind[asset.asset_kind] = asset
        missing = [kind for kind in REQUIRED_KINDS if kind not in by_kind]
        if missing:
            raise RuntimeError(
                f"mixed live snapshot missing ready kinds={missing} workspace={workspace_id}"
            )
        for kind, asset in by_kind.items():
            if asset.status != "ready":
                raise RuntimeError(
                    f"mixed live snapshot asset kind={kind} status={asset.status} expected=ready"
                )

        asset_ids = [by_kind[kind].id for kind in REQUIRED_KINDS]
        representations = list(
            db.scalars(
                select(AssetRepresentation).where(
                    AssetRepresentation.asset_id.in_(asset_ids)
                )
            )
        )
        content_units = list(
            db.scalars(select(ContentUnit).where(ContentUnit.asset_id.in_(asset_ids)))
        )
        embeddings = list(
            db.scalars(
                select(ContentUnitEmbedding).where(
                    ContentUnitEmbedding.asset_id.in_(asset_ids)
                )
            )
        )
        locators = list(
            db.scalars(
                select(EvidenceLocator).where(EvidenceLocator.asset_id.in_(asset_ids))
            )
        )
        locator_ids = [locator.id for locator in locators]
        citations = list(
            db.scalars(
                select(MessageCitation).where(MessageCitation.asset_id.in_(asset_ids))
            )
        )
        note_sources = list(
            db.scalars(select(NoteSource).where(NoteSource.asset_id.in_(asset_ids)))
        )
        document_asset_id = by_kind["document"].id
        document_reps = [
            rep.id
            for rep in representations
            if rep.asset_id == document_asset_id
            and rep.representation_kind == "document_normalized"
        ]
        normalized_contents = list(
            db.scalars(
                select(DocumentNormalizedContent).where(
                    DocumentNormalizedContent.representation_id.in_(document_reps)
                )
            )
        ) if document_reps else []
        document_blocks = list(
            db.scalars(
                select(DocumentBlock).where(
                    DocumentBlock.representation_id.in_(document_reps)
                )
            )
        ) if document_reps else []
        document_locator_details = list(
            db.scalars(
                select(DocumentLocatorDetail).where(
                    DocumentLocatorDetail.locator_id.in_(locator_ids)
                )
            )
        ) if locator_ids else []
        pdf_locator_details = list(
            db.scalars(
                select(PdfLocatorDetail).where(PdfLocatorDetail.locator_id.in_(locator_ids))
            )
        ) if locator_ids else []
        image_locator_details = list(
            db.scalars(
                select(ImageLocatorDetail).where(
                    ImageLocatorDetail.locator_id.in_(locator_ids)
                )
            )
        ) if locator_ids else []
        spatial_regions = list(
            db.scalars(
                select(SpatialLocatorRegion).where(
                    SpatialLocatorRegion.locator_id.in_(locator_ids)
                )
            )
        ) if locator_ids else []

        scoped_rows = {
            "assets": _project_rows(list(by_kind.values()), ASSET_FIELDS),
            "asset_representations": _project_rows(representations, REPRESENTATION_FIELDS),
            "content_units": _project_rows(content_units, CONTENT_UNIT_FIELDS),
            "content_unit_embeddings": _project_rows(
                embeddings, EMBEDDING_IDENTITY_FIELDS
            ),
            "evidence_locators": _project_rows(locators, EVIDENCE_LOCATOR_FIELDS),
            "message_citations": _project_rows(citations, CITATION_FIELDS),
            "note_sources": _project_rows(note_sources, NOTE_SOURCE_FIELDS),
            "document_normalized_contents": _project_rows(
                normalized_contents, NORMALIZED_CONTENT_FIELDS
            ),
            "document_blocks": _project_rows(document_blocks, DOCUMENT_BLOCK_FIELDS),
            "document_locator_details": _project_rows(
                document_locator_details, DOCUMENT_LOCATOR_DETAIL_FIELDS
            ),
            "pdf_locator_details": _project_rows(
                pdf_locator_details, PDF_LOCATOR_DETAIL_FIELDS
            ),
            "image_locator_details": _project_rows(
                image_locator_details, IMAGE_LOCATOR_DETAIL_FIELDS
            ),
            "spatial_locator_regions": _project_rows(
                spatial_regions, SPATIAL_REGION_FIELDS
            ),
        }

        citation_kinds = sorted(
            {
                str(row["asset_kind_snapshot"])
                for row in scoped_rows["message_citations"]
                if row.get("asset_kind_snapshot")
            }
        )
        for kind in REQUIRED_KINDS:
            if kind not in citation_kinds:
                raise RuntimeError(
                    f"mixed live snapshot missing historical citation kind={kind}"
                )

        object_keys: list[str] = []
        for asset in by_kind.values():
            if asset.object_key:
                object_keys.append(asset.object_key)
        for rep in representations:
            if rep.object_key:
                object_keys.append(rep.object_key)
        object_keys = sorted(set(object_keys))

        # Verify MinIO objects still exist for durable identity.
        missing_objects = [key for key in object_keys if not object_exists(key)]
        if missing_objects:
            raise RuntimeError(
                f"mixed live snapshot missing MinIO objects count={len(missing_objects)} "
                f"sample={missing_objects[:3]}"
            )

        assets_by_kind = {
            kind: _project_row(by_kind[kind], ASSET_FIELDS) for kind in REQUIRED_KINDS
        }
        live_identity = {
            "assetKinds": list(REQUIRED_KINDS),
            "citationKinds": citation_kinds,
            "sourceAvailableByKind": {
                kind: assets_by_kind[kind]["deleted_at"] is None for kind in REQUIRED_KINDS
            },
            "assetIdsByKind": {kind: assets_by_kind[kind]["id"] for kind in REQUIRED_KINDS},
            "citationIdsByKind": {
                kind: sorted(
                    row["id"]
                    for row in scoped_rows["message_citations"]
                    if row.get("asset_kind_snapshot") == kind
                )
                for kind in REQUIRED_KINDS
            },
            "objectKeyCount": len(object_keys),
        }
        semantic_payload = {
            "workspaceId": workspace_id,
            "assetsByKind": assets_by_kind,
            "scopedRows": scoped_rows,
            "objectKeys": object_keys,
            "liveIdentity": live_identity,
        }
        return {
            "schemaVersion": SCHEMA_VERSION,
            "evidenceMode": EVIDENCE_MODE_LIVE,
            "workspaceId": workspace_id,
            "requiredKinds": list(REQUIRED_KINDS),
            "assetsByKind": assets_by_kind,
            "scopedRows": scoped_rows,
            "objectKeys": object_keys,
            "liveIdentity": live_identity,
            "semanticSha256": _semantic_sha256(semantic_payload),
            "capturedAt": datetime.now(UTC).isoformat(),
        }


def snapshot(*, mode: str, output: Path, workspace_id: str | None) -> dict[str, Any]:
    if mode == "fixture":
        payload = _fixture_snapshot()
    else:
        resolved = workspace_id or os.environ.get("V5D_WORKSPACE_ID")
        if not resolved:
            raise RuntimeError("live snapshot requires --workspace-id or V5D_WORKSPACE_ID")
        payload = _live_snapshot(resolved)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def verify(*, before_path: Path, after_path: Path, output: Path | None) -> dict[str, Any]:
    before = json.loads(before_path.read_text())
    after = json.loads(after_path.read_text())
    if before.get("schemaVersion") != SCHEMA_VERSION or after.get("schemaVersion") != SCHEMA_VERSION:
        raise RuntimeError("mixed restore snapshot schema mismatch")
    if before.get("evidenceMode") != EVIDENCE_MODE_LIVE or after.get("evidenceMode") != EVIDENCE_MODE_LIVE:
        raise RuntimeError("mixed restore verify requires live evidenceMode on both sides")

    mismatches: list[str] = []
    for key in (
        "workspaceId",
        "semanticSha256",
        "requiredKinds",
        "assetsByKind",
        "scopedRows",
        "objectKeys",
        "liveIdentity",
    ):
        if before.get(key) != after.get(key):
            mismatches.append(key)

    result = {
        "schemaVersion": "v5d-mixed-restore-verification-v1",
        "passed": not mismatches,
        "mismatches": mismatches,
        "beforeSemanticSha256": before.get("semanticSha256"),
        "afterSemanticSha256": after.get("semanticSha256"),
        "workspaceId": before.get("workspaceId"),
        "requiredKinds": REQUIRED_KINDS,
    }
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if mismatches:
        raise RuntimeError(f"mixed restore identity mismatch fields={mismatches}")
    return result


def main() -> int:
    args = parse_args()
    if args.command == "snapshot":
        payload = snapshot(
            mode=args.mode, output=args.output, workspace_id=args.workspace_id
        )
        print(
            json.dumps(
                {
                    "schemaVersion": payload["schemaVersion"],
                    "evidenceMode": payload["evidenceMode"],
                    "workspaceId": payload.get("workspaceId"),
                    "semanticSha256": payload.get("semanticSha256"),
                    "output": str(args.output),
                },
                sort_keys=True,
            )
        )
        return 0
    if args.command == "verify":
        result = verify(
            before_path=args.before, after_path=args.after, output=args.output
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    raise SystemExit(f"unknown command {args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - CLI boundary
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        raise SystemExit(1) from error
