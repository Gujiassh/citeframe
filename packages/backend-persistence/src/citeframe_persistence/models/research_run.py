from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from citeframe_persistence.base import Base


RUN_STATUSES = (
    "planning", "awaiting_plan_approval", "queued", "running", "awaiting_human_decision",
    "awaiting_retry", "cancel_requested", "completed", "failed", "cancelled",
)


class ResearchRun(Base):
    __tablename__ = "research_runs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_research_runs_workspace_id"),
        Index("ix_research_runs_workspace_status_created", "workspace_id", "status", "created_at"),
        Index("ix_research_runs_creator_created", "created_by_user_id", "created_at"),
        CheckConstraint(
            "status IN ('planning','awaiting_plan_approval','queued','running','awaiting_human_decision',"
            "'awaiting_retry','cancel_requested','completed','failed','cancelled')",
            name="ck_research_runs_status",
        ),
        CheckConstraint("state_version >= 1", name="ck_research_runs_state_version"),
        CheckConstraint("next_event_seq >= 1", name="ck_research_runs_next_event_seq"),
        CheckConstraint("cost_currency = upper(cost_currency)", name="ck_research_runs_currency_upper"),
        CheckConstraint(
            "((status IN ('completed','failed','cancelled')) AND finished_at IS NOT NULL) OR "
            "((status NOT IN ('completed','failed','cancelled')) AND finished_at IS NULL)",
            name="ck_research_runs_terminal_finished",
        ),
        CheckConstraint(
            "(cancel_requested_by_user_id IS NULL) = (cancel_requested_at IS NULL)",
            name="ck_research_runs_cancel_audit_pair",
        ),
        CheckConstraint(
            "status <> 'cancel_requested' OR cancel_requested_by_user_id IS NOT NULL",
            name="ck_research_runs_cancel_requested_actor",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    origin_thread_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("chat_threads.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    state_version: Mapped[int] = mapped_column(BigInteger, default=1)
    next_event_seq: Mapped[int] = mapped_column(BigInteger, default=1)
    current_plan_revision_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("research_plan_revisions.id", use_alter=True, name="fk_research_runs_current_plan_revision"),
        nullable=True,
    )
    approved_execution_snapshot_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "research_execution_snapshots.id",
            use_alter=True,
            name="fk_research_runs_approved_execution_snapshot",
        ),
        nullable=True,
        unique=True,
    )
    cost_currency: Mapped[str] = mapped_column(String(3), default="USD")
    latest_checkpoint_artifact_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("research_artifacts.id", use_alter=True, name="fk_research_runs_latest_checkpoint_artifact"),
        nullable=True,
    )
    cancel_requested_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    cancel_reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResearchPlanRevision(Base):
    __tablename__ = "research_plan_revisions"
    __table_args__ = (
        UniqueConstraint("run_id", "revision_number", name="uq_research_plan_revisions_run_number"),
        UniqueConstraint("workspace_id", "id", name="uq_research_plan_revisions_workspace_id"),
        CheckConstraint("revision_number > 0", name="ck_research_plan_revisions_number"),
        CheckConstraint("scope_mode IN ('all_ready','selected')", name="ck_research_plan_revisions_scope"),
        CheckConstraint("proposed_retrieval_top_k > 0", name="ck_research_plan_revisions_top_k"),
        CheckConstraint("planning_max_provider_calls > 0", name="ck_research_plan_revisions_planning_calls"),
        CheckConstraint("proposed_max_provider_calls > 0", name="ck_research_plan_revisions_provider_calls"),
        CheckConstraint("proposed_max_tool_calls > 0", name="ck_research_plan_revisions_tool_calls"),
        CheckConstraint("planning_max_cost_microunits >= 0", name="ck_research_plan_revisions_planning_cost"),
        CheckConstraint("proposed_max_cost_microunits >= 0", name="ck_research_plan_revisions_cost"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_runs.id"), index=True)
    revision_number: Mapped[int] = mapped_column(Integer)
    supersedes_revision_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_plan_revisions.id"), nullable=True
    )
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    question_text: Mapped[str] = mapped_column(Text)
    scope_mode: Mapped[str] = mapped_column(String(16))
    proposed_workflow_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("workflow_versions.id"))
    planner_prompt_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("prompt_versions.id"))
    proposed_generation_provider: Mapped[str] = mapped_column(String(64))
    proposed_generation_model: Mapped[str] = mapped_column(String(128))
    proposed_provider_config_fingerprint: Mapped[str] = mapped_column(String(64))
    proposed_pricing_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proposed_data_boundary_policy_version: Mapped[str] = mapped_column(String(64))
    proposed_embedding_provider: Mapped[str] = mapped_column(String(64))
    proposed_embedding_model: Mapped[str] = mapped_column(String(128))
    proposed_embedding_version: Mapped[str] = mapped_column(String(64))
    proposed_retrieval_strategy: Mapped[str] = mapped_column(String(32))
    proposed_retrieval_top_k: Mapped[int] = mapped_column(Integer)
    planning_max_provider_calls: Mapped[int] = mapped_column(Integer)
    planning_max_input_tokens: Mapped[int] = mapped_column(BigInteger)
    planning_max_output_tokens: Mapped[int] = mapped_column(BigInteger)
    planning_max_cost_microunits: Mapped[int] = mapped_column(BigInteger)
    planning_cost_currency: Mapped[str] = mapped_column(String(3))
    planning_max_step_attempts: Mapped[int] = mapped_column(SmallInteger)
    planning_budget_policy_version: Mapped[str] = mapped_column(String(64))
    planning_retry_policy_version: Mapped[str] = mapped_column(String(64))
    planning_max_step_timeout_seconds: Mapped[int] = mapped_column(Integer)
    planning_max_provider_timeout_seconds: Mapped[int] = mapped_column(Integer)
    proposed_max_parallel_researchers: Mapped[int] = mapped_column(SmallInteger)
    proposed_max_step_attempts: Mapped[int] = mapped_column(SmallInteger)
    proposed_max_provider_calls: Mapped[int] = mapped_column(Integer)
    proposed_max_tool_calls: Mapped[int] = mapped_column(Integer)
    proposed_max_input_tokens: Mapped[int] = mapped_column(BigInteger)
    proposed_max_output_tokens: Mapped[int] = mapped_column(BigInteger)
    proposed_max_cost_microunits: Mapped[int] = mapped_column(BigInteger)
    proposed_cost_currency: Mapped[str] = mapped_column(String(3))
    proposed_budget_policy_version: Mapped[str] = mapped_column(String(64))
    proposed_retry_policy_version: Mapped[str] = mapped_column(String(64))
    proposed_max_run_timeout_seconds: Mapped[int] = mapped_column(Integer)
    proposed_max_step_timeout_seconds: Mapped[int] = mapped_column(Integer)
    proposed_max_provider_timeout_seconds: Mapped[int] = mapped_column(Integer)
    agent_result_schema_version: Mapped[str] = mapped_column(
        String(64),
        default="research-agent-results-v1",
        server_default="research-agent-results-v1",
    )
    context_policy_version: Mapped[str] = mapped_column(
        String(64),
        default="research-context-policy-v1",
        server_default="research-context-policy-v1",
    )
    compact_policy_version: Mapped[str] = mapped_column(
        String(64),
        default="research-compact-policy-v1",
        server_default="research-compact-policy-v1",
    )
    planning_snapshot_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResearchPlanRevisionAsset(Base):
    __tablename__ = "research_plan_revision_assets"
    __table_args__ = (
        UniqueConstraint("plan_revision_id", "asset_order", name="uq_research_plan_assets_order"),
        CheckConstraint("asset_order >= 0", name="ck_research_plan_assets_order"),
    )

    plan_revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_plan_revisions.id"), primary_key=True
    )
    asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("assets.id"), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    asset_order: Mapped[int] = mapped_column(Integer)
    asset_kind_snapshot: Mapped[str] = mapped_column(String(64))
    asset_title_snapshot: Mapped[str] = mapped_column(String(255))
    processing_generation_snapshot: Mapped[int] = mapped_column(Integer)
    index_version_snapshot: Mapped[int] = mapped_column(Integer)


class ResearchExecutionSnapshot(Base):
    __tablename__ = "research_execution_snapshots"
    __table_args__ = (
        CheckConstraint("scope_mode IN ('all_ready','selected')", name="ck_research_execution_scope"),
        CheckConstraint("retrieval_top_k > 0", name="ck_research_execution_top_k"),
        CheckConstraint("max_provider_calls > 0", name="ck_research_execution_provider_calls"),
        CheckConstraint("max_tool_calls > 0", name="ck_research_execution_tool_calls"),
        CheckConstraint("max_cost_microunits >= 0", name="ck_research_execution_cost"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_runs.id"), unique=True)
    approved_plan_revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_plan_revisions.id"), unique=True
    )
    approval_decision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("human_decisions.id", use_alter=True, name="fk_research_execution_approval_decision"),
        unique=True,
    )
    approved_plan_artifact_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_artifacts.id", use_alter=True, name="fk_research_execution_plan_artifact"),
    )
    approved_plan_artifact_sha256: Mapped[str] = mapped_column(String(64))
    input_version: Mapped[int] = mapped_column(Integer)
    question_text: Mapped[str] = mapped_column(Text)
    scope_mode: Mapped[str] = mapped_column(String(16))
    workflow_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("workflow_versions.id"))
    generation_provider: Mapped[str] = mapped_column(String(64))
    generation_model: Mapped[str] = mapped_column(String(128))
    provider_config_fingerprint: Mapped[str] = mapped_column(String(64))
    pricing_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_boundary_policy_version: Mapped[str] = mapped_column(String(64))
    embedding_provider: Mapped[str] = mapped_column(String(64))
    embedding_model: Mapped[str] = mapped_column(String(128))
    embedding_version: Mapped[str] = mapped_column(String(64))
    retrieval_strategy: Mapped[str] = mapped_column(String(32))
    retrieval_top_k: Mapped[int] = mapped_column(Integer)
    max_parallel_researchers: Mapped[int] = mapped_column(SmallInteger)
    max_step_attempts: Mapped[int] = mapped_column(SmallInteger)
    max_provider_calls: Mapped[int] = mapped_column(Integer)
    max_tool_calls: Mapped[int] = mapped_column(Integer)
    max_input_tokens: Mapped[int] = mapped_column(BigInteger)
    max_output_tokens: Mapped[int] = mapped_column(BigInteger)
    max_cost_microunits: Mapped[int] = mapped_column(BigInteger)
    cost_currency: Mapped[str] = mapped_column(String(3))
    budget_policy_version: Mapped[str] = mapped_column(String(64))
    retry_policy_version: Mapped[str] = mapped_column(String(64))
    max_run_timeout_seconds: Mapped[int] = mapped_column(Integer)
    max_step_timeout_seconds: Mapped[int] = mapped_column(Integer)
    max_provider_timeout_seconds: Mapped[int] = mapped_column(Integer)
    agent_result_schema_version: Mapped[str] = mapped_column(
        String(64),
        default="research-agent-results-v1",
        server_default="research-agent-results-v1",
    )
    context_policy_version: Mapped[str] = mapped_column(
        String(64),
        default="research-context-policy-v1",
        server_default="research-context-policy-v1",
    )
    compact_policy_version: Mapped[str] = mapped_column(
        String(64),
        default="research-compact-policy-v1",
        server_default="research-compact-policy-v1",
    )
    execution_snapshot_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResearchExecutionAsset(Base):
    __tablename__ = "research_execution_assets"
    __table_args__ = (
        UniqueConstraint("execution_snapshot_id", "asset_order", name="uq_research_execution_assets_order"),
    )

    execution_snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_execution_snapshots.id"), primary_key=True
    )
    asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("assets.id"), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    asset_order: Mapped[int] = mapped_column(Integer)
    asset_kind_snapshot: Mapped[str] = mapped_column(String(64))
    asset_title_snapshot: Mapped[str] = mapped_column(String(255))
    processing_generation_snapshot: Mapped[int] = mapped_column(Integer)
    index_version_snapshot: Mapped[int] = mapped_column(Integer)


class ResearchExecutionPromptVersion(Base):
    __tablename__ = "research_execution_prompt_versions"

    execution_snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_execution_snapshots.id"), primary_key=True
    )
    node_key: Mapped[str] = mapped_column(String(96), primary_key=True)
    prompt_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("prompt_versions.id"))
