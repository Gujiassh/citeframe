"""CI-only assembly of official, fixed-version MinIO binaries; never publishes images."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
import re
from dataclasses import dataclass
import secrets
import time
from pathlib import Path
import subprocess
import urllib.request

BASE = "python:3.12-slim@sha256:c3d81d25b3154142b0b42eb1e61300024426268edeb5b5a26dd7ddf64d9daf28"
ORIGINAL_IMAGES = (
    "quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e",
    "quay.io/minio/mc:RELEASE.2025-08-13T08-35-41Z@sha256:a7fe349ef4bd8521fb8497f55c6042871b2ae640607cf99d9bede5e9bdf11727",
)
ASSETS = {
    "minio": {
        "release": "RELEASE.2025-09-07T16-13-09Z",
        "sha256": "7c5bd8512c6e966455b1d198209358b2d191c77a83ab377c4073281065fb855f",
    },
    "mc": {
        "release": "RELEASE.2025-08-13T08-35-41Z",
        "sha256": "01f866e9c5f9b87c2b09116fa5d7c06695b106242d829a8bb32990c00312e891",
    },
}


def asset_url(name: str) -> str:
    release = ASSETS[name]["release"]
    return f"https://github.com/minio/{name}/releases/download/{release}/{name}.linux-amd64.{release}"


def verify_binary(name: str, path: Path) -> None:
    if sha256(path.read_bytes()).hexdigest() != ASSETS[name]["sha256"]:
        raise ValueError(f"Official {name} binary checksum mismatch")


LOG_LIMIT = 16384


class AssemblyError(RuntimeError):
    """Failure with bounded diagnostics and no subprocess credential arguments."""


@dataclass
class CommandResult:
    stdout: str
    exit_code: int | None
    timed_out: bool = False


class CommandRunner:
    def __init__(self, output: Path):
        self.output = output
        self.private: list[str] = []
        self.environment = os.environ.copy()
        identity = secrets.token_hex(6)
        self.server = "citeframe-ci-minio-server-" + identity
        self.client = "citeframe-ci-minio-client-" + identity
        self.containers_used = False

    def sanitize(self, value) -> str:
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        value = str(value or "")
        for secret in sorted(self.private, key=len, reverse=True):
            value = value.replace(secret, "<redacted>")
        encoded = value.encode("utf-8")
        if len(encoded) > LOG_LIMIT:
            value = encoded[:LOG_LIMIT].decode("utf-8", errors="ignore") + "\n<truncated>"
        return value

    def invoke(self, label, command, *, timeout=900, allow_unavailable=False) -> CommandResult:
        if command[:2] == ["docker", "run"]:
            command = list(command)
            if "--name" not in command:
                command[2:2] = ["--name", self.client]
            self.containers_used = True
        timed_out, code = False, None
        try:
            result = subprocess.run(command, text=True, capture_output=True, timeout=timeout,
                                    env=self.environment)
            stdout, stderr, code = result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired as error:
            stdout, stderr, timed_out = error.stdout, error.stderr, True
        except subprocess.CalledProcessError as error:
            stdout, stderr, code = error.stdout, error.stderr, error.returncode
        except OSError as error:
            stdout, stderr = "", self.sanitize(error)
        stdout, stderr = self.sanitize(stdout), self.sanitize(stderr)
        (self.output / f"{label}.out").write_text(stdout, encoding="utf-8")
        (self.output / f"{label}.err").write_text(stderr, encoding="utf-8")
        if code != 0 or timed_out:
            failure = {"stage": label, "exitCode": code, "timedOut": timed_out,
                       "timeoutSeconds": timeout, "status": "unavailable" if allow_unavailable else "failed",
                       "command": [self.sanitize(arg) for arg in command]}
            (self.output / f"{label}.failure.json").write_text(json.dumps(failure, indent=2), encoding="utf-8")
            if not allow_unavailable:
                reason = "timed out" if timed_out else f"failed (exit {code})"
                raise AssemblyError(f"{label} {reason}; see bounded diagnostics") from None
        return CommandResult(stdout.strip(), code, timed_out)

    def run(self, label, command):
        return self.invoke(label, command).stdout

    def cleanup(self) -> list[str]:
        errors = []
        if self.containers_used:
            for kind, name in (("client", self.client), ("server", self.server)):
                try:
                    self.invoke(f"cleanup-{kind}", ["docker", "rm", "-fv", name],
                                timeout=30, allow_unavailable=True)
                    remaining = self.invoke(f"remaining-{kind}", ["docker", "container", "ls", "-aq",
                                            "--filter", f"name=^/{name}$"], timeout=30, allow_unavailable=True)
                    if remaining.exit_code != 0 or remaining.timed_out or remaining.stdout:
                        errors.append(f"{kind} container absence unverified")
                except Exception as error:
                    errors.append(self.sanitize(f"{kind} cleanup failed: {type(error).__name__}: {error}"))
        (self.output / "cleanup.json").write_text(json.dumps({"passed": not errors, "errors": errors}, indent=2), encoding="utf-8")
        return errors


def assemble(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    runner = CommandRunner(output)
    failure, record = None, None
    try:
        record = _assemble(output, runner)
    except Exception as error:
        failure = runner.sanitize(f"{type(error).__name__}: {error}")
    try:
        cleanup_errors = runner.cleanup()
    except Exception as error:
        cleanup_errors = [runner.sanitize(f"cleanup evidence failure: {type(error).__name__}: {error}")]
    if failure or cleanup_errors:
        metadata = {"status": "failed", "primaryFailure": failure, "cleanupErrors": cleanup_errors}
        (output / "assembly-failure.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        raise AssemblyError(failure or "; ".join(cleanup_errors)) from None
    (output / "assembly.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def _assemble(output: Path, runner: "CommandRunner") -> dict:
    record = {"scope": "ci-dependency-substitution", "originalImageIdentity": False,
              "base": BASE, "assets": ASSETS, "assetUrls": {name: asset_url(name) for name in ASSETS},
              "originalImages": list(ORIGINAL_IMAGES), "architecture": "linux/amd64",
              "assemblySourceSHA256": sha256(Path(__file__).read_bytes()).hexdigest(), "images": {}}

    run = runner.run

    record["originalPulls"] = []
    for index, original in enumerate(ORIGINAL_IMAGES):
        pulled = runner.invoke(f"original-pull-{index}", ["docker", "pull", original],
                               timeout=120, allow_unavailable=True)
        record["originalPulls"].append({"image": original, "exitCode": pulled.exit_code,
                                         "timedOut": pulled.timed_out})
    if all(item["exitCode"] == 0 and not item["timedOut"] for item in record["originalPulls"]):
        record.update(scope="original-pinned-images", originalImageIdentity=True)
        for target, original in zip(("server", "client"), ORIGINAL_IMAGES):
            image = run(f"original-inspect-{target}", ["docker", "image", "inspect", "--format", "{{.Id}}", original])
            record["images"][target] = image
            (output / f"{target}.iid").write_text(image, encoding="utf-8")
        return record

    for name, asset in ASSETS.items():
        urllib.request.urlretrieve(asset_url(name), output / name)
        verify_binary(name, output / name)
        urllib.request.urlretrieve(
            f"https://raw.githubusercontent.com/minio/{name}/{asset['release']}/LICENSE",
            output / f"LICENSE.{name}",
        )
    notices = ["MinIO and mc: Copyright MinIO, Inc.; AGPL-3.0. Unmodified official binaries."]
    for name, asset in ASSETS.items():
        notices.append(f"{name} binary: {asset_url(name)}")
        notices.append(f"{name} corresponding source: https://github.com/minio/{name}/tree/{asset['release']}")
    (output / "NOTICE").write_text("\n".join(notices) + "\n", encoding="utf-8")
    dockerfile = f"""FROM {BASE} AS binaries
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY minio mc /usr/local/bin/
RUN chmod 0755 /usr/local/bin/minio /usr/local/bin/mc
COPY LICENSE.minio LICENSE.mc NOTICE /licenses/
LABEL org.opencontainers.image.licenses="AGPL-3.0" org.opencontainers.image.description="Citeframe CI dependency assembly; unmodified official MinIO binaries"
FROM binaries AS server
ENTRYPOINT ["/usr/local/bin/minio"]
FROM binaries AS client
ENTRYPOINT ["/usr/local/bin/mc"]
"""
    (output / "Dockerfile").write_text(dockerfile, encoding="utf-8")

    for target, binary in (("server", "minio"), ("client", "mc")):
        iid = output / f"{target}.iid"
        run(f"build-{target}", ["docker", "build", "--platform", "linux/amd64", "--target", target,
                                "--iidfile", str(iid), str(output)])
        image = iid.read_text().strip()
        run(f"inspect-{target}", ["docker", "image", "inspect", image])
        actual = run(f"checksum-{target}", ["docker", "run", "--rm", "--entrypoint", "sha256sum",
                                           image, f"/usr/local/bin/{binary}"])
        assert actual.split()[0] == ASSETS[binary]["sha256"], "Assembled binary changed"
        version = run(f"version-{target}", ["docker", "run", "--rm", image, "--version"])
        assert ASSETS[binary]["release"] in version, "Unexpected binary version"
        record["images"][target] = image
    container = runner.server
    user, password = secrets.token_hex(12), secrets.token_hex(20)
    runner.private = [user, password]
    runner.environment.update(MINIO_ROOT_USER=user, MINIO_ROOT_PASSWORD=password)
    run("health-start", ["docker", "run", "-d", "--name", container,
        "-e", "MINIO_ROOT_USER", "-e", "MINIO_ROOT_PASSWORD",
        "--health-cmd", "curl -f http://127.0.0.1:9000/minio/health/live",
        "--health-interval", "1s", "--health-timeout", "5s", "--health-retries", "30",
        record["images"]["server"], "server", "/data"])
    for _ in range(40):
        status = run("health-status", ["docker", "inspect", "--format",
                     "{{.State.Health.Status}}", container])
        if status == "healthy":
            break
        time.sleep(1)
    else:
        raise RuntimeError("Assembled MinIO failed the production curl healthcheck")
    run("mc-backup-restore", ["docker", "run", "--rm", "--user", "1001:1001",
        "-e", "MC_CONFIG_DIR=/tmp/mc-config", "--network", f"container:{container}",
        "-e", "MINIO_ROOT_USER", "-e", "MINIO_ROOT_PASSWORD",
        "--entrypoint", "/bin/sh", record["images"]["client"], "-ec",
        'mc alias set ci http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null; '
        'mc mb ci/assembly-source ci/assembly-restored; '
        'printf assembly-fixture > /tmp/object; mc cp /tmp/object ci/assembly-source/object; '
        'mc mirror --overwrite ci/assembly-source /tmp/backup; cmp /tmp/object /tmp/backup/object; '
        'mc mirror --overwrite --remove /tmp/backup ci/assembly-restored; '
        'mc cat ci/assembly-restored/object > /tmp/restored; cmp /tmp/object /tmp/restored'])
    record.update(healthcheckPassed=True, backupRestoreOperationPassed=True)
    record["files"] = {p.name: sha256(p.read_bytes()).hexdigest() for p in output.iterdir()
                       if p.name in {"Dockerfile", "LICENSE.minio", "LICENSE.mc", "NOTICE"}}
    return record


def storage_identity(record: dict) -> dict:
    expected = {"base": BASE, "assets": ASSETS, "assetUrls": {name: asset_url(name) for name in ASSETS},
                "originalImages": list(ORIGINAL_IMAGES), "architecture": "linux/amd64",
                "assemblySourceSHA256": sha256(Path(__file__).read_bytes()).hexdigest()}
    if any(record.get(key) != value for key, value in expected.items()):
        raise ValueError("Storage source or fixed pins differ from the comparison helper")
    original = record.get("originalImageIdentity")
    if type(original) is not bool:
        raise ValueError("Missing storage identity mode")
    scope = "original-pinned-images" if original else "ci-dependency-substitution"
    if record.get("scope") != scope:
        raise ValueError("Inconsistent storage identity scope")
    images = record.get("images", {})
    if set(images) != {"server", "client"} or any(not re.fullmatch(r"sha256:[0-9a-f]{64}", image) for image in images.values()):
        raise ValueError("Missing exact storage image IDs")
    files = record.get("files", {})
    if not original and (set(files) != {"Dockerfile", "LICENSE.minio", "LICENSE.mc", "NOTICE"}
                         or any(not re.fullmatch(r"[0-9a-f]{64}", digest) for digest in files.values())):
        raise ValueError("Missing assembly file identity")
    return {**expected, "scope": scope, "originalImageIdentity": original, "images": images, "files": files}


def compare_storage_runs(runs: list[Path], output: Path) -> dict:
    report = {"passed": False, "scope": "storage-dependency-identity-comparison"}
    try:
        if len(runs) != 3 or len({path.resolve() for path in runs}) != 3:
            raise ValueError("Three distinct baseline, positive, and serial run directories are required")
        identities = [storage_identity(json.loads((path / "minio-assembly/assembly.json").read_text())) for path in runs]
        if not all(identity == identities[0] for identity in identities[1:]):
            raise ValueError("Baseline, positive, and serial storage image or assembly identities differ")
        report.update(passed=True, identity=identities[0])
    except (OSError, ValueError, TypeError) as error:
        report["error"] = type(error).__name__ + ": storage identity comparison failed"
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        raise AssemblyError(report["error"]) from None
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compare", type=Path, nargs=3, metavar=("BASELINE", "POSITIVE", "SERIAL"))
    args = parser.parse_args()
    result = (compare_storage_runs(args.compare, args.output.resolve()) if args.compare
              else assemble(args.output.resolve()))
    print(json.dumps(result, indent=2))
