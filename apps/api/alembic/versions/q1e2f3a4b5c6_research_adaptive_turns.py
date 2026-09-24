"""Persist bounded adaptive model turns independently of attempt retries."""
from alembic import op
import sqlalchemy as sa
from citeframe_persistence.models.research_versions import JSON_DOCUMENT

revision = "q1e2f3a4b5c6"
down_revision = "p0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("research_adaptive_turns",
        sa.Column("step_id", sa.String(36), sa.ForeignKey("research_steps.id"), primary_key=True),
        sa.Column("turn_number", sa.Integer(), primary_key=True),
        sa.Column("execution_snapshot_id", sa.String(36), sa.ForeignKey("research_execution_snapshots.id"), nullable=False),
        sa.Column("created_by_attempt_id", sa.String(36), sa.ForeignKey("research_step_attempts.id"), nullable=False),
        sa.Column("query", sa.String(4000), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("result_sha256", sa.String(64), nullable=False),
        sa.Column("result_json", JSON_DOCUMENT, nullable=False),
        sa.CheckConstraint("turn_number >= 0 AND turn_number <= 2", name="ck_research_adaptive_turn_bound"))


def downgrade():
    raise RuntimeError("Adaptive checkpoints cannot be dropped while frozen v3 runs can resume.")
