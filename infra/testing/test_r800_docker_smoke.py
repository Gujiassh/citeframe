"""Negative controls for evidence integrity; no Docker or product imports required."""
import ast
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r800_docker_probe import assert_attempts
from r800_docker_smoke import free_ports, official_mc_mirror, scrub


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

    def test_official_mirror_preserves_exact_product_pin(self):
        root = Path(__file__).resolve().parents[2]
        script = (root / "infra/scripts/compose-common.sh").read_text()
        mirror = official_mc_mirror(script)
        self.assertTrue(mirror.startswith("quay.io/minio/mc:"))
        self.assertIn(mirror.removeprefix("quay.io/"), script)
        for invalid in ("", "MINIO_MC_IMAGE=${MINIO_MC_IMAGE:-minio/mc:latest}"):
            with self.subTest(script=invalid), self.assertRaises(ValueError):
                official_mc_mirror(invalid)

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
        self.assertEqual(len(polls), 2)
        self.assertTrue(all(not any(k.arg == "processor" for k in node.keywords) for node in polls))


if __name__ == "__main__":
    unittest.main()
