from __future__ import annotations

import copy
import json
from collections.abc import Generator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_pdf_api.db.base import Base
from ai_pdf_api.db.session import get_db
from ai_pdf_api.models.evaluation import (
    ResearchEvaluationCaseResult,
    ResearchEvaluationClaimResult,
    ResearchEvaluationRun,
    ResearchEvaluationSuite,
)
from ai_pdf_api.models.research_artifact import ResearchArtifact
from ai_pdf_api.models.research_run import ResearchRun
from ai_pdf_api.models.research_versions import WorkflowVersion
from ai_pdf_api.models.user import User
from ai_pdf_api.models.workspace import Workspace
from ai_pdf_api.models.workspace_membership import WorkspaceMembership
from ai_pdf_api.routers.evaluation import router
from ai_pdf_api.services.evaluation import (
    EvaluationImportError,
    EvaluationImportResult,
    canonical_evaluation_report_bytes,
    import_evaluation_report,
    import_evaluation_report_transactionally,
)


WORKFLOW_VERSION_ID = "10000000-0000-4000-8000-000000000001"


def _ratio(value: float | None = 1.0, *, reason: str = "not_applicable") -> dict[str, object]:
    if value is None:
        return {"value": None, "sampleCount": 0, "notEvaluableReason": reason}
    return {"value": value, "sampleCount": 2, "notEvaluableReason": None}


def _case(case_key: str, *, refusal: bool = False) -> dict[str, object]:
    claims: list[dict[str, object]] = [] if refusal else [
        {
            "claimKey": f"{case_key}:claim",
            "supportResult": "supported",
            "locatorResult": "accurate",
            "conflictResult": "none",
            "expectedEvidenceCount": 1,
            "observedEvidenceCount": 1,
            "failureCode": None,
        }
    ]
    return {
        "caseKey": case_key,
        "caseType": "insufficiency" if refusal else "comparison",
        "expectedDisposition": "refuse" if refusal else "answer",
        "observedDisposition": "refuse" if refusal else "answer",
        "claimSupportRate": _ratio(None, reason="no_claims") if refusal else _ratio(),
        "evidenceRecall": _ratio(),
        "evidencePrecision": _ratio(),
        "locatorAccuracy": _ratio(),
        "conflictDetectionRate": _ratio(),
        "refusalCorrectness": _ratio() if refusal else _ratio(None, reason="not_refusal"),
        "wallTimeMs": 50,
        "providerCalls": 1,
        "cost": {"currency": "USD", "amountMicros": 10},
        "unsupportedClaimCount": 0,
        "humanInterventionCount": 0,
        "humanWaitMs": 0,
        "failureCode": None,
        "claims": claims,
    }


def evaluation_report(
    *,
    suite_key: str = "v4-core",
    created_at: str = "2026-07-27T10:00:00Z",
) -> dict[str, object]:
    fixture_sha = "a" * 64
    scorer_version = "scorer-v1"
    cases = [_case("compare"), _case("refuse", refusal=True)]
    return {
        "schemaVersion": "citeframe-evaluation-report-v1",
        "suite": {
            "suiteKey": suite_key,
            "version": 1,
            "title": "V4 core evaluation",
            "fixtureManifestSha256": fixture_sha,
            "scorerVersion": scorer_version,
            "caseCount": len(cases),
        },
        "evaluation": {
            "mode": "quick",
            "status": "completed",
            "researchRunId": None,
            "baselineEvaluationRunId": None,
            "fixtureManifestSha256": fixture_sha,
            "assetScopeSha256": "b" * 64,
            "provider": "openai",
            "model": "gpt-5.5",
            "providerProfileSha256": "c" * 64,
            "scorerVersion": scorer_version,
            "workflowVersionId": None,
            "promptBindingSha256": None,
            "sourceArtifact": None,
            "modelQualityEvidenceKind": "scripted",
            "userValueEvidenceRef": None,
            "wallTimeMs": 100,
            "providerCalls": 2,
            "inputTokens": 100,
            "outputTokens": 50,
            "cost": {"currency": "USD", "amountMicros": 20},
            "parallelSpeedup": None,
            "retryRate": _ratio(0.0),
            "recoveryRate": _ratio(1.0),
            "claimSupportRate": _ratio(1.0),
            "evidenceRecall": _ratio(1.0),
            "evidencePrecision": _ratio(1.0),
            "locatorAccuracy": _ratio(1.0),
            "conflictDetectionRate": _ratio(1.0),
            "refusalCorrectness": _ratio(1.0),
            "engineeringGate": "pass",
            "modelQualityGate": "not_evaluable",
            "userValueGate": "not_evaluable",
            "failure": None,
            "createdAt": created_at,
            "completedAt": created_at,
        },
        "cases": cases,
    }


@pytest.fixture
def evaluation_app() -> Generator[tuple[TestClient, Session, dict[str, object]], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)()
    owner = User(
        id=str(uuid4()), email="evaluation-owner@example.com", name="Owner", password_hash="hash", avatar_url=""
    )
    member = User(
        id=str(uuid4()), email="evaluation-member@example.com", name="Member", password_hash="hash", avatar_url=""
    )
    stranger = User(
        id=str(uuid4()), email="evaluation-stranger@example.com", name="Stranger", password_hash="hash", avatar_url=""
    )
    now = datetime.now(UTC)
    workspace = Workspace(
        id=str(uuid4()), name="Evaluation", created_by_user_id=owner.id, created_at=now, updated_at=now
    )
    other_workspace = Workspace(
        id=str(uuid4()), name="Other", created_by_user_id=stranger.id, created_at=now, updated_at=now
    )
    db.add_all([owner, member, stranger, workspace, other_workspace])
    db.flush()
    db.add_all(
        [
            WorkflowVersion(
                id=WORKFLOW_VERSION_ID,
                workflow_key="evaluation-test",
                version_number=1,
                availability="active",
                manifest_schema_version="v1",
                manifest_json={},
                manifest_sha256="9" * 64,
                created_by_release_id="evaluation-test",
                created_at=now,
            ),
            WorkspaceMembership(workspace_id=workspace.id, user_id=owner.id, role="owner"),
            WorkspaceMembership(workspace_id=workspace.id, user_id=member.id, role="member"),
            WorkspaceMembership(workspace_id=other_workspace.id, user_id=stranger.id, role="owner"),
        ]
    )
    db.commit()
    app = FastAPI()
    app.include_router(router)

    def override_get_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    context = {
        "owner": owner,
        "member": member,
        "stranger": stranger,
        "workspace": workspace,
        "otherWorkspace": other_workspace,
    }
    with TestClient(app) as client:
        yield client, db, context
    db.close()
    engine.dispose()


def _auth(user: User) -> dict[str, str]:
    return {
        "x-ai-pdf-internal-token": "local-development-internal-token",
        "x-user-id": user.id,
    }


def _import(db: Session, workspace: Workspace, report: dict[str, object]):
    return import_evaluation_report(
        db,
        workspace_id=workspace.id,
        report_bytes=canonical_evaluation_report_bytes(report),
    )


def test_import_flushes_the_graph_in_foreign_key_order() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    user_id = str(uuid4())
    workspace_id = str(uuid4())
    now = datetime.now(UTC)
    with factory.begin() as db:
        db.add(
            User(
                id=user_id,
                email="evaluation-fk-order@example.com",
                name="FK order",
                password_hash="hash",
                avatar_url="",
            )
        )
    with factory.begin() as db:
        db.add(
            Workspace(
                id=workspace_id,
                name="FK order",
                created_by_user_id=user_id,
                created_at=now,
                updated_at=now,
            )
        )
    result = import_evaluation_report_transactionally(
        factory,
        workspace_id=workspace_id,
        report_bytes=canonical_evaluation_report_bytes(evaluation_report()),
    )
    with factory() as db:
        assert db.get(ResearchEvaluationRun, result.evaluation_run_id) is not None
        assert db.scalar(select(func.count()).select_from(ResearchEvaluationCaseResult)) == 2
        assert db.scalar(select(func.count()).select_from(ResearchEvaluationClaimResult)) == 1
    engine.dispose()


def test_import_is_atomic_idempotent_and_append_only(evaluation_app) -> None:
    _client, db, context = evaluation_app
    workspace = context["workspace"]
    assert isinstance(workspace, Workspace)
    report = evaluation_report()

    first = _import(db, workspace, report)
    db.commit()
    replay = _import(db, workspace, report)
    db.commit()

    assert first.created is True
    assert replay.created is False
    assert replay.evaluation_run_id == first.evaluation_run_id
    assert db.scalar(select(func.count()).select_from(ResearchEvaluationSuite)) == 1
    assert db.scalar(select(func.count()).select_from(ResearchEvaluationRun)) == 1
    assert db.scalar(select(func.count()).select_from(ResearchEvaluationCaseResult)) == 2
    assert db.scalar(select(func.count()).select_from(ResearchEvaluationClaimResult)) == 1

    correction = copy.deepcopy(report)
    correction["evaluation"]["createdAt"] = "2026-07-27T10:01:00Z"  # type: ignore[index]
    correction["evaluation"]["completedAt"] = "2026-07-27T10:01:00Z"  # type: ignore[index]
    second = _import(db, workspace, correction)
    db.commit()
    assert second.created is True
    assert second.evaluation_run_id != first.evaluation_run_id
    assert db.scalar(select(func.count()).select_from(ResearchEvaluationRun)) == 2

    conflicting_suite = copy.deepcopy(correction)
    conflicting_suite["suite"]["title"] = "Mutated title"  # type: ignore[index]
    conflicting_suite["evaluation"]["createdAt"] = "2026-07-27T10:02:00Z"  # type: ignore[index]
    conflicting_suite["evaluation"]["completedAt"] = "2026-07-27T10:02:00Z"  # type: ignore[index]
    with pytest.raises(EvaluationImportError, match="immutable") as captured:
        _import(db, workspace, conflicting_suite)
    assert captured.value.code == "evaluation_suite_conflict"
    assert db.scalar(select(func.count()).select_from(ResearchEvaluationRun)) == 2
    assert db.scalar(select(func.count()).select_from(ResearchEvaluationCaseResult)) == 4


def test_import_rejects_noncanonical_unknown_and_duplicate_fields_without_rows(evaluation_app) -> None:
    _client, db, context = evaluation_app
    workspace = context["workspace"]
    assert isinstance(workspace, Workspace)
    report = evaluation_report()

    with pytest.raises(EvaluationImportError) as pretty_error:
        import_evaluation_report(
            db,
            workspace_id=workspace.id,
            report_bytes=json.dumps(report, indent=2).encode(),
        )
    assert pretty_error.value.code == "noncanonical_evaluation_report"

    forbidden = copy.deepcopy(report)
    forbidden["evaluation"]["promptText"] = "secret prompt"  # type: ignore[index]
    with pytest.raises(EvaluationImportError) as schema_error:
        _import(db, workspace, forbidden)
    assert schema_error.value.code == "invalid_evaluation_report"

    with pytest.raises(EvaluationImportError, match="Duplicate JSON key"):
        import_evaluation_report(db, workspace_id=workspace.id, report_bytes=b'{"a":1,"a":2}')
    assert db.scalar(select(func.count()).select_from(ResearchEvaluationSuite)) == 0
    assert db.scalar(select(func.count()).select_from(ResearchEvaluationRun)) == 0


@pytest.mark.parametrize(
    "field",
    ["researchRunId", "baselineEvaluationRunId", "workflowVersionId", "sourceArtifact.artifactId"],
)
def test_import_requires_canonical_uuid_ids(evaluation_app, field: str) -> None:
    _client, db, context = evaluation_app
    workspace = context["workspace"]
    assert isinstance(workspace, Workspace)
    report = evaluation_report()
    evaluation = report["evaluation"]
    assert isinstance(evaluation, dict)
    if field == "workflowVersionId":
        evaluation[field] = "10000000-0000-4000-8000-00000000000A"
    elif field == "sourceArtifact.artifactId":
        evaluation["mode"] = "research"
        evaluation["researchRunId"] = str(uuid4())
        evaluation["sourceArtifact"] = {"artifactId": "artifact-not-a-uuid", "sha256": "e" * 64}
    else:
        evaluation["mode"] = "research"
        evaluation[field] = "not-a-canonical-uuid"

    with pytest.raises(EvaluationImportError) as captured:
        _import(db, workspace, report)
    assert captured.value.code == "invalid_evaluation_report"
    assert db.scalar(select(func.count()).select_from(ResearchEvaluationRun)) == 0


@pytest.mark.parametrize(
    ("mutate", "path"),
    [
        (lambda report: report["evaluation"].update(modelQualityGate="pass"), "modelQualityGate"),
        (lambda report: report["evaluation"].update(userValueGate="pass"), "userValueGate"),
        (
            lambda report: report["evaluation"]["claimSupportRate"].update(value=1.5),
            "claimSupportRate",
        ),
        (lambda report: report["cases"].append(copy.deepcopy(report["cases"][0])), "cases"),
    ],
)
def test_import_enforces_gate_ratio_and_unique_case_rules(evaluation_app, mutate, path: str) -> None:
    _client, db, context = evaluation_app
    workspace = context["workspace"]
    assert isinstance(workspace, Workspace)
    report = evaluation_report()
    mutate(report)

    with pytest.raises(EvaluationImportError) as captured:
        _import(db, workspace, report)
    assert captured.value.code == "invalid_evaluation_report", path
    assert db.scalar(select(func.count()).select_from(ResearchEvaluationRun)) == 0


def test_import_requires_exact_quick_research_pairing_keys_and_case_set(evaluation_app) -> None:
    _client, db, context = evaluation_app
    workspace = context["workspace"]
    assert isinstance(workspace, Workspace)
    quick = _import(db, workspace, evaluation_report())
    db.commit()

    research = evaluation_report(created_at="2026-07-27T11:00:00Z")
    research["evaluation"].update(  # type: ignore[union-attr]
        mode="research",
        baselineEvaluationRunId=quick.evaluation_run_id,
        workflowVersionId=WORKFLOW_VERSION_ID,
        promptBindingSha256="d" * 64,
    )
    paired = _import(db, workspace, research)
    db.commit()
    assert paired.created is True

    mismatch = copy.deepcopy(research)
    mismatch["evaluation"]["createdAt"] = "2026-07-27T11:01:00Z"  # type: ignore[index]
    mismatch["evaluation"]["completedAt"] = "2026-07-27T11:01:00Z"  # type: ignore[index]
    mismatch["evaluation"]["provider"] = "anthropic"  # type: ignore[index]
    with pytest.raises(EvaluationImportError) as key_error:
        _import(db, workspace, mismatch)
    assert key_error.value.code == "evaluation_pair_mismatch"

    case_mismatch = copy.deepcopy(research)
    case_mismatch["evaluation"]["createdAt"] = "2026-07-27T11:02:00Z"  # type: ignore[index]
    case_mismatch["evaluation"]["completedAt"] = "2026-07-27T11:02:00Z"  # type: ignore[index]
    case_mismatch["cases"][0]["caseKey"] = "different-case"  # type: ignore[index]
    with pytest.raises(EvaluationImportError) as case_error:
        _import(db, workspace, case_mismatch)
    assert case_error.value.code == "evaluation_pair_mismatch"
    assert db.scalar(select(func.count()).select_from(ResearchEvaluationRun)) == 2


def test_import_rolls_back_a_flushed_graph_and_transactional_entry_commits(evaluation_app, monkeypatch) -> None:
    _client, db, context = evaluation_app
    workspace = context["workspace"]
    assert isinstance(workspace, Workspace)
    original_flush = db.flush

    def flush_then_fail(*args, **kwargs):
        original_flush(*args, **kwargs)
        raise EvaluationImportError("forced_failure", "Forced failure after graph flush.")

    monkeypatch.setattr(db, "flush", flush_then_fail)
    with pytest.raises(EvaluationImportError, match="Forced failure"):
        _import(db, workspace, evaluation_report())
    monkeypatch.setattr(db, "flush", original_flush)
    db.commit()
    assert db.scalar(select(func.count()).select_from(ResearchEvaluationSuite)) == 0
    assert db.scalar(select(func.count()).select_from(ResearchEvaluationRun)) == 0
    assert db.scalar(select(func.count()).select_from(ResearchEvaluationCaseResult)) == 0
    assert db.scalar(select(func.count()).select_from(ResearchEvaluationClaimResult)) == 0

    factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False, future=True)
    committed = import_evaluation_report_transactionally(
        factory,
        workspace_id=workspace.id,
        report_bytes=canonical_evaluation_report_bytes(evaluation_report()),
    )
    db.expire_all()
    assert db.get(ResearchEvaluationRun, committed.evaluation_run_id) is not None


def test_unique_race_loser_is_returned_as_idempotent_replay(evaluation_app, monkeypatch) -> None:
    import ai_pdf_api.services.evaluation as evaluation_service
    from sqlalchemy.exc import IntegrityError

    _client, db, context = evaluation_app
    workspace = context["workspace"]
    assert isinstance(workspace, Workspace)
    report_bytes = canonical_evaluation_report_bytes(evaluation_report())
    winner = import_evaluation_report(db, workspace_id=workspace.id, report_bytes=report_bytes)
    db.commit()

    def lose_unique_race(*args, **kwargs):
        raise IntegrityError("INSERT", {}, RuntimeError("unique violation"))

    monkeypatch.setattr(evaluation_service, "_import_evaluation_graph", lose_unique_race)
    replay = import_evaluation_report(db, workspace_id=workspace.id, report_bytes=report_bytes)
    assert replay.created is False
    assert replay.evaluation_run_id == winner.evaluation_run_id
    assert db.scalar(select(func.count()).select_from(ResearchEvaluationRun)) == 1


def test_different_report_suite_race_retries_the_complete_graph_once(evaluation_app, monkeypatch) -> None:
    import ai_pdf_api.services.evaluation as evaluation_service
    from sqlalchemy.exc import IntegrityError

    _client, db, context = evaluation_app
    workspace = context["workspace"]
    assert isinstance(workspace, Workspace)
    calls = 0
    expected_id = str(uuid4())

    def lose_suite_then_insert(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise IntegrityError("INSERT suite", {}, RuntimeError("unique suite violation"))
        return EvaluationImportResult(expected_id, kwargs["source_report_sha256"], True)

    monkeypatch.setattr(evaluation_service, "_import_evaluation_graph", lose_suite_then_insert)
    result = import_evaluation_report(
        db,
        workspace_id=workspace.id,
        report_bytes=canonical_evaluation_report_bytes(evaluation_report()),
    )
    assert calls == 2
    assert result.created is True
    assert result.evaluation_run_id == expected_id


def test_non_replay_integrity_conflict_remains_fail_closed_after_one_retry(evaluation_app, monkeypatch) -> None:
    import ai_pdf_api.services.evaluation as evaluation_service
    from sqlalchemy.exc import IntegrityError

    _client, db, context = evaluation_app
    workspace = context["workspace"]
    assert isinstance(workspace, Workspace)
    calls = 0

    def persistent_conflict(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise IntegrityError("INSERT graph", {}, RuntimeError("persistent constraint violation"))

    monkeypatch.setattr(evaluation_service, "_import_evaluation_graph", persistent_conflict)
    with pytest.raises(EvaluationImportError) as captured:
        import_evaluation_report(
            db,
            workspace_id=workspace.id,
            report_bytes=canonical_evaluation_report_bytes(evaluation_report()),
        )
    assert captured.value.code == "evaluation_import_conflict"
    assert calls == 2


def test_import_validates_research_run_and_source_artifact_ownership(evaluation_app) -> None:
    _client, db, context = evaluation_app
    owner = context["owner"]
    workspace = context["workspace"]
    other_workspace = context["otherWorkspace"]
    assert isinstance(owner, User)
    assert isinstance(workspace, Workspace)
    assert isinstance(other_workspace, Workspace)
    now = datetime.now(UTC)
    research_run = ResearchRun(
        id=str(uuid4()),
        workspace_id=workspace.id,
        created_by_user_id=owner.id,
        status="planning",
        state_version=1,
        next_event_seq=1,
        cost_currency="USD",
        created_at=now,
        updated_at=now,
    )
    other_run = ResearchRun(
        id=str(uuid4()),
        workspace_id=other_workspace.id,
        created_by_user_id=owner.id,
        status="planning",
        state_version=1,
        next_event_seq=1,
        cost_currency="USD",
        created_at=now,
        updated_at=now,
    )
    artifact = ResearchArtifact(
        id=str(uuid4()),
        workspace_id=workspace.id,
        run_id=research_run.id,
        generated_by_step_id=str(uuid4()),
        generated_by_attempt_id=str(uuid4()),
        artifact_kind="final_report",
        visibility="user",
        logical_key="final-report",
        schema_version="v1",
        object_key="private/object-key",
        content_type="application/json",
        byte_size=10,
        content_sha256="e" * 64,
        workflow_version_id=str(uuid4()),
        retention_class="workspace_lifetime",
        expires_at=None,
        created_at=now,
    )
    db.add_all([research_run, other_run, artifact])
    db.commit()

    report = evaluation_report(suite_key="research-source")
    report["suite"]["fixtureManifestSha256"] = "f" * 64  # type: ignore[index]
    report["evaluation"].update(  # type: ignore[union-attr]
        mode="research",
        researchRunId=research_run.id,
        fixtureManifestSha256="f" * 64,
        sourceArtifact={"artifactId": artifact.id, "sha256": artifact.content_sha256},
    )
    imported = _import(db, workspace, report)
    db.commit()
    row = db.get(ResearchEvaluationRun, imported.evaluation_run_id)
    assert row is not None
    assert row.source_artifact_sha256 == artifact.content_sha256

    wrong_workspace = evaluation_report(
        suite_key="research-other",
        created_at="2026-07-27T12:00:00Z",
    )
    wrong_workspace["suite"]["fixtureManifestSha256"] = "1" * 64  # type: ignore[index]
    wrong_workspace["evaluation"].update(  # type: ignore[union-attr]
        mode="research",
        researchRunId=other_run.id,
        fixtureManifestSha256="1" * 64,
    )
    with pytest.raises(EvaluationImportError) as captured:
        _import(db, workspace, wrong_workspace)
    assert captured.value.code == "evaluation_research_run_not_found"


def test_owner_read_api_matches_web_dtos_and_never_exposes_import_only_fields(evaluation_app) -> None:
    client, db, context = evaluation_app
    owner = context["owner"]
    workspace = context["workspace"]
    assert isinstance(owner, User)
    assert isinstance(workspace, Workspace)
    first = _import(db, workspace, evaluation_report())
    later = evaluation_report(created_at="2026-07-27T10:01:00Z")
    second = _import(db, workspace, later)
    db.commit()

    suites = client.get(f"/v1/workspaces/{workspace.id}/evaluation-suites", headers=_auth(owner))
    assert suites.status_code == 200
    assert suites.headers["Cache-Control"] == "no-store"
    assert len(suites.json()["items"]) == 1
    suite_id = suites.json()["items"][0]["id"]
    suite = client.get(
        f"/v1/workspaces/{workspace.id}/evaluation-suites/{suite_id}", headers=_auth(owner)
    )
    assert suite.status_code == 200
    assert suite.json()["suite"]["caseCount"] == 2

    page_one = client.get(
        f"/v1/workspaces/{workspace.id}/evaluations?mode=quick&limit=1", headers=_auth(owner)
    )
    assert page_one.status_code == 200
    assert page_one.json()["items"][0]["id"] == second.evaluation_run_id
    cursor = page_one.json()["nextCursor"]
    assert cursor
    page_two = client.get(
        f"/v1/workspaces/{workspace.id}/evaluations?mode=quick&limit=1&cursor={cursor}",
        headers=_auth(owner),
    )
    assert page_two.status_code == 200
    assert page_two.json()["items"][0]["id"] == first.evaluation_run_id
    run = page_one.json()["items"][0]
    assert set(run) == {
        "id", "workspaceId", "suiteId", "mode", "status", "researchRunId",
        "baselineEvaluationRunId", "fixtureManifestSha256", "assetScopeSha256", "provider",
        "model", "providerProfileSha256", "scorerVersion", "workflowVersionId",
        "promptBindingSha256", "wallTimeMs", "providerCalls", "inputTokens", "outputTokens",
        "cost", "parallelSpeedup", "retryRate", "recoveryRate", "claimSupportRate",
        "evidenceRecall", "evidencePrecision", "locatorAccuracy", "conflictDetectionRate",
        "refusalCorrectness", "engineeringGate", "modelQualityGate", "userValueGate",
        "sourceReportSha256", "createdAt", "completedAt", "failure",
    }
    serialized = json.dumps(page_one.json())
    for forbidden in (
        "sourceArtifact", "sourceArtifactSha256", "modelQualityEvidenceKind",
        "userValueEvidenceRef", "objectKey", "promptText", "rawProviderPayload",
    ):
        assert forbidden not in serialized

    detail = client.get(
        f"/v1/workspaces/{workspace.id}/evaluations/{second.evaluation_run_id}", headers=_auth(owner)
    )
    assert detail.status_code == 200
    cases = client.get(
        f"/v1/workspaces/{workspace.id}/evaluations/{second.evaluation_run_id}/cases",
        headers=_auth(owner),
    )
    assert cases.status_code == 200
    case_key = cases.json()["items"][0]["caseKey"]
    case = client.get(
        f"/v1/workspaces/{workspace.id}/evaluations/{second.evaluation_run_id}/cases/{case_key}",
        headers=_auth(owner),
    )
    assert case.status_code == 200
    assert "claims" in case.json()["case"]


def test_non_owner_and_cross_workspace_reads_do_not_enumerate_evaluations(evaluation_app) -> None:
    client, db, context = evaluation_app
    workspace = context["workspace"]
    other_workspace = context["otherWorkspace"]
    member = context["member"]
    stranger = context["stranger"]
    assert isinstance(workspace, Workspace)
    assert isinstance(other_workspace, Workspace)
    assert isinstance(member, User)
    assert isinstance(stranger, User)
    imported = _import(db, workspace, evaluation_report())
    db.commit()

    denied = client.get(f"/v1/workspaces/{workspace.id}/evaluation-suites", headers=_auth(member))
    assert denied.status_code == 403
    hidden = client.get(
        f"/v1/workspaces/{other_workspace.id}/evaluations/{imported.evaluation_run_id}",
        headers=_auth(stranger),
    )
    assert hidden.status_code == 404
    assert "evaluation" not in hidden.text.lower() or hidden.json() == {"detail": "Evaluation run not found."}
    other_suites = client.get(
        f"/v1/workspaces/{other_workspace.id}/evaluation-suites", headers=_auth(stranger)
    )
    assert other_suites.status_code == 200
    assert other_suites.json() == {"items": []}


def test_invalid_cursor_is_rejected_without_falling_back_to_first_page(evaluation_app) -> None:
    client, db, context = evaluation_app
    workspace = context["workspace"]
    owner = context["owner"]
    assert isinstance(workspace, Workspace)
    assert isinstance(owner, User)
    _import(db, workspace, evaluation_report())
    db.commit()

    response = client.get(
        f"/v1/workspaces/{workspace.id}/evaluations?cursor=not-a-cursor",
        headers=_auth(owner),
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Evaluation cursor is invalid."}
