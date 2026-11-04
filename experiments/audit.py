# Deriv technical audit for Google Colab. Public endpoint only: no token, no trades.
#
# For each symbol it measures what actually matters for research:
#   - is the market open / trading suspended?
#   - how fast do ticks arrive (median seconds between ticks)?
#   - which Rise/Fall durations are offered, at what real payout,
#     and therefore what break-even win rate you must beat?
#
# Output: a printed summary and the file /content/audit.csv (download it from the
# folder icon to keep a record).
#
# Usage in Colab: paste in a cell and run it, then in another cell:
#   await audit(max_symbols=15)   # quick first look (~2 min)
#   await audit()                 # everything (~8 min)
#   await audit(only=['frxXAGUSD'])        # one or a few symbols
#   await audit(markets=['forex','commodities'])  # whole markets
#   await audit(markets=['forex','commodities','indices'], durations=[(5,'m'),(15,'m'),(30,'m'),(1,'h'),(1,'d')])

import asyncio
import csv
import json
import statistics
from collections import defaultdict

import websockets

URL = "wss://api.derivws.com/trading/v1/options/ws/public"
DURATIONS = [(5, "t"), (10, "t"), (30, "s"), (1, "m"), (5, "m")]
PAUSE = 0.7  # seconds between requests, to stay well under rate limits
OUT = "/content/audit.csv"


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
                await asyncio.sleep(PAUSE)
                return msg


def tick_gap(history):
    times = history.get("times") or []
    gaps = [b - a for a, b in zip(times, times[1:]) if b > a]
    return statistics.median(gaps) if gaps else None


async def audit(max_symbols=None, only=None, markets=None, durations=None, types=('CALL', 'PUT')):
    rows = []
    async with websockets.connect(URL, ping_interval=20) as ws:
        rpc = Rpc(ws)
        syms = (await rpc.call({"active_symbols": "brief"})).get("active_symbols", [])
        by_market = defaultdict(int)
        for s in syms:
            by_market[s.get("market")] += 1
        print(f"{len(syms)} symbols by market: {dict(by_market)}\n")
        todo = syms
        if only:
            todo = [s for s in todo if s.get("underlying_symbol") in only]
        if markets:
            todo = [s for s in todo if s.get("market") in markets]
        if max_symbols:
            todo = todo[:max_symbols]
        for i, s in enumerate(todo, 1):
            name = s.get("underlying_symbol")
            base = {"symbol": name, "market": s.get("market"), "submarket": s.get("submarket"),
                    "open": s.get("exchange_is_open"), "suspended": s.get("is_trading_suspended")}
            gap = None
            try:
                h = await rpc.call({"ticks_history": name, "count": 1000, "end": "latest", "style": "ticks"})
                gap = tick_gap(h.get("history", {}))
            except Exception as e:
                print(f"history failed for {name}: {e}")
            for dur, unit in (durations or DURATIONS):
                for ctype in types:
                    row = {**base, "tick_gap_s": gap, "duration": f"{dur}{unit}", "type": ctype,
                           "payout": None, "break_even": None, "error": None}
                    try:
                        m = await rpc.call({"proposal": 1, "amount": 1, "basis": "stake", "contract_type": ctype,
                                            "currency": "USD", "duration": dur, "duration_unit": unit,
                                            "underlying_symbol": name})
                        if "error" in m:
                            row["error"] = (m["error"].get("message") or "")[:80]
                        else:
                            p = m["proposal"]
                            row["payout"] = float(p["payout"])
                            row["break_even"] = round(float(p["ask_price"]) / float(p["payout"]), 4)
                    except Exception as e:
                        row["error"] = str(e)[:80]
                    rows.append(row)
            print(f"[{i}/{len(todo)}] {name}: tick gap {gap}s")

    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    ok = [r for r in rows if r["break_even"]]
    print(f"\n{len(ok)} of {len(rows)} symbol/duration/type combinations are priced. Saved to {OUT}")
    print("\nBreak-even win rate to beat (median across symbols), by market, duration and side:")
    groups = defaultdict(list)
    for r in ok:
        groups[(r["market"], r["duration"], r["type"])].append(r["break_even"])
    for (market, dur, ctype), v in sorted(groups.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        print(f"  {str(market):<13}{dur:<5}{ctype:<5} n={len(v):<3} {statistics.median(v)*100:.1f}%")

    # House margin: if both sides are priced, (CALL break-even + PUT break-even - 1) is what you pay
    # per round, whatever the direction. A cheap CALL usually means an expensive PUT.
    pair = defaultdict(dict)
    for r in ok:
        pair[(r["symbol"], r["market"], r["duration"])][r["type"]] = r["break_even"]
    margins = defaultdict(list)
    for (sym, market, dur), d in pair.items():
        if "CALL" in d and "PUT" in d:
            margins[(market, dur)].append(d["CALL"] + d["PUT"] - 1)
    print("\nHouse margin = CALL break-even + PUT break-even - 1 (median):")
    for (market, dur), v in sorted(margins.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        print(f"  {str(market):<13}{dur:<5} n={len(v):<3} {statistics.median(v)*100:.1f}%")

    print("\nThe 10 cheapest single sides to beat (check the OTHER side before getting excited):")
    for r in sorted(ok, key=lambda r: r["break_even"])[:10]:
        other = pair[(r["symbol"], r["market"], r["duration"])].get("PUT" if r["type"] == "CALL" else "CALL")
        o = f"{other*100:.1f}%" if other else "n/a"
        print(f"  {r['symbol']:<12}{r['duration']:<5}{r['type']:<5}{r['break_even']*100:.1f}%   other side: {o}")
    errs = defaultdict(int)
    for r in rows:
        if r["error"]:
            errs[r["error"]] += 1
    print("\nMost common refusals:")
    for e, c in sorted(errs.items(), key=lambda kv: -kv[1])[:5]:
        print(f"  {c}x {e}")

# await audit(max_symbols=15)
