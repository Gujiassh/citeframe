import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session
from alembic.operations import Operations
from alembic.migration import MigrationContext
from citeframe_persistence import Base
from citeframe_persistence.models import WorkflowVersion, PromptVersion
from ai_pdf_api.services.research.research_prompt_provenance import (
    load_v2_release,
    V3_WORKFLOW_VERSION_ID,
    V4_WORKFLOW_VERSION_ID,
)

VERSIONS = Path(__file__).parents[1] / "alembic/versions"
NAMES = [
    "p0d1e2f3a4b5_research_autonomy.py",
    "q1e2f3a4b5c6_research_adaptive_turns.py",
    "r2f3a4b5c6d7_conflict_investigation.py",
]


def prepare(path):
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        for name in ("research_conflict_turns", "research_adaptive_turns"):
            Base.metadata.tables[name].drop(connection)
        with Operations.context(MigrationContext.configure(connection)) as op:
            with op.batch_alter_table("human_decisions") as batch:
                batch.drop_constraint("ck_human_decisions_origin", type_="check")
                batch.drop_constraint(
                    "ck_human_decisions_submitted_fields", type_="check"
                )
                batch.drop_column("decision_origin")
                batch.create_check_constraint(
                    "ck_human_decisions_submitted_fields",
                    "(status = 'submitted' AND decided_by_user_id IS NOT NULL AND action IS NOT NULL AND decided_at IS NOT NULL) OR status <> 'submitted'",
                )
    engine.dispose()


def upgrade(path, names):
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            for name in names:
                spec = importlib.util.spec_from_file_location(
                    "migration", VERSIONS / name
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                module.upgrade()
    engine.dispose()


def release_rows(path):
    engine = create_engine(f"sqlite:///{path}")
    with Session(engine) as db:
        for id in (V3_WORKFLOW_VERSION_ID, V4_WORKFLOW_VERSION_ID):
            load_v2_release(db, workflow_id=id)
        workflows = [
            (r.id, r.version_number, r.manifest_json, r.manifest_sha256)
            for r in db.scalars(select(WorkflowVersion).order_by(WorkflowVersion.id))
        ]
        prompts = [
            (
                r.id,
                r.version_number,
                r.template_text,
                r.template_sha256,
                r.variables_schema_json,
            )
            for r in db.scalars(select(PromptVersion).order_by(PromptVersion.id))
        ]
    columns = {
        name: [
            (c["name"], str(c["type"]), c["nullable"])
            for c in inspect(engine).get_columns(name)
        ]
        for name in (
            "human_decisions",
            "research_conflict_turns",
            "research_adaptive_turns",
        )
    }
    return workflows, prompts, columns


def test_frozen_p0_seed_and_fresh_slice_equal_staged_upgrade_after_process_restart(
    tmp_path, monkeypatch
):
    from ai_pdf_api.services.research import research_versions_service

    monkeypatch.setattr(
        research_versions_service,
        "publish_research_versions_for_release",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("dynamic publisher must not be called")
        ),
    )
    fresh = tmp_path / "fresh.db"
    staged = tmp_path / "staged.db"
    prepare(fresh)
    prepare(staged)
    upgrade(fresh, NAMES)
    upgrade(staged, NAMES[:1])
    code = "import sys;from test_research_conflict_migration import upgrade,NAMES;upgrade(sys.argv[1],NAMES[1:])"
    subprocess.run(
        [sys.executable, "-B", "-c", code, str(staged)],
        cwd=Path(__file__).parent,
        check=True,
        capture_output=True,
    )
    assert release_rows(fresh) == release_rows(staged)
    workflows, prompts, _ = release_rows(staged)
    assert [w[1] for w in workflows] == [3, 4]
    assert sum(p[1] == 3 for p in prompts) == 5 and sum(p[1] == 4 for p in prompts) == 6


def test_historical_v3_seed_is_frozen_against_runtime_default():
    data = json.loads((VERSIONS.parent / "release_data/research_v3.json").read_text())
    assert data["workflowId"] == V3_WORKFLOW_VERSION_ID
    assert data["manifest"]["autonomy"]["conflicts"] == "keep_as_unresolved"
    assert (
        data["manifest"]["autonomy"]["agentResultSchemaVersion"]
        == "research-agent-results-v2"
    )
    assert "investigator" not in data["prompts"]
