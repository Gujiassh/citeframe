from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ai_pdf_api.core.settings import settings
from ai_pdf_api.models import Asset, ContentUnitEmbedding, IngestionJob
from ai_pdf_api.services.providers import EmbeddingProvider, ModelProviderError

EMBEDDING_INDEX_MISMATCH_CODE = "embedding_index_mismatch"
EMBEDDING_INDEX_MISMATCH_MESSAGE = (
    "Current embedding index does not match the active embedding contract; "
    "explicit reindex is required."
)
TEXT_EMBEDDING_SPACE = "text"
_SUCCESSFUL_INDEX_JOB_TYPES = frozenset({"ingest", "embed_chunks"})


@dataclass(frozen=True)
class EmbeddingIndexContract:
    """Active embedding index contract used for retrieval and reindex snapshots.

    Stored vectors are matched on provider/model/dimensions/version. When a ready
    asset's latest successful ingest/reindex job freezes embeddingProfileFingerprint,
    that fingerprint must also match. Legacy jobs without the field keep
    provider/model/dimensions/version-only compatibility. No embedding-row schema
    change in this slice.
    """

    provider: str
    model: str
    dimensions: int
    version: str
    config_fingerprint: str

    def matches_vector(
        self,
        *,
        provider: str,
        model: str,
        dimensions: int,
        version: str,
    ) -> bool:
        return (
            provider == self.provider
            and model == self.model
            and dimensions == self.dimensions
            and version == self.version
        )


def _require_non_empty_fingerprint(value: object, *, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ModelProviderError(
            "embedding_configuration_mismatch",
            f"Active embedding profile fingerprint is unavailable ({context}).",
        )
    return value


def _fingerprint_from_capability_registry() -> str:
    from ai_pdf_api.services.capabilities import build_capability_registry

    profile = build_capability_registry().resolve("embedding")
    return _require_non_empty_fingerprint(
        profile.config_fingerprint,
        context="capability registry",
    )


def resolve_embedding_index_contract(
    embedding_provider: EmbeddingProvider | None = None,
) -> EmbeddingIndexContract:
    """Resolve the active embedding index contract from a provider or server settings.

    Fingerprint resolution is fail-closed: never returns an empty fingerprint.
    """

    if embedding_provider is not None:
        provider_fingerprint = getattr(embedding_provider, "config_fingerprint", None)
        if isinstance(provider_fingerprint, str) and provider_fingerprint:
            fingerprint = provider_fingerprint
        else:
            # Injected providers may omit fingerprint; never write empty. Resolve
            # the active server embedding profile fingerprint fail-closed instead.
            fingerprint = _fingerprint_from_capability_registry()
        return EmbeddingIndexContract(
            provider=embedding_provider.provider,
            model=embedding_provider.model,
            dimensions=embedding_provider.dimensions,
            version=embedding_provider.version,
            config_fingerprint=fingerprint,
        )

    fingerprint = _fingerprint_from_capability_registry()
    return EmbeddingIndexContract(
        provider=settings.embedding_provider,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        version=settings.embedding_version,
        config_fingerprint=fingerprint,
    )


def embedding_index_job_snapshot_fields(
    contract: EmbeddingIndexContract | None = None,
) -> dict[str, object]:
    """Profile fields frozen onto ingest/reindex job config snapshots."""

    resolved = contract or resolve_embedding_index_contract()
    fingerprint = _require_non_empty_fingerprint(
        resolved.config_fingerprint,
        context="index contract snapshot",
    )
    return {
        "embeddingProvider": resolved.provider,
        "embeddingModel": resolved.model,
        "embeddingDimensions": resolved.dimensions,
        "embeddingVersion": resolved.version,
        "embeddingProfileFingerprint": fingerprint,
    }


def raise_embedding_index_mismatch() -> None:
    raise ModelProviderError(EMBEDDING_INDEX_MISMATCH_CODE, EMBEDDING_INDEX_MISMATCH_MESSAGE)


def _ready_embedding_base_filters(
    workspace_id: str,
    asset_ids: list[str] | None,
) -> tuple:
    filters = (
        ContentUnitEmbedding.workspace_id == workspace_id,
        ContentUnitEmbedding.is_current.is_(True),
        ContentUnitEmbedding.embedding_space == TEXT_EMBEDDING_SPACE,
        Asset.workspace_id == workspace_id,
        Asset.status == "ready",
        Asset.deleted_at.is_(None),
        ContentUnitEmbedding.asset_id == Asset.id,
    )
    if asset_ids is not None:
        return (*filters, ContentUnitEmbedding.asset_id.in_(asset_ids))
    return filters


def _latest_successful_index_job(
    db: Session,
    *,
    workspace_id: str,
    asset_id: str,
) -> IngestionJob | None:
    """Resolve the newest successful index-producing job for an asset.

    Does not trust Asset.latest_ingestion_job_id: a later failed reindex or
    non-index job may own that pointer while an older successful index job still
    freezes the fingerprint that produced current vectors.
    """

    return db.scalar(
        select(IngestionJob)
        .where(
            IngestionJob.workspace_id == workspace_id,
            IngestionJob.asset_id == asset_id,
            IngestionJob.status == "succeeded",
            IngestionJob.job_type.in_(tuple(_SUCCESSFUL_INDEX_JOB_TYPES)),
        )
        .order_by(
            IngestionJob.finished_at.desc(),
            IngestionJob.created_at.desc(),
            IngestionJob.id.desc(),
        )
        .limit(1)
    )


def _assert_matching_assets_job_fingerprints(
    db: Session,
    workspace_id: str,
    contract: EmbeddingIndexContract,
    *,
    asset_ids: list[str] | None,
) -> None:
    """When job snapshots freeze embeddingProfileFingerprint, require an equal active value."""

    base_filters = _ready_embedding_base_filters(workspace_id, asset_ids)
    matching_asset_ids = [
        asset_id
        for asset_id in db.scalars(
            select(Asset.id)
            .join(ContentUnitEmbedding, ContentUnitEmbedding.asset_id == Asset.id)
            .where(
                *base_filters,
                ContentUnitEmbedding.provider == contract.provider,
                ContentUnitEmbedding.model == contract.model,
                ContentUnitEmbedding.version == contract.version,
                ContentUnitEmbedding.dimensions == contract.dimensions,
            )
            .distinct()
            .order_by(Asset.id)
        ).all()
    ]
    for asset_id in matching_asset_ids:
        job = _latest_successful_index_job(
            db,
            workspace_id=workspace_id,
            asset_id=asset_id,
        )
        if job is None:
            # No successful index job remains legacy absence of a frozen snapshot.
            continue
        # Queried jobs must still belong to the ready asset scope before any snapshot is trusted.
        if job.asset_id != asset_id or job.workspace_id != workspace_id:
            raise_embedding_index_mismatch()
        snapshot = job.config_snapshot or {}
        if "embeddingProfileFingerprint" not in snapshot:
            # Legacy successful jobs remain provider/model/dimensions/version-only.
            continue
        expected = snapshot.get("embeddingProfileFingerprint")
        if expected != contract.config_fingerprint:
            raise_embedding_index_mismatch()


def assert_current_embeddings_match_contract(
    db: Session,
    workspace_id: str,
    contract: EmbeddingIndexContract,
    *,
    asset_ids: list[str] | None = None,
) -> None:
    """Fail closed when scoped ready assets only have current vectors outside the contract.

    Semantics:
    - no ready assets / no current vectors → allow empty retrieval
    - at least one matching current vector in scope → allow retrieval after optional
      job-snapshot fingerprint checks for assets that freeze embeddingProfileFingerprint
    - only non-matching current vectors in scope → embedding_index_mismatch
    - matching and non-matching current vectors may coexist (multi-provider); matching wins
    - settings/profile drift never auto-reindexes or rewrites vectors
    """

    if asset_ids == []:
        return

    base_filters = _ready_embedding_base_filters(workspace_id, asset_ids)

    matching_exists = db.scalar(
        select(ContentUnitEmbedding.id)
        .join(Asset, Asset.id == ContentUnitEmbedding.asset_id)
        .where(
            *base_filters,
            ContentUnitEmbedding.provider == contract.provider,
            ContentUnitEmbedding.model == contract.model,
            ContentUnitEmbedding.version == contract.version,
            ContentUnitEmbedding.dimensions == contract.dimensions,
        )
        .limit(1)
    )
    if matching_exists is not None:
        _assert_matching_assets_job_fingerprints(
            db,
            workspace_id,
            contract,
            asset_ids=asset_ids,
        )
        return

    mismatched_exists = db.scalar(
        select(ContentUnitEmbedding.id)
        .join(Asset, Asset.id == ContentUnitEmbedding.asset_id)
        .where(
            *base_filters,
            or_(
                ContentUnitEmbedding.provider != contract.provider,
                ContentUnitEmbedding.model != contract.model,
                ContentUnitEmbedding.version != contract.version,
                ContentUnitEmbedding.dimensions != contract.dimensions,
            ),
        )
        .limit(1)
    )
    if mismatched_exists is not None:
        raise_embedding_index_mismatch()
