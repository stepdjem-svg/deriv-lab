"""Where data lives. Code goes to GitHub; DATA goes to Google Drive (survives Colab resets)."""
import os
from pathlib import Path

SUBDIRS = ("journal", "runs", "artifacts", "checkpoints", "backups")


def data_root():
    """DERIV_LAB_DATA env var wins; else Google Drive if mounted; else ./data (local/tests)."""
    env = os.environ.get("DERIV_LAB_DATA")
    if env:
        return Path(env)
    drive = Path("/content/drive/MyDrive")
    if drive.exists():
        return drive / "deriv-lab-data"
    return Path.cwd() / "data"


def ensure_dirs(root=None):
    root = Path(root) if root else data_root()
    for name in SUBDIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root
