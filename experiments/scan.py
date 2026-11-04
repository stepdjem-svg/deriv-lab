# Deriv market scanner for Google Colab (no token, no account, no trading).
#
# What it does:
#   1. Lists the markets Deriv offers (public endpoint, no login).
#   2. Downloads recent tick history for each NON-synthetic symbol.
#   3. For each symbol, picks the best simple rule (momentum or reversion) on the
#      FIRST 70% of the data, then checks it on the LAST 30% it has never seen.
#   4. Prints a table. Only a result that holds on the unseen 30% means anything.
#
# Usage in Colab:  paste this in a cell, run it, then in another cell:  await scan()
# Assumption: a win pays 0.90 per 1.00 staked (same as your synthetic test), so
# break-even is 52.6%. Real payouts differ by market and duration: check with a
# 'proposal' before trusting any result.

import asyncio
import json
import math

import websockets

URL = "wss://api.derivws.com/trading/v1/options/ws/public"
BREAK_EVEN = 1 / 1.9
LOOKBACKS = (1, 3, 5)
HORIZONS = (1, 5, 10)


# ---------- pure analysis (no network) ----------
def run_rule(prices, k, h, rule, start, end):
    """Non-overlapping trades on prices[start:end]. Returns (wins, trades).
    rule 'mom' bets the last k-tick move continues; 'rev' bets it reverses.
    A tie after h ticks counts as a loss (Rise needs strictly higher, Fall strictly lower)."""
    wins = trades = 0
    t = max(start, k)
    while t + h < end:
        move = prices[t] - prices[t - k]
        if move != 0:
            up_bet = (move > 0) if rule == "mom" else (move < 0)
            fut = prices[t + h] - prices[t]
            won = fut > 0 if up_bet else fut < 0
            wins += 1 if won else 0
            trades += 1
            t += h  # skip ahead so trades don't overlap
        else:
            t += 1
    return wins, trades


def z_vs_break_even(wins, n):
    if n == 0:
        return 0.0
    p = wins / n
    return (p - BREAK_EVEN) / math.sqrt(BREAK_EVEN * (1 - BREAK_EVEN) / n)


def analyze(prices):
    """Pick best rule on first 70%, evaluate it on last 30%."""
    n = len(prices)
    cut = int(n * 0.7)
    best = None
    for k in LOOKBACKS:
        for h in HORIZONS:
            for rule in ("mom", "rev"):
                w, t = run_rule(prices, k, h, rule, 0, cut)
                if t < 50:
                    continue
                rate = w / t
                if best is None or rate > best["train_rate"]:
                    best = {"k": k, "h": h, "rule": rule, "train_rate": rate, "train_n": t}
    if best is None:
        return None
    w, t = run_rule(prices, best["k"], best["h"], best["rule"], cut, n)
    best.update(test_n=t, test_rate=(w / t if t else 0.0), test_z=z_vs_break_even(w, t))
    return best


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
                if "error" in msg:
                    raise RuntimeError(f"{msg['error'].get('code')}: {msg['error'].get('message')}")
                return msg


def is_synthetic(sym):
    text = " ".join(str(sym.get(f, "")) for f in ("market", "market_display_name", "submarket")).lower()
    return "synthetic" in text or "derived" in text


async def scan(max_symbols=40):
    async with websockets.connect(URL, ping_interval=20) as ws:
        rpc = Rpc(ws)
        syms = (await rpc.call({"active_symbols": "brief"})).get("active_symbols", [])
        print(f"{len(syms)} symbols. Example of one entry (to check field names):")
        print(syms[0] if syms else "none")
        real = [s for s in syms if not is_synthetic(s)]
        print(f"{len(real)} non-synthetic symbols; scanning up to {max_symbols}.\n")
        rows = []
        for s in real[:max_symbols]:
            name = s.get("underlying_symbol") or s.get("symbol")
            try:
                msg = await rpc.call({"ticks_history": name, "count": 5000, "end": "latest", "style": "ticks"})
                prices = [float(p) for p in msg["history"]["prices"]]
            except Exception as e:  # keep scanning even if one symbol fails
                print(f"skip {name}: {e}")
                continue
            res = analyze(prices)
            await asyncio.sleep(1.0)  # stay far below rate limits
            if res:
                rows.append((name, s.get("market"), len(prices), res))
        rows.sort(key=lambda r: -r[3]["test_z"])
        print(f"{'symbol':<14}{'market':<14}{'ticks':>6}  {'rule':<8}{'train':>7}{'test':>7}{'n_test':>7}{'z':>7}")
        for name, market, n, r in rows:
            rule = f"{r['rule']} k{r['k']} h{r['h']}"
            print(f"{name:<14}{str(market)[:13]:<14}{n:>6}  {rule:<8}{r['train_rate']*100:>6.1f}%{r['test_rate']*100:>6.1f}%{r['test_n']:>7}{r['test_z']:>7.2f}")
        threshold = 3.0  # strict: we scanned many symbols and rules, so luck will produce z around 2
        winners = [r for r in rows if r[3]["test_z"] > threshold]
        print(f"\nSymbols with test z > {threshold}: {[w[0] for w in winners] or 'none'}")
        print("Break-even win rate assumed: 52.6%. Expect 'train' to look better than 'test': that gap is the luck.")

# await scan()
