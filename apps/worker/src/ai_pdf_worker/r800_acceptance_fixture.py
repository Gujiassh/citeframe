"""Deterministic PDF, object-store, and database seeding for R800 acceptance."""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256

import fitz
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ContentUnit,
    ContentUnitEmbedding,
    EvidenceLocator,
    PdfLocatorDetail,
    PdfPage,
    User,
    Workspace,
    WorkspaceMembership,
)
from sqlalchemy.orm import Session

from ai_pdf_worker.r800_acceptance_common import (
    API_BASE_URL,
    IDS,
    NOW,
    SCHEMA_VERSION,
    SOURCE_TEXT,
    _canonical_bytes,
    _fixture_facts,
)


def _pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 96), "Citeframe R800 Research Acceptance", fontsize=18)
    page.insert_textbox(fitz.Rect(72, 132, 540, 300), SOURCE_TEXT, fontsize=12)
    document.set_metadata({"title": "R800 Research Acceptance", "author": "Citeframe"})
    payload = document.tobytes(garbage=4, deflate=True)
    document.close()
    return payload


def seed_state(
    session_factory: Callable[[], Session],
    *,
    uploader: Callable[[str, bytes, str], None],
    cleanup: Callable[[str], None],
) -> dict[str, object]:
    source = _pdf_bytes()
    source_key = (
        f"workspaces/{IDS['workspace']}/assets/{IDS['asset']}/source/"
        "r800-research.pdf"
    )
    representation_payload = _canonical_bytes(
        {"schemaVersion": 1, "page": 1, "textSha256": sha256(SOURCE_TEXT.encode()).hexdigest()}
    )
    representation_key = (
        f"workspaces/{IDS['workspace']}/assets/{IDS['asset']}/representations/"
        "1/pdf_page_layout.json"
    )
    stored: list[str] = []
    with session_factory() as db:
        if db.get(Workspace, IDS["workspace"]) is not None:
            raise RuntimeError("R800 workspace already exists; seed requires an empty acceptance deployment")
        users = [
            User(
                id=IDS[role],
                email=f"r800-{role}@example.com",
                name=f"R800 {role.title()}",
                password_hash="r800-not-used-by-internal-http",
                avatar_url="",
                created_at=NOW,
                updated_at=NOW,
            )
            for role in ("owner", "creator", "member")
        ]
        workspace = Workspace(
            id=IDS["workspace"],
            name="R800 Research Acceptance",
            description="Isolated Research runtime and restore oracle",
            system_prompt="Answer only from immutable Evidence.",
            retrieval_top_k=10,
            chunk_size=1200,
            created_by_user_id=IDS["owner"],
            created_at=NOW,
            updated_at=NOW,
        )
        db.add_all([*users, workspace])
        db.flush()
        db.add_all(
            [
                WorkspaceMembership(
                    id=IDS[f"{role}-membership"],
                    workspace_id=workspace.id,
                    user_id=IDS[role],
                    role="owner" if role == "owner" else "member",
                    created_at=NOW,
                )
                for role in ("owner", "creator", "member")
            ]
        )
        asset = Asset(
            id=IDS["asset"],
            workspace_id=workspace.id,
            created_by_user_id=IDS["creator"],
            asset_kind="pdf",
            title="r800-research.pdf",
            source_filename="r800-research.pdf",
            object_key=source_key,
            mime_type="application/pdf",
            byte_size=len(source),
            source_sha256=sha256(source).hexdigest(),
            status="ready",
            current_processing_generation=1,
            current_index_version=1,
            created_at=NOW,
            updated_at=NOW,
        )
        representation = AssetRepresentation(
            id=IDS["representation"],
            workspace_id=workspace.id,
            asset_id=asset.id,
            representation_kind="pdf_page_layout",
            processing_generation=1,
            generator_provider="r800",
            generator_model="deterministic",
            generator_version="r800-v1",
            object_key=representation_key,
            content_sha256=sha256(representation_payload).hexdigest(),
            created_at=NOW,
        )
        db.add_all([asset, representation])
        db.flush()
        page = PdfPage(
            id=IDS["page"],
            workspace_id=workspace.id,
            asset_id=asset.id,
            representation_id=representation.id,
            page_number=1,
            media_x0_points=0,
            media_y0_points=0,
            media_x1_points=612,
            media_y1_points=792,
            crop_x0_points=0,
            crop_y0_points=0,
            crop_x1_points=612,
            crop_y1_points=792,
            rotation_degrees=0,
            display_width_points=612,
            display_height_points=792,
            extracted_text=SOURCE_TEXT,
            char_count=len(SOURCE_TEXT),
            legacy_ocr_blocks=[],
            created_at=NOW,
        )
        locator = EvidenceLocator(
            id=IDS["locator"],
            workspace_id=workspace.id,
            asset_id=asset.id,
            locator_kind="pdf_page",
            locator_version=1,
            processing_generation_snapshot=1,
            representation_id_snapshot=representation.id,
            created_at=NOW,
        )
        db.add_all([page, locator])
        db.flush()
        db.add(
            PdfLocatorDetail(
                locator_id=locator.id,
                page_id=page.id,
                page_number=1,
                coordinate_space=None,
                crop_x0_points=0,
                crop_y0_points=0,
                crop_x1_points=612,
                crop_y1_points=792,
                rotation_degrees=0,
                display_width_points=612,
                display_height_points=792,
            )
        )
        unit = ContentUnit(
            id=IDS["unit"],
            workspace_id=workspace.id,
            asset_id=asset.id,
            representation_id=representation.id,
            source_locator_id=locator.id,
            unit_kind="pdf_text_chunk",
            unit_order=0,
            text_content=SOURCE_TEXT,
            token_count=len(SOURCE_TEXT.split()),
            char_start=0,
            char_end=len(SOURCE_TEXT),
            index_version=1,
            created_at=NOW,
        )
        db.add(unit)
        db.flush()
        db.add(
            ContentUnitEmbedding(
                id=IDS["embedding"],
                workspace_id=workspace.id,
                asset_id=asset.id,
                content_unit_id=unit.id,
                processing_generation=1,
                index_version=1,
                is_current=True,
                embedding_space="text",
                provider="ollama",
                model="qwen3-embedding:0.6b",
                dimensions=1024,
                version="embedding-v1",
                embedding=[1.0, *([0.0] * 1023)],
                created_at=NOW,
            )
        )
        try:
            uploader(source_key, source, "application/pdf")
            stored.append(source_key)
            uploader(representation_key, representation_payload, "application/json")
            stored.append(representation_key)
            db.commit()
        except Exception:
            db.rollback()
            for object_key in reversed(stored):
                cleanup(object_key)
            raise
    return {
        "schemaVersion": SCHEMA_VERSION,
        **_fixture_facts(),
        "source": {
            "objectKey": source_key,
            "byteSize": len(source),
            "sha256": sha256(source).hexdigest(),
        },
        "httpAuth": {
            "baseUrl": API_BASE_URL,
            "internalTokenHeader": "x-ai-pdf-internal-token",
            "userHeader": "x-user-id",
            "actors": {
                "owner": IDS["owner"],
                "creator": IDS["creator"],
                "member": IDS["member"],
            },
        },
    }
