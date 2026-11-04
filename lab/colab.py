"""One-call setup for Google Colab. Idempotent: safe to run again after Colab resets.

Needs 2 Colab Secrets (key icon, 'Notebook access' ON):
  GITHUB_TOKEN  fine-grained token limited to THIS repository, permission 'Contents: Read and write'
  GITHUB_REPO   'your-username/deriv-lab'
"""
import os
import sys
from pathlib import Path

from . import gitsync
from .journal import Journal
from .paths import ensure_dirs

REPO_DIR = Path("/content/deriv-lab")


def _secret(name):
    from google.colab import userdata
    try:
        return userdata.get(name)
    except Exception as e:  # secret missing or access not granted
        raise RuntimeError(f"Colab secret {name} is missing or 'Notebook access' is off") from e


def setup(repo_dir=REPO_DIR, mount_drive=True):
    repo_dir = Path(repo_dir)
    if mount_drive:
        from google.colab import drive
        drive.mount("/content/drive")
    token, repo = _secret("GITHUB_TOKEN"), _secret("GITHUB_REPO")
    if (repo_dir / ".git").exists():
        gitsync.init_repo(repo_dir)
        try:
            gitsync.pull(repo_dir, repo, token)
            state = "repo updated from GitHub"
        except RuntimeError as e:  # e.g. first push never happened
            state = f"pull skipped ({e})"
    elif repo_dir.exists() and any(repo_dir.iterdir()):
        # first run: the unzipped project is here but not yet on GitHub
        print(gitsync.push(repo_dir, repo, token, "initial import"))
        state = "first push done"
    else:
        gitsync.clone(repo, token, repo_dir)
        state = "repo cloned from GitHub (resume after reset)"
    if str(repo_dir) not in sys.path:
        sys.path.insert(0, str(repo_dir))
    root = ensure_dirs()
    os.environ["DERIV_LAB_DATA"] = str(root)
    j = Journal(root)
    seed = repo_dir / "journal" / "seed.jsonl"
    added = j.import_legacy(seed) if seed.exists() else 0
    print(f"{state}. Data folder: {root}. Legacy journal entries added: {added}.")
    return {"repo_dir": repo_dir, "repo": repo, "token": token, "root": root, "journal": j}


def sync(ctx, message="journal sync"):
    """Save the journal to GitHub (history + backup). Results themselves stay in Drive."""
    return gitsync.sync_journal(ctx["repo_dir"], ctx["repo"], ctx["token"], ctx["root"], message)
