"""Executable dependency boundaries for the production Worker and offline tools."""

from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
PRODUCT_ROOTS = [
    ROOT / path
    for path in (
        "apps/worker/src",
        "apps/api/src",
        "packages/backend-contracts/src",
        "packages/backend-persistence/src",
        "packages/research-persistence/src",
    )
]


def test_product_has_no_evaluation_imports_including_lazy_or_dynamic_imports() -> None:
    forbidden = ("citeframe_evaluation", "ai_pdf_worker.r800_", "ai_pdf_worker.r803_")
    violations = []
    for source_root in PRODUCT_ROOTS:
        for path in source_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                elif isinstance(node, ast.Call) and (
                    isinstance(node.func, ast.Name)
                    and node.func.id == "__import__"
                    or isinstance(node.func, ast.Attribute)
                    and node.func.attr == "import_module"
                ):
                    modules = [
                        arg.value
                        for arg in node.args
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                    ]
                for module in modules:
                    if module.startswith(forbidden):
                        violations.append(
                            f"{path.relative_to(ROOT)}:{node.lineno}: {module}"
                        )
    assert not violations, "\n".join(violations)


def test_product_flat_namespace_contains_only_process_entry_and_metrics() -> None:
    worker = ROOT / "apps/worker/src/ai_pdf_worker"
    assert {p.name for p in worker.glob("*.py")} == {
        "__init__.py",
        "main.py",
        "metrics.py",
    }
    assert not list(worker.rglob("r800*"))
    assert not list(worker.rglob("r803*"))


def test_production_validation_and_observer_work_when_evaluation_is_unavailable() -> (
    None
):
    code = r"""
import importlib.abc
import sys
class BlockEvaluation(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith('citeframe_evaluation'):
            raise AssertionError('production loaded evaluation: ' + fullname)
sys.meta_path.insert(0, BlockEvaluation())
from ai_pdf_worker.research.agents import GenerationResearchAgents
from citeframe_contracts import ResearchExecutionError
from citeframe_contracts.validation import AgentResultValidationError
from types import SimpleNamespace
lease = SimpleNamespace(step_id='step')
class Generation:
    def prompt(self, node_key):
        return SimpleNamespace(template_text='system', variable_names=(), node_key='researchers', prompt_key='research.researcher')
    def generate(self, lease, *, node_key, messages):
        return self.output
variables = dict(subproblem={}, frozenAssetScope={}, toolContracts={}, resultSchema={})
for raw in ('{invalid', '[]', '{}'):
    for diagnostic in (False, True):
        generation = Generation()
        generation.output = raw
        seen = []
        def validator(node_key, value, **kwargs):
            raise ValueError('invalid role payload')
        agents = GenerationResearchAgents(generation, result_validator=validator, output_observer=lambda *args: seen.append(args), diagnostic_mode=diagnostic)
        expected = AgentResultValidationError if diagnostic and raw != '{}' else ResearchExecutionError
        try:
            agents._json(lease, 'researcher', variables)
        except expected as error:
            assert str(error) == 'researcher_invalid_output'
        else:
            raise AssertionError('invalid output was accepted')
        assert seen == [('researcher', 'step:researcher', raw)]
assert not any(name.startswith('citeframe_evaluation') for name in sys.modules)
print('production-validation-without-evaluation=pass')
"""
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(map(str, PRODUCT_ROOTS)),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "production-validation-without-evaluation=pass" in result.stdout


def test_worker_manifest_never_installs_evaluation() -> None:
    import tomllib

    manifest = tomllib.loads((ROOT / "apps/worker/pyproject.toml").read_text())
    assert not any("evaluation" in name for name in manifest["project"]["dependencies"])
    dockerfile = (ROOT / "infra/docker/Dockerfile.python").read_text()
    product, tooling = dockerfile.split("FROM worker AS evaluation", 1)
    assert "COPY tools/evaluation" not in product
    assert "COPY tools/evaluation" in tooling
