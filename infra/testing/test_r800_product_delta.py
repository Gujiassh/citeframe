"""The integrated deployment whitelist rejects unreviewed product drift."""
import copy
import unittest
from r800_product_delta import ARCHITECTURE_BASE, assert_exact_delta


class ProductDeltaTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {"schemaVersion": 1, "architectureBase": ARCHITECTURE_BASE,
                         "files": [{"path": "apps/api/src/known.py", "integratedBlob": "a" * 40}]}
        self.observed = {"apps/api/src/known.py": "a" * 40}

    def test_exact_delta(self):
        assert_exact_delta(self.manifest, self.observed)

    def test_unknown_path_fails(self):
        with self.assertRaises(AssertionError):
            assert_exact_delta(self.manifest, {**self.observed, "apps/api/src/unknown.py": "a" * 40})

    def test_changed_known_blob_fails(self):
        with self.assertRaises(AssertionError):
            assert_exact_delta(self.manifest, {"apps/api/src/known.py": "b" * 40})

    def test_missing_path_fails(self):
        with self.assertRaises(AssertionError):
            assert_exact_delta(self.manifest, {})

    def test_changed_baseline_fails(self):
        changed = {**self.manifest, "architectureBase": "b" * 40}
        with self.assertRaises(AssertionError):
            assert_exact_delta(changed, self.observed)

    def test_duplicate_path_fails(self):
        changed = copy.deepcopy(self.manifest)
        changed["files"] *= 2
        with self.assertRaises(AssertionError):
            assert_exact_delta(changed, self.observed)
