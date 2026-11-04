"""Crash-safe storage primitives. Colab can die at any moment, so:
  - JSONL appends are written in ONE call and fsync'ed; a torn last line is tolerated on read.
  - JSON snapshots (checkpoints) are written to a temp file then atomically renamed.
  - Artifacts are copied with a SHA-256 check and recorded in a manifest.
"""
import hashlib
import json
import os
import secrets
import shutil
import time
from pathlib import Path

from .paths import ensure_dirs


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_run_id(prefix="run"):
    return f"{prefix}-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{secrets.token_hex(2)}"


def append_jsonl(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
    # If a previous crash left a half-written last line (no newline), close it first so the new
    # record starts on its own line instead of being glued to the fragment and lost.
    prefix = b""
    if path.exists() and path.stat().st_size > 0:
        with open(path, "rb") as f:
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                prefix = b"\n"
    with open(path, "ab") as f:
        f.write(prefix + line.encode("utf-8"))  # single write call: one record = one line
        f.flush()
        os.fsync(f.fileno())


def read_jsonl(path):
    """Returns (records, skipped). A line that is not valid JSON (e.g. cut off by a crash) is skipped."""
    path = Path(path)
    if not path.exists():
        return [], 0
    records, skipped = [], 0
    with open(path, "rb") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                records.append(json.loads(raw.decode("utf-8")))
            except (ValueError, UnicodeDecodeError):
                skipped += 1
    return records, skipped


def write_json_atomic(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)  # atomic on the same filesystem


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return default


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


class Checkpoint:
    """Resume point for a long job. Save after each unit of work; on restart, load() and skip what is done."""

    def __init__(self, run_id, root=None):
        self.run_id = run_id
        self.path = ensure_dirs(root) / "checkpoints" / f"{run_id}.json"

    def save(self, state):
        write_json_atomic(self.path, {"run_id": self.run_id, "saved_at": utc_now(), "state": state})

    def load(self, default=None):
        data = read_json(self.path)
        return data["state"] if data and "state" in data else default

    def clear(self):
        if self.path.exists():
            self.path.unlink()


def save_artifact(src, run_id, root=None):
    """Copy a result file (CSV, log...) into Drive under artifacts/<run_id>/, verify it, record it."""
    root = ensure_dirs(root)
    src = Path(src)
    dest_dir = root / "artifacts" / run_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    digest = sha256_file(src)
    if sha256_file(dest) != digest:
        raise IOError(f"Artifact copy corrupted: {src} -> {dest}")
    append_jsonl(root / "artifacts" / "manifest.jsonl", {
        "saved_at": utc_now(), "run_id": run_id, "name": src.name,
        "bytes": dest.stat().st_size, "sha256": digest,
    })
    return dest
