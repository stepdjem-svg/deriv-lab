# Forward test (paper only) for Deriv, Google Colab. No token, no account, no money.
#
# Rule fixed IN ADVANCE (do not change it after seeing results):
#   symbol  = frxXAGUSD
#   signal  = last tick move (k=1); bet it continues ("momentum")
#   horizon = 10 ticks; a tie counts as a loss
#
# Step 1: asks Deriv for the REAL price of a Rise/Fall contract on that symbol,
#         to learn the true break-even win rate (replaces my 52.6% assumption).
# Step 2: watches live ticks and records what the rule WOULD have won or lost.
#
# Verdict rule, also fixed in advance: the rule is only interesting if, after
# at least 300 paper trades, the win rate is above break-even with z > 2.
#
# Usage in Colab: paste in a cell and run it, then in another cell:  await forward_test()

import asyncio
import json
import math
import time

import websockets

URL = "wss://api.derivws.com/trading/v1/options/ws/public"
SYMBOL = "frxXAGUSD"
HORIZON = 10          # ticks
TARGET_TRADES = 300
DEFAULT_BREAK_EVEN = 1 / 1.9


class PaperTrader:
    """Pure logic, no network. Feed it ticks with on_tick()."""

    def __init__(self, horizon=HORIZON, break_even=DEFAULT_BREAK_EVEN):
        self.h, self.be = horizon, break_even
        self.prev = None
        self.pending = None   # (entry_price, bet_up, ticks_left)
        self.wins = self.n = 0

    def z(self):
        if not self.n:
            return 0.0
        p = self.wins / self.n
        return (p - self.be) / math.sqrt(self.be * (1 - self.be) / self.n)

    def on_tick(self, price):
        if self.pending:
            entry, bet_up, left = self.pending
            left -= 1
            if left > 0:
                self.pending = (entry, bet_up, left)
                self.prev = price
                return
            won = price > entry if bet_up else price < entry  # tie = loss
            self.wins += 1 if won else 0
            self.n += 1
            self.pending = None
        if self.prev is not None and price != self.prev:
            self.pending = (price, price > self.prev, self.h)  # momentum: bet it continues
        self.prev = price


async def check_contract(ws):
    """Ask for the real price of a 10-tick Rise contract. Returns break-even or None."""
    await ws.send(json.dumps({
        "proposal": 1, "amount": 1, "basis": "stake", "contract_type": "CALL",
        "currency": "USD", "duration": HORIZON, "duration_unit": "t",
        "underlying_symbol": SYMBOL, "req_id": 1,
    }))
    while True:
        msg = json.loads(await asyncio.wait_for(ws.recv(), 20))
        if msg.get("req_id") == 1:
            break
    if "error" in msg:
        print(f"Contract check FAILED: {msg['error'].get('code')}: {msg['error'].get('message')}")
        print("=> A 10-tick Rise/Fall on this symbol may not be offered. The paper test below")
        print("   would not correspond to a contract you can actually buy.")
        return None
    prop = msg["proposal"]
    ask, payout = float(prop["ask_price"]), float(prop["payout"])
    be = ask / payout
    print(f"Contract offered: stake {ask:.2f} pays {payout:.2f} -> profit {payout-ask:.2f}")
    print(f"REAL break-even win rate: {be*100:.1f}%  (my earlier assumption was 52.6%)")
    return be


async def forward_test(max_minutes=180):
    deadline = time.time() + max_minutes * 60
    async with websockets.connect(URL, ping_interval=20) as ws:
        # warn if the market is closed (forex closes on weekends)
        await ws.send(json.dumps({"active_symbols": "brief", "req_id": 2}))
        while True:
            m = json.loads(await asyncio.wait_for(ws.recv(), 20))
            if m.get("req_id") == 2:
                break
        info = next((s for s in m.get("active_symbols", []) if s.get("underlying_symbol") == SYMBOL), None)
        if info is None or not info.get("exchange_is_open", 1):
            print(f"{SYMBOL} looks CLOSED right now: no ticks will come. Try again when the market is open.")
            return
        be = await check_contract(ws)
        if be is None:
            return
        trader = PaperTrader(HORIZON, be)
        await ws.send(json.dumps({"ticks": SYMBOL, "subscribe": 1, "req_id": 3}))
        print(f"\nWatching {SYMBOL} live. Target: {TARGET_TRADES} paper trades (max {max_minutes} min).\n")
        last_print = 0
        while trader.n < TARGET_TRADES and time.time() < deadline:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 60))
            except asyncio.TimeoutError:
                print("No tick for 60 s (market may have closed). Stopping.")
                break
            if msg.get("msg_type") == "tick" and "tick" in msg:
                trader.on_tick(float(msg["tick"]["quote"]))
                if trader.n - last_print >= 25:
                    last_print = trader.n
                    print(f"{trader.n} trades: {trader.wins} won ({100*trader.wins/trader.n:.1f}%), z vs break-even {trader.z():+.2f}")
        n = trader.n
        print("\n=== FINAL ===")
        if not n:
            print("No trades recorded.")
            return
        rate = trader.wins / n
        print(f"{n} paper trades, {trader.wins} won ({rate*100:.1f}%). Break-even {be*100:.1f}%. z = {trader.z():+.2f}")
        if n < TARGET_TRADES:
            print(f"Only {n}/{TARGET_TRADES} trades: too few to conclude anything.")
        elif rate > be and trader.z() > 2:
            print("Passes the pre-set bar. Still only one test: repeat on another day before believing it.")
        else:
            print("Does NOT pass the bar. The earlier 72% was most likely luck.")

# await forward_test()
