# Does any Deriv index have STRUCTURE a bot could use? Public data only: no token, no trades.
#
# Hypothesis (fixed in advance): the "random" synthetic indices have none, but indices that are
# DESIGNED with hidden regimes or built-in bias (Drift Switching, Trek, Jump, Range Break...)
# might show measurable persistence. For every synthetic index this script measures:
#   - drift:        is the average tick move different from zero?
#   - VR(q):        variance ratio at q ticks. >1 = moves persist (trend), <1 = moves reverse.
#   - persistence:  how often does the next block of ticks move the same way as the previous one?
# Multiple-testing guard: with ~46 symbols x 6 tests, a result only counts if |z| > 3.7.
#
# Usage in Colab: paste in a cell and run it, then in another cell:
#   await structure(max_symbols=5)        # quick look
#   await structure()                     # all synthetic indices (~5 min)
#   await structure(markets=["indices"])  # or any other market name

import asyncio
import csv
import json
import math

import websockets

URL = "wss://api.derivws.com/trading/v1/options/ws/public"
TARGET_TICKS = 10000
Z_BAR = 3.7
OUT = "/content/structure.csv"


# ---------- pure statistics (no network) ----------
def returns(prices):
    if all(p > 0 for p in prices):
        return [math.log(b / a) for a, b in zip(prices, prices[1:])]
    return [b - a for a, b in zip(prices, prices[1:])]


def drift_z(r):
    n = len(r)
    m = sum(r) / n
    var = sum((x - m) ** 2 for x in r) / (n - 1)
    return m / math.sqrt(var / n) if var > 0 else 0.0


def variance_ratio_z(r, q):
    n = len(r)
    m = sum(r) / n
    var1 = sum((x - m) ** 2 for x in r) / (n - 1)
    if var1 == 0 or n <= q:
        return 1.0, 0.0
    sums = [sum(r[i:i + q]) for i in range(n - q + 1)]
    varq = sum((s - q * m) ** 2 for s in sums) / (len(sums) - 1)
    vr = varq / (q * var1)
    z = (vr - 1) / math.sqrt(2 * (2 * q - 1) * (q - 1) / (3 * q * n))
    return vr, z


def persistence(prices, h):
    """Non-overlapping blocks of h ticks: does the next block move the same way as the previous?"""
    same = tot = 0
    for i in range(0, len(prices) - 2 * h, h):
        a = prices[i + h] - prices[i]
        b = prices[i + 2 * h] - prices[i + h]
        if a != 0 and b != 0:
            tot += 1
            same += 1 if (a > 0) == (b > 0) else 0
    if tot < 30:
        return 0.5, 0.0, tot
    p = same / tot
    return p, (p - 0.5) / math.sqrt(0.25 / tot), tot


def analyze(prices):
    r = returns(prices)
    out = {"n": len(prices), "drift_z": drift_z(r)}
    for q in (5, 30, 120):
        vr, z = variance_ratio_z(r, q)
        out[f"vr{q}"], out[f"vr{q}_z"] = vr, z
    for h in (30, 120):
        p, z, tot = persistence(prices, h)
        out[f"pers{h}"], out[f"pers{h}_z"] = p, z
    out["max_abs_z"] = max(abs(out[k]) for k in ("drift_z", "vr5_z", "vr30_z", "vr120_z", "pers30_z", "pers120_z"))
    return out


# ---------- network ----------
class Rpc:
    def __init__(self, ws):
        self.ws, self.n = ws, 0

    async def call(self, payload):
        self.n += 1
        payload = {**payload, "req_id": self.n}
        await self.ws.send(json.dumps(payload))
        while True:
            msg = json.loads(await asyncio.wait_for(self.ws.recv(), 30))
            if msg.get("req_id") == self.n:
                await asyncio.sleep(0.6)
                return msg


async def fetch_ticks(rpc, symbol, target=TARGET_TICKS):
    """Pages backwards in time until `target` ticks or no more data."""
    by_time = {}
    end = "latest"
    for _ in range(40):
        msg = await rpc.call({"ticks_history": symbol, "count": 5000, "end": end, "style": "ticks"})
        if "error" in msg:
            msg = await rpc.call({"ticks_history": symbol, "count": 1000, "end": end, "style": "ticks"})
            if "error" in msg:
                break
        h = msg.get("history", {})
        times, prices = h.get("times") or [], h.get("prices") or []
        if not times:
            break
        before = len(by_time)
        for t, p in zip(times, prices):
            by_time[t] = float(p)
        if len(by_time) >= target or len(by_time) == before:
            break
        end = min(times)
    ts = sorted(by_time)
    return [by_time[t] for t in ts]


async def structure(max_symbols=None, markets=("synthetic_index",)):
    rows = []
    async with websockets.connect(URL, ping_interval=20) as ws:
        rpc = Rpc(ws)
        syms = (await rpc.call({"active_symbols": "brief"})).get("active_symbols", [])
        syms = [s for s in syms if s.get("market") in markets]
        if max_symbols:
            syms = syms[:max_symbols]
        print(f"Scanning {len(syms)} symbols, up to {TARGET_TICKS} ticks each.\n")
        for i, s in enumerate(syms, 1):
            name = s.get("underlying_symbol")
            try:
                prices = await fetch_ticks(rpc, name)
                if len(prices) < 1500:
                    print(f"[{i}/{len(syms)}] {name}: only {len(prices)} ticks, skipped")
                    continue
                res = analyze(prices)
                res.update(symbol=name, submarket=s.get("submarket"))
                rows.append(res)
                print(f"[{i}/{len(syms)}] {name}: {len(prices)} ticks, max |z| {res['max_abs_z']:.2f}")
            except Exception as e:
                print(f"[{i}/{len(syms)}] {name}: failed ({e})")
    if not rows:
        print("No data.")
        return
    keys = ["symbol", "submarket", "n", "drift_z", "vr5", "vr5_z", "vr30", "vr30_z", "vr120", "vr120_z",
            "pers30", "pers30_z", "pers120", "pers120_z", "max_abs_z"]
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows({k: r.get(k) for k in keys} for r in rows)
    rows.sort(key=lambda r: -r["max_abs_z"])
    print(f"\nSaved to {OUT}. Strongest signals first (z needs to beat {Z_BAR}):")
    print(f"{'symbol':<14}{'ticks':>6}{'drift z':>9}{'VR5 z':>8}{'VR30 z':>8}{'VR120 z':>9}{'pers30':>8}{'pers120':>9}")
    for r in rows[:15]:
        print(f"{r['symbol']:<14}{r['n']:>6}{r['drift_z']:>9.2f}{r['vr5_z']:>8.2f}{r['vr30_z']:>8.2f}"
              f"{r['vr120_z']:>9.2f}{r['pers30']*100:>7.1f}%{r['pers120']*100:>8.1f}%")
    flagged = [r["symbol"] for r in rows if r["max_abs_z"] > Z_BAR]
    expected = 0.05 * len(rows) * 6
    print(f"\nSymbols above the bar: {flagged or 'none'}")
    print(f"(By pure luck you would still expect about {expected:.0f} readings above |z|=2 among {len(rows)*6} tests.)")
    print("A flagged symbol is a LEAD, not a strategy: it must be re-tested on fresh data and priced against the real payout.")

# await structure(max_symbols=5)
