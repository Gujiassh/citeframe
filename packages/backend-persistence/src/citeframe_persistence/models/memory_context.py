"""Shared-task compaction state; native owners retain the only active pointers."""
from sqlalchemy import (BigInteger, CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint,
                        Index, Integer, JSON, String, Table, Text, UniqueConstraint, text)
from sqlalchemy.dialects.postgresql import JSONB
from citeframe_persistence.base import Base

J = JSONB().with_variant(JSON(), "sqlite")


def c(name, typ=String(36), nullable=False, **kw):
    return Column(name, typ, nullable=nullable, **kw)


def fk(name, target, nullable=False):
    return Column(name, String(36), ForeignKey(target, ondelete="RESTRICT"), nullable=nullable)


def common():
    return [c("id", primary_key=True), fk("workspace_id", "workspaces.id"),
            UniqueConstraint("workspace_id", "id")]


executions = Table("chat_memory_executions", Base.metadata, *common(),
    fk("actor_user_id", "users.id"), fk("thread_id", "chat_threads.id"),
    fk("user_message_id", "chat_messages.id"), fk("assistant_message_id", "chat_messages.id"),
    c("request_id"), c("request_sha256", String(64)), fk("retry_of_id", "chat_memory_executions.id", True),
    c("attempt_number", Integer), c("state", String(24)), c("version", BigInteger),
    c("context_version", BigInteger, server_default=text("0")), c("checkpoint_id", nullable=True),
    fk("anchor_leaf_id", "chat_messages.id", True), c("policy", J), c("deadline_at", DateTime(timezone=True)),
    c("cancel_requested_at", DateTime(timezone=True), True), c("error_code", String(128), True),
    c("created_at", DateTime(timezone=True)), c("finished_at", DateTime(timezone=True), True),
    c("lease_token_hash", String(64), True), c("lease_expires_at", DateTime(timezone=True), True),
    c("worker_id", String(128), True),
    UniqueConstraint("assistant_message_id"), UniqueConstraint("workspace_id", "actor_user_id", "request_id"),
    UniqueConstraint("retry_of_id"),
    CheckConstraint("version >= 1 AND context_version >= 0 AND attempt_number >= 1", name="ck_chat_memory_versions"),
    CheckConstraint("state IN ('prepared','running','waiting_context','succeeded','failed','cancel_requested','cancelled','outcome_unknown')", name="ck_chat_memory_state"),
    ForeignKeyConstraint(["workspace_id", "checkpoint_id"], ["task_memory_snapshots.workspace_id", "task_memory_snapshots.id"],
                         name="fk_chat_memory_checkpoint", use_alter=True),
)

calls = Table("memory_calls", Base.metadata, *common(), fk("actor_user_id", "users.id"),
    c("chat_execution_id", nullable=True), fk("research_attempt_id", "research_step_attempts.id", True),
    c("purpose", String(24)), c("logical_key", String(160)), c("ordinal", Integer),
    c("parent_call_id", nullable=True), fk("native_provider_call_id", "research_provider_calls.id", True),
    fk("native_tool_call_id", "research_tool_calls.id", True), fk("research_budget_ledger_id", "research_budget_ledgers.id", True),
    c("provider_tool_call_id", String(255), True), c("state", String(24)), c("context_version", BigInteger),
    c("checkpoint_id", nullable=True), c("input_manifest", J), c("request_object_key", String(1024), True),
    c("request_sha256", String(64)), c("result_object_key", String(1024), True), c("result_sha256", String(64), True),
    c("result_state", String(16)), c("result_manifest", J, True), c("result_tokens", BigInteger, True),
    c("policy_fingerprint", String(64)), c("reserved_input", BigInteger), c("reserved_output", BigInteger),
    c("actual_input", BigInteger, True), c("actual_output", BigInteger, True), c("usage_source", String(16)),
    c("cost_microunits", BigInteger, True), c("reservation_state", String(16)),
    c("no_progress_boundary_sha256", String(64), True), c("created_at", DateTime(timezone=True)),
    c("sent_at", DateTime(timezone=True), True), c("settled_at", DateTime(timezone=True), True),
    UniqueConstraint("native_provider_call_id"),
    ForeignKeyConstraint(["workspace_id", "chat_execution_id"], ["chat_memory_executions.workspace_id", "chat_memory_executions.id"]),
    ForeignKeyConstraint(["workspace_id", "parent_call_id"], ["memory_calls.workspace_id", "memory_calls.id"]),
    ForeignKeyConstraint(["workspace_id", "checkpoint_id"], ["task_memory_snapshots.workspace_id", "task_memory_snapshots.id"],
                         name="fk_memory_call_checkpoint", use_alter=True),
    CheckConstraint("(chat_execution_id IS NULL) <> (research_attempt_id IS NULL)", name="ck_memory_call_owner"),
    CheckConstraint("purpose IN ('main','compact_chunk','compact_merge','tool_group','read_source')", name="ck_memory_call_purpose"),
    CheckConstraint("state IN ('reserved','sent','succeeded','failed','cancelled','outcome_unknown') AND result_state IN ('absent','valid','invalidated','erased') AND reservation_state IN ('reserved','settled') AND usage_source IN ('reported','estimated','unknown')", name="ck_memory_call_state"),
    CheckConstraint("ordinal >= 0 AND context_version >= 0 AND reserved_input >= 0 AND reserved_output >= 0 AND actual_input >= 0 AND actual_output >= 0 AND result_tokens >= 0", name="ck_memory_call_counts"),
)
for owner in ("chat_execution_id", "research_attempt_id"):
    Index("uq_memory_call_" + owner, calls.c[owner], calls.c.logical_key, unique=True,
          postgresql_where=text(owner + " IS NOT NULL"), sqlite_where=text(owner + " IS NOT NULL"))

snapshots = Table("task_memory_snapshots", Base.metadata, *common(), fk("owner_user_id", "users.id"),
    c("audience", String(16)), fk("thread_id", "chat_threads.id", True), fk("run_id", "research_runs.id", True),
    fk("step_id", "research_steps.id", True), fk("attempt_id", "research_step_attempts.id", True),
    c("branch_key", String(128), True), fk("anchor_leaf_id", "chat_messages.id", True),
    c("parent_snapshot_id", nullable=True), c("version", BigInteger), c("context_version", BigInteger),
    c("status", String(16)), c("summary", J, True), c("schema_version", String(32)), c("policy_snapshot", J),
    c("provider_fingerprint", String(64)), c("counter_version", String(64)), c("input_sha256", String(64)),
    c("manifest_sha256", String(64)), c("operation_key", String(64)), c("before_tokens", BigInteger),
    c("after_tokens", BigInteger), c("count_source", String(16)), c("generation_call_id", nullable=True),
    c("created_at", DateTime(timezone=True)), c("invalidated_at", DateTime(timezone=True), True),
    c("erased_at", DateTime(timezone=True), True), UniqueConstraint("operation_key"),
    ForeignKeyConstraint(["workspace_id", "parent_snapshot_id"], ["task_memory_snapshots.workspace_id", "task_memory_snapshots.id"]),
    ForeignKeyConstraint(["workspace_id", "generation_call_id"], ["memory_calls.workspace_id", "memory_calls.id"]),
    CheckConstraint("audience = 'workspace' AND version >= 1 AND context_version >= 1 AND before_tokens >= 0 AND after_tokens >= 0 AND count_source IN ('exact','estimated')", name="ck_task_snapshot_values"),
    CheckConstraint("(thread_id IS NOT NULL AND run_id IS NULL AND step_id IS NULL AND attempt_id IS NULL AND branch_key IS NULL) OR (thread_id IS NULL AND anchor_leaf_id IS NULL AND run_id IS NOT NULL AND step_id IS NOT NULL AND attempt_id IS NOT NULL)", name="ck_task_snapshot_owner"),
    CheckConstraint("(status = 'committed' AND summary IS NOT NULL AND erased_at IS NULL) OR (status = 'invalidated' AND erased_at IS NULL) OR (status = 'erased' AND summary IS NULL AND erased_at IS NOT NULL)", name="ck_task_snapshot_payload"),
)

coverage = Table("task_memory_coverage", Base.metadata,
    fk("snapshot_id", "task_memory_snapshots.id"), c("ordinal", Integer), c("unit_key", String(160)),
    fk("source_id", "memory_sources.id", True), fk("tool_group_id", "memory_calls.id", True),
    c("source_version", BigInteger, True), c("parent_message_id", nullable=True),
    UniqueConstraint("snapshot_id", "unit_key"),
    CheckConstraint("ordinal >= 0 AND ((source_id IS NOT NULL AND source_version IS NOT NULL AND source_version >= 1 AND tool_group_id IS NULL) OR (source_id IS NULL AND source_version IS NULL AND tool_group_id IS NOT NULL))", name="ck_task_coverage_unit"),
)
from sqlalchemy import PrimaryKeyConstraint
coverage.append_constraint(PrimaryKeyConstraint("snapshot_id", "ordinal"))


class ChatMemoryExecution(Base):
    __table__ = executions


class MemoryCall(Base):
    __table__ = calls


class TaskMemorySnapshot(Base):
    __table__ = snapshots


class TaskMemoryCoverage(Base):
    __table__ = coverage
