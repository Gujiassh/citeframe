from __future__ import annotations

import hashlib
from collections.abc import Sequence
from threading import Lock
from ai_pdf_api.services.research.research_prompt_provenance import (
    V2_WORKFLOW_VERSION_ID,
)
from citeframe_evaluation.contracts import EvaluationPackage
from citeframe_evaluation.provider import frozen_v2_prompts
from ai_pdf_worker.research.executor import (
    ApprovedResearchExecution,
    EvidenceHandle,
    FrozenAsset,
    LoadedEvidence,
    StepLease,
    ToolExecutionContext,
)


class FrozenEvidencePort:
    def __init__(self, package: EvaluationPackage) -> None:
        self._package = package
        self._issued: dict[str, tuple[EvidenceHandle, str]] = {}
        self._lock = Lock()

    def restore_handles(
        self, context: ToolExecutionContext
    ) -> tuple[EvidenceHandle, ...]:
        del context
        return ()

    def search(
        self,
        context: ToolExecutionContext,
        *,
        tool_call_key: str,
        query: str,
        asset_ids: Sequence[str],
        top_k: int,
    ) -> tuple[EvidenceHandle, ...]:
        del query
        scoped_assets = (
            set(asset_ids)
            if asset_ids
            else {item.asset_id for item in context.frozen_assets}
        )
        items = [
            item
            for item in self._package.evidence.values()
            if item.asset_id in scoped_assets
        ]
        handles: list[EvidenceHandle] = []
        for item in sorted(items, key=lambda value: value.id)[:top_k]:
            handle_id = (
                "handle-"
                + hashlib.sha256(f"{context.step_id}:{item.id}".encode()).hexdigest()[
                    :24
                ]
            )
            handle = EvidenceHandle(
                id=handle_id,
                workspace_id=context.workspace_id,
                run_id=context.run_id,
                execution_snapshot_id=context.execution_snapshot_id,
                owner_step_id=context.step_id,
                branch_key=context.branch_key,
                asset_id=item.asset_id,
                processing_generation=1,
                index_version=1,
                representation_id=f"fixture:{item.asset_id}",
                parser_version="r803-evidence-v1",
                locator_id=f"fixture:{item.asset_id}:{item.locator_key}",
                locator_kind=item.locator_kind,
                excerpt=item.content,
                source_fingerprint_sha256=item.source_fingerprint_sha256,
                created_by_tool_call_id=tool_call_key,
            )
            handles.append(handle)
            with self._lock:
                self._issued[handle_id] = (handle, item.id)
        return tuple(handles)

    def load(
        self,
        context: ToolExecutionContext,
        *,
        tool_call_key: str,
        handle_ids: Sequence[str],
    ) -> tuple[LoadedEvidence, ...]:
        del context, tool_call_key
        loaded: list[LoadedEvidence] = []
        with self._lock:
            issued = dict(self._issued)
        for handle_id in handle_ids:
            handle, evidence_id = issued[handle_id]
            item = self._package.evidence[evidence_id]
            loaded.append(
                LoadedEvidence(
                    evidence_handle=handle.id,
                    asset_id=handle.asset_id,
                    processing_generation=handle.processing_generation,
                    index_version=handle.index_version,
                    representation_id=handle.representation_id,
                    parser_version=handle.parser_version,
                    locator_id=handle.locator_id,
                    locator_kind=handle.locator_kind,
                    content=item.content,
                    content_sha256=hashlib.sha256(
                        item.content.encode("utf-8")
                    ).hexdigest(),
                    source_available=True,
                )
            )
        return tuple(loaded)

    def evidence_id(self, handle_id: str) -> str:
        with self._lock:
            return self._issued[handle_id][1]


def build_execution(
    package: EvaluationPackage, case: dict[str, object]
) -> ApprovedResearchExecution:
    prompts = frozen_v2_prompts()
    assets = tuple(FrozenAsset(asset_id, 1, 1) for asset_id in case["assetScope"])
    return ApprovedResearchExecution(
        workspace_id="r803-evaluation",
        run_id=f"r803:{case['id']}",
        execution_snapshot_id=f"r803:{case['id']}:snapshot",
        snapshot_sha256=package.sha256,
        question=str(case["question"]),
        subproblems=(),
        frozen_assets=assets,
        workflow_version_id=V2_WORKFLOW_VERSION_ID,
        prompt_version_ids=tuple(item.prompt_version_id for item in prompts),
        provider_config_fingerprint=package.comparison_keys.provider_profile_sha256,
        budget_policy_version="budget-v1",
        retry_policy_version=package.document["executionPolicy"]["retryPolicyVersion"],
        max_parallel_researchers=3,
        max_provider_calls=32,
        max_tool_calls=32,
        max_input_tokens=100_000,
        max_output_tokens=32_000,
        max_cost_microunits=5_000_000,
        retrieval_top_k=6,
        prompts=prompts,
    )


def _lease(case_key: str, node_key: str, index: int = 0) -> StepLease:
    return StepLease(
        step_id=f"{case_key}:{node_key}:{index}",
        attempt_id=f"{case_key}:{node_key}:{index}:attempt",
        attempt_number=1,
    )
