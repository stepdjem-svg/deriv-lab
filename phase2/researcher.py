# Role chercheur : quels contrats Rise/Fall existent vraiment, et a quel paiement.

def _sym(s):
    return s.get("underlying_symbol") or s.get("symbol")

def list_symbols(api):
    for req in ({"active_symbols": "brief"}, {"active_symbols": "brief", "product_type": "basic"}):
        r = api.call(req)
        items = [s for s in r.get("active_symbols", []) if not s.get("is_trading_suspended")]
        opened = [_sym(s) for s in items if s.get("exchange_is_open") == 1 and _sym(s)]
        if opened:
            return opened
        anysym = [_sym(s) for s in items if _sym(s)]
        if anysym:
            return anysym
        api.last_response = r
    return []

def _dur(s):
    digits = "".join(ch for ch in s if ch.isdigit())
    return int(digits), s[-1]

def _proposal(api, sym, d, stake):
    base = {"proposal": 1, "amount": stake, "basis": "stake", "contract_type": "CALL",
            "currency": "USD", "duration": d, "duration_unit": "t"}
    p = api.call({**base, "underlying_symbol": sym})
    if "error" in p and p["error"].get("code") in ("InputValidationFailed", "ValidationError", "InvalidRequest"):
        p = api.call({**base, "symbol": sym})
    return p

def probe(api, sym, stake=1, target=10):
    r = api.call({"contracts_for": sym})
    if "error" in r:
        return {"error": r["error"].get("code", "error"), "msg": str(r["error"].get("message", ""))[:80]}
    avail = r.get("contracts_for", {}).get("available", [])
    cands = [c for c in avail if c.get("contract_type") == "CALL"
             and c.get("contract_category") == "callput"
             and c.get("barrier_category") in ("euro_atm", None)]
    if not cands:
        return {"error": "no_rise_fall", "types": sorted({str(c.get("contract_type")) for c in avail})[:8],
                "keys": sorted(avail[0].keys())[:12] if avail else []}
    ticks = [c for c in cands if str(c.get("min_contract_duration", "")).endswith("t")]
    if not ticks:
        return {"error": "no_tick_duration", "min": cands[0].get("min_contract_duration")}
    c = ticks[0]
    mn, _ = _dur(c["min_contract_duration"])
    mx = _dur(c["max_contract_duration"])[0] if str(c.get("max_contract_duration", "")).endswith("t") else mn
    d = min(max(mn, target), mx)
    p = _proposal(api, sym, d, stake)
    if "error" in p:
        return {"error": p["error"].get("code", "proposal_error"), "duration": d,
                "msg": str(p["error"].get("message", ""))[:80]}
    pr = p["proposal"]
    ask, payout = float(pr["ask_price"]), float(pr["payout"])
    return {"duration": d, "unit": "t", "ask": ask, "payout": payout,
            "breakeven": ask / payout, "source": "proposal"}

def is_tradable(c):
    return ("error" not in c) and c.get("unit") == "t" and 0 < c.get("breakeven", 0) < 1
