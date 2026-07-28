from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ai_pdf_api.db.base import Base
from ai_pdf_api.models.research_versions import JSON_DOCUMENT


class ResearchStep(Base):
    __tablename__ = "research_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "step_key", name="uq_research_steps_run_key"),
        UniqueConstraint("workspace_id", "id", name="uq_research_steps_workspace_id"),
        Index("ix_research_steps_run_status_kind", "run_id", "status", "step_kind"),
        Index("ix_research_steps_run_branch", "run_id", "branch_key"),
        CheckConstraint(
            "step_kind IN ('planner','plan_approval_gate','researcher','join','verifier','critic',"
            "'conflict_decision_gate','synthesizer','artifact_publisher')",
            name="ck_research_steps_kind",
        ),
        CheckConstraint(
            "status IN ('pending','queued','running','waiting','succeeded','failed','cancelled','skipped')",
            name="ck_research_steps_status",
        ),
        CheckConstraint(
            "(step_kind = 'researcher' AND branch_key IS NOT NULL) OR "
            "(step_kind <> 'researcher' AND branch_key IS NULL)",
            name="ck_research_steps_branch",
        ),
        CheckConstraint(
            "status <> 'waiting' OR step_kind IN ('plan_approval_gate','conflict_decision_gate')",
            name="ck_research_steps_waiting_gate",
        ),
        CheckConstraint("max_attempts_snapshot > 0", name="ck_research_steps_max_attempts"),
        CheckConstraint("current_attempt_number >= 0", name="ck_research_steps_current_attempt"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_runs.id"))
    plan_revision_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_plan_revisions.id"), nullable=True
    )
    execution_snapshot_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_execution_snapshots.id"), nullable=True
    )
    step_key: Mapped[str] = mapped_column(String(128))
    step_kind: Mapped[str] = mapped_column(String(32))
    branch_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    state_version: Mapped[int] = mapped_column(BigInteger, default=1)
    prompt_version_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("prompt_versions.id"), nullable=True)
    max_attempts_snapshot: Mapped[int] = mapped_column(SmallInteger)
    current_attempt_number: Mapped[int] = mapped_column(SmallInteger, default=0)
    input_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResearchStepDependency(Base):
    __tablename__ = "research_step_dependencies"

    step_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_steps.id"), primary_key=True)
    depends_on_step_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_steps.id"), primary_key=True)


class ResearchStepAttempt(Base):
    __tablename__ = "research_step_attempts"
    __table_args__ = (
        UniqueConstraint("step_id", "attempt_number", name="uq_research_step_attempts_number"),
        CheckConstraint(
            "status IN ('running','succeeded','failed','timed_out','abandoned','cancelled')",
            name="ck_research_step_attempts_status",
        ),
        CheckConstraint("attempt_number > 0", name="ck_research_step_attempts_number"),
        CheckConstraint("provider_call_count >= 0", name="ck_research_step_attempts_provider_calls"),
        CheckConstraint("tool_call_count >= 0", name="ck_research_step_attempts_tool_calls"),
        CheckConstraint("input_tokens >= 0 AND output_tokens >= 0", name="ck_research_step_attempts_tokens"),
        CheckConstraint("cost_microunits >= 0", name="ck_research_step_attempts_cost"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    step_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_steps.id"), index=True)
    attempt_number: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(String(16))
    lease_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    worker_instance_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input_sha256: Mapped[str] = mapped_column(String(64))
    output_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_call_count: Mapped[int] = mapped_column(Integer, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cost_microunits: Mapped[int] = mapped_column(BigInteger, default=0)
    checkpoint_artifact_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("research_artifacts.id", use_alter=True, name="fk_research_attempt_checkpoint_artifact"),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchStepRetryRequest(Base):
    __tablename__ = "research_step_retry_requests"
    __table_args__ = (
        UniqueConstraint("step_id", "failed_attempt_number", name="uq_research_retry_step_attempt"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_runs.id"))
    step_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_steps.id"))
    failed_attempt_number: Mapped[int] = mapped_column(SmallInteger)
    requested_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    expected_run_state_version: Mapped[int] = mapped_column(BigInteger)
    expected_step_state_version: Mapped[int] = mapped_column(BigInteger)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResearchToolCall(Base):
    __tablename__ = "research_tool_calls"
    __table_args__ = (
        UniqueConstraint(
            "step_id", "tool_call_key", "call_attempt_number", name="uq_research_tool_calls_logical_attempt"
        ),
        UniqueConstraint("attempt_id", "call_order", name="uq_research_tool_calls_attempt_order"),
        Index(
            "uq_research_tool_calls_succeeded_logical",
            "step_id",
            "tool_call_key",
            unique=True,
            postgresql_where=text("status = 'succeeded'"),
            sqlite_where=text("status = 'succeeded'"),
        ),
        CheckConstraint("tool_name IN ('evidence.search','evidence.load')", name="ck_research_tool_calls_name"),
        CheckConstraint(
            "status IN ('requested','running','succeeded','failed','cancelled','abandoned')",
            name="ck_research_tool_calls_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_runs.id"))
    execution_snapshot_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_execution_snapshots.id"))
    step_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_steps.id"))
    attempt_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_step_attempts.id"))
    tool_call_key: Mapped[str] = mapped_column(String(160))
    call_attempt_number: Mapped[int] = mapped_column(SmallInteger)
    call_order: Mapped[int] = mapped_column(Integer)
    tool_name: Mapped[str] = mapped_column(String(32))
    tool_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16))
    request_sha256: Mapped[str] = mapped_column(String(64))
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchEvidenceHandle(Base):
    __tablename__ = "research_evidence_handles"
    __table_args__ = (
        UniqueConstraint("created_by_tool_call_id", "result_order", name="uq_research_evidence_handles_order"),
        UniqueConstraint("run_id", "handle_fingerprint_sha256", name="uq_research_evidence_handles_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_runs.id"))
    execution_snapshot_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_execution_snapshots.id"))
    owner_step_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_steps.id"))
    created_by_tool_call_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_tool_calls.id"))
    evidence_snapshot_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_evidence_snapshots.id"))
    result_order: Mapped[int] = mapped_column(Integer)
    handle_fingerprint_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResearchToolCallInputHandle(Base):
    __tablename__ = "research_tool_call_input_handles"
    __table_args__ = (
        UniqueConstraint("tool_call_id", "input_order", name="uq_research_tool_input_handles_order"),
    )

    tool_call_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_tool_calls.id"), primary_key=True)
    evidence_handle_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_evidence_handles.id"), primary_key=True
    )
    input_order: Mapped[int] = mapped_column(Integer)


class ResearchBudgetLedger(Base):
    __tablename__ = "research_budget_ledgers"
    __table_args__ = (
        CheckConstraint(
            "(plan_revision_id IS NULL) <> (execution_snapshot_id IS NULL)",
            name="ck_research_budget_ledgers_single_scope",
        ),
        CheckConstraint(
            "reserved_provider_calls >= 0 AND reserved_tool_calls >= 0 AND actual_provider_calls >= 0 "
            "AND actual_tool_calls >= 0",
            name="ck_research_budget_ledgers_calls",
        ),
        CheckConstraint(
            "reserved_input_tokens >= 0 AND reserved_output_tokens >= 0 AND actual_input_tokens >= 0 "
            "AND actual_output_tokens >= 0",
            name="ck_research_budget_ledgers_tokens",
        ),
        CheckConstraint(
            "reserved_cost_microunits >= 0 AND actual_cost_microunits >= 0",
            name="ck_research_budget_ledgers_cost",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_runs.id"))
    plan_revision_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_plan_revisions.id"), nullable=True, unique=True
    )
    execution_snapshot_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_execution_snapshots.id"), nullable=True, unique=True
    )
    currency: Mapped[str] = mapped_column(String(3))
    state_version: Mapped[int] = mapped_column(BigInteger, default=1)
    reserved_provider_calls: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved_tool_calls: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved_input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved_output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved_cost_microunits: Mapped[int] = mapped_column(BigInteger, default=0)
    actual_provider_calls: Mapped[int] = mapped_column(BigInteger, default=0)
    actual_tool_calls: Mapped[int] = mapped_column(BigInteger, default=0)
    actual_input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    actual_output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    actual_cost_microunits: Mapped[int] = mapped_column(BigInteger, default=0)
    usage_final: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResearchProviderCall(Base):
    __tablename__ = "research_provider_calls"
    __table_args__ = (
        UniqueConstraint("attempt_id", "logical_call_key", "send_attempt", name="uq_research_provider_calls_send"),
        CheckConstraint(
            "status IN ('reserved','sent','succeeded','failed','outcome_unknown','cancelled')",
            name="ck_research_provider_calls_status",
        ),
        CheckConstraint("usage_source IN ('reserved','actual','estimated')", name="ck_research_provider_calls_usage"),
        CheckConstraint(
            "reserved_input_tokens >= 0 AND reserved_output_tokens >= 0 AND reserved_cost_microunits >= 0",
            name="ck_research_provider_calls_reservation",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_runs.id"))
    budget_ledger_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_budget_ledgers.id"))
    step_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_steps.id"))
    attempt_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_step_attempts.id"))
    logical_call_key: Mapped[str] = mapped_column(String(160))
    send_attempt: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(String(24))
    request_sha256: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    provider_config_fingerprint: Mapped[str] = mapped_column(String(64))
    reserved_input_tokens: Mapped[int] = mapped_column(BigInteger)
    reserved_output_tokens: Mapped[int] = mapped_column(BigInteger)
    reserved_cost_microunits: Mapped[int] = mapped_column(BigInteger)
    actual_input_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actual_output_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actual_cost_microunits: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    usage_source: Mapped[str] = mapped_column(String(16))
    usage_final: Mapped[bool] = mapped_column(Boolean)
    provider_response_id_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchIdempotencyRecord(Base):
    __tablename__ = "research_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "actor_user_id", "workspace_id", "operation", "canonical_resource_path", "idempotency_key",
            name="uq_research_idempotency_scope_key",
        ),
        CheckConstraint(
            "operation IN ('create_run','cancel_run','submit_plan_decision','submit_conflict_decision','retry_step')",
            name="ck_research_idempotency_operation",
        ),
        CheckConstraint("status IN ('in_progress','completed','failed')", name="ck_research_idempotency_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    actor_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    operation: Mapped[str] = mapped_column(String(32))
    canonical_resource_path: Mapped[str] = mapped_column(String(512))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    http_status: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    result_resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    response_schema_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    response_json: Mapped[dict[str, object] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResearchEvent(Base):
    __tablename__ = "research_events"
    __table_args__ = (
        UniqueConstraint("run_id", "seq", name="uq_research_events_run_seq"),
        UniqueConstraint("run_id", "dedupe_key", name="uq_research_events_run_dedupe"),
        CheckConstraint(
            "event_type IN ('run_created','run_status_changed','step_queued','step_started','step_waiting',"
            "'step_succeeded','step_failed','attempt_abandoned','approval_requested','decision_submitted',"
            "'cancel_requested','artifact_published','run_completed','run_failed','run_cancelled')",
            name="ck_research_events_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_runs.id"))
    seq: Mapped[int] = mapped_column(BigInteger)
    event_type: Mapped[str] = mapped_column(String(64))
    event_schema_version: Mapped[str] = mapped_column(String(32), default="1")
    step_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("research_steps.id"), nullable=True)
    attempt_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_step_attempts.id"), nullable=True
    )
    dedupe_key: Mapped[str] = mapped_column(String(160))
    payload_json: Mapped[dict[str, object]] = mapped_column(JSON_DOCUMENT)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
