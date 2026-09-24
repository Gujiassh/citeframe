"""Record policy decision provenance and install immutable research v3 release."""
from datetime import UTC, datetime
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session
revision = "p0d1e2f3a4b5"
down_revision = "o9c0d1e2f3a4"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("human_decisions") as batch:
        batch.add_column(sa.Column("decision_origin", sa.String(16), nullable=False, server_default="human"))
        batch.create_check_constraint("ck_human_decisions_origin", "decision_origin IN ('human','policy')")
        batch.drop_constraint("ck_human_decisions_submitted_fields", type_="check")
        batch.create_check_constraint("ck_human_decisions_submitted_fields",
            "(status = 'submitted' AND (decided_by_user_id IS NOT NULL OR decision_origin = 'policy') AND action IS NOT NULL AND decided_at IS NOT NULL) OR status <> 'submitted'")
    from ai_pdf_api.services.research.research_versions_service import publish_research_versions_for_release
    with Session(bind=op.get_bind()) as db:
        publish_research_versions_for_release(db, datetime.now(UTC))
        db.flush()

def downgrade():
    raise RuntimeError("Research policy decisions and frozen v3 executions require a non-lossy forward migration.")
