"""add the research evaluation ledger

Revision ID: c5e7a9b1d3f6
Revises: b4d6f8a0c2e4
Create Date: 2026-07-27 19:00:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c5e7a9b1d3f6"
down_revision: str | Sequence[str] | None = "b4d6f8a0c2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EVALUATION_TABLES = (
    "research_evaluation_suites",
    "research_evaluation_runs",
    "research_evaluation_case_results",
    "research_evaluation_claim_results",
)
APPEND_ONLY_FUNCTION_NAME = "reject_research_evaluation_mutation"


def _ratio_columns(prefix: str) -> tuple[sa.Column[object], ...]:
    return (
        sa.Column(f"{prefix}_value", sa.Float(), nullable=True),
        sa.Column(f"{prefix}_sample_count", sa.Integer(), nullable=False),
        sa.Column(f"{prefix}_not_evaluable_reason", sa.String(length=128), nullable=True),
    )


def _ratio_constraints(scope: str, prefix: str) -> tuple[sa.CheckConstraint, sa.CheckConstraint]:
    return (
        sa.CheckConstraint(
            f"{prefix}_sample_count >= 0",
            name=f"ck_{scope}_{prefix}_sample_count",
        ),
        sa.CheckConstraint(
            f"(({prefix}_value IS NULL AND {prefix}_not_evaluable_reason IS NOT NULL) OR "
            f"({prefix}_value >= 0 AND {prefix}_value <= 1 AND {prefix}_sample_count > 0 "
            f"AND {prefix}_not_evaluable_reason IS NULL))",
            name=f"ck_{scope}_{prefix}_state",
        ),
    )


def append_only_install_statements() -> tuple[str, ...]:
    function = f"""
CREATE FUNCTION {APPEND_ONLY_FUNCTION_NAME}() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'research evaluation tables are append-only' USING ERRCODE = '55000';
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;
""".strip()
    triggers = tuple(
        f"CREATE TRIGGER trg_{table_name.removeprefix('research_')}_append_only "
        f"BEFORE UPDATE OR DELETE ON {table_name} FOR EACH ROW "
        f"EXECUTE FUNCTION {APPEND_ONLY_FUNCTION_NAME}()"
        for table_name in EVALUATION_TABLES
    )
    return (function, *triggers)


def append_only_remove_statements() -> tuple[str, ...]:
    triggers = tuple(
        f"DROP TRIGGER IF EXISTS trg_{table_name.removeprefix('research_')}_append_only ON {table_name}"
        for table_name in reversed(EVALUATION_TABLES)
    )
    return (*triggers, f"DROP FUNCTION IF EXISTS {APPEND_ONLY_FUNCTION_NAME}()")


def _install_append_only_guards() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for statement in append_only_install_statements():
            op.execute(sa.text(statement))


def _remove_append_only_guards() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for statement in append_only_remove_statements():
            op.execute(sa.text(statement))


def upgrade() -> None:
    op.create_table(
        "research_evaluation_suites",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("suite_key", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("fixture_manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("scorer_version", sa.String(length=128), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_research_evaluation_suites_version"),
        sa.CheckConstraint("case_count >= 0", name="ck_research_evaluation_suites_case_count"),
        sa.CheckConstraint(
            "length(fixture_manifest_sha256) = 64 AND fixture_manifest_sha256 = lower(fixture_manifest_sha256)",
            name="ck_eval_suites_fixture_sha256",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "suite_key",
            "version",
            name="uq_research_evaluation_suites_key_version",
        ),
        sa.UniqueConstraint(
            "fixture_manifest_sha256",
            "scorer_version",
            name="uq_research_evaluation_suites_fixture_scorer",
        ),
    )
    op.create_table(
        "research_evaluation_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("suite_id", sa.String(length=36), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("research_run_id", sa.String(length=36), nullable=True),
        sa.Column("baseline_evaluation_run_id", sa.String(length=36), nullable=True),
        sa.Column("fixture_manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("asset_scope_sha256", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("provider_profile_sha256", sa.String(length=64), nullable=False),
        sa.Column("scorer_version", sa.String(length=128), nullable=False),
        sa.Column("workflow_version_id", sa.String(length=36), nullable=True),
        sa.Column("prompt_binding_sha256", sa.String(length=64), nullable=True),
        sa.Column("source_report_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column("model_quality_evidence_kind", sa.String(length=24), nullable=False),
        sa.Column("user_value_evidence_ref", sa.String(length=255), nullable=True),
        sa.Column("wall_time_ms", sa.BigInteger(), nullable=True),
        sa.Column("provider_calls", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False),
        sa.Column("cost_currency", sa.String(length=3), nullable=False),
        sa.Column("cost_microunits", sa.BigInteger(), nullable=False),
        sa.Column("parallel_speedup", sa.Float(), nullable=True),
        *_ratio_columns("retry_rate"),
        *_ratio_columns("recovery_rate"),
        *_ratio_columns("claim_support_rate"),
        *_ratio_columns("evidence_recall"),
        *_ratio_columns("evidence_precision"),
        *_ratio_columns("locator_accuracy"),
        *_ratio_columns("conflict_detection_rate"),
        *_ratio_columns("refusal_correctness"),
        sa.Column("engineering_gate", sa.String(length=24), nullable=False),
        sa.Column("model_quality_gate", sa.String(length=24), nullable=False),
        sa.Column("user_value_gate", sa.String(length=24), nullable=False),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("mode IN ('quick','research')", name="ck_research_evaluation_runs_mode"),
        sa.CheckConstraint(
            "status IN ('not_evaluable','completed','failed')",
            name="ck_research_evaluation_runs_status",
        ),
        sa.CheckConstraint(
            "engineering_gate IN ('not_evaluable','pass','fail')",
            name="ck_research_evaluation_runs_engineering_gate",
        ),
        sa.CheckConstraint(
            "model_quality_gate IN ('not_evaluable','pass','fail')",
            name="ck_research_evaluation_runs_model_quality_gate",
        ),
        sa.CheckConstraint(
            "user_value_gate IN ('not_evaluable','pass','fail')",
            name="ck_research_evaluation_runs_user_value_gate",
        ),
        sa.CheckConstraint(
            "model_quality_evidence_kind IN ('scripted','provider_backed')",
            name="ck_research_evaluation_runs_quality_evidence_kind",
        ),
        sa.CheckConstraint(
            "(mode = 'quick' AND research_run_id IS NULL AND baseline_evaluation_run_id IS NULL) "
            "OR mode = 'research'",
            name="ck_research_evaluation_runs_mode_links",
        ),
        sa.CheckConstraint(
            "source_artifact_sha256 IS NULL OR (mode = 'research' AND research_run_id IS NOT NULL)",
            name="ck_eval_runs_source_artifact_link",
        ),
        sa.CheckConstraint(
            "length(fixture_manifest_sha256) = 64 AND fixture_manifest_sha256 = lower(fixture_manifest_sha256) "
            "AND length(asset_scope_sha256) = 64 AND asset_scope_sha256 = lower(asset_scope_sha256) "
            "AND length(provider_profile_sha256) = 64 AND provider_profile_sha256 = lower(provider_profile_sha256) "
            "AND length(source_report_sha256) = 64 AND source_report_sha256 = lower(source_report_sha256)",
            name="ck_eval_runs_required_sha256",
        ),
        sa.CheckConstraint(
            "(prompt_binding_sha256 IS NULL OR (length(prompt_binding_sha256) = 64 "
            "AND prompt_binding_sha256 = lower(prompt_binding_sha256))) AND "
            "(source_artifact_sha256 IS NULL OR (length(source_artifact_sha256) = 64 "
            "AND source_artifact_sha256 = lower(source_artifact_sha256)))",
            name="ck_eval_runs_optional_sha256",
        ),
        sa.CheckConstraint(
            "model_quality_evidence_kind <> 'scripted' OR model_quality_gate = 'not_evaluable'",
            name="ck_eval_runs_scripted_quality_gate",
        ),
        sa.CheckConstraint(
            "user_value_evidence_ref IS NOT NULL OR user_value_gate = 'not_evaluable'",
            name="ck_eval_runs_user_value_evidence",
        ),
        sa.CheckConstraint(
            "(failure_code IS NULL) = (failure_message IS NULL)",
            name="ck_eval_runs_failure_pair",
        ),
        sa.CheckConstraint(
            "(status = 'failed' AND failure_code IS NOT NULL AND engineering_gate = 'fail' "
            "AND model_quality_gate = 'not_evaluable' AND user_value_gate = 'not_evaluable') OR "
            "(status <> 'failed' AND failure_code IS NULL)",
            name="ck_eval_runs_failure_gate",
        ),
        sa.CheckConstraint(
            "status <> 'not_evaluable' OR (engineering_gate = 'not_evaluable' "
            "AND model_quality_gate = 'not_evaluable' AND user_value_gate = 'not_evaluable')",
            name="ck_eval_runs_not_evaluable_gates",
        ),
        sa.CheckConstraint(
            "status NOT IN ('completed','failed') OR completed_at IS NOT NULL",
            name="ck_eval_runs_terminal_completed_at",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= created_at",
            name="ck_eval_runs_completed_order",
        ),
        sa.CheckConstraint("provider_calls >= 0", name="ck_research_evaluation_runs_provider_calls"),
        sa.CheckConstraint("input_tokens >= 0", name="ck_research_evaluation_runs_input_tokens"),
        sa.CheckConstraint("output_tokens >= 0", name="ck_research_evaluation_runs_output_tokens"),
        sa.CheckConstraint("cost_microunits >= 0", name="ck_research_evaluation_runs_cost"),
        sa.CheckConstraint(
            "cost_currency = upper(cost_currency)",
            name="ck_research_evaluation_runs_currency",
        ),
        sa.CheckConstraint("wall_time_ms IS NULL OR wall_time_ms >= 0", name="ck_eval_runs_wall_time"),
        sa.CheckConstraint(
            "parallel_speedup IS NULL OR parallel_speedup >= 0",
            name="ck_eval_runs_parallel_speedup",
        ),
        *_ratio_constraints("eval_runs", "retry_rate"),
        *_ratio_constraints("eval_runs", "recovery_rate"),
        *_ratio_constraints("eval_runs", "claim_support_rate"),
        *_ratio_constraints("eval_runs", "evidence_recall"),
        *_ratio_constraints("eval_runs", "evidence_precision"),
        *_ratio_constraints("eval_runs", "locator_accuracy"),
        *_ratio_constraints("eval_runs", "conflict_detection_rate"),
        *_ratio_constraints("eval_runs", "refusal_correctness"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["suite_id"], ["research_evaluation_suites.id"]),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"]),
        sa.ForeignKeyConstraint(
            ["baseline_evaluation_run_id"],
            ["research_evaluation_runs.id"],
        ),
        sa.ForeignKeyConstraint(["workflow_version_id"], ["workflow_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "source_report_sha256",
            name="uq_research_evaluation_runs_workspace_report",
        ),
    )
    op.create_index(
        "ix_research_evaluation_runs_workspace_suite_created",
        "research_evaluation_runs",
        ["workspace_id", "suite_id", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "research_evaluation_case_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("evaluation_run_id", sa.String(length=36), nullable=False),
        sa.Column("case_key", sa.String(length=160), nullable=False),
        sa.Column("case_type", sa.String(length=96), nullable=False),
        sa.Column("expected_disposition", sa.String(length=24), nullable=False),
        sa.Column("observed_disposition", sa.String(length=24), nullable=False),
        *_ratio_columns("claim_support_rate"),
        *_ratio_columns("evidence_recall"),
        *_ratio_columns("evidence_precision"),
        *_ratio_columns("locator_accuracy"),
        *_ratio_columns("conflict_detection_rate"),
        *_ratio_columns("refusal_correctness"),
        sa.Column("wall_time_ms", sa.BigInteger(), nullable=True),
        sa.Column("provider_calls", sa.Integer(), nullable=False),
        sa.Column("cost_currency", sa.String(length=3), nullable=False),
        sa.Column("cost_microunits", sa.BigInteger(), nullable=False),
        sa.Column("unsupported_claim_count", sa.Integer(), nullable=False),
        sa.Column("human_intervention_count", sa.Integer(), nullable=False),
        sa.Column("human_wait_ms", sa.BigInteger(), nullable=False),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "expected_disposition IN ('answer','refuse','not_evaluable')",
            name="ck_research_evaluation_cases_expected_disposition",
        ),
        sa.CheckConstraint(
            "observed_disposition IN ('answer','refuse','not_evaluable')",
            name="ck_research_evaluation_cases_observed_disposition",
        ),
        sa.CheckConstraint("provider_calls >= 0", name="ck_research_evaluation_cases_provider_calls"),
        sa.CheckConstraint("cost_microunits >= 0", name="ck_research_evaluation_cases_cost"),
        sa.CheckConstraint(
            "unsupported_claim_count >= 0",
            name="ck_research_evaluation_cases_unsupported",
        ),
        sa.CheckConstraint(
            "human_intervention_count >= 0",
            name="ck_research_evaluation_cases_interventions",
        ),
        sa.CheckConstraint("human_wait_ms >= 0", name="ck_research_evaluation_cases_human_wait"),
        sa.CheckConstraint("wall_time_ms IS NULL OR wall_time_ms >= 0", name="ck_eval_cases_wall_time"),
        sa.CheckConstraint("cost_currency = upper(cost_currency)", name="ck_eval_cases_currency"),
        sa.CheckConstraint(
            "failure_code IS NULL OR failure_code IN ('conflict_missed','evidence_missing',"
            "'insufficient_evidence','locator_inaccurate','scorer_error','unsupported_claim')",
            name="ck_eval_cases_failure_code",
        ),
        *_ratio_constraints("eval_cases", "claim_support_rate"),
        *_ratio_constraints("eval_cases", "evidence_recall"),
        *_ratio_constraints("eval_cases", "evidence_precision"),
        *_ratio_constraints("eval_cases", "locator_accuracy"),
        *_ratio_constraints("eval_cases", "conflict_detection_rate"),
        *_ratio_constraints("eval_cases", "refusal_correctness"),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["research_evaluation_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evaluation_run_id",
            "case_key",
            name="uq_research_evaluation_case_results_run_key",
        ),
    )
    op.create_index(
        "ix_research_evaluation_case_results_run",
        "research_evaluation_case_results",
        ["evaluation_run_id", "case_key"],
        unique=False,
    )
    op.create_table(
        "research_evaluation_claim_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_result_id", sa.String(length=36), nullable=False),
        sa.Column("claim_key", sa.String(length=160), nullable=False),
        sa.Column("support_result", sa.String(length=24), nullable=False),
        sa.Column("locator_result", sa.String(length=24), nullable=False),
        sa.Column("conflict_result", sa.String(length=24), nullable=False),
        sa.Column("expected_evidence_count", sa.Integer(), nullable=False),
        sa.Column("observed_evidence_count", sa.Integer(), nullable=False),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "support_result IN ('supported','unsupported','not_evaluable')",
            name="ck_research_evaluation_claims_support",
        ),
        sa.CheckConstraint(
            "locator_result IN ('accurate','inaccurate','not_evaluable')",
            name="ck_research_evaluation_claims_locator",
        ),
        sa.CheckConstraint(
            "conflict_result IN ('none','detected','missed','not_evaluable')",
            name="ck_research_evaluation_claims_conflict",
        ),
        sa.CheckConstraint(
            "expected_evidence_count >= 0",
            name="ck_research_evaluation_claims_expected",
        ),
        sa.CheckConstraint(
            "observed_evidence_count >= 0",
            name="ck_research_evaluation_claims_observed",
        ),
        sa.CheckConstraint(
            "failure_code IS NULL OR failure_code IN ('conflict_missed','evidence_missing',"
            "'insufficient_evidence','locator_inaccurate','scorer_error','unsupported_claim')",
            name="ck_eval_claims_failure_code",
        ),
        sa.ForeignKeyConstraint(["case_result_id"], ["research_evaluation_case_results.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "case_result_id",
            "claim_key",
            name="uq_research_evaluation_claim_results_case_key",
        ),
    )
    _install_append_only_guards()


def downgrade() -> None:
    connection = op.get_bind()
    populated = [
        table_name
        for table_name in EVALUATION_TABLES
        if connection.execute(sa.text(f"SELECT 1 FROM {table_name} LIMIT 1")).first() is not None
    ]
    if populated:
        raise RuntimeError(
            "Refusing destructive Research Evaluation downgrade with persisted data: "
            + ", ".join(populated)
        )
    _remove_append_only_guards()
    op.drop_table("research_evaluation_claim_results")
    op.drop_index(
        "ix_research_evaluation_case_results_run",
        table_name="research_evaluation_case_results",
    )
    op.drop_table("research_evaluation_case_results")
    op.drop_index(
        "ix_research_evaluation_runs_workspace_suite_created",
        table_name="research_evaluation_runs",
    )
    op.drop_table("research_evaluation_runs")
    op.drop_table("research_evaluation_suites")
