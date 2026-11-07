# autolab.py - unattended research run. PUBLIC data only: no token, no trades. Resumable (candles are cached).
# 1) pre-registers two hypotheses in the journal BEFORE touching data, 2) downloads candle history,
# 3) tests them with fixed rules and a multiple-testing bar, 4) writes FINAL_SUMMARY.txt + journal result.
import asyncio, csv, json, math, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import websockets
from lab.journal import Journal, fingerprint
from lab.judge import z_threshold

URL = "wss://api.derivws.com/trading/v1/options/ws/public"
DATA = Path(os.environ.get("DERIV_LAB_DATA", "deriv-lab-data"))
CANDLES = DATA / "candles"
GRANS = {900: "15m", 3600: "1h"}
LOOKBACKS, MODES, HURDLE, PRIOR_TESTS, MAX_PAGES = (1, 4, 16), ("mom", "rev"), 0.549, 40, 6
MARKETS = ("forex", "indices", "commodities")
PAUSE = 0.7


def zv(w, n, p0):
    return (w / n - p0) / math.sqrt(p0 * (1 - p0) / n) if n else 0.0


def load(path):
    with open(path) as f:
        r = csv.reader(f); next(r)
        return sorted((int(a), float(b), float(c)) for a, b, c in r)


def predict(s, g, L, mode, lo, hi):
    """Bet that the last L-candle move continues (mom) or reverses (rev) over the next candle. Tie = loss."""
    w = n = 0
    for i in range(max(lo, L), min(hi, len(s) - 1)):
        if s[i + 1][0] - s[i][0] != g or s[i][0] - s[i - L][0] != L * g:
            continue  # skip gaps (weekends, closed hours)
        mv = s[i][2] - s[i - L][2]
        if mv == 0:
            continue
        up = (mv > 0) if mode == "mom" else (mv < 0)
        d = s[i + 1][2] - s[i][2]
        n += 1
        w += 1 if (d != 0 and (d > 0) == up) else 0
    return w, n


def sessions(s, g=900, min_len=8):
    runs, cur = [], [s[0]]
    for a, b in zip(s, s[1:]):
        if b[0] - a[0] == g:
            cur.append(b)
        else:
            if len(cur) >= min_len: runs.append(cur)
            cur = [b]
    if len(cur) >= min_len: runs.append(cur)
    return runs


def intraday(s):
    """Does the first half-hour return of a session predict the last half-hour return? (documented anomaly)"""
    w = n = 0
    for r in sessions(s):
        first, last = r[1][2] - r[0][1], r[-1][2] - r[-2][1]
        if first and last:
            n += 1
            w += 1 if (first > 0) == (last > 0) else 0
    return w, n


async def rpc(ws, st, payload):
    st["n"] += 1
    await ws.send(json.dumps({**payload, "req_id": st["n"]}))
    while True:
        m = json.loads(await asyncio.wait_for(ws.recv(), 30))
        if m.get("req_id") == st["n"]:
            await asyncio.sleep(PAUSE)
            return m


async def download(ws, st, sym, gran):
    path = CANDLES / f"{sym}_{gran}.csv"
    if path.exists():
        return path  # cache = resume after an interruption
    rows, end = {}, "latest"
    for _ in range(MAX_PAGES):
        m = await rpc(ws, st, {"ticks_history": sym, "style": "candles", "granularity": gran, "count": 5000, "end": end})
        if "error" in m:
            raise RuntimeError(m["error"].get("message", "error")[:70])
        c = m.get("candles") or []
        before = len(rows)
        for x in c:
            rows[int(x["epoch"])] = (float(x["open"]), float(x["close"]))
        if not c or len(rows) == before or len(c) < 100:
            break
        end = min(rows) - 1
    if len(rows) < 500:
        raise RuntimeError(f"only {len(rows)} candles")
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["epoch", "open", "close"])
        for e in sorted(rows): w.writerow([e, *rows[e]])
    os.replace(tmp, path)
    return path


def prereg(j, title, hyp, rule, crit):
    fp = fingerprint(rule, crit)
    for e in j.events():
        if e.get("type") == "prereg" and e.get("fingerprint") == fp:
            return e["id"]
    return j.preregister(title, hyp, rule, crit, tags=["autolab", "pre-registered"])


async def main():
    j = Journal()
    ruleA = {"markets": list(MARKETS), "granularities_s": list(GRANS), "lookbacks_candles": list(LOOKBACKS), "modes": list(MODES),
             "horizon": "next candle", "tie": "loss", "hurdle": HURDLE, "split": "first 70% / last 30%", "script": "experiments/autolab.py"}
    critA = {"candidate_if": "accuracy>=hurdle AND z_vs_hurdle>=3 AND accuracy>=hurdle in BOTH first 70% and last 30%",
             "bar": "two-sided Bonferroni via judge.z_threshold over all tests + 40 earlier tests", "else": "not_supported"}
    ruleB = {"markets": ["indices", "commodities"], "granularity_s": 900, "signal": "sign of first 30 min return of a session",
             "target": "sign of last 30 min return", "hurdle": HURDLE, "pooled": True, "script": "experiments/autolab.py"}
    critB = {"candidate_if": "pooled accuracy>=hurdle AND z_vs_hurdle>=3", "else": "not_supported"}
    pA = prereg(j, "Next-candle direction predictability (lagged returns) on Deriv real markets",
                "Past returns predict the next 15m/1h move well enough to beat the break-even hurdle.", ruleA, critA)
    pB = prereg(j, "Intraday momentum on indices and metals",
                "The first half-hour return of a session predicts the last half-hour return beyond the hurdle.", ruleB, critB)
    print("PRE-REGISTERED", pA, pB, flush=True)
    CANDLES.mkdir(parents=True, exist_ok=True)
    failed, st = [], {"n": 0}
    async with websockets.connect(URL, ping_interval=20) as ws:
        syms = [s for s in (await rpc(ws, st, {"active_symbols": "brief"})).get("active_symbols", []) if s.get("market") in MARKETS]
        print(f"{len(syms)} symbols to download", flush=True)
        for k, s in enumerate(syms, 1):
            for g in GRANS:
                try:
                    await download(ws, st, s["underlying_symbol"], g)
                except Exception as e:
                    failed.append(f"{s['underlying_symbol']} {GRANS[g]}: {e}")
            print(f"[{k}/{len(syms)}] {s['underlying_symbol']} done", flush=True)
    market = {s["underlying_symbol"]: s["market"] for s in syms}

    tests, depth = [], {}
    for p in sorted(CANDLES.glob("*.csv")):
        sym, g = p.stem.rsplit("_", 1); g = int(g)
        if sym not in market:
            continue
        s = load(p); depth.setdefault(GRANS[g], []).append(len(s))
        cut = int(len(s) * 0.7)
        for L in LOOKBACKS:
            for mode in MODES:
                w, n = predict(s, g, L, mode, 0, len(s)); w1, n1 = predict(s, g, L, mode, 0, cut); w2, n2 = predict(s, g, L, mode, cut, len(s))
                if n >= 500 and n1 and n2:
                    tests.append({"sym": sym, "g": GRANS[g], "L": L, "mode": mode, "n": n, "acc": w / n, "z05": zv(w, n, .5),
                                  "zH": zv(w, n, HURDLE), "a1": w1 / n1, "a2": w2 / n2})
    bar = z_threshold(len(tests) + 1 + PRIOR_TESTS)
    candA = [t for t in tests if t["acc"] >= HURDLE and t["zH"] >= 3 and t["a1"] >= HURDLE and t["a2"] >= HURDLE]
    pw = pn = 0; perB = []
    for sym, mk in market.items():
        f = CANDLES / f"{sym}_900.csv"
        if mk in ("indices", "commodities") and f.exists():
            w, n = intraday(load(f)); pw += w; pn += n
            if n >= 50: perB.append((sym, n, w / n))
    candB = pn >= 300 and pw / pn >= HURDLE and zv(pw, pn, HURDLE) >= 3
    usable = len({t["sym"] for t in tests})
    vA = "supported" if candA else ("inconclusive" if usable < 10 else "not_supported")
    vB = "supported" if candB else ("inconclusive" if pn < 300 else "not_supported")
    top = sorted(tests, key=lambda t: -t["acc"])[:8]
    L_ = ["=== FINAL SUMMARY (demo research, public data) ===",
          f"symbols with data: {usable} | download failures: {len(failed)}",
          "candles per series (median): " + ", ".join(f"{k}={sorted(v)[len(v)//2]}" for k, v in depth.items()),
          f"A) next-candle predictability: {len(tests)} tests, bar z={bar:.2f}, hurdle {HURDLE*100:.1f}%",
          f"   tests above bar (z vs 50%): {sum(abs(t['z05']) > bar for t in tests)} | best accuracy {max([t['acc'] for t in tests] or [0])*100:.1f}%",
          "   top 8 (sym gran L mode n acc z05 first70 last30):"]
    L_ += [f"   {t['sym']} {t['g']} L{t['L']} {t['mode']} n={t['n']} {t['acc']*100:.1f}% z={t['z05']:.1f} {t['a1']*100:.1f}/{t['a2']*100:.1f}" for t in top]
    L_ += [f"   candidates: {[(t['sym'], t['g'], t['L'], t['mode']) for t in candA] or 'none'}  => {vA}",
           f"B) intraday momentum: sessions={pn}, accuracy={(pw/pn*100 if pn else 0):.1f}%, z vs hurdle={zv(pw, pn, HURDLE):.2f} => {vB}",
           "   per symbol: " + ", ".join(f"{s} {a*100:.0f}%({n})" for s, n, a in perB[:8]),
           "failures: " + ("; ".join(failed[:6]) or "none"),
           "Any 'supported' = CANDIDATE only: must be confirmed on fresh data. Demo only, no real trades."]
    text = "\n".join(L_)
    print("\n" + text)
    (DATA / "runs").mkdir(parents=True, exist_ok=True)
    (DATA / "runs" / "FINAL_SUMMARY.txt").write_text(text + "\n")
    done = {e.get("prereg_id") for e in j.events() if e.get("type") == "result"}
    for pid, rule, crit, v, m in ((pA, ruleA, critA, vA, {"tests": len(tests), "bar": round(bar, 2), "best_acc": round(max([t["acc"] for t in tests] or [0]), 4), "candidates": len(candA)}),
                                  (pB, ruleB, critB, vB, {"sessions": pn, "acc": round(pw / pn, 4) if pn else None, "z_vs_hurdle": round(zv(pw, pn, HURDLE), 2)})):
        if usable >= 10 and pid not in done:
            j.record_result(pid, "autolab", m, v, rule, crit, notes="see FINAL_SUMMARY.txt")
    print("journal verify:", j.verify(), "| result recorded" if usable >= 10 else "| NOT recorded: too little data")

if __name__ == "__main__":
    asyncio.run(main())
