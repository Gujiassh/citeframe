"""Exercise the production Image path through real API and Worker boundaries.

The script uses only the checked-in synthetic image fixture and a local
deterministic provider. Its report proves plumbing and Evidence persistence,
not model quality.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4

import ai_pdf_worker.main as worker_main
from ai_pdf_api.core.settings import settings
from ai_pdf_api.db.session import SessionLocal
from ai_pdf_api.modalities.ingestion import IngestionAdapterRegistry, IngestionError
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    AssetTag,
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
    SpatialLocatorRegion,
    Tag,
    User,
    Workspace,
    WorkspaceMembership,
)
from ai_pdf_api.services.providers import get_embedding_provider
from ai_pdf_api.services.retrieval import retrieve_query_content
from ai_pdf_api.services.storage import delete_objects_with_prefix
from ai_pdf_worker.main import process_one_job
from PIL import Image
from sqlalchemy import delete, select

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPOSITORY_ROOT / "docs/fixtures/evidence-contract/image-coordinate-fixture.png"
API_BASE = "http://127.0.0.1:8000"


def _transcode_fixture(source: bytes, image_format: str) -> bytes:
    with Image.open(BytesIO(source)) as image:
        output = BytesIO()
        image.convert("RGB").save(output, format=image_format)
        return output.getvalue()


def _request(
    method: str,
    path: str,
    *,
    user_id: str,
    body: bytes | None = None,
    content_type: str | None = None,
    allow_error: bool = False,
) -> tuple[int, dict | None, bytes]:
    headers = {
        "x-user-id": user_id,
        "x-ai-pdf-internal-token": settings.api_internal_token,
    }
    if content_type:
        headers["content-type"] = content_type
    request = Request(f"{API_BASE}{path}", data=body, method=method, headers=headers)
    try:
        with urlopen(request, timeout=60) as response:
            payload = response.read()
            return response.status, _decode_json(payload), payload
    except HTTPError as error:
        response = error.code
        payload = error.read()
        if allow_error:
            return response, _decode_json(payload), payload
        raise RuntimeError(f"{method} {path} failed status={response} body={payload[:500]!r}") from error


def _decode_json(payload: bytes) -> dict | None:
    if not payload:
        return None
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _seed_identity() -> tuple[str, str]:
    user_id = str(uuid4())
    workspace_id = str(uuid4())
    now = datetime.now(UTC)
    with SessionLocal() as db:
        db.add(
            User(
                id=user_id,
                email=f"m403b-{user_id}@example.invalid",
                name="M403B Acceptance",
                password_hash="m403b-acceptance-only",
                avatar_url="https://example.invalid/avatar.png",
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            Workspace(
                id=workspace_id,
                name="M403B acceptance",
                description="Synthetic production Image acceptance workspace",
                created_by_user_id=user_id,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            WorkspaceMembership(
                id=str(uuid4()),
                workspace_id=workspace_id,
                user_id=user_id,
                role="owner",
                created_at=now,
            )
        )
        db.commit()
    return user_id, workspace_id


def _cleanup_identity(user_id: str, workspace_id: str) -> None:
    delete_objects_with_prefix(f"workspaces/{workspace_id}/")
    with SessionLocal() as db:
        message_ids = select(ChatMessage.id).where(ChatMessage.workspace_id == workspace_id)
        locator_ids = select(EvidenceLocator.id).where(EvidenceLocator.workspace_id == workspace_id)
        db.execute(delete(MessageRetrievalScopeAsset).where(MessageRetrievalScopeAsset.message_id.in_(message_ids)))
        for model in (
            MessageCitation,
            MessageInputEvidence,
            NoteSource,
            MessageRetrievalScope,
            ChatMessage,
            ChatThread,
            Note,
            ContentUnitEmbedding,
            ContentUnit,
        ):
            db.execute(delete(model).where(model.workspace_id == workspace_id))
        db.execute(delete(SpatialLocatorRegion).where(SpatialLocatorRegion.locator_id.in_(locator_ids)))
        db.execute(delete(ImageLocatorDetail).where(ImageLocatorDetail.locator_id.in_(locator_ids)))
        db.execute(delete(EvidenceLocator).where(EvidenceLocator.workspace_id == workspace_id))
        for model in (
            ImageRepresentationGeometry,
            AssetRepresentation,
            IngestionJob,
            AssetTag,
            Asset,
            Tag,
            WorkspaceMembership,
        ):
            db.execute(delete(model).where(model.workspace_id == workspace_id))
        db.execute(delete(Workspace).where(Workspace.id == workspace_id))
        db.execute(delete(User).where(User.id == user_id))
        db.commit()


class _FailOnceImageAdapter:
    asset_kind = "image"

    def __init__(self, delegate: object) -> None:
        self._delegate = delegate
        self._failed = False

    def ingest(self, *args: object, **kwargs: object) -> object:
        if not self._failed:
            self._failed = True
            raise IngestionError("m403b_transient_failure", "Deterministic transient Image failure.")
        return self._delegate.ingest(*args, **kwargs)  # type: ignore[attr-defined]

    def cleanup(self, *args: object, **kwargs: object) -> None:
        self._delegate.cleanup(*args, **kwargs)  # type: ignore[attr-defined]


def _process_one_job(expected_status: str = "ready", *, fail_image_once: bool = False) -> dict:
    previous_adapters = worker_main.INGESTION_ADAPTERS
    if fail_image_once:
        worker_main.INGESTION_ADAPTERS = IngestionAdapterRegistry(
            (
                previous_adapters.get("pdf"),
                _FailOnceImageAdapter(previous_adapters.get("image")),
            )
        )
    try:
        if not process_one_job():
            raise RuntimeError("Worker did not claim the finalized Image ingest job")
    finally:
        if fail_image_once:
            worker_main.INGESTION_ADAPTERS = previous_adapters
    return {"workerClaimed": True, "expectedStatus": expected_status}


def _exercise_image_format(
    *,
    user_id: str,
    workspace_id: str,
    source_filename: str,
    mime_type: str,
    payload: bytes,
) -> dict[str, object]:
    status, session, _ = _request(
        "POST",
        f"/v1/workspaces/{workspace_id}/assets/upload-session",
        user_id=user_id,
        body=json.dumps(
            {
                "sourceFilename": source_filename,
                "mimeType": mime_type,
                "byteSize": len(payload),
            }
        ).encode(),
        content_type="application/json",
    )
    if status != 201 or session is None:
        raise RuntimeError(f"unexpected {mime_type} upload-session response: {status}")
    asset_id = str(session["asset"]["id"])
    object_key = str(session["upload"]["objectKey"])
    status, _, _ = _request(
        "PUT",
        f"/v1/workspaces/{workspace_id}/assets/{asset_id}/upload?objectKey={quote(object_key)}",
        user_id=user_id,
        body=payload,
        content_type=mime_type,
    )
    if status != 204:
        raise RuntimeError(f"unexpected {mime_type} upload response: {status}")
    status, finalized, _ = _request(
        "POST",
        f"/v1/workspaces/{workspace_id}/assets/{asset_id}/finalize-upload",
        user_id=user_id,
        body=json.dumps({"objectKey": object_key}).encode(),
        content_type="application/json",
    )
    if status != 200 or finalized is None:
        raise RuntimeError(f"unexpected {mime_type} finalize response: {status}")
    _process_one_job()
    with SessionLocal() as db:
        asset = db.get(Asset, asset_id)
        oriented = db.scalar(
            select(AssetRepresentation).where(
                AssetRepresentation.asset_id == asset_id,
                AssetRepresentation.representation_kind == "image_oriented",
                AssetRepresentation.processing_generation == asset.current_processing_generation,
            )
        ) if asset else None
        representation_count = db.query(AssetRepresentation).filter(AssetRepresentation.asset_id == asset_id).count()
        content_unit_count = db.query(ContentUnit).filter(ContentUnit.asset_id == asset_id).count()
        if (
            asset is None
            or asset.status != "ready"
            or asset.mime_type != mime_type
            or asset.source_sha256 != sha256(payload).hexdigest()
            or oriented is None
            or not oriented.object_key
            or representation_count < 2
            or content_unit_count < 1
        ):
            raise RuntimeError(f"{mime_type} production ingest did not become ready")
        oriented_key = oriented.object_key

    delete_status, deleted, _ = _request(
        "DELETE",
        f"/v1/workspaces/{workspace_id}/assets/{asset_id}",
        user_id=user_id,
    )
    if delete_status != 202 or deleted is None:
        raise RuntimeError(f"unexpected {mime_type} delete response: {delete_status}")
    _process_one_job(expected_status="deleted")
    with SessionLocal() as db:
        deleted_asset = db.get(Asset, asset_id)
        deleted_job = db.get(IngestionJob, deleted_asset.latest_ingestion_job_id) if deleted_asset else None
        if (
            deleted_asset is None
            or deleted_asset.status != "deleted"
            or deleted_asset.deleted_at is None
            or deleted_job is None
            or deleted_job.status != "succeeded"
        ):
            raise RuntimeError(f"{mime_type} delete did not reach its terminal state")
    source_exists = _object_exists(object_key)
    oriented_exists = _object_exists(oriented_key)
    if source_exists or oriented_exists:
        raise RuntimeError(f"{mime_type} objects survived delete cleanup")
    return {
        "sessionStatus": 201,
        "putStatus": 204,
        "finalizeStatus": 200,
        "assetStatus": "ready",
        "representations": representation_count,
        "contentUnits": content_unit_count,
        "deleteStatus": delete_status,
        "deleteJobStatus": "succeeded",
        "sourceObjectExistsAfterDelete": source_exists,
        "orientedObjectExistsAfterDelete": oriented_exists,
    }


def run(output: Path) -> None:
    source = FIXTURE.read_bytes()
    source_sha = sha256(source).hexdigest()
    user_id, workspace_id = _seed_identity()
    asset_id = ""
    object_key = ""
    oriented_key = ""
    retry_oriented_key = ""
    format_coverage: dict[str, dict[str, object]] = {}
    report: dict[str, object] = {
        "schemaVersion": "m403b-production-acceptance-v1",
        "provider": "local-deterministic-stub",
        "modelQualityClaim": False,
        "source": str(FIXTURE.relative_to(REPOSITORY_ROOT)),
        "sourceSha256": source_sha,
        "formatCoverage": format_coverage,
    }
    try:
        mismatch_source = {
            "sourceFilename": "m403b-mime-mismatch.png",
            "mimeType": "image/png",
            "byteSize": len(source),
        }
        status, mismatch_session, _ = _request(
            "POST",
            f"/v1/workspaces/{workspace_id}/assets/upload-session",
            user_id=user_id,
            body=json.dumps(mismatch_source).encode(),
            content_type="application/json",
        )
        if status != 201 or mismatch_session is None:
            raise RuntimeError(f"unexpected MIME mismatch upload-session response: {status}")
        mismatch_asset_id = str(mismatch_session["asset"]["id"])
        mismatch_object_key = str(mismatch_session["upload"]["objectKey"])
        status, mismatch_error, _ = _request(
            "PUT",
            f"/v1/workspaces/{workspace_id}/assets/{mismatch_asset_id}/upload?objectKey={quote(mismatch_object_key)}",
            user_id=user_id,
            body=source,
            content_type="image/jpeg",
            allow_error=True,
        )
        if status != 422 or not mismatch_error or "Content-Type" not in str(mismatch_error.get("detail", "")):
            raise RuntimeError(f"MIME mismatch was not rejected: status={status} detail={mismatch_error}")
        report["mimeMismatch"] = {
            "sessionStatus": 201,
            "putStatus": status,
            "errorDetail": mismatch_error["detail"],
        }

        retry_source = {
            "sourceFilename": "m403b-retry.png",
            "mimeType": "image/png",
            "byteSize": len(source),
        }
        status, retry_session, _ = _request(
            "POST",
            f"/v1/workspaces/{workspace_id}/assets/upload-session",
            user_id=user_id,
            body=json.dumps(retry_source).encode(),
            content_type="application/json",
        )
        if status != 201 or retry_session is None:
            raise RuntimeError(f"unexpected retry upload-session response: {status}")
        retry_asset_id = str(retry_session["asset"]["id"])
        retry_object_key = str(retry_session["upload"]["objectKey"])
        status, _, _ = _request(
            "PUT",
            f"/v1/workspaces/{workspace_id}/assets/{retry_asset_id}/upload?objectKey={quote(retry_object_key)}",
            user_id=user_id,
            body=source,
            content_type="image/png",
        )
        if status != 204:
            raise RuntimeError(f"unexpected corrupt upload response: {status}")
        status, retry_finalized, _ = _request(
            "POST",
            f"/v1/workspaces/{workspace_id}/assets/{retry_asset_id}/finalize-upload",
            user_id=user_id,
            body=json.dumps({"objectKey": retry_object_key}).encode(),
            content_type="application/json",
        )
        if status != 200 or retry_finalized is None:
            raise RuntimeError(f"unexpected retry finalize response: {status}")
        _process_one_job(fail_image_once=True)
        with SessionLocal() as db:
            failed_asset = db.get(Asset, retry_asset_id)
            failed_job = db.get(IngestionJob, failed_asset.latest_ingestion_job_id) if failed_asset else None
            if failed_asset is None or failed_asset.status != "failed" or failed_job is None:
                raise RuntimeError(f"corrupt Image did not fail closed: asset={failed_asset} job={failed_job}")
            failure_state = {
                "assetStatus": failed_asset.status,
                "errorCode": failed_asset.last_error_code,
                "errorMessage": failed_asset.last_error_message,
                "attemptCount": failed_job.attempt_count,
            }
            if failed_asset.byte_size != len(source) or failed_asset.source_sha256 != source_sha:
                raise RuntimeError("Transient failure changed the immutable source identity")
            db.commit()

        status, retry_response, _ = _request(
            "POST",
            f"/v1/workspaces/{workspace_id}/assets/{retry_asset_id}/retry",
            user_id=user_id,
            content_type="application/json",
        )
        if status != 200 or retry_response is None:
            raise RuntimeError(f"unexpected retry response: {status}")
        _process_one_job()
        with SessionLocal() as db:
            retried_asset = db.get(Asset, retry_asset_id)
            retried_job = db.get(IngestionJob, retried_asset.latest_ingestion_job_id) if retried_asset else None
            if retried_asset is None or retried_asset.status != "ready" or retried_job is None:
                raise RuntimeError(f"Image retry did not become ready: asset={retried_asset} job={retried_job}")
            retry_oriented = db.scalar(
                select(AssetRepresentation).where(
                    AssetRepresentation.asset_id == retry_asset_id,
                    AssetRepresentation.representation_kind == "image_oriented",
                    AssetRepresentation.processing_generation == retried_asset.current_processing_generation,
                )
            )
            if retry_oriented is None or not retry_oriented.object_key:
                raise RuntimeError("Retried Image oriented representation is missing")
            retry_oriented_key = retry_oriented.object_key
            report["failureRetry"] = {
                "failure": failure_state,
                "retryStatus": status,
                "retryAssetStatus": retried_asset.status,
                "retryAttemptCount": retried_job.attempt_count,
                "retryJobStatus": retried_job.status,
                "sourceIdentityPreserved": True,
            }

        format_coverage["image/jpeg"] = _exercise_image_format(
            user_id=user_id,
            workspace_id=workspace_id,
            source_filename="m403b-format.jpg",
            mime_type="image/jpeg",
            payload=_transcode_fixture(source, "JPEG"),
        )
        format_coverage["image/webp"] = _exercise_image_format(
            user_id=user_id,
            workspace_id=workspace_id,
            source_filename="m403b-format.webp",
            mime_type="image/webp",
            payload=_transcode_fixture(source, "WEBP"),
        )

        status, session, _ = _request(
            "POST",
            f"/v1/workspaces/{workspace_id}/assets/upload-session",
            user_id=user_id,
            body=json.dumps(
                {
                    "sourceFilename": "m403b-image.png",
                    "mimeType": "image/png",
                    "byteSize": len(source),
                }
            ).encode(),
            content_type="application/json",
        )
        if status != 201 or session is None:
            raise RuntimeError(f"unexpected upload-session response: {status}")
        asset_id = str(session["asset"]["id"])
        object_key = str(session["upload"]["objectKey"])
        status, _, _ = _request(
            "PUT",
            f"/v1/workspaces/{workspace_id}/assets/{asset_id}/upload?objectKey={quote(object_key)}",
            user_id=user_id,
            body=source,
            content_type="image/png",
        )
        if status != 204:
            raise RuntimeError(f"unexpected binary upload response: {status}")
        status, finalized, _ = _request(
            "POST",
            f"/v1/workspaces/{workspace_id}/assets/{asset_id}/finalize-upload",
            user_id=user_id,
            body=json.dumps({"objectKey": object_key}).encode(),
            content_type="application/json",
        )
        if status != 200 or finalized is None:
            raise RuntimeError(f"unexpected finalize response: {status}")
        report["upload"] = {
            "sessionStatus": 201,
            "putStatus": 204,
            "finalizeStatus": status,
            "assetKind": finalized["asset"]["kind"],
            "mimeType": finalized["asset"]["mimeType"],
            "title": finalized["asset"]["title"],
        }

        report["worker"] = _process_one_job()
        with SessionLocal() as db:
            asset = db.get(Asset, asset_id)
            if asset is None or asset.status != "ready":
                raise RuntimeError(f"Image ingest did not become ready: {asset}")
            format_coverage["image/png"] = {
                "sessionStatus": 201,
                "putStatus": 204,
                "finalizeStatus": 200,
                "assetStatus": asset.status,
            }
            oriented_key = f"{asset.object_key.rsplit('/source/', 1)[0]}/representations/{asset.current_processing_generation}/image_oriented"
            provider = get_embedding_provider()
            retrieved = retrieve_query_content(
                db,
                workspace_id,
                "Synthetic production image caption for M403B acceptance.",
                provider.embed_query("Synthetic production image caption for M403B acceptance."),
                asset_ids=[asset_id],
                embedding_provider=provider,
                limit=6,
                strategy="hybrid",
            )
            report["retrieval"] = {
                "count": len(retrieved),
                "assetIds": sorted({item.asset.id for item in retrieved}),
                "locatorKinds": sorted({item.locator.locator_kind for item in retrieved}),
            }
            if not retrieved:
                raise RuntimeError("production Image retrieval returned no ContentUnit")
            report["worker"]["contentUnits"] = db.query(ContentUnit).filter(ContentUnit.asset_id == asset_id).count()
            report["worker"]["representations"] = db.query(AssetRepresentation).filter(AssetRepresentation.asset_id == asset_id).count()
            generation = asset.current_processing_generation

        status, detail, _ = _request(
            "GET",
            f"/v1/workspaces/{workspace_id}/assets/{asset_id}",
            user_id=user_id,
        )
        if status != 200 or detail is None:
            raise RuntimeError(f"unexpected asset detail response: {status}")
        image_detail = detail["detail"]
        status, _, oriented_bytes = _request(
            "GET",
            f"/v1/workspaces/{workspace_id}/assets/{asset_id}/representations/current-image-oriented/file?processingGeneration={generation}",
            user_id=user_id,
        )
        if status != 200 or not oriented_bytes.startswith(b"\x89PNG"):
            raise RuntimeError(f"unexpected oriented image response: {status}")
        report["evidenceViewer"] = {
            "detailStatus": 200,
            "orientedStatus": status,
            "orientedMime": "image/png",
            "orientedSha256": sha256(oriented_bytes).hexdigest(),
            "naturalSize": [image_detail["widthPixels"], image_detail["heightPixels"]],
            "orientationApplied": image_detail["orientationApplied"],
            "generation": generation,
        }

        status, thread, _ = _request(
            "POST",
            f"/v1/workspaces/{workspace_id}/threads",
            user_id=user_id,
            body=json.dumps({"title": "M403B evidence thread"}).encode(),
            content_type="application/json",
        )
        if status != 201 or thread is None:
            raise RuntimeError(f"unexpected thread response: {status}")
        thread_id = str(thread["thread"]["id"])
        chat_body = {
            "threadId": thread_id,
            "question": "What is visible in this image?",
            "assetScope": {"mode": "selected", "assetIds": [asset_id]},
            "evidenceTargets": [
                {
                    "kind": "image_region",
                    "assetId": asset_id,
                    "processingGeneration": generation,
                    "coordinateSpace": "image_normalized_top_left_v1",
                    "regions": [{"x": 0.1, "y": 0.1, "width": 0.6, "height": 0.6}],
                }
            ],
        }
        status, _, stream = _request(
            "POST",
            f"/v1/workspaces/{workspace_id}/chat/stream",
            user_id=user_id,
            body=json.dumps(chat_body).encode(),
            content_type="application/json",
        )
        stream_text = stream.decode("utf-8", errors="replace")
        if status != 200 or "event: citations" not in stream_text or "event: done" not in stream_text:
            raise RuntimeError(f"chat Evidence stream did not complete: status={status}")
        with SessionLocal() as db:
            messages = db.query(ChatMessage).filter(ChatMessage.thread_id == thread_id).all()
            user_message = next(message for message in messages if message.role == "user")
            assistant_message = next(message for message in messages if message.role == "assistant")
            input_evidence = db.query(MessageInputEvidence).filter(MessageInputEvidence.message_id == user_message.id).count()
            citations = db.query(MessageCitation).filter(MessageCitation.message_id == assistant_message.id).count()
            report["evidence"] = {
                "chatStatus": status,
                "streamHasCitations": True,
                "streamHasDone": True,
                "inputEvidenceRows": input_evidence,
                "citationRows": citations,
                "assistantStatus": assistant_message.status,
            }
            if input_evidence != 1 or citations < 1 or assistant_message.status != "completed":
                raise RuntimeError("Evidence target was not persisted through Chat")

        status, deleted, _ = _request(
            "DELETE",
            f"/v1/workspaces/{workspace_id}/assets/{asset_id}",
            user_id=user_id,
        )
        if status != 202 or deleted is None:
            raise RuntimeError(f"unexpected delete response: {status}")
        _process_one_job(expected_status="deleted")
        with SessionLocal() as db:
            deleted_asset = db.get(Asset, asset_id)
            deleted_job = db.get(IngestionJob, deleted_asset.latest_ingestion_job_id) if deleted_asset else None
            cleanup_content_units = db.query(ContentUnit).filter(ContentUnit.asset_id == asset_id).count()
            cleanup_embeddings = db.query(ContentUnitEmbedding).filter(ContentUnitEmbedding.asset_id == asset_id).count()
            cleanup_geometry = db.query(ImageRepresentationGeometry).filter(ImageRepresentationGeometry.asset_id == asset_id).count()
            if (
                deleted_asset is None
                or deleted_asset.status != "deleted"
                or deleted_asset.deleted_at is None
                or deleted_job is None
                or deleted_job.status != "succeeded"
                or cleanup_content_units != 0
                or cleanup_embeddings != 0
                or cleanup_geometry != 0
            ):
                raise RuntimeError(
                    "Ready Image delete did not complete: "
                    f"asset={deleted_asset} job={deleted_job} "
                    f"contentUnits={cleanup_content_units} embeddings={cleanup_embeddings} geometry={cleanup_geometry}"
                )
            report["cleanup"] = {
                "deleteStatus": status,
                "assetStatus": deleted_asset.status,
                "deletedAtPresent": deleted_asset.deleted_at is not None,
                "deleteJobStatus": deleted_job.status,
                "contentUnitsRemaining": cleanup_content_units,
                "embeddingsRemaining": cleanup_embeddings,
                "geometryRemaining": cleanup_geometry,
                "sourceObjectExists": _object_exists(object_key),
                "orientedObjectExists": _object_exists(oriented_key),
            }
        if report["cleanup"]["sourceObjectExists"] or report["cleanup"]["orientedObjectExists"]:
            raise RuntimeError("Image source or oriented object survived delete cleanup")
        retry_delete_status, retry_deleted, _ = _request(
            "DELETE",
            f"/v1/workspaces/{workspace_id}/assets/{retry_asset_id}",
            user_id=user_id,
        )
        if retry_delete_status != 202 or retry_deleted is None:
            raise RuntimeError(f"unexpected retry asset delete response: {retry_delete_status}")
        _process_one_job(expected_status="deleted")
        with SessionLocal() as db:
            retry_deleted_asset = db.get(Asset, retry_asset_id)
            retry_deleted_job = db.get(IngestionJob, retry_deleted_asset.latest_ingestion_job_id) if retry_deleted_asset else None
            retry_cleanup_content_units = db.query(ContentUnit).filter(ContentUnit.asset_id == retry_asset_id).count()
            retry_cleanup_embeddings = db.query(ContentUnitEmbedding).filter(ContentUnitEmbedding.asset_id == retry_asset_id).count()
            retry_cleanup_geometry = db.query(ImageRepresentationGeometry).filter(ImageRepresentationGeometry.asset_id == retry_asset_id).count()
            if (
                retry_deleted_asset is None
                or retry_deleted_asset.status != "deleted"
                or retry_deleted_asset.deleted_at is None
                or retry_deleted_job is None
                or retry_deleted_job.status != "succeeded"
                or retry_cleanup_content_units != 0
                or retry_cleanup_embeddings != 0
                or retry_cleanup_geometry != 0
            ):
                raise RuntimeError(
                    "Retried Image delete did not complete: "
                    f"asset={retry_deleted_asset} job={retry_deleted_job} "
                    f"contentUnits={retry_cleanup_content_units} embeddings={retry_cleanup_embeddings} geometry={retry_cleanup_geometry}"
                )
            report["failureRetry"]["cleanup"] = {
                "deleteStatus": retry_delete_status,
                "assetStatus": retry_deleted_asset.status,
                "deletedAtPresent": retry_deleted_asset.deleted_at is not None,
                "deleteJobStatus": retry_deleted_job.status,
                "contentUnitsRemaining": retry_cleanup_content_units,
                "embeddingsRemaining": retry_cleanup_embeddings,
                "geometryRemaining": retry_cleanup_geometry,
                "sourceObjectExists": _object_exists(retry_object_key),
                "orientedObjectExists": _object_exists(retry_oriented_key),
            }
        if report["failureRetry"]["cleanup"]["sourceObjectExists"] or report["failureRetry"]["cleanup"]["orientedObjectExists"]:
            raise RuntimeError("Retried Image source or oriented object survived delete cleanup")
        report["releaseGatePassed"] = True
    finally:
        _cleanup_identity(user_id, workspace_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


def _object_exists(object_key: str) -> bool:
    if not object_key:
        return False
    from ai_pdf_api.services.storage import object_exists

    return object_exists(object_key)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.output)
