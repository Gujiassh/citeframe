#!/usr/bin/env python3
"""Seed the V5-B Document browser state through the deployed API and database.

The upload/finalize/job path is exercised over the real API and Worker. The
Citation and NoteSource are added only after the asset is ready so the browser
replay resolves a generation-scoped production locator.
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
            with urllib.request.urlopen(request, timeout=30) as response:
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


def create_historical_evidence(
    *, user_id: str, workspace_id: str, asset_id: str
) -> dict[str, Any]:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        asset = db.get(Asset, asset_id)
        if asset is None or asset.workspace_id != workspace_id:
            raise RuntimeError("seeded document asset was not found in its workspace")
        unit = db.scalar(
            select(ContentUnit)
            .where(
                ContentUnit.asset_id == asset.id,
                ContentUnit.unit_kind == "document_text_chunk",
            )
            .order_by(ContentUnit.unit_order)
        )
        if unit is None:
            raise RuntimeError("ready Document has no document_text_chunk")
        locator = db.get(EvidenceLocator, unit.source_locator_id)
        representation = db.get(AssetRepresentation, unit.representation_id)
        if locator is None or representation is None:
            raise RuntimeError("ready Document retrieval chain is incomplete")
        detail = db.get(DocumentLocatorDetail, locator.id)
        if detail is None:
            raise RuntimeError("ready Document locator has no document detail")

        citation_locator = clone_evidence_locator(db, locator.id, created_at=now)
        note_locator = clone_evidence_locator(db, citation_locator.id, created_at=now)
        thread = ChatThread(
            workspace_id=workspace_id,
            created_by_user_id=user_id,
            title="Document deployment evidence",
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
            content="Document deployment evidence.",
            status="completed",
            created_at=now,
        )
        note = Note(
            workspace_id=workspace_id,
            created_by_user_id=user_id,
            updated_by_user_id=user_id,
            title="Document deployment note",
            body_md=unit.text_content,
            created_at=now,
            updated_at=now,
        )
        db.add_all([message, note])
        db.flush()
        thread.active_message_id = message.id
        citation = MessageCitation(
            workspace_id=workspace_id,
            message_id=message.id,
            citation_index=0,
            evidence_locator_id=citation_locator.id,
            asset_id=asset.id,
            asset_kind_snapshot="document",
            asset_title_snapshot=asset.title,
            excerpt_snapshot=unit.text_content,
            processing_generation_snapshot=locator.processing_generation_snapshot,
            representation_id_snapshot=representation.id,
            parser_version_snapshot=DOCUMENT_PARSER_VERSION,
            index_version_snapshot=asset.current_index_version,
            created_at=now,
        )
        db.add(citation)
        db.flush()
        note_source = NoteSource(
            workspace_id=workspace_id,
            note_id=note.id,
            source_order=0,
            message_citation_id=citation.id,
            evidence_locator_id=note_locator.id,
            asset_id=asset.id,
            asset_kind_snapshot="document",
            asset_title_snapshot=asset.title,
            excerpt_snapshot=unit.text_content,
            processing_generation_snapshot=locator.processing_generation_snapshot,
            representation_id_snapshot=representation.id,
            parser_version_snapshot=DOCUMENT_PARSER_VERSION,
            index_version_snapshot=asset.current_index_version,
            created_at=now,
        )
        db.add(note_source)
        db.commit()
        return {
            "citationId": citation.id,
            "noteSourceId": note_source.id,
            "documentAssetId": asset.id,
            "expectedProcessingGeneration": locator.processing_generation_snapshot,
            "expectedBlockId": detail.block_id,
            "expectedCharStart": detail.char_start,
            "expectedCharEnd": detail.char_end,
            "expectedTextSha256": detail.text_sha256,
        }


def seed(*, fixture_path: Path, state_path: Path) -> dict[str, Any]:
    email = os.environ["V5B_BROWSER_EMAIL"]
    password = os.environ["V5B_BROWSER_PASSWORD"]
    api = ApiClient(
        os.environ.get("V5B_SEED_API_BASE_URL", "http://api:8000"),
        os.environ["AI_PDF_API_INTERNAL_TOKEN"],
    )
    source = fixture_path.read_bytes()
    fixture = json.loads(fixture_path.with_suffix(".fixture.json").read_text())

    registered = api.request(
        "POST",
        "/v1/auth/register",
        payload={"email": email, "password": password, "name": "V5-B deployment owner"},
    )
    user_id = str(registered["user"]["id"])
    workspace_response = api.request(
        "POST",
        "/v1/workspaces",
        user_id=user_id,
        payload={"name": "V5-B deployment workspace", "description": ""},
    )
    workspace_id = str(workspace_response["workspace"]["id"])
    session = api.request(
        "POST",
        f"/v1/workspaces/{workspace_id}/assets/upload-session",
        user_id=user_id,
        payload={
            "sourceFilename": "markdown-note.md",
            "mimeType": "text/markdown",
            "byteSize": len(source),
            "title": "Markdown Note",
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
        content_type="text/markdown",
    )
    finalized = api.request(
        "POST",
        f"/v1/workspaces/{workspace_id}/assets/{asset_id}/finalize-upload",
        user_id=user_id,
        payload={"objectKey": object_key},
    )
    job = finalized["job"]
    deadline = time.monotonic() + 180
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
                    f"seed ingestion failed status={current['status']} "
                    f"errorCode={current.get('errorCode')} errorMessage={current.get('errorMessage')}"
                )
            break
        if time.monotonic() >= deadline:
            raise TimeoutError(f"seed ingestion timed out job={job['id']}")
        time.sleep(1)

    evidence = create_historical_evidence(
        user_id=user_id, workspace_id=workspace_id, asset_id=asset_id
    )
    state = {
        "schemaVersion": "v5b-document-browser-state-v1",
        "email": email,
        "password": password,
        "workspaceId": workspace_id,
        **evidence,
        "fixtureSourceSha256": fixture["sourceSha256"],
        "seedJobId": job["id"],
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    return {
        "schemaVersion": "v5b-document-deployment-seed-v1",
        "workspaceId": workspace_id,
        "assetId": asset_id,
        "jobId": job["id"],
        "citationId": evidence["citationId"],
        "statePath": str(state_path),
        "sourceSha256": sha256(source).hexdigest(),
        "fixtureSourceSha256": fixture["sourceSha256"],
        "sourceAvailable": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    result = seed(fixture_path=args.fixture, state_path=args.state)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
