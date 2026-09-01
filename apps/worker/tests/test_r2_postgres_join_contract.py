"""Source and pure-oracle contracts for the R2-H process proof."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "infra/scripts/run-r2-postgres-multi-worker.py"
WORKER = ROOT / "infra/scripts/r2_worker_entry.py"
SCENARIO = ROOT / "infra/scripts/r2_scenario_h_join.py"


def load_scenario():
    spec = importlib.util.spec_from_file_location("r2_h_join_contract", SCENARIO)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_r2_h_is_a_separate_proof_module_and_uses_real_child_operations() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    worker = WORKER.read_text(encoding="utf-8")
    scenario = SCENARIO.read_text(encoding="utf-8")
    assert 'H_JOIN_SCENARIO = ROOT / "infra/scripts/r2_scenario_h_join.py"' in runner
    assert '"h_join_readiness"' in runner
    assert "h_join.run_scenario(" in runner
    assert '"claim_complete_specific"' in worker
    assert "claim_specific_research_step(" in worker
    assert "complete_research_step(" in worker
    assert scenario.count('"operation": "claim_complete_specific"') >= 3
    assert "ResearchStepDependency" in scenario
    assert '"dependencies"' in scenario
    assert 'outcomes == ["completed", "conflict"]' in scenario
    assert '"verifierHasNoAttempt"' in scenario
    assert '"strictJoinPartialOrder"' in scenario


def test_r2_controller_prefers_database_url_environment_without_argv_secret() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    assert 'parser.add_argument("--database-url-env", default="R2_DATABASE_URL")' in runner
    assert 'parser.add_argument("--database-url", help=argparse.SUPPRESS)' in runner
    assert "os.environ.get(args.database_url_env) or args.database_url" in runner
    assert 'secrets = {database_url}' in runner


def test_join_event_oracle_rejects_wrong_actual_sequence_order() -> None:
    scenario = load_scenario()
    upstream_one = "upstream-1"
    upstream_two = "upstream-2"
    join = "join"
    verifier = "verifier"
    attempts = [
        {"id": "attempt-1", "step_id": upstream_one, "status": "succeeded"},
        {"id": "attempt-2", "step_id": upstream_two, "status": "succeeded"},
    ]
    events = [
        {"seq": 1, "event_type": "step_started", "step_id": upstream_one, "attempt_id": "attempt-1", "dedupe_key": "u1s"},
        {"seq": 2, "event_type": "step_succeeded", "step_id": upstream_one, "attempt_id": "attempt-1", "dedupe_key": "u1t"},
        {"seq": 3, "event_type": "step_started", "step_id": upstream_two, "attempt_id": "attempt-2", "dedupe_key": "u2s"},
        {"seq": 4, "event_type": "step_succeeded", "step_id": upstream_two, "attempt_id": "attempt-2", "dedupe_key": "u2t"},
        {"seq": 5, "event_type": "step_queued", "step_id": join, "attempt_id": None, "dedupe_key": "jq"},
        {"seq": 6, "event_type": "step_started", "step_id": join, "attempt_id": "join-attempt", "dedupe_key": "js"},
        {"seq": 7, "event_type": "step_succeeded", "step_id": join, "attempt_id": "join-attempt", "dedupe_key": "jt"},
        {"seq": 8, "event_type": "step_queued", "step_id": verifier, "attempt_id": None, "dedupe_key": "vq"},
    ]
    oracle = scenario.join_event_oracle(
        {"events": events, "attempts": attempts},
        upstream_ids=(upstream_one, upstream_two),
        join_id=join,
        verifier_id=verifier,
    )
    assert oracle["sequencesStrictlyContiguous"] is True
    assert oracle["dedupeKeysUnique"] is True
    assert oracle["upstreamLifecycle"]["valid"] is True
    assert oracle["strictPartialOrder"] is True

    wrong_order = [events[1], events[0], *events[2:]]
    wrong = scenario.join_event_oracle(
        {"events": wrong_order, "attempts": attempts},
        upstream_ids=(upstream_one, upstream_two),
        join_id=join,
        verifier_id=verifier,
    )
    assert wrong["sequencesStrictlyContiguous"] is False


def _valid_upstream_state() -> tuple[dict[str, object], tuple[str, str], str, str]:
    upstream_ids = ("upstream-1", "upstream-2")
    join_id = "join"
    verifier_id = "verifier"
    attempts = [
        {"id": "attempt-1", "step_id": upstream_ids[0], "status": "succeeded"},
        {"id": "attempt-2", "step_id": upstream_ids[1], "status": "succeeded"},
    ]
    events = [
        {"seq": 1, "event_type": "step_started", "step_id": upstream_ids[0], "attempt_id": "attempt-1", "dedupe_key": "u1s"},
        {"seq": 2, "event_type": "step_succeeded", "step_id": upstream_ids[0], "attempt_id": "attempt-1", "dedupe_key": "u1t"},
        {"seq": 3, "event_type": "step_started", "step_id": upstream_ids[1], "attempt_id": "attempt-2", "dedupe_key": "u2s"},
        {"seq": 4, "event_type": "step_succeeded", "step_id": upstream_ids[1], "attempt_id": "attempt-2", "dedupe_key": "u2t"},
        {"seq": 5, "event_type": "step_queued", "step_id": join_id, "attempt_id": None, "dedupe_key": "jq"},
        {"seq": 6, "event_type": "step_started", "step_id": join_id, "attempt_id": "join-attempt", "dedupe_key": "js"},
        {"seq": 7, "event_type": "step_succeeded", "step_id": join_id, "attempt_id": "join-attempt", "dedupe_key": "jt"},
        {"seq": 8, "event_type": "step_queued", "step_id": verifier_id, "attempt_id": None, "dedupe_key": "vq"},
    ]
    return {"events": events, "attempts": attempts}, upstream_ids, join_id, verifier_id


def _oracle_for_state(state: dict[str, object]):
    scenario = load_scenario()
    return scenario.join_event_oracle(
        state,
        upstream_ids=("upstream-1", "upstream-2"),
        join_id="join",
        verifier_id="verifier",
    )


def test_join_event_oracle_rejects_duplicate_upstream_terminal() -> None:
    state, _, _, _ = _valid_upstream_state()
    events = list(state["events"])
    events.insert(
        2,
        {
            "seq": 3,
            "event_type": "step_succeeded",
            "step_id": "upstream-1",
            "attempt_id": "attempt-1",
            "dedupe_key": "u1t-duplicate",
        },
    )
    for index, event in enumerate(events, start=1):
        event["seq"] = index
    state["events"] = events
    oracle = _oracle_for_state(state)
    assert oracle["upstreamLifecycle"]["succeededExactlyOnce"] is False
    assert oracle["upstreamLifecycle"]["valid"] is False
    assert oracle["strictPartialOrder"] is False


def test_join_event_oracle_rejects_upstream_terminal_before_started() -> None:
    state, _, _, _ = _valid_upstream_state()
    events = list(state["events"])
    events[0], events[1] = events[1], events[0]
    for index, event in enumerate(events, start=1):
        event["seq"] = index
    state["events"] = events
    oracle = _oracle_for_state(state)
    assert (
        oracle["upstreamLifecycle"]["startedBeforeSucceededBeforeJoinQueued"]
        is False
    )
    assert oracle["upstreamLifecycle"]["valid"] is False
    assert oracle["strictPartialOrder"] is False


def test_join_event_oracle_rejects_multiple_upstream_attempts() -> None:
    state, _, _, _ = _valid_upstream_state()
    state["attempts"] = [
        *state["attempts"],
        {"id": "attempt-1-retry", "step_id": "upstream-1", "status": "succeeded"},
    ]
    oracle = _oracle_for_state(state)
    assert oracle["upstreamLifecycle"]["exactlyOneSucceededAttempt"] is False
    assert oracle["upstreamLifecycle"]["valid"] is False
    assert oracle["strictPartialOrder"] is False


def test_h_fixture_documents_queued_state_as_precondition_not_event_proof() -> None:
    scenario = SCENARIO.read_text(encoding="utf-8")
    assert '"initialUpstreamQueuedEventsClaimedOrProven": False' in scenario
    assert '"upstreamStepsSeededQueued": True' in scenario
    assert "Initial upstream queued Step rows are fixture preconditions" in scenario
    assert "proof begins at each upstream step_started Event" in scenario
