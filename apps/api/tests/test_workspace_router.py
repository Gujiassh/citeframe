from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_pdf_api.core.settings import settings
from ai_pdf_api.db.base import Base
from ai_pdf_api.db.session import get_db
from ai_pdf_api.models import Asset, User, Workspace, WorkspaceMembership
from ai_pdf_api.routers.workspaces import router as workspaces_router


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(workspaces_router)

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def create_user(db_session: Session, *, email: str, name: str) -> User:
    user = User(
        email=email,
        name=name,
        password_hash="hashed",
        avatar_url=f"https://example.com/{name}.png",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def create_workspace_with_membership(
    db_session: Session,
    *,
    user: User,
    name: str,
    role: str = "owner",
    description: str | None = None,
) -> Workspace:
    now = datetime.now(UTC)
    workspace = Workspace(
        name=name,
        description=description,
        created_by_user_id=user.id,
        created_at=now,
        updated_at=now,
    )
    db_session.add(workspace)
    db_session.flush()
    db_session.add(
        WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=user.id,
            role=role,
        ),
    )
    db_session.commit()
    db_session.refresh(workspace)
    return workspace




def create_asset(db_session: Session, *, workspace: Workspace, user: User, source_filename: str = "attention.pdf") -> Asset:
    now = datetime.now(UTC)
    asset = Asset(
        asset_kind="pdf",
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        title="Attention Is All You Need",
        source_filename=source_filename,
        object_key=f"workspaces/{workspace.id}/assets/doc/original.pdf",
        mime_type="application/pdf",
        byte_size=1234,
        status="uploaded",
        current_index_version=1,
        created_at=now,
        updated_at=now,
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset
def test_list_workspaces_returns_only_current_user_memberships(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    stranger = create_user(db_session, email="stranger@example.com", name="Stranger")
    visible = create_workspace_with_membership(db_session, user=owner, name="Visible Workspace")
    create_workspace_with_membership(db_session, user=stranger, name="Hidden Workspace")

    response = client.get("/v1/workspaces", headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id})

    assert response.status_code == 200
    payload = response.json()
    assert payload["nextCursor"] is None
    assert payload["items"] == [
        {
            "id": visible.id,
            "name": "Visible Workspace",
            "description": None,
            "systemPrompt": "You are an AI research assistant. Answer using only the supplied PDF context and cite supporting sources.",
            "retrievalTopK": 6,
            "chunkSize": 1200,
            "embeddingProvider": "ollama",
            "embeddingModel": "qwen3-embedding:0.6b",
            "embeddingDimensions": 1024,
            "embeddingVersion": "embedding-v1",
            "generationProvider": "openai",
            "generationModel": "gpt-5.5",
            "role": "owner",
            "assetCount": 0,
            "noteCount": 0,
            "threadCount": 0,
            "createdAt": payload["items"][0]["createdAt"],
            "updatedAt": payload["items"][0]["updatedAt"],
        },
    ]




def test_workspace_summary_includes_real_asset_count(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Visible Workspace")
    create_asset(db_session, workspace=workspace, user=owner)

    list_response = client.get("/v1/workspaces", headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id})
    detail_response = client.get(f"/v1/workspaces/{workspace.id}", headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id})

    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    assert list_response.json()["items"][0]["assetCount"] == 1
    assert detail_response.json()["workspace"]["assetCount"] == 1
def test_create_workspace_creates_owner_membership(client: TestClient, db_session: Session) -> None:
    user = create_user(db_session, email="owner@example.com", name="Owner")

    response = client.post(
        "/v1/workspaces",
        headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": user.id},
        json={"name": " Papers ", "description": " Research notes "},
    )

    assert response.status_code == 201
    payload = response.json()
    workspace_id = payload["workspace"]["id"]
    assert payload["workspace"]["name"] == "Papers"
    assert payload["workspace"]["description"] == "Research notes"
    assert payload["workspace"]["role"] == "owner"

    workspace = db_session.get(Workspace, workspace_id)
    membership = db_session.scalar(
        select(WorkspaceMembership).where(WorkspaceMembership.workspace_id == workspace_id),
    )
    assert workspace is not None
    assert workspace.created_by_user_id == user.id
    assert membership is not None
    assert membership.user_id == user.id
    assert membership.role == "owner"


def test_update_workspace_settings_persists_and_returns_runtime_metadata(
    client: TestClient, db_session: Session
) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Settings")

    response = client.patch(
        f"/v1/workspaces/{workspace.id}/settings",
        headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id},
        json={
            "systemPrompt": "Answer with a contract-review checklist.",
            "retrievalTopK": 9,
            "chunkSize": 900,
        },
    )

    assert response.status_code == 200
    payload = response.json()["workspace"]
    assert payload["systemPrompt"] == "Answer with a contract-review checklist."
    assert payload["retrievalTopK"] == 9
    assert payload["chunkSize"] == 900
    assert payload["embeddingDimensions"] == 1024
    persisted = db_session.get(Workspace, workspace.id)
    assert persisted is not None
    assert persisted.system_prompt == "Answer with a contract-review checklist."
    assert persisted.retrieval_top_k == 9
    assert persisted.chunk_size == 900


def test_update_workspace_settings_requires_owner(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    member = create_user(db_session, email="member@example.com", name="Member")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Settings")
    db_session.add(WorkspaceMembership(workspace_id=workspace.id, user_id=member.id, role="member"))
    db_session.commit()

    response = client.patch(
        f"/v1/workspaces/{workspace.id}/settings",
        headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": member.id},
        json={"systemPrompt": "no", "retrievalTopK": 2, "chunkSize": 400},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Only workspace owners can update workspace settings."


def test_get_workspace_requires_membership(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    stranger = create_user(db_session, email="stranger@example.com", name="Stranger")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Owner Workspace")

    response = client.get(f"/v1/workspaces/{workspace.id}", headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": stranger.id})

    assert response.status_code == 404
    assert response.json()["detail"] == "Workspace not found."


def test_archive_workspace_marks_archived_and_hides_from_future_lists(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Archive Me")

    response = client.delete(f"/v1/workspaces/{workspace.id}", headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id})

    assert response.status_code == 204
    archived_workspace = db_session.get(Workspace, workspace.id)
    assert archived_workspace is not None
    assert archived_workspace.archived_at is not None

    list_response = client.get("/v1/workspaces", headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": owner.id})
    assert list_response.status_code == 200
    assert list_response.json()["items"] == []


def test_archive_workspace_requires_owner_role(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="owner@example.com", name="Owner")
    member = create_user(db_session, email="member@example.com", name="Member")
    workspace = create_workspace_with_membership(db_session, user=owner, name="Shared Workspace")
    db_session.add(
        WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=member.id,
            role="member",
        ),
    )
    db_session.commit()

    response = client.delete(f"/v1/workspaces/{workspace.id}", headers={"x-ai-pdf-internal-token": settings.api_internal_token, "x-user-id": member.id})

    assert response.status_code == 403
    assert response.json()["detail"] == "Only workspace owners can archive this workspace."


def test_workspace_routes_require_authenticated_header(client: TestClient) -> None:
    response = client.get("/v1/workspaces")

    assert response.status_code == 401
    assert response.json()["detail"] == "Internal API authentication required."


def test_workspace_routes_require_internal_api_token(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="token-owner@example.com", name="Owner")

    response = client.get("/v1/workspaces", headers={"x-user-id": owner.id})

    assert response.status_code == 401
    assert response.json()["detail"] == "Internal API authentication required."
