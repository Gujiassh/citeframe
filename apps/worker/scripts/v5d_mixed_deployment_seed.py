#!/usr/bin/env python3
"""Seed one Workspace with PDF + Image + Markdown Document for V5-D mixed gates.

Upload/finalize/job path is exercised over the real API and Worker for all three
modalities. Historical MessageCitations are attached only after assets are ready
so production-start browser replay can open typed locators without mocking BFF.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ai_pdf_api.db.session import SessionLocal
from ai_pdf_api.modalities.document import DOCUMENT_PARSER_VERSION
from ai_pdf_api.modalities.evidence import clone_evidence_locator
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ChatMessage,
    ChatThread,
    ContentUnit,
    DocumentLocatorDetail,
    EvidenceLocator,
    MessageCitation,
    Note,
    NoteSource,
)

SCHEMA_VERSION = "v5d-mixed-browser-state-v1"
SEED_RESULT_SCHEMA = "v5d-mixed-deployment-seed-v1"

UNIT_KIND_BY_ASSET_KIND = {
    "pdf": ("pdf_text_chunk", "pdf_ocr_region"),
    "image": ("image_ocr_region", "image_caption"),
    "document": ("document_text_chunk",),
}


class ApiError(RuntimeError):
    pass


class ApiClient:
    def __init__(self, base_url: str, internal_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.internal_token = internal_token

    def request(
        self,
        method: str,
        path: str,
        *,
        user_id: str | None = None,
        payload: dict[str, Any] | None = None,
        body: bytes | None = None,
        content_type: str | None = None,
        timeout: float = 60,
    ) -> Any:
        headers = {"x-ai-pdf-internal-token": self.internal_token}
        if user_id:
            headers["x-user-id"] = user_id
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=body, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                response_body = response.read()
                status = response.status
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise ApiError(f"{method} {path} status={error.code} body={detail}") from error
        if status < 200 or status >= 300:
            raise ApiError(f"{method} {path} status={status}")
        if not response_body:
            return None
        return json.loads(response_body)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_fixtures() -> dict[str, dict[str, str]]:
    root = _repo_root()
    return {
        "pdf": {
            "path": str(root / "docs/fixtures/evidence-contract/pdf-coordinate-fixture.pdf"),
            "sourceFilename": "pdf-coordinate-fixture.pdf",
            "mimeType": "application/pdf",
            "title": "Mixed PDF Fixture",
        },
        "image": {
            "path": str(root / "docs/fixtures/evidence-contract/image-coordinate-fixture.png"),
            "sourceFilename": "image-coordinate-fixture.png",
            "mimeType": "image/png",
            "title": "Mixed Image Fixture",
        },
        "document": {
            "path": str(root / "docs/fixtures/document-modality/markdown-note.md"),
            "sourceFilename": "markdown-note.md",
            "mimeType": "text/markdown",
            "title": "Mixed Markdown Fixture",
        },
    }


def _upload_and_wait(
    api: ApiClient,
    *,
    user_id: str,
    workspace_id: str,
    source: bytes,
    source_filename: str,
    mime_type: str,
    title: str,
    timeout_seconds: float = 300,
) -> dict[str, Any]:
    session = api.request(
        "POST",
        f"/v1/workspaces/{workspace_id}/assets/upload-session",
        user_id=user_id,
        payload={
            "sourceFilename": source_filename,
            "mimeType": mime_type,
            "byteSize": len(source),
            "title": title,
        },
    )
    asset = session["asset"]
    asset_id = str(asset["id"])
    object_key = str(session["upload"]["objectKey"])
    api.request(
        "PUT",
        f"/v1/workspaces/{workspace_id}/assets/{asset_id}/upload?{urllib.parse.urlencode({'objectKey': object_key})}",
        user_id=user_id,
        body=source,
        content_type=mime_type,
    )
    finalized = api.request(
        "POST",
        f"/v1/workspaces/{workspace_id}/assets/{asset_id}/finalize-upload",
        user_id=user_id,
        payload={"objectKey": object_key},
    )
    job = finalized["job"]
    deadline = time.monotonic() + timeout_seconds
    while True:
        job_payload = api.request(
            "GET",
            f"/v1/workspaces/{workspace_id}/jobs/{job['id']}",
            user_id=user_id,
        )
        current = job_payload["job"]
        if current["status"] in {"succeeded", "failed", "cancelled"}:
            if current["status"] != "succeeded":
                raise RuntimeError(
                    f"seed ingestion failed kind_hint={mime_type} status={current['status']} "
                    f"errorCode={current.get('errorCode')} errorMessage={current.get('errorMessage')}"
                )
            break
        if time.monotonic() >= deadline:
            raise TimeoutError(f"seed ingestion timed out job={job['id']} mime={mime_type}")
        time.sleep(1)
    return {
        "assetId": asset_id,
        "jobId": job["id"],
        "kind": asset.get("kind"),
        "sourceSha256": sha256(source).hexdigest(),
        "mimeType": mime_type,
        "sourceFilename": source_filename,
        "title": title,
    }


def _pick_unit(db: Any, asset_id: str, preferred_kinds: tuple[str, ...]) -> ContentUnit:
    for unit_kind in preferred_kinds:
        unit = db.scalar(
            select(ContentUnit)
            .where(ContentUnit.asset_id == asset_id, ContentUnit.unit_kind == unit_kind)
            .order_by(ContentUnit.unit_order)
        )
        if unit is not None:
            return unit
    raise RuntimeError(
        f"ready asset={asset_id} has no content unit in kinds={preferred_kinds}"
    )


def create_mixed_historical_evidence(
    *, user_id: str, workspace_id: str, assets: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        thread = ChatThread(
            workspace_id=workspace_id,
            created_by_user_id=user_id,
            title="V5-D Mixed deployment evidence",
            last_message_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(thread)
        db.flush()
        message = ChatMessage(
            workspace_id=workspace_id,
            thread_id=thread.id,
            role="assistant",
            content="Mixed PDF, image, and markdown evidence.",
            status="completed",
            created_at=now,
        )
        note = Note(
            workspace_id=workspace_id,
            created_by_user_id=user_id,
            updated_by_user_id=user_id,
            title="Mixed deployment note",
            body_md="PDF + Image + Markdown historical evidence.",
            created_at=now,
            updated_at=now,
        )
        db.add_all([message, note])
        db.flush()
        thread.active_message_id = message.id

        citation_ids: dict[str, str] = {}
        note_source_ids: dict[str, str] = {}
        evidence: dict[str, Any] = {}
        citation_index = 0
        note_order = 0

        for kind in ("pdf", "image", "document"):
            asset_id = assets[kind]["assetId"]
            asset = db.get(Asset, asset_id)
            if asset is None or asset.workspace_id != workspace_id:
                raise RuntimeError(f"seeded {kind} asset was not found in its workspace")
            if asset.status != "ready":
                raise RuntimeError(f"seeded {kind} asset status={asset.status} expected=ready")
            unit = _pick_unit(db, asset_id, UNIT_KIND_BY_ASSET_KIND[kind])
            locator = db.get(EvidenceLocator, unit.source_locator_id)
            representation = db.get(AssetRepresentation, unit.representation_id)
            if locator is None or representation is None:
                raise RuntimeError(f"ready {kind} retrieval chain is incomplete")

            citation_locator = clone_evidence_locator(db, locator.id, created_at=now)
            note_locator = clone_evidence_locator(db, citation_locator.id, created_at=now)
            parser_version = representation.generator_version
            if kind == "document":
                parser_version = DOCUMENT_PARSER_VERSION

            citation = MessageCitation(
                workspace_id=workspace_id,
                message_id=message.id,
                citation_index=citation_index,
                evidence_locator_id=citation_locator.id,
                asset_id=asset.id,
                asset_kind_snapshot=asset.asset_kind,
                asset_title_snapshot=asset.title,
                excerpt_snapshot=unit.text_content[:500],
                processing_generation_snapshot=locator.processing_generation_snapshot,
                representation_id_snapshot=representation.id,
                parser_version_snapshot=parser_version,
                index_version_snapshot=asset.current_index_version,
                created_at=now,
            )
            db.add(citation)
            db.flush()
            note_source = NoteSource(
                workspace_id=workspace_id,
                note_id=note.id,
                source_order=note_order,
                message_citation_id=citation.id,
                evidence_locator_id=note_locator.id,
                asset_id=asset.id,
                asset_kind_snapshot=asset.asset_kind,
                asset_title_snapshot=asset.title,
                excerpt_snapshot=unit.text_content[:500],
                processing_generation_snapshot=locator.processing_generation_snapshot,
                representation_id_snapshot=representation.id,
                parser_version_snapshot=parser_version,
                index_version_snapshot=asset.current_index_version,
                created_at=now,
            )
            db.add(note_source)
            db.flush()

            citation_ids[kind] = citation.id
            note_source_ids[kind] = note_source.id
            entry: dict[str, Any] = {
                "assetId": asset.id,
                "citationId": citation.id,
                "noteSourceId": note_source.id,
                "expectedProcessingGeneration": locator.processing_generation_snapshot,
                "representationId": representation.id,
                "locatorKind": locator.locator_kind,
                "unitKind": unit.unit_kind,
                "excerpt": unit.text_content[:200],
            }
            if kind == "document":
                detail = db.get(DocumentLocatorDetail, locator.id)
                if detail is None:
                    raise RuntimeError("ready Document locator has no document detail")
                entry.update(
                    {
                        "expectedBlockId": detail.block_id,
                        "expectedCharStart": detail.char_start,
                        "expectedCharEnd": detail.char_end,
                        "expectedTextSha256": detail.text_sha256,
                    }
                )
            evidence[kind] = entry
            citation_index += 1
            note_order += 1

        db.commit()
        return {
            "threadId": thread.id,
            "messageId": message.id,
            "noteId": note.id,
            "citationIds": citation_ids,
            "noteSourceIds": note_source_ids,
            "evidence": evidence,
        }


def seed(*, state_path: Path, fixtures: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    email = os.environ["V5D_BROWSER_EMAIL"]
    password = os.environ["V5D_BROWSER_PASSWORD"]
    api = ApiClient(
        os.environ.get("V5D_SEED_API_BASE_URL", "http://api:8000"),
        os.environ["AI_PDF_API_INTERNAL_TOKEN"],
    )
    fixture_map = fixtures or _default_fixtures()
    for kind, meta in fixture_map.items():
        path = Path(meta["path"])
        if not path.is_file():
            raise FileNotFoundError(f"mixed seed fixture missing kind={kind} path={path}")

    registered = api.request(
        "POST",
        "/v1/auth/register",
        payload={"email": email, "password": password, "name": "V5-D mixed deployment owner"},
    )
    user_id = str(registered["user"]["id"])
    workspace_response = api.request(
        "POST",
        "/v1/workspaces",
        user_id=user_id,
        payload={"name": "V5-D Mixed Workspace", "description": "PDF + Image + Markdown"},
    )
    workspace_id = str(workspace_response["workspace"]["id"])

    assets: dict[str, dict[str, Any]] = {}
    for kind in ("pdf", "image", "document"):
        meta = fixture_map[kind]
        source = Path(meta["path"]).read_bytes()
        assets[kind] = _upload_and_wait(
            api,
            user_id=user_id,
            workspace_id=workspace_id,
            source=source,
            source_filename=meta["sourceFilename"],
            mime_type=meta["mimeType"],
            title=meta["title"],
        )

    historical = create_mixed_historical_evidence(
        user_id=user_id, workspace_id=workspace_id, assets=assets
    )
    state = {
        "schemaVersion": SCHEMA_VERSION,
        "email": email,
        "password": password,
        "userId": user_id,
        "workspaceId": workspace_id,
        "threadId": historical["threadId"],
        "messageId": historical["messageId"],
        "assets": {
            kind: {
                "assetId": assets[kind]["assetId"],
                "kind": kind,
                "mimeType": assets[kind]["mimeType"],
                "sourceFilename": assets[kind]["sourceFilename"],
                "title": assets[kind]["title"],
                "sourceSha256": assets[kind]["sourceSha256"],
                "jobId": assets[kind]["jobId"],
            }
            for kind in ("pdf", "image", "document")
        },
        "citationIds": historical["citationIds"],
        "noteSourceIds": historical["noteSourceIds"],
        "evidence": historical["evidence"],
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    return {
        "schemaVersion": SEED_RESULT_SCHEMA,
        "workspaceId": workspace_id,
        "userId": user_id,
        "assets": {kind: assets[kind]["assetId"] for kind in assets},
        "citationIds": historical["citationIds"],
        "threadId": historical["threadId"],
        "statePath": str(state_path),
        "sourceAvailable": True,
        "modalities": ["pdf", "image", "document"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed mixed PDF+Image+Document workspace")
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, default=None)
    parser.add_argument("--image", type=Path, default=None)
    parser.add_argument("--document", type=Path, default=None)
    args = parser.parse_args()
    fixtures = _default_fixtures()
    if args.pdf is not None:
        fixtures["pdf"]["path"] = str(args.pdf)
    if args.image is not None:
        fixtures["image"]["path"] = str(args.image)
    if args.document is not None:
        fixtures["document"]["path"] = str(args.document)
    result = seed(state_path=args.state, fixtures=fixtures)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
