"""Budget and complete PostgreSQL-chain oracles for the issue-25 service fixture."""

import os

import pytest
from issue25_service_support import ROOT, Deployment, archive_legacy
from test_issue25_services import assert_report_and_edit, start
from test_issue25_services import deployment as service_deployment

deployment = service_deployment

pytestmark = pytest.mark.skipif(
    not os.environ.get("CITEFRAME_TEST_POSTGRES_URL"), reason="requires PostgreSQL/S3"
)


def test_shared_tool_budget_is_enforced_during_investigation(deployment):
    d = deployment
    start(d, "unresolved")
    d.work("unresolved", until_gate=True)
    d.work("unresolved", exhaust_tools=True)
    detail = assert_report_and_edit(d, investigation_status="unresolved")
    assert detail["conflictInvestigation"]["reason"] == "budget_exhausted"
    snapshot = d.binding()["snapshot"]
    ledger = next(
        r
        for r in d.rows("research_budget_ledgers")
        if r["execution_snapshot_id"] == snapshot["id"]
    )
    assert (
        ledger["actual_tool_calls"] == snapshot["max_tool_calls"]
        and ledger["reserved_tool_calls"] == 0
    )
    assert len(d.rows("research_tool_calls")) == snapshot["max_tool_calls"]
    assert (
        ledger["actual_provider_calls"] + ledger["reserved_provider_calls"]
        <= snapshot["max_provider_calls"]
    )
    d.capture("budget", {"snapshot": snapshot, "ledger": ledger, "http": detail})


def test_real_postgresql_fresh_and_historical_upgrade_install_identical_releases(
    deployment, tmp_path
):
    staged = deployment
    old = archive_legacy(tmp_path / "legacy")
    staged.migrate(old)
    before = {
        name: staged.rows(name)
        for name in ("workflow_versions", "prompt_versions", "workflow_prompt_bindings")
    }
    staged.migrate(ROOT)
    with_later = {name: staged.rows(name) for name in before}
    for name, rows in before.items():
        assert all(row in with_later[name] for row in rows), (
            "upgrade rewrote an installed release"
        )
    fresh = Deployment(tmp_path / "fresh", os.environ["CITEFRAME_TEST_POSTGRES_URL"])
    try:
        fresh.migrate(ROOT)

        def immutable(rows):
            return sorted(
                [{k: v for k, v in r.items() if k != "created_at"} for r in rows],
                key=str,
            )

        for table in before:
            assert immutable(fresh.rows(table)) == immutable(staged.rows(table)), table
        staged.capture(
            "postgres-fresh-staged",
            {"tables": list(before), "result": "equal", "priorRowsPreserved": True},
        )
    finally:
        fresh.close()
