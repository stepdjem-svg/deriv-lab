# Download candle history from Deriv (public endpoint: no token, no trades) and report
# how far back the data goes. This is the raw material for honest backtests.
#
# Usage in Colab: paste in a cell and run it, then in another cell:
#   await candles()                                   # default symbols, 1h and 30m
#   await candles(symbols=["frxEURUSD"], granularities=[3600], pages=6)
# Saves one CSV per symbol and granularity in /content/candles/

import asyncio
import csv
import datetime as dt
import json
import os

import websockets

URL = "wss://api.derivws.com/trading/v1/options/ws/public"
PAUSE = 1.0
OUTDIR = "/content/candles"
DEFAULT_SYMBOLS = ["frxEURUSD", "frxUSDJPY", "frxGBPUSD", "frxAUDUSD", "OTC_SPC", "OTC_FTSE"]


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


def fmt(epoch):
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).strftime("%Y-%m-%d %H:%M")


async def fetch(rpc, symbol, granularity, pages, count=5000):
    """Walk backwards in time, `count` candles per page. Returns candles sorted oldest first."""
    got, end = {}, "latest"
    for _ in range(pages):
        msg = await rpc.call({"ticks_history": symbol, "style": "candles", "granularity": granularity,
                              "count": count, "end": end})
        if "error" in msg:
            print(f"  {symbol} g={granularity}: {msg['error'].get('code')}: {msg['error'].get('message')}")
            break
        batch = msg.get("candles") or []
        if not batch:
            break
        before = len(got)
        for c in batch:
            got[int(c["epoch"])] = c
        if len(got) == before:  # no new data: reached the start of history
            break
        end = min(got) - 1
    return [got[e] for e in sorted(got)]


async def candles(symbols=None, granularities=(3600, 1800), pages=4):
    os.makedirs(OUTDIR, exist_ok=True)
    summary = []
    async with websockets.connect(URL, ping_interval=20) as ws:
        rpc = Rpc(ws)
        for sym in (symbols or DEFAULT_SYMBOLS):
            for g in granularities:
                data = await fetch(rpc, sym, g, pages)
                if not data:
                    summary.append((sym, g, 0, "-", "-"))
                    continue
                path = f"{OUTDIR}/{sym}_{g}.csv"
                with open(path, "w", newline="") as f:
                    w = csv.writer(f)
                    w.writerow(["epoch", "open", "high", "low", "close"])
                    for c in data:
                        w.writerow([c["epoch"], c.get("open"), c.get("high"), c.get("low"), c.get("close")])
                summary.append((sym, g, len(data), fmt(int(data[0]["epoch"])), fmt(int(data[-1]["epoch"]))))
                print(f"{sym} {g}s: {len(data)} candles, {fmt(int(data[0]['epoch']))} -> {fmt(int(data[-1]['epoch']))}")
    print("\nSummary (symbol, granularity s, candles, from, to) UTC:")
    for row in summary:
        print("  ", *row)
    print(f"\nFiles are in {OUTDIR}. Folder icon > {OUTDIR} to download them.")

# await candles()
