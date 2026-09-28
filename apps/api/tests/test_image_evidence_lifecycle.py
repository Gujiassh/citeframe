from ai_pdf_api.routers.deps import require_workspace_member

import json
import base64
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from ai_pdf_api.db.base import Base
from ai_pdf_api.modalities.evidence import (
    EvidenceContractError,
    clone_evidence_locator,
    serialize_evidence_locator,
)
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
    MessageInputEvidence,
    MessageCitation,
    Note,
    NoteSource,
    SpatialLocatorRegion,
    User,
    Workspace,
    WorkspaceMembership,
)
from ai_pdf_api.routers.chat import list_thread_messages, to_citation
from ai_pdf_api.schemas.chat import (
    AllReadyAssetScope,
    ImageRegionEvidenceTarget,
    ImageRegionLocator,
    PdfPageLocator,
    PdfRegionLocator,
    SelectedAssetScope,
    SpatialRegion,
)
from ai_pdf_api.schemas.notes import CreateNoteRequest
from ai_pdf_api.services.chat import ChatError, complete_chat, prepare_chat
from ai_pdf_api.services.evidence_targets import EvidenceTargetError, resolve_evidence_targets
from ai_pdf_api.services.notes import NotesError, create_note, get_note
from ai_pdf_api.services.providers import ModelProviderError
from ai_pdf_api.services import chat as chat_service

FIXTURE_DIRECTORY = Path(__file__).resolve().parents[3] / "docs/fixtures/evidence-contract"


class FakeEmbeddingProvider:
    provider = "fake"
    model = "fake-embedding"
    dimensions = 3
    version = "fake-v1"

    def embed_query(self, _text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


class FakeGenerationProvider:
    provider = "fake"
    model = "fake-generation"

    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    def generate(self, messages: list[dict[str, object]]) -> str:
        self.messages = messages
        return "The image shows the sustained latency drop [1]."


class FailingGenerationProvider(FakeGenerationProvider):
    def generate(self, messages: list[dict[str, object]]) -> str:
        self.messages = messages
        raise ModelProviderError("generation_provider_unreachable", "Provider unavailable.")


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIRECTORY / name).read_text(encoding="utf-8"))


def _build_image_session() -> tuple[
    Session,
    User,
    Workspace,
    Asset,
    ChatThread,
    AssetRepresentation,
    AssetRepresentation,
    EvidenceLocator,
]:
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, future=True)()
    now = datetime.now(UTC)
    user = User(
        id=str(uuid4()),
        email="image-evidence@example.com",
        name="Image evidence owner",
        password_hash="hash",
        avatar_url="https://example.com/avatar.svg",
    )
    workspace = Workspace(
        id=str(uuid4()),
        name="Image evidence",
        created_by_user_id=user.id,
        retrieval_top_k=1,
        created_at=now,
        updated_at=now,
    )
    asset = Asset(
        id=str(uuid4()),
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        asset_kind="image",
        title="Synthetic Image Evidence Fixture",
        source_filename="image-coordinate-fixture.png",
        object_key="fixtures/image-coordinate-fixture.png",
        mime_type="image/png",
        byte_size=1,
        source_sha256="0" * 64,
        status="ready",
        current_processing_generation=1,
        current_index_version=1,
        created_at=now,
        updated_at=now,
    )
    thread = ChatThread(
        id=str(uuid4()),
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        title=None,
        last_message_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add_all([user, workspace, asset, thread])
    session.flush()
    session.add(WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role="owner"))
    oriented = AssetRepresentation(
        id=str(uuid4()),
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_kind="image_oriented",
        processing_generation=1,
        generator_provider="pillow",
        generator_version="pillow-canonical-png-v1",
        object_key="representations/1/image-oriented.png",
        content_sha256="585b2489a7e6288d71636258b84e56610b345a1fc74ffd42967ee434678d8955",
        created_at=now,
    )
    caption = AssetRepresentation(
        id=str(uuid4()),
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_kind="image_caption",
        processing_generation=1,
        generator_provider="openai",
        generator_model="gpt-5.5",
        generator_version="image-caption-v1",
        created_at=now,
    )
    session.add_all([oriented, caption])
    session.flush()
    session.add(
        ImageRepresentationGeometry(
            representation_id=oriented.id,
            workspace_id=workspace.id,
            asset_id=asset.id,
            width_pixels=1200,
            height_pixels=800,
            orientation_applied=True,
        )
    )
    locator = EvidenceLocator(
        id=str(uuid4()),
        workspace_id=workspace.id,
        asset_id=asset.id,
        locator_kind="image_region",
        locator_version=1,
        processing_generation_snapshot=1,
        representation_id_snapshot=caption.id,
        created_at=now,
    )
    session.add(locator)
    session.flush()
    session.add(
        ImageLocatorDetail(
            locator_id=locator.id,
            coordinate_space="image_normalized_top_left_v1",
            width_pixels=1200,
            height_pixels=800,
            orientation_applied=True,
        )
    )
    session.add_all(
        [
            SpatialLocatorRegion(
                locator_id=locator.id,
                region_order=0,
                x=0.066667,
                y=0.2375,
                width=0.566667,
                height=0.525,
            ),
            SpatialLocatorRegion(
                locator_id=locator.id,
                region_order=1,
                x=0.683333,
                y=0.275,
                width=0.25,
                height=0.375,
            ),
        ]
    )
    unit = ContentUnit(
        id=str(uuid4()),
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_id=caption.id,
        source_locator_id=locator.id,
        unit_kind="image_caption",
        unit_order=0,
        text_content="Release 4 begins the sustained latency drop.",
        token_count=8,
        char_start=None,
        char_end=None,
        index_version=1,
        created_at=now,
    )
    session.add(unit)
    session.flush()
    session.add(
        ContentUnitEmbedding(
            workspace_id=workspace.id,
            asset_id=asset.id,
            content_unit_id=unit.id,
            processing_generation=1,
            index_version=1,
            is_current=True,
            embedding_space="text",
            provider="fake",
            model="fake-embedding",
            dimensions=3,
            version="fake-v1",
            embedding=[1.0, 0.0, 0.0],
            created_at=now,
        )
    )
    session.commit()
    return session, user, workspace, asset, thread, oriented, caption, locator


def _target(asset: Asset, **overrides: object) -> ImageRegionEvidenceTarget:
    payload = {
        "kind": "image_region",
        "assetId": asset.id,
        "processingGeneration": 1,
        "coordinateSpace": "image_normalized_top_left_v1",
        "regions": [{"x": 0.1, "y": 0.2, "width": 0.2, "height": 0.3}],
        **overrides,
    }
    return ImageRegionEvidenceTarget.model_validate(payload)


def _fixture_png() -> bytes:
    return (FIXTURE_DIRECTORY / "image-coordinate-fixture.png").read_bytes()


def _add_ocr_unit(
    session: Session,
    *,
    workspace: Workspace,
    asset: Asset,
    text: str = "Observation: 42 ms",
    region: SpatialRegion | None = None,
) -> tuple[AssetRepresentation, EvidenceLocator]:
    now = datetime.now(UTC)
    ocr = AssetRepresentation(
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_kind="image_ocr",
        processing_generation=1,
        generator_provider="rapidocr",
        generator_version="rapidocr-image-region-v1",
        created_at=now,
    )
    session.add(ocr)
    session.flush()
    locator = EvidenceLocator(
        workspace_id=workspace.id,
        asset_id=asset.id,
        locator_kind="image_region",
        locator_version=1,
        processing_generation_snapshot=1,
        representation_id_snapshot=ocr.id,
        created_at=now,
    )
    session.add(locator)
    session.flush()
    session.add(
        ImageLocatorDetail(
            locator_id=locator.id,
            coordinate_space="image_normalized_top_left_v1",
            width_pixels=1200,
            height_pixels=800,
            orientation_applied=True,
        )
    )
    selected = region or SpatialRegion(x=0.12, y=0.22, width=0.1, height=0.1)
    session.add(
        SpatialLocatorRegion(
            locator_id=locator.id,
            region_order=0,
            x=selected.x,
            y=selected.y,
            width=selected.width,
            height=selected.height,
        )
    )
    session.add(
        ContentUnit(
            workspace_id=workspace.id,
            asset_id=asset.id,
            representation_id=ocr.id,
            source_locator_id=locator.id,
            unit_kind="image_ocr_region",
            unit_order=0,
            text_content=text,
            token_count=4,
            char_start=None,
            char_end=None,
            index_version=1,
            created_at=now,
        )
    )
    session.commit()
    return ocr, locator


def _expected_citation(
    citation: MessageCitation,
    *,
    asset: Asset,
    representation: AssetRepresentation,
) -> dict:
    expected = _load_fixture("image-citation.json")
    expected.update(
        {
            "id": citation.id,
            "messageId": citation.message_id,
            "assetId": asset.id,
        }
    )
    expected["sourceVersions"]["representationId"] = representation.id
    return expected


def test_image_citation_and_note_source_remain_frozen_after_reprocessing() -> None:
    session, user, workspace, asset, thread, _oriented, caption, _locator = (
        _build_image_session()
    )
    completed = complete_chat(
        session,
        workspace_id=workspace.id,
        user_id=user.id,
        thread=thread,
        question="When does latency begin to drop?",
        asset_scope=AllReadyAssetScope(mode="all_ready"),
        embedding_provider=FakeEmbeddingProvider(),
        generation_provider=FakeGenerationProvider(),
    )
    citation = completed.citations[0]
    expected_citation = _expected_citation(
        citation,
        asset=asset,
        representation=caption,
    )
    citation_before = to_citation(session, citation).model_dump()
    assert citation_before == expected_citation
    citation_locator_id = citation.evidence_locator_id

    created = create_note(
        session,
        workspace.id,
        user.id,
        CreateNoteRequest(
            bodyMd="The latency drop begins at release 4.",
            sourceCitationIds=[citation.id],
        ),
    )
    source = session.scalar(
        select(NoteSource).where(NoteSource.note_id == created.note.id)
    )
    assert source is not None
    assert source.evidence_locator_id != citation.evidence_locator_id
    assert source.processing_generation_snapshot == 1
    assert source.representation_id_snapshot == caption.id

    expected_source = _load_fixture("image-note-source.json")
    expected_source.update(
        {
            "id": source.id,
            "messageCitationId": citation.id,
            "assetId": asset.id,
            "createdAt": source.created_at.replace(tzinfo=UTC).isoformat(),
        }
    )
    expected_source["sourceVersions"]["representationId"] = caption.id
    source_before = created.sources[0].model_dump()
    assert source_before == expected_source
    source_locator_id = source.evidence_locator_id
    source_locator_before = serialize_evidence_locator(
        session,
        source.evidence_locator_id,
        workspace_id=workspace.id,
        asset_id=asset.id,
        processing_generation=1,
        representation_id=caption.id,
    ).model_dump()
    assert source_locator_before == expected_source["locator"]

    now = datetime.now(UTC)
    session.add_all(
        [
            AssetRepresentation(
                workspace_id=workspace.id,
                asset_id=asset.id,
                representation_kind="image_oriented",
                processing_generation=2,
                generator_provider="pillow",
                generator_version="pillow-canonical-png-v1",
                object_key="representations/2/image-oriented.png",
                content_sha256="2" * 64,
                created_at=now,
            ),
            AssetRepresentation(
                workspace_id=workspace.id,
                asset_id=asset.id,
                representation_kind="image_caption",
                processing_generation=2,
                generator_provider="openai",
                generator_model="gpt-5.5",
                generator_version="image-caption-v2",
                created_at=now,
            ),
        ]
    )
    asset.current_processing_generation = 2
    asset.current_index_version = 2
    session.commit()

    session.refresh(citation)
    session.refresh(source)
    assert citation.evidence_locator_id == citation_locator_id
    assert source.evidence_locator_id == source_locator_id
    assert to_citation(session, citation).model_dump() == citation_before
    source_after = get_note(session, workspace.id, created.note.id).note.sources[0].model_dump()
    assert source_after == source_before
    assert serialize_evidence_locator(
        session,
        source.evidence_locator_id,
        workspace_id=workspace.id,
        asset_id=asset.id,
        processing_generation=1,
        representation_id=caption.id,
    ).model_dump() == source_locator_before


@pytest.mark.parametrize("invalid_snapshot", ["display_representation", "generation"])
def test_image_evidence_rejects_inconsistent_representation_snapshot(
    invalid_snapshot: str,
) -> None:
    session, _user, _workspace, _asset, _thread, oriented, _caption, locator = (
        _build_image_session()
    )
    if invalid_snapshot == "display_representation":
        locator.representation_id_snapshot = oriented.id
    else:
        locator.processing_generation_snapshot = 2
    session.flush()

    with pytest.raises(EvidenceContractError):
        serialize_evidence_locator(session, locator.id)
    with pytest.raises(EvidenceContractError):
        clone_evidence_locator(session, locator.id, created_at=datetime.now(UTC))


def test_image_evidence_rejects_missing_regions_before_clone() -> None:
    session, _user, _workspace, _asset, _thread, _oriented, _caption, locator = (
        _build_image_session()
    )
    session.execute(
        delete(SpatialLocatorRegion).where(SpatialLocatorRegion.locator_id == locator.id)
    )
    session.commit()

    with pytest.raises(EvidenceContractError, match="requires at least one region"):
        clone_evidence_locator(session, locator.id, created_at=datetime.now(UTC))


@pytest.mark.parametrize(
    "overrides",
    [
        {"widthPixels": 0},
        {"orientationApplied": False},
        {"regions": [{"x": 0.8, "y": 0.2, "width": 0.3, "height": 0.1}]},
    ],
)
def test_image_locator_schema_rejects_invalid_geometry(overrides: dict) -> None:
    payload = {
        "kind": "image_region",
        "version": 1,
        "coordinateSpace": "image_normalized_top_left_v1",
        "widthPixels": 1200,
        "heightPixels": 800,
        "orientationApplied": True,
        "regions": [{"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1}],
        **overrides,
    }
    with pytest.raises(ValidationError):
        ImageRegionLocator.model_validate(payload)


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (PdfPageLocator, {"kind": "pdf_page", "version": 1, "pageNumber": 0}),
        (
            PdfRegionLocator,
            {
                "kind": "pdf_region",
                "version": 1,
                "pageNumber": 0,
                "coordinateSpace": "pdf_crop_box_normalized_top_left_v1",
                "pageGeometry": {
                    "cropBoxPoints": [0, 0, 612, 792],
                    "rotationDegrees": 0,
                    "displayWidthPoints": 612,
                    "displayHeightPoints": 792,
                },
                "regions": [{"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1}],
            },
        ),
    ],
)
def test_pdf_locator_schema_rejects_non_positive_pages(schema: type, payload: dict) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate(payload)


def test_note_creation_rolls_back_when_citation_snapshot_drifted() -> None:
    session, user, workspace, asset, thread, _oriented, _caption, _locator = (
        _build_image_session()
    )
    completed = complete_chat(
        session,
        workspace_id=workspace.id,
        user_id=user.id,
        thread=thread,
        question="When does latency begin to drop?",
        asset_scope=AllReadyAssetScope(mode="all_ready"),
        embedding_provider=FakeEmbeddingProvider(),
        generation_provider=FakeGenerationProvider(),
    )
    citation = completed.citations[0]
    citation.processing_generation_snapshot = 2
    session.commit()

    with pytest.raises(NotesError, match="invalid evidence"):
        create_note(
            session,
            workspace.id,
            user.id,
            CreateNoteRequest(bodyMd="Do not persist.", sourceCitationIds=[citation.id]),
        )
    assert session.scalar(select(func.count()).select_from(Note)) == 0


@pytest.mark.parametrize(
    "forbidden_field",
    ["representationId", "excerpt", "widthPixels", "heightPixels", "orientationApplied"],
)
def test_image_evidence_target_rejects_client_owned_fields(forbidden_field: str) -> None:
    payload = {
        "kind": "image_region",
        "assetId": "asset",
        "processingGeneration": 1,
        "coordinateSpace": "image_normalized_top_left_v1",
        "regions": [{"x": 0.1, "y": 0.2, "width": 0.2, "height": 0.3}],
        forbidden_field: "forbidden",
    }

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ImageRegionEvidenceTarget.model_validate(payload)


def test_image_evidence_target_rejects_extra_region_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ImageRegionEvidenceTarget.model_validate(
            {
                "kind": "image_region",
                "assetId": "asset",
                "processingGeneration": 1,
                "coordinateSpace": "image_normalized_top_left_v1",
                "regions": [
                    {"x": 0.1, "y": 0.2, "width": 0.2, "height": 0.3, "pixels": 42}
                ],
            }
        )


def test_image_target_resolver_uses_caption_and_crops_canonical_png() -> None:
    session, _user, workspace, asset, _thread, oriented, caption, source_locator = (
        _build_image_session()
    )
    original_locator_count = session.scalar(select(func.count()).select_from(EvidenceLocator))

    resolved = resolve_evidence_targets(
        session,
        workspace_id=workspace.id,
        targets=[_target(asset)],
        created_at=datetime.now(UTC),
        image_bytes_loader=lambda object_key: (
            _fixture_png() if object_key == oriented.object_key else b"wrong object"
        ),
    )

    assert len(resolved) == 1
    target = resolved[0]
    assert target.representation.id == caption.id
    assert target.representation.representation_kind == "image_caption"
    assert target.locator.id != source_locator.id
    assert target.locator.representation_id_snapshot == caption.id
    assert target.excerpt == "Release 4 begins the sustained latency drop."
    assert session.scalar(select(func.count()).select_from(EvidenceLocator)) == original_locator_count + 1
    assert len(target.image_payloads) == 1
    with Image.open(BytesIO(_fixture_png())) as source, Image.open(
        BytesIO(target.image_payloads[0])
    ) as crop:
        source.load()
        crop.load()
        assert crop.format == "PNG"
        assert crop.size == (240, 240)
        expected_pixels = source.crop((120, 160, 360, 400)).tobytes()
        assert sha256(crop.tobytes()).hexdigest() == sha256(expected_pixels).hexdigest()


def test_image_target_resolver_prefers_overlapping_ocr_evidence() -> None:
    session, _user, workspace, asset, _thread, oriented, caption, _source_locator = (
        _build_image_session()
    )
    ocr, _ocr_locator = _add_ocr_unit(
        session,
        workspace=workspace,
        asset=asset,
        text="Observation: 42 ms",
    )

    resolved = resolve_evidence_targets(
        session,
        workspace_id=workspace.id,
        targets=[_target(asset)],
        created_at=datetime.now(UTC),
        image_bytes_loader=lambda object_key: (
            _fixture_png() if object_key == oriented.object_key else b"wrong object"
        ),
    )[0]

    assert resolved.representation.id == ocr.id
    assert resolved.representation.id != caption.id
    assert resolved.representation.representation_kind == "image_ocr"
    assert resolved.excerpt == "Observation: 42 ms"


def test_image_target_resolver_uses_caption_when_any_selected_region_lacks_ocr() -> None:
    session, _user, workspace, asset, _thread, oriented, caption, _source_locator = (
        _build_image_session()
    )
    _add_ocr_unit(session, workspace=workspace, asset=asset)
    target = _target(
        asset,
        regions=[
            {"x": 0.1, "y": 0.2, "width": 0.2, "height": 0.3},
            {"x": 0.7, "y": 0.7, "width": 0.1, "height": 0.1},
        ],
    )

    resolved = resolve_evidence_targets(
        session,
        workspace_id=workspace.id,
        targets=[target],
        created_at=datetime.now(UTC),
        image_bytes_loader=lambda object_key: (
            _fixture_png() if object_key == oriented.object_key else b"wrong object"
        ),
    )[0]

    assert resolved.representation.id == caption.id
    assert resolved.excerpt == "Release 4 begins the sustained latency drop."
    assert [Image.open(BytesIO(payload)).size for payload in resolved.image_payloads] == [
        (240, 240),
        (120, 80),
    ]


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("generation", "evidence_target_generation_changed"),
        ("geometry", "evidence_target_geometry_invalid"),
        ("hash", "evidence_target_image_invalid"),
        ("caption", "evidence_target_content_invalid"),
    ],
)
def test_image_target_resolver_fails_closed_without_persisting_locator(
    mutation: str,
    expected_code: str,
) -> None:
    session, _user, workspace, asset, _thread, oriented, _caption, _source_locator = (
        _build_image_session()
    )
    target = _target(asset)
    if mutation == "generation":
        asset.current_processing_generation = 2
    elif mutation == "geometry":
        geometry = session.get(ImageRepresentationGeometry, oriented.id)
        assert geometry is not None
        geometry.orientation_applied = False
    elif mutation == "hash":
        oriented.content_sha256 = "f" * 64
    else:
        caption_unit = session.scalar(
            select(ContentUnit).where(ContentUnit.unit_kind == "image_caption")
        )
        assert caption_unit is not None
        caption_unit.unit_kind = "image_ocr_region"
    session.commit()
    locator_count = session.scalar(select(func.count()).select_from(EvidenceLocator))

    with pytest.raises(EvidenceTargetError) as captured:
        resolve_evidence_targets(
            session,
            workspace_id=workspace.id,
            targets=[target],
            created_at=datetime.now(UTC),
            image_bytes_loader=lambda _object_key: _fixture_png(),
        )
    session.rollback()

    assert captured.value.code == expected_code
    assert session.scalar(select(func.count()).select_from(EvidenceLocator)) == locator_count


def test_image_region_chat_persists_input_evidence_and_multimodal_payload() -> None:
    session, user, workspace, asset, thread, oriented, caption, _source_locator = (
        _build_image_session()
    )
    generation = FakeGenerationProvider()

    completed = complete_chat(
        session,
        workspace_id=workspace.id,
        user_id=user.id,
        thread=thread,
        question="What is inside this image region?",
        asset_scope=AllReadyAssetScope(mode="all_ready"),
        evidence_targets=[_target(asset)],
        embedding_provider=FakeEmbeddingProvider(),
        generation_provider=generation,
        image_bytes_loader=lambda object_key: (
            _fixture_png() if object_key == oriented.object_key else b"wrong object"
        ),
    )

    input_row = session.scalar(
        select(MessageInputEvidence).where(
            MessageInputEvidence.message_id == completed.user_message.id
        )
    )
    assert input_row is not None
    assert input_row.target_order == 0
    assert input_row.asset_id == asset.id
    assert input_row.representation_id_snapshot == caption.id
    assert input_row.evidence_locator_id not in {
        citation.evidence_locator_id for citation in completed.citations
    }
    user_input = generation.messages[-1]
    assert user_input["role"] == "user"
    content = user_input["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "input_text"
    assert "What is inside this image region?" in content[0]["text"]
    assert content[1]["type"] == "input_image"
    image_url = content[1]["image_url"]
    assert image_url.startswith("data:image/png;base64,")
    with Image.open(BytesIO(base64.b64decode(image_url.split(",", 1)[1]))) as crop:
        assert crop.size == (240, 240)

    refreshed = list_thread_messages(
        workspace.id,
        thread.id,
        access=require_workspace_member(workspace.id, user.id, session),
        db=session,
    )
    user_dto = next(message for message in refreshed.messages if message.id == completed.user_message.id)
    assert len(user_dto.inputEvidence) == 1
    evidence = user_dto.inputEvidence[0]
    assert evidence.id == input_row.id
    assert evidence.excerpt == "Release 4 begins the sustained latency drop."
    assert evidence.locator.model_dump() == {
        "kind": "image_region",
        "version": 1,
        "coordinateSpace": "image_normalized_top_left_v1",
        "widthPixels": 1200,
        "heightPixels": 800,
        "orientationApplied": True,
        "regions": [{"x": 0.1, "y": 0.2, "width": 0.2, "height": 0.3}],
    }


def test_image_region_chat_succeeds_without_retrieval_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, user, workspace, asset, thread, oriented, _caption, _source_locator = (
        _build_image_session()
    )
    monkeypatch.setattr(chat_service, "retrieve_query_content", lambda *_args, **_kwargs: [])

    completed = complete_chat(
        session,
        workspace_id=workspace.id,
        user_id=user.id,
        thread=thread,
        question="Analyze only this region.",
        asset_scope=AllReadyAssetScope(mode="all_ready"),
        evidence_targets=[_target(asset)],
        embedding_provider=FakeEmbeddingProvider(),
        generation_provider=FakeGenerationProvider(),
        image_bytes_loader=lambda object_key: (
            _fixture_png() if object_key == oriented.object_key else b"wrong object"
        ),
    )

    assert completed.assistant_message.status == "completed"
    assert completed.citations == []
    assert session.scalar(
        select(func.count()).select_from(MessageInputEvidence).where(
            MessageInputEvidence.message_id == completed.user_message.id
        )
    ) == 1


def test_image_region_chat_failure_retains_user_input_evidence() -> None:
    session, user, workspace, asset, thread, oriented, _caption, _source_locator = (
        _build_image_session()
    )

    with pytest.raises(ModelProviderError):
        complete_chat(
            session,
            workspace_id=workspace.id,
            user_id=user.id,
            thread=thread,
            question="Analyze this region.",
            asset_scope=AllReadyAssetScope(mode="all_ready"),
            evidence_targets=[_target(asset)],
            embedding_provider=FakeEmbeddingProvider(),
            generation_provider=FailingGenerationProvider(),
            image_bytes_loader=lambda object_key: (
                _fixture_png() if object_key == oriented.object_key else b"wrong object"
            ),
        )

    input_row = session.scalar(select(MessageInputEvidence))
    assert input_row is not None
    assert session.get(EvidenceLocator, input_row.evidence_locator_id) is not None
    failed_assistant = session.scalar(
        select(ChatMessage).where(ChatMessage.role == "assistant")
    )
    assert failed_assistant is not None
    assert failed_assistant.status == "failed"
    assert session.scalar(
        select(func.count()).select_from(MessageCitation).where(
            MessageCitation.message_id == failed_assistant.id
        )
    ) == 0


def test_chat_rejects_image_target_outside_selected_asset_scope() -> None:
    session, user, workspace, image_asset, thread, _oriented, _caption, _source_locator = (
        _build_image_session()
    )
    pdf_asset = Asset(
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        asset_kind="pdf",
        title="Selected PDF",
        source_filename="selected.pdf",
        object_key="selected.pdf",
        mime_type="application/pdf",
        byte_size=1,
        status="ready",
        current_processing_generation=1,
        current_index_version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(pdf_asset)
    session.commit()

    with pytest.raises(ChatError) as captured:
        prepare_chat(
            session,
            workspace_id=workspace.id,
            user_id=user.id,
            thread=thread,
            question="Analyze the image.",
            asset_scope=SelectedAssetScope(mode="selected", assetIds=[pdf_asset.id]),
            evidence_targets=[_target(image_asset)],
            embedding_provider=FakeEmbeddingProvider(),
            generation_provider=FakeGenerationProvider(),
        )

    assert captured.value.code == "evidence_target_outside_scope"
    assert session.scalar(select(func.count()).select_from(MessageInputEvidence)) == 0


def test_direct_image_region_note_freezes_source_without_citation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, user, workspace, asset, _thread, _oriented, caption, _source_locator = (
        _build_image_session()
    )
    monkeypatch.setattr(
        "ai_pdf_api.services.evidence_targets.download_bytes",
        lambda _object_key: _fixture_png(),
    )

    created = create_note(
        session,
        workspace.id,
        user.id,
        CreateNoteRequest(
            title="Selected chart region",
            bodyMd="The region shows the latency change.",
            evidenceTargets=[_target(asset)],
        ),
    )

    assert len(created.sources) == 1
    source_before = created.sources[0].model_dump()
    assert source_before["messageCitationId"] is None
    assert source_before["sourceVersions"]["representationId"] == caption.id
    source_row = session.scalar(
        select(NoteSource).where(NoteSource.note_id == created.note.id)
    )
    assert source_row is not None
    assert source_row.message_citation_id is None
    assert source_row.source_order == 0

    asset.current_processing_generation = 2
    asset.current_index_version = 2
    session.commit()

    assert get_note(session, workspace.id, created.note.id).note.sources[0].model_dump() == source_before


def test_direct_note_rolls_back_all_targets_when_later_target_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, user, workspace, asset, _thread, _oriented, _caption, _source_locator = (
        _build_image_session()
    )
    monkeypatch.setattr(
        "ai_pdf_api.services.evidence_targets.download_bytes",
        lambda _object_key: _fixture_png(),
    )
    locator_count = session.scalar(select(func.count()).select_from(EvidenceLocator))

    with pytest.raises(NotesError) as captured:
        create_note(
            session,
            workspace.id,
            user.id,
            CreateNoteRequest(
                bodyMd="This note must roll back.",
                evidenceTargets=[
                    _target(asset),
                    _target(asset, processingGeneration=2),
                ],
            ),
        )

    assert captured.value.code == "evidence_target_generation_changed"
    assert session.scalar(select(func.count()).select_from(Note)) == 0
    assert session.scalar(select(func.count()).select_from(NoteSource)) == 0
    assert session.scalar(select(func.count()).select_from(EvidenceLocator)) == locator_count


@pytest.mark.parametrize("failure", ["missing", "corrupt_after_valid"])
def test_direct_note_rejects_unopenable_canonical_image_atomically(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    session, user, workspace, asset, _thread, _oriented, _caption, _source_locator = (
        _build_image_session()
    )
    baseline = {
        "notes": session.scalar(select(func.count()).select_from(Note)),
        "sources": session.scalar(select(func.count()).select_from(NoteSource)),
        "locators": session.scalar(select(func.count()).select_from(EvidenceLocator)),
        "details": session.scalar(select(func.count()).select_from(ImageLocatorDetail)),
        "regions": session.scalar(select(func.count()).select_from(SpatialLocatorRegion)),
    }
    calls = 0

    def load_image(_object_key: str) -> bytes:
        nonlocal calls
        calls += 1
        if failure == "missing":
            raise FileNotFoundError("canonical image is missing")
        return _fixture_png() if calls == 1 else b"corrupt canonical image"

    monkeypatch.setattr("ai_pdf_api.services.evidence_targets.download_bytes", load_image)
    targets = [_target(asset)]
    if failure == "corrupt_after_valid":
        targets.append(_target(asset, regions=[{"x": 0.4, "y": 0.2, "width": 0.2, "height": 0.3}]))

    with pytest.raises(NotesError) as captured:
        create_note(
            session,
            workspace.id,
            user.id,
            CreateNoteRequest(bodyMd="This note must not persist.", evidenceTargets=targets),
        )

    assert captured.value.code == "evidence_target_image_invalid"
    assert session.scalar(select(func.count()).select_from(Note)) == baseline["notes"]
    assert session.scalar(select(func.count()).select_from(NoteSource)) == baseline["sources"]
    assert session.scalar(select(func.count()).select_from(EvidenceLocator)) == baseline["locators"]
    assert session.scalar(select(func.count()).select_from(ImageLocatorDetail)) == baseline["details"]
    assert session.scalar(select(func.count()).select_from(SpatialLocatorRegion)) == baseline["regions"]
