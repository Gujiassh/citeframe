from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sys


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts/m403a_capacity_acceptance.py"
SCRIPT_SPEC = importlib.util.spec_from_file_location("m403a_capacity_acceptance", SCRIPT_PATH)
assert SCRIPT_SPEC is not None and SCRIPT_SPEC.loader is not None
m403a = importlib.util.module_from_spec(SCRIPT_SPEC)
sys.modules[SCRIPT_SPEC.name] = m403a
SCRIPT_SPEC.loader.exec_module(m403a)


def test_scale_and_signature_counts_are_exact_and_multimodal() -> None:
    production_signatures = set(m403a.TEXT_CHANNEL.type_signatures)
    # M403A freezes PDF/Image capacity only; Document may exist in production.
    assert m403a.CONFIGURED_TYPE_SIGNATURES.issubset(production_signatures)
    assert len(m403a.CONFIGURED_TYPE_SIGNATURES) == len(m403a.SIGNATURES)
    assert m403a.CONFIGURED_TYPE_SIGNATURES == {
        tuple(item[1:5]) for item in m403a.SIGNATURES
    }
    assert m403a.DOCUMENT_TYPE_SIGNATURE in production_signatures
    assert m403a.DOCUMENT_TYPE_SIGNATURE not in m403a.CONFIGURED_TYPE_SIGNATURES
    assert all(item[1] in {"pdf", "image"} for item in m403a.SIGNATURES)
    for scale, (visible, physical) in m403a.SCALES.items():
        counts = m403a._signature_counts(visible)
        assert sum(counts) == visible
        assert sum(counts[:6]) == int(visible * 0.8)
        assert sum(counts[6:]) == visible - int(visible * 0.8)
        noise = m403a._noise_counts(physical - visible)
        assert set(noise) == {"outside", "old_generation", "old_index", "wrong_provider"}
        assert sum(sum(items) for items in noise.values()) == physical - visible
        assert m403a._target_workspace(scale) != m403a._noise_workspace(scale)

        profiles = m403a._expected_profile_counts(visible)
        assert sum(item["rows"] for item in profiles.values()) == visible
        assert profiles["D1"]["rows"] == profiles["D1"]["locations"]
        assert profiles["D8"]["locations"] == sum(
            (count + 1) // 3 // 8 + bool(((count + 1) // 3) % 8)
            for count in counts
        )


def test_all_scope_tables_are_analyzed_after_capacity_seed() -> None:
    assert {
        "assets",
        "asset_representations",
        "evidence_locators",
        "content_units",
        "content_unit_embeddings",
    }.issubset(m403a.ANALYZE_TABLES)


def test_query_vectors_are_database_derived_1024_dimension_signals() -> None:
    assert m403a.VECTOR_SIGNAL_DIMENSIONS == 64
    assert m403a.SIGNATURE_CENTROID_WEIGHT == 4.0
    assert m403a.LOCATOR_SIGNAL_WEIGHT == 0.1
    assert m403a.CapacityProvider().dimensions == 1024
    assert m403a._content_unit_id("s0", "visible", "pdf-text-legacy", 1) == (
        "4e226b56-40d7-e47c-c228-585180991df6"
    )
    assert len(m403a.RECALL_QUERY_CASES) == 8
    assert {signature for signature, _profile in m403a.RECALL_QUERY_CASES} == {
        item[0] for item in m403a.SIGNATURES
    }

    vector_sql = " ".join(m403a._vector_seed_sql().split())
    signature_array = ",".join(f"'{item[0]}'" for item in m403a.SIGNATURES)
    assert f"ARRAY[{signature_array}]::text[]" in vector_sql
    assert "THEN 4.0::real" in vector_sql
    assert ") * 0.1" in vector_sql
    assert "FROM generate_series(1,64) AS dimension" in vector_sql
    assert "AS signal" in vector_sql
    assert "array_fill" not in vector_sql

    embedding_sql = " ".join(m403a._embedding_insert_sql().split())
    assert "vectors.signal || array_fill(0.0::real, ARRAY[960])" in embedding_sql
    assert ")::vector" in embedding_sql


def test_plan_summary_collects_index_buffers_and_temp_blocks() -> None:
    plan = [
        {
            "Planning Time": 1.25,
            "Execution Time": 4.5,
            "Plan": {
                "Node Type": "Limit",
                "Shared Hit Blocks": 90,
                "Shared Read Blocks": 10,
                "Temp Read Blocks": 0,
                "Temp Written Blocks": 0,
                "Plans": [
                    {
                        "Node Type": "Index Scan",
                        "Index Name": "ix_content_unit_embeddings_current_embedding_hnsw",
                    }
                ],
            },
        }
    ]
    summary = m403a._plan_summary(plan)
    assert summary["indexes"] == ["ix_content_unit_embeddings_current_embedding_hnsw"]
    assert summary["sharedBufferHitRatio"] == 0.9
    assert summary["tempReadBlocks"] == 0
    assert summary["raw"] == plan


def test_recall_and_latency_summary_are_deterministic() -> None:
    assert m403a._recall(["a", "b", "c", "d"], ["a", "b", "x", "y"]) == 0.5
    summary = m403a._latency_summary([4.0, 1.0, 3.0, 2.0, 5.0])
    assert summary == {"min": 1.0, "p50": 3.0, "p95": 5.0, "p99": 5.0, "max": 5.0, "mean": 3.0}

    fingerprint = m403a._persisted_fingerprint(
        [{"cohort": "visible", "signature": "pdf-text-legacy", "count": 1}],
        {"D1": {"rows": 1, "locations": 1}},
        {"minimum": 500, "p50": 500, "p95": 1200, "maximum": 1200},
    )
    assert fingerprint == m403a._persisted_fingerprint(
        [{"count": 1, "signature": "pdf-text-legacy", "cohort": "visible"}],
        {"D1": {"locations": 1, "rows": 1}},
        {"maximum": 1200, "p95": 1200, "p50": 500, "minimum": 500},
    )


def test_postgres_shm_covers_hnsw_build_memory() -> None:
    compose_path = Path(__file__).resolve().parents[3] / "infra/docker/compose.m403a.yml"
    compose = compose_path.read_text()
    shm_match = re.search(r"^\s+shm_size:\s*(\d+)g$", compose, re.MULTILINE)
    work_mem_match = re.search(r"^\s+- maintenance_work_mem=(\d+)GB$", compose, re.MULTILINE)
    assert shm_match is not None
    assert work_mem_match is not None
    assert int(shm_match.group(1)) > int(work_mem_match.group(1))


def test_production_and_capacity_hnsw_build_quality_match() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    model = (repo_root / "apps/api/src/ai_pdf_api/models/content_unit_embedding.py").read_text()
    migration = (
        repo_root
        / "apps/api/alembic/versions/f2a4c6e8b0d1_add_embedding_current_scope.py"
    ).read_text()

    assert 'postgresql_with={"ef_construction": 512}' in model
    assert 'postgresql_with={"ef_construction": 512}' in migration
    assert "ix_content_unit_embeddings_current_embedding_binary_hnsw" in model
    assert "binary_quantize(embedding)::bit(1024)" in model
    assert "ix_content_unit_embeddings_current_embedding_binary_hnsw" in migration
    assert "binary_quantize(embedding)::bit(1024)" in migration
    assert "bit_hamming_ops" in migration
    assert 'postgresql_where=text("is_current IS TRUE")' in model
    assert 'postgresql_where=sa.text("is_current IS TRUE")' in migration
    assert "WITH (ef_construction=512)" in m403a.INDEX_SQL["hnsw"]
    assert "WHERE is_current IS TRUE" in m403a.INDEX_SQL["hnsw"]
    assert "binary_quantize(embedding)::bit(1024)" in m403a.INDEX_SQL["binaryHnsw"]
    assert "bit_hamming_ops" in m403a.INDEX_SQL["binaryHnsw"]
    assert 'postgresql_with={"ef_construction": 64}' in model
    assert "WITH (ef_construction=64)" in migration
    assert "WITH (ef_construction=64)" in m403a.INDEX_SQL["binaryHnsw"]
    assert "WHERE is_current IS TRUE" in m403a.INDEX_SQL["binaryHnsw"]


def test_capacity_requires_both_ann_indexes_in_all_ready_and_selected_plans() -> None:
    script = SCRIPT_PATH.read_text()

    assert '"binaryHnswPlan"' in script
    assert 'binary_hnsw_index in warm_plans["denseD1"]["indexes"]' in script
    assert 'binary_hnsw_index in warm_plans["denseD8"]["indexes"]' in script
    assert 'binary_hnsw_index in warm_plans["denseSelectedD1"]["indexes"]' in script
    assert "ix_content_unit_embeddings_current_embedding_binary_hnsw" in script


def test_capacity_measurement_gates_selected_scope_against_exact_locations() -> None:
    script = SCRIPT_PATH.read_text()

    assert 'exact_comparisons["selected:pdf-text-legacy:D1"]' in script
    assert 'asset_ids=selected_assets' in script
    assert 'item["recallAt10"] >= 0.95 for item in exact_comparisons.values()' in script


def test_production_and_capacity_fts_use_stored_search_vector() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    model = (repo_root / "apps/api/src/ai_pdf_api/models/content_unit.py").read_text()
    migration = (
        repo_root
        / "apps/api/alembic/versions/e1f3a5c7d9b2_add_content_unit_search_vector.py"
    ).read_text()
    script = SCRIPT_PATH.read_text()

    assert '"search_vector"' in model
    assert "to_tsvector('simple'::regconfig, text_content)" in migration
    assert '"search_vector"' in migration
    assert "search_vector" in m403a.INDEX_SQL["ftsGin"]
    assert "to_tsvector('simple', text_content)" not in m403a.INDEX_SQL["ftsGin"]
    assert "search_vector" in script


def test_production_and_capacity_hnsw_search_depth_match() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    for relative_path in (
        "infra/docker/compose.deploy.yml",
        "infra/docker/compose.m403a.yml",
    ):
        compose = (repo_root / relative_path).read_text()
        assert "- hnsw.iterative_scan=strict_order" in compose
        assert "- hnsw.ef_search=400" in compose
        assert "- hnsw.max_scan_tuples=200000" in compose

    deploy_compose = (repo_root / "infra/docker/compose.deploy.yml").read_text()
    assert "stop_grace_period: 5m" in deploy_compose


def test_capacity_seed_flushes_wal_before_cold_restart() -> None:
    script = SCRIPT_PATH.read_text()
    assert 'connection.execute(text("CHECKPOINT"))' in script
    assert '"checkpointSeconds": round(checkpoint_seconds, 3)' in script
    assert "+ checkpoint_seconds" in script


def test_subset_capacity_runs_cannot_claim_release() -> None:
    runner_path = Path(__file__).resolve().parents[3] / "infra/scripts/run-m403a-acceptance.sh"
    runner = runner_path.read_text()
    assert 'complete_scale_set = scales == ["s0", "s1", "s2"]' in runner
    assert '"releaseGatePassed": complete_scale_set and all(all_gates.values())' in runner
    assert runner.count("wait_for_service_health postgres 300") == 2
    assert runner.count("wait_for_postgres_sql 300") == 2
    for source_path in (
        "apps/api/alembic/versions/c9d1e2f3a4b5_migrate_documents_to_assets.py",
        "apps/api/alembic/versions/e1f3a5c7d9b2_add_content_unit_search_vector.py",
        "apps/api/alembic/versions/f2a4c6e8b0d1_add_embedding_current_scope.py",
        "apps/api/src/ai_pdf_api/models/content_unit.py",
        "apps/api/src/ai_pdf_api/models/content_unit_embedding.py",
        "apps/api/src/ai_pdf_api/services/ingestion.py",
        "apps/api/tests/test_dense_ann_retrieval.py",
        "apps/api/tests/test_embedding_current_scope.py",
    ):
        assert f'"{source_path}"' in runner
