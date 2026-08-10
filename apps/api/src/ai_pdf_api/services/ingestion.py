from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from ai_pdf_api.core.settings import settings
from ai_pdf_api.modalities.ingestion import (
    GeneratedObject,
    IngestionAdapterRegistry,
    IngestionError,
    IngestionResult,
)
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ContentUnit,
    ContentUnitEmbedding,
    EvidenceLocator,
    IngestionJob,
)
from ai_pdf_api.services.providers import EmbeddingProvider, ModelProviderError
from ai_pdf_api.services.storage import (
    delete_object_if_exists,
    delete_objects_with_prefix,
    download_bytes,
    upload_bytes,
)
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

INGESTION_LEASE_TIMEOUT = timedelta(minutes=15)
logger = logging.getLogger("ai_pdf_api.ingestion")


class _SupersededIngestionJob(RuntimeError):
    pass


def recover_stale_ingestion_jobs(db: Session, now: datetime) -> None:
    cutoff = now - INGESTION_LEASE_TIMEOUT
    stale_jobs = db.scalars(
        select(IngestionJob)
        .where(
            IngestionJob.status == "running",
            IngestionJob.job_type.in_(("ingest", "embed_chunks", "delete_cleanup")),
            (IngestionJob.started_at.is_(None)) | (IngestionJob.started_at < cutoff),
        )
        .with_for_update(skip_locked=True),
    ).all()

    for job in stale_jobs:
        asset = db.scalar(
            select(Asset)
            .where(Asset.id == job.asset_id)
            .with_for_update()
        )
        if (
            asset is None
            or asset.deleted_at is not None
            or asset.latest_ingestion_job_id not in {None, job.id}
        ):
            job.status = "cancelled"
            job.finished_at = now
            continue

        job.status = "queued"
        job.queued_at = now
        job.started_at = None
        job.finished_at = None
        job.attempt_count += 1
        job.error_code = None
        job.error_message = None
        if asset.status not in {"deleted", "deleting"}:
            if job.job_type == "ingest":
                asset.status = "uploaded"
            elif job.job_type == "embed_chunks":
                asset.status = _available_asset_status(db, asset.id)
            else:
                asset.status = "deleting"
            asset.updated_at = now
    db.flush()


def claim_next_ingestion_job(db: Session) -> str | None:
    now = datetime.now(UTC)
    recover_stale_ingestion_jobs(db, now)
    job = db.scalar(
        select(IngestionJob)
        .where(
            IngestionJob.status == "queued",
            IngestionJob.job_type.in_(("ingest", "embed_chunks", "delete_cleanup")),
        )
        .order_by(IngestionJob.queued_at)
        .with_for_update(skip_locked=True)
        .limit(1),
    )
    if job is None:
        db.commit()
        return None

    asset = db.scalar(
        select(Asset)
        .where(Asset.id == job.asset_id)
        .with_for_update()
    )
    if asset is None or asset.deleted_at is not None:
        job.status = "cancelled"
        job.finished_at = now
        db.commit()
        return None
    if (
        asset.latest_ingestion_job_id not in {None, job.id}
        or (
            job.job_type in {"ingest", "embed_chunks"}
            and asset.status in {"deleting", "deleted"}
        )
    ):
        job.status = "cancelled"
        job.error_code = "ingestion_job_superseded"
        job.error_message = "A newer job or deletion state replaced this job."
        job.finished_at = now
        db.commit()
        return None

    job.status = "running"
    job.started_at = now
    if job.job_type == "ingest":
        asset.status = "parsing"
    elif job.job_type == "embed_chunks":
        asset.status = "embedding"
    else:
        asset.status = "deleting"
    asset.last_error_code = None
    asset.last_error_message = None
    asset.updated_at = now
    db.commit()
    return job.id


def process_ingestion_job(
    db: Session,
    job_id: str,
    *,
    ingestion_adapters: IngestionAdapterRegistry | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> None:
    job = db.get(IngestionJob, job_id)
    if job is None or job.status != "running":
        return
    if job.job_type == "embed_chunks":
        process_embedding_job(db, job_id, embedding_provider)
        return
    if job.job_type == "delete_cleanup":
        process_delete_cleanup(db, job_id, ingestion_adapters)
        return

    asset = db.get(Asset, job.asset_id)
    if asset is None:
        _mark_job_failed(db, job, None, "asset_missing", "Asset disappeared before processing.")
        return
    if asset.latest_ingestion_job_id not in {None, job.id}:
        _cancel_superseded_job(db, job.id)
        return

    generated_object_keys: list[str] = []
    try:
        if embedding_provider is not None:
            _validate_job_embedding_config(job, embedding_provider)
        # Image caption config/fingerprint validation is performed by the
        # modality adapter against the injected caption provider (not a fresh
        # global factory that can require live API keys in tests/workers).
        if ingestion_adapters is None:
            raise IngestionError(
                "modality_adapter_unavailable",
                "No ingestion adapters are configured in this worker build.",
            )
        adapter = ingestion_adapters.get(asset.asset_kind)
        payload = download_bytes(asset.object_key)
        if asset.source_sha256 is not None:
            payload_sha256 = sha256(payload).hexdigest()
            if len(payload) != asset.byte_size or payload_sha256 != asset.source_sha256.lower():
                raise IngestionError(
                    "source_object_integrity_mismatch",
                    "Downloaded source object does not match its persisted size or SHA-256.",
                )
        snapshot = job.config_snapshot or {}
        now = datetime.now(UTC)
        latest_generation = db.scalar(
            select(func.max(AssetRepresentation.processing_generation)).where(
                AssetRepresentation.asset_id == asset.id
            )
        )
        processing_generation = (
            asset.current_processing_generation
            if latest_generation is None
            else latest_generation + 1
        )
        asset.status = "chunking"
        asset.updated_at = now
        result = adapter.ingest(
            db,
            asset=asset,
            payload=payload,
            processing_generation=processing_generation,
            config_snapshot=snapshot,
            created_at=now,
        )
        _upload_generated_objects(asset, result, generated_object_keys)
        if embedding_provider is None:
            asset.status = "chunked"
            _assert_job_is_latest(db, job)
        else:
            asset.status = "embedding"
            asset.updated_at = datetime.now(UTC)
            _embed_content_units(
                db,
                asset,
                embedding_provider,
                processing_generation=processing_generation,
            )
            _assert_job_is_latest(db, job)
            asset.current_processing_generation = processing_generation
            db.flush()
            _activate_current_embeddings(
                db,
                asset,
                embedding_provider,
                processing_generation=processing_generation,
            )
            asset.status = "ready"
        if embedding_provider is None:
            asset.current_processing_generation = processing_generation
        asset.updated_at = datetime.now(UTC)
        job.status = "succeeded"
        job.finished_at = datetime.now(UTC)
        db.commit()
    except _SupersededIngestionJob:
        failed_cleanup_keys = _discard_generated_objects(generated_object_keys)
        _cancel_superseded_job(db, job.id, failed_cleanup_keys)
    except IngestionError as error:
        _mark_job_failed_after_object_cleanup(
            db,
            job,
            asset,
            error.code,
            str(error),
            generated_object_keys,
        )
    except ModelProviderError as error:
        _mark_job_failed_after_object_cleanup(
            db,
            job,
            asset,
            error.code,
            error.message,
            generated_object_keys,
        )
    except Exception as error:
        _mark_job_failed_after_object_cleanup(
            db,
            job,
            asset,
            "ingestion_failed",
            str(error),
            generated_object_keys,
        )


def process_embedding_job(
    db: Session,
    job_id: str,
    embedding_provider: EmbeddingProvider | None,
) -> None:
    job = db.get(IngestionJob, job_id)
    if job is None or job.status != "running":
        return
    asset = db.get(Asset, job.asset_id)
    if asset is None:
        _mark_job_failed(db, job, None, "asset_missing", "Asset disappeared before embedding.")
        return
    if asset.latest_ingestion_job_id not in {None, job.id}:
        _cancel_superseded_job(db, job.id)
        return
    if embedding_provider is None:
        _mark_embedding_job_failed(db, job, asset, "embedding_provider_missing", "Embedding provider is not configured.")
        return

    try:
        _validate_job_embedding_config(job, embedding_provider)
        asset.status = "embedding"
        asset.updated_at = datetime.now(UTC)
        _embed_content_units(
            db,
            asset,
            embedding_provider,
            processing_generation=asset.current_processing_generation,
        )
        _assert_job_is_latest(db, job)
        _activate_current_embeddings(
            db,
            asset,
            embedding_provider,
            processing_generation=asset.current_processing_generation,
        )
        asset.status = "ready"
        asset.updated_at = datetime.now(UTC)
        job.status = "succeeded"
        job.finished_at = datetime.now(UTC)
        db.commit()
    except _SupersededIngestionJob:
        _cancel_superseded_job(db, job.id)
    except ModelProviderError as error:
        _mark_embedding_job_failed(db, job, asset, error.code, error.message)
    except Exception as error:
        _mark_embedding_job_failed(db, job, asset, "embedding_failed", str(error))


def process_delete_cleanup(
    db: Session,
    job_id: str,
    ingestion_adapters: IngestionAdapterRegistry | None,
) -> None:
    job = db.get(IngestionJob, job_id)
    if job is None or job.status != "running":
        return
    asset = db.get(Asset, job.asset_id)
    if asset is None:
        job.status = "succeeded"
        job.finished_at = datetime.now(UTC)
        db.commit()
        return
    if asset.latest_ingestion_job_id not in {None, job.id}:
        _cancel_superseded_job(db, job.id)
        return
    if asset.deleted_at is not None:
        job.status = "cancelled"
        job.finished_at = datetime.now(UTC)
        db.commit()
        return

    try:
        if ingestion_adapters is None:
            raise IngestionError(
                "modality_adapter_unavailable",
                "No ingestion adapters are configured in this worker build.",
            )
        adapter = ingestion_adapters.get(asset.asset_kind)
        derived_object_keys = db.scalars(
            select(AssetRepresentation.object_key).where(
                AssetRepresentation.asset_id == asset.id,
                AssetRepresentation.object_key.is_not(None),
            )
        ).all()
        object_keys = dict.fromkeys(
            (asset.object_key, *(key for key in derived_object_keys if key is not None))
        )
        for object_key in object_keys:
            delete_object_if_exists(object_key)
        delete_objects_with_prefix(
            f"workspaces/{asset.workspace_id}/assets/{asset.id}/"
        )
        adapter.cleanup(db, asset=asset)
        now = datetime.now(UTC)
        asset.deleted_at = now
        asset.status = "deleted"
        asset.last_error_code = None
        asset.last_error_message = None
        asset.updated_at = now
        job.status = "succeeded"
        job.error_code = None
        job.error_message = None
        job.finished_at = now
        db.commit()
    except Exception as error:
        _mark_delete_job_failed(db, job, asset, "delete_cleanup_failed", str(error))


def _embed_content_units(
    db: Session,
    asset: Asset,
    embedding_provider: EmbeddingProvider,
    *,
    processing_generation: int,
) -> None:
    units = db.scalars(
        select(ContentUnit)
        .join(
            AssetRepresentation,
            AssetRepresentation.id == ContentUnit.representation_id,
        )
        .join(EvidenceLocator, EvidenceLocator.id == ContentUnit.source_locator_id)
        .where(
            ContentUnit.asset_id == asset.id,
            ContentUnit.workspace_id == asset.workspace_id,
            ContentUnit.index_version == asset.current_index_version,
            AssetRepresentation.asset_id == asset.id,
            AssetRepresentation.workspace_id == asset.workspace_id,
            AssetRepresentation.processing_generation == processing_generation,
            EvidenceLocator.asset_id == asset.id,
            EvidenceLocator.workspace_id == asset.workspace_id,
            EvidenceLocator.representation_id_snapshot == AssetRepresentation.id,
            EvidenceLocator.processing_generation_snapshot == processing_generation,
        )
        .order_by(ContentUnit.unit_order, ContentUnit.id),
    ).all()
    if not units:
        raise IngestionError("no_chunks", "Asset produced no non-empty chunks.")

    unit_ids = [unit.id for unit in units]
    db.execute(
        update(ContentUnitEmbedding)
        .where(
            ContentUnitEmbedding.asset_id == asset.id,
            ContentUnitEmbedding.is_current.is_(True),
            or_(
                ContentUnitEmbedding.processing_generation != processing_generation,
                ContentUnitEmbedding.index_version != asset.current_index_version,
            ),
        )
        .values(is_current=False)
    )
    db.execute(
        delete(ContentUnitEmbedding).where(
            ContentUnitEmbedding.content_unit_id.in_(unit_ids),
            ContentUnitEmbedding.embedding_space == "text",
            ContentUnitEmbedding.provider == embedding_provider.provider,
            ContentUnitEmbedding.model == embedding_provider.model,
            ContentUnitEmbedding.version == embedding_provider.version,
        )
    )

    batch_size = settings.embedding_batch_size
    for offset in range(0, len(units), batch_size):
        batch = units[offset : offset + batch_size]
        vectors = embedding_provider.embed_documents([unit.text_content for unit in batch])
        if len(vectors) != len(batch):
            raise ModelProviderError("embedding_invalid_response", "Embedding provider returned an invalid vector count.")
        for unit, vector in zip(batch, vectors, strict=True):
            db.add(
                ContentUnitEmbedding(
                    workspace_id=asset.workspace_id,
                    asset_id=asset.id,
                    content_unit_id=unit.id,
                    processing_generation=processing_generation,
                    index_version=unit.index_version,
                    is_current=False,
                    embedding_space="text",
                    provider=embedding_provider.provider,
                    model=embedding_provider.model,
                    dimensions=embedding_provider.dimensions,
                    version=embedding_provider.version,
                    embedding=vector,
                    created_at=datetime.now(UTC),
                )
            )
        db.flush()


def _activate_current_embeddings(
    db: Session,
    asset: Asset,
    embedding_provider: EmbeddingProvider,
    *,
    processing_generation: int,
) -> None:
    db.execute(
        update(ContentUnitEmbedding)
        .where(
            ContentUnitEmbedding.asset_id == asset.id,
            ContentUnitEmbedding.workspace_id == asset.workspace_id,
            ContentUnitEmbedding.processing_generation == processing_generation,
            ContentUnitEmbedding.index_version == asset.current_index_version,
            ContentUnitEmbedding.embedding_space == "text",
            ContentUnitEmbedding.provider == embedding_provider.provider,
            ContentUnitEmbedding.model == embedding_provider.model,
            ContentUnitEmbedding.version == embedding_provider.version,
            ContentUnitEmbedding.dimensions == embedding_provider.dimensions,
            ContentUnitEmbedding.is_current.is_(False),
        )
        .values(is_current=True)
    )


def _assert_job_is_latest(db: Session, job: IngestionJob) -> None:
    latest_job_id = db.scalar(
        select(Asset.latest_ingestion_job_id)
        .where(Asset.id == job.asset_id)
        .with_for_update()
    )
    if latest_job_id not in {None, job.id}:
        raise _SupersededIngestionJob(job.id)


def _cancel_superseded_job(
    db: Session,
    job_id: str,
    failed_cleanup_keys: list[str] | None = None,
) -> None:
    db.rollback()
    job = db.get(IngestionJob, job_id)
    if job is None:
        return
    now = datetime.now(UTC)
    job.status = "cancelled"
    job.error_code = "ingestion_job_superseded"
    job.error_message = "A newer ingestion job replaced this job before commit."
    if failed_cleanup_keys:
        job.error_code = "generated_object_cleanup_failed"
        job.error_message += " Pending generated object cleanup: " + ",".join(
            sorted(failed_cleanup_keys)
        )
    job.finished_at = now
    db.commit()


def _validate_job_embedding_config(job: IngestionJob, embedding_provider: EmbeddingProvider) -> None:
    from ai_pdf_api.services.capabilities import require_matching_snapshot_fingerprint

    snapshot = job.config_snapshot or {}
    expected = {
        "embeddingProvider": embedding_provider.provider,
        "embeddingModel": embedding_provider.model,
        "embeddingDimensions": embedding_provider.dimensions,
        "embeddingVersion": embedding_provider.version,
    }
    if any(key in snapshot and snapshot[key] != value for key, value in expected.items()):
        raise ModelProviderError(
            "embedding_configuration_mismatch",
            "Embedding provider configuration does not match the job snapshot.",
        )
    require_matching_snapshot_fingerprint(
        snapshot,
        field_name="embeddingProfileFingerprint",
        actual_fingerprint=getattr(embedding_provider, "config_fingerprint", None),
        error_code="embedding_configuration_mismatch",
        error_message="Embedding provider configuration does not match the job snapshot.",
        error_cls=ModelProviderError,
    )



def _available_asset_status(db: Session, asset_id: str) -> str:
    asset = db.get(Asset, asset_id)
    if asset is None:
        return "chunked"
    unit_ids = db.scalars(
        select(ContentUnit.id)
        .join(
            AssetRepresentation,
            AssetRepresentation.id == ContentUnit.representation_id,
        )
        .join(EvidenceLocator, EvidenceLocator.id == ContentUnit.source_locator_id)
        .where(
            ContentUnit.asset_id == asset.id,
            ContentUnit.workspace_id == asset.workspace_id,
            ContentUnit.index_version == asset.current_index_version,
            AssetRepresentation.asset_id == asset.id,
            AssetRepresentation.workspace_id == asset.workspace_id,
            AssetRepresentation.processing_generation == asset.current_processing_generation,
            EvidenceLocator.asset_id == asset.id,
            EvidenceLocator.workspace_id == asset.workspace_id,
            EvidenceLocator.representation_id_snapshot == AssetRepresentation.id,
            EvidenceLocator.processing_generation_snapshot
            == asset.current_processing_generation,
        )
    ).all()
    if not unit_ids:
        return "chunked"
    embedded_unit_ids = set(
        db.scalars(
            select(ContentUnitEmbedding.content_unit_id).where(
                ContentUnitEmbedding.content_unit_id.in_(unit_ids),
                ContentUnitEmbedding.asset_id == asset.id,
                ContentUnitEmbedding.workspace_id == asset.workspace_id,
                ContentUnitEmbedding.processing_generation
                == asset.current_processing_generation,
                ContentUnitEmbedding.index_version == asset.current_index_version,
                ContentUnitEmbedding.is_current.is_(True),
                ContentUnitEmbedding.embedding_space == "text",
                ContentUnitEmbedding.provider == settings.embedding_provider,
                ContentUnitEmbedding.model == settings.embedding_model,
                ContentUnitEmbedding.version == settings.embedding_version,
                ContentUnitEmbedding.dimensions == settings.embedding_dimensions,
            )
        ).all()
    )
    return "ready" if embedded_unit_ids == set(unit_ids) else "chunked"


def _upload_generated_objects(
    asset: Asset,
    result: IngestionResult,
    attempted_object_keys: list[str],
) -> None:
    if not isinstance(result, IngestionResult):
        raise IngestionError(
            "modality_adapter_result_invalid",
            "Ingestion adapter returned an invalid result.",
        )
    expected_prefix = f"workspaces/{asset.workspace_id}/assets/{asset.id}/representations/"
    seen_keys: set[str] = set()
    for generated in result.generated_objects:
        _validate_generated_object(asset, generated, expected_prefix, seen_keys)
        attempted_object_keys.append(generated.object_key)
        delete_object_if_exists(generated.object_key)
        upload_bytes(generated.object_key, generated.payload, generated.content_type)
        seen_keys.add(generated.object_key)


def _validate_generated_object(
    asset: Asset,
    generated: GeneratedObject,
    expected_prefix: str,
    seen_keys: set[str],
) -> None:
    if generated.object_key == asset.object_key or not generated.object_key.startswith(expected_prefix):
        raise IngestionError(
            "generated_object_key_invalid",
            "Generated objects must use the asset representation namespace.",
        )
    if generated.object_key in seen_keys:
        raise IngestionError("generated_object_duplicate", "Generated object keys must be unique.")
    if not generated.payload or not generated.content_type:
        raise IngestionError("generated_object_invalid", "Generated object payload is invalid.")
    if sha256(generated.payload).hexdigest() != generated.content_sha256:
        raise IngestionError(
            "generated_object_hash_mismatch",
            "Generated object hash does not match its payload.",
        )


def _discard_generated_objects(object_keys: list[str]) -> list[str]:
    failed_object_keys: list[str] = []
    for object_key in reversed(object_keys):
        try:
            delete_object_if_exists(object_key)
        except Exception as error:
            failed_object_keys.append(object_key)
            logger.exception(
                "generated_object_cleanup_failed object_key=%s error_type=%s",
                object_key,
                type(error).__name__,
            )
    return failed_object_keys


def _mark_job_failed_after_object_cleanup(
    db: Session,
    job: IngestionJob,
    asset: Asset,
    error_code: str,
    error_message: str,
    generated_object_keys: list[str],
) -> None:
    failed_cleanup_keys = _discard_generated_objects(generated_object_keys)
    if failed_cleanup_keys:
        error_code = "generated_object_cleanup_failed"
        error_message = (
            f"{error_message} Pending generated object cleanup: "
            f"{','.join(sorted(failed_cleanup_keys))}"
        )
    _mark_job_failed(db, job, asset, error_code, error_message)


def _mark_embedding_job_failed(
    db: Session,
    job: IngestionJob,
    asset: Asset,
    error_code: str,
    error_message: str,
) -> None:
    job, current_asset = _prepare_job_failure(db, job.id)
    if job is None:
        return
    now = datetime.now(UTC)
    job.status = "failed"
    job.error_code = error_code
    job.error_message = error_message
    job.finished_at = now
    if current_asset is not None:
        current_asset.status = _available_asset_status(db, current_asset.id)
        current_asset.last_error_code = error_code
        current_asset.last_error_message = error_message
        current_asset.updated_at = now
    db.commit()


def _mark_job_failed(
    db: Session,
    job: IngestionJob,
    asset: Asset | None,
    error_code: str,
    error_message: str,
) -> None:
    job, current_asset = _prepare_job_failure(db, job.id)
    if job is None:
        return
    now = datetime.now(UTC)
    job.status = "failed"
    job.error_code = error_code
    job.error_message = error_message
    job.finished_at = now
    if current_asset is not None:
        # Fail closed: only preserve ready when the current generation already has
        # a complete retrieval chain (units + locators + current embeddings).
        # Representation existence alone is not enough; partial/initial ingest
        # must become failed rather than chunked.
        if _available_asset_status(db, current_asset.id) == "ready":
            current_asset.status = "ready"
        else:
            current_asset.status = "failed"
        current_asset.last_error_code = error_code
        current_asset.last_error_message = error_message
        current_asset.updated_at = now
    db.commit()


def _mark_delete_job_failed(
    db: Session,
    job: IngestionJob,
    asset: Asset,
    error_code: str,
    error_message: str,
) -> None:
    job, current_asset = _prepare_job_failure(db, job.id)
    if job is None:
        return
    now = datetime.now(UTC)
    job.status = "failed"
    job.error_code = error_code
    job.error_message = error_message
    job.finished_at = now
    if current_asset is not None:
        current_asset.status = "deleting"
        current_asset.last_error_code = error_code
        current_asset.last_error_message = error_message
        current_asset.updated_at = now
    db.commit()


def _prepare_job_failure(
    db: Session,
    job_id: str,
) -> tuple[IngestionJob | None, Asset | None]:
    """Reload failure targets and cancel stale work before changing Asset state."""
    db.rollback()
    job = db.get(IngestionJob, job_id)
    if job is None:
        return None, None
    asset = db.scalar(
        select(Asset)
        .where(Asset.id == job.asset_id)
        .with_for_update()
    )
    if asset is not None and asset.latest_ingestion_job_id not in {None, job.id}:
        now = datetime.now(UTC)
        job.status = "cancelled"
        job.error_code = "ingestion_job_superseded"
        job.error_message = "A newer ingestion job replaced this job before failure commit."
        job.finished_at = now
        db.commit()
        return None, None
    return job, asset
