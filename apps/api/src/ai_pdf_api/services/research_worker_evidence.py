from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from datetime import UTC, datetime

from ai_pdf_api.modalities.evidence import (
    clone_evidence_locator,
    serialize_evidence_locator,
)
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ResearchEvidenceHandle,
    ResearchEvidenceSnapshot,
    ResearchExecutionAsset,
    ResearchExecutionSnapshot,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
    ResearchToolCall,
    ResearchToolCallInputHandle,
)
from ai_pdf_api.services.embedding_index import EMBEDDING_INDEX_MISMATCH_CODE
from ai_pdf_api.services.providers import (
    EmbeddingProvider,
    ModelProviderError,
    get_embedding_provider,
)
from ai_pdf_api.services.research import (
    ResearchError,
    canonical_sha256,
)
from ai_pdf_api.services.research_evidence_provenance import (
    evidence_source_fingerprint,
    validate_evidence_source_fingerprint,
)
from ai_pdf_api.services.research_worker_lease import _active_attempt_chain
from ai_pdf_api.services.research_worker_tools import (
    begin_tool_call,
    complete_tool_call,
    restore_evidence_handles,
)
from ai_pdf_api.services.research_worker_types import (
    FrozenEvidence,
    LoadedFrozenEvidence,
)
from ai_pdf_api.services.retrieval import retrieve_query_content
from sqlalchemy import select
from sqlalchemy.orm import Session


def _frozen_execution_context(
    db: Session,
    *,
    run_id: str,
    execution_snapshot_id: str,
    step_id: str,
    attempt_id: str,
    branch_key: str,
    now: datetime,
) -> tuple[ResearchRun, ResearchExecutionSnapshot, ResearchStep, ResearchStepAttempt, list[ResearchExecutionAsset]]:
    run, step, attempt = _active_attempt_chain(db, attempt_id, now=now)
    snapshot = db.get(ResearchExecutionSnapshot, execution_snapshot_id)
    if (
        run.id != run_id
        or step.id != step_id
        or step.branch_key != branch_key
        or step.step_kind != "researcher"
        or step.execution_snapshot_id != execution_snapshot_id
        or snapshot is None
        or snapshot.run_id != run.id
        or snapshot.workspace_id != run.workspace_id
        or run.approved_execution_snapshot_id != snapshot.id
    ):
        raise ResearchError("tool_scope_violation", "Research Evidence tool scope is invalid.", 409)
    assets = list(
        db.scalars(
            select(ResearchExecutionAsset)
            .where(ResearchExecutionAsset.execution_snapshot_id == snapshot.id)
            .order_by(ResearchExecutionAsset.asset_order)
        ).all()
    )
    if any(item.workspace_id != run.workspace_id for item in assets):
        raise ResearchError("tool_scope_violation", "Frozen Research Asset scope is invalid.", 409)
    return run, snapshot, step, attempt, assets


def _frozen_evidence_value(
    db: Session,
    handle: ResearchEvidenceHandle,
    *,
    branch_key: str,
    score: float = 0.0,
) -> FrozenEvidence:
    evidence = db.get(ResearchEvidenceSnapshot, handle.evidence_snapshot_id)
    representation = db.get(AssetRepresentation, evidence.representation_id_snapshot) if evidence else None
    if (
        evidence is None
        or representation is None
        or handle.workspace_id != evidence.workspace_id
        or handle.run_id != evidence.run_id
        or representation.id != evidence.representation_id_snapshot
        or representation.workspace_id != evidence.workspace_id
        or representation.asset_id != evidence.asset_id
        or representation.processing_generation != evidence.processing_generation_snapshot
    ):
        raise ResearchError("research_state_conflict", "Persisted Research Evidence is invalid.", 409)
    locator_row = serialize_evidence_locator(
        db,
        evidence.evidence_locator_id,
        workspace_id=evidence.workspace_id,
        asset_id=evidence.asset_id,
        processing_generation=evidence.processing_generation_snapshot,
        representation_id=evidence.representation_id_snapshot,
    )
    _require_valid_evidence_source(evidence, locator_kind=locator_row.kind)
    return FrozenEvidence(
        evidence_handle=handle.id,
        workspace_id=handle.workspace_id,
        run_id=handle.run_id,
        execution_snapshot_id=handle.execution_snapshot_id,
        owner_step_id=handle.owner_step_id,
        branch_key=branch_key,
        asset_id=evidence.asset_id,
        asset_kind=evidence.asset_kind_snapshot,
        asset_title=evidence.asset_title_snapshot,
        excerpt=evidence.excerpt_snapshot,
        processing_generation=evidence.processing_generation_snapshot,
        index_version=evidence.index_version_snapshot,
        representation_id=evidence.representation_id_snapshot,
        parser_version=evidence.parser_version_snapshot,
        locator_id=evidence.evidence_locator_id,
        locator_kind=locator_row.kind,
        source_fingerprint_sha256=evidence.source_fingerprint_sha256,
        created_by_tool_call_id=handle.created_by_tool_call_id,
        score=score,
    )


def _require_valid_evidence_source(
    evidence: ResearchEvidenceSnapshot,
    *,
    locator_kind: str,
) -> None:
    try:
        validate_evidence_source_fingerprint(evidence, locator_kind=locator_kind)
    except ValueError as error:
        raise ResearchError(
            "research_state_conflict",
            "Persisted Research Evidence fingerprint is invalid.",
            409,
        ) from error


def _replay_successful_tool_call(
    db: Session,
    *,
    step_id: str,
    tool_call_key: str,
    tool_name: str,
    request_sha256: str,
) -> ResearchToolCall | None:
    call = db.scalar(
        select(ResearchToolCall).where(
            ResearchToolCall.step_id == step_id,
            ResearchToolCall.tool_call_key == tool_call_key,
            ResearchToolCall.status == "succeeded",
        )
    )
    if call is not None and (call.tool_name != tool_name or call.request_sha256 != request_sha256):
        raise ResearchError("research_state_conflict", "Research tool replay input changed.", 409)
    return call


def search_frozen_evidence(
    db: Session,
    *,
    run_id: str,
    execution_snapshot_id: str,
    step_id: str,
    attempt_id: str,
    branch_key: str,
    tool_call_key: str,
    query: str,
    asset_ids: Sequence[str],
    top_k: int,
    embedding_provider: EmbeddingProvider | None = None,
    now: datetime | None = None,
) -> list[FrozenEvidence]:
    called_at = now or datetime.now(UTC)
    run, snapshot, step, _attempt, frozen_assets = _frozen_execution_context(
        db,
        run_id=run_id,
        execution_snapshot_id=execution_snapshot_id,
        step_id=step_id,
        attempt_id=attempt_id,
        branch_key=branch_key,
        now=called_at,
    )
    normalized_query = query.strip()
    requested_asset_ids = list(asset_ids)
    frozen_asset_ids = {item.asset_id for item in frozen_assets}
    if (
        not normalized_query
        or len(normalized_query) > 4000
        or not 1 <= top_k <= 20
        or len(requested_asset_ids) > 100
        or len(requested_asset_ids) != len(set(requested_asset_ids))
    ):
        raise ResearchError("tool_input_invalid", "Research Evidence search input is invalid.", 422)
    if not set(requested_asset_ids).issubset(frozen_asset_ids):
        raise ResearchError("tool_scope_violation", "Research Evidence search exceeds frozen scope.", 409)
    effective_asset_ids = requested_asset_ids or [item.asset_id for item in frozen_assets]
    request_sha256 = canonical_sha256(
        {"query": normalized_query, "assetIds": requested_asset_ids, "topK": top_k}
    )
    replay = _replay_successful_tool_call(
        db,
        step_id=step.id,
        tool_call_key=tool_call_key,
        tool_name="evidence.search",
        request_sha256=request_sha256,
    )
    if replay is not None:
        handles = list(
            db.scalars(
                select(ResearchEvidenceHandle)
                .where(ResearchEvidenceHandle.created_by_tool_call_id == replay.id)
                .order_by(ResearchEvidenceHandle.result_order)
            ).all()
        )
        return [_frozen_evidence_value(db, handle, branch_key=branch_key) for handle in handles]
    if embedding_provider is None:
        from ai_pdf_api.services.capabilities import matches_frozen_execution_fingerprint

        if not matches_frozen_execution_fingerprint(
            snapshot.provider_config_fingerprint,
            retrieval_top_k=snapshot.retrieval_top_k,
        ):
            raise ResearchError(
                "research_provider_config_drift",
                "Actual provider capability profile does not match the frozen Research fingerprint.",
                409,
            )
        provider = get_embedding_provider()
    else:
        # Explicit test-only/injected provider path: skip live capability fingerprint dual-read.
        provider = embedding_provider
    if (
        provider.provider != snapshot.embedding_provider
        or provider.model != snapshot.embedding_model
        or provider.version != snapshot.embedding_version
    ):
        raise ResearchError("tool_scope_violation", "Embedding provider does not match the frozen execution.", 409)
    reservation = begin_tool_call(
        db,
        attempt_id=attempt_id,
        tool_call_key=tool_call_key,
        tool_name="evidence.search",
        request_sha256=request_sha256,
        now=called_at,
    )
    try:
        query_embedding = provider.embed_query(normalized_query)
        results = retrieve_query_content(
            db,
            run.workspace_id,
            normalized_query,
            query_embedding,
            asset_ids=effective_asset_ids,
            embedding_provider=provider,
            limit=min(top_k, snapshot.retrieval_top_k),
            strategy=snapshot.retrieval_strategy,
        )
        frozen_by_asset = {item.asset_id: item for item in frozen_assets}
        values: list[FrozenEvidence] = []

        def persist_results(session: Session, call: ResearchToolCall) -> int:
            for result_order, result in enumerate(results):
                frozen = frozen_by_asset.get(result.asset.id)
                representation = session.get(AssetRepresentation, result.content_unit.representation_id)
                if (
                    frozen is None
                    or representation is None
                    or result.asset.workspace_id != run.workspace_id
                    or result.asset.current_processing_generation != frozen.processing_generation_snapshot
                    or result.asset.current_index_version != frozen.index_version_snapshot
                    or result.content_unit.index_version != frozen.index_version_snapshot
                    or representation.processing_generation != frozen.processing_generation_snapshot
                ):
                    raise ResearchError("tool_scope_violation", "Retrieved Evidence escaped frozen scope.", 409)
                excerpt = result.content_unit.text_content[:2000]
                locator = clone_evidence_locator(
                    session,
                    result.locator.id,
                    created_at=called_at,
                    workspace_id=run.workspace_id,
                    asset_id=result.asset.id,
                    processing_generation=frozen.processing_generation_snapshot,
                    representation_id=representation.id,
                )
                evidence = ResearchEvidenceSnapshot(
                    workspace_id=run.workspace_id,
                    run_id=run.id,
                    captured_by_step_id=step.id,
                    evidence_locator_id=locator.id,
                    asset_id=result.asset.id,
                    asset_kind_snapshot=frozen.asset_kind_snapshot,
                    asset_title_snapshot=frozen.asset_title_snapshot,
                    excerpt_snapshot=excerpt,
                    processing_generation_snapshot=frozen.processing_generation_snapshot,
                    representation_id_snapshot=representation.id,
                    parser_version_snapshot=representation.generator_version,
                    index_version_snapshot=frozen.index_version_snapshot,
                    retrieval_channel=result.channel,
                    source_fingerprint_sha256="pending",
                    created_at=called_at,
                )
                evidence.source_fingerprint_sha256 = evidence_source_fingerprint(
                    evidence,
                    locator_kind=locator.locator_kind,
                )
                session.add(evidence)
                session.flush()
                handle_fingerprint = canonical_sha256(
                    {
                        "runId": run.id,
                        "executionSnapshotId": snapshot.id,
                        "stepId": step.id,
                        "toolCallId": call.id,
                        "evidenceSnapshotId": evidence.id,
                        "resultOrder": result_order,
                    }
                )
                handle = ResearchEvidenceHandle(
                    workspace_id=run.workspace_id,
                    run_id=run.id,
                    execution_snapshot_id=snapshot.id,
                    owner_step_id=step.id,
                    created_by_tool_call_id=call.id,
                    evidence_snapshot_id=evidence.id,
                    result_order=result_order,
                    handle_fingerprint_sha256=handle_fingerprint,
                    created_at=called_at,
                )
                session.add(handle)
                session.flush()
                score = 1.0 - float(result.distance)
                if not math.isfinite(score):
                    raise ResearchError("tool_scope_violation", "Research Evidence score is invalid.", 409)
                values.append(_frozen_evidence_value(session, handle, branch_key=branch_key, score=score))
            return len(results)

        complete_tool_call(
            db,
            tool_call_id=reservation.tool_call_id,
            status="succeeded",
            complete=persist_results,
            now=called_at,
        )
        return values
    except ModelProviderError as error:
        db.rollback()
        call = db.get(ResearchToolCall, reservation.tool_call_id)
        if error.code == EMBEDDING_INDEX_MISMATCH_CODE:
            if call is not None and call.status in {"requested", "running"}:
                complete_tool_call(
                    db,
                    tool_call_id=call.id,
                    status="failed",
                    error_code=error.code,
                    error_message=error.message,
                    now=called_at,
                )
            # Non-retryable configuration/index drift: preserve reindex-required meaning.
            raise ResearchError(error.code, error.message, 409) from error
        if call is not None and call.status in {"requested", "running"}:
            complete_tool_call(
                db,
                tool_call_id=call.id,
                status="failed",
                error_code="tool_temporarily_unavailable",
                error_message="Evidence search failed.",
                now=called_at,
            )
        raise
    except Exception:
        db.rollback()
        call = db.get(ResearchToolCall, reservation.tool_call_id)
        if call is not None and call.status in {"requested", "running"}:
            complete_tool_call(
                db,
                tool_call_id=call.id,
                status="failed",
                error_code="tool_temporarily_unavailable",
                error_message="Evidence search failed.",
                now=called_at,
            )
        raise


def load_frozen_evidence(
    db: Session,
    *,
    run_id: str,
    execution_snapshot_id: str,
    step_id: str,
    attempt_id: str,
    branch_key: str,
    tool_call_key: str,
    evidence_handle_ids: Sequence[str],
    now: datetime | None = None,
) -> list[LoadedFrozenEvidence]:
    called_at = now or datetime.now(UTC)
    run, snapshot, step, _attempt, _assets = _frozen_execution_context(
        db,
        run_id=run_id,
        execution_snapshot_id=execution_snapshot_id,
        step_id=step_id,
        attempt_id=attempt_id,
        branch_key=branch_key,
        now=called_at,
    )
    handle_ids = list(evidence_handle_ids)
    if not 1 <= len(handle_ids) <= 20 or len(handle_ids) != len(set(handle_ids)):
        raise ResearchError("tool_input_invalid", "Research Evidence load input is invalid.", 422)
    request_sha256 = canonical_sha256({"evidenceHandles": handle_ids})
    replay = _replay_successful_tool_call(
        db,
        step_id=step.id,
        tool_call_key=tool_call_key,
        tool_name="evidence.load",
        request_sha256=request_sha256,
    )
    handles = list(
        db.scalars(
            select(ResearchEvidenceHandle).where(ResearchEvidenceHandle.id.in_(handle_ids))
        ).all()
    )
    by_id = {handle.id: handle for handle in handles}
    ordered_handles = [by_id.get(handle_id) for handle_id in handle_ids]
    if any(
        handle is None
        or handle.workspace_id != run.workspace_id
        or handle.run_id != run.id
        or handle.execution_snapshot_id != snapshot.id
        or handle.owner_step_id != step.id
        for handle in ordered_handles
    ):
        raise ResearchError("evidence_handle_not_found", "Research Evidence handle was not found.", 404)
    values: list[LoadedFrozenEvidence] = []
    for handle in ordered_handles:
        assert handle is not None
        evidence = db.get(ResearchEvidenceSnapshot, handle.evidence_snapshot_id)
        asset = db.get(Asset, evidence.asset_id) if evidence else None
        if evidence is None or evidence.run_id != run.id or evidence.workspace_id != run.workspace_id:
            raise ResearchError("research_state_conflict", "Research Evidence snapshot scope is invalid.", 409)
        locator = serialize_evidence_locator(
            db,
            evidence.evidence_locator_id,
            workspace_id=run.workspace_id,
            asset_id=evidence.asset_id,
            processing_generation=evidence.processing_generation_snapshot,
            representation_id=evidence.representation_id_snapshot,
        )
        _require_valid_evidence_source(evidence, locator_kind=locator.kind)
        source_available = bool(
            asset is not None
            and asset.deleted_at is None
            and asset.status == "ready"
            and asset.current_processing_generation == evidence.processing_generation_snapshot
            and asset.current_index_version == evidence.index_version_snapshot
        )
        values.append(
            LoadedFrozenEvidence(
                evidence_handle=handle.id,
                asset_id=evidence.asset_id,
                asset_kind=evidence.asset_kind_snapshot,
                asset_title=evidence.asset_title_snapshot,
                source_available=source_available,
                content=evidence.excerpt_snapshot,
                content_sha256=hashlib.sha256(evidence.excerpt_snapshot.encode("utf-8")).hexdigest(),
                processing_generation=evidence.processing_generation_snapshot,
                index_version=evidence.index_version_snapshot,
                representation_id=evidence.representation_id_snapshot,
                parser_version=evidence.parser_version_snapshot,
                locator_id=evidence.evidence_locator_id,
                locator_kind=locator.kind,
            )
        )
    if replay is not None:
        replay_inputs = list(
            db.scalars(
                select(ResearchToolCallInputHandle.evidence_handle_id)
                .where(ResearchToolCallInputHandle.tool_call_id == replay.id)
                .order_by(ResearchToolCallInputHandle.input_order)
            ).all()
        )
        if replay_inputs != handle_ids:
            raise ResearchError("research_state_conflict", "Research Evidence load replay changed.", 409)
        return values
    reservation = begin_tool_call(
        db,
        attempt_id=attempt_id,
        tool_call_key=tool_call_key,
        tool_name="evidence.load",
        request_sha256=request_sha256,
        now=called_at,
    )

    def persist_inputs(session: Session, call: ResearchToolCall) -> int:
        session.add_all(
            [
                ResearchToolCallInputHandle(
                    tool_call_id=call.id,
                    evidence_handle_id=handle_id,
                    input_order=index,
                )
                for index, handle_id in enumerate(handle_ids)
            ]
        )
        return len(handle_ids)

    complete_tool_call(
        db,
        tool_call_id=reservation.tool_call_id,
        status="succeeded",
        complete=persist_inputs,
        now=called_at,
    )
    return values


def restore_frozen_evidence(
    db: Session,
    *,
    run_id: str,
    execution_snapshot_id: str,
    owner_step_id: str,
) -> list[FrozenEvidence]:
    step = db.get(ResearchStep, owner_step_id)
    handles = restore_evidence_handles(
        db,
        run_id=run_id,
        execution_snapshot_id=execution_snapshot_id,
        owner_step_id=owner_step_id,
    )
    assert step is not None and step.branch_key is not None
    return [
        _frozen_evidence_value(db, handle, branch_key=step.branch_key)
        for handle in handles
    ]
