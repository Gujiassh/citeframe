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
