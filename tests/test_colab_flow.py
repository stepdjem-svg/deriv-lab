"""Simulates the whole Colab life cycle with a fake Colab and a local 'GitHub':
unzip -> first push -> Colab reset (all local files lost) -> clone back -> journal and data intact."""
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def install_fake_colab(secrets):
    google = types.ModuleType("google")
    colab = types.ModuleType("google.colab")
    colab.userdata = types.SimpleNamespace(get=lambda k: secrets[k])
    colab.drive = types.SimpleNamespace(mount=lambda p: None)
    google.colab = colab
    sys.modules["google"], sys.modules["google.colab"] = google, colab


class ColabFlowTests(unittest.TestCase):
    def test_setup_reset_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            remote = base / "remote.git"
            subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)
            data = base / "drive" / "deriv-lab-data"
            os.environ["DERIV_LAB_DATA"] = str(data)
            install_fake_colab({"GITHUB_TOKEN": "ghp_FAKE", "GITHUB_REPO": str(remote)})
            from lab import colab, selftest
            from lab.journal import Journal
            from lab.storage import Checkpoint

            work = base / "content" / "deriv-lab"
            shutil.copytree(PROJECT, work, ignore=shutil.ignore_patterns(".git", "__pycache__"))

            ctx = colab.setup(repo_dir=work)  # first run: unzipped project, not yet on GitHub
            self.assertEqual(len([e for e in Journal(data).events() if e["type"] == "legacy"]), 8)
            Checkpoint("exp-1", data).save({"done": ["EURUSD"]})
            Journal(data).note("work done before the reset")
            colab.sync(ctx, "journal after experiment")
            self.assertTrue(selftest.run(ctx))

            shutil.rmtree(work)  # Colab reset: the VM disk is gone, Drive survives
            ctx2 = colab.setup(repo_dir=work)  # resume: clone from "GitHub", reuse Drive data
            self.assertTrue((work / "lab" / "journal.py").exists())
            self.assertEqual(Checkpoint("exp-1", data).load(), {"done": ["EURUSD"]})
            self.assertEqual(len([e for e in Journal(data).events() if e["type"] == "legacy"]), 8)  # not duplicated
            self.assertIn("work done before the reset", (work / "journal" / "JOURNAL.md").read_text())
            self.assertTrue(selftest.run(ctx2))
            os.environ.pop("DERIV_LAB_DATA", None)


if __name__ == "__main__":
    unittest.main()
