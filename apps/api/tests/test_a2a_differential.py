from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "infra/scripts/run-a2a-differential.py"


def test_a2a_executable_differential_oracle(tmp_path: Path) -> None:
    report = tmp_path / "a2a-differential.json"
    completed = subprocess.run(
        [sys.executable, str(RUNNER), "--root", str(ROOT), "--output", str(report)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert completed.returncode == 0, completed.stdout
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["equal"] is True
    assert payload["baselineRef"] == "d1b5945e977445e4db6bf56ef54cf61607ead2e2"
    assert len(payload["candidateSemanticWorktreeSha256"]) == 64
    assert len(payload["repairSnapshotSha256"]) == 64
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
        "fixedMultiStepProcessOne",
    }

    semantics = payload["candidate"]
    assert set(semantics["normalizedDbRows"]) == {"transitions", "processOne"}
    assert len(semantics["exactEventBytes"]["transitions"]) >= 15
    assert len(semantics["exactEventBytes"]["processOne"]) >= 40
    assert set(semantics["exactPayloadBytes"]["processOne"]) == {
        "apiResponses",
        "objectPayloads",
    }
    assert semantics["fixedMultiStepProcessOne"]["processOneOutputs"] == [
        True,
        True,
        True,
        False,
    ]
    assert semantics["fixedMultiStepProcessOne"]["runStatus"] == "completed"

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
        timeout=120,
    )
    assert completed.returncode == 2, completed.stdout
    assert "candidate probe failed" in completed.stdout
    assert "must not use API research_worker facade" in completed.stdout
