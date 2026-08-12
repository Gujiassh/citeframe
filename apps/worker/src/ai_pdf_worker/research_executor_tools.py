from __future__ import annotations

from collections.abc import Sequence
from threading import Lock

from ai_pdf_worker.research_executor_contracts import (
    BranchResult,
    DraftClaim,
    EvidenceHandle,
    EvidenceToolPort,
    LoadedEvidence,
    ResearchExecutionError,
    ToolExecutionContext,
    ToolPolicyError,
)


class EvidenceToolRegistry:
    def __init__(self, port: EvidenceToolPort, context: ToolExecutionContext) -> None:
        self._port = port
        self._context = context
        self._issued: dict[str, EvidenceHandle] = {}
        self._call_order = 0
        self._lock = Lock()
        restored = tuple(self._port.restore_handles(context))
        self._accept_scoped_handles(restored)

    def search(
        self,
        *,
        query: str,
        asset_ids: Sequence[str] = (),
        top_k: int,
    ) -> tuple[EvidenceHandle, ...]:
        normalized_query = query.strip()
        requested_assets = tuple(asset_ids)
        frozen_ids = {asset.asset_id for asset in self._context.frozen_assets}
        if not normalized_query or len(normalized_query) > 4000:
            raise ToolPolicyError("tool_input_invalid")
        if not 1 <= top_k <= 20:
            raise ToolPolicyError("tool_input_invalid")
        if len(requested_assets) > 100 or len(set(requested_assets)) != len(requested_assets):
            raise ToolPolicyError("tool_input_invalid")
        if not set(requested_assets).issubset(frozen_ids):
            raise ToolPolicyError("tool_scope_violation")
        handles = tuple(
            self._port.search(
                self._context,
                tool_call_key=self._next_call_key("evidence.search"),
                query=normalized_query,
                asset_ids=requested_assets,
                top_k=top_k,
            )
        )
        if len(handles) > top_k:
            raise ToolPolicyError("tool_result_invalid")
        self._accept_scoped_handles(handles)
        return handles

    def load(self, *, evidence_handles: Sequence[str]) -> tuple[LoadedEvidence, ...]:
        handle_ids = tuple(evidence_handles)
        if not 1 <= len(handle_ids) <= 20 or len(set(handle_ids)) != len(handle_ids):
            raise ToolPolicyError("tool_input_invalid")
        with self._lock:
            known = {handle_id: self._issued.get(handle_id) for handle_id in handle_ids}
        if any(handle is None for handle in known.values()):
            raise ToolPolicyError("evidence_handle_not_found")
        loaded = tuple(
            self._port.load(
                self._context,
                tool_call_key=self._next_call_key("evidence.load"),
                handle_ids=handle_ids,
            )
        )
        if [item.evidence_handle for item in loaded] != list(handle_ids):
            raise ToolPolicyError("tool_result_invalid")
        for item in loaded:
            source = known[item.evidence_handle]
            assert source is not None
            if (
                item.asset_id != source.asset_id
                or item.processing_generation != source.processing_generation
                or item.index_version != source.index_version
                or item.representation_id != source.representation_id
                or item.parser_version != source.parser_version
                or item.locator_id != source.locator_id
                or item.locator_kind != source.locator_kind
                or len(item.content) > 12000
                or len(item.content_sha256) != 64
            ):
                raise ToolPolicyError("tool_scope_violation")
        return loaded

    def validate_branch_result(self, result: BranchResult) -> None:
        if result.branch_key != self._context.branch_key:
            raise ResearchExecutionError("researcher_branch_mismatch")
        evidence_ids = [item.id for item in result.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ResearchExecutionError("duplicate_branch_evidence")
        with self._lock:
            issued = dict(self._issued)
        for evidence in result.evidence:
            if issued.get(evidence.id) != evidence:
                raise ResearchExecutionError("unproven_branch_evidence")
        _validate_claims(result.claims, set(evidence_ids))

    def _next_call_key(self, tool_name: str) -> str:
        with self._lock:
            self._call_order += 1
            return f"{tool_name}:{self._call_order}"

    def _accept_scoped_handles(self, handles: Sequence[EvidenceHandle]) -> None:
        frozen = {asset.asset_id: asset for asset in self._context.frozen_assets}
        for handle in handles:
            asset = frozen.get(handle.asset_id)
            if (
                handle.workspace_id != self._context.workspace_id
                or handle.run_id != self._context.run_id
                or handle.execution_snapshot_id != self._context.execution_snapshot_id
                or handle.owner_step_id != self._context.step_id
                or handle.branch_key != self._context.branch_key
                or asset is None
                or handle.processing_generation != asset.processing_generation
                or handle.index_version != asset.index_version
                or handle.locator_kind
                not in {"pdf_page", "pdf_region", "image_region", "document_anchor"}
                or len(handle.source_fingerprint_sha256) != 64
                or not handle.created_by_tool_call_id
            ):
                raise ToolPolicyError("tool_scope_violation")
        with self._lock:
            for handle in handles:
                previous = self._issued.get(handle.id)
                if previous is not None and previous != handle:
                    raise ToolPolicyError("evidence_handle_changed")
                self._issued[handle.id] = handle


def _validate_claims(claims: Sequence[DraftClaim], evidence_ids: set[str]) -> None:
    claim_ids = [claim.id for claim in claims]
    if len(claim_ids) != len(set(claim_ids)):
        raise ResearchExecutionError("duplicate_claim_id")
    for claim in claims:
        if not claim.text.strip() or len(claim.text) > 12000:
            raise ResearchExecutionError("invalid_claim")
        if not claim.evidence_handle_ids:
            raise ResearchExecutionError("claim_requires_evidence")
        if len(claim.evidence_handle_ids) != len(set(claim.evidence_handle_ids)):
            raise ResearchExecutionError("duplicate_claim_evidence")
        if not set(claim.evidence_handle_ids).issubset(evidence_ids):
            raise ResearchExecutionError("claim_evidence_not_in_branch")
