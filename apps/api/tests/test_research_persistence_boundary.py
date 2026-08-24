from __future__ import annotations

import ast
import inspect
import subprocess
import sys
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = ROOT / "packages/research-persistence"
PACKAGE_SRC = PACKAGE_ROOT / "src"
PACKAGE = PACKAGE_SRC / "citeframe_research_persistence"
ALLOWED_ROOTS = set(sys.stdlib_module_names) | {
    "__future__",
    "sqlalchemy",
    "citeframe_contracts",
    "citeframe_persistence",
    "citeframe_research_persistence",
}


def test_research_persistence_manifest_has_only_neutral_dependencies() -> None:
    manifest = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert set(manifest["project"]["dependencies"]) == {
        "SQLAlchemy>=2.0,<3.0",
        "citeframe-backend-contracts",
        "citeframe-backend-persistence",
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
    subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            code,
            str(PACKAGE_SRC),
            str(ROOT / "packages/backend-persistence/src"),
            str(ROOT / "packages/backend-contracts/src"),
            str(ROOT / "apps/api/src"),
            str(ROOT / "apps/worker/src"),
        ],
        check=True,
    )


def test_api_and_worker_composition_uses_neutral_transition_owners() -> None:
    import citeframe_research_persistence as research
    from ai_pdf_api.services import research_worker
    from ai_pdf_api.services.research import research_runs
    from ai_pdf_api.services.research import research_worker_completion, research_worker_state

    identity_names = {
        "claim_next_research_step",
        "claim_specific_research_step",
        "complete_control_step",
        "complete_research_critique",
        "complete_research_step",
        "complete_research_verification",
        "fail_research_step",
        "heartbeat_research_step",
        "reclaim_expired_research_steps",
    }
    for name in identity_names:
        assert inspect.unwrap(getattr(research_worker, name)) is getattr(research, name), name
    assert inspect.unwrap(research_worker_completion.complete_research_critique) is research.complete_research_critique
    assert inspect.unwrap(research_worker_completion.complete_research_verification) is research.complete_research_verification
    assert inspect.unwrap(research_worker_state.complete_control_step) is research.complete_control_step
    assert inspect.unwrap(research_worker_state.reclaim_expired_research_steps) is research.reclaim_expired_research_steps
    assert research_runs.finalize_cancel_if_idle is research.finalize_cancel_if_idle
    assert "def finalize_cancel_if_idle" not in inspect.getsource(research_runs)


def test_locked_attempt_legacy_signature_supports_positional_keyword_and_patch_chain(monkeypatch) -> None:
    import citeframe_research_persistence.lease as neutral_lease
    from ai_pdf_api.services.research import research_worker_lease as legacy

    signature = inspect.signature(legacy._locked_attempt)
    assert list(signature.parameters) == ["db", "attempt_id", "lease_token", "now"]
    assert signature.parameters["db"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert all(
        signature.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
        for name in ("attempt_id", "lease_token", "now")
    )

    now = datetime(2026, 8, 24, tzinfo=UTC)
    db = object()
    run = SimpleNamespace(
        workspace_id="workspace-1",
        status="running",
        created_by_user_id="user-1",
    )
    step = SimpleNamespace(
        workspace_id="workspace-1",
        status="running",
        step_kind="researcher",
        execution_snapshot_id="snapshot-1",
        plan_revision_id="revision-1",
    )
    attempt = SimpleNamespace(
        workspace_id="workspace-1",
        status="running",
        lease_token_hash=__import__("hashlib").sha256(b"token").hexdigest(),
        lease_expires_at=now + timedelta(seconds=30),
    )
    calls: list[tuple[object, str]] = []

    def patched_chain(received_db, attempt_id):
        calls.append((received_db, attempt_id))
        return run, step, attempt

    monkeypatch.setattr(legacy, "_locked_attempt_chain", patched_chain)
    monkeypatch.setattr(neutral_lease, "ensure_creator_membership", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(neutral_lease, "ResearchExecutionSnapshot", object())
    # Avoid ORM lookup while retaining the facade's real neutral validation path.
    monkeypatch.setattr(step, "execution_snapshot_id", None)
    monkeypatch.setattr(step, "step_kind", "planner")
    monkeypatch.setattr(neutral_lease, "ResearchPlanRevision", object())

    class Db:
        def get(self, _model, _identifier):
            return SimpleNamespace(run_id="run-1", workspace_id="workspace-1")

    actual_db = Db()
    run.id = "run-1"
    assert legacy._locked_attempt(
        actual_db,
        attempt_id="attempt-1",
        lease_token="token",
        now=now,
    ) == (run, step, attempt)
    assert legacy._locked_attempt(
        db=actual_db,
        attempt_id="attempt-2",
        lease_token="token",
        now=now,
    ) == (run, step, attempt)
    assert calls == [(actual_db, "attempt-1"), (actual_db, "attempt-2")]


def test_supported_legacy_private_symbols_preserve_neutral_identity() -> None:
    from ai_pdf_api.services.research import (
        research_idempotency,
        research_worker_lease,
        research_worker_tools,
    )
    from citeframe_research_persistence import idempotency, lease, tools
    from citeframe_research_persistence.errors import persisted_error_payload

    assert research_idempotency._persisted_error_payload is persisted_error_payload
    assert research_idempotency._frozen_error is idempotency._frozen_error
    assert research_worker_lease._lease_step is lease._lease_step
    assert research_worker_lease._queue_ready_dependents is lease._queue_ready_dependents
    assert research_worker_tools.ToolResultCallback is tools.ToolResultCallback
