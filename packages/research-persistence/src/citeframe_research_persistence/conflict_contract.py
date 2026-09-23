"""Closed investigator result contract and literal source-condition checks."""

_TEXT = {"type":"string", "minLength":1, "maxLength":12000}
_IDS = {"type":"array", "minItems":1, "maxItems":100, "uniqueItems":True, "items":{"type":"string"}}
_CONDITION = {"type":["string", "null"], "minLength":1, "maxLength":1000}
INVESTIGATOR_SCHEMA = {"type":"object", "additionalProperties":False,
    "required":["inspections", "revisions", "gaps", "reason", "nextQuery"], "properties":{
    "inspections":{"type":"array", "minItems":1, "maxItems":100, "items":{
        "type":"object", "additionalProperties":False,
        "required":["evidenceHandleId", "quote", "version", "environment", "time", "conditions"],
        "properties":{"evidenceHandleId":{"type":"string"}, "quote":_TEXT,
            **{k:_CONDITION for k in ("version", "environment", "time", "conditions")}}}},
    "revisions":{"type":"array", "maxItems":100, "items":{"type":"object", "additionalProperties":False,
        "required":["originalClaimIds", "text", "evidenceHandleIds"],
        "properties":{"originalClaimIds":_IDS, "text":_TEXT, "evidenceHandleIds":_IDS}}},
    "gaps":{"type":"array", "maxItems":30, "items":_TEXT}, "reason":_TEXT,
    "nextQuery":{"type":["string", "null"], "minLength":1, "maxLength":1000}}}


def validate_investigation(value, *, claims=None, evidence=None):
    _validate(INVESTIGATOR_SCHEMA, value)
    if claims is None:
        return
    source = {c["id"]: c for c in claims}
    handles = {e["id"]: e for e in evidence}
    inspected = set()
    for item in value["inspections"]:
        handle = handles.get(item["evidenceHandleId"])
        if handle is None or item["evidenceHandleId"] in inspected or item["quote"] not in handle["excerpt"]:
            raise ValueError("investigator_source_quote_invalid")
        inspected.add(item["evidenceHandleId"])
        for key in ("version", "environment", "time", "conditions"):
            if item[key] is not None and item[key] not in item["quote"]:
                raise ValueError("investigator_invented_condition")
    required = {h for c in claims for h in c["evidenceHandleIds"]}
    if not required.issubset(inspected):
        raise ValueError("investigator_original_source_omitted")
    covered = set()
    for revision in value["revisions"]:
        if not set(revision["originalClaimIds"]).issubset(source) or not set(revision["evidenceHandleIds"]).issubset(inspected):
            raise ValueError("investigator_revision_scope_invalid")
        covered.update(revision["originalClaimIds"])
    if value["revisions"] and covered != set(source):
        raise ValueError("investigator_original_claim_omitted")


def _validate(schema, value):
    types = schema.get("type")
    types = [types] if isinstance(types, str) else types
    kind = "null" if value is None else "string" if isinstance(value, str) else "array" if isinstance(value, list) else "object" if isinstance(value, dict) else "invalid"
    if kind not in types:
        raise ValueError("investigator_schema_invalid")
    if kind == "string" and not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 12000):
        raise ValueError("investigator_schema_invalid")
    if kind == "object":
        if set(value) != set(schema["required"]):
            raise ValueError("investigator_schema_invalid")
        for key, item in value.items():
            _validate(schema["properties"][key], item)
    if kind == "array":
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 100):
            raise ValueError("investigator_schema_invalid")
        for item in value:
            _validate(schema["items"], item)
        if schema.get("uniqueItems") and len(set(value)) != len(value):
            raise ValueError("investigator_schema_invalid")
