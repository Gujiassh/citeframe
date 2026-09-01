"""R2-H real-process join-readiness proof scenario.

This module is proof-only. It composes existing production claim/completion commands through
the R2 child entry and never mutates production source or contracts.

The fixture seeds both upstream Steps in ``queued`` state. That seeded row state is an
explicit precondition for this scenario; R2-H does not claim to prove the earlier creation of
their initial ``step_queued`` Events. The event proof starts at each upstream's
``step_started`` Event and requires its matching ``step_succeeded`` Event before the join is
queued.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from citeframe_persistence.models import ResearchStep, ResearchStepDependency
from sqlalchemy import select


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def full_projection(
    harness: Any,
    run_id: str,
    projection: Callable[[Any, str], dict[str, Any]],
) -> dict[str, Any]:
    state = projection(harness, run_id)
    with harness.sessions() as db:
        rows = db.execute(
            select(
                ResearchStepDependency.step_id,
                ResearchStepDependency.depends_on_step_id,
            )
            .join(ResearchStep, ResearchStep.id == ResearchStepDependency.step_id)
            .where(ResearchStep.run_id == run_id)
            .order_by(
                ResearchStepDependency.step_id,
                ResearchStepDependency.depends_on_step_id,
            )
        ).all()
    state["dependencies"] = [
        {"step_id": row.step_id, "depends_on_step_id": row.depends_on_step_id}
        for row in rows
    ]
    return state


def step_by_id(state: dict[str, Any], step_id: str) -> dict[str, Any]:
    return next(step for step in state["steps"] if step["id"] == step_id)


def attempts_for_step(state: dict[str, Any], step_id: str) -> list[dict[str, Any]]:
    return [attempt for attempt in state["attempts"] if attempt["step_id"] == step_id]


def event_for(
    state: dict[str, Any], *, event_type: str, step_id: str
) -> list[dict[str, Any]]:
    return [
        event
        for event in state["events"]
        if event["event_type"] == event_type and event["step_id"] == step_id
    ]


def _single_event_sequence(events: list[dict[str, Any]]) -> int | None:
    if len(events) != 1:
        return None
    return int(events[0]["seq"])


def upstream_lifecycle_oracle(
    state: dict[str, Any],
    *,
    upstream_ids: tuple[str, str],
    join_queued_seq: int | None,
) -> dict[str, Any]:
    """Validate the committed upstream facts that make the join ready.

    Initial upstream queue Events are deliberately outside this oracle. The fixture's queued
    Step rows are a setup precondition, while every started/succeeded fact below must be a
    persisted Event linked one-to-one to the sole succeeded Attempt for that upstream Step.
    """

    proofs: list[dict[str, Any]] = []
    for step_id in upstream_ids:
        started_events = event_for(
            state,
            event_type="step_started",
            step_id=step_id,
        )
        succeeded_events = event_for(
            state,
            event_type="step_succeeded",
            step_id=step_id,
        )
        attempts = attempts_for_step(state, step_id)
        started_seq = _single_event_sequence(started_events)
        succeeded_seq = _single_event_sequence(succeeded_events)
        exactly_one_started = len(started_events) == 1
        exactly_one_succeeded = len(succeeded_events) == 1
        exactly_one_attempt = len(attempts) == 1
        attempt_succeeded = exactly_one_attempt and attempts[0]["status"] == "succeeded"
        expected_attempt_id = str(attempts[0]["id"]) if exactly_one_attempt else None
        event_attempt_ids_match = (
            exactly_one_started
            and exactly_one_succeeded
            and expected_attempt_id is not None
            and str(started_events[0].get("attempt_id")) == expected_attempt_id
            and str(succeeded_events[0].get("attempt_id")) == expected_attempt_id
        )
        started_before_succeeded_before_join = (
            started_seq is not None
            and succeeded_seq is not None
            and join_queued_seq is not None
            and started_seq < succeeded_seq < join_queued_seq
        )
        proofs.append(
            {
                "stepId": step_id,
                "startedEventCount": len(started_events),
                "succeededEventCount": len(succeeded_events),
                "attemptCount": len(attempts),
                "attemptId": expected_attempt_id,
                "attemptStatus": attempts[0]["status"] if exactly_one_attempt else None,
                "startedSeq": started_seq,
                "succeededSeq": succeeded_seq,
                "startedExactlyOnce": exactly_one_started,
                "succeededExactlyOnce": exactly_one_succeeded,
                "exactlyOneAttempt": exactly_one_attempt,
                "attemptSucceeded": attempt_succeeded,
                "eventAttemptIdsMatch": event_attempt_ids_match,
                "startedBeforeSucceededBeforeJoinQueued": started_before_succeeded_before_join,
                "valid": (
                    exactly_one_started
                    and exactly_one_succeeded
                    and exactly_one_attempt
                    and attempt_succeeded
                    and event_attempt_ids_match
                    and started_before_succeeded_before_join
                ),
            }
        )
    return {
        "initialQueuedEventProofClaimed": False,
        "fixtureQueuedStepStateIsPrecondition": True,
        "upstreams": proofs,
        "startedExactlyOnce": all(item["startedExactlyOnce"] for item in proofs),
        "succeededExactlyOnce": all(item["succeededExactlyOnce"] for item in proofs),
        "exactlyOneSucceededAttempt": all(
            item["exactlyOneAttempt"] and item["attemptSucceeded"] for item in proofs
        ),
        "eventAttemptIdsMatch": all(item["eventAttemptIdsMatch"] for item in proofs),
        "startedBeforeSucceededBeforeJoinQueued": all(
            item["startedBeforeSucceededBeforeJoinQueued"] for item in proofs
        ),
        "valid": all(item["valid"] for item in proofs),
    }


def join_event_oracle(
    state: dict[str, Any],
    *,
    upstream_ids: tuple[str, str],
    join_id: str,
    verifier_id: str,
) -> dict[str, Any]:
    sequences = [int(event["seq"]) for event in state["events"]]
    dedupe_keys = [event["dedupe_key"] for event in state["events"]]
    upstream_terminal = [
        _single_event_sequence(
            event_for(state, event_type="step_succeeded", step_id=step_id)
        )
        for step_id in upstream_ids
    ]
    join_queued = _single_event_sequence(
        event_for(state, event_type="step_queued", step_id=join_id)
    )
    join_started = _single_event_sequence(
        event_for(state, event_type="step_started", step_id=join_id)
    )
    join_terminal = _single_event_sequence(
        event_for(state, event_type="step_succeeded", step_id=join_id)
    )
    verifier_queued = _single_event_sequence(
        event_for(state, event_type="step_queued", step_id=verifier_id)
    )
    upstream_oracle = upstream_lifecycle_oracle(
        state,
        upstream_ids=upstream_ids,
        join_queued_seq=join_queued,
    )
    partial_order = (
        upstream_oracle["valid"]
        and all(sequence is not None for sequence in upstream_terminal)
        and join_queued is not None
        and join_started is not None
        and join_terminal is not None
        and verifier_queued is not None
        and max(sequence for sequence in upstream_terminal if sequence is not None)
        < join_queued
        < join_started
        < join_terminal
        < verifier_queued
    )
    return {
        "eventSequences": sequences,
        "sequencesStrictlyContiguous": sequences
        == list(range(1, len(sequences) + 1)),
        "dedupeKeysUnique": len(dedupe_keys) == len(set(dedupe_keys)),
        "upstreamTerminalSeq": upstream_terminal,
        "joinQueuedSeq": join_queued,
        "joinStartedSeq": join_started,
        "joinTerminalSeq": join_terminal,
        "verifierQueuedSeq": verifier_queued,
        "upstreamLifecycle": upstream_oracle,
        "strictPartialOrder": partial_order,
    }


def seed_join_fixture(harness: Any) -> dict[str, Any]:
    fixture = harness.seed_run("r2-h-join", step_count=4)
    upstream_ids = (fixture.step_ids[0], fixture.step_ids[1])
    join_id = fixture.step_ids[2]
    verifier_id = fixture.step_ids[3]
    with harness.sessions() as db:
        upstream_one = db.get(ResearchStep, upstream_ids[0])
        upstream_two = db.get(ResearchStep, upstream_ids[1])
        join = db.get(ResearchStep, join_id)
        verifier = db.get(ResearchStep, verifier_id)
        assert all(step is not None for step in (upstream_one, upstream_two, join, verifier))
        join.step_key = "join:r2-h"
        join.step_kind = "join"
        join.branch_key = None
        join.status = "pending"
        join.queued_at = None
        join.updated_at = datetime.now(UTC)
        verifier.step_key = "verifier:r2-h"
        verifier.step_kind = "verifier"
        verifier.branch_key = None
        verifier.status = "pending"
        verifier.queued_at = None
        verifier.updated_at = datetime.now(UTC)
        db.add_all(
            [
                ResearchStepDependency(step_id=join_id, depends_on_step_id=upstream_ids[0]),
                ResearchStepDependency(step_id=join_id, depends_on_step_id=upstream_ids[1]),
                ResearchStepDependency(step_id=verifier_id, depends_on_step_id=join_id),
            ]
        )
        db.commit()
    return {
        "fixture": fixture,
        "upstreamIds": upstream_ids,
        "upstreamKeys": (fixture.step_keys[0], fixture.step_keys[1]),
        "upstreamBranches": (fixture.branch_keys[0], fixture.branch_keys[1]),
        "joinId": join_id,
        "joinKey": "join:r2-h",
        "verifierId": verifier_id,
    }


def run_scenario(
    harness: Any,
    database_url: str,
    timeout_seconds: float,
    *,
    launch_workers: Callable[..., dict[str, Any]],
    projection: Callable[[Any, str], dict[str, Any]],
    lock_projection: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    topology = seed_join_fixture(harness)
    fixture = topology["fixture"]
    upstream_ids = topology["upstreamIds"]
    join_id = topology["joinId"]
    verifier_id = topology["verifierId"]
    before = full_projection(harness, fixture.run_id, projection)
    assert all(
        step_by_id(before, step_id)["status"] == "queued"
        for step_id in upstream_ids
    )
    assert step_by_id(before, join_id)["status"] == "pending"
    assert step_by_id(before, verifier_id)["status"] == "pending"

    upstream_one = launch_workers(
        scenario="h_join_readiness",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[{
            "workerInstanceId": "h-upstream-1",
            "operation": "claim_complete_specific",
            "runId": fixture.run_id,
            "stepKey": topology["upstreamKeys"][0],
            "branchKey": topology["upstreamBranches"][0],
            "outputSha256": sha("r2-h-upstream-1"),
        }],
        timeout_seconds=timeout_seconds,
    )
    after_first_upstream = full_projection(harness, fixture.run_id, projection)
    assert upstream_one["processRecords"][0]["outcome"] == "completed"
    assert step_by_id(after_first_upstream, upstream_ids[0])["status"] == "succeeded"
    assert step_by_id(after_first_upstream, upstream_ids[1])["status"] == "queued"
    assert step_by_id(after_first_upstream, join_id)["status"] == "pending"
    assert step_by_id(after_first_upstream, verifier_id)["status"] == "pending"
    assert event_for(
        after_first_upstream, event_type="step_queued", step_id=join_id
    ) == []

    upstream_two = launch_workers(
        scenario="h_join_readiness",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[{
            "workerInstanceId": "h-upstream-2",
            "operation": "claim_complete_specific",
            "runId": fixture.run_id,
            "stepKey": topology["upstreamKeys"][1],
            "branchKey": topology["upstreamBranches"][1],
            "outputSha256": sha("r2-h-upstream-2"),
        }],
        timeout_seconds=timeout_seconds,
    )
    after_second_upstream = full_projection(harness, fixture.run_id, projection)
    assert upstream_two["processRecords"][0]["outcome"] == "completed"
    assert upstream_one["processRecords"][0]["osPid"] != upstream_two["processRecords"][0]["osPid"]
    assert (
        upstream_one["processRecords"][0]["pgBackendPid"]
        != upstream_two["processRecords"][0]["pgBackendPid"]
    )
    assert all(
        step_by_id(after_second_upstream, step_id)["status"] == "succeeded"
        for step_id in upstream_ids
    )
    assert step_by_id(after_second_upstream, join_id)["status"] == "queued"
    assert len(event_for(after_second_upstream, event_type="step_queued", step_id=join_id)) == 1
    assert step_by_id(after_second_upstream, verifier_id)["status"] == "pending"
    assert attempts_for_step(after_second_upstream, verifier_id) == []

    join_race = launch_workers(
        scenario="h_join_readiness",
        database_url=database_url,
        schema=harness.schema,
        worker_specs=[
            {
                "workerInstanceId": "h-join-1",
                "operation": "claim_complete_specific",
                "runId": fixture.run_id,
                "stepKey": topology["joinKey"],
                "outputSha256": sha("r2-h-join-1"),
            },
            {
                "workerInstanceId": "h-join-2",
                "operation": "claim_complete_specific",
                "runId": fixture.run_id,
                "stepKey": topology["joinKey"],
                "outputSha256": sha("r2-h-join-2"),
            },
        ],
        timeout_seconds=timeout_seconds,
    )
    after = full_projection(harness, fixture.run_id, projection)
    outcomes = sorted(record["outcome"] for record in join_race["processRecords"])
    assert outcomes == ["completed", "conflict"]
    conflict = next(record for record in join_race["processRecords"] if record["outcome"] == "conflict")
    assert conflict["errorCode"] == "research_state_conflict"
    assert step_by_id(after, join_id)["status"] == "succeeded"
    join_attempts = attempts_for_step(after, join_id)
    assert len(join_attempts) == 1
    assert join_attempts[0]["status"] == "succeeded"
    assert len(event_for(after, event_type="step_queued", step_id=join_id)) == 1
    assert len(event_for(after, event_type="step_started", step_id=join_id)) == 1
    assert len(event_for(after, event_type="step_succeeded", step_id=join_id)) == 1
    assert step_by_id(after, verifier_id)["status"] == "queued"
    assert attempts_for_step(after, verifier_id) == []
    assert len(event_for(after, event_type="step_queued", step_id=verifier_id)) == 1
    oracle = join_event_oracle(
        after,
        upstream_ids=upstream_ids,
        join_id=join_id,
        verifier_id=verifier_id,
    )
    assert oracle["sequencesStrictlyContiguous"]
    assert oracle["dedupeKeysUnique"]
    assert oracle["upstreamLifecycle"]["startedExactlyOnce"]
    assert oracle["upstreamLifecycle"]["succeededExactlyOnce"]
    assert oracle["upstreamLifecycle"]["exactlyOneSucceededAttempt"]
    assert oracle["upstreamLifecycle"]["eventAttemptIdsMatch"]
    assert oracle["upstreamLifecycle"]["startedBeforeSucceededBeforeJoinQueued"]
    assert oracle["upstreamLifecycle"]["valid"]
    assert oracle["strictPartialOrder"]
    return {
        "topology": {
            "upstreamStepIds": list(upstream_ids),
            "joinStepId": join_id,
            "verifierStepId": verifier_id,
        },
        "before": before,
        "upstreamOne": upstream_one,
        "afterFirstUpstream": after_first_upstream,
        "upstreamTwo": upstream_two,
        "afterSecondUpstream": after_second_upstream,
        "joinRace": join_race,
        "after": after,
        "eventOracle": oracle,
        "fixturePreconditions": {
            "upstreamStepsSeededQueued": True,
            "initialUpstreamQueuedEventsClaimedOrProven": False,
            "note": (
                "Initial upstream queued Step rows are fixture preconditions; R2-H event "
                "proof begins at each upstream step_started Event."
            ),
        },
        "locks": lock_projection(harness),
        "assertions": {
            "joinPendingAfterFirstCommittedUpstream": True,
            "joinQueuedOnceAfterBothCommittedUpstreams": True,
            "twoDistinctUpstreamOsProcesses": True,
            "twoDistinctUpstreamPostgresBackends": True,
            "joinCompletedExactlyOnce": True,
            "competingJoinWorkerFenced": True,
            "joinAttemptStartedAndTerminalExactlyOnce": True,
            "verifierQueuedOnlyAfterJoinCommit": True,
            "verifierHasNoAttempt": True,
            "dependenciesFullyProjected": True,
            "eventSequenceAndDedupeValid": True,
            "strictJoinPartialOrder": True,
            "eachUpstreamStartedExactlyOnce": True,
            "eachUpstreamSucceededExactlyOnce": True,
            "eachUpstreamHasOneSucceededAttempt": True,
            "upstreamEventsMatchSoleAttempt": True,
            "upstreamStartedThenSucceededBeforeJoinQueued": True,
        },
    }
