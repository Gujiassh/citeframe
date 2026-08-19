"""V5-B Document recovery/restore acceptance unit checks.

Ownership: B-INT-MIXED / B-RESTORE helper coverage. Does not own Worker document
adapter unit tests. Live PostgreSQL/MinIO evidence is skipped only when
unavailable and that result is stated explicitly.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.acceptance

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts/v5b_document_restore_acceptance.py"
SCRIPT_SPEC = importlib.util.spec_from_file_location("v5b_document_restore_acceptance", SCRIPT_PATH)
assert SCRIPT_SPEC is not None and SCRIPT_SPEC.loader is not None
v5b = importlib.util.module_from_spec(SCRIPT_SPEC)
sys.modules[SCRIPT_SPEC.name] = v5b
SCRIPT_SPEC.loader.exec_module(v5b)

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = REPO_ROOT / "docs/fixtures/document-modality"
FIXTURE_PATH = FIXTURE_DIR / "markdown-note.fixture.json"
GENERATOR_PATH = FIXTURE_DIR / "generate_fixture.py"


def _load_fixture_generator():
    """Import the durable fixture generator module (production parser path)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "document_modality_generate_fixture",
        GENERATOR_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _valid_live_snapshot(*, deleted: bool = True) -> dict:
    """Build a structurally valid live oracle from the offline fixture shape.

    Default models the after-delete historical evidence path (sourceAvailable=false)
    while retaining locator/citation/note-source rows. Pass deleted=False for an
    active Document asset with sourceAvailable=true.
    """
    fixture = v5b.snapshot(mode="fixture")
    scoped = copy.deepcopy(fixture["scopedRows"])
    if deleted:
        scoped["assets"][0]["deleted_at"] = "2026-08-05T00:00:00+00:00"
    else:
        scoped["assets"][0]["deleted_at"] = None
    historical = v5b._build_historical_evidence(scoped)
    live = {
        "schemaVersion": v5b.SCHEMA_VERSION,
        "evidenceMode": "live",
        "livePostgresMinio": True,
        "workspaceId": fixture["workspaceId"],
        "assetId": fixture["assetId"],
        "objectPrefix": fixture["objectPrefix"],
        "scopedRows": scoped,
        "objects": copy.deepcopy(fixture["objects"]),
        "typedTables": copy.deepcopy(fixture["typedTables"]),
        "catalog": copy.deepcopy(fixture["catalog"]),
        "historicalEvidence": historical,
    }
    live["semanticSha256"] = v5b._compute_semantic_sha256(live)
    return live


def test_checked_in_fixture_matches_production_parser_generator() -> None:
    """Parity oracle: checked-in JSON must match the production generator/parser path."""
    generator = _load_fixture_generator()
    checked_in = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    regenerated = generator.build_fixture(source_path=FIXTURE_DIR / "markdown-note.md")

    assert regenerated["sourceSha256"] == checked_in["sourceSha256"]
    assert regenerated["normalizedContentSha256"] == checked_in["normalizedContentSha256"]
    assert regenerated["normalizedText"] == checked_in["normalizedText"]
    assert regenerated["contentUnitKinds"] == ["document_text_chunk"]
    assert "document_block" not in regenerated["contentUnitKinds"]
    assert regenerated["retrieval"]["unitKinds"] == ["document_text_chunk"]

    assert len(regenerated["blocks"]) == len(checked_in["blocks"])
    for actual, expected in zip(regenerated["blocks"], checked_in["blocks"], strict=True):
        assert actual["blockId"] == expected["blockId"]
        assert actual["blockKind"] == expected["blockKind"]
        assert actual["headingLevel"] == expected["headingLevel"]
        assert actual["headingPath"] == expected["headingPath"]
        assert actual["charStart"] == expected["charStart"]
        assert actual["charEnd"] == expected["charEnd"]
        assert actual["textSha256"] == expected["textSha256"]
        assert actual["text"] == expected["text"]
        assert actual["blockOrder"] == expected["blockOrder"]
        assert actual["normalizationVersion"] == expected["normalizationVersion"]

    assert regenerated["locatorSnapshots"] == checked_in["locatorSnapshots"]
    assert (
        regenerated["expectedCitationProjection"]["locator"]
        == checked_in["expectedCitationProjection"]["locator"]
    )
    # Full oracle equality prevents silent drift outside the fields above.
    assert regenerated == checked_in


def test_fixture_declares_restore_typed_tables() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    tables = fixture["lifecycleInvariants"]["backupRestoreTypedTables"]
    for required in v5b.DOCUMENT_TYPED_TABLES:
        assert required in tables


def test_fixture_snapshot_shape_is_self_consistent() -> None:
    before = v5b.snapshot(mode="fixture")
    after = copy.deepcopy(before)
    # Fixture mode is offline shape only. Live restore verify must not pass it.
    result = v5b.verify(before, after)
    assert result["passed"] is False
    assert result["skipped"] is True
    assert "fixture-shape" in result["reason"]
    assert result["livePostgresMinio"] is False
    assert before["schemaVersion"] == v5b.SCHEMA_VERSION
    assert before["evidenceMode"] == "fixture-shape-only"
    assert before["livePostgresMinio"] is False
    assert before["workspaceId"] == v5b.IDS["workspace"]
    assert before["assetId"] == v5b.IDS["document-asset"]
    assert before["objectPrefix"] == (
        f"workspaces/{before['workspaceId']}/assets/{before['assetId']}/"
    )
    for table in (
        "assets",
        "asset_representations",
        "document_normalized_contents",
        "document_blocks",
        "content_units",
        "content_unit_embeddings",
        "evidence_locators",
        "document_locator_details",
        "message_citations",
        "note_sources",
    ):
        assert table in before["scopedRows"]
        assert isinstance(before["scopedRows"][table], list)
    assert before["objects"]
    assert all(item["objectKey"].startswith(before["objectPrefix"]) for item in before["objects"])
    assert before["scopedRows"]["assets"][0]["byte_size"] == 114
    assert before["objects"][0]["byteSize"] == 114
    assert before["scopedRows"]["assets"][0]["source_sha256"].startswith("5fca")
    assert before["scopedRows"]["document_normalized_contents"][0]["normalized_text"].startswith("Intro")
    assert before["historicalEvidence"]["sourceAvailable"] is False
    assert before["historicalEvidence"]["retainedLocatorIds"]
    assert before["historicalEvidence"]["retainedCitationIds"]
    assert before["historicalEvidence"]["retainedNoteSourceIds"]
    assert before["semanticSha256"] == v5b._compute_semantic_sha256(before)
    for table in (*v5b.DOCUMENT_TYPED_TABLES, *v5b.CATALOG_TABLES):
        assert before["typedTables"][table]["present"] is True
    assert before["catalog"]["documentEnabled"] is True
    assert before["catalog"]["documentLocator"] == {
        "kind": "document_anchor",
        "detail_family": "record",
        "contract_version": 1,
    }
    assert before["catalog"]["requiredCatalog"] == v5b._required_catalog_values()
    for table in v5b.REQUIRED_SCOPED_LINK_TABLES:
        assert before["typedTables"][table]["present"] is True
        assert before["typedTables"][table]["requiredColumnsPresent"] is True


def test_verify_rejects_schema_and_semantic_drift() -> None:
    before = _valid_live_snapshot()
    after = copy.deepcopy(before)
    after["schemaVersion"] = "v5b-document-restore-acceptance-v0"
    with pytest.raises(ValueError, match="schema mismatch"):
        v5b.verify(before, after)

    after = copy.deepcopy(before)
    after["objects"][0]["sha256"] = "0" * 64
    after["semanticSha256"] = v5b._compute_semantic_sha256(after)
    result = v5b.verify(before, after)
    assert result["passed"] is False
    assert result["skipped"] is False
    assert result["livePostgresMinio"] is True
    assert "objects" in result["mismatches"] or "semanticSha256" in result["mismatches"]


def test_verify_requires_live_postgres_minio_on_both_sides() -> None:
    live = _valid_live_snapshot()
    incomplete = copy.deepcopy(live)
    incomplete["evidenceMode"] = "postgres-only"
    incomplete["livePostgresMinio"] = False
    result = v5b.verify(live, incomplete)
    assert result["passed"] is False
    assert result["skipped"] is True
    assert "live PostgreSQL+MinIO" in result["reason"]


def test_live_verify_passes_on_exact_scoped_equality() -> None:
    live = _valid_live_snapshot()
    result = v5b.verify(live, copy.deepcopy(live))
    assert result["passed"] is True
    assert result["skipped"] is False
    assert result["mismatches"] == []
    assert result["livePostgresMinio"] is True


def test_live_verify_rejects_missing_identity_and_scope_fields() -> None:
    """Missing live scope fields must fail even when both sides recompute the same digest."""
    live = _valid_live_snapshot()

    identity_fields = ("workspaceId", "assetId", "objectPrefix", "scopedRows", "objects")
    for field in identity_fields:
        after = copy.deepcopy(live)
        after.pop(field, None)
        after["semanticSha256"] = v5b._compute_semantic_sha256(after)
        result = v5b.verify(live, after)
        assert result["passed"] is False, field
        assert result["skipped"] is False, field
        assert any(
            item == field or item.endswith(f".{field}") or field in item
            for item in result["mismatches"]
        ), (field, result["mismatches"])

        both = copy.deepcopy(live)
        both.pop(field, None)
        both["semanticSha256"] = v5b._compute_semantic_sha256(both)
        both_result = v5b.verify(both, copy.deepcopy(both))
        assert both_result["passed"] is False, field
        assert both_result["skipped"] is False, field
        assert any(
            item == field or item.endswith(f".{field}") or field in item
            for item in both_result["mismatches"]
        ), (field, both_result["mismatches"])

    for table in v5b.REQUIRED_SCOPED_ROW_COLLECTIONS:
        after = copy.deepcopy(live)
        after["scopedRows"] = copy.deepcopy(live["scopedRows"])
        after["scopedRows"].pop(table, None)
        after["semanticSha256"] = v5b._compute_semantic_sha256(after)
        result = v5b.verify(live, after)
        assert result["passed"] is False, table
        assert any(
            f"scopedRows.{table}" in item or item == "scopedRows"
            for item in result["mismatches"]
        ), (table, result["mismatches"])

        both = copy.deepcopy(live)
        both["scopedRows"] = copy.deepcopy(live["scopedRows"])
        both["scopedRows"].pop(table, None)
        both["semanticSha256"] = v5b._compute_semantic_sha256(both)
        both_result = v5b.verify(both, copy.deepcopy(both))
        assert both_result["passed"] is False, table
        assert any(
            f"scopedRows.{table}" in item or item == "scopedRows"
            for item in both_result["mismatches"]
        ), (table, both_result["mismatches"])

    empty_assets = copy.deepcopy(live)
    empty_assets["scopedRows"] = copy.deepcopy(live["scopedRows"])
    empty_assets["scopedRows"]["assets"] = []
    empty_assets["semanticSha256"] = v5b._compute_semantic_sha256(empty_assets)
    result = v5b.verify(empty_assets, copy.deepcopy(empty_assets))
    assert result["passed"] is False
    assert any("scopedRows.assets" in item for item in result["mismatches"])

    wrong_prefix = copy.deepcopy(live)
    wrong_prefix["objectPrefix"] = "workspaces/other/assets/other/"
    wrong_prefix["semanticSha256"] = v5b._compute_semantic_sha256(wrong_prefix)
    result = v5b.verify(wrong_prefix, copy.deepcopy(wrong_prefix))
    assert result["passed"] is False
    assert any("objectPrefix" in item for item in result["mismatches"])


def test_verify_rejects_absent_typed_tables_even_when_sha_matches_rows() -> None:
    live = _valid_live_snapshot()
    after = copy.deepcopy(live)
    after.pop("typedTables", None)
    # Recompute semantic hash without typedTables so the old weak body would match.
    weak_body = {
        "workspaceId": after["workspaceId"],
        "assetId": after["assetId"],
        "objectPrefix": after["objectPrefix"],
        "scopedRows": after["scopedRows"],
        "objects": after["objects"],
    }
    after["semanticSha256"] = v5b._semantic_sha256(weak_body)
    result = v5b.verify(live, after)
    assert result["passed"] is False
    assert result["skipped"] is False
    assert any("typedTables" in item for item in result["mismatches"])


def test_verify_rejects_mutated_catalog_or_typed_tables() -> None:
    live = _valid_live_snapshot()

    missing_typed = copy.deepcopy(live)
    missing_typed["typedTables"] = {
        key: value
        for key, value in missing_typed["typedTables"].items()
        if key != "document_blocks"
    }
    missing_typed["semanticSha256"] = v5b._compute_semantic_sha256(missing_typed)
    result = v5b.verify(live, missing_typed)
    assert result["passed"] is False
    assert any("typedTables" in item for item in result["mismatches"])

    mutated_catalog = copy.deepcopy(live)
    mutated_catalog["catalog"] = copy.deepcopy(live["catalog"])
    mutated_catalog["catalog"]["documentEnabled"] = False
    mutated_catalog["semanticSha256"] = v5b._compute_semantic_sha256(mutated_catalog)
    result = v5b.verify(live, mutated_catalog)
    assert result["passed"] is False
    assert any("catalog" in item for item in result["mismatches"])

    wrong_detail = copy.deepcopy(live)
    wrong_detail["catalog"] = copy.deepcopy(live["catalog"])
    wrong_detail["catalog"]["documentLocator"] = {
        "kind": "document_anchor",
        "detail_family": "json",
        "contract_version": 1,
    }
    wrong_detail["semanticSha256"] = v5b._compute_semantic_sha256(wrong_detail)
    result = v5b.verify(live, wrong_detail)
    assert result["passed"] is False
    assert any("documentLocator" in item or "catalog" in item for item in result["mismatches"])

    wrong_asset_kind = copy.deepcopy(live)
    wrong_asset_kind["catalog"] = copy.deepcopy(live["catalog"])
    wrong_asset_kind["catalog"]["requiredCatalog"] = copy.deepcopy(
        live["catalog"]["requiredCatalog"]
    )
    wrong_asset_kind["catalog"]["requiredCatalog"]["representation_types"] = [
        {
            "kind": "document_normalized",
            "asset_kind": "pdf",
            "contract_version": 1,
        },
        {
            "kind": "document_source",
            "asset_kind": "document",
            "contract_version": 1,
        },
    ]
    wrong_asset_kind["semanticSha256"] = v5b._compute_semantic_sha256(wrong_asset_kind)
    result = v5b.verify(live, wrong_asset_kind)
    assert result["passed"] is False
    assert any(
        "requiredCatalog.representation_types" in item or "catalog" in item
        for item in result["mismatches"]
    )


def test_verify_rejects_falsified_semantic_sha_even_when_bodies_match() -> None:
    live = _valid_live_snapshot()
    after = copy.deepcopy(live)
    after["semanticSha256"] = "0" * 64
    result = v5b.verify(live, after)
    assert result["passed"] is False
    assert result["skipped"] is False
    assert "semanticSha256" in result["mismatches"] or any(
        item.endswith("semanticSha256") for item in result["mismatches"]
    )


def test_check_tables_from_fixture_snapshot() -> None:
    snap = v5b.snapshot(mode="fixture")
    result = v5b.check_tables(snap)
    # Fixture-shape is offline only: shape may be ok, but live acceptance passed is false.
    assert result["passed"] is False
    assert result["skipped"] is False
    assert result["livePostgresMinio"] is False
    assert result["fixtureShapeOk"] is True
    assert result["offlineCatalogShapeOk"] is True
    assert result["missingTables"] == []
    assert result["catalogOk"] is True
    assert result["catalogMismatches"] == []
    assert result["requiredCatalog"] == v5b._required_catalog_values()


def test_check_tables_requires_required_catalog_values() -> None:
    snap = v5b.snapshot(mode="fixture")
    snap["catalog"] = copy.deepcopy(snap["catalog"])
    snap["catalog"]["requiredCatalog"] = {
        "asset_types": [
            {"kind": "document", "enabled": True, "contract_version": 1},
        ],
        "representation_types": [
            {
                "kind": "document_source",
                "asset_kind": "document",
                "contract_version": 1,
            },
        ],
        "content_unit_types": [
            {
                "kind": "document_block",
                "asset_kind": "document",
                "contract_version": 1,
            },
            {
                "kind": "document_text_chunk",
                "asset_kind": "document",
                "contract_version": 1,
            },
        ],
        "locator_types": [
            {
                "kind": "document_anchor",
                "detail_family": "record",
                "contract_version": 1,
            },
        ],
    }
    result = v5b.check_tables(snap)
    assert result["passed"] is False
    assert result["catalogOk"] is False
    assert "catalog.requiredCatalog.representation_types" in result["catalogMismatches"]

    snap = v5b.snapshot(mode="fixture")
    snap["catalog"] = copy.deepcopy(snap["catalog"])
    snap["catalog"]["documentLocator"] = {
        "kind": "document_anchor",
        "detail_family": "json",
        "contract_version": 1,
    }
    result = v5b.check_tables(snap)
    assert result["passed"] is False
    assert "catalog.documentLocator.detail_family" in result["catalogMismatches"]


def test_live_postgres_minio_skip_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("V5B_DATABASE_URL", raising=False)
    monkeypatch.delenv("AI_PDF_DATABASE_URL", raising=False)
    monkeypatch.delenv("V5B_WORKSPACE_ID", raising=False)
    monkeypatch.delenv("V5B_ASSET_ID", raising=False)

    blocked = v5b.snapshot(mode="live")
    assert blocked["evidenceMode"] == "blocked"
    assert blocked["livePostgresMinio"] is False
    assert blocked["passed"] is False
    assert "V5B_WORKSPACE_ID" in blocked["skipReason"]
    assert "V5B_ASSET_ID" in blocked["skipReason"]

    monkeypatch.setenv("V5B_WORKSPACE_ID", v5b.IDS["workspace"])
    monkeypatch.setenv("V5B_ASSET_ID", v5b.IDS["document-asset"])
    live = v5b.snapshot(mode="live")
    assert live["evidenceMode"] == "skipped"
    assert live["livePostgresMinio"] is False
    assert "skipReason" in live
    assert "SQLite" not in live.get("skipReason", "") or "PostgreSQL" in live["skipReason"]

    checked = v5b.check_tables(live)
    assert checked["skipped"] is True
    assert checked["livePostgresMinio"] is False
    assert checked["passed"] is False

    verify_result = v5b.verify(live, live)
    assert verify_result["skipped"] is True
    assert verify_result["passed"] is False
    assert verify_result["livePostgresMinio"] is False


def test_live_acceptance_reads_production_database_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("V5B_WORKSPACE_ID", v5b.IDS["workspace"])
    monkeypatch.setenv("V5B_ASSET_ID", v5b.IDS["document-asset"])
    monkeypatch.setenv("AI_PDF_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("V5B_DATABASE_URL", raising=False)

    live = v5b.snapshot(mode="live")
    assert live["evidenceMode"] == "skipped"
    assert live["livePostgresMinio"] is False
    assert "PostgreSQL" in live["skipReason"]


def test_restore_acceptance_reads_production_minio_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeMinio:
        def __init__(self, endpoint, access_key, secret_key, secure):
            captured.update(
                endpoint=endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=secure,
            )

    monkeypatch.setitem(sys.modules, "minio", SimpleNamespace(Minio=FakeMinio))
    for key in (
        "V5B_MINIO_ENDPOINT",
        "MINIO_ENDPOINT",
        "MINIO_HOST",
        "V5B_MINIO_ACCESS_KEY",
        "MINIO_ACCESS_KEY",
        "MINIO_ROOT_USER",
        "V5B_MINIO_SECRET_KEY",
        "MINIO_SECRET_KEY",
        "MINIO_ROOT_PASSWORD",
        "V5B_MINIO_BUCKET",
        "MINIO_BUCKET",
        "V5B_MINIO_SECURE",
        "MINIO_SECURE",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AI_PDF_MINIO_ENDPOINT", "minio:9000")
    monkeypatch.setenv("AI_PDF_MINIO_ACCESS_KEY", "compose-user")
    monkeypatch.setenv("AI_PDF_MINIO_SECRET_KEY", "compose-password")
    monkeypatch.setenv("AI_PDF_MINIO_BUCKET", "compose-bucket")
    monkeypatch.setenv("AI_PDF_MINIO_SECURE", "false")

    client, bucket = v5b._minio_client_from_env()
    assert isinstance(client, FakeMinio)
    assert captured == {
        "endpoint": "minio:9000",
        "access_key": "compose-user",
        "secret_key": "compose-password",
        "secure": False,
    }
    assert bucket == "compose-bucket"


def test_live_sqlite_url_is_not_accepted_as_restore_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("V5B_WORKSPACE_ID", v5b.IDS["workspace"])
    monkeypatch.setenv("V5B_ASSET_ID", v5b.IDS["document-asset"])
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    live = v5b.snapshot(mode="live")
    assert live["evidenceMode"] == "skipped"
    assert live["livePostgresMinio"] is False
    assert "PostgreSQL" in live["skipReason"]
    # Never claim SQLite-only as live restore success.
    assert live.get("passed") is not True


def test_live_missing_scope_ids_are_blocked_never_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://example/db")
    monkeypatch.delenv("V5B_WORKSPACE_ID", raising=False)
    monkeypatch.delenv("V5B_ASSET_ID", raising=False)
    live = v5b.snapshot(mode="live", workspace_id=None, asset_id=None)
    assert live["evidenceMode"] == "blocked"
    assert live["passed"] is False
    assert live["livePostgresMinio"] is False


def test_json_rows_uses_expanding_bindparams_for_id_lists() -> None:
    """Regression: list-valued scoped filters must bind via expanding parameters."""
    recorded: dict[str, object] = {}

    class _Scalars:
        def __iter__(self):
            return iter(())

    class _Result:
        def scalars(self):
            return _Scalars()

    class _Connection:
        def execute(self, statement, parameters=None):
            recorded["statement"] = statement
            recorded["parameters"] = parameters
            return _Result()

    rows = v5b._json_rows(
        _Connection(),
        """
        SELECT *
        FROM document_blocks
        WHERE representation_id IN :representation_ids
        ORDER BY representation_id
        """,
        expanding=("representation_ids",),
        representation_ids=["rep-1", "rep-2"],
    )
    assert rows == []
    statement = recorded["statement"]
    assert recorded["parameters"] == {"representation_ids": ["rep-1", "rep-2"]}
    bind = statement._bindparams["representation_ids"]
    assert bind.expanding is True

def test_catalog_comparison_is_order_independent() -> None:
    """Representation catalog order from SQL must not affect semantic equality."""
    expected = v5b._required_catalog_values()
    reordered = copy.deepcopy(expected)
    reordered["representation_types"] = list(reversed(reordered["representation_types"]))
    reordered["content_unit_types"] = list(reversed(reordered["content_unit_types"]))
    assert v5b._catalog_rows_match(
        "representation_types",
        reordered["representation_types"],
        expected["representation_types"],
    )
    assert v5b._catalog_rows_match(
        "content_unit_types",
        reordered["content_unit_types"],
        expected["content_unit_types"],
    )
    assert v5b._catalog_requirement_mismatches(
        {
            "documentEnabled": True,
            "documentLocator": {
                "kind": "document_anchor",
                "detail_family": "record",
                "contract_version": 1,
            },
            "requiredCatalog": reordered,
        }
    ) == []

    live = _valid_live_snapshot()
    after = copy.deepcopy(live)
    after["catalog"] = copy.deepcopy(live["catalog"])
    after["catalog"]["requiredCatalog"] = reordered
    after["catalog"]["representationKinds"] = list(
        reversed(after["catalog"]["representationKinds"])
    )
    after["semanticSha256"] = v5b._compute_semantic_sha256(after)
    result = v5b.verify(live, after)
    assert result["passed"] is True
    assert result["mismatches"] == []
    assert after["semanticSha256"] == live["semanticSha256"]


def test_verify_rejects_missing_required_link_schema() -> None:
    live = _valid_live_snapshot()

    missing_table = copy.deepcopy(live)
    missing_table["typedTables"] = copy.deepcopy(live["typedTables"])
    missing_table["typedTables"].pop("message_citations", None)
    missing_table["semanticSha256"] = v5b._compute_semantic_sha256(missing_table)
    result = v5b.verify(live, missing_table)
    assert result["passed"] is False
    assert any("message_citations" in item for item in result["mismatches"])

    missing_columns = copy.deepcopy(live)
    missing_columns["typedTables"] = copy.deepcopy(live["typedTables"])
    missing_columns["typedTables"]["note_sources"] = {
        "present": False,
        "rowCount": 0,
        "requiredColumnsPresent": False,
    }
    missing_columns["semanticSha256"] = v5b._compute_semantic_sha256(missing_columns)
    result = v5b.verify(live, missing_columns)
    assert result["passed"] is False
    assert any("note_sources" in item for item in result["mismatches"])


def test_check_tables_live_pass_requires_postgres_minio_evidence() -> None:
    live = _valid_live_snapshot()
    result = v5b.check_tables(live)
    assert result["passed"] is True
    assert result["skipped"] is False
    assert result["livePostgresMinio"] is True
    assert result["offlineCatalogShapeOk"] is True
    assert result["fixtureShapeOk"] is False

    not_live = copy.deepcopy(live)
    not_live["evidenceMode"] = "fixture-shape-only"
    not_live["livePostgresMinio"] = False
    result = v5b.check_tables(not_live)
    assert result["passed"] is False
    assert result["offlineCatalogShapeOk"] is True
    assert result["livePostgresMinio"] is False


def test_live_uploaded_document_may_explicitly_omit_citation_and_note_links() -> None:
    uploaded = _valid_live_snapshot(deleted=False)
    uploaded["scopedRows"] = copy.deepcopy(uploaded["scopedRows"])
    uploaded["scopedRows"]["message_citations"] = []
    uploaded["scopedRows"]["note_sources"] = []
    uploaded["historicalEvidence"] = v5b._build_historical_evidence(uploaded["scopedRows"])
    uploaded["semanticSha256"] = v5b._compute_semantic_sha256(uploaded)

    strict = v5b.verify(uploaded, copy.deepcopy(uploaded))
    assert strict["passed"] is False
    assert "before.scopedRows.message_citations.min" in strict["mismatches"]
    assert "before.scopedRows.note_sources.min" in strict["mismatches"]

    uploaded["requireEvidenceLinks"] = False
    uploaded["semanticSha256"] = v5b._compute_semantic_sha256(uploaded)
    allowed = v5b.verify(uploaded, copy.deepcopy(uploaded))
    assert allowed["passed"] is True
    assert allowed["mismatches"] == []


def test_verify_rejects_foreign_object_prefix_and_malformed_objects() -> None:
    live = _valid_live_snapshot(deleted=False)

    foreign = copy.deepcopy(live)
    foreign["objects"] = copy.deepcopy(live["objects"])
    foreign["objects"][0] = copy.deepcopy(live["objects"][0])
    foreign["objects"][0]["objectKey"] = (
        f"workspaces/{live['workspaceId']}/assets/other-asset/original.md"
    )
    foreign["semanticSha256"] = v5b._compute_semantic_sha256(foreign)
    result = v5b.verify(foreign, copy.deepcopy(foreign))
    assert result["passed"] is False
    assert any("objects" in item for item in result["mismatches"])

    empty_objects = copy.deepcopy(live)
    empty_objects["objects"] = []
    empty_objects["semanticSha256"] = v5b._compute_semantic_sha256(empty_objects)
    result = v5b.verify(empty_objects, copy.deepcopy(empty_objects))
    assert result["passed"] is False
    assert any("objects" in item for item in result["mismatches"])

    # Soft-deleted assets may retain historical rows with an empty object list.
    deleted_empty = _valid_live_snapshot(deleted=True)
    deleted_empty["objects"] = []
    deleted_empty["semanticSha256"] = v5b._compute_semantic_sha256(deleted_empty)
    result = v5b.verify(deleted_empty, copy.deepcopy(deleted_empty))
    assert result["passed"] is True

    nondict = copy.deepcopy(live)
    nondict["objects"] = ["not-a-dict"]
    nondict["semanticSha256"] = v5b._compute_semantic_sha256(nondict)
    result = v5b.verify(nondict, copy.deepcopy(nondict))
    assert result["passed"] is False
    assert any("objects" in item for item in result["mismatches"])

    missing_fields = copy.deepcopy(live)
    missing_fields["objects"] = [{"objectKey": live["objects"][0]["objectKey"]}]
    missing_fields["semanticSha256"] = v5b._compute_semantic_sha256(missing_fields)
    result = v5b.verify(missing_fields, copy.deepcopy(missing_fields))
    assert result["passed"] is False
    assert any("objects" in item for item in result["mismatches"])

    bad_sha = copy.deepcopy(live)
    bad_sha["objects"] = copy.deepcopy(live["objects"])
    bad_sha["objects"][0] = copy.deepcopy(live["objects"][0])
    bad_sha["objects"][0]["sha256"] = "not-a-hex-digest"
    bad_sha["semanticSha256"] = v5b._compute_semantic_sha256(bad_sha)
    result = v5b.verify(bad_sha, copy.deepcopy(bad_sha))
    assert result["passed"] is False
    assert any("objects" in item for item in result["mismatches"])


def test_verify_rejects_malformed_block_and_citation_rows() -> None:
    live = _valid_live_snapshot(deleted=False)

    bad_block = copy.deepcopy(live)
    bad_block["scopedRows"] = copy.deepcopy(live["scopedRows"])
    bad_block["scopedRows"]["document_blocks"] = copy.deepcopy(
        live["scopedRows"]["document_blocks"]
    )
    bad_block["scopedRows"]["document_blocks"][0] = copy.deepcopy(
        live["scopedRows"]["document_blocks"][0]
    )
    bad_block["scopedRows"]["document_blocks"][0]["char_end"] = -1
    bad_block["semanticSha256"] = v5b._compute_semantic_sha256(bad_block)
    result = v5b.verify(bad_block, copy.deepcopy(bad_block))
    assert result["passed"] is False
    assert any("document_blocks" in item for item in result["mismatches"])

    missing_block_field = copy.deepcopy(live)
    missing_block_field["scopedRows"] = copy.deepcopy(live["scopedRows"])
    missing_block_field["scopedRows"]["document_blocks"] = copy.deepcopy(
        live["scopedRows"]["document_blocks"]
    )
    broken = copy.deepcopy(live["scopedRows"]["document_blocks"][0])
    broken.pop("text_sha256")
    missing_block_field["scopedRows"]["document_blocks"][0] = broken
    missing_block_field["semanticSha256"] = v5b._compute_semantic_sha256(missing_block_field)
    result = v5b.verify(missing_block_field, copy.deepcopy(missing_block_field))
    assert result["passed"] is False
    assert any("document_blocks" in item for item in result["mismatches"])

    bad_citation = copy.deepcopy(live)
    bad_citation["scopedRows"] = copy.deepcopy(live["scopedRows"])
    bad_citation["scopedRows"]["message_citations"] = copy.deepcopy(
        live["scopedRows"]["message_citations"]
    )
    bad_citation["scopedRows"]["message_citations"][0] = copy.deepcopy(
        live["scopedRows"]["message_citations"][0]
    )
    bad_citation["scopedRows"]["message_citations"][0]["evidence_locator_id"] = "missing-locator"
    # historicalEvidence must stay consistent with scoped rows or integrity fails twice.
    bad_citation["historicalEvidence"] = v5b._build_historical_evidence(
        bad_citation["scopedRows"]
    )
    bad_citation["semanticSha256"] = v5b._compute_semantic_sha256(bad_citation)
    result = v5b.verify(bad_citation, copy.deepcopy(bad_citation))
    assert result["passed"] is False
    assert any("message_citations" in item for item in result["mismatches"])

    wrong_unit_kind = copy.deepcopy(live)
    wrong_unit_kind["scopedRows"] = copy.deepcopy(live["scopedRows"])
    wrong_unit_kind["scopedRows"]["content_units"] = copy.deepcopy(
        live["scopedRows"]["content_units"]
    )
    wrong_unit_kind["scopedRows"]["content_units"][0] = copy.deepcopy(
        live["scopedRows"]["content_units"][0]
    )
    wrong_unit_kind["scopedRows"]["content_units"][0]["unit_kind"] = "document_block"
    wrong_unit_kind["semanticSha256"] = v5b._compute_semantic_sha256(wrong_unit_kind)
    result = v5b.verify(wrong_unit_kind, copy.deepcopy(wrong_unit_kind))
    assert result["passed"] is False
    assert any("content_units" in item for item in result["mismatches"])


def test_verify_rejects_missing_required_scoped_collection_even_when_hash_matches() -> None:
    live = _valid_live_snapshot(deleted=False)
    after = copy.deepcopy(live)
    after["scopedRows"] = copy.deepcopy(live["scopedRows"])
    after["scopedRows"].pop("document_blocks", None)
    after["semanticSha256"] = v5b._compute_semantic_sha256(after)
    result = v5b.verify(after, copy.deepcopy(after))
    assert result["passed"] is False
    assert any("document_blocks" in item for item in result["mismatches"])


def test_verify_rejects_historical_evidence_and_source_available_mutation() -> None:
    live = _valid_live_snapshot(deleted=True)
    assert live["historicalEvidence"]["sourceAvailable"] is False
    assert live["historicalEvidence"]["retainedLocatorIds"]
    assert live["historicalEvidence"]["retainedCitationIds"]

    mutated = copy.deepcopy(live)
    mutated["historicalEvidence"] = copy.deepcopy(live["historicalEvidence"])
    mutated["historicalEvidence"]["sourceAvailable"] = True
    mutated["semanticSha256"] = v5b._compute_semantic_sha256(mutated)
    result = v5b.verify(mutated, copy.deepcopy(mutated))
    assert result["passed"] is False
    assert any("historicalEvidence" in item for item in result["mismatches"])

    drop_ids = copy.deepcopy(live)
    drop_ids["historicalEvidence"] = copy.deepcopy(live["historicalEvidence"])
    drop_ids["historicalEvidence"]["retainedLocatorIds"] = []
    drop_ids["semanticSha256"] = v5b._compute_semantic_sha256(drop_ids)
    result = v5b.verify(drop_ids, copy.deepcopy(drop_ids))
    assert result["passed"] is False
    assert any("historicalEvidence" in item for item in result["mismatches"])

    missing = copy.deepcopy(live)
    missing.pop("historicalEvidence", None)
    missing["semanticSha256"] = v5b._compute_semantic_sha256(missing)
    result = v5b.verify(missing, copy.deepcopy(missing))
    assert result["passed"] is False
    assert any("historicalEvidence" in item for item in result["mismatches"])

    # Before/after drift on historicalEvidence fails equality even when integrity holds.
    before = _valid_live_snapshot(deleted=True)
    after = _valid_live_snapshot(deleted=False)
    result = v5b.verify(before, after)
    assert result["passed"] is False
    assert "historicalEvidence" in result["mismatches"] or any(
        "historicalEvidence" in item for item in result["mismatches"]
    )


def test_fixture_uses_checked_in_markdown_facts() -> None:
    fixture_json = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    snap = v5b.snapshot(mode="fixture")
    asset = snap["scopedRows"]["assets"][0]
    assert asset["byte_size"] == fixture_json["byteSize"] == 114
    assert asset["source_sha256"] == fixture_json["sourceSha256"]
    assert (
        snap["scopedRows"]["document_normalized_contents"][0]["content_sha256"]
        == fixture_json["normalizedContentSha256"]
    )
    assert (
        snap["scopedRows"]["document_normalized_contents"][0]["normalized_text"]
        == fixture_json["normalizedText"]
    )
    assert len(snap["scopedRows"]["document_blocks"]) == len(fixture_json["blocks"])
    assert snap["scopedRows"]["document_blocks"][0]["block_id"] == fixture_json["blocks"][0]["blockId"]
    assert snap["scopedRows"]["document_blocks"][0]["text_sha256"] == fixture_json["blocks"][0]["textSha256"]
    assert snap["objects"][0]["byteSize"] == 114
    assert snap["historicalEvidence"]["sourceAvailable"] is False
