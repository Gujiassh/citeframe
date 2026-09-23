"""Cross-version controls applied to actual reports from current candidate execution."""
from copy import deepcopy
import base64
import json


def verify_feature_negative_controls(payload):
    from a2a_conflict_feature_oracle import compare_conflict_history as compare_historical_feature
    baseline = payload["rawBaselineReport"]
    source = payload["rawCandidateReport"]
    assert compare_historical_feature(baseline, source)["accepted"]
    for change in ("wrong_actor", "policy_forgery", "prompt_drift", "default_downgrade", "historical_adaptive_work"):
        candidate = deepcopy(source)
        rows = candidate["semantics"]["normalizedDbRows"]["processOne"]
        if change == "wrong_actor": rows["human_decisions"][0]["decided_by_user_id"] = "foreign"
        if change == "policy_forgery": rows["human_decisions"][0]["decision_origin"] = "policy"
        if change == "prompt_drift": candidate["workflowEvidence"]["prompts"][0]["sha256"] = "0" * 64
        if change == "default_downgrade": candidate["workflowEvidence"]["currentDefaultWorkflowId"] = candidate["workflowEvidence"]["workflowId"]
        if change == "historical_adaptive_work": rows["research_adaptive_turns"].append({"turn_number": 0})
        assert not compare_historical_feature(baseline, candidate)["accepted"], change
    stored = deepcopy(payload["rawStoredReplayReport"])
    responses = stored["semantics"]["exactPayloadBytes"]["processOne"]["apiResponses"]
    dto = json.loads(base64.b64decode(responses[1])); dto["decision"]["decisionOrigin"] = "human"
    responses[1] = base64.b64encode(json.dumps(dto).encode()).decode()
    assert not compare_historical_feature(baseline, stored, stored_responses=True)["accepted"]
