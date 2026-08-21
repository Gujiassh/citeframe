import ast
import re
import subprocess
import sys
import tomllib
from dataclasses import asdict
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = API_ROOT.parents[1]
CONTRACTS_ROOT = REPOSITORY_ROOT / "packages/backend-contracts"
CONTRACTS_SRC = CONTRACTS_ROOT / "src"
PERSISTENCE_ROOT = REPOSITORY_ROOT / "packages/backend-persistence"
RESEARCH_PERSISTENCE_ROOT = REPOSITORY_ROOT / "packages/research-persistence"
LOCAL_DISTRIBUTIONS = {"citeframe-backend-contracts", "citeframe-backend-persistence", "citeframe-research-persistence"}
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

    assert not (runtime_dependencies - LOCAL_DISTRIBUTIONS) - deploy_dependencies
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
    }
    lock = (API_ROOT / "uv.lock").read_text(encoding="utf-8")
    assert 'name = "citeframe-backend-contracts"' in lock
    assert 'source = { editable = "../../packages/backend-contracts" }' in lock
    assert 'name = "citeframe-backend-persistence"' in lock
    assert 'source = { editable = "../../packages/backend-persistence" }' in lock
    assert 'name = "citeframe-research-persistence"' in lock
    assert 'source = { editable = "../../packages/research-persistence" }' in lock


def test_contracts_source_is_pure_and_imports_with_only_its_source_path() -> None:
    package_manifest = tomllib.loads((CONTRACTS_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert package_manifest["project"]["dependencies"] == []
    for path in CONTRACTS_SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots = [alias.name.split(".", 1)[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 0, (path, node.lineno)
                imported_roots = [(node.module or "").split(".", 1)[0]]
            else:
                continue
            assert all(root in STDLIB_IMPORT_ROOTS for root in imported_roots), (path, imported_roots)

    code = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import citeframe_contracts
assert Path(citeframe_contracts.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve())
"""
    subprocess.run([sys.executable, "-I", "-c", code, str(CONTRACTS_SRC)], check=True)


def test_contracts_dataclass_defaults_and_serialization_are_representative() -> None:
    sys.path.insert(0, str(CONTRACTS_SRC))
    import citeframe_contracts as contracts

    draft = contracts.PlanSubproblemDraft("question")
    assert draft == contracts.PlanSubproblemDraft("question", (), ())
    assert asdict(draft) == {"question": "question", "asset_ids": (), "expected_evidence": ()}
    claim = contracts.VerifiedClaim("claim-1", "fact", ("evidence-1",), "supported")
    assert claim.conflict_status == "none"
    assert asdict(claim)["conflict_status"] == "none"


def test_a2a_docker_stages_copy_and_expose_all_backend_packages() -> None:
    dockerfile = (REPOSITORY_ROOT / "infra/docker/Dockerfile.python").read_text(encoding="utf-8")
    api_stage = dockerfile.split("FROM python-base AS api\n", 1)[1].split("FROM python-base AS worker\n", 1)[0]
    worker_stage = dockerfile.split("FROM python-base AS worker\n", 1)[1]
    for stage in (api_stage, worker_stage):
        assert "COPY packages/backend-contracts/pyproject.toml /app/packages/backend-contracts/pyproject.toml" in stage
        assert "COPY packages/backend-contracts/src /app/packages/backend-contracts/src" in stage
        assert "COPY packages/backend-persistence/pyproject.toml /app/packages/backend-persistence/pyproject.toml" in stage
        assert "COPY packages/backend-persistence/src /app/packages/backend-persistence/src" in stage
        assert "COPY packages/research-persistence/pyproject.toml /app/packages/research-persistence/pyproject.toml" in stage
        assert "COPY packages/research-persistence/src /app/packages/research-persistence/src" in stage
        assert "citeframe_research_persistence" in stage
        assert "backend-package-import-smoke=pass" in stage
    assert "ENV PYTHONPATH=/app/packages/backend-contracts/src:/app/packages/backend-persistence/src:/app/packages/research-persistence/src:/app/apps/api/src" in api_stage
    assert "ENV PYTHONPATH=/app/packages/backend-contracts/src:/app/packages/backend-persistence/src:/app/packages/research-persistence/src:/app/apps/api/src:/app/apps/worker/src" in worker_stage
    assert "COPY apps/worker /app/apps/worker" not in api_stage
    assert "COPY apps/api /app/apps/api" not in worker_stage
    assert "COPY apps/api/src /app/apps/api/src" in worker_stage


def test_ci_uses_a2a_export_format_and_research_persistence_smokes() -> None:
    ci = (REPOSITORY_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    api_job = ci.split("\n  api:\n", 1)[1].split("\n  worker-fast:\n", 1)[0]
    worker_job = ci.split("\n  worker-fast:\n", 1)[1].split("\n  worker-acceptance:\n", 1)[0]
    assert (
        "uv export --project apps/api --frozen --no-dev --format requirements.txt\n"
        "          --no-emit-project --no-emit-package citeframe-backend-contracts\n"
        "          --no-emit-package citeframe-backend-persistence\n"
        "          --no-emit-package citeframe-research-persistence\n"
        "          --output-file apps/api/requirements.deploy.txt"
    ) in api_job
    assert "--no-emit-package ai-pdf-api" not in api_job
    assert 'import citeframe_contracts, citeframe_persistence, citeframe_research_persistence; print("backend-contracts-persistence-research-import-smoke=pass")' in api_job
    assert (
        "uv export --project apps/worker --frozen --no-dev --format requirements.txt\n"
        "          --no-emit-project --no-emit-package citeframe-backend-contracts\n"
        "          --no-emit-package citeframe-backend-persistence\n"
        "          --no-emit-package citeframe-research-persistence\n"
        "          --no-emit-package ai-pdf-api\n"
        "          --output-file apps/worker/requirements.deploy.txt"
    ) in worker_job
    assert 'import citeframe_contracts, citeframe_persistence, citeframe_research_persistence; print("backend-contracts-persistence-research-import-smoke=pass")' in worker_job
