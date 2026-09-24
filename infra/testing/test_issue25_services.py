"""Opt-in real HTTP/PostgreSQL/S3 recovery gates; generation is a local fixture."""

from __future__ import annotations

import json
import os
import time

import pytest
from issue25_service_support import ROOT, Deployment, archive_legacy
from sqlalchemy import text

BASE_URL = os.environ.get("CITEFRAME_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not BASE_URL, reason="requires isolated PostgreSQL and S3 services"
)
V3 = "30000000-0000-4000-8000-000000000001"
V4 = "40000000-0000-4000-8000-000000000001"


@pytest.fixture
def deployment(tmp_path):
    d = Deployment(tmp_path, BASE_URL)
    try:
        yield d
    finally:
        d.close()


def start(d, mode="resolved"):
    d.migrate()
    d.start_api()
    d.seed()
    d.create("Issue 25 " + mode)


def assert_report_and_edit(d, *, investigation_status):
    detail = d.request("GET", d.path).json()["run"]
    assert detail["status"] == "completed", detail
    investigation = detail["conflictInvestigation"]
    if investigation_status is None:
        assert investigation is None
    else:
        assert investigation["status"] == investigation_status
        assert investigation["originalClaims"] and investigation["sources"]
        if investigation_status == "resolved":
            assert investigation["revisions"] and not investigation["gaps"]
        else:
            assert not investigation["revisions"] and investigation["gaps"]
    artifacts = d.request("GET", d.path + "/artifacts").json()["items"]
    final = next(a for a in artifacts if a["kind"] == "final_report")
    content_path = d.path + "/artifacts/" + final["id"] + "/content"
    original = d.request("GET", content_path).content
    binding = d.binding()
    editor = d.request("GET", d.path + "/report-edit").json()
    saved = d.request(
        "PUT",
        d.path + "/report-edit",
        json={
            "originalArtifactId": editor["originalArtifactId"],
            "originalSha256": editor["originalSha256"],
            "expectedVersion": editor["version"],
            "markdown": "# User edition\nUnverified local note.",
        },
    ).json()
    assert saved["verificationStatus"] == "unverified" and saved["version"] == 1
    d.stop_api()
    d.start_api()
    assert d.request("GET", d.path + "/report-edit").json() == saved
    assert d.request("GET", content_path).content == original
    assert d.binding() == binding
    d.capture(
        "http-page-and-editor",
        {
            "run": detail,
            "artifact": final,
            "edit": saved,
            "originalMarkdown": original.decode(),
            "binding": binding,
        },
    )
    return detail


def test_approved_v3_snapshot_survives_default_v4_upgrade_and_edit(
    deployment, tmp_path
):
    d = deployment
    old = archive_legacy(tmp_path / "legacy")
    d.migrate(old)
    d.start_api()
    d.seed()
    d.create("Already approved v3 task must retain all bindings")
    d.work(steps=2)
    assert any(
        row["step_kind"] == "researcher" and row["status"] == "succeeded"
        for row in d.rows("research_steps")
    )
    before = d.binding()
    assert before["snapshot"]["workflow_version_id"] == V3
    assert len(before["approval"]) == 1
    assert before["approval"][0]["status"] == "submitted"
    assert before["approval"][0]["action"] == "approve"
    assert (
        before["snapshot"]["agent_result_schema_version"] == "research-agent-results-v2"
    )
    assert all(
        row["prompt_version_id"].startswith("30000000") for row in before["prompts"]
    )
    d.capture("approved-before-upgrade", before)
    d.capture(
        "execution-before-upgrade",
        {
            "steps": d.rows("research_steps"),
            "attempts": d.rows("research_step_attempts"),
            "claims": d.rows("research_claims"),
            "artifacts": d.rows("research_artifacts"),
        },
    )
    d.stop_api()
    d.migrate(ROOT)
    assert {r["id"] for r in d.rows("workflow_versions")} >= {V3, V4}
    assert d.binding() == before
    d.start_api()
    d.work()
    assert_report_and_edit(d, investigation_status=None)
    assert d.binding() == before
    assert d.rows("research_conflict_turns") == []
    assert all(a["workflow_version_id"] == V3 for a in d.rows("research_artifacts"))
    d.create("A new task after upgrade uses v4")
    revision = next(
        r for r in d.rows("research_plan_revisions") if r["run_id"] == d.run
    )
    assert revision["proposed_workflow_version_id"] == V4


@pytest.mark.parametrize("mode", ["resolved", "unresolved"])
def test_real_api_pages_publication_and_edit(deployment, mode):
    d = deployment
    start(d, mode)
    d.work(mode)
    detail = assert_report_and_edit(d, investigation_status=mode)
    if mode == "resolved":
        assert [o["phase"] for o in detail["conflictInvestigation"]["operations"]] == [
            "inspect",
            "verify",
            "critic",
            "finish",
        ]
    else:
        assert detail["conflictInvestigation"]["reason"] == "no_new_evidence"


CRASHES = [
    ("inspect:before-reserve", "resolved", "resolved"),
    ("inspect:after-reserve", "resolved", "unresolved"),
    ("inspect:before-result", "resolved", "unresolved"),
    ("inspect:after-result", "resolved", "resolved"),
    ("search:before-reserve", "unresolved", "unresolved"),
    ("search:after-reserve", "unresolved", "unresolved"),
    ("search:before-result", "unresolved", "unresolved"),
    ("search:after-result", "unresolved", "unresolved"),
    ("verify:before-result", "resolved", "unresolved"),
    ("verify:after-result", "resolved", "resolved"),
    ("critic:before-result", "resolved", "unresolved"),
    ("critic:after-result", "resolved", "resolved"),
]


@pytest.mark.parametrize("point,mode,status", CRASHES)
def test_journal_recovery_after_actual_worker_process_exit(
    deployment, point, mode, status
):
    d = deployment
    start(d, mode)
    d.work(mode, until_gate=True)
    binding = d.binding()
    originals = d.rows("research_claims")
    d.work(mode, crash=point)
    assert json.loads((d.directory / "crash.json").read_text())["point"] == point
    prior = d.rows("research_conflict_turns")
    calls = d.rows("research_provider_calls")
    tools = d.rows("research_tool_calls")
    d.capture(
        "crash-state",
        {
            "turns": prior,
            "providers": calls,
            "tools": tools,
            "attempts": d.rows("research_step_attempts"),
            "steps": d.rows("research_steps"),
        },
    )
    # Wait for the genuine fixture lease to expire; do not rewrite lease timestamps.
    time.sleep(9)
    d.stop_api()
    d.start_api()
    d.work(mode)
    d.capture(
        "restart-state",
        {
            t: d.rows(t)
            for t in (
                "research_steps",
                "research_step_attempts",
                "research_runs",
                "research_conflict_turns",
                "research_publication_intents",
            )
        },
    )
    detail = assert_report_and_edit(d, investigation_status=status)
    current = d.rows("research_conflict_turns")
    by_number = {r["operation_number"]: r for r in current}
    assert len(by_number) == len(current)
    for old in prior:
        assert by_number[old["operation_number"]] == old, (
            "recovery rewrote a committed journal reservation/result"
        )
    if point.endswith(("after-reserve", "before-result")):
        assert detail["conflictInvestigation"]["reason"] == "operation_outcome_unknown"
        assert d.rows("research_provider_calls") == calls
        assert d.rows("research_tool_calls") == tools
    gate = next(
        s
        for s in d.rows("research_steps")
        if s["step_kind"] == "conflict_decision_gate"
    )
    attempts = [
        a for a in d.rows("research_step_attempts") if a["step_id"] == gate["id"]
    ]
    assert [
        a["status"] for a in sorted(attempts, key=lambda a: a["attempt_number"])
    ] == ["abandoned", "succeeded"]
    # Each successfully checkpointed phase is backed by only its original external operation.
    for phase in ("inspect", "verify", "critic"):
        if any(r["phase"] == phase and r["status"] == "succeeded" for r in prior):
            node = {
                "inspect": "investigator",
                "verify": "verifier",
                "critic": "critic",
            }[phase]
            before = [
                c
                for c in calls
                if c["step_id"] == gate["id"] and node in c["logical_call_key"]
            ]
            after = [
                c
                for c in d.rows("research_provider_calls")
                if c["step_id"] == gate["id"] and node in c["logical_call_key"]
            ]
            assert after == before
    if point.startswith("search:") and point != "search:before-reserve":
        assert [
            t for t in d.rows("research_tool_calls") if t["step_id"] == gate["id"]
        ] == [t for t in tools if t["step_id"] == gate["id"]]
    assert d.binding() == binding
    assert [(c["id"], c["statement_text"]) for c in d.rows("research_claims")] == [
        (c["id"], c["statement_text"]) for c in originals
    ]
    d.capture(
        "recovered",
        {
            "point": point,
            "turns": current,
            "attempts": attempts,
            "http": detail,
            "providers": d.rows("research_provider_calls"),
            "tools": d.rows("research_tool_calls"),
            "budgetLedgers": d.rows("research_budget_ledgers"),
            "artifacts": d.rows("research_artifacts"),
        },
    )


@pytest.mark.parametrize("boundary", ["cancel", "permission"])
def test_revocation_or_cancel_between_processes_prevents_more_work(
    deployment, boundary
):
    d = deployment
    start(d)
    d.work(until_gate=True)
    d.work(crash="inspect:after-result")
    before = {
        table: d.rows(table)
        for table in (
            "research_conflict_turns",
            "research_provider_calls",
            "research_tool_calls",
        )
    }
    if boundary == "cancel":
        run = d.request("GET", d.path).json()["run"]
        d.request(
            "POST",
            d.path + "/cancel",
            expected=202,
            json={
                "expectedStateVersion": run["stateVersion"],
                "reasonCode": "user_requested",
            },
        )
    else:
        with d.engine.begin() as connection:
            connection.execute(
                text("DELETE FROM workspace_memberships WHERE user_id=:id"),
                {"id": d.user},
            )
    time.sleep(9)
    log = d.work(expected=1 if boundary == "permission" else 0)
    if boundary == "permission":
        assert "Research creator is no longer a Workspace member" in log.read_text(
            encoding="utf-8"
        )
    for table, rows in before.items():
        assert d.rows(table) == rows, table
    assert not [
        a for a in d.rows("research_artifacts") if a["artifact_kind"] == "final_report"
    ]
    assert d.rows("research_runs")[0]["status"] == "cancelled"
    if boundary == "permission":
        assert (
            d.request("GET", d.path, expected=404).json()["error"]["code"]
            == "workspace_not_found"
        )
