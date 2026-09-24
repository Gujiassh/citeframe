"""Persist bounded conflict investigations and install workflow v4."""

from datetime import UTC, datetime
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "r2f3a4b5c6d7"
down_revision = "q1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "research_conflict_turns",
        sa.Column(
            "step_id",
            sa.String(36),
            sa.ForeignKey("research_steps.id"),
            primary_key=True,
        ),
        sa.Column("operation_number", sa.Integer(), primary_key=True),
        sa.Column(
            "execution_snapshot_id",
            sa.String(36),
            sa.ForeignKey("research_execution_snapshots.id"),
            nullable=False,
        ),
        sa.Column(
            "created_by_attempt_id",
            sa.String(36),
            sa.ForeignKey("research_step_attempts.id"),
            nullable=False,
        ),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column(
            "request_json",
            sa.JSON().with_variant(JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("result_sha256", sa.String(64)),
        sa.Column("result_json", sa.JSON().with_variant(JSONB(), "postgresql")),
        sa.CheckConstraint(
            "operation_number >= 0 AND operation_number < 13",
            name="ck_conflict_operation_bound",
        ),
        sa.CheckConstraint(
            "status IN ('started','succeeded')", name="ck_conflict_operation_status"
        ),
        sa.CheckConstraint(
            "phase IN ('inspect','search','verify','critic','finish')",
            name="ck_conflict_operation_phase",
        ),
    )
    import hashlib
    import json
    from pathlib import Path

    data = json.loads(
        (Path(__file__).parents[1] / "release_data/research_v4.json").read_text(
            encoding="utf-8"
        )
    )
    bind = op.get_bind()
    meta = sa.MetaData()
    workflow = sa.Table("workflow_versions", meta, autoload_with=bind)
    prompt = sa.Table("prompt_versions", meta, autoload_with=bind)
    binding = sa.Table("workflow_prompt_bindings", meta, autoload_with=bind)

    def digest(value):
        return hashlib.sha256(
            json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()

    now = datetime.now(UTC)
    bind.execute(
        workflow.insert().values(
            id=data["workflowId"],
            workflow_key="evidence_research",
            version_number=4,
            availability="active",
            manifest_schema_version="2",
            manifest_json=data["manifest"],
            manifest_sha256=digest(data["manifest"]),
            created_by_release_id=data["releaseId"],
            created_at=now,
        )
    )
    for node, spec in data["prompts"].items():
        bind.execute(
            prompt.insert().values(
                id=spec["id"],
                prompt_key=spec["prompt_key"],
                version_number=4,
                step_kind=spec["step_kind"],
                availability="active",
                template_text=spec["template_text"],
                variables_schema_version="2",
                variables_schema_json=spec["variables_schema"],
                template_sha256=digest(
                    {
                        "template": spec["template_text"],
                        "variables": spec["variables_schema"],
                    }
                ),
                created_by_release_id=data["releaseId"],
                created_at=now,
            )
        )
        bind.execute(
            binding.insert().values(
                workflow_version_id=data["workflowId"],
                node_key=node,
                prompt_version_id=spec["id"],
            )
        )


def downgrade():
    raise RuntimeError("Investigation provenance requires a forward migration.")
