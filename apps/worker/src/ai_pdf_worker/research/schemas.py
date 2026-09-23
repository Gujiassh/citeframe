from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping, Sequence

from ai_pdf_api.services.research.research_agent_io_registry import (
    AGENT_RESULT_SCHEMA_VERSION as AGENT_RESULT_SCHEMA_VERSION,
    AGENT_RESULT_SCHEMA_VERSION_LEGACY,
    COMPACT_POLICY_VERSION as COMPACT_POLICY_VERSION,
    COMPACT_POLICY_VERSION_LEGACY,
    CONTEXT_POLICY_VERSION as CONTEXT_POLICY_VERSION,
    CONTEXT_POLICY_VERSION_LEGACY,
    PRODUCTION_REGISTRY,
    AgentIoRegistryEntry,
    resolve_role_contract,
    require_current_production_registry,
)

AGENT_RESULT_SCHEMAS: dict[str, dict[str, object]] = {
    "planner": {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "knownGaps", "estimatedProviderCalls", "subproblems"],
        "properties": {
            "summary": {"type": "string", "minLength": 1},
            "knownGaps": {"type": "array", "items": {"type": "string"}},
            "estimatedProviderCalls": {"type": "integer", "minimum": 1},
            "subproblems": {
                "type": "array",
                "minItems": 1,
                "maxItems": 16,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["question", "assetIds", "expectedEvidence"],
                    "properties": {
                        "question": {"type": "string", "minLength": 1, "maxLength": 4000},
                        "assetIds": {
                            "type": "array",
                            "maxItems": 100,
                            "uniqueItems": True,
                            "items": {"type": "string"},
                        },
                        "expectedEvidence": {
                            "type": "array",
                            "maxItems": 20,
                            "uniqueItems": True,
                            "items": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
    "researcher": {
        "type": "object",
        "additionalProperties": False,
        "required": ["claims"],
        "properties": {
            "claims": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["text", "evidenceHandleIds"],
                    "properties": {
                        "text": {"type": "string", "minLength": 1, "maxLength": 12000},
                        "evidenceHandleIds": {
                            "type": "array",
                            "minItems": 1,
                            "uniqueItems": True,
                            "items": {"type": "string"},
                        },
                    },
                },
            }
        },
    },
    "verifier": {
        "type": "object",
        "additionalProperties": False,
        "required": ["claims"],
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "status"],
                    "properties": {
                        "id": {"type": "string"},
                        "status": {"type": "string", "enum": ["supported", "unsupported"]},
                    },
                },
            }
        },
    },
    "critic": {
        "type": "object",
        "additionalProperties": False,
        "required": ["conflictClaimIds"],
        "properties": {
            "conflictClaimIds": {
                "type": "array",
                "uniqueItems": True,
                "items": {"type": "string"},
            }
        },
    },
    "synthesizer": {
        "type": "object",
        "additionalProperties": False,
        "required": ["factClaimIds", "unresolvedClaimIds"],
        "properties": {
            "factClaimIds": {
                "type": "array",
                "uniqueItems": True,
                "items": {"type": "string"},
            },
            "unresolvedClaimIds": {
                "type": "array",
                "uniqueItems": True,
                "items": {"type": "string"},
            },
        },
    },
}


# Legacy persisted agent results used the same object shapes but allowed a
# researcher branch to complete with an empty claim list. Keep that reader
# explicit instead of weakening the approved production schema.
LEGACY_AGENT_RESULT_SCHEMAS: dict[str, dict[str, object]] = deepcopy(AGENT_RESULT_SCHEMAS)
LEGACY_AGENT_RESULT_SCHEMAS["researcher"]["properties"] = deepcopy(
    AGENT_RESULT_SCHEMAS["researcher"]["properties"]
)
LEGACY_AGENT_RESULT_SCHEMAS["researcher"]["properties"]["claims"].pop("minItems", None)  # type: ignore[index]

_SCHEMAS_BY_ID: dict[str, dict[str, object]] = {
    **{
        f"research.{node_key}.v1": schema
        for node_key, schema in AGENT_RESULT_SCHEMAS.items()
    },
    **{
        f"research.{node_key}.legacy-v0": schema
        for node_key, schema in LEGACY_AGENT_RESULT_SCHEMAS.items()
    },
}


def _string_list(
    value: object,
    *,
    minimum: int = 0,
    maximum: int | None = None,
    unique: bool = True,
) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= minimum
        and (maximum is None or len(value) <= maximum)
        and all(isinstance(item, str) for item in value)
        and (not unique or len(value) == len(set(value)))
    )


def validate_agent_result(node_key: str, value: dict[str, Any]) -> None:
    # Registry/version availability is checked when the execution snapshot is
    # bound. The structural validator is also used by the legacy recovery
    # reader, so it must not require the current production registry here.
    if node_key == "planner":
        if set(value) != {"summary", "knownGaps", "estimatedProviderCalls", "subproblems"}:
            raise ValueError("planner schema mismatch")
        subproblems = value["subproblems"]
        if (
            not isinstance(value["summary"], str)
            or not value["summary"]
            or not _string_list(value["knownGaps"], unique=False)
            or type(value["estimatedProviderCalls"]) is not int
            or value["estimatedProviderCalls"] < 1
            or not isinstance(subproblems, list)
            or not 1 <= len(subproblems) <= 16
        ):
            raise ValueError("planner schema mismatch")
        for item in subproblems:
            if (
                not isinstance(item, dict)
                or set(item) != {"question", "assetIds", "expectedEvidence"}
                or not isinstance(item["question"], str)
                or not 1 <= len(item["question"]) <= 4000
                or not _string_list(item["assetIds"], maximum=100)
                or not _string_list(item["expectedEvidence"], maximum=20)
            ):
                raise ValueError("planner schema mismatch")
        return

    if node_key == "researcher":
        if set(value) != {"claims"} or not isinstance(value["claims"], list) or not value["claims"]:
            raise ValueError("researcher schema mismatch")
        for item in value["claims"]:
            if (
                not isinstance(item, dict)
                or set(item) != {"text", "evidenceHandleIds"}
                or not isinstance(item["text"], str)
                or not 1 <= len(item["text"]) <= 12000
                or not _string_list(item["evidenceHandleIds"], minimum=1)
            ):
                raise ValueError("researcher schema mismatch")
        return

    if node_key == "verifier":
        if set(value) != {"claims"} or not isinstance(value["claims"], list):
            raise ValueError("verifier schema mismatch")
        for item in value["claims"]:
            if (
                not isinstance(item, dict)
                or set(item) != {"id", "status"}
                or not isinstance(item["id"], str)
                or item["status"] not in {"supported", "unsupported"}
            ):
                raise ValueError("verifier schema mismatch")
        return

    if node_key == "synthesizer":
        if set(value) != {"factClaimIds", "unresolvedClaimIds"} or not all(
            _string_list(value[name]) for name in ("factClaimIds", "unresolvedClaimIds")
        ):
            raise ValueError("synthesizer schema mismatch")
        return

    if node_key == "critic":
        if set(value) != {"conflictClaimIds"} or not _string_list(value["conflictClaimIds"]):
            raise ValueError("critic schema mismatch")
        return

    raise ValueError("unknown agent result schema")


def validate_legacy_agent_result(node_key: str, value: dict[str, Any]) -> None:
    if node_key != "researcher":
        validate_agent_result(node_key, value)
        return
    if set(value) != {"claims"} or not isinstance(value["claims"], list):
        raise ValueError("researcher schema mismatch")
    for item in value["claims"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"text", "evidenceHandleIds"}
            or not isinstance(item["text"], str)
            or not 1 <= len(item["text"]) <= 12000
            or not _string_list(item["evidenceHandleIds"], minimum=1)
        ):
            raise ValueError("researcher schema mismatch")


def schemas_for_registry(entry: AgentIoRegistryEntry) -> dict[str, dict[str, object]]:
    resolved: dict[str, dict[str, object]] = {}
    for node_key in entry.roles:
        role = resolve_role_contract(entry, node_key)
        schema = _SCHEMAS_BY_ID.get(role.result_schema_id)
        if schema is None:
            raise ValueError("research_agent_role_version_unavailable")
        resolved[node_key] = schema
    return resolved


def validators_for_registry(
    entry: AgentIoRegistryEntry,
) -> dict[str, Callable[[str, dict[str, Any]], None]]:
    validators = {
        "research-agent-validator.v1": validate_agent_result,
        "research-agent-validator.legacy-v0": validate_legacy_agent_result,
    }
    resolved: dict[str, Callable[[str, dict[str, Any]], None]] = {}
    for node_key in entry.roles:
        role = resolve_role_contract(entry, node_key)
        validator = validators.get(role.validator_key)
        if validator is None:
            raise ValueError("research_agent_role_version_unavailable")
        resolved[node_key] = validator
    return resolved


def validator_for_registry(entry: AgentIoRegistryEntry) -> Callable[[str, dict[str, Any]], None]:
    validators = validators_for_registry(entry)

    def validate_bound(node_key: str, value: dict[str, Any], **_: object) -> None:
        validator = validators.get(node_key)
        if validator is None:
            raise ValueError("research_agent_role_version_unavailable")
        validator(node_key, value)

    return validate_bound


def validate_researcher_claim_evidence_scope(
    claims: Sequence[Mapping[str, Any]],
    *,
    branch_evidence_handle_ids: Sequence[str],
    allow_empty: bool = False,
) -> None:
    allowed = set(branch_evidence_handle_ids)
    if not claims and not allow_empty:
        raise ValueError("researcher claims must be non-empty")
    for claim in claims:
        handle_ids = claim.get("evidenceHandleIds")
        if not isinstance(handle_ids, list) or not handle_ids:
            raise ValueError("claim_requires_evidence")
        if len(handle_ids) != len(set(handle_ids)):
            raise ValueError("duplicate_claim_evidence")
        if not set(str(item) for item in handle_ids).issubset(allowed):
            raise ValueError("claim_evidence_not_in_branch")


def validate_verifier_claim_set(
    verifier_claims: Sequence[Mapping[str, Any]],
    *,
    researcher_claim_ids: Sequence[str],
) -> None:
    expected = set(researcher_claim_ids)
    observed = [str(item.get("id")) for item in verifier_claims]
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise ValueError("verifier_claim_set_mismatch")


def validate_critic_claim_set(
    conflict_claim_ids: Sequence[str],
    *,
    verified_claim_ids: Sequence[str],
) -> None:
    allowed = set(verified_claim_ids)
    if len(conflict_claim_ids) != len(set(conflict_claim_ids)):
        raise ValueError("critic_conflict_set_mismatch")
    if not set(conflict_claim_ids).issubset(allowed):
        raise ValueError("critic_conflict_set_mismatch")


def validate_synthesizer_claim_sets(
    *,
    fact_claim_ids: Sequence[str],
    unresolved_claim_ids: Sequence[str],
    allowed_claim_ids: Sequence[str],
) -> None:
    allowed = set(allowed_claim_ids)
    if len(fact_claim_ids) != len(set(fact_claim_ids)):
        raise ValueError("invalid_synthesis_selection")
    if len(unresolved_claim_ids) != len(set(unresolved_claim_ids)):
        raise ValueError("invalid_synthesis_selection")
    if not set(fact_claim_ids).issubset(allowed) or not set(unresolved_claim_ids).issubset(allowed):
        raise ValueError("invalid_synthesis_selection")
    if set(fact_claim_ids) & set(unresolved_claim_ids):
        raise ValueError("invalid_synthesis_selection")


def production_registry_versions() -> dict[str, str]:
    entry = require_current_production_registry()
    return {
        "agentResultSchemaVersion": entry.agent_result_schema_version,
        "contextPolicyVersion": entry.context_policy_version,
        "compactPolicyVersion": entry.compact_policy_version,
        "roleCount": str(len(PRODUCTION_REGISTRY.roles)),
    }
