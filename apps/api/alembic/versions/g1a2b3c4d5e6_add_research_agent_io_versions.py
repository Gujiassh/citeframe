"""add Research agent I/O and context/compact policy versions

Revision ID: g1a2b3c4d5e6
Revises: f9a1b2c3d4e5
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "g1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "f9a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_AGENT = "research-agent-results-legacy-v0"
LEGACY_CONTEXT = "research-context-policy-legacy-v0"
LEGACY_COMPACT = "research-compact-policy-legacy-v0"
CURRENT_AGENT = "research-agent-results-v1"
CURRENT_CONTEXT = "research-context-policy-v1"
CURRENT_COMPACT = "research-compact-policy-v1"


def upgrade() -> None:
    op.add_column(
        "research_plan_revisions",
        sa.Column("agent_result_schema_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "research_plan_revisions",
        sa.Column("context_policy_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "research_plan_revisions",
        sa.Column("compact_policy_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "research_execution_snapshots",
        sa.Column("agent_result_schema_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "research_execution_snapshots",
        sa.Column("context_policy_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "research_execution_snapshots",
        sa.Column("compact_policy_version", sa.String(length=64), nullable=True),
    )

    # Historical rows without the new fields become an explicit legacy registry entry.
    op.execute(
        sa.text(
            """
            UPDATE research_plan_revisions
            SET agent_result_schema_version = :agent,
                context_policy_version = :context,
                compact_policy_version = :compact
            WHERE agent_result_schema_version IS NULL
               OR context_policy_version IS NULL
               OR compact_policy_version IS NULL
            """
        ).bindparams(agent=LEGACY_AGENT, context=LEGACY_CONTEXT, compact=LEGACY_COMPACT)
    )
    op.execute(
        sa.text(
            """
            UPDATE research_execution_snapshots
            SET agent_result_schema_version = :agent,
                context_policy_version = :context,
                compact_policy_version = :compact
            WHERE agent_result_schema_version IS NULL
               OR context_policy_version IS NULL
               OR compact_policy_version IS NULL
            """
        ).bindparams(agent=LEGACY_AGENT, context=LEGACY_CONTEXT, compact=LEGACY_COMPACT)
    )

    op.alter_column(
        "research_plan_revisions",
        "agent_result_schema_version",
        existing_type=sa.String(length=64),
        nullable=False,
        server_default=CURRENT_AGENT,
    )
    op.alter_column(
        "research_plan_revisions",
        "context_policy_version",
        existing_type=sa.String(length=64),
        nullable=False,
        server_default=CURRENT_CONTEXT,
    )
    op.alter_column(
        "research_plan_revisions",
        "compact_policy_version",
        existing_type=sa.String(length=64),
        nullable=False,
        server_default=CURRENT_COMPACT,
    )
    op.alter_column(
        "research_execution_snapshots",
        "agent_result_schema_version",
        existing_type=sa.String(length=64),
        nullable=False,
        server_default=CURRENT_AGENT,
    )
    op.alter_column(
        "research_execution_snapshots",
        "context_policy_version",
        existing_type=sa.String(length=64),
        nullable=False,
        server_default=CURRENT_CONTEXT,
    )
    op.alter_column(
        "research_execution_snapshots",
        "compact_policy_version",
        existing_type=sa.String(length=64),
        nullable=False,
        server_default=CURRENT_COMPACT,
    )


def downgrade() -> None:
    op.drop_column("research_execution_snapshots", "compact_policy_version")
    op.drop_column("research_execution_snapshots", "context_policy_version")
    op.drop_column("research_execution_snapshots", "agent_result_schema_version")
    op.drop_column("research_plan_revisions", "compact_policy_version")
    op.drop_column("research_plan_revisions", "context_policy_version")
    op.drop_column("research_plan_revisions", "agent_result_schema_version")
