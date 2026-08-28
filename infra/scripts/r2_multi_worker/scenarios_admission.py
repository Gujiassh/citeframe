"""Per-Run admission, fairness, and deterministic-order R2 scenarios."""
from __future__ import annotations

import time
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text

from citeframe_persistence.models import ResearchStep, ResearchStepAttempt

from .common import utcnow


class AdmissionScenarios:
    def effective_researcher_attempts(self, run_id: str) -> int:
        with self.sessions() as db:
            return int(
                db.scalar(
                    select(func.count())
                    .select_from(ResearchStepAttempt)
                    .join(ResearchStep, ResearchStep.id == ResearchStepAttempt.step_id)
                    .where(
                        ResearchStep.run_id == run_id,
                        ResearchStep.step_kind == "researcher",
                        ResearchStepAttempt.status == "running",
                        ResearchStepAttempt.lease_expires_at > func.now(),
                    )
                )
                or 0
            )

    def start_concurrent_workers(
        self,
        *,
        action: str,
        worker_ids: list[str],
        barrier_name: str,
        handler_delay: float = 0,
    ) -> list[tuple[Any, Path, Path]]:
        barrier = self.temp_path / barrier_name
        workers = [
            self.worker(
                action,
                worker_id=worker_id,
                barrier=barrier,
                handler_delay=handler_delay,
            )
            for worker_id in worker_ids
        ]
        barrier.touch()
        return workers

    def scenario_cap(self, cap: int) -> dict[str, Any]:
        fixture = self.seed_run(f"r2-cap-{cap}", step_count=cap + 1)
        self.set_cap(fixture, cap)
        workers = self.start_concurrent_workers(
            action="claim_only",
            worker_ids=[f"r2-cap-{cap}-worker-{index + 1}" for index in range(cap + 1)],
            barrier_name=f"r2-cap-{cap}.go",
        )
        effective_samples: list[int] = []
        while any(process.poll() is None for process, _output, _barrier in workers):
            effective_samples.append(self.effective_researcher_attempts(fixture.run_id))
            time.sleep(0.01)
        results = [self.finish_worker(worker) for worker in workers]
        effective_after = self.effective_researcher_attempts(fixture.run_id)
        effective_samples.append(effective_after)
        max_effective = max(effective_samples, default=effective_after)
        claimed = [row for row in results if row.get("claim") is not None]
        no_work = [row for row in results if row.get("status") == "no_work"]
        all_claims_target_run = all(row["claim"]["runId"] == fixture.run_id for row in claimed)
        unique_claims = (
            len({row["claim"]["stepId"] for row in claimed}) == len(claimed)
            and len({row["claim"]["attemptId"] for row in claimed}) == len(claimed)
        )
        process_ids_unique = len({row["pid"] for row in results}) == len(results)
        worker_start_spread_ms = round(
            (max(row["startedAtEpoch"] for row in results) - min(row["startedAtEpoch"] for row in results))
            * 1000,
            3,
        )
        simultaneous_barrier_release = process_ids_unique and worker_start_spread_ms < 1000
        never_exceeded = max_effective <= cap and effective_after <= cap
        passed = (
            never_exceeded
            and simultaneous_barrier_release
            and effective_after == cap
            and len(claimed) == cap
            and len(no_work) == 1
            and all_claims_target_run
            and unique_claims
        )
        snapshot = self.snapshot(fixture.run_id)
        return {
            "status": "pass" if passed else "fail",
            "expectedCap": cap,
            "simultaneousWorkerCount": len(workers),
            "workerProcessIdsUnique": process_ids_unique,
            "workerStartSpreadMs": worker_start_spread_ms,
            "simultaneousBarrierRelease": simultaneous_barrier_release,
            "claimedWorkerCount": len(claimed),
            "noWorkWorkerCount": len(no_work),
            "effectiveAttemptSampleCount": len(effective_samples),
            "observedEffectiveAttemptCounts": sorted(set(effective_samples)),
            "maxEffectiveUnexpiredResearcherAttempts": max_effective,
            "effectiveUnexpiredResearcherAttemptsAfterContention": effective_after,
            "capNeverExceededDuringOrAfterContention": never_exceeded,
            "workers": results,
            "snapshot": snapshot,
            "rootCause": None if passed else "concurrent per-Run admission invariant failed",
            "authorizationBlocker": None,
        }

    def scenario_expired_slot_atomic(self) -> dict[str, Any]:
        fixture = self.seed_run("r2-expired-slot", step_count=2)
        self.set_cap(fixture, 1)
        first = self.claim_only("r2-expired-slot-owner")
        with self.sessions() as db:
            attempt = db.get(ResearchStepAttempt, first["claim"]["attemptId"])
            attempt.lease_expires_at = utcnow() - timedelta(seconds=1)
            db.commit()
        recovery = self.claim_only("r2-expired-slot-recovery")
        snapshot = self.snapshot(fixture.run_id)
        effective = sum(
            row["status"] == "running" and row["leaseExpiresAt"] is not None
            for row in snapshot["attempts"]
        )
        statuses = [row["status"] for row in snapshot["attempts"]]
        passed = (
            statuses.count("abandoned") == 1
            and statuses.count("running") == 1
            and effective == 1
            and sum(row["type"] == "attempt_abandoned" for row in snapshot["events"]) == 1
            and recovery["claim"]["attemptId"] != first["claim"]["attemptId"]
        )
        return {
            "status": "pass" if passed else "fail",
            "cap": 1,
            "firstWorker": first,
            "recoveryWorker": recovery,
            "effectiveUnexpiredResearcherAttempts": effective,
            "snapshot": snapshot,
        }

    def scenario_fairness(self) -> dict[str, Any]:
        base_time = utcnow() - timedelta(seconds=5)
        full = self.seed_run("r2-fair-full", step_count=2, queued_at=base_time)
        eligible = self.seed_run(
            "r2-fair-eligible",
            step_count=4,
            queued_at=base_time + timedelta(seconds=1),
        )
        self.set_cap(full, 1)
        before = self.snapshot(full.run_id)
        first = self.claim_only("r2-fair-full-owner")
        full_after_first = self.snapshot(full.run_id)

        contender_waves: list[list[dict[str, Any]]] = []
        full_after_waves: list[dict[str, Any]] = []
        full_effective_after_waves: list[int] = []
        for wave in range(2):
            workers = self.start_concurrent_workers(
                action="claim_complete",
                worker_ids=[f"r2-fair-wave-{wave + 1}-worker-{index + 1}" for index in range(2)],
                barrier_name=f"r2-fair-wave-{wave + 1}.go",
                handler_delay=0.2,
            )
            contender_waves.append([self.finish_worker(worker) for worker in workers])
            full_after_waves.append(self.snapshot(full.run_id))
            full_effective_after_waves.append(self.effective_researcher_attempts(full.run_id))

        contenders = [worker for wave in contender_waves for worker in wave]
        full_final = full_after_waves[-1]
        eligible_after = self.snapshot(eligible.run_id)
        cap_full_zero_mutation = all(
            len(snapshot["attempts"]) == len(full_after_first["attempts"])
            and len(snapshot["events"]) == len(full_after_first["events"])
            and snapshot["steps"] == full_after_first["steps"]
            for snapshot in full_after_waves
        )
        each_wave_claimed_eligible = all(
            all(worker.get("claim", {}).get("runId") == eligible.run_id for worker in wave)
            for wave in contender_waves
        )
        unique_eligible_claims = (
            len({worker["claim"]["stepId"] for worker in contenders}) == len(contenders)
            and len({worker["claim"]["attemptId"] for worker in contenders}) == len(contenders)
        )
        contender_processes_unique = len({worker["pid"] for worker in contenders}) == len(contenders)
        wave_start_spreads_ms = [
            round(
                (max(worker["startedAtEpoch"] for worker in wave) - min(worker["startedAtEpoch"] for worker in wave))
                * 1000,
                3,
            )
            for wave in contender_waves
        ]
        concurrent_waves_proven = contender_processes_unique and all(
            spread < 1000 for spread in wave_start_spreads_ms
        )
        full_remained_full = full_effective_after_waves == [1, 1]
        passed = (
            cap_full_zero_mutation
            and concurrent_waves_proven
            and each_wave_claimed_eligible
            and unique_eligible_claims
            and full_remained_full
            and all(worker.get("status") == "completed" for worker in contenders)
        )
        return {
            "status": "pass" if passed else "fail",
            "firstWorker": first,
            "contenderWaves": contender_waves,
            "contenderProcessIdsUnique": contender_processes_unique,
            "waveStartSpreadsMs": wave_start_spreads_ms,
            "concurrentBarrierWavesProven": concurrent_waves_proven,
            "capFullZeroMutation": cap_full_zero_mutation,
            "eligibleRunClaimedInEveryWave": each_wave_claimed_eligible,
            "eligibleClaimsUnique": unique_eligible_claims,
            "fullEffectiveAttemptsAfterWaves": full_effective_after_waves,
            "fullRunRemainedAtCap": full_remained_full,
            "fullBefore": before,
            "fullAfterFirst": full_after_first,
            "fullAfterWaves": full_after_waves,
            "fullFinal": full_final,
            "eligibleAfter": eligible_after,
            "rootCause": None if passed else "concurrent fairness/no-starvation invariant failed",
            "authorizationBlocker": None,
        }

    def scenario_tie_order(self) -> dict[str, Any]:
        fixture = self.seed_run("r2-tie", step_count=2)
        tied = utcnow() - timedelta(seconds=1)
        with self.sessions() as db:
            db.execute(
                text("UPDATE research_steps SET queued_at=:stamp, created_at=:stamp WHERE run_id=:run"),
                {"stamp": tied, "run": fixture.run_id},
            )
            db.commit()
        result = self.claim_only("r2-tie-worker")
        expected = min(fixture.step_ids)
        actual = result["claim"]["stepId"]
        return {
            "status": "pass" if actual == expected else "fail",
            "expectedStepId": expected,
            "actualStepId": actual,
            "worker": result,
        }
