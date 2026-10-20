"""Exact current shared native sources, under already-held owner/member guards."""
from sqlalchemy import select
from citeframe_contracts.compaction import SourceReference
from citeframe_persistence.models import (Asset, ChatMessage, MemorySource, ResearchEvidenceHandle,
                                         ResearchEvidenceSnapshot, ResearchExecutionAsset)
from .guards import body_hash, lock_one
from .policy import CompactionError


def native_source(guard, kind, native_id):
    db, owner = guard.db, guard.owner
    if kind == "chat_message" and owner.kind == "chat":
        # The full-thread manifest contains siblings only as metadata. Read bodies only on ancestry.
        if native_id not in guard.ancestry:
            raise CompactionError("source_branch_mismatch")
        row = lock_one(db, ChatMessage, native_id)
        if (row is None or row.workspace_id != owner.workspace_id or row.thread_id != guard.thread.id
                or row.status not in ("completed", "failed") or row.role not in ("user", "assistant")):
            raise CompactionError("source_unavailable")
        version = dict(messageId=row.id, parentMessageId=row.parent_message_id, role=row.role,
                       status=row.status, contentSha256=body_hash(row.content),
                       compactionRevision=row.compaction_revision)
        return row.content, version, row.compaction_revision
    if kind == "research_evidence" and owner.kind == "research":
        handle = lock_one(db, ResearchEvidenceHandle, native_id)
        if (handle is None or handle.workspace_id != owner.workspace_id or handle.run_id != guard.run.id
                or handle.owner_step_id != guard.step.id
                or handle.execution_snapshot_id != guard.step.execution_snapshot_id):
            raise CompactionError("source_frozen_scope_mismatch")
        evidence = lock_one(db, ResearchEvidenceSnapshot, handle.evidence_snapshot_id)
        if evidence is None or evidence.run_id != guard.run.id or evidence.workspace_id != owner.workspace_id:
            raise CompactionError("source_unavailable")
        asset = lock_one(db, Asset, evidence.asset_id)
        if asset is None or asset.workspace_id != owner.workspace_id or asset.status != "ready" or asset.deleted_at:
            raise CompactionError("source_unavailable")
        membership=db.scalar(select(ResearchExecutionAsset).where(
            ResearchExecutionAsset.execution_snapshot_id==handle.execution_snapshot_id,
            ResearchExecutionAsset.asset_id==asset.id).with_for_update(nowait=True))
        if (membership is None or membership.workspace_id!=owner.workspace_id
                or membership.processing_generation_snapshot!=evidence.processing_generation_snapshot
                or membership.index_version_snapshot!=evidence.index_version_snapshot):
            raise CompactionError("source_frozen_scope_mismatch")
        version = dict(runId=guard.run.id, executionSnapshotId=handle.execution_snapshot_id,
                       evidenceSnapshotId=evidence.id, evidenceHandleId=handle.id,
                       sourceFingerprintSha256=evidence.source_fingerprint_sha256)
        return evidence.excerpt_snapshot, version, 1
    raise CompactionError("shared_source_kind_forbidden")


def read_registered(guard, reference: SourceReference):
    source = lock_one(guard.db, MemorySource, reference.source_id)
    if (source is None or source.workspace_id != guard.owner.workspace_id or source.audience != "workspace"
            or source.kind not in ("chat_message", "research_evidence") or source.state != "current"
            or source.source_version != reference.version or source.content_sha256 != reference.sha256):
        raise CompactionError("shared_source_unavailable")
    body, version, revision = native_source(guard, source.kind, source.native_id)
    if source.native_version != version or source.source_version != revision or body_hash(body) != reference.sha256:
        raise CompactionError("source_version_changed")
    return body, source
