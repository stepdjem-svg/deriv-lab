import csv, math, os
from pathlib import Path
from lab.journal import Journal, fingerprint
HURDLE, DATA = 0.549, Path(os.environ.get("DERIV_LAB_DATA", "deriv-lab-data"))
RULE = {"markets": "forex (frx*) 1h candles, cached", "signal": "sign of Asia return = close(06:00 UTC bar) - open(00:00 UTC bar)",
        "target": "sign of London return = close(11:00 UTC bar) - open(07:00 UTC bar)", "bet": "London continues Asia",
        "tie": "loss", "hurdle": HURDLE, "pooled": True, "split": "first 50% / last 50% of days"}
CRIT = {"candidate_if": "pooled accuracy >= hurdle AND z_vs_hurdle >= 3 AND accuracy >= hurdle in BOTH halves",
        "else": "not_supported", "note": "candidate only; confirm on fresh data"}
def zv(w, n): return (w / n - HURDLE) / math.sqrt(HURDLE * (1 - HURDLE) / n) if n else 0.0
def run():
    j = Journal()
    fp = fingerprint(RULE, CRIT)
    pid = next((e["id"] for e in j.events() if e.get("type") == "prereg" and e.get("fingerprint") == fp), None)
    if pid is None:
        pid = j.preregister("Forex session continuation: Asia direction predicts London direction",
            "The Asia-session move on forex 1h candles predicts the London-session move beyond the 54.9% hurdle.", RULE, CRIT, tags=["pre-registered"])
    print("PRE-REGISTERED", pid, flush=True)
    W = {"h1": [0, 0], "h2": [0, 0]}
    for p in sorted((DATA / "candles").glob("frx*_3600.csv")):
        bars = {}
        with open(p) as f:
            r = csv.reader(f); next(r)
            for e, o, c in r: bars[int(e)] = (float(o), float(c))
        byday = {}
        for e in bars:
            byday.setdefault(e // 86400, {})[(e % 86400) // 3600] = bars[e]
        keys = sorted(byday)
        for i, d in enumerate(keys):
            h = byday[d]
            if all(k in h for k in (0, 6, 7, 11)):
                asia = h[6][1] - h[0][0]; lon = h[11][1] - h[7][0]
                if asia and lon:
                    half = "h1" if i < len(keys) / 2 else "h2"
                    W[half][1] += 1; W[half][0] += 1 if (asia > 0) == (lon > 0) else 0
    w, n = W["h1"][0] + W["h2"][0], W["h1"][1] + W["h2"][1]
    a1 = W["h1"][0] / W["h1"][1] if W["h1"][1] else 0; a2 = W["h2"][0] / W["h2"][1] if W["h2"][1] else 0
    ok = n >= 300 and w / n >= HURDLE and zv(w, n) >= 3 and a1 >= HURDLE and a2 >= HURDLE
    verdict = "supported" if ok else ("inconclusive" if n < 300 else "not_supported")
    print(f"days={n} accuracy={(w/n*100 if n else 0):.1f}% z={zv(w,n):.2f} halves={a1*100:.1f}/{a2*100:.1f} => {verdict}")
    if n >= 300 and not any(e.get("type") == "result" and e.get("prereg_id") == pid for e in j.events()):
        j.record_result(pid, "session_continuation", {"days": n, "acc": round(w/n, 4), "z": round(zv(w, n), 2),
            "halves": [round(a1, 4), round(a2, 4)]}, verdict, RULE, CRIT, notes="see stdout")
    print("verify:", j.verify())
run()
