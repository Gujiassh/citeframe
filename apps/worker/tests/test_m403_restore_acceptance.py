from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts/m403_restore_acceptance.py"
RUNNER_PATH = Path(__file__).resolve().parents[3] / "infra/scripts/run-m403-acceptance.sh"
SCRIPT_SPEC = importlib.util.spec_from_file_location("m403_restore_acceptance", SCRIPT_PATH)
assert SCRIPT_SPEC is not None and SCRIPT_SPEC.loader is not None
m403 = importlib.util.module_from_spec(SCRIPT_SPEC)
sys.modules[SCRIPT_SPEC.name] = m403
SCRIPT_SPEC.loader.exec_module(m403)


def _snapshot() -> dict[str, object]:
    return {
        "schemaVersion": m403.SCHEMA_VERSION,
        "workspaceId": m403.IDS["workspace"],
        "semanticSha256": "a" * 64,
        "tableCounts": {"assets": 5},
        "objectCount": 9,
        "checks": {"imageProductionDisabled": True},
        "rows": {"assets": [{"id": "asset"}]},
        "objects": [{"objectKey": "fixture", "sha256": "b" * 64}],
        "visualReplay": {"pdf": {"pixelSha256": "c" * 64}},
    }


def _semantic_rows() -> dict[str, list[dict[str, object]]]:
    return {
        "assets": [
            {"id": m403.IDS["pdf"], "asset_kind": "pdf", "status": "ready", "deleted_at": None},
            {"id": m403.IDS["image"], "asset_kind": "image", "status": "ready", "deleted_at": None},
            {"id": m403.IDS["deleted-pdf"], "asset_kind": "pdf", "status": "ready", "deleted_at": "2026-01-01"},
            {"id": m403.IDS["deleted-image"], "asset_kind": "image", "status": "ready", "deleted_at": "2026-01-01"},
            {"id": m403.IDS["failed-image"], "asset_kind": "image", "status": "failed", "deleted_at": None},
        ],
        "catalog": [
            {"kind": "pdf", "enabled": True},
            {"kind": "image", "enabled": False},
        ],
        "message_citations": [
            {"citation_index": 0, "processing_generation_snapshot": 1},
            {"citation_index": 1, "processing_generation_snapshot": 2},
            {"citation_index": 2, "processing_generation_snapshot": 1},
            {"citation_index": 3, "processing_generation_snapshot": 2},
        ],
        "message_input_evidence": [
            {"asset_kind_snapshot": "image", "processing_generation_snapshot": 1},
        ],
        "note_sources": [
            {"source_order": 0, "message_citation_id": "citation-pdf"},
            {"source_order": 1, "message_citation_id": "citation-image"},
            {"source_order": 2, "message_citation_id": None},
        ],
        "message_retrieval_scope_assets": [
            {"asset_id": m403.IDS["image"]},
            {"asset_id": m403.IDS["pdf"]},
        ],
    }


def _objects() -> list[dict[str, object]]:
    return [
        {"expectedExists": True, "exists": True},
        {"expectedExists": False, "exists": False},
    ]


def test_verify_accepts_only_exact_semantic_snapshot() -> None:
    before = _snapshot()
    result = m403.verify(before, copy.deepcopy(before))
    assert result["passed"] is True
    assert result["mismatches"] == []

    after = copy.deepcopy(before)
    after["objects"][0]["sha256"] = "d" * 64
    with pytest.raises(RuntimeError, match="objects"):
        m403.verify(before, after)


def test_verify_rejects_unknown_snapshot_schema() -> None:
    before = _snapshot()
    after = copy.deepcopy(before)
    after["schemaVersion"] = "m403-restore-acceptance-v2"
    with pytest.raises(ValueError, match="schema mismatch"):
        m403.verify(before, after)


def test_semantic_checks_cover_history_direct_note_and_deleted_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("M403_EXPECT_IMAGE_ENABLED", raising=False)
    checks = m403._semantic_checks(_semantic_rows(), _objects())
    assert all(checks.values())


def test_semantic_checks_accept_enabled_image_catalog_when_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("M403_EXPECT_IMAGE_ENABLED", "true")
    rows = _semantic_rows()
    rows["catalog"][1]["enabled"] = True

    checks = m403._semantic_checks(rows, _objects())

    assert checks["imageProductionEnabled"] is True


def test_semantic_checks_reject_invalid_image_expectation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("M403_EXPECT_IMAGE_ENABLED", "enabled")

    with pytest.raises(ValueError, match="must be true or false"):
        m403._semantic_checks(_semantic_rows(), _objects())


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda rows, objects: rows["catalog"][1].update(enabled=True), "imageProductionDisabled"),
        (lambda rows, objects: rows["note_sources"][2].update(message_citation_id="invented"), "noteSourceKinds"),
        (lambda rows, objects: objects[1].update(exists=True), "deletedObjectsAbsent"),
        (lambda rows, objects: rows["message_retrieval_scope_assets"].reverse(), "selectedScopeOrder"),
    ],
)
def test_semantic_checks_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    mutation,
    expected: str,
) -> None:
    monkeypatch.delenv("M403_EXPECT_IMAGE_ENABLED", raising=False)
    rows = _semantic_rows()
    objects = _objects()
    mutation(rows, objects)
    with pytest.raises(RuntimeError, match=expected):
        m403._semantic_checks(rows, objects)


def test_runner_final_cleanup_fails_closed_on_inspection_or_report_errors() -> None:
    runner = RUNNER_PATH.read_text()

    for status in (
        "container_inspect_status",
        "volume_inspect_status",
        "network_inspect_status",
    ):
        assert f"{status}=0" in runner
        assert f'"${status}" -eq 0' in runner
    assert "cleanup_report_status=0" in runner
    assert '"$cleanup_report_status" -ne 0' in runner
    assert 'report["releaseGatePassed"] = bool(report.get("releaseGatePassed")) and cleanup["passed"]' in runner


def test_runner_binds_historical_viewer_to_snapshot_oracles() -> None:
    runner = RUNNER_PATH.read_text()

    assert 'before["visualReplay"]["images"]' in runner
    assert 'if item["generation"] == 1' in runner
    assert 'before["rows"]["spatial_locator_regions"]' in runner
    assert '"imagePixelOraclePassed": image_pixel_oracle_passed' in runner
    assert '"regionOraclePassed": region_oracle_passed' in runner


def test_runner_propagates_validated_image_catalog_expectation() -> None:
    runner = RUNNER_PATH.read_text()
    compose_override = (RUNNER_PATH.parents[1] / "docker/compose.m403.yml").read_text()

    assert 'M403_EXPECT_IMAGE_ENABLED=${M403_EXPECT_IMAGE_ENABLED:-false}' in runner
    assert "export M403_EXPECT_IMAGE_ENABLED" in runner
    assert "m403_invalid_image_expectation" in runner
    assert "M403_EXPECT_IMAGE_ENABLED: ${M403_EXPECT_IMAGE_ENABLED:-false}" in compose_override
