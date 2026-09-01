from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "infra/scripts/run-a2a-differential.py"


def test_a2a_executable_differential_oracle(tmp_path: Path) -> None:
    outer = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            (
                "import importlib.util; "
                "print('present' if importlib.util.find_spec('langgraph') else 'absent')"
            ),
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    assert outer.stdout.strip() == "absent", (sys.executable, outer.stdout)

    report = tmp_path / "a2a-differential.json"
    completed = subprocess.run(
        [sys.executable, str(RUNNER), "--root", str(ROOT), "--output", str(report)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=660,
    )
    assert completed.returncode == 0, completed.stdout
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["equal"] is True
    assert payload["baselineRef"] == "d1b5945e977445e4db6bf56ef54cf61607ead2e2"
    assert len(payload["candidateSemanticWorktreeSha256"]) == 64
    assert len(payload["repairSnapshotSha256"]) == 64
    assert payload["probeExecution"] == "uv-worker-frozen-exact"
    for name in ("baselineWorkerEnvironment", "candidateWorkerEnvironment"):
        environment = payload[name]
        prefix = Path(environment["pythonPrefix"]).absolute()
        assert Path(environment["pythonExecutable"]).absolute().is_relative_to(prefix)
        assert Path(environment["langgraphModule"]).absolute().is_relative_to(prefix)
        assert prefix != Path(sys.prefix).absolute()
    candidate_environment = payload["candidateWorkerEnvironment"]
    expected_worker_root = (ROOT / "apps/worker").absolute()
    assert Path(candidate_environment["pythonPrefix"]).absolute() == (
        expected_worker_root / ".venv"
    )
    assert Path(candidate_environment["workerModule"]).absolute().is_relative_to(
        expected_worker_root / "src"
    )
    assert payload["baselineComposition"] == {
        "commandModule": "ai_pdf_api.services.research.research_worker_lease",
        "kind": "baseline-api-research-worker",
        "uowEnterCount": 0,
    }
    candidate_composition = payload["candidateComposition"]
    assert candidate_composition["kind"] == "candidate-neutral-research-uow"
    assert candidate_composition["commandModule"].startswith(
        "citeframe_research_persistence"
    )
    assert candidate_composition["uowEnterCount"] > 0
    assert payload["baseline"] == payload["candidate"]
    assert set(payload["coverage"]) == {
        "normalizedDbRows",
        "exactPayloadBytes",
        "exactEventBytes",
        "leaseFencing",
        "retryCancelReclaimRecovery",
        "permission",
        "terminalProcessSemantics",
    }

    semantics = payload["candidate"]
    assert set(semantics["normalizedDbRows"]) == {"transitions", "processOne"}
    assert len(semantics["exactEventBytes"]["transitions"]) >= 15
    assert len(semantics["exactEventBytes"]["processOne"]) >= 40
    assert set(semantics["exactPayloadBytes"]["processOne"]) == {
        "apiResponses",
        "objectPayloads",
    }
    assert payload["schedulerDelta"]["allowed"] is True
    assert payload["schedulerDelta"]["baseline"]["processOneOutputs"] == [
        True,
        True,
        True,
        False,
    ]
    assert payload["schedulerDelta"]["candidate"]["processOneOutputs"] == [
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        False,
    ]
    assert semantics["terminalProcessSemantics"]["idleAfterTerminal"] is False
    assert semantics["terminalProcessSemantics"]["runStatus"] == "completed"

    rows = semantics["normalizedDbRows"]
    assert len(rows["transitions"]) == 29
    assert len(rows["processOne"]) == 29
    assert len(rows["transitions"]["research_step_retry_requests"]) == 1
    assert len(rows["transitions"]["research_idempotency_records"]) >= 4
    assert len(rows["processOne"]["research_idempotency_records"]) == 3
    serialized_rows = json.dumps(rows, ensure_ascii=True, sort_keys=True)
    assert "<process-worker-instance-id>" in serialized_rows
    assert "worker-a" in serialized_rows
    assert "worker-retry-2" in serialized_rows
    assert "<datetime>" not in serialized_rows
    assert "<sha256>" not in serialized_rows


def test_candidate_api_facade_composition_mutation_fails_closed() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--root",
            str(ROOT),
            "--candidate-mutation",
            "candidate-api-facade",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=360,
    )
    assert completed.returncode == 2, completed.stdout
    assert "candidate probe failed" in completed.stdout
    assert "must not use API research_worker facade" in completed.stdout


def _pollution_wheel(tmp_path: Path) -> Path:
    import zipfile

    wheel = tmp_path / "citeframe_a2a_pollution-0.0.1-py3-none-any.whl"
    module = """\
import os
from pathlib import Path


def pytest_configure(config):
    del config
    sentinel = os.environ.get("A2A_POLLUTION_SENTINEL")
    if sentinel:
        Path(sentinel).write_text("loaded\\n", encoding="utf-8")
"""
    metadata = """\
Metadata-Version: 2.1
Name: citeframe-a2a-pollution
Version: 0.0.1
"""
    wheel_metadata = """\
Wheel-Version: 1.0
Generator: citeframe-a2a-differential-test
Root-Is-Purelib: true
Tag: py3-none-any
"""
    entries = """\
[pytest11]
citeframe_a2a_pollution = citeframe_a2a_pollution
"""
    files = {
        "citeframe_a2a_pollution.py": module,
        "citeframe_a2a_pollution-0.0.1.dist-info/METADATA": metadata,
        "citeframe_a2a_pollution-0.0.1.dist-info/WHEEL": wheel_metadata,
        "citeframe_a2a_pollution-0.0.1.dist-info/entry_points.txt": entries,
    }
    record_path = "citeframe_a2a_pollution-0.0.1.dist-info/RECORD"
    files[record_path] = "".join(f"{name},,\n" for name in (*files, record_path))
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return wheel


def test_exact_worker_sync_removes_real_pytest_plugin_pollution(tmp_path: Path) -> None:
    import os
    import shutil

    uv_value = shutil.which("uv")
    assert uv_value is not None
    worker_project = ROOT / "apps/worker"
    worker_python = worker_project / (
        ".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python"
    )
    uv_env = os.environ.copy()
    for inherited in (
        "PYTEST_ADDOPTS",
        "PYTEST_PLUGINS",
        "UV_INEXACT",
        "UV_NO_SYNC",
        "UV_PROJECT_ENVIRONMENT",
        "VIRTUAL_ENV",
    ):
        uv_env.pop(inherited, None)
    exact_command = [
        uv_value,
        "run",
        "--project",
        str(worker_project),
        "--frozen",
        "--exact",
        "--python",
        "3.12",
        "python",
        "-c",
        "pass",
    ]
    subprocess.run(
        exact_command, cwd=ROOT, env=uv_env, check=True, timeout=300
    )
    wheel = _pollution_wheel(tmp_path)
    sentinel = tmp_path / "pollution-loaded.txt"
    report = tmp_path / "pollution-oracle.json"
    distribution_probe = (
        "import importlib.metadata as m; "
        "d=m.distribution('citeframe-a2a-pollution'); "
        "e=[x for x in d.entry_points if x.group=='pytest11']; "
        "assert e and e[0].name=='citeframe_a2a_pollution'; print('discoverable')"
    )

    try:
        subprocess.run(
            [
                uv_value,
                "pip",
                "install",
                "--python",
                str(worker_python),
                "--no-deps",
                str(wheel),
            ],
            cwd=ROOT,
            env=uv_env,
            check=True,
            timeout=120,
        )
        discovered = subprocess.run(
            [str(worker_python), "-I", "-c", distribution_probe],
            cwd=ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
        assert discovered.stdout.strip() == "discoverable"
        plugin_env = os.environ.copy()
        plugin_env["A2A_POLLUTION_SENTINEL"] = str(sentinel)
        smoke_test = tmp_path / "test_pollution_plugin_smoke.py"
        smoke_test.write_text("def test_smoke():\n    assert True\n", encoding="utf-8")
        subprocess.run(
            [str(worker_python), "-m", "pytest", "-q", str(smoke_test)],
            cwd=ROOT,
            env=plugin_env,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
        )
        assert sentinel.read_text(encoding="utf-8") == "loaded\n"
        sentinel.unlink()

        oracle_env = os.environ.copy()
        oracle_env["A2A_POLLUTION_SENTINEL"] = str(sentinel)
        completed = subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--root",
                str(ROOT),
                "--output",
                str(report),
            ],
            cwd=ROOT,
            env=oracle_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=660,
        )
        assert completed.returncode == 0, completed.stdout
        assert json.loads(report.read_text(encoding="utf-8"))["equal"] is True
        assert not sentinel.exists(), "extraneous pytest11 plugin loaded during exact probe"
        absent = subprocess.run(
            [
                str(worker_python),
                "-I",
                "-c",
                (
                    "import importlib.metadata as m; "
                    "print('present' if any(d.metadata['Name']=='citeframe-a2a-pollution' "
                    "for d in m.distributions()) else 'absent')"
                ),
            ],
            cwd=ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
        assert absent.stdout.strip() == "absent"
    finally:
        cleanup = subprocess.run(
            exact_command,
            cwd=ROOT,
            env=uv_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=300,
        )
        if sentinel.exists():
            sentinel.unlink()
        assert cleanup.returncode == 0, cleanup.stdout
