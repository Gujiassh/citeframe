from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from shell_test_support import find_bash

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = REPO_ROOT / "infra/scripts/run-r800-acceptance.sh"
COMPOSE_OVERRIDE_PATH = REPO_ROOT / "infra/docker/compose.r800.yml"


def _runner() -> str:
    return RUNNER_PATH.read_text()


def test_runner_has_valid_shell_syntax() -> None:
    bash = find_bash(REPO_ROOT)
    if bash is None:
        pytest.skip("A real Bash executable is required for shell syntax validation")
    result = subprocess.run(
        [bash, "-n", str(RUNNER_PATH)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_runner_uses_an_owned_isolated_project_and_cleans_every_resource() -> None:
    runner = _runner()

    assert "umask 077" in runner
    assert 'mkdir -m 700 -p "$OUTPUT_DIR"' in runner
    assert 'chmod 600 "$ENV_FILE"' in runner
    assert "pick_free_port()" in runner
    assert "^citeframe-r800-[a-z0-9][a-z0-9_-]*$" in runner
    assert 'COMPOSE_OVERRIDE_FILE="$REPO_ROOT/infra/docker/compose.r800.yml"' in runner
    assert "export ENV_FILE COMPOSE_PROJECT COMPOSE_OVERRIDE_FILE" in runner
    assert "OWNS_PROJECT=false" in runner
    assert "OWNS_PROJECT=true" in runner
    trap_position = runner.index("trap cleanup EXIT INT TERM")
    assert trap_position < runner.index("validate_common_options", trap_position)
    assert trap_position < runner.index("require_command uv", trap_position)
    assert trap_position < runner.index("OWNS_PROJECT=true")
    assert "compose down --volumes --remove-orphans" in runner
    assert (
        'docker ps -a --filter "label=com.docker.compose.project=$COMPOSE_PROJECT"'
        in runner
    )
    assert (
        'docker volume ls --filter "label=com.docker.compose.project=$COMPOSE_PROJECT"'
        in runner
    )
    assert (
        'docker network ls --filter "label=com.docker.compose.project=$COMPOSE_PROJECT"'
        in runner
    )
    assert 'rm -f "$ENV_FILE"' in runner
    assert '"envRemoved": sys.argv[7] == "true"' in runner


def test_runner_orders_real_services_routes_and_restore_oracles() -> None:
    runner = _runner()
    commands = (
        "\nwrite_redacted_compose_config\n",
        "compose up -d postgres minio redis",
        'compose build api worker web > "$OUTPUT_DIR/build.log"',
        "compose up -d provider-stub",
        'compose run --rm -T migration > "$OUTPUT_DIR/migration.log"',
        "python scripts/r800_research_acceptance.py seed",
        "compose up -d web caddy",
        "python scripts/r800_research_acceptance.py run-scenarios",
        "python scripts/r800_research_acceptance.py snapshot",
        '"$SCRIPT_DIR/backup-deployment.sh"',
        'compose down --volumes --remove-orphans > "$OUTPUT_DIR/down-before-restore.log"',
        '"$SCRIPT_DIR/restore-deployment.sh"',
    )
    positions = [runner.index(command) for command in commands]
    assert positions == sorted(positions)
    assert "compose up -d worker web caddy" not in runner

    after_restore = runner.index('"$SCRIPT_DIR/restore-deployment.sh"')
    after_snapshot = runner.index(
        "python scripts/r800_research_acceptance.py snapshot",
        after_restore,
    )
    verify = runner.index(
        "uv run python scripts/r800_research_acceptance.py verify",
        after_snapshot,
    )
    assert after_restore < after_snapshot < verify
    assert '--before "$OUTPUT_DIR/before.json"' in runner
    assert '--after "$OUTPUT_DIR/after.json"' in runner
    assert '--output "$OUTPUT_DIR/verification.json"' in runner


def test_runner_captures_production_backup_restore_artifacts() -> None:
    runner = _runner()

    assert '"$SCRIPT_DIR/backup-deployment.sh"' in runner
    assert '"$SCRIPT_DIR/restore-deployment.sh"' in runner
    assert "--confirm" in runner
    for artifact in (
        "compose-config.yml",
        "compose-config.sha256",
        "migration.log",
        "api-readiness.json",
        "api.log",
        "worker.log",
        "provider.log",
        "provider-timeline.json",
        "provider-timeline-after-restore.json",
        "scenarios.json",
        "before.json",
        "after.json",
        "backup.log",
        "restore.log",
        "verification.json",
        "cleanup.json",
        "report.json",
    ):
        assert artifact in runner


def test_provider_stays_private_and_runner_uses_only_compose_v1() -> None:
    runner = _runner()
    compose_override = COMPOSE_OVERRIDE_PATH.read_text()

    assert "provider-stub:" in compose_override
    assert 'expose:\n      - "18082"' in compose_override
    assert "ports:" not in compose_override
    assert "provider-stub:18082" in runner
    assert "docker compose" not in runner


def test_runner_separates_engineering_model_and_user_gates() -> None:
    runner = _runner()

    assert 'scenarios.get("engineeringGate") == "pass"' in runner
    assert 'verification.get("passed") is True' in runner
    assert '"engineeringGate": engineering_gate' in runner
    assert '"modelQualityGate": "not_evaluable"' in runner
    assert '"scripted_provider_is_engineering_evidence_only"' in runner
    assert '"userValueGate": "not_evaluable"' in runner
    assert '"no_real_target_user_evidence"' in runner
    assert (
        'report["releaseGatePassed"] = report.get("engineeringGate") == "pass" and cleanup["passed"]'
        in runner
    )
    assert '"releaseGatePassed": False' in runner
    assert '"$cleanup_passed" != true' in runner


def test_runner_redacts_secrets_and_never_copies_them_into_report() -> None:
    runner = _runner()

    redaction_bindings = {
        "R800_SECRET_POSTGRES": "POSTGRES_PASSWORD",
        "R800_SECRET_MINIO_USER": "MINIO_ROOT_USER",
        "R800_SECRET_MINIO_PASSWORD": "MINIO_ROOT_PASSWORD",
        "R800_SECRET_INTERNAL_TOKEN": "API_INTERNAL_TOKEN",
        "R800_SECRET_SESSION": "SESSION_SECRET",
        "R800_SECRET_OPENAI": "OPENAI_API_KEY",
    }
    for redaction_variable, secret_variable in redaction_bindings.items():
        assert f'{redaction_variable}="${secret_variable}"' in runner
    assert 'payload.replace(value, "<redacted>")' in runner
    assert 'payload.replace("r800-private-deterministic-key", "<redacted>")' in runner

    report_block = runner[
        runner.index(
            'python3 - "$OUTPUT_DIR" "$COMPOSE_PROJECT" <<\'PY\''
        ) : runner.index("r800_engineering_gate_failed")
    ]
    for forbidden in (
        "POSTGRES_PASSWORD",
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
        "API_INTERNAL_TOKEN",
        "SESSION_SECRET",
        "OPENAI_API_KEY",
        ".env.deploy",
    ):
        assert forbidden not in report_block
