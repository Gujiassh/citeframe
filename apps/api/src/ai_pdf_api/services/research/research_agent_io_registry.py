"""Strict versioned production Agent I/O registry for Research.

Each approved role version freezes schema, validator, runtime metadata and
historical recovery as one immutable unit. New Runs may bind only the current
approved production versions. Historical rows are read through an explicit
legacy registry entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

# Production current versions. New Runs bind these exact values.
AGENT_RESULT_SCHEMA_VERSION = "research-agent-results-v1"
CONTEXT_POLICY_VERSION = "research-context-policy-v1"
COMPACT_POLICY_VERSION = "research-compact-policy-v1"

# Historical recovery-only versions for rows created before V5-C.
AGENT_RESULT_SCHEMA_VERSION_LEGACY = "research-agent-results-legacy-v0"
CONTEXT_POLICY_VERSION_LEGACY = "research-context-policy-legacy-v0"
COMPACT_POLICY_VERSION_LEGACY = "research-compact-policy-legacy-v0"

SOFT_COMPACT_RATIO = 0.85
MANDATORY_CONTEXT_FIELD_ORDER = (
    "claimIds",
    "evidenceHandleIds",
    "sourceFingerprints",
    "branchScope",
    "schemaFields",
    "orderedPayload",
)


@dataclass(frozen=True)
class RoleContract:
    node_key: str
    schema_version: str
    result_schema_id: str
    validator_key: str
    runtime_adapter_key: str
    api_projection_key: str
    prompt_key: str
    input_required: tuple[str, ...]
    output_required: tuple[str, ...]
    prompt_node_key: str
    additional_properties: bool = False


@dataclass(frozen=True)
class AgentIoRegistryEntry:
    agent_result_schema_version: str
    context_policy_version: str
    compact_policy_version: str
    soft_compact_ratio: float
    mandatory_field_order: tuple[str, ...]
    roles: Mapping[str, RoleContract]
    approved_for_new_runs: bool


ROLE_CONTRACTS: dict[str, RoleContract] = {
    "planner": RoleContract(
        node_key="planner",
        schema_version=AGENT_RESULT_SCHEMA_VERSION,
        result_schema_id="research.planner.v1",
        validator_key="research-agent-validator.v1",
        runtime_adapter_key="research-runtime-adapter.v1",
        api_projection_key="research-plan-dto.v1",
        prompt_key="research.planner",
        input_required=("question", "frozenAssetScope", "planningLimits", "planOutputSchema"),
        output_required=("summary", "knownGaps", "estimatedProviderCalls", "subproblems"),
        prompt_node_key="planner",
    ),
    "researcher": RoleContract(
        node_key="researcher",
        schema_version=AGENT_RESULT_SCHEMA_VERSION,
        result_schema_id="research.researcher.v1",
        validator_key="research-agent-validator.v1",
        runtime_adapter_key="research-runtime-adapter.v1",
        api_projection_key="research-claim-dto.v1",
        prompt_key="research.researcher",
        input_required=("subproblem", "frozenAssetScope", "toolContracts", "resultSchema"),
        output_required=("claims",),
        prompt_node_key="researchers",
    ),
    "verifier": RoleContract(
        node_key="verifier",
        schema_version=AGENT_RESULT_SCHEMA_VERSION,
        result_schema_id="research.verifier.v1",
        validator_key="research-agent-validator.v1",
        runtime_adapter_key="research-runtime-adapter.v1",
        api_projection_key="research-claim-dto.v1",
        prompt_key="research.verifier",
        input_required=("claims", "evidence", "reasonTaxonomy", "resultSchema"),
        output_required=("claims",),
        prompt_node_key="verifier",
    ),
    "critic": RoleContract(
        node_key="critic",
        schema_version=AGENT_RESULT_SCHEMA_VERSION,
        result_schema_id="research.critic.v1",
        validator_key="research-agent-validator.v1",
        runtime_adapter_key="research-runtime-adapter.v1",
        api_projection_key="research-conflict-dto.v1",
        prompt_key="research.critic",
        input_required=("claims", "resultSchema"),
        output_required=("conflictClaimIds",),
        prompt_node_key="critic",
    ),
    "synthesizer": RoleContract(
        node_key="synthesizer",
        schema_version=AGENT_RESULT_SCHEMA_VERSION,
        result_schema_id="research.synthesizer.v1",
        validator_key="research-agent-validator.v1",
        runtime_adapter_key="research-runtime-adapter.v1",
        api_projection_key="research-artifact-dto.v1",
        prompt_key="research.synthesizer",
        input_required=("question", "claims", "resultSchema"),
        output_required=("factClaimIds", "unresolvedClaimIds"),
        prompt_node_key="synthesizer",
    ),
}


LEGACY_ROLE_CONTRACTS: dict[str, RoleContract] = {
    node_key: RoleContract(
        node_key=contract.node_key,
        schema_version=AGENT_RESULT_SCHEMA_VERSION_LEGACY,
        result_schema_id=contract.result_schema_id.replace(".v1", ".legacy-v0"),
        validator_key="research-agent-validator.legacy-v0",
        runtime_adapter_key="research-runtime-adapter.legacy-v0",
        api_projection_key=contract.api_projection_key,
        prompt_key=contract.prompt_key,
        input_required=contract.input_required,
        output_required=contract.output_required,
        prompt_node_key=contract.prompt_node_key,
        additional_properties=contract.additional_properties,
    )
    for node_key, contract in ROLE_CONTRACTS.items()
}


PRODUCTION_REGISTRY = AgentIoRegistryEntry(
    agent_result_schema_version=AGENT_RESULT_SCHEMA_VERSION,
    context_policy_version=CONTEXT_POLICY_VERSION,
    compact_policy_version=COMPACT_POLICY_VERSION,
    soft_compact_ratio=SOFT_COMPACT_RATIO,
    mandatory_field_order=MANDATORY_CONTEXT_FIELD_ORDER,
    roles=ROLE_CONTRACTS,
    approved_for_new_runs=True,
)


LEGACY_REGISTRY = AgentIoRegistryEntry(
    agent_result_schema_version=AGENT_RESULT_SCHEMA_VERSION_LEGACY,
    context_policy_version=CONTEXT_POLICY_VERSION_LEGACY,
    compact_policy_version=COMPACT_POLICY_VERSION_LEGACY,
    soft_compact_ratio=SOFT_COMPACT_RATIO,
    mandatory_field_order=MANDATORY_CONTEXT_FIELD_ORDER,
    roles=LEGACY_ROLE_CONTRACTS,
    approved_for_new_runs=False,
)


_REGISTRY_BY_VERSION: dict[tuple[str, str, str], AgentIoRegistryEntry] = {
    (
        PRODUCTION_REGISTRY.agent_result_schema_version,
        PRODUCTION_REGISTRY.context_policy_version,
        PRODUCTION_REGISTRY.compact_policy_version,
    ): PRODUCTION_REGISTRY,
    (
        LEGACY_REGISTRY.agent_result_schema_version,
        LEGACY_REGISTRY.context_policy_version,
        LEGACY_REGISTRY.compact_policy_version,
    ): LEGACY_REGISTRY,
}

_ROLE_BINDING_KEYS: dict[str, tuple[str, str, str, str, str]] = {
    "planner": (
        "research.planner",
        "research-plan-dto.v1",
        "planner",
        "research-agent-validator.v1",
        "research-runtime-adapter.v1",
    ),
    "researcher": (
        "research.researcher",
        "research-claim-dto.v1",
        "researchers",
        "research-agent-validator.v1",
        "research-runtime-adapter.v1",
    ),
    "verifier": (
        "research.verifier",
        "research-claim-dto.v1",
        "verifier",
        "research-agent-validator.v1",
        "research-runtime-adapter.v1",
    ),
    "critic": (
        "research.critic",
        "research-conflict-dto.v1",
        "critic",
        "research-agent-validator.v1",
        "research-runtime-adapter.v1",
    ),
    "synthesizer": (
        "research.synthesizer",
        "research-artifact-dto.v1",
        "synthesizer",
        "research-agent-validator.v1",
        "research-runtime-adapter.v1",
    ),
}


def current_production_versions() -> dict[str, str]:
    return {
        "agentResultSchemaVersion": PRODUCTION_REGISTRY.agent_result_schema_version,
        "contextPolicyVersion": PRODUCTION_REGISTRY.context_policy_version,
        "compactPolicyVersion": PRODUCTION_REGISTRY.compact_policy_version,
    }


def legacy_recovery_versions() -> dict[str, str]:
    return {
        "agentResultSchemaVersion": LEGACY_REGISTRY.agent_result_schema_version,
        "contextPolicyVersion": LEGACY_REGISTRY.context_policy_version,
        "compactPolicyVersion": LEGACY_REGISTRY.compact_policy_version,
    }


def resolve_registry(
    *,
    agent_result_schema_version: str | None,
    context_policy_version: str | None,
    compact_policy_version: str | None,
    for_new_run: bool = False,
) -> AgentIoRegistryEntry:
    """Resolve a frozen registry entry.

    Missing version fields are treated as the explicit legacy recovery entry.
    New Runs may bind only the approved production entry.
    """

    if (
        not agent_result_schema_version
        and not context_policy_version
        and not compact_policy_version
    ):
        if for_new_run:
            raise ValueError("research_agent_io_version_unavailable")
        return LEGACY_REGISTRY

    key = (
        agent_result_schema_version or LEGACY_REGISTRY.agent_result_schema_version,
        context_policy_version or LEGACY_REGISTRY.context_policy_version,
        compact_policy_version or LEGACY_REGISTRY.compact_policy_version,
    )
    entry = _REGISTRY_BY_VERSION.get(key)
    if entry is None:
        raise ValueError("research_agent_io_version_unavailable")
    if for_new_run and not entry.approved_for_new_runs:
        raise ValueError("research_agent_io_version_unavailable")
    return entry


def resolve_role_contract(entry: AgentIoRegistryEntry, node_key: str) -> RoleContract:
    """Resolve the immutable role contract for a frozen registry entry."""

    try:
        role = entry.roles[node_key]
    except KeyError as error:
        raise ValueError("research_agent_role_version_unavailable") from error
    if (
        role.node_key != node_key
        or role.schema_version != entry.agent_result_schema_version
        or not role.result_schema_id
        or not role.validator_key
        or not role.runtime_adapter_key
        or not role.api_projection_key
        or not role.prompt_key
        or not role.prompt_node_key
    ):
        raise ValueError("research_agent_role_version_unavailable")
    expected_prompt_key, expected_projection_key, expected_prompt_node_key, validator_key, adapter_key = _ROLE_BINDING_KEYS[node_key]
    expected_schema_id = expected_prompt_key + (
        ".legacy-v0" if entry.agent_result_schema_version == AGENT_RESULT_SCHEMA_VERSION_LEGACY else ".v1"
    )
    expected_validator_key = validator_key.replace(".v1", ".legacy-v0") if entry.agent_result_schema_version == AGENT_RESULT_SCHEMA_VERSION_LEGACY else validator_key
    expected_adapter_key = adapter_key.replace(".v1", ".legacy-v0") if entry.agent_result_schema_version == AGENT_RESULT_SCHEMA_VERSION_LEGACY else adapter_key
    if (
        role.result_schema_id != expected_schema_id
        or role.validator_key != expected_validator_key
        or role.runtime_adapter_key != expected_adapter_key
        or role.api_projection_key != expected_projection_key
        or role.prompt_key != expected_prompt_key
        or role.prompt_node_key != expected_prompt_node_key
    ):
        raise ValueError("research_agent_role_version_unavailable")
    return role


def require_registry_role(
    *,
    agent_result_schema_version: str | None,
    context_policy_version: str | None,
    compact_policy_version: str | None,
    node_key: str,
) -> tuple[AgentIoRegistryEntry, RoleContract]:
    entry = resolve_registry(
        agent_result_schema_version=agent_result_schema_version,
        context_policy_version=context_policy_version,
        compact_policy_version=compact_policy_version,
        for_new_run=False,
    )
    return entry, resolve_role_contract(entry, node_key)


def require_current_production_registry() -> AgentIoRegistryEntry:
    entry = PRODUCTION_REGISTRY
    if not entry.approved_for_new_runs:
        raise ValueError("research_agent_io_version_unavailable")
    if not entry.roles or set(entry.roles) != {
        "planner",
        "researcher",
        "verifier",
        "critic",
        "synthesizer",
    }:
        raise ValueError("research_agent_io_version_unavailable")
    for node_key in entry.roles:
        resolve_role_contract(entry, node_key)
    return entry


def registry_snapshot_fields(entry: AgentIoRegistryEntry | None = None) -> dict[str, str]:
    active = entry or require_current_production_registry()
    return {
        "agentResultSchemaVersion": active.agent_result_schema_version,
        "contextPolicyVersion": active.context_policy_version,
        "compactPolicyVersion": active.compact_policy_version,
    }


def soft_compact_threshold(max_input_tokens: int, *, policy_version: str | None = None) -> int:
    entry = (
        resolve_registry(
            agent_result_schema_version=AGENT_RESULT_SCHEMA_VERSION
            if policy_version in {None, CONTEXT_POLICY_VERSION}
            else AGENT_RESULT_SCHEMA_VERSION_LEGACY,
            context_policy_version=policy_version or CONTEXT_POLICY_VERSION,
            compact_policy_version=COMPACT_POLICY_VERSION
            if policy_version in {None, CONTEXT_POLICY_VERSION}
            else COMPACT_POLICY_VERSION_LEGACY,
        )
        if policy_version
        else PRODUCTION_REGISTRY
    )
    if max_input_tokens < 1:
        raise ValueError("max_input_tokens must be >= 1")
    return max(1, int(max_input_tokens * entry.soft_compact_ratio))


def estimate_text_tokens(text: str) -> int:
    # Deterministic local estimate used for context packing gates only.
    if not text:
        return 0
    return max(1, (len(text.encode("utf-8")) + 3) // 4)


def estimate_json_tokens(value: Any) -> int:
    import json

    return estimate_text_tokens(json.dumps(value, ensure_ascii=True, separators=(",", ":")))
