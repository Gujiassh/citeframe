#!/usr/bin/env python3
"""Process-isolated claim holder for the R2-J crash-recovery proof.

The lease token is written only to an exclusive, controller-owned secret IPC file.  The
database URL, fixture identity, synchronization paths, and token path are supplied through
the environment, so neither the token nor other connection secrets can appear in argv or
stdout.  ``hold_claim`` is intentionally terminated by the controller after the committed
lease is observed; ``claim_export`` exits only after a public release barrier.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from citeframe_research_persistence.errors import ResearchError
from citeframe_research_persistence.lease import (
    claim_specific_research_step,
    complete_research_step,
)
from citeframe_research_persistence.state import reclaim_expired_research_steps
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker


def required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"required environment value is missing: {name}")
    return value


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _current_windows_user_sid() -> str:
    completed = subprocess.run(
        ["whoami.exe", "/user", "/fo", "csv", "/nh"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    match = re.search(r"S-1-[0-9-]+", completed.stdout)
    if match is None:
        raise RuntimeError("current Windows user SID could not be resolved")
    return match.group(0)


def _split_sddl_aces(blob: str) -> tuple[list[str], bool]:
    """Split every top-level ACE and reject stray or unbalanced SDDL text."""
    groups: list[str] = []
    depth = 0
    start = -1
    valid = True
    for index, character in enumerate(blob):
        if character == "(":
            if depth == 0:
                start = index
            depth += 1
        elif character == ")":
            if depth == 0:
                valid = False
                continue
            depth -= 1
            if depth == 0:
                groups.append(blob[start : index + 1])
        elif depth == 0 and not character.isspace():
            valid = False
    return groups, valid and depth == 0 and bool(groups)


def _validate_windows_dacl(
    dacl: str,
    current_sid: str,
    *,
    expected_ace_flags: str,
    require_protected: bool,
) -> dict[str, object]:
    first_ace = dacl.find("(")
    header = dacl[:first_ace] if first_ace >= 0 else dacl
    ace_blob = dacl[first_ace:] if first_ace >= 0 else ""
    ace_groups, all_aces_split = _split_sddl_aces(ace_blob)
    expected_header = "D:PAI" if require_protected else "D:AI"
    expected_trustees = {current_sid, "SY", "BA"}
    parsed_aces: list[tuple[str, str, str, str, str, str]] = []
    every_ace_shape_parsed = all_aces_split
    for group in ace_groups:
        fields = group[1:-1].split(";")
        if len(fields) != 6:
            every_ace_shape_parsed = False
            continue
        parsed_aces.append(tuple(fields))  # type: ignore[arg-type]
    actual_trustees = {ace[5] for ace in parsed_aces}
    every_ace_exact = all(
        ace_type == "A"
        and ace_flags == expected_ace_flags
        and rights == "FA"
        and object_guid == ""
        and inherited_object_guid == ""
        and trustee in expected_trustees
        for (
            ace_type,
            ace_flags,
            rights,
            object_guid,
            inherited_object_guid,
            trustee,
        ) in parsed_aces
    )
    valid = (
        header == expected_header
        and every_ace_shape_parsed
        and len(ace_groups) == 3
        and len(parsed_aces) == len(ace_groups)
        and actual_trustees == expected_trustees
        and every_ace_exact
    )
    trustee_kinds = {
        "current_user"
        if trustee == current_sid
        else "local_system"
        if trustee == "SY"
        else "local_administrators"
        if trustee == "BA"
        else "unexpected"
        for trustee in actual_trustees
    }
    return {
        "valid": valid,
        "daclProtected": require_protected and header == expected_header,
        "allAcesParsed": (
            every_ace_shape_parsed and len(parsed_aces) == len(ace_groups)
        ),
        "allRulesExplicit": expected_ace_flags == "OICI" and every_ace_exact,
        "allRulesInherited": expected_ace_flags == "ID" and every_ace_exact,
        "allRulesAllowFullControl": every_ace_exact,
        "aceFlagsExact": every_ace_exact,
        "allowedTrusteeKinds": sorted(trustee_kinds),
        "unexpectedTrusteeCount": sum(
            trustee not in expected_trustees for trustee in actual_trustees
        ),
        "actualRuleCount": len(ace_groups),
    }


def _windows_acl_evidence(
    path: Path,
    current_sid: str,
    *,
    expected_ace_flags: str,
    require_protected: bool,
) -> dict[str, object]:
    acl_export = path.with_name(f".{path.name}.{os.urandom(6).hex()}.acl")
    try:
        completed = subprocess.run(
            ["icacls.exe", str(path), "/save", str(acl_export), "/q"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if completed.returncode != 0 or not acl_export.is_file():
            raise RuntimeError("icacls could not export lease-token secret IPC DACL")
        exported = acl_export.read_text(encoding="utf-16-le")
    finally:
        acl_export.unlink(missing_ok=True)
    dacl = next((line for line in exported.splitlines() if line.startswith("D:")), "")
    evidence = _validate_windows_dacl(
        dacl,
        current_sid,
        expected_ace_flags=expected_ace_flags,
        require_protected=require_protected,
    )
    if not evidence["valid"]:
        raise RuntimeError(
            "lease-token secret IPC DACL verification failed "
            f"(ruleCount={evidence['actualRuleCount']}, "
            f"allAcesParsed={evidence['allAcesParsed']}, "
            f"unexpectedTrusteeCount={evidence['unexpectedTrusteeCount']})"
        )
    evidence.pop("valid")
    return {
        "platformMode": (
            "windows_protected_dacl"
            if require_protected
            else "windows_inherited_from_protected_parent"
        ),
        **evidence,
        "verifiedBeforeSecretWrite": True,
    }


def _restrict_windows_secret_directory(path: Path) -> dict[str, object]:
    current_sid = _current_windows_user_sid()
    completed = subprocess.run(
        [
            "icacls.exe",
            str(path),
            "/inheritance:r",
            "/grant:r",
            f"*{current_sid}:(OI)(CI)(F)",
            "*S-1-5-18:(OI)(CI)(F)",
            "*S-1-5-32-544:(OI)(CI)(F)",
            "/remove:g",
            "*S-1-3-4",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if completed.returncode != 0:
        raise RuntimeError("icacls failed to restrict lease-token secret IPC directory")
    return _windows_acl_evidence(
        path,
        current_sid,
        expected_ace_flags="OICI",
        require_protected=True,
    )


def cleanup_secret_boundary(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    try:
        path.parent.rmdir()
    except OSError:
        pass


def write_secret_once(path: Path, value: str) -> dict[str, object]:
    """Create the token inside a pre-protected private directory, then write once."""
    secret_directory = path.parent
    secret_directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    descriptor: int | None = None
    try:
        if os.name == "nt":
            directory_acl = _restrict_windows_secret_directory(secret_directory)
        else:
            mode = stat.S_IMODE(secret_directory.stat().st_mode)
            if mode & 0o077:
                raise RuntimeError(
                    "lease-token secret IPC directory is accessible by group/other"
                )
            directory_acl = {
                "platformMode": "posix_owner_only",
                "daclProtected": None,
                "ownerReadWriteOnly": True,
            }
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        if os.name == "nt":
            current_sid = _current_windows_user_sid()
            file_acl = _windows_acl_evidence(
                path,
                current_sid,
                expected_ace_flags="ID",
                require_protected=False,
            )
            if file_acl["unexpectedTrusteeCount"] != 0:
                raise RuntimeError("lease-token secret IPC inherited an unexpected trustee")
            acl_evidence = {
                **directory_acl,
                "fileInheritedFromProtectedDirectory": True,
                "fileAclTrusteesExactAtBirth": True,
                "fileAclEvidence": file_acl,
                "noFileCreateThenRestrictWindow": True,
                "verifiedBeforeSecretWrite": True,
            }
        else:
            mode = stat.S_IMODE(path.stat().st_mode)
            if mode & 0o077:
                raise RuntimeError("lease-token secret IPC is accessible by group/other")
            acl_evidence = {
                **directory_acl,
                "fileInheritedFromProtectedDirectory": None,
                "fileAclTrusteesExactAtBirth": None,
                "noFileCreateThenRestrictWindow": True,
                "verifiedBeforeSecretWrite": True,
            }
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(value)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return acl_evidence
    except BaseException:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        cleanup_secret_boundary(path)
        raise


def advisory_lock_key(worker_instance_id: str) -> int:
    raw = int.from_bytes(
        hashlib.sha256(worker_instance_id.encode("utf-8")).digest()[:8],
        byteorder="big",
        signed=False,
    )
    return raw - (1 << 64) if raw >= (1 << 63) else raw


def wait_for_release(path: Path) -> None:
    while not path.exists():
        time.sleep(0.02)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--operation",
        choices=("hold_claim", "claim_export", "reclaim", "complete"),
        required=True,
    )
    args = parser.parse_args()

    ready_path = Path(required_environment("CITEFRAME_R2_J_READY_FILE"))
    secret_path = Path(required_environment("CITEFRAME_R2_J_LEASE_SECRET_FILE"))
    release_path = Path(required_environment("CITEFRAME_R2_J_RELEASE_FILE"))
    cleanup_path = Path(required_environment("CITEFRAME_R2_J_CLEANUP_FILE"))
    result_path = Path(required_environment("CITEFRAME_R2_J_RESULT_FILE"))
    database_url = required_environment("CITEFRAME_R2_DATABASE_URL")
    schema = required_environment("CITEFRAME_R2_J_SCHEMA")
    run_id = required_environment("CITEFRAME_R2_J_RUN_ID")
    step_key = required_environment("CITEFRAME_R2_J_STEP_KEY")
    branch_key = required_environment("CITEFRAME_R2_J_BRANCH_KEY")
    worker_instance_id = required_environment("CITEFRAME_R2_J_WORKER_INSTANCE_ID")
    lease_seconds = int(os.environ.get("CITEFRAME_R2_J_LEASE_SECONDS", "120"))
    if not re.fullmatch(r"citeframe_r0_[0-9a-f]{12}", schema):
        raise RuntimeError("R2-J received an invalid generated schema")
    if not 1 <= lease_seconds <= 300:
        raise RuntimeError("R2-J lease duration is outside the bounded proof range")

    record: dict[str, object] = {
        "scenario": "j_crash_recovery",
        "operation": args.operation,
        "workerInstanceId": worker_instance_id,
        "osPid": os.getpid(),
        "pgBackendPid": None,
        "argv": sys.argv[1:],
        "phase": "starting",
        "exitStatus": None,
        "sqlState": None,
    }
    engine = None
    normal_cleanup = False
    try:
        engine = create_engine(
            database_url,
            future=True,
            connect_args={"options": f"-csearch_path={schema},public"},
        )
        Session = sessionmaker(
            bind=engine,
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )
        with Session() as db:
            db.execute(
                text("SELECT set_config('application_name', :name, false)"),
                {"name": f"citeframe-r2-j:{worker_instance_id}"},
            )
            record["pgBackendPid"] = int(db.scalar(text("SELECT pg_backend_pid()")))
            record["applicationName"] = str(
                db.scalar(text("SELECT current_setting('application_name')"))
            )
            record["lockTimeoutSetting"] = str(
                db.scalar(text("SHOW lock_timeout"))
            )
            record["statementTimeoutSetting"] = str(
                db.scalar(text("SHOW statement_timeout"))
            )

            if args.operation in {"hold_claim", "claim_export"}:
                lease = claim_specific_research_step(
                    db,
                    run_id=run_id,
                    step_key=step_key,
                    branch_key=branch_key,
                    worker_instance_id=worker_instance_id,
                    lease_seconds=lease_seconds,
                )
                db.commit()
                # The session-level advisory lock is observation-only. It is acquired only
                # after the production lease commit and remains live until crash/exit.
                db.execute(
                    text("SELECT pg_advisory_lock(:key)"),
                    {"key": advisory_lock_key(worker_instance_id)},
                )
                acl_evidence = write_secret_once(secret_path, lease.lease_token)
                record.update(
                    {
                        "attemptId": str(lease.attempt_id),
                        "attemptNumber": int(lease.attempt_number),
                        "stepId": str(lease.step_id),
                        "leaseExpiresAt": (
                            lease.lease_expires_at.isoformat()
                            if isinstance(lease.lease_expires_at, datetime)
                            else str(lease.lease_expires_at)
                        ),
                        "phase": "lease_committed_and_holding",
                        "observationLockKind": "session_advisory",
                        "secretIpcAcl": acl_evidence,
                    }
                )
                atomic_write_json(ready_path, record)
                if args.operation == "hold_claim":
                    while True:
                        time.sleep(1.0)
                wait_for_release(release_path)
                record["phase"] = "released_after_committed_claim"
            else:
                db.execute(
                    text("SELECT pg_advisory_lock(:key)"),
                    {"key": advisory_lock_key(worker_instance_id)},
                )
                record.update(
                    {
                        "phase": "ready_for_production_operation",
                        "observationLockKind": "session_advisory",
                    }
                )
                atomic_write_json(ready_path, record)
                wait_for_release(release_path)
                try:
                    if args.operation == "reclaim":
                        reclaimed = reclaim_expired_research_steps(db, limit=1)
                        db.commit()
                        record.update(
                            {"outcome": "reclaimed", "reclaimedCount": reclaimed}
                        )
                    else:
                        attempt_id = required_environment("CITEFRAME_R2_J_ATTEMPT_ID")
                        lease_token = required_environment("CITEFRAME_R2_J_LEASE_TOKEN")
                        output_sha256 = required_environment(
                            "CITEFRAME_R2_J_OUTPUT_SHA256"
                        )
                        complete_research_step(
                            db,
                            attempt_id=attempt_id,
                            lease_token=lease_token,
                            output_sha256=output_sha256,
                        )
                        db.commit()
                        record["outcome"] = "completed"
                except ResearchError as error:
                    db.rollback()
                    record.update(
                        {"outcome": "fenced", "errorCode": error.code}
                    )
                record["phase"] = "production_operation_finished"
        record["exitStatus"] = 0
        atomic_write_json(result_path, record)
        normal_cleanup = True
        return 0
    except DBAPIError as error:
        record["phase"] = "database_error"
        record["errorType"] = type(error).__name__
        record["sqlState"] = getattr(
            error.orig,
            "sqlstate",
            getattr(error.orig, "pgcode", None),
        )
        record["exitStatus"] = 1
        try:
            atomic_write_json(result_path, record)
        except OSError:
            pass
        cleanup_secret_boundary(secret_path)
        normal_cleanup = True
        return 1
    except Exception as error:  # noqa: BLE001 - public IPC records only the error type
        record["phase"] = "failed"
        record["errorType"] = type(error).__name__
        record["exitStatus"] = 1
        try:
            atomic_write_json(ready_path, record)
        except OSError:
            pass
        cleanup_secret_boundary(secret_path)
        try:
            atomic_write_json(result_path, record)
        except OSError:
            pass
        normal_cleanup = True
        return 1
    finally:
        if engine is not None:
            engine.dispose()
        if normal_cleanup:
            cleanup_path.write_text("normal-cleanup\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
