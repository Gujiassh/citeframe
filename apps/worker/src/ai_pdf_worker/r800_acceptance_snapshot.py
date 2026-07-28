"""PostgreSQL relation and MinIO byte snapshots with exact before/after verification."""

from __future__ import annotations

import json
from collections.abc import Callable
from hashlib import sha256

from ai_pdf_api.core.settings import settings
from ai_pdf_api.db.session import SessionLocal
from ai_pdf_api.services.storage import build_storage_client
from minio.error import S3Error
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from ai_pdf_worker.r800_acceptance_common import (
    FIXTURE_RELATIONS,
    RESEARCH_RELATIONS,
    SNAPSHOT_VERSION,
    _fixture_facts,
    _semantic_sha256,
)


def _query_json_rows(db: Session, table_name: str) -> list[object]:
    statement = text(
        f'SELECT to_jsonb(row_data)::text FROM (SELECT * FROM "{table_name}") row_data '
        "ORDER BY to_jsonb(row_data)::text"
    )
    return [json.loads(value) for value in db.scalars(statement)]


def _minio_snapshot() -> list[dict[str, object]]:
    client = build_storage_client()
    try:
        objects = list(client.list_objects(settings.minio_bucket, recursive=True))
    except S3Error as error:
        if error.code in {"NoSuchBucket", "NoSuchKey", "NoSuchObject"}:
            return []
        raise
    rows: list[dict[str, object]] = []
    for item in sorted(objects, key=lambda value: value.object_name or ""):
        object_key = item.object_name
        if not object_key:
            continue
        response = client.get_object(settings.minio_bucket, object_key)
        try:
            payload = response.read()
        finally:
            response.close()
            response.release_conn()
        rows.append(
            {
                "objectKey": object_key,
                "byteSize": len(payload),
                "sha256": sha256(payload).hexdigest(),
            }
        )
    return rows


def snapshot_state(
    session_factory: Callable[[], Session] = SessionLocal,
    *,
    object_snapshot: Callable[[], list[dict[str, object]]] = _minio_snapshot,
) -> dict[str, object]:
    with session_factory() as db:
        existing = set(inspect(db.bind).get_table_names())
        relations = {
            table_name: _query_json_rows(db, table_name)
            for table_name in (*FIXTURE_RELATIONS, *RESEARCH_RELATIONS)
            if table_name in existing
        }
        alembic = _query_json_rows(db, "alembic_version") if "alembic_version" in existing else []
    state = {
        "fixture": _fixture_facts(),
        "alembic": alembic,
        "relations": relations,
        "objects": object_snapshot(),
    }
    return {
        "schemaVersion": SNAPSHOT_VERSION,
        "semanticSha256": _semantic_sha256(state),
        **state,
    }


def verify_snapshots(before: dict[str, object], after: dict[str, object]) -> dict[str, object]:
    mismatches: list[str] = []
    if before.get("schemaVersion") != SNAPSHOT_VERSION:
        mismatches.append("before_schema_version")
    if after.get("schemaVersion") != SNAPSHOT_VERSION:
        mismatches.append("after_schema_version")
    before_semantic = before.get("semanticSha256")
    after_semantic = after.get("semanticSha256")
    if before_semantic != after_semantic:
        mismatches.append("semantic_sha256")
    before_body = {key: value for key, value in before.items() if key != "semanticSha256"}
    after_body = {key: value for key, value in after.items() if key != "semanticSha256"}
    if before_body != after_body:
        mismatches.append("snapshot_payload")
    passed = not mismatches
    verification = {
        "passed": passed,
        "beforeSemanticSha256": before_semantic,
        "afterSemanticSha256": after_semantic,
        "mismatches": mismatches,
    }
    return {
        "schemaVersion": "citeframe-r800-research-verification-v1",
        "passed": passed,
        "verification": verification,
    }
