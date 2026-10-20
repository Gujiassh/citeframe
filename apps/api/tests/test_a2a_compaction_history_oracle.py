"""Default-only compaction projection controls; live reports exercise frozen oracles."""
from copy import deepcopy
import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "infra/scripts"))
import a2a_compaction_history_oracle as oracle
from a2a_r2_publication_oracle import canonical

TABLE = oracle.ATTEMPTS
FIELDS = oracle.FIELDS
SNAPSHOTS = [
    ("rawDatabaseRows", "transitions"),
    ("rawDatabaseRows", "processOne"),
    ("semantics", "normalizedDbRows", "transitions"),
    ("semantics", "normalizedDbRows", "processOne"),
    ("publicationMaintenance", "before"),
    ("publicationMaintenance", "after"),
    *(("publicationLifecycle", index, "rows") for index in range(5)),
]
MUTATIONS = ("missing_version", "missing_checkpoint", "extra_field", "boolean", "null", "string", "nonzero", "checkpoint")


def _at(report, path):
    for key in path:
        report = report[key]
    return report


def _mutate(row, kind):
    if kind == "missing_version":
        del row[FIELDS[0]]
    elif kind == "missing_checkpoint":
        del row[FIELDS[1]]
    elif kind == "extra_field":
        row["memory_unapproved"] = None
    elif kind == "checkpoint":
        row[FIELDS[1]] = "checkpoint-id"
    else:
        row[FIELDS[0]] = {"boolean": False, "null": None, "string": "0", "nonzero": 1}[kind]


@pytest.fixture
def reports():
    baseline = {"researchTableColumns": {TABLE: ["id", "status", "worker_instance_id"]}}
    tables = {TABLE: [{"id": "attempt", "status": "succeeded", "worker_instance_id": "worker-a",
                       FIELDS[0]: 0, FIELDS[1]: None}]}
    candidate = {
        "researchTableColumns": {TABLE: sorted([*baseline["researchTableColumns"][TABLE], *FIELDS])},
        "rawDatabaseRows": {phase: deepcopy(tables) for phase in ("transitions", "processOne")},
        "semantics": {"normalizedDbRows": {phase: deepcopy(tables) for phase in ("transitions", "processOne")}},
        "publicationMaintenance": {phase: deepcopy(tables) for phase in ("before", "after")},
        "publicationLifecycle": [{"rows": deepcopy(tables)} for _ in range(5)],
        "unrelated": {"memory_context_version": 7, "payload": "unchanged"},
    }
    return baseline, candidate


def test_exact_projection_preserves_original_bytes_and_all_other_fields(reports):
    baseline, candidate = reports
    original = canonical(candidate)
    baseline_bytes = canonical(baseline)
    projected = oracle.project_compaction_history(baseline, candidate)
    expected = deepcopy(candidate)
    expected["researchTableColumns"][TABLE] = baseline["researchTableColumns"][TABLE]
    for path in SNAPSHOTS:
        for row in _at(expected, path)[TABLE]:
            for field in FIELDS:
                del row[field]
    assert projected == expected
    assert canonical(candidate) == original
    assert canonical(baseline) == baseline_bytes
    projected["unrelated"]["payload"] = "changed copy"
    assert canonical(candidate) == original


@pytest.mark.parametrize("path", SNAPSHOTS)
@pytest.mark.parametrize("kind", MUTATIONS)
def test_every_snapshot_rejects_missing_extra_type_and_nondefault(reports, path, kind):
    baseline, candidate = reports
    _mutate(_at(candidate, path)[TABLE][0], kind)
    original = canonical(candidate)
    result = oracle.compare_compaction_history(baseline, candidate)
    assert result["accepted"] is False
    assert result["compactionHistoricalDeltaValid"] is False
    assert canonical(candidate) == original


@pytest.mark.parametrize("kind", ["missing_version", "missing_checkpoint", "duplicate_version", "duplicate_checkpoint", "extra", "old_missing", "not_list"])
def test_exact_schema_presence_and_cardinality(reports, kind):
    baseline, candidate = reports
    columns = candidate["researchTableColumns"][TABLE]
    if kind.startswith("missing_"):
        columns.remove(FIELDS[0 if kind.endswith("version") else 1])
    elif kind.startswith("duplicate_"):
        columns.append(FIELDS[0 if kind.endswith("version") else 1])
        columns.sort()
    elif kind == "extra":
        columns.append("memory_future")
        columns.sort()
    elif kind == "old_missing":
        columns.remove("status")
    else:
        candidate["researchTableColumns"][TABLE] = tuple(columns)
    assert not oracle.compare_compaction_history(baseline, candidate)["compactionHistoricalDeltaValid"]


@pytest.mark.parametrize("path", SNAPSHOTS)
def test_missing_attempt_capture_is_not_vacuous_success(reports, path):
    baseline, candidate = reports
    del _at(candidate, path)[TABLE]
    assert not oracle.compare_compaction_history(baseline, candidate)["compactionHistoricalDeltaValid"]


def test_original_raw_normalized_validation_precedes_projection(reports):
    baseline, candidate = reports
    candidate["rawDatabaseRows"]["processOne"][TABLE][0]["status"] = "failed"
    result = oracle.compare_compaction_history(baseline, candidate)
    assert not result["compactionHistoricalDeltaValid"]
    assert "rawDatabaseRows.projection mismatch" in result["compactionErrors"]


@pytest.mark.parametrize("stored", [False, True])
def test_delegates_projected_copy_to_unchanged_oracle(reports, monkeypatch, stored):
    baseline, candidate = reports
    original = canonical(candidate)
    seen = []
    def downstream(base, projected, *, stored_responses):
        seen.append((base, projected, stored_responses))
        return {"accepted": False, "unknownDifferences": ["unchanged strict rejection"]}
    monkeypatch.setattr(oracle, "compare_conflict_history", downstream)
    result = oracle.compare_compaction_history(baseline, candidate, stored_responses=stored)
    assert result == {"accepted": False, "unknownDifferences": ["unchanged strict rejection"],
                      "compactionHistoricalDeltaValid": True}
    assert seen == [(baseline, oracle.project_compaction_history(baseline, candidate), stored)]
    assert canonical(candidate) == original


def legacy_controls_payload(payload):
    """Feed existing controls validated copies without changing their original evidence."""
    projected = deepcopy(payload)
    for name in ("rawCandidateReport", "rawStoredReplayReport"):
        projected[name] = oracle.project_compaction_history(payload["rawBaselineReport"], payload[name])
    return projected


def verify_compaction_negative_controls(payload):
    baseline = payload["rawBaselineReport"]
    original = canonical(payload)
    count = 0
    for name in ("rawCandidateReport", "rawStoredReplayReport"):
        source = payload[name]
        stored = name == "rawStoredReplayReport"
        assert oracle.compare_compaction_history(baseline, source, stored_responses=stored)["accepted"]
        for path in SNAPSHOTS:
            for kind in MUTATIONS:
                candidate = deepcopy(source)
                _mutate(_at(candidate, path)[TABLE][0], kind)
                result = oracle.compare_compaction_history(baseline, candidate, stored_responses=stored)
                assert not result["accepted"] and not result["compactionHistoricalDeltaValid"], (name, path, kind)
                count += 1
    assert canonical(payload) == original
    for report, hash_key in (("rawBaselineReport", "rawBaselineSha256"),
                             ("rawCandidateReport", "rawCandidateSha256"),
                             ("rawStoredReplayReport", "rawStoredReplaySha256")):
        assert hashlib.sha256(canonical(payload[report])).hexdigest() == payload[hash_key]
    return count

@pytest.mark.parametrize("path", SNAPSHOTS)
def test_later_attempts_are_validated(reports, path):
    baseline, candidate = reports
    rows = _at(candidate, path)[TABLE]
    rows.append({**rows[0], "id": "second", FIELDS[0]: 1})
    assert not oracle.compare_compaction_history(baseline, candidate)["compactionHistoricalDeltaValid"]


@pytest.mark.parametrize("value", [0.0, True, -1, [], {}])
def test_version_requires_exact_integer_zero(reports, value):
    baseline, candidate = reports
    candidate["rawDatabaseRows"]["transitions"][TABLE][0][FIELDS[0]] = value
    assert not oracle.compare_compaction_history(baseline, candidate)["compactionHistoricalDeltaValid"]


@pytest.mark.parametrize("value", [False, 0, "", [], {}])
def test_checkpoint_requires_explicit_null(reports, value):
    baseline, candidate = reports
    candidate["rawDatabaseRows"]["transitions"][TABLE][0][FIELDS[1]] = value
    assert not oracle.compare_compaction_history(baseline, candidate)["compactionHistoricalDeltaValid"]


@pytest.mark.parametrize("kind", ["raw_phase", "normalized_phase", "empty_attempts", "missing_lifecycle", "extra_lifecycle"])
def test_capture_cardinality_is_required(reports, kind):
    baseline, candidate = reports
    if kind == "raw_phase":
        del candidate["rawDatabaseRows"]["transitions"]
    elif kind == "normalized_phase":
        del candidate["semantics"]["normalizedDbRows"]["processOne"]
    elif kind == "empty_attempts":
        candidate["publicationMaintenance"]["before"][TABLE] = []
    elif kind == "missing_lifecycle":
        candidate["publicationLifecycle"].pop()
    else:
        candidate["publicationLifecycle"].append(deepcopy(candidate["publicationLifecycle"][0]))
    assert not oracle.compare_compaction_history(baseline, candidate)["compactionHistoricalDeltaValid"]
