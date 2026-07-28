from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from ai_pdf_api.db.base import Base
import ai_pdf_api.models  # noqa: F401


def load_migration():
    path = Path(__file__).parents[1] / "alembic/versions/c5e7a9b1d3f6_add_research_evaluation_ledger.py"
    spec = importlib.util.spec_from_file_location("evaluation_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = load_migration()
EVALUATION_TABLES = set(MIGRATION.EVALUATION_TABLES)


def _without_evaluation_tables(connection) -> set[str]:
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in EVALUATION_TABLES:
            table.drop(connection)
    return set(inspect(connection).get_table_names())


def _upgrade(connection):
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        MIGRATION.upgrade()
    return context


def test_evaluation_migration_upgrade_and_empty_downgrade_are_reversible() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        before = _without_evaluation_tables(connection)
        context = _upgrade(connection)
        inspector = inspect(connection)
        after = set(inspector.get_table_names())

        assert after - before == EVALUATION_TABLES
        for table_name in EVALUATION_TABLES:
            model_table = Base.metadata.tables[table_name]
            actual_columns = {
                column["name"]: (str(column["type"]), column["nullable"])
                for column in inspector.get_columns(table_name)
            }
            expected_columns = {
                column.name: (str(column.type), column.nullable) for column in model_table.columns
            }
            assert actual_columns == expected_columns
            assert {constraint["name"] for constraint in inspector.get_check_constraints(table_name)} == {
                constraint.name
                for constraint in model_table.constraints
                if constraint.__class__.__name__ == "CheckConstraint"
            }
            assert {constraint["name"] for constraint in inspector.get_unique_constraints(table_name)} == {
                constraint.name
                for constraint in model_table.constraints
                if constraint.__class__.__name__ == "UniqueConstraint"
            }
            actual_foreign_keys = {
                (
                    tuple(foreign_key["constrained_columns"]),
                    foreign_key["referred_table"],
                    tuple(foreign_key["referred_columns"]),
                )
                for foreign_key in inspector.get_foreign_keys(table_name)
            }
            expected_foreign_keys = {
                (
                    tuple(element.parent.name for element in constraint.elements),
                    next(iter(constraint.elements)).column.table.name,
                    tuple(element.column.name for element in constraint.elements),
                )
                for constraint in model_table.foreign_key_constraints
            }
            assert actual_foreign_keys == expected_foreign_keys
            actual_indexes = {
                index["name"]: tuple(index["column_names"])
                for index in inspector.get_indexes(table_name)
            }
            expected_indexes = {
                index.name: tuple(column.name for column in index.columns) for index in model_table.indexes
            }
            assert actual_indexes == expected_indexes
        with Operations.context(context):
            MIGRATION.downgrade()
        assert set(inspect(connection).get_table_names()) == before
    engine.dispose()


def test_evaluation_migration_refuses_downgrade_with_any_persisted_data() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        _without_evaluation_tables(connection)
        context = _upgrade(connection)
        connection.exec_driver_sql(
            "INSERT INTO research_evaluation_suites "
            "(id, suite_key, version, title, fixture_manifest_sha256, scorer_version, case_count, created_at) "
            "VALUES ('10000000-0000-4000-8000-000000000001', 'test-suite', 1, 'Test suite', "
            "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'scorer-v1', 0, "
            "CURRENT_TIMESTAMP)"
        )
        with pytest.raises(RuntimeError, match="Refusing destructive Research Evaluation downgrade"):
            with Operations.context(context):
                MIGRATION.downgrade()
        assert EVALUATION_TABLES <= set(inspect(connection).get_table_names())
    engine.dispose()


def test_postgresql_append_only_trigger_definitions_cover_every_table_and_operation() -> None:
    install = MIGRATION.append_only_install_statements()
    remove = MIGRATION.append_only_remove_statements()

    assert len(install) == len(EVALUATION_TABLES) + 1
    assert "RETURNS trigger" in install[0]
    assert "RAISE EXCEPTION 'research evaluation tables are append-only'" in install[0]
    assert "LANGUAGE plpgsql" in install[0]
    for table_name in MIGRATION.EVALUATION_TABLES:
        matching = [statement for statement in install[1:] if f" ON {table_name} " in statement]
        assert len(matching) == 1
        assert "BEFORE UPDATE OR DELETE" in matching[0]
        assert f"EXECUTE FUNCTION {MIGRATION.APPEND_ONLY_FUNCTION_NAME}()" in matching[0]
        assert any(f" ON {table_name}" in statement for statement in remove[:-1])
    assert remove[-1] == f"DROP FUNCTION IF EXISTS {MIGRATION.APPEND_ONLY_FUNCTION_NAME}()"
