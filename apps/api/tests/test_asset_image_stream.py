from collections.abc import Generator, Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_pdf_api.core.settings import settings
from ai_pdf_api.db.base import Base
from ai_pdf_api.db.session import get_db
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ImageRepresentationGeometry,
    User,
    Workspace,
    WorkspaceMembership,
)
from ai_pdf_api.routers.assets import router as assets_router


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(assets_router)

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    monkeypatch.setattr("ai_pdf_api.routers.assets.object_exists", lambda object_key: True)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def create_user(db: Session, email: str) -> User:
    user = User(
        email=email,
        name=email.split("@", maxsplit=1)[0],
        password_hash="hashed",
        avatar_url="https://example.com/avatar.png",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_workspace(db: Session, owner: User) -> Workspace:
    now = datetime.now(UTC)
    workspace = Workspace(
        name="Images",
        description=None,
        created_by_user_id=owner.id,
        created_at=now,
        updated_at=now,
    )
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMembership(workspace_id=workspace.id, user_id=owner.id, role="owner"))
    db.commit()
    db.refresh(workspace)
    return workspace


def create_image_asset(db: Session, workspace: Workspace, owner: User, generation: int) -> Asset:
    now = datetime.now(UTC)
    asset = Asset(
        asset_kind="image",
        workspace_id=workspace.id,
        created_by_user_id=owner.id,
        title="Evidence image",
        source_filename="photo.png",
        object_key=f"workspaces/{workspace.id}/assets/image/original.png",
        mime_type="image/png",
        byte_size=1234,
        status="ready",
        current_processing_generation=generation,
        current_index_version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def add_image_representations(
    db: Session,
    asset: Asset,
    generation: int,
    *,
    orientation_applied: bool = True,
) -> dict[str, AssetRepresentation]:
    representations: dict[str, AssetRepresentation] = {}
    for kind in ("image_oriented", "image_caption"):
        representation = AssetRepresentation(
            workspace_id=asset.workspace_id,
            asset_id=asset.id,
            representation_kind=kind,
            processing_generation=generation,
            generator_version="fixture-v1",
            object_key=(
                f"workspaces/{asset.workspace_id}/assets/{asset.id}/representations/"
                f"{generation}/image-oriented.png"
                if kind == "image_oriented"
                else None
            ),
        )
        db.add(representation)
        db.flush()
        representations[kind] = representation
    db.add(
        ImageRepresentationGeometry(
            representation_id=representations["image_oriented"].id,
            workspace_id=asset.workspace_id,
            asset_id=asset.id,
            width_pixels=1200,
            height_pixels=800,
            orientation_applied=orientation_applied,
        )
    )
    db.commit()
    return representations


def auth_headers(user: User) -> dict[str, str]:
    return {
        "x-ai-pdf-internal-token": settings.api_internal_token,
        "x-user-id": user.id,
    }


def test_image_streams_keep_frozen_evidence_separate_from_current_asset(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = create_user(db_session, "owner@example.com")
    member = create_user(db_session, "member@example.com")
    stranger = create_user(db_session, "stranger@example.com")
    workspace = create_workspace(db_session, owner)
    db_session.add(WorkspaceMembership(workspace_id=workspace.id, user_id=member.id, role="editor"))
    asset = create_image_asset(db_session, workspace, owner, 2)
    generation_one = add_image_representations(db_session, asset, 1)
    generation_two = add_image_representations(db_session, asset, 2)
    streamed_keys: list[str] = []

    def stream_fixture(object_key: str) -> Iterator[bytes]:
        streamed_keys.append(object_key)
        yield f"png:{object_key}".encode()

    monkeypatch.setattr("ai_pdf_api.routers.assets.stream_bytes", stream_fixture)
    frozen_url = (
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}/representations/image-oriented/file"
        f"?processingGeneration=1&evidenceRepresentationId={generation_one['image_caption'].id}"
    )

    for user in (owner, member):
        response = client.get(frozen_url, headers=auth_headers(user))
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.headers["cache-control"] == "private, max-age=31536000, immutable"
        assert b"representations/1/image-oriented.png" in response.content

    current_response = client.get(
        (
            f"/v1/workspaces/{workspace.id}/assets/{asset.id}/representations/"
            "current-image-oriented/file?processingGeneration=2"
        ),
        headers=auth_headers(owner),
    )
    assert current_response.status_code == 200
    assert current_response.headers["cache-control"] == "private, max-age=3600"
    assert b"representations/2/image-oriented.png" in current_response.content
    assert streamed_keys == [
        generation_one["image_oriented"].object_key,
        generation_one["image_oriented"].object_key,
        generation_two["image_oriented"].object_key,
    ]

    forbidden = client.get(frozen_url, headers=auth_headers(stranger))
    assert forbidden.status_code == 404
    assert forbidden.json()["detail"] == "Workspace not found."

    stale_current = client.get(
        (
            f"/v1/workspaces/{workspace.id}/assets/{asset.id}/representations/"
            "current-image-oriented/file?processingGeneration=1"
        ),
        headers=auth_headers(owner),
    )
    assert stale_current.status_code == 409
    assert stale_current.json()["detail"] == (
        "Current image representation changed. Reload the asset detail."
    )


def test_image_detail_and_stream_reject_invalid_oriented_geometry(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, "owner@example.com")
    workspace = create_workspace(db_session, owner)
    asset = create_image_asset(db_session, workspace, owner, 1)
    representations = add_image_representations(
        db_session,
        asset,
        1,
        orientation_applied=False,
    )
    headers = auth_headers(owner)

    detail = client.get(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}",
        headers=headers,
    )
    assert detail.status_code == 500
    assert detail.json()["detail"] == "Oriented image representation geometry is invalid."

    base_url = f"/v1/workspaces/{workspace.id}/assets/{asset.id}/representations/image-oriented/file"
    wrong_evidence = client.get(
        f"{base_url}?processingGeneration=1&evidenceRepresentationId={representations['image_oriented'].id}",
        headers=headers,
    )
    assert wrong_evidence.status_code == 404
    assert wrong_evidence.json()["detail"] == "Image evidence snapshot not found."

    invalid_geometry = client.get(
        f"{base_url}?processingGeneration=1&evidenceRepresentationId={representations['image_caption'].id}",
        headers=headers,
    )
    assert invalid_geometry.status_code == 500
    assert invalid_geometry.json()["detail"] == "Oriented image representation geometry is invalid."


@pytest.mark.parametrize("mismatch", ("asset", "workspace"))
def test_image_detail_rejects_geometry_linked_to_foreign_representation(
    client: TestClient,
    db_session: Session,
    mismatch: str,
) -> None:
    owner = create_user(db_session, "owner@example.com")
    workspace = create_workspace(db_session, owner)
    asset = create_image_asset(db_session, workspace, owner, 1)
    if mismatch == "asset":
        foreign_workspace = workspace
    else:
        foreign_workspace = create_workspace(db_session, owner)
    foreign_asset = create_image_asset(db_session, foreign_workspace, owner, 1)
    representation = AssetRepresentation(
        workspace_id=foreign_workspace.id,
        asset_id=foreign_asset.id,
        representation_kind="image_oriented",
        processing_generation=1,
        generator_version="fixture-v1",
        object_key=(
            f"workspaces/{foreign_workspace.id}/assets/{foreign_asset.id}/"
            "representations/1/image-oriented.png"
        ),
    )
    db_session.add(representation)
    db_session.flush()
    db_session.add(
        ImageRepresentationGeometry(
            representation_id=representation.id,
            workspace_id=workspace.id,
            asset_id=asset.id,
            width_pixels=777,
            height_pixels=333,
            orientation_applied=True,
        )
    )
    db_session.commit()

    response = client.get(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}",
        headers=auth_headers(owner),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Asset detail not found."
