# Orchestrateur minimal : etapes reprenables (checkpoint atomique) + journal de tous les resultats.
import json, os, datetime
from . import researcher, developer, statistician, auditor

def _save(path, state):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, path)

def _journal(base, rec):
    rec = dict(rec)
    rec["ts"] = datetime.datetime.utcnow().isoformat()
    with open(os.path.join(base, "journal", "phase2_journal.jsonl"), "a") as f:
        f.write(json.dumps(rec) + "\n")

def run(api, base, symbols=None, max_symbols=None):
    for d in ("checkpoints", "journal", "artifacts"):
        os.makedirs(os.path.join(base, d), exist_ok=True)
    ck = os.path.join(base, "checkpoints", "phase2_state.json")
    state = json.load(open(ck)) if os.path.exists(ck) else {"contracts": {}, "results": {}}
    syms = symbols or researcher.list_symbols(api)
    if max_symbols:
        syms = syms[:max_symbols]
    # Etape 1 : contrats reels
    for s in syms:
        if s in state["contracts"] and state["contracts"][s].get("error") not in ("ConnectionFailed", "RateLimit"):
            continue
        state["contracts"][s] = researcher.probe(api, s)
        _save(ck, state)
    tradable = [s for s in syms if researcher.is_tradable(state["contracts"][s])]
    # Etape 2 : experience hors echantillon
    for s in tradable:
        if state["results"].get(s, {}).get("v") == 2:
            continue
        c = state["contracts"][s]
        prices = developer.fetch_ticks(api, s)
        if len(prices) < 1000:
            state["results"][s] = {"error": "not_enough_ticks", "n_ticks": len(prices)}
        else:
            state["results"][s] = dict(developer.experiment(prices, c["duration"], c["breakeven"]), v=2)
        _journal(base, {"symbol": s, "result": state["results"][s]})
        _save(ck, state)
    # Etape 3 : verdict (correction avec le nombre final de tests)
    n_tests = max(1, len([s for s in tradable if "error" not in state["results"].get(s, {"error": 1})]))
    rows, survivors = [], []
    for s in tradable:
        r = state["results"].get(s, {})
        if "error" in r:
            continue
        ev = statistician.evaluate(r["wins"], r["n"], r["breakeven"], n_tests)
        issues = auditor.audit(r, ev, n_tests, state["contracts"][s])
        if issues and ev["verdict"].startswith("AVANTAGE"):
            ev["verdict"] = "REJETE PAR L'AUDITEUR"
        if ev["verdict"].startswith("AVANTAGE"):
            survivors.append(s)
        rows.append({"symbol": s, **ev, "issues": issues})
    skipped = {s: state["contracts"][s].get("error") for s in syms if not researcher.is_tradable(state["contracts"][s])}
    report = {"n_symbols": len(syms), "n_tradable": len(tradable), "n_tests": n_tests,
              "skipped_reasons": skipped, "rows": rows, "survivors": survivors,
              "global": ("AVANTAGE POSSIBLE sur " + ",".join(survivors) if survivors
                         else "AUCUN AVANTAGE FIABLE DETECTE")}
    with open(os.path.join(base, "artifacts", "phase2_report.json"), "w") as f:
        json.dump(report, f, indent=1)
    _journal(base, {"report": report["global"], "n_tradable": len(tradable)})
    return report
