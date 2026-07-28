from collections.abc import Generator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_pdf_api.core.settings import settings
from ai_pdf_api.db.base import Base
from ai_pdf_api.db.session import get_db
from ai_pdf_api.modalities.evidence import EvidenceContractError, serialize_evidence_locator
from ai_pdf_api.models import (
    ChatMessage,
    ChatThread,
    Asset,
    AssetRepresentation,
    AssetTag,
    EvidenceLocator,
    MessageCitation,
    Note,
    NoteSource,
    NoteTag,
    PdfLocatorDetail,
    SpatialLocatorRegion,
    User,
    Workspace,
    WorkspaceMembership,
)
from ai_pdf_api.routers.notes import router


@pytest.fixture()
def notes_app() -> Generator[tuple[TestClient, Session, User, Workspace, User, Workspace], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, future=True)()
    now = datetime.now(UTC)

    owner = User(
        id=str(uuid4()),
        email="notes-owner@example.com",
        name="Notes owner",
        password_hash="hash",
        avatar_url="https://example.com/owner.svg",
    )
    other = User(
        id=str(uuid4()),
        email="notes-other@example.com",
        name="Other owner",
        password_hash="hash",
        avatar_url="https://example.com/other.svg",
    )
    workspace = Workspace(
        id=str(uuid4()),
        name="Notes workspace",
        created_by_user_id=owner.id,
        created_at=now,
        updated_at=now,
    )
    other_workspace = Workspace(
        id=str(uuid4()),
        name="Other workspace",
        created_by_user_id=other.id,
        created_at=now,
        updated_at=now,
    )
    session.add_all([owner, other, workspace, other_workspace])
    session.flush()
    session.add_all(
        [
            WorkspaceMembership(workspace_id=workspace.id, user_id=owner.id, role="owner"),
            WorkspaceMembership(workspace_id=other_workspace.id, user_id=other.id, role="owner"),
        ]
    )
    session.commit()

    app = FastAPI()
    app.include_router(router)

    def override_get_db() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client, session, owner, workspace, other, other_workspace
    app.dependency_overrides.clear()
    session.close()


def create_asset(session: Session, *, workspace: Workspace, user: User) -> Asset:
    asset = Asset(
        asset_kind="pdf",
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        title="Source paper",
        source_filename="source.pdf",
        object_key=f"workspaces/{workspace.id}/assets/source.pdf",
        mime_type="application/pdf",
        byte_size=100,
        status="ready",
        current_index_version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(asset)
    session.commit()
    return asset


def create_citation(session: Session, *, workspace: Workspace, user: User, asset: Asset) -> MessageCitation:
    now = datetime.now(UTC)
    thread = ChatThread(
        id=str(uuid4()),
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        title="Research",
        last_message_at=now,
        created_at=now,
        updated_at=now,
    )
    message = ChatMessage(
        id=str(uuid4()),
        workspace_id=workspace.id,
        thread_id=thread.id,
        role="assistant",
        content="An answer with a source.",
        status="completed",
        created_at=now,
    )
    representation = AssetRepresentation(
        id=str(uuid4()),
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_kind="pdf_text_legacy",
        processing_generation=1,
        generator_version="fixture-parser-v1",
        created_at=now,
    )
    locator = EvidenceLocator(
        id=str(uuid4()),
        workspace_id=workspace.id,
        asset_id=asset.id,
        locator_kind="pdf_page",
        locator_version=1,
        processing_generation_snapshot=1,
        representation_id_snapshot=representation.id,
        created_at=now,
    )
    session.add_all([thread, message, representation, locator])
    session.flush()
    session.add(PdfLocatorDetail(locator_id=locator.id, page_number=8))
    citation = MessageCitation(
        id=str(uuid4()),
        workspace_id=workspace.id,
        message_id=message.id,
        citation_index=0,
        evidence_locator_id=locator.id,
        asset_id=asset.id,
        asset_kind_snapshot="pdf",
        asset_title_snapshot=asset.title,
        excerpt_snapshot="A persisted source excerpt.",
        processing_generation_snapshot=1,
        representation_id_snapshot=representation.id,
        parser_version_snapshot="fixture-parser-v1",
        index_version_snapshot=1,
        created_at=now,
    )
    session.add(citation)
    session.commit()
    return citation


def headers(user: User) -> dict[str, str]:
    return {"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": user.id}


def test_create_note_persists_citation_snapshot(notes_app) -> None:
    client, session, owner, workspace, _other, _other_workspace = notes_app
    asset = create_asset(session, workspace=workspace, user=owner)
    citation = create_citation(session, workspace=workspace, user=owner, asset=asset)

    response = client.post(
        f"/v1/workspaces/{workspace.id}/notes",
        headers=headers(owner),
        json={
            "title": "Method notes",
            "bodyMd": "The method is useful.",
            "sourceCitationIds": [citation.id],
        },
    )

    assert response.status_code == 201
    payload = response.json()
    note = payload["note"]
    source = payload["sources"][0]
    assert note["workspaceId"] == workspace.id
    assert note["tagIds"] == []
    assert note["tags"] == []
    assert source == note["sources"][0]
    assert source["messageCitationId"] == citation.id
    assert source["assetId"] == asset.id
    assert source["assetTitle"] == "Source paper"
    assert source["assetKind"] == "pdf"
    assert source["locator"] == {"kind": "pdf_page", "version": 1, "pageNumber": 8}
    assert source["sourceVersions"]["parserVersion"] == "fixture-parser-v1"
    assert source["excerpt"] == "A persisted source excerpt."

    persisted = session.scalar(select(Note).where(Note.id == note["id"]))
    assert persisted is not None
    source_row = session.scalar(select(NoteSource).where(NoteSource.note_id == persisted.id))
    assert source_row is not None
    assert source_row.message_citation_id == citation.id
    assert source_row.asset_title_snapshot == "Source paper"


def test_create_note_clones_pdf_region_source_snapshot(notes_app) -> None:
    client, session, owner, workspace, _other, _other_workspace = notes_app
    asset = create_asset(session, workspace=workspace, user=owner)
    citation = create_citation(session, workspace=workspace, user=owner, asset=asset)
    locator = session.get(EvidenceLocator, citation.evidence_locator_id)
    detail = session.get(PdfLocatorDetail, citation.evidence_locator_id)
    assert locator is not None and detail is not None
    locator.locator_kind = "pdf_region"
    detail.coordinate_space = "pdf_crop_box_normalized_top_left_v1"
    detail.crop_x0_points = 0.0
    detail.crop_y0_points = 0.0
    detail.crop_x1_points = 612.0
    detail.crop_y1_points = 792.0
    detail.rotation_degrees = 0
    detail.display_width_points = 612.0
    detail.display_height_points = 792.0
    session.add_all(
        [
            SpatialLocatorRegion(
                locator_id=locator.id,
                region_order=0,
                x=0.15,
                y=0.25,
                width=0.3,
                height=0.1,
            ),
            SpatialLocatorRegion(
                locator_id=locator.id,
                region_order=1,
                x=0.2,
                y=0.5,
                width=0.4,
                height=0.1,
            ),
        ]
    )
    session.commit()

    response = client.post(
        f"/v1/workspaces/{workspace.id}/notes",
        headers=headers(owner),
        json={"bodyMd": "Regional note.", "sourceCitationIds": [citation.id]},
    )

    assert response.status_code == 201
    locator_payload = response.json()["sources"][0]["locator"]
    assert locator_payload["kind"] == "pdf_region"
    assert locator_payload["pageGeometry"] == {
        "cropBoxPoints": [0.0, 0.0, 612.0, 792.0],
        "rotationDegrees": 0,
        "displayWidthPoints": 612.0,
        "displayHeightPoints": 792.0,
    }
    assert locator_payload["regions"] == [
        {"x": 0.15, "y": 0.25, "width": 0.3, "height": 0.1},
        {"x": 0.2, "y": 0.5, "width": 0.4, "height": 0.1},
    ]


def test_evidence_serializer_rejects_unsupported_locator_version(notes_app) -> None:
    _client, session, owner, workspace, _other, _other_workspace = notes_app
    asset = create_asset(session, workspace=workspace, user=owner)
    citation = create_citation(session, workspace=workspace, user=owner, asset=asset)
    locator = session.get(EvidenceLocator, citation.evidence_locator_id)
    assert locator is not None
    locator.locator_version = 2
    session.commit()

    with pytest.raises(
        EvidenceContractError,
        match="Unsupported locator version for pdf_page: 2",
    ):
        serialize_evidence_locator(session, locator.id)


def test_evidence_codec_rejects_unsupported_coordinate_space(notes_app) -> None:
    _client, session, owner, workspace, _other, _other_workspace = notes_app
    asset = create_asset(session, workspace=workspace, user=owner)
    citation = create_citation(session, workspace=workspace, user=owner, asset=asset)
    locator = session.get(EvidenceLocator, citation.evidence_locator_id)
    detail = session.get(PdfLocatorDetail, citation.evidence_locator_id)
    assert locator is not None and detail is not None
    locator.locator_kind = "pdf_region"
    detail.coordinate_space = "wrong_space"
    detail.crop_x0_points = 0.0
    detail.crop_y0_points = 0.0
    detail.crop_x1_points = 612.0
    detail.crop_y1_points = 792.0
    detail.rotation_degrees = 0
    detail.display_width_points = 612.0
    detail.display_height_points = 792.0
    session.add(
        SpatialLocatorRegion(
            locator_id=locator.id,
            region_order=0,
            x=0.1,
            y=0.2,
            width=0.3,
            height=0.1,
        )
    )
    session.commit()

    with pytest.raises(EvidenceContractError, match="unsupported coordinate space"):
        serialize_evidence_locator(session, locator.id)


@pytest.mark.parametrize("citation_kind", ["missing", "cross_workspace"])
def test_create_note_rejects_invalid_citation_without_partial_note(notes_app, citation_kind: str) -> None:
    client, session, owner, workspace, other, other_workspace = notes_app
    citation_id = str(uuid4())
    if citation_kind == "cross_workspace":
        other_asset = create_asset(session, workspace=other_workspace, user=other)
        citation_id = create_citation(
            session,
            workspace=other_workspace,
            user=other,
            asset=other_asset,
        ).id

    response = client.post(
        f"/v1/workspaces/{workspace.id}/notes",
        headers=headers(owner),
        json={"bodyMd": "Should not be saved.", "sourceCitationIds": [citation_id]},
    )

    assert response.status_code == 404
    assert session.scalar(select(func.count()).select_from(Note).where(Note.workspace_id == workspace.id)) == 0


def test_tags_and_bindings_return_refreshable_snapshots_and_replace_relations(notes_app) -> None:
    client, session, owner, workspace, _other, _other_workspace = notes_app
    asset = create_asset(session, workspace=workspace, user=owner)
    note_response = client.post(
        f"/v1/workspaces/{workspace.id}/notes",
        headers=headers(owner),
        json={"bodyMd": "A free note."},
    )
    note_id = note_response.json()["note"]["id"]
    tag_one = client.post(
        f"/v1/workspaces/{workspace.id}/tags",
        headers=headers(owner),
        json={"name": "Important", "slug": "important", "color": "#f97316"},
    ).json()["tag"]
    tag_two = client.post(
        f"/v1/workspaces/{workspace.id}/tags",
        headers=headers(owner),
        json={"name": "Review", "slug": "review"},
    ).json()["tag"]

    asset_binding = client.post(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}/tags",
        headers=headers(owner),
        json={"tagIds": [tag_one["id"], tag_two["id"]]},
    )
    assert asset_binding.status_code == 200
    assert asset_binding.json()["tagIds"] == [tag_one["id"], tag_two["id"]]

    note_binding = client.post(
        f"/v1/workspaces/{workspace.id}/notes/{note_id}/tags",
        headers=headers(owner),
        json={"tagIds": [tag_one["id"]]},
    )
    assert note_binding.status_code == 200
    assert note_binding.json()["tagIds"] == [tag_one["id"]]

    tags = client.get(f"/v1/workspaces/{workspace.id}/tags", headers=headers(owner)).json()["items"]
    by_id = {tag["id"]: tag for tag in tags}
    assert by_id[tag_one["id"]]["assetIds"] == [asset.id]
    assert by_id[tag_one["id"]]["noteIds"] == [note_id]
    assert by_id[tag_two["id"]]["assetIds"] == [asset.id]
    assert by_id[tag_two["id"]]["noteIds"] == []

    notes = client.get(f"/v1/workspaces/{workspace.id}/notes", headers=headers(owner)).json()["items"]
    note = next(item for item in notes if item["id"] == note_id)
    assert note["tagIds"] == [tag_one["id"]]
    assert note["tags"][0]["name"] == "Important"

    cleared_note = client.post(
        f"/v1/workspaces/{workspace.id}/notes/{note_id}/tags",
        headers=headers(owner),
        json={"tagIds": []},
    )
    assert cleared_note.status_code == 200
    assert cleared_note.json()["tagIds"] == []
    assert session.scalar(select(NoteTag).where(NoteTag.note_id == note_id)) is None

    cleared_asset = client.post(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}/tags",
        headers=headers(owner),
        json={"tagIds": []},
    )
    assert cleared_asset.status_code == 200
    assert cleared_asset.json()["tagIds"] == []
    assert session.scalar(select(AssetTag).where(AssetTag.asset_id == asset.id)) is None


def test_workspace_isolation_rejects_foreign_resources_and_tag_ids(notes_app) -> None:
    client, session, owner, workspace, other, other_workspace = notes_app
    asset = create_asset(session, workspace=workspace, user=owner)
    foreign_tag_response = client.post(
        f"/v1/workspaces/{other_workspace.id}/tags",
        headers=headers(other),
        json={"name": "Private", "slug": "private"},
    )
    assert foreign_tag_response.status_code == 201
    foreign_tag_id = foreign_tag_response.json()["tag"]["id"]

    denied_workspace = client.get(f"/v1/workspaces/{other_workspace.id}/tags", headers=headers(owner))
    assert denied_workspace.status_code == 404
    denied_binding = client.post(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}/tags",
        headers=headers(owner),
        json={"tagIds": [foreign_tag_id]},
    )
    assert denied_binding.status_code == 404
    assert session.scalar(select(AssetTag).where(AssetTag.asset_id == asset.id)) is None


def test_deleting_tag_cleans_asset_and_note_relations(notes_app) -> None:
    client, session, owner, workspace, _other, _other_workspace = notes_app
    asset = create_asset(session, workspace=workspace, user=owner)
    note_id = client.post(
        f"/v1/workspaces/{workspace.id}/notes",
        headers=headers(owner),
        json={"bodyMd": "A note."},
    ).json()["note"]["id"]
    tag_id = client.post(
        f"/v1/workspaces/{workspace.id}/tags",
        headers=headers(owner),
        json={"name": "Delete me", "slug": "delete-me"},
    ).json()["tag"]["id"]
    client.post(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}/tags",
        headers=headers(owner),
        json={"tagIds": [tag_id]},
    )
    client.post(
        f"/v1/workspaces/{workspace.id}/notes/{note_id}/tags",
        headers=headers(owner),
        json={"tagIds": [tag_id]},
    )

    deleted = client.delete(f"/v1/workspaces/{workspace.id}/tags/{tag_id}", headers=headers(owner))

    assert deleted.status_code == 204
    assert session.scalar(select(AssetTag).where(AssetTag.tag_id == tag_id)) is None
    assert session.scalar(select(NoteTag).where(NoteTag.tag_id == tag_id)) is None
    assert client.get(f"/v1/workspaces/{workspace.id}/tags/{tag_id}", headers=headers(owner)).status_code == 404
