"""Issue 43 default-only Attempt delta before the frozen historical oracles."""
from copy import deepcopy

from a2a_conflict_feature_oracle import compare_conflict_history
from a2a_r2_delta import validate_raw_rows
from a2a_r2_publication_oracle import require

ATTEMPTS = "research_step_attempts"
FIELDS = ("memory_context_version", "memory_checkpoint_id")


def _snapshots(report):
    for collection, groups in (
        ("rawDatabaseRows", report["rawDatabaseRows"]),
        ("normalizedDbRows", report["semantics"]["normalizedDbRows"]),
    ):
        require(set(groups) == {"transitions", "processOne"}, f"compaction.{collection}.phases")
        for phase, tables in groups.items():
            yield f"{collection}.{phase}", tables
    maintenance = report["publicationMaintenance"]
    for phase in ("before", "after"):
        yield f"publicationMaintenance.{phase}", maintenance[phase]
    lifecycle = report["publicationLifecycle"]
    require(isinstance(lifecycle, list) and len(lifecycle) == 5, "compaction.lifecycle.cardinality")
    for index, phase in enumerate(lifecycle):
        yield f"publicationLifecycle.{index}", phase["rows"]


def project_compaction_history(baseline, candidate):
    old = baseline["researchTableColumns"][ATTEMPTS]
    columns = candidate["researchTableColumns"][ATTEMPTS]
    require(isinstance(old, list) and all(isinstance(c, str) for c in old)
            and len(old) == len(set(old)) and not set(FIELDS).intersection(old),
            "compaction.baseline.schema")
    require(isinstance(columns, list) and columns == sorted([*old, *FIELDS]),
            "compaction.attempt.schema")
    for path, tables in _snapshots(candidate):
        rows = tables[ATTEMPTS]
        require(isinstance(rows, list) and bool(rows), f"compaction.{path}.attempts")
        for index, row in enumerate(rows):
            location = f"compaction.{path}.{index}"
            require(isinstance(row, dict) and set(row) == set(columns), location + ".fields")
            require(type(row[FIELDS[0]]) is int and row[FIELDS[0]] == 0, location + ".version")
            require(row[FIELDS[1]] is None, location + ".checkpoint")
    # Validate original evidence before discarding either additive field.
    validate_raw_rows(candidate)
    projected = deepcopy(candidate)
    projected["researchTableColumns"][ATTEMPTS] = [c for c in columns if c not in FIELDS]
    for _, tables in _snapshots(projected):
        for row in tables[ATTEMPTS]:
            for field in FIELDS:
                del row[field]
    return projected


def compare_compaction_history(baseline, candidate, *, stored_responses=False):
    try:
        projected = project_compaction_history(baseline, candidate)
    except (KeyError, ValueError, TypeError, IndexError, AttributeError) as error:
        return {"accepted": False, "compactionHistoricalDeltaValid": False,
                "compactionErrors": [str(error)]}
    result = compare_conflict_history(baseline, projected, stored_responses=stored_responses)
    return {**result, "compactionHistoricalDeltaValid": True}
