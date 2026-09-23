"""Lease-guarded, write-once investigation operations shared across worker retries."""
from copy import deepcopy
from datetime import UTC, datetime
from sqlalchemy import select
from citeframe_persistence.models import ResearchConflictTurn, ResearchExecutionSnapshot, ResearchStep
from .conflict_policy import investigation_step
from .errors import ResearchError, canonical_json, canonical_sha256
from .lease import _locked_attempt


def conflict_turn(db, *, attempt_id, lease_token, operation_number, phase, request, result=None, now=None):
    _, step, attempt = _locked_attempt(db, attempt_id=attempt_id, lease_token=lease_token, now=now or datetime.now(UTC))
    snapshot = db.get(ResearchExecutionSnapshot, step.execution_snapshot_id)
    if (not investigation_step(step, snapshot) or type(operation_number) is not int
            or not 0 <= operation_number < 13 or phase not in {"inspect", "search", "verify", "critic", "finish"}):
        raise ResearchError("research_state_conflict", "Invalid investigation scope.", 409)
    if len(canonical_json(request)) > 1_000_000 or (result is not None and len(canonical_json(result)) > 1_000_000):
        raise ResearchError("research_context_limit_exceeded", "Investigation context exceeds its bound.", 409)
    request_hash = canonical_sha256(request)
    row = db.get(ResearchConflictTurn, (step.id, operation_number), populate_existing=True)
    if row is not None:
        if (row.execution_snapshot_id != snapshot.id or row.phase != phase or row.request_sha256 != request_hash
                or canonical_sha256(row.request_json) != request_hash
                or (row.result_json is not None and canonical_sha256(row.result_json) != row.result_sha256)):
            raise ResearchError("research_state_conflict", "Investigation replay changed.", 409)
        if row.status == "succeeded":
            if result is not None and canonical_sha256(result) != row.result_sha256:
                raise ResearchError("research_state_conflict", "Investigation result changed.", 409)
            return {"status":"succeeded", "result":deepcopy(row.result_json)}
        if result is None:
            # The caller cannot know whether the prior external call completed.
            return {"status":"outcome_unknown", "result":None}
    else:
        if result is not None:
            raise ResearchError("research_state_conflict", "Investigation operation was not reserved.", 409)
        previous = db.get(ResearchConflictTurn, (step.id, operation_number - 1)) if operation_number else None
        if operation_number and (previous is None or (previous.status != "succeeded" and phase != "finish") or previous.phase == "finish"):
            raise ResearchError("research_state_conflict", "Investigation predecessor is incomplete.", 409)
        if phase == "search":
            query = " ".join(request.get("query", "").split()).casefold()
            rows = list(db.scalars(select(ResearchConflictTurn).where(ResearchConflictTurn.step_id == step.id, ResearchConflictTurn.phase == "search")))
            if not query or len(query) > 1000 or len(rows) >= 2 or any(" ".join(r.request_json["query"].split()).casefold() == query for r in rows):
                raise ResearchError("research_state_conflict", "Investigation query limit or duplicate.", 409)
        row = ResearchConflictTurn(step_id=step.id, operation_number=operation_number,
            execution_snapshot_id=snapshot.id, created_by_attempt_id=attempt.id, phase=phase,
            status="started", request_sha256=request_hash, request_json=deepcopy(request))
        db.add(row); db.flush()
        return {"status":"reserved", "result":None}
    if row.created_by_attempt_id != attempt.id and phase != "finish":
        raise ResearchError("research_state_conflict", "Previous attempt outcome is ambiguous.", 409)
    if phase == "finish":
        _validate_outcome(db, step, request, result)
    row.result_json = deepcopy(result)
    row.result_sha256 = canonical_sha256(result)
    row.status = "succeeded"
    db.flush()
    return {"status":"succeeded", "result":deepcopy(result)}


def investigation_details(db, run_id):
    rows = list(db.scalars(select(ResearchConflictTurn).join(ResearchStep, ResearchStep.id == ResearchConflictTurn.step_id)
        .where(ResearchStep.run_id == run_id).order_by(ResearchConflictTurn.operation_number)))
    for row in rows:
        if canonical_sha256(row.request_json) != row.request_sha256 or (row.result_json is not None and canonical_sha256(row.result_json) != row.result_sha256):
            raise ResearchError("research_state_conflict", "Investigation integrity failed.", 409)
    return [{"operation":r.operation_number, "phase":r.phase, "status":r.status,
        "attemptId":r.created_by_attempt_id, "request":deepcopy(r.request_json), "result":deepcopy(r.result_json)} for r in rows]


def investigation_outcome(db, run_id):
    rows = investigation_details(db, run_id)
    if not rows:
        return None
    last = rows[-1]
    if last["phase"] != "finish" or last["status"] != "succeeded":
        raise ResearchError("research_state_conflict", "Investigation has no completed outcome.", 409)
    return last["result"]


def _validate_outcome(db, step, request, result):
    from citeframe_persistence.models import ResearchClaim
    original = list(db.scalars(select(ResearchClaim).where(ResearchClaim.run_id == step.run_id,
        ResearchClaim.conflict_status == "conflicted")))
    if (set(request["conflictClaimIds"]) != {c.id for c in original}
            or {c["id"] for c in result["originalClaims"]} != {c.id for c in original}):
        raise ResearchError("research_state_conflict", "Investigation original claim set changed.", 409)
    if not result["resolved"]:
        if result["revisions"] or not result["gaps"]:
            raise ResearchError("research_state_conflict", "Unresolved investigation lacks gaps.", 409)
        return
    records = list(db.scalars(select(ResearchConflictTurn).where(ResearchConflictTurn.step_id == step.id,
        ResearchConflictTurn.status == "succeeded").order_by(ResearchConflictTurn.operation_number)))
    if len(records) < 3 or [r.phase for r in records[-3:]] != ["inspect", "verify", "critic"]:
        raise ResearchError("research_state_conflict", "Resolution requires verification and conflict review.", 409)
    inspection, verification, critique = records[-3:]
    from .conflict_contract import validate_investigation
    validate_investigation(inspection.result_json, claims=inspection.request_json["claims"], evidence=inspection.request_json["evidence"])
    revisions = result["revisions"]
    if (not revisions or result["reason"] != "source_backed_revision"
            or [{k:v for k,v in c.items() if k != "id"} for c in revisions] != inspection.result_json["revisions"]
            or verification.request_json["revisions"] != revisions
            or critique.result_json != {"conflictClaimIds":[]}):
        raise ResearchError("research_state_conflict", "Resolution provenance is incomplete.", 409)
    checked = verification.result_json.get("claims", [])
    by_id = {c["id"]:c for c in checked}
    if len(checked) != len(revisions) or set(by_id) != {c["id"] for c in revisions} or any(
        by_id[c["id"]]["verification_status"] != "supported" or by_id[c["id"]]["text"] != c["text"]
        or list(by_id[c["id"]]["evidence_handle_ids"]) != c["evidenceHandleIds"] for c in revisions):
        raise ResearchError("research_state_conflict", "Resolution is not evidence verified.", 409)


def investigation_view(db, run_id, run_status):
    rows = investigation_details(db, run_id)
    if not rows:
        return None
    final = rows[-1]["result"] if rows[-1]["phase"] == "finish" and rows[-1]["status"] == "succeeded" else None
    inspection = next((r for r in reversed(rows) if r["phase"] == "inspect"), None)
    payload = final or (inspection["result"] if inspection and inspection["status"] == "succeeded" else {})
    sources = final.get("evidence", []) if final else inspection["request"]["evidence"] if inspection else []
    return {"status":("resolved" if final["resolved"] else "unresolved") if final else
                ("cancelled" if run_status == "cancelled" else "failed" if run_status in {"failed", "awaiting_retry"} else "running"),
        "phase":rows[-1]["phase"], "reason":final["reason"] if final else None,
        "explanation":final["explanation"] if final else None,
        "operations":[{"number":r["operation"], "phase":r["phase"], "status":r["status"]} for r in rows],
        "queries":[r["request"]["query"] for r in rows if r["phase"] == "search"],
        "inspections":payload.get("inspections", []), "gaps":payload.get("gaps", []),
        "originalClaims":final["originalClaims"] if final else inspection["request"]["claims"] if inspection else [],
        "revisions":final["revisions"] if final else [],
        "sources":[{"id":e["id"], "assetId":e["asset_id"], "locatorId":e["locator_id"],
                    "excerpt":e["excerpt"], "fingerprint":e["source_fingerprint_sha256"]} for e in sources]}
