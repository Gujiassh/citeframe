from __future__ import annotations

import hashlib
import importlib.util
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import citeframe_persistence.models  # noqa: F401
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from citeframe_persistence import Base
from citeframe_persistence.models import ResearchPublicationIntent
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.exc import IntegrityError

MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "alembic/versions/n8b9c0d1e2f3_add_research_publication_intents.py"
)
TABLE_NAME = "research_publication_intents"
MAX_PAYLOAD_BYTES = 16 * 1024 * 1024


def load_migration():
    spec = importlib.util.spec_from_file_location("research_publication_intent_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _upgrade(connection: Connection) -> None:
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        load_migration().upgrade()


def _downgrade(connection: Connection) -> None:
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        load_migration().downgrade()


def _assert_schema(connection: Connection, *, postgres: bool) -> None:
    inspector = inspect(connection)
    columns = {column["name"]: column for column in inspector.get_columns(TABLE_NAME)}
    assert set(columns) == set(ResearchPublicationIntent.__table__.columns.keys())
    assert columns["payload_bytes"]["type"].__class__.__name__.upper() == (
        "BYTEA" if postgres else "BLOB"
    )
    assert columns["selection_json"]["type"].__class__.__name__.upper() == (
        "JSONB" if postgres else "JSON"
    )

    foreign_keys = {
        (tuple(foreign_key["constrained_columns"]), foreign_key["referred_table"])
        for foreign_key in inspector.get_foreign_keys(TABLE_NAME)
    }
    assert foreign_keys == {
        (("workspace_id",), "workspaces"),
        (("run_id",), "research_runs"),
        (("step_id",), "research_steps"),
        (("attempt_id",), "research_step_attempts"),
        (("execution_snapshot_id",), "research_execution_snapshots"),
        (("committed_artifact_id",), "research_artifacts"),
    }

    checks = {constraint["name"]: constraint["sqltext"] for constraint in inspector.get_check_constraints(TABLE_NAME)}
    assert set(checks) == {
        constraint.name
        for constraint in ResearchPublicationIntent.__table__.constraints
        if constraint.__class__.__name__ == "CheckConstraint"
    }
    payload_check = checks["ck_research_publication_intents_payload_size"].lower()
    assert "16777216" in payload_check
    assert "length(payload_bytes)" in payload_check

    indexes = {index["name"]: index for index in inspector.get_indexes(TABLE_NAME)}
    assert {
        "ix_research_publication_intents_run",
        "ix_research_publication_intents_schedule",
        "ix_research_publication_intents_step",
        "uq_research_publication_intents_active_run_key",
    }.issubset(indexes)
    partial = indexes["uq_research_publication_intents_active_run_key"]
    assert bool(partial["unique"])
    where = str(
        partial.get("dialect_options", {}).get(
            "postgresql_where" if postgres else "sqlite_where", ""
        )
    ).lower()
    assert "status" in where and "absent" in where


def test_publication_intent_migration_upgrades_and_downgrades_sqlite() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        ResearchPublicationIntent.__table__.drop(connection)
        assert TABLE_NAME not in inspect(connection).get_table_names()
        _upgrade(connection)
        _assert_schema(connection, postgres=False)
        connection.execute(
            ResearchPublicationIntent.__table__.insert().values(**_intent_values(b"durable"))
        )
        with pytest.raises(RuntimeError, match="Refusing destructive publication-intent downgrade"):
            _downgrade(connection)
        assert TABLE_NAME in inspect(connection).get_table_names()
        connection.execute(ResearchPublicationIntent.__table__.delete())
        _downgrade(connection)
        assert TABLE_NAME not in inspect(connection).get_table_names()


def _intent_values(payload: bytes, *, run_id: str | None = None) -> dict[str, object]:
    now = datetime.now(UTC)
    digest = hashlib.sha256(payload).hexdigest()
    return {
        "id": str(uuid4()),
        "workspace_id": str(uuid4()),
        "run_id": run_id or str(uuid4()),
        "step_id": str(uuid4()),
        "attempt_id": str(uuid4()),
        "execution_snapshot_id": str(uuid4()),
        "logical_key": "final-report",
        "artifact_id": str(uuid4()),
        "committed_artifact_id": None,
        "object_prefix": f"research/test/{uuid4()}",
        "current_object_generation": None,
        "current_object_key": None,
        "adopted_object_generation": None,
        "adopted_object_key": None,
        "content_type": "text/markdown",
        "render_schema_version": "final-report-v1",
        "payload_bytes": payload,
        "byte_size": len(payload),
        "content_sha256": digest,
        "selection_json": {"factClaimIds": [], "unresolvedClaimIds": []},
        "selection_sha256": digest,
        "status": "prepared",
        "state_version": 1,
        "claim_generation": 0,
        "claim_owner": None,
        "claim_token_hash": None,
        "claim_expires_at": None,
        "claim_heartbeat_at": None,
        "next_reconcile_at": now,
        "reconcile_attempt_count": 0,
        "last_error_code": None,
        "created_at": now,
        "updated_at": now,
        "resolved_at": None,
        "orphan_sweep_after": None,
    }


def _committed_intent_values(payload: bytes) -> dict[str, object]:
    values = _intent_values(payload)
    values.update(
        status="committed",
        committed_artifact_id=values["artifact_id"],
        adopted_object_generation=1,
        adopted_object_key=f"{values['object_prefix']}/publication/1/final.md",
        resolved_at=values["updated_at"],
        orphan_sweep_after=values["updated_at"],
    )
    return values


def test_publication_intent_sqlite_enforces_payload_length_limit_and_partial_unique() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    table = ResearchPublicationIntent.__table__
    run_id = str(uuid4())
    with engine.connect() as connection:
        boundary = _intent_values(b"x" * MAX_PAYLOAD_BYTES, run_id=run_id)
        connection.execute(table.insert().values(**boundary))
        assert connection.scalar(
            select(table.c.byte_size).where(table.c.id == boundary["id"])
        ) == MAX_PAYLOAD_BYTES
        connection.execute(table.delete())

        too_large = _intent_values(b"x" * (MAX_PAYLOAD_BYTES + 1))
        with pytest.raises(IntegrityError):
            connection.execute(table.insert().values(**too_large))
        connection.rollback()

        wrong_length = _intent_values(b"payload")
        wrong_length["byte_size"] = len(b"payload") - 1
        with pytest.raises(IntegrityError):
            connection.execute(table.insert().values(**wrong_length))
        connection.rollback()

        non_hex = _intent_values(b"payload")
        non_hex["content_sha256"] = "g" * 64
        with pytest.raises(IntegrityError):
            connection.execute(table.insert().values(**non_hex))
        connection.rollback()

        uppercase = _intent_values(b"payload")
        uppercase["selection_sha256"] = "A" * 64
        with pytest.raises(IntegrityError):
            connection.execute(table.insert().values(**uppercase))
        connection.rollback()

        invalid_adopted_generation = _committed_intent_values(b"payload")
        invalid_adopted_generation["adopted_object_generation"] = 0
        with pytest.raises(IntegrityError):
            connection.execute(table.insert().values(**invalid_adopted_generation))
        connection.rollback()

        terminal_without_sweep = _committed_intent_values(b"payload")
        terminal_without_sweep["orphan_sweep_after"] = None
        with pytest.raises(IntegrityError):
            connection.execute(table.insert().values(**terminal_without_sweep))
        connection.rollback()

        first = _intent_values(b"first", run_id=run_id)
        second = _intent_values(b"second", run_id=run_id)
        connection.execute(table.insert().values(**first))
        with pytest.raises(IntegrityError):
            connection.execute(table.insert().values(**second))


@contextmanager
def _temporary_postgresql_database(base_url: str):
    url = make_url(base_url)
    if not url.drivername.startswith("postgresql"):
        pytest.skip("CITEFRAME_TEST_POSTGRES_URL must use PostgreSQL")
    database = f"citeframe_publication_migration_{uuid4().hex}"
    admin_url = url.set(database="postgres")
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    engine: Engine | None = None
    try:
        with admin.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{database}"')
        engine = create_engine(url.set(database=database))
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        with admin.connect() as connection:
            connection.exec_driver_sql(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (database,),
            )
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database}"')
        admin.dispose()


def test_publication_intent_migration_upgrades_and_downgrades_real_postgresql() -> None:
    base_url = os.environ.get("CITEFRAME_TEST_POSTGRES_URL")
    if base_url is None:
        pytest.skip("set CITEFRAME_TEST_POSTGRES_URL to run the real PostgreSQL migration gate")
    with _temporary_postgresql_database(base_url) as engine:
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            ResearchPublicationIntent.__table__.drop(connection)
            _upgrade(connection)
            _assert_schema(connection, postgres=True)
            connection.exec_driver_sql("SET session_replication_role = 'replica'")
            connection.execute(
                ResearchPublicationIntent.__table__.insert().values(
                    **_intent_values(b"durable")
                )
            )
            connection.exec_driver_sql("SET session_replication_role = 'origin'")
            with pytest.raises(
                RuntimeError,
                match="Refusing destructive publication-intent downgrade",
            ):
                _downgrade(connection)
            assert TABLE_NAME in inspect(connection).get_table_names()
            connection.execute(ResearchPublicationIntent.__table__.delete())
            _downgrade(connection)
            assert TABLE_NAME not in inspect(connection).get_table_names()
