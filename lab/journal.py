"""Persistent research journal (append-only JSONL) with PRE-REGISTRATION.

Workflow that prevents fooling ourselves:
  1. preregister(): write the hypothesis, the exact rule and the pass/fail criteria BEFORE running.
     A fingerprint (SHA-256) of rule+criteria is stored.
  2. run the experiment.
  3. record_result(): must present the same rule+criteria; if they changed, it is refused.
verify() lists anything suspicious (results without pre-registration, changed rules, open items).
Legacy experiments (done before this journal existed) are imported with preregistered=False.
"""
import hashlib
import json
from pathlib import Path

from .paths import ensure_dirs
from .storage import append_jsonl, read_jsonl, utc_now

VERDICTS = ("supported", "not_supported", "inconclusive", "invalid")


class RuleChangedAfterPreregistration(ValueError):
    pass


def fingerprint(rule, criteria):
    blob = json.dumps({"rule": rule, "criteria": criteria}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class Journal:
    def __init__(self, root=None):
        self.root = ensure_dirs(root)
        self.path = self.root / "journal" / "journal.jsonl"

    # ---- reading ----
    def events(self):
        records, _ = read_jsonl(self.path)
        return records

    def _next_id(self, prefix):
        n = sum(1 for e in self.events() if str(e.get("id", "")).startswith(prefix)) + 1
        return f"{prefix}{n:03d}"

    # ---- writing ----
    def preregister(self, title, hypothesis, rule, criteria, tags=None):
        pid = self._next_id("P")
        append_jsonl(self.path, {
            "type": "prereg", "id": pid, "ts": utc_now(), "title": title,
            "hypothesis": hypothesis, "rule": rule, "criteria": criteria,
            "fingerprint": fingerprint(rule, criteria), "tags": tags or [],
        })
        return pid

    def record_result(self, prereg_id, run_id, metrics, verdict, rule, criteria, notes="", tags=None):
        if verdict not in VERDICTS:
            raise ValueError(f"verdict must be one of {VERDICTS}")
        pre = next((e for e in self.events() if e.get("type") == "prereg" and e.get("id") == prereg_id), None)
        if pre is None:
            raise KeyError(f"No pre-registration {prereg_id}")
        if fingerprint(rule, criteria) != pre["fingerprint"]:
            raise RuleChangedAfterPreregistration(
                f"{prereg_id}: rule or criteria differ from what was registered. Register a NEW hypothesis instead.")
        rid = self._next_id("R")
        append_jsonl(self.path, {
            "type": "result", "id": rid, "prereg_id": prereg_id, "run_id": run_id, "ts": utc_now(),
            "metrics": metrics, "verdict": verdict, "notes": notes, "tags": tags or [],
        })
        return rid

    def note(self, text, tags=None):
        nid = self._next_id("N")
        append_jsonl(self.path, {"type": "note", "id": nid, "ts": utc_now(), "text": text, "tags": tags or []})
        return nid

    def decision(self, text, tags=None):
        did = self._next_id("D")
        append_jsonl(self.path, {"type": "decision", "id": did, "ts": utc_now(), "text": text, "tags": tags or []})
        return did

    def import_legacy(self, seed_path):
        """Idempotent: entries already present (same id) are not added twice. Returns number added."""
        have = {e.get("id") for e in self.events()}
        added = 0
        records, _ = read_jsonl(seed_path)
        for rec in records:
            if rec.get("id") in have:
                continue
            rec = {**rec, "type": "legacy", "preregistered": False, "imported_at": utc_now()}
            append_jsonl(self.path, rec)
            added += 1
        return added

    # ---- auditing ----
    def open_preregistrations(self):
        done = {e["prereg_id"] for e in self.events() if e.get("type") == "result"}
        return [e for e in self.events() if e.get("type") == "prereg" and e["id"] not in done]

    def verify(self):
        problems = []
        pre = {e["id"]: e for e in self.events() if e.get("type") == "prereg"}
        for e in self.events():
            if e.get("type") == "result":
                if e["prereg_id"] not in pre:
                    problems.append(f"{e['id']}: result without pre-registration")
            if e.get("type") == "prereg" and e.get("fingerprint") != fingerprint(e["rule"], e["criteria"]):
                problems.append(f"{e['id']}: stored rule no longer matches its fingerprint (file edited?)")
        return problems

    # ---- human-readable export ----
    def render_markdown(self):
        lines = ["# Research journal", "",
                 "Generated from journal.jsonl (append-only). Do not edit by hand.", ""]
        legacy = [e for e in self.events() if e.get("type") == "legacy"]
        if legacy:
            lines += ["## Earlier experiments (before pre-registration existed)", ""]
            for e in legacy:
                lines += [f"### {e['id']} - {e.get('title', '')}  [{e.get('verdict', '?')}]",
                          f"*{e.get('date', '')}* - {e.get('summary', '')}", ""]
        results = {e["prereg_id"]: e for e in self.events() if e.get("type") == "result"}
        pres = [e for e in self.events() if e.get("type") == "prereg"]
        if pres:
            lines += ["## Pre-registered experiments", ""]
            for p in pres:
                r = results.get(p["id"])
                status = r["verdict"] if r else "OPEN (no result yet)"
                lines += [f"### {p['id']} - {p['title']}  [{status}]", f"*{p['ts']}* - {p['hypothesis']}",
                          f"- rule: `{json.dumps(p['rule'], sort_keys=True)}`",
                          f"- criteria: `{json.dumps(p['criteria'], sort_keys=True)}`"]
                if r:
                    lines += [f"- result {r['id']} (run {r['run_id']}): `{json.dumps(r['metrics'], sort_keys=True)}`"]
                    if r.get("notes"):
                        lines += [f"- notes: {r['notes']}"]
                lines += [""]
        notes = [e for e in self.events() if e.get("type") in ("note", "decision")]
        if notes:
            lines += ["## Notes and decisions", ""]
            for e in notes:
                lines += [f"- {e['id']} ({e['ts']}): {e['text']}"]
        return "\n".join(lines) + "\n"
