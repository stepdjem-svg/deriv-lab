import json
import tempfile
import unittest
from pathlib import Path

from lab.journal import Journal, RuleChangedAfterPreregistration, fingerprint

SEED = Path(__file__).resolve().parents[1] / "journal" / "seed.jsonl"


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.j = Journal(self.tmp.name)
        self.rule = {"symbol": "WLDGBP", "d": 1, "h": 5}
        self.crit = {"z_min": 3.0, "both_halves_above_break_even": True}

    def tearDown(self):
        self.tmp.cleanup()

    def test_full_cycle(self):
        pid = self.j.preregister("MR on WLD", "reversion survives 1-tick delay", self.rule, self.crit)
        self.assertEqual(len(self.j.open_preregistrations()), 1)
        rid = self.j.record_result(pid, "run-1", {"n": 300, "z": 1.2}, "not_supported", self.rule, self.crit)
        self.assertEqual((pid, rid), ("P001", "R001"))
        self.assertEqual(self.j.open_preregistrations(), [])
        self.assertEqual(self.j.verify(), [])

    def test_changed_rule_is_refused(self):
        pid = self.j.preregister("t", "h", self.rule, self.crit)
        with self.assertRaises(RuleChangedAfterPreregistration):
            self.j.record_result(pid, "r", {}, "supported", {**self.rule, "h": 10}, self.crit)
        with self.assertRaises(RuleChangedAfterPreregistration):
            self.j.record_result(pid, "r", {}, "supported", self.rule, {**self.crit, "z_min": 2.0})
        self.assertEqual([e for e in self.j.events() if e["type"] == "result"], [])

    def test_unknown_prereg_and_bad_verdict(self):
        with self.assertRaises(KeyError):
            self.j.record_result("P999", "r", {}, "supported", self.rule, self.crit)
        pid = self.j.preregister("t", "h", self.rule, self.crit)
        with self.assertRaises(ValueError):
            self.j.record_result(pid, "r", {}, "great_success", self.rule, self.crit)

    def test_key_order_does_not_change_fingerprint(self):
        self.assertEqual(fingerprint({"a": 1, "b": 2}, {"c": 3}), fingerprint({"b": 2, "a": 1}, {"c": 3}))

    def test_verify_detects_tampering(self):
        self.j.preregister("t", "h", self.rule, self.crit)
        text = self.j.path.read_text()
        self.j.path.write_text(text.replace('"d": 1', '"d": 2'))  # someone edits the stored rule
        self.assertEqual(len(self.j.verify()), 1)

    def test_seed_import_is_idempotent_and_valid(self):
        self.assertEqual(self.j.import_legacy(SEED), 8)
        self.assertEqual(self.j.import_legacy(SEED), 0)
        legacy = [e for e in self.j.events() if e["type"] == "legacy"]
        self.assertEqual(len({e["id"] for e in legacy}), 8)
        self.assertTrue(all(e["preregistered"] is False for e in legacy))

    def test_seed_file_is_well_formed(self):
        for line in SEED.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            for key in ("id", "title", "date", "summary", "verdict"):
                self.assertIn(key, rec)

    def test_markdown_render(self):
        self.j.import_legacy(SEED)
        pid = self.j.preregister("MR on WLD", "h", self.rule, self.crit)
        self.j.note("hello")
        md = self.j.render_markdown()
        self.assertIn("L002", md)
        self.assertIn(f"{pid} - MR on WLD", md)
        self.assertIn("OPEN", md)
        self.assertIn("hello", md)


if __name__ == "__main__":
    unittest.main()
