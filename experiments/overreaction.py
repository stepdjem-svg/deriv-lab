# overreaction.py - P005. PUBLIC cached candles only: no token, no trades.
# Run from the repo root AFTER experiments/autolab.py has cached candles:  python3 experiments/overreaction.py
# The rule and criteria below are fixed. The script pre-registers them in the journal BEFORE reading any data.
# Changing anything in RULE or CRIT means a NEW hypothesis (the journal refuses the result otherwise).
import csv, math, os, statistics, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.journal import Journal, fingerprint

HURDLE, LOOKBACK, K, MIN_N = 0.549, 24, 2.5, 300
DATA = Path(os.environ.get("DERIV_LAB_DATA", "deriv-lab-data"))
TITLE = "Overreaction reversal: forex and metals after an extreme candle"
HYP = ("After a candle whose close-to-close move exceeds 2.5x the trailing 24-candle standard deviation, "
       "the next candle reverses often enough to beat the 54.9% hurdle.")
RULE = {"markets": "all cached frx* symbols (forex + metals), candles from experiments/autolab.py",
        "granularities_s": [900, 3600], "return": "close(t) - close(t-1), contiguous candles only (gaps skipped)",
        "sigma": f"stdev of the previous {LOOKBACK} contiguous returns, excluding r(t)",
        "signal": f"|r(t)| >= {K} * sigma", "bet": "next candle moves opposite to r(t)",
        "target": "sign of close(t+1) - close(t)", "tie": "loss", "spacing": "signals at least 2 candles apart per symbol",
        "hurdle": HURDLE, "pooled": "all symbols pooled, one test per granularity",
        "split": "events sorted by time: first 50% / last 50%"}
CRIT = {"candidate_if": "for a granularity: n >= 300 AND accuracy >= hurdle AND z_vs_hurdle >= 3 "
                        "AND accuracy >= hurdle in BOTH halves",
        "verdict": "supported if any granularity is a candidate; inconclusive if every n < 300; else not_supported",
        "note": "candidate only; confirm on fresh data collected after this run, then on demo with real payouts"}


def zv(w, n):
    return (w / n - HURDLE) / math.sqrt(HURDLE * (1 - HURDLE) / n) if n else 0.0


def load(path):
    with open(path) as f:
        r = csv.reader(f); next(r)
        return sorted((int(e), float(c)) for e, _o, c in r)


def events(bars, g):
    """Yield (epoch, win) for each signal. Only contiguous candles are used."""
    out, last = [], -10
    for i in range(LOOKBACK + 1, len(bars) - 1):
        span = bars[i - LOOKBACK - 1:i + 2]
        if any(b[0] - a[0] != g for a, b in zip(span, span[1:])):
            continue
        rets = [span[j + 1][1] - span[j][1] for j in range(LOOKBACK)]
        r, nxt = bars[i][1] - bars[i - 1][1], bars[i + 1][1] - bars[i][1]
        sd = statistics.pstdev(rets)
        if sd == 0 or abs(r) < K * sd or i - last < 2:
            continue
        last = i
        out.append((bars[i][0], 1 if nxt != 0 and (nxt > 0) != (r > 0) else 0))
    return out


def run():
    if not any((DATA / "candles").glob("frx*_*.csv")):
        print(f"No cached candles in {DATA / 'candles'}: run experiments/autolab.py first. Nothing registered.")
        return
    j = Journal()
    fp = fingerprint(RULE, CRIT)
    pid = next((e["id"] for e in j.events() if e.get("type") == "prereg" and e.get("fingerprint") == fp), None)
    if pid is None:
        pid = j.preregister(TITLE, HYP, RULE, CRIT, tags=["pre-registered", "P005"])
    print("PRE-REGISTERED", pid, flush=True)
    metrics, candidates, sizes = {}, [], []
    for g in RULE["granularities_s"]:
        ev = []
        for p in sorted((DATA / "candles").glob(f"frx*_{g}.csv")):
            ev += events(load(p), g)
        ev.sort()
        n, w = len(ev), sum(x for _, x in ev)
        h = n // 2
        a1 = sum(x for _, x in ev[:h]) / h if h else 0.0
        a2 = sum(x for _, x in ev[h:]) / (n - h) if n - h else 0.0
        acc, z = (w / n if n else 0.0), zv(w, n)
        ok = n >= MIN_N and acc >= HURDLE and z >= 3 and a1 >= HURDLE and a2 >= HURDLE
        sizes.append(n)
        if ok:
            candidates.append(g)
        metrics[str(g)] = {"n": n, "acc": round(acc, 4), "z": round(z, 2), "halves": [round(a1, 4), round(a2, 4)]}
        print(f"g={g}s events={n} accuracy={acc*100:.1f}% z={z:.2f} halves={a1*100:.1f}/{a2*100:.1f} candidate={ok}")
    verdict = "supported" if candidates else ("inconclusive" if all(n < MIN_N for n in sizes) else "not_supported")
    metrics["candidates"] = candidates
    print("verdict:", verdict)
    if not any(e.get("type") == "result" and e.get("prereg_id") == pid for e in j.events()):
        j.record_result(pid, "overreaction", metrics, verdict, RULE, CRIT, notes="see stdout")
    print("verify:", j.verify())


if __name__ == "__main__":
    run()
