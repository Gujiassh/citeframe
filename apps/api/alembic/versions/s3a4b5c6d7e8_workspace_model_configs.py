"""Add encrypted workspace capability overrides with durable reset revisions."""
from alembic import op
import sqlalchemy as sa

revision = "s3a4b5c6d7e8"
down_revision = "r2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workspace_model_configs",
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), primary_key=True),
        sa.Column("capability", sa.String(16), primary_key=True),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("protocol", sa.String(40)),
        sa.Column("base_url", sa.String(2048)),
        sa.Column("model", sa.String(128)),
        sa.Column("encrypted_api_key", sa.Text()),
        sa.Column("updated_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("capability IN ('generation', 'embedding')", name="ck_model_config_capability"),
        sa.CheckConstraint("mode IN ('inherit', 'override')", name="ck_model_config_mode"),
        sa.CheckConstraint("revision >= 1", name="ck_model_config_revision"),
    )


def downgrade():
    raise RuntimeError("Export encrypted workspace configuration before an explicitly approved rollback.")
