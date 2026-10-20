"""Injected CI assembly failures and exact storage-identity controls; no Docker/network."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_minio import (ASSETS, LOG_LIMIT, AssemblyError, assemble, asset_url,
                      compare_storage_runs, verify_binary)


class DockerFixture:
    def __init__(self, fault=None, cleanup_failure=False, original=False):
        self.fault, self.cleanup_failure, self.original = fault, cleanup_failure, original
        self.calls = []
        self.credentials = []
        self.images = {"server": "sha256:" + "1" * 64, "client": "sha256:" + "2" * 64}

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        code, stdout, stderr = 0, "", ""
        if command[1] == "pull":
            if self.fault == "pull-timeout" and len(self.calls) == 1:
                raise subprocess.TimeoutExpired(command, 120, output=b"partial registry output", stderr=b"registry timeout")
            code = 0 if self.original else 1
        elif command[1] == "build":
            if self.fault == "build-timeout":
                raise subprocess.TimeoutExpired(command, 900, output=b"partial build", stderr=b"build stalled")
            if self.fault == "build":
                code = 1
            target = command[command.index("--target") + 1]
            Path(command[command.index("--iidfile") + 1]).write_text(self.images[target])
        elif "{{.Id}}" in command:
            stdout = self.images["server" if "/minio:" in command[-1] else "client"]
        elif "sha256sum" in command:
            stdout = ("0" * 64 if self.fault == "checksum" else ASSETS[command[-1].rsplit("/", 1)[-1]]["sha256"]) + "  binary"
        elif command[-1] == "--version":
            stdout = "wrong release" if self.fault == "version" else ASSETS["minio" if command[-2] == self.images["server"] else "mc"]["release"]
        elif "{{.State.Health.Status}}" in command:
            stdout = "starting" if self.fault == "health" else "healthy"
        elif command[1] == "run" and ("--health-cmd" in command or command[-2] == "-ec"):
            values = kwargs["env"]
            self.credentials = [values["MINIO_ROOT_USER"], values["MINIO_ROOT_PASSWORD"]]
            # A failed assertion uses a generic message so credentials never enter test output.
            if any(secret in str(command) for secret in self.credentials):
                raise AssertionError("Probe credential reached argv")
            if "--health-cmd" in command and self.fault == "health-start":
                return subprocess.CompletedProcess(command, 1, self.credentials[0], self.credentials[1])
            if command[-2] == "-ec":
                if self.fault == "mc-timeout":
                    partial = (self.credentials[0] + " " + self.credentials[1] + " " + "x" * (LOG_LIMIT * 2)).encode()
                    raise subprocess.TimeoutExpired(command, 900, output=partial, stderr=partial)
                if self.fault == "mc":
                    raise subprocess.CalledProcessError(9, command, output=self.credentials[0], stderr=self.credentials[1])
        elif command[1:3] == ["rm", "-fv"]:
            if self.cleanup_failure == "timeout":
                raise subprocess.TimeoutExpired(command, 30, output=" ".join(self.credentials).encode(), stderr=b"cleanup stalled")
            code = 1 if self.cleanup_failure else 0
        elif command[1:3] == ["container", "ls"]:
            stdout = "remaining-container" if self.cleanup_failure else ""
        return subprocess.CompletedProcess(command, code, stdout, stderr)


def download_fixture(url, destination):
    Path(destination).write_bytes(b"fixture")


class AssemblyTests(unittest.TestCase):
    def exercise(self, output, docker):
        with patch("ci_minio.urllib.request.urlretrieve", side_effect=download_fixture), patch("ci_minio.verify_binary"), patch("ci_minio.subprocess.run", side_effect=docker), patch("ci_minio.time.sleep"):
            return assemble(output)

    def assert_both_removed(self, docker):
        removed = [command[-1] for command in docker.calls if command[1:3] == ["rm", "-fv"]]
        self.assertEqual(len(removed), 2)
        self.assertTrue(any("-client-" in name for name in removed))
        self.assertTrue(any("-server-" in name for name in removed))
        checked = [command[-1].removeprefix("name=^/").removesuffix("$") for command in docker.calls if command[1:3] == ["container", "ls"]]
        self.assertEqual(removed, checked)
        self.assertTrue(all("--name" in command for command in docker.calls if command[1] == "run"))

    def test_tampered_download_stops_before_build(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "assembly"
            with patch("ci_minio.urllib.request.urlretrieve", side_effect=download_fixture), patch("ci_minio.subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "unavailable")) as docker:
                with self.assertRaisesRegex(AssemblyError, "checksum mismatch"):
                    assemble(output)
                self.assertTrue(all(call.args[0][1] == "pull" for call in docker.call_args_list))
                self.assertFalse((output / "assembly.json").exists())

    def test_both_fixed_assets_reject_wrong_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "binary"
            path.write_bytes(b"other release")
            for name in ASSETS:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    verify_binary(name, path)

    def test_official_asset_urls_match_product_release_pins(self):
        root = Path(__file__).resolve().parents[2]
        for name, path in (("minio", "infra/docker/compose.deploy.yml"), ("mc", "infra/scripts/compose-common.sh")):
            self.assertIn(ASSETS[name]["release"], (root / path).read_text())
            self.assertEqual(asset_url(name), f"https://github.com/minio/{name}/releases/download/{ASSETS[name]['release']}/{name}.linux-amd64.{ASSETS[name]['release']}")

    def test_accessible_originals_preserve_image_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            docker = DockerFixture(original=True)
            result = self.exercise(Path(directory) / "assembly", docker)
            self.assertTrue(result["originalImageIdentity"])
            self.assertFalse(any(command[1] in {"build", "run"} for command in docker.calls))
            self.assertEqual(result["scope"], "original-pinned-images")
            self.assertTrue(all(item["exitCode"] == 0 and not item["timedOut"] for item in result["originalPulls"]))

    def test_original_pull_timeout_is_recorded_and_falls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "assembly"
            docker = DockerFixture("pull-timeout")
            result = self.exercise(output, docker)
            self.assertFalse(result["originalImageIdentity"])
            self.assertTrue(result["originalPulls"][0]["timedOut"])
            self.assertEqual(len(result["originalPulls"]), 2)
            self.assertEqual((output / "original-pull-0.out").read_text(), "partial registry output")
            self.assertTrue(json.loads((output / "original-pull-0.failure.json").read_text())["timedOut"])
            self.assert_both_removed(docker)

    def test_fatal_failures_never_emit_success_and_clean_up_named_probes(self):
        for fault in ("build", "build-timeout", "checksum", "version", "health", "health-start", "mc", "mc-timeout"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "assembly"
                docker = DockerFixture(fault)
                with self.assertRaises(AssemblyError) as captured:
                    self.exercise(output, docker)
                self.assertFalse((output / "assembly.json").exists())
                self.assertTrue((output / "assembly-failure.json").exists())
                if fault not in {"build", "build-timeout"}:
                    self.assert_both_removed(docker)
                diagnostics = "".join(traceback.format_exception(captured.exception)) + repr(captured.exception) + "".join(p.read_text() for p in output.iterdir() if p.suffix in {".json", ".out", ".err"})
                self.assertFalse(any(secret in diagnostics for secret in docker.credentials), "Fixture credential leaked in exception or diagnostics")
                if fault == "mc-timeout":
                    for suffix in ("out", "err"):
                        log = (output / f"mc-backup-restore.{suffix}").read_text()
                        self.assertIn("<redacted>", log)
                        self.assertLessEqual(len(log.encode()), LOG_LIMIT + 20)
                    self.assertTrue(json.loads((output / "mc-backup-restore.failure.json").read_text())["timedOut"])

    def test_primary_timeout_survives_cleanup_failure(self):
        for cleanup_failure in (True, "timeout"):
            with self.subTest(cleanup=cleanup_failure), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "assembly"
                docker = DockerFixture("mc-timeout", cleanup_failure=cleanup_failure)
                with self.assertRaisesRegex(AssemblyError, "mc-backup-restore timed out") as captured:
                    self.exercise(output, docker)
                failure = json.loads((output / "assembly-failure.json").read_text())
                self.assertIn("mc-backup-restore timed out", failure["primaryFailure"])
                self.assertEqual(len(failure["cleanupErrors"]), 2)
                self.assert_both_removed(docker)
                self.assertFalse((output / "assembly.json").exists())
                diagnostics = "".join(traceback.format_exception(captured.exception)) + "".join(p.read_text() for p in output.iterdir() if p.suffix in {".json", ".out", ".err"})
                self.assertFalse(any(secret in diagnostics for secret in docker.credentials), "Fixture credential leaked during failed cleanup")
                if cleanup_failure == "timeout":
                    self.assertTrue(json.loads((output / "cleanup-client.failure.json").read_text())["timedOut"])
                    self.assertTrue(json.loads((output / "cleanup-server.failure.json").read_text())["timedOut"])

    def test_cleanup_failure_after_success_is_fatal(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "assembly"
            docker = DockerFixture(cleanup_failure=True)
            with self.assertRaisesRegex(AssemblyError, "absence unverified"):
                self.exercise(output, docker)
            self.assert_both_removed(docker)
            self.assertFalse((output / "assembly.json").exists())

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory, patch("ci_minio.urllib.request.urlretrieve") as download:
            with self.assertRaises(FileExistsError):
                assemble(Path(directory))
            download.assert_not_called()

    def test_three_run_comparison_requires_exact_ids_source_pins_and_packaging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = self.exercise(root / "reference", DockerFixture())
            runs = [root / name for name in ("baseline", "positive", "serial")]
            for run in runs:
                (run / "minio-assembly").mkdir(parents=True)
                (run / "minio-assembly/assembly.json").write_text(json.dumps(reference))
            report = root / "comparison.json"
            self.assertTrue(compare_storage_runs(runs, report)["passed"])
            for field, replacement in (("images", {"server": "sha256:" + "3" * 64, "client": reference["images"]["client"]}),
                                       ("files", {**reference["files"], "NOTICE": "4" * 64}),
                                       ("assemblySourceSHA256", "5" * 64), ("base", "other-base"),
                                       ("assets", {}), ("assetUrls", {}), ("originalImages", []),
                                       ("originalImageIdentity", True)):
                with self.subTest(field=field):
                    changed = deepcopy(reference)
                    changed[field] = replacement
                    (runs[1] / "minio-assembly/assembly.json").write_text(json.dumps(changed))
                    with self.assertRaises(AssemblyError):
                        compare_storage_runs(runs, report)
                    self.assertFalse(json.loads(report.read_text())["passed"])
            (runs[1] / "minio-assembly/assembly.json").unlink()
            with self.assertRaises(AssemblyError):
                compare_storage_runs(runs, report)
            with self.assertRaises(AssemblyError):
                compare_storage_runs([runs[0]] * 3, report)


if __name__ == "__main__":
    unittest.main()
