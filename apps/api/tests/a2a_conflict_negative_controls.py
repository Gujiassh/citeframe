"""Issue 25 mutations on actual candidate reports, outside R2 normalization."""

from copy import deepcopy
import base64
import json
from a2a_conflict_current_acceptance import assert_v4_completion
from a2a_conflict_feature_oracle import compare_conflict_history


def verify_conflict_negative_controls(payload):
    base = payload["rawBaselineReport"]
    source = payload["rawCandidateReport"]
    assert compare_conflict_history(base, source)["accepted"]
    for kind in ("journal_row", "journal_schema", "wrong_default", "wrong_io"):
        changed = deepcopy(source)
        if kind == "journal_row":
            changed["rawDatabaseRows"]["processOne"]["research_conflict_turns"].append(
                {"phase": "inspect"}
            )
        elif kind == "journal_schema":
            changed["researchTableColumns"]["research_conflict_turns"].append(
                "unapproved"
            )
        elif kind == "wrong_default":
            changed["workflowEvidence"]["currentDefaultWorkflowId"] = (
                "30000000-0000-4000-8000-000000000001"
            )
        else:
            changed["workflowEvidence"]["currentDefaultAgentSchema"] = (
                "research-agent-results-v2"
            )
        assert not compare_conflict_history(base, changed)["accepted"], kind

    def check(report):
        semantics = report["semantics"]
        exact = semantics["exactPayloadBytes"]["processOne"]
        objects = {k: base64.b64decode(v) for k, v in exact["objectPayloads"].items()}
        assert_v4_completion(
            semantics["normalizedDbRows"]["processOne"],
            objects,
            exact["apiResponses"],
            report["workflowEvidence"],
        )

    current = payload["rawCurrentDefaultReport"]
    check(current)
    for kind in (
        "wrong_version",
        "missing_journal",
        "wrong_snapshot",
        "wrong_attempt",
        "changed_result_hash",
        "changed_original",
    ):
        changed = deepcopy(current)
        rows = changed["semantics"]["normalizedDbRows"]["processOne"]
        if kind == "wrong_version":
            changed["workflowEvidence"]["workflowVersion"] = 3
        elif kind == "missing_journal":
            rows["research_conflict_turns"] = []
        elif kind == "wrong_snapshot":
            rows["research_conflict_turns"][0]["execution_snapshot_id"] = "foreign"
        elif kind == "wrong_attempt":
            rows["research_conflict_turns"][0]["created_by_attempt_id"] = "foreign"
        elif kind == "changed_result_hash":
            rows["research_conflict_turns"][0]["result_sha256"] = "0" * 64
        else:
            rows["research_claims"][0]["id"] = "foreign"
        try:
            check(changed)
        except (AssertionError, KeyError, StopIteration):
            pass
        else:
            raise AssertionError(kind)
    return 10
