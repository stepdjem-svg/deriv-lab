"""Verification for phase 1. Prints PASS / FAIL / SKIP per check. Run it in Colab after setup()."""
import tempfile
from pathlib import Path

from . import gitsync
from .journal import Journal
from .paths import ensure_dirs
from .storage import Checkpoint, append_jsonl, read_jsonl, save_artifact, write_json_atomic, read_json


def run(ctx=None):
    root = ensure_dirs(ctx["root"] if ctx else None)
    results = []

    def check(name, fn):
        try:
            res = fn()
            results.append((name, "SKIP" if res == "skip" else "PASS", ""))
        except Exception as e:  # report, keep going
            results.append((name, "FAIL", f"{type(e).__name__}: {e}"))

    probe = root / "backups" / "_selftest"
    probe.mkdir(parents=True, exist_ok=True)

    def t_roundtrip():
        p = probe / "t.jsonl"
        if p.exists():
            p.unlink()
        for i in range(3):
            append_jsonl(p, {"i": i})
        recs, skipped = read_jsonl(p)
        assert [r["i"] for r in recs] == [0, 1, 2] and skipped == 0

    def t_torn_line():
        p = probe / "torn.jsonl"
        p.write_bytes(b'{"a": 1}\n{"b": 2}\n{"c": 3')  # simulated crash in the middle of a write
        recs, skipped = read_jsonl(p)
        assert len(recs) == 2 and skipped == 1

    def t_atomic():
        p = probe / "state.json"
        write_json_atomic(p, {"x": 1})
        write_json_atomic(p, {"x": 2})
        assert read_json(p)["x"] == 2 and not list(probe.glob("*.tmp"))

    def t_checkpoint():
        ck = Checkpoint("selftest-run", root)
        ck.save({"done": ["a", "b"]})
        assert Checkpoint("selftest-run", root).load()["done"] == ["a", "b"]
        ck.clear()

    def t_artifact():
        src = probe / "a.csv"
        src.write_text("x,y\n1,2\n")
        dest = save_artifact(src, "selftest-run", root)
        assert dest.read_text() == "x,y\n1,2\n"

    def t_journal():
        with tempfile.TemporaryDirectory() as tmp:
            j = Journal(tmp)
            rule, crit = {"k": 1}, {"z_min": 3}
            pid = j.preregister("t", "h", rule, crit)
            j.record_result(pid, "r1", {"n": 1}, "inconclusive", rule, crit)
            assert j.verify() == []
            try:
                p2 = j.preregister("t2", "h2", rule, crit)
                j.record_result(p2, "r2", {}, "supported", {"k": 2}, crit)
            except ValueError:
                return
            raise AssertionError("changed rule was accepted")

    def t_seed():
        j = Journal(root)
        ids = [e.get("id") for e in j.events() if e.get("type") == "legacy"]
        assert len(ids) == len(set(ids)) and len(ids) >= 8, f"{len(ids)} legacy entries"

    def t_git():
        if not ctx:
            return "skip"
        ok, out = gitsync.remote_reachable(ctx["repo"], ctx["token"])
        assert ok, out
        assert gitsync.has_commits(ctx["repo_dir"]), "no commit yet in the local repo"

    for name, fn in [("append/read round-trip", t_roundtrip), ("crash-torn line tolerated", t_torn_line),
                     ("atomic JSON write", t_atomic), ("checkpoint resume", t_checkpoint),
                     ("artifact copy + hash", t_artifact), ("journal pre-registration guard", t_journal),
                     ("legacy experiments imported", t_seed), ("GitHub reachable + commits", t_git)]:
        check(name, fn)
    for name, status, msg in results:
        print(f"{status:<5} {name}" + (f"  -> {msg}" if msg else ""))
    ok = all(s != "FAIL" for _, s, _ in results)
    print("\nPHASE 1 VERIFIED" if ok else "\nPHASE 1 NOT VERIFIED: fix the FAIL lines first")
    return ok
