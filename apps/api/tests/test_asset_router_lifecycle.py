from datetime import UTC, datetime

import pytest
from ai_pdf_api.core.settings import settings
from ai_pdf_api.modalities.pdf_ingestion import (
    split_page_text,
)
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ContentUnit,
    IngestionJob,
    PdfPage,
    WorkspaceMembership,
)
from ai_pdf_api.services.ingestion import (
    claim_next_ingestion_job,
    process_ingestion_job,
)
from asset_router_test_support import (
    create_asset,
    create_pdf_content_unit,
    create_user,
    create_workspace_with_membership,
    static_pdf_adapters,
)
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


def test_asset_detail_returns_persisted_page_text(
    asset_client: TestClient, asset_db_session: Session
) -> None:
    owner = create_user(asset_db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )
    asset = create_asset(
        asset_db_session, workspace=workspace, user=owner, status="chunked"
    )
    create_pdf_content_unit(
        asset_db_session,
        asset=asset,
        page_number=1,
        text="Extracted page text.",
    )
    asset_db_session.commit()

    response = asset_client.get(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}",
        params={"pageNumber": 1},
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["asset"]["id"] == asset.id
    assert payload["detail"]["pages"] == [
        {
            "pageNumber": 1,
            "text": "Extracted page text.",
            "charCount": 20,
            "ocrBlocks": [],
        }
    ]

    missing_page = asset_client.get(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}",
        params={"pageNumber": 2},
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
        },
    )
    assert missing_page.status_code == 404
    assert missing_page.json()["detail"] == "Asset page not found."


def test_asset_detail_reads_only_current_canonical_page_representation(
    asset_client: TestClient,
    asset_db_session: Session,
) -> None:
    owner = create_user(
        asset_db_session, email="canonical-owner@example.com", name="Owner"
    )
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )
    asset = create_asset(
        asset_db_session, workspace=workspace, user=owner, status="chunked"
    )
    asset.current_processing_generation = 2
    now = datetime.now(UTC)
    legacy = AssetRepresentation(
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_kind="pdf_text_legacy",
        processing_generation=1,
        generator_version="legacy-v1",
        created_at=now,
    )
    layout = AssetRepresentation(
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_kind="pdf_page_layout",
        processing_generation=2,
        generator_version="layout-v1",
        created_at=now,
    )
    ocr = AssetRepresentation(
        workspace_id=workspace.id,
        asset_id=asset.id,
        representation_kind="pdf_ocr",
        processing_generation=2,
        generator_version="ocr-v1",
        created_at=now,
    )
    asset_db_session.add_all([legacy, layout, ocr])
    asset_db_session.flush()
    asset_db_session.add_all(
        [
            PdfPage(
                workspace_id=workspace.id,
                asset_id=asset.id,
                representation_id=legacy.id,
                page_number=1,
                extracted_text="stale generation",
                char_count=16,
                created_at=now,
            ),
            PdfPage(
                workspace_id=workspace.id,
                asset_id=asset.id,
                representation_id=layout.id,
                page_number=1,
                extracted_text="current layout",
                char_count=14,
                created_at=now,
            ),
            PdfPage(
                workspace_id=workspace.id,
                asset_id=asset.id,
                representation_id=ocr.id,
                page_number=1,
                extracted_text="non-canonical OCR row",
                char_count=21,
                created_at=now,
            ),
        ]
    )
    asset_db_session.commit()

    response = asset_client.get(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}",
        params={"pageNumber": 1},
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
        },
    )

    assert response.status_code == 200
    assert response.json()["detail"] == {
        "kind": "pdf",
        "pageCount": 1,
        "pages": [
            {
                "pageNumber": 1,
                "text": "current layout",
                "charCount": 14,
                "ocrBlocks": [],
            }
        ],
    }


def test_asset_detail_returns_persisted_ocr_blocks(
    asset_client: TestClient, asset_db_session: Session
) -> None:
    owner = create_user(asset_db_session, email="owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )
    asset = create_asset(
        asset_db_session, workspace=workspace, user=owner, status="chunked"
    )
    create_pdf_content_unit(
        asset_db_session,
        asset=asset,
        page_number=1,
        text="扫描文本",
        legacy_ocr_blocks=[
            {"text": "扫描文本", "x": 0.1, "y": 0.2, "width": 0.7, "height": 0.1}
        ],
    )
    asset_db_session.commit()

    response = asset_client.get(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}",
        params={"pageNumber": 1},
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
        },
    )

    assert response.status_code == 200
    assert response.json()["detail"]["pages"][0]["ocrBlocks"] == [
        {"text": "扫描文本", "x": 0.1, "y": 0.2, "width": 0.7, "height": 0.1}
    ]


def test_delete_asset_requires_owner_and_queues_cleanup(
    asset_client: TestClient, asset_db_session: Session
) -> None:
    owner = create_user(asset_db_session, email="owner@example.com", name="Owner")
    member = create_user(asset_db_session, email="member@example.com", name="Member")
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )
    asset_db_session.add(
        WorkspaceMembership(workspace_id=workspace.id, user_id=member.id, role="member")
    )
    asset_db_session.commit()
    asset = create_asset(asset_db_session, workspace=workspace, user=owner)
    create_pdf_content_unit(
        asset_db_session, asset=asset, page_number=1, text="Delete me."
    )
    asset_db_session.commit()

    forbidden = asset_client.delete(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": member.id,
        },
    )
    assert forbidden.status_code == 403

    deleted = asset_client.delete(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
        },
    )
    assert deleted.status_code == 202
    payload = deleted.json()
    assert payload["asset"]["status"] == "deleting"
    assert payload["job"]["jobType"] == "delete_cleanup"
    assert payload["job"]["status"] == "queued"

    refreshed = asset_db_session.get(Asset, asset.id)
    assert refreshed is not None
    assert refreshed.deleted_at is None
    assert refreshed.status == "deleting"
    assert asset_db_session.scalars(
        select(PdfPage).where(PdfPage.asset_id == asset.id)
    ).all()
    assert asset_db_session.scalars(
        select(ContentUnit).where(ContentUnit.asset_id == asset.id)
    ).all()

    list_response = asset_client.get(
        f"/v1/workspaces/{workspace.id}/assets",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
        },
    )
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["status"] == "deleting"


def test_delete_cleanup_worker_removes_asset_artifacts(
    asset_db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = create_user(
        asset_db_session, email="cleanup-owner@example.com", name="Owner"
    )
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )
    asset = create_asset(
        asset_db_session, workspace=workspace, user=owner, status="deleting"
    )
    create_pdf_content_unit(
        asset_db_session, asset=asset, page_number=1, text="Delete me."
    )
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="delete_cleanup",
        status="queued",
        attempt_count=1,
        config_snapshot={"source": "delete_asset"},
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    asset_db_session.add(job)
    asset_db_session.flush()
    asset.latest_ingestion_job_id = job.id
    asset_db_session.commit()
    deleted_objects: list[str] = []
    deleted_prefixes: list[str] = []
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.delete_object_if_exists",
        lambda object_key: deleted_objects.append(object_key),
    )
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.delete_objects_with_prefix",
        lambda prefix: deleted_prefixes.append(prefix),
    )

    claimed_job_id = claim_next_ingestion_job(asset_db_session)
    assert claimed_job_id == job.id
    process_ingestion_job(
        asset_db_session,
        claimed_job_id,
        ingestion_adapters=static_pdf_adapters(),
    )

    refreshed_asset = asset_db_session.get(Asset, asset.id)
    refreshed_job = asset_db_session.get(IngestionJob, job.id)
    assert refreshed_asset is not None
    assert refreshed_asset.status == "deleted"
    assert refreshed_asset.deleted_at is not None
    assert refreshed_job is not None
    assert refreshed_job.status == "succeeded"
    assert deleted_objects == [asset.object_key]
    assert deleted_prefixes == [f"workspaces/{workspace.id}/assets/{asset.id}/"]
    assert (
        asset_db_session.scalars(
            select(PdfPage).where(PdfPage.asset_id == asset.id)
        ).all()
        == []
    )
    assert (
        asset_db_session.scalars(
            select(ContentUnit).where(ContentUnit.asset_id == asset.id)
        ).all()
        == []
    )


def test_delete_cleanup_does_not_resurrect_deleted_asset(
    asset_db_session: Session,
) -> None:
    owner = create_user(
        asset_db_session, email="cleanup-deleted-owner@example.com", name="Owner"
    )
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )
    asset = create_asset(
        asset_db_session, workspace=workspace, user=owner, status="deleted"
    )
    asset.deleted_at = datetime.now(UTC)
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="delete_cleanup",
        status="queued",
        attempt_count=1,
        config_snapshot={"source": "delete_asset"},
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    asset_db_session.add(job)
    asset_db_session.flush()
    asset.latest_ingestion_job_id = job.id
    asset_db_session.commit()

    claimed_job_id = claim_next_ingestion_job(asset_db_session)

    assert claimed_job_id is None
    refreshed_asset = asset_db_session.get(Asset, asset.id)
    refreshed_job = asset_db_session.get(IngestionJob, job.id)
    assert refreshed_asset is not None
    assert refreshed_asset.status == "deleted"
    assert refreshed_asset.deleted_at is not None
    assert refreshed_job is not None
    assert refreshed_job.status == "cancelled"


def test_failed_delete_cleanup_can_be_retried(
    asset_client: TestClient, asset_db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = create_user(
        asset_db_session, email="cleanup-retry-owner@example.com", name="Owner"
    )
    member = create_user(
        asset_db_session, email="cleanup-retry-member@example.com", name="Member"
    )
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )
    asset_db_session.add(
        WorkspaceMembership(workspace_id=workspace.id, user_id=member.id, role="member")
    )
    asset_db_session.commit()
    asset = create_asset(
        asset_db_session, workspace=workspace, user=owner, status="deleting"
    )
    job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="delete_cleanup",
        status="queued",
        attempt_count=1,
        config_snapshot={"source": "delete_asset"},
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    asset_db_session.add(job)
    asset_db_session.flush()
    asset.latest_ingestion_job_id = job.id
    asset_db_session.commit()
    monkeypatch.setattr(
        "ai_pdf_api.services.ingestion.delete_object_if_exists",
        lambda _object_key: (_ for _ in ()).throw(RuntimeError("storage unavailable")),
    )

    claimed_job_id = claim_next_ingestion_job(asset_db_session)
    assert claimed_job_id == job.id
    process_ingestion_job(
        asset_db_session,
        claimed_job_id,
        ingestion_adapters=static_pdf_adapters(),
    )
    failed_job = asset_db_session.get(IngestionJob, job.id)
    assert failed_job is not None
    assert failed_job.status == "failed"

    forbidden = asset_client.post(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}/delete-retry",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": member.id,
        },
    )
    assert forbidden.status_code == 403

    response = asset_client.post(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}/delete-retry",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["asset"]["status"] == "deleting"
    assert payload["job"]["jobType"] == "delete_cleanup"
    assert payload["job"]["attemptCount"] == 2
    retried_job = asset_db_session.get(IngestionJob, payload["job"]["id"])
    assert retried_job is not None
    assert retried_job.config_snapshot == {"source": "retry_delete"}


def test_retry_failed_asset_creates_new_ingestion_job(
    asset_client: TestClient, asset_db_session: Session
) -> None:
    owner = create_user(asset_db_session, email="retry-owner@example.com", name="Owner")
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )
    asset = create_asset(
        asset_db_session, workspace=workspace, user=owner, status="failed"
    )
    failed_job = IngestionJob(
        workspace_id=workspace.id,
        asset_id=asset.id,
        job_type="ingest",
        status="failed",
        attempt_count=2,
        config_snapshot={"source": "initial"},
        error_code="ocr_failed",
        error_message="OCR provider failed.",
        requested_by_user_id=owner.id,
        queued_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    asset_db_session.add(failed_job)
    asset_db_session.flush()
    asset.latest_ingestion_job_id = failed_job.id
    asset_db_session.commit()

    response = asset_client.post(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}/retry",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["asset"]["status"] == "uploaded"
    assert payload["job"]["jobType"] == "ingest"
    assert payload["job"]["status"] == "queued"
    assert payload["job"]["attemptCount"] == 3
    retried_job = asset_db_session.get(IngestionJob, payload["job"]["id"])
    refreshed_asset = asset_db_session.get(Asset, asset.id)
    assert retried_job is not None
    assert retried_job.config_snapshot is not None
    assert retried_job.config_snapshot["source"] == "retry"
    assert retried_job.config_snapshot["embeddingProvider"] == settings.embedding_provider
    assert retried_job.config_snapshot["embeddingModel"] == settings.embedding_model
    assert retried_job.config_snapshot["embeddingDimensions"] == settings.embedding_dimensions
    assert retried_job.config_snapshot["embeddingVersion"] == settings.embedding_version
    assert retried_job.config_snapshot["chunkSize"] == workspace.chunk_size
    assert isinstance(retried_job.config_snapshot["embeddingProfileFingerprint"], str)
    assert len(retried_job.config_snapshot["embeddingProfileFingerprint"]) == 64
    assert refreshed_asset is not None
    assert refreshed_asset.latest_ingestion_job_id == retried_job.id
    assert refreshed_asset.last_error_code is None
    assert refreshed_asset.last_error_message is None


def test_retry_asset_rejects_a_asset_that_is_not_failed(
    asset_client: TestClient, asset_db_session: Session
) -> None:
    owner = create_user(
        asset_db_session, email="retry-ready-owner@example.com", name="Owner"
    )
    workspace = create_workspace_with_membership(
        asset_db_session, user=owner, name="Docs"
    )
    asset = create_asset(
        asset_db_session, workspace=workspace, user=owner, status="ready"
    )

    response = asset_client.post(
        f"/v1/workspaces/{workspace.id}/assets/{asset.id}/retry",
        headers={
            "x-ai-pdf-internal-token": settings.api_internal_token,
            "x-user-id": owner.id,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Only failed assets can be retried."


def test_split_page_text_honors_workspace_chunk_size() -> None:
    chunks = split_page_text("word " * 300, chunk_size=200)

    assert len(chunks) > 1
    assert all(len(chunk_text) <= 200 for _start, _end, chunk_text in chunks)
