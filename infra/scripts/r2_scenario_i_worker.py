#!/usr/bin/env python3
"""Process-isolated production command driver for the R2-I proof scenario."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any

from ai_pdf_api.schemas.research import ConflictDecisionRequest
from ai_pdf_api.services.research.research_decisions import decide_conflict
from citeframe_research_persistence.completion import (
    VerificationResult,
    complete_research_critique,
    complete_research_synthesis,
    complete_research_verification,
)
from citeframe_research_persistence.errors import (
    ResearchError,
    canonical_sha256,
    persisted_error_payload,
)
from citeframe_research_persistence.lease import (
    claim_next_research_step,
    claim_specific_research_step,
)
from citeframe_research_persistence.publication import wait_for_conflict_decision
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

OPERATIONS = (
    "verify",
    "critique",
    "wait_gate",
    "claim_next_probe",
    "claim_specific_probe",
    "decide_conflict",
    "synthesize",
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
            raise TimeoutError("R2-I release barrier was not opened")
        time.sleep(0.02)


class ObjectStore:
    """Minimal filesystem-backed object port with path-free evidence records."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.records: dict[str, dict[str, object]] = {}

    def _path(self, object_key: str) -> Path:
        key = PurePosixPath(object_key)
        if key.is_absolute() or not key.parts or any(part in {"", ".", ".."} for part in key.parts):
            raise ValueError("invalid R2-I object key")
        destination = self.root.joinpath(*key.parts).resolve()
        if not destination.is_relative_to(self.root):
            raise ValueError("R2-I object key escaped its root")
        return destination

    def store(self, object_key: str, payload: bytes, _content_type: str) -> None:
        destination = self._path(object_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        self.records[object_key] = {
            "key": object_key,
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    def cleanup(self, object_key: str) -> None:
        destination = self._path(object_key)
        try:
            destination.unlink()
        except FileNotFoundError:
            pass
        self.records.pop(object_key, None)

    def manifest(self) -> list[dict[str, object]]:
        return [self.records[key] for key in sorted(self.records)]


def lease_record(lease: Any) -> dict[str, object]:
    return {
        "attemptId": str(lease.attempt_id),
        "attemptNumber": int(lease.attempt_number),
        "runId": str(lease.run_id),
        "stepId": str(lease.step_id),
        "stepKey": str(lease.step_key),
    }


def claim_specific(args: argparse.Namespace, db: Session) -> Any:
    if not args.run_id or not args.step_key:
        raise ValueError("operation requires --run-id and --step-key")
    return claim_specific_research_step(
        db,
        run_id=args.run_id,
        step_key=args.step_key,
        branch_key=None,
        worker_instance_id=args.worker_instance_id,
    )


def verify(args: argparse.Namespace, db: Session) -> dict[str, object]:
    if not args.claim_id:
        raise ValueError("verify requires --claim-id")
    lease = claim_specific(args, db)
    db.commit()
    complete_research_verification(
        db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        results=(VerificationResult(args.claim_id, "supported"),),
    )
    db.commit()
    return {"outcome": "completed", "lease": lease_record(lease)}


def critique(args: argparse.Namespace, db: Session) -> dict[str, object]:
    if not args.claim_id:
        raise ValueError("critique requires --claim-id")
    lease = claim_specific(args, db)
    db.commit()
    complete_research_critique(
        db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        conflict_claim_ids=(args.claim_id,),
    )
    db.commit()
    return {"outcome": "completed", "lease": lease_record(lease)}


def wait_gate(
    args: argparse.Namespace,
    db: Session,
    objects: ObjectStore,
) -> dict[str, object]:
    if not args.claim_id:
        raise ValueError("wait_gate requires --claim-id")
    lease = claim_specific(args, db)
    db.commit()
    decision_id = wait_for_conflict_decision(
        db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        conflict_claim_ids=(args.claim_id,),
        store_bytes=objects.store,
        cleanup_bytes=objects.cleanup,
    )
    db.commit()
    return {
        "outcome": "waiting",
        "decisionId": decision_id,
        "lease": lease_record(lease),
    }


def claim_next_probe(args: argparse.Namespace, db: Session) -> dict[str, object]:
    lease = claim_next_research_step(db, worker_instance_id=args.worker_instance_id)
    db.commit()
    if lease is None:
        return {"outcome": "none"}
    return {"outcome": "claimed", "lease": lease_record(lease)}


def claim_specific_probe(args: argparse.Namespace, db: Session) -> dict[str, object]:
    try:
        lease = claim_specific(args, db)
        db.commit()
        return {"outcome": "claimed", "lease": lease_record(lease)}
    except ResearchError as error:
        db.rollback()
        return {"outcome": "fenced", "errorCode": error.code}


def decide(args: argparse.Namespace, db: Session) -> dict[str, object]:
    required = (
        args.workspace_id,
        args.actor_user_id,
        args.run_id,
        args.decision_id,
        args.input_artifact_sha256,
        args.input_snapshot_sha256,
        args.idempotency_key,
    )
    if any(value is None for value in required):
        raise ValueError("decide_conflict requires the complete decision request")
    if args.expected_state_version is None or args.expected_decision_state_version is None:
        raise ValueError("decide_conflict requires expected state versions")
    payload = ConflictDecisionRequest(
        expected_state_version=args.expected_state_version,
        expected_decision_state_version=args.expected_decision_state_version,
        input_artifact_sha256=args.input_artifact_sha256,
        input_snapshot_sha256=args.input_snapshot_sha256,
        action="keep_as_unresolved",
        comment="R2-I persisted conflict resume proof.",
    )
    try:
        status, response, replayed = decide_conflict(
            db,
            workspace_id=args.workspace_id,
            actor_user_id=args.actor_user_id,
            run_id=args.run_id,
            decision_id=args.decision_id,
            payload=payload,
            idempotency_key=args.idempotency_key,
        )
        return {
            "outcome": "replayed" if replayed else "decided",
            "httpStatus": status,
            "decisionStatus": response["decision"]["status"],
            "idempotencyKey": args.idempotency_key,
            "responseJson": response,
            "responseSha256": canonical_sha256(response),
        }
    except ResearchError as error:
        db.rollback()
        response = persisted_error_payload(error)
        persisted_error = response["error"]
        return {
            "outcome": "fenced",
            "errorCode": error.code,
            "errorMessage": error.message,
            "errorRetryable": persisted_error["retryable"],
            "errorRequestId": persisted_error["requestId"],
            "errorDetails": persisted_error.get("details"),
            "httpStatus": error.status_code,
            "idempotencyKey": args.idempotency_key,
            "responseJson": response,
            "responseSha256": canonical_sha256(response),
        }


def synthesize(
    args: argparse.Namespace,
    db: Session,
    objects: ObjectStore,
) -> dict[str, object]:
    if not args.claim_id:
        raise ValueError("synthesize requires --claim-id")
    try:
        lease = claim_specific(args, db)
        db.commit()
    except ResearchError as error:
        db.rollback()
        return {"outcome": "conflict", "errorCode": error.code}
    try:
        complete_research_synthesis(
            db,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            fact_claim_ids=(),
            unresolved_claim_ids=(args.claim_id,),
            store_bytes=objects.store,
            cleanup_bytes=objects.cleanup,
        )
        db.commit()
        return {"outcome": "completed", "lease": lease_record(lease)}
    except ResearchError as error:
        db.rollback()
        return {"outcome": "conflict", "errorCode": error.code}


def run_operation(
    args: argparse.Namespace,
    db: Session,
    objects: ObjectStore,
) -> dict[str, object]:
    if args.operation == "verify":
        return verify(args, db)
    if args.operation == "critique":
        return critique(args, db)
    if args.operation == "wait_gate":
        return wait_gate(args, db, objects)
    if args.operation == "claim_next_probe":
        return claim_next_probe(args, db)
    if args.operation == "claim_specific_probe":
        return claim_specific_probe(args, db)
    if args.operation == "decide_conflict":
        return decide(args, db)
    if args.operation == "synthesize":
        return synthesize(args, db, objects)
    raise AssertionError(f"unsupported R2-I operation: {args.operation}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--operation", choices=OPERATIONS, required=True)
    parser.add_argument("--database-url-env", default="CITEFRAME_R2_DATABASE_URL")
    parser.add_argument("--object-root-env", default="CITEFRAME_R2_OBJECT_ROOT")
    parser.add_argument("--schema", required=True)
    parser.add_argument("--worker-instance-id", required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    parser.add_argument("--release-file", type=Path, required=True)
    parser.add_argument("--wait-timeout-seconds", type=float, default=25.0)
    parser.add_argument("--run-id")
    parser.add_argument("--step-key")
    parser.add_argument("--claim-id")
    parser.add_argument("--workspace-id")
    parser.add_argument("--actor-user-id")
    parser.add_argument("--decision-id")
    parser.add_argument("--expected-state-version", type=int)
    parser.add_argument("--expected-decision-state-version", type=int)
    parser.add_argument("--input-artifact-sha256")
    parser.add_argument("--input-snapshot-sha256")
    parser.add_argument("--idempotency-key")
    args = parser.parse_args()

    if not re.fullmatch(r"citeframe_r0_[0-9a-f]{12}", args.schema):
        parser.error("--schema is not a generated R0 harness schema")
    database_url = os.environ.get(args.database_url_env)
    object_root = os.environ.get(args.object_root_env)
    if not database_url:
        parser.error(f"database URL environment variable is missing: {args.database_url_env}")
    if not object_root:
        parser.error(f"object root environment variable is missing: {args.object_root_env}")

    record: dict[str, object] = {
        "scenario": "i_conflict_decision_resume",
        "operation": args.operation,
        "workerInstanceId": args.worker_instance_id,
        "osPid": os.getpid(),
        "pgBackendPid": None,
        "argv": sys.argv[1:],
        "exitStatus": 1,
        "objectManifest": [],
    }
    engine = None
    objects = ObjectStore(Path(object_root))
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
            record.update(run_operation(args, db, objects))
        record["objectManifest"] = objects.manifest()
        record["exitStatus"] = 0
        return 0
    except Exception as error:  # noqa: BLE001 - proof record captures child failure
        record["error"] = f"{type(error).__name__}: {error}"
        record["objectManifest"] = objects.manifest()
        return 1
    finally:
        if engine is not None:
            engine.dispose()
        print(json.dumps(record, sort_keys=True), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
