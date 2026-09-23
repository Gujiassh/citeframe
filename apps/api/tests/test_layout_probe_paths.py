"""The historical A2a oracle still runs against its original flat module layout."""
import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_baseline_probe_rebinding_is_limited_to_import_paths(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "infra/scripts"))
    spec = importlib.util.spec_from_file_location("layout_differential_runner", ROOT / "infra/scripts/run-a2a-differential.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    source = (ROOT / "apps/api/tests/test_a2a_differential_probe.py").read_text(encoding="utf-8")
    historical = runner._historical_probe_source(source)
    assert "from ai_pdf_worker.r800_acceptance_fixture import seed_state" in historical
    assert "import ai_pdf_worker.research_runtime" in historical
    assert "citeframe_evaluation" not in historical
    assert "ai_pdf_worker.research." not in historical
    def without_imports(text):
        class RemoveImports(ast.NodeTransformer):
            def visit_Import(self, node):
                return None
            def visit_ImportFrom(self, node):
                return None
        return ast.dump(RemoveImports().visit(ast.parse(text)), include_attributes=False)
    assert without_imports(source) == without_imports(historical)
