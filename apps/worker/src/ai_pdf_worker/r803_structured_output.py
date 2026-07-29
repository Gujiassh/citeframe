from __future__ import annotations

from copy import deepcopy
from typing import cast

from ai_pdf_worker.research_agent_schemas import AGENT_RESULT_SCHEMAS

STRUCTURED_OUTPUT_TRANSPORT_VERSION = "responses-json-schema-v1"
STRUCTURED_OUTPUT_SCHEMA_SET_VERSION = "r803-provider-output-schemas-v2"
QUICK_RESULT_SCHEMA_VERSION = "r803-quick-result-v2"
PROMPT_RESULT_SCHEMA_NODES = {
    "planner": "planner",
    "researchers": "researcher",
    "verifier": "verifier",
    "critic": "critic",
    "synthesizer": "synthesizer",
}

QUICK_RESULT_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["answer", "claims", "conflictDetected"],
    "properties": {
        "answer": {"type": "string", "minLength": 1},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "evidenceIds"],
                "properties": {
                    "text": {"type": "string", "minLength": 1},
                    "evidenceIds": {
                        "type": "array",
                        "minItems": 1,
                        "uniqueItems": True,
                        "items": {"type": "string"},
                    },
                },
            },
        },
        "conflictDetected": {"type": "boolean"},
    },
}

SEMANTIC_RESULT_SCHEMAS: dict[str, dict[str, object]] = {
    "quick": QUICK_RESULT_SCHEMA,
    **AGENT_RESULT_SCHEMAS,
}

_UNSUPPORTED_PROVIDER_KEYWORDS = {
    "maxItems",
    "maxLength",
    "minLength",
    "minimum",
    "uniqueItems",
}


def _provider_schema(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _provider_schema(item)
            for key, item in value.items()
            if key not in _UNSUPPORTED_PROVIDER_KEYWORDS
        }
    if isinstance(value, list):
        return [_provider_schema(item) for item in value]
    return deepcopy(value)


PROVIDER_RESULT_SCHEMAS: dict[str, dict[str, object]] = {
    node_key: cast(dict[str, object], _provider_schema(schema))
    for node_key, schema in SEMANTIC_RESULT_SCHEMAS.items()
}


def structured_output_format(node_key: str) -> dict[str, object]:
    try:
        schema = PROVIDER_RESULT_SCHEMAS[node_key]
    except KeyError as error:
        raise ValueError("unsupported_structured_output_node") from error
    return {
        "type": "json_schema",
        "name": f"r803_{node_key}_v2",
        "strict": True,
        "schema": schema,
    }
