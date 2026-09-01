#!/usr/bin/env python3
"""Spawned, process-isolated PostgreSQL claim worker for R2 evidence."""

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
from typing import Any

from citeframe_persistence.models import (
    ResearchExecutionSnapshot,
    ResearchStep,
    ResearchStepAttempt,
)
from citeframe_research_persistence.cancellation import cancel_research_run_transition
from citeframe_research_persistence.errors import (
    ResearchAdmissionDeferred,
    ResearchError,
)
from citeframe_research_persistence.lease import (
    claim_next_research_step,
    claim_specific_research_step,
    complete_research_step,
)
from citeframe_research_persistence.provider import (
    mark_provider_call_sent,
    reconcile_provider_call,
    reserve_provider_call,
)
from citeframe_research_persistence.state import reclaim_expired_research_steps
from citeframe_research_persistence.tools import begin_tool_call, complete_tool_call
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

OPERATIONS = (
    "identity",
    "claim_next",
    "claim_specific",
    "claim_complete_specific",
    "processor_claim",
    "reclaim",
    "complete",
    "cancel",
    "reserve_provider",
    "mark_sent",
    "reconcile",
    "begin_tool",
    "complete_tool",
)


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    """Publish a synchronization record without exposing a partially written file."""
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
    while not path.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError(f"release file was not created before timeout: {path}")
        time.sleep(0.02)


def lease_record(lease: Any) -> dict[str, object]:
    result: dict[str, object] = {
        "attemptId": str(lease.attempt_id),
        "attemptNumber": int(lease.attempt_number),
        "stepId": str(lease.step_id),
    }
    for source_name, output_name in (("run_id", "runId"), ("step_key", "stepKey")):
        value = getattr(lease, source_name, None)
        if value is not None:
            result[output_name] = str(value)
    return result


def claim_next(db: Session, worker_instance_id: str, retry_none_seconds: float) -> dict[str, object]:
    deadline = time.monotonic() + retry_none_seconds
    while True:
        try:
            lease = claim_next_research_step(db, worker_instance_id=worker_instance_id)
            if lease is not None:
                db.commit()
                return {"outcome": "claimed", "lease": lease_record(lease)}
            db.commit()
            if time.monotonic() >= deadline:
                return {"outcome": "none"}
            time.sleep(0.02)
        except ResearchAdmissionDeferred as deferred:
            db.rollback()
            return {"outcome": "deferred", "deferredRunId": str(deferred.run_id)}


def claim_specific(args: argparse.Namespace, db: Session) -> dict[str, object]:
    if not args.run_id or not args.step_key:
        raise ValueError("claim_specific requires --run-id and --step-key")
    try:
        lease = claim_specific_research_step(
            db,
            run_id=args.run_id,
            step_key=args.step_key,
            branch_key=args.branch_key,
            worker_instance_id=args.worker_instance_id,
        )
        db.commit()
        return {"outcome": "claimed", "lease": lease_record(lease)}
    except ResearchError as error:
        db.rollback()
        return {"outcome": "conflict", "errorCode": error.code}


def claim_complete_specific(args: argparse.Namespace, db: Session) -> dict[str, object]:
    """Claim and complete one persisted Step in this child, exposing the claim race."""
    if not args.run_id or not args.step_key:
        raise ValueError("claim_complete_specific requires --run-id and --step-key")
    try:
        lease = claim_specific_research_step(
            db,
            run_id=args.run_id,
            step_key=args.step_key,
            branch_key=args.branch_key,
            worker_instance_id=args.worker_instance_id,
        )
        db.commit()
    except ResearchError as error:
        db.rollback()
        return {"outcome": "conflict", "errorCode": error.code}
    try:
        complete_research_step(
            db,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            output_sha256=args.output_sha256,
        )
        db.commit()
        return {"outcome": "completed", "lease": lease_record(lease)}
    except ResearchError as error:
        db.rollback()
        return {"outcome": "conflict", "errorCode": error.code}


def reclaim(db: Session) -> dict[str, object]:
    reclaimed = reclaim_expired_research_steps(db, limit=1)
    db.commit()
    return {"outcome": "reclaimed", "reclaimedCount": reclaimed}


def complete(args: argparse.Namespace, db: Session) -> dict[str, object]:
    if not args.attempt_id or not args.lease_token:
        raise ValueError("complete requires --attempt-id and an injected lease token")
    try:
        complete_research_step(
            db,
            attempt_id=args.attempt_id,
            lease_token=args.lease_token,
            output_sha256=args.output_sha256,
        )
        db.commit()
        return {"outcome": "completed"}
    except ResearchError as error:
        db.rollback()
        return {"outcome": "fenced", "errorCode": error.code}


def reserve_provider(args: argparse.Namespace, db: Session) -> dict[str, object]:
    if not args.attempt_id:
        raise ValueError("reserve_provider requires --attempt-id")
    attempt = db.get(ResearchStepAttempt, args.attempt_id)
    step = db.get(ResearchStep, attempt.step_id) if attempt is not None else None
    snapshot = (
        db.get(ResearchExecutionSnapshot, step.execution_snapshot_id)
        if step is not None and step.execution_snapshot_id is not None
        else None
    )
    if attempt is None or step is None or snapshot is None:
        raise ValueError("reserve_provider requires a valid execution Attempt chain")
    logical_call_key = args.logical_call_key or args.worker_instance_id
    request_sha256 = args.request_sha256 or hashlib.sha256(
        logical_call_key.encode("utf-8")
    ).hexdigest()
    try:
        reservation = reserve_provider_call(
            db,
            attempt_id=attempt.id,
            logical_call_key=logical_call_key,
            request_sha256=request_sha256,
            provider=snapshot.generation_provider,
            model=snapshot.generation_model,
            provider_config_fingerprint=snapshot.provider_config_fingerprint,
            reserved_input_tokens=10,
            reserved_output_tokens=10,
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
        return {"outcome": "fenced", "errorCode": error.code}


def mark_sent(args: argparse.Namespace, db: Session) -> dict[str, object]:
    if not args.provider_call_id:
        raise ValueError("mark_sent requires --provider-call-id")
    try:
        mark_provider_call_sent(db, args.provider_call_id)
        db.commit()
        return {"outcome": "sent"}
    except ResearchError as error:
        db.rollback()
        return {"outcome": "fenced", "errorCode": error.code}


def reconcile(args: argparse.Namespace, db: Session) -> dict[str, object]:
    if not args.provider_call_id:
        raise ValueError("reconcile requires --provider-call-id")
    try:
        reconcile_provider_call(
            db,
            provider_call_id=args.provider_call_id,
            status="outcome_unknown",
            actual_input_tokens=10,
            actual_output_tokens=10,
            usage_source="estimated",
            usage_final=False,
            error_code="provider_outcome_unknown",
        )
        db.commit()
        return {"outcome": "reconciled"}
    except ResearchError as error:
        db.rollback()
        return {"outcome": "fenced", "errorCode": error.code}


def begin_tool(args: argparse.Namespace, db: Session) -> dict[str, object]:
    if not args.attempt_id:
        raise ValueError("begin_tool requires --attempt-id")
    tool_call_key = args.tool_call_key or args.worker_instance_id
    request_sha256 = args.request_sha256 or hashlib.sha256(
        tool_call_key.encode("utf-8")
    ).hexdigest()
    try:
        reservation = begin_tool_call(
            db,
            attempt_id=args.attempt_id,
            tool_call_key=tool_call_key,
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
        return {"outcome": "fenced", "errorCode": error.code}


def complete_tool(args: argparse.Namespace, db: Session) -> dict[str, object]:
    if not args.tool_call_id:
        raise ValueError("complete_tool requires --tool-call-id")
    try:
        complete_tool_call(
            db,
            tool_call_id=args.tool_call_id,
            status=args.tool_status,
            error_code=("lease_expired" if args.tool_status == "abandoned" else None),
        )
        db.commit()
        return {"outcome": "completed", "toolStatus": args.tool_status}
    except ResearchError as error:
        db.rollback()
        return {"outcome": "fenced", "errorCode": error.code}

def cancel(args: argparse.Namespace, db: Session) -> dict[str, object]:
    if not args.run_id or not args.workspace_id or not args.actor_user_id or args.expected_state_version is None:
        raise ValueError("cancel requires run/workspace/actor ids and expected state version")
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
        return {"outcome": "cancelled", "runStatus": run.status, "runStateVersion": run.state_version}
    except ResearchError as error:
        db.rollback()
        return {"outcome": "conflict", "errorCode": error.code}

def processor_claim(Session: sessionmaker[Session], worker_instance_id: str) -> dict[str, object]:
    """Compose and call the production processor rather than simulating exclusions."""
    from ai_pdf_worker.research_persistence_service import build_worker_research_service
    from ai_pdf_worker.research_runtime_processor import ResearchWorkProcessor

    claimed = ResearchWorkProcessor(
        Session,
        build_worker_research_service(),
        worker_instance_id=worker_instance_id,
    ).claim()
    if claimed is None:
        return {"outcome": "none"}
    return {
        "outcome": "claimed",
        "lease": lease_record(claimed.lease),
        "claimedRunId": claimed.run_id,
    }


def run_operation(
    args: argparse.Namespace, Session: sessionmaker[Session], db: Session
) -> dict[str, object]:
    if args.operation == "identity":
        return {"outcome": "identity"}
    if args.operation == "claim_next":
        return claim_next(db, args.worker_instance_id, args.retry_none_seconds)
    if args.operation == "claim_specific":
        return claim_specific(args, db)
    if args.operation == "claim_complete_specific":
        return claim_complete_specific(args, db)
    if args.operation == "processor_claim":
        return processor_claim(Session, args.worker_instance_id)
    if args.operation == "reclaim":
        return reclaim(db)
    if args.operation == "complete":
        return complete(args, db)
    if args.operation == "cancel":
        return cancel(args, db)
    if args.operation == "reserve_provider":
        return reserve_provider(args, db)
    if args.operation == "mark_sent":
        return mark_sent(args, db)
    if args.operation == "reconcile":
        return reconcile(args, db)
    if args.operation == "begin_tool":
        return begin_tool(args, db)
    if args.operation == "complete_tool":
        return complete_tool(args, db)
    raise AssertionError(f"unsupported operation: {args.operation}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--operation", choices=OPERATIONS, required=True)
    parser.add_argument("--database-url-env", default="CITEFRAME_R2_DATABASE_URL")
    parser.add_argument("--schema")
    parser.add_argument("--worker-instance-id", required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    parser.add_argument("--release-file", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--step-key")
    parser.add_argument("--branch-key")
    parser.add_argument("--attempt-id")
    parser.add_argument("--lease-token-env")
    parser.add_argument("--output-sha256", default="r2-output")
    parser.add_argument("--workspace-id")
    parser.add_argument("--actor-user-id")
    parser.add_argument("--expected-state-version", type=int)
    parser.add_argument("--provider-call-id")
    parser.add_argument("--logical-call-key")
    parser.add_argument("--request-sha256")
    parser.add_argument("--tool-call-id")
    parser.add_argument("--tool-call-key")
    parser.add_argument("--tool-name", default="evidence.search")
    parser.add_argument(
        "--tool-status",
        choices=("succeeded", "failed", "cancelled", "abandoned"),
        default="abandoned",
    )
    parser.add_argument("--wait-timeout-seconds", type=float, default=20.0)
    parser.add_argument("--retry-none-seconds", type=float, default=0.0)
    args = parser.parse_args()
    database_url = os.environ.get(args.database_url_env)
    if not database_url:
        parser.error(f"database URL environment variable is missing: {args.database_url_env}")
    args.lease_token = (
        os.environ.get(args.lease_token_env) if args.lease_token_env is not None else None
    )
    if args.lease_token_env is not None and not args.lease_token:
        parser.error(f"lease token environment variable is missing: {args.lease_token_env}")
    if args.schema is not None and not re.fullmatch(r"citeframe_r0_[0-9a-f]{12}", args.schema):
        parser.error("--schema is not a generated R0 harness schema")

    record: dict[str, object] = {
        "scenario": args.scenario,
        "operation": args.operation,
        "workerInstanceId": args.worker_instance_id,
        "osPid": os.getpid(),
        "pgBackendPid": None,
        "argv": sys.argv[1:],
        "exitStatus": 1,
    }
    engine = None
    try:
        connect_args = {"options": f"-csearch_path={args.schema},public"} if args.schema else {}
        # Every spawned interpreter creates its own Engine and Session factory.
        engine = create_engine(database_url, future=True, connect_args=connect_args)
        Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with Session() as db:
            record["pgBackendPid"] = int(db.scalar(text("SELECT pg_backend_pid()")))
            atomic_write_json(args.ready_file, record)
            wait_for_release(args.release_file, args.wait_timeout_seconds)
            record.update(run_operation(args, Session, db))
        record["exitStatus"] = 0
        return 0
    except Exception as error:  # noqa: BLE001 - evidence must capture worker failure
        record["error"] = f"{type(error).__name__}: {error}"
        try:
            atomic_write_json(args.ready_file, record)
        except OSError:
            pass
        return 1
    finally:
        if engine is not None:
            engine.dispose()
        print(json.dumps(record, sort_keys=True), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
