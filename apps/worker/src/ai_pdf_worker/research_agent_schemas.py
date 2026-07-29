from __future__ import annotations

from typing import Any

AGENT_RESULT_SCHEMA_VERSION = "research-agent-results-v1"
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

    key = "conflictClaimIds" if node_key == "critic" else None
    if node_key == "synthesizer":
        if set(value) != {"factClaimIds", "unresolvedClaimIds"} or not all(
            _string_list(value[name]) for name in ("factClaimIds", "unresolvedClaimIds")
        ):
            raise ValueError("synthesizer schema mismatch")
        return
    if key is not None and (set(value) != {key} or not _string_list(value[key])):
        raise ValueError("critic schema mismatch")
    if key is None:
        raise ValueError("unknown agent result schema")
