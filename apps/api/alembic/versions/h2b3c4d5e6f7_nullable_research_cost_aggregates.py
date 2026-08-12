"""allow Research cost aggregates to remain unknown when pricing is absent

Revision ID: h2b3c4d5e6f7
Revises: g1a2b3c4d5e6
Create Date: 2026-08-10
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "h2b3c4d5e6f7"
down_revision: str | Sequence[str] | None = "g1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "research_step_attempts",
        "cost_microunits",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
    op.alter_column(
        "research_budget_ledgers",
        "reserved_cost_microunits",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
    op.alter_column(
        "research_budget_ledgers",
        "actual_cost_microunits",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
    op.alter_column(
        "research_provider_calls",
        "reserved_cost_microunits",
        existing_type=sa.BigInteger(),
        nullable=True,
    )


def downgrade() -> None:
    # Historical unknown values cannot be converted back to a truthful number.
    # Refuse a lossy downgrade instead of silently writing fake zero values.
    connection = op.get_bind()
    for table, column in (
        ("research_step_attempts", "cost_microunits"),
        ("research_budget_ledgers", "reserved_cost_microunits"),
        ("research_budget_ledgers", "actual_cost_microunits"),
        ("research_provider_calls", "reserved_cost_microunits"),
    ):
        if connection.execute(sa.text(f"SELECT 1 FROM {table} WHERE {column} IS NULL LIMIT 1")).first():
            raise RuntimeError(f"cannot downgrade unknown Research cost aggregate {table}.{column}")
    op.alter_column("research_provider_calls", "reserved_cost_microunits", existing_type=sa.BigInteger(), nullable=False)
    op.alter_column("research_budget_ledgers", "actual_cost_microunits", existing_type=sa.BigInteger(), nullable=False)
    op.alter_column("research_budget_ledgers", "reserved_cost_microunits", existing_type=sa.BigInteger(), nullable=False)
    op.alter_column("research_step_attempts", "cost_microunits", existing_type=sa.BigInteger(), nullable=False)
