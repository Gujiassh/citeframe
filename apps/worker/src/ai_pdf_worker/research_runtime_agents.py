"""Production Research orchestration ports.

The worker owns orchestration and provider adapters.  The API owns the Research
ledger and the transaction boundaries.  This module deliberately contains no
SQLAlchemy model imports: a missing or incomplete API port is a hard failure.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from uuid import uuid4

from ai_pdf_api.services.providers import GenerationMessage

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

from ai_pdf_api.services.research_agent_io_registry import (
    AGENT_RESULT_SCHEMA_VERSION_LEGACY,
    require_current_production_registry,
    resolve_registry,
    resolve_role_contract,
)

from ai_pdf_worker.research_agent_schemas import (
    schemas_for_registry,
    validators_for_registry,
)
from ai_pdf_worker.research_agent_schemas import (
    validate_critic_claim_set,
    validate_researcher_claim_evidence_scope,
    validate_synthesizer_claim_sets,
    validate_verifier_claim_set,
)


class GenerationResearchAgents:
    """Strict JSON agents.  All content is treated as untrusted evidence."""

    def __init__(
        self,
        generation: LedgeredGeneration,
        *,
        result_schemas: Mapping[str, dict[str, object]] | None = None,
        result_validator: Callable[[str, dict[str, Any]], None] | None = None,
        output_observer: Callable[[str, str, str], None] | None = None,
        diagnostic_mode: bool = False,
        allow_empty_researcher_claims: bool = False,
    ) -> None:
        self._generation = generation
        execution = getattr(generation, "execution", None)
        if execution is None:
            self._registry = require_current_production_registry()
        else:
            self._registry = resolve_registry(
                agent_result_schema_version=getattr(execution, "agent_result_schema_version", None),
                context_policy_version=getattr(execution, "context_policy_version", None),
                compact_policy_version=getattr(execution, "compact_policy_version", None),
                for_new_run=False,
            )
        self._result_schemas = result_schemas or schemas_for_registry(self._registry)
        self._result_validators = (
            {node_key: result_validator for node_key in self._registry.roles}
            if result_validator is not None
            else validators_for_registry(self._registry)
        )
        self._legacy_mode = self._registry.agent_result_schema_version == AGENT_RESULT_SCHEMA_VERSION_LEGACY
        self._output_observer = output_observer
        # Evaluator-only boundary. Production/default remains historical failure codes.
        self._diagnostic_mode = bool(diagnostic_mode)
        self._allow_empty_researcher_claims = bool(allow_empty_researcher_claims)
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
                },
                "planOutputSchema": self._result_schemas["planner"],
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
        retrieval_top_k = int(getattr(self._generation.execution, "retrieval_top_k", 0) or 0)
        if retrieval_top_k < 1:
            raise ResearchExecutionError("research_retrieval_top_k_unavailable")
        handles = tuple(
            tools.search(
                query=subproblem.question,
                asset_ids=subproblem.asset_ids,
                top_k=retrieval_top_k,
            )
        )
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
                "resultSchema": self._result_schemas["researcher"],
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
        try:
            if not claims and self._allow_empty_researcher_claims:
                return BranchResult(subproblem.branch_key, claims, handles)
            validate_researcher_claim_evidence_scope(
                [
                    {
                        "text": claim.text,
                        "evidenceHandleIds": list(claim.evidence_handle_ids),
                    }
                    for claim in claims
                ],
                branch_evidence_handle_ids=[item.id for item in handles],
                allow_empty=self._legacy_mode,
            )
        except ValueError as error:
            raise ResearchExecutionError("researcher_invalid_output") from error
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
                "resultSchema": self._result_schemas["verifier"],
            },
        )
        rows = payload.get("claims") if isinstance(payload, dict) else None
        source = {item.id: item for item in claims}
        if not isinstance(rows, list):
            raise ResearchExecutionError("verifier_invalid_output")
        try:
            validate_verifier_claim_set(rows, researcher_claim_ids=tuple(source))
        except ValueError as error:
            raise ResearchExecutionError("verifier_invalid_output") from error
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
                "resultSchema": self._result_schemas["critic"],
            },
        )
        conflicts = payload.get("conflictClaimIds") if isinstance(payload, dict) else None
        if not isinstance(conflicts, list):
            raise ResearchExecutionError("critic_invalid_output")
        try:
            validate_critic_claim_set(
                [str(item) for item in conflicts],
                verified_claim_ids=[claim.id for claim in claims],
            )
        except ValueError as error:
            raise ResearchExecutionError("critic_invalid_output") from error
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
                "resultSchema": self._result_schemas["synthesizer"],
            },
        )
        fact_claim_ids = tuple(str(item) for item in payload.get("factClaimIds", ()))
        unresolved_claim_ids = tuple(str(item) for item in payload.get("unresolvedClaimIds", ()))
        try:
            validate_synthesizer_claim_sets(
                fact_claim_ids=fact_claim_ids,
                unresolved_claim_ids=unresolved_claim_ids,
                allowed_claim_ids=[claim.id for claim in (*claims, *unresolved)],
            )
        except ValueError as error:
            raise ResearchExecutionError("synthesizer_invalid_output") from error
        return SynthesisSelection(fact_claim_ids, unresolved_claim_ids)

    def _json(self, lease: StepLease, node_key: str, variables: Mapping[str, object]) -> Any:
        role = resolve_role_contract(self._registry, node_key)
        prompt = self._generation.prompt(node_key)
        if (
            prompt.node_key != role.prompt_node_key
            or prompt.prompt_key != role.prompt_key
        ):
            raise ResearchExecutionError("research_prompt_contract_invalid")
        _validate_prompt_variables(prompt, variables)
        messages: list[GenerationMessage] = [
            {"role": "system", "content": prompt.template_text},
            {"role": "user", "content": json.dumps(variables, ensure_ascii=True)},
        ]
        raw = self._generation.generate(lease, node_key=node_key, messages=messages)
        logical_call_key = f"{lease.step_id}:{node_key}"
        raw_sha256 = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        if self._output_observer is not None:
            self._output_observer(node_key, logical_call_key, raw)
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            if self._diagnostic_mode:
                from ai_pdf_worker.r803_evaluation_diagnostics import (
                    AgentResultValidationError,
                )

                raise AgentResultValidationError(
                    node_key,
                    "json_decode",
                    "$",
                    logical_call_key=logical_call_key,
                    raw_output_sha256=raw_sha256,
                ) from error
            raise ResearchExecutionError(f"{node_key}_invalid_output") from error
        if not isinstance(value, dict):
            if self._diagnostic_mode:
                from ai_pdf_worker.r803_evaluation_diagnostics import (
                    AgentResultValidationError,
                )

                raise AgentResultValidationError(
                    node_key,
                    "json_root_object",
                    "$",
                    logical_call_key=logical_call_key,
                    raw_output_sha256=raw_sha256,
                )
            raise ResearchExecutionError(f"{node_key}_invalid_output")
        result_validator = self._result_validators.get(node_key)
        if result_validator is not None:
            try:
                # Prefer keyword-aware diagnostic validators when available.
                try:
                    result_validator(
                        node_key,
                        value,
                        logical_call_key=logical_call_key,
                        raw_output_sha256=raw_sha256,
                    )
                except TypeError:
                    result_validator(node_key, value)
            except Exception as error:
                # Preserve production failure codes while allowing evaluator-only
                # typed diagnostics to propagate when callers opt into them.
                from ai_pdf_worker.r803_evaluation_diagnostics import (
                    AgentResultValidationError,
                )

                if isinstance(error, AgentResultValidationError):
                    raise
                if isinstance(error, (KeyError, TypeError, ValueError)):
                    raise ResearchExecutionError(f"{node_key}_invalid_output") from error
                raise
        return value
