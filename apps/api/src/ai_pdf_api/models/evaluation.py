from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ai_pdf_api.db.base import Base


def _uuid() -> str:
    return str(uuid4())


def _ratio_constraints(scope: str, prefix: str) -> tuple[CheckConstraint, CheckConstraint]:
    return (
        CheckConstraint(
            f"{prefix}_sample_count >= 0",
            name=f"ck_{scope}_{prefix}_sample_count",
        ),
        CheckConstraint(
            f"(({prefix}_value IS NULL AND {prefix}_not_evaluable_reason IS NOT NULL) OR "
            f"({prefix}_value >= 0 AND {prefix}_value <= 1 AND {prefix}_sample_count > 0 "
            f"AND {prefix}_not_evaluable_reason IS NULL))",
            name=f"ck_{scope}_{prefix}_state",
        ),
    )


class ResearchEvaluationSuite(Base):
    __tablename__ = "research_evaluation_suites"
    __table_args__ = (
        UniqueConstraint("suite_key", "version", name="uq_research_evaluation_suites_key_version"),
        UniqueConstraint(
            "fixture_manifest_sha256",
            "scorer_version",
            name="uq_research_evaluation_suites_fixture_scorer",
        ),
        CheckConstraint("version > 0", name="ck_research_evaluation_suites_version"),
        CheckConstraint("case_count >= 0", name="ck_research_evaluation_suites_case_count"),
        CheckConstraint(
            "length(fixture_manifest_sha256) = 64 AND fixture_manifest_sha256 = lower(fixture_manifest_sha256)",
            name="ck_eval_suites_fixture_sha256",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    suite_key: Mapped[str] = mapped_column(String(128))
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    fixture_manifest_sha256: Mapped[str] = mapped_column(String(64))
    scorer_version: Mapped[str] = mapped_column(String(128))
    case_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResearchEvaluationRun(Base):
    __tablename__ = "research_evaluation_runs"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "source_report_sha256",
            name="uq_research_evaluation_runs_workspace_report",
        ),
        Index(
            "ix_research_evaluation_runs_workspace_suite_created",
            "workspace_id",
            "suite_id",
            "created_at",
            "id",
        ),
        CheckConstraint("mode IN ('quick','research')", name="ck_research_evaluation_runs_mode"),
        CheckConstraint(
            "status IN ('not_evaluable','completed','failed')",
            name="ck_research_evaluation_runs_status",
        ),
        CheckConstraint(
            "engineering_gate IN ('not_evaluable','pass','fail')",
            name="ck_research_evaluation_runs_engineering_gate",
        ),
        CheckConstraint(
            "model_quality_gate IN ('not_evaluable','pass','fail')",
            name="ck_research_evaluation_runs_model_quality_gate",
        ),
        CheckConstraint(
            "user_value_gate IN ('not_evaluable','pass','fail')",
            name="ck_research_evaluation_runs_user_value_gate",
        ),
        CheckConstraint(
            "model_quality_evidence_kind IN ('scripted','provider_backed')",
            name="ck_research_evaluation_runs_quality_evidence_kind",
        ),
        CheckConstraint(
            "(mode = 'quick' AND research_run_id IS NULL AND baseline_evaluation_run_id IS NULL) OR mode = 'research'",
            name="ck_research_evaluation_runs_mode_links",
        ),
        CheckConstraint(
            "source_artifact_sha256 IS NULL OR (mode = 'research' AND research_run_id IS NOT NULL)",
            name="ck_eval_runs_source_artifact_link",
        ),
        CheckConstraint(
            "length(fixture_manifest_sha256) = 64 AND fixture_manifest_sha256 = lower(fixture_manifest_sha256) "
            "AND length(asset_scope_sha256) = 64 AND asset_scope_sha256 = lower(asset_scope_sha256) "
            "AND length(provider_profile_sha256) = 64 AND provider_profile_sha256 = lower(provider_profile_sha256) "
            "AND length(source_report_sha256) = 64 AND source_report_sha256 = lower(source_report_sha256)",
            name="ck_eval_runs_required_sha256",
        ),
        CheckConstraint(
            "(prompt_binding_sha256 IS NULL OR (length(prompt_binding_sha256) = 64 "
            "AND prompt_binding_sha256 = lower(prompt_binding_sha256))) AND "
            "(source_artifact_sha256 IS NULL OR (length(source_artifact_sha256) = 64 "
            "AND source_artifact_sha256 = lower(source_artifact_sha256)))",
            name="ck_eval_runs_optional_sha256",
        ),
        CheckConstraint(
            "model_quality_evidence_kind <> 'scripted' OR model_quality_gate = 'not_evaluable'",
            name="ck_eval_runs_scripted_quality_gate",
        ),
        CheckConstraint(
            "user_value_evidence_ref IS NOT NULL OR user_value_gate = 'not_evaluable'",
            name="ck_eval_runs_user_value_evidence",
        ),
        CheckConstraint(
            "(failure_code IS NULL) = (failure_message IS NULL)",
            name="ck_eval_runs_failure_pair",
        ),
        CheckConstraint(
            "(status = 'failed' AND failure_code IS NOT NULL AND engineering_gate = 'fail' "
            "AND model_quality_gate = 'not_evaluable' AND user_value_gate = 'not_evaluable') OR "
            "(status <> 'failed' AND failure_code IS NULL)",
            name="ck_eval_runs_failure_gate",
        ),
        CheckConstraint(
            "status <> 'not_evaluable' OR (engineering_gate = 'not_evaluable' "
            "AND model_quality_gate = 'not_evaluable' AND user_value_gate = 'not_evaluable')",
            name="ck_eval_runs_not_evaluable_gates",
        ),
        CheckConstraint(
            "status NOT IN ('completed','failed') OR completed_at IS NOT NULL",
            name="ck_eval_runs_terminal_completed_at",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= created_at",
            name="ck_eval_runs_completed_order",
        ),
        CheckConstraint("provider_calls >= 0", name="ck_research_evaluation_runs_provider_calls"),
        CheckConstraint("input_tokens >= 0", name="ck_research_evaluation_runs_input_tokens"),
        CheckConstraint("output_tokens >= 0", name="ck_research_evaluation_runs_output_tokens"),
        CheckConstraint("cost_microunits >= 0", name="ck_research_evaluation_runs_cost"),
        CheckConstraint("cost_currency = upper(cost_currency)", name="ck_research_evaluation_runs_currency"),
        CheckConstraint("wall_time_ms IS NULL OR wall_time_ms >= 0", name="ck_eval_runs_wall_time"),
        CheckConstraint(
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
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"))
    suite_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_evaluation_suites.id"))
    mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24))
    research_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_runs.id"), nullable=True
    )
    baseline_evaluation_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_evaluation_runs.id"), nullable=True
    )
    fixture_manifest_sha256: Mapped[str] = mapped_column(String(64))
    asset_scope_sha256: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    provider_profile_sha256: Mapped[str] = mapped_column(String(64))
    scorer_version: Mapped[str] = mapped_column(String(128))
    workflow_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workflow_versions.id"), nullable=True
    )
    prompt_binding_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_report_sha256: Mapped[str] = mapped_column(String(64))
    source_artifact_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_quality_evidence_kind: Mapped[str] = mapped_column(String(24))
    user_value_evidence_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    wall_time_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider_calls: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int] = mapped_column(BigInteger)
    output_tokens: Mapped[int] = mapped_column(BigInteger)
    cost_currency: Mapped[str] = mapped_column(String(3))
    cost_microunits: Mapped[int] = mapped_column(BigInteger)
    parallel_speedup: Mapped[float | None] = mapped_column(Float, nullable=True)

    retry_rate_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    retry_rate_sample_count: Mapped[int] = mapped_column(Integer)
    retry_rate_not_evaluable_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    recovery_rate_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    recovery_rate_sample_count: Mapped[int] = mapped_column(Integer)
    recovery_rate_not_evaluable_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    claim_support_rate_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    claim_support_rate_sample_count: Mapped[int] = mapped_column(Integer)
    claim_support_rate_not_evaluable_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    evidence_recall_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_recall_sample_count: Mapped[int] = mapped_column(Integer)
    evidence_recall_not_evaluable_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    evidence_precision_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_precision_sample_count: Mapped[int] = mapped_column(Integer)
    evidence_precision_not_evaluable_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    locator_accuracy_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    locator_accuracy_sample_count: Mapped[int] = mapped_column(Integer)
    locator_accuracy_not_evaluable_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    conflict_detection_rate_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    conflict_detection_rate_sample_count: Mapped[int] = mapped_column(Integer)
    conflict_detection_rate_not_evaluable_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    refusal_correctness_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    refusal_correctness_sample_count: Mapped[int] = mapped_column(Integer)
    refusal_correctness_not_evaluable_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)

    engineering_gate: Mapped[str] = mapped_column(String(24))
    model_quality_gate: Mapped[str] = mapped_column(String(24))
    user_value_gate: Mapped[str] = mapped_column(String(24))
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchEvaluationCaseResult(Base):
    __tablename__ = "research_evaluation_case_results"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_run_id",
            "case_key",
            name="uq_research_evaluation_case_results_run_key",
        ),
        Index("ix_research_evaluation_case_results_run", "evaluation_run_id", "case_key"),
        CheckConstraint(
            "expected_disposition IN ('answer','refuse','not_evaluable')",
            name="ck_research_evaluation_cases_expected_disposition",
        ),
        CheckConstraint(
            "observed_disposition IN ('answer','refuse','not_evaluable')",
            name="ck_research_evaluation_cases_observed_disposition",
        ),
        CheckConstraint("provider_calls >= 0", name="ck_research_evaluation_cases_provider_calls"),
        CheckConstraint("cost_microunits >= 0", name="ck_research_evaluation_cases_cost"),
        CheckConstraint("unsupported_claim_count >= 0", name="ck_research_evaluation_cases_unsupported"),
        CheckConstraint("human_intervention_count >= 0", name="ck_research_evaluation_cases_interventions"),
        CheckConstraint("human_wait_ms >= 0", name="ck_research_evaluation_cases_human_wait"),
        CheckConstraint("wall_time_ms IS NULL OR wall_time_ms >= 0", name="ck_eval_cases_wall_time"),
        CheckConstraint("cost_currency = upper(cost_currency)", name="ck_eval_cases_currency"),
        CheckConstraint(
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
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    evaluation_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_evaluation_runs.id")
    )
    case_key: Mapped[str] = mapped_column(String(160))
    case_type: Mapped[str] = mapped_column(String(96))
    expected_disposition: Mapped[str] = mapped_column(String(24))
    observed_disposition: Mapped[str] = mapped_column(String(24))

    claim_support_rate_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    claim_support_rate_sample_count: Mapped[int] = mapped_column(Integer)
    claim_support_rate_not_evaluable_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    evidence_recall_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_recall_sample_count: Mapped[int] = mapped_column(Integer)
    evidence_recall_not_evaluable_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    evidence_precision_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_precision_sample_count: Mapped[int] = mapped_column(Integer)
    evidence_precision_not_evaluable_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    locator_accuracy_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    locator_accuracy_sample_count: Mapped[int] = mapped_column(Integer)
    locator_accuracy_not_evaluable_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    conflict_detection_rate_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    conflict_detection_rate_sample_count: Mapped[int] = mapped_column(Integer)
    conflict_detection_rate_not_evaluable_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    refusal_correctness_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    refusal_correctness_sample_count: Mapped[int] = mapped_column(Integer)
    refusal_correctness_not_evaluable_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)

    wall_time_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider_calls: Mapped[int] = mapped_column(Integer)
    cost_currency: Mapped[str] = mapped_column(String(3))
    cost_microunits: Mapped[int] = mapped_column(BigInteger)
    unsupported_claim_count: Mapped[int] = mapped_column(Integer)
    human_intervention_count: Mapped[int] = mapped_column(Integer)
    human_wait_ms: Mapped[int] = mapped_column(BigInteger)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ResearchEvaluationClaimResult(Base):
    __tablename__ = "research_evaluation_claim_results"
    __table_args__ = (
        UniqueConstraint(
            "case_result_id",
            "claim_key",
            name="uq_research_evaluation_claim_results_case_key",
        ),
        CheckConstraint(
            "support_result IN ('supported','unsupported','not_evaluable')",
            name="ck_research_evaluation_claims_support",
        ),
        CheckConstraint(
            "locator_result IN ('accurate','inaccurate','not_evaluable')",
            name="ck_research_evaluation_claims_locator",
        ),
        CheckConstraint(
            "conflict_result IN ('none','detected','missed','not_evaluable')",
            name="ck_research_evaluation_claims_conflict",
        ),
        CheckConstraint("expected_evidence_count >= 0", name="ck_research_evaluation_claims_expected"),
        CheckConstraint("observed_evidence_count >= 0", name="ck_research_evaluation_claims_observed"),
        CheckConstraint(
            "failure_code IS NULL OR failure_code IN ('conflict_missed','evidence_missing',"
            "'insufficient_evidence','locator_inaccurate','scorer_error','unsupported_claim')",
            name="ck_eval_claims_failure_code",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_result_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_evaluation_case_results.id")
    )
    claim_key: Mapped[str] = mapped_column(String(160))
    support_result: Mapped[str] = mapped_column(String(24))
    locator_result: Mapped[str] = mapped_column(String(24))
    conflict_result: Mapped[str] = mapped_column(String(24))
    expected_evidence_count: Mapped[int] = mapped_column(Integer)
    observed_evidence_count: Mapped[int] = mapped_column(Integer)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
