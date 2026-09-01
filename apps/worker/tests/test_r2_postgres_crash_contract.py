"""Source and pure-oracle contracts for the R2-J crash-recovery proof."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "infra/scripts/run-r2-postgres-multi-worker.py"
SCENARIO = ROOT / "infra/scripts/r2_scenario_j_crash.py"
WORKER = ROOT / "infra/scripts/r2_scenario_j_crash_worker.py"


def load_scenario():
    spec = importlib.util.spec_from_file_location("r2_j_crash_contract", SCENARIO)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_worker():
    spec = importlib.util.spec_from_file_location("r2_j_crash_worker_contract", WORKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _valid_state() -> dict[str, object]:
    scenario = load_scenario()
    timestamp = "2026-09-01T00:00:00+00:00"
    later = "2026-09-01T00:00:01+00:00"
    attempt_common = {
        "checkpoint_artifact_id": None,
        "cost_microunits": 0,
        "heartbeat_at": timestamp,
        "input_sha256": "input-sha",
        "input_tokens": 0,
        "lease_expires_at": None,
        "lease_token_hash": "[redacted]",
        "output_tokens": 0,
        "provider_call_count": 0,
        "started_at": timestamp,
        "step_id": "step",
        "tool_call_count": 0,
        "workspace_id": "workspace",
    }
    event_common = {
        "event_schema_version": "1",
        "run_id": "run",
        "workspace_id": "workspace",
        "created_at": timestamp,
    }
    return {
        "run": {
            "id": "run",
            "status": "running",
            "state_version": 8,
            "next_event_seq": 8,
        },
        "steps": [
            {
                "id": "step",
                "workspace_id": "workspace",
                "run_id": "run",
                "step_kind": "researcher",
                "branch_key": "branch",
                "input_sha256": "input-sha",
                "status": "succeeded",
                "current_attempt_number": 2,
                "state_version": 6,
            },
            {
                "id": "dependent",
                "workspace_id": "workspace",
                "run_id": "run",
                "step_kind": "researcher",
                "branch_key": "dependent-branch",
                "input_sha256": "dependent-input",
                "status": "queued",
                "current_attempt_number": 0,
                "state_version": 2,
            },
        ],
        "attempts": [
            {
                **attempt_common,
                "id": "old",
                "attempt_number": 1,
                "status": "abandoned",
                "error_code": "lease_expired",
                "error_message": "Research Attempt lease expired.",
                "output_sha256": None,
                "worker_instance_id": "j-crash-holder",
                "finished_at": later,
            },
            {
                **attempt_common,
                "id": "replacement",
                "attempt_number": 2,
                "status": "succeeded",
                "error_code": None,
                "error_message": None,
                "output_sha256": scenario.sha("r2-j-replacement-output"),
                "worker_instance_id": "j-replacement-claimer",
                "finished_at": later,
            },
        ],
        "events": [
            {
                **event_common,
                "seq": 1,
                "event_type": "run_status_changed",
                "step_id": None,
                "attempt_id": None,
                "dedupe_key": "worker-run-started:old",
                "payload_json": {
                    "previousStatus": "queued",
                    "status": "running",
                    "runStateVersion": 2,
                    "reasonCode": None,
                },
            },
            {
                **event_common,
                "seq": 2,
                "event_type": "step_started",
                "step_id": "step",
                "attempt_id": "old",
                "dedupe_key": "step-started:old",
                "payload_json": {
                    "stepId": "step",
                    "stepKind": "researcher",
                    "branchKey": "branch",
                    "attemptId": "old",
                    "attemptNumber": 1,
                    "stepStateVersion": 2,
                    "runStateVersion": 3,
                },
            },
            {
                **event_common,
                "seq": 3,
                "event_type": "attempt_abandoned",
                "step_id": "step",
                "attempt_id": "old",
                "dedupe_key": "attempt-abandoned:old",
                "payload_json": {
                    "stepId": "step",
                    "attemptId": "old",
                    "attemptNumber": 1,
                    "reasonCode": "lease_expired",
                    "stepStateVersion": 3,
                    "runStateVersion": 4,
                },
            },
            {
                **event_common,
                "seq": 4,
                "event_type": "step_queued",
                "step_id": "step",
                "attempt_id": None,
                "dedupe_key": "step-queued:step:1",
                "payload_json": {
                    "stepId": "step",
                    "stepKind": "researcher",
                    "branchKey": "branch",
                    "attemptNumber": 1,
                    "stepStateVersion": 4,
                    "runStateVersion": 5,
                },
            },
            {
                **event_common,
                "seq": 5,
                "event_type": "step_started",
                "step_id": "step",
                "attempt_id": "replacement",
                "dedupe_key": "step-started:replacement",
                "payload_json": {
                    "stepId": "step",
                    "stepKind": "researcher",
                    "branchKey": "branch",
                    "attemptId": "replacement",
                    "attemptNumber": 2,
                    "stepStateVersion": 5,
                    "runStateVersion": 6,
                },
            },
            {
                **event_common,
                "seq": 6,
                "event_type": "step_succeeded",
                "step_id": "step",
                "attempt_id": "replacement",
                "dedupe_key": "step-succeeded:replacement",
                "payload_json": {
                    "stepId": "step",
                    "stepKind": "researcher",
                    "attemptId": "replacement",
                    "attemptNumber": 2,
                    "evidenceCount": 0,
                    "artifactIds": [],
                    "stepStateVersion": 6,
                    "runStateVersion": 7,
                },
            },
            {
                **event_common,
                "seq": 7,
                "event_type": "step_queued",
                "step_id": "dependent",
                "attempt_id": None,
                "dedupe_key": "step-queued:dependent:0",
                "payload_json": {
                    "stepId": "dependent",
                    "stepKind": "researcher",
                    "branchKey": "dependent-branch",
                    "attemptNumber": 0,
                    "stepStateVersion": 2,
                    "runStateVersion": 8,
                },
            },
        ],
        "dependencies": [
            {"step_id": "dependent", "depends_on_step_id": "step"}
        ],
    }


def _oracle(state: dict[str, object]):
    return load_scenario().crash_event_oracle(
        state,
        step_id="step",
        dependent_step_id="dependent",
        old_attempt_id="old",
        replacement_attempt_id="replacement",
        expected_output_sha256=load_scenario().sha("r2-j-replacement-output"),
    )


def test_r2_j_is_modular_and_wired_to_the_canonical_runner() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    scenario = SCENARIO.read_text(encoding="utf-8")
    worker = WORKER.read_text(encoding="utf-8")

    assert 'J_CRASH_SCENARIO = ROOT / "infra/scripts/r2_scenario_j_crash.py"' in runner
    assert '"j_crash_recovery"' in runner
    assert "j_crash.run_scenario(" in runner
    assert "claim_specific_research_step(" in worker
    assert 'operation="reclaim"' in scenario
    assert scenario.count('operation="complete"') >= 2
    assert "session_replication_role" not in scenario


def test_r2_j_uses_real_strong_kill_and_database_clock_without_expiry_fixture_edit() -> None:
    scenario = SCENARIO.read_text(encoding="utf-8")
    assert "subprocess.Popen" in scenario
    assert "holder.kill()" in scenario
    assert "Windows TerminateProcess" in scenario
    assert "GetExitCodeProcess" in scenario
    assert "CreateToolhelp32Snapshot" in scenario
    assert "QueryFullProcessImageNameW" in scenario
    assert "GetProcessTimes" in scenario
    assert "launcherIsAncestor" in scenario
    assert "executableMatchesExpectedPython" in scenario
    assert "sameHandleUsedForAliveCheckAndTerminate" in scenario
    assert "clock_timestamp()" in scenario
    assert "expiredByDatabaseClock" in scenario
    assert "lease_expires_at =" not in scenario
    assert 'old_attempt["lease_expires_at"] is not None' in scenario
    assert "normalCleanupMarkerPresent" in scenario


def test_r2_j_lease_tokens_are_secret_ipc_or_environment_only() -> None:
    scenario = SCENARIO.read_text(encoding="utf-8")
    worker = WORKER.read_text(encoding="utf-8")
    assert "CITEFRAME_R2_J_LEASE_SECRET_FILE" in worker
    assert "write_secret_once(secret_path, lease.lease_token)" in worker
    assert "icacls.exe" in worker
    assert '"/inheritance:r"' in worker
    assert '"/save"' in worker
    assert "_split_sddl_aces" in worker
    assert "len(ace_groups) == 3" in worker
    assert 'ace_type == "A"' in worker
    assert 'rights == "FA"' in worker
    assert "len(parsed_aces) == len(ace_groups)" in worker
    assert '"*S-1-5-18:(OI)(CI)(F)"' in worker
    assert '"*S-1-5-32-544:(OI)(CI)(F)"' in worker
    assert "_restrict_windows_secret_file" not in worker
    directory_restriction = worker.index(
        "_restrict_windows_secret_directory(secret_directory)"
    )
    file_creation = worker.index(
        "descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)"
    )
    assert directory_restriction < file_creation
    assert '"fileAclTrusteesExactAtBirth": True' in worker
    assert '"noFileCreateThenRestrictWindow": True' in worker
    assert '"*S-1-3-4"' in worker
    assert "lease-secret-{os.urandom(8).hex()}" in scenario
    assert '"secretIpcDirectoriesDeletedAfterRead"' in scenario
    assert '"verifiedBeforeSecretWrite": True' in worker
    assert '"leaseToken"' not in worker
    assert "print(" not in worker
    assert '"--lease-token"' not in scenario
    assert "lease_token=old_token" in scenario
    assert "lease_token=replacement_token" in scenario
    assert "_assert_secret_scrub(result, secrets)" in scenario
    assert '"stdoutWasEmpty": True' in scenario
    assert '"stderrWasEmpty": True' in scenario


def _validate_fake_dacl(
    dacl: str,
    *,
    expected_ace_flags: str = "OICI",
    require_protected: bool = True,
):
    worker = load_worker()
    return worker._validate_windows_dacl(
        dacl,
        "S-1-5-21-current",
        expected_ace_flags=expected_ace_flags,
        require_protected=require_protected,
    )


def test_r2_j_dacl_parser_accepts_only_the_three_legal_aces() -> None:
    directory = _validate_fake_dacl(
        "D:PAI"
        "(A;OICI;FA;;;BA)"
        "(A;OICI;FA;;;SY)"
        "(A;OICI;FA;;;S-1-5-21-current)"
    )
    assert directory["valid"] is True
    assert directory["actualRuleCount"] == 3
    assert directory["allAcesParsed"] is True
    assert directory["allRulesExplicit"] is True
    assert directory["allRulesAllowFullControl"] is True

    inherited_file = _validate_fake_dacl(
        "D:AI"
        "(A;ID;FA;;;BA)"
        "(A;ID;FA;;;SY)"
        "(A;ID;FA;;;S-1-5-21-current)",
        expected_ace_flags="ID",
        require_protected=False,
    )
    assert inherited_file["valid"] is True
    assert inherited_file["actualRuleCount"] == 3
    assert inherited_file["allAcesParsed"] is True
    assert inherited_file["allRulesInherited"] is True
    assert inherited_file["allRulesAllowFullControl"] is True


@pytest.mark.parametrize(
    ("dacl", "expected_ace_flags", "require_protected"),
    [
        (
            (
                "D:PAI(A;OICI;FA;;;BA)(A;OICI;FA;;;SY)"
                "(A;OICI;FA;;;S-1-5-21-current)(A;OICI;FR;;;OW)"
            ),
            "OICI",
            True,
        ),
        (
            (
                "D:PAI(A;OICI;FA;;;BA)(A;OICI;FA;;;SY)"
                "(A;OICI;FA;;;S-1-5-21-current)(A;OICI;FR;;;BU)"
            ),
            "OICI",
            True,
        ),
        (
            (
                "D:PAI(A;OICI;FA;;;BA)(A;OICI;FA;;;SY)"
                "(A;OICI;FA;;;S-1-5-21-current)(D;OICI;FA;;;BU)"
            ),
            "OICI",
            True,
        ),
        (
            (
                "D:PAI(A;OICI;FA;;;BA)(A;OICI;FA;;;SY)"
                "(A;OICI;FA;;;S-1-5-21-current)"
                "(OA;OICI;FA;11111111-1111-1111-1111-111111111111;;BU)"
            ),
            "OICI",
            True,
        ),
        (
            (
                "D:PAI(A;OICI;FA;;;BA)(A;OICI;FA;;;SY)"
                "(A;OICI;FA;;;S-1-5-21-current)(A;OICI;FA;;;BU"
            ),
            "OICI",
            True,
        ),
        (
            (
                "D:AI(A;ID;FA;;;BA)(A;ID;FA;;;SY)"
                "(A;ID;FA;;;S-1-5-21-current)(A;;FA;;;OW)"
            ),
            "ID",
            False,
        ),
        (
            (
                "D:PAI(A;OICI;FA;;;BA)(A;OICI;FA;;;SY)"
                "(A;OICI;FA;;;S-1-5-21-current)(A;OICIID;FA;;;OW)"
            ),
            "OICI",
            True,
        ),
    ],
    ids=(
        "owner-rights-read",
        "ordinary-trustee-read",
        "deny-ace",
        "object-ace",
        "unparsed-ace",
        "file-extra-explicit",
        "directory-extra-inherited",
    ),
)
def test_r2_j_dacl_parser_rejects_every_extra_or_unparsed_ace(
    dacl: str,
    expected_ace_flags: str,
    require_protected: bool,
) -> None:
    evidence = _validate_fake_dacl(
        dacl,
        expected_ace_flags=expected_ace_flags,
        require_protected=require_protected,
    )
    assert evidence["valid"] is False


@pytest.mark.skipif(os.name != "nt", reason="Windows DACL proof")
def test_r2_j_secret_file_is_born_inside_the_protected_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = load_worker()
    with tempfile.TemporaryDirectory(prefix="citeframe-r2-j-acl-test-") as temporary:
        secret_path = Path(temporary) / "private" / "lease.secret"
        restrict_directory = worker._restrict_windows_secret_directory
        observed: dict[str, bool] = {}

        def observe_restriction(path: Path):
            observed["directoryExisted"] = path.is_dir()
            observed["fileAbsentBeforeDirectoryProtection"] = not secret_path.exists()
            evidence = restrict_directory(path)
            with pytest.raises(FileNotFoundError):
                os.open(secret_path, os.O_RDONLY)
            observed["preopenHandleImpossibleBeforeFileBirth"] = True
            return evidence

        monkeypatch.setattr(
            worker,
            "_restrict_windows_secret_directory",
            observe_restriction,
        )
        evidence = worker.write_secret_once(secret_path, "test-capability")

        assert observed == {
            "directoryExisted": True,
            "fileAbsentBeforeDirectoryProtection": True,
            "preopenHandleImpossibleBeforeFileBirth": True,
        }
        assert evidence["daclProtected"] is True
        assert evidence["fileInheritedFromProtectedDirectory"] is True
        assert evidence["fileAclTrusteesExactAtBirth"] is True
        assert evidence["fileAclEvidence"]["actualRuleCount"] == 3
        assert evidence["fileAclEvidence"]["allAcesParsed"] is True
        assert evidence["fileAclEvidence"]["allRulesInherited"] is True
        assert evidence["fileAclEvidence"]["aceFlagsExact"] is True
        assert evidence["noFileCreateThenRestrictWindow"] is True
        assert secret_path.read_text(encoding="utf-8") == "test-capability\n"
        secret_path.unlink()
        secret_path.parent.rmdir()


def test_r2_j_secret_writer_rejects_a_preexisting_parent_boundary(
    tmp_path: Path,
) -> None:
    worker = load_worker()
    secret_path = tmp_path / "preexisting" / "lease.secret"
    secret_path.parent.mkdir()

    with pytest.raises(FileExistsError):
        worker.write_secret_once(secret_path, "test-capability")

    assert not secret_path.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows DACL proof")
def test_r2_j_secret_writer_removes_the_private_directory_on_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = load_worker()
    secret_path = tmp_path / "private-on-error" / "lease.secret"

    def fail_restriction(_path: Path):
        raise RuntimeError("injected ACL failure")

    monkeypatch.setattr(
        worker,
        "_restrict_windows_secret_directory",
        fail_restriction,
    )
    with pytest.raises(RuntimeError, match="injected ACL failure"):
        worker.write_secret_once(secret_path, "test-capability")

    assert not secret_path.exists()
    assert not secret_path.parent.exists()


def test_crash_event_oracle_accepts_only_the_complete_lifecycle() -> None:
    oracle = _oracle(_valid_state())
    assert oracle["sequencesContiguousFromOne"] is True
    assert oracle["dedupeKeysUnique"] is True
    assert oracle["strictCrashRecoveryOrder"] is True
    assert oracle["attemptLifecycleValid"] is True
    assert oracle["attemptFieldsExact"] is True
    assert oracle["uniqueReplacementTerminal"] is True
    assert oracle["eventRowsExact"] is True
    assert oracle["eventPayloadsExact"] is True
    assert oracle["runAndStepStateVersionsExact"] is True


def test_crash_event_oracle_rejects_wrong_event_order() -> None:
    state = _valid_state()
    events = state["events"]
    events[2]["seq"], events[3]["seq"] = events[3]["seq"], events[2]["seq"]
    oracle = _oracle(state)
    assert oracle["sequencesContiguousFromOne"] is False
    assert oracle["strictCrashRecoveryOrder"] is False


def test_crash_event_oracle_rejects_duplicate_terminal() -> None:
    state = _valid_state()
    duplicate = dict(state["events"][5])
    duplicate["seq"] = 8
    duplicate["dedupe_key"] = "duplicate-terminal"
    state["events"].append(duplicate)
    oracle = _oracle(state)
    assert oracle["uniqueReplacementTerminal"] is False
    assert oracle["strictCrashRecoveryOrder"] is False


def test_crash_event_oracle_rejects_invalid_attempt_facts() -> None:
    state = _valid_state()
    state["attempts"][0]["error_code"] = "provider_timeout"
    oracle = _oracle(state)
    assert oracle["attemptLifecycleValid"] is False


def test_crash_event_oracle_rejects_wrong_output_and_event_payload_versions() -> None:
    state = _valid_state()
    state["attempts"][1]["output_sha256"] = "wrong-output"
    state["events"][4]["payload_json"]["runStateVersion"] = 999
    oracle = _oracle(state)
    assert oracle["attemptLifecycleValid"] is False
    assert oracle["eventPayloadsExact"] is False


def _stage_state(dependent_status: str, *, attempts: int, queued_events: int):
    state = _valid_state()
    state["steps"][1]["status"] = dependent_status
    state["attempts"] = [
        {
            "id": f"dependent-attempt-{index}",
            "step_id": "dependent",
            "attempt_number": index + 1,
        }
        for index in range(attempts)
    ]
    state["events"] = [
        {
            "seq": index + 1,
            "event_type": "step_queued",
            "step_id": "dependent",
        }
        for index in range(queued_events)
    ]
    return state


def test_dependent_stage_oracle_rejects_premature_queue_attempt_and_dependency_drift() -> None:
    scenario = load_scenario()
    valid_stages = {
        name: _stage_state("pending", attempts=0, queued_events=0)
        for name in (
            "oldClaimCommitted",
            "afterKill",
            "afterDatabaseExpiry",
            "afterReclaim",
            "replacementClaimCommitted",
            "afterLateOldCompletion",
        )
    }
    valid_stages["afterReplacementCompletion"] = _stage_state(
        "queued", attempts=0, queued_events=1
    )
    accepted = scenario.dependent_stage_oracle(
        valid_stages,
        upstream_step_id="step",
        dependent_step_id="dependent",
    )
    assert accepted["valid"] is True

    premature = {key: dict(value) for key, value in valid_stages.items()}
    premature["afterKill"] = _stage_state("queued", attempts=1, queued_events=1)
    premature["afterReclaim"]["dependencies"] = []
    rejected = scenario.dependent_stage_oracle(
        premature,
        upstream_step_id="step",
        dependent_step_id="dependent",
    )
    assert rejected["valid"] is False
    assert rejected["dependencyExactAtEveryStage"] is False


def test_process_lock_diagnostics_rejects_real_lock_timeout_sqlstate() -> None:
    scenario = load_scenario()
    accepted = scenario.derive_process_lock_diagnostics(
        [
            {
                "workerInstanceId": "one",
                "lockTimeoutSetting": "0",
                "sqlState": None,
            }
        ]
    )
    assert accepted["lockTimeoutsObserved"] == 0
    assert accepted["valid"] is True
    rejected = scenario.derive_process_lock_diagnostics(
        [
            {
                "workerInstanceId": "timed-out",
                "lockTimeoutSetting": "250ms",
                "sqlState": "55P03",
            }
        ]
    )
    assert rejected["lockTimeoutsObserved"] == 1
    assert rejected["lockTimeoutWorkerInstanceIds"] == ["timed-out"]
    assert rejected["valid"] is False


def test_r2_j_records_live_backend_locks_zero_mutation_and_source_hashes() -> None:
    scenario = SCENARIO.read_text(encoding="utf-8")
    for phrase in (
        "pg_stat_activity",
        "pg_locks",
        'lock["lockType"] == "advisory"',
        '"lateCompletionZeroMutation"',
        '"productionSourceSha256Before"',
        '"productionSourceSha256After"',
        "derive_process_lock_diagnostics(process_records)",
        '"dependentStageOracle"',
        '"processDerivedLockTimeoutEvidence"',
    ):
        assert phrase in scenario
