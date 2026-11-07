import asyncio, json, time
import websockets

URL = "wss://api.derivws.com/trading/v1/options/ws/public"
SYMS = ["frxEURUSD", "OTC_SPC", "frxXAUUSD"]
GRANS = [(60, "1m"), (900, "15m"), (3600, "1h")]
MAX_PAGES = 12


async def call(ws, n, payload):
    await ws.send(json.dumps({**payload, "req_id": n}))
    while True:
        m = json.loads(await asyncio.wait_for(ws.recv(), 30))
        if m.get("req_id") == n:
            await asyncio.sleep(0.7)
            return m


async def main():
    n = 0
    async with websockets.connect(URL, ping_interval=20) as ws:
        print("== HISTORY DEPTH (candles) ==")
        for sym in SYMS:
            for gran, label in GRANS:
                total, end, earliest, err = 0, "latest", None, None
                for _ in range(MAX_PAGES):
                    n += 1
                    m = await call(ws, n, {"ticks_history": sym, "style": "candles", "granularity": gran,
                                           "count": 5000, "end": end})
                    if "error" in m:
                        err = m["error"].get("message", "")[:60]
                        break
                    c = m.get("candles") or []
                    if not c:
                        break
                    ep = [x["epoch"] for x in c]
                    new_earliest = min(ep)
                    if earliest is not None and new_earliest >= earliest:
                        break
                    total += len(c)
                    earliest = new_earliest
                    end = earliest - 1
                    if len(c) < 100:
                        break
                since = time.strftime("%Y-%m-%d", time.gmtime(earliest)) if earliest else "-"
                days = round((time.time() - earliest) / 86400) if earliest else 0
                print(f"{sym:<10}{label:<4} candles={total:<6} since={since} ({days} days)" + (f" ERR {err}" if err else ""))
        print("\n== QUOTE FORMAT (30m, one snapshot) ==")
        for sym in SYMS:
            for side in ("CALL", "PUT"):
                n += 1
                m = await call(ws, n, {"proposal": 1, "amount": 1, "basis": "stake", "contract_type": side,
                                       "currency": "USD", "duration": 30, "duration_unit": "m",
                                       "underlying_symbol": sym})
                if "error" in m:
                    print(f"{sym} {side}: {m['error'].get('message', '')[:80]}")
                    continue
                p = m["proposal"]
                be = float(p["ask_price"]) / float(p["payout"])
                print(f"{sym} {side}: break-even {be*100:.1f}% spot={p.get('spot')} barrier={p.get('barrier')} "
                      f"start={p.get('date_start')} expiry={p.get('date_expiry')}")
                print("   longcode:", (p.get("longcode") or "")[:170])
                if sym == SYMS[0] and side == "CALL":
                    print("   proposal keys:", sorted(p.keys()))

asyncio.run(main())
