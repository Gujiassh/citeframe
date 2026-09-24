"""Add independently versioned user-edited final reports.

Revision ID: o9c0d1e2f3a4
Revises: n8b9c0d1e2f3
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "o9c0d1e2f3a4"
down_revision: str | Sequence[str] | None = "n8b9c0d1e2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_report_edits",
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("research_runs.id"), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("base_artifact_id", sa.String(length=36), sa.ForeignKey("research_artifacts.id"), nullable=False),
        sa.Column("base_artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_research_report_edits_version"),
        sa.CheckConstraint("length(markdown) > 0", name="ck_research_report_edits_markdown"),
    )


def downgrade() -> None:
    op.drop_table("research_report_edits")
