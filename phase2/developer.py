# Role developpeur : recupere les ticks et execute l'experience pre-enregistree.
# Hypothese H1 : apres une montee/baisse sur d ticks, les d ticks suivants continuent (momentum)
# ou s'inversent (reversion). Le signe est choisi sur la 1re moitie, teste sur la 2e.

def fetch_ticks(api, sym, count=5000, target=20000, max_pages=20):
    # Pagination vers le passe : chaque page se termine a l'epoch le plus ancien de la precedente.
    prices, seen, end = [], set(), "latest"
    for _ in range(max_pages):
        r = api.call({"ticks_history": sym, "end": end, "count": count, "style": "ticks"})
        h = r.get("history", {})
        p, tm = h.get("prices", []), h.get("times", [])
        if not p:
            break
        if len(p) != len(tm):
            if not prices:
                prices = [float(x) for x in p]
            break
        new = [(a, b) for a, b in zip(tm, p) if a not in seen]
        if not new:
            break
        seen.update(a for a, _ in new)
        prices = [float(b) for _, b in new] + prices
        if len(prices) >= target:
            break
        end = str(min(tm))
    return prices

def outcomes(p, d, sign):
    w = n = 0
    i = d
    while i + d < len(p):
        prev = p[i] - p[i - d]
        if prev != 0:
            pred = 1 if sign * prev > 0 else -1
            fut = p[i + d] - p[i]
            n += 1
            if (pred == 1 and fut > 0) or (pred == -1 and fut < 0):
                w += 1
        i += d
    return w, n

def experiment(prices, d, breakeven):
    h = len(prices) // 2
    train, test = prices[:h], prices[h:]
    best = None
    for sign in (1, -1):
        w, n = outcomes(train, d, sign)
        wr = w / n if n else 0
        if best is None or wr > best[1]:
            best = (sign, wr, n)
    sign, train_wr, train_n = best
    w, n = outcomes(test, d, sign)
    return {"hypothesis": "H1_momentum_reversal", "sign": sign, "d": d, "breakeven": breakeven,
            "train_wr": train_wr, "train_n": train_n, "wins": w, "n": n,
            "train_end": h, "test_start": h, "n_ticks": len(prices)}
