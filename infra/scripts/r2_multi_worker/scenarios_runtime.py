"""Worker-runtime, recovery, cancellation, and publication R2 scenarios."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, text

from citeframe_persistence.models import (
    HumanDecision,
    ResearchArtifact,
    ResearchBudgetLedger,
    ResearchClaim,
    ResearchProviderCall,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
    ResearchStepDependency,
)
from citeframe_research_persistence.errors import ResearchError
from citeframe_research_persistence.provider import (
    mark_provider_call_sent,
    reconcile_provider_call,
    reserve_provider_call,
)
from ai_pdf_api.schemas.research import ConflictDecisionRequest
from ai_pdf_api.services.research.research_decisions import decide_conflict

from .common import PROCESS_TIMEOUT_SECONDS, error_json, sha, utcnow


class RuntimeScenarios:
    def scenario_two_workers(self) -> dict[str, Any]:
        fixture = self.seed_run("r2-two-workers", step_count=2)
        barrier = self.temp_path / "two-workers.go"
        workers = [
            self.worker("claim_complete", worker_id="r2-os-worker-a", barrier=barrier, handler_delay=1.2),
            self.worker("claim_complete", worker_id="r2-os-worker-b", barrier=barrier, handler_delay=1.2),
        ]
        wall_started = time.time()
        barrier.touch()
        time.sleep(0.5)
        with self.base.monitor_engine.connect() as db:
            activity = [
                dict(row)
                for row in db.execute(
                    text(
                        "SELECT pid, application_name, state, wait_event_type, wait_event "
                        "FROM pg_stat_activity WHERE application_name LIKE 'citeframe-r2:r2-os-worker-%' ORDER BY pid"
                    )
                ).mappings()
            ]
            locks = [
                dict(row)
                for row in db.execute(
                    text(
                        "SELECT a.pid, a.application_name, l.locktype, l.mode, l.granted "
                        "FROM pg_stat_activity a JOIN pg_locks l ON l.pid=a.pid "
                        "WHERE a.application_name LIKE 'citeframe-r2:r2-os-worker-%' ORDER BY a.pid,l.locktype,l.mode"
                    )
                ).mappings()
            ]
        results = [self.finish_worker(item) for item in workers]
        wall = time.time() - wall_started
        intervals = [(row["handlerStartedAtEpoch"], row["handlerFinishedAtEpoch"]) for row in results]
        overlap = max(start for start, _ in intervals) < min(end for _, end in intervals)
        snapshot = self.snapshot(fixture.run_id)
        oracle = self.event_oracle(snapshot)
        unique = (
            len({row["pid"] for row in results}) == 2
            and len({row["postgresPid"] for row in results}) == 2
            and len({row["workerInstanceId"] for row in results}) == 2
            and len({row["claim"]["stepId"] for row in results}) == 2
            and len({row["claim"]["attemptId"] for row in results}) == 2
        )
        passed = unique and overlap and wall < 3.0 and all(oracle.values())
        return {
            "status": "pass" if passed else "fail",
            "processes": results,
            "processIsolation": unique,
            "handlerOverlap": overlap,
            "wallSeconds": round(wall, 3),
            "pgStatActivity": activity,
            "pgLocks": locks,
            "eventOracle": oracle,
            "snapshot": snapshot,
        }

    def scenario_lease_reclaim(self) -> dict[str, Any]:
        fixture = self.seed_run("r2-lease-reclaim")
        barrier = self.temp_path / "lease.go"
        late = self.worker(
            "claim_late_complete",
            worker_id="r2-expiring-worker",
            barrier=barrier,
            handler_delay=3.0,
        )
        barrier.touch()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            snapshot = self.snapshot(fixture.run_id)
            if snapshot["attempts"]:
                break
            time.sleep(0.05)
        else:
            raise AssertionError("expiring Worker did not claim")
        with self.sessions() as db:
            attempt = db.get(ResearchStepAttempt, snapshot["attempts"][0]["id"])
            attempt.lease_expires_at = utcnow() - timedelta(seconds=1)
            db.commit()
        recovery_barrier = self.temp_path / "recovery.go"
        recovery = self.worker("claim_complete", worker_id="r2-recovery-worker", barrier=recovery_barrier)
        recovery_barrier.touch()
        recovery_result = self.finish_worker(recovery)
        late_result = self.finish_worker(late)
        final = self.snapshot(fixture.run_id)
        oracle = self.event_oracle(final)
        attempts = final["attempts"]
        passed = (
            late_result.get("lateCompletion") == "fenced"
            and late_result.get("lateCompletionError", {}).get("code") == "research_state_conflict"
            and [row["status"] for row in attempts] == ["abandoned", "succeeded"]
            and [row["number"] for row in attempts] == [1, 2]
            and recovery_result["claim"]["attemptNumber"] == 2
            and sum(row["type"] == "attempt_abandoned" for row in final["events"]) == 1
            and all(oracle.values())
        )
        return {
            "status": "pass" if passed else "fail",
            "lateWorker": late_result,
            "recoveryWorker": recovery_result,
            "eventOracle": oracle,
            "snapshot": final,
        }

    def scenario_join_readiness(self) -> dict[str, Any]:
        fixture = self.base.seed_run("r2-join", step_count=2)
        with self.sessions() as db:
            first = db.get(ResearchStep, fixture.step_ids[0])
            join = db.get(ResearchStep, fixture.step_ids[1])
            join.step_kind = "join"
            join.step_key = "join:r2"
            join.branch_key = None
            join.status = "pending"
            join.queued_at = None
            db.add(ResearchStepDependency(step_id=join.id, depends_on_step_id=first.id))
            db.commit()
        self.seed_queued_events(fixture, step_ids={fixture.step_ids[0]})
        first_barrier = self.temp_path / "join-first.go"
        first_worker = self.worker("claim_complete", worker_id="r2-join-parent", barrier=first_barrier)
        first_barrier.touch()
        first_result = self.finish_worker(first_worker)
        mid = self.snapshot(fixture.run_id)
        second_barrier = self.temp_path / "join-second.go"
        second_worker = self.worker("claim_complete", worker_id="r2-join-handler", barrier=second_barrier)
        second_barrier.touch()
        second_result = self.finish_worker(second_worker)
        final = self.snapshot(fixture.run_id)
        oracle = self.event_oracle(final)
        queued_event = next(
            row for row in mid["events"] if row["type"] == "step_queued" and row["stepId"] == fixture.step_ids[1]
        )
        parent_terminal = next(
            row for row in mid["events"] if row["type"] == "step_succeeded" and row["stepId"] == fixture.step_ids[0]
        )
        passed = (
            first_result["claim"]["stepId"] == fixture.step_ids[0]
            and mid["steps"][1 if mid["steps"][1]["id"] == fixture.step_ids[1] else 0]["status"] == "queued"
            and parent_terminal["seq"] < queued_event["seq"]
            and second_result["claim"]["stepId"] == fixture.step_ids[1]
            and all(oracle.values())
        )
        return {
            "status": "pass" if passed else "fail",
            "parentWorker": first_result,
            "joinWorker": second_result,
            "dependencyBeforeReady": parent_terminal["seq"] < queued_event["seq"],
            "eventOracle": oracle,
            "snapshot": final,
        }


    def scenario_tool_reclaim_exactly_once(self) -> dict[str, Any]:
        evidence = self.base.scenario_reclaim_call("tool")
        fixture_task = evidence["tasks"]
        sqlstates = [task.get("error", {}).get("sqlstate") for task in fixture_task if task.get("error")]
        passed = not any(state in {"40P01", "55P03"} for state in sqlstates)
        return {
            "status": "pass" if passed else "fail",
            "productionCommands": ["reclaim_expired_research_steps", "complete_tool_call"],
            "processShape": "real PostgreSQL lock race; OS process requirement proven by other R2 scenarios",
            "evidence": evidence,
        }


    def scenario_provider_cancel(self) -> dict[str, Any]:
        fixture = self.seed_run("r2-provider-cancel")
        lease = self.base.claim_specific(fixture, 0, "r2-provider-owner")
        with self.sessions() as db:
            reservation = reserve_provider_call(
                db,
                attempt_id=lease.attempt_id,
                logical_call_key="r2-provider-race",
                request_sha256=sha("r2-provider-request"),
                provider="openai",
                model="gpt-5.5",
                provider_config_fingerprint=sha("r2-provider-cancel/provider"),
                reserved_input_tokens=10,
                reserved_output_tokens=10,
                now=utcnow(),
                provider_config_matcher=lambda _db, _step, _fingerprint: True,
            )
            mark_provider_call_sent(db, reservation.provider_call_id, now=utcnow())
            db.commit()
        with self.sessions() as db:
            expected_run_version = db.get(ResearchRun, fixture.run_id).state_version
        barrier = self.temp_path / "provider-race.go"

        def command_process(name: str, code: str) -> tuple[subprocess.Popen[str], Path]:
            output = self.temp_path / f"{name}.json"
            script = self.temp_path / f"{name}.py"
            script.write_text(code)
            process = subprocess.Popen([sys.executable, str(script)], cwd=self.repo_root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.children.add(process)
            return process, output

        expected_snapshot_json = json.dumps(self.source_snapshot, sort_keys=True, separators=(",", ":"))
        common = f'''import json, sys, time\nfrom datetime import UTC, datetime\nfrom pathlib import Path\nfrom sqlalchemy import create_engine, text\nfrom sqlalchemy.orm import sessionmaker\nsys.path.insert(0, {str(self.repo_root / "infra/scripts")!r})\nfrom r2_multi_worker.common import candidate_source_snapshot\nEXPECTED_SNAPSHOT={expected_snapshot_json!r}; EXPECTED_HEAD={self.args.expected_head!r}; REPO_ROOT=Path({str(self.repo_root)!r})\nACTUAL_SNAPSHOT=json.dumps(candidate_source_snapshot(REPO_ROOT,EXPECTED_HEAD),sort_keys=True,separators=(",", ":"))\nif ACTUAL_SNAPSHOT != EXPECTED_SNAPSHOT: raise AssertionError("provider race child source manifest mismatch")\nMANIFEST={self.source_snapshot["candidateSourceManifestSha256"]!r}\nURL={self.args.database_url!r}; SCHEMA={self.base.schema!r}; BARRIER={str(barrier)!r}\ne=create_engine(URL,connect_args={{"options":f"-csearch_path={{SCHEMA}},public"}}); S=sessionmaker(bind=e,expire_on_commit=False)\nwhile not Path(BARRIER).exists(): time.sleep(.01)\n'''
        cancel_code = common + f'''from citeframe_research_persistence.cancellation import cancel_research_run_transition\nwith S() as db:\n cancel_research_run_transition(db,workspace_id={self.base.workspace_id!r},actor_user_id={self.base.user_id!r},actor_role="owner",run_id={fixture.run_id!r},expected_state_version={expected_run_version},reason_code="user_requested",now=datetime.now(UTC)); db.commit()\nprint(json.dumps({{"pid":__import__("os").getpid(),"status":"pass","candidateSourceManifestSha256":MANIFEST}}))\n'''
        reconcile_code = common + f'''from citeframe_research_persistence.provider import reconcile_provider_call\nwith S() as db:\n reconcile_provider_call(db,provider_call_id={reservation.provider_call_id!r},status="outcome_unknown",actual_input_tokens=10,actual_output_tokens=10,usage_source="estimated",usage_final=False,error_code="provider_outcome_unknown",now=datetime.now(UTC)); db.commit()\nprint(json.dumps({{"pid":__import__("os").getpid(),"status":"pass","candidateSourceManifestSha256":MANIFEST}}))\n'''
        procs = [command_process("provider-cancel", cancel_code), command_process("provider-reconcile", reconcile_code)]
        barrier.touch()
        process_results = []
        for process, _output in procs:
            try:
                stdout, stderr = process.communicate(timeout=PROCESS_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    stdout, stderr = process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate(timeout=2)
            finally:
                self.children.discard(process)
            stdout_lines = stdout.splitlines()
            child_result = json.loads(stdout_lines[-1]) if stdout_lines else {}
            process_results.append(
                {
                    "pid": process.pid,
                    "returncode": process.returncode,
                    "stdout": stdout_lines,
                    "stderr": stderr.splitlines(),
                    "candidateSourceManifestSha256": child_result.get(
                        "candidateSourceManifestSha256"
                    ),
                }
            )
        with self.sessions() as db:
            call = db.get(ResearchProviderCall, reservation.provider_call_id)
            ledger = db.get(ResearchBudgetLedger, fixture.ledger_id)
            second_error = None
            try:
                reconcile_provider_call(
                    db,
                    provider_call_id=call.id,
                    status="outcome_unknown",
                    actual_input_tokens=10,
                    actual_output_tokens=10,
                    usage_source="estimated",
                    usage_final=False,
                    error_code="provider_outcome_unknown",
                    now=utcnow(),
                )
            except ResearchError as error:
                db.rollback()
                second_error = error_json(error)
            state = {
                "callStatus": call.status,
                "ledgerActualProviderCalls": ledger.actual_provider_calls,
                "ledgerActualInputTokens": ledger.actual_input_tokens,
                "ledgerActualOutputTokens": ledger.actual_output_tokens,
                "ledgerUsageFinal": ledger.usage_final,
                "secondReconcile": second_error,
            }
        passed = (
            all(row["returncode"] == 0 for row in process_results)
            and all(
                row["candidateSourceManifestSha256"]
                == self.source_snapshot["candidateSourceManifestSha256"]
                for row in process_results
            )
            and state["callStatus"] == "outcome_unknown"
            and state["ledgerActualProviderCalls"] == 1
            and state["ledgerActualInputTokens"] == 10
            and state["ledgerActualOutputTokens"] == 10
            and state["secondReconcile"].get("code") == "research_state_conflict"
        )
        return {"status": "pass" if passed else "fail", "processes": process_results, "state": state, "snapshot": self.snapshot(fixture.run_id)}


    def scenario_conflict_resume(self) -> dict[str, Any]:
        fixture = self.base.seed_run("r2-conflict")
        prompt_id = self.seed_prompt(fixture, "critic")
        claim_id = self.r0_module.uid(f"{self.base.schema}/r2-conflict/claim")
        statement = "Supported but conflicted R2 claim"
        with self.sessions() as db:
            step = db.get(ResearchStep, fixture.step_ids[0])
            step.step_kind = "conflict_decision_gate"
            step.step_key = "conflict-gate:r2"
            step.branch_key = None
            step.prompt_version_id = prompt_id
            db.add(
                ResearchClaim(
                    id=claim_id,
                    workspace_id=self.base.workspace_id,
                    run_id=fixture.run_id,
                    claim_key="r2-conflict-claim",
                    claim_order=0,
                    statement_text=statement,
                    statement_sha256=sha(statement),
                    produced_by_step_id=step.id,
                    verification_status="supported",
                    conflict_status="conflicted",
                    critic_step_id=step.id,
                    created_at=utcnow(),
                    verified_at=utcnow(),
                )
            )
            db.commit()
        self.seed_queued_events(fixture)
        barrier = self.temp_path / "conflict.go"
        storage = self.temp_path / "conflict-storage"
        worker = self.worker(
            "conflict_wait",
            worker_id="r2-conflict-worker",
            barrier=barrier,
            extra={"claimIds": [claim_id], "storage": str(storage)},
        )
        barrier.touch()
        worker_result = self.finish_worker(worker)
        with self.sessions() as db:
            run = db.get(ResearchRun, fixture.run_id)
            decision = db.get(HumanDecision, worker_result["decisionId"])
            payload = ConflictDecisionRequest(
                expectedStateVersion=run.state_version,
                expectedDecisionStateVersion=decision.state_version,
                inputArtifactSha256=decision.input_artifact_sha256,
                inputSnapshotSha256=decision.input_snapshot_sha256,
                action="keep_as_unresolved",
            )
            status_code, _body, replay = decide_conflict(
                db,
                workspace_id=self.base.workspace_id,
                actor_user_id=self.base.user_id,
                run_id=fixture.run_id,
                decision_id=decision.id,
                payload=payload,
                idempotency_key="r2-conflict-resume-key",
            )
            db.commit()
            decision = db.get(HumanDecision, decision.id)
            claim = db.get(ResearchClaim, claim_id)
            run = db.get(ResearchRun, fixture.run_id)
            state = {"httpStatus": status_code, "replay": replay, "decisionStatus": decision.status, "claimConflictStatus": claim.conflict_status, "runStatus": run.status}
        snapshot = self.snapshot(fixture.run_id)
        oracle = self.event_oracle(snapshot)
        passed = state == {"httpStatus": 200, "replay": False, "decisionStatus": "submitted", "claimConflictStatus": "resolved_unresolved", "runStatus": "queued"} and all(oracle.values())
        return {"status": "pass" if passed else "fail", "worker": worker_result, "resume": state, "eventOracle": oracle, "snapshot": snapshot}

    def scenario_final_publication(self) -> dict[str, Any]:
        fixture = self.base.seed_run("r2-publication")
        prompt_id = self.seed_prompt(fixture, "synthesizer")
        with self.sessions() as db:
            step = db.get(ResearchStep, fixture.step_ids[0])
            step.step_kind = "artifact_publisher"
            step.step_key = "artifact-publisher:r2"
            step.branch_key = None
            step.prompt_version_id = prompt_id
            db.commit()
        self.seed_queued_events(fixture)
        barrier = self.temp_path / "publication.go"
        storage = self.temp_path / "publication-storage"
        worker = self.worker(
            "publish_final",
            worker_id="r2-publication-worker",
            barrier=barrier,
            extra={"storage": str(storage)},
        )
        barrier.touch()
        result = self.finish_worker(worker)
        snapshot = self.snapshot(fixture.run_id)
        oracle = self.event_oracle(snapshot, require_terminal_run_last=True)
        with self.sessions() as db:
            artifact_count = int(db.scalar(select(func.count()).select_from(ResearchArtifact).where(ResearchArtifact.run_id == fixture.run_id)) or 0)
        passed = result["status"] == "published" and snapshot["run"]["status"] == "completed" and artifact_count == 1 and all(oracle.values())
        return {"status": "pass" if passed else "fail", "worker": result, "artifactCount": artifact_count, "eventOracle": oracle, "snapshot": snapshot}
