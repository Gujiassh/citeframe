from datetime import UTC, datetime

import pytest
from ai_pdf_api.core.settings import settings
from ai_pdf_api.models import (
    Asset,
    IngestionJob,
    WorkspaceMembership,
)
from asset_router_test_support import (
    create_asset,
    create_user,
    create_workspace_with_membership,
)
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_list_assets_requires_membership(
    asset_client: TestClient, asset_db_session: Session
) -> None:
    owner = create_user(asset_db_session, email="owner@example.com", name="Owner")
    stranger = create_user(
        asset_db_session, email="stranger@example.com", name="Stranger"
    )
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Private"
    )
    create_asset(asset_db_session, workspace=workspace, user=owner)

    response = asset_client.get(
        f"/v1/workspaces/{workspace.id}/assets",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": stranger.id,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Workspace not found."


def test_get_asset_file_streams_original_pdf_for_members(
    asset_client: TestClient, asset_db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = create_user(asset_db_session, email="owner@example.com", name="Owner")
    member = create_user(asset_db_session, email="member@example.com", name="Member")
    stranger = create_user(
        asset_db_session, email="stranger@example.com", name="Stranger"
    )
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Private"
    )
    asset_db_session.add(
        WorkspaceMembership(workspace_id=workspace.id, user_id=member.id, role="editor")
    )
    asset_db_session.commit()
    asset = create_asset(
        asset_db_session,
        workspace=workspace,
        user=owner,
        source_filename="原始资料.pdf",
    )
    monkeypatch.setattr(
        "ai_pdf_api.routers.assets.stream_bytes",
        lambda object_key: iter((b"%PDF-1.7\n", b"original page bytes")),
    )

    for user_id in (owner.id, member.id):
        response = asset_client.get(
            f"/v1/workspaces/{workspace.id}/assets/{asset.id}/file",
            headers={
                "x-ai-pdf-internal-token": settings.api_internal_token,
                "x-user-id": user_id,
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["content-disposition"].startswith("inline; filename*=")
        assert response.content == b"%PDF-1.7\noriginal page bytes"

    forbidden_response = asset_client.get(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}/file",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": stranger.id,
        },
    )
    assert forbidden_response.status_code == 404
    assert forbidden_response.json()["detail"] == "Workspace not found."


def test_create_upload_session_persists_pending_asset(
    asset_client: TestClient, asset_db_session: Session
) -> None:
    owner = create_user(asset_db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )

    response = asset_client.post(
        f"/v1/workspaces/{workspace.id}/assets/upload-session",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
        },
        json={
            "sourceFilename": "attention.pdf",
            "mimeType": "application/pdf",
            "byteSize": len(b"%PDF-1.7 fake pdf bytes"),
            "title": "Attention Is All You Need",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["asset"]["workspaceId"] == workspace.id
    assert payload["asset"]["status"] == "pending_upload"
    assert payload["upload"]["method"] == "PUT"
    assert payload["upload"]["headers"]["Content-Type"] == "application/pdf"
    assert payload["upload"]["objectKey"].startswith(
        f"workspaces/{workspace.id}/assets/"
    )

    asset = asset_db_session.get(Asset, payload["asset"]["id"])
    assert asset is not None
    assert asset.status == "pending_upload"
    assert asset.object_key == payload["upload"]["objectKey"]


def test_create_upload_session_canonicalizes_mime_type(
    asset_client: TestClient,
    asset_db_session: Session,
) -> None:
    owner = create_user(asset_db_session, email="mime-owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )

    response = asset_client.post(
        f"/v1/workspaces/{workspace.id}/assets/upload-session",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
        },
        json={
            "sourceFilename": "attention.pdf",
            "mimeType": "APPLICATION/PDF",
            "byteSize": len(b"%PDF-1.7 fake pdf bytes"),
        },
    )

    assert response.status_code == 201
    assert response.json()["asset"]["mimeType"] == "application/pdf"
    assert response.json()["upload"]["headers"] == {"Content-Type": "application/pdf"}


def test_create_upload_session_rejects_unregistered_mime_type(
    asset_client: TestClient, asset_db_session: Session
) -> None:
    owner = create_user(asset_db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )

    response = asset_client.post(
        f"/v1/workspaces/{workspace.id}/assets/upload-session",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
        },
        json={
            "sourceFilename": "notes.txt",
            "mimeType": "text/plain",
            "byteSize": 12,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Unsupported MIME type: text/plain"


@pytest.mark.parametrize(
    ("source_filename", "mime_type"),
    [
        ("diagram.png", "image/png"),
        ("photo.jpg", "image/jpeg"),
        ("chart.webp", "image/webp"),
    ],
)
def test_create_upload_session_accepts_enabled_image_formats(
    asset_client: TestClient,
    asset_db_session: Session,
    source_filename: str,
    mime_type: str,
) -> None:
    owner = create_user(asset_db_session, email="image-owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Images"
    )

    response = asset_client.post(
        f"/v1/workspaces/{workspace.id}/assets/upload-session",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
        },
        json={
            "sourceFilename": source_filename,
            "mimeType": mime_type,
            "byteSize": 128,
        },
    )

    assert response.status_code == 201
    assert response.json()["asset"]["kind"] == "image"
    assert response.json()["asset"]["mimeType"] == mime_type
    assert response.json()["upload"]["headers"] == {"Content-Type": mime_type}
    assert (
        asset_db_session.query(Asset).filter_by(workspace_id=workspace.id).count() == 1
    )


def test_binary_upload_and_finalize_creates_queued_ingestion_job(
    asset_client: TestClient, asset_db_session: Session
) -> None:
    owner = create_user(asset_db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )
    upload_session = asset_client.post(
        f"/v1/workspaces/{workspace.id}/assets/upload-session",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
        },
        json={
            "sourceFilename": "attention.pdf",
            "mimeType": "application/pdf",
            "byteSize": len(b"%PDF-1.7 fake pdf bytes"),
            "title": "Attention Is All You Need",
        },
    ).json()

    asset_id = upload_session["asset"]["id"]
    object_key = upload_session["upload"]["objectKey"]

    upload_response = asset_client.put(
        f"/v1/workspaces/{workspace.id}/assets/{asset_id}/upload",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
            "content-type": "application/pdf",
        },
        params={"objectKey": object_key},
        content=b"%PDF-1.7 fake pdf bytes",
    )
    assert upload_response.status_code == 204

    finalize_response = asset_client.post(
        f"/v1/workspaces/{workspace.id}/assets/{asset_id}/finalize-upload",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
        },
        json={"objectKey": object_key},
    )

    assert finalize_response.status_code == 200
    payload = finalize_response.json()
    assert payload["asset"]["status"] == "uploaded"
    assert payload["job"]["jobType"] == "ingest"
    assert payload["job"]["status"] == "queued"

    asset = asset_db_session.get(Asset, asset_id)
    assert asset is not None
    assert asset.status == "uploaded"
    assert asset.latest_ingestion_job_id == payload["job"]["id"]

    job = asset_db_session.get(IngestionJob, payload["job"]["id"])
    assert job is not None
    assert job.asset_id == asset_id
    assert job.job_type == "ingest"


def test_binary_upload_rejects_size_mismatch(
    asset_client: TestClient, asset_db_session: Session
) -> None:
    owner = create_user(asset_db_session, email="size-owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )
    upload_session = asset_client.post(
        f"/v1/workspaces/{workspace.id}/assets/upload-session",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
        },
        json={
            "sourceFilename": "attention.pdf",
            "mimeType": "application/pdf",
            "byteSize": 99,
        },
    ).json()

    response = asset_client.put(
        f"/v1/workspaces/{workspace.id}/assets/{upload_session['asset']['id']}/upload",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
            "content-type": "application/pdf",
        },
        params={"objectKey": upload_session["upload"]["objectKey"]},
        content=b"short",
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Upload size does not match the upload session."


def test_binary_upload_rejects_content_type_mismatch(
    asset_client: TestClient,
    asset_db_session: Session,
) -> None:
    owner = create_user(
        asset_db_session, email="content-type-owner@example.com", name="Owner"
    )
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )
    source = b"%PDF-1.7 fake pdf bytes"
    upload_session = asset_client.post(
        f"/v1/workspaces/{workspace.id}/assets/upload-session",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
        },
        json={
            "sourceFilename": "attention.pdf",
            "mimeType": "application/pdf",
            "byteSize": len(source),
        },
    ).json()

    response = asset_client.put(
        f"/v1/workspaces/{workspace.id}/assets/{upload_session['asset']['id']}/upload",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
            "content-type": "image/png",
        },
        params={"objectKey": upload_session["upload"]["objectKey"]},
        content=source,
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == "Upload Content-Type does not match the upload session."
    )


def test_get_job_returns_persisted_job(
    asset_client: TestClient, asset_db_session: Session
) -> None:
    owner = create_user(asset_db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )
    asset = create_asset(
        asset_db_session, workspace=workspace, user=owner, status="uploaded"
    )
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="queued",
        attempt_count=1,
        config_snapshot={"source": "test"},
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    asset_db_session.add(job)
    asset_db_session.commit()
    asset_db_session.refresh(job)

    response = asset_client.get(
        f"/v1/workspaces/{workspace.id}/jobs/{job.id}",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job"]["id"] == job.id
    assert payload["job"]["assetId"] == asset.id
