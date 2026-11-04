# Which Rise/Fall contracts does Deriv REALLY offer, and at what break-even?
# Public endpoint only: no token, no trades.
#
# For each symbol it asks Deriv's own list of contracts (contracts_for), then prices
# the shortest allowed Rise (CALL) contract to get the real payout and break-even.
#
# Usage in Colab: paste in a cell and run it, then in another cell:
#   await contracts()                              # all non-synthetic markets (~1-2 min)
#   await contracts(only=["frxXAUUSD","frxEURUSD"])
# Saves /content/contracts.csv

import asyncio
import csv
import json
import re

import websockets

URL = "wss://api.derivws.com/trading/v1/options/ws/public"
PAUSE = 0.7
OUT = "/content/contracts.csv"
DUR = re.compile(r"^(\d+)([tsmhd])$")


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


def parse_duration(text):
    m = DUR.match(str(text or ""))
    return (int(m.group(1)), m.group(2)) if m else None


async def contracts(only=None, include_synthetic=False):
    rows = []
    async with websockets.connect(URL, ping_interval=20) as ws:
        rpc = Rpc(ws)
        syms = (await rpc.call({"active_symbols": "brief"})).get("active_symbols", [])
        if only:
            syms = [s for s in syms if s.get("underlying_symbol") in only]
        elif not include_synthetic:
            syms = [s for s in syms if "synthetic" not in str(s.get("market"))]
        print(f"Probing {len(syms)} symbols.\n")
        shown_raw = False
        for i, s in enumerate(syms, 1):
            name = s.get("underlying_symbol")
            try:
                m = await rpc.call({"contracts_for": name})
            except Exception as e:
                print(f"{name}: contracts_for failed: {e}")
                continue
            if "error" in m:
                print(f"{name}: {m['error'].get('code')}: {m['error'].get('message')}")
                continue
            items = m.get("contracts_for", {}).get("available", [])
            if items and not shown_raw:
                print("Example contract entry (to check field names):")
                print(items[0], "\n")
                shown_raw = True
            calls = [c for c in items if c.get("contract_type") == "CALL"]
            if not calls:
                print(f"{name}: no CALL contract listed")
                continue
            for c in calls:
                row = {"symbol": name, "market": s.get("market"),
                       "category": c.get("contract_category"), "barriers": c.get("barriers"),
                       "expiry_type": c.get("expiry_type"),
                       "min_duration": c.get("min_contract_duration"),
                       "max_duration": c.get("max_contract_duration"),
                       "payout": None, "break_even": None, "error": None}
                d = parse_duration(row["min_duration"])
                if d and not c.get("barriers"):  # plain Rise needs no barrier
                    try:
                        p = await rpc.call({"proposal": 1, "amount": 1, "basis": "stake",
                                            "contract_type": "CALL", "currency": "USD",
                                            "duration": d[0], "duration_unit": d[1],
                                            "underlying_symbol": name})
                        if "error" in p:
                            row["error"] = (p["error"].get("message") or "")[:70]
                        else:
                            q = p["proposal"]
                            row["payout"] = float(q["payout"])
                            row["break_even"] = round(float(q["ask_price"]) / float(q["payout"]), 4)
                    except Exception as e:
                        row["error"] = str(e)[:70]
                rows.append(row)
            print(f"[{i}/{len(syms)}] {name} done")

    if not rows:
        print("No rows collected.")
        return
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nSaved {len(rows)} rows to {OUT}\n")
    print(f"{'symbol':<12}{'category':<10}{'barr':<6}{'min':<6}{'max':<6}{'payout':<8}{'break-even'}")
    for r in rows:
        be = f"{r['break_even']*100:.1f}%" if r["break_even"] else (r["error"] or "-")
        pay = f"{r['payout']:.2f}" if r["payout"] else "-"
        print(f"{r['symbol']:<12}{str(r['category'])[:9]:<10}{str(r['barriers']):<6}"
              f"{str(r['min_duration']):<6}{str(r['max_duration']):<6}{pay:<8}{be}")

# await contracts()
