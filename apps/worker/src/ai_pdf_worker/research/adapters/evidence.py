from __future__ import annotations

from collections.abc import Sequence
from citeframe_contracts import (
    EvidenceHandle,
    EvidenceToolPort,
    LoadedEvidence,
    ToolExecutionContext,
)
from ai_pdf_worker.research.core import (
    ResearchPortError,
    ResearchWorkerService,
    SessionFactory,
    _ApiPort,
    _evidence_handle,
    _loaded_evidence,
    _now,
    _observed_tool,
)


class SqlEvidenceToolPort(_ApiPort, EvidenceToolPort):
    """Evidence-only port backed by frozen API retrieval and handle ledgers."""

    def __init__(
        self, sessions: SessionFactory, service: ResearchWorkerService
    ) -> None:
        super().__init__(sessions, service)

    def restore_handles(
        self, context: ToolExecutionContext
    ) -> Sequence[EvidenceHandle]:
        rows = self._call(
            "restore_frozen_evidence",
            run_id=context.run_id,
            execution_snapshot_id=context.execution_snapshot_id,
            owner_step_id=context.step_id,
        )
        handles = tuple(_evidence_handle(item) for item in rows)
        self._validate_handles(context, handles)
        return handles

    def search(
        self,
        context: ToolExecutionContext,
        *,
        tool_call_key: str,
        query: str,
        asset_ids: Sequence[str],
        top_k: int,
    ) -> Sequence[EvidenceHandle]:
        with _observed_tool(context, "evidence.search") as observation:
            rows = self._call(
                "search_frozen_evidence",
                write=True,
                run_id=context.run_id,
                execution_snapshot_id=context.execution_snapshot_id,
                step_id=context.step_id,
                attempt_id=context.attempt_id,
                branch_key=context.branch_key,
                tool_call_key=tool_call_key,
                query=query,
                asset_ids=tuple(asset_ids),
                top_k=top_k,
                now=_now(),
            )
            handles = tuple(_evidence_handle(item) for item in rows)
            self._validate_handles(context, handles)
            observation.evidence_count = len(handles)
            return handles

    def load(
        self,
        context: ToolExecutionContext,
        *,
        tool_call_key: str,
        handle_ids: Sequence[str],
    ) -> Sequence[LoadedEvidence]:
        with _observed_tool(context, "evidence.load") as observation:
            rows = self._call(
                "load_frozen_evidence",
                write=True,
                run_id=context.run_id,
                execution_snapshot_id=context.execution_snapshot_id,
                step_id=context.step_id,
                attempt_id=context.attempt_id,
                branch_key=context.branch_key,
                tool_call_key=tool_call_key,
                evidence_handle_ids=tuple(handle_ids),
                now=_now(),
            )
            items = tuple(_loaded_evidence(item) for item in rows)
            if [item.evidence_handle for item in items] != list(handle_ids):
                raise ResearchPortError("evidence_load_order_mismatch")
            observation.evidence_count = len(items)
            return items

    @staticmethod
    def _validate_handles(
        context: ToolExecutionContext, handles: Sequence[EvidenceHandle]
    ) -> None:
        frozen = {item.asset_id: item for item in context.frozen_assets}
        for handle in handles:
            asset = frozen.get(handle.asset_id)
            if (
                handle.workspace_id != context.workspace_id
                or handle.run_id != context.run_id
                or handle.execution_snapshot_id != context.execution_snapshot_id
                or handle.owner_step_id != context.step_id
                or handle.branch_key != context.branch_key
                or asset is None
                or handle.processing_generation != asset.processing_generation
                or handle.index_version != asset.index_version
                or len(handle.source_fingerprint_sha256) != 64
                or not handle.created_by_tool_call_id
            ):
                raise ResearchPortError("evidence_handle_scope_mismatch")
