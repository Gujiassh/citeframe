"""Add durable final-report publication intents.

Revision ID: n8b9c0d1e2f3
Revises: m7a8b9c0d1e2
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from citeframe_persistence.models.research_versions import JSON_DOCUMENT

revision: str = "n8b9c0d1e2f3"
down_revision: str | Sequence[str] | None = "m7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _lower_hex_sha256_check(column: str) -> str:
    stripped = column
    for character in "0123456789abcdef":
        stripped = f"replace({stripped}, '{character}', '')"
    return f"length({column}) = 64 AND {column} = lower({column}) AND {stripped} = ''"


def upgrade() -> None:
    op.create_table(
        "research_publication_intents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("step_id", sa.String(length=36), nullable=False),
        sa.Column("attempt_id", sa.String(length=36), nullable=False),
        sa.Column("execution_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("logical_key", sa.String(length=160), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), nullable=False),
        sa.Column("committed_artifact_id", sa.String(length=36), nullable=True),
        sa.Column("object_prefix", sa.String(length=1024), nullable=False),
        sa.Column("current_object_generation", sa.BigInteger(), nullable=True),
        sa.Column("current_object_key", sa.String(length=1024), nullable=True),
        sa.Column("adopted_object_generation", sa.BigInteger(), nullable=True),
        sa.Column("adopted_object_key", sa.String(length=1024), nullable=True),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("render_schema_version", sa.String(length=32), nullable=False),
        sa.Column("payload_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("selection_json", JSON_DOCUMENT, nullable=False),
        sa.Column("selection_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("state_version", sa.BigInteger(), nullable=False),
        sa.Column("claim_generation", sa.BigInteger(), nullable=False),
        sa.Column("claim_owner", sa.String(length=128), nullable=True),
        sa.Column("claim_token_hash", sa.String(length=64), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_reconcile_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reconcile_attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("orphan_sweep_after", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('prepared','uploaded','committing','committed','compensating','absent')",
            name="ck_research_publication_intents_status",
        ),
        sa.CheckConstraint(
            "logical_key = 'final-report' AND content_type = 'text/markdown' "
            "AND render_schema_version = 'final-report-v1'",
            name="ck_research_publication_intents_fixed_contract",
        ),
        sa.CheckConstraint(
            "byte_size >= 0 AND byte_size <= 16777216 AND byte_size = length(payload_bytes)",
            name="ck_research_publication_intents_payload_size",
        ),
        sa.CheckConstraint("state_version >= 1", name="ck_research_publication_intents_state_version"),
        sa.CheckConstraint("claim_generation >= 0", name="ck_research_publication_intents_claim_generation"),
        sa.CheckConstraint(
            "reconcile_attempt_count >= 0",
            name="ck_research_publication_intents_reconcile_attempts",
        ),
        sa.CheckConstraint(
            f"{_lower_hex_sha256_check('content_sha256')} AND "
            f"{_lower_hex_sha256_check('selection_sha256')}",
            name="ck_research_publication_intents_hashes",
        ),
        sa.CheckConstraint(
            "(claim_owner IS NULL AND claim_token_hash IS NULL AND claim_expires_at IS NULL "
            "AND claim_heartbeat_at IS NULL) OR "
            "(claim_owner IS NOT NULL AND claim_token_hash IS NOT NULL "
            "AND claim_expires_at IS NOT NULL AND claim_heartbeat_at IS NOT NULL)",
            name="ck_research_publication_intents_claim_group",
        ),
        sa.CheckConstraint(
            "((status IN ('committed','absent')) AND resolved_at IS NOT NULL) OR "
            "((status NOT IN ('committed','absent')) AND resolved_at IS NULL)",
            name="ck_research_publication_intents_resolution",
        ),
        sa.CheckConstraint(
            "status NOT IN ('committed','absent') OR "
            "(claim_owner IS NULL AND claim_token_hash IS NULL AND claim_expires_at IS NULL "
            "AND claim_heartbeat_at IS NULL)",
            name="ck_research_publication_intents_terminal_claim",
        ),
        sa.CheckConstraint(
            "(status = 'committed' AND committed_artifact_id IS NOT NULL "
            "AND committed_artifact_id = artifact_id AND adopted_object_generation IS NOT NULL "
            "AND adopted_object_key IS NOT NULL) OR "
            "(status <> 'committed' AND committed_artifact_id IS NULL "
            "AND adopted_object_generation IS NULL AND adopted_object_key IS NULL)",
            name="ck_research_publication_intents_committed_fields",
        ),
        sa.CheckConstraint(
            "(current_object_generation IS NULL) = (current_object_key IS NULL)",
            name="ck_research_publication_intents_current_pair",
        ),
        sa.CheckConstraint(
            "current_object_generation IS NULL OR current_object_generation > 0",
            name="ck_research_publication_intents_current_generation",
        ),
        sa.CheckConstraint(
            "adopted_object_generation IS NULL OR adopted_object_generation > 0",
            name="ck_research_publication_intents_adopted_generation",
        ),
        sa.CheckConstraint(
            "status NOT IN ('uploaded','committing') OR "
            "(claim_owner IS NOT NULL AND current_object_generation IS NOT NULL "
            "AND current_object_generation = claim_generation)",
            name="ck_research_publication_intents_uploaded_claim",
        ),
        sa.CheckConstraint(
            "status <> 'prepared' OR "
            "((claim_owner IS NULL AND current_object_generation IS NULL) OR "
            "(claim_owner IS NOT NULL AND current_object_generation = claim_generation))",
            name="ck_research_publication_intents_prepared_claim",
        ),
        sa.CheckConstraint(
            "status NOT IN ('compensating','committed','absent') OR current_object_generation IS NULL",
            name="ck_research_publication_intents_no_terminal_current",
        ),
        sa.CheckConstraint(
            "status NOT IN ('committed','absent') OR orphan_sweep_after IS NOT NULL",
            name="ck_research_publication_intents_terminal_sweep",
        ),
        sa.ForeignKeyConstraint(["attempt_id"], ["research_step_attempts.id"]),
        sa.ForeignKeyConstraint(
            ["committed_artifact_id"],
            ["research_artifacts.id"],
            name="fk_research_publication_intents_committed_artifact",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(["execution_snapshot_id"], ["research_execution_snapshots.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"]),
        sa.ForeignKeyConstraint(["step_id"], ["research_steps.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_id"),
        sa.UniqueConstraint("attempt_id"),
        sa.UniqueConstraint("committed_artifact_id"),
        sa.UniqueConstraint("current_object_key"),
        sa.UniqueConstraint("adopted_object_key"),
        sa.UniqueConstraint("object_prefix"),
    )
    op.create_index(
        "ix_research_publication_intents_run",
        "research_publication_intents",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_research_publication_intents_schedule",
        "research_publication_intents",
        ["status", "next_reconcile_at", "claim_expires_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_research_publication_intents_step",
        "research_publication_intents",
        ["step_id"],
        unique=False,
    )
    op.create_index(
        "uq_research_publication_intents_active_run_key",
        "research_publication_intents",
        ["run_id", "logical_key"],
        unique=True,
        postgresql_where=sa.text("status <> 'absent'"),
        sqlite_where=sa.text("status <> 'absent'"),
    )


def downgrade() -> None:
    row_count = op.get_bind().execute(
        sa.text("SELECT count(*) FROM research_publication_intents")
    ).scalar_one()
    if row_count:
        raise RuntimeError(
            "Refusing destructive publication-intent downgrade while durable rows exist; "
            "first verify every intent is terminal, preserve required history, and confirm "
            "the corresponding generation object prefixes satisfy the rollback runbook."
        )
    op.drop_index(
        "uq_research_publication_intents_active_run_key",
        table_name="research_publication_intents",
    )
    op.drop_index("ix_research_publication_intents_step", table_name="research_publication_intents")
    op.drop_index("ix_research_publication_intents_schedule", table_name="research_publication_intents")
    op.drop_index("ix_research_publication_intents_run", table_name="research_publication_intents")
    op.drop_table("research_publication_intents")
