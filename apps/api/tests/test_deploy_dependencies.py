import ast
import re
import subprocess
import sys
import tomllib
from dataclasses import asdict
from pathlib import Path

import pytest


API_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = API_ROOT.parents[1]
CONTRACTS_ROOT = REPOSITORY_ROOT / "packages/backend-contracts"
CONTRACTS_SRC = CONTRACTS_ROOT / "src"
PERSISTENCE_ROOT = REPOSITORY_ROOT / "packages/backend-persistence"
RESEARCH_PERSISTENCE_ROOT = REPOSITORY_ROOT / "packages/research-persistence"
LOCAL_DISTRIBUTIONS = {
    "citeframe-backend-contracts",
    "citeframe-backend-persistence",
    "citeframe-research-persistence",
    "citeframe-memory-service",
}
STDLIB_IMPORT_ROOTS = set(sys.stdlib_module_names) | {"__future__"}


def _canonicalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_names(path: Path) -> set[str]:
    return {
        _canonicalize_package_name(match.group(1))
        for line in path.read_text(encoding="utf-8").splitlines()
        if (match := re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==", line))
    }


def test_deploy_requirements_include_third_party_runtime_dependencies_only() -> None:
    pyproject = tomllib.loads((API_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    runtime_dependencies = {
        _canonicalize_package_name(re.match(r"[A-Za-z0-9_.-]+", dependency).group())
        for dependency in pyproject["project"]["dependencies"]
    }
    deploy_dependencies = _requirement_names(API_ROOT / "requirements.deploy.txt")

    assert runtime_dependencies - deploy_dependencies == LOCAL_DISTRIBUTIONS
    assert not LOCAL_DISTRIBUTIONS & deploy_dependencies
    requirement_text = (API_ROOT / "requirements.deploy.txt").read_text(encoding="utf-8")
    assert "-e " not in requirement_text
    assert "file:" not in requirement_text
    assert "../" not in requirement_text


def test_persistence_manifest_and_lock_use_only_the_a2a_local_sources() -> None:
    manifest = tomllib.loads((API_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert manifest["tool"]["uv"]["sources"] == {
        "citeframe-backend-contracts": {"path": "../../packages/backend-contracts", "editable": True},
        "citeframe-backend-persistence": {"path": "../../packages/backend-persistence", "editable": True},
        "citeframe-research-persistence": {"path": "../../packages/research-persistence", "editable": True},
        "citeframe-memory-service": {"path": "../../packages/memory-service", "editable": True},
    }
    lock = tomllib.loads((API_ROOT / "uv.lock").read_text(encoding="utf-8"))
    local_lock_sources = {
        package["name"]: package["source"]
        for package in lock["package"]
        if "editable" in package["source"] and package["name"] != manifest["project"]["name"]
    }
    assert local_lock_sources == {
        name: {"editable": source["path"]}
        for name, source in manifest["tool"]["uv"]["sources"].items()
    }


APPROVED_CONTRACT_RELATIVE_IMPORTS = {
    ("citeframe_contracts/__init__.py", 1, "memory"),
    ("citeframe_contracts/history.py", 1, "compaction"),
    ("citeframe_contracts/history.py", 1, "memory"),
}


def _assert_contract_imports(path: Path, source: str) -> None:
    tree = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots = [alias.name.split(".", 1)[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                assert (path.relative_to(CONTRACTS_SRC).as_posix(), node.level, node.module) in (
                    APPROVED_CONTRACT_RELATIVE_IMPORTS
                ), (path, node.lineno)
                continue
            imported_roots = [(node.module or "").split(".", 1)[0]]
        else:
            continue
        assert all(root in STDLIB_IMPORT_ROOTS for root in imported_roots), (path, node.lineno, imported_roots)


def test_contracts_source_is_pure_and_imports_with_only_its_source_path() -> None:
    package_manifest = tomllib.loads((CONTRACTS_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert package_manifest["project"]["dependencies"] == []
    for path in CONTRACTS_SRC.rglob("*.py"):
        _assert_contract_imports(path, path.read_text(encoding="utf-8"))

    code = """
import sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
import citeframe_contracts
import citeframe_contracts.history as history
import citeframe_contracts.compaction as compaction
import citeframe_contracts.memory as memory
for module, relative in (
    (citeframe_contracts, "citeframe_contracts/__init__.py"),
    (history, "citeframe_contracts/history.py"),
    (compaction, "citeframe_contracts/compaction.py"),
    (memory, "citeframe_contracts/memory.py"),
):
    assert Path(module.__file__).resolve() == root / relative
assert history.SourceReference is compaction.SourceReference
assert history.MemoryError is memory.MemoryError
forbidden = {"citeframe_memory", "citeframe_persistence", "citeframe_research_persistence",
             "ai_pdf_api", "ai_pdf_worker", "sqlalchemy", "pydantic", "fastapi"}
assert not forbidden.intersection(name.split(".", 1)[0] for name in sys.modules)
"""
    subprocess.run([sys.executable, "-I", "-S", "-B", "-c", code, str(CONTRACTS_SRC)], check=True)


@pytest.mark.parametrize("origin,source", [
    ("__init__.py", "from .memory import MemoryError"),
    ("history.py", "from .compaction import SourceReference"),
    ("history.py", "from .memory import MemoryError"),
])
def test_contract_relative_import_exact_allowlist(origin: str, source: str) -> None:
    assert APPROVED_CONTRACT_RELATIVE_IMPORTS == {
        ("citeframe_contracts/__init__.py", 1, "memory"),
        ("citeframe_contracts/history.py", 1, "compaction"),
        ("citeframe_contracts/history.py", 1, "memory"),
    }
    _assert_contract_imports(CONTRACTS_SRC / "citeframe_contracts" / origin, source)


@pytest.mark.parametrize("origin,source", [
    ("memory.py", "from .memory import MemoryError"),
    ("__init__.py", "from .compaction import SourceReference"),
    ("history.py", "from ..memory import MemoryError"),
    ("history.py", "from ...memory import MemoryError"),
    ("history.py", "from .unknown import value"),
    ("history.py", "from . import memory"),
    ("history.py", "import citeframe_contracts.memory"),
    ("history.py", "from citeframe_contracts.memory import MemoryError"),
    ("history.py", "import sqlalchemy"),
    ("history.py", "from fastapi import FastAPI"),
    ("history.py", "from ai_pdf_api import models"),
    ("history.py", "import ai_pdf_worker"),
    ("history.py", "import citeframe_persistence"),
    ("history.py", "from citeframe_research_persistence import models"),
    ("history.py", "from citeframe_memory import history"),
    ("history.py", "import json, sqlalchemy"),
])
def test_contract_import_boundary_rejects_unapproved_edges(origin: str, source: str) -> None:
    path = CONTRACTS_SRC / "citeframe_contracts" / origin
    with pytest.raises(AssertionError) as caught:
        _assert_contract_imports(path, source)
    assert path.name in str(caught.value)
    assert ", 1" in str(caught.value)


def test_contracts_dataclass_defaults_and_serialization_are_representative() -> None:
    sys.path.insert(0, str(CONTRACTS_SRC))
    import citeframe_contracts as contracts

    draft = contracts.PlanSubproblemDraft("question")
    assert draft == contracts.PlanSubproblemDraft("question", (), ())
    assert asdict(draft) == {"question": "question", "asset_ids": (), "expected_evidence": ()}
    claim = contracts.VerifiedClaim("claim-1", "fact", ("evidence-1",), "supported")
    assert claim.conflict_status == "none"
    assert asdict(claim)["conflict_status"] == "none"


def _docker_stages(path: Path) -> dict[str, list[str]]:
    stages: dict[str, list[str]] = {}
    current_stage: str | None = None
    logical_line = ""

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        logical_line = f"{logical_line} {stripped}".strip()
        if logical_line.endswith("\\"):
            logical_line = logical_line[:-1].rstrip()
            continue

        from_match = re.fullmatch(r"FROM\s+\S+(?:\s+AS\s+(\S+))?", logical_line, re.IGNORECASE)
        if from_match:
            current_stage = from_match.group(1)
            if current_stage is not None:
                stages[current_stage] = []
        elif current_stage is not None:
            stages[current_stage].append(logical_line)
        logical_line = ""

    assert not logical_line
    return stages


def test_docker_stage_parser_ignores_commented_instructions(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        "FROM python:3.12-slim AS api\n"
        "# COPY packages/backend-contracts/src /app/packages/backend-contracts/src\n",
        encoding="utf-8",
    )

    assert _docker_stages(dockerfile) == {"api": []}


def test_a2a_docker_stages_copy_backend_packages_as_effective_instructions() -> None:
    stages = _docker_stages(REPOSITORY_ROOT / "infra/docker/Dockerfile.python")
    backend_copy_instructions = {
        "COPY packages/backend-contracts/pyproject.toml /app/packages/backend-contracts/pyproject.toml",
        "COPY packages/backend-contracts/src /app/packages/backend-contracts/src",
        "COPY packages/backend-persistence/pyproject.toml /app/packages/backend-persistence/pyproject.toml",
        "COPY packages/backend-persistence/src /app/packages/backend-persistence/src",
        "COPY packages/research-persistence/pyproject.toml /app/packages/research-persistence/pyproject.toml",
        "COPY packages/research-persistence/src /app/packages/research-persistence/src",
        "COPY packages/memory-service/pyproject.toml /app/packages/memory-service/pyproject.toml",
        "COPY packages/memory-service/src /app/packages/memory-service/src",
    }

    for stage in ("api", "worker"):
        assert {line for line in stages[stage] if line.startswith("COPY packages/")} == backend_copy_instructions
    assert (
        "ENV PYTHONPATH=/app/packages/backend-contracts/src:/app/packages/backend-persistence/src:"
        "/app/packages/research-persistence/src:/app/packages/memory-service/src:/app/apps/api/src"
    ) in stages["api"]
    assert (
        "ENV PYTHONPATH=/app/packages/backend-contracts/src:/app/packages/backend-persistence/src:"
        "/app/packages/research-persistence/src:/app/packages/memory-service/src:/app/apps/api/src:/app/apps/worker/src"
    ) in stages["worker"]
    assert "COPY apps/worker /app/apps/worker" not in stages["api"]
    assert "COPY apps/api /app/apps/api" not in stages["worker"]
    assert "COPY apps/api/src /app/apps/api/src" in stages["worker"]
