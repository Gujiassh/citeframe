from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from ai_pdf_api.core.settings import settings
from ai_pdf_api.db.base import Base
from ai_pdf_api.modalities.evidence import EvidenceContractError
from ai_pdf_api.modalities.image_ingestion import (
    ImageAnalysisResult,
    ImageNormalizationResult,
    ImageOcrRegionResult,
    build_image_oriented_object_key,
    persist_image_analysis,
    persist_image_orientation,
)
from ai_pdf_api.modalities.pdf_ingestion import (
    PageArtifactResult,
    PageRegionResult,
    PageTextResult,
    PdfPageGeometryResult,
    SpatialRegionResult,
    replace_pdf_content,
)
from ai_pdf_api.modalities.registry import build_production_registry
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ChatThread,
    ContentUnit,
    ContentUnitEmbedding,
    EvidenceLocator,
    ImageLocatorDetail,
    MessageRetrievalScope,
    MessageRetrievalScopeAsset,
    PdfLocatorDetail,
    PdfPage,
    SpatialLocatorRegion,
    User,
    Workspace,
    WorkspaceMembership,
)
from ai_pdf_api.schemas.chat import AllReadyAssetScope, SelectedAssetScope
from ai_pdf_api.services.chat import complete_chat
from ai_pdf_api.services.retrieval import (
    retrieve_content,
    retrieve_lexical_content,
    retrieve_query_content,
)
from ai_pdf_api.services.retrieval_experiments import LexicalCorpus
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, delete, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker


class MixedEmbeddingProvider:
    provider = "mixed-test"
    model = "mixed-embedding"
    dimensions = 1024
    version = "mixed-v1"

    def embed_query(self, _text: str) -> list[float]:
        return [1.0, *([0.0] * 1023)]


class MixedGenerationProvider:
    provider = "mixed-test"
    model = "mixed-generation"

    def generate(self, _messages) -> str:
        return "PDF evidence [1] and image evidence [2] support the answer."


def _build_mixed_session() -> tuple[Session, User, Workspace, Asset, Asset]:
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, future=True)()
    user, workspace, pdf, image = _populate_mixed_session(db)
    return db, user, workspace, pdf, image


def _populate_mixed_session(
    db: Session,
) -> tuple[User, Workspace, Asset, Asset]:
    now = datetime.now(UTC)
    user = User(
        id="00000000-0000-0000-0000-000000000001",
        email="mixed@example.com",
        name="Mixed retrieval",
        password_hash="hash",
        avatar_url="https://example.com/avatar.svg",
    )
    workspace = Workspace(
        id="00000000-0000-0000-0000-000000000010",
        name="Mixed workspace",
        created_by_user_id=user.id,
        retrieval_top_k=6,
        created_at=now,
        updated_at=now,
    )
    pdf = Asset(
        id="00000000-0000-0000-0000-000000000100",
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        asset_kind="pdf",
        title="Latency report",
        source_filename="latency.pdf",
        object_key="latency.pdf",
        mime_type="application/pdf",
        byte_size=1,
        status="ready",
        current_processing_generation=1,
        current_index_version=1,
        created_at=now,
        updated_at=now,
    )
    image = Asset(
        id="00000000-0000-0000-0000-000000000200",
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        asset_kind="image",
        title="Latency chart",
        source_filename="latency.png",
        object_key="latency.png",
        mime_type="image/png",
        byte_size=1,
        status="ready",
        current_processing_generation=1,
        current_index_version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    db.add(workspace)
    db.flush()
    db.add_all([pdf, image])
    db.flush()
    db.add(WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role="owner"))
    _add_pdf_candidate(db, workspace, pdf, now)
    _add_image_candidate(
        db,
        workspace,
        image,
        now,
        representation_kind="image_ocr",
        unit_kind="image_ocr_region",
        unit_id="00000000-0000-0000-0000-000000001002",
        text="Latency drops to 42 ms in the chart.",
        region_x=0.1,
    )
    _add_image_candidate(
        db,
        workspace,
        image,
        now,
        representation_kind="image_caption",
        unit_kind="image_caption",
        unit_id="00000000-0000-0000-0000-000000001003",
        text="Latency chart showing a sustained 42 ms result.",
        region_x=0.4,
    )
    _add_invalid_candidates(db, workspace, pdf, image, now)
    db.commit()
    return user, workspace, pdf, image


def _add_pdf_candidate(db: Session, workspace: Workspace, asset: Asset, now: datetime) -> None:
    representation = AssetRepresentation(
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_kind="pdf_page_layout",
        processing_generation=1,
        generator_version="pdf-layout-v1",
        created_at=now,
    )
    db.add(representation)
    db.flush()
    page = PdfPage(
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_id=representation.id,
        page_number=4,
        extracted_text="Latency reaches 42 ms in the report.",
        char_count=36,
        created_at=now,
    )
    locator = EvidenceLocator(
        workspace_id=workspace.id,
        asset_id=asset.id,
        locator_kind="pdf_page",
        locator_version=1,
        processing_generation_snapshot=1,
        representation_id_snapshot=representation.id,
        created_at=now,
    )
    db.add_all([page, locator])
    db.flush()
    db.add(PdfLocatorDetail(locator_id=locator.id, page_id=page.id, page_number=4))
    _add_unit(
        db,
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_id=representation.id,
        locator_id=locator.id,
        unit_kind="pdf_text_chunk",
        unit_id="00000000-0000-0000-0000-000000001001",
        text="Latency reaches 42 ms in the report.",
        index_version=1,
        embedding_workspace_id=workspace.id,
        now=now,
    )


def _add_duplicate_pdf_page_candidates(
    db: Session,
    workspace: Workspace,
    asset: Asset,
    now: datetime,
    *,
    count: int,
) -> None:
    representation = db.scalar(
        select(AssetRepresentation).where(
            AssetRepresentation.asset_id == asset.id,
            AssetRepresentation.representation_kind == "pdf_page_layout",
            AssetRepresentation.processing_generation == 1,
        )
    )
    assert representation is not None
    page = db.scalar(
        select(PdfPage).where(PdfPage.asset_id == asset.id, PdfPage.page_number == 4)
    )
    assert page is not None
    for index in range(count):
        locator = EvidenceLocator(
            workspace_id=workspace.id,
            asset_id=asset.id,
            locator_kind="pdf_page",
            locator_version=1,
            processing_generation_snapshot=1,
            representation_id_snapshot=representation.id,
            created_at=now,
        )
        db.add(locator)
        db.flush()
        db.add(PdfLocatorDetail(locator_id=locator.id, page_id=page.id, page_number=4))
        _add_unit(
            db,
            workspace_id=workspace.id,
            asset_id=asset.id,
            representation_id=representation.id,
            locator_id=locator.id,
            unit_kind="pdf_text_chunk",
            unit_id=f"00000000-0000-0000-0000-{1100 + index:012d}",
            text="Latency reaches 42 ms in another chunk on the same page.",
            index_version=1,
            embedding_workspace_id=workspace.id,
            now=now,
        )


def _add_image_candidate(
    db: Session,
    workspace: Workspace,
    asset: Asset,
    now: datetime,
    *,
    representation_kind: str,
    unit_kind: str,
    unit_id: str,
    text: str,
    region_x: float,
) -> None:
    representation = AssetRepresentation(
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_kind=representation_kind,
        processing_generation=1,
        generator_version=f"{representation_kind}-v1",
        created_at=now,
    )
    db.add(representation)
    db.flush()
    locator = _image_locator(
        db,
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_id=representation.id,
        generation=1,
        region_x=region_x,
        now=now,
    )
    _add_unit(
        db,
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_id=representation.id,
        locator_id=locator.id,
        unit_kind=unit_kind,
        unit_id=unit_id,
        text=text,
        index_version=1,
        embedding_workspace_id=workspace.id,
        now=now,
    )


def _add_invalid_candidates(
    db: Session,
    workspace: Workspace,
    pdf: Asset,
    image: Asset,
    now: datetime,
) -> None:
    foreign_workspace = Workspace(
        id=str(uuid4()),
        name="Foreign embedding workspace",
        created_by_user_id=workspace.created_by_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(foreign_workspace)
    db.flush()
    old_representation = AssetRepresentation(
        workspace_id=workspace.id,
        asset_id=image.id,
        representation_kind="image_caption",
        processing_generation=2,
        generator_version="old-generation",
        created_at=now,
    )
    db.add(old_representation)
    db.flush()
    old_locator = _image_locator(
        db,
        workspace_id=workspace.id,
        asset_id=image.id,
        representation_id=old_representation.id,
        generation=2,
        region_x=0.7,
        now=now,
    )
    _add_unit(
        db,
        workspace_id=workspace.id,
        asset_id=image.id,
        representation_id=old_representation.id,
        locator_id=old_locator.id,
        unit_kind="image_caption",
        unit_id="00000000-0000-0000-0000-000000009001",
        text="Latency old generation must not appear.",
        index_version=1,
        embedding_workspace_id=workspace.id,
        now=now,
    )

    current_representation = db.scalar(
        select(AssetRepresentation).where(
            AssetRepresentation.asset_id == image.id,
            AssetRepresentation.representation_kind == "image_caption",
            AssetRepresentation.processing_generation == 1,
        )
    )
    assert current_representation is not None
    stale_locator = _image_locator(
        db,
        workspace_id=workspace.id,
        asset_id=image.id,
        representation_id=current_representation.id,
        generation=1,
        region_x=0.75,
        now=now,
    )
    _add_unit(
        db,
        workspace_id=workspace.id,
        asset_id=image.id,
        representation_id=current_representation.id,
        locator_id=stale_locator.id,
        unit_kind="image_caption",
        unit_id="00000000-0000-0000-0000-000000009002",
        text="Latency stale index must not appear.",
        index_version=0,
        embedding_workspace_id=workspace.id,
        now=now,
    )

    cross_asset_locator = _image_locator(
        db,
        workspace_id=workspace.id,
        asset_id=pdf.id,
        representation_id=current_representation.id,
        generation=1,
        region_x=0.8,
        now=now,
    )
    _add_unit(
        db,
        workspace_id=workspace.id,
        asset_id=image.id,
        representation_id=current_representation.id,
        locator_id=cross_asset_locator.id,
        unit_kind="image_caption",
        unit_id="00000000-0000-0000-0000-000000009003",
        text="Latency cross asset must not appear.",
        index_version=1,
        embedding_workspace_id=workspace.id,
        now=now,
    )

    wrong_modality_locator = _image_locator(
        db,
        workspace_id=workspace.id,
        asset_id=image.id,
        representation_id=current_representation.id,
        generation=1,
        region_x=0.85,
        now=now,
    )

    pdf_representation = db.scalar(
        select(AssetRepresentation).where(
            AssetRepresentation.asset_id == pdf.id,
            AssetRepresentation.representation_kind == "pdf_page_layout",
        )
    )
    assert pdf_representation is not None
    wrong_pdf_signature_locator = EvidenceLocator(
        workspace_id=workspace.id,
        asset_id=pdf.id,
        locator_kind="pdf_region",
        locator_version=1,
        processing_generation_snapshot=1,
        representation_id_snapshot=pdf_representation.id,
        created_at=now,
    )
    db.add(wrong_pdf_signature_locator)
    db.flush()
    db.add(
        PdfLocatorDetail(
            locator_id=wrong_pdf_signature_locator.id,
            page_number=4,
            coordinate_space="pdf_crop_box_normalized_top_left_v1",
            crop_x0_points=0,
            crop_y0_points=0,
            crop_x1_points=612,
            crop_y1_points=792,
            rotation_degrees=0,
            display_width_points=612,
            display_height_points=792,
        )
    )
    db.add(
        SpatialLocatorRegion(
            locator_id=wrong_pdf_signature_locator.id,
            region_order=0,
            x=0.1,
            y=0.1,
            width=0.1,
            height=0.1,
        )
    )
    _add_unit(
        db,
        workspace_id=workspace.id,
        asset_id=pdf.id,
        representation_id=pdf_representation.id,
        locator_id=wrong_pdf_signature_locator.id,
        unit_kind="pdf_figure",
        unit_id="00000000-0000-0000-0000-000000009006",
        text="Latency valid kinds in an invalid PDF signature must not appear.",
        index_version=1,
        embedding_workspace_id=workspace.id,
        now=now,
    )
    _add_unit(
        db,
        workspace_id=workspace.id,
        asset_id=image.id,
        representation_id=current_representation.id,
        locator_id=wrong_modality_locator.id,
        unit_kind="pdf_figure",
        unit_id="00000000-0000-0000-0000-000000009004",
        text="Latency wrong modality type must not appear.",
        index_version=1,
        embedding_workspace_id=workspace.id,
        now=now,
    )

    wrong_embedding_locator = _image_locator(
        db,
        workspace_id=workspace.id,
        asset_id=image.id,
        representation_id=current_representation.id,
        generation=1,
        region_x=0.9,
        now=now,
    )
    _add_unit(
        db,
        workspace_id=workspace.id,
        asset_id=image.id,
        representation_id=current_representation.id,
        locator_id=wrong_embedding_locator.id,
        unit_kind="image_caption",
        unit_id="00000000-0000-0000-0000-000000009005",
        text="Unrelated invalid vector.",
        index_version=1,
        embedding_workspace_id=foreign_workspace.id,
        now=now,
    )


def _image_locator(
    db: Session,
    *,
    workspace_id: str,
    asset_id: str,
    representation_id: str,
    generation: int,
    region_x: float,
    now: datetime,
) -> EvidenceLocator:
    locator = EvidenceLocator(
        workspace_id=workspace_id,
        asset_id=asset_id,
        locator_kind="image_region",
        locator_version=1,
        processing_generation_snapshot=generation,
        representation_id_snapshot=representation_id,
        created_at=now,
    )
    db.add(locator)
    db.flush()
    db.add(
        ImageLocatorDetail(
            locator_id=locator.id,
            coordinate_space="image_normalized_top_left_v1",
            width_pixels=1200,
            height_pixels=800,
            orientation_applied=True,
        )
    )
    db.add(
        SpatialLocatorRegion(
            locator_id=locator.id,
            region_order=0,
            x=region_x,
            y=0.1,
            width=0.05,
            height=0.1,
        )
    )
    return locator


def _add_unit(
    db: Session,
    *,
    workspace_id: str,
    asset_id: str,
    representation_id: str,
    locator_id: str,
    unit_kind: str,
    unit_id: str,
    text: str,
    index_version: int,
    embedding_workspace_id: str,
    now: datetime,
) -> None:
    unit = ContentUnit(
        id=unit_id,
        workspace_id=workspace_id,
        asset_id=asset_id,
        representation_id=representation_id,
        source_locator_id=locator_id,
        unit_kind=unit_kind,
        unit_order=0,
        text_content=text,
        token_count=6,
        char_start=None,
        char_end=None,
        index_version=index_version,
        created_at=now,
    )
    db.add(unit)
    db.flush()
    representation = db.get(AssetRepresentation, representation_id)
    locator = db.get(EvidenceLocator, locator_id)
    asset = db.get(Asset, asset_id)
    assert representation is not None
    assert locator is not None
    assert asset is not None
    is_current = (
        embedding_workspace_id == workspace_id
        and workspace_id == asset.workspace_id
        and representation.asset_id == asset_id
        and representation.workspace_id == workspace_id
        and representation.processing_generation == asset.current_processing_generation
        and locator.asset_id == asset_id
        and locator.workspace_id == workspace_id
        and locator.representation_id_snapshot == representation_id
        and locator.processing_generation_snapshot == representation.processing_generation
        and index_version == asset.current_index_version
    )
    db.add(
        ContentUnitEmbedding(
            workspace_id=embedding_workspace_id,
            asset_id=asset_id,
            content_unit_id=unit.id,
            processing_generation=representation.processing_generation,
            index_version=index_version,
            is_current=is_current,
            embedding_space="text",
            provider="mixed-test",
            model="mixed-embedding",
            dimensions=1024,
            version="mixed-v1",
            embedding=[1.0, *([0.0] * 1023)],
            created_at=now,
        )
    )


def _new_thread(db: Session, workspace: Workspace, user: User) -> ChatThread:
    now = datetime.now(UTC)
    thread = ChatThread(
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        last_message_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(thread)
    db.commit()
    return thread


def _persisted_signatures(db: Session, asset_ids: list[str]) -> set[tuple[str, str, str, str]]:
    rows = db.execute(
        select(
            Asset.asset_kind,
            ContentUnit.unit_kind,
            AssetRepresentation.representation_kind,
            EvidenceLocator.locator_kind,
        )
        .join(ContentUnit, ContentUnit.asset_id == Asset.id)
        .join(AssetRepresentation, AssetRepresentation.id == ContentUnit.representation_id)
        .join(EvidenceLocator, EvidenceLocator.id == ContentUnit.source_locator_id)
        .where(Asset.id.in_(asset_ids))
    ).all()
    return set(rows)


def test_current_persisters_emit_only_registered_text_channel_signatures() -> None:
    db, user, workspace, _mixed_pdf, _mixed_image = _build_mixed_session()
    now = datetime.now(UTC)
    pdf = Asset(
        id="00000000-0000-0000-0000-000000000300",
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        asset_kind="pdf",
        title="Persister PDF",
        source_filename="persister.pdf",
        object_key="persister.pdf",
        mime_type="application/pdf",
        byte_size=1,
        status="ready",
        current_processing_generation=1,
        current_index_version=1,
        created_at=now,
        updated_at=now,
    )
    image = Asset(
        id="00000000-0000-0000-0000-000000000400",
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        asset_kind="image",
        title="Persister Image",
        source_filename="persister.png",
        object_key="persister.png",
        mime_type="image/png",
        byte_size=1,
        status="ready",
        current_processing_generation=1,
        current_index_version=1,
        created_at=now,
        updated_at=now,
    )
    db.add_all([pdf, image])
    db.flush()
    geometry = PdfPageGeometryResult(
        media_box_points=(0.0, 0.0, 612.0, 792.0),
        crop_box_points=(0.0, 0.0, 612.0, 792.0),
        rotation_degrees=0,
        display_width_points=612.0,
        display_height_points=792.0,
    )
    ocr_text = "OCR evidence"
    artifact_text = "Model Score\nEvidence-A 91.4\nFigure 1. Trend rises."
    table_source = "Model Score\nEvidence-A 91.4"
    figure_source = "Figure 1. Trend rises."
    table_start = artifact_text.index(table_source)
    figure_start = artifact_text.index(figure_source)
    replace_pdf_content(
        db,
        asset=pdf,
        pages=[
            PageTextResult(page_number=1, text="Native evidence", geometry=geometry),
            PageTextResult(
                page_number=2,
                text=ocr_text,
                geometry=geometry,
                source_kind="ocr",
                regions=(
                    PageRegionResult(
                        text=ocr_text,
                        unit_kind="pdf_ocr_region",
                        x=0.1,
                        y=0.2,
                        width=0.4,
                        height=0.1,
                        char_start=0,
                        char_end=len(ocr_text),
                    ),
                ),
            ),
            PageTextResult(
                page_number=3,
                text="OCR located\nunlocated",
                geometry=geometry,
                source_kind="ocr",
                regions=(
                    PageRegionResult(
                        text="OCR located",
                        unit_kind="pdf_ocr_region",
                        x=0.1,
                        y=0.2,
                        width=0.4,
                        height=0.1,
                        char_start=0,
                        char_end=len("OCR located"),
                    ),
                ),
            ),
            PageTextResult(
                page_number=4,
                text=artifact_text,
                geometry=geometry,
                artifacts=(
                    PageArtifactResult(
                        text="| Model | Score |\n| --- | --- |\n| Evidence-A | 91.4 |",
                        unit_kind="pdf_table",
                        regions=(SpatialRegionResult(x=0.1, y=0.2, width=0.7, height=0.2),),
                        char_ranges=((table_start, table_start + len(table_source)),),
                    ),
                    PageArtifactResult(
                        text=figure_source,
                        unit_kind="pdf_figure",
                        regions=(SpatialRegionResult(x=0.1, y=0.5, width=0.7, height=0.2),),
                        char_ranges=((figure_start, figure_start + len(figure_source)),),
                    ),
                ),
            ),
        ],
        processing_generation=1,
        chunk_size=1_200,
        created_at=now,
    )
    normalized = ImageNormalizationResult(
        payload=b"canonical-png",
        content_sha256="a" * 64,
        width_pixels=1200,
        height_pixels=800,
        orientation_applied=True,
    )
    oriented = persist_image_orientation(
        db,
        asset=image,
        result=normalized,
        object_key=build_image_oriented_object_key(image, 1),
        processing_generation=1,
        created_at=now,
    )
    persist_image_analysis(
        db,
        asset=image,
        oriented_representation=oriented,
        geometry=normalized,
        result=ImageAnalysisResult(
            ocr_regions=(
                ImageOcrRegionResult(
                    text="Image OCR",
                    x=0.1,
                    y=0.2,
                    width=0.3,
                    height=0.1,
                    char_start=0,
                    char_end=len("Image OCR"),
                ),
            ),
            caption="Image caption",
            caption_provider="fixture",
            caption_model="fixture",
            caption_version="fixture-v1",
        ),
        processing_generation=1,
        created_at=now,
    )
    db.flush()

    current_signatures = _persisted_signatures(db, [pdf.id, image.id])
    registered = build_production_registry().retrieval_channel_scope("text").type_signatures

    assert current_signatures == registered - {
        ("pdf", "pdf_text_chunk", "pdf_text_legacy", "pdf_page")
    }


def test_mixed_text_channel_is_stable_and_filters_invalid_candidate_chains() -> None:
    db, _user, workspace, pdf, image = _build_mixed_session()
    provider = MixedEmbeddingProvider()

    first = retrieve_query_content(
        db,
        workspace.id,
        "latency 42 ms",
        provider.embed_query("latency 42 ms"),
        embedding_provider=provider,
        limit=6,
        strategy="hybrid",
    )
    second = retrieve_query_content(
        db,
        workspace.id,
        "latency 42 ms",
        provider.embed_query("latency 42 ms"),
        embedding_provider=provider,
        limit=6,
        strategy="hybrid",
    )

    assert [item.content_unit.id for item in first] == [
        "00000000-0000-0000-0000-000000001001",
        "00000000-0000-0000-0000-000000001002",
        "00000000-0000-0000-0000-000000001003",
    ]
    assert [item.content_unit.id for item in second] == [item.content_unit.id for item in first]
    assert [item.asset.id for item in first] == [pdf.id, image.id, image.id]
    assert {item.channel for item in first} == {"text"}

    image_only = retrieve_query_content(
        db,
        workspace.id,
        "latency 42 ms",
        provider.embed_query("latency 42 ms"),
        asset_ids=[image.id],
        embedding_provider=provider,
        limit=6,
        strategy="hybrid",
    )
    assert [item.asset.id for item in image_only] == [image.id, image.id]
    pdf_only = retrieve_query_content(
        db,
        workspace.id,
        "latency 42 ms",
        provider.embed_query("latency 42 ms"),
        asset_ids=[pdf.id],
        embedding_provider=provider,
        limit=6,
        strategy="hybrid",
    )
    assert [item.asset.id for item in pdf_only] == [pdf.id]
    assert retrieve_query_content(
        db,
        workspace.id,
        "latency 42 ms",
        provider.embed_query("latency 42 ms"),
        asset_ids=[],
        embedding_provider=provider,
        limit=6,
        strategy="hybrid",
    ) == []


def test_candidate_limits_count_unique_evidence_locations_before_fusion() -> None:
    db, _user, workspace, pdf, image = _build_mixed_session()
    provider = MixedEmbeddingProvider()
    _add_duplicate_pdf_page_candidates(
        db,
        workspace,
        pdf,
        datetime.now(UTC),
        count=4,
    )
    db.commit()
    statements: list[str] = []
    bind = db.get_bind()

    def capture_statement(_conn, _cursor, statement, _parameters, _context, _many) -> None:
        statements.append(" ".join(statement.lower().split()))

    event.listen(bind, "before_cursor_execute", capture_statement)

    try:
        dense = retrieve_content(
            db,
            workspace.id,
            provider.embed_query("latency 42 ms"),
            embedding_provider=provider,
            limit=3,
        )
        lexical = retrieve_lexical_content(
            db,
            workspace.id,
            "latency 42 ms",
            limit=3,
        )
    finally:
        event.remove(bind, "before_cursor_execute", capture_statement)

    assert [item.asset.id for item in dense] == [pdf.id, image.id, image.id]
    assert [item.asset.id for item in lexical] == [pdf.id, image.id, image.id]
    assert len({item.location_key for item in dense}) == 3
    assert len({item.location_key for item in lexical}) == 3
    assert sum(" from pdf_locator_details " in item for item in statements) == 2
    assert sum(" from image_locator_details " in item for item in statements) == 2
    assert sum(" from spatial_locator_regions " in item for item in statements) == 2


@pytest.mark.parametrize("drift_field", ["processing_generation", "index_version"])
def test_sqlite_dense_retrieval_rejects_embedding_projection_drift(
    drift_field: str,
) -> None:
    db, _user, workspace, pdf, _image = _build_mixed_session()
    provider = MixedEmbeddingProvider()
    embedding = db.scalar(
        select(ContentUnitEmbedding)
        .join(ContentUnit, ContentUnit.id == ContentUnitEmbedding.content_unit_id)
        .where(ContentUnit.asset_id == pdf.id)
    )
    assert embedding is not None
    setattr(embedding, drift_field, 99)
    db.commit()

    assert retrieve_content(
        db,
        workspace.id,
        provider.embed_query("latency 42 ms"),
        asset_ids=[pdf.id],
        embedding_provider=provider,
        limit=6,
    ) == []


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_detail", "has no typed detail"),
        ("missing_region", "requires at least one region"),
        ("invalid_geometry", "contains invalid typed details"),
    ],
)
def test_batched_retrieval_keys_fail_closed_on_corrupt_locator_details(
    mutation: str,
    message: str,
) -> None:
    db, _user, workspace, _pdf, image = _build_mixed_session()
    provider = MixedEmbeddingProvider()
    caption_unit = db.scalar(
        select(ContentUnit).where(
            ContentUnit.asset_id == image.id,
            ContentUnit.unit_kind == "image_caption",
        )
    )
    assert caption_unit is not None
    detail = db.get(ImageLocatorDetail, caption_unit.source_locator_id)
    assert detail is not None
    if mutation == "missing_detail":
        db.delete(detail)
    elif mutation == "missing_region":
        db.execute(
            delete(SpatialLocatorRegion).where(
                SpatialLocatorRegion.locator_id == caption_unit.source_locator_id
            )
        )
    else:
        detail.width_pixels = 0
    db.commit()

    with pytest.raises(EvidenceContractError, match=message):
        retrieve_content(
            db,
            workspace.id,
            provider.embed_query("latency 42 ms"),
            asset_ids=[image.id],
            embedding_provider=provider,
            limit=6,
        )


def test_offline_lexical_corpus_reuses_current_chain_and_selected_asset_scope() -> None:
    db, user, workspace, pdf, _image = _build_mixed_session()
    now = datetime.now(UTC)
    other_pdf = Asset(
        id="00000000-0000-0000-0000-000000000500",
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        asset_kind="pdf",
        title="Out of scope PDF",
        source_filename="other.pdf",
        object_key="other.pdf",
        mime_type="application/pdf",
        byte_size=1,
        status="ready",
        current_processing_generation=1,
        current_index_version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(other_pdf)
    db.flush()
    other_representation = AssetRepresentation(
        workspace_id=workspace.id,
        asset_id=other_pdf.id,
        representation_kind="pdf_page_layout",
        processing_generation=1,
        generator_version="pdf-layout-v1",
        created_at=now,
    )
    db.add(other_representation)
    db.flush()
    other_page = PdfPage(
        workspace_id=workspace.id,
        asset_id=other_pdf.id,
        representation_id=other_representation.id,
        page_number=1,
        extracted_text="Out of scope evidence.",
        char_count=22,
        created_at=now,
    )
    other_locator = EvidenceLocator(
        workspace_id=workspace.id,
        asset_id=other_pdf.id,
        locator_kind="pdf_page",
        locator_version=1,
        processing_generation_snapshot=1,
        representation_id_snapshot=other_representation.id,
        created_at=now,
    )
    db.add_all([other_page, other_locator])
    db.flush()
    db.add(
        PdfLocatorDetail(
            locator_id=other_locator.id,
            page_id=other_page.id,
            page_number=1,
        )
    )
    _add_unit(
        db,
        workspace_id=workspace.id,
        asset_id=other_pdf.id,
        representation_id=other_representation.id,
        locator_id=other_locator.id,
        unit_kind="pdf_text_chunk",
        unit_id="00000000-0000-0000-0000-000000009100",
        text="Out of scope evidence.",
        index_version=1,
        embedding_workspace_id=workspace.id,
        now=now,
    )

    current_representation = db.scalar(
        select(AssetRepresentation).where(
            AssetRepresentation.asset_id == pdf.id,
            AssetRepresentation.representation_kind == "pdf_page_layout",
            AssetRepresentation.processing_generation == 1,
        )
    )
    assert current_representation is not None
    page = db.scalar(select(PdfPage).where(PdfPage.asset_id == pdf.id))
    assert page is not None
    old_representation = AssetRepresentation(
        workspace_id=workspace.id,
        asset_id=pdf.id,
        representation_kind="pdf_page_layout",
        processing_generation=2,
        generator_version="old-generation",
        created_at=now,
    )
    db.add(old_representation)
    db.flush()
    old_locator = EvidenceLocator(
        workspace_id=workspace.id,
        asset_id=pdf.id,
        locator_kind="pdf_page",
        locator_version=1,
        processing_generation_snapshot=2,
        representation_id_snapshot=old_representation.id,
        created_at=now,
    )
    cross_asset_locator = EvidenceLocator(
        workspace_id=workspace.id,
        asset_id=other_pdf.id,
        locator_kind="pdf_page",
        locator_version=1,
        processing_generation_snapshot=1,
        representation_id_snapshot=current_representation.id,
        created_at=now,
    )
    db.add_all([old_locator, cross_asset_locator])
    db.flush()
    db.add_all(
        [
            PdfLocatorDetail(locator_id=old_locator.id, page_id=page.id, page_number=4),
            PdfLocatorDetail(
                locator_id=cross_asset_locator.id,
                page_id=page.id,
                page_number=4,
            ),
        ]
    )
    _add_unit(
        db,
        workspace_id=workspace.id,
        asset_id=pdf.id,
        representation_id=old_representation.id,
        locator_id=old_locator.id,
        unit_kind="pdf_text_chunk",
        unit_id="00000000-0000-0000-0000-000000009101",
        text="Old generation corpus poison.",
        index_version=1,
        embedding_workspace_id=workspace.id,
        now=now,
    )
    _add_unit(
        db,
        workspace_id=workspace.id,
        asset_id=pdf.id,
        representation_id=current_representation.id,
        locator_id=cross_asset_locator.id,
        unit_kind="pdf_text_chunk",
        unit_id="00000000-0000-0000-0000-000000009102",
        text="Cross asset corpus poison.",
        index_version=1,
        embedding_workspace_id=workspace.id,
        now=now,
    )
    db.commit()

    corpus = LexicalCorpus.from_database(db, workspace.id, asset_ids=[pdf.id])

    assert [(record.asset_id, record.content_unit_id) for record in corpus.records] == [
        (pdf.id, "00000000-0000-0000-0000-000000001001")
    ]


def test_mixed_chat_freezes_pdf_and_image_citations_and_explicit_scope() -> None:
    db, user, workspace, pdf, image = _build_mixed_session()
    provider = MixedEmbeddingProvider()
    completed = complete_chat(
        db,
        workspace_id=workspace.id,
        user_id=user.id,
        thread=_new_thread(db, workspace, user),
        question="Compare the latency evidence.",
        asset_scope=AllReadyAssetScope(mode="all_ready"),
        embedding_provider=provider,
        generation_provider=MixedGenerationProvider(),
    )

    assert [citation.asset_kind_snapshot for citation in completed.citations] == [
        "pdf",
        "image",
        "image",
    ]
    assert [citation.asset_id for citation in completed.citations] == [pdf.id, image.id, image.id]
    assert [citation.processing_generation_snapshot for citation in completed.citations] == [1, 1, 1]
    scope = db.get(MessageRetrievalScope, completed.user_message.id)
    assert scope is not None and scope.scope_mode == "all_ready"
    scope_assets = db.scalars(
        select(MessageRetrievalScopeAsset)
        .where(MessageRetrievalScopeAsset.message_id == completed.user_message.id)
        .order_by(MessageRetrievalScopeAsset.asset_order)
    ).all()
    assert [(item.asset_id, item.asset_kind_snapshot) for item in scope_assets] == [
        (pdf.id, "pdf"),
        (image.id, "image"),
    ]

    selected = complete_chat(
        db,
        workspace_id=workspace.id,
        user_id=user.id,
        thread=_new_thread(db, workspace, user),
        question="Use only the selected image.",
        asset_scope=SelectedAssetScope(mode="selected", assetIds=[image.id]),
        embedding_provider=provider,
        generation_provider=MixedGenerationProvider(),
    )
    assert [citation.asset_id for citation in selected.citations] == [image.id, image.id]
    selected_scope = db.get(MessageRetrievalScope, selected.user_message.id)
    assert selected_scope is not None and selected_scope.scope_mode == "selected"
    selected_assets = db.scalars(
        select(MessageRetrievalScopeAsset).where(
            MessageRetrievalScopeAsset.message_id == selected.user_message.id
        )
    ).all()
    assert [(item.asset_id, item.asset_order) for item in selected_assets] == [(image.id, 0)]

    reversed_scope = complete_chat(
        db,
        workspace_id=workspace.id,
        user_id=user.id,
        thread=_new_thread(db, workspace, user),
        question="Compare both assets in selected order.",
        asset_scope=SelectedAssetScope(mode="selected", assetIds=[image.id, pdf.id]),
        embedding_provider=provider,
        generation_provider=MixedGenerationProvider(),
    )
    reversed_assets = db.scalars(
        select(MessageRetrievalScopeAsset)
        .where(MessageRetrievalScopeAsset.message_id == reversed_scope.user_message.id)
        .order_by(MessageRetrievalScopeAsset.asset_order)
    ).all()
    assert [(item.asset_id, item.asset_order) for item in reversed_assets] == [
        (image.id, 0),
        (pdf.id, 1),
    ]


def test_postgresql_mixed_retrieval_matches_sqlite_oracle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_url = make_url(settings.database_url)
    if not base_url.drivername.startswith("postgresql"):
        pytest.skip("PostgreSQL mixed retrieval oracle requires PostgreSQL")
    database_name = f"citeframe_m305_{uuid4().hex[:12]}"
    admin_url = base_url.set(database="postgres")
    try:
        admin_engine = create_engine(admin_url, future=True, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    except OperationalError as error:
        pytest.skip(f"PostgreSQL mixed retrieval oracle is unavailable: {error}")

    oracle_url = base_url.set(database=database_name)
    try:
        bootstrap_engine = create_engine(
            oracle_url,
            future=True,
            isolation_level="AUTOCOMMIT",
        )
        with bootstrap_engine.connect() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        bootstrap_engine.dispose()

        monkeypatch.setattr(
            settings,
            "database_url",
            oracle_url.render_as_string(hide_password=False),
        )
        alembic_config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        command.upgrade(alembic_config, "head")

        oracle_engine = create_engine(oracle_url, future=True)
        factory = sessionmaker(bind=oracle_engine, autoflush=False, future=True)
        provider = MixedEmbeddingProvider()
        with factory() as db:
            _user, workspace, pdf, image = _populate_mixed_session(db)
            _add_duplicate_pdf_page_candidates(
                db,
                workspace,
                pdf,
                datetime.now(UTC),
                count=4,
            )
            db.commit()

            def result_ids(asset_ids: list[str] | None) -> list[str]:
                return [
                    item.content_unit.id
                    for item in retrieve_query_content(
                        db,
                        workspace.id,
                        "latency 42 ms",
                        provider.embed_query("latency 42 ms"),
                        asset_ids=asset_ids,
                        embedding_provider=provider,
                        limit=6,
                        strategy="hybrid",
                    )
                ]

            expected = [
                "00000000-0000-0000-0000-000000001001",
                "00000000-0000-0000-0000-000000001002",
                "00000000-0000-0000-0000-000000001003",
            ]
            migration_heads = set(ScriptDirectory.from_config(alembic_config).get_heads())
            assert migration_heads == {
                db.execute(text("select version_num from alembic_version")).scalar_one()
            }
            generated_column = db.execute(
                text(
                    """
                    SELECT is_generated, generation_expression
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'content_units'
                      AND column_name = 'search_vector'
                    """
                )
            ).mappings().one()
            assert generated_column["is_generated"] == "ALWAYS"
            assert "to_tsvector" in generated_column["generation_expression"]
            index_definition = db.scalar(
                text(
                    "SELECT pg_get_indexdef(indexrelid) FROM pg_index "
                    "WHERE indexrelid = 'ix_content_units_text_content_fts'::regclass"
                )
            )
            assert index_definition is not None
            assert "search_vector" in index_definition
            assert "to_tsvector" not in index_definition
            assert result_ids(None) == expected
            assert result_ids(None) == expected
            assert result_ids([pdf.id]) == expected[:1]
            assert result_ids([image.id]) == expected[1:]
            dense_unique = retrieve_content(
                db,
                workspace.id,
                provider.embed_query("latency 42 ms"),
                embedding_provider=provider,
                limit=3,
            )
            lexical_unique = retrieve_lexical_content(
                db,
                workspace.id,
                "latency 42 ms",
                limit=3,
            )
            assert [item.asset.id for item in dense_unique] == [pdf.id, image.id, image.id]
            assert [item.asset.id for item in lexical_unique] == [pdf.id, image.id, image.id]
        oracle_engine.dispose()
    finally:
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "select pg_terminate_backend(pid) from pg_stat_activity "
                    "where datname=:database_name and pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        admin_engine.dispose()
