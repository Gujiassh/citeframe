from __future__ import annotations

from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "infra/scripts/run-v5b-document-acceptance.sh"
SEED = REPO_ROOT / "apps/worker/scripts/v5b_document_deployment_seed.py"
COMPOSE = REPO_ROOT / "infra/docker/compose.v5b.yml"
DEPLOY_COMPOSE = REPO_ROOT / "infra/docker/compose.deploy.yml"
RESTORE = REPO_ROOT / "infra/scripts/restore-deployment.sh"


def test_v5b_runner_and_seed_compile() -> None:
    shell = subprocess.run(
        ["bash", "-n", str(RUNNER)], capture_output=True, text=True, check=False
    )
    assert shell.returncode == 0, shell.stderr
    compile_result = subprocess.run(
        ["python3", "-m", "py_compile", str(SEED)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert compile_result.returncode == 0, compile_result.stderr


def test_v5b_runner_binds_one_isolated_project_to_real_gates() -> None:
    runner = RUNNER.read_text()
    override = COMPOSE.read_text()

    assert "^citeframe-v5b-[a-z0-9][a-z0-9_-]*$" in runner
    assert 'COMPOSE_OVERRIDE_FILE="$REPO_ROOT/infra/docker/compose.v5b.yml"' in runner
    assert "compose build api worker web" in runner
    assert "v5b_document_deployment_seed.py" in runner
    assert "v5b_document_restore_acceptance.py snapshot" in runner
    assert "v5b_document_restore_acceptance.py verify" in runner
    assert 'PLAYWRIGHT_STANDALONE_SERVER=1' in runner
    assert 'PLAYWRIGHT_START_WEB' not in runner
    assert '"$SCRIPT_DIR/backup-deployment.sh"' in runner
    assert '"$SCRIPT_DIR/restore-deployment.sh"' in runner
    assert "compose down --volumes --remove-orphans" in runner
    assert 'docker image rm "$API_IMAGE" "$WORKER_IMAGE" "$WEB_IMAGE"' in runner
    assert "provider-stub:" in override
    assert 'expose:\n      - "18082"' in override
    assert 'CADDY_BIND_ADDRESS=127.0.0.1' in runner
    assert "browser-asset-before.json" in runner
    assert "browser-asset-after.json" in runner
    assert "browser-asset-verification.json" in runner
    assert "--allow-empty-evidence-links" in runner
    assert '"backupIncludesBothDocumentAssets"' in runner
    assert '"browserAssetRestoreVerification"' in runner
    assert "runtime-containers-before.json" in runner
    assert "runtime-containers-after.json" in runner
    assert '"runtimeContainersBeforeMatchBuiltImages"' in runner
    assert '"runtimeContainersAfterMatchBuiltImages"' in runner
    assert 'health_ok = entry.get("health") == "healthy"' in runner
    assert 'service == "worker" and entry.get("health") is None' in runner
    assert '["node", "apps/web/server.js"]' in runner


def test_v5b_deployment_preserves_public_default_and_scopes_browser_binding() -> None:
    compose = DEPLOY_COMPOSE.read_text()
    assert '${CADDY_BIND_ADDRESS:-0.0.0.0}:${CADDY_HTTP_PORT:-80}:80' in compose
    assert '${CADDY_BIND_ADDRESS:-0.0.0.0}:${CADDY_HTTPS_PORT:-443}:443' in compose
    assert '127.0.0.1:${CADDY_HTTP_PORT' not in compose
    assert 'provider-stub' in RESTORE.read_text()


def test_seed_binds_ready_document_to_active_citation_and_note_source() -> None:
    seed = SEED.read_text()
    assert "finalize-upload" in seed
    assert 'current["status"]' in seed
    assert "thread.active_message_id = message.id" in seed
    assert "MessageCitation(" in seed
    assert "NoteSource(" in seed
    assert "clone_evidence_locator" in seed
    assert '"schemaVersion": "v5b-document-browser-state-v1"' in seed
