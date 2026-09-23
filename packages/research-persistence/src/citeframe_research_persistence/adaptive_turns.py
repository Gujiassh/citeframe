"""Write-once model decisions; successful tool calls replay through their existing ledger."""
from copy import deepcopy
from datetime import UTC, datetime

from sqlalchemy import select
from citeframe_persistence.models import ResearchAdaptiveTurn, ResearchExecutionSnapshot
from .autonomy import ADAPTIVE_SCHEMA_VERSION, MAX_SUPPLEMENTAL_SEARCHES
from .errors import ResearchError, canonical_json, canonical_sha256
from .lease import _locked_attempt


def adaptive_turn(db, *, attempt_id, lease_token, turn_number, request, result=None, now=None):
    _, step, attempt = _locked_attempt(db, attempt_id=attempt_id, lease_token=lease_token, now=now or datetime.now(UTC))
    snapshot = db.get(ResearchExecutionSnapshot, step.execution_snapshot_id)
    if (step.step_kind != "researcher" or snapshot is None
            or snapshot.agent_result_schema_version != ADAPTIVE_SCHEMA_VERSION
            or type(turn_number) is not int or not 0 <= turn_number <= MAX_SUPPLEMENTAL_SEARCHES):
        raise ResearchError("research_state_conflict", "Invalid adaptive turn scope.", 409)
    query = request.get("toolContracts", {}).get("retrievalQuery")
    if not isinstance(query, str) or not query.strip() or len(query) > 4000:
        raise ResearchError("tool_input_invalid", "Invalid adaptive query.", 422)
    if len(canonical_json(request)) > 1_000_000:
        raise ResearchError("research_context_limit_exceeded", "Adaptive request is too large.", 409)
    request_hash = canonical_sha256(request)
    row = db.scalar(select(ResearchAdaptiveTurn).where(
        ResearchAdaptiveTurn.step_id == step.id, ResearchAdaptiveTurn.turn_number == turn_number
    ).execution_options(populate_existing=True))
    if row is not None:
        if (row.execution_snapshot_id != snapshot.id or row.query != query
                or row.request_sha256 != request_hash
                or row.result_sha256 != canonical_sha256(row.result_json)
                or (result is not None and row.result_sha256 != canonical_sha256(result))):
            raise ResearchError("research_state_conflict", "Adaptive replay input or result changed.", 409)
        return deepcopy(row.result_json)
    if turn_number:
        previous = db.get(ResearchAdaptiveTurn, (step.id, turn_number - 1))
        if (previous is None or previous.execution_snapshot_id != snapshot.id
                or previous.result_sha256 != canonical_sha256(previous.result_json)
                or previous.result_json.get("nextQuery") != query):
            raise ResearchError("research_state_conflict", "Adaptive predecessor is missing or changed.", 409)
    if result is None:
        return None
    if len(canonical_json(result)) > 1_000_000:
        raise ResearchError("research_context_limit_exceeded", "Adaptive result is too large.", 409)
    db.add(ResearchAdaptiveTurn(step_id=step.id, turn_number=turn_number,
        execution_snapshot_id=snapshot.id, created_by_attempt_id=attempt.id, query=query,
        request_sha256=request_hash, result_sha256=canonical_sha256(result), result_json=deepcopy(result)))
    db.flush()
    return deepcopy(result)
