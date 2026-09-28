"""Strict task-local summaries and annotated omission checks; no semantic truth claim."""
import json
from citeframe_contracts.memory import GenerationMessage, GenerationRequest, TextDelta, TurnComplete, Usage
from .guards import canonical
from .policy import CompactionError

ARRAYS = ("goals", "confirmedConstraints", "confirmedDecisions", "facts", "completedWork",
          "failedAttempts", "unresolved", "nextSteps")
ATOM_KEYS = {"key", "text", "attribution", "sourceRefs", "conditions", "quantities", "negated"}


def validate_summary(summary, units):
    if (not isinstance(summary, dict) or set(summary) != set(ARRAYS) | {"conflicts", "progress"}
            or len(canonical(summary).encode()) > 131072):
        raise CompactionError("invalid_summary_schema")
    refs = {(u.source.source_id, u.source.version, u.source.sha256) for u in units if u.source}
    tools = {u.tool_group_id for u in units if u.tool_group_id}
    atom_count = 0
    keys = set()
    def atom(value, confirmed=False):
        nonlocal atom_count
        if (not isinstance(value, dict) or set(value) != ATOM_KEYS
                or not isinstance(value["key"], str) or not 1 <= len(value["key"]) <= 128
                or value["key"] in keys or not isinstance(value["text"], str) or not 1 <= len(value["text"]) <= 2000
                or value["attribution"] not in ("user_explicit", "sourced_observation", "model_proposal")
                or type(value["negated"]) is not bool or not isinstance(value["sourceRefs"], list)
                or not value["sourceRefs"] or len(value["sourceRefs"]) > 128
                or not isinstance(value["conditions"], list) or len(value["conditions"]) > 128
                or any(not isinstance(c,str) or not 1 <= len(c) <= 2000 for c in value["conditions"])
                or not isinstance(value["quantities"], list) or len(value["quantities"]) > 128
                or (confirmed and value["attribution"] != "user_explicit")):
            raise CompactionError("invalid_summary_atom")
        if value["attribution"] == "user_explicit" or confirmed:
            # Activated native sources have no authenticated manual confirmation action.
            raise CompactionError("summary_confirmation_unattributable")
        keys.add(value["key"]); atom_count += 1
        for ref in value["sourceRefs"]:
            if not isinstance(ref, dict): raise CompactionError("invalid_summary_source")
            if set(ref) == {"source_id", "version", "sha256"}:
                if (ref["source_id"], ref["version"], ref["sha256"]) not in refs:
                    raise CompactionError("invalid_summary_source")
            elif set(ref) != {"tool_group_id"} or ref["tool_group_id"] not in tools:
                raise CompactionError("invalid_summary_source")
        for quantity in value["quantities"]:
            if (not isinstance(quantity, dict) or set(quantity) != {"value","unit","qualifier"}
                    or any(not isinstance(quantity[k],str) or len(quantity[k]) > 128 for k in quantity)):
                raise CompactionError("invalid_summary_quantity")
    for name in ARRAYS:
        if not isinstance(summary[name], list) or len(summary[name]) > 128:
            raise CompactionError("invalid_summary_array")
        for value in summary[name]: atom(value, name.startswith("confirmed"))
    if not isinstance(summary["conflicts"], list) or len(summary["conflicts"]) > 128:
        raise CompactionError("invalid_summary_conflicts")
    for conflict in summary["conflicts"]:
        if (not isinstance(conflict,dict) or set(conflict) != {"key","sideA","sideB","resolution","decisionSource"}
                or not isinstance(conflict["key"],str) or not 1 <= len(conflict["key"]) <= 128
                or conflict["resolution"] is not None or conflict["decisionSource"] is not None):
            raise CompactionError("invalid_summary_conflict")
        atom(conflict["sideA"]); atom(conflict["sideB"])
    progress = summary["progress"]
    if (not isinstance(progress,dict) or set(progress) != {"stepId","stateVersion","status","artifactIds"}
            or (progress["stepId"] is not None and not isinstance(progress["stepId"],str))
            or type(progress["stateVersion"]) is not int or progress["stateVersion"] < 1
            or not isinstance(progress["status"],str) or not isinstance(progress["artifactIds"],list)
            or any(not isinstance(id_,str) for id_ in progress["artifactIds"])):
        raise CompactionError("invalid_summary_progress")
    if not atom_count: raise CompactionError("empty_summary")
    return summary


def omission_findings(summary, *, quantities=(), conditions=(), negated_keys=(), conflict_keys=()):
    """Independent annotated-fixture oracle; its expectations never confer confirmation."""
    atoms = [atom for name in ARRAYS for atom in summary[name]]
    atoms += [side for conflict in summary["conflicts"] for side in (conflict["sideA"],conflict["sideB"])]
    findings = []
    available_quantities = {canonical(q) for a in atoms for q in a["quantities"]}
    available_conditions = {c for a in atoms for c in a["conditions"]}
    for q in quantities:
        if canonical(q) not in available_quantities: findings.append("quantity_omitted")
    for c in conditions:
        if c not in available_conditions: findings.append("condition_omitted")
    for key in negated_keys:
        if not any(a["key"] == key and a["negated"] for a in atoms): findings.append("negation_omitted")
    for key in conflict_keys:
        if not any(c["key"] == key for c in summary["conflicts"]): findings.append("conflict_omitted")
    return tuple(findings)


def collect_summary(generation, request, *, cancelled=lambda: False, max_bytes=131072):
    if request.purpose not in ("compact_chunk", "compact_merge") or request.tools:
        raise CompactionError("nonrecursive_summary_required")
    parts, length, complete, usage = [], 0, False, None
    for event in generation.stream_turn(request):
        if cancelled(): raise CompactionError("summary_cancelled")
        if complete: raise CompactionError("summary_protocol_after_complete")
        if isinstance(event, TextDelta):
            length += len(event.text.encode())
            if length > max_bytes: raise CompactionError("summary_output_limit")
            parts.append(event.text)
        elif isinstance(event, Usage): usage = event
        elif isinstance(event, TurnComplete) and event.reason == "answer": complete = True
        else: raise CompactionError("summary_protocol_invalid")
    if not complete: raise CompactionError("summary_outcome_unknown")
    try:
        result = json.loads("".join(parts))
    except (ValueError, RecursionError):
        raise CompactionError("invalid_summary_json") from None
    return result, usage
