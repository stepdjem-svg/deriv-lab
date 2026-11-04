# Safe Deriv trading agent for Google Colab (new Deriv API: REST OTP + WebSocket)
#
# SETUP (one time)
# 1. Register an app at developers.deriv.com (type: PAT). Legacy app_ids do NOT work.
# 2. Create a PAT with "trade" scope. Use a DEMO account.
# 3. In Colab: left sidebar > key icon (Secrets). Add:
#       DERIV_PAT         = your personal access token
#       DERIV_APP_ID      = your NEW app id
#       DERIV_ACCOUNT_ID  = your demo account id (e.g. DOT12345678)
#    Turn "Notebook access" on for each.
# 4. Run:  !pip -q install websockets aiohttp   (usually preinstalled)
#
# SAFETY DEFAULTS: DRY_RUN=True (logs signals, places no trades),
# demo only, stake cap, daily loss cap, trade cap, cooldown.

import asyncio
import csv
import json
import os
import random
import logging
import time
from collections import deque
from dataclasses import dataclass

import aiohttp
import websockets
import os 
pat = os.getenv("DERIV_PAT")
app_id = os.getenv("DERIV_APP_ID")
account_id = os.getenv("DERIV_ACCOUNT_ID")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("agent")


@dataclass
class Config:
    symbol: str = "1HZ100V"
    stake: float = 1.0              # per trade, USD
    duration_ticks: int = 5
    fast: int = 5                   # fast SMA window
    slow: int = 20                  # slow SMA window
    max_trades: int = 10            # per run
    max_daily_loss: float = 5.0     # stop when cumulative loss reaches this
    cooldown_s: int = 30            # min seconds between trades
    dry_run: bool = True            # True = never buys
    allow_real: bool = False        # keep False; blocks real-money endpoint
    api_base: str = "https://api.derivws.com"
    strategy: str = "ab"            # "ab" (recommended A/B test), "sma", or "random"
    max_consecutive_losses: int = 4 # stop after this many losses in a row
    log_file: str = "/content/trades.csv"


class DerivClient:
    def __init__(self, cfg, pat, app_id, account_id):
        self.cfg, self.pat, self.app_id, self.account_id = cfg, pat, app_id, account_id
        self.ws = None
        self._req = 0
        self._pending = {}
        self.ticks = asyncio.Queue(maxsize=1000)
        self._reader = None

    async def _get_ws_url(self):
        url = f"{self.cfg.api_base}/trading/v1/options/accounts/{self.account_id}/otp"
        headers = {"Authorization": f"Bearer {self.pat}", "Deriv-App-ID": self.app_id}
        async with aiohttp.ClientSession() as s:
            async with s.post(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    raise RuntimeError(f"OTP request failed: HTTP {r.status} {(await r.text())[:200]}")
                data = await r.json()
        ws_url = data["data"]["url"]
        if "/ws/real" in ws_url and not self.cfg.allow_real:
            raise RuntimeError("Account is REAL. Refusing. Use a demo account.")
        return ws_url

    async def connect(self):
        ws_url = await self._get_ws_url()  # fresh one-time URL every (re)connect
        self.ws = await websockets.connect(ws_url, ping_interval=20, ping_timeout=20, max_size=2**22)
        self._reader = asyncio.create_task(self._read_loop())
        log.info("Connected (%s)", "demo" if "/ws/demo" in ws_url else "unknown endpoint")

    async def _read_loop(self):
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                fut = self._pending.pop(msg.get("req_id"), None)
                if msg.get("msg_type") == "tick" and "tick" in msg:
                    if self.ticks.full():
                        self.ticks.get_nowait()
                    self.ticks.put_nowait(float(msg["tick"]["quote"]))
                if fut and not fut.done():
                    fut.set_result(msg)
        finally:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(ConnectionError("socket closed"))
            self._pending.clear()

    async def call(self, payload, timeout=15):
        self._req += 1
        payload = {**payload, "req_id": self._req}
        fut = asyncio.get_running_loop().create_future()
        self._pending[self._req] = fut
        await self.ws.send(json.dumps(payload))
        msg = await asyncio.wait_for(fut, timeout)
        if "error" in msg:
            raise RuntimeError(f"API error: {msg['error'].get('code')}: {msg['error'].get('message')}")
        return msg

    async def close(self):
        try:
            if self.ws:
                await self.call({"forget_all": "ticks"}, timeout=5)
        except Exception:
            pass
        if self.ws:
            await self.ws.close()
        if self._reader:
            self._reader.cancel()


class Agent:
    def __init__(self, cfg, client):
        self.cfg, self.c = cfg, client
        self.prices = deque(maxlen=cfg.slow + 1)
        self.trades = 0
        self.pnl = 0.0
        self.last_trade = 0.0
        self.wins = 0
        self.losses = 0
        self.streak = 0  # consecutive losses
        self.arms = {}   # arm name -> [wins, losses]

    def record(self, side, contract_id, status, profit, arm):
        new = not os.path.exists(self.cfg.log_file)
        with open(self.cfg.log_file, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["time", "strategy", "side", "contract_id", "status", "profit", "session_pnl"])
            w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), arm, side,
                        contract_id, status, profit, round(self.pnl, 2)])

    def summary(self):
        be = 1 / 1.9  # break-even win rate when a win pays 0.90 per 1.00 staked
        log.info("Break-even win rate: %.1f%%", 100 * be)
        for arm, (w, l) in self.arms.items():
            n = w + l
            if not n:
                continue
            rate = w / n
            z = (rate - be) / ((be * (1 - be) / n) ** 0.5)
            log.info("SUMMARY [%s]: %d trades, %d won (%.1f%%), z-score vs break-even %.2f "
                     "(need above ~2 AND hundreds of trades to mean anything)", arm, n, w, 100 * rate, z)
        log.info("Session P&L %.2f USD", self.pnl)

    def signal(self, force=None):
        if len(self.prices) < self.cfg.slow:
            return None
        if force is None and self.cfg.strategy == "random":
            return random.choice(["CALL", "PUT"])
        p = list(self.prices)
        fast = sum(p[-self.cfg.fast:]) / self.cfg.fast
        slow = sum(p[-self.cfg.slow:]) / self.cfg.slow
        if fast > slow * 1.00005:
            return "CALL"
        if fast < slow * 0.99995:
            return "PUT"
        return None

    def can_trade(self):
        if self.trades >= self.cfg.max_trades:
            log.warning("Max trades reached, stopping.")
            return False
        if self.streak >= self.cfg.max_consecutive_losses:
            log.warning("%d losses in a row, stopping.", self.streak)
            return False
        if self.pnl <= -self.cfg.max_daily_loss:
            log.warning("Loss limit hit (%.2f), stopping.", self.pnl)
            return False
        return True

    async def trade(self, side, arm="sma"):
        prop = (await self.c.call({
            "proposal": 1, "amount": self.cfg.stake, "basis": "stake",
            "contract_type": side, "currency": "USD",
            "duration": self.cfg.duration_ticks, "duration_unit": "t",
            "underlying_symbol": self.cfg.symbol,
        }))["proposal"]
        ask = float(prop["ask_price"])
        if ask > self.cfg.stake * 1.05:
            log.warning("Price %.2f exceeds stake cap, skipping", ask)
            return
        if self.cfg.dry_run:
            log.info("[DRY RUN] would buy %s at %.2f", side, ask)
            self.last_trade = time.time()
            return
        buy = (await self.c.call({"buy": prop["id"], "price": ask}))["buy"]
        cid = buy["contract_id"]
        self.trades += 1
        self.last_trade = time.time()
        log.info("Bought %s contract %s", side, cid)
        for _ in range(60):  # poll up to ~2 min
            await asyncio.sleep(2)
            poc = (await self.c.call({"proposal_open_contract": 1, "contract_id": cid}))["proposal_open_contract"]
            if poc.get("is_sold") or poc.get("status") in ("won", "lost"):
                profit = float(poc.get("profit", 0))
                self.pnl += profit
                w_l = self.arms.setdefault(arm, [0, 0])
                if profit > 0:
                    self.wins += 1
                    w_l[0] += 1
                    self.streak = 0
                else:
                    self.losses += 1
                    w_l[1] += 1
                    self.streak += 1
                self.record(side, cid, poc.get("status"), profit, arm)
                log.info("Result: %s, profit %.2f, session P&L %.2f", poc.get("status"), profit, self.pnl)
                return
        log.warning("Contract %s still open after timeout; check your account.", cid)

    async def run(self):
        await self.c.call({"ticks": self.cfg.symbol, "subscribe": 1})
        log.info("Watching %s (strategy=%s, dry_run=%s)", self.cfg.symbol, self.cfg.strategy, self.cfg.dry_run)
        try:
            while self.can_trade():
                price = await asyncio.wait_for(self.c.ticks.get(), timeout=60)
                self.prices.append(price)
                if time.time() - self.last_trade < self.cfg.cooldown_s:
                    continue
                if self.cfg.strategy == "ab":
                    # A/B test: when the trend signal fires, flip a coin to decide
                    # whether to follow it (arm "sma") or bet randomly (arm "random").
                    sig = self.signal(force="sma")
                    if sig:
                        if random.random() < 0.5:
                            await self.trade(sig, "sma")
                        else:
                            await self.trade(random.choice(["CALL", "PUT"]), "random")
                else:
                    side = self.signal()
                    if side:
                        await self.trade(side, self.cfg.strategy)
        finally:
            self.summary()


async def main(cfg=Config(), max_duration_s=1800):
    pat = os.getenv("DERIV_PAT")
    app_id = os.getenv("DERIV_APP_ID")
    account_id = os.getenv("DERIV_ACCOUNT_ID")
    deadline = time.time() + max_duration_s
    delay = 2
    while time.time() < deadline:
        client = DerivClient(cfg, pat, app_id, account_id)
        try:
            await client.connect()
            delay = 2
            agent = Agent(cfg, client)
            await asyncio.wait_for(agent.run(), timeout=max(1, deadline - time.time()))
            break  # finished normally (limits hit)
        except (asyncio.TimeoutError, ConnectionError, websockets.ConnectionClosed, aiohttp.ClientError) as e:
            log.warning("Connection problem (%r). Retrying in %ss", e, delay)
        except RuntimeError as e:
            if "HTTP 40" in str(e) or "REAL" in str(e):
                log.error("%s", e)  # auth/config errors: retrying won't help
                break
            log.warning("%s. Retrying in %ss", e, delay)
        finally:
            await client.close()
        await asyncio.sleep(delay)
        delay = min(delay * 2, 60)
    log.info("Agent stopped.")

# In a Colab cell (A/B test, demo account, same market conditions for both arms):
# await main(Config(dry_run=False, max_trades=200), max_duration_s=7200)
# Read the two SUMMARY lines at the end. Trades are saved in /content/trades.csv

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
