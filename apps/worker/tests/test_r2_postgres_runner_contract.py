"""Contract checks for the R2 real-process PostgreSQL proof runner."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
WORKER = ROOT / "infra/scripts/r2_worker_entry.py"
RUNNER = ROOT / "infra/scripts/run-r2-postgres-multi-worker.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("r2_runner_contract", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_r2_runner_uses_real_subprocesses_and_explicit_file_barrier() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert "subprocess.Popen" in source
    assert "TemporaryDirectory" in source
    assert "ready-file" in source and "release-file" in source
    assert "threading" not in source
    assert "Thread(" not in source


def test_r2_worker_constructs_own_engine_sessions_and_calls_production_paths() -> None:
    source = WORKER.read_text(encoding="utf-8")
    assert "create_engine(database_url" in source
    assert "sessionmaker(bind=engine" in source
    assert "SELECT pg_backend_pid()" in source
    assert 'os.environ.get(args.database_url_env)' in source
    assert 'os.environ.get(args.lease_token_env)' in source
    assert 'parser.add_argument("--database-url"' not in source
    assert 'parser.add_argument("--lease-token")' not in source
    assert "claim_specific_research_step" in source
    assert "claim_next_research_step" in source
    assert "ResearchWorkProcessor" in source
    assert "reclaim_expired_research_steps" in source
    assert "complete_research_step" in source
    assert "build_worker_research_service" in source
    assert "reserve_provider_call" in source
    assert "mark_provider_call_sent" in source
    assert "reconcile_provider_call" in source
    assert "begin_tool_call" in source
    assert "complete_tool_call" in source
    for field in (
        "scenario",
        "operation",
        "workerInstanceId",
        "osPid",
        "pgBackendPid",
        "argv",
        "exitStatus",
    ):
        assert f'"{field}"' in source


def test_r2_validation_rejects_thread_like_or_shared_identities() -> None:
    runner = load_runner()
    argv = {"one": ["--worker-instance-id", "one"], "two": ["--worker-instance-id", "two"]}
    shared_os_pid = [
        {"scenario": "identity_probe", "workerInstanceId": "one", "osPid": 10, "pgBackendPid": 21, "argv": argv["one"], "exitStatus": 0, "controllerObservedExitStatus": 0},
        {"scenario": "identity_probe", "workerInstanceId": "two", "osPid": 10, "pgBackendPid": 22, "argv": argv["two"], "exitStatus": 0, "controllerObservedExitStatus": 0},
    ]
    with pytest.raises(AssertionError, match="distinct OS subprocess PIDs"):
        runner.validate_process_records(shared_os_pid, argv, "identity_probe")


def test_r2_artifact_hash_and_cleanup_contract(tmp_path: Path) -> None:
    runner = load_runner()
    hashes = runner.candidate_file_hashes()
    assert hashes == {
        str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in runner.CANDIDATE_FILES
    }
    assert "packages/research-persistence/src/citeframe_research_persistence/lease.py" in hashes
    assert "apps/worker/src/ai_pdf_worker/research_runtime_processor.py" in hashes
    assert "infra/scripts/r2_scenario_l_budget.py" in hashes
    assert "infra/scripts/r2_scenario_l_worker.py" in hashes
    output = tmp_path / "nested" / "r2.json"
    payload = b'{"cleanup":{"forceDropSucceeded":true},"passed":true}\n'
    runner.atomic_write(output, payload)
    assert output.read_bytes() == payload
    assert not output.with_suffix(output.suffix + ".tmp").exists()


def test_r2_runner_source_has_all_process_scenario_evidence_contract() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert any(isinstance(node, ast.Try) for node in ast.walk(tree))
    for scenario in (
        "identity_probe",
        "a_same_step_claim",
        "b_processor_exclusion",
        "c_cap_n",
        "d_step_id_tiebreak",
        "e_lease_reclaim_late_completion",
        "f_cancel_races",
        "g_provider_reconcile",
        "h_join_readiness",
        "l_budget_exhaustion_reconcile",
    ):
        assert f'"{scenario}"' in source
    for field in (
        "schemaVersion",
        "baseSha",
        "candidateHeadSha",
        "candidateFileHashes",
        "exactCommand",
        "environment",
        "processRecords",
        "dbProjection",
        "locks",
        "assertions",
        "cleanup",
        "payloadWithoutHashFieldSha256",
        "forceDropSucceeded",
        "qualityEvidence",
    ):
        assert f'"{field}"' in source
    assert "DROP DATABASE IF EXISTS" in source and "WITH (FORCE)" in source
    assert "r15.aggregate_snapshot" in source and "r15.set_cap" in source


def test_r2_runner_fails_closed_about_incomplete_k_coverage() -> None:
    runner = load_runner()
    assert runner.BLOCKED_SCENARIOS == ("k_publication_outcome_unknown",)
    assert "k_publication_outcome_unknown" not in runner.SCENARIOS
    source = RUNNER.read_text(encoding="utf-8")
    assert '"blockedScenarios": list(BLOCKED_SCENARIOS)' in source
    assert '"r2Complete": False' in source
    assert '"qualityEvidence": False' in source


def test_r2_g_contract_covers_provider_and_tool_recovery_without_controller_mutation() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    for evidence_key in (
        "reservedUnsent",
        "sentCancelDualReconcile",
        "sentLeaseReclaim",
        "toolCancelDualComplete",
        "toolLeaseReclaim",
        "providerUsageNotDuplicated",
        "toolAccountingNotDuplicated",
    ):
        assert f'"{evidence_key}"' in source
    assert '"operation": "reserve_provider"' in source
    assert '"operation": "mark_sent"' in source
    assert source.count('"operation": "reconcile"') >= 4
    assert '"operation": "begin_tool"' in source
    assert source.count('"operation": "complete_tool"') >= 4
    assert "from citeframe_research_persistence.provider import reserve_provider_call" not in source
    assert "from citeframe_research_persistence.tools import begin_tool_call" not in source


def test_r2_projection_and_event_oracle_use_persisted_sequence_order() -> None:
    runner = load_runner()
    assert runner.event_sequence_oracle({"events": [{"seq": 1}, {"seq": 2}]}) == {
        "eventSequences": [1, 2],
        "unique": True,
        "strictlyOrdered": True,
    }
    assert runner.event_sequence_oracle({"events": [{"seq": 2}, {"seq": 1}]}) == {
        "eventSequences": [2, 1],
        "unique": True,
        "strictlyOrdered": False,
    }
    source = RUNNER.read_text(encoding="utf-8")
    assert 'state["events"] = sorted(' in source
    assert 'key=lambda event: int(event["seq"])' in source


def test_r2_artifact_redacts_database_and_lease_secrets() -> None:
    runner = load_runner()
    database_url = "postgresql+psycopg://user:secret@127.0.0.1:5432/database"
    command = runner.redacted_cli_command(
        ["runner.py", "--database-url", database_url, "--scenario", "all"]
    )
    assert command == [
        "runner.py",
        "--database-url",
        "[redacted]",
        "--scenario",
        "all",
    ]
    payload = runner.redact_sensitive_payload(
        {"command": command, "error": f"failed against {database_url} using secret"},
        {database_url, "secret"},
    )
    assert database_url not in str(payload)
    assert "secret" not in str(payload)

    runner_source = RUNNER.read_text(encoding="utf-8")
    worker_source = WORKER.read_text(encoding="utf-8")
    assert '"--database-url", database_url' not in runner_source
    assert '"leaseToken": "--lease-token"' not in runner_source
    assert '"--database-url-env", "CITEFRAME_R2_DATABASE_URL"' in runner_source
    assert '"--lease-token-env", "CITEFRAME_R2_LEASE_TOKEN"' in runner_source
    assert 'attempt["lease_token_hash"] = "[redacted]"' in runner_source
    assert "readyBarrierBackendObservation" in runner_source
    assert "live_worker_backends_at_ready_barrier" in runner_source
    assert "sys.argv[1:]" in worker_source
