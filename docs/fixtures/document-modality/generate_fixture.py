#!/usr/bin/env python3
"""Regenerate document-modality fixture oracles from the production Markdown parser.

This generator imports the current worktree Worker parse entrypoint and API stable
identity helpers. It does not re-exec source text, does not use sibling worktrees,
and does not write production modules.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SOURCE = Path(__file__).resolve().parent / "markdown-note.md"
OUT = Path(__file__).resolve().parent / "markdown-note.fixture.json"

API_SRC = ROOT / "apps" / "api" / "src"
WORKER_SRC = ROOT / "apps" / "worker" / "src"


def _ensure_worktree_imports() -> None:
    """Put this worktree's API/Worker packages on sys.path and import production helpers."""
    missing = [str(path) for path in (API_SRC, WORKER_SRC) if not path.is_dir()]
    if missing:
        raise SystemExit(
            "document fixture generator requires production package trees; missing: "
            + ", ".join(missing)
        )
    for path in (API_SRC, WORKER_SRC):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)

    try:
        from ai_pdf_api.modalities.document import (  # noqa: F401
            DOCUMENT_NORMALIZATION_VERSION,
            DOCUMENT_PARSER_VERSION,
            stable_document_block_id,
            text_sha256,
        )
        from ai_pdf_worker.document_markdown import parse_markdown_document  # noqa: F401
    except Exception as error:  # pragma: no cover - import failure is operator-facing
        raise SystemExit(
            "document fixture generator could not import production parser/helpers from "
            f"{API_SRC} and {WORKER_SRC}: {error}"
        ) from error


def build_fixture(*, source_path: Path = SOURCE) -> dict[str, Any]:
    """Parse the canonical Markdown source with production helpers and build the oracle."""
    _ensure_worktree_imports()
    from ai_pdf_api.modalities.document import (
        DOCUMENT_NORMALIZATION_VERSION,
        DOCUMENT_PARSER_VERSION,
        stable_document_block_id,
        text_sha256,
    )
    from ai_pdf_worker.document_markdown import parse_markdown_document

    source = source_path.read_bytes()
    result = parse_markdown_document(source, mime_type="text/markdown")

    blocks: list[dict[str, Any]] = []
    locators: list[dict[str, Any]] = []
    for block in result.blocks:
        text_digest = text_sha256(block.text)
        block_id = stable_document_block_id(
            source_sha256=result.source_sha256,
            parser_version=DOCUMENT_PARSER_VERSION,
            block_order=block.block_order,
            block_kind=block.block_kind,
            heading_path=list(block.heading_path),
            text_sha256=text_digest,
        )
        blocks.append(
            {
                "blockOrder": block.block_order,
                "blockKind": block.block_kind,
                "headingLevel": block.heading_level,
                "headingPath": list(block.heading_path),
                "text": block.text,
                "charStart": block.char_start,
                "charEnd": block.char_end,
                "textSha256": text_digest,
                "blockId": block_id,
                "normalizationVersion": DOCUMENT_NORMALIZATION_VERSION,
            }
        )
        # DocumentAnchorLocator contract does not include headingLevel.
        locators.append(
            {
                "kind": "document_anchor",
                "version": 1,
                "blockId": block_id,
                "blockKind": block.block_kind,
                "headingPath": list(block.heading_path),
                "charStart": block.char_start,
                "charEnd": block.char_end,
                "textSha256": text_digest,
                "normalizationVersion": DOCUMENT_NORMALIZATION_VERSION,
            }
        )

    primary = next(block for block in blocks if block["blockKind"] == "paragraph")
    primary_locator = next(item for item in locators if item["blockId"] == primary["blockId"])
    relative_source = source_path.resolve().relative_to(ROOT).as_posix()

    return {
        "schemaVersion": "document-modality-fixture-v1",
        "assetKind": "document",
        "format": "markdown",
        "mimeType": "text/markdown",
        "acceptedMimeTypes": ["text/markdown"],
        "rejectedMimeTypes": ["text/html", "application/pdf", "image/png"],
        "parserVersion": DOCUMENT_PARSER_VERSION,
        "normalizationVersion": DOCUMENT_NORMALIZATION_VERSION,
        "sourceFilename": source_path.name,
        "sourcePath": relative_source,
        "sourceSha256": result.source_sha256,
        "byteSize": len(source),
        "normalizedText": result.normalized_text,
        "normalizedContentSha256": result.content_sha256,
        "normalizedContentType": "text/plain; charset=utf-8",
        "representationKinds": ["document_source", "document_normalized"],
        # Actual retrieval ContentUnit kind only; DocumentBlock rows are structure, not units.
        "contentUnitKinds": ["document_text_chunk"],
        "locatorKind": "document_anchor",
        "locatorDetailFamily": "record",
        "retrieval": {
            "embeddingSpace": "text",
            "channels": ["text", "lexical"],
            "unitKinds": ["document_text_chunk"],
            "expectedPrimaryExcerpt": primary["text"],
        },
        "blocks": blocks,
        "locatorSnapshots": locators,
        "expectedCitationProjection": {
            "assetKind": "document",
            "assetTitle": "Markdown Note",
            "sourceAvailable": True,
            "excerpt": primary["text"],
            "locator": primary_locator,
            "sourceVersions": {
                "parserVersion": DOCUMENT_PARSER_VERSION,
                "processingGeneration": 1,
                "representationId": "rep_document_normalized_fixture_v1",
                "indexVersion": 1,
            },
        },
        "expectedNoteSourceProjection": {
            "assetKind": "document",
            "assetTitle": "Markdown Note",
            "sourceAvailable": True,
            "excerpt": primary["text"],
            "locator": primary_locator,
            "sourceVersions": {
                "parserVersion": DOCUMENT_PARSER_VERSION,
                "processingGeneration": 1,
                "representationId": "rep_document_normalized_fixture_v1",
                "indexVersion": 1,
            },
        },
        "historicalAfterDeleteProjection": {
            "sourceAvailable": False,
            "locatorUnchanged": True,
            "sourceVersionsUnchanged": True,
        },
        "failureContracts": [
            {
                "id": "invalid-utf8",
                "payloadBase64": "//5ub3QgdXRmOA==",
                "mimeType": "text/markdown",
                "expectedErrorCode": "asset_encoding_unsupported",
                "persistDerivedRows": False,
            },
            {
                "id": "invalid-mime-html",
                "payloadText": "# x\n",
                "mimeType": "text/html",
                "expectedErrorCode": "asset_mime_mismatch",
                "persistDerivedRows": False,
            },
            {
                "id": "empty-bytes",
                "payloadText": "",
                "mimeType": "text/markdown",
                "expectedErrorCode": "asset_bytes_invalid",
                "persistDerivedRows": False,
            },
            {
                "id": "binary-nul",
                "payloadBase64": "IyB4AHkK",
                "mimeType": "text/markdown",
                "expectedErrorCode": "asset_bytes_invalid",
                "persistDerivedRows": False,
            },
            {
                "id": "pdf-signature",
                "payloadText": "%PDF-1.4\n",
                "mimeType": "text/markdown",
                "expectedErrorCode": "asset_bytes_invalid",
                "persistDerivedRows": False,
            },
        ],
        "lifecycleInvariants": {
            "retryIdempotent": True,
            "partialObjectCleanupOnFailure": True,
            "deleteNoResurrection": True,
            "historicalSnapshotReadable": True,
            "backupRestoreTypedTables": [
                "document_normalized_contents",
                "document_blocks",
                "document_locator_details",
                "asset_types",
                "representation_types",
                "content_unit_types",
                "locator_types",
            ],
        },
    }


def main() -> int:
    fixture = build_fixture()
    OUT.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
