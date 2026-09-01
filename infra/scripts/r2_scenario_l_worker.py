#!/usr/bin/env python3
"""Process-isolated production command driver for the R2-L budget proof."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from citeframe_persistence.models import (
    ResearchExecutionSnapshot,
    ResearchStep,
    ResearchStepAttempt,
)
from citeframe_research_persistence.cancellation import cancel_research_run_transition
from citeframe_research_persistence.errors import ResearchError
from citeframe_research_persistence.lease import claim_specific_research_step
from citeframe_research_persistence.provider import (
    cancel_provider_reservation,
    mark_provider_call_sent,
    reconcile_provider_call,
    reserve_provider_call,
)
from citeframe_research_persistence.state import reclaim_expired_research_steps
from citeframe_research_persistence.tools import begin_tool_call, complete_tool_call
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

OPERATIONS = (
    "claim_specific",
    "reserve_provider",
    "mark_provider_sent",
    "cancel_provider_reservation",
    "reconcile_provider_succeeded",
    "begin_tool",
    "complete_tool",
    "cancel_run",
    "reclaim",
)


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def wait_for_release(path: Path, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not path.is_file():
        if time.monotonic() >= deadline:
            raise TimeoutError("R2-L release barrier was not opened")
        time.sleep(0.02)


def safe_error(error: Exception, database_url: str) -> str:
    message = f"{type(error).__name__}: {error}"
    secrets = {database_url}
    try:
        password = make_url(database_url).password
        if password:
            secrets.add(password)
    except (TypeError, ValueError):
        pass
    for secret in secrets:
        message = message.replace(secret, "[redacted]")
    return message


def attempt_snapshot_chain(
    db: Session, attempt_id: str
) -> tuple[ResearchStepAttempt, ResearchStep, ResearchExecutionSnapshot]:
    attempt = db.get(ResearchStepAttempt, attempt_id)
    step = db.get(ResearchStep, attempt.step_id) if attempt is not None else None
    snapshot = (
        db.get(ResearchExecutionSnapshot, step.execution_snapshot_id)
        if step is not None and step.execution_snapshot_id is not None
        else None
    )
    if attempt is None or step is None or snapshot is None:
        raise ValueError("operation requires a valid execution Attempt chain")
    return attempt, step, snapshot


def claim_specific(args: argparse.Namespace, db: Session) -> dict[str, object]:
    if not args.run_id or not args.step_key:
        raise ValueError("claim_specific requires run and step keys")
    try:
        lease = claim_specific_research_step(
            db,
            run_id=args.run_id,
            step_key=args.step_key,
            branch_key=args.branch_key,
            worker_instance_id=args.worker_instance_id,
            lease_seconds=args.lease_seconds,
        )
        db.commit()
        expires_at = lease.lease_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return {
            "outcome": "claimed",
            "runId": lease.run_id,
            "stepId": lease.step_id,
            "attemptId": lease.attempt_id,
            "attemptNumber": lease.attempt_number,
            "leaseExpiresAt": expires_at.astimezone(UTC).isoformat(),
            "leaseSeconds": args.lease_seconds,
        }
    except ResearchError as error:
        db.rollback()
        return {"outcome": "fenced", "errorCode": error.code}


def reserve_provider(args: argparse.Namespace, db: Session) -> dict[str, object]:
    if not args.attempt_id or not args.logical_call_key:
        raise ValueError("reserve_provider requires attempt and logical call keys")
    attempt, _step, snapshot = attempt_snapshot_chain(db, args.attempt_id)
    request_sha256 = args.request_sha256 or hashlib.sha256(
        args.logical_call_key.encode("utf-8")
    ).hexdigest()
    try:
        reservation = reserve_provider_call(
            db,
            attempt_id=attempt.id,
            logical_call_key=args.logical_call_key,
            request_sha256=request_sha256,
            provider=snapshot.generation_provider,
            model=snapshot.generation_model,
            provider_config_fingerprint=snapshot.provider_config_fingerprint,
            reserved_input_tokens=args.reserved_input_tokens,
            reserved_output_tokens=args.reserved_output_tokens,
            provider_config_matcher=lambda _db, _step, _fingerprint: True,
        )
        db.commit()
        return {
            "outcome": "reserved",
            "providerCallId": reservation.provider_call_id,
            "budgetLedgerId": reservation.budget_ledger_id,
        }
    except ResearchError as error:
        db.rollback()
        outcome = (
            "budget_exhausted"
            if error.code == "research_budget_limit"
            else "context_limit_exceeded"
            if error.code == "research_context_limit_exceeded"
            else "fenced"
        )
        return {"outcome": outcome, "errorCode": error.code}


def mark_provider_sent(args: argparse.Namespace, db: Session) -> dict[str, object]:
    if not args.provider_call_id:
        raise ValueError("mark_provider_sent requires provider call id")
    try:
        mark_provider_call_sent(db, args.provider_call_id)
        db.commit()
        return {"outcome": "sent"}
    except ResearchError as error:
        db.rollback()
        return {"outcome": "fenced", "errorCode": error.code}


def cancel_provider(args: argparse.Namespace, db: Session) -> dict[str, object]:
    if not args.provider_call_id:
        raise ValueError("cancel_provider_reservation requires provider call id")
    try:
        cancel_provider_reservation(db, args.provider_call_id)
        db.commit()
        return {"outcome": "cancelled"}
    except ResearchError as error:
        db.rollback()
        return {"outcome": "fenced", "errorCode": error.code}


def reconcile_provider(args: argparse.Namespace, db: Session) -> dict[str, object]:
    if not args.provider_call_id:
        raise ValueError("reconcile_provider_succeeded requires provider call id")
    try:
        reconcile_provider_call(
            db,
            provider_call_id=args.provider_call_id,
            status="succeeded",
            actual_input_tokens=args.actual_input_tokens,
            actual_output_tokens=args.actual_output_tokens,
            usage_source="actual",
            usage_final=True,
        )
        db.commit()
        return {"outcome": "reconciled", "providerStatus": "succeeded"}
    except ResearchError as error:
        db.rollback()
        return {"outcome": "fenced", "errorCode": error.code}


def begin_tool(args: argparse.Namespace, db: Session) -> dict[str, object]:
    if not args.attempt_id or not args.tool_call_key:
        raise ValueError("begin_tool requires attempt and tool call keys")
    request_sha256 = args.request_sha256 or hashlib.sha256(
        args.tool_call_key.encode("utf-8")
    ).hexdigest()
    try:
        reservation = begin_tool_call(
            db,
            attempt_id=args.attempt_id,
            tool_call_key=args.tool_call_key,
            tool_name=args.tool_name,
            request_sha256=request_sha256,
        )
        db.commit()
        return {
            "outcome": "running",
            "toolCallId": reservation.tool_call_id,
            "budgetLedgerId": reservation.budget_ledger_id,
        }
    except ResearchError as error:
        db.rollback()
        outcome = "budget_exhausted" if error.code == "research_budget_limit" else "fenced"
        return {"outcome": outcome, "errorCode": error.code}


def complete_tool(args: argparse.Namespace, db: Session) -> dict[str, object]:
    if not args.tool_call_id:
        raise ValueError("complete_tool requires tool call id")
    try:
        complete_tool_call(db, tool_call_id=args.tool_call_id, status="succeeded")
        db.commit()
        return {"outcome": "completed", "toolStatus": "succeeded"}
    except ResearchError as error:
        db.rollback()
        return {"outcome": "fenced", "errorCode": error.code}


def cancel_run(args: argparse.Namespace, db: Session) -> dict[str, object]:
    required = (args.run_id, args.workspace_id, args.actor_user_id)
    if any(value is None for value in required) or args.expected_state_version is None:
        raise ValueError("cancel_run requires run scope and expected state version")
    try:
        run = cancel_research_run_transition(
            db,
            workspace_id=args.workspace_id,
            actor_user_id=args.actor_user_id,
            actor_role="owner",
            run_id=args.run_id,
            expected_state_version=args.expected_state_version,
            reason_code="user_requested",
            now=datetime.now(UTC),
        )
        db.commit()
        return {"outcome": "cancelled", "runStatus": run.status}
    except ResearchError as error:
        db.rollback()
        return {"outcome": "fenced", "errorCode": error.code}


def reclaim(db: Session) -> dict[str, object]:
    reclaimed = reclaim_expired_research_steps(db, limit=1)
    db.commit()
    return {"outcome": "reclaimed", "reclaimedCount": reclaimed}


def run_operation(args: argparse.Namespace, db: Session) -> dict[str, object]:
    if args.operation == "claim_specific":
        return claim_specific(args, db)
    if args.operation == "reserve_provider":
        return reserve_provider(args, db)
    if args.operation == "mark_provider_sent":
        return mark_provider_sent(args, db)
    if args.operation == "cancel_provider_reservation":
        return cancel_provider(args, db)
    if args.operation == "reconcile_provider_succeeded":
        return reconcile_provider(args, db)
    if args.operation == "begin_tool":
        return begin_tool(args, db)
    if args.operation == "complete_tool":
        return complete_tool(args, db)
    if args.operation == "cancel_run":
        return cancel_run(args, db)
    if args.operation == "reclaim":
        return reclaim(db)
    raise AssertionError(f"unsupported R2-L operation: {args.operation}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--operation", choices=OPERATIONS, required=True)
    parser.add_argument("--database-url-env", default="CITEFRAME_R2_DATABASE_URL")
    parser.add_argument("--schema", required=True)
    parser.add_argument("--worker-instance-id", required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    parser.add_argument("--release-file", type=Path, required=True)
    parser.add_argument("--wait-timeout-seconds", type=float, default=25.0)
    parser.add_argument("--attempt-id")
    parser.add_argument("--run-id")
    parser.add_argument("--step-key")
    parser.add_argument("--branch-key")
    parser.add_argument("--lease-seconds", type=int, default=120)
    parser.add_argument("--logical-call-key")
    parser.add_argument("--provider-call-id")
    parser.add_argument("--request-sha256")
    parser.add_argument("--reserved-input-tokens", type=int, default=9)
    parser.add_argument("--reserved-output-tokens", type=int, default=8)
    parser.add_argument("--actual-input-tokens", type=int, default=4)
    parser.add_argument("--actual-output-tokens", type=int, default=3)
    parser.add_argument("--tool-call-key")
    parser.add_argument("--tool-call-id")
    parser.add_argument("--tool-name", default="evidence.search")
    parser.add_argument("--workspace-id")
    parser.add_argument("--actor-user-id")
    parser.add_argument("--expected-state-version", type=int)
    args = parser.parse_args()

    if not re.fullmatch(r"citeframe_r0_[0-9a-f]{12}", args.schema):
        parser.error("--schema is not a generated R0 harness schema")
    database_url = os.environ.get(args.database_url_env)
    if not database_url:
        parser.error(f"database URL environment variable is missing: {args.database_url_env}")

    record: dict[str, object] = {
        "scenario": "l_budget_exhaustion_reconcile",
        "operation": args.operation,
        "workerInstanceId": args.worker_instance_id,
        "osPid": os.getpid(),
        "pgBackendPid": None,
        "argv": sys.argv[1:],
        "databaseUrlPassedViaEnvironment": True,
        "exitStatus": 1,
    }
    engine = None
    try:
        engine = create_engine(
            database_url,
            future=True,
            connect_args={"options": f"-csearch_path={args.schema},public"},
        )
        sessions = sessionmaker(
            bind=engine,
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )
        with sessions() as db:
            record["pgBackendPid"] = int(db.scalar(text("SELECT pg_backend_pid()")))
            atomic_write_json(args.ready_file, record)
            wait_for_release(args.release_file, args.wait_timeout_seconds)
            record.update(run_operation(args, db))
        record["exitStatus"] = 0
        return 0
    except Exception as error:  # noqa: BLE001 - proof record captures child failure
        record["error"] = safe_error(error, database_url)
        return 1
    finally:
        if engine is not None:
            engine.dispose()
        print(json.dumps(record, sort_keys=True), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
