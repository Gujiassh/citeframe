"""Validate journal source references against frozen evidence and its tool ledger."""

import hashlib

from sqlalchemy import select
from citeframe_persistence.models import (
    ResearchClaimEvidence,
    ResearchEvidenceHandle,
    ResearchEvidenceSnapshot,
    ResearchExecutionAsset,
    ResearchToolCall,
    EvidenceLocator,
    ResearchStep,
    ResearchStepAttempt,
)
from .errors import ResearchError
from .evidence import validate_evidence_source_fingerprint
from .publication_adoption import tool_attempt_is_replayable


def validate_sources(db, step, originals, outcome):
    def invalid():
        raise ResearchError(
            "research_state_conflict", "Investigation source provenance changed.", 409
        )

    original_values = {c["id"]: c for c in outcome["originalClaims"]}
    if len(original_values) != len(outcome["originalClaims"]):
        invalid()
    for claim in originals:
        if original_values[claim.id]["text"] != claim.statement_text:
            invalid()
    sources = {}
    for value in outcome["evidence"]:
        handle = db.get(ResearchEvidenceHandle, value["id"], populate_existing=True)
        evidence = (
            db.get(
                ResearchEvidenceSnapshot,
                handle.evidence_snapshot_id,
                populate_existing=True,
            )
            if handle
            else None
        )
        tool = (
            db.get(
                ResearchToolCall, handle.created_by_tool_call_id, populate_existing=True
            )
            if handle
            else None
        )
        producer = db.get(ResearchStep, handle.owner_step_id) if handle else None
        current = (
            db.scalar(
                select(ResearchStepAttempt).where(
                    ResearchStepAttempt.step_id == producer.id,
                    ResearchStepAttempt.attempt_number
                    == producer.current_attempt_number,
                )
            )
            if producer
            else None
        )
        live_gate = bool(
            producer
            and current
            and producer.id == step.id
            and current.status == "running"
            and producer.status == "running"
            and current.workspace_id == step.workspace_id
            and current.finished_at is None
            and tool
            and tool.attempt_id == current.id
            and tool.tool_name == "evidence.search"
            and current.input_sha256
            == (
                producer.input_sha256
                or hashlib.sha256(producer.id.encode("utf-8")).hexdigest()
            )
        )
        replay = bool(
            producer
            and current
            and tool
            and tool_attempt_is_replayable(db, tool, producer, current)
        )
        if (
            handle is None
            or evidence is None
            or tool is None
            or value["id"] in sources
            or handle.run_id != step.run_id
            or handle.workspace_id != step.workspace_id
            or handle.execution_snapshot_id != step.execution_snapshot_id
            or evidence.run_id != step.run_id
            or evidence.workspace_id != step.workspace_id
            or evidence.captured_by_step_id != handle.owner_step_id
            or tool.workspace_id != step.workspace_id
            or tool.tool_version != 1
            or tool.error_code is not None
            or tool.error_message is not None
            or tool.status != "succeeded"
            or tool.run_id != step.run_id
            or tool.execution_snapshot_id != step.execution_snapshot_id
            or tool.step_id != handle.owner_step_id
            or not (live_gate or replay)
        ):
            invalid()
        expected = {
            "asset_id": evidence.asset_id,
            "excerpt": evidence.excerpt_snapshot,
            "processing_generation": evidence.processing_generation_snapshot,
            "index_version": evidence.index_version_snapshot,
            "representation_id": evidence.representation_id_snapshot,
            "parser_version": evidence.parser_version_snapshot,
            "locator_id": evidence.evidence_locator_id,
            "source_fingerprint_sha256": evidence.source_fingerprint_sha256,
            "created_by_tool_call_id": handle.created_by_tool_call_id,
            "owner_step_id": handle.owner_step_id,
            "workspace_id": step.workspace_id,
            "run_id": step.run_id,
            "execution_snapshot_id": step.execution_snapshot_id,
        }
        if any(value.get(k) != v for k, v in expected.items()):
            invalid()
        asset = db.scalar(
            select(ResearchExecutionAsset).where(
                ResearchExecutionAsset.execution_snapshot_id
                == step.execution_snapshot_id,
                ResearchExecutionAsset.asset_id == evidence.asset_id,
            )
        )
        locator = db.get(EvidenceLocator, evidence.evidence_locator_id)
        if (
            asset is None
            or locator is None
            or value["locator_kind"] != locator.locator_kind
            or asset.processing_generation_snapshot
            != evidence.processing_generation_snapshot
            or asset.index_version_snapshot != evidence.index_version_snapshot
        ):
            invalid()
        try:
            validate_evidence_source_fingerprint(
                evidence, locator_kind=locator.locator_kind
            )
        except ValueError:
            invalid()
        sources[handle.id] = evidence.id
    for claim in originals:
        ids = original_values[claim.id]["evidenceHandleIds"]
        linked = set(
            db.scalars(
                select(ResearchClaimEvidence.evidence_snapshot_id).where(
                    ResearchClaimEvidence.claim_id == claim.id
                )
            )
        )
        if (
            not ids
            or not set(ids).issubset(sources)
            or {sources[i] for i in ids} != linked
        ):
            invalid()
