import re
import tomllib
from pathlib import Path


WORKER_ROOT = Path(__file__).resolve().parents[1]
LOCAL_DISTRIBUTIONS = {"citeframe-backend-contracts", "citeframe-backend-persistence", "citeframe-research-persistence", "ai-pdf-api"}


def _canonicalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def test_worker_deploy_requirements_omit_only_local_distributions() -> None:
    pyproject = tomllib.loads((WORKER_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    runtime_dependencies = {
        _canonicalize_package_name(re.match(r"[A-Za-z0-9_.-]+", dependency).group())
        for dependency in pyproject["project"]["dependencies"]
    }
    deploy_text = (WORKER_ROOT / "requirements.deploy.txt").read_text(encoding="utf-8")
    deploy_dependencies = {
        _canonicalize_package_name(match.group(1))
        for line in deploy_text.splitlines()
        if (match := re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==", line))
    }

    assert not (runtime_dependencies - LOCAL_DISTRIBUTIONS) - deploy_dependencies
    assert not LOCAL_DISTRIBUTIONS & deploy_dependencies
    assert "-e " not in deploy_text
    assert "file:" not in deploy_text
    assert "../" not in deploy_text


def test_worker_persistence_manifest_and_lock_include_research_stage() -> None:
    manifest = tomllib.loads((WORKER_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert manifest["tool"]["uv"]["sources"] == {
        "ai-pdf-api": {"path": "../api", "editable": True},
        "citeframe-backend-contracts": {
            "path": "../../packages/backend-contracts",
            "editable": True,
        },
        "citeframe-backend-persistence": {"path": "../../packages/backend-persistence", "editable": True},
        "citeframe-research-persistence": {"path": "../../packages/research-persistence", "editable": True},
    }
    lock = (WORKER_ROOT / "uv.lock").read_text(encoding="utf-8")
    assert 'source = { editable = "../../packages/backend-contracts" }' in lock
    assert 'name = "citeframe-backend-persistence"' in lock
    assert 'source = { editable = "../../packages/backend-persistence" }' in lock
    assert 'name = "citeframe-research-persistence"' in lock
    assert 'source = { editable = "../../packages/research-persistence" }' in lock
