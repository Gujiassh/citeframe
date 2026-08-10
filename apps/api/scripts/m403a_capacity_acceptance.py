from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import md5
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import time
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import bindparam, create_engine, func, literal, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ai_pdf_api.core.settings import settings
from ai_pdf_api.models import ContentUnit, ContentUnitEmbedding
from ai_pdf_api.services.providers import EmbeddingProvider
from ai_pdf_api.services.retrieval import (
    TEXT_CHANNEL,
    _candidates,
    _dense_ann_ranked_statement,
    _dedupe_locations,
    _latin_lexical_ranked_statement,
    _load_dense_ranked_rows,
    _unique_latin_terms,
    retrieval_scope_statement,
    retrieve_content,
    retrieve_lexical_content,
    retrieve_query_content,
)


Scale = Literal["s0", "s1", "s2"]

SCALES: dict[Scale, tuple[int, int]] = {
    "s0": (10_000, 14_000),
    "s1": (100_000, 140_000),
    "s2": (500_000, 700_000),
}
SIGNATURES = (
    ("pdf-text-legacy", "pdf", "pdf_text_chunk", "pdf_text_legacy", "pdf_page", 0.20),
    ("pdf-page-layout", "pdf", "pdf_text_chunk", "pdf_page_layout", "pdf_page", 0.12),
    ("pdf-text-ocr", "pdf", "pdf_text_chunk", "pdf_ocr", "pdf_page", 0.12),
    ("pdf-ocr-region", "pdf", "pdf_ocr_region", "pdf_ocr", "pdf_region", 0.12),
    ("pdf-table", "pdf", "pdf_table", "pdf_table", "pdf_region", 0.12),
    ("pdf-figure", "pdf", "pdf_figure", "pdf_figure", "pdf_region", 0.12),
    ("image-ocr", "image", "image_ocr_region", "image_ocr", "image_region", 0.12),
    ("image-caption", "image", "image_caption", "image_caption", "image_region", 0.08),
)
# M403A freezes a PDF/Image capacity cohort only. It must stay an exact
# PDF/Image signature set for seed/recall/perf claims, but must not reject
# later approved text-channel modalities such as Document.
CONFIGURED_TYPE_SIGNATURES = {tuple(item[1:5]) for item in SIGNATURES}
PRODUCTION_TEXT_TYPE_SIGNATURES = set(TEXT_CHANNEL.type_signatures)
DOCUMENT_TYPE_SIGNATURE = (
    "document",
    "document_text_chunk",
    "document_normalized",
    "document_anchor",
)
if not CONFIGURED_TYPE_SIGNATURES.issubset(PRODUCTION_TEXT_TYPE_SIGNATURES):
    raise RuntimeError(
        "M403A PDF/Image signatures must remain a subset of the production text registry"
    )
if len(CONFIGURED_TYPE_SIGNATURES) != len(SIGNATURES):
    raise RuntimeError("M403A signature cohort must stay exact and unique")
if DOCUMENT_TYPE_SIGNATURE not in PRODUCTION_TEXT_TYPE_SIGNATURES:
    raise RuntimeError(
        "Production text registry must include the approved Document type signature"
    )
PROFILE_DUPLICATES = {"D1": 1, "D8": 8, "D64": 64}
VECTOR_SIGNAL_DIMENSIONS = 64
SIGNATURE_CENTROID_WEIGHT = 4.0
LOCATOR_SIGNAL_WEIGHT = 0.1
RECALL_QUERY_CASES = tuple(
    (signature[0], profile)
    for signature, profile in zip(
        SIGNATURES,
        ("D1", "D8", "D64", "D1", "D8", "D64", "D1", "D8"),
        strict=True,
    )
)
NOW = datetime(2026, 1, 20, tzinfo=UTC)
WARMUP_RUNS = 20
SERIAL_RUNS = 20
CONCURRENT_RUNS = 32
CONCURRENCY = 8


def _id(scale: Scale, name: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"https://citeframe.local/m403a/{scale}/{name}"))


def _target_workspace(scale: Scale) -> str:
    return _id(scale, "workspace-target")


def _noise_workspace(scale: Scale) -> str:
    return _id(scale, "workspace-noise")


@dataclass(frozen=True)
class CapacityProvider(EmbeddingProvider):
    provider: str = "m403a"
    model: str = "deterministic-1024"
    dimensions: int = 1024
    version: str = "m403a-v1"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(value) for value in texts]

    def embed_query(self, text_value: str) -> list[float]:
        del text_value
        return [1.0, *([0.0] * 1023)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="M403A PostgreSQL capacity acceptance.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("seed", "measure"):
        child = subparsers.add_parser(command)
        child.add_argument("--scale", choices=sorted(SCALES), required=True)
        child.add_argument("--output", type=Path)
    return parser.parse_args()


def _write(payload: dict[str, Any], output: Path | None) -> None:
    value = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output is None:
        print(value, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(output)


def _signature_counts(total: int) -> list[int]:
    counts = [int(total * item[5]) for item in SIGNATURES]
    counts[0] += total - sum(counts)
    return counts


def _noise_counts(noise_total: int) -> dict[str, list[int]]:
    cohorts = ("outside", "old_generation", "old_index", "wrong_provider")
    base = noise_total // len(cohorts)
    totals = [base, base, base, noise_total - base * 3]
    result: dict[str, list[int]] = {}
    for cohort, total in zip(cohorts, totals, strict=True):
        counts = [total // len(SIGNATURES)] * len(SIGNATURES)
        counts[0] += total - sum(counts)
        result[cohort] = counts
    return result


def _expected_profile_counts(visible_total: int) -> dict[str, dict[str, int]]:
    result = {profile: {"rows": 0, "locations": 0} for profile in PROFILE_DUPLICATES}
    for count in _signature_counts(visible_total):
        per_profile = {
            "D1": (count + 2) // 3,
            "D8": (count + 1) // 3,
            "D64": count // 3,
        }
        for profile, rows in per_profile.items():
            result[profile]["rows"] += rows
            result[profile]["locations"] += math.ceil(rows / PROFILE_DUPLICATES[profile])
    return result


def _asset_id(scale: Scale, cohort: str, signature: str) -> str:
    return _id(scale, f"asset-{cohort}-{signature}")


def _content_unit_id(scale: Scale, cohort: str, signature: str, source_order: int) -> str:
    payload = f"{scale}:unit:{cohort}:{signature}:{source_order}".encode()
    return str(UUID(md5(payload).hexdigest()))


def _representation_id(scale: Scale, cohort: str, signature: str, generation: int) -> str:
    return _id(scale, f"representation-{cohort}-{signature}-g{generation}")


def _vector_seed_sql() -> str:
    signature_names = ",".join(f"'{item[0]}'" for item in SIGNATURES)
    return f"""
        CREATE TEMP TABLE m403a_vector_seed ON COMMIT DROP AS
        SELECT keys.signature,keys.profile,keys.locator_order,keys.vector_cohort,
          (
            SELECT
              array_agg(
                (CASE
                  WHEN dimension = array_position(
                    ARRAY[{signature_names}]::text[], keys.signature
                  ) THEN {SIGNATURE_CENTROID_WEIGHT}::real
                  ELSE ((
                    (hashtextextended(
                      :scale || ':' || keys.signature || ':' || keys.profile || ':' ||
                      keys.locator_order || ':' || keys.vector_cohort || ':' || dimension,
                      0
                    ) & 65535)::double precision / 32767.5 - 1.0) *
                    {LOCATOR_SIGNAL_WEIGHT}
                  )::real
                END)
                ORDER BY dimension
              )
            FROM generate_series(1,{VECTOR_SIGNAL_DIMENSIONS}) AS dimension
          ) AS signal
        FROM (
          SELECT DISTINCT signature,profile,locator_order,
            CASE
              WHEN cohort='visible' THEN 'target'
              WHEN cohort IN ('old_generation','old_index') AND source_order<=4 THEN 'target'
              ELSE cohort
            END AS vector_cohort
          FROM m403a_unit_seed
        ) keys
        """


def _embedding_insert_sql() -> str:
    return """
        INSERT INTO content_unit_embeddings(
          id,workspace_id,content_unit_id,embedding_space,provider,model,dimensions,
          version,asset_id,processing_generation,index_version,is_current,embedding,created_at
        )
        SELECT units.embedding_id,units.workspace_id,units.unit_id,'text',
          CASE WHEN units.cohort='wrong_provider' THEN 'wrong-provider' ELSE 'm403a' END,
          CASE WHEN units.cohort='wrong_provider' THEN 'wrong-model' ELSE 'deterministic-1024' END,
          1024,
          CASE WHEN units.cohort='wrong_provider' THEN 'wrong-version' ELSE 'm403a-v1' END,
          units.asset_id,
          units.generation,
          units.index_version,
          (units.generation = 2 AND units.index_version = 2),
          (vectors.signal || array_fill(0.0::real, ARRAY[960]))::vector,
          :now
        FROM m403a_unit_seed units
        JOIN m403a_vector_seed vectors
          ON vectors.signature=units.signature
         AND vectors.profile=units.profile
         AND vectors.locator_order=units.locator_order
         AND vectors.vector_cohort=CASE
           WHEN units.cohort='visible' THEN 'target'
           WHEN units.cohort IN ('old_generation','old_index') AND units.source_order<=4
             THEN 'target'
           ELSE units.cohort
         END
        """


def _seed_metadata(connection, scale: Scale, visible_total: int, physical_total: int) -> list[dict[str, Any]]:
    target = _target_workspace(scale)
    noise = _noise_workspace(scale)
    user = _id(scale, "user")
    connection.execute(
        text(
            """
            INSERT INTO users(id,email,name,password_hash,avatar_url,created_at,updated_at)
            VALUES (:user,:email,'M403A Capacity','not-used','https://example.com/m403a.svg',:now,:now)
            """
        ),
        {"user": user, "email": f"m403a-{scale}@example.com", "now": NOW},
    )
    connection.execute(
        text(
            """
            INSERT INTO workspaces(
              id,name,description,system_prompt,retrieval_top_k,chunk_size,
              created_by_user_id,created_at,updated_at
            ) VALUES
              (:target,:target_name,'M403A target corpus','capacity',10,1200,:user,:now,:now),
              (:noise,:noise_name,'M403A outside-workspace noise','capacity',10,1200,:user,:now,:now)
            """
        ),
        {
            "target": target,
            "noise": noise,
            "target_name": f"M403A {scale.upper()} target",
            "noise_name": f"M403A {scale.upper()} noise",
            "user": user,
            "now": NOW,
        },
    )
    visible_counts = _signature_counts(visible_total)
    noise_counts = _noise_counts(physical_total - visible_total)
    rows: list[dict[str, Any]] = []
    for order, ((signature, asset_kind, unit_kind, rep_kind, locator_kind, _weight), visible_count) in enumerate(
        zip(SIGNATURES, visible_counts, strict=True),
        start=1,
    ):
        row = {
            "signature": signature,
            "signature_order": order,
            "asset_kind": asset_kind,
            "unit_kind": unit_kind,
            "representation_kind": rep_kind,
            "locator_kind": locator_kind,
            "visible_count": visible_count,
            "outside_count": noise_counts["outside"][order - 1],
            "old_generation_count": noise_counts["old_generation"][order - 1],
            "old_index_count": noise_counts["old_index"][order - 1],
            "wrong_provider_count": noise_counts["wrong_provider"][order - 1],
            "visible_asset_id": _asset_id(scale, "visible", signature),
            "visible_rep_g1": _representation_id(scale, "visible", signature, 1),
            "visible_rep_g2": _representation_id(scale, "visible", signature, 2),
            "outside_asset_id": _asset_id(scale, "outside", signature),
            "outside_rep_g2": _representation_id(scale, "outside", signature, 2),
        }
        rows.append(row)
        for cohort, workspace_id, status, asset_id in (
            ("visible", target, "ready", row["visible_asset_id"]),
            ("outside", noise, "ready", row["outside_asset_id"]),
        ):
            connection.execute(
                text(
                    """
                    INSERT INTO assets(
                      id,workspace_id,created_by_user_id,asset_kind,title,source_filename,
                      object_key,mime_type,byte_size,source_sha256,status,
                      current_processing_generation,current_index_version,created_at,updated_at
                    ) VALUES (
                      :id,:workspace_id,:user,:asset_kind,:title,:title,:object_key,:mime_type,
                      0,NULL,:status,2,2,:now,:now
                    )
                    """
                ),
                {
                    "id": asset_id,
                    "workspace_id": workspace_id,
                    "user": user,
                    "asset_kind": asset_kind,
                    "title": f"{scale}-{cohort}-{signature}",
                    "object_key": f"m403a/{scale}/{cohort}/{signature}",
                    "mime_type": "application/pdf" if asset_kind == "pdf" else "image/png",
                    "status": status,
                    "now": NOW,
                },
            )
        for cohort, workspace_id, asset_id, generation, representation_id in (
            ("visible", target, row["visible_asset_id"], 1, row["visible_rep_g1"]),
            ("visible", target, row["visible_asset_id"], 2, row["visible_rep_g2"]),
            ("outside", noise, row["outside_asset_id"], 2, row["outside_rep_g2"]),
        ):
            connection.execute(
                text(
                    """
                    INSERT INTO asset_representations(
                      id,workspace_id,asset_id,representation_kind,processing_generation,
                      generator_provider,generator_model,generator_version,created_at
                    ) VALUES (:id,:workspace_id,:asset_id,:kind,:generation,'m403a','deterministic','m403a-v1',:now)
                    """
                ),
                {
                    "id": representation_id,
                    "workspace_id": workspace_id,
                    "asset_id": asset_id,
                    "kind": rep_kind,
                    "generation": generation,
                    "now": NOW,
                },
            )
    connection.execute(
        text(
            """
            CREATE TEMP TABLE m403a_signature_seed(
              signature text, signature_order integer, asset_kind text, unit_kind text,
              representation_kind text, locator_kind text, visible_count bigint,
              outside_count bigint, old_generation_count bigint, old_index_count bigint,
              wrong_provider_count bigint, visible_asset_id text, visible_rep_g1 text,
              visible_rep_g2 text, outside_asset_id text, outside_rep_g2 text
            ) ON COMMIT DROP
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO m403a_signature_seed VALUES (
              :signature,:signature_order,:asset_kind,:unit_kind,:representation_kind,
              :locator_kind,:visible_count,:outside_count,:old_generation_count,
              :old_index_count,:wrong_provider_count,:visible_asset_id,:visible_rep_g1,
              :visible_rep_g2,:outside_asset_id,:outside_rep_g2
            )
            """
        ),
        rows,
    )
    return rows


CREATE_UNIT_SEED_SQL = """
CREATE TEMP TABLE m403a_unit_seed ON COMMIT DROP AS
WITH cohorts AS (
  SELECT s.*, c.cohort, c.row_count,
    CASE c.cohort
      WHEN 'outside' THEN :noise_workspace
      ELSE :target_workspace
    END AS workspace_id,
    CASE c.cohort
      WHEN 'outside' THEN s.outside_asset_id
      ELSE s.visible_asset_id
    END AS asset_id,
    CASE c.cohort
      WHEN 'outside' THEN s.outside_rep_g2
      WHEN 'old_generation' THEN s.visible_rep_g1
      ELSE s.visible_rep_g2
    END AS representation_id,
    CASE c.cohort WHEN 'old_generation' THEN 1 ELSE 2 END AS generation,
    CASE c.cohort WHEN 'old_index' THEN 1 ELSE 2 END AS index_version
  FROM m403a_signature_seed s
  CROSS JOIN LATERAL (VALUES
    ('visible', s.visible_count),
    ('outside', s.outside_count),
    ('old_generation', s.old_generation_count),
    ('old_index', s.old_index_count),
    ('wrong_provider', s.wrong_provider_count)
  ) c(cohort, row_count)
), expanded AS (
  SELECT c.*, g AS source_order,
    CASE WHEN c.cohort = 'visible' THEN
      CASE (g - 1) % 3 WHEN 0 THEN 'D1' WHEN 1 THEN 'D8' ELSE 'D64' END
    ELSE 'D8' END AS profile,
    CASE WHEN c.cohort = 'visible' THEN ((g - 1) / 3) + 1 ELSE g END AS profile_order
  FROM cohorts c
  CROSS JOIN LATERAL generate_series(1, c.row_count) g
), profiled AS (
  SELECT e.*,
    CASE e.profile WHEN 'D1' THEN 1 WHEN 'D8' THEN 8 ELSE 64 END AS duplicate_factor,
    CASE e.profile WHEN 'D1' THEN 0.3::real WHEN 'D8' THEN 0.0::real ELSE 0.6::real END AS profile_code
  FROM expanded e
)
SELECT p.*,
  ((p.profile_order - 1) / p.duplicate_factor) + 1 AS locator_order,
  ((p.profile_order - 1) % p.duplicate_factor)::integer AS unit_order,
  md5(:scale || ':locator:' || p.cohort || ':' || p.signature || ':' || p.profile || ':' || (((p.profile_order - 1) / p.duplicate_factor) + 1)::text)::uuid::text AS locator_id,
  md5(:scale || ':unit:' || p.cohort || ':' || p.signature || ':' || p.source_order::text)::uuid::text AS unit_id,
  md5(:scale || ':embedding:' || p.cohort || ':' || p.signature || ':' || p.source_order::text)::uuid::text AS embedding_id
FROM profiled p
"""


def _seed_units(connection, scale: Scale) -> None:
    connection.execute(
        text(CREATE_UNIT_SEED_SQL),
        {
            "target_workspace": _target_workspace(scale),
            "noise_workspace": _noise_workspace(scale),
            "scale": scale,
        },
    )
    connection.execute(text("ANALYZE m403a_unit_seed"))
    connection.execute(
        text(
            """
            INSERT INTO evidence_locators(
              id,workspace_id,asset_id,locator_kind,locator_version,
              processing_generation_snapshot,representation_id_snapshot,created_at
            )
            SELECT locator_id,min(workspace_id),min(asset_id),min(locator_kind),1,
                   min(generation),min(representation_id),:now
            FROM m403a_unit_seed
            GROUP BY locator_id
            """
        ),
        {"now": NOW},
    )
    connection.execute(
        text(
            """
            INSERT INTO pdf_locator_details(
              locator_id,page_number,coordinate_space,crop_x0_points,crop_y0_points,
              crop_x1_points,crop_y1_points,rotation_degrees,display_width_points,display_height_points
            )
            SELECT locator_id,
              min((CASE profile WHEN 'D1' THEN 1000000 WHEN 'D8' THEN 2000000 ELSE 3000000 END) + locator_order)::integer,
              CASE WHEN min(locator_kind)='pdf_region' THEN 'pdf_crop_box_normalized_top_left_v1' ELSE NULL END,
              0,0,612,792,0,612,792
            FROM m403a_unit_seed
            WHERE locator_kind IN ('pdf_page','pdf_region')
            GROUP BY locator_id
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO image_locator_details(locator_id,coordinate_space,width_pixels,height_pixels,orientation_applied)
            SELECT DISTINCT locator_id,'image_normalized_top_left_v1',1200,800,true
            FROM m403a_unit_seed WHERE locator_kind='image_region'
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO spatial_locator_regions(id,locator_id,region_order,x,y,width,height)
            SELECT md5(:scale || ':region:' || l.id)::uuid::text,
                   l.id,0,0.1,0.2,0.4,0.3
            FROM evidence_locators l
            WHERE l.workspace_id IN (:target_workspace,:noise_workspace)
              AND l.locator_kind IN ('pdf_region','image_region')
            """
        ),
        {
            "scale": scale,
            "target_workspace": _target_workspace(scale),
            "noise_workspace": _noise_workspace(scale),
        },
    )
    connection.execute(
        text(
            """
            INSERT INTO content_units(
              id,workspace_id,asset_id,representation_id,source_locator_id,unit_kind,
              unit_order,text_content,token_count,char_start,char_end,index_version,created_at
            )
            SELECT unit_id,workspace_id,asset_id,representation_id,locator_id,unit_kind,
                   unit_order,
                   rpad(
                     'm403a capacity ' || signature || ' ' || profile || ' row ' || source_order ||
                       CASE WHEN cohort <> 'wrong_provider' AND source_order % 97 = 0
                         THEN ' raretokenalpha' ELSE '' END,
                     CASE WHEN source_order % 5 = 0 THEN 1200 ELSE 500 END,
                     ' evidence context'
                   ),
                   CASE WHEN source_order % 5 = 0 THEN 300 ELSE 125 END,
                   NULL,NULL,index_version,:now
            FROM m403a_unit_seed
            """
        ),
        {"now": NOW},
    )
    connection.execute(text(_vector_seed_sql()), {"scale": scale})
    connection.execute(text("ANALYZE m403a_vector_seed"))
    connection.execute(
        text(_embedding_insert_sql()),
        {"now": NOW},
    )


INDEX_SQL = {
    "hnsw": "CREATE INDEX ix_content_unit_embeddings_current_embedding_hnsw ON content_unit_embeddings USING hnsw (embedding vector_cosine_ops) WITH (ef_construction=512) WHERE is_current IS TRUE",
    "binaryHnsw": "CREATE INDEX ix_content_unit_embeddings_current_embedding_binary_hnsw ON content_unit_embeddings USING hnsw ((binary_quantize(embedding)::bit(1024)) bit_hamming_ops) WITH (ef_construction=64) WHERE is_current IS TRUE",
    "ftsGin": "CREATE INDEX ix_content_units_text_content_fts ON content_units USING gin (search_vector)",
    "trigramGist": "CREATE INDEX ix_content_units_text_content_trgm_gist ON content_units USING gist (text_content gist_trgm_ops(siglen=64))",
}

ANALYZE_TABLES = (
    "assets",
    "asset_representations",
    "evidence_locators",
    "pdf_locator_details",
    "image_locator_details",
    "spatial_locator_regions",
    "content_units",
    "content_unit_embeddings",
)


def seed(engine: Engine, scale: Scale) -> dict[str, Any]:
    visible_total, physical_total = SCALES[scale]
    started = time.perf_counter()
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL synchronous_commit=off"))
        for index_name in (
            "ix_content_unit_embeddings_current_embedding_hnsw",
            "ix_content_unit_embeddings_current_embedding_binary_hnsw",
            "ix_content_units_text_content_fts",
            "ix_content_units_text_content_trgm_gist",
        ):
            connection.execute(text(f'DROP INDEX IF EXISTS "{index_name}"'))
        signature_rows = _seed_metadata(connection, scale, visible_total, physical_total)
        _seed_units(connection, scale)
    load_seconds = time.perf_counter() - started
    index_seconds: dict[str, float] = {}
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("SET maintenance_work_mem='2GB'"))
        for name, statement in INDEX_SQL.items():
            index_started = time.perf_counter()
            connection.execute(text(statement))
            index_seconds[name] = time.perf_counter() - index_started
        vacuum_started = time.perf_counter()
        for table_name in ANALYZE_TABLES:
            connection.execute(text(f'VACUUM (ANALYZE) "{table_name}"'))
        vacuum_seconds = time.perf_counter() - vacuum_started
        checkpoint_started = time.perf_counter()
        connection.execute(text("CHECKPOINT"))
        checkpoint_seconds = time.perf_counter() - checkpoint_started
    with engine.connect() as connection:
        counts = {
            "contentUnits": connection.scalar(text("SELECT count(*) FROM content_units")),
            "embeddings": connection.scalar(text("SELECT count(*) FROM content_unit_embeddings")),
            "currentEmbeddings": connection.scalar(
                text("SELECT count(*) FROM content_unit_embeddings WHERE is_current IS TRUE")
            ),
            "invalidCurrentEmbeddings": connection.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM content_unit_embeddings e
                    JOIN content_units cu ON cu.id=e.content_unit_id
                    JOIN evidence_locators l ON l.id=cu.source_locator_id
                    JOIN assets a ON a.id=cu.asset_id
                    WHERE e.is_current IS TRUE
                      AND (
                        e.workspace_id<>cu.workspace_id
                        OR e.asset_id<>cu.asset_id
                        OR e.processing_generation<>l.processing_generation_snapshot
                        OR e.index_version<>cu.index_version
                        OR e.processing_generation<>a.current_processing_generation
                        OR e.index_version<>a.current_index_version
                      )
                    """
                )
            ),
            "locators": connection.scalar(text("SELECT count(*) FROM evidence_locators")),
            "lexicalCurrentChain": connection.scalar(
                text(
                    """
                    SELECT count(*) FROM content_units cu
                    JOIN assets a ON a.id=cu.asset_id
                    JOIN asset_representations r ON r.id=cu.representation_id
                    JOIN evidence_locators l ON l.id=cu.source_locator_id
                    WHERE cu.workspace_id=:workspace AND a.workspace_id=:workspace
                      AND a.status='ready' AND a.deleted_at IS NULL
                      AND r.processing_generation=a.current_processing_generation
                      AND l.processing_generation_snapshot=a.current_processing_generation
                      AND cu.index_version=a.current_index_version
                    """
                ),
                {"workspace": _target_workspace(scale)},
            ),
            "denseEligible": connection.scalar(
                text(
                    """
                    SELECT count(*) FROM content_units cu
                    JOIN assets a ON a.id=cu.asset_id
                    JOIN asset_representations r ON r.id=cu.representation_id
                    JOIN evidence_locators l ON l.id=cu.source_locator_id
                    JOIN content_unit_embeddings e ON e.content_unit_id=cu.id
                    WHERE cu.workspace_id=:workspace AND a.workspace_id=:workspace
                      AND a.status='ready' AND a.deleted_at IS NULL
                      AND r.processing_generation=a.current_processing_generation
                      AND l.processing_generation_snapshot=a.current_processing_generation
                      AND cu.index_version=a.current_index_version
                      AND e.workspace_id=:workspace AND e.embedding_space='text'
                      AND e.is_current IS TRUE
                      AND e.provider='m403a' AND e.model='deterministic-1024'
                      AND e.version='m403a-v1' AND e.dimensions=1024
                    """
                ),
                {"workspace": _target_workspace(scale)},
            ),
        }
        by_signature = [dict(row) for row in connection.execute(
            text(
                """
                SELECT a.title,count(*) AS count
                FROM content_units cu
                JOIN assets a ON a.id=cu.asset_id
                JOIN asset_representations r ON r.id=cu.representation_id
                JOIN evidence_locators l ON l.id=cu.source_locator_id
                JOIN content_unit_embeddings e ON e.content_unit_id=cu.id
                WHERE cu.workspace_id=:workspace AND a.status='ready'
                  AND cu.index_version=a.current_index_version
                  AND r.processing_generation=a.current_processing_generation
                  AND l.processing_generation_snapshot=a.current_processing_generation
                  AND e.is_current IS TRUE
                  AND e.provider='m403a' AND e.model='deterministic-1024'
                  AND e.version='m403a-v1' AND e.dimensions=1024
                GROUP BY a.title ORDER BY a.title
                """
            ),
            {"workspace": _target_workspace(scale)},
        ).mappings()]
        profile_counts = {
            row["profile"]: {"rows": int(row["rows"]), "locations": int(row["locations"])}
            for row in connection.execute(
                text(
                    """
                    SELECT split_part(cu.text_content,' ',4) AS profile,
                           count(*) AS rows,
                           count(DISTINCT cu.source_locator_id) AS locations
                    FROM content_units cu
                    JOIN assets a ON a.id=cu.asset_id
                    JOIN asset_representations r ON r.id=cu.representation_id
                    JOIN evidence_locators l ON l.id=cu.source_locator_id
                    JOIN content_unit_embeddings e ON e.content_unit_id=cu.id
                    WHERE cu.workspace_id=:workspace AND a.status='ready'
                      AND cu.index_version=a.current_index_version
                      AND r.processing_generation=a.current_processing_generation
                      AND l.processing_generation_snapshot=a.current_processing_generation
                      AND e.is_current IS TRUE
                      AND e.provider='m403a' AND e.model='deterministic-1024'
                      AND e.version='m403a-v1' AND e.dimensions=1024
                    GROUP BY profile ORDER BY profile
                    """
                ),
                {"workspace": _target_workspace(scale)},
            ).mappings()
        }
        text_distribution = dict(
            connection.execute(
                text(
                    """
                    SELECT avg(length(text_content)) AS average,
                           percentile_disc(0.50) WITHIN GROUP (ORDER BY length(text_content)) AS p50,
                           percentile_disc(0.95) WITHIN GROUP (ORDER BY length(text_content)) AS p95,
                           min(length(text_content)) AS minimum,
                           max(length(text_content)) AS maximum,
                           count(*) FILTER (WHERE text_content LIKE '%raretokenalpha%') AS rare_token_rows
                    FROM content_units
                    """
                )
            ).mappings().one()
        )
        text_distribution = {
            "average": float(text_distribution["average"]),
            "p50": int(text_distribution["p50"]),
            "p95": int(text_distribution["p95"]),
            "minimum": int(text_distribution["minimum"]),
            "maximum": int(text_distribution["maximum"]),
            "rareTokenRows": int(text_distribution["rare_token_rows"]),
        }
        cohort_rows = [
            dict(row)
            for row in connection.execute(
                text(
                    """
                    SELECT CASE
                             WHEN cu.workspace_id<>:workspace THEN 'outside'
                             WHEN r.processing_generation<>a.current_processing_generation THEN 'old_generation'
                             WHEN cu.index_version<>a.current_index_version THEN 'old_index'
                             WHEN e.provider<>'m403a' OR e.model<>'deterministic-1024'
                               OR e.version<>'m403a-v1' THEN 'wrong_provider'
                             ELSE 'visible'
                           END AS cohort,
                           a.asset_kind,cu.unit_kind,r.representation_kind,l.locator_kind,
                           split_part(cu.text_content,' ',4) AS profile,
                           count(*) AS count
                    FROM content_units cu
                    JOIN assets a ON a.id=cu.asset_id
                    JOIN asset_representations r ON r.id=cu.representation_id
                    JOIN evidence_locators l ON l.id=cu.source_locator_id
                    JOIN content_unit_embeddings e ON e.content_unit_id=cu.id
                    GROUP BY cohort,a.asset_kind,cu.unit_kind,r.representation_kind,l.locator_kind,profile
                    ORDER BY cohort,a.asset_kind,cu.unit_kind,r.representation_kind,l.locator_kind,profile
                    """
                ),
                {"workspace": _target_workspace(scale)},
            ).mappings()
        ]
        signature_by_type = {tuple(item[1:5]): item[0] for item in SIGNATURES}
        cohort_signature_counts = [
            {
                "cohort": row["cohort"],
                "signature": signature_by_type[
                    (
                        row["asset_kind"],
                        row["unit_kind"],
                        row["representation_kind"],
                        row["locator_kind"],
                    )
                ],
                "profile": row["profile"],
                "count": int(row["count"]),
            }
            for row in cohort_rows
        ]
        poison_counts = {
            row["cohort"]: {
                "annNearestRows": int(row["ann_nearest_rows"]),
                "lexicalTokenRows": int(row["lexical_token_rows"]),
            }
            for row in connection.execute(
                text(
                    """
                    SELECT CASE
                             WHEN cu.workspace_id<>:workspace THEN 'outside'
                             WHEN r.processing_generation<>a.current_processing_generation THEN 'old_generation'
                             WHEN cu.index_version<>a.current_index_version THEN 'old_index'
                             WHEN e.provider<>'m403a' OR e.model<>'deterministic-1024'
                               OR e.version<>'m403a-v1' THEN 'wrong_provider'
                             ELSE 'visible'
                           END AS cohort,
                           count(*) FILTER (
                             WHERE split_part(cu.text_content,' ',4)='D8'
                               AND split_part(cu.text_content,' ',6)::integer<=4
                           ) AS ann_nearest_rows,
                           count(*) FILTER (
                             WHERE cu.text_content LIKE '%raretokenalpha%'
                           ) AS lexical_token_rows
                    FROM content_units cu
                    JOIN assets a ON a.id=cu.asset_id
                    JOIN asset_representations r ON r.id=cu.representation_id
                    JOIN content_unit_embeddings e ON e.content_unit_id=cu.id
                    GROUP BY cohort ORDER BY cohort
                    """
                ),
                {"workspace": _target_workspace(scale)},
            ).mappings()
        }
    expected_embeddings = physical_total
    noise_per_cohort = (physical_total - visible_total) // 4
    wrong_provider_count = (physical_total - visible_total) // 4
    expected_current_embeddings = visible_total + noise_per_cohort + wrong_provider_count
    expected_signature_counts = {
        f"{scale}-visible-{signature}": count
        for (signature, *_), count in zip(SIGNATURES, _signature_counts(visible_total), strict=True)
    }
    actual_signature_counts = {row["title"]: int(row["count"]) for row in by_signature}
    expected_cohort_signature_counts: dict[tuple[str, str, str], int] = {}
    for row in signature_rows:
        visible_count = int(row["visible_count"])
        expected_cohort_signature_counts.update(
            {
                ("visible", row["signature"], "D1"): (visible_count + 2) // 3,
                ("visible", row["signature"], "D8"): (visible_count + 1) // 3,
                ("visible", row["signature"], "D64"): visible_count // 3,
            }
        )
        for cohort in ("outside", "old_generation", "old_index", "wrong_provider"):
            expected_cohort_signature_counts[(cohort, row["signature"], "D8")] = int(
                row[f"{cohort}_count"]
            )
    actual_cohort_signature_counts = {
        (row["cohort"], row["signature"], row["profile"]): row["count"]
        for row in cohort_signature_counts
    }
    persisted_fingerprint = _persisted_fingerprint(
        cohort_signature_counts,
        profile_counts,
        text_distribution,
    )
    checks = {
        "physicalContentUnits": counts["contentUnits"] == physical_total,
        "denseEligible": counts["denseEligible"] == visible_total,
        "lexicalCurrentChain": counts["lexicalCurrentChain"] == visible_total + wrong_provider_count,
        "embeddingCount": counts["embeddings"] == expected_embeddings,
        "currentEmbeddingProjection": (
            counts["currentEmbeddings"] == expected_current_embeddings
            and counts["invalidCurrentEmbeddings"] == 0
        ),
        "eightProductionSignatures": (
            len(signature_rows) == 8
            and CONFIGURED_TYPE_SIGNATURES.issubset(PRODUCTION_TEXT_TYPE_SIGNATURES)
            and len(CONFIGURED_TYPE_SIGNATURES) == len(SIGNATURES)
            and actual_signature_counts == expected_signature_counts
        ),
        "duplicateProfiles": profile_counts == _expected_profile_counts(visible_total),
        "cohortSignatureDistribution": (
            actual_cohort_signature_counts == expected_cohort_signature_counts
        ),
        "textDistribution": (
            text_distribution["minimum"] == 500
            and text_distribution["p50"] == 500
            and text_distribution["p95"] == 1200
            and text_distribution["maximum"] == 1200
        ),
        "poisonCoverage": (
            all(
                poison_counts[name]["lexicalTokenRows"] > 0
                for name in ("visible", "outside", "old_generation", "old_index")
            )
            and poison_counts["old_generation"]["annNearestRows"] > 0
            and poison_counts["old_index"]["annNearestRows"] > 0
            and poison_counts["wrong_provider"]["lexicalTokenRows"] == 0
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"M403A seed checks failed: {checks}")
    return {
        "schemaVersion": "m403a-seed-v3",
        "scale": scale,
        "visibleContentUnits": visible_total,
        "physicalContentUnits": physical_total,
        "wrongProviderContentUnits": wrong_provider_count,
        "counts": counts,
        "bySignature": by_signature,
        "profileCounts": profile_counts,
        "textDistribution": text_distribution,
        "cohortSignatureProfileCounts": cohort_signature_counts,
        "poisonCounts": poison_counts,
        "loadSeconds": round(load_seconds, 3),
        "indexBuildSeconds": {key: round(value, 3) for key, value in index_seconds.items()},
        "vacuumSeconds": round(vacuum_seconds, 3),
        "checkpointSeconds": round(checkpoint_seconds, 3),
        "loadAndIndexSeconds": round(
            load_seconds
            + sum(index_seconds.values())
            + vacuum_seconds
            + checkpoint_seconds,
            3,
        ),
        "checks": checks,
        "datasetChecksum": _dataset_checksum(scale, signature_rows),
        "persistedFingerprint": persisted_fingerprint,
    }


def _dataset_checksum(scale: Scale, rows: list[dict[str, Any]]) -> str:
    from hashlib import sha256

    payload = json.dumps(
        {"scale": scale, "sizes": SCALES[scale], "signatures": rows},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return sha256(payload).hexdigest()


def _persisted_fingerprint(
    cohort_signature_counts: list[dict[str, Any]],
    profile_counts: dict[str, dict[str, int]],
    text_distribution: dict[str, Any],
) -> str:
    from hashlib import sha256

    payload = json.dumps(
        {
            "cohortSignatureProfileCounts": cohort_signature_counts,
            "profileCounts": profile_counts,
            "textDistribution": text_distribution,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return sha256(payload).hexdigest()


def _query_vector_from_database(
    db: Session,
    scale: Scale,
    signature: str,
    profile: str,
) -> list[float]:
    source_order = {"D1": 1, "D8": 2, "D64": 3}[profile]
    vector = db.scalar(
        select(ContentUnitEmbedding.embedding).where(
            ContentUnitEmbedding.content_unit_id
            == _content_unit_id(scale, "visible", signature, source_order),
            ContentUnitEmbedding.is_current.is_(True),
        )
    )
    if not isinstance(vector, list) or len(vector) != 1024:
        raise RuntimeError(f"M403A query vector missing for {signature}:{profile}")
    return vector


def _dense_exact_statement(
    workspace_id: str,
    asset_ids: list[str] | None,
    vector: list[float],
):
    provider = CapacityProvider()
    statement = (
        retrieval_scope_statement(workspace_id, asset_ids, TEXT_CHANNEL)
        .join(ContentUnitEmbedding, ContentUnitEmbedding.content_unit_id == ContentUnit.id)
        .where(
            ContentUnitEmbedding.workspace_id == workspace_id,
            ContentUnitEmbedding.is_current.is_(True),
            ContentUnitEmbedding.embedding_space == TEXT_CHANNEL.embedding_space,
            ContentUnitEmbedding.provider == provider.provider,
            ContentUnitEmbedding.model == provider.model,
            ContentUnitEmbedding.version == provider.version,
            ContentUnitEmbedding.dimensions == provider.dimensions,
        )
    )
    # Adding zero preserves distance while preventing the ANN ordering operator from being used.
    distance_expression = ContentUnitEmbedding.embedding.cosine_distance(vector) + literal(0.0)
    distance = distance_expression.label("distance")
    return statement.add_columns(distance).order_by(distance, ContentUnit.id)


def _dense_ann_statement(
    workspace_id: str,
    asset_ids: list[str] | None,
    vector: list[float],
    *,
    ann_limit: int,
):
    provider = CapacityProvider()
    return _dense_ann_ranked_statement(
        retrieval_scope_statement(workspace_id, asset_ids, TEXT_CHANNEL),
        workspace_id,
        asset_ids,
        vector,
        provider.provider,
        provider.model,
        provider.version,
        provider.dimensions,
        ann_limit=ann_limit,
    )


def _latin_statement(workspace_id: str, asset_ids: list[str] | None, query: str):
    scoped = retrieval_scope_statement(workspace_id, asset_ids, TEXT_CHANNEL)
    terms = _unique_latin_terms(query)
    return _latin_lexical_ranked_statement(
        scoped,
        workspace_id,
        asset_ids,
        terms,
        candidate_limit=20,
    )


def _cjk_statement(workspace_id: str, asset_ids: list[str] | None, query: str):
    scoped = retrieval_scope_statement(workspace_id, asset_ids, TEXT_CHANNEL)
    value = bindparam("lexical_query", value=query)
    distance = ContentUnit.text_content.op("<->>")(value).label("lexical_distance")
    return (
        scoped.with_only_columns(ContentUnit.id, distance, maintain_column_froms=True)
        .order_by(distance, ContentUnit.id)
    )


def _raw_explain(db: Session, statement, *, limit: int) -> list[dict[str, Any]]:
    compiled = statement.limit(limit).compile(
        dialect=db.bind.dialect,
        compile_kwargs={"render_postcompile": True},
    )
    processors = compiled._bind_processors  # SQLAlchemy exposes the production type binders here.
    parameters = {
        key: processors[key](value) if key in processors else value
        for key, value in compiled.params.items()
    }
    raw = db.connection().connection
    with raw.cursor() as cursor:
        cursor.execute(
            f"EXPLAIN (ANALYZE, BUFFERS, SETTINGS, FORMAT JSON) {compiled}",
            parameters,
        )
        return cursor.fetchone()[0]


def _walk_plan(node: dict[str, Any]) -> list[dict[str, Any]]:
    result = [node]
    for child in node.get("Plans", []):
        result.extend(_walk_plan(child))
    return result


def _plan_summary(plan: list[dict[str, Any]]) -> dict[str, Any]:
    document = plan[0]
    root = document["Plan"]
    nodes = _walk_plan(root)
    hits = int(root.get("Shared Hit Blocks", 0))
    reads = int(root.get("Shared Read Blocks", 0))
    return {
        "planningTimeMs": document.get("Planning Time"),
        "executionTimeMs": document.get("Execution Time"),
        "nodeTypes": sorted({node.get("Node Type") for node in nodes}),
        "indexes": sorted({node["Index Name"] for node in nodes if node.get("Index Name")}),
        "sharedHitBlocks": hits,
        "sharedReadBlocks": reads,
        "sharedBufferHitRatio": hits / (hits + reads) if hits + reads else 1.0,
        "tempReadBlocks": int(root.get("Temp Read Blocks", 0)),
        "tempWrittenBlocks": int(root.get("Temp Written Blocks", 0)),
        "raw": plan,
    }


def _recall(expected: list[Any], actual: list[Any]) -> float:
    return len(set(expected) & set(actual)) / len(expected) if expected else 0.0


def _location_keys(items: list[Any]) -> list[tuple[str, str]]:
    return [item.location_key for item in items]


def _instrument_unique(
    db: Session,
    workspace_id: str,
    vector: list[float],
    limit: int = 10,
) -> dict[str, Any]:
    provider = CapacityProvider()
    scoped_statement = retrieval_scope_statement(workspace_id, None, TEXT_CHANNEL)
    candidate_limit = limit
    rounds = []
    while True:
        rows = _load_dense_ranked_rows(
            db,
            scoped_statement,
            workspace_id,
            None,
            vector,
            provider.provider,
            provider.model,
            provider.version,
            provider.dimensions,
            candidate_limit,
        )
        candidates = _candidates(
            db,
            [
                (unit, asset, locator, representation, float(distance))
                for unit, asset, locator, representation, distance in rows
            ],
        )
        unique = _dedupe_locations(candidates)
        rounds.append(
            {
                "rankedLimit": candidate_limit,
                "rankedRows": len(rows),
                "uniqueLocations": len(unique),
            }
        )
        if len(unique) >= limit or len(rows) < candidate_limit:
            results = unique[:limit]
            return {
                "rounds": rounds,
                "roundCount": len(rounds),
                "cumulativeRankedRows": sum(item["rankedRows"] for item in rounds),
                "resultCount": len(results),
                "orderedLocationKeys": [list(key) for key in _location_keys(results)],
            }
        candidate_limit *= 2


def _exact_location_comparison(
    db: Session,
    workspace_id: str,
    vector: list[float],
    provider: CapacityProvider,
    expected_signature: str,
    require_exclusive_signature: bool,
    asset_ids: list[str] | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    maximum_ranked = limit * max(PROFILE_DUPLICATES.values())
    exact_rows = db.execute(
        _dense_exact_statement(workspace_id, asset_ids, vector).limit(maximum_ranked)
    ).all()
    exact_candidates = _candidates(
        db,
        [
            (unit, asset, locator, representation, float(distance))
            for unit, asset, locator, representation, distance in exact_rows
        ],
    )
    exact_rounds = []
    exact_results = []
    ranked_limit = limit
    while ranked_limit <= maximum_ranked:
        exact_results = _dedupe_locations(exact_candidates[:ranked_limit])
        exact_rounds.append(
            {
                "rankedLimit": ranked_limit,
                "rankedRows": min(ranked_limit, len(exact_rows)),
                "uniqueLocations": len(exact_results),
            }
        )
        if len(exact_results) >= limit or len(exact_rows) < ranked_limit:
            break
        ranked_limit *= 2
    exact_results = exact_results[:limit]
    hnsw_results = retrieve_content(
        db,
        workspace_id,
        vector,
        embedding_provider=provider,
        asset_ids=asset_ids,
        limit=limit,
    )
    exact_keys = _location_keys(exact_results)
    hnsw_keys = _location_keys(hnsw_results)
    result_ids = [item.content_unit.id for item in hnsw_results]
    embedding_contract_statement = (
        select(func.count())
        .select_from(ContentUnitEmbedding)
        .where(
            ContentUnitEmbedding.content_unit_id.in_(result_ids),
            ContentUnitEmbedding.workspace_id == workspace_id,
            ContentUnitEmbedding.is_current.is_(True),
            ContentUnitEmbedding.embedding_space == TEXT_CHANNEL.embedding_space,
            ContentUnitEmbedding.provider == provider.provider,
            ContentUnitEmbedding.model == provider.model,
            ContentUnitEmbedding.version == provider.version,
            ContentUnitEmbedding.dimensions == provider.dimensions,
        )
    )
    if asset_ids is not None:
        embedding_contract_statement = embedding_contract_statement.where(
            ContentUnitEmbedding.asset_id.in_(asset_ids)
        )
    embedding_contract_count = int(db.scalar(embedding_contract_statement) or 0)
    ordered_signatures = [
        item.asset.title.split("-visible-", 1)[1]
        for item in hnsw_results
    ]
    actual_signatures = sorted(set(ordered_signatures))
    contract_checks = {
        "resultCount": len(hnsw_results) == limit,
        "workspace": all(
            item.content_unit.workspace_id == workspace_id
            and item.asset.workspace_id == workspace_id
            and item.locator.workspace_id == workspace_id
            for item in hnsw_results
        ),
        "currentChain": all(
            item.content_unit.index_version == item.asset.current_index_version
            and item.locator.processing_generation_snapshot
            == item.asset.current_processing_generation
            for item in hnsw_results
        ),
        "embeddingMetadata": embedding_contract_count == len(hnsw_results),
        "expectedSignatureCovered": (
            bool(ordered_signatures)
            and ordered_signatures[0] == expected_signature
            and expected_signature in actual_signatures
        ),
        "expectedSignatureExclusiveWhenRequired": (
            not require_exclusive_signature
            or actual_signatures == [expected_signature]
        ),
    }
    return {
        "expectedSignature": expected_signature,
        "orderedSignatures": ordered_signatures,
        "actualSignatures": actual_signatures,
        "contractChecks": contract_checks,
        "exactOrderedLocationKeys": [list(key) for key in exact_keys],
        "hnswOrderedLocationKeys": [list(key) for key in hnsw_keys],
        "recallAt10": _recall(exact_keys, hnsw_keys),
        "exactRounds": exact_rounds,
        "assetIds": asset_ids,
    }


def _latency_summary(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    def percentile(value: float) -> float:
        index = min(len(ordered) - 1, max(0, math.ceil(value * len(ordered)) - 1))
        return ordered[index]
    return {
        "min": min(ordered),
        "p50": statistics.median(ordered),
        "p95": percentile(0.95),
        "p99": percentile(0.99),
        "max": max(ordered),
        "mean": statistics.fmean(ordered),
    }


def _timed_runs(
    factory,
    scale: Scale,
    workspace_id: str,
    provider: CapacityProvider,
) -> dict[str, Any]:
    with factory() as db:
        vector = _query_vector_from_database(
            db, scale, "pdf-text-legacy", "D1"
        )
    query = "raretokenalpha"
    operations = {
        "dense": lambda db: retrieve_content(db, workspace_id, vector, embedding_provider=provider, limit=10),
        "lexical": lambda db: retrieve_lexical_content(db, workspace_id, query, limit=10),
        "hybrid": lambda db: retrieve_query_content(
            db,
            workspace_id,
            query,
            vector,
            embedding_provider=provider,
            limit=10,
            strategy="hybrid",
            candidate_limit=10,
            rrf_constant=60,
        ),
    }
    for _ in range(WARMUP_RUNS):
        with factory() as db:
            operations["hybrid"](db)
    reports = {}
    for name, operation in operations.items():
        values = []
        signature: list[str] | None = None
        drift = 0
        for _ in range(SERIAL_RUNS):
            with factory() as db:
                started = time.perf_counter()
                result = operation(db)
                values.append((time.perf_counter() - started) * 1000)
                current = _location_keys(result)
                if signature is None:
                    signature = current
                elif current != signature:
                    drift += 1
        reports[name] = {"samples": len(values), "latencyMs": _latency_summary(values), "resultCount": len(signature or []), "resultDriftCount": drift}
    return reports


def _concurrency(
    factory,
    scale: Scale,
    workspace_id: str,
    provider: CapacityProvider,
) -> dict[str, Any]:
    query = "raretokenalpha"
    with factory() as db:
        vector = _query_vector_from_database(
            db, scale, "pdf-text-legacy", "D1"
        )
        expected = [
            item.location_key
            for item in retrieve_query_content(
                db, workspace_id, query, vector, embedding_provider=provider,
                limit=10, strategy="hybrid", candidate_limit=10, rrf_constant=60,
            )
        ]
    def run_one() -> tuple[float, list[str]]:
        with factory() as db:
            started = time.perf_counter()
            result = retrieve_query_content(
                db, workspace_id, query, vector, embedding_provider=provider,
                limit=10, strategy="hybrid", candidate_limit=10, rrf_constant=60,
            )
            return (time.perf_counter() - started) * 1000, _location_keys(result)
    values = []
    errors = []
    drift = 0
    wall_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = [executor.submit(run_one) for _ in range(CONCURRENT_RUNS)]
        for future in as_completed(futures):
            try:
                latency, signature = future.result()
            except Exception as error:  # noqa: BLE001 - report all capacity failures
                errors.append(type(error).__name__)
                continue
            values.append(latency)
            if signature != expected:
                drift += 1
    wall_seconds = time.perf_counter() - wall_started
    return {
        "concurrency": CONCURRENCY,
        "requestCount": CONCURRENT_RUNS,
        "completedCount": len(values),
        "errorCount": len(errors),
        "errorTypes": sorted(set(errors)),
        "resultDriftCount": drift,
        "latencyMs": _latency_summary(values) if values else None,
        "wallMs": wall_seconds * 1000,
        "throughputPerSecond": len(values) / wall_seconds if wall_seconds else 0.0,
    }


def _sizes(db: Session) -> dict[str, Any]:
    rows = db.execute(
        text(
            """
            SELECT relname,pg_total_relation_size(oid) AS bytes
            FROM pg_class
            WHERE relname IN (
              'content_units','content_unit_embeddings','evidence_locators',
              'ix_content_unit_embeddings_current_embedding_hnsw',
              'ix_content_unit_embeddings_current_embedding_binary_hnsw',
              'ix_content_units_text_content_fts','ix_content_units_text_content_trgm_gist'
            ) ORDER BY relname
            """
        )
    ).mappings()
    database_bytes = int(db.scalar(text("SELECT pg_database_size(current_database())")))
    database_gib = database_bytes / (1024**3)
    storage_cost = {
        "capturedAt": datetime.now(UTC).isoformat(),
        "provider": "AWS EBS gp3",
        "region": "us-east-1",
        "currency": "USD",
        "sourceUrl": "https://aws.amazon.com/ebs/pricing/",
        "pricePerGiBMonth": 0.08,
        "primaryCopies": 1,
        "replicaCopies": 0,
        "backupCopies": 1,
        "formula": "databaseGiB * pricePerGiBMonth * (primaryCopies + replicaCopies + backupCopies)",
    }
    copy_count = (
        storage_cost["primaryCopies"]
        + storage_cost["replicaCopies"]
        + storage_cost["backupCopies"]
    )
    return {
        "databaseBytes": database_bytes,
        "databaseGiB": database_gib,
        "relations": {row["relname"]: int(row["bytes"]) for row in rows},
        "costAssumption": storage_cost,
        "estimatedStorageUsdPerMonth": database_gib * storage_cost["pricePerGiBMonth"] * copy_count,
        "externalEmbeddingCostUsd": 0.0,
    }


def _cgroup_limits() -> dict[str, Any]:
    cpu_value = Path("/sys/fs/cgroup/cpu.max").read_text().strip().split()
    memory_value = Path("/sys/fs/cgroup/memory.max").read_text().strip()
    cpu_quota = None if cpu_value[0] == "max" else int(cpu_value[0]) / int(cpu_value[1])
    memory_bytes = None if memory_value == "max" else int(memory_value)
    return {"cpuQuota": cpu_quota, "memoryBytes": memory_bytes}


def _environment(db: Session) -> dict[str, Any]:
    names = (
        "server_version",
        "shared_buffers",
        "effective_cache_size",
        "maintenance_work_mem",
        "work_mem",
        "hnsw.iterative_scan",
        "hnsw.ef_search",
        "hnsw.max_scan_tuples",
    )
    values = {name: db.scalar(text(f"SHOW {name}")) for name in names}
    values["vectorVersion"] = db.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
    return {
        "postgres": values,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cpuCountHostVisible": os.cpu_count(),
        "clientCgroup": _cgroup_limits(),
        "resourceContract": {"projectCpu": 4, "projectMemoryGiB": 8, "postgresCpu": 3, "postgresMemoryGiB": 6, "clientCpu": 1, "clientMemoryGiB": 2},
    }


def measure(engine: Engine, scale: Scale) -> dict[str, Any]:
    workspace_id = _target_workspace(scale)
    provider = CapacityProvider()
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    with factory() as db:
        vector_d1 = _query_vector_from_database(
            db, scale, "pdf-text-legacy", "D1"
        )
        vector_d8 = _query_vector_from_database(
            db, scale, "pdf-text-legacy", "D8"
        )
        vector_d64 = _query_vector_from_database(
            db, scale, "pdf-text-legacy", "D64"
        )
        selected_assets = [
            _asset_id(scale, "visible", "pdf-text-legacy"),
            _asset_id(scale, "visible", "image-ocr"),
        ]
        dense_d1 = _dense_ann_statement(workspace_id, None, vector_d1, ann_limit=10)
        dense_d8 = _dense_ann_statement(workspace_id, None, vector_d8, ann_limit=10)
        dense_selected = _dense_ann_statement(
            workspace_id,
            selected_assets,
            vector_d1,
            ann_limit=10,
        )
        latin = _latin_statement(workspace_id, None, "raretokenalpha")
        latin_selected = _latin_statement(workspace_id, selected_assets, "raretokenalpha")
        cjk = _cjk_statement(workspace_id, None, "容量证据")
        first_plans = {
            "denseD1": _plan_summary(_raw_explain(db, dense_d1, limit=10)),
            "denseD8": _plan_summary(_raw_explain(db, dense_d8, limit=10)),
            "latinRare": _plan_summary(_raw_explain(db, latin, limit=10)),
            "cjk": _plan_summary(_raw_explain(db, cjk, limit=10)),
        }
        exact_comparisons = {
            f"{signature}:{profile}": _exact_location_comparison(
                db,
                workspace_id,
                _query_vector_from_database(db, scale, signature, profile),
                provider,
                signature,
                scale in {"s1", "s2"},
            )
            for signature_order, (signature, profile) in enumerate(RECALL_QUERY_CASES, start=1)
        }
        selected_exact_comparison = _exact_location_comparison(
            db,
            workspace_id,
            vector_d1,
            provider,
            "pdf-text-legacy",
            True,
            asset_ids=selected_assets,
        )
        exact_comparisons["selected:pdf-text-legacy:D1"] = selected_exact_comparison
        for _ in range(5):
            db.execute(dense_d1.limit(10)).all()
            db.execute(latin.limit(10)).all()
        warm_plans = {
            "denseD1": _plan_summary(_raw_explain(db, dense_d1, limit=10)),
            "denseD8": _plan_summary(_raw_explain(db, dense_d8, limit=10)),
            "denseSelectedD1": _plan_summary(_raw_explain(db, dense_selected, limit=10)),
            "latinRare": _plan_summary(_raw_explain(db, latin, limit=10)),
            "latinSelectedRare": _plan_summary(_raw_explain(db, latin_selected, limit=10)),
            "cjk": _plan_summary(_raw_explain(db, cjk, limit=10)),
        }
        unique = {
            "D8": _instrument_unique(db, workspace_id, vector_d8),
            "D64": _instrument_unique(db, workspace_id, vector_d64),
        }
        all_results = retrieve_content(db, workspace_id, vector_d1, embedding_provider=provider, limit=10)
        selected_results = retrieve_content(
            db, workspace_id, vector_d1, asset_ids=selected_assets,
            embedding_provider=provider, limit=10,
        )
        lexical_results = retrieve_lexical_content(
            db, workspace_id, "raretokenalpha", limit=10
        )
        lexical_selected_results = retrieve_lexical_content(
            db,
            workspace_id,
            "raretokenalpha",
            asset_ids=selected_assets,
            limit=10,
        )
        scope_checks = {
            "allReadyFull": len(all_results) == 10,
            "selectedFull": len(selected_results) == 10,
            "lexicalAllReadyFull": len(lexical_results) == 10,
            "lexicalSelectedFull": len(lexical_selected_results) == 10,
            "allReadyWorkspace": all(item.asset.workspace_id == workspace_id for item in all_results),
            "selectedAssetsOnly": all(item.asset.id in selected_assets for item in selected_results),
            "lexicalAllReadyWorkspace": all(
                item.asset.workspace_id == workspace_id for item in lexical_results
            ),
            "lexicalSelectedAssetsOnly": all(
                item.asset.id in selected_assets for item in lexical_selected_results
            ),
            "currentChainOnly": all(
                item.locator.processing_generation_snapshot == item.asset.current_processing_generation
                and item.content_unit.index_version == item.asset.current_index_version
                for item in [
                    *all_results,
                    *selected_results,
                    *lexical_results,
                    *lexical_selected_results,
                ]
            ),
        }
        environment = _environment(db)
        storage = _sizes(db)
    serial = _timed_runs(factory, scale, workspace_id, provider)
    concurrent = _concurrency(factory, scale, workspace_id, provider)
    hnsw_index = "ix_content_unit_embeddings_current_embedding_hnsw"
    binary_hnsw_index = "ix_content_unit_embeddings_current_embedding_binary_hnsw"
    fts_index = "ix_content_units_text_content_fts"
    require_ann = scale in {"s1", "s2"}
    gates = {
        "scopeAndCurrentChain": all(scope_checks.values()),
        "hnswPlan": (
            hnsw_index in warm_plans["denseD1"]["indexes"]
            and hnsw_index in warm_plans["denseD8"]["indexes"]
            and hnsw_index in warm_plans["denseSelectedD1"]["indexes"]
        ) if require_ann else True,
        "binaryHnswPlan": (
            binary_hnsw_index in warm_plans["denseD1"]["indexes"]
            and binary_hnsw_index in warm_plans["denseD8"]["indexes"]
            and binary_hnsw_index in warm_plans["denseSelectedD1"]["indexes"]
        ) if require_ann else True,
        "ftsGinPlan": (
            fts_index in warm_plans["latinRare"]["indexes"]
            and fts_index in warm_plans["latinSelectedRare"]["indexes"]
        ) if require_ann else True,
        "hnswRecallAt10": all(
            item["recallAt10"] >= 0.95 for item in exact_comparisons.values()
        ) if require_ann else True,
        "targetedScopeCurrentChain": all(
            all(item["contractChecks"].values())
            for item in exact_comparisons.values()
        ),
        "d8Replenishment": (
            unique["D8"]["roundCount"] <= 4
            and unique["D8"]["cumulativeRankedRows"] <= 150
            and unique["D8"]["resultCount"] == 10
        ),
        "d64Measured": unique["D64"]["resultCount"] == 10,
        "clientResourceLimits": (
            environment["clientCgroup"]["cpuQuota"] == 1.0
            and environment["clientCgroup"]["memoryBytes"] == 2 * 1024**3
        ),
        "noSerialDrift": all(item["resultDriftCount"] == 0 and item["resultCount"] == 10 for item in serial.values()),
        "concurrencyStable": concurrent["errorCount"] == 0 and concurrent["resultDriftCount"] == 0 and concurrent["completedCount"] == CONCURRENT_RUNS,
        "noWarmTempBlocks": all(item["tempReadBlocks"] == 0 and item["tempWrittenBlocks"] == 0 for item in warm_plans.values()),
    }
    if scale == "s2":
        gates.update(
            {
                "denseP95": serial["dense"]["latencyMs"]["p95"] <= 100,
                "lexicalP95": serial["lexical"]["latencyMs"]["p95"] <= 150,
                "hybridP95": serial["hybrid"]["latencyMs"]["p95"] <= 250,
                "concurrentP95": concurrent["latencyMs"]["p95"] <= 400,
                "throughput": concurrent["throughputPerSecond"] >= 20,
                "bufferHitRatio": all(
                    warm_plans[name]["sharedBufferHitRatio"] >= 0.90
                    for name in (
                        "denseD1",
                        "denseSelectedD1",
                        "latinRare",
                        "latinSelectedRare",
                    )
                ),
                "databaseSize": storage["databaseGiB"] <= 12,
            }
        )
    return {
        "schemaVersion": "m403a-measurement-v3",
        "scale": scale,
        "environment": environment,
        "plans": {"firstRunAfterRestart": first_plans, "warm": warm_plans},
        "exactComparisons": exact_comparisons,
        "scopeChecks": scope_checks,
        "uniqueLocation": unique,
        "serial": serial,
        "concurrency": concurrent,
        "storage": storage,
        "gates": gates,
        "queryGatePassed": all(gates.values()),
    }


def main() -> None:
    args = parse_args()
    scale: Scale = args.scale
    engine = create_engine(settings.database_url, pool_size=12, max_overflow=4, future=True)
    try:
        payload = seed(engine, scale) if args.command == "seed" else measure(engine, scale)
    finally:
        engine.dispose()
    _write(payload, args.output)


if __name__ == "__main__":
    main()
