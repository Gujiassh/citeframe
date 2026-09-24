"""Keep dependency diagnostics separate from acceptance CLI JSON output."""
import json
from pathlib import Path
import subprocess
import sys


def test_import_diagnostics_do_not_contaminate_json_stdout():
    code = r'''
import builtins
import importlib
original = builtins.__import__
def noisy_import(name, *args, **kwargs):
    if name == "ai_pdf_api.db.session":
        print("dependency-import-diagnostic")
    return original(name, *args, **kwargs)
builtins.__import__ = noisy_import
cli = importlib.import_module("citeframe_evaluation.acceptance.cli")
cli.snapshot_state = lambda: {"testSnapshot": True}
raise SystemExit(cli.main(["snapshot"]))
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            cwd=Path(__file__).resolve().parents[3], check=True)
    assert json.loads(result.stdout) == {"testSnapshot": True}
    assert "dependency-import-diagnostic" in result.stderr
    assert "dependency-import-diagnostic" not in result.stdout


def test_docker_timeline_query_uses_real_persistence_columns(monkeypatch):
    import re
    import runpy
    from ai_pdf_api.models import ResearchStep, ResearchStepAttempt

    root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(root / "infra/testing"))
    query = runpy.run_path(str(root / "infra/testing/r800_docker_smoke.py"))["ATTEMPT_TIMELINE_QUERY"]
    columns = {"s": set(ResearchStep.__table__.columns.keys()),
               "a": set(ResearchStepAttempt.__table__.columns.keys())}
    references = re.findall(r"\b([a-z])\.([a-z_]+)", query)
    assert references
    for alias, column in references:
        assert alias in columns and column in columns[alias], (alias, column)
