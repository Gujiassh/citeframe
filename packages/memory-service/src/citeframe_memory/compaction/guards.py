"""Bounded Option A native guards; no remote work or partial manifest acceptance."""
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json

from sqlalchemy import select, text
from sqlalchemy.orm import Session
from citeframe_contracts.compaction import ContextOwner
from citeframe_persistence.models import (
    ChatMemoryExecution, ChatMessage, ChatThread, ResearchBudgetLedger, ResearchRun,
    ResearchProviderCall, ResearchStep, ResearchStepAttempt, TaskMemorySnapshot, User, Workspace, WorkspaceMembership,
)
from .policy import CompactionError


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def body_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class GuardLimits:
    max_thread_rows: int = 1024
    max_manifest_bytes: int = 131072
    max_body_bytes: int = 1048576
    statement_timeout_ms: int = 2000
    lock_timeout_ms: int = 250
    transaction_timeout_ms: int = 5000

    def __post_init__(self):
        if any(type(v) is not int or v <= 0 for v in asdict(self).values()):
            raise CompactionError("invalid_guard_limits")


def lock_one(db, model, key):
    return db.scalar(select(model).where(model.id == key).with_for_update(nowait=True)
                     .execution_options(populate_existing=True))


class NativeGuard:
    def __init__(self, db: Session, owner: ContextOwner, limits: GuardLimits, now: datetime, native_provider_call_id=None):
        self.db, self.owner, self.limits, self.now = db, owner, limits, now
        self.native_provider_call_id=native_provider_call_id
        if db.bind.dialect.name != "postgresql":
            raise CompactionError("postgresql_required")
        if db.connection().get_isolation_level() != "READ COMMITTED":
            raise CompactionError("read_committed_required")
        db.execute(text("SET LOCAL transaction_timeout = " + str(limits.transaction_timeout_ms)))
        db.execute(text("SET LOCAL statement_timeout = " + str(limits.statement_timeout_ms)))
        db.execute(text("SET LOCAL lock_timeout = " + str(limits.lock_timeout_ms)))
        workspace = lock_one(db, Workspace, owner.workspace_id)
        member = db.scalar(select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == owner.workspace_id,
            WorkspaceMembership.user_id == owner.actor_user_id).with_for_update(nowait=True))
        if workspace is None or workspace.archived_at is not None or member is None or member.role not in ("owner", "member"):
            raise CompactionError("context_access_denied")
        if lock_one(db, User, owner.actor_user_id) is None:
            raise CompactionError("context_access_denied")
        self.thread = self.run = self.step = self.ledger = None
        if owner.kind == "chat":
            self._chat()
        else:
            self._research()
        self.snapshot = None

    def _chat(self):
        # Locate IDs only before taking the native parent/root guards.
        located = self.db.execute(select(ChatMemoryExecution.thread_id, ChatMemoryExecution.retry_of_id).where(
            ChatMemoryExecution.id == self.owner.owner_id)).first()
        if located is None:
            raise CompactionError("context_access_denied")
        self.thread = lock_one(self.db, ChatThread, located.thread_id)
        if self.thread is None or self.thread.workspace_id != self.owner.workspace_id or self.thread.archived_at:
            raise CompactionError("context_access_denied")
        ids, key = [], self.owner.owner_id
        while key:
            if key in ids or len(ids) >= 16:
                raise CompactionError("retry_limit")
            ids.append(key)
            key = self.db.scalar(select(ChatMemoryExecution.retry_of_id).where(ChatMemoryExecution.id == key))
        chain = [lock_one(self.db, ChatMemoryExecution, id_) for id_ in reversed(ids)]
        if any(row is None or row.workspace_id != self.owner.workspace_id
               or row.actor_user_id != self.owner.actor_user_id or row.thread_id != self.thread.id for row in chain):
            raise CompactionError("context_access_denied")
        self.root, self.native = chain[0], chain[-1]
        if self.native.state not in ("prepared", "running", "waiting_context") or self.native.cancel_requested_at:
            raise CompactionError("context_cancelled_or_terminal")
        if self.root.deadline_at <= self.now:
            raise CompactionError("context_deadline")
        self._lease()
        rows = self.db.execute(select(ChatMessage.id, ChatMessage.compaction_revision, ChatMessage.parent_message_id,
            ChatMessage.workspace_id, ChatMessage.role, ChatMessage.status).where(
            ChatMessage.thread_id == self.thread.id).order_by(ChatMessage.id)
            .limit(self.limits.max_thread_rows + 1).with_for_update(nowait=True)).all()
        self.membership = [[row.id,row.compaction_revision] for row in rows]
        if len(rows) > self.limits.max_thread_rows or len(canonical(self.membership).encode()) > self.limits.max_manifest_bytes:
            raise CompactionError("context_too_large")
        metadata={row.id:row for row in rows}
        user,assistant=metadata.get(self.native.user_message_id),metadata.get(self.native.assistant_message_id)
        if (user is None or assistant is None or user.workspace_id!=self.owner.workspace_id
                or assistant.workspace_id!=self.owner.workspace_id or user.role!="user" or user.status!="completed"
                or assistant.role!="assistant" or assistant.status!="streaming"
                or assistant.parent_message_id!=user.id):
            raise CompactionError("invalid_native_message")
        if self.native.anchor_leaf_id is not None and (self.native.anchor_leaf_id not in metadata
                or metadata[self.native.anchor_leaf_id].workspace_id!=self.owner.workspace_id):
            raise CompactionError("source_branch_mismatch")
        if self.thread.active_message_id!=self.native.anchor_leaf_id:
            raise CompactionError("context_branch_changed")
        self.ancestry=set();current=user.id
        while current is not None:
            row=metadata.get(current)
            if (current in self.ancestry or row is None or row.workspace_id!=self.owner.workspace_id
                    or row.role not in ("user","assistant") or row.status not in ("completed","failed")):
                raise CompactionError("source_branch_mismatch")
            self.ancestry.add(current);current=row.parent_message_id
        self.native_state = dict(thread=self.thread.id, revision=self.thread.compaction_revision,
                                 leaf=self.thread.active_message_id, messages=self.membership,
                                 designatedUser=user.id, designatedAssistant=assistant.id,
                                 version=self.native.version, lease=self.native.lease_token_hash)
        self.policy = self.root.policy

    def retry_owner_ids(self):
        if self.owner.kind!="chat":return [self.owner.owner_id]
        owners=[self.root.id]
        for _ in range(16):
            children=list(self.db.scalars(select(ChatMemoryExecution.id).where(ChatMemoryExecution.retry_of_id.in_(owners))))
            new=[id_ for id_ in children if id_ not in owners]
            if not new:return owners
            owners.extend(new)
        raise CompactionError("retry_limit")

    def _research(self):
        located = self.db.execute(select(ResearchStepAttempt.step_id, ResearchStep.run_id).join(
            ResearchStep, ResearchStep.id == ResearchStepAttempt.step_id).where(
            ResearchStepAttempt.id == self.owner.owner_id)).first()
        if located is None:
            raise CompactionError("context_access_denied")
        self.run = lock_one(self.db, ResearchRun, located.run_id)
        self.step = lock_one(self.db, ResearchStep, located.step_id)
        self.native = lock_one(self.db, ResearchStepAttempt, self.owner.owner_id)
        if (any(row is None or row.workspace_id != self.owner.workspace_id for row in (self.run,self.step,self.native))
                or self.run.created_by_user_id != self.owner.actor_user_id or self.run.archived_at
                or self.run.status not in ("planning", "running") or self.run.cancel_requested_at
                or self.step.status != "running" or self.native.status != "running"
                or self.step.current_attempt_number != self.native.attempt_number
                or self.native.step_id != self.step.id or self.step.run_id != self.run.id):
            raise CompactionError("context_cancelled_or_terminal")
        self._lease()
        if self.native_provider_call_id:
            provider_call=lock_one(self.db,ResearchProviderCall,self.native_provider_call_id)
            if (provider_call is None or provider_call.workspace_id!=self.owner.workspace_id
                    or provider_call.run_id!=self.run.id or provider_call.step_id!=self.step.id
                    or provider_call.attempt_id!=self.native.id):
                raise CompactionError("native_call_scope_mismatch")
        self.ledger = self.db.scalar(select(ResearchBudgetLedger).where(
            ResearchBudgetLedger.run_id == self.run.id,
            ResearchBudgetLedger.plan_revision_id == self.step.plan_revision_id,
            ResearchBudgetLedger.execution_snapshot_id == self.step.execution_snapshot_id).with_for_update(nowait=True))
        if self.ledger is None or self.ledger.workspace_id != self.owner.workspace_id:
            raise CompactionError("native_ledger_missing")
        self.native_state = dict(run=self.run.id, runVersion=self.run.state_version,
                                 step=self.step.id, stepVersion=self.step.state_version,
                                 attempt=self.native.id, lease=self.native.lease_token_hash,
                                 executionSnapshot=self.step.execution_snapshot_id, planRevision=self.step.plan_revision_id,
                                 branch=self.step.branch_key)
        self.policy = None

    def _lease(self):
        if (self.native.lease_token_hash != self.owner.lease_token_hash
                or self.native.lease_expires_at is None or self.native.lease_expires_at <= self.now):
            raise CompactionError("context_lease_lost")

    @property
    def context_version(self):
        return self.native.context_version if self.owner.kind == "chat" else self.native.memory_context_version

    @property
    def checkpoint_id(self):
        return self.native.checkpoint_id if self.owner.kind == "chat" else self.native.memory_checkpoint_id
