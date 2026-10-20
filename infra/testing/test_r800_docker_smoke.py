"""Negative controls for evidence integrity; no Docker or product imports required."""
import ast
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r800_docker_probe import assert_attempts
from r800_docker_smoke import free_ports, default_mc_image, scrub, main
from r800_docker_registry import (REDIS_DIGEST, HISTORICAL_REDIS_IMAGE, OFFICIAL_REDIS_IMAGE,
                                  historical_redis_source, redis_alias_provenance, configure_ci_override)


class EvidenceContractTests(unittest.TestCase):
    def test_attempt_requires_expected_real_worker_and_success(self):
        good = [{"status": "succeeded", "worker_instance_id": "worker-1:research:1"}]
        assert_attempts(good, "worker-1")
        for bad in ([], [{"status": "running", "worker_instance_id": "worker-1:research:1"}],
                    [{"status": "succeeded", "worker_instance_id": "r800-acceptance-cli"}]):
            with self.subTest(attempts=bad), self.assertRaises(AssertionError):
                assert_attempts(bad, "worker-1")

    def test_secret_redaction_handles_overlapping_values(self):
        self.assertEqual(scrub("abc abcdef", ["abc", "abcdef"]), "<redacted> <redacted>")

    def test_default_image_preserves_exact_product_pin(self):
        root = Path(__file__).resolve().parents[2]
        script = (root / "infra/scripts/compose-common.sh").read_text()
        mirror = default_mc_image(script)
        self.assertTrue(mirror.startswith("quay.io/minio/mc:"))
        self.assertIn("MINIO_MC_IMAGE=${MINIO_MC_IMAGE:-" + mirror + "}", script)
        for invalid in ("", "MINIO_MC_IMAGE=${MINIO_MC_IMAGE:-minio/mc:latest}"):
            with self.subTest(script=invalid), self.assertRaises(ValueError):
                default_mc_image(invalid)

    def test_harness_only_injects_client_for_explicit_ci_assembly(self):
        tree = ast.parse(Path(__file__).with_name("r800_docker_smoke.py").read_text())
        injected = [node for node in ast.walk(tree) if isinstance(node, ast.Subscript)
                    and isinstance(node.ctx, ast.Store)
                    and isinstance(node.slice, ast.Constant)
                    and node.slice.value == "MINIO_MC_IMAGE"]
        self.assertEqual(len(injected), 1)
        guards = [node for node in ast.walk(tree) if isinstance(node, ast.If)
                  and ast.unparse(node.test) == "args.ci_minio_assembly"]
        self.assertEqual(len(guards), 1)
        self.assertIn(injected[0], list(ast.walk(guards[0])))
        assignment = next(node for node in ast.walk(guards[0]) if isinstance(node, ast.Assign)
                          and injected[0] in node.targets)
        self.assertEqual(ast.unparse(assignment.value), "dependency_assembly['images']['client']")
        self.assertTrue(any(isinstance(node, ast.Assert)
                            and ast.unparse(node.test) == "'MINIO_MC_IMAGE' not in env"
                            for node in ast.walk(tree)))
        removals = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute) and node.func.attr == "pop"
                    and node.args and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == "MINIO_MC_IMAGE"]
        self.assertEqual(len(removals), 1)

    def test_workflow_tracks_common_deployment_script(self):
        root = Path(__file__).resolve().parents[2]
        workflow = (root / ".github/workflows/r800-deployment.yml").read_text()
        self.assertIn("- 'infra/scripts/compose-common.sh'", workflow)

    def test_bound_ports_are_unique(self):
        ports = free_ports(3)
        self.assertEqual(len(set(ports)), 3)
        self.assertTrue(all(0 < port < 65536 for port in ports))

    def test_new_workload_never_runs_processor_in_harness(self):
        path = Path(__file__).with_name("r800_docker_probe.py")
        tree = ast.parse(path.read_text())
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        self.assertFalse(any(isinstance(node.func, ast.Attribute) and node.func.attr == "process_one"
                             for node in calls))
        polls = [node for node in calls if isinstance(node.func, ast.Name)
                 and node.func.id == "_process_until"]
        self.assertEqual(len(polls), 1)
        self.assertFalse(any(isinstance(node.func, ast.Name) and node.func.id == "_submit_plan" for node in calls))
        self.assertTrue(all(not any(k.arg == "processor" for k in node.keywords) for node in polls))


class RegistryOriginTests(unittest.TestCase):
    def test_frozen_historical_source_retains_the_pinned_redis_manifest(self):
        root = Path(__file__).resolve().parents[2]
        deploy = subprocess.check_output(["git", "show",
            "50af19dc3b79fbb677d9ac66c005b77cbe76f3d9:infra/docker/compose.deploy.yml"], cwd=root).decode()
        self.assertEqual(historical_redis_source(deploy), HISTORICAL_REDIS_IMAGE)

    def test_alias_rejects_changed_source_origin_tag_digest_or_duplicate(self):
        for image in (OFFICIAL_REDIS_IMAGE, HISTORICAL_REDIS_IMAGE.replace("7.4.9", "7.4.8"),
                      HISTORICAL_REDIS_IMAGE.replace(REDIS_DIGEST, "sha256:" + "0" * 64)):
            with self.subTest(image=image), self.assertRaises(ValueError):
                historical_redis_source("  redis:\n    image: " + image + "\n")
        deploy = "  redis:\n    image: " + HISTORICAL_REDIS_IMAGE + "\n"
        with self.assertRaises(ValueError):
            historical_redis_source(deploy + deploy)
        with self.assertRaises(ValueError):
            historical_redis_source("")
        with self.assertRaises(ValueError):
            redis_alias_provenance(OFFICIAL_REDIS_IMAGE, {})

    def test_pulled_identity_requires_exact_official_repository_and_digest(self):
        for repository in ("redis", "docker.io/library/redis"):
            digest = repository + "@" + REDIS_DIGEST
            evidence = redis_alias_provenance(HISTORICAL_REDIS_IMAGE,
                {"Id": "sha256:" + "1" * 64, "RepoDigests": [digest]})
            self.assertEqual(evidence["aliasImage"], OFFICIAL_REDIS_IMAGE)
            self.assertEqual(evidence["sourceImage"], HISTORICAL_REDIS_IMAGE)
            self.assertEqual(evidence["repoDigests"], [digest])
        for inspection in (
            {"Id": "sha256:" + "1" * 64, "RepoDigests": ["other/redis@" + REDIS_DIGEST]},
            {"Id": "sha256:" + "1" * 64, "RepoDigests": ["redis@sha256:" + "0" * 64]},
            {"Id": "sha256:" + "1" * 64, "RepoDigests": []},
            {"Id": "sha256:" + "1" * 64, "RepoDigests": None},
            {"Id": "not-an-image-id", "RepoDigests": ["redis@" + REDIS_DIGEST]},
        ):
            with self.subTest(inspection=inspection), self.assertRaises(ValueError):
                redis_alias_provenance(HISTORICAL_REDIS_IMAGE, inspection)

    def test_generated_override_binds_compose_and_scripts_in_both_minio_modes(self):
        source = Path(__file__).resolve().parents[1] / "docker/compose.r800.yml"
        original = source.read_bytes()
        for redis_alias, minio_image in ((True, None), (True, "sha256:" + "2" * 64),
                                        (False, "sha256:" + "2" * 64)):
            with self.subTest(redis_alias=redis_alias, minio_image=minio_image), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                env = {"COMPOSE_OVERRIDE_FILE": str(source)}
                if minio_image is not None:
                    env["MINIO_MC_IMAGE"] = "sha256:" + "3" * 64
                compose = ["docker-compose", "-f", "unchanged-production-compose", "-f", str(source)]
                configure_ci_override(source, output, compose, env,
                    redis_origin_alias=redis_alias, minio_image=minio_image)
                override = output / "compose.ci.yml"
                self.assertEqual(env["COMPOSE_OVERRIDE_FILE"], str(override))
                self.assertEqual(compose, ["docker-compose", "-f", "unchanged-production-compose", "-f", str(override)])
                expected = source.read_text()
                if redis_alias:
                    expected += "\n  redis:\n    image: " + OFFICIAL_REDIS_IMAGE + "\n"
                if minio_image is not None:
                    expected += "\n  minio:\n    image: " + minio_image + "\n"
                    self.assertEqual(env["MINIO_MC_IMAGE"], "sha256:" + "3" * 64)
                else:
                    self.assertNotIn("MINIO_MC_IMAGE", env)
                self.assertEqual(override.read_text(), expected)
                self.assertEqual(source.read_bytes(), original)

    def test_original_mode_keeps_source_override_and_collision_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "compose.r800.yml"
            source.write_text("services:\n  redis:\n    image: existing\n")
            compose, env = ["docker-compose", "-f", str(source)], {"COMPOSE_OVERRIDE_FILE": str(source)}
            configure_ci_override(source, root, compose, env)
            self.assertFalse((root / "compose.ci.yml").exists())
            self.assertEqual(env["COMPOSE_OVERRIDE_FILE"], str(source))
            self.assertEqual(compose[-1], str(source))
            with self.assertRaises(ValueError):
                configure_ci_override(source, root, compose, env, redis_origin_alias=True)
            self.assertFalse((root / "compose.ci.yml").exists())

    def test_alias_flag_rejects_product_before_any_runtime_command(self):
        with patch.object(sys, "argv", ["r800", "--source", ".", "--output", "unused", "--ci-redis-origin-alias"]), \
                patch("r800_docker_smoke.subprocess.run") as run:
            with self.assertRaises(SystemExit) as error:
                main()
            self.assertEqual(error.exception.code, 2)
            run.assert_not_called()
        workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/r800-deployment.yml").read_text()
        alias_runs = [line for line in workflow.splitlines() if "--ci-redis-origin-alias" in line]
        self.assertEqual(len(alias_runs), 1)
        self.assertIn("--source baseline", alias_runs[0])
        self.assertIn("--historical-scenarios-only", alias_runs[0])

    def test_product_uses_official_origins_with_unchanged_pins(self):
        root = Path(__file__).resolve().parents[2]
        web = (root / "infra/docker/Dockerfile.web").read_text().splitlines()
        node = "docker.io/library/node:22-bookworm-slim@sha256:f86be15afa9a8277608e141ce2a8aa55d3d9c40845921b8511f4fb7897be2554"
        self.assertEqual([line for line in web if line.startswith("FROM ")],
                         ["FROM " + node + " AS build", "FROM " + node + " AS runtime"])
        deploy = (root / "infra/docker/compose.deploy.yml").read_text()
        self.assertIn("  redis:\n    image: " + OFFICIAL_REDIS_IMAGE + "\n", deploy)


if __name__ == "__main__":
    unittest.main()
