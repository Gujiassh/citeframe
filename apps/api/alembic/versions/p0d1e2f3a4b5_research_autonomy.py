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
    import hashlib
    import json
    from pathlib import Path
    data = json.loads((Path(__file__).parents[1] / "release_data/research_v3.json").read_text(encoding="utf-8"))
    bind = op.get_bind()
    meta = sa.MetaData()
    workflow = sa.Table("workflow_versions", meta, autoload_with=bind)
    prompt = sa.Table("prompt_versions", meta, autoload_with=bind)
    binding = sa.Table("workflow_prompt_bindings", meta, autoload_with=bind)
    def digest(value):
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    now = datetime.now(UTC)
    bind.execute(workflow.insert().values(id=data["workflowId"], workflow_key="evidence_research",
        version_number=3, availability="active", manifest_schema_version="2",
        manifest_json=data["manifest"], manifest_sha256=digest(data["manifest"]),
        created_by_release_id=data["releaseId"], created_at=now))
    for node, spec in data["prompts"].items():
        bind.execute(prompt.insert().values(id=spec["id"], prompt_key=spec["prompt_key"],
            version_number=3, step_kind=spec["step_kind"], availability="active",
            template_text=spec["template_text"], variables_schema_version="2",
            variables_schema_json=spec["variables_schema"],
            template_sha256=digest({"template":spec["template_text"],"variables":spec["variables_schema"]}),
            created_by_release_id=data["releaseId"], created_at=now))
        bind.execute(binding.insert().values(workflow_version_id=data["workflowId"],
            node_key=node, prompt_version_id=spec["id"]))

def downgrade():
    raise RuntimeError("Research policy decisions and frozen v3 executions require a non-lossy forward migration.")
