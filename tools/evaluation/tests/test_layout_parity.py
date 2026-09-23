"""Semantic oracle captured from 50af19d before the package relocation."""

from dataclasses import asdict
from itertools import count
import json
from pathlib import Path

import pytest

from citeframe_evaluation.runtime import research
from citeframe_evaluation.contracts import (
    DEFAULT_PACKAGE_PATH,
    DEFAULT_PACKAGE_V5_PATH,
    load_evaluation_package,
    score_case,
)
from citeframe_evaluation.runtime import run_quick_case, run_research_case
from r803_test_helpers import DeterministicProvider


def _without_elapsed_measurements(value):
    if isinstance(value, dict):
        return {
            key: _without_elapsed_measurements(item)
            for key, item in value.items()
            if key not in {"duration_ms", "wall_time_ms", "wallTimeMs"}
        }
    if isinstance(value, list):
        return [_without_elapsed_measurements(item) for item in value]
    return value


@pytest.mark.parametrize("clock_step, expected_speedup", [(0, None), (100, 1.0)])
def test_frozen_case_outputs_and_scores_match_pre_relocation_baseline(
    monkeypatch, clock_step, expected_speedup
):
    # Branch durations depend on host clock resolution. Exercise both timing paths
    # explicitly while retaining the pre-relocation fixture bytes.
    ticks = count(0, clock_step)
    monkeypatch.setattr(research, "monotonic_ns", lambda: next(ticks))
    rows = []
    for path in (DEFAULT_PACKAGE_PATH, DEFAULT_PACKAGE_V5_PATH):
        package = load_evaluation_package(path)
        for case in package.cases:
            for mode, execute in (
                ("quick", run_quick_case),
                ("research", run_research_case),
            ):
                result = execute(package, case, DeterministicProvider())
                rows.append(
                    {
                        "package": path.name,
                        "case": case["id"],
                        "mode": mode,
                        "execution": asdict(result),
                        "score": score_case(case, result),
                    }
                )
    # JSON roundtrip matches the serialized tuple/list representation of the baseline.
    actual = _without_elapsed_measurements(json.loads(json.dumps(rows)))
    expected = json.loads(
        (Path(__file__).parent / "fixtures/layout-baseline.json").read_text(
            encoding="utf-8"
        )
    )
    for actual_row, expected_row in zip(actual, expected, strict=True):
        expected_metric = expected_speedup if actual_row["mode"] == "research" else None
        assert actual_row["execution"]["parallel_speedup"] == expected_metric
        assert expected_row["execution"]["parallel_speedup"] is None
        # The captured fixture used a zero-duration clock. Only adapt this derived
        # timing field after independently checking its controlled-clock value.
        expected_row["execution"]["parallel_speedup"] = expected_metric
    assert actual == expected
