"""Executable mutations of live A2 reports; no replacement historical fixture."""
from copy import deepcopy
import base64
import importlib
import json
from pathlib import Path
import sys


def verify_negative_controls(payload):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "infra/scripts"))
    compare = importlib.import_module("a2a_r2_delta").compare
    base = payload["rawBaselineReport"]
    source = payload["rawCandidateReport"]
    require_original = deepcopy(source)
    assert compare(base, source)["accepted"]
    assert source == require_original, "oracle must not rewrite raw snapshots"

    def rows(c):
        return c["semantics"]["normalizedDbRows"]["processOne"]

    def final(c):
        return next(a for a in rows(c)["research_artifacts"] if a["artifact_kind"] == "final_report")

    def change_report(c):
        key = final(c)["object_key"]
        c["semantics"]["exactPayloadBytes"]["processOne"]["objectPayloads"][key] = base64.b64encode(b"wrong report").decode()

    def change_event(c, field, value):
        e = next(e for e in rows(c)["research_events"] if e["event_type"] == "run_completed")
        e[field] = value

    def duplicate_budget(c):
        rs = rows(c)["research_budget_ledgers"]
        rs.append(deepcopy(rs[0]))

    def duplicate_event(c):
        es = rows(c)["research_events"]
        terminal = next(e for e in es if e["event_type"] == "run_completed")
        terminal["id"] = next(e["id"] for e in es if e is not terminal)

    def missing_event(c):
        es = rows(c)["research_events"]
        es[:] = [e for e in es if e["event_type"] != "run_completed"]

    def wire_event(c):
        es = c["semantics"]["exactEventBytes"]["processOne"]
        event = json.loads(base64.b64decode(es[-1]))
        event["id"] = "forged-event-id"
        es[-1] = base64.b64encode(json.dumps(event).encode()).decode()

    controls = {
        "report_bytes": change_report,
        "evidence_relation": lambda c: rows(c)["research_claim_evidence"][0].update(evidence_snapshot_id="foreign"),
        "unauthorized_adoption": lambda c: c["publicationLifecycle"][2]["authorization"].update(role=None),
        "object_owner": lambda c: rows(c)["research_publication_intents"][0].update(run_id="foreign"),
        "intent_snapshot": lambda c: rows(c)["research_publication_intents"][0].update(execution_snapshot_id="foreign"),
        "intent_owner": lambda c: c["publicationLifecycle"][1]["rows"]["research_publication_intents"][0].update(claim_owner="foreign"),
        "intent_fence": lambda c: c["publicationLifecycle"][2]["rows"]["research_publication_intents"][0].update(claim_token_hash="0" * 64),
        "extra_business_step": lambda c: rows(c)["research_steps"].append(deepcopy(rows(c)["research_steps"][0])),
        "duplicate_accounting": duplicate_budget,
        "unknown_table": lambda c: rows(c).update(research_unapproved=[]),
        "unknown_field": lambda c: rows(c)["research_runs"][0].update(unknown=1),
        "unknown_empty_table_column": lambda c: c["researchTableColumns"]["research_evaluation_runs"].append("unapproved"),
        "raw_only_mutation": lambda c: c["rawDatabaseRows"]["processOne"]["research_runs"][0].update(state_version=999),
        "orphan_object": lambda c: c["semantics"]["exactPayloadBytes"]["processOne"]["objectPayloads"].update(foreign="YQ=="),
        "unknown_intent_field": lambda c: rows(c)["research_publication_intents"][0].update(unknown=1),
        "terminal_wrong_run": lambda c: change_event(c, "run_id", "foreign"),
        "terminal_wrong_dedupe": lambda c: change_event(c, "dedupe_key", "foreign"),
        "terminal_payload": lambda c: change_event(c, "payload_json", "{}"),
        "terminal_duplicate": duplicate_event,
        "terminal_missing": missing_event,
        "wire_identity": wire_event,
        "maintenance_extra_call": lambda c: c["publicationMaintenance"]["outputs"].insert(0, True),
        "maintenance_provider": lambda c: c["publicationMaintenance"]["providerCallsAfter"].append("synthesizer"),
        "maintenance_budget": lambda c: c["publicationMaintenance"]["after"]["research_budget_ledgers"][0].update(state_version=999),
        "unexplained_timestamp": lambda c: rows(c)["research_claims"][0].update(created_at="2026-08-25 04:00:00.000000"),
    }
    for name, mutate in controls.items():
        candidate = deepcopy(source)
        mutate(candidate)
        result = compare(base, candidate)
        assert not result["accepted"], (name, result)
        assert result["unknownDifferences"] or result["r2ValidationErrors"], name
    return list(controls)
