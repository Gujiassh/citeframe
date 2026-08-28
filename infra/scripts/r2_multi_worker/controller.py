"""Immutable real-PostgreSQL, real-process baseline for Research R2."""
from __future__ import annotations

import argparse
import json
import os
import re
import traceback
from pathlib import Path
from typing import Any

from .common import START_SHA, error_json, utcnow
from .harness import HarnessBase
from .scenarios_accounting import AccountingScenarios
from .scenarios_admission import AdmissionScenarios
from .scenarios_publication import PublicationOutcomeScenarios
from .scenarios_runtime import RuntimeScenarios
from .worker_actor import worker_main


class R2Harness(
    RuntimeScenarios,
    AccountingScenarios,
    PublicationOutcomeScenarios,
    AdmissionScenarios,
    HarnessBase,
):
    def run(self) -> dict[str, Any]:
        self.add_scenario("two-os-workers-same-run-overlap", self.scenario_two_workers)
        self.add_scenario("lease-expiry-late-completion-reclaim-recovery", self.scenario_lease_reclaim)
        self.add_scenario("join-dependency-readiness", self.scenario_join_readiness)
        self.add_scenario("provider-cancel-outcome-unknown-exactly-once", self.scenario_provider_cancel)
        self.add_scenario("provider-budget-exactly-once", self.scenario_provider_budget_exactly_once)
        self.add_scenario("tool-reclaim-exactly-once", self.scenario_tool_reclaim_exactly_once)
        self.add_scenario(
            "tool-completion-vs-lease-reclaim",
            self.scenario_tool_completion_vs_lease_reclaim,
        )
        self.add_scenario("step-completion-vs-cancel", self.scenario_step_completion_vs_cancel)
        self.add_scenario("conflict-wait-resume", self.scenario_conflict_resume)
        self.add_scenario("final-publication", self.scenario_final_publication)
        self.add_scenario(
            "publication-commit-outcome-matrix",
            self.scenario_publication_outcome_matrix,
        )
        self.add_scenario("cap-1", lambda: self.scenario_cap(1))
        self.add_scenario("cap-n", lambda: self.scenario_cap(2))
        self.add_scenario("cap-1-expired-slot-reclaim-atomic", self.scenario_expired_slot_atomic)
        self.add_scenario("cap-full-fairness-no-starvation-zero-mutation", self.scenario_fairness)
        self.add_scenario("equal-time-step-id-tie-parity", self.scenario_tie_order)
        self.verify_source_snapshot()
        deadlocks_after = self.base.deadlock_count()
        self.report["deadlocksBefore"] = self.deadlocks_before
        self.report["deadlocksAfter"] = deadlocks_after
        self.report["sqlstate40P01Or55P03"] = [
            row for scenario in self.report["scenarios"] for row in json.dumps(scenario).split() if "40P01" in row or "55P03" in row
        ]
        self.report["summary"] = {
            "pass": sum(row["status"] == "pass" for row in self.report["scenarios"]),
            "fail": sum(row["status"] == "fail" for row in self.report["scenarios"]),
            "blocked": sum(row["status"] == "blocked" for row in self.report["scenarios"]),
        }
        self.report["status"] = (
            "pass"
            if self.report["summary"]["fail"] == 0
            and self.report["summary"]["blocked"] == 0
            and deadlocks_after == self.deadlocks_before
            and not self.report["sqlstate40P01Or55P03"]
            else "fail"
        )
        self.report["admissionDecisionNeeded"] = self.report["status"] == "fail" and any(
            row["name"].startswith("cap-") and row["status"] == "fail" for row in self.report["scenarios"]
        )
        return self.report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--expected-head", default=START_SHA)
    parser.add_argument("--postgres-image", default="external")
    parser.add_argument("--postgres-image-id", default="external")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--worker-config", type=Path)
    parser.add_argument("--worker-output", type=Path)
    args = parser.parse_args()
    args.database_url = os.environ.get("R2_INTERNAL_DATABASE_URL")
    if args.worker_config:
        if args.worker_output is None:
            parser.error("--worker-output is required with --worker-config")
    elif not all((args.database_url, args.output, args.repo_root)):
        parser.error("R2_INTERNAL_DATABASE_URL, --output and --repo-root are required")
    return args


def main() -> int:
    args = parse_args()
    if args.worker_config:
        return worker_main(args.worker_config, args.worker_output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    harness = R2Harness(args)
    exit_code = 0
    try:
        harness.setup()
        report = harness.run()
        if report["status"] != "pass":
            exit_code = 1
    except BaseException as error:  # noqa: BLE001
        report = harness.report
        report["status"] = "fail"
        report["fatalError"] = error_json(error)
        report["fatalTraceback"] = traceback.format_exc()
        exit_code = 1
    finally:
        try:
            harness.cleanup()
            report["cleanup"] = "pass"
        except BaseException as error:  # noqa: BLE001
            report["cleanup"] = "fail"
            report["cleanupError"] = error_json(error)
            report["status"] = "fail"
            exit_code = 1
        report["finishedAt"] = utcnow().isoformat()
        serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
        secret_patterns = {
            "lease-token-field": r"lease_token|leaseToken",
            "generated-database-password": r"r2_[0-9a-f]{12}_[0-9a-f]{24}",
            "database-uri-credentials": r"postgres(?:ql)?(?:\+psycopg)?://[^\s/@:]+:[^\s/@]+@",
        }
        secrets_found = [name for name, pattern in secret_patterns.items() if re.search(pattern, serialized)]
        report["secretScan"] = {"status": "pass" if not secrets_found else "fail", "matches": secrets_found}
        if secrets_found:
            report["status"] = "fail"
        serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
        args.output.write_text(serialized)
        if secrets_found:
            exit_code = 1
    return 0 if args.report_only else exit_code
