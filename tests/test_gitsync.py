import subprocess
import tempfile
import unittest
from pathlib import Path

from lab import gitsync
from lab.journal import Journal

TOKEN = "ghp_SECRETTOKEN123"


class GitSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.remote = base / "remote.git"
        subprocess.run(["git", "init", "--bare", "-b", "main", str(self.remote)], check=True, capture_output=True)
        self.work = base / "work"
        self.work.mkdir()
        self.data = base / "data"

    def tearDown(self):
        self.tmp.cleanup()

    def test_scrub_and_url(self):
        self.assertEqual(gitsync.scrub(f"fatal: {TOKEN} bad", TOKEN), "fatal: *** bad")
        url = gitsync.remote_url("me/deriv-lab", TOKEN)
        self.assertTrue(url.startswith("https://x-access-token:") and url.endswith("@github.com/me/deriv-lab.git"))
        self.assertEqual(gitsync.remote_url("/tmp/x.git", TOKEN), "/tmp/x.git")

    def test_first_push_then_clone_resume(self):
        (self.work / "a.txt").write_text("v1")
        self.assertEqual(gitsync.push(self.work, str(self.remote), TOKEN, "first"), "pushed")
        (self.work / "a.txt").write_text("v2")
        self.assertEqual(gitsync.push(self.work, str(self.remote), TOKEN, "second"), "pushed")
        # simulate Colab reset: fresh machine, clone from remote
        fresh = Path(self.tmp.name) / "fresh"
        gitsync.clone(str(self.remote), TOKEN, fresh)
        self.assertEqual((fresh / "a.txt").read_text(), "v2")
        log = subprocess.run(["git", "log", "--oneline"], cwd=fresh, capture_output=True, text=True).stdout
        self.assertEqual(len(log.strip().splitlines()), 2)  # history preserved

    def test_token_not_stored_in_git_config(self):
        (self.work / "a.txt").write_text("x")
        gitsync.push(self.work, str(self.remote), TOKEN, "m")
        cfg = (self.work / ".git" / "config").read_text()
        self.assertNotIn(TOKEN, cfg)

    def test_failed_push_error_hides_token(self):
        (self.work / "a.txt").write_text("x")
        bad_remote = f"file://{self.tmp.name}/does-not-exist.git"
        with self.assertRaises(RuntimeError) as cm:
            gitsync.push(self.work, bad_remote, TOKEN, "m")
        self.assertNotIn(TOKEN, str(cm.exception))

    def test_pull_updates_existing_clone(self):
        (self.work / "a.txt").write_text("v1")
        gitsync.push(self.work, str(self.remote), TOKEN, "first")
        other = Path(self.tmp.name) / "other"
        gitsync.clone(str(self.remote), TOKEN, other)
        (self.work / "a.txt").write_text("v2")
        gitsync.push(self.work, str(self.remote), TOKEN, "second")
        gitsync.pull(other, str(self.remote), TOKEN)
        self.assertEqual((other / "a.txt").read_text(), "v2")

    def test_sync_journal_exports_jsonl_and_markdown(self):
        j = Journal(self.data)
        j.note("first note")
        (self.work / "README.md").write_text("x")
        self.assertEqual(gitsync.sync_journal(self.work, str(self.remote), TOKEN, self.data), "pushed")
        self.assertTrue((self.work / "journal" / "journal.jsonl").exists())
        self.assertIn("first note", (self.work / "journal" / "JOURNAL.md").read_text())
        # second sync with no new data pushes nothing new but does not fail
        self.assertTrue(gitsync.sync_journal(self.work, str(self.remote), TOKEN, self.data).startswith("pushed"))

    def test_clone_does_not_keep_token_in_config(self):
        (self.work / "a.txt").write_text("x")
        gitsync.push(self.work, str(self.remote), TOKEN, "m")
        fresh = Path(self.tmp.name) / "fresh2"
        gitsync.clone(f"{self.remote}", TOKEN, fresh)
        self.assertNotIn(TOKEN, (fresh / ".git" / "config").read_text())
        # and for a real-looking repo name the stored URL is token-free
        self.assertEqual(gitsync.remote_url("me/deriv-lab", None), "https://github.com/me/deriv-lab.git")


if __name__ == "__main__":
    unittest.main()
