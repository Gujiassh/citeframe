from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from citeframe_persistence.base import Base


class ResearchArtifact(Base):
    __tablename__ = "research_artifacts"
    __table_args__ = (
        UniqueConstraint("run_id", "logical_key", name="uq_research_artifacts_run_key"),
        UniqueConstraint("object_key", name="uq_research_artifacts_object_key"),
        Index("ix_research_artifacts_run_kind_created", "run_id", "artifact_kind", "created_at"),
        Index("ix_research_artifacts_retention", "workspace_id", "retention_class", "expires_at"),
        CheckConstraint(
            "artifact_kind IN ('research_plan','evidence_bundle','verification_result','conflict_report',"
            "'execution_checkpoint','final_report','trace_export')",
            name="ck_research_artifacts_kind",
        ),
        CheckConstraint("visibility IN ('user','internal')", name="ck_research_artifacts_visibility"),
        CheckConstraint(
            "retention_class IN ('workspace_lifetime','time_limited_diagnostics')",
            name="ck_research_artifacts_retention",
        ),
        CheckConstraint("byte_size >= 0", name="ck_research_artifacts_byte_size"),
        CheckConstraint(
            "(retention_class = 'time_limited_diagnostics' AND expires_at IS NOT NULL) OR "
            "(retention_class = 'workspace_lifetime' AND expires_at IS NULL)",
            name="ck_research_artifacts_expiry",
        ),
        CheckConstraint(
            "artifact_kind NOT IN ('verification_result','execution_checkpoint') OR visibility = 'internal'",
            name="ck_research_artifacts_internal_visibility",
        ),
        CheckConstraint(
            "artifact_kind <> 'final_report' OR visibility = 'user'",
            name="ck_research_artifacts_final_visibility",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_runs.id"))
    generated_by_step_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_steps.id"))
    generated_by_attempt_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_step_attempts.id"))
    artifact_kind: Mapped[str] = mapped_column(String(32))
    visibility: Mapped[str] = mapped_column(String(16))
    logical_key: Mapped[str] = mapped_column(String(160))
    schema_version: Mapped[str] = mapped_column(String(32))
    object_key: Mapped[str] = mapped_column(String(1024))
    content_type: Mapped[str] = mapped_column(String(255))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    content_sha256: Mapped[str] = mapped_column(String(64))
    workflow_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("workflow_versions.id"))
    direct_prompt_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("prompt_versions.id"), nullable=True
    )
    generation_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generation_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    supersedes_artifact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_artifacts.id"), nullable=True
    )
    retention_class: Mapped[str] = mapped_column(String(32))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResearchArtifactPromptVersion(Base):
    __tablename__ = "research_artifact_prompt_versions"

    artifact_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_artifacts.id"), primary_key=True)
    node_key: Mapped[str] = mapped_column(String(96), primary_key=True)
    prompt_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("prompt_versions.id"))


class ResearchClaim(Base):
    __tablename__ = "research_claims"
    __table_args__ = (
        UniqueConstraint("run_id", "claim_key", name="uq_research_claims_run_key"),
        UniqueConstraint("run_id", "claim_order", name="uq_research_claims_run_order"),
        CheckConstraint(
            "verification_status IN ('pending','supported','unsupported')",
            name="ck_research_claims_verification",
        ),
        CheckConstraint(
            "conflict_status IN ('none','conflicted','resolved_excluded','resolved_unresolved')",
            name="ck_research_claims_conflict",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_runs.id"))
    claim_key: Mapped[str] = mapped_column(String(160))
    claim_order: Mapped[int] = mapped_column(Integer)
    statement_text: Mapped[str] = mapped_column(Text)
    statement_sha256: Mapped[str] = mapped_column(String(64))
    produced_by_step_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_steps.id"))
    verification_status: Mapped[str] = mapped_column(String(16), default="pending")
    verified_by_step_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("research_steps.id"), nullable=True)
    verification_reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    conflict_status: Mapped[str] = mapped_column(String(24), default="none")
    critic_step_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("research_steps.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchEvidenceSnapshot(Base):
    __tablename__ = "research_evidence_snapshots"
    __table_args__ = (
        UniqueConstraint("evidence_locator_id", name="uq_research_evidence_snapshots_locator"),
        UniqueConstraint("run_id", "source_fingerprint_sha256", name="uq_research_evidence_snapshots_source"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_runs.id"))
    captured_by_step_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_steps.id"))
    evidence_locator_id: Mapped[str] = mapped_column(String(36), ForeignKey("evidence_locators.id"))
    asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("assets.id"))
    asset_kind_snapshot: Mapped[str] = mapped_column(String(64))
    asset_title_snapshot: Mapped[str] = mapped_column(String(255))
    excerpt_snapshot: Mapped[str] = mapped_column(Text)
    processing_generation_snapshot: Mapped[int] = mapped_column(Integer)
    representation_id_snapshot: Mapped[str] = mapped_column(String(36))
    parser_version_snapshot: Mapped[str] = mapped_column(String(64))
    index_version_snapshot: Mapped[int] = mapped_column(Integer)
    retrieval_channel: Mapped[str] = mapped_column(String(64))
    source_fingerprint_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResearchClaimEvidence(Base):
    __tablename__ = "research_claim_evidence"
    __table_args__ = (
        UniqueConstraint("claim_id", "evidence_order", name="uq_research_claim_evidence_order"),
        CheckConstraint("relationship IN ('supports','contradicts')", name="ck_research_claim_evidence_relation"),
    )

    claim_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_claims.id"), primary_key=True)
    evidence_snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_evidence_snapshots.id"), primary_key=True
    )
    evidence_order: Mapped[int] = mapped_column(Integer)
    relationship: Mapped[str] = mapped_column(String(16))
    assessed_by_step_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_steps.id"))


class ResearchArtifactClaim(Base):
    __tablename__ = "research_artifact_claims"
    __table_args__ = (
        UniqueConstraint("artifact_id", "claim_order", name="uq_research_artifact_claims_order"),
        CheckConstraint(
            "section_kind IN ('fact','conclusion','unresolved','conflict')",
            name="ck_research_artifact_claims_section",
        ),
    )

    artifact_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_artifacts.id"), primary_key=True)
    claim_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_claims.id"), primary_key=True)
    claim_order: Mapped[int] = mapped_column(Integer)
    section_kind: Mapped[str] = mapped_column(String(16))


class HumanDecision(Base):
    __tablename__ = "human_decisions"
    __table_args__ = (
        UniqueConstraint("gate_step_id", "request_number", name="uq_human_decisions_gate_request"),
        CheckConstraint(
            "decision_type IN ('plan_approval','conflict_resolution')", name="ck_human_decisions_type"
        ),
        CheckConstraint(
            "status IN ('pending','submitted','expired','cancelled','superseded')",
            name="ck_human_decisions_status",
        ),
        CheckConstraint(
            "action IS NULL OR action IN ('approve','request_revision','cancel_run','exclude_conflicted_claims',"
            "'keep_as_unresolved')",
            name="ck_human_decisions_action",
        ),
        CheckConstraint(
            "(status = 'submitted' AND decided_by_user_id IS NOT NULL AND action IS NOT NULL AND decided_at IS NOT NULL) "
            "OR status <> 'submitted'",
            name="ck_human_decisions_submitted_fields",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_runs.id"))
    gate_step_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_steps.id"))
    decision_type: Mapped[str] = mapped_column(String(32))
    request_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    state_version: Mapped[int] = mapped_column(BigInteger, default=1)
    input_artifact_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_artifacts.id"))
    input_artifact_sha256: Mapped[str] = mapped_column(String(64))
    input_snapshot_sha256: Mapped[str] = mapped_column(String(64))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HumanDecisionClaim(Base):
    __tablename__ = "human_decision_claims"
    __table_args__ = (
        CheckConstraint("disposition IN ('exclude','leave_unresolved')", name="ck_human_decision_claims_disposition"),
    )

    decision_id: Mapped[str] = mapped_column(String(36), ForeignKey("human_decisions.id"), primary_key=True)
    claim_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_claims.id"), primary_key=True)
    disposition: Mapped[str] = mapped_column(String(24))
