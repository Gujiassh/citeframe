from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import fitz
from ai_pdf_api.core.security import hash_password
from ai_pdf_api.core.settings import settings
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ChatMessage,
    ChatThread,
    ContentUnit,
    ContentUnitEmbedding,
    EvidenceLocator,
    ImageLocatorDetail,
    ImageRepresentationGeometry,
    IngestionJob,
    MessageCitation,
    MessageInputEvidence,
    MessageRetrievalScope,
    MessageRetrievalScopeAsset,
    Note,
    NoteSource,
    PdfLocatorDetail,
    PdfPage,
    SpatialLocatorRegion,
    User,
    Workspace,
    WorkspaceMembership,
)
from ai_pdf_api.services.storage import (
    build_storage_client,
    download_bytes,
    object_exists,
    upload_bytes,
)
from PIL import Image, ImageDraw
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

SCHEMA_VERSION = "m403-restore-acceptance-v1"
NOW = datetime(2026, 1, 15, 8, 30, tzinfo=UTC)
PASSWORD = "M403-restore-acceptance!"


def _expect_image_enabled() -> bool:
    value = os.environ.get("M403_EXPECT_IMAGE_ENABLED", "false").strip().lower()
    if value not in {"true", "false"}:
        raise ValueError("M403_EXPECT_IMAGE_ENABLED must be true or false")
    return value == "true"


def _id(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"https://citeframe.local/m403/{name}"))


IDS = {
    name: _id(name)
    for name in (
        "user",
        "workspace",
        "membership",
        "pdf",
        "image",
        "deleted-pdf",
        "deleted-image",
        "failed-image",
        "thread",
        "all-user",
        "all-assistant",
        "selected-user",
        "selected-assistant",
        "failed-user",
        "failed-assistant",
        "note",
        "failed-job",
    )
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed and verify M403 restore semantics.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    seed_parser = subparsers.add_parser("seed")
    seed_parser.add_argument("--state", type=Path)
    snapshot_parser = subparsers.add_parser("snapshot")
    snapshot_parser.add_argument("--output", type=Path)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--before", type=Path, required=True)
    verify_parser.add_argument("--after", type=Path, required=True)
    verify_parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.draw_rect(fitz.Rect(72, 144, 360, 360), color=(0.1, 0.35, 0.7), width=3)
    page.insert_text((92, 120), "M403 historical PDF evidence", fontsize=18)
    page.insert_text((92, 190), "Generation one remains frozen after restore.", fontsize=12)
    page.insert_text((92, 410), "Current generation two uses the same immutable source.", fontsize=12)
    document.set_metadata({"title": "M403 restore fixture", "author": "Citeframe"})
    payload = document.tobytes(garbage=4, deflate=True)
    document.close()
    return payload


def _png_bytes(generation: int) -> bytes:
    image = Image.new("RGB", (640, 480), "white")
    draw = ImageDraw.Draw(image)
    color = (18, 109, 92) if generation == 1 else (188, 63, 47)
    draw.rectangle((96, 96, 416, 312), fill=color, outline=(20, 20, 20), width=4)
    draw.text((112, 112), f"M403 generation {generation}", fill="white")
    draw.text((112, 344), "Historical image region", fill=(20, 20, 20))
    output = BytesIO()
    image.save(output, format="PNG", optimize=False)
    return output.getvalue()


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _object_key(asset: Asset, suffix: str) -> str:
    return f"workspaces/{asset.workspace_id}/assets/{asset.id}/{suffix}"


def _add_asset(
    db: Session,
    *,
    name: str,
    kind: str,
    title: str,
    payload: bytes,
    mime_type: str,
    status: str,
    generation: int,
    index_version: int,
    deleted: bool = False,
) -> Asset:
    asset = Asset(
        id=IDS[name],
        workspace_id=IDS["workspace"],
        created_by_user_id=IDS["user"],
        asset_kind=kind,
        title=title,
        source_filename=title,
        object_key=f"workspaces/{IDS['workspace']}/assets/{IDS[name]}/source/{title}",
        mime_type=mime_type,
        byte_size=len(payload),
        source_sha256=sha256(payload).hexdigest(),
        status=status,
        current_processing_generation=generation,
        current_index_version=index_version,
        last_error_code="fixture_failure" if status == "failed" else None,
        last_error_message="Deterministic failed branch" if status == "failed" else None,
        deleted_at=NOW + timedelta(hours=2) if deleted else None,
        created_at=NOW,
        updated_at=NOW + timedelta(hours=2) if deleted else NOW,
    )
    db.add(asset)
    db.flush()
    if not deleted:
        upload_bytes(asset.object_key, payload, mime_type)
    return asset


def _add_representation(
    db: Session,
    *,
    asset: Asset,
    name: str,
    kind: str,
    generation: int,
    payload: bytes,
    content_type: str,
    deleted: bool = False,
) -> AssetRepresentation:
    representation = AssetRepresentation(
        id=_id(name),
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        representation_kind=kind,
        processing_generation=generation,
        generator_provider="m403",
        generator_model="deterministic",
        generator_version="m403-v1",
        object_key=_object_key(asset, f"representations/{generation}/{kind}"),
        content_sha256=sha256(payload).hexdigest(),
        created_at=NOW + timedelta(minutes=generation),
    )
    db.add(representation)
    db.flush()
    if not deleted:
        upload_bytes(representation.object_key, payload, content_type)
    return representation


def _add_pdf_locator(
    db: Session,
    *,
    name: str,
    asset: Asset,
    representation: AssetRepresentation,
    page: PdfPage,
    kind: str,
    region: tuple[float, float, float, float] | None,
) -> EvidenceLocator:
    locator = EvidenceLocator(
        id=_id(name),
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        locator_kind=kind,
        locator_version=1,
        processing_generation_snapshot=representation.processing_generation,
        representation_id_snapshot=representation.id,
        created_at=NOW + timedelta(minutes=representation.processing_generation),
    )
    db.add(locator)
    db.flush()
    db.add(
        PdfLocatorDetail(
            locator_id=locator.id,
            page_id=page.id,
            page_number=1,
            coordinate_space="pdf_crop_box_normalized_top_left_v1" if region else None,
            crop_x0_points=0,
            crop_y0_points=0,
            crop_x1_points=612,
            crop_y1_points=792,
            rotation_degrees=0,
            display_width_points=612,
            display_height_points=792,
        )
    )
    if region:
        db.add(
            SpatialLocatorRegion(
                id=_id(f"{name}-region"),
                locator_id=locator.id,
                region_order=0,
                x=region[0],
                y=region[1],
                width=region[2],
                height=region[3],
            )
        )
    db.flush()
    return locator


def _add_image_locator(
    db: Session,
    *,
    name: str,
    asset: Asset,
    representation: AssetRepresentation,
    region: tuple[float, float, float, float],
) -> EvidenceLocator:
    locator = EvidenceLocator(
        id=_id(name),
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        locator_kind="image_region",
        locator_version=1,
        processing_generation_snapshot=representation.processing_generation,
        representation_id_snapshot=representation.id,
        created_at=NOW + timedelta(minutes=representation.processing_generation),
    )
    db.add(locator)
    db.flush()
    db.add(
        ImageLocatorDetail(
            locator_id=locator.id,
            coordinate_space="image_normalized_top_left_v1",
            width_pixels=640,
            height_pixels=480,
            orientation_applied=True,
        )
    )
    db.add(
        SpatialLocatorRegion(
            id=_id(f"{name}-region"),
            locator_id=locator.id,
            region_order=0,
            x=region[0],
            y=region[1],
            width=region[2],
            height=region[3],
        )
    )
    db.flush()
    return locator


def _clone_locator(db: Session, source: EvidenceLocator, name: str) -> EvidenceLocator:
    locator = EvidenceLocator(
        id=_id(name),
        workspace_id=source.workspace_id,
        asset_id=source.asset_id,
        locator_kind=source.locator_kind,
        locator_version=source.locator_version,
        processing_generation_snapshot=source.processing_generation_snapshot,
        representation_id_snapshot=source.representation_id_snapshot,
        created_at=NOW + timedelta(hours=1),
    )
    db.add(locator)
    db.flush()
    pdf = db.get(PdfLocatorDetail, source.id)
    image = db.get(ImageLocatorDetail, source.id)
    if pdf:
        db.add(
            PdfLocatorDetail(
                locator_id=locator.id,
                page_id=pdf.page_id,
                page_number=pdf.page_number,
                coordinate_space=pdf.coordinate_space,
                crop_x0_points=pdf.crop_x0_points,
                crop_y0_points=pdf.crop_y0_points,
                crop_x1_points=pdf.crop_x1_points,
                crop_y1_points=pdf.crop_y1_points,
                rotation_degrees=pdf.rotation_degrees,
                display_width_points=pdf.display_width_points,
                display_height_points=pdf.display_height_points,
            )
        )
    elif image:
        db.add(
            ImageLocatorDetail(
                locator_id=locator.id,
                coordinate_space=image.coordinate_space,
                width_pixels=image.width_pixels,
                height_pixels=image.height_pixels,
                orientation_applied=image.orientation_applied,
            )
        )
    else:
        raise RuntimeError(f"Typed locator detail missing for {source.id}")
    for region in db.scalars(
        select(SpatialLocatorRegion)
        .where(SpatialLocatorRegion.locator_id == source.id)
        .order_by(SpatialLocatorRegion.region_order)
    ):
        db.add(
            SpatialLocatorRegion(
                id=_id(f"{name}-region-{region.region_order}"),
                locator_id=locator.id,
                region_order=region.region_order,
                x=region.x,
                y=region.y,
                width=region.width,
                height=region.height,
            )
        )
    db.flush()
    return locator


def _add_content(
    db: Session,
    *,
    name: str,
    asset: Asset,
    representation: AssetRepresentation,
    locator: EvidenceLocator,
    kind: str,
    text_content: str,
    index_version: int,
    vector_head: float,
) -> None:
    unit = ContentUnit(
        id=_id(f"{name}-unit"),
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        representation_id=representation.id,
        source_locator_id=locator.id,
        unit_kind=kind,
        unit_order=0,
        text_content=text_content,
        token_count=len(text_content.split()),
        char_start=None,
        char_end=None,
        index_version=index_version,
        created_at=NOW,
    )
    db.add(unit)
    db.flush()
    db.add(
        ContentUnitEmbedding(
            id=_id(f"{name}-embedding"),
            workspace_id=asset.workspace_id,
            asset_id=asset.id,
            content_unit_id=unit.id,
            processing_generation=representation.processing_generation,
            index_version=index_version,
            is_current=(
                representation.processing_generation == asset.current_processing_generation
                and index_version == asset.current_index_version
            ),
            embedding_space="text",
            provider="ollama",
            model="qwen3-embedding:0.6b",
            dimensions=1024,
            version="embedding-v1",
            embedding=[vector_head, 1.0 - vector_head, *([0.0] * 1022)],
            created_at=NOW,
        )
    )


def _seed_assets(db: Session) -> dict[str, Any]:
    pdf_payload = _pdf_bytes()
    image_g1 = _png_bytes(1)
    image_g2 = _png_bytes(2)
    pdf = _add_asset(
        db,
        name="pdf",
        kind="pdf",
        title="m403-history.pdf",
        payload=pdf_payload,
        mime_type="application/pdf",
        status="ready",
        generation=2,
        index_version=2,
    )
    image = _add_asset(
        db,
        name="image",
        kind="image",
        title="m403-history.png",
        payload=image_g1,
        mime_type="image/png",
        status="ready",
        generation=2,
        index_version=2,
    )
    deleted_pdf = _add_asset(
        db,
        name="deleted-pdf",
        kind="pdf",
        title="m403-deleted.pdf",
        payload=pdf_payload,
        mime_type="application/pdf",
        status="ready",
        generation=1,
        index_version=1,
        deleted=True,
    )
    deleted_image = _add_asset(
        db,
        name="deleted-image",
        kind="image",
        title="m403-deleted.png",
        payload=image_g1,
        mime_type="image/png",
        status="ready",
        generation=1,
        index_version=1,
        deleted=True,
    )
    failed_image = _add_asset(
        db,
        name="failed-image",
        kind="image",
        title="m403-failed.png",
        payload=image_g1,
        mime_type="image/png",
        status="failed",
        generation=2,
        index_version=1,
    )

    pdf_reps: dict[int, AssetRepresentation] = {}
    pdf_pages: dict[int, PdfPage] = {}
    pdf_locators: dict[int, EvidenceLocator] = {}
    for generation in (1, 2):
        manifest = _json_bytes({"generation": generation, "kind": "pdf_page_layout", "page": 1})
        rep = _add_representation(
            db,
            asset=pdf,
            name=f"pdf-layout-g{generation}",
            kind="pdf_page_layout",
            generation=generation,
            payload=manifest,
            content_type="application/json",
        )
        page = PdfPage(
            id=_id(f"pdf-page-g{generation}"),
            workspace_id=pdf.workspace_id,
            asset_id=pdf.id,
            representation_id=rep.id,
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
            extracted_text=f"M403 PDF generation {generation}",
            char_count=24,
            legacy_ocr_blocks=[],
            created_at=NOW + timedelta(minutes=generation),
        )
        db.add(page)
        db.flush()
        locator = _add_pdf_locator(
            db,
            name=f"pdf-source-g{generation}",
            asset=pdf,
            representation=rep,
            page=page,
            kind="pdf_region" if generation == 1 else "pdf_page",
            region=(0.12, 0.18, 0.5, 0.3) if generation == 1 else None,
        )
        _add_content(
            db,
            name=f"pdf-g{generation}",
            asset=pdf,
            representation=rep,
            locator=locator,
            kind="pdf_text_chunk",
            text_content=f"M403 PDF generation {generation} evidence",
            index_version=generation,
            vector_head=0.9,
        )
        pdf_reps[generation] = rep
        pdf_pages[generation] = page
        pdf_locators[generation] = locator

    image_reps: dict[int, AssetRepresentation] = {}
    image_locators: dict[int, EvidenceLocator] = {}
    for generation, payload in ((1, image_g1), (2, image_g2)):
        oriented = _add_representation(
            db,
            asset=image,
            name=f"image-oriented-g{generation}",
            kind="image_oriented",
            generation=generation,
            payload=payload,
            content_type="image/png",
        )
        db.add(
            ImageRepresentationGeometry(
                representation_id=oriented.id,
                workspace_id=image.workspace_id,
                asset_id=image.id,
                width_pixels=640,
                height_pixels=480,
                orientation_applied=True,
            )
        )
        ocr_payload = _json_bytes({"generation": generation, "text": "Historical image region"})
        ocr = _add_representation(
            db,
            asset=image,
            name=f"image-ocr-g{generation}",
            kind="image_ocr",
            generation=generation,
            payload=ocr_payload,
            content_type="application/json",
        )
        locator = _add_image_locator(
            db,
            name=f"image-source-g{generation}",
            asset=image,
            representation=ocr,
            region=(0.15, 0.2, 0.5, 0.45),
        )
        _add_content(
            db,
            name=f"image-g{generation}",
            asset=image,
            representation=ocr,
            locator=locator,
            kind="image_ocr_region",
            text_content=f"M403 Image generation {generation} evidence",
            index_version=generation,
            vector_head=0.8,
        )
        image_reps[generation] = ocr
        image_locators[generation] = locator

    deleted_pdf_rep = _add_representation(
        db,
        asset=deleted_pdf,
        name="deleted-pdf-rep",
        kind="pdf_page_layout",
        generation=1,
        payload=_json_bytes({"deleted": True, "kind": "pdf"}),
        content_type="application/json",
        deleted=True,
    )
    deleted_image_rep = _add_representation(
        db,
        asset=deleted_image,
        name="deleted-image-rep",
        kind="image_oriented",
        generation=1,
        payload=image_g1,
        content_type="image/png",
        deleted=True,
    )
    db.add(
        ImageRepresentationGeometry(
            representation_id=deleted_image_rep.id,
            workspace_id=deleted_image.workspace_id,
            asset_id=deleted_image.id,
            width_pixels=640,
            height_pixels=480,
            orientation_applied=True,
        )
    )
    del deleted_pdf_rep
    return {
        "pdf": pdf,
        "image": image,
        "deleted_pdf": deleted_pdf,
        "deleted_image": deleted_image,
        "failed_image": failed_image,
        "pdf_reps": pdf_reps,
        "pdf_locators": pdf_locators,
        "image_reps": image_reps,
        "image_locators": image_locators,
    }


def _citation(
    db: Session,
    *,
    index: int,
    label: str,
    message: ChatMessage,
    asset: Asset,
    representation: AssetRepresentation,
    source: EvidenceLocator,
) -> MessageCitation:
    locator = _clone_locator(db, source, f"citation-{label}-locator")
    citation = MessageCitation(
        id=_id(f"citation-{label}"),
        workspace_id=asset.workspace_id,
        message_id=message.id,
        citation_index=index,
        evidence_locator_id=locator.id,
        asset_id=asset.id,
        asset_kind_snapshot=asset.asset_kind,
        asset_title_snapshot=asset.title,
        excerpt_snapshot=f"M403 {label} excerpt",
        processing_generation_snapshot=representation.processing_generation,
        representation_id_snapshot=representation.id,
        parser_version_snapshot=representation.generator_version,
        index_version_snapshot=representation.processing_generation,
        created_at=NOW + timedelta(hours=1),
    )
    db.add(citation)
    db.flush()
    return citation


def _seed_conversation(db: Session, seeded: dict[str, Any]) -> dict[str, Any]:
    pdf: Asset = seeded["pdf"]
    image: Asset = seeded["image"]
    thread = ChatThread(
        id=IDS["thread"],
        workspace_id=IDS["workspace"],
        created_by_user_id=IDS["user"],
        title="M403 restore semantics",
        last_message_at=NOW + timedelta(hours=1),
        created_at=NOW,
        updated_at=NOW + timedelta(hours=1),
    )
    all_user = ChatMessage(
        id=IDS["all-user"],
        workspace_id=IDS["workspace"],
        thread_id=thread.id,
        role="user",
        content="Compare all ready assets.",
        status="completed",
        created_at=NOW + timedelta(minutes=10),
    )
    all_assistant = ChatMessage(
        id=IDS["all-assistant"],
        workspace_id=IDS["workspace"],
        thread_id=thread.id,
        parent_message_id=all_user.id,
        role="assistant",
        content="All-ready scope was frozen before restore.",
        status="completed",
        model_provider="m403",
        model_name="deterministic",
        created_at=NOW + timedelta(minutes=11),
    )
    selected_user = ChatMessage(
        id=IDS["selected-user"],
        workspace_id=IDS["workspace"],
        thread_id=thread.id,
        parent_message_id=all_assistant.id,
        role="user",
        content="Open current and historical evidence.",
        status="completed",
        created_at=NOW + timedelta(minutes=20),
    )
    selected_assistant = ChatMessage(
        id=IDS["selected-assistant"],
        workspace_id=IDS["workspace"],
        thread_id=thread.id,
        parent_message_id=selected_user.id,
        role="assistant",
        content="[1] PDF history [2] PDF current [3] Image history [4] Image current",
        status="completed",
        model_provider="m403",
        model_name="deterministic",
        created_at=NOW + timedelta(minutes=21),
    )
    failed_user = ChatMessage(
        id=IDS["failed-user"],
        workspace_id=IDS["workspace"],
        thread_id=thread.id,
        parent_message_id=selected_assistant.id,
        role="user",
        content="Preserve a failed branch.",
        status="completed",
        created_at=NOW + timedelta(minutes=30),
    )
    failed_assistant = ChatMessage(
        id=IDS["failed-assistant"],
        workspace_id=IDS["workspace"],
        thread_id=thread.id,
        parent_message_id=failed_user.id,
        role="assistant",
        content="Deterministic generation failure.",
        status="failed",
        model_provider="m403",
        model_name="deterministic",
        created_at=NOW + timedelta(minutes=31),
    )
    db.add(thread)
    db.flush()
    for message in (all_user, all_assistant, selected_user, selected_assistant, failed_user, failed_assistant):
        db.add(message)
        db.flush()
    thread.active_message_id = selected_assistant.id
    db.add_all(
        [
            MessageRetrievalScope(
                message_id=all_user.id,
                workspace_id=IDS["workspace"],
                scope_mode="all_ready",
                created_at=all_user.created_at,
            ),
            MessageRetrievalScope(
                message_id=selected_user.id,
                workspace_id=IDS["workspace"],
                scope_mode="selected",
                created_at=selected_user.created_at,
            ),
            MessageRetrievalScope(
                message_id=failed_user.id,
                workspace_id=IDS["workspace"],
                scope_mode="all_ready",
                created_at=failed_user.created_at,
            ),
            MessageRetrievalScopeAsset(
                message_id=selected_user.id,
                asset_id=image.id,
                asset_order=0,
                asset_kind_snapshot=image.asset_kind,
                asset_title_snapshot=image.title,
            ),
            MessageRetrievalScopeAsset(
                message_id=selected_user.id,
                asset_id=pdf.id,
                asset_order=1,
                asset_kind_snapshot=pdf.asset_kind,
                asset_title_snapshot=pdf.title,
            ),
        ]
    )
    input_locator = _clone_locator(db, seeded["image_locators"][1], "input-image-history-locator")
    input_evidence = MessageInputEvidence(
        id=_id("input-image-history"),
        workspace_id=IDS["workspace"],
        message_id=selected_user.id,
        target_order=0,
        evidence_locator_id=input_locator.id,
        asset_id=image.id,
        asset_kind_snapshot=image.asset_kind,
        asset_title_snapshot=image.title,
        excerpt_snapshot="M403 direct image selection",
        processing_generation_snapshot=1,
        representation_id_snapshot=seeded["image_reps"][1].id,
        parser_version_snapshot="m403-v1",
        index_version_snapshot=1,
        created_at=selected_user.created_at,
    )
    db.add(input_evidence)
    citations = [
        _citation(
            db,
            index=0,
            label="pdf-history",
            message=selected_assistant,
            asset=pdf,
            representation=seeded["pdf_reps"][1],
            source=seeded["pdf_locators"][1],
        ),
        _citation(
            db,
            index=1,
            label="pdf-current",
            message=selected_assistant,
            asset=pdf,
            representation=seeded["pdf_reps"][2],
            source=seeded["pdf_locators"][2],
        ),
        _citation(
            db,
            index=2,
            label="image-history",
            message=selected_assistant,
            asset=image,
            representation=seeded["image_reps"][1],
            source=seeded["image_locators"][1],
        ),
        _citation(
            db,
            index=3,
            label="image-current",
            message=selected_assistant,
            asset=image,
            representation=seeded["image_reps"][2],
            source=seeded["image_locators"][2],
        ),
    ]
    note = Note(
        id=IDS["note"],
        workspace_id=IDS["workspace"],
        created_by_user_id=IDS["user"],
        updated_by_user_id=IDS["user"],
        title="M403 frozen note",
        body_md="Historical PDF and Image evidence must survive restore.",
        is_pinned=True,
        created_at=NOW + timedelta(hours=1),
        updated_at=NOW + timedelta(hours=1),
    )
    db.add(note)
    db.flush()
    note_sources: list[NoteSource] = []
    for order, citation in enumerate((citations[0], citations[2])):
        source_locator = _clone_locator(db, db.get(EvidenceLocator, citation.evidence_locator_id), f"note-citation-{order}-locator")
        note_sources.append(
            NoteSource(
                id=_id(f"note-citation-{order}"),
                workspace_id=IDS["workspace"],
                note_id=note.id,
                source_order=order,
                message_citation_id=citation.id,
                evidence_locator_id=source_locator.id,
                asset_id=citation.asset_id,
                asset_kind_snapshot=citation.asset_kind_snapshot,
                asset_title_snapshot=citation.asset_title_snapshot,
                excerpt_snapshot=citation.excerpt_snapshot,
                processing_generation_snapshot=citation.processing_generation_snapshot,
                representation_id_snapshot=citation.representation_id_snapshot,
                parser_version_snapshot=citation.parser_version_snapshot,
                index_version_snapshot=citation.index_version_snapshot,
                created_at=NOW + timedelta(hours=1),
            )
        )
    direct_locator = _clone_locator(db, seeded["image_locators"][1], "note-direct-image-locator")
    note_sources.append(
        NoteSource(
            id=_id("note-direct-image"),
            workspace_id=IDS["workspace"],
            note_id=note.id,
            source_order=2,
            message_citation_id=None,
            evidence_locator_id=direct_locator.id,
            asset_id=image.id,
            asset_kind_snapshot=image.asset_kind,
            asset_title_snapshot=image.title,
            excerpt_snapshot="M403 direct historical image note",
            processing_generation_snapshot=1,
            representation_id_snapshot=seeded["image_reps"][1].id,
            parser_version_snapshot="m403-v1",
            index_version_snapshot=1,
            created_at=NOW + timedelta(hours=1),
        )
    )
    db.add_all(note_sources)
    return {
        "thread": thread,
        "citations": citations,
        "input": input_evidence,
        "note": note,
        "note_sources": note_sources,
    }


def seed() -> dict[str, Any]:
    engine = create_engine(settings.database_url, future=True)
    with Session(engine) as db:
        if db.get(Workspace, IDS["workspace"]):
            raise RuntimeError("M403 workspace already exists; seed requires an empty acceptance database")
        user = User(
            id=IDS["user"],
            email="m403-restore@example.com",
            name="M403 Restore Acceptance",
            password_hash=hash_password(PASSWORD),
            avatar_url="https://example.com/m403.svg",
            created_at=NOW,
            updated_at=NOW,
        )
        workspace = Workspace(
            id=IDS["workspace"],
            name="M403 Restore Acceptance",
            description="Isolated backup and restore semantic oracle",
            system_prompt="Answer only from frozen evidence.",
            retrieval_top_k=10,
            chunk_size=1200,
            created_by_user_id=user.id,
            created_at=NOW,
            updated_at=NOW,
        )
        db.add_all([user, workspace])
        db.flush()
        db.add(
            WorkspaceMembership(
                id=IDS["membership"],
                workspace_id=workspace.id,
                user_id=user.id,
                role="owner",
                created_at=NOW,
            )
        )
        seeded = _seed_assets(db)
        _seed_conversation(db, seeded)
        failed: Asset = seeded["failed_image"]
        job = IngestionJob(
            id=IDS["failed-job"],
            workspace_id=workspace.id,
            asset_id=failed.id,
            job_type="ingest",
            status="failed",
            attempt_count=2,
            config_snapshot={"fixture": "m403", "generation": 2},
            error_code="fixture_failure",
            error_message="Deterministic failed ingestion branch",
            requested_by_user_id=user.id,
            queued_at=NOW,
            started_at=NOW + timedelta(minutes=1),
            finished_at=NOW + timedelta(minutes=2),
            created_at=NOW,
        )
        db.add(job)
        failed.latest_ingestion_job_id = job.id
        db.commit()
    engine.dispose()
    return {
        "schemaVersion": "m403-state-v1",
        "email": "m403-restore@example.com",
        "password": PASSWORD,
        "userId": IDS["user"],
        "workspaceId": IDS["workspace"],
        "threadId": IDS["thread"],
        "citationIds": {
            "pdfHistorical": _id("citation-pdf-history"),
            "pdfCurrent": _id("citation-pdf-current"),
            "imageHistorical": _id("citation-image-history"),
            "imageCurrent": _id("citation-image-current"),
        },
    }


def _query_json_rows(db: Session, query: str, **parameters: Any) -> list[dict[str, Any]]:
    return [
        json.loads(payload)
        for payload in db.scalars(text(f"SELECT to_jsonb(row_data)::text FROM ({query}) row_data"), parameters)
    ]


def _table_rows(db: Session) -> dict[str, list[dict[str, Any]]]:
    workspace_id = IDS["workspace"]
    result: dict[str, list[dict[str, Any]]] = {}
    inspector = inspect(db.bind)
    excluded = {
        "alembic_version",
        "asset_types",
        "content_unit_types",
        "embedding_spaces",
        "locator_types",
        "representation_types",
    }
    for table_name in sorted(inspector.get_table_names()):
        if table_name in excluded:
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "workspace_id" in columns:
            query = f'SELECT * FROM "{table_name}" WHERE workspace_id = :workspace_id ORDER BY to_jsonb("{table_name}")::text'
            result[table_name] = _query_json_rows(db, query, workspace_id=workspace_id)
    result["users"] = _query_json_rows(db, "SELECT * FROM users WHERE id = :id", id=IDS["user"])
    result["workspaces"] = _query_json_rows(db, "SELECT * FROM workspaces WHERE id = :id", id=workspace_id)
    result["message_retrieval_scope_assets"] = _query_json_rows(
        db,
        """
        SELECT a.* FROM message_retrieval_scope_assets a
        JOIN message_retrieval_scopes s ON s.message_id = a.message_id
        WHERE s.workspace_id = :workspace_id
        ORDER BY a.message_id, a.asset_order
        """,
        workspace_id=workspace_id,
    )
    for table_name in ("pdf_locator_details", "image_locator_details", "spatial_locator_regions"):
        join_column = "locator_id"
        result[table_name] = _query_json_rows(
            db,
            f"""
            SELECT d.* FROM {table_name} d
            JOIN evidence_locators l ON l.id = d.{join_column}
            WHERE l.workspace_id = :workspace_id
            ORDER BY to_jsonb(d)::text
            """,
            workspace_id=workspace_id,
        )
    result["catalog"] = _query_json_rows(
        db,
        "SELECT kind, contract_version, enabled FROM asset_types ORDER BY kind",
    )
    result["alembic_version"] = _query_json_rows(db, "SELECT version_num FROM alembic_version")
    return dict(sorted(result.items()))


def _object_manifest(db: Session) -> list[dict[str, Any]]:
    assets = db.scalars(select(Asset).where(Asset.workspace_id == IDS["workspace"]).order_by(Asset.id)).all()
    representations = db.scalars(
        select(AssetRepresentation)
        .where(AssetRepresentation.workspace_id == IDS["workspace"])
        .order_by(AssetRepresentation.id)
    ).all()
    asset_by_id = {asset.id: asset for asset in assets}
    entries: list[dict[str, Any]] = []
    for asset in assets:
        exists = asset.deleted_at is None
        if not exists and object_exists(asset.object_key):
            raise RuntimeError(f"Deleted asset object still exists: {asset.id}")
        actual = download_bytes(asset.object_key) if exists else None
        if actual is not None and (sha256(actual).hexdigest() != asset.source_sha256 or len(actual) != asset.byte_size):
            raise RuntimeError(f"Asset object mismatch: {asset.id}")
        entries.append(
            {
                "ownerType": "asset",
                "ownerId": asset.id,
                "assetId": asset.id,
                "objectKey": asset.object_key,
                "expectedExists": exists,
                "exists": actual is not None,
                "byteSize": len(actual) if actual is not None else None,
                "sha256": sha256(actual).hexdigest() if actual is not None else None,
            }
        )
    for representation in representations:
        if representation.object_key is None:
            continue
        exists = asset_by_id[representation.asset_id].deleted_at is None
        if not exists and object_exists(representation.object_key):
            raise RuntimeError(f"Deleted representation object still exists: {representation.id}")
        actual = download_bytes(representation.object_key) if exists else None
        if actual is not None and sha256(actual).hexdigest() != representation.content_sha256:
            raise RuntimeError(f"Representation object mismatch: {representation.id}")
        entries.append(
            {
                "ownerType": "representation",
                "ownerId": representation.id,
                "assetId": representation.asset_id,
                "generation": representation.processing_generation,
                "kind": representation.representation_kind,
                "objectKey": representation.object_key,
                "expectedExists": exists,
                "exists": actual is not None,
                "byteSize": len(actual) if actual is not None else None,
                "sha256": sha256(actual).hexdigest() if actual is not None else None,
            }
        )
    client = build_storage_client()
    bucket_objects = sorted(
        item.object_name
        for item in client.list_objects(
            settings.minio_bucket,
            prefix=f"workspaces/{IDS['workspace']}/",
            recursive=True,
        )
        if item.object_name
    )
    expected_objects = sorted(entry["objectKey"] for entry in entries if entry["expectedExists"])
    if bucket_objects != expected_objects:
        raise RuntimeError("M403 workspace object set is not closed")
    return sorted(entries, key=lambda item: (item["objectKey"], item["ownerType"], item["ownerId"]))


def _visual_replay(db: Session) -> dict[str, Any]:
    pdf_payload = download_bytes(db.get(Asset, IDS["pdf"]).object_key)
    document = fitz.open(stream=pdf_payload, filetype="pdf")
    pixmap = document[0].get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
    pdf_pixels = sha256(pixmap.samples).hexdigest()
    pdf_size = [pixmap.width, pixmap.height]
    document.close()
    image_rows = db.execute(
        select(AssetRepresentation, ImageRepresentationGeometry)
        .join(ImageRepresentationGeometry, ImageRepresentationGeometry.representation_id == AssetRepresentation.id)
        .where(
            AssetRepresentation.asset_id == IDS["image"],
            AssetRepresentation.representation_kind == "image_oriented",
        )
        .order_by(AssetRepresentation.processing_generation)
    ).all()
    images = []
    for representation, geometry in image_rows:
        payload = download_bytes(representation.object_key)
        with Image.open(BytesIO(payload)) as image:
            pixels = image.convert("RGBA").tobytes()
            images.append(
                {
                    "generation": representation.processing_generation,
                    "size": [image.width, image.height],
                    "geometry": [geometry.width_pixels, geometry.height_pixels, geometry.orientation_applied],
                    "pixelSha256": sha256(pixels).hexdigest(),
                }
            )
    return {"pdf": {"page": 1, "size": pdf_size, "pixelSha256": pdf_pixels}, "images": images}


def _semantic_checks(rows: dict[str, list[dict[str, Any]]], objects: list[dict[str, Any]]) -> dict[str, Any]:
    assets = {item["id"]: item for item in rows["assets"]}
    citations = sorted(rows["message_citations"], key=lambda item: item["citation_index"])
    note_sources = sorted(rows["note_sources"], key=lambda item: item["source_order"])
    inputs = rows["message_input_evidence"]
    selected = rows["message_retrieval_scope_assets"]
    image_catalog = next(item for item in rows["catalog"] if item["kind"] == "image")
    expect_image_enabled = _expect_image_enabled()
    image_catalog_check = "imageProductionEnabled" if expect_image_enabled else "imageProductionDisabled"
    checks = {
        image_catalog_check: image_catalog["enabled"] is expect_image_enabled,
        "activeAssetKinds": sorted(
            item["asset_kind"] for item in assets.values() if item["status"] == "ready" and item["deleted_at"] is None
        ) == ["image", "pdf"],
        "deletedModalitiesCovered": sorted(
            item["asset_kind"] for item in assets.values() if item["deleted_at"] is not None
        ) == ["image", "pdf"],
        "failedBranchCovered": any(item["status"] == "failed" for item in assets.values()),
        "historicalAndCurrentCitations": [item["processing_generation_snapshot"] for item in citations] == [1, 2, 1, 2],
        "imageInputEvidenceHistorical": len(inputs) == 1 and inputs[0]["asset_kind_snapshot"] == "image" and inputs[0]["processing_generation_snapshot"] == 1,
        "noteSourceKinds": [item["message_citation_id"] is None for item in note_sources] == [False, False, True],
        "selectedScopeOrder": [item["asset_id"] for item in selected] == [IDS["image"], IDS["pdf"]],
        "activeObjectsPresent": all(item["exists"] for item in objects if item["expectedExists"]),
        "deletedObjectsAbsent": all(not item["exists"] for item in objects if not item["expectedExists"]),
    }
    if not all(checks.values()):
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise RuntimeError(f"M403 semantic checks failed: {', '.join(failed)}")
    return checks


def snapshot() -> dict[str, Any]:
    engine = create_engine(settings.database_url, future=True)
    with Session(engine) as db:
        rows = _table_rows(db)
        objects = _object_manifest(db)
        checks = _semantic_checks(rows, objects)
        visual = _visual_replay(db)
    engine.dispose()
    semantic_payload = {"rows": rows, "objects": objects, "visualReplay": visual}
    return {
        "schemaVersion": SCHEMA_VERSION,
        "workspaceId": IDS["workspace"],
        "semanticSha256": sha256(_json_bytes(semantic_payload)).hexdigest(),
        "tableCounts": {name: len(items) for name, items in rows.items()},
        "objectCount": sum(1 for item in objects if item["exists"]),
        "checks": checks,
        **semantic_payload,
    }


def verify(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    if before.get("schemaVersion") != SCHEMA_VERSION or after.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("M403 snapshot schema mismatch")
    compared_fields = ("workspaceId", "semanticSha256", "tableCounts", "objectCount", "checks", "rows", "objects", "visualReplay")
    mismatches = [field for field in compared_fields if before.get(field) != after.get(field)]
    result = {
        "schemaVersion": "m403-restore-verification-v1",
        "beforeSemanticSha256": before["semanticSha256"],
        "afterSemanticSha256": after["semanticSha256"],
        "comparedFields": list(compared_fields),
        "mismatches": mismatches,
        "passed": not mismatches,
    }
    if mismatches:
        raise RuntimeError(f"M403 restore mismatch: {', '.join(mismatches)}")
    return result


def _write_or_print(payload: dict[str, Any], output: Path | None) -> None:
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output is None:
        print(encoded, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(output)


def main() -> None:
    args = parse_args()
    if args.command == "seed":
        _write_or_print(seed(), args.state)
    elif args.command == "snapshot":
        _write_or_print(snapshot(), args.output)
    else:
        before = json.loads(args.before.read_text(encoding="utf-8"))
        after = json.loads(args.after.read_text(encoding="utf-8"))
        _write_or_print(verify(before, after), args.output)


if __name__ == "__main__":
    main()
