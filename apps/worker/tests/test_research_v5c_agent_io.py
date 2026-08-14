from __future__ import annotations

import json
from typing import Any

import pytest

from ai_pdf_worker.research_agent_schemas import (
    AGENT_RESULT_SCHEMA_VERSION,
    AGENT_RESULT_SCHEMA_VERSION_LEGACY,
    COMPACT_POLICY_VERSION,
    COMPACT_POLICY_VERSION_LEGACY,
    CONTEXT_POLICY_VERSION,
    CONTEXT_POLICY_VERSION_LEGACY,
    validate_agent_result,
    validate_critic_claim_set,
    validate_researcher_claim_evidence_scope,
    validate_synthesizer_claim_sets,
    validate_verifier_claim_set,
)
from ai_pdf_worker.research_executor import ResearchExecutionError
from ai_pdf_worker.research_executor_contracts import (
    ApprovedResearchExecution,
    FrozenAsset,
    FrozenPrompt,
    ResearchSubproblem,
    StepLease,
    VerifiedClaim,
)
from ai_pdf_worker.research_runtime_agents import GenerationResearchAgents


class _FakeGeneration:
    def __init__(self, execution: ApprovedResearchExecution, raw: str) -> None:
        self.execution = execution
        self.raw = raw
        self.messages: list[dict[str, object]] = []

    def prompt(self, node_key: str) -> FrozenPrompt:
        required = {
            "planner": {"question", "frozenAssetScope", "planningLimits", "planOutputSchema"},
            "researcher": {"subproblem", "frozenAssetScope", "toolContracts", "resultSchema"},
            "verifier": {"claims", "evidence", "reasonTaxonomy", "resultSchema"},
            "critic": {"claims", "resultSchema"},
            "synthesizer": {"question", "claims", "resultSchema"},
        }[node_key]
        prompt_node_key = "researchers" if node_key == "researcher" else node_key
        return FrozenPrompt(
            node_key=prompt_node_key,
            prompt_version_id=f"{node_key}-v",
            prompt_key=f"research.{node_key}",
            version=2,
            step_kind=prompt_node_key if prompt_node_key != "researchers" else "researcher",
            template_text="system",
            variables_schema_version="2",
            variables_schema={
                "type": "object",
                "required": sorted(required),
                "properties": {name: {"type": "object"} for name in required},
            },
            template_sha256="c" * 64,
        )

    def generate(self, lease: StepLease, *, node_key: str, messages: list[dict[str, object]]) -> str:
        del lease, node_key
        self.messages = messages
        return self.raw


class _FakeTools:
    def __init__(self, top_k_seen: list[int]) -> None:
        self.top_k_seen = top_k_seen

    def search(self, *, query: str, asset_ids: Any, top_k: int):
        del query, asset_ids
        self.top_k_seen.append(top_k)

        class Handle:
            def __init__(self, handle_id: str) -> None:
                self.id = handle_id

        return [Handle("h1"), Handle("h2"), Handle("h3")][:top_k]

    def load(self, *, evidence_handles: Any):
        class Loaded:
            def __init__(self, handle_id: str) -> None:
                self.evidence_handle = handle_id
                self.content = f"content-{handle_id}"
                self.asset_id = "asset-1"
                self.locator_id = "loc-1"
                self.content_sha256 = "a" * 64

        return [Loaded(item) for item in evidence_handles]


def _execution(*, retrieval_top_k: int = 3, legacy: bool = False) -> ApprovedResearchExecution:
    nodes = ("planner", "researchers", "verifier", "critic", "synthesizer")
    return ApprovedResearchExecution(
        workspace_id="workspace-1",
        run_id="run-1",
        execution_snapshot_id="execution-1",
        snapshot_sha256="a" * 64,
        question="Compare",
        subproblems=(
            ResearchSubproblem(
                step_id="step-1",
                branch_key="branch-1",
                question="Subproblem",
                asset_ids=("asset-1",),
            ),
        ),
        frozen_assets=(FrozenAsset("asset-1", 1, 1),),
        workflow_version_id="workflow-1",
        prompt_version_ids=tuple(f"{node}-v" for node in nodes),
        provider_config_fingerprint="b" * 64,
        budget_policy_version="budget-v1",
        retry_policy_version="retry-v1",
        max_parallel_researchers=1,
        max_provider_calls=4,
        max_tool_calls=8,
        max_input_tokens=10_000,
        max_output_tokens=1_000,
        retrieval_top_k=retrieval_top_k,
        agent_result_schema_version=(AGENT_RESULT_SCHEMA_VERSION_LEGACY if legacy else AGENT_RESULT_SCHEMA_VERSION),
        context_policy_version=(CONTEXT_POLICY_VERSION_LEGACY if legacy else CONTEXT_POLICY_VERSION),
        compact_policy_version=(COMPACT_POLICY_VERSION_LEGACY if legacy else COMPACT_POLICY_VERSION),
        prompts=tuple(
            FrozenPrompt(
                node_key=node,
                prompt_version_id=f"{node}-v",
                prompt_key=f"research.{node}",
                version=2,
                step_kind=node if node != "researchers" else "researcher",
                template_text="system",
                variables_schema_version="2",
                variables_schema={"type": "object"},
                template_sha256="c" * 64,
            )
            for node in nodes
        ),
    )


def test_strict_role_schema_rejects_extra_and_empty_researcher_claims() -> None:
    validate_agent_result(
        "researcher",
        {"claims": [{"text": "fact", "evidenceHandleIds": ["h1"]}]},
    )
    with pytest.raises(ValueError):
        validate_agent_result("researcher", {"claims": []})
    with pytest.raises(ValueError):
        validate_agent_result(
            "researcher",
            {"claims": [{"text": "fact", "evidenceHandleIds": []}]},
        )
    with pytest.raises(ValueError):
        validate_agent_result(
            "researcher",
            {"claims": [{"text": "fact", "evidenceHandleIds": ["h1"]}], "extra": True},
        )


def test_cross_role_claim_and_evidence_invariants() -> None:
    validate_researcher_claim_evidence_scope(
        [{"text": "fact", "evidenceHandleIds": ["h1"]}],
        branch_evidence_handle_ids=["h1", "h2"],
    )
    with pytest.raises(ValueError, match="claim_evidence_not_in_branch"):
        validate_researcher_claim_evidence_scope(
            [{"text": "fact", "evidenceHandleIds": ["missing"]}],
            branch_evidence_handle_ids=["h1"],
        )

    validate_verifier_claim_set(
        [{"id": "c1", "status": "supported"}, {"id": "c2", "status": "unsupported"}],
        researcher_claim_ids=["c1", "c2"],
    )
    with pytest.raises(ValueError, match="verifier_claim_set_mismatch"):
        validate_verifier_claim_set(
            [{"id": "c1", "status": "supported"}],
            researcher_claim_ids=["c1", "c2"],
        )

    validate_critic_claim_set(["c1"], verified_claim_ids=["c1", "c2"])
    with pytest.raises(ValueError, match="critic_conflict_set_mismatch"):
        validate_critic_claim_set(["missing"], verified_claim_ids=["c1"])

    validate_synthesizer_claim_sets(
        fact_claim_ids=["c1"],
        unresolved_claim_ids=["c2"],
        allowed_claim_ids=["c1", "c2"],
    )
    with pytest.raises(ValueError, match="invalid_synthesis_selection"):
        validate_synthesizer_claim_sets(
            fact_claim_ids=["c1"],
            unresolved_claim_ids=["c1"],
            allowed_claim_ids=["c1"],
        )


def test_legacy_registry_reader_accepts_historical_empty_researcher_claims() -> None:
    execution = _execution(legacy=True)
    generation = _FakeGeneration(execution, json.dumps({"claims": []}))
    agents = GenerationResearchAgents(generation)  # type: ignore[arg-type]
    top_k_seen: list[int] = []
    result = agents.researcher(
        execution.subproblems[0],
        _FakeTools(top_k_seen),
        StepLease(step_id="step-1", attempt_id="attempt-1", attempt_number=1, lease_token="tok"),
    )
    assert top_k_seen == [3]
    assert result.claims == ()
    packed_variables = json.loads(str(generation.messages[1]["content"]))
    assert "minItems" not in packed_variables["resultSchema"]["properties"]["claims"]


def test_current_registry_binds_strict_researcher_schema_to_prompt() -> None:
    execution = _execution()
    generation = _FakeGeneration(
        execution,
        json.dumps({"claims": [{"text": "fact", "evidenceHandleIds": ["h1"]}]}),
    )
    agents = GenerationResearchAgents(generation)  # type: ignore[arg-type]
    agents.researcher(
        execution.subproblems[0],
        _FakeTools([]),
        StepLease(step_id="step-1", attempt_id="attempt-1", attempt_number=1, lease_token="tok"),
    )
    packed_variables = json.loads(str(generation.messages[1]["content"]))
    assert packed_variables["resultSchema"]["properties"]["claims"]["minItems"] == 1


def test_researcher_uses_frozen_retrieval_top_k() -> None:
    execution = _execution(retrieval_top_k=3)
    generation = _FakeGeneration(
        execution,
        json.dumps({"claims": [{"text": "fact", "evidenceHandleIds": ["h1"]}]}),
    )
    agents = GenerationResearchAgents(generation)  # type: ignore[arg-type]
    top_k_seen: list[int] = []
    tools = _FakeTools(top_k_seen)
    lease = StepLease(step_id="step-1", attempt_id="attempt-1", attempt_number=1, lease_token="tok")
    result = agents.researcher(execution.subproblems[0], tools, lease)
    assert top_k_seen == [3]
    assert result.claims[0].evidence_handle_ids == ("h1",)


def test_researcher_fails_without_frozen_retrieval_top_k() -> None:
    execution = _execution(retrieval_top_k=0)
    generation = _FakeGeneration(execution, "{}")
    agents = GenerationResearchAgents(generation)  # type: ignore[arg-type]
    lease = StepLease(step_id="step-1", attempt_id="attempt-1", attempt_number=1, lease_token="tok")
    with pytest.raises(ResearchExecutionError, match="research_retrieval_top_k_unavailable"):
        agents.researcher(execution.subproblems[0], _FakeTools([]), lease)


def test_execution_contract_carries_versions_and_retrieval_top_k() -> None:
    execution = _execution(retrieval_top_k=7)
    assert execution.retrieval_top_k == 7
    assert execution.agent_result_schema_version == AGENT_RESULT_SCHEMA_VERSION
    assert execution.context_policy_version == CONTEXT_POLICY_VERSION
    assert execution.compact_policy_version == COMPACT_POLICY_VERSION


def test_runtime_critic_rejects_claim_ids_outside_verified_set() -> None:
    generation = _FakeGeneration(_execution(), json.dumps({"conflictClaimIds": ["missing"]}))
    agents = GenerationResearchAgents(generation)  # type: ignore[arg-type]
    lease = StepLease(step_id="step-1", attempt_id="attempt-1", attempt_number=1, lease_token="tok")

    with pytest.raises(ResearchExecutionError, match="critic_invalid_output"):
        agents.critic((VerifiedClaim("c1", "fact", ("h1",), "supported"),), lease)


def test_runtime_synthesizer_rejects_overlapping_claim_sets() -> None:
    generation = _FakeGeneration(
        _execution(),
        json.dumps({"factClaimIds": ["c1"], "unresolvedClaimIds": ["c1"]}),
    )
    agents = GenerationResearchAgents(generation)  # type: ignore[arg-type]
    lease = StepLease(step_id="step-1", attempt_id="attempt-1", attempt_number=1, lease_token="tok")

    with pytest.raises(ResearchExecutionError, match="synthesizer_invalid_output"):
        agents.synthesizer(
            "question",
            (VerifiedClaim("c1", "fact", ("h1",), "supported"),),
            (),
            lease,
        )

def test_f1_executable_registry_runtime_bindings() -> None:
    """Executable role/version mapping through Worker schema/validator resolvers.

    For every production and legacy role, resolve the concrete schema and
    validator from the frozen registry entry, validate a representative payload,
    and accept the legacy empty-researcher recovery case. Projection keys remain
    registry metadata only (API research_views owns DTO projection).
    """

    from ai_pdf_api.services.research.research_agent_io_registry import (
        AGENT_RESULT_SCHEMA_VERSION,
        AGENT_RESULT_SCHEMA_VERSION_LEGACY,
        COMPACT_POLICY_VERSION,
        COMPACT_POLICY_VERSION_LEGACY,
        CONTEXT_POLICY_VERSION,
        CONTEXT_POLICY_VERSION_LEGACY,
        require_current_production_registry,
        resolve_registry,
        resolve_role_contract,
    )
    from ai_pdf_worker.research_agent_schemas import (
        schemas_for_registry,
        validate_legacy_agent_result,
        validators_for_registry,
    )

    payloads = {
        "planner": {
            "summary": "plan",
            "knownGaps": [],
            "estimatedProviderCalls": 2,
            "subproblems": [
                {
                    "question": "What does the source claim?",
                    "assetIds": ["asset-1"],
                    "expectedEvidence": ["quote"],
                }
            ],
        },
        "researcher": {
            "claims": [{"text": "fact", "evidenceHandleIds": ["h1"]}],
        },
        "verifier": {
            "claims": [{"id": "c1", "status": "supported"}],
        },
        "critic": {"conflictClaimIds": ["c1"]},
        "synthesizer": {
            "factClaimIds": ["c1"],
            "unresolvedClaimIds": ["c2"],
        },
    }

    production = require_current_production_registry()
    production_schemas = schemas_for_registry(production)
    production_validators = validators_for_registry(production)
    assert set(production_schemas) == set(payloads)
    assert set(production_validators) == set(payloads)
    for node_key, payload in payloads.items():
        role = resolve_role_contract(production, node_key)
        assert role.result_schema_id == f"research.{node_key}.v1"
        assert role.validator_key == "research-agent-validator.v1"
        assert role.runtime_adapter_key == "research-runtime-adapter.v1"
        assert production_schemas[node_key]["type"] == "object"
        production_validators[node_key](node_key, payload)
    # Production researcher must reject empty claims.
    with pytest.raises(ValueError):
        production_validators["researcher"]("researcher", {"claims": []})

    legacy = resolve_registry(
        agent_result_schema_version=AGENT_RESULT_SCHEMA_VERSION_LEGACY,
        context_policy_version=CONTEXT_POLICY_VERSION_LEGACY,
        compact_policy_version=COMPACT_POLICY_VERSION_LEGACY,
        for_new_run=False,
    )
    legacy_schemas = schemas_for_registry(legacy)
    legacy_validators = validators_for_registry(legacy)
    assert set(legacy_schemas) == set(payloads)
    assert set(legacy_validators) == set(payloads)
    for node_key, payload in payloads.items():
        role = resolve_role_contract(legacy, node_key)
        assert role.result_schema_id == f"research.{node_key}.legacy-v0"
        assert role.validator_key == "research-agent-validator.legacy-v0"
        assert role.runtime_adapter_key == "research-runtime-adapter.legacy-v0"
        assert role.schema_version == AGENT_RESULT_SCHEMA_VERSION_LEGACY
        assert legacy_schemas[node_key]["type"] == "object"
        if node_key == "researcher":
            # Legacy recovery accepts empty researcher claims; production does not.
            legacy_validators[node_key](node_key, {"claims": []})
            validate_legacy_agent_result("researcher", {"claims": []})
        else:
            legacy_validators[node_key](node_key, payload)

    # Mutated validator key must fail closed before any provider path uses it.
    from dataclasses import replace
    from ai_pdf_api.services.research.research_agent_io_registry import AgentIoRegistryEntry

    roles = dict(production.roles)
    roles["researcher"] = replace(
        roles["researcher"],
        validator_key="research-agent-validator.unknown",
    )
    tampered = AgentIoRegistryEntry(
        agent_result_schema_version=production.agent_result_schema_version,
        context_policy_version=production.context_policy_version,
        compact_policy_version=production.compact_policy_version,
        soft_compact_ratio=production.soft_compact_ratio,
        mandatory_field_order=production.mandatory_field_order,
        roles=roles,
        approved_for_new_runs=production.approved_for_new_runs,
    )
    with pytest.raises(ValueError, match="research_agent_role_version_unavailable"):
        resolve_role_contract(tampered, "researcher")
    # Even if resolve_role_contract is bypassed, schema map must fail closed.
    roles_schema = dict(production.roles)
    roles_schema["planner"] = replace(
        roles_schema["planner"],
        result_schema_id="research.planner.unknown",
    )
    # resolve_role_contract rejects unknown schema ids via binding keys first
    tampered_schema = AgentIoRegistryEntry(
        agent_result_schema_version=production.agent_result_schema_version,
        context_policy_version=production.context_policy_version,
        compact_policy_version=production.compact_policy_version,
        soft_compact_ratio=production.soft_compact_ratio,
        mandatory_field_order=production.mandatory_field_order,
        roles=roles_schema,
        approved_for_new_runs=production.approved_for_new_runs,
    )
    with pytest.raises(ValueError, match="research_agent_role_version_unavailable"):
        schemas_for_registry(tampered_schema)

    # api_projection_key is documented metadata, not a runtime resolver key.
    assert {
        node_key: role.api_projection_key
        for node_key, role in production.roles.items()
    } == {
        "planner": "research-plan-dto.v1",
        "researcher": "research-claim-dto.v1",
        "verifier": "research-claim-dto.v1",
        "critic": "research-conflict-dto.v1",
        "synthesizer": "research-artifact-dto.v1",
    }
    assert production.agent_result_schema_version == AGENT_RESULT_SCHEMA_VERSION
    assert production.context_policy_version == CONTEXT_POLICY_VERSION
    assert production.compact_policy_version == COMPACT_POLICY_VERSION


