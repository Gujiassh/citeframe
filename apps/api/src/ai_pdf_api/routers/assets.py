from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from tempfile import SpooledTemporaryFile
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ai_pdf_api.core.settings import settings
from ai_pdf_api.services.capabilities import embedding_profile_snapshot_fields
from ai_pdf_api.services.embedding_index import embedding_index_job_snapshot_fields
from ai_pdf_api.db.session import get_db
from ai_pdf_api.modalities.document import (
    DocumentIntegrityError,
    validate_document_normalized_bundle,
)
from ai_pdf_api.modalities.registry import ModalityContractError, build_production_registry
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ContentUnit,
    DocumentBlock,
    DocumentNormalizedContent,
    ImageRepresentationGeometry,
    IngestionJob,
    PdfPage,
    User,
)
from ai_pdf_api.routers.deps import get_accessible_workspace, require_existing_user, require_user_id
from ai_pdf_api.schemas.asset import (
    CreateUploadSessionRequest,
    CreateUploadSessionResponse,
    AssetDetailResponse,
    AssetListResponse,
    DocumentAssetDetail,
    DocumentHeadingSummary,
    DocumentNormalizedBlock,
    DocumentNormalizedContentResponse,
    PdfPageContent,
    PdfPageOcrBlock,
    AssetSummary,
    FinalizeUploadRequest,
    FinalizeUploadResponse,
    UploadDescriptor,
    ImageAssetDetail,
    PdfAssetDetail,
)
from ai_pdf_api.schemas.job import JobStatus
from ai_pdf_api.services.storage import download_bytes, object_exists, stream_bytes, upload_stream

router = APIRouter(prefix="/v1/workspaces/{workspace_id}/assets", tags=["assets"])
modality_registry = build_production_registry()


def to_asset_summary(asset: Asset) -> AssetSummary:
    return AssetSummary(
        id=asset.id,
        workspaceId=asset.workspace_id,
        kind=asset.asset_kind,
        title=asset.title,
        sourceFilename=asset.source_filename,
        mimeType=asset.mime_type,
        byteSize=asset.byte_size,
        status=asset.status,
        currentProcessingGeneration=asset.current_processing_generation,
        currentIndexVersion=asset.current_index_version,
        lastErrorCode=asset.last_error_code,
        lastErrorMessage=asset.last_error_message,
        createdAt=asset.created_at.astimezone(UTC).isoformat(),
        updatedAt=asset.updated_at.astimezone(UTC).isoformat(),
    )


def to_job_status(job: IngestionJob) -> JobStatus:
    return JobStatus(
        id=job.id,
        workspaceId=job.workspace_id,
        assetId=job.asset_id,
        jobType=job.job_type,
        status=job.status,
        attemptCount=job.attempt_count,
        queuedAt=job.queued_at.astimezone(UTC).isoformat(),
        startedAt=job.started_at.astimezone(UTC).isoformat() if job.started_at else None,
        finishedAt=job.finished_at.astimezone(UTC).isoformat() if job.finished_at else None,
        errorCode=job.error_code,
        errorMessage=job.error_message,
    )


def get_workspace_asset(
    db: Session,
    workspace_id: str,
    asset_id: str,
    *,
    allow_deleting: bool = False,
) -> Asset:
    asset = db.scalar(
        select(Asset).where(
            Asset.id == asset_id,
            Asset.workspace_id == workspace_id,
            Asset.deleted_at.is_(None),
        ),
    )
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found.",
        )
    if asset.status in {"deleting", "deleted"} and not allow_deleting:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asset is being deleted.")
    return asset


def validate_image_representation_geometry(
    geometry: ImageRepresentationGeometry,
    *,
    workspace_id: str,
    asset_id: str,
) -> None:
    if (
        geometry.workspace_id != workspace_id
        or geometry.asset_id != asset_id
        or geometry.width_pixels <= 0
        or geometry.height_pixels <= 0
        or not geometry.orientation_applied
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Oriented image representation geometry is invalid.",
        )


def build_object_key(workspace_id: str, asset_id: str, source_filename: str) -> str:
    suffix = Path(source_filename).suffix.lower() or ".pdf"
    return f"workspaces/{workspace_id}/assets/{asset_id}/original{suffix}"


def build_ingest_job(
    *,
    workspace_id: str,
    asset_id: str,
    asset_kind: str,
    user_id: str,
    chunk_size: int,
    source: str,
    now: datetime,
    attempt_count: int = 1,
) -> IngestionJob:
    config_snapshot: dict[str, object] = {
        "source": source,
        "chunkSize": chunk_size,
        **embedding_profile_snapshot_fields(),
    }
    config_snapshot.update(modality_registry.ingestion_config_snapshot(asset_kind))
    return IngestionJob(
        workspace_id=workspace_id,
        asset_id=asset_id,
        job_type="ingest",
        status="queued",
        attempt_count=attempt_count,
        config_snapshot=config_snapshot,
        requested_by_user_id=user_id,
        queued_at=now,
        created_at=now,
    )


def build_delete_cleanup_job(
    *,
    workspace_id: str,
    asset_id: str,
    user_id: str,
    source: str,
    now: datetime,
    attempt_count: int = 1,
) -> IngestionJob:
    return IngestionJob(
        workspace_id=workspace_id,
        asset_id=asset_id,
        job_type="delete_cleanup",
        status="queued",
        attempt_count=attempt_count,
        config_snapshot={"source": source},
        requested_by_user_id=user_id,
        queued_at=now,
        created_at=now,
    )


@router.get("", response_model=AssetListResponse)
def list_assets(
    workspace_id: str,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> AssetListResponse:
    get_accessible_workspace(db, user_id, workspace_id)
    items = db.scalars(
        select(Asset)
        .where(Asset.workspace_id == workspace_id, Asset.deleted_at.is_(None))
        .order_by(Asset.created_at.desc())
    ).all()
    return AssetListResponse(items=[to_asset_summary(asset) for asset in items], nextCursor=None)


@router.get("/{asset_id}", response_model=AssetDetailResponse)
def get_asset_detail(
    workspace_id: str,
    asset_id: str,
    page_number: int = Query(1, alias="pageNumber", ge=1),
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> AssetDetailResponse:
    get_accessible_workspace(db, user_id, workspace_id)
    asset = get_workspace_asset(db, workspace_id, asset_id)
    if asset.asset_kind == "image":
        geometry = db.scalar(
            select(ImageRepresentationGeometry)
            .join(
                AssetRepresentation,
                AssetRepresentation.id == ImageRepresentationGeometry.representation_id,
            )
            .where(
                ImageRepresentationGeometry.asset_id == asset.id,
                ImageRepresentationGeometry.workspace_id == workspace_id,
                AssetRepresentation.asset_id == asset.id,
                AssetRepresentation.workspace_id == workspace_id,
                AssetRepresentation.representation_kind == "image_oriented",
                AssetRepresentation.processing_generation
                == asset.current_processing_generation,
            )
        )
        if geometry is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset detail not found.")
        validate_image_representation_geometry(
            geometry,
            workspace_id=workspace_id,
            asset_id=asset.id,
        )
        return AssetDetailResponse(
            asset=to_asset_summary(asset),
            detail=ImageAssetDetail(
                widthPixels=geometry.width_pixels,
                heightPixels=geometry.height_pixels,
                orientationApplied=geometry.orientation_applied,
            ),
        )
    if asset.asset_kind == "document":
        representation = db.scalar(
            select(AssetRepresentation).where(
                AssetRepresentation.asset_id == asset.id,
                AssetRepresentation.workspace_id == workspace_id,
                AssetRepresentation.representation_kind == "document_normalized",
                AssetRepresentation.processing_generation
                == asset.current_processing_generation,
            )
        )
        if representation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Asset detail not found."
            )
        normalized = db.get(DocumentNormalizedContent, representation.id)
        if normalized is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Asset detail not found."
            )
        heading_blocks = db.scalars(
            select(DocumentBlock)
            .where(
                DocumentBlock.representation_id == representation.id,
                DocumentBlock.block_kind == "heading",
            )
            .order_by(DocumentBlock.block_order)
        ).all()
        headings: list[DocumentHeadingSummary] = []
        for block in heading_blocks:
            if block.heading_level is None or not (1 <= block.heading_level <= 6):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Document heading level is invalid.",
                )
            headings.append(
                DocumentHeadingSummary(
                    blockId=block.block_id,
                    level=block.heading_level,
                    text=block.text_content,
                    order=block.block_order,
                )
            )
        return AssetDetailResponse(
            asset=to_asset_summary(asset),
            detail=DocumentAssetDetail(
                format="markdown",
                parserVersion=normalized.parser_version,  # type: ignore[arg-type]
                normalizationVersion=normalized.normalization_version,  # type: ignore[arg-type]
                representationId=representation.id,
                blockCount=normalized.block_count,
                headings=headings,
            ),
        )
    representation = db.scalar(
        select(AssetRepresentation)
        .where(
            AssetRepresentation.asset_id == asset.id,
            AssetRepresentation.workspace_id == workspace_id,
            AssetRepresentation.processing_generation == asset.current_processing_generation,
            AssetRepresentation.representation_kind.in_(("pdf_page_layout", "pdf_text_legacy")),
        )
        .order_by(
            case((AssetRepresentation.representation_kind == "pdf_page_layout", 0), else_=1),
            AssetRepresentation.id,
        )
    )
    if representation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset detail not found.")
    page = db.scalar(
        select(PdfPage)
        .where(
            PdfPage.asset_id == asset.id,
            PdfPage.representation_id == representation.id,
            PdfPage.page_number == page_number,
        ),
    )
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset page not found.")
    return AssetDetailResponse(
        asset=to_asset_summary(asset),
        detail=PdfAssetDetail(
            pageCount=db.scalar(
                select(func.count(PdfPage.id)).where(
                    PdfPage.asset_id == asset.id,
                    PdfPage.representation_id == representation.id,
                )
            ) or 0,
            pages=[
                PdfPageContent(
                    pageNumber=page.page_number,
                    text=page.extracted_text,
                    charCount=page.char_count,
                    ocrBlocks=[
                        PdfPageOcrBlock.model_validate(block)
                        for block in (page.legacy_ocr_blocks or [])
                    ],
                )
            ],
        ),
    )


@router.get("/{asset_id}/file")
def get_asset_file(
    workspace_id: str,
    asset_id: str,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    get_accessible_workspace(db, user_id, workspace_id)
    asset = get_workspace_asset(db, workspace_id, asset_id)
    if not object_exists(asset.object_key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset file not found.")

    return StreamingResponse(
        stream_bytes(asset.object_key),
        media_type=asset.mime_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(asset.source_filename)}",
            "X-Content-Type-Options": "nosniff",
        },
    )



@router.get(
    "/{asset_id}/representations/{representation_id}/content",
    response_model=DocumentNormalizedContentResponse,
)
def get_document_representation_content(
    workspace_id: str,
    asset_id: str,
    representation_id: str,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> DocumentNormalizedContentResponse:
    """Generation-scoped normalized document content for exact block lookup.

    Source `/file` remains the immutable upload object and is unchanged.
    """
    get_accessible_workspace(db, user_id, workspace_id)
    asset = get_workspace_asset(db, workspace_id, asset_id)
    if asset.asset_kind != "document":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document representation not found.",
        )
    representation = db.scalar(
        select(AssetRepresentation).where(
            AssetRepresentation.id == representation_id,
            AssetRepresentation.asset_id == asset.id,
            AssetRepresentation.workspace_id == workspace_id,
            AssetRepresentation.representation_kind == "document_normalized",
        )
    )
    if representation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document representation not found.",
        )
    normalized = db.get(DocumentNormalizedContent, representation.id)
    if normalized is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document normalized content not found.",
        )
    blocks = db.scalars(
        select(DocumentBlock)
        .where(DocumentBlock.representation_id == representation.id)
        .order_by(DocumentBlock.block_order)
    ).all()
    try:
        normalized_text, validated_blocks = validate_document_normalized_bundle(
            normalized, blocks
        )
    except DocumentIntegrityError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document normalized content is corrupt: {error}",
        ) from error
    return DocumentNormalizedContentResponse(
        assetId=asset.id,
        representationId=representation.id,
        processingGeneration=representation.processing_generation,
        format="markdown",
        parserVersion=normalized.parser_version,  # type: ignore[arg-type]
        normalizationVersion=normalized.normalization_version,  # type: ignore[arg-type]
        contentSha256=normalized.content_sha256,
        normalizedText=normalized_text,
        blocks=[
            DocumentNormalizedBlock(
                blockId=block.block_id,
                blockOrder=block.block_order,
                blockKind=block.block_kind,  # type: ignore[arg-type]
                headingLevel=block.heading_level,
                headingPath=list(block.heading_path or []),
                charStart=block.char_start,
                charEnd=block.char_end,
                textSha256=block.text_sha256,
                text=block.text_content,
            )
            for block in validated_blocks
        ],
    )


def resolve_image_oriented_representation(
    db: Session,
    *,
    asset: Asset,
    workspace_id: str,
    processing_generation: int,
) -> AssetRepresentation:
    representation = db.scalar(
        select(AssetRepresentation).where(
            AssetRepresentation.workspace_id == workspace_id,
            AssetRepresentation.asset_id == asset.id,
            AssetRepresentation.processing_generation == processing_generation,
            AssetRepresentation.representation_kind == "image_oriented",
        )
    )
    if representation is None or not representation.object_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oriented image representation not found.",
        )

    geometry = db.get(ImageRepresentationGeometry, representation.id)
    if geometry is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Oriented image representation geometry is invalid.",
        )
    validate_image_representation_geometry(
        geometry,
        workspace_id=workspace_id,
        asset_id=asset.id,
    )
    if not object_exists(representation.object_key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oriented image file not found.",
        )
    return representation


def stream_image_oriented_representation(
    representation: AssetRepresentation,
    *,
    processing_generation: int,
    cache_control: str,
) -> StreamingResponse:
    assert representation.object_key is not None
    return StreamingResponse(
        stream_bytes(representation.object_key),
        media_type="image/png",
        headers={
            "Cache-Control": cache_control,
            "Content-Disposition": (
                f'inline; filename="image-oriented-generation-{processing_generation}.png"'
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{asset_id}/representations/image-oriented/file")
def get_image_oriented_file(
    workspace_id: str,
    asset_id: str,
    processing_generation: int = Query(..., alias="processingGeneration", ge=1),
    evidence_representation_id: str = Query(..., alias="evidenceRepresentationId", min_length=1),
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    get_accessible_workspace(db, user_id, workspace_id)
    asset = get_workspace_asset(db, workspace_id, asset_id)
    if asset.asset_kind != "image":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image representation not found.",
        )

    evidence_representation = db.scalar(
        select(AssetRepresentation).where(
            AssetRepresentation.id == evidence_representation_id,
            AssetRepresentation.workspace_id == workspace_id,
            AssetRepresentation.asset_id == asset.id,
            AssetRepresentation.processing_generation == processing_generation,
            AssetRepresentation.representation_kind.in_(("image_ocr", "image_caption")),
        )
    )
    if evidence_representation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image evidence snapshot not found.",
        )

    oriented_representation = resolve_image_oriented_representation(
        db,
        asset=asset,
        workspace_id=workspace_id,
        processing_generation=processing_generation,
    )
    return stream_image_oriented_representation(
        oriented_representation,
        processing_generation=processing_generation,
        cache_control="private, max-age=31536000, immutable",
    )


@router.get("/{asset_id}/representations/current-image-oriented/file")
def get_current_image_oriented_file(
    workspace_id: str,
    asset_id: str,
    processing_generation: int = Query(..., alias="processingGeneration", ge=1),
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    get_accessible_workspace(db, user_id, workspace_id)
    asset = get_workspace_asset(db, workspace_id, asset_id)
    if asset.asset_kind != "image":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image representation not found.",
        )
    if processing_generation != asset.current_processing_generation:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Current image representation changed. Reload the asset detail.",
        )

    oriented_representation = resolve_image_oriented_representation(
        db,
        asset=asset,
        workspace_id=workspace_id,
        processing_generation=processing_generation,
    )
    return stream_image_oriented_representation(
        oriented_representation,
        processing_generation=processing_generation,
        cache_control="private, max-age=3600",
    )


@router.post("/upload-session", response_model=CreateUploadSessionResponse, status_code=status.HTTP_201_CREATED)
def create_upload_session(
    workspace_id: str,
    payload: CreateUploadSessionRequest,
    user: User = Depends(require_existing_user),
    db: Session = Depends(get_db),
) -> CreateUploadSessionResponse:
    get_accessible_workspace(db, user.id, workspace_id)
    try:
        mime_type = payload.mimeType.lower()
        module = modality_registry.for_mime_type(mime_type)
    except ModalityContractError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
    now = datetime.now(UTC)
    title = (payload.title or Path(payload.sourceFilename).stem).strip()
    asset = Asset(
        workspace_id=workspace_id,
        created_by_user_id=user.id,
        asset_kind=module.asset_kind,
        title=title or payload.sourceFilename,
        source_filename=payload.sourceFilename,
        object_key="",
        mime_type=mime_type,
        byte_size=payload.byteSize,
        status="pending_upload",
        current_processing_generation=1,
        current_index_version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(asset)
    db.flush()
    asset.object_key = build_object_key(workspace_id, asset.id, payload.sourceFilename)
    db.commit()
    db.refresh(asset)
    return CreateUploadSessionResponse(
        asset=to_asset_summary(asset),
        upload=UploadDescriptor(
            method="PUT",
            objectKey=asset.object_key,
            headers={"Content-Type": mime_type},
        ),
    )


@router.put("/{asset_id}/upload", status_code=status.HTTP_204_NO_CONTENT)
async def upload_asset_binary(
    workspace_id: str,
    asset_id: str,
    request: Request,
    object_key: str = Query(..., alias="objectKey"),
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> Response:
    get_accessible_workspace(db, user_id, workspace_id)
    asset = get_workspace_asset(db, workspace_id, asset_id)
    # Serialize concurrent first PUTs before streaming the body so only one
    # request can persist source bytes / source_sha256 for this Asset.
    db.refresh(asset, with_for_update=True)
    if asset.status != "pending_upload":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Asset is not awaiting upload.",
        )
    if asset.object_key != object_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Object key mismatch.",
        )
    if asset.source_sha256 is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Asset source object is immutable after upload.",
        )

    declared_length = request.headers.get("content-length")
    if declared_length:
        try:
            if int(declared_length) > settings.max_upload_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Upload exceeds max size.",
                )
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid content length.") from error

    request_content_type = request.headers.get("content-type")
    if (
        request_content_type is not None
        and request_content_type.split(";", 1)[0].strip().lower() != asset.mime_type
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Upload Content-Type does not match the upload session.",
        )
    with SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b") as payload:
        total_size = 0
        digest = sha256()
        async for chunk in request.stream():
            total_size += len(chunk)
            if total_size > settings.max_upload_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Upload exceeds max size.",
                )
            payload.write(chunk)
            digest.update(chunk)

        if total_size == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty upload body.")
        if total_size != asset.byte_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Upload size does not match the upload session.",
            )
        payload.seek(0)
        header = payload.read(16)
        try:
            inspected = modality_registry.inspect_upload(asset.mime_type, header)
        except ModalityContractError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
        if inspected.asset_kind != asset.asset_kind:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asset kind mismatch.")
        if inspected.full_payload_validator is not None:
            payload.seek(0)
            full_payload = payload.read()
            try:
                modality_registry.validate_upload_payload(inspected, full_payload)
            except ModalityContractError as error:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=str(error),
                ) from error
        # Re-lock/recheck after body validation. Covers same-session mutations
        # during stream and keeps the pre-storage identity gate explicit.
        db.refresh(asset, with_for_update=True)
        if asset.status != "pending_upload":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Asset is not awaiting upload.",
            )
        if asset.object_key != object_key:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Object key mismatch.",
            )
        if asset.source_sha256 is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Asset source object is immutable after upload.",
            )
        payload.seek(0)
        upload_stream(asset.object_key, payload, total_size, asset.mime_type)

    asset.source_sha256 = digest.hexdigest()
    asset.updated_at = datetime.now(UTC)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{asset_id}/finalize-upload", response_model=FinalizeUploadResponse)
def finalize_upload(
    workspace_id: str,
    asset_id: str,
    payload: FinalizeUploadRequest,
    user: User = Depends(require_existing_user),
    db: Session = Depends(get_db),
) -> FinalizeUploadResponse:
    workspace, _role = get_accessible_workspace(db, user.id, workspace_id)
    asset = get_workspace_asset(db, workspace_id, asset_id)
    db.refresh(asset, with_for_update=True)
    if asset.status != "pending_upload":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Asset is not awaiting finalize upload.",
        )
    if asset.object_key != payload.objectKey:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Object key mismatch.",
        )
    if asset.source_sha256 is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Asset source hash is missing.",
        )
    if not object_exists(asset.object_key):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Uploaded object not found in storage.",
        )
    stored_bytes = download_bytes(asset.object_key)
    stored_sha256 = sha256(stored_bytes).hexdigest()
    if (
        len(stored_bytes) != asset.byte_size
        or stored_sha256 != asset.source_sha256.lower()
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Uploaded object does not match its persisted size or SHA-256.",
        )

    now = datetime.now(UTC)
    job = build_ingest_job(
        workspace_id=workspace_id,
        asset_id=asset.id,
        asset_kind=asset.asset_kind,
        user_id=user.id,
        chunk_size=workspace.chunk_size,
        source="finalize_upload",
        now=now,
    )
    db.add(job)
    db.flush()

    asset.status = "uploaded"
    asset.latest_ingestion_job_id = job.id
    asset.last_error_code = None
    asset.last_error_message = None
    asset.updated_at = now
    db.commit()
    db.refresh(asset)
    db.refresh(job)

    return FinalizeUploadResponse(asset=to_asset_summary(asset), job=to_job_status(job))


@router.post("/{asset_id}/retry", response_model=FinalizeUploadResponse)
def retry_asset(
    workspace_id: str,
    asset_id: str,
    user: User = Depends(require_existing_user),
    db: Session = Depends(get_db),
) -> FinalizeUploadResponse:
    workspace, _role = get_accessible_workspace(db, user.id, workspace_id)
    asset = get_workspace_asset(db, workspace_id, asset_id)
    db.refresh(asset, with_for_update=True)
    if asset.status != "failed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only failed assets can be retried.")
    if db.scalar(
        select(IngestionJob.id).where(
            IngestionJob.asset_id == asset.id,
            IngestionJob.job_type == "delete_cleanup",
            IngestionJob.status.in_(("queued", "running")),
        )
    ) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asset deletion is already running.")
    if not object_exists(asset.object_key):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asset file is no longer available.")
    if db.scalar(
        select(IngestionJob.id).where(
            IngestionJob.asset_id == asset.id,
            IngestionJob.job_type == "ingest",
            IngestionJob.status.in_(("queued", "running")),
        )
    ) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asset ingestion is already running.")

    previous_attempt_count = db.scalar(
        select(func.max(IngestionJob.attempt_count)).where(
            IngestionJob.asset_id == asset.id,
            IngestionJob.job_type == "ingest",
        )
    ) or 0
    now = datetime.now(UTC)
    job = build_ingest_job(
        workspace_id=workspace_id,
        asset_id=asset.id,
        asset_kind=asset.asset_kind,
        user_id=user.id,
        chunk_size=workspace.chunk_size,
        source="retry",
        now=now,
        attempt_count=previous_attempt_count + 1,
    )
    db.add(job)
    db.flush()

    asset.status = "uploaded"
    asset.latest_ingestion_job_id = job.id
    asset.last_error_code = None
    asset.last_error_message = None
    asset.updated_at = now
    db.commit()
    db.refresh(asset)
    db.refresh(job)
    return FinalizeUploadResponse(asset=to_asset_summary(asset), job=to_job_status(job))


@router.post("/{asset_id}/reindex", response_model=FinalizeUploadResponse)
def reindex_asset(
    workspace_id: str,
    asset_id: str,
    user: User = Depends(require_existing_user),
    db: Session = Depends(get_db),
) -> FinalizeUploadResponse:
    workspace, _role = get_accessible_workspace(db, user.id, workspace_id)
    asset = get_workspace_asset(db, workspace_id, asset_id)
    db.refresh(asset, with_for_update=True)
    if asset.status in {"pending_upload", "uploaded", "parsing", "chunking", "deleting", "deleted"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Asset is not ready to reindex.",
        )
    if db.scalar(
        select(IngestionJob.id).where(
            IngestionJob.asset_id == asset.id,
            IngestionJob.job_type == "delete_cleanup",
            IngestionJob.status.in_(("queued", "running")),
        )
    ) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asset deletion is already running.")
    if db.scalar(
        select(IngestionJob.id).where(
            IngestionJob.asset_id == asset.id,
            IngestionJob.job_type == "embed_chunks",
            IngestionJob.status.in_(("queued", "running")),
        )
    ) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asset reindex is already running.")
    if db.scalar(select(ContentUnit.id).where(ContentUnit.asset_id == asset.id)) is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asset has no chunks to reindex.")

    now = datetime.now(UTC)
    job = IngestionJob(
        workspace_id=workspace_id,
        asset_id=asset.id,
        job_type="embed_chunks",
        status="queued",
        attempt_count=1,
        config_snapshot={
            "source": "reindex",
            "chunkSize": workspace.chunk_size,
            **embedding_index_job_snapshot_fields(),
        },
        requested_by_user_id=user.id,
        queued_at=now,
        created_at=now,
    )
    db.add(job)
    db.flush()
    asset.latest_ingestion_job_id = job.id
    asset.last_error_code = None
    asset.last_error_message = None
    asset.updated_at = now
    db.commit()
    db.refresh(asset)
    db.refresh(job)
    return FinalizeUploadResponse(asset=to_asset_summary(asset), job=to_job_status(job))


@router.delete("/{asset_id}", response_model=FinalizeUploadResponse, status_code=status.HTTP_202_ACCEPTED)
def delete_asset(
    workspace_id: str,
    asset_id: str,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> FinalizeUploadResponse:
    _workspace, role = get_accessible_workspace(db, user_id, workspace_id)
    if role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners can delete assets.",
        )

    asset = get_workspace_asset(db, workspace_id, asset_id)
    db.refresh(asset, with_for_update=True)
    if db.scalar(
        select(IngestionJob.id).where(
            IngestionJob.asset_id == asset.id,
            IngestionJob.job_type == "delete_cleanup",
            IngestionJob.status.in_(("queued", "running")),
        )
    ) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asset deletion is already running.")

    now = datetime.now(UTC)
    job = build_delete_cleanup_job(
        workspace_id=workspace_id,
        asset_id=asset.id,
        user_id=user_id,
        source="delete_asset",
        now=now,
    )
    db.add(job)
    db.flush()
    asset.status = "deleting"
    asset.latest_ingestion_job_id = job.id
    asset.last_error_code = None
    asset.last_error_message = None
    asset.updated_at = now
    db.commit()
    db.refresh(asset)
    db.refresh(job)
    return FinalizeUploadResponse(asset=to_asset_summary(asset), job=to_job_status(job))


@router.post("/{asset_id}/delete-retry", response_model=FinalizeUploadResponse)
def retry_delete_asset(
    workspace_id: str,
    asset_id: str,
    user: User = Depends(require_existing_user),
    db: Session = Depends(get_db),
) -> FinalizeUploadResponse:
    _workspace, role = get_accessible_workspace(db, user.id, workspace_id)
    if role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners can delete assets.",
        )
    asset = get_workspace_asset(db, workspace_id, asset_id, allow_deleting=True)
    db.refresh(asset, with_for_update=True)
    if asset.status != "deleting":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asset does not have a failed deletion.")
    if db.scalar(
        select(IngestionJob.id).where(
            IngestionJob.asset_id == asset.id,
            IngestionJob.job_type == "delete_cleanup",
            IngestionJob.status.in_(("queued", "running")),
        )
    ) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asset deletion is already running.")
    if db.scalar(
        select(IngestionJob.id).where(
            IngestionJob.id == asset.latest_ingestion_job_id,
            IngestionJob.job_type == "delete_cleanup",
            IngestionJob.status == "failed",
        )
    ) is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asset does not have a failed deletion.")

    previous_attempt_count = db.scalar(
        select(func.max(IngestionJob.attempt_count)).where(
            IngestionJob.asset_id == asset.id,
            IngestionJob.job_type == "delete_cleanup",
        )
    ) or 0
    now = datetime.now(UTC)
    job = build_delete_cleanup_job(
        workspace_id=workspace_id,
        asset_id=asset.id,
        user_id=user.id,
        source="retry_delete",
        now=now,
        attempt_count=previous_attempt_count + 1,
    )
    db.add(job)
    db.flush()
    asset.latest_ingestion_job_id = job.id
    asset.last_error_code = None
    asset.last_error_message = None
    asset.updated_at = now
    db.commit()
    db.refresh(asset)
    db.refresh(job)
    return FinalizeUploadResponse(asset=to_asset_summary(asset), job=to_job_status(job))
