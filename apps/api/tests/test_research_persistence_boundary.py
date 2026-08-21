from __future__ import annotations

import ast
import hashlib
import json
import json
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = ROOT / "packages/research-persistence"
PACKAGE_SRC = PACKAGE_ROOT / "src"
PACKAGE = PACKAGE_SRC / "citeframe_research_persistence"
GOLDEN = Path(__file__).resolve().parent / "fixtures/citeframe-a2a-research-golden.json"
GOLDEN_SHA256 = "dcfbe21ba4e36774ea76b8f114b6f3d0650ece2e237aea3a59ad7f6ccddcaae3"
ALLOWED_ROOTS = set(sys.stdlib_module_names) | {"__future__", "sqlalchemy", "citeframe_contracts", "citeframe_persistence", "citeframe_research_persistence"}


def test_research_persistence_manifest_has_only_neutral_dependencies() -> None:
    manifest = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert set(manifest["project"]["dependencies"]) == {
        "SQLAlchemy>=2.0,<3.0", "citeframe-backend-contracts", "citeframe-backend-persistence"
    }


def test_research_persistence_source_imports_only_allowlisted_roots() -> None:
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".", 1)[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                roots = [(node.module or "").split(".", 1)[0]]
            else:
                continue
            assert set(roots) <= ALLOWED_ROOTS, (path, node.lineno, roots)


def test_research_persistence_imports_without_api_or_worker_paths() -> None:
    code = """
import sys
from pathlib import Path
package_src, persistence_src, contracts_src, api_src, worker_src = map(Path, sys.argv[1:])
original_path = sys.path[:]
sys.path = [str(package_src), str(persistence_src), str(contracts_src), *original_path]
import citeframe_research_persistence as research
assert Path(research.__file__).resolve().is_relative_to(package_src.resolve())
assert not any(name == 'ai_pdf_api' or name.startswith('ai_pdf_api.') for name in sys.modules)
assert not any(name == 'ai_pdf_worker' or name.startswith('ai_pdf_worker.') for name in sys.modules)
assert not Path(research.__file__).resolve().is_relative_to(api_src.resolve())
assert not Path(research.__file__).resolve().is_relative_to(worker_src.resolve())
"""
    subprocess.run([sys.executable, "-I", "-c", code, str(PACKAGE_SRC), str(ROOT / "packages/backend-persistence/src"), str(ROOT / "packages/backend-contracts/src"), str(ROOT / "apps/api/src"), str(ROOT / "apps/worker/src")], check=True)


def test_api_and_worker_compatibility_surface_uses_neutral_commands() -> None:
    from ai_pdf_api.services import research_worker
    import citeframe_research_persistence as research

    assert research_worker.claim_next_research_step is research.claim_next_research_step
    assert research_worker.complete_research_step is research.complete_research_step
    assert research_worker.heartbeat_research_step is research.heartbeat_research_step
    assert research_worker.fail_research_step is research.fail_research_step


def test_research_persistence_golden_fixture_is_immutable_and_complete() -> None:
    payload = GOLDEN.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == GOLDEN_SHA256
    fixture = json.loads(payload)
    assert fixture["schemaVersion"] == "a2a-research-persistence-golden-v1"
    assert fixture["runtimeInvariant"] == "fixed-langgraph-multi-step-process-one"
    assert {case["name"] for case in fixture["cases"]} == {"multi_step_process_one", "retry_cancel_reclaim_recovery"}
    for case in fixture["cases"]:
        assert case["dbRows"]
        assert case["payloads"]
        assert case["events"]
