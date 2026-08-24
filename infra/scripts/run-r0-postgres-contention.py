#!/usr/bin/env python3
"""Real-PostgreSQL contention evidence for the R0 Research lock order."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import threading
import time
import traceback
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from citeframe_persistence.base import Base
from citeframe_persistence.models import (
    ResearchBudgetLedger,
    ResearchEvent,
    ResearchExecutionSnapshot,
    ResearchProviderCall,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
    ResearchToolCall,
    User,
    Workspace,
    WorkspaceMembership,
)
from citeframe_research_persistence.commands import (
    begin_tool_call,
    cancel_provider_reservation,
    cancel_research_run_transition,
    claim_next_research_step,
    claim_specific_research_step,
    complete_research_step,
    complete_tool_call,
    heartbeat_research_step,
    reclaim_expired_research_steps,
    reserve_provider_call,
)
from citeframe_research_persistence.errors import ResearchError


LOCK_TIMEOUT_MS = 8_000
WAIT_TIMEOUT_SECONDS = 5.0
TASK_TIMEOUT_SECONDS = 12.0
APP_PREFIX = "citeframe-r0:"


def utcnow() -> datetime:
    return datetime.now(UTC)


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def uid(value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"citeframe-r0/{value}"))


def json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if is_dataclass(value):
        payload = asdict(value)
        if "lease_token" in payload:
            payload["lease_token"] = "<redacted>"
        return {key: json_value(item) for key, item in payload.items()}
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_value(item) for item in value]
    return repr(value)


def sqlstate(error: BaseException | None) -> str | None:
    current = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        value = getattr(current, "sqlstate", None) or getattr(current, "pgcode", None)
        if value:
            return str(value)
        current = getattr(current, "orig", None) or getattr(current, "__cause__", None)
    return None


def error_value(error: BaseException | None) -> dict[str, Any] | None:
    if error is None:
        return None
    payload: dict[str, Any] = {
        "type": type(error).__name__,
        "message": str(error),
        "sqlstate": sqlstate(error),
    }
    code = getattr(error, "code", None)
    if code is not None:
        payload["code"] = code
    return payload


@dataclass
class CommandTask:
    name: str
    target: Callable[[Session], Any]
    pid: int | None = None
    result: Any = None
    error: BaseException | None = None
    started: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None

    def report(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "pid": self.pid,
            "done": self.done.is_set(),
            "result": json_value(self.result),
            "error": error_value(self.error),
        }


@dataclass(frozen=True)
class RunFixture:
    run_id: str
    snapshot_id: str
    ledger_id: str
    step_ids: tuple[str, ...]
    step_keys: tuple[str, ...]
    branch_keys: tuple[str | None, ...]


class RowGate:
    TABLES = {
        "research_runs",
        "research_steps",
        "research_provider_calls",
        "research_tool_calls",
    }

    def __init__(self, harness: "ContentionHarness", name: str, table: str, row_id: str) -> None:
        if table not in self.TABLES:
            raise ValueError(f"unsupported gate table: {table}")
        self.harness = harness
        self.name = name
        self.db = harness.sessions()
        harness.configure_session(self.db, name, lock_timeout=False)
        self.pid = int(self.db.scalar(select(func.pg_backend_pid())))
        row = self.db.execute(
            text(f"SELECT id FROM {table} WHERE id = :row_id FOR UPDATE"),
            {"row_id": row_id},
        ).scalar_one_or_none()
        if row is None:
            self.db.rollback()
            self.db.close()
            raise AssertionError(f"gate row missing: {table}/{row_id}")
        self.released = False

    def release(self) -> None:
        if not self.released:
            self.db.commit()
            self.db.close()
            self.released = True


class AttemptInsertGate:
    """Pause a claim only after it has locked its Run and Step."""

    def __init__(self, harness: "ContentionHarness", name: str, worker_instance_id: str) -> None:
        self.harness = harness
        self.name = name
        self.db = harness.sessions()
        harness.configure_session(self.db, name, lock_timeout=False)
        self.pid = int(self.db.scalar(select(func.pg_backend_pid())))
        self.key = int(
            self.db.execute(
                text("SELECT hashtextextended(:worker, 0)"),
                {"worker": worker_instance_id},
            ).scalar_one()
        )
        self.db.execute(text("SELECT pg_advisory_lock(:key)"), {"key": self.key})
        self.released = False

    def release(self) -> None:
        if not self.released:
            self.db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": self.key})
            self.db.commit()
            self.db.close()
            self.released = True


class ContentionHarness:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.schema = f"citeframe_r0_{uuid4().hex[:12]}"
        self.admin_engine = create_engine(database_url, future=True, pool_pre_ping=True)
        self.engine: Engine | None = None
        self.sessions: sessionmaker[Session]
        self.monitor_engine: Engine | None = None
        self.user_id = uid(f"{self.schema}/user")
        self.workspace_id = uid(f"{self.schema}/workspace")
        self.tasks: list[CommandTask] = []
        self.report: dict[str, Any] = {
            "schemaVersion": "citeframe-r0-postgres-contention-v1",
            "startedAt": utcnow().isoformat(),
            "schema": self.schema,
            "lockTimeoutMs": LOCK_TIMEOUT_MS,
            "scenarios": [],
        }
        self.deadlocks_before = 0
        self.created_extensions: list[str] = []

    def setup(self) -> None:
        if not re.fullmatch(r"citeframe_r0_[0-9a-f]{12}", self.schema):
            raise AssertionError("unsafe generated schema name")
        with self.admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            existing_extensions = set(
                connection.execute(
                    text("SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pg_trgm')")
                ).scalars()
            )
            for extension in ("vector", "pg_trgm"):
                connection.execute(text(f"CREATE EXTENSION IF NOT EXISTS {extension}"))
                if extension not in existing_extensions:
                    self.created_extensions.append(extension)
            connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        self.report["createdExtensions"] = list(self.created_extensions)
        options = f"-csearch_path={self.schema},public"
        self.engine = create_engine(
            self.database_url,
            future=True,
            pool_pre_ping=True,
            connect_args={"options": options},
        )
        self.monitor_engine = create_engine(
            self.database_url,
            future=True,
            pool_pre_ping=True,
            isolation_level="AUTOCOMMIT",
            connect_args={"options": options},
        )
        self.sessions = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE FUNCTION citeframe_r0_attempt_insert_gate() RETURNS trigger
                    LANGUAGE plpgsql AS $$
                    BEGIN
                        PERFORM pg_advisory_xact_lock(hashtextextended(NEW.worker_instance_id, 0));
                        RETURN NEW;
                    END
                    $$
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TRIGGER citeframe_r0_attempt_insert_gate
                    BEFORE INSERT ON research_step_attempts
                    FOR EACH ROW EXECUTE FUNCTION citeframe_r0_attempt_insert_gate()
                    """
                )
            )
        self.report["claimGate"] = {
            "kind": "transaction advisory lock in a BEFORE INSERT trigger",
            "position": "after production claim owns ResearchRun and ResearchStep",
        }
        self._seed_identity()
        self.deadlocks_before = self.deadlock_count()
        with self.monitor_engine.connect() as connection:
            version = connection.execute(text("SELECT version()")).scalar_one()
            vector_version = connection.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ).scalar_one()
        self.report["postgresVersion"] = version
        self.report["pgvectorVersion"] = vector_version
        production_modules = {
            command.__module__
            for command in (
                begin_tool_call,
                cancel_provider_reservation,
                cancel_research_run_transition,
                claim_next_research_step,
                claim_specific_research_step,
                complete_research_step,
                complete_tool_call,
                heartbeat_research_step,
                reclaim_expired_research_steps,
                reserve_provider_call,
            )
        }
        self.report["productionSourceSha256"] = {}
        for module_name in sorted(production_modules | {"citeframe_research_persistence.locks"}):
            module_path = Path(importlib.import_module(module_name).__file__).resolve()
            self.report["productionSourceSha256"][module_name] = hashlib.sha256(
                module_path.read_bytes()
            ).hexdigest()

    def cleanup(self) -> None:
        if self.engine is not None:
            self.engine.dispose()
        if self.monitor_engine is not None:
            self.monitor_engine.dispose()
        with self.admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))
            for extension in reversed(self.created_extensions):
                connection.execute(text(f"DROP EXTENSION IF EXISTS {extension}"))
        self.admin_engine.dispose()

    def configure_session(self, db: Session, name: str, *, lock_timeout: bool = True) -> None:
        if not re.fullmatch(r"[a-z0-9:-]+", name) or len(name) > 63:
            raise ValueError(f"unsafe application name: {name}")
        db.execute(text(f"SET LOCAL application_name = '{name}'"))
        if lock_timeout:
            db.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT_MS}ms'"))
            db.execute(text(f"SET LOCAL statement_timeout = '{LOCK_TIMEOUT_MS + 4000}ms'"))

    def _seed_identity(self) -> None:
        now = utcnow()
        with self.sessions() as db:
            db.add(
                User(
                    id=self.user_id,
                    email=f"r0-{self.schema}@example.invalid",
                    name="R0 PostgreSQL Harness",
                    password_hash="not-a-login",
                    avatar_url="",
                    created_at=now,
                    updated_at=now,
                )
            )
            db.flush()
            db.add(
                Workspace(
                    id=self.workspace_id,
                    name="R0 PostgreSQL Harness",
                    created_by_user_id=self.user_id,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.flush()
            db.add(
                WorkspaceMembership(
                    workspace_id=self.workspace_id,
                    user_id=self.user_id,
                    role="owner",
                    created_at=now,
                )
            )
            db.commit()

    def seed_run(
        self,
        name: str,
        *,
        step_count: int = 1,
        queued_at: datetime | None = None,
    ) -> RunFixture:
        now = queued_at or utcnow()
        run_id = uid(f"{self.schema}/{name}/run")
        snapshot_id = uid(f"{self.schema}/{name}/snapshot")
        ledger_id = uid(f"{self.schema}/{name}/ledger")
        run = ResearchRun(
            id=run_id,
            workspace_id=self.workspace_id,
            created_by_user_id=self.user_id,
            status="queued",
            state_version=1,
            next_event_seq=1,
            cost_currency="USD",
            created_at=now,
            updated_at=now,
        )
        with self.sessions() as db:
            db.add(run)
            db.commit()
        snapshot = ResearchExecutionSnapshot(
            id=snapshot_id,
            workspace_id=self.workspace_id,
            run_id=run_id,
            approved_plan_revision_id=uid(f"{self.schema}/{name}/revision"),
            approval_decision_id=uid(f"{self.schema}/{name}/decision"),
            approved_plan_artifact_id=uid(f"{self.schema}/{name}/artifact"),
            approved_plan_artifact_sha256=sha(f"{name}/plan"),
            input_version=1,
            question_text=f"R0 contention scenario {name}",
            scope_mode="selected",
            workflow_version_id=uid(f"{self.schema}/{name}/workflow"),
            generation_provider="openai",
            generation_model="gpt-5.5",
            provider_config_fingerprint=sha(f"{name}/provider"),
            pricing_version="research-pricing-v1",
            data_boundary_policy_version="r0-boundary-v1",
            embedding_provider="test",
            embedding_model="test",
            embedding_version="test-v1",
            retrieval_strategy="hybrid",
            retrieval_top_k=6,
            max_parallel_researchers=2,
            max_step_attempts=3,
            max_provider_calls=8,
            max_tool_calls=8,
            max_input_tokens=10_000,
            max_output_tokens=10_000,
            max_cost_microunits=100_000,
            cost_currency="USD",
            budget_policy_version="r0-budget-v1",
            retry_policy_version="r0-retry-v1",
            max_run_timeout_seconds=3_600,
            max_step_timeout_seconds=600,
            max_provider_timeout_seconds=120,
            agent_result_schema_version="research-agent-results-v1",
            context_policy_version="research-context-policy-v1",
            compact_policy_version="research-compact-policy-v1",
            execution_snapshot_sha256=sha(f"{name}/execution"),
            created_at=now,
        )
        ledger = ResearchBudgetLedger(
            id=ledger_id,
            workspace_id=self.workspace_id,
            run_id=run_id,
            execution_snapshot_id=snapshot_id,
            currency="USD",
            state_version=1,
            usage_final=True,
            updated_at=now,
        )
        steps: list[ResearchStep] = []
        for index in range(step_count):
            step_key = f"researcher:{name}:{index + 1}"
            steps.append(
                ResearchStep(
                    id=uid(f"{self.schema}/{name}/step/{index + 1}"),
                    workspace_id=self.workspace_id,
                    run_id=run_id,
                    execution_snapshot_id=snapshot_id,
                    step_key=step_key,
                    step_kind="researcher",
                    branch_key=f"{name}-branch-{index + 1}",
                    status="queued",
                    state_version=1,
                    max_attempts_snapshot=3,
                    current_attempt_number=0,
                    input_sha256=sha(f"{name}/input/{index + 1}"),
                    queued_at=now + timedelta(microseconds=index),
                    created_at=now + timedelta(microseconds=index),
                    updated_at=now,
                )
            )
        with self.sessions() as db:
            # The existing SQLite fixture intentionally uses opaque FK ids for frozen
            # version/artifact records. Replica role makes the same minimal graph usable
            # here while all Research rows exercised by production commands remain real.
            db.execute(text("SET LOCAL session_replication_role = replica"))
            db.add_all([snapshot, ledger, *steps])
            db.flush()
            db.execute(
                text("UPDATE research_runs SET approved_execution_snapshot_id = :snapshot WHERE id = :run"),
                {"snapshot": snapshot_id, "run": run_id},
            )
            db.commit()
        return RunFixture(
            run_id=run_id,
            snapshot_id=snapshot_id,
            ledger_id=ledger_id,
            step_ids=tuple(step.id for step in steps),
            step_keys=tuple(step.step_key for step in steps),
            branch_keys=tuple(step.branch_key for step in steps),
        )

    def start_task(self, suffix: str, target: Callable[[Session], Any]) -> CommandTask:
        name = f"{APP_PREFIX}{suffix}"
        task = CommandTask(name=name, target=target)

        def run() -> None:
            with self.sessions() as db:
                try:
                    self.configure_session(db, name)
                    task.pid = int(db.scalar(select(func.pg_backend_pid())))
                    task.started.set()
                    task.result = target(db)
                    db.commit()
                except BaseException as error:  # noqa: BLE001 - evidence records exact command failure
                    task.error = error
                    db.rollback()
                finally:
                    task.done.set()

        task.thread = threading.Thread(target=run, name=name, daemon=True)
        self.tasks.append(task)
        task.thread.start()
        if not task.started.wait(WAIT_TIMEOUT_SECONDS):
            raise AssertionError(f"task did not start: {name}")
        return task

    def join(self, task: CommandTask, timeout: float = TASK_TIMEOUT_SECONDS) -> None:
        if task.thread is None:
            raise AssertionError(f"task has no thread: {task.name}")
        task.thread.join(timeout)
        if task.thread.is_alive():
            raise AssertionError(f"task did not finish: {task.name}")

    def activity(self, pid: int) -> dict[str, Any] | None:
        if self.monitor_engine is None:
            raise RuntimeError("monitor engine is not initialized")
        with self.monitor_engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT pid, application_name, state, wait_event_type, wait_event,
                           pg_blocking_pids(pid) AS blocking_pids
                    FROM pg_stat_activity
                    WHERE pid = :pid
                    """
                ),
                {"pid": pid},
            ).mappings().one_or_none()
        return dict(row) if row else None

    def wait_blocked_by(self, task: CommandTask, blocker_pid: int) -> dict[str, Any]:
        if task.pid is None:
            raise AssertionError(f"task has no pid: {task.name}")
        deadline = time.monotonic() + WAIT_TIMEOUT_SECONDS
        last: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            last = self.activity(task.pid)
            if (
                last is not None
                and last["wait_event_type"] == "Lock"
                and blocker_pid in list(last["blocking_pids"] or [])
            ):
                return last
            if task.done.is_set():
                break
            time.sleep(0.02)
        raise AssertionError(
            f"{task.name} did not block on pid={blocker_pid}; activity={last}; outcome={task.report()}"
        )

    def capture_locks(self, label: str) -> dict[str, Any]:
        if self.monitor_engine is None:
            raise RuntimeError("monitor engine is not initialized")
        with self.monitor_engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT a.pid, a.application_name, a.state, a.wait_event_type, a.wait_event,
                           pg_blocking_pids(a.pid) AS blocking_pids,
                           l.locktype, l.mode, l.granted,
                           CASE WHEN l.relation IS NULL THEN NULL ELSE l.relation::regclass::text END AS relation,
                           l.page, l.tuple, l.transactionid, l.virtualxid
                    FROM pg_stat_activity AS a
                    LEFT JOIN pg_locks AS l ON l.pid = a.pid
                    WHERE a.datname = current_database()
                      AND a.application_name LIKE :prefix
                    ORDER BY a.application_name, l.granted, l.locktype, l.mode, relation
                    """
                ),
                {"prefix": f"{APP_PREFIX}%"},
            ).mappings().all()
        return {"label": label, "rows": [json_value(dict(row)) for row in rows]}

    def deadlock_count(self) -> int:
        with self.admin_engine.connect() as connection:
            return int(
                connection.execute(
                    text("SELECT deadlocks FROM pg_stat_database WHERE datname = current_database()")
                ).scalar_one()
            )

    def run_command(self, suffix: str, target: Callable[[Session], Any]) -> Any:
        task = self.start_task(suffix, target)
        self.join(task)
        self.require_success(task)
        return task.result

    @staticmethod
    def require_success(task: CommandTask) -> None:
        if task.error is not None:
            raise AssertionError(f"unexpected task error: {task.report()}")

    @staticmethod
    def require_fail_closed(task: CommandTask) -> None:
        if not isinstance(task.error, ResearchError) or task.error.code not in {
            "research_resource_not_found",
            "research_state_conflict",
            "stale_state_version",
        }:
            raise AssertionError(f"expected fail-closed Research conflict: {task.report()}")

    def claim_specific(self, fixture: RunFixture, index: int, worker: str) -> Any:
        return self.run_command(
            f"setup-{worker}",
            lambda db: claim_specific_research_step(
                db,
                run_id=fixture.run_id,
                step_key=fixture.step_keys[index],
                branch_key=fixture.branch_keys[index],
                worker_instance_id=worker,
                lease_seconds=120,
                now=utcnow(),
            ),
        )

    def count(self, model: type[Any], *criteria: Any) -> int:
        with self.sessions() as db:
            return int(db.scalar(select(func.count()).select_from(model).where(*criteria)) or 0)

    def scenario_claim_cancel(self) -> dict[str, Any]:
        fixture = self.seed_run("claim-cancel")
        gate = AttemptInsertGate(self, f"{APP_PREFIX}claim-cancel:gate", "r0-claim-cancel")
        claim = self.start_task(
            "claim-cancel:claim",
            lambda db: claim_next_research_step(db, worker_instance_id="r0-claim-cancel", lease_seconds=120),
        )
        cancel: CommandTask | None = None
        sample: dict[str, Any] | None = None
        try:
            self.wait_blocked_by(claim, gate.pid)
            cancel = self.start_task(
                "claim-cancel:cancel",
                lambda db: cancel_research_run_transition(
                    db,
                    workspace_id=self.workspace_id,
                    actor_user_id=self.user_id,
                    actor_role="owner",
                    run_id=fixture.run_id,
                    expected_state_version=1,
                    reason_code="user_requested",
                    now=utcnow(),
                ),
            )
            self.wait_blocked_by(cancel, claim.pid or -1)
            sample = self.capture_locks("claim-vs-cancel")
        finally:
            gate.release()
            self.join(claim)
            if cancel is not None:
                self.join(cancel)
        self.require_success(claim)
        if cancel is None:
            raise AssertionError("claim-vs-cancel did not start cancellation")
        self.require_fail_closed(cancel)
        if getattr(claim.result, "run_id", None) != fixture.run_id:
            raise AssertionError("claim-vs-cancel claimed the wrong Run")
        attempts = self.count(ResearchStepAttempt, ResearchStepAttempt.step_id == fixture.step_ids[0])
        if attempts != 1:
            raise AssertionError(f"claim-vs-cancel duplicate claim count={attempts}")
        return {"name": "claim-vs-cancel", "sample": sample, "tasks": [claim.report(), cancel.report()]}

    def scenario_claim_complete(self) -> dict[str, Any]:
        fixture = self.seed_run("claim-complete", step_count=2)
        active = self.claim_specific(fixture, 0, "claim-complete-active")
        gate = AttemptInsertGate(self, f"{APP_PREFIX}claim-complete:gate", "r0-claim-complete")
        claim = self.start_task(
            "claim-complete:claim",
            lambda db: claim_next_research_step(db, worker_instance_id="r0-claim-complete", lease_seconds=120),
        )
        completion: CommandTask | None = None
        sample: dict[str, Any] | None = None
        try:
            self.wait_blocked_by(claim, gate.pid)
            completion = self.start_task(
                "claim-complete:complete",
                lambda db: complete_research_step(
                    db,
                    attempt_id=active.attempt_id,
                    lease_token=active.lease_token,
                    output_sha256=sha("claim-complete-output"),
                    now=utcnow(),
                ),
            )
            self.wait_blocked_by(completion, claim.pid or -1)
            sample = self.capture_locks("claim-vs-complete")
        finally:
            gate.release()
            self.join(claim)
            if completion is not None:
                self.join(completion)
        self.require_success(claim)
        if completion is None:
            raise AssertionError("claim-vs-complete did not start completion")
        self.require_success(completion)
        terminal_events = self.count(
            ResearchEvent,
            ResearchEvent.attempt_id == active.attempt_id,
            ResearchEvent.event_type == "step_succeeded",
        )
        if terminal_events != 1:
            raise AssertionError(f"claim-vs-complete duplicate completion count={terminal_events}")
        return {"name": "claim-vs-complete", "sample": sample, "tasks": [claim.report(), completion.report()]}

    def scenario_claims_same_run(self) -> dict[str, Any]:
        fixture = self.seed_run("claims-same-run")
        gate = AttemptInsertGate(self, f"{APP_PREFIX}claims-same:gate", "r0-same-1")
        first = self.start_task(
            "claims-same:first",
            lambda db: claim_next_research_step(db, worker_instance_id="r0-same-1", lease_seconds=120),
        )
        second: CommandTask | None = None
        sample: dict[str, Any] | None = None
        try:
            self.wait_blocked_by(first, gate.pid)
            second = self.start_task(
                "claims-same:second",
                lambda db: claim_next_research_step(db, worker_instance_id="r0-same-2", lease_seconds=120),
            )
            if not second.done.wait(2.0):
                raise AssertionError("second same-Run claim did not SKIP LOCKED")
            self.require_success(second)
            if second.result is not None:
                raise AssertionError("second same-Run claim duplicated ownership")
            sample = self.capture_locks("two-claims-same-run")
        finally:
            gate.release()
            self.join(first)
            if second is not None:
                self.join(second)
        self.require_success(first)
        if second is None:
            raise AssertionError("same-Run second claimant did not start")
        attempts = self.count(ResearchStepAttempt, ResearchStepAttempt.step_id == fixture.step_ids[0])
        if attempts != 1:
            raise AssertionError(f"same-Run claim count={attempts}")
        return {"name": "two-claims-same-run", "sample": sample, "tasks": [first.report(), second.report()]}

    def scenario_claims_different_runs(self) -> dict[str, Any]:
        base = utcnow() + timedelta(seconds=5)
        first_fixture = self.seed_run("claims-different-a", queued_at=base)
        second_fixture = self.seed_run("claims-different-b", queued_at=base + timedelta(seconds=1))
        gate = AttemptInsertGate(
            self,
            f"{APP_PREFIX}claims-different:gate",
            "r0-different-1",
        )
        first = self.start_task(
            "claims-different:first",
            lambda db: claim_next_research_step(db, worker_instance_id="r0-different-1", lease_seconds=120),
        )
        second: CommandTask | None = None
        sample: dict[str, Any] | None = None
        try:
            self.wait_blocked_by(first, gate.pid)
            second = self.start_task(
                "claims-different:second",
                lambda db: claim_next_research_step(db, worker_instance_id="r0-different-2", lease_seconds=120),
            )
            if not second.done.wait(2.0):
                raise AssertionError("different-Run claim was head-blocked")
            self.require_success(second)
            if getattr(second.result, "run_id", None) != second_fixture.run_id:
                raise AssertionError("different-Run claimant did not skip the locked Run")
            sample = self.capture_locks("claims-different-runs")
        finally:
            gate.release()
            self.join(first)
            if second is not None:
                self.join(second)
        self.require_success(first)
        if second is None:
            raise AssertionError("different-Run second claimant did not start")
        if getattr(first.result, "run_id", None) != first_fixture.run_id:
            raise AssertionError("first different-Run claimant changed ordering")
        return {"name": "claims-different-runs", "sample": sample, "tasks": [first.report(), second.report()]}

    def scenario_locator_changed(self) -> dict[str, Any]:
        source = self.seed_run("locator-source")
        destination = self.seed_run("locator-destination")
        lease = self.claim_specific(source, 0, "locator-active")
        with self.sessions() as db:
            before_expiry = db.get(ResearchStepAttempt, lease.attempt_id).lease_expires_at
        gate = RowGate(self, f"{APP_PREFIX}locator:gate", "research_runs", source.run_id)
        heartbeat = self.start_task(
            "locator:heartbeat",
            lambda db: heartbeat_research_step(
                db,
                attempt_id=lease.attempt_id,
                lease_token=lease.lease_token,
                lease_seconds=300,
                now=utcnow(),
            ),
        )
        sample: dict[str, Any] | None = None
        try:
            self.wait_blocked_by(heartbeat, gate.pid)
            with self.sessions() as db:
                self.configure_session(db, f"{APP_PREFIX}locator:move")
                db.execute(
                    text("UPDATE research_step_attempts SET step_id = :destination WHERE id = :attempt"),
                    {"destination": destination.step_ids[0], "attempt": lease.attempt_id},
                )
                db.commit()
            sample = self.capture_locks("locator-changed-fail-closed")
        finally:
            gate.release()
            self.join(heartbeat)
        self.require_fail_closed(heartbeat)
        with self.sessions() as db:
            attempt = db.get(ResearchStepAttempt, lease.attempt_id)
            if attempt is None or attempt.step_id != destination.step_ids[0]:
                raise AssertionError("locator move was not retained")
            if attempt.lease_expires_at != before_expiry:
                raise AssertionError("stale locator heartbeat changed lease expiry")
            source_step = db.get(ResearchStep, source.step_ids[0])
            if source_step is None or source_step.status != "running":
                raise AssertionError("stale locator heartbeat changed source Step")
        return {"name": "locator-changed-fail-closed", "sample": sample, "tasks": [heartbeat.report()]}

    def prepare_reclaim(self, name: str, kind: str) -> tuple[RunFixture, Any, str, datetime]:
        fixture = self.seed_run(name)
        lease = self.claim_specific(fixture, 0, f"{name}-active")
        if kind == "provider":
            reservation = self.run_command(
                f"setup-{name}-provider",
                lambda db: reserve_provider_call(
                    db,
                    attempt_id=lease.attempt_id,
                    logical_call_key=f"{name}:provider",
                    request_sha256=sha(f"{name}/provider-request"),
                    provider="openai",
                    model="gpt-5.5",
                    provider_config_fingerprint=sha(f"{name}/provider"),
                    reserved_input_tokens=10,
                    reserved_output_tokens=10,
                    now=utcnow(),
                    provider_config_matcher=lambda _db, _step, _fingerprint: True,
                ),
            )
            call_id = reservation.provider_call_id
        else:
            reservation = self.run_command(
                f"setup-{name}-tool",
                lambda db: begin_tool_call(
                    db,
                    attempt_id=lease.attempt_id,
                    tool_call_key=f"{name}:tool",
                    tool_name="evidence.search",
                    request_sha256=sha(f"{name}/tool-request"),
                    now=utcnow(),
                ),
            )
            call_id = reservation.tool_call_id
        reclaim_at = utcnow()
        with self.sessions() as db:
            attempt = db.get(ResearchStepAttempt, lease.attempt_id)
            if attempt is None:
                raise AssertionError(f"{name} setup Attempt is missing")
            attempt.lease_expires_at = reclaim_at - timedelta(seconds=2)
            db.commit()
        return fixture, lease, call_id, reclaim_at

    def scenario_reclaim_call(self, kind: str) -> dict[str, Any]:
        name = f"reclaim-{kind}"
        fixture, lease, call_id, reclaim_at = self.prepare_reclaim(name, kind)
        table = "research_provider_calls" if kind == "provider" else "research_tool_calls"
        gate = RowGate(self, f"{APP_PREFIX}{name}:gate", table, call_id)
        reclaim = self.start_task(
            f"{name}:reclaim",
            lambda db: reclaim_expired_research_steps(db, limit=1, now=reclaim_at),
        )
        call_task: CommandTask | None = None
        sample: dict[str, Any] | None = None
        try:
            self.wait_blocked_by(reclaim, gate.pid)
            if kind == "provider":
                call_task = self.start_task(
                    f"{name}:call",
                    lambda db: cancel_provider_reservation(db, call_id, now=utcnow()),
                )
            else:
                call_task = self.start_task(
                    f"{name}:call",
                    lambda db: complete_tool_call(
                        db,
                        tool_call_id=call_id,
                        status="succeeded",
                        now=utcnow(),
                    ),
                )
            self.wait_blocked_by(call_task, reclaim.pid or -1)
            sample = self.capture_locks(f"reclaim-vs-{kind}")
        finally:
            gate.release()
            self.join(reclaim)
            if call_task is not None:
                self.join(call_task)
        self.require_success(reclaim)
        if reclaim.result != 1:
            raise AssertionError(f"{name} reclaimed count={reclaim.result}")
        if call_task is None:
            raise AssertionError(f"{name} competing Call command did not start")
        self.require_fail_closed(call_task)
        with self.sessions() as db:
            attempt = db.get(ResearchStepAttempt, lease.attempt_id)
            ledger = db.get(ResearchBudgetLedger, fixture.ledger_id)
            if attempt is None or attempt.status != "abandoned":
                raise AssertionError(f"{name} did not abandon exactly one Attempt")
            if ledger is None:
                raise AssertionError(f"{name} ledger missing")
            if kind == "provider":
                call = db.get(ResearchProviderCall, call_id)
                if call is None or call.status != "cancelled" or ledger.reserved_provider_calls != 0:
                    raise AssertionError(f"{name} provider/ledger terminal facts are not unique")
            else:
                call = db.get(ResearchToolCall, call_id)
                if call is None or call.status != "abandoned":
                    raise AssertionError(f"{name} tool terminal fact is not unique")
                if ledger.reserved_tool_calls != 0 or ledger.actual_tool_calls != 1:
                    raise AssertionError(f"{name} tool ledger was applied more than once")
        abandoned_events = self.count(
            ResearchEvent,
            ResearchEvent.attempt_id == lease.attempt_id,
            ResearchEvent.event_type == "attempt_abandoned",
        )
        if abandoned_events != 1:
            raise AssertionError(f"{name} duplicate abandoned event count={abandoned_events}")
        return {"name": f"reclaim-vs-{kind}", "sample": sample, "tasks": [reclaim.report(), call_task.report()]}

    def run(self) -> dict[str, Any]:
        scenarios = [
            self.scenario_claim_cancel,
            self.scenario_claim_complete,
            self.scenario_claims_same_run,
            self.scenario_claims_different_runs,
            self.scenario_locator_changed,
            lambda: self.scenario_reclaim_call("provider"),
            lambda: self.scenario_reclaim_call("tool"),
        ]
        for scenario in scenarios:
            started = time.monotonic()
            evidence = scenario()
            evidence["durationMs"] = round((time.monotonic() - started) * 1000, 3)
            evidence["status"] = "pass"
            self.report["scenarios"].append(evidence)
            print(f"r0_harness scenario={evidence['name']} status=pass", flush=True)
        for task in self.tasks:
            state = sqlstate(task.error)
            if state in {"40P01", "55P03"}:
                raise AssertionError(f"deadlock or lock timeout in {task.report()}")
        deadlocks_after = self.deadlock_count()
        if deadlocks_after != self.deadlocks_before:
            raise AssertionError(
                f"PostgreSQL deadlock counter changed: before={self.deadlocks_before} after={deadlocks_after}"
            )
        self.report["deadlocksBefore"] = self.deadlocks_before
        self.report["deadlocksAfter"] = deadlocks_after
        self.report["status"] = "pass"
        return self.report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    harness = ContentionHarness(args.database_url)
    exit_code = 0
    try:
        harness.setup()
        report = harness.run()
    except BaseException as error:  # noqa: BLE001 - always emit actionable evidence
        exit_code = 1
        report = harness.report
        report["status"] = "fail"
        report["error"] = error_value(error)
        report["traceback"] = traceback.format_exc()
        print(f"r0_harness status=fail error={type(error).__name__}:{error}", flush=True)
    finally:
        try:
            harness.cleanup()
            report["cleanup"] = "pass"
        except BaseException as cleanup_error:  # noqa: BLE001
            report["cleanup"] = "fail"
            report["cleanupError"] = error_value(cleanup_error)
            exit_code = 1
        report["finishedAt"] = utcnow().isoformat()
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True, default=json_value) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
