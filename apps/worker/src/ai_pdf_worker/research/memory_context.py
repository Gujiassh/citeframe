"""Pure, unregistered transcript projection of already-authorized Research data.

Callers supply lawful shared-task input and fully loaded, committed journal rows
in native history order. Authorization, commit/provenance checks and private-data
exclusion belong before this boundary. Descriptors confer no read or evidence
rights. This module never constructs provider messages or executes transcript
content; downstream consumers must retain that data-only treatment.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy

from sqlalchemy import inspect

from citeframe_contracts import StepLease
from citeframe_persistence.models import ResearchAdaptiveTurn, ResearchConflictTurn
from citeframe_research_persistence.autonomy import MAX_SUPPLEMENTAL_SEARCHES
from citeframe_research_persistence.conflict_policy import MAX_INVESTIGATION_OPERATIONS
from citeframe_research_persistence.errors import canonical_sha256


_ROLES = {"planner", "researcher", "verifier", "critic", "investigator", "synthesizer"}
_CONFLICT_ROLES = {
    "inspect": "investigator",
    "verify": "verifier",
    "critic": "critic",
    "search": None,
    "finish": None,
}


def project_context(
    *,
    lease: StepLease,
    step_kind: str,
    role: str,
    goal: str,
    constraints: Mapping[str, object],
    system_prompt: str,
    role_input: Mapping[str, object],
    journals: Sequence[ResearchAdaptiveTurn | ResearchConflictTurn] = (),
) -> dict[str, object]:
    """Copy exact native input and journal bodies into local transcript data.

    ``role_input`` is the variables mapping passed to GenerationResearchAgents
    ``_json``; ``system_prompt`` is its resolved template. Goal and constraints
    come from authorized task context, without inferred confirmation. The whole
    current input is protected, including original evidence and result schemas.
    ``step_kind`` and ``role`` retain the consuming gate/nested-role distinction;
    their authority is a caller precondition, not validated by this projection.

    History order is supplied explicitly: native tables have no cross-Step
    chronology. No sorting, deduplication, summary or request reconstruction is
    performed. Repeated composite locators are rejected rather than collapsed.
    """
    if role not in _ROLES:
        raise ValueError("unsupported Research model role")
    consumer = {
        "stepId": lease.step_id,
        "attemptId": lease.attempt_id,
        "attemptNumber": lease.attempt_number,
        "stepKind": step_kind,
        "role": role,
    }
    history = []
    seen = set()
    for row in journals:
        record = _project_journal(row)
        source = record["source"]
        locator = source["locator"]
        key = tuple(locator.items())
        if key in seen:
            raise ValueError("duplicate native journal locator")
        seen.add(key)
        history.append(record)
    return {
        "kind": "research_transcript_data",
        "consumer": consumer,
        "protected": {
            "goal": deepcopy(goal),
            "constraints": deepcopy(dict(constraints)),
            "systemPrompt": system_prompt,
            "roleInput": deepcopy(dict(role_input)),
        },
        "history": history,
    }


def _project_journal(row: ResearchAdaptiveTurn | ResearchConflictTurn) -> dict:
    if not isinstance(row, (ResearchAdaptiveTurn, ResearchConflictTurn)):
        raise TypeError("expected a native Research journal row")
    # Expired/deferred ORM attributes could otherwise perform an implicit read.
    if inspect(row).unloaded:
        raise ValueError("journal row must be fully loaded before projection")
    adaptive = isinstance(row, ResearchAdaptiveTurn)
    ordinal = row.turn_number if adaptive else row.operation_number
    bound = MAX_SUPPLEMENTAL_SEARCHES + 1 if adaptive else MAX_INVESTIGATION_OPERATIONS
    if type(ordinal) is not int or not 0 <= ordinal < bound:
        raise ValueError("invalid native journal ordinal")
    if adaptive:
        _check_body(row.result_json, row.result_sha256)
        locator = {"kind": "adaptive", "stepId": row.step_id, "turnNumber": ordinal}
        producer_role = "researcher"
        status = "succeeded"
        request = {"availability": "not_stored", "sha256": row.request_sha256}
    else:
        if row.phase not in _CONFLICT_ROLES or row.status not in {"started", "succeeded"}:
            raise ValueError("invalid native conflict phase or status")
        _check_body(row.request_json, row.request_sha256)
        if row.status == "succeeded":
            _check_body(row.result_json, row.result_sha256)
        elif row.result_json is not None or row.result_sha256 is not None:
            raise ValueError("started conflict operation cannot carry a result")
        locator = {"kind": "conflict", "stepId": row.step_id, "operationNumber": ordinal}
        producer_role = _CONFLICT_ROLES[row.phase]
        status = row.status
        # These are native operation arguments, not necessarily _json variables.
        request = {
            "availability": "native_journal",
            "sha256": row.request_sha256,
            "body": deepcopy(row.request_json),
        }
    record = {
        "source": {
            "registration": "unregistered",
            "locator": locator,
            "executionSnapshotId": row.execution_snapshot_id,
        },
        "producer": {
            "stepId": row.step_id,
            "attemptId": row.created_by_attempt_id,
            "stepKind": "researcher" if adaptive else "conflict_decision_gate",
            "role": producer_role,
        },
        "status": status,
        "request": request,
        "result": {
            "availability": "native_journal" if status == "succeeded" else "not_recorded",
            "sha256": row.result_sha256,
            "body": deepcopy(row.result_json),
        },
    }
    if adaptive:
        record["query"] = row.query
    else:
        record["phase"] = row.phase
    return record


def _check_body(body: object, sha256: str | None) -> None:
    if not isinstance(body, dict) or sha256 != canonical_sha256(body):
        raise ValueError("native journal body/hash mismatch")
