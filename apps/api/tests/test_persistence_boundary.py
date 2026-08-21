from __future__ import annotations

import ast
import hashlib
import importlib
import json
import subprocess
import sys
import tomllib
from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable


API_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = API_ROOT.parents[1]
API_SRC = API_ROOT / "src"
WORKER_SRC = REPOSITORY_ROOT / "apps/worker/src"
PERSISTENCE_ROOT = REPOSITORY_ROOT / "packages/backend-persistence"
PERSISTENCE_SRC = PERSISTENCE_ROOT / "src"
PERSISTENCE_PACKAGE = PERSISTENCE_SRC / "citeframe_persistence"
SNAPSHOT_PATH = API_ROOT / "tests/fixtures/citeframe-a1b-before-metadata.json"
SNAPSHOT_SHA256 = "678ad54b9977cc6258639b92fa65e5976d032ac323428c98ed89215cf02167af"
STDLIB_IMPORT_ROOTS = set(sys.stdlib_module_names) | {"__future__"}
PERSISTENCE_RUNTIME_IMPORT_ROOTS = STDLIB_IMPORT_ROOTS | {
    "citeframe_persistence",
    "pgvector",
    "sqlalchemy",
}
PERSISTENCE_RUNTIME_DISTRIBUTIONS = {"pgvector", "sqlalchemy"}
FORBIDDEN_RESEARCH_PERSISTENCE_NAMES = (
    "citeframe_research_persistence",
    "citeframe-research-persistence",
    "research-persistence",
)


def _canonicalize_distribution_name(name: str) -> str:
    return name.replace("_", "-").lower()


def _dependency_name(dependency: str) -> str:
    return _canonicalize_distribution_name(
        dependency.split(";", 1)[0]
        .split("[", 1)[0]
        .split(">", 1)[0]
        .split("<", 1)[0]
        .split("=", 1)[0]
        .strip()
    )


def _compiled_postgresql_metadata_snapshot(metadata) -> dict[str, dict[str, dict[str, list[str] | str]]]:
    dialect = postgresql.dialect()
    return {
        "tables": {
            table.name: {
                "create_table": str(CreateTable(table).compile(dialect=dialect)),
                "indexes": [
                    str(CreateIndex(index).compile(dialect=dialect))
                    for index in sorted(table.indexes, key=lambda index: index.name or "")
                ],
            }
            for table in sorted(metadata.sorted_tables, key=lambda table: table.name)
        }
    }


def _config_boundary_paths() -> list[Path]:
    paths: set[Path] = set()
    for pattern in (
        "**/pyproject.toml",
        "**/uv.lock",
        "**/requirements*.txt",
        "**/package.json",
        "**/pnpm-lock.yaml",
        ".github/workflows/*.yml",
        ".github/workflows/*.yaml",
        "infra/docker/Dockerfile*",
        "infra/docker/compose*.yml",
        "infra/docker/compose*.yaml",
    ):
        paths.update(REPOSITORY_ROOT.glob(pattern))
    return sorted(path for path in paths if path.is_file())


def test_legacy_and_neutral_persistence_exports_are_same_objects() -> None:
    import ai_pdf_api.db.base as legacy_base_module
    import ai_pdf_api.models as legacy_models
    import citeframe_persistence
    import citeframe_persistence.base as neutral_base_module
    import citeframe_persistence.models as neutral_models

    assert legacy_base_module.Base is citeframe_persistence.Base is neutral_base_module.Base
    assert legacy_base_module.Base.metadata is citeframe_persistence.Base.metadata
    assert legacy_models.__all__ == neutral_models.__all__

    for name in neutral_models.__all__:
        assert getattr(legacy_models, name) is getattr(neutral_models, name)
        assert getattr(citeframe_persistence, name) is getattr(neutral_models, name)

    for path in sorted((API_SRC / "ai_pdf_api/models").glob("*.py")):
        if path.name == "__init__.py":
            continue
        module_name = path.stem
        legacy_submodule = importlib.import_module(f"ai_pdf_api.models.{module_name}")
        neutral_submodule = importlib.import_module(f"citeframe_persistence.models.{module_name}")
        assert legacy_submodule is neutral_submodule, module_name


def test_persistence_models_share_one_metadata_object_and_match_snapshot() -> None:
    import ai_pdf_api.db.base as legacy_base_module
    import ai_pdf_api.models as legacy_models
    import citeframe_persistence
    import citeframe_persistence.models as neutral_models

    assert SNAPSHOT_PATH.is_file()
    snapshot_bytes = SNAPSHOT_PATH.read_bytes()
    assert hashlib.sha256(snapshot_bytes).hexdigest() == SNAPSHOT_SHA256

    metadata = citeframe_persistence.Base.metadata
    assert metadata is legacy_base_module.Base.metadata
    assert metadata is neutral_models.Asset.metadata
    assert metadata is legacy_models.Asset.metadata

    model_metadata = {
        getattr(neutral_models, name).__table__.metadata
        for name in neutral_models.__all__
        if hasattr(getattr(neutral_models, name), "__table__")
    }
    assert model_metadata == {metadata}

    actual = _compiled_postgresql_metadata_snapshot(metadata)
    assert len(actual["tables"]) == 80
    assert sum(len(table["indexes"]) for table in actual["tables"].values()) == 93
    assert actual == json.loads(snapshot_bytes)


def test_neutral_persistence_imports_without_api_or_worker_paths() -> None:
    code = """
import sys
from pathlib import Path

persistence_src = Path(sys.argv[1]).resolve()
api_src = Path(sys.argv[2]).resolve()
worker_src = Path(sys.argv[3]).resolve()

def keep_path(entry: str) -> bool:
    if not entry:
        return True
    try:
        resolved = Path(entry).resolve()
    except OSError:
        return True
    return resolved not in {persistence_src, api_src, worker_src}

sys.path = [str(persistence_src), *[entry for entry in sys.path if keep_path(entry)]]
assert str(api_src) not in sys.path
assert str(worker_src) not in sys.path

import citeframe_persistence
import citeframe_persistence.models.asset

package_file = Path(citeframe_persistence.__file__).resolve()
assert package_file.is_relative_to(persistence_src), package_file
assert len(citeframe_persistence.Base.metadata.tables) == 80
assert not any(name == "ai_pdf_api" or name.startswith("ai_pdf_api.") for name in sys.modules)
assert not any(name == "ai_pdf_worker" or name.startswith("ai_pdf_worker.") for name in sys.modules)
"""
    subprocess.run(
        [sys.executable, "-I", "-c", code, str(PERSISTENCE_SRC), str(API_SRC), str(WORKER_SRC)],
        check=True,
    )


def test_persistence_package_runtime_dependencies_and_imports_stay_allowlisted() -> None:
    manifest = tomllib.loads((PERSISTENCE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    runtime_dependencies = {
        _dependency_name(dependency)
        for dependency in manifest["project"].get("dependencies", [])
    }
    assert runtime_dependencies == PERSISTENCE_RUNTIME_DISTRIBUTIONS

    for path in sorted(PERSISTENCE_PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots = [alias.name.split(".", 1)[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    continue
                imported_roots = [(node.module or "").split(".", 1)[0]]
            else:
                continue
            disallowed = [root for root in imported_roots if root not in PERSISTENCE_RUNTIME_IMPORT_ROOTS]
            assert not disallowed, (path, node.lineno, disallowed)


def test_research_persistence_package_is_declared_at_a2a_boundaries() -> None:
    package_manifest = tomllib.loads((REPOSITORY_ROOT / "packages/research-persistence/pyproject.toml").read_text(encoding="utf-8"))
    assert package_manifest["project"]["name"] == "citeframe-research-persistence"
    for project in (REPOSITORY_ROOT / "apps/api/pyproject.toml", REPOSITORY_ROOT / "apps/worker/pyproject.toml"):
        manifest = tomllib.loads(project.read_text(encoding="utf-8"))
        assert "citeframe-research-persistence" in manifest["project"]["dependencies"]
        assert manifest["tool"]["uv"]["sources"]["citeframe-research-persistence"] == {
            "path": "../../packages/research-persistence", "editable": True
        }

def test_alembic_env_loads_neutral_persistence_metadata_directly() -> None:
    env_source = (API_ROOT / "alembic/env.py").read_text(encoding="utf-8")

    assert "from citeframe_persistence import Base" in env_source
    assert "import citeframe_persistence.models" in env_source
    assert "from ai_pdf_api.db.base import Base" not in env_source
    assert "import ai_pdf_api.models" not in env_source

