"""Coherent raw/projection mutations for the explicitly scoped retry repair."""

import json
from copy import deepcopy


def verify_retry_negative_controls(payload):
    from a2a_r2_delta import compare

    baseline, source = payload["rawBaselineReport"], payload["rawCandidateReport"]
    accepted = compare(baseline, source)
    assert accepted["accepted"] and accepted["retryStepErrorDeltaValid"]
    delta = accepted["retryStepErrorDelta"][0]

    def mutate_rows(report, table, identity, changes):
        for tables in (
            report["rawDatabaseRows"]["transitions"],
            report["semantics"]["normalizedDbRows"]["transitions"],
        ):
            row = next(r for r in tables[table] if r["id"] == identity)
            row.update(changes)
            tables[table].sort(
                key=lambda r: json.dumps(
                    r, ensure_ascii=True, sort_keys=True, separators=(",", ":")
                )
            )

    def mutate(kind):
        b, c = deepcopy(baseline), deepcopy(source)
        step, prior, current = (
            delta["stepId"],
            delta["priorAttemptId"],
            delta["currentAttemptId"],
        )
        if kind == "unclaimed":
            mutate_rows(
                c,
                "research_step_attempts",
                current,
                {"status": "requested", "lease_token_hash": None},
            )
        elif kind == "historical_attempt":
            mutate_rows(
                c,
                "research_step_attempts",
                prior,
                {"error_code": None, "error_message": None},
            )
        elif kind == "historical_event":
            event = next(
                e
                for e in c["rawDatabaseRows"]["transitions"]["research_events"]
                if e["attempt_id"] == prior and e["event_type"] == "attempt_abandoned"
            )
            value = json.loads(event["payload_json"])
            value["reasonCode"] = None
            mutate_rows(
                c,
                "research_events",
                event["id"],
                {
                    "payload_json": json.dumps(
                        value, sort_keys=True, separators=(",", ":")
                    )
                },
            )
        elif kind == "one_field":
            mutate_rows(
                c,
                "research_steps",
                step,
                {"error_message": "Research Attempt lease expired."},
            )
        elif kind == "cross_step":
            foreign = next(
                s["id"]
                for s in c["rawDatabaseRows"]["transitions"]["research_steps"]
                if s["id"] != step
            )
            mutate_rows(c, "research_step_attempts", current, {"step_id": foreign})
        elif kind == "wrong_input":
            mutate_rows(
                c, "research_step_attempts", current, {"input_sha256": "0" * 64}
            )
        elif kind == "new_failure_erased":
            for report in (b, c):
                mutate_rows(
                    report,
                    "research_step_attempts",
                    current,
                    {
                        "status": "failed",
                        "error_code": "new_failure",
                        "error_message": "New attempt failed.",
                    },
                )
            mutate_rows(
                b,
                "research_steps",
                step,
                {
                    "status": "failed",
                    "error_code": "new_failure",
                    "error_message": "New attempt failed.",
                },
            )
            mutate_rows(c, "research_steps", step, {"status": "failed"})
        elif kind == "other_step_field":
            mutate_rows(c, "research_steps", step, {"max_attempts_snapshot": 99})
        result = compare(b, c)
        assert not result["accepted"], (kind, result)
        assert result["retryStepErrorValidationErrors"] or result["unknownDifferences"]

    names = [
        "unclaimed",
        "historical_attempt",
        "historical_event",
        "one_field",
        "cross_step",
        "wrong_input",
        "new_failure_erased",
        "other_step_field",
    ]
    for name in names:
        mutate(name)
    return names
