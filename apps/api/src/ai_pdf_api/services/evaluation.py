from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ai_pdf_api.models.evaluation import (
    ResearchEvaluationCaseResult,
    ResearchEvaluationClaimResult,
    ResearchEvaluationRun,
    ResearchEvaluationSuite,
)
from ai_pdf_api.models.research_artifact import ResearchArtifact
from ai_pdf_api.models.research_run import ResearchRun
from ai_pdf_api.models.research_versions import WorkflowVersion
from ai_pdf_api.models.workspace import Workspace
from ai_pdf_api.schemas.evaluation import (
    EvaluationCaseImport,
    EvaluationClaimImport,
    EvaluationImportReport,
    EvaluationRunImport,
    RatioMetric,
)


class EvaluationImportError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class EvaluationReadError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class EvaluationImportResult:
    evaluation_run_id: str
    source_report_sha256: str
    created: bool


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvaluationImportError("invalid_evaluation_report", f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise EvaluationImportError("invalid_evaluation_report", f"Invalid JSON number: {value}")


def canonical_evaluation_report_bytes(document: dict[str, Any] | BaseModel) -> bytes:
    if isinstance(document, BaseModel):
        value = document.model_dump(mode="json", by_alias=True)
    else:
        value = document
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise EvaluationImportError("invalid_evaluation_report", "Report cannot be encoded as canonical JSON.") from error


def parse_evaluation_report(report_bytes: bytes) -> EvaluationImportReport:
    try:
        decoded = report_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise EvaluationImportError("invalid_evaluation_report", "Report must be UTF-8 JSON.") from error
    try:
        document = json.loads(
            decoded,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except EvaluationImportError:
        raise
    except json.JSONDecodeError as error:
        raise EvaluationImportError("invalid_evaluation_report", "Report must contain valid JSON.") from error
    if not isinstance(document, dict):
        raise EvaluationImportError("invalid_evaluation_report", "Report root must be an object.")
    if canonical_evaluation_report_bytes(document) != report_bytes:
        raise EvaluationImportError(
            "noncanonical_evaluation_report",
            "Report bytes must use canonical UTF-8 JSON with sorted keys and no insignificant whitespace.",
        )
    try:
        return EvaluationImportReport.model_validate(document)
    except ValidationError as error:
        first = error.errors()[0] if error.errors() else {}
        path = ".".join(str(part) for part in first.get("loc", ()))
        suffix = f" at {path}" if path else ""
        raise EvaluationImportError(
            "invalid_evaluation_report",
            f"Report schema validation failed{suffix}.",
        ) from error


def _ratio_columns(prefix: str, metric: RatioMetric) -> dict[str, object]:
    return {
        f"{prefix}_value": metric.value,
        f"{prefix}_sample_count": metric.sample_count,
        f"{prefix}_not_evaluable_reason": metric.not_evaluable_reason,
    }


def _suite_for_import(db: Session, report: EvaluationImportReport) -> ResearchEvaluationSuite:
    imported = report.suite
    suite = db.scalar(
        select(ResearchEvaluationSuite).where(
            ResearchEvaluationSuite.suite_key == imported.suite_key,
            ResearchEvaluationSuite.version == imported.version,
        )
    )
    hash_owner = db.scalar(
        select(ResearchEvaluationSuite).where(
            ResearchEvaluationSuite.fixture_manifest_sha256 == imported.fixture_manifest_sha256,
            ResearchEvaluationSuite.scorer_version == imported.scorer_version,
        )
    )
    if suite is None:
        if hash_owner is not None:
            raise EvaluationImportError(
                "evaluation_suite_conflict",
                "Fixture/scorer identity is already bound to another immutable suite version.",
            )
        suite = ResearchEvaluationSuite(
            id=str(uuid4()),
            suite_key=imported.suite_key,
            version=imported.version,
            title=imported.title,
            fixture_manifest_sha256=imported.fixture_manifest_sha256,
            scorer_version=imported.scorer_version,
            case_count=imported.case_count,
            created_at=datetime.now(UTC),
        )
        db.add(suite)
        return suite
    expected = (
        imported.title,
        imported.fixture_manifest_sha256,
        imported.scorer_version,
        imported.case_count,
    )
    actual = (suite.title, suite.fixture_manifest_sha256, suite.scorer_version, suite.case_count)
    if actual != expected or (hash_owner is not None and hash_owner.id != suite.id):
        raise EvaluationImportError(
            "evaluation_suite_conflict",
            "Suite key/version is immutable and does not match the imported definition.",
        )
    return suite


def _validate_research_and_artifact(
    db: Session,
    *,
    workspace_id: str,
    evaluation: EvaluationRunImport,
) -> None:
    if (
        evaluation.workflow_version_id is not None
        and db.get(WorkflowVersion, evaluation.workflow_version_id) is None
    ):
        raise EvaluationImportError(
            "evaluation_workflow_version_not_found",
            "Workflow version does not exist.",
        )
    if evaluation.research_run_id is None:
        return
    research_run = db.scalar(
        select(ResearchRun).where(
            ResearchRun.id == evaluation.research_run_id,
            ResearchRun.workspace_id == workspace_id,
        )
    )
    if research_run is None:
        raise EvaluationImportError(
            "evaluation_research_run_not_found",
            "Research run does not belong to the import Workspace.",
        )
    source = evaluation.source_artifact
    if source is None:
        return
    artifact = db.scalar(
        select(ResearchArtifact).where(
            ResearchArtifact.id == source.artifact_id,
            ResearchArtifact.workspace_id == workspace_id,
            ResearchArtifact.run_id == research_run.id,
        )
    )
    if artifact is None or artifact.content_sha256 != source.sha256:
        raise EvaluationImportError(
            "evaluation_source_artifact_mismatch",
            "Source Artifact identity or content hash does not match the Research run.",
        )


def _validate_baseline(
    db: Session,
    *,
    workspace_id: str,
    suite_id: str,
    evaluation: EvaluationRunImport,
    cases: list[EvaluationCaseImport],
) -> None:
    baseline_id = evaluation.baseline_evaluation_run_id
    if baseline_id is None:
        return
    if evaluation.mode != "research":
        raise EvaluationImportError("evaluation_pair_mismatch", "Only Research evaluations can name a baseline.")
    baseline = db.scalar(
        select(ResearchEvaluationRun).where(
            ResearchEvaluationRun.id == baseline_id,
            ResearchEvaluationRun.workspace_id == workspace_id,
            ResearchEvaluationRun.mode == "quick",
        )
    )
    if baseline is None:
        raise EvaluationImportError(
            "evaluation_pair_mismatch",
            "Baseline must be an existing Quick evaluation in the same Workspace.",
        )
    comparison = (
        baseline.suite_id,
        baseline.fixture_manifest_sha256,
        baseline.asset_scope_sha256,
        baseline.provider,
        baseline.model,
        baseline.provider_profile_sha256,
        baseline.scorer_version,
    )
    expected = (
        suite_id,
        evaluation.fixture_manifest_sha256,
        evaluation.asset_scope_sha256,
        evaluation.provider,
        evaluation.model,
        evaluation.provider_profile_sha256,
        evaluation.scorer_version,
    )
    if comparison != expected:
        raise EvaluationImportError(
            "evaluation_pair_mismatch",
            "Quick and Research comparison keys do not match.",
        )
    baseline_case_keys = set(
        db.scalars(
            select(ResearchEvaluationCaseResult.case_key).where(
                ResearchEvaluationCaseResult.evaluation_run_id == baseline.id
            )
        ).all()
    )
    if baseline_case_keys != {case.case_key for case in cases}:
        raise EvaluationImportError(
            "evaluation_pair_mismatch",
            "Quick and Research case sets do not match.",
        )


def _run_from_import(
    *,
    run_id: str,
    workspace_id: str,
    suite_id: str,
    source_report_sha256: str,
    evaluation: EvaluationRunImport,
) -> ResearchEvaluationRun:
    values: dict[str, object] = {
        "id": run_id,
        "workspace_id": workspace_id,
        "suite_id": suite_id,
        "mode": evaluation.mode,
        "status": evaluation.status,
        "research_run_id": evaluation.research_run_id,
        "baseline_evaluation_run_id": evaluation.baseline_evaluation_run_id,
        "fixture_manifest_sha256": evaluation.fixture_manifest_sha256,
        "asset_scope_sha256": evaluation.asset_scope_sha256,
        "provider": evaluation.provider,
        "model": evaluation.model,
        "provider_profile_sha256": evaluation.provider_profile_sha256,
        "scorer_version": evaluation.scorer_version,
        "workflow_version_id": evaluation.workflow_version_id,
        "prompt_binding_sha256": evaluation.prompt_binding_sha256,
        "source_report_sha256": source_report_sha256,
        "source_artifact_sha256": (
            evaluation.source_artifact.sha256 if evaluation.source_artifact is not None else None
        ),
        "model_quality_evidence_kind": evaluation.model_quality_evidence_kind,
        "user_value_evidence_ref": evaluation.user_value_evidence_ref,
        "wall_time_ms": evaluation.wall_time_ms,
        "provider_calls": evaluation.provider_calls,
        "input_tokens": evaluation.input_tokens,
        "output_tokens": evaluation.output_tokens,
        "cost_currency": evaluation.cost.currency,
        "cost_microunits": evaluation.cost.amount_micros,
        "parallel_speedup": evaluation.parallel_speedup,
        "engineering_gate": evaluation.engineering_gate,
        "model_quality_gate": evaluation.model_quality_gate,
        "user_value_gate": evaluation.user_value_gate,
        "failure_code": evaluation.failure.code if evaluation.failure is not None else None,
        "failure_message": evaluation.failure.message if evaluation.failure is not None else None,
        "created_at": evaluation.created_at,
        "completed_at": evaluation.completed_at,
    }
    for name in (
        "retry_rate",
        "recovery_rate",
        "claim_support_rate",
        "evidence_recall",
        "evidence_precision",
        "locator_accuracy",
        "conflict_detection_rate",
        "refusal_correctness",
    ):
        values.update(_ratio_columns(name, getattr(evaluation, name)))
    return ResearchEvaluationRun(**values)


def _case_from_import(*, case_id: str, run_id: str, imported: EvaluationCaseImport) -> ResearchEvaluationCaseResult:
    values: dict[str, object] = {
        "id": case_id,
        "evaluation_run_id": run_id,
        "case_key": imported.case_key,
        "case_type": imported.case_type,
        "expected_disposition": imported.expected_disposition,
        "observed_disposition": imported.observed_disposition,
        "wall_time_ms": imported.wall_time_ms,
        "provider_calls": imported.provider_calls,
        "cost_currency": imported.cost.currency,
        "cost_microunits": imported.cost.amount_micros,
        "unsupported_claim_count": imported.unsupported_claim_count,
        "human_intervention_count": imported.human_intervention_count,
        "human_wait_ms": imported.human_wait_ms,
        "failure_code": imported.failure_code,
    }
    for name in (
        "claim_support_rate",
        "evidence_recall",
        "evidence_precision",
        "locator_accuracy",
        "conflict_detection_rate",
        "refusal_correctness",
    ):
        values.update(_ratio_columns(name, getattr(imported, name)))
    return ResearchEvaluationCaseResult(**values)


def _claim_from_import(*, case_id: str, imported: EvaluationClaimImport) -> ResearchEvaluationClaimResult:
    return ResearchEvaluationClaimResult(
        id=str(uuid4()),
        case_result_id=case_id,
        claim_key=imported.claim_key,
        support_result=imported.support_result,
        locator_result=imported.locator_result,
        conflict_result=imported.conflict_result,
        expected_evidence_count=imported.expected_evidence_count,
        observed_evidence_count=imported.observed_evidence_count,
        failure_code=imported.failure_code,
    )


def _existing_import(
    db: Session,
    *,
    workspace_id: str,
    source_report_sha256: str,
) -> ResearchEvaluationRun | None:
    return db.scalar(
        select(ResearchEvaluationRun).where(
            ResearchEvaluationRun.workspace_id == workspace_id,
            ResearchEvaluationRun.source_report_sha256 == source_report_sha256,
        )
    )


def _import_evaluation_graph(
    db: Session,
    *,
    workspace_id: str,
    source_report_sha256: str,
    report: EvaluationImportReport,
) -> EvaluationImportResult:
    if db.get(Workspace, workspace_id) is None:
        raise EvaluationImportError("evaluation_workspace_not_found", "Import Workspace does not exist.")
    existing = _existing_import(
        db,
        workspace_id=workspace_id,
        source_report_sha256=source_report_sha256,
    )
    if existing is not None:
        return EvaluationImportResult(existing.id, source_report_sha256, False)
    suite = _suite_for_import(db, report)
    _validate_research_and_artifact(db, workspace_id=workspace_id, evaluation=report.evaluation)
    _validate_baseline(
        db,
        workspace_id=workspace_id,
        suite_id=suite.id,
        evaluation=report.evaluation,
        cases=report.cases,
    )
    run_id = str(uuid4())
    db.flush([suite])
    run = _run_from_import(
        run_id=run_id,
        workspace_id=workspace_id,
        suite_id=suite.id,
        source_report_sha256=source_report_sha256,
        evaluation=report.evaluation,
    )
    db.add(run)
    db.flush([run])
    case_rows: list[ResearchEvaluationCaseResult] = []
    claim_rows: list[ResearchEvaluationClaimResult] = []
    for imported_case in report.cases:
        case_id = str(uuid4())
        case_rows.append(_case_from_import(case_id=case_id, run_id=run_id, imported=imported_case))
        claim_rows.extend(
            _claim_from_import(case_id=case_id, imported=claim) for claim in imported_case.claims
        )
    if case_rows:
        db.add_all(case_rows)
        db.flush(case_rows)
    if claim_rows:
        db.add_all(claim_rows)
        db.flush(claim_rows)
    return EvaluationImportResult(run_id, source_report_sha256, True)


def import_evaluation_report(
    db: Session,
    *,
    workspace_id: str,
    report_bytes: bytes,
) -> EvaluationImportResult:
    report = parse_evaluation_report(report_bytes)
    source_report_sha256 = hashlib.sha256(report_bytes).hexdigest()
    if db.new or db.dirty or db.deleted:
        raise EvaluationImportError(
            "evaluation_import_session_not_clean",
            "Evaluation import requires a clean transaction boundary.",
        )
    try:
        with db.begin_nested():
            return _import_evaluation_graph(
                db,
                workspace_id=workspace_id,
                source_report_sha256=source_report_sha256,
                report=report,
            )
    except IntegrityError:
        # PostgreSQL's default READ COMMITTED isolation exposes the winner after the
        # unique-key wait completes and the savepoint rolls back the losing insert.
        existing = _existing_import(
            db,
            workspace_id=workspace_id,
            source_report_sha256=source_report_sha256,
        )
        if existing is not None:
            return EvaluationImportResult(existing.id, source_report_sha256, False)
        try:
            # A different report can lose the first immutable-suite insert race. One
            # bounded retry reuses the committed suite while preserving append-only runs.
            with db.begin_nested():
                return _import_evaluation_graph(
                    db,
                    workspace_id=workspace_id,
                    source_report_sha256=source_report_sha256,
                    report=report,
                )
        except IntegrityError as retry_error:
            existing = _existing_import(
                db,
                workspace_id=workspace_id,
                source_report_sha256=source_report_sha256,
            )
            if existing is not None:
                return EvaluationImportResult(existing.id, source_report_sha256, False)
            raise EvaluationImportError(
                "evaluation_import_conflict",
                "Evaluation import conflicted with another immutable record.",
            ) from retry_error


def import_evaluation_report_transactionally(
    session_factory: sessionmaker[Session],
    *,
    workspace_id: str,
    report_bytes: bytes,
) -> EvaluationImportResult:
    with session_factory.begin() as db:
        return import_evaluation_report(
            db,
            workspace_id=workspace_id,
            report_bytes=report_bytes,
        )


def _ratio_dto(row: object, prefix: str) -> dict[str, object]:
    return {
        "value": getattr(row, f"{prefix}_value"),
        "sampleCount": getattr(row, f"{prefix}_sample_count"),
        "notEvaluableReason": getattr(row, f"{prefix}_not_evaluable_reason"),
    }


def suite_dto(suite: ResearchEvaluationSuite) -> dict[str, object]:
    return {
        "id": suite.id,
        "suiteKey": suite.suite_key,
        "version": suite.version,
        "title": suite.title,
        "fixtureManifestSha256": suite.fixture_manifest_sha256,
        "scorerVersion": suite.scorer_version,
        "caseCount": suite.case_count,
        "createdAt": suite.created_at,
    }


def run_dto(run: ResearchEvaluationRun) -> dict[str, object]:
    result: dict[str, object] = {
        "id": run.id,
        "workspaceId": run.workspace_id,
        "suiteId": run.suite_id,
        "mode": run.mode,
        "status": run.status,
        "researchRunId": run.research_run_id,
        "baselineEvaluationRunId": run.baseline_evaluation_run_id,
        "fixtureManifestSha256": run.fixture_manifest_sha256,
        "assetScopeSha256": run.asset_scope_sha256,
        "provider": run.provider,
        "model": run.model,
        "providerProfileSha256": run.provider_profile_sha256,
        "scorerVersion": run.scorer_version,
        "workflowVersionId": run.workflow_version_id,
        "promptBindingSha256": run.prompt_binding_sha256,
        "wallTimeMs": run.wall_time_ms,
        "providerCalls": run.provider_calls,
        "inputTokens": run.input_tokens,
        "outputTokens": run.output_tokens,
        "cost": {"currency": run.cost_currency, "amountMicros": run.cost_microunits},
        "parallelSpeedup": run.parallel_speedup,
        "engineeringGate": run.engineering_gate,
        "modelQualityGate": run.model_quality_gate,
        "userValueGate": run.user_value_gate,
        "sourceReportSha256": run.source_report_sha256,
        "createdAt": run.created_at,
        "completedAt": run.completed_at,
        "failure": (
            {"code": run.failure_code, "message": run.failure_message}
            if run.failure_code is not None and run.failure_message is not None
            else None
        ),
    }
    for name in (
        "retry_rate",
        "recovery_rate",
        "claim_support_rate",
        "evidence_recall",
        "evidence_precision",
        "locator_accuracy",
        "conflict_detection_rate",
        "refusal_correctness",
    ):
        result[_camel(name)] = _ratio_dto(run, name)
    return result


def case_dto(case: ResearchEvaluationCaseResult) -> dict[str, object]:
    result: dict[str, object] = {
        "id": case.id,
        "caseKey": case.case_key,
        "caseType": case.case_type,
        "expectedDisposition": case.expected_disposition,
        "observedDisposition": case.observed_disposition,
        "wallTimeMs": case.wall_time_ms,
        "providerCalls": case.provider_calls,
        "cost": {"currency": case.cost_currency, "amountMicros": case.cost_microunits},
        "unsupportedClaimCount": case.unsupported_claim_count,
        "humanInterventionCount": case.human_intervention_count,
        "humanWaitMs": case.human_wait_ms,
        "failureCode": case.failure_code,
    }
    for name in (
        "claim_support_rate",
        "evidence_recall",
        "evidence_precision",
        "locator_accuracy",
        "conflict_detection_rate",
        "refusal_correctness",
    ):
        result[_camel(name)] = _ratio_dto(case, name)
    return result


def claim_dto(claim: ResearchEvaluationClaimResult) -> dict[str, object]:
    return {
        "id": claim.id,
        "claimKey": claim.claim_key,
        "supportResult": claim.support_result,
        "locatorResult": claim.locator_result,
        "conflictResult": claim.conflict_result,
        "expectedEvidenceCount": claim.expected_evidence_count,
        "observedEvidenceCount": claim.observed_evidence_count,
        "failureCode": claim.failure_code,
    }


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


def _encode_cursor(run: ResearchEvaluationRun) -> str:
    timestamp = run.created_at
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    raw = json.dumps(
        {"createdAt": timestamp.isoformat(), "id": run.id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.b64decode(cursor + padding, altchars=b"-_", validate=True)
        value = json.loads(raw)
        if not isinstance(value, dict) or set(value) != {"createdAt", "id"}:
            raise ValueError
        created_at = datetime.fromisoformat(value["createdAt"])
        run_id = value["id"]
        if created_at.tzinfo is None or not isinstance(run_id, str) or not 1 <= len(run_id) <= 36:
            raise ValueError
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise EvaluationReadError("invalid_evaluation_cursor", "Evaluation cursor is invalid.") from error
    return created_at, run_id


def list_suites(db: Session, *, workspace_id: str) -> dict[str, object]:
    suites = db.scalars(
        select(ResearchEvaluationSuite)
        .join(ResearchEvaluationRun, ResearchEvaluationRun.suite_id == ResearchEvaluationSuite.id)
        .where(ResearchEvaluationRun.workspace_id == workspace_id)
        .distinct()
        .order_by(ResearchEvaluationSuite.suite_key, ResearchEvaluationSuite.version.desc())
    ).all()
    return {"items": [suite_dto(suite) for suite in suites]}


def get_suite(db: Session, *, workspace_id: str, suite_id: str) -> dict[str, object]:
    suite = db.scalar(
        select(ResearchEvaluationSuite)
        .join(ResearchEvaluationRun, ResearchEvaluationRun.suite_id == ResearchEvaluationSuite.id)
        .where(
            ResearchEvaluationSuite.id == suite_id,
            ResearchEvaluationRun.workspace_id == workspace_id,
        )
    )
    if suite is None:
        raise EvaluationReadError("evaluation_suite_not_found", "Evaluation suite not found.")
    return {"suite": suite_dto(suite)}


def list_runs(
    db: Session,
    *,
    workspace_id: str,
    suite_id: str | None,
    mode: Literal["quick", "research"] | None,
    cursor: str | None,
    limit: int,
) -> dict[str, object]:
    statement = select(ResearchEvaluationRun).where(ResearchEvaluationRun.workspace_id == workspace_id)
    if suite_id is not None:
        statement = statement.where(ResearchEvaluationRun.suite_id == suite_id)
    if mode is not None:
        statement = statement.where(ResearchEvaluationRun.mode == mode)
    if cursor is not None:
        created_at, run_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                ResearchEvaluationRun.created_at < created_at,
                and_(
                    ResearchEvaluationRun.created_at == created_at,
                    ResearchEvaluationRun.id < run_id,
                ),
            )
        )
    rows = db.scalars(
        statement.order_by(ResearchEvaluationRun.created_at.desc(), ResearchEvaluationRun.id.desc()).limit(limit + 1)
    ).all()
    has_more = len(rows) > limit
    page = rows[:limit]
    return {
        "items": [run_dto(run) for run in page],
        "nextCursor": _encode_cursor(page[-1]) if has_more and page else None,
    }


def get_run(db: Session, *, workspace_id: str, evaluation_run_id: str) -> ResearchEvaluationRun:
    run = db.scalar(
        select(ResearchEvaluationRun).where(
            ResearchEvaluationRun.id == evaluation_run_id,
            ResearchEvaluationRun.workspace_id == workspace_id,
        )
    )
    if run is None:
        raise EvaluationReadError("evaluation_run_not_found", "Evaluation run not found.")
    return run


def run_response(db: Session, *, workspace_id: str, evaluation_run_id: str) -> dict[str, object]:
    return {"evaluation": run_dto(get_run(db, workspace_id=workspace_id, evaluation_run_id=evaluation_run_id))}


def list_cases(db: Session, *, workspace_id: str, evaluation_run_id: str) -> dict[str, object]:
    run = get_run(db, workspace_id=workspace_id, evaluation_run_id=evaluation_run_id)
    cases = db.scalars(
        select(ResearchEvaluationCaseResult)
        .where(ResearchEvaluationCaseResult.evaluation_run_id == run.id)
        .order_by(ResearchEvaluationCaseResult.case_key)
    ).all()
    return {"items": [case_dto(case) for case in cases]}


def case_response(
    db: Session,
    *,
    workspace_id: str,
    evaluation_run_id: str,
    case_key: str,
) -> dict[str, object]:
    run = get_run(db, workspace_id=workspace_id, evaluation_run_id=evaluation_run_id)
    case = db.scalar(
        select(ResearchEvaluationCaseResult).where(
            ResearchEvaluationCaseResult.evaluation_run_id == run.id,
            ResearchEvaluationCaseResult.case_key == case_key,
        )
    )
    if case is None:
        raise EvaluationReadError("evaluation_case_not_found", "Evaluation case not found.")
    claims = db.scalars(
        select(ResearchEvaluationClaimResult)
        .where(ResearchEvaluationClaimResult.case_result_id == case.id)
        .order_by(ResearchEvaluationClaimResult.claim_key)
    ).all()
    detail = case_dto(case)
    detail["claims"] = [claim_dto(claim) for claim in claims]
    return {"case": detail}
