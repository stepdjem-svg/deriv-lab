"""Statistical judge: decides whether results (demo trades or backtest) beat chance. Pure functions, stdlib only.

It never says "profitable". Best possible verdict: "candidate" = passed every gate, still needs fresh-data confirmation.
Threshold convention (same as tests_log.csv): two-sided Bonferroni, z_thr = Phi^-1(1 - alpha / (2 * n_tests)).
Four tests -> z about 2.50. Every extra idea tried raises the bar, because many tries produce lucky false winners.
"""
import math
from statistics import NormalDist

_N = NormalDist()


def break_even(ask, payout):
    """Win rate needed to break even for a contract bought at `ask` that pays `payout` on a win."""
    return ask / payout


def z_vs(wins, n, p0):
    if n <= 0:
        return 0.0
    return (wins / n - p0) / math.sqrt(p0 * (1 - p0) / n)


def z_threshold(n_tests, alpha=0.05):
    return _N.inv_cdf(1 - alpha / (2 * max(1, n_tests)))


def required_trades(p0, edge, alpha=0.05, power=0.8):
    """Trades needed to detect a true win rate of p0+edge against break-even p0 (one-sided test)."""
    p1 = p0 + edge
    za, zb = _N.inv_cdf(1 - alpha), _N.inv_cdf(power)
    n = ((za * math.sqrt(p0 * (1 - p0)) + zb * math.sqrt(p1 * (1 - p1))) / edge) ** 2
    return math.ceil(n)


def ev_per_stake(win_rate, p0):
    """Expected profit per 1 staked when break-even is p0 (win pays (1-p0)/p0 per 1 staked)."""
    payout_profit = (1 - p0) / p0
    return win_rate * payout_profit - (1 - win_rate)


def max_drawdown(pnls):
    peak = cum = worst = 0.0
    for x in pnls:
        cum += x
        peak = max(peak, cum)
        worst = max(worst, peak - cum)
    return worst


def two_prop_z(w1, n1, w2, n2):
    if n1 == 0 or n2 == 0:
        return 0.0
    p = (w1 + w2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    return ((w1 / n1) - (w2 / n2)) / se if se > 0 else 0.0


def evaluate(wins, n, p0, n_tests, control=None, out_of_sample=None, pnls=None, edge_of_interest=0.03, alpha=0.05):
    """control=(wins, n) of a coin-flip arm on the same market; out_of_sample=(wins, n) from unseen data."""
    z = z_vs(wins, n, p0)
    thr = z_threshold(n_tests, alpha)
    need = required_trades(p0, edge_of_interest)
    gates, reasons = {}, []
    gates["beats_break_even"] = z >= thr
    if not gates["beats_break_even"]:
        reasons.append(f"z {z:.2f} < bar {thr:.2f} (bar rises with the {n_tests} tests tried)")
    if control is not None:
        zc = two_prop_z(wins, n, control[0], control[1])
        gates["beats_random_control"] = zc >= 1.645
        if not gates["beats_random_control"]:
            reasons.append(f"not better than the coin-flip control (z {zc:.2f})")
    else:
        gates["beats_random_control"] = None
        reasons.append("no random control provided")
    if out_of_sample is not None:
        zo = z_vs(out_of_sample[0], out_of_sample[1], p0)
        gates["holds_out_of_sample"] = zo >= 1.645
        if not gates["holds_out_of_sample"]:
            reasons.append(f"fails on unseen data (z {zo:.2f})")
    else:
        gates["holds_out_of_sample"] = None
        reasons.append("no out-of-sample test yet")
    win_rate = wins / n if n else 0.0
    ev = ev_per_stake(win_rate, p0)
    gates["positive_expected_value"] = ev > 0
    enough = n >= need
    if not enough:
        reasons.append(f"only {n} trades; about {need} needed to see a {edge_of_interest*100:.0f}-point edge reliably")
    passed = all(v is True for v in gates.values())
    if passed and enough:
        verdict = "candidate"
    elif not enough and (gates["beats_break_even"] is False or None in gates.values()):
        verdict = "inconclusive"
    else:
        verdict = "reject" if enough else "inconclusive"
    out = {"verdict": verdict, "z": round(z, 3), "z_bar": round(thr, 3), "win_rate": round(win_rate, 4),
           "break_even": round(p0, 4), "ev_per_stake": round(ev, 4), "trades": n, "trades_needed": need,
           "gates": gates, "reasons": reasons}
    if pnls is not None:
        out["max_drawdown"] = round(max_drawdown(pnls), 2)
    return out
