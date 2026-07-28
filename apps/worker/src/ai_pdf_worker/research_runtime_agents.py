"""Production Research orchestration ports.

The worker owns orchestration and provider adapters.  The API owns the Research
ledger and the transaction boundaries.  This module deliberately contains no
SQLAlchemy model imports: a missing or incomplete API port is a hard failure.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import uuid4

from ai_pdf_api.services.providers import (
    GenerationMessage,
)

from ai_pdf_worker.research_executor import (
    BranchResult,
    DraftClaim,
    EvidenceHandle,
    FrozenAsset,
    PlanSubproblemDraft,
    ResearchExecutionError,
    ResearchSubproblem,
    StepLease,
    SynthesisSelection,
    VerifiedClaim,
)
from ai_pdf_worker.research_runtime_core import (
    _field,
    _validate_prompt_variables,
)
from ai_pdf_worker.research_runtime_ports import LedgeredGeneration


class GenerationResearchAgents:
    """Strict JSON agents.  All content is treated as untrusted evidence."""

    def __init__(self, generation: LedgeredGeneration) -> None:
        self._generation = generation
        self.plan_summary: str | None = None
        self.plan_known_gaps: tuple[str, ...] = ()
        self.plan_estimated_provider_calls: int | None = None

    def planner(self, question: str, assets: Sequence[FrozenAsset], lease: StepLease | None = None) -> Sequence[PlanSubproblemDraft]:
        if lease is None:
            raise ResearchExecutionError("planner_lease_required")
        payload = self._json(
            lease,
            "planner",
            {
                "question": question,
                "frozenAssetScope": {
                    "assets": [
                        {
                            "assetId": asset.asset_id,
                            "processingGeneration": asset.processing_generation,
                            "indexVersion": asset.index_version,
                        }
                        for asset in assets
                    ]
                },
                "planningLimits": {
                    "maxSubproblems": 16,
                    "maxProviderCalls": self._generation.execution.max_provider_calls,
                    "maxInputTokens": self._generation.execution.max_input_tokens,
                    "maxOutputTokens": self._generation.execution.max_output_tokens,
                    "maxCostMicrounits": self._generation.execution.max_cost_microunits,
                },
                "planOutputSchema": {
                    "type": "object",
                    "required": ["summary", "knownGaps", "estimatedProviderCalls", "subproblems"],
                },
            },
        )
        rows = payload.get("subproblems") if isinstance(payload, dict) else None
        summary = payload.get("summary") if isinstance(payload, dict) else None
        gaps = payload.get("knownGaps") if isinstance(payload, dict) else None
        estimated_calls = payload.get("estimatedProviderCalls") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or not isinstance(summary, str) or not summary.strip() or not isinstance(gaps, list) or not isinstance(estimated_calls, int) or estimated_calls < 1:
            raise ResearchExecutionError("planner_invalid_output")
        self.plan_summary = summary.strip()
        self.plan_known_gaps = tuple(str(item) for item in gaps)
        self.plan_estimated_provider_calls = estimated_calls
        return tuple(PlanSubproblemDraft(str(_field(row, "question")), tuple(str(x) for x in _field(row, "assetIds")), tuple(str(x) for x in _field(row, "expectedEvidence"))) for row in rows)

    def researcher(self, subproblem: ResearchSubproblem, tools: Any, lease: StepLease | None = None) -> BranchResult:
        if lease is None:
            raise ResearchExecutionError("researcher_lease_required")
        handles = tuple(tools.search(query=subproblem.question, asset_ids=subproblem.asset_ids, top_k=8))
        if not handles:
            raise ResearchExecutionError("no_evidence_found")
        loaded = tools.load(evidence_handles=tuple(item.id for item in handles))
        payload = self._json(
            lease,
            "researcher",
            {
                "subproblem": {
                    "question": subproblem.question,
                    "assetIds": list(subproblem.asset_ids),
                },
                "frozenAssetScope": {"assetIds": list(subproblem.asset_ids)},
                "toolContracts": {
                    "allowedTools": ["evidence.search.v1", "evidence.load.v1"],
                    "evidence": [
                        {
                            "evidenceHandle": item.evidence_handle,
                            "content": item.content,
                            "assetId": item.asset_id,
                            "locatorId": item.locator_id,
                            "contentSha256": item.content_sha256,
                        }
                        for item in loaded
                    ],
                },
                "resultSchema": {
                    "type": "object",
                    "required": ["claims"],
                },
            },
        )
        rows = payload.get("claims") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ResearchExecutionError("researcher_invalid_output")
        claims = tuple(
            DraftClaim(
                str(uuid4()),
                str(_field(row, "text")),
                tuple(str(item) for item in _field(row, "evidenceHandleIds")),
            )
            for row in rows
        )
        return BranchResult(subproblem.branch_key, claims, handles)

    def verifier(self, claims: Sequence[DraftClaim], evidence: Sequence[EvidenceHandle], lease: StepLease | None = None) -> Sequence[VerifiedClaim]:
        if lease is None:
            raise ResearchExecutionError("verifier_lease_required")
        by_handle = {item.id: item for item in evidence}
        referenced_ids = tuple(
            dict.fromkeys(
                handle_id
                for claim in claims
                for handle_id in claim.evidence_handle_ids
            )
        )
        if any(handle_id not in by_handle for handle_id in referenced_ids):
            raise ResearchExecutionError("verifier_evidence_scope_mismatch")
        payload = self._json(
            lease,
            "verifier",
            {
                "claims": [
                    {
                        "id": claim.id,
                        "text": claim.text,
                        "evidenceHandleIds": list(claim.evidence_handle_ids),
                    }
                    for claim in claims
                ],
                "evidence": [
                    {
                        "evidenceHandle": handle_id,
                        "excerpt": by_handle[handle_id].excerpt,
                        "assetId": by_handle[handle_id].asset_id,
                        "locatorId": by_handle[handle_id].locator_id,
                        "sourceFingerprintSha256": by_handle[handle_id].source_fingerprint_sha256,
                    }
                    for handle_id in referenced_ids
                ],
                "reasonTaxonomy": ["supported", "unsupported"],
                "resultSchema": {
                    "type": "object",
                    "required": ["claims"],
                },
            },
        )
        rows = payload.get("claims") if isinstance(payload, dict) else None
        source = {item.id: item for item in claims}
        if not isinstance(rows, list) or {str(_field(row, "id")) for row in rows} != set(source):
            raise ResearchExecutionError("verifier_invalid_output")
        return tuple(VerifiedClaim(item.id, item.text, item.evidence_handle_ids, _field(next(row for row in rows if str(_field(row, "id")) == item.id), "status")) for item in claims)

    def critic(self, claims: Sequence[VerifiedClaim], lease: StepLease | None = None) -> Sequence[str]:
        if lease is None:
            raise ResearchExecutionError("critic_lease_required")
        payload = self._json(
            lease,
            "critic",
            {
                "claims": [
                    {"id": claim.id, "text": claim.text, "status": claim.verification_status}
                    for claim in claims
                ],
                "resultSchema": {
                    "type": "object",
                    "required": ["conflictClaimIds"],
                },
            },
        )
        conflicts = payload.get("conflictClaimIds") if isinstance(payload, dict) else None
        if not isinstance(conflicts, list):
            raise ResearchExecutionError("critic_invalid_output")
        return tuple(str(item) for item in conflicts)

    def synthesizer(self, question: str, claims: Sequence[VerifiedClaim], unresolved: Sequence[VerifiedClaim], lease: StepLease | None = None) -> SynthesisSelection:
        if lease is None:
            raise ResearchExecutionError("synthesizer_lease_required")
        payload = self._json(
            lease,
            "synthesizer",
            {
                "question": question,
                "claims": [
                    {
                        "id": item.id,
                        "text": item.text,
                        "verificationStatus": item.verification_status,
                        "conflictStatus": item.conflict_status,
                    }
                    for item in (*claims, *unresolved)
                ],
                "resultSchema": {
                    "type": "object",
                    "required": ["factClaimIds", "unresolvedClaimIds"],
                },
            },
        )
        return SynthesisSelection(tuple(str(item) for item in payload.get("factClaimIds", ())), tuple(str(item) for item in payload.get("unresolvedClaimIds", ())))

    def _json(self, lease: StepLease, node_key: str, variables: Mapping[str, object]) -> Any:
        prompt = self._generation.prompt(node_key)
        _validate_prompt_variables(prompt, variables)
        messages: list[GenerationMessage] = [
            {"role": "system", "content": prompt.template_text},
            {"role": "user", "content": json.dumps(variables, ensure_ascii=True)},
        ]
        raw = self._generation.generate(lease, node_key=node_key, messages=messages)
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ResearchExecutionError(f"{node_key}_invalid_output") from error
        if not isinstance(value, dict):
            raise ResearchExecutionError(f"{node_key}_invalid_output")
        return value
