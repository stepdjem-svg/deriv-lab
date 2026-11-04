# Follow-up to the structure scan. Public data only: no token, no trades.
#
# Two questions, each with rules FIXED IN ADVANCE (nothing is tuned on the data):
#
# A) PRICING: are short Rise/Fall contracts offered on the WLD baskets, BOOM1000 and CRASH1000,
#    and at what break-even for each side? (BOOM/CRASH looked "persistent" only because they
#    drift one way between rare spikes. If Deriv prices that in, there is nothing to find.)
#
# B) MEAN REVERSION on the WLD baskets (they showed strong reversal in the scan):
#    signal  = last tick is far above/below its 20-tick average (Bollinger-style z-score, |z| > 1.5)
#    bet     = it comes back (price above average -> Fall, below -> Rise)
#    entry   = d ticks AFTER the signal (d=1 is the realistic one: you cannot buy on the signal tick)
#    exit    = h ticks after entry; a tie counts as a loss; trades never overlap
#    The result is shown for the first half and the second half of the data separately.
#    Controls: R_100 and 1HZ100V (random indices: expect about 50%).
#
# Usage in Colab: paste in a cell and run it, then in another cell:  await followup()

import asyncio
import json
import math

import websockets

URL = "wss://api.derivws.com/trading/v1/options/ws/public"
PRICED = ["WLDAUD", "WLDEUR", "WLDGBP", "WLDUSD", "WLDXAU", "BOOM1000", "CRASH1000", "R_100"]
TESTED = ["WLDAUD", "WLDEUR", "WLDGBP", "WLDUSD", "WLDXAU", "R_100", "1HZ100V"]
DURATIONS = [(5, "t"), (10, "t"), (30, "s"), (1, "m")]
N_MA, THRESH = 20, 1.5
TARGET_TICKS = 30000
Z_BAR = 3.0


# ---------- pure logic (no network) ----------
def mr_trades(prices, d=1, h=5, start=0, end=None):
    end = len(prices) if end is None else end
    pre, pre2 = [0.0], [0.0]
    for p in prices:
        pre.append(pre[-1] + p)
        pre2.append(pre2[-1] + p * p)
    wins = trades = 0
    t = max(start, N_MA)
    while t + d + h < end:
        ma = (pre[t + 1] - pre[t + 1 - N_MA]) / N_MA
        var = (pre2[t + 1] - pre2[t + 1 - N_MA]) / N_MA - ma * ma
        sd = math.sqrt(var) if var > 1e-18 else 0.0
        if sd > 0:
            z = (prices[t] - ma) / sd
            if abs(z) > THRESH:
                bet_up = z < 0  # far below average -> bet it comes back up
                entry, exit_ = prices[t + d], prices[t + d + h]
                win = exit_ > entry if bet_up else exit_ < entry  # tie = loss
                wins += 1 if win else 0
                trades += 1
                t += d + h
                continue
        t += 1
    return wins, trades


def z_vs(wins, n, be):
    if n == 0:
        return 0.0
    return (wins / n - be) / math.sqrt(be * (1 - be) / n)


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
    by_time, end = {}, "latest"
    for _ in range(60):
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
    return [by_time[t] for t in sorted(by_time)]


async def price_table(rpc):
    be_by = {}
    print("A) PRICING (break-even win rate per side; 'n/a' = not offered)\n")
    print(f"{'symbol':<11}{'dur':<5}{'CALL':>8}{'PUT':>8}")
    for sym in PRICED:
        for dur, unit in DURATIONS:
            cells = {}
            for ctype in ("CALL", "PUT"):
                m = await rpc.call({"proposal": 1, "amount": 1, "basis": "stake", "contract_type": ctype,
                                    "currency": "USD", "duration": dur, "duration_unit": unit,
                                    "underlying_symbol": sym})
                if "error" in m:
                    cells[ctype] = None
                else:
                    p = m["proposal"]
                    cells[ctype] = float(p["ask_price"]) / float(p["payout"])
            if any(cells.values()):
                be_by[(sym, f"{dur}{unit}")] = cells
            f = lambda v: f"{v*100:.1f}%" if v else "n/a"
            print(f"{sym:<11}{str(dur)+unit:<5}{f(cells['CALL']):>8}{f(cells['PUT']):>8}")
    return be_by


async def followup():
    async with websockets.connect(URL, ping_interval=20) as ws:
        rpc = Rpc(ws)
        be_by = await price_table(rpc)
        print("\nB) MEAN REVERSION TEST (fixed rules; Z bar =", Z_BAR, ")\n")
        print(f"{'symbol':<9}{'d':>2}{'h':>3}{'n':>6}{'hit':>7}{'half1':>7}{'half2':>7}{'be':>7}{'z':>7}")
        for sym in TESTED:
            prices = await fetch_ticks(rpc, sym)
            if len(prices) < 3000:
                print(f"{sym}: only {len(prices)} ticks, skipped")
                continue
            mid = len(prices) // 2
            for d in (1, 2):
                for h in (5, 10):
                    w, n = mr_trades(prices, d, h)
                    w1, n1 = mr_trades(prices, d, h, 0, mid)
                    w2, n2 = mr_trades(prices, d, h, mid, len(prices))
                    cells = be_by.get((sym, f"{h}t"))
                    be = (sum(v for v in cells.values() if v) / len([v for v in cells.values() if v])) if cells else 1 / 1.9
                    hit = w / n if n else 0
                    print(f"{sym:<9}{d:>2}{h:>3}{n:>6}{hit*100:>6.1f}%{(w1/n1*100 if n1 else 0):>6.1f}%"
                          f"{(w2/n2*100 if n2 else 0):>6.1f}%{be*100:>6.1f}%{z_vs(w, n, be):>7.2f}")
        print("\nbe = average break-even of the two sides when the 10-tick/5-tick contract is priced, else 52.6% assumed.")
        print(f"Only a result with z > {Z_BAR} at d=1, with BOTH halves above break-even, is worth a fresh-data test.")

# await followup()
