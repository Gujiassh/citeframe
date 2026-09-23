"""Bounded disposable Compose smoke; product scripts and image commands stay intact."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
import re
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

PRODUCT_PATHS = ["apps", "packages", "tools/evaluation", "infra/docker",
                 "infra/scripts/compose-common.sh", "infra/scripts/backup-deployment.sh",
                 "infra/scripts/restore-deployment.sh", "infra/scripts/run-r800-acceptance.sh",
                 "package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml"]


ATTEMPT_TIMELINE_QUERY = ("SELECT coalesce(json_agg(t), '[]') FROM (SELECT s.run_id, s.step_kind, s.step_key, "
         "s.status AS step_status, a.attempt_number, a.status, a.worker_instance_id, "
         "a.lease_expires_at, a.heartbeat_at, a.started_at, a.finished_at "
         "FROM research_step_attempts a JOIN research_steps s ON s.id=a.step_id "
         "ORDER BY a.started_at) t")


def scrub(value: str, secret_values: list[str]) -> str:
    for secret in sorted(secret_values, key=len, reverse=True):
        value = value.replace(secret, "<redacted>")
    return value


def official_mc_mirror(common_script: str) -> str:
    match = re.search(r"MINIO_MC_IMAGE=\$\{MINIO_MC_IMAGE:-([^}]+)\}", common_script)
    if not match or not re.fullmatch(r"minio/mc:[^@]+@sha256:[0-9a-f]{64}", match[1]):
        raise ValueError("Expected digest-pinned original MinIO client reference")
    return "quay.io/" + match[1]


def free_ports(count: int) -> list[int]:
    sockets = []
    try:
        for _ in range(count):
            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            sockets.append(sock)
        return [sock.getsockname()[1] for sock in sockets]
    finally:
        for sock in sockets:
            sock.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--historical-scenarios-only", action="store_true")
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    harness = Path(__file__).resolve().parent
    output.mkdir(parents=True, exist_ok=False)
    env_file = output / ".env.deploy"
    project = "citeframe-r800-pr26-" + secrets.token_hex(5)
    env = os.environ.copy()
    env["COMPOSE_OVERRIDE_FILE"] = str(source / "infra/docker/compose.r800.yml")
    values = {name: secrets.token_hex(20) for name in (
        "POSTGRES_PASSWORD", "MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD",
        "AI_PDF_API_INTERNAL_TOKEN", "AI_PDF_SESSION_SECRET", "AI_PDF_OPENAI_API_KEY")}
    private = list(values.values()) + ["r800-private-deterministic-key"]
    ports = free_ports(3)
    values.update(POSTGRES_DB="ai_pdf_workspace", POSTGRES_USER="ai_pdf",
                  MINIO_BUCKET="ai-pdf-workspace", CADDY_SITE_ADDRESS=":80",
                  CADDY_BIND_ADDRESS="127.0.0.1", CADDY_HTTP_PORT=str(ports[0]),
                  CADDY_HTTPS_PORT=str(ports[1]), MINIO_CONSOLE_PORT=str(ports[2]),
                  AI_PDF_API_IMAGE=project + "-api", AI_PDF_WORKER_IMAGE=project + "-worker",
                  AI_PDF_WEB_IMAGE=project + "-web", AI_PDF_OLLAMA_BASE_URL="http://provider-stub:18082",
                  AI_PDF_OPENAI_API_BASE="http://provider-stub:18082/v1")
    env_file.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    env_file.chmod(0o600)
    compose = ["docker-compose", "--project-name", project, "--env-file", str(env_file),
               "-f", str(source / "infra/docker/compose.deploy.yml"), "-f", env["COMPOSE_OVERRIDE_FILE"]]
    commands = []

    def run(name, command, *, timeout=900, required=True):
        started = time.monotonic()
        try:
            result = subprocess.run(command, cwd=source, env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            (output / f"{name}.timeout.txt").write_text(str(error))
            raise
        commands.append({"name": name, "command": command, "exitCode": result.returncode,
                         "elapsedSeconds": round(time.monotonic() - started, 3)})
        (output / "commands.json").write_text(json.dumps(commands, indent=2))
        (output / f"{name}.out").write_text(scrub(result.stdout, private))
        (output / f"{name}.err").write_text(scrub(result.stderr, private))
        print(f"{name}: exit={result.returncode}", flush=True)
        if required and result.returncode:
            raise RuntimeError(f"{name} exited {result.returncode}; see evidence logs")
        return result.stdout

    def cli(name, *arguments):
        entry = (["python", "scripts/r800_research_acceptance.py"] if args.historical_scenarios_only
                 else ["python", "-m", "citeframe_evaluation.acceptance.cli"])
        output_text = run(name, compose + ["run", "--rm", "-T", "--no-deps", "worker", *entry, *arguments])
        if not args.historical_scenarios_only:
            json.loads(output_text)
        return output_text

    def wait_ready():
        for _ in range(90):
            probe = subprocess.run(compose + ["exec", "-T", "api", "python", "-c",
                "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready',timeout=3)"],
                cwd=source, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            if probe.returncode == 0:
                return
            time.sleep(2)
        raise TimeoutError("API readiness after normal compose up")

    def worker_identity(label):
        container = run(label + "-id", compose + ["ps", "-q", "worker"]).strip()
        assert container, "Normal compose up did not create Worker"
        raw = run(label + "-inspect", ["docker", "inspect", "--format",
            '{{json .Config.Cmd}}|{{.Image}}|{{.Config.Hostname}}|{{.State.Status}}', container])
        command, image_id, hostname, state = raw.strip().split("|")
        assert json.loads(command) == ["python", "-m", "ai_pdf_worker.main"], raw
        assert state == "running", raw
        run(label + "-image", ["docker", "image", "inspect", "--format",
            '{{.Id}}|{{json .Config.Cmd}}', image_id])
        pid_one = run(label + "-pid1", ["docker", "exec", container, "python", "-c",
            "from pathlib import Path; print(Path('/proc/1/cmdline').read_bytes().replace(bytes([0]), b' ').decode())"])
        assert pid_one.strip() == "python -m ai_pdf_worker.main", pid_one
        return "worker-1"

    success = False
    scenarios_passed = False
    try:
        target_head = run("source-head", ["git", "rev-parse", "HEAD"]).strip()
        harness_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=harness, text=True).strip()
        assert not run("source-status", ["git", "status", "--porcelain"]).strip()
        expected = "50af19dc3b79fbb677d9ac66c005b77cbe76f3d9" if args.historical_scenarios_only else harness_head
        assert target_head == expected, "Unexpected product source SHA"
        baseline = "82ecb8149831c9ab148291778598b251ac6558fd"
        product_diff = run("product-diff", ["git", "diff", "--name-only", baseline, target_head,
                                           "--", *PRODUCT_PATHS])
        if not args.historical_scenarios_only:
            assert set(product_diff.splitlines()) <= {
                "tools/evaluation/src/citeframe_evaluation/acceptance/cli.py",
                "tools/evaluation/tests/test_acceptance_cli_output.py",
            }, product_diff
        (output / "provenance.json").write_text(json.dumps({"productHead": target_head,
            "harnessHead": harness_head, "baselineHead": baseline, "project": project,
            "harnessFiles": {p.name: sha256(p.read_bytes()).hexdigest()
                             for p in (Path(__file__), harness / "r800_docker_probe.py")}}, indent=2))
        if not args.historical_scenarios_only:
            # The official second registry serves the identical pinned manifest.
            image = official_mc_mirror((source / "infra/scripts/compose-common.sh").read_text())
            env["MINIO_MC_IMAGE"] = image
            (output / "mc-image-source.json").write_text(json.dumps({
                "override": image, "defaultRegistryPassed": False,
                "reason": "Default Docker Hub pull denied in run 35891438408; same-digest official mirror",
            }, indent=2))
            run("mc-pull", ["docker", "pull", image])
            digests = json.loads(run("mc-digests", ["docker", "image", "inspect", "--format",
                "{{json .RepoDigests}}", image]))
            assert "quay.io/minio/mc@" + image.split("@", 1)[1] in digests
        run("compose-redacted", compose + ["config"])
        targets = ["api", "worker"] if args.historical_scenarios_only else ["api", "worker", "web"]
        run("build", compose + ["build", *targets], timeout=1200)
        run("infrastructure", compose + ["up", "-d", "postgres", "minio", "redis", "provider-stub"])
        run("migration", compose + ["run", "--rm", "-T", "migration"])
        run("api", compose + ["up", "-d", "api"])
        wait_ready()
        cli("seed", "seed")
        raw_scenarios = cli("scenarios", "run-scenarios")
        if args.historical_scenarios_only:
            # Preserve raw stdout; only separate this observed legacy diagnostic for attribution.
            warning = "warning: The `fitz` API is deprecated and will be removed in future. Use `import pymupdf` instead.\n"
            raw_scenarios = raw_scenarios.removeprefix(warning)
        scenarios = json.loads(raw_scenarios)
        scenarios_passed = scenarios["engineeringGate"] == "pass"
        (output / "scenario-summary.json").write_text(json.dumps(scenarios, indent=2))
        run("scenario-provider-timeline", compose + ["exec", "-T", "provider-stub", "python", "-c",
            "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:18082/__r800__/control/timeline').read().decode())"])
        run("scenario-attempt-timeline", compose + ["exec", "-T", "postgres", "psql", "--username",
            "ai_pdf", "--dbname", "ai_pdf_workspace", "--no-psqlrc", "-At", "-c", ATTEMPT_TIMELINE_QUERY])
        if args.historical_scenarios_only:
            return
        cli("before", "snapshot")
        script_args = ["--env-file", str(env_file), "--project", project]
        run("backup", ["bash", str(source / "infra/scripts/backup-deployment.sh"),
                       *script_args, "--output-dir", str(output / "backup")])
        worker_identity("backup-restarted-worker")
        run("empty-target", compose + ["down", "--volumes", "--remove-orphans"])
        remaining = run("empty-volumes", ["docker", "volume", "ls", "--filter",
                                           f"label=com.docker.compose.project={project}", "-q"])
        assert not remaining.strip()
        run("restore", ["bash", str(source / "infra/scripts/restore-deployment.sh"),
                        *script_args, "--backup-dir", str(output / "backup"), "--confirm"])
        worker_id = worker_identity("restored-worker")
        cli("after", "snapshot")
        mount = ["-v", f"{output}:/evidence", "-v", f"{harness}:/smoke:ro"]
        run("verify", compose + ["run", "--rm", "-T", "--no-deps", *mount, "worker",
            "python", "-m", "citeframe_evaluation.acceptance.cli", "verify",
            "--before", "/evidence/before.out", "--after", "/evidence/after.out",
            "--output", "/tmp/verification.json"])
        run("objects", compose + ["run", "--rm", "-T", "--no-deps", "--user", "0:0", *mount,
            "worker", "python", "/smoke/r800_docker_probe.py", "objects", "--backup", "/evidence/backup/minio"])
        run("new-task", compose + ["run", "--rm", "-T", "--no-deps", "-v", f"{harness}:/smoke:ro",
            "-e", f"SMOKE_EXPECTED_WORKER={worker_id}", "worker", "python", "/smoke/r800_docker_probe.py", "exercise"])
        worker_identity("post-task-worker")
        assert json.loads((output / "new-task.out").read_text())["status"] == "completed"
        success = True
    finally:
        run("final-ps", compose + ["ps", "-a"], required=False)
        run("final-logs", compose + ["logs", "--no-color"], required=False)
        run("cleanup", compose + ["down", "--volumes", "--remove-orphans"], required=False)
        cleanup_ok = commands[-1]["exitCode"] == 0
        for kind in ("container", "volume", "network"):
            remaining = run("remaining-" + kind, ["docker", kind, "ls", "-q", "--filter",
                f"label=com.docker.compose.project={project}"], required=False)
            cleanup_ok = cleanup_ok and commands[-1]["exitCode"] == 0 and not remaining.strip()
        env_file.unlink(missing_ok=True)
        # Backups are synthetic but do not publish DB dumps or credentials in CI artifacts.
        report = {"mode": "historical-scenario-attribution" if args.historical_scenarios_only else "deployment",
                  "passed": success and cleanup_ok and scenarios_passed,
                  "deploymentGatePassed": success, "scenarioGatePassed": scenarios_passed, "cleanupPassed": cleanup_ok, "modelQuality": "not_evaluated", "project": project}
        (output / "result.json").write_text(json.dumps(report, indent=2))
        for path in output.rglob("*"):
            if path.is_file() and path.suffix in {".out", ".err", ".json", ".txt", ".env"}:
                path.write_text(scrub(path.read_text(), private))
        if not cleanup_ok:
            raise RuntimeError("Disposable Compose cleanup failed")
    if not scenarios_passed:
        raise RuntimeError("Historical R800 scenario gate failed; see scenarios.out")


if __name__ == "__main__":
    main()
