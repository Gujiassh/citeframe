"""R800 acceptance HTTP client, worker polling, and scenario aggregate gate."""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta

import httpx
from ai_pdf_api.core.settings import settings
from ai_pdf_api.db.session import SessionLocal
from ai_pdf_api.models import (
    HumanDecision,
    ResearchArtifact,
    ResearchArtifactClaim,
    ResearchClaim,
    ResearchEvent,
    ResearchStep,
    ResearchStepAttempt,
    WorkspaceMembership,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_pdf_worker.r800_acceptance_common import (
    API_BASE_URL,
    IDS,
    PROVIDER_BASE_URL,
    SCHEMA_VERSION,
)
from ai_pdf_worker.research_runtime import (
    ResearchWorkProcessor,
    build_default_research_service,
)


class ResearchHttpClient:
    def __init__(
        self,
        *,
        base_url: str = API_BASE_URL,
        internal_token: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._internal_token = internal_token or settings.api_internal_token
        self._client = httpx.Client(base_url=base_url, timeout=30, transport=transport)

    def close(self) -> None:
        self._client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        actor_id: str,
        idempotency_key: str | None = None,
        payload: object | None = None,
        headers: dict[str, str] | None = None,
        expected: Iterable[int] = (200,),
    ) -> httpx.Response:
        request_headers = {
            "x-ai-pdf-internal-token": self._internal_token,
            "x-user-id": actor_id,
            **(headers or {}),
        }
        if idempotency_key:
            request_headers["Idempotency-Key"] = idempotency_key
        response = self._client.request(
            method,
            path,
            headers=request_headers,
            json=payload,
        )
        if response.status_code not in set(expected):
            raise RuntimeError(
                f"R800 HTTP {method} {path} returned {response.status_code}: {response.text[:500]}"
            )
        return response

    def run(self, run_id: str, *, actor_id: str = IDS["creator"]) -> dict[str, object]:
        response = self.request(
            "GET",
            f"/v1/workspaces/{IDS['workspace']}/research-runs/{run_id}",
            actor_id=actor_id,
        )
        return response.json()["run"]


def _provider_request(
    method: str,
    path: str,
    *,
    payload: object | None = None,
) -> dict[str, object]:
    response = httpx.request(
        method,
        f"{PROVIDER_BASE_URL}{path}",
        json=payload,
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def _check(passed: bool, *, evidence: object, blocked: str | None = None) -> dict[str, object]:
    return {
        "status": "pass" if passed else ("blocked" if blocked else "fail"),
        "passed": passed,
        "evidence": evidence,
        **({"blockedReason": blocked} if blocked else {}),
    }


def _create_run(
    client: ResearchHttpClient,
    *,
    actor_id: str,
    key: str,
    question: str,
) -> dict[str, object]:
    response = client.request(
        "POST",
        f"/v1/workspaces/{IDS['workspace']}/research-runs",
        actor_id=actor_id,
        idempotency_key=key,
        payload={
            "question": question,
            "assetScope": {"mode": "selected", "assetIds": [IDS["asset"]]},
        },
        expected=(201,),
    )
    return response.json()["run"]


def _process_until(
    client: ResearchHttpClient,
    run_id: str,
    statuses: set[str],
    *,
    processor: ResearchWorkProcessor | None = None,
    actor_id: str = IDS["creator"],
    timeout_seconds: float = 90,
) -> tuple[dict[str, object], list[str]]:
    deadline = time.monotonic() + timeout_seconds
    errors: list[str] = []
    while time.monotonic() < deadline:
        run = client.run(run_id, actor_id=actor_id)
        if str(run["status"]) in statuses:
            return run, errors
        if processor is not None:
            try:
                handled = processor.process_one()
            except Exception as error:  # noqa: BLE001 - scenario evidence must record every worker failure
                errors.append(f"{type(error).__name__}:{str(error)[:160]}")
                handled = True
            if handled:
                continue
        time.sleep(0.2)
    current = client.run(run_id, actor_id=actor_id)
    raise TimeoutError(
        f"worker_poll_timeout run_id={run_id} status={current.get('status')} "
        f"errors={errors!r}"
    )


def _submit_plan(client: ResearchHttpClient, run: dict[str, object]) -> dict[str, object]:
    decisions = run.get("pendingDecisions")
    if not isinstance(decisions, list) or len(decisions) != 1:
        raise RuntimeError("R800 expected exactly one pending Plan decision")
    decision = decisions[0]
    response = client.request(
        "POST",
        f"/v1/workspaces/{IDS['workspace']}/research-runs/{run['id']}/"
        f"plan-decisions/{decision['id']}",
        actor_id=IDS["creator"],
        idempotency_key=f"r800-plan-{run['id']}",
        payload={
            "expectedStateVersion": run["stateVersion"],
            "expectedDecisionStateVersion": decision["stateVersion"],
            "inputArtifactSha256": decision["inputArtifactSha256"],
            "inputSnapshotSha256": decision["inputSnapshotSha256"],
            "action": "approve",
            "comment": "R800 deterministic approval.",
            "revision": None,
        },
    )
    return response.json()["run"]


def _submit_conflict(client: ResearchHttpClient, run: dict[str, object]) -> dict[str, object]:
    decisions = run.get("pendingDecisions")
    if not isinstance(decisions, list) or len(decisions) != 1:
        raise RuntimeError("R800 expected exactly one pending conflict decision")
    decision = decisions[0]
    response = client.request(
        "POST",
        f"/v1/workspaces/{IDS['workspace']}/research-runs/{run['id']}/"
        f"conflict-decisions/{decision['id']}",
        actor_id=IDS["creator"],
        idempotency_key=f"r800-conflict-{run['id']}",
        payload={
            "expectedStateVersion": run["stateVersion"],
            "expectedDecisionStateVersion": decision["stateVersion"],
            "inputArtifactSha256": decision["inputArtifactSha256"],
            "inputSnapshotSha256": decision["inputSnapshotSha256"],
            "action": "keep_as_unresolved",
            "comment": "Preserve the deterministic conflict as unresolved.",
        },
    )
    return response.json()["run"]


def _event_ids(payload: str) -> list[int]:
    return [int(value) for value in re.findall(r"(?m)^id: (\d+)$", payload)]


def _main_scenario(
    client: ResearchHttpClient,
    processor: ResearchWorkProcessor,
    session_factory: Callable[[], Session],
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    _provider_request("POST", "/__r800__/control/reset", payload={})
    _provider_request(
        "POST",
        "/__r800__/control/configure",
        payload={"node": "researcher", "failFirst": 1, "delayMs": 150},
    )
    created = _create_run(
        client,
        actor_id=IDS["creator"],
        key="r800-main-create-0001",
        question="Compare unsupported conflict evidence across the frozen fixture.",
    )
    run, worker_errors = _process_until(
        client,
        str(created["id"]),
        {"awaiting_plan_approval", "failed"},
        processor=processor,
    )
    if run["status"] == "awaiting_plan_approval":
        run = _submit_plan(client, run)
        run, later_errors = _process_until(
            client,
            str(run["id"]),
            {"awaiting_human_decision", "completed", "failed", "awaiting_retry"},
            processor=processor,
        )
        worker_errors.extend(later_errors)
    if run["status"] == "awaiting_human_decision":
        run = _submit_conflict(client, run)
        run, later_errors = _process_until(
            client,
            str(run["id"]),
            {"completed", "failed", "awaiting_retry"},
            processor=processor,
        )
        worker_errors.extend(later_errors)

    artifacts_response = client.request(
        "GET",
        f"/v1/workspaces/{IDS['workspace']}/research-runs/{run['id']}/artifacts",
        actor_id=IDS["creator"],
    ).json()
    artifacts = artifacts_response.get("items", [])
    final_items = [item for item in artifacts if item.get("kind") == "final_report"]
    final_detail: dict[str, object] = {}
    if len(final_items) == 1:
        final_detail = client.request(
            "GET",
            f"/v1/workspaces/{IDS['workspace']}/research-runs/{run['id']}/"
            f"artifacts/{final_items[0]['id']}",
            actor_id=IDS["creator"],
        ).json()["artifact"]

    events = client.request(
        "GET",
        f"/v1/workspaces/{IDS['workspace']}/research-runs/{run['id']}/events",
        actor_id=IDS["creator"],
        headers={"Accept": "text/event-stream"},
    ).text
    all_ids = _event_ids(events)
    cursor = all_ids[len(all_ids) // 2] if all_ids else 0
    replay = client.request(
        "GET",
        f"/v1/workspaces/{IDS['workspace']}/research-runs/{run['id']}/events",
        actor_id=IDS["creator"],
        headers={"Accept": "text/event-stream", "Last-Event-ID": str(cursor)},
    ).text
    replay_ids = _event_ids(replay)
    timeline = _provider_request("GET", "/__r800__/control/timeline")

    with session_factory() as db:
        unsupported = db.scalar(
            select(func.count()).select_from(ResearchClaim).where(
                ResearchClaim.run_id == run["id"],
                ResearchClaim.verification_status == "unsupported",
            )
        ) or 0
        final_links = (
            db.scalar(
                select(func.count())
                .select_from(ResearchArtifactClaim)
                .join(ResearchArtifact, ResearchArtifact.id == ResearchArtifactClaim.artifact_id)
                .join(ResearchClaim, ResearchClaim.id == ResearchArtifactClaim.claim_id)
                .where(
                    ResearchArtifact.run_id == run["id"],
                    ResearchArtifact.artifact_kind == "final_report",
                    ResearchClaim.verification_status == "unsupported",
                )
            )
            or 0
        )
        retry_attempts = db.scalar(
            select(func.count())
            .select_from(ResearchStepAttempt)
            .join(ResearchStep, ResearchStep.id == ResearchStepAttempt.step_id)
            .where(
                ResearchStep.run_id == run["id"],
                ResearchStepAttempt.attempt_number > 1,
            )
        ) or 0
        failed_attempts = db.scalar(
            select(func.count())
            .select_from(ResearchStepAttempt)
            .join(ResearchStep, ResearchStep.id == ResearchStepAttempt.step_id)
            .where(
                ResearchStep.run_id == run["id"],
                ResearchStepAttempt.status == "failed",
            )
        ) or 0
        submitted_conflicts = db.scalar(
            select(func.count()).select_from(HumanDecision).where(
                HumanDecision.run_id == run["id"],
                HumanDecision.decision_type == "conflict_resolution",
                HumanDecision.status == "submitted",
            )
        ) or 0
        final_count = db.scalar(
            select(func.count()).select_from(ResearchArtifact).where(
                ResearchArtifact.run_id == run["id"],
                ResearchArtifact.artifact_kind == "final_report",
            )
        ) or 0

    entries = timeline.get("entries", [])
    transient_entries = [entry for entry in entries if entry.get("httpStatus") == 503]
    main_checks = {
        "mainCompleted": _check(
            run["status"] == "completed",
            evidence={"runId": run["id"], "status": run["status"], "workerErrors": worker_errors},
        ),
        "parallelFanout": _check(
            int(timeline.get("maxActive", 0)) >= 2,
            evidence={"maxActive": timeline.get("maxActive"), "providerEntries": len(entries)},
        ),
        "unsupportedWithheld": _check(
            unsupported > 0 and final_links == 0,
            evidence={"unsupportedClaims": unsupported, "unsupportedFinalLinks": final_links},
        ),
        "conflictResume": _check(
            submitted_conflicts == 1 and bool(final_detail),
            evidence={"submittedConflictDecisions": submitted_conflicts},
        ),
        "transientRetry": _check(
            bool(transient_entries) and (retry_attempts > 0 or failed_attempts > 0),
            evidence={
                "transientProviderResponses": len(transient_entries),
                "retryAttempts": retry_attempts,
                "failedAttempts": failed_attempts,
            },
        ),
        "sseReplay": _check(
            bool(all_ids)
            and all_ids == list(range(1, max(all_ids) + 1))
            and replay_ids == [item for item in all_ids if item > cursor],
            evidence={"allEventIds": all_ids, "cursor": cursor, "replayEventIds": replay_ids},
        ),
        "uniqueFinal": _check(
            final_count == 1 and len(final_items) == 1,
            evidence={"databaseFinalCount": final_count, "apiFinalCount": len(final_items)},
        ),
    }
    return {
        "id": run["id"],
        "status": run["status"],
        "artifactIds": [item.get("id") for item in artifacts],
        "eventCount": len(all_ids),
        "providerTimeline": {
            "maxActive": timeline.get("maxActive"),
            "entryCount": len(entries),
            "transientCount": len(transient_entries),
        },
    }, main_checks


def _reclaim_scenario(
    client: ResearchHttpClient,
    processor: ResearchWorkProcessor,
    session_factory: Callable[[], Session],
) -> tuple[dict[str, object], dict[str, object]]:
    created = _create_run(
        client,
        actor_id=IDS["creator"],
        key="r800-reclaim-create-0001",
        question="Verify lease reclaim from frozen evidence.",
    )
    run, _errors = _process_until(
        client,
        str(created["id"]),
        {"awaiting_plan_approval", "failed"},
        processor=processor,
    )
    if run["status"] != "awaiting_plan_approval":
        return run, _check(False, evidence={"status": run["status"]}, blocked="plan_not_ready")
    run = _submit_plan(client, run)
    claimed = processor.claim()
    if claimed is None or claimed.run_id != run["id"]:
        return run, _check(False, evidence={"claimed": False}, blocked="step_claim_raced")
    with session_factory() as db:
        attempt = db.get(ResearchStepAttempt, claimed.lease.attempt_id)
        if attempt is None:
            return run, _check(False, evidence={"attempt": None}, blocked="attempt_missing")
        attempt.lease_expires_at = datetime.now(UTC) - timedelta(seconds=5)
        db.commit()
    processor.process_one()
    with session_factory() as db:
        original = db.get(ResearchStepAttempt, claimed.lease.attempt_id)
        attempts = list(
            db.scalars(
                select(ResearchStepAttempt)
                .where(ResearchStepAttempt.step_id == claimed.lease.step_id)
                .order_by(ResearchStepAttempt.attempt_number)
            ).all()
        )
        passed = original is not None and original.status == "abandoned" and len(attempts) >= 2
        evidence = {
            "originalAttemptStatus": original.status if original else None,
            "attemptNumbers": [item.attempt_number for item in attempts],
        }
    current = client.run(str(run["id"]))
    if current["status"] not in {"completed", "failed", "cancelled"}:
        client.request(
            "POST",
            f"/v1/workspaces/{IDS['workspace']}/research-runs/{run['id']}/cancel",
            actor_id=IDS["creator"],
            idempotency_key="r800-reclaim-cleanup-cancel",
            payload={"expectedStateVersion": current["stateVersion"], "reasonCode": "user_requested"},
            expected=(202,),
        )
    return {"id": run["id"], "status": client.run(str(run["id"]))["status"]}, _check(
        passed, evidence=evidence
    )


def _cancel_scenario(
    client: ResearchHttpClient,
    session_factory: Callable[[], Session],
) -> tuple[dict[str, object], dict[str, object]]:
    run = _create_run(
        client,
        actor_id=IDS["creator"],
        key="r800-cancel-create-0001",
        question="Cancel this deterministic run before publication.",
    )
    response = client.request(
        "POST",
        f"/v1/workspaces/{IDS['workspace']}/research-runs/{run['id']}/cancel",
        actor_id=IDS["creator"],
        idempotency_key="r800-cancel-action-0001",
        payload={"expectedStateVersion": run["stateVersion"], "reasonCode": "user_requested"},
        expected=(202,),
    )
    cancelled = response.json()["run"]
    with session_factory() as db:
        final_count = db.scalar(
            select(func.count()).select_from(ResearchArtifact).where(
                ResearchArtifact.run_id == run["id"],
                ResearchArtifact.artifact_kind == "final_report",
            )
        ) or 0
        cancel_events = db.scalar(
            select(func.count()).select_from(ResearchEvent).where(
                ResearchEvent.run_id == run["id"],
                ResearchEvent.event_type == "run_cancelled",
            )
        ) or 0
    return {"id": run["id"], "status": cancelled["status"]}, _check(
        cancelled["status"] == "cancelled" and final_count == 0 and cancel_events == 1,
        evidence={"status": cancelled["status"], "finalCount": final_count, "cancelEvents": cancel_events},
    )


def _membership_scenario(
    client: ResearchHttpClient,
    processor: ResearchWorkProcessor,
    session_factory: Callable[[], Session],
) -> tuple[dict[str, object], dict[str, object]]:
    run = _create_run(
        client,
        actor_id=IDS["member"],
        key="r800-membership-create-0001",
        question="Membership removal must stop this Research run.",
    )
    with session_factory() as db:
        membership = db.get(WorkspaceMembership, IDS["member-membership"])
        if membership is None:
            return run, _check(False, evidence={}, blocked="membership_missing")
        db.delete(membership)
        db.commit()
    processing_error = None
    try:
        processor.process_one()
    except Exception as error:  # noqa: BLE001 - membership rejection is the expected evidence
        processing_error = f"{type(error).__name__}:{str(error)[:160]}"
    observed, _errors = _process_until(
        client,
        str(run["id"]),
        {"cancel_requested", "cancelled", "completed", "failed"},
        actor_id=IDS["owner"],
        timeout_seconds=30,
    )
    with session_factory() as db:
        events = list(
            db.scalars(
                select(ResearchEvent.event_type).where(ResearchEvent.run_id == run["id"])
            ).all()
        )
    passed = observed["status"] in {"cancel_requested", "cancelled"} and "cancel_requested" in events
    return {"id": run["id"], "status": observed["status"]}, _check(
        passed,
        evidence={
            "status": observed["status"],
            "eventTypes": events,
            "workerResult": processing_error,
        },
    )


def run_scenarios(
    *,
    client: ResearchHttpClient | None = None,
    processor: ResearchWorkProcessor | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
) -> dict[str, object]:
    owns_client = client is None
    client = client or ResearchHttpClient()
    processor = processor or ResearchWorkProcessor(
        SessionLocal,
        build_default_research_service(),
        worker_instance_id="r800-acceptance-cli",
    )
    checks: dict[str, dict[str, object]] = {}
    runs: dict[str, object] = {}
    errors: list[dict[str, str]] = []
    try:
        main_run, main_checks = _main_scenario(client, processor, session_factory)
        runs["main"] = main_run
        checks.update(main_checks)
        reclaim_run, reclaim_check = _reclaim_scenario(client, processor, session_factory)
        runs["reclaim"] = reclaim_run
        checks["leaseReclaim"] = reclaim_check
        cancel_run, cancel_check = _cancel_scenario(client, session_factory)
        runs["cancel"] = cancel_run
        checks["cancelNoFinal"] = cancel_check
        membership_run, membership_check = _membership_scenario(
            client, processor, session_factory
        )
        runs["membershipRemoval"] = membership_run
        checks["membershipRemoval"] = membership_check
    except Exception as error:  # noqa: BLE001 - a scenario exception must fail the aggregate gate
        errors.append({"type": type(error).__name__, "message": str(error)[:500]})
        checks["scenarioExecution"] = _check(
            False,
            evidence=errors,
            blocked="scenario_exception",
        )
    finally:
        if owns_client:
            client.close()
    engineering_gate = (
        "pass"
        if checks and all(item.get("status") == "pass" for item in checks.values())
        else "fail"
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "engineeringGate": engineering_gate,
        "checks": checks,
        "runs": runs,
        "errors": errors,
    }
