"""Negative controls for evidence integrity; no Docker or product imports required."""
import ast
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r800_docker_probe import assert_attempts
from r800_docker_smoke import free_ports, default_mc_image, scrub


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

    def test_harness_cannot_inject_minio_client_override(self):
        tree = ast.parse(Path(__file__).with_name("r800_docker_smoke.py").read_text())
        injected = [node for node in ast.walk(tree) if isinstance(node, ast.Subscript)
                    and isinstance(node.ctx, ast.Store)
                    and isinstance(node.slice, ast.Constant)
                    and node.slice.value == "MINIO_MC_IMAGE"]
        self.assertEqual(injected, [])
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


if __name__ == "__main__":
    unittest.main()
