"""Approved R2 deltas only; historical A2 semantics stay strict elsewhere."""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json

from a2a_r2_publication_oracle import INTENTS, canonical, one, require, validate_publication


def differences(left, right, path="semantics"):
    if type(left) is not type(right):
        return [path]
    if isinstance(left, dict):
        result = [f"{path}.{k}" for k in sorted(left.keys() ^ right.keys())]
        for key in sorted(left.keys() & right.keys()):
            result.extend(differences(left[key], right[key], f"{path}.{key}"))
        return result
    if isinstance(left, list):
        if len(left) != len(right):
            return [path + ".length"]
        return [p for i, (a, b) in enumerate(zip(left, right, strict=True))
                for p in differences(a, b, f"{path}[{i}]")]
    return [] if left == right else [path]


def event_map(events):
    identity = {(e["run_id"], e["dedupe_key"]): e for e in events}
    require(len(identity) == len(events), "events.duplicate run/dedupe_key")
    require(len({e["id"] for e in events}) == len(events), "events.duplicate id")
    require(len({(e["run_id"], e["seq"]) for e in events}) == len(events), "events.duplicate seq")
    return identity


def map_terminal_events(baseline, candidate, final):
    old_events = baseline["normalizedDbRows"]["processOne"]["research_events"]
    new_events = candidate["normalizedDbRows"]["processOne"]["research_events"]
    old, new = event_map(old_events), event_map(new_events)
    require(old.keys() == new.keys(), "events.missing/extra identity")
    expected = {
        "step-succeeded:" + final["generated_by_attempt_id"]: "step_succeeded",
        "artifact-published:" + final["id"]: "artifact_published",
        "run-completed:" + final["id"]: "run_completed",
    }
    changed = {key for key in old if old[key]["id"] != new[key]["id"]}
    require(changed == {(final["run_id"], key) for key in expected}, "events.exact three terminal identities")
    mapping = []
    for dedupe, kind in expected.items():
        key = (final["run_id"], dedupe)
        before, after = old[key], new[key]
        require(before["event_type"] == after["event_type"] == kind, "events.type")
        require(after == {**before, "id": after["id"]}, "events.terminal payload/seq/references")
        mapping.append({"runId": key[0], "dedupeKey": key[1], "eventType": kind,
                        "seq": after["seq"], "baselineId": before["id"], "candidateId": after["id"]})
    require([m["seq"] for m in mapping] == [38, 39, 40], "events.terminal order")
    require(len({m["candidateId"] for m in mapping}) == len({m["baselineId"] for m in mapping}) == 3,
            "events.mapping bijection")
    # Check every wire identity against its own DB, before editing these three ID fields.
    for semantics, db in ((baseline, old), (candidate, new)):
        wire = [json.loads(base64.b64decode(b, validate=True)) for b in semantics["exactEventBytes"]["processOne"]]
        require(len(wire) == len(db), "events.wire cardinality")
        require(len({e["id"] for e in wire}) == len(wire), "events.wire duplicate")
        require([e["seq"] for e in wire] == sorted(e["seq"] for e in db.values()), "events.wire order")
        for e in wire:
            row = db.get((e["runId"], e["dedupeKey"]))
            require(row is not None and e["id"] == row["id"] and e["type"] == row["event_type"]
                    and e["seq"] == row["seq"] and e["stepId"] == row["step_id"]
                    and e["attemptId"] == row["attempt_id"]
                    and e["payload"] == json.loads(row["payload_json"]), "events.wire DB references")
    by_id = {m["candidateId"]: m["baselineId"] for m in mapping}
    for row in new_events:
        if row["id"] in by_id:
            row["id"] = by_id[row["id"]]
    new_events.sort(key=canonical)
    for index, encoded in enumerate(candidate["exactEventBytes"]["processOne"]):
        row = json.loads(base64.b64decode(encoded, validate=True))
        if row["id"] in by_id:
            row["id"] = by_id[row["id"]]
            candidate["exactEventBytes"]["processOne"][index] = base64.b64encode(canonical(row)).decode()
    return mapping


def compare(baseline, candidate):
    left, right = baseline["semantics"], deepcopy(candidate["semantics"])
    raw_equal = canonical(left) == canonical(right)
    errors, mapping, object_mapping = [], [], []
    try:
        final, old_key, new_key = validate_publication(candidate)
        columns = deepcopy(candidate["researchTableColumns"])
        require(columns.pop(INTENTS) == sorted(candidate["semantics"]["normalizedDbRows"]["processOne"][INTENTS][0]), "schema.intent fields")
        require(columns == baseline["researchTableColumns"], "schema.unknown table/field")
        for report in (baseline, candidate):
            validate_raw_rows(report)
        old_final = one(left["normalizedDbRows"]["processOne"]["research_artifacts"], id=final["id"])
        require(old_final["object_key"] == old_key, "object.baseline owner")
        require(final == {**old_final, "object_key": new_key}, "object.artifact fields")
        for phase in ("transitions", "processOne"):
            require(INTENTS not in left["normalizedDbRows"][phase], "baseline unexpected R2 intent")
        require(right["normalizedDbRows"]["transitions"][INTENTS] == [], "transition unexpected intent")
        # Removal follows complete validation, including lifecycle and maintenance.
        del right["normalizedDbRows"]["transitions"][INTENTS]
        del right["normalizedDbRows"]["processOne"][INTENTS]
        one(right["normalizedDbRows"]["processOne"]["research_artifacts"], id=final["id"])["object_key"] = old_key
        pairs = ((left["exactPayloadBytes"]["processOne"]["objectPayloads"], right["exactPayloadBytes"]["processOne"]["objectPayloads"]),
                 (left["terminalProcessSemantics"]["objectPayloads"], right["terminalProcessSemantics"]["objectPayloads"]))
        for old, new in pairs:
            require(old_key not in new and new_key not in old, "object.key collision")
            require(old[old_key] == new[new_key], "object.exact bytes")
            new[old_key] = new.pop(new_key)
        object_mapping = [{"artifactId": final["id"], "baselineKey": old_key, "candidateKey": new_key,
                           "contentSha256": final["content_sha256"]}]
        mapping = map_terminal_events(left, right, final)
        require(baseline["publicationLifecycle"] == [], "baseline.lifecycle")
        bm = baseline["publicationMaintenance"]
        require(bm["before"] == bm["after"] == left["normalizedDbRows"]["processOne"], "baseline.maintenance rows")
        require(bm["outputs"] == [False] and bm["providerCallsBefore"] == bm["providerCallsAfter"], "baseline.maintenance")
        require(baseline["schedulerEvidence"] == {"handledAttemptCount": 3, "maintenanceCallCount": 0,
                "processOneOutputs": [True] * 3 + [False]}, "baseline.schedule")
        require(candidate["schedulerEvidence"] == {"handledAttemptCount": 8, "maintenanceCallCount": 1,
                "processOneOutputs": [True] * 9 + [False]}, "candidate.schedule")
    except (ValueError, KeyError, TypeError, IndexError) as error:
        errors.append(str(error))
    unknown = differences(left, right)
    return {
        "rawEqual": raw_equal,
        "historicalInvariantsEqual": not unknown,
        "r2DeltaValid": not errors,
        "unknownDifferences": unknown,
        "r2ValidationErrors": errors,
        "accepted": not errors and not unknown,
        "eventIdBijection": mapping,
        "objectKeyBijection": object_mapping,
        "rawBaselineSha256": hashlib.sha256(canonical(baseline)).hexdigest(),
        "rawCandidateSha256": hashlib.sha256(canonical(candidate)).hexdigest(),
    }


def validate_raw_rows(report):
    # Preserve the original raw records. Only the pre-existing process identity
    # normalization may differ from their historical-comparison projection.
    for phase, tables in report["rawDatabaseRows"].items():
        projected = deepcopy(tables)
        for table_rows in projected.values():
            for row in table_rows:
                if "worker_instance_id" in row:
                    owner = row["worker_instance_id"]
                    if isinstance(owner, str) and owner.startswith("worker-") and owner[7:].isdigit():
                        row["worker_instance_id"] = "<process-worker-instance-id>"
                if isinstance(row.get("payload_json"), str):
                    row["payload_json"] = canonical(json.loads(row["payload_json"])).decode()
            table_rows.sort(key=canonical)
        require(projected == report["semantics"]["normalizedDbRows"][phase], "rawDatabaseRows.projection mismatch")
