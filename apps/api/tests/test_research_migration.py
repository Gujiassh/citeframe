from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

import ai_pdf_api.models  # noqa: F401
from ai_pdf_api.db.base import Base
from ai_pdf_api.models import PromptVersion, WorkflowPromptBinding, WorkflowVersion
from ai_pdf_api.services.research_prompt_provenance import (
    V2_PROMPT_SPECS,
    V2_PROMPT_VERSION_IDS,
    V2_WORKFLOW_VERSION_ID,
    prompt_contract_sha256,
    v2_workflow_manifest,
)


def load_migration():
    path = Path(__file__).parents[1] / "alembic/versions/b4d6f8a0c2e4_add_research_ledger.py"
    spec = importlib.util.spec_from_file_location("research_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_prompt_v2_migration():
    path = Path(__file__).parents[1] / "alembic/versions/e8f1a2b3c4d5_add_research_prompt_v2.py"
    spec = importlib.util.spec_from_file_location("research_prompt_v2_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RESEARCH_TABLES = set(load_migration().RESEARCH_TABLES)


def test_research_migration_is_additive_and_empty_downgrade_is_reversible() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            if table.name in RESEARCH_TABLES:
                table.drop(connection)
        before = set(inspect(connection).get_table_names())
        context = MigrationContext.configure(connection)
        migration = load_migration()
        with Operations.context(context):
            migration.upgrade()
        after = set(inspect(connection).get_table_names())
        assert after - before == RESEARCH_TABLES
        assert before <= after
        assert connection.exec_driver_sql("SELECT count(*) FROM workflow_versions").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT count(*) FROM prompt_versions").scalar_one() == 5
        assert connection.exec_driver_sql("SELECT count(*) FROM workflow_prompt_bindings").scalar_one() == 5
        with Operations.context(context):
            migration.downgrade()
        assert set(inspect(connection).get_table_names()) == before


def test_research_migration_refuses_destructive_downgrade_with_data() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            if table.name in RESEARCH_TABLES:
                table.drop(connection)
        context = MigrationContext.configure(connection)
        migration = load_migration()
        with Operations.context(context):
            migration.upgrade()
        connection.exec_driver_sql(
            "INSERT INTO workflow_versions "
            "(id, workflow_key, version_number, availability, manifest_schema_version, manifest_json, "
            "manifest_sha256, created_by_release_id, created_at) VALUES "
            "('00000000-0000-0000-0000-000000000001', 'test', 1, 'active', '1', '{}', "
            "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'test', CURRENT_TIMESTAMP)"
        )
        with (
            pytest.raises(RuntimeError, match="Refusing destructive Research ledger downgrade"),
            Operations.context(context),
        ):
            migration.downgrade()


def test_prompt_v2_migration_is_append_only_and_matches_runtime_contract() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as db:
        v1_workflow = WorkflowVersion(
            id="10000000-0000-4000-8000-000000000001",
            workflow_key="evidence_research",
            version_number=1,
            availability="active",
            manifest_schema_version="1",
            manifest_json={"schemaVersion": 1},
            manifest_sha256="1" * 64,
            created_by_release_id="citeframe-research-v1",
            created_at=now,
        )
        db.add(v1_workflow)
        for index, (node_key, spec) in enumerate(V2_PROMPT_SPECS.items(), start=1):
            prompt = PromptVersion(
                id=f"10000000-0000-4000-8000-0000000001{index:02d}",
                prompt_key=spec.prompt_key,
                version_number=1,
                step_kind=spec.step_kind,
                availability="active",
                template_text=f"legacy {node_key}",
                variables_schema_version="1",
                variables_schema_json={"schemaVersion": 1, "additionalProperties": False},
                template_sha256=str(index) * 64,
                created_by_release_id="citeframe-research-v1",
                created_at=now,
            )
            db.add(prompt)
            db.add(
                WorkflowPromptBinding(
                    workflow_version_id=v1_workflow.id,
                    node_key=node_key,
                    prompt_version_id=prompt.id,
                )
            )
        db.commit()
    migration = load_prompt_v2_migration()
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()
        assert connection.exec_driver_sql("SELECT count(*) FROM workflow_versions").scalar_one() == 2
        assert connection.exec_driver_sql("SELECT count(*) FROM prompt_versions").scalar_one() == 10
        v2_manifest = connection.exec_driver_sql(
            "SELECT manifest_json FROM workflow_versions WHERE id = ?",
            (V2_WORKFLOW_VERSION_ID,),
        ).scalar_one()
        assert __import__("json").loads(v2_manifest) == v2_workflow_manifest()
        rows = connection.exec_driver_sql(
            "SELECT id, prompt_key, template_text, variables_schema_json, template_sha256 "
            "FROM prompt_versions WHERE version_number = 2 ORDER BY id"
        ).all()
        assert [row.id for row in rows] == list(V2_PROMPT_VERSION_IDS.values())
        for row, spec in zip(rows, V2_PROMPT_SPECS.values(), strict=True):
            variables = __import__("json").loads(row.variables_schema_json)
            assert row.prompt_key == spec.prompt_key
            assert row.template_text == spec.template_text
            assert variables == spec.variables_schema
            assert row.template_sha256 == prompt_contract_sha256(row.template_text, variables)
        with Operations.context(context):
            migration.downgrade()
        assert connection.exec_driver_sql("SELECT count(*) FROM workflow_versions").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT count(*) FROM prompt_versions").scalar_one() == 5


@pytest.mark.parametrize(
    ("reference_kind", "table_name", "column_name"),
    [
        ("workflow", table_name, column_name)
        for table_name, column_name in load_prompt_v2_migration().WORKFLOW_REFERENCE_COLUMNS
    ]
    + [
        ("prompt", table_name, column_name)
        for table_name, column_name in load_prompt_v2_migration().PROMPT_REFERENCE_COLUMNS
    ],
)
def test_prompt_v2_migration_refuses_downgrade_for_every_business_reference(
    monkeypatch: pytest.MonkeyPatch,
    reference_kind: str,
    table_name: str,
    column_name: str,
) -> None:
    migration = load_prompt_v2_migration()
    bind = Mock()

    def execute(statement: object, _parameters: object) -> Mock:
        sql = str(statement)
        result = Mock()
        result.scalar_one.return_value = int(table_name in sql and column_name in sql)
        return result

    bind.execute.side_effect = execute
    monkeypatch.setattr(migration.op, "get_bind", lambda: bind)

    with pytest.raises(RuntimeError, match="while business rows reference it"):
        migration.downgrade()

    expected_parameter = "workflow_id" if reference_kind == "workflow" else "prompt_ids"
    assert any(
        table_name in str(call.args[0])
        and column_name in str(call.args[0])
        and expected_parameter in call.args[1]
        for call in bind.execute.call_args_list
    )
    assert not any(str(call.args[0]).lstrip().startswith("DELETE") for call in bind.execute.call_args_list)


def test_alembic_has_one_evolvable_head_after_prompt_v2() -> None:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    assert ScriptDirectory.from_config(config).get_heads() == ["f9a1b2c3d4e5"]
