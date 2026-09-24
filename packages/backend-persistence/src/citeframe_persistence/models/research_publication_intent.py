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
    LargeBinary,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from citeframe_persistence.base import Base
from citeframe_persistence.models.research_versions import JSON_DOCUMENT

PUBLICATION_INTENT_STATUSES = (
    "prepared",
    "uploaded",
    "committing",
    "committed",
    "compensating",
    "absent",
)


def _lower_hex_sha256_check(column: str) -> str:
    stripped = column
    for character in "0123456789abcdef":
        stripped = f"replace({stripped}, '{character}', '')"
    return f"length({column}) = 64 AND {column} = lower({column}) AND {stripped} = ''"


class ResearchPublicationIntent(Base):
    """Durable owner for one final-report publication saga.

    The frozen payload is deliberately internal.  A reconciler may resume after the
    publishing process exits without rendering again or depending on mutable Claim rows.
    """

    __tablename__ = "research_publication_intents"
    __table_args__ = (
        Index(
            "uq_research_publication_intents_active_run_key",
            "run_id",
            "logical_key",
            unique=True,
            postgresql_where=text("status <> 'absent'"),
            sqlite_where=text("status <> 'absent'"),
        ),
        Index(
            "ix_research_publication_intents_schedule",
            "status",
            "next_reconcile_at",
            "claim_expires_at",
            "id",
        ),
        Index("ix_research_publication_intents_run", "run_id"),
        Index("ix_research_publication_intents_step", "step_id"),
        CheckConstraint(
            "status IN ('prepared','uploaded','committing','committed','compensating','absent')",
            name="ck_research_publication_intents_status",
        ),
        CheckConstraint(
            "logical_key = 'final-report' AND content_type = 'text/markdown' "
            "AND render_schema_version = 'final-report-v1'",
            name="ck_research_publication_intents_fixed_contract",
        ),
        CheckConstraint(
            "byte_size >= 0 AND byte_size <= 16777216 AND byte_size = length(payload_bytes)",
            name="ck_research_publication_intents_payload_size",
        ),
        CheckConstraint("state_version >= 1", name="ck_research_publication_intents_state_version"),
        CheckConstraint("claim_generation >= 0", name="ck_research_publication_intents_claim_generation"),
        CheckConstraint(
            "reconcile_attempt_count >= 0",
            name="ck_research_publication_intents_reconcile_attempts",
        ),
        CheckConstraint(
            f"{_lower_hex_sha256_check('content_sha256')} AND "
            f"{_lower_hex_sha256_check('selection_sha256')}",
            name="ck_research_publication_intents_hashes",
        ),
        CheckConstraint(
            "(claim_owner IS NULL AND claim_token_hash IS NULL AND claim_expires_at IS NULL "
            "AND claim_heartbeat_at IS NULL) OR "
            "(claim_owner IS NOT NULL AND claim_token_hash IS NOT NULL "
            "AND claim_expires_at IS NOT NULL AND claim_heartbeat_at IS NOT NULL)",
            name="ck_research_publication_intents_claim_group",
        ),
        CheckConstraint(
            "((status IN ('committed','absent')) AND resolved_at IS NOT NULL) OR "
            "((status NOT IN ('committed','absent')) AND resolved_at IS NULL)",
            name="ck_research_publication_intents_resolution",
        ),
        CheckConstraint(
            "status NOT IN ('committed','absent') OR "
            "(claim_owner IS NULL AND claim_token_hash IS NULL AND claim_expires_at IS NULL "
            "AND claim_heartbeat_at IS NULL)",
            name="ck_research_publication_intents_terminal_claim",
        ),
        CheckConstraint(
            "(status = 'committed' AND committed_artifact_id IS NOT NULL "
            "AND committed_artifact_id = artifact_id AND adopted_object_generation IS NOT NULL "
            "AND adopted_object_key IS NOT NULL) OR "
            "(status <> 'committed' AND committed_artifact_id IS NULL "
            "AND adopted_object_generation IS NULL AND adopted_object_key IS NULL)",
            name="ck_research_publication_intents_committed_fields",
        ),
        CheckConstraint(
            "(current_object_generation IS NULL) = (current_object_key IS NULL)",
            name="ck_research_publication_intents_current_pair",
        ),
        CheckConstraint(
            "current_object_generation IS NULL OR current_object_generation > 0",
            name="ck_research_publication_intents_current_generation",
        ),
        CheckConstraint(
            "adopted_object_generation IS NULL OR adopted_object_generation > 0",
            name="ck_research_publication_intents_adopted_generation",
        ),
        CheckConstraint(
            "status NOT IN ('uploaded','committing') OR "
            "(claim_owner IS NOT NULL AND current_object_generation IS NOT NULL "
            "AND current_object_generation = claim_generation)",
            name="ck_research_publication_intents_uploaded_claim",
        ),
        CheckConstraint(
            "status <> 'prepared' OR "
            "((claim_owner IS NULL AND current_object_generation IS NULL) OR "
            "(claim_owner IS NOT NULL AND current_object_generation = claim_generation))",
            name="ck_research_publication_intents_prepared_claim",
        ),
        CheckConstraint(
            "status NOT IN ('compensating','committed','absent') OR current_object_generation IS NULL",
            name="ck_research_publication_intents_no_terminal_current",
        ),
        CheckConstraint(
            "status NOT IN ('committed','absent') OR orphan_sweep_after IS NOT NULL",
            name="ck_research_publication_intents_terminal_sweep",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_runs.id"))
    step_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_steps.id"))
    attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_step_attempts.id"), unique=True
    )
    execution_snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_execution_snapshots.id")
    )
    logical_key: Mapped[str] = mapped_column(String(160), default="final-report")
    artifact_id: Mapped[str] = mapped_column(String(36), unique=True)
    committed_artifact_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "research_artifacts.id",
            use_alter=True,
            name="fk_research_publication_intents_committed_artifact",
            deferrable=True,
            initially="DEFERRED",
        ),
        unique=True,
        nullable=True,
    )
    object_prefix: Mapped[str] = mapped_column(String(1024), unique=True)
    current_object_generation: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    current_object_key: Mapped[str | None] = mapped_column(String(1024), unique=True, nullable=True)
    adopted_object_generation: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    adopted_object_key: Mapped[str | None] = mapped_column(String(1024), unique=True, nullable=True)
    content_type: Mapped[str] = mapped_column(String(255), default="text/markdown")
    render_schema_version: Mapped[str] = mapped_column(String(32), default="final-report-v1")
    payload_bytes: Mapped[bytes] = mapped_column(LargeBinary)
    byte_size: Mapped[int] = mapped_column(BigInteger)
    content_sha256: Mapped[str] = mapped_column(String(64))
    selection_json: Mapped[dict[str, object]] = mapped_column(JSON_DOCUMENT)
    selection_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="prepared")
    state_version: Mapped[int] = mapped_column(BigInteger, default=1)
    claim_generation: Mapped[int] = mapped_column(BigInteger, default=0)
    claim_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    claim_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_reconcile_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reconcile_attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    orphan_sweep_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
