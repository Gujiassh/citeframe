from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import ai_pdf_api.models  # noqa: F401
import httpx
import pytest
from ai_pdf_api.db.base import Base
from ai_pdf_api.models import Asset, ContentUnitEmbedding, EvidenceLocator
from ai_pdf_worker import r800_acceptance_scenarios as scenarios
from ai_pdf_worker.r800_acceptance_common import (
    IDS,
    SCHEMA_VERSION,
    SNAPSHOT_VERSION,
    _semantic_sha256,
)
from ai_pdf_worker.r800_acceptance_fixture import seed_state
from ai_pdf_worker.r800_acceptance_scenarios import (
    ResearchHttpClient,
    _process_until,
    run_scenarios,
)
from ai_pdf_worker.r800_acceptance_snapshot import verify_snapshots
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts/r800_research_acceptance.py"
SPEC = importlib.util.spec_from_file_location("r800_research_acceptance", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
R800 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R800)


def test_verify_requires_exact_semantic_and_payload_identity(tmp_path: Path) -> None:
    body = {
        "schemaVersion": SNAPSHOT_VERSION,
        "fixture": {"workspaceId": "workspace"},
        "alembic": [{"version_num": "head"}],
        "relations": {"research_runs": []},
        "objects": [{"objectKey": "research/run/final.md", "byteSize": 4, "sha256": "a" * 64}],
    }
    semantic = _semantic_sha256({key: value for key, value in body.items() if key != "schemaVersion"})
    before = {**body, "semanticSha256": semantic}
    after = json.loads(json.dumps(before))

    passed = verify_snapshots(before, after)
    assert passed["passed"] is True
    assert passed["verification"]["mismatches"] == []

    after["objects"][0]["byteSize"] = 5
    failed = verify_snapshots(before, after)
    assert failed["passed"] is False
    assert failed["verification"]["mismatches"] == ["snapshot_payload"]


def test_http_client_sends_only_internal_actor_and_idempotency_headers() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["json"] = json.loads(request.content)
        return httpx.Response(201, json={"run": {"id": "run"}})

    client = ResearchHttpClient(
        base_url="http://api.test",
        internal_token="private-test-token",
        transport=httpx.MockTransport(handler),
    )
    try:
        response = client.request(
            "POST",
            "/v1/workspaces/workspace/research-runs",
            actor_id="creator",
            idempotency_key="r800-test-key-0001",
            payload={"question": "test"},
            expected=(201,),
        )
    finally:
        client.close()

    assert response.status_code == 201
    headers = captured["headers"]
    assert headers["x-ai-pdf-internal-token"] == "private-test-token"
    assert headers["x-user-id"] == "creator"
    assert headers["idempotency-key"] == "r800-test-key-0001"
    assert "authorization" not in headers
    assert captured["json"] == {"question": "test"}


def test_seed_builds_deterministic_pdf_evidence_and_1024_embedding() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, future=True)
    stored: dict[str, tuple[bytes, str]] = {}

    result = seed_state(
        sessions,
        uploader=lambda key, payload, media_type: stored.__setitem__(
            key, (payload, media_type)
        ),
        cleanup=lambda key: stored.pop(key, None),
    )

    assert result["schemaVersion"] == SCHEMA_VERSION
    assert result["workspaceId"] == IDS["workspace"]
    assert len(stored) == 2
    with Session(engine) as db:
        asset = db.get(Asset, IDS["asset"])
        locator = db.get(EvidenceLocator, IDS["locator"])
        embedding = db.get(ContentUnitEmbedding, IDS["embedding"])
        assert asset is not None and asset.status == "ready"
        assert locator is not None and locator.locator_kind == "pdf_page"
        assert embedding is not None and len(embedding.embedding) == 1024
        assert embedding.embedding[0] == 1.0
        assert all(value == 0.0 for value in embedding.embedding[1:])
    engine.dispose()


def test_scenario_gate_fails_when_any_check_is_blocked(monkeypatch) -> None:
    class Client:
        def close(self) -> None:
            raise AssertionError("injected clients are not closed")

    monkeypatch.setattr(
        scenarios,
        "_main_scenario",
        lambda *_args: (
            {"id": "main", "status": "completed"},
            {"mainCompleted": scenarios._check(True, evidence={})},
        ),
    )
    monkeypatch.setattr(
        scenarios,
        "_reclaim_scenario",
        lambda *_args: (
            {"id": "reclaim", "status": "queued"},
            scenarios._check(False, evidence={}, blocked="step_claim_raced"),
        ),
    )
    monkeypatch.setattr(
        scenarios,
        "_cancel_scenario",
        lambda *_args: (
            {"id": "cancel", "status": "cancelled"},
            scenarios._check(True, evidence={}),
        ),
    )
    monkeypatch.setattr(
        scenarios,
        "_membership_scenario",
        lambda *_args: (
            {"id": "membership", "status": "cancelled"},
            scenarios._check(True, evidence={}),
        ),
    )

    result = run_scenarios(
        client=Client(),
        processor=object(),
        session_factory=lambda: None,
    )

    assert result["engineeringGate"] == "fail"
    assert result["checks"]["leaseReclaim"]["status"] == "blocked"
    assert result["checks"]["leaseReclaim"]["passed"] is False


def test_process_until_drives_the_isolated_production_worker() -> None:
    class Client:
        def __init__(self) -> None:
            self.polls = 0

        def run(self, _run_id: str, *, actor_id: str) -> dict[str, object]:
            assert actor_id == IDS["creator"]
            self.polls += 1
            return {
                "id": "run-1",
                "status": "awaiting_plan_approval" if self.polls > 1 else "planning",
            }

    class Processor:
        calls = 0

        def process_one(self) -> bool:
            self.calls += 1
            return True

    client = Client()
    processor = Processor()
    run, errors = _process_until(
        client,
        "run-1",
        {"awaiting_plan_approval"},
        processor=processor,
        timeout_seconds=1,
    )

    assert run["status"] == "awaiting_plan_approval"
    assert errors == []
    assert processor.calls == 1


def test_process_until_fails_fast_before_opening_persistent_sse() -> None:
    class Client:
        def run(self, _run_id: str, *, actor_id: str) -> dict[str, object]:
            assert actor_id == IDS["creator"]
            return {"id": "run-1", "status": "running"}

    with pytest.raises(
        TimeoutError,
        match="worker_poll_timeout run_id=run-1 status=running",
    ):
        _process_until(
            Client(),
            "run-1",
            {"completed"},
            timeout_seconds=0,
        )


def test_cli_contract_exposes_runner_commands_and_required_verify_output() -> None:
    assert R800.parse_args(["seed"]).command == "seed"
    assert R800.parse_args(["run-scenarios"]).command == "run-scenarios"
    assert R800.parse_args(["snapshot"]).command == "snapshot"
    args = R800.parse_args(
        [
            "verify",
            "--before",
            "before.json",
            "--after",
            "after.json",
            "--output",
            "verification.json",
        ]
    )
    assert args.command == "verify"
    assert args.output == Path("verification.json")
