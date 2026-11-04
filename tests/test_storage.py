import os
import tempfile
import unittest
from pathlib import Path

from lab import paths
from lab.storage import (Checkpoint, append_jsonl, new_run_id, read_json, read_jsonl, save_artifact,
                         sha256_file, write_json_atomic)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_append_and_read(self):
        p = self.root / "a.jsonl"
        for i in range(5):
            append_jsonl(p, {"i": i, "txt": "é"})
        recs, skipped = read_jsonl(p)
        self.assertEqual([r["i"] for r in recs], list(range(5)))
        self.assertEqual(skipped, 0)

    def test_torn_last_line_is_skipped_and_next_append_is_not_lost(self):
        p = self.root / "t.jsonl"
        p.write_bytes(b'{"a": 1}\n{"b": 2')  # crash mid-write, no trailing newline
        recs, skipped = read_jsonl(p)
        self.assertEqual((len(recs), skipped), (1, 1))
        append_jsonl(p, {"c": 3})
        recs, skipped = read_jsonl(p)
        self.assertEqual(recs, [{"a": 1}, {"c": 3}])  # the new record survives; only the fragment is lost
        self.assertEqual(skipped, 1)

    def test_missing_file(self):
        self.assertEqual(read_jsonl(self.root / "nope.jsonl"), ([], 0))

    def test_atomic_write_leaves_no_tmp(self):
        p = self.root / "s.json"
        write_json_atomic(p, {"v": 1})
        write_json_atomic(p, {"v": 2})
        self.assertEqual(read_json(p), {"v": 2})
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_read_json_corrupt_returns_default(self):
        p = self.root / "bad.json"
        p.write_text("{not json")
        self.assertEqual(read_json(p, default="d"), "d")

    def test_checkpoint_resume(self):
        ck = Checkpoint("run-x", self.root)
        self.assertIsNone(ck.load())
        ck.save({"done": [1, 2]})
        self.assertEqual(Checkpoint("run-x", self.root).load(), {"done": [1, 2]})
        ck.clear()
        self.assertIsNone(Checkpoint("run-x", self.root).load())

    def test_artifact_copy_manifest_and_hash(self):
        src = self.root / "r.csv"
        src.write_text("a,b\n1,2\n")
        dest = save_artifact(src, "run-1", self.root)
        self.assertEqual(sha256_file(src), sha256_file(dest))
        recs, _ = read_jsonl(self.root / "artifacts" / "manifest.jsonl")
        self.assertEqual(recs[0]["name"], "r.csv")
        self.assertEqual(recs[0]["sha256"], sha256_file(src))

    def test_run_ids_unique_and_prefixed(self):
        ids = {new_run_id("audit") for _ in range(50)}
        self.assertEqual(len(ids), 50)
        self.assertTrue(all(i.startswith("audit-") for i in ids))


class PathsTests(unittest.TestCase):
    def test_env_override_and_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("DERIV_LAB_DATA")
            os.environ["DERIV_LAB_DATA"] = tmp
            try:
                self.assertEqual(paths.data_root(), Path(tmp))
                root = paths.ensure_dirs()
                for name in paths.SUBDIRS:
                    self.assertTrue((root / name).is_dir())
            finally:
                if old is None:
                    del os.environ["DERIV_LAB_DATA"]
                else:
                    os.environ["DERIV_LAB_DATA"] = old


if __name__ == "__main__":
    unittest.main()
