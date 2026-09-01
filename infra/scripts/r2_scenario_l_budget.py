"""R2-L PostgreSQL budget exhaustion and reconciliation proof scenario.

This module is proof-only. It calls the frozen production persistence transitions from
independent operating-system processes and changes only per-scenario database fixtures.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from citeframe_persistence.models import (
    ResearchBudgetLedger,
    ResearchEvent,
    ResearchExecutionSnapshot,
    ResearchProviderCall,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
    ResearchToolCall,
)
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "infra/scripts/r2_scenario_l_worker.py"

PRODUCTION_SOURCE_FILES = (
    "packages/research-persistence/src/citeframe_research_persistence/provider.py",
    "packages/research-persistence/src/citeframe_research_persistence/tools.py",
    "packages/research-persistence/src/citeframe_research_persistence/state.py",
    "packages/research-persistence/src/citeframe_research_persistence/cancellation.py",
    "packages/research-persistence/src/citeframe_research_persistence/lease.py",
    "packages/research-persistence/src/citeframe_research_persistence/locks.py",
    "packages/research-persistence/src/citeframe_research_persistence/events.py",
    "packages/research-persistence/src/citeframe_research_persistence/errors.py",
    "packages/research-persistence/src/citeframe_research_persistence/membership.py",
    "packages/research-persistence/src/citeframe_research_persistence/policy.py",
    "packages/research-persistence/src/citeframe_research_persistence/types.py",
    "packages/research-persistence/src/citeframe_research_persistence/constants.py",
    "packages/backend-persistence/src/citeframe_persistence/models/__init__.py",
    "packages/backend-persistence/src/citeframe_persistence/models/research_execution.py",
    "packages/backend-persistence/src/citeframe_persistence/models/research_run.py",
    "packages/backend-persistence/src/citeframe_persistence/models/workspace.py",
    "packages/backend-persistence/src/citeframe_persistence/models/workspace_membership.py",
)

BUDGET_SEMANTICS = {
    "hardReservationGates": ["provider_call_count", "tool_call_count"],
    "providerTokenLimits": "per_call_context_and_output_ceiling",
    "cumulativeProviderTokensAreHardGate": False,
    "providerCostIsHardGate": False,
    "toolOutcomeUnknownOrReconcileApiClaimed": False,
    "toolLeaseRecoverySemantics": "running_to_abandoned_with_one_actual_call_charge",
}


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def git_bytes(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def production_source_proof(
    *,
    git_reader: Callable[..., bytes] = git_bytes,
    source_files: tuple[str, ...] = PRODUCTION_SOURCE_FILES,
) -> dict[str, Any]:
    """Bind every R2-L production boundary to the canonical checked-in HEAD blob."""

    base_sha = git_reader("rev-parse", "HEAD").decode("ascii").strip()
    hashes: dict[str, str] = {}
    blob_ids: dict[str, str] = {}
    for relative in source_files:
        expected_blob = git_reader("rev-parse", f"{base_sha}:{relative}").decode(
            "ascii"
        ).strip()
        current_blob = git_reader(
            "hash-object", f"--path={relative}", relative
        ).decode("ascii").strip()
        if current_blob != expected_blob:
            raise AssertionError(f"R2-L production source differs from baseSha: {relative}")
        canonical_source = git_reader("show", f"{base_sha}:{relative}")
        hashes[relative] = sha_bytes(canonical_source)
        blob_ids[relative] = expected_blob
    return {
        "baseSha": base_sha,
        "productionSourceSha256": hashes,
        "productionSourceGitBlobIds": blob_ids,
        "aggregateSha256": sha_bytes(canonical_bytes(hashes)),
        "matchesBaseSha": True,
    }


def manual_lease_expiry_violations(source: str) -> list[str]:
    """Reject proof-only lease mutation, including hidden raw-SQL equivalents."""

    violations: list[str] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            raw_targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            targets.extend(raw_targets)
        for target in targets:
            if isinstance(target, ast.Attribute) and target.attr == "lease_expires_at":
                violations.append(f"attribute_assignment:{getattr(node, 'lineno', 0)}")
    if re.search(
        r"UPDATE\s+research_step_attempts\b[\s\S]*?\blease_expires_at\b",
        source,
        re.IGNORECASE,
    ):
        violations.append("raw_sql_update")
    return violations


def json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


def row_value(row: Any) -> dict[str, Any]:
    return {
        attribute.key: json_value(getattr(row, attribute.key))
        for attribute in inspect(row).mapper.column_attrs
    }


def ordered_rows(db: Any, model: Any, *filters: Any) -> list[dict[str, Any]]:
    statement = select(model)
    if filters:
        statement = statement.where(*filters)
    statement = statement.order_by(model.id)
    return [row_value(row) for row in db.scalars(statement)]


def full_projection(runtime: Any, run_id: str) -> dict[str, Any]:
    """Project complete persisted rows for the budget aggregate."""

    with runtime.sessions() as db:
        run = db.get(ResearchRun, run_id)
        if run is None:
            raise AssertionError(f"R2-L run is missing: {run_id}")
        steps = ordered_rows(db, ResearchStep, ResearchStep.run_id == run_id)
        step_ids = [row["id"] for row in steps]
        attempts = (
            ordered_rows(db, ResearchStepAttempt, ResearchStepAttempt.step_id.in_(step_ids))
            if step_ids
            else []
        )
        for attempt in attempts:
            if attempt.get("lease_token_hash") is not None:
                attempt["lease_token_hash"] = "[redacted]"
        events = [
            row_value(row)
            for row in db.scalars(
                select(ResearchEvent)
                .where(ResearchEvent.run_id == run_id)
                .order_by(ResearchEvent.seq)
            )
        ]
        return {
            "run": row_value(run),
            "snapshots": ordered_rows(
                db,
                ResearchExecutionSnapshot,
                ResearchExecutionSnapshot.run_id == run_id,
            ),
            "steps": steps,
            "attempts": attempts,
            "events": events,
            "providerCalls": ordered_rows(
                db,
                ResearchProviderCall,
                ResearchProviderCall.run_id == run_id,
            ),
            "toolCalls": ordered_rows(
                db,
                ResearchToolCall,
                ResearchToolCall.run_id == run_id,
            ),
            "budgetLedgers": ordered_rows(
                db,
                ResearchBudgetLedger,
                ResearchBudgetLedger.run_id == run_id,
            ),
        }


def event_oracle(
    state: dict[str, Any],
    *,
    mode: str,
    run: dict[str, Any],
    step: dict[str, Any],
    attempt: dict[str, Any],
) -> dict[str, Any]:
    """Validate the complete, exact production event stream for one Attempt."""

    events = state["events"]
    event_types = [str(event["event_type"]) for event in events]
    expected_types = {
        "active": ["run_status_changed", "step_started"],
        "cancel_reclaim": [
            "run_status_changed",
            "step_started",
            "cancel_requested",
            "attempt_abandoned",
            "run_cancelled",
        ],
        "requeue_reclaim": [
            "run_status_changed",
            "step_started",
            "attempt_abandoned",
            "step_queued",
        ],
    }[mode]
    sequences = [int(event["seq"]) for event in events]
    dedupe_keys = [str(event["dedupe_key"]) for event in events]
    attempt_number = int(attempt["attempt_number"])
    common = [
        {
            "type": "run_status_changed",
            "stepId": None,
            "attemptId": None,
            "dedupeKey": f"worker-run-started:{attempt['id']}",
            "payload": {
                "previousStatus": "queued",
                "status": "running",
                "runStateVersion": 2,
                "reasonCode": None,
            },
        },
        {
            "type": "step_started",
            "stepId": step["id"],
            "attemptId": attempt["id"],
            "dedupeKey": f"step-started:{attempt['id']}",
            "payload": {
                "stepId": step["id"],
                "stepKind": step["step_kind"],
                "branchKey": step["branch_key"],
                "attemptId": attempt["id"],
                "attemptNumber": attempt_number,
                "stepStateVersion": 2,
                "runStateVersion": 3,
            },
        },
    ]
    expected = list(common)
    if mode == "cancel_reclaim":
        expected.extend(
            [
                {
                    "type": "cancel_requested",
                    "stepId": None,
                    "attemptId": None,
                    "dedupeKey": "cancel-requested:4",
                    "payload": {
                        "actorUserId": run["created_by_user_id"],
                        "reasonCode": "user_requested",
                        "runStateVersion": 4,
                    },
                },
                {
                    "type": "attempt_abandoned",
                    "stepId": step["id"],
                    "attemptId": attempt["id"],
                    "dedupeKey": f"attempt-abandoned:{attempt['id']}",
                    "payload": {
                        "stepId": step["id"],
                        "attemptId": attempt["id"],
                        "attemptNumber": attempt_number,
                        "reasonCode": "lease_expired",
                        "stepStateVersion": 3,
                        "runStateVersion": 5,
                    },
                },
                {
                    "type": "run_cancelled",
                    "stepId": None,
                    "attemptId": None,
                    "dedupeKey": f"run-cancelled:{run['id']}",
                    "payload": {
                        "status": "cancelled",
                        "reasonCode": "user_requested",
                        "runStateVersion": 6,
                    },
                },
            ]
        )
    elif mode == "requeue_reclaim":
        expected.extend(
            [
                {
                    "type": "attempt_abandoned",
                    "stepId": step["id"],
                    "attemptId": attempt["id"],
                    "dedupeKey": f"attempt-abandoned:{attempt['id']}",
                    "payload": {
                        "stepId": step["id"],
                        "attemptId": attempt["id"],
                        "attemptNumber": attempt_number,
                        "reasonCode": "lease_expired",
                        "stepStateVersion": 3,
                        "runStateVersion": 4,
                    },
                },
                {
                    "type": "step_queued",
                    "stepId": step["id"],
                    "attemptId": None,
                    "dedupeKey": f"step-queued:{step['id']}:{attempt_number}",
                    "payload": {
                        "stepId": step["id"],
                        "stepKind": step["step_kind"],
                        "branchKey": step["branch_key"],
                        "attemptNumber": attempt_number,
                        "stepStateVersion": 4,
                        "runStateVersion": 5,
                    },
                },
            ]
        )
    exact_rows = len(events) == len(expected) and all(
        event["workspace_id"] == run["workspace_id"]
        and event["run_id"] == run["id"]
        and event["event_schema_version"] == "1"
        and event["event_type"] == wanted["type"]
        and event["step_id"] == wanted["stepId"]
        and event["attempt_id"] == wanted["attemptId"]
        and event["dedupe_key"] == wanted["dedupeKey"]
        and event["payload_json"] == wanted["payload"]
        for event, wanted in zip(events, expected, strict=True)
    )
    run_versions = [int(event["payload_json"]["runStateVersion"]) for event in events]
    result = {
        "mode": mode,
        "eventTypes": event_types,
        "expectedEventTypes": expected_types,
        "noExtraEvents": event_types == expected_types,
        "sequences": sequences,
        "contiguousFromOne": sequences == list(range(1, len(events) + 1)),
        "dedupeKeysUnique": len(dedupe_keys) == len(set(dedupe_keys)),
        "exactRowsAndPayloads": exact_rows,
        "runStateVersions": run_versions,
        "runStateVersionsContiguous": run_versions
        == list(range(2, 2 + len(events))),
        "cancelOrderAndTerminal": mode != "cancel_reclaim"
        or (
            event_types.index("cancel_requested")
            < event_types.index("attempt_abandoned")
            < event_types.index("run_cancelled")
            and event_types[-1] == "run_cancelled"
            and run["status"] == "cancelled"
        ),
    }
    result["passed"] = all(
        value
        for key, value in result.items()
        if key
        in {
            "noExtraEvents",
            "contiguousFromOne",
            "dedupeKeysUnique",
            "exactRowsAndPayloads",
            "runStateVersionsContiguous",
            "cancelOrderAndTerminal",
        }
    )
    return result


def accounting_oracle(
    state: dict[str, Any],
    *,
    expected_provider_statuses: list[str],
    expected_tool_statuses: list[str],
    expected_attempt_status: str,
    expected_run_status: str,
    event_mode: str,
    expected_provider_requests: dict[str, str],
    expected_tool_requests: dict[str, str],
) -> dict[str, Any]:
    """Fail-closed bidirectional Call -> Ledger -> Attempt accounting proof."""

    try:
        exact_cardinality = (
            len(state["snapshots"]) == 1
            and len(state["steps"]) == 1
            and len(state["attempts"]) == 1
            and len(state["budgetLedgers"]) == 1
            and len(state["providerCalls"]) == len(expected_provider_statuses)
            and len(state["toolCalls"]) == len(expected_tool_statuses)
        )
        if not exact_cardinality:
            return {"passed": False, "exactCardinality": False}
        run = state["run"]
        snapshot = state["snapshots"][0]
        step = state["steps"][0]
        attempt = state["attempts"][0]
        ledger = state["budgetLedgers"][0]
        providers = state["providerCalls"]
        tools = state["toolCalls"]
        provider_statuses = Counter(str(call["status"]) for call in providers)
        tool_statuses = Counter(str(call["status"]) for call in tools)
        provider_terminal = [
            call
            for call in providers
            if call["status"] in {"succeeded", "failed", "outcome_unknown"}
        ]
        provider_reserved = [
            call for call in providers if call["status"] in {"reserved", "sent"}
        ]
        provider_actual = [
            call
            for call in providers
            if call["status"] in {"sent", "succeeded", "failed", "outcome_unknown"}
        ]
        tool_reserved = [
            call for call in tools if call["status"] in {"requested", "running"}
        ]
        tool_terminal = [
            call
            for call in tools
            if call["status"] in {"succeeded", "failed", "cancelled", "abandoned"}
        ]

        def timestamp(value: Any) -> datetime:
            if isinstance(value, datetime):
                return value
            return datetime.fromisoformat(str(value))

        def ordered_timestamps(*values: Any) -> bool:
            parsed = [timestamp(value) for value in values]
            return parsed == sorted(parsed)

        def provider_lifecycle_valid(call: dict[str, Any]) -> bool:
            status = str(call["status"])
            reserved_at = call["reserved_at"]
            sent_at = call["sent_at"]
            finished_at = call["finished_at"]
            actual_values = (
                call["actual_input_tokens"],
                call["actual_output_tokens"],
                call["actual_cost_microunits"],
            )
            base = (
                int(call["send_attempt"]) >= 1
                and reserved_at is not None
                and call["usage_source"] in {"reserved", "actual", "estimated"}
            )
            if status == "reserved":
                return base and (
                    sent_at is None
                    and finished_at is None
                    and all(value is None for value in actual_values)
                    and call["usage_source"] == "reserved"
                    and call["usage_final"] is False
                    and call["error_code"] is None
                )
            if status == "sent":
                return base and (
                    sent_at is not None
                    and finished_at is None
                    and ordered_timestamps(reserved_at, sent_at)
                    and all(value is None for value in actual_values)
                    and call["usage_source"] == "reserved"
                    and call["usage_final"] is False
                    and call["error_code"] is None
                )
            if status in {"succeeded", "failed"}:
                return base and (
                    sent_at is not None
                    and finished_at is not None
                    and ordered_timestamps(reserved_at, sent_at, finished_at)
                    and all(value is not None for value in actual_values)
                    and call["usage_source"] == "actual"
                    and call["usage_final"] is True
                    and (
                        (status == "succeeded" and call["error_code"] is None)
                        or (status == "failed" and bool(call["error_code"]))
                    )
                )
            if status == "outcome_unknown":
                return base and (
                    sent_at is not None
                    and finished_at is not None
                    and ordered_timestamps(reserved_at, sent_at, finished_at)
                    and all(value is not None for value in actual_values)
                    and call["usage_source"] == "estimated"
                    and call["usage_final"] is False
                    and call["error_code"] == "provider_outcome_unknown"
                )
            if status == "cancelled":
                return base and (
                    sent_at is None
                    and finished_at is not None
                    and ordered_timestamps(reserved_at, finished_at)
                    and all(value is None for value in actual_values)
                    and call["usage_source"] == "reserved"
                    and call["usage_final"] is True
                    and call["error_code"] is None
                )
            return False

        def tool_lifecycle_valid(call: dict[str, Any]) -> bool:
            status = str(call["status"])
            created_at = call["created_at"]
            started_at = call["started_at"]
            finished_at = call["finished_at"]
            error_code = call["error_code"]
            error_message = call["error_message"]
            base = (
                int(call["call_attempt_number"]) >= 1
                and int(call["call_order"]) >= 0
                and created_at is not None
            )
            if status == "requested":
                return base and (
                    started_at is None
                    and finished_at is None
                    and error_code is None
                    and error_message is None
                )
            if status == "running":
                return base and (
                    started_at is not None
                    and finished_at is None
                    and ordered_timestamps(created_at, started_at)
                    and error_code is None
                    and error_message is None
                )
            if status == "succeeded":
                return base and (
                    started_at is not None
                    and finished_at is not None
                    and ordered_timestamps(created_at, started_at, finished_at)
                    and error_code is None
                    and error_message is None
                )
            if status == "failed":
                return base and (
                    started_at is not None
                    and finished_at is not None
                    and ordered_timestamps(created_at, started_at, finished_at)
                    and bool(error_code)
                    and bool(error_message)
                )
            if status == "cancelled":
                return base and (
                    started_at is not None
                    and finished_at is not None
                    and ordered_timestamps(created_at, started_at, finished_at)
                )
            if status == "abandoned":
                return base and (
                    started_at is not None
                    and finished_at is not None
                    and ordered_timestamps(created_at, started_at, finished_at)
                    and error_code == "lease_expired"
                    and bool(error_message)
                )
            return False
        ledger_numbers = (
            "reserved_provider_calls",
            "actual_provider_calls",
            "reserved_tool_calls",
            "actual_tool_calls",
            "reserved_input_tokens",
            "actual_input_tokens",
            "reserved_output_tokens",
            "actual_output_tokens",
            "reserved_cost_microunits",
            "actual_cost_microunits",
        )
        ledger_nonnegative = all(
            ledger[field] is not None and int(ledger[field]) >= 0
            for field in ledger_numbers
        )
        attempt_nonnegative = all(
            attempt[field] is not None and int(attempt[field]) >= 0
            for field in (
                "provider_call_count",
                "tool_call_count",
                "input_tokens",
                "output_tokens",
                "cost_microunits",
            )
        )
        call_nonnegative = all(
            all(
                call[field] is not None and int(call[field]) >= 0
                for field in (
                    "reserved_input_tokens",
                    "reserved_output_tokens",
                    "reserved_cost_microunits",
                )
            )
            and (
                call not in provider_terminal
                or all(
                    call[field] is not None and int(call[field]) >= 0
                    for field in (
                        "actual_input_tokens",
                        "actual_output_tokens",
                        "actual_cost_microunits",
                    )
                )
            )
            for call in providers
        )
        scope_matches = (
            run["status"] == expected_run_status
            and snapshot["workspace_id"] == run["workspace_id"]
            and snapshot["run_id"] == run["id"]
            and step["workspace_id"] == run["workspace_id"]
            and step["run_id"] == run["id"]
            and step["execution_snapshot_id"] == snapshot["id"]
            and attempt["workspace_id"] == run["workspace_id"]
            and attempt["step_id"] == step["id"]
            and attempt["status"] == expected_attempt_status
            and ledger["workspace_id"] == run["workspace_id"]
            and ledger["run_id"] == run["id"]
            and ledger["execution_snapshot_id"] == snapshot["id"]
            and ledger["plan_revision_id"] is None
            and all(
                call["workspace_id"] == run["workspace_id"]
                and call["run_id"] == run["id"]
                and call["step_id"] == step["id"]
                and call["attempt_id"] == attempt["id"]
                and call["budget_ledger_id"] == ledger["id"]
                for call in providers
            )
            and all(
                call["workspace_id"] == run["workspace_id"]
                and call["run_id"] == run["id"]
                and call["execution_snapshot_id"] == snapshot["id"]
                and call["step_id"] == step["id"]
                and call["attempt_id"] == attempt["id"]
                for call in tools
            )
        )
        provider_ledger_matches = (
            int(ledger["reserved_provider_calls"])
            == sum(call["status"] == "reserved" for call in providers)
            and int(ledger["actual_provider_calls"]) == len(provider_actual)
            and int(ledger["reserved_input_tokens"])
            == sum(int(call["reserved_input_tokens"]) for call in provider_reserved)
            and int(ledger["reserved_output_tokens"])
            == sum(int(call["reserved_output_tokens"]) for call in provider_reserved)
            and int(ledger["reserved_cost_microunits"])
            == sum(int(call["reserved_cost_microunits"]) for call in provider_reserved)
            and int(ledger["actual_input_tokens"])
            == sum(int(call["actual_input_tokens"]) for call in provider_terminal)
            and int(ledger["actual_output_tokens"])
            == sum(int(call["actual_output_tokens"]) for call in provider_terminal)
            and int(ledger["actual_cost_microunits"])
            == sum(int(call["actual_cost_microunits"]) for call in provider_terminal)
            and bool(ledger["usage_final"])
            == all(bool(call["usage_final"]) for call in provider_terminal)
        )
        attempt_provider_matches = (
            int(attempt["provider_call_count"]) == len(provider_terminal)
            and int(attempt["input_tokens"])
            == sum(int(call["actual_input_tokens"]) for call in provider_terminal)
            and int(attempt["output_tokens"])
            == sum(int(call["actual_output_tokens"]) for call in provider_terminal)
            and int(attempt["cost_microunits"])
            == sum(int(call["actual_cost_microunits"]) for call in provider_terminal)
        )
        tool_accounting_matches = (
            int(ledger["reserved_tool_calls"]) == len(tool_reserved)
            and int(ledger["actual_tool_calls"]) == len(tool_terminal)
            and int(attempt["tool_call_count"]) == len(tool_terminal)
            and all(
                call["status"] != "abandoned"
                or call["error_code"] == "lease_expired"
                for call in tools
            )
        )
        usage_status_valid = all(
            call["status"] != "outcome_unknown" or call["usage_final"] is False
            for call in providers
        )
        lifecycle_status_valid = all(
            provider_lifecycle_valid(call) for call in providers
        ) and all(tool_lifecycle_valid(call) for call in tools)

        provider_attempts: dict[tuple[str, str], list[int]] = {}
        for call in providers:
            provider_attempts.setdefault(
                (str(call["attempt_id"]), str(call["logical_call_key"])), []
            ).append(int(call["send_attempt"]))
        tool_orders: dict[str, list[int]] = {}
        for call in tools:
            tool_orders.setdefault(str(call["attempt_id"]), []).append(
                int(call["call_order"])
            )
        call_ordering_valid = (
            len({str(call["id"]) for call in providers}) == len(providers)
            and len({str(call["id"]) for call in tools}) == len(tools)
            and all(
                sorted(attempts) == list(range(1, len(attempts) + 1))
                for attempts in provider_attempts.values()
            )
            and all(
                sorted(orders) == list(range(len(orders)))
                for orders in tool_orders.values()
            )
            and len(
                {
                    (
                        str(call["step_id"]),
                        str(call["tool_call_key"]),
                        int(call["call_attempt_number"]),
                    )
                    for call in tools
                }
            )
            == len(tools)
        )
        provider_version_cost = {
            "reserved": 1,
            "sent": 2,
            "succeeded": 3,
            "failed": 3,
            "outcome_unknown": 3,
            "cancelled": 2,
        }
        tool_version_cost = {
            "requested": 1,
            "running": 1,
            "succeeded": 2,
            "failed": 2,
            "cancelled": 2,
            "abandoned": 2,
        }
        expected_ledger_state_version = (
            1
            + sum(provider_version_cost[str(call["status"])] for call in providers)
            + sum(tool_version_cost[str(call["status"])] for call in tools)
        )
        currency_and_ledger_version_valid = (
            run["cost_currency"] == snapshot["cost_currency"] == ledger["currency"]
            and isinstance(ledger["currency"], str)
            and len(ledger["currency"]) == 3
            and int(ledger["state_version"]) == expected_ledger_state_version
            and ledger["updated_at"] is not None
        )
        sha256_pattern = re.compile(r"[0-9a-f]{64}")
        snapshot_call_bindings_valid = (
            all(
                call["provider"] == snapshot["generation_provider"]
                and call["model"] == snapshot["generation_model"]
                and call["provider_config_fingerprint"]
                == snapshot["provider_config_fingerprint"]
                and bool(sha256_pattern.fullmatch(str(call["request_sha256"])))
                and str(call["logical_call_key"]) in expected_provider_requests
                and call["request_sha256"]
                == expected_provider_requests[str(call["logical_call_key"])]
                for call in providers
            )
            and all(
                call["tool_name"] in {"evidence.search", "evidence.load"}
                and int(call["tool_version"]) == 1
                and bool(sha256_pattern.fullmatch(str(call["request_sha256"])))
                and str(call["tool_call_key"]) in expected_tool_requests
                and call["request_sha256"]
                == expected_tool_requests[str(call["tool_call_key"])]
                for call in tools
            )
        )
        within_limits = (
            int(ledger["reserved_provider_calls"])
            + int(ledger["actual_provider_calls"])
            <= int(snapshot["max_provider_calls"])
            and int(ledger["reserved_tool_calls"])
            + int(ledger["actual_tool_calls"])
            <= int(snapshot["max_tool_calls"])
        )
        event = event_oracle(
            state, mode=event_mode, run=run, step=step, attempt=attempt
        )
        run_versions = [
            int(item["payload_json"]["runStateVersion"]) for item in state["events"]
        ]
        step_versions = [
            int(item["payload_json"]["stepStateVersion"])
            for item in state["events"]
            if "stepStateVersion" in item["payload_json"]
        ]
        final_versions_valid = (
            int(run["state_version"]) == run_versions[-1]
            and int(run["next_event_seq"]) == len(state["events"]) + 1
            and int(step["state_version"]) == max(step_versions)
            and int(step["current_attempt_number"])
            == int(attempt["attempt_number"])
        )
        if event_mode == "active":
            final_status_rows_valid = (
                run["status"] == "running"
                and run["finished_at"] is None
                and run["failure_code"] is None
                and run["failure_message"] is None
                and run["cancel_reason_code"] is None
                and run["cancel_requested_at"] is None
                and step["status"] == "running"
                and step["error_code"] is None
                and step["error_message"] is None
                and step["finished_at"] is None
                and attempt["status"] == "running"
                and attempt["error_code"] is None
                and attempt["error_message"] is None
                and attempt["finished_at"] is None
                and attempt["lease_expires_at"] is not None
            )
        elif event_mode == "cancel_reclaim":
            final_status_rows_valid = (
                run["status"] == "cancelled"
                and run["finished_at"] is not None
                and run["failure_code"] is None
                and run["failure_message"] is None
                and run["cancel_reason_code"] == "user_requested"
                and run["cancel_requested_at"] is not None
                and step["status"] == "cancelled"
                and step["error_code"] == "lease_expired"
                and bool(step["error_message"])
                and step["finished_at"] is not None
                and attempt["status"] == "abandoned"
                and attempt["error_code"] == "lease_expired"
                and bool(attempt["error_message"])
                and attempt["finished_at"] is not None
                and attempt["lease_expires_at"] is None
            )
        else:
            final_status_rows_valid = (
                event_mode == "requeue_reclaim"
                and run["status"] == "running"
                and run["finished_at"] is None
                and run["failure_code"] is None
                and run["failure_message"] is None
                and run["cancel_reason_code"] is None
                and run["cancel_requested_at"] is None
                and step["status"] == "queued"
                and step["error_code"] == "lease_expired"
                and bool(step["error_message"])
                and step["finished_at"] is None
                and attempt["status"] == "abandoned"
                and attempt["error_code"] == "lease_expired"
                and bool(attempt["error_message"])
                and attempt["finished_at"] is not None
                and attempt["lease_expires_at"] is None
            )
        result = {
            "exactCardinality": exact_cardinality,
            "expectedProviderStatuses": dict(Counter(expected_provider_statuses)),
            "providerStatuses": dict(provider_statuses),
            "providerStatusesExact": provider_statuses
            == Counter(expected_provider_statuses),
            "expectedToolStatuses": dict(Counter(expected_tool_statuses)),
            "toolStatuses": dict(tool_statuses),
            "toolStatusesExact": tool_statuses == Counter(expected_tool_statuses),
            "scopeMatches": scope_matches,
            "ledgerFieldsNonnegative": ledger_nonnegative,
            "attemptFieldsNonnegative": attempt_nonnegative,
            "callFieldsNonnegative": call_nonnegative,
            "providerLedgerMatchesCalls": provider_ledger_matches,
            "attemptProviderUsageMatchesCalls": attempt_provider_matches,
            "toolLedgerAndAttemptMatchCalls": tool_accounting_matches,
            "usageStatusValid": usage_status_valid,
            "statusCoupledLifecycleValid": lifecycle_status_valid,
            "coreCallOrderingValid": call_ordering_valid,
            "currencyAndLedgerVersionValid": currency_and_ledger_version_valid,
            "snapshotCallBindingsValid": snapshot_call_bindings_valid,
            "expectedProviderRequestTruth": expected_provider_requests,
            "expectedToolRequestTruth": expected_tool_requests,
            "finalVersionsMatchEvents": final_versions_valid,
            "finalStatusRowsValid": final_status_rows_valid,
            "callCountsWithinFrozenLimits": within_limits,
            "eventOracle": event,
        }
        result["passed"] = all(
            value
            for key, value in result.items()
            if key
            in {
                "exactCardinality",
                "providerStatusesExact",
                "toolStatusesExact",
                "scopeMatches",
                "ledgerFieldsNonnegative",
                "attemptFieldsNonnegative",
                "callFieldsNonnegative",
                "providerLedgerMatchesCalls",
                "attemptProviderUsageMatchesCalls",
                "toolLedgerAndAttemptMatchCalls",
                "usageStatusValid",
                "statusCoupledLifecycleValid",
                "coreCallOrderingValid",
                "currencyAndLedgerVersionValid",
                "snapshotCallBindingsValid",
                "finalVersionsMatchEvents",
                "finalStatusRowsValid",
                "callCountsWithinFrozenLimits",
            }
        ) and event["passed"]
        return result
    except (KeyError, TypeError, ValueError, IndexError) as error:
        return {"passed": False, "error": f"{type(error).__name__}: {error}"}


def scrub_secrets(value: Any, secrets: set[str]) -> Any:
    if isinstance(value, dict):
        return {key: scrub_secrets(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub_secrets(item, secrets) for item in value]
    if isinstance(value, tuple):
        return [scrub_secrets(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[redacted]")
    return value


def read_ready_records(paths: list[Path], timeout_seconds: float) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if all(path.is_file() for path in paths):
            return [json.loads(path.read_text(encoding="utf-8")) for path in paths]
        time.sleep(0.02)
    missing = [str(path) for path in paths if not path.is_file()]
    raise TimeoutError(f"R2-L workers did not become ready: {missing}")


def observe_live_backends(
    database_url: str, ready_records: list[dict[str, Any]]
) -> dict[str, Any]:
    backend_pids = [int(record["pgBackendPid"]) for record in ready_records]
    parameters = {f"pid_{index}": pid for index, pid in enumerate(backend_pids)}
    placeholders = ", ".join(f":pid_{index}" for index in range(len(backend_pids)))
    engine = create_engine(database_url, future=True)
    try:
        with engine.connect() as connection:
            activity = list(
                connection.execute(
                    text(
                        f"""
                        SELECT pid AS "pgBackendPid", state,
                               wait_event_type AS "waitEventType",
                               wait_event AS "waitEvent"
                        FROM pg_stat_activity
                        WHERE pid IN ({placeholders})
                        ORDER BY pid
                        """
                    ),
                    parameters,
                ).mappings()
            )
            locks = list(
                connection.execute(
                    text(
                        f"""
                        SELECT pid AS "pgBackendPid", locktype AS "lockType",
                               mode, granted,
                               CASE WHEN relation IS NULL THEN NULL
                                    ELSE relation::regclass::text END AS relation
                        FROM pg_locks
                        WHERE pid IN ({placeholders})
                        ORDER BY pid, locktype, mode, relation
                        """
                    ),
                    parameters,
                ).mappings()
            )
    finally:
        engine.dispose()
    observed = {int(row["pgBackendPid"]) for row in activity}
    return {
        "evidenceKind": "identity_only_pre_operation",
        "requestedBackendPids": backend_pids,
        "allBackendsLiveAtBarrier": observed == set(backend_pids),
        "activity": [dict(row) for row in activity],
        "locks": [dict(row) for row in locks],
    }


def observe_operation_contention(
    runtime: Any,
    ready_records: list[dict[str, Any]],
    *,
    relation: str,
    blocker_pid: int,
    timeout_seconds: float,
    require_all_workers: bool = True,
) -> dict[str, Any]:
    """Capture worker-owned relation locks and transaction waits during an operation."""

    backend_pids = [int(record["pgBackendPid"]) for record in ready_records]
    parameters = {f"pid_{index}": pid for index, pid in enumerate(backend_pids)}
    placeholders = ", ".join(f":pid_{index}" for index in range(len(backend_pids)))
    deadline = time.monotonic() + timeout_seconds
    samples: list[dict[str, Any]] = []
    polls = 0
    while time.monotonic() < deadline:
        polls += 1
        with runtime.monitor_engine.connect() as connection:
            rows = list(
                connection.execute(
                    text(
                        f"""
                        SELECT a.pid AS "pgBackendPid", a.state,
                               a.wait_event_type AS "waitEventType",
                               a.wait_event AS "waitEvent",
                               pg_blocking_pids(a.pid) AS "blockingPids",
                               l.locktype AS "lockType", l.mode, l.granted,
                               CASE WHEN l.relation IS NULL THEN NULL
                                    ELSE l.relation::regclass::text END AS relation,
                               l.transactionid::text AS "transactionId",
                               l.virtualxid AS "virtualXid"
                        FROM pg_stat_activity AS a
                        JOIN pg_locks AS l ON l.pid = a.pid
                        WHERE a.pid IN ({placeholders})
                        ORDER BY a.pid, l.granted, l.locktype, l.mode, relation
                        """
                    ),
                    parameters,
                ).mappings()
            )
        sample_rows = [dict(row) for row in rows]
        sightings: dict[str, dict[str, Any]] = {}
        proved_count = 0
        for pid in backend_pids:
            owned = [row for row in sample_rows if int(row["pgBackendPid"]) == pid]
            granted_relation = [
                row
                for row in owned
                if row["lockType"] == "relation"
                and row["granted"] is True
                and row["relation"] == relation
            ]
            waiting_transaction = [
                row
                for row in owned
                if row["lockType"] == "transactionid" and row["granted"] is False
            ]
            sightings[str(pid)] = {
                "grantedRelationLocks": granted_relation,
                "waitingTransactionLocks": waiting_transaction,
                "blockedByController": any(
                    blocker_pid in list(row["blockingPids"] or []) for row in owned
                ),
            }
            if granted_relation and waiting_transaction:
                proved_count += 1
        samples.append({"poll": polls, "workerLocks": sightings})
        criterion_met = (
            proved_count == len(backend_pids)
            if require_all_workers
            else proved_count >= 1
        )
        if criterion_met:
            return {
                "evidenceKind": "worker_operation_contention",
                "relation": relation,
                "controllerBlockerPid": blocker_pid,
                "workerBackendPids": backend_pids,
                "pollCount": polls,
                "samples": samples,
                "finalWorkerLocks": sightings,
                "criterion": "all_workers"
                if require_all_workers
                else "at_least_one_worker",
                "allWorkersHaveGrantedRelationLock": all(
                    bool(value["grantedRelationLocks"])
                    for value in sightings.values()
                ),
                "allWorkersWaitingOnNonVirtualTransactionLock": all(
                    bool(value["waitingTransactionLocks"])
                    for value in sightings.values()
                ),
                "controllerLockNotCountedAsWorkerEvidence": True,
                "passed": True,
            }
        time.sleep(0.02)
    raise TimeoutError(
        "R2-L workers did not expose operation contention locks: "
        f"relation={relation}, samples={samples[-3:]}"
    )


def parse_worker_output(
    process: subprocess.Popen[str], timeout_seconds: float
) -> dict[str, Any]:
    stdout, stderr = process.communicate(timeout=timeout_seconds)
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(
            f"R2-L worker produced no record: exit={process.returncode}, stderr={stderr!r}"
        )
    record = json.loads(lines[-1])
    if process.returncode != 0 or int(record.get("exitStatus", 1)) != 0:
        raise RuntimeError(
            "R2-L worker failed: "
            f"exit={process.returncode}, record={record!r}, stderr={stderr!r}"
        )
    return record


def terminate_workers(workers: list[subprocess.Popen[str]]) -> None:
    for worker in workers:
        if worker.poll() is None:
            worker.terminate()
    for worker in workers:
        if worker.poll() is None:
            try:
                worker.wait(timeout=2)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=2)


def launch_workers(
    runtime: Any,
    database_url: str,
    timeout_seconds: float,
    *specs: dict[str, Any],
    operation_blocker: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workers: list[subprocess.Popen[str]] = []
    commands: dict[str, list[str]] = {}
    option_names = {
        "attemptId": "--attempt-id",
        "stepKey": "--step-key",
        "branchKey": "--branch-key",
        "leaseSeconds": "--lease-seconds",
        "logicalCallKey": "--logical-call-key",
        "providerCallId": "--provider-call-id",
        "requestSha256": "--request-sha256",
        "reservedInputTokens": "--reserved-input-tokens",
        "reservedOutputTokens": "--reserved-output-tokens",
        "actualInputTokens": "--actual-input-tokens",
        "actualOutputTokens": "--actual-output-tokens",
        "toolCallKey": "--tool-call-key",
        "toolCallId": "--tool-call-id",
        "toolName": "--tool-name",
        "runId": "--run-id",
        "workspaceId": "--workspace-id",
        "actorUserId": "--actor-user-id",
        "expectedStateVersion": "--expected-state-version",
    }
    try:
        with tempfile.TemporaryDirectory(prefix="citeframe-r2-l-") as directory:
            temporary = Path(directory)
            ready_files = [temporary / f"ready-{index}.json" for index in range(len(specs))]
            release_files = [temporary / f"release-{index}" for index in range(len(specs))]
            for index, spec in enumerate(specs):
                worker_id = str(spec["workerInstanceId"])
                command = [
                    sys.executable,
                    str(WORKER),
                    "--operation",
                    str(spec["operation"]),
                    "--database-url-env",
                    "CITEFRAME_R2_DATABASE_URL",
                    "--schema",
                    runtime.schema,
                    "--worker-instance-id",
                    worker_id,
                    "--ready-file",
                    str(ready_files[index]),
                    "--release-file",
                    str(release_files[index]),
                    "--wait-timeout-seconds",
                    str(timeout_seconds),
                ]
                for key, option in option_names.items():
                    if key in spec:
                        command.extend((option, str(spec[key])))
                environment = os.environ.copy()
                environment["CITEFRAME_R2_DATABASE_URL"] = database_url
                commands[worker_id] = command[2:]
                workers.append(
                    subprocess.Popen(
                        command,
                        cwd=ROOT,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env=environment,
                    )
                )
            ready = read_ready_records(ready_files, timeout_seconds)
            live = observe_live_backends(database_url, ready)
            assert live["allBackendsLiveAtBarrier"]
            contention = None
            if operation_blocker is None:
                for release in release_files:
                    release.write_text("release\n", encoding="utf-8")
            else:
                run_id = str(operation_blocker["runId"])
                relation = str(operation_blocker.get("relation", "research_runs"))
                with runtime.sessions() as run_blocker, runtime.sessions() as step_blocker:
                    run_blocker_pid = int(
                        run_blocker.scalar(text("SELECT pg_backend_pid()"))
                    )
                    locked = run_blocker.execute(
                        text(
                            "SELECT id FROM research_runs "
                            "WHERE id = :run_id FOR UPDATE"
                        ),
                        {"run_id": run_id},
                    ).scalar_one()
                    assert locked == run_id
                    step_blocker_pid = int(
                        step_blocker.scalar(text("SELECT pg_backend_pid()"))
                    )
                    blocked_step_id = step_blocker.execute(
                        text(
                            "SELECT id FROM research_steps WHERE run_id = :run_id "
                            "ORDER BY id LIMIT 1 FOR UPDATE"
                        ),
                        {"run_id": run_id},
                    ).scalar_one()
                    for release in release_files:
                        release.write_text("release\n", encoding="utf-8")
                    initial_run_block = observe_operation_contention(
                        runtime,
                        ready,
                        relation=relation,
                        blocker_pid=run_blocker_pid,
                        timeout_seconds=timeout_seconds,
                        require_all_workers=False,
                    )
                    run_blocker.commit()
                    contention = observe_operation_contention(
                        runtime,
                        ready,
                        relation=relation,
                        blocker_pid=step_blocker_pid,
                        timeout_seconds=timeout_seconds,
                    )
                    contention["controlledBlockers"] = {
                        "runRow": {
                            "relation": "research_runs",
                            "rowId": run_id,
                            "pgBackendPid": run_blocker_pid,
                        },
                        "stepRow": {
                            "relation": "research_steps",
                            "rowId": blocked_step_id,
                            "pgBackendPid": step_blocker_pid,
                        },
                    }
                    contention["initialRunBlockEvidence"] = initial_run_block
                    step_blocker.commit()
            records = [parse_worker_output(worker, timeout_seconds) for worker in workers]
            if len(records) > 1:
                assert len({int(record["osPid"]) for record in records}) == len(records)
                assert len({int(record["pgBackendPid"]) for record in records}) == len(records)
            for ready_record, record in zip(ready, records, strict=True):
                assert ready_record["workerInstanceId"] == record["workerInstanceId"]
                assert ready_record["osPid"] == record["osPid"]
                assert ready_record["pgBackendPid"] == record["pgBackendPid"]
                assert database_url not in json.dumps(record, sort_keys=True)
            evidence = {
                "readyRecords": ready,
                "identityOnlyPreOperation": live,
                "operationContention": contention,
                "processRecords": records,
                "workerArgv": commands,
            }
            secrets = {database_url}
            password = make_url(database_url).password
            if password:
                secrets.add(password)
            return scrub_secrets(evidence, secrets)
    finally:
        terminate_workers(workers)


def only_process(evidence: dict[str, Any]) -> dict[str, Any]:
    records = evidence["processRecords"]
    assert len(records) == 1
    return records[0]


def assert_outcomes(evidence: dict[str, Any], expected: list[str]) -> None:
    outcomes = sorted(str(record["outcome"]) for record in evidence["processRecords"])
    assert outcomes == sorted(expected)


def configure_limits(
    runtime: Any,
    fixture: Any,
    *,
    provider_calls: int,
    tool_calls: int,
    input_tokens: int = 10,
    output_tokens: int = 10,
) -> None:
    with runtime.sessions() as db:
        snapshot = db.get(ResearchExecutionSnapshot, fixture.snapshot_id)
        assert snapshot is not None
        snapshot.max_provider_calls = provider_calls
        snapshot.max_tool_calls = tool_calls
        snapshot.max_input_tokens = input_tokens
        snapshot.max_output_tokens = output_tokens
        snapshot.max_cost_microunits = 0
        db.commit()


class ClaimedLease(dict[str, Any]):
    @property
    def attempt_id(self) -> str:
        return str(self["attemptId"])


def claim_attempt(
    runtime: Any,
    database_url: str,
    timeout_seconds: float,
    fixture: Any,
    worker: str,
    *,
    lease_seconds: int = 120,
) -> dict[str, Any]:
    evidence = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        {
            "workerInstanceId": worker,
            "operation": "claim_specific",
            "runId": fixture.run_id,
            "stepKey": fixture.step_keys[0],
            "branchKey": fixture.branch_keys[0],
            "leaseSeconds": lease_seconds,
        },
    )
    record = only_process(evidence)
    assert record["outcome"] == "claimed"
    assert record["runId"] == fixture.run_id
    assert record["stepId"] == fixture.step_ids[0]
    assert int(record["leaseSeconds"]) == lease_seconds
    return {"processEvidence": evidence, "lease": ClaimedLease(record)}


def pg_clock_sample(runtime: Any, attempt_id: str) -> dict[str, Any]:
    with runtime.monitor_engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT clock_timestamp() AS "pgClock",
                       lease_expires_at AS "leaseExpiresAt",
                       clock_timestamp() >= lease_expires_at AS expired
                FROM research_step_attempts
                WHERE id = :attempt_id
                """
            ),
            {"attempt_id": attempt_id},
        ).mappings().one()
    return {key: json_value(value) for key, value in dict(row).items()}


def wait_for_pg_lease_expiry(
    runtime: Any, attempt_id: str, timeout_seconds: float
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    samples: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        sample = {"poll": len(samples) + 1, **pg_clock_sample(runtime, attempt_id)}
        samples.append(sample)
        if sample["expired"] is True:
            return {
                "oracle": "PostgreSQL clock_timestamp() >= persisted lease_expires_at",
                "pollCount": len(samples),
                "samples": samples,
                "expired": True,
            }
        time.sleep(0.05)
    raise TimeoutError(f"R2-L lease did not expire by PostgreSQL clock: {samples[-3:]}")


def reserve_spec(
    worker: str,
    attempt_id: str,
    logical_key: str,
    *,
    input_tokens: int = 9,
    output_tokens: int = 8,
) -> dict[str, Any]:
    return {
        "workerInstanceId": worker,
        "operation": "reserve_provider",
        "attemptId": attempt_id,
        "logicalCallKey": logical_key,
        "reservedInputTokens": input_tokens,
        "reservedOutputTokens": output_tokens,
    }


def request_truth(*keys: str) -> dict[str, str]:
    """Controller-owned request truth, independent from persisted Call rows."""

    return {key: sha_bytes(key.encode("utf-8")) for key in keys}


def sent_spec(worker: str, provider_call_id: str) -> dict[str, Any]:
    return {
        "workerInstanceId": worker,
        "operation": "mark_provider_sent",
        "providerCallId": provider_call_id,
    }


def reconcile_spec(
    worker: str,
    provider_call_id: str,
    *,
    input_tokens: int = 4,
    output_tokens: int = 3,
) -> dict[str, Any]:
    return {
        "workerInstanceId": worker,
        "operation": "reconcile_provider_succeeded",
        "providerCallId": provider_call_id,
        "actualInputTokens": input_tokens,
        "actualOutputTokens": output_tokens,
    }


def provider_call_count_race(
    runtime: Any, database_url: str, timeout_seconds: float
) -> dict[str, Any]:
    fixture = runtime.seed_run("r2-l-provider-count")
    configure_limits(runtime, fixture, provider_calls=1, tool_calls=1)
    claim = claim_attempt(
        runtime, database_url, timeout_seconds, fixture, "l-provider-owner"
    )
    lease = claim["lease"]
    before = full_projection(runtime, fixture.run_id)
    context_probe = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        reserve_spec(
            "l-provider-context-limit",
            lease.attempt_id,
            "l-provider-oversized",
            input_tokens=11,
            output_tokens=8,
        ),
    )
    assert only_process(context_probe)["outcome"] == "context_limit_exceeded"
    after_context_probe = full_projection(runtime, fixture.run_id)
    assert after_context_probe["providerCalls"] == []
    assert after_context_probe["budgetLedgers"] == before["budgetLedgers"]

    reserve_race = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        reserve_spec("l-provider-reserve-1", lease.attempt_id, "l-provider-1"),
        reserve_spec("l-provider-reserve-2", lease.attempt_id, "l-provider-2"),
        operation_blocker={"runId": fixture.run_id},
    )
    assert_outcomes(reserve_race, ["reserved", "budget_exhausted"])
    winner = next(
        record for record in reserve_race["processRecords"] if record["outcome"] == "reserved"
    )
    provider_call_id = str(winner["providerCallId"])
    mark_race = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        sent_spec("l-provider-mark-1", provider_call_id),
        sent_spec("l-provider-mark-2", provider_call_id),
    )
    assert_outcomes(mark_race, ["sent", "fenced"])
    reconcile_race = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        reconcile_spec("l-provider-reconcile-1", provider_call_id),
        reconcile_spec("l-provider-reconcile-2", provider_call_id),
        operation_blocker={"runId": fixture.run_id},
    )
    assert_outcomes(reconcile_race, ["reconciled", "fenced"])
    post_reserve = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        reserve_spec("l-provider-post-limit", lease.attempt_id, "l-provider-post"),
    )
    assert only_process(post_reserve)["outcome"] == "budget_exhausted"
    after = full_projection(runtime, fixture.run_id)
    call = after["providerCalls"][0]
    ledger = after["budgetLedgers"][0]
    assert len(after["providerCalls"]) == 1
    assert call["status"] == "succeeded"
    assert call["usage_source"] == "actual"
    assert call["usage_final"] is True
    assert ledger["actual_provider_calls"] == 1
    assert ledger["actual_input_tokens"] == 4
    assert ledger["actual_output_tokens"] == 3
    oracle = accounting_oracle(
        after,
        expected_provider_statuses=["succeeded"],
        expected_tool_statuses=[],
        expected_attempt_status="running",
        expected_run_status="running",
        event_mode="active",
        expected_provider_requests=request_truth("l-provider-1", "l-provider-2"),
        expected_tool_requests={},
    )
    assert oracle["passed"]
    return {
        "claim": claim,
        "before": before,
        "contextLimitProbe": context_probe,
        "afterContextLimitProbe": after_context_probe,
        "reserveRace": reserve_race,
        "markSentRace": mark_race,
        "reconcileRace": reconcile_race,
        "postReconcileReserve": post_reserve,
        "after": after,
        "oracles": oracle,
        "assertions": {
            "perCallTokenCeilingRejectedWithoutMutation": True,
            "doubleReserveExactlyOneReservedOneBudgetExhausted": True,
            "doubleMarkSentExactlyOneSentOneFenced": True,
            "doubleReconcileExactlyOneAppliedOneFenced": True,
            "providerUsageChargedExactlyOnce": True,
            "postReconcileReserveBudgetExhausted": True,
        },
    }


def provider_nonhard_token_cost_semantics(
    runtime: Any, database_url: str, timeout_seconds: float
) -> dict[str, Any]:
    fixture = runtime.seed_run("r2-l-provider-nonhard")
    configure_limits(runtime, fixture, provider_calls=2, tool_calls=1)
    claim = claim_attempt(
        runtime, database_url, timeout_seconds, fixture, "l-provider-nonhard-owner"
    )
    lease = claim["lease"]
    before = full_projection(runtime, fixture.run_id)
    phases: list[dict[str, Any]] = []
    for index in (1, 2):
        reserve = launch_workers(
            runtime,
            database_url,
            timeout_seconds,
            reserve_spec(
                f"l-provider-nonhard-reserve-{index}",
                lease.attempt_id,
                f"l-provider-nonhard-{index}",
                input_tokens=10,
                output_tokens=10,
            ),
        )
        record = only_process(reserve)
        assert record["outcome"] == "reserved"
        call_id = str(record["providerCallId"])
        mark = launch_workers(
            runtime,
            database_url,
            timeout_seconds,
            sent_spec(f"l-provider-nonhard-mark-{index}", call_id),
        )
        assert only_process(mark)["outcome"] == "sent"
        reconcile = launch_workers(
            runtime,
            database_url,
            timeout_seconds,
            reconcile_spec(
                f"l-provider-nonhard-reconcile-{index}",
                call_id,
                input_tokens=10,
                output_tokens=10,
            ),
        )
        assert only_process(reconcile)["outcome"] == "reconciled"
        phases.append({"reserve": reserve, "mark": mark, "reconcile": reconcile})
    post_reserve = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        reserve_spec("l-provider-nonhard-post", lease.attempt_id, "l-provider-nonhard-3"),
    )
    assert only_process(post_reserve)["outcome"] == "budget_exhausted"
    after = full_projection(runtime, fixture.run_id)
    ledger = after["budgetLedgers"][0]
    assert ledger["actual_provider_calls"] == 2
    assert ledger["actual_input_tokens"] == 20
    assert ledger["actual_output_tokens"] == 20
    assert int(ledger["actual_input_tokens"]) > int(after["snapshots"][0]["max_input_tokens"])
    assert int(ledger["actual_output_tokens"]) > int(
        after["snapshots"][0]["max_output_tokens"]
    )
    assert int(ledger["actual_cost_microunits"]) > int(
        after["snapshots"][0]["max_cost_microunits"]
    )
    oracle = accounting_oracle(
        after,
        expected_provider_statuses=["succeeded", "succeeded"],
        expected_tool_statuses=[],
        expected_attempt_status="running",
        expected_run_status="running",
        event_mode="active",
        expected_provider_requests=request_truth(
            "l-provider-nonhard-1", "l-provider-nonhard-2"
        ),
        expected_tool_requests={},
    )
    assert oracle["passed"]
    return {
        "claim": claim,
        "before": before,
        "callPhases": phases,
        "postCallCountReserve": post_reserve,
        "after": after,
        "oracles": oracle,
        "assertions": {
            "twoPerCallBoundedReservationsSucceeded": True,
            "cumulativeInputTokensCanExceedPerCallCeiling": True,
            "cumulativeOutputTokensCanExceedPerCallCeiling": True,
            "costCanExceedFrozenMetadataWithoutBlocking": True,
            "thirdCallRejectedByCallCount": True,
        },
    }


def provider_unsent_linearization(
    runtime: Any, database_url: str, timeout_seconds: float
) -> dict[str, Any]:
    fixture = runtime.seed_run("r2-l-provider-unsent")
    configure_limits(runtime, fixture, provider_calls=1, tool_calls=1)
    claim = claim_attempt(
        runtime, database_url, timeout_seconds, fixture, "l-provider-unsent-owner"
    )
    lease = claim["lease"]
    reserve = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        reserve_spec("l-provider-unsent-reserve", lease.attempt_id, "l-provider-unsent"),
    )
    call_id = str(only_process(reserve)["providerCallId"])
    before = full_projection(runtime, fixture.run_id)
    race = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        sent_spec("l-provider-unsent-mark", call_id),
        {
            "workerInstanceId": "l-provider-unsent-cancel",
            "operation": "cancel_provider_reservation",
            "providerCallId": call_id,
        },
    )
    outcomes = sorted(record["outcome"] for record in race["processRecords"])
    completion: dict[str, Any]
    if outcomes == ["fenced", "sent"]:
        linearization = "mark_sent_before_cancel_reservation"
        completion = {
            "reconcile": launch_workers(
                runtime,
                database_url,
                timeout_seconds,
                reconcile_spec("l-provider-unsent-reconcile", call_id),
            )
        }
        assert only_process(completion["reconcile"])["outcome"] == "reconciled"
    elif outcomes == ["cancelled", "fenced"]:
        linearization = "cancel_reservation_before_mark_sent"
        replacement = launch_workers(
            runtime,
            database_url,
            timeout_seconds,
            reserve_spec(
                "l-provider-unsent-replacement",
                lease.attempt_id,
                "l-provider-unsent-replacement",
            ),
        )
        replacement_id = str(only_process(replacement)["providerCallId"])
        mark = launch_workers(
            runtime,
            database_url,
            timeout_seconds,
            sent_spec("l-provider-unsent-replacement-mark", replacement_id),
        )
        reconcile = launch_workers(
            runtime,
            database_url,
            timeout_seconds,
            reconcile_spec("l-provider-unsent-replacement-reconcile", replacement_id),
        )
        assert only_process(replacement)["outcome"] == "reserved"
        assert only_process(mark)["outcome"] == "sent"
        assert only_process(reconcile)["outcome"] == "reconciled"
        completion = {"replacement": replacement, "mark": mark, "reconcile": reconcile}
    else:
        raise AssertionError(f"illegal unsent provider linearization: {outcomes}")
    post_reserve = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        reserve_spec("l-provider-unsent-post", lease.attempt_id, "l-provider-unsent-post"),
    )
    assert only_process(post_reserve)["outcome"] == "budget_exhausted"
    after = full_projection(runtime, fixture.run_id)
    assert after["budgetLedgers"][0]["actual_provider_calls"] == 1
    assert len([call for call in after["providerCalls"] if call["status"] == "succeeded"]) == 1
    expected_statuses = (
        ["succeeded"]
        if linearization == "mark_sent_before_cancel_reservation"
        else ["cancelled", "succeeded"]
    )
    oracle = accounting_oracle(
        after,
        expected_provider_statuses=expected_statuses,
        expected_tool_statuses=[],
        expected_attempt_status="running",
        expected_run_status="running",
        event_mode="active",
        expected_provider_requests=request_truth(
            "l-provider-unsent", "l-provider-unsent-replacement"
        ),
        expected_tool_requests={},
    )
    assert oracle["passed"]
    return {
        "claim": claim,
        "reserve": reserve,
        "beforeRace": before,
        "race": race,
        "linearization": linearization,
        "completion": completion,
        "postCompletionReserve": post_reserve,
        "after": after,
        "oracles": oracle,
        "assertions": {
            "raceHasOneLegalWinner": True,
            "loserFenced": True,
            "winningBranchCompleted": True,
            "exactlyOneProviderCallCharged": True,
            "postCompletionReserveBudgetExhausted": True,
        },
    }


def provider_sent_cancel_reclaim(
    runtime: Any, database_url: str, timeout_seconds: float
) -> dict[str, Any]:
    fixture = runtime.seed_run("r2-l-provider-reclaim")
    configure_limits(runtime, fixture, provider_calls=1, tool_calls=1)
    claim = claim_attempt(
        runtime,
        database_url,
        timeout_seconds,
        fixture,
        "l-provider-reclaim-owner",
        lease_seconds=8,
    )
    lease = claim["lease"]
    reserve = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        reserve_spec("l-provider-reclaim-reserve", lease.attempt_id, "l-provider-reclaim"),
    )
    call_id = str(only_process(reserve)["providerCallId"])
    mark = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        sent_spec("l-provider-reclaim-mark", call_id),
    )
    assert only_process(mark)["outcome"] == "sent"
    before_cancel = full_projection(runtime, fixture.run_id)
    cancel = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        {
            "workerInstanceId": "l-provider-reclaim-cancel",
            "operation": "cancel_run",
            "runId": fixture.run_id,
            "workspaceId": runtime.workspace_id,
            "actorUserId": runtime.user_id,
            "expectedStateVersion": before_cancel["run"]["state_version"],
        },
    )
    assert only_process(cancel)["outcome"] == "cancelled"
    assert only_process(cancel)["runStatus"] == "cancel_requested"
    pre_expiry_clock = pg_clock_sample(runtime, lease.attempt_id)
    assert pre_expiry_clock["expired"] is False
    before_pre_expiry_reclaim = full_projection(runtime, fixture.run_id)
    pre_expiry_reclaim = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        {
            "workerInstanceId": "l-provider-pre-expiry-reclaim",
            "operation": "reclaim",
        },
    )
    assert only_process(pre_expiry_reclaim)["reclaimedCount"] == 0
    after_pre_expiry_reclaim = full_projection(runtime, fixture.run_id)
    assert after_pre_expiry_reclaim == before_pre_expiry_reclaim
    natural_expiry = wait_for_pg_lease_expiry(
        runtime, lease.attempt_id, timeout_seconds
    )
    reclaim = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        {"workerInstanceId": "l-provider-reclaim", "operation": "reclaim"},
    )
    assert only_process(reclaim)["reclaimedCount"] == 1
    after_reclaim = full_projection(runtime, fixture.run_id)
    assert after_reclaim["providerCalls"][0]["status"] == "outcome_unknown"
    assert after_reclaim["providerCalls"][0]["usage_source"] == "estimated"
    assert after_reclaim["providerCalls"][0]["usage_final"] is False
    assert after_reclaim["providerCalls"][0]["actual_input_tokens"] == 9
    assert after_reclaim["providerCalls"][0]["actual_output_tokens"] == 8
    late_reconcile = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        reconcile_spec("l-provider-reclaim-late-1", call_id),
        reconcile_spec("l-provider-reclaim-late-2", call_id),
    )
    assert_outcomes(late_reconcile, ["fenced", "fenced"])
    after = full_projection(runtime, fixture.run_id)
    assert after == after_reclaim
    assert after["run"]["status"] == "cancelled"
    oracle = accounting_oracle(
        after,
        expected_provider_statuses=["outcome_unknown"],
        expected_tool_statuses=[],
        expected_attempt_status="abandoned",
        expected_run_status="cancelled",
        event_mode="cancel_reclaim",
        expected_provider_requests=request_truth("l-provider-reclaim"),
        expected_tool_requests={},
    )
    assert oracle["passed"]
    return {
        "claim": claim,
        "reserve": reserve,
        "markSent": mark,
        "beforeCancel": before_cancel,
        "cancel": cancel,
        "preExpiryClockSample": pre_expiry_clock,
        "beforePreExpiryReclaim": before_pre_expiry_reclaim,
        "preExpiryReclaim": pre_expiry_reclaim,
        "afterPreExpiryReclaim": after_pre_expiry_reclaim,
        "naturalExpiry": natural_expiry,
        "reclaim": reclaim,
        "afterReclaim": after_reclaim,
        "lateReconcileRace": late_reconcile,
        "after": after,
        "oracles": oracle,
        "assertions": {
            "sentCallRecoveredAsOutcomeUnknown": True,
            "reservedTokensConservativelyChargedOnce": True,
            "lateReconciliationFenced": True,
            "lateReconciliationZeroMutation": True,
            "cancelFinalizedAfterExpiredLease": True,
            "preExpiryReclaimReturnedZeroWithFullProjectionUnchanged": True,
            "leaseExpiredNaturallyByPostgresClock": True,
        },
    }


def tool_call_count_race(
    runtime: Any, database_url: str, timeout_seconds: float
) -> dict[str, Any]:
    fixture = runtime.seed_run("r2-l-tool-count")
    configure_limits(runtime, fixture, provider_calls=1, tool_calls=1)
    claim = claim_attempt(runtime, database_url, timeout_seconds, fixture, "l-tool-owner")
    lease = claim["lease"]
    before = full_projection(runtime, fixture.run_id)
    begin_race = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        {
            "workerInstanceId": "l-tool-begin-1",
            "operation": "begin_tool",
            "attemptId": lease.attempt_id,
            "toolCallKey": "l-tool-1",
        },
        {
            "workerInstanceId": "l-tool-begin-2",
            "operation": "begin_tool",
            "attemptId": lease.attempt_id,
            "toolCallKey": "l-tool-2",
        },
        operation_blocker={"runId": fixture.run_id},
    )
    assert_outcomes(begin_race, ["running", "budget_exhausted"])
    winner = next(
        record for record in begin_race["processRecords"] if record["outcome"] == "running"
    )
    tool_call_id = str(winner["toolCallId"])
    complete_race = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        {
            "workerInstanceId": "l-tool-complete-1",
            "operation": "complete_tool",
            "toolCallId": tool_call_id,
        },
        {
            "workerInstanceId": "l-tool-complete-2",
            "operation": "complete_tool",
            "toolCallId": tool_call_id,
        },
        operation_blocker={"runId": fixture.run_id},
    )
    assert_outcomes(complete_race, ["completed", "fenced"])
    post_begin = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        {
            "workerInstanceId": "l-tool-post-limit",
            "operation": "begin_tool",
            "attemptId": lease.attempt_id,
            "toolCallKey": "l-tool-post",
        },
    )
    assert only_process(post_begin)["outcome"] == "budget_exhausted"
    after = full_projection(runtime, fixture.run_id)
    assert len(after["toolCalls"]) == 1
    assert after["toolCalls"][0]["status"] == "succeeded"
    assert after["budgetLedgers"][0]["actual_tool_calls"] == 1
    oracle = accounting_oracle(
        after,
        expected_provider_statuses=[],
        expected_tool_statuses=["succeeded"],
        expected_attempt_status="running",
        expected_run_status="running",
        event_mode="active",
        expected_provider_requests={},
        expected_tool_requests=request_truth("l-tool-1", "l-tool-2"),
    )
    assert oracle["passed"]
    return {
        "claim": claim,
        "before": before,
        "beginRace": begin_race,
        "completeRace": complete_race,
        "postCompleteBegin": post_begin,
        "after": after,
        "oracles": oracle,
        "assertions": {
            "doubleBeginExactlyOneRunningOneBudgetExhausted": True,
            "doubleCompleteExactlyOneCompletedOneFenced": True,
            "toolUsageChargedExactlyOnce": True,
            "postCompleteBeginBudgetExhausted": True,
        },
    }


def tool_expiry_reclaim(
    runtime: Any, database_url: str, timeout_seconds: float
) -> dict[str, Any]:
    fixture = runtime.seed_run("r2-l-tool-reclaim")
    configure_limits(runtime, fixture, provider_calls=1, tool_calls=1)
    claim = claim_attempt(
        runtime,
        database_url,
        timeout_seconds,
        fixture,
        "l-tool-reclaim-owner",
        lease_seconds=5,
    )
    lease = claim["lease"]
    begin = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        {
            "workerInstanceId": "l-tool-reclaim-begin",
            "operation": "begin_tool",
            "attemptId": lease.attempt_id,
            "toolCallKey": "l-tool-reclaim",
        },
    )
    tool_call_id = str(only_process(begin)["toolCallId"])
    before = full_projection(runtime, fixture.run_id)
    pre_expiry_clock = pg_clock_sample(runtime, lease.attempt_id)
    assert pre_expiry_clock["expired"] is False
    pre_expiry_reclaim = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        {
            "workerInstanceId": "l-tool-pre-expiry-reclaim",
            "operation": "reclaim",
        },
    )
    assert only_process(pre_expiry_reclaim)["reclaimedCount"] == 0
    after_pre_expiry_reclaim = full_projection(runtime, fixture.run_id)
    assert after_pre_expiry_reclaim == before
    natural_expiry = wait_for_pg_lease_expiry(
        runtime, lease.attempt_id, timeout_seconds
    )
    reclaim = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        {"workerInstanceId": "l-tool-reclaim", "operation": "reclaim"},
    )
    assert only_process(reclaim)["reclaimedCount"] == 1
    after_reclaim = full_projection(runtime, fixture.run_id)
    assert after_reclaim["toolCalls"][0]["status"] == "abandoned"
    assert after_reclaim["toolCalls"][0]["error_code"] == "lease_expired"
    late_complete = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        {
            "workerInstanceId": "l-tool-reclaim-late-complete",
            "operation": "complete_tool",
            "toolCallId": tool_call_id,
        },
    )
    assert only_process(late_complete)["outcome"] == "fenced"
    post_begin = launch_workers(
        runtime,
        database_url,
        timeout_seconds,
        {
            "workerInstanceId": "l-tool-reclaim-post-limit",
            "operation": "begin_tool",
            "attemptId": lease.attempt_id,
            "toolCallKey": "l-tool-reclaim-post",
        },
    )
    assert only_process(post_begin)["outcome"] == "fenced"
    after = full_projection(runtime, fixture.run_id)
    assert after == after_reclaim
    oracle = accounting_oracle(
        after,
        expected_provider_statuses=[],
        expected_tool_statuses=["abandoned"],
        expected_attempt_status="abandoned",
        expected_run_status="running",
        event_mode="requeue_reclaim",
        expected_provider_requests={},
        expected_tool_requests=request_truth("l-tool-reclaim"),
    )
    assert oracle["passed"]
    return {
        "claim": claim,
        "begin": begin,
        "beforeExpiry": before,
        "preExpiryClockSample": pre_expiry_clock,
        "preExpiryReclaim": pre_expiry_reclaim,
        "afterPreExpiryReclaim": after_pre_expiry_reclaim,
        "naturalExpiry": natural_expiry,
        "reclaim": reclaim,
        "afterReclaim": after_reclaim,
        "lateComplete": late_complete,
        "postReclaimBegin": post_begin,
        "after": after,
        "oracles": oracle,
        "assertions": {
            "expiredToolCallAbandoned": True,
            "abandonedToolChargedExactlyOnce": True,
            "lateCompleteFenced": True,
            "lateCompleteZeroMutation": True,
            "noToolOutcomeUnknownOrReconcileClaim": True,
            "preExpiryReclaimReturnedZeroWithFullProjectionUnchanged": True,
            "leaseExpiredNaturallyByPostgresClock": True,
        },
    }


def lock_projection(runtime: Any) -> dict[str, Any]:
    with runtime.monitor_engine.connect() as connection:
        rows = list(
            connection.execute(
                text(
                    """
                    SELECT locktype AS "lockType", mode, granted,
                           CASE WHEN relation IS NULL THEN NULL
                                ELSE relation::regclass::text END AS relation
                    FROM pg_locks
                    WHERE pid = pg_backend_pid()
                    ORDER BY locktype, mode, relation
                    """
                )
            ).mappings()
        )
    return {
        "evidenceKind": "controller_identity_only_not_operation_contention",
        "controllerLocks": [dict(row) for row in rows],
    }


def run_scenario(
    runtime: Any, database_url: str, timeout_seconds: float
) -> dict[str, Any]:
    """Run the complete R2-L proof against a configured PostgreSQL harness."""

    source_before = production_source_proof()
    proof_source_guard = {
        str(path.relative_to(ROOT)): manual_lease_expiry_violations(
            path.read_text(encoding="utf-8")
        )
        for path in (Path(__file__).resolve(), WORKER)
    }
    assert all(not violations for violations in proof_source_guard.values())
    result = {
        "budgetSemantics": BUDGET_SEMANTICS,
        "providerCallCountRace": provider_call_count_race(
            runtime, database_url, timeout_seconds
        ),
        "providerNonHardTokenCostSemantics": provider_nonhard_token_cost_semantics(
            runtime, database_url, timeout_seconds
        ),
        "providerUnsentLinearization": provider_unsent_linearization(
            runtime, database_url, timeout_seconds
        ),
        "providerSentCancelReclaim": provider_sent_cancel_reclaim(
            runtime, database_url, timeout_seconds
        ),
        "toolCallCountRace": tool_call_count_race(runtime, database_url, timeout_seconds),
        "toolExpiryReclaim": tool_expiry_reclaim(runtime, database_url, timeout_seconds),
        "locks": lock_projection(runtime),
        "assertions": {
            "providerCallCountIsHardGate": True,
            "toolCallCountIsHardGate": True,
            "providerTokensArePerCallLimits": True,
            "cumulativeProviderTokensAreNotHardGate": True,
            "providerCostIsNotHardGate": True,
            "allRelevantRowsFullyProjectedBeforeAndAfter": True,
            "allConcurrentRacesUseDistinctOsProcessesAndLivePostgresBackends": True,
            "allLedgersRemainNonnegativeAndWithinCallCounts": True,
            "noDuplicateProviderOrToolUsage": True,
            "toolReconcileOrOutcomeUnknownApiNotClaimed": True,
            "databaseUrlAndPasswordScrubbed": True,
            "proofSourcesContainNoManualLeaseExpiryMutation": True,
        },
    }
    source_after = production_source_proof()
    assert source_after == source_before
    result["productionSourceProof"] = {
        "before": source_before,
        "after": source_after,
        "unchanged": True,
    }
    result["proofSourceGuard"] = proof_source_guard
    core_contention = (
        result["providerCallCountRace"]["reserveRace"]["operationContention"],
        result["providerCallCountRace"]["reconcileRace"]["operationContention"],
        result["toolCallCountRace"]["beginRace"]["operationContention"],
        result["toolCallCountRace"]["completeRace"]["operationContention"],
    )
    assert all(evidence is not None and evidence["passed"] for evidence in core_contention)
    result["assertions"]["allFourCoreRacesHaveWorkerOperationContention"] = True
    source_url = make_url(database_url)
    secrets = {database_url}
    if source_url.password:
        secrets.add(source_url.password)
    scrubbed = scrub_secrets(result, secrets)
    serialized = json.dumps(scrubbed, sort_keys=True)
    assert all(secret not in serialized for secret in secrets if secret)
    return scrubbed
