"""Validation for the deliberately bounded function-tool schema subset."""

import math

from ._wire import WireLimits, bounded_text, strict_json

_TYPES = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool, "null": type(None)}
_COMMON = {"type", "description", "enum"}
_SPECIFIC = {
    "object": {"properties", "required", "additionalProperties"},
    "array": {"items", "minItems", "maxItems"},
    "string": {"minLength", "maxLength"},
    "integer": {"minimum", "maximum"},
    "number": {"minimum", "maximum"},
    "boolean": set(), "null": set(),
}


def equal(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(equal(a, b) for a, b in zip(left, right))
    return left == right


def check_schema(schema, depth=0):
    if depth > 16 or not isinstance(schema, dict) or schema.get("type") not in _TYPES:
        raise ValueError("unsupported tool schema")
    kind = schema["type"]
    if set(schema) - _COMMON - _SPECIFIC[kind]:
        raise ValueError("unsupported tool schema keyword")
    if "description" in schema and not isinstance(schema["description"], str):
        raise ValueError("invalid schema description")
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        raise ValueError("invalid schema enum")
    if kind == "object":
        props = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(props, dict) or not isinstance(required, list) or any(not isinstance(key, str) or key not in props for key in required) or len(set(required)) != len(required):
            raise ValueError("invalid object schema")
        if type(schema.get("additionalProperties", True)) is not bool:
            raise ValueError("unsupported additional properties schema")
        for value in props.values():
            check_schema(value, depth + 1)
    if kind == "array":
        check_schema(schema.get("items"), depth + 1)
    for key in ("minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems"):
        if key not in schema:
            continue
        bound = schema[key]
        if key in {"minimum", "maximum"}:
            if type(bound) not in (int, float) or not math.isfinite(bound):
                raise ValueError("invalid numeric schema bound")
        elif type(bound) is not int or bound < 0:
            raise ValueError("invalid size schema bound")
    for low, high in (("minimum", "maximum"), ("minLength", "maxLength"), ("minItems", "maxItems")):
        if low in schema and high in schema and schema[low] > schema[high]:
            raise ValueError("inverted schema bounds")


def validate(value, schema, depth=0):
    if depth > 16:
        raise ValueError("tool nesting limit")
    kind = schema["type"]
    if not isinstance(value, _TYPES[kind]) or (kind in {"integer", "number"} and isinstance(value, bool)):
        raise ValueError("tool argument type mismatch")
    if kind == "number" and not math.isfinite(value):
        raise ValueError("non-finite tool argument")
    if "enum" in schema and not any(equal(value, item) for item in schema["enum"]):
        raise ValueError("tool argument enum mismatch")
    if kind == "object":
        props = schema.get("properties", {})
        if set(schema.get("required", [])) - value.keys():
            raise ValueError("missing required tool argument")
        if not schema.get("additionalProperties", True) and value.keys() - props.keys():
            raise ValueError("unknown tool argument")
        for key, item in value.items():
            if key in props:
                validate(item, props[key], depth + 1)
    if kind == "array":
        for item in value:
            validate(item, schema["items"], depth + 1)
    for low, high, actual in (("minLength", "maxLength", len(value) if kind == "string" else None), ("minItems", "maxItems", len(value) if kind == "array" else None), ("minimum", "maximum", value if kind in {"integer", "number"} else None)):
        if actual is not None and ((low in schema and actual < schema[low]) or (high in schema and actual > schema[high])):
            raise ValueError("tool argument bound exceeded")


def schemas(tools, limits=WireLimits()):
    result = {}
    for tool in tools:
        bounded_text(tool.name, limits.max_id_bytes, "tool name", empty=False)
        bounded_text(tool.description, limits.max_argument_bytes, "tool description")
        bounded_text(tool.parameters_json, limits.max_argument_bytes, "tool schema", empty=False)
        if tool.name in result:
            raise ValueError("duplicate tool name")
        schema = strict_json(tool.parameters_json)
        check_schema(schema)
        if schema["type"] != "object":
            raise ValueError("tool schema must be object")
        result[tool.name] = schema
    return result
