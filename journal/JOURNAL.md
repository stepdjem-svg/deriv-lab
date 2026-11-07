# Research journal

Generated from journal.jsonl (append-only). Do not edit by hand.

## Pre-registered experiments

### P001 - Mean reversion on WLD baskets with a 1-tick entry delay  [not_supported]
*2026-11-05T11:21:32Z* - The strong short-term reversal in WLD baskets survives a realistic entry delay and beats break-even.
- rule: `{"bet": "reversion toward the mean", "controls": ["R_100", "1HZ100V"], "entry_delay_ticks": [1, 2], "horizon_ticks": [5, 10], "script": "experiments/followup.py", "signal": "last tick vs 20-tick mean, Bollinger z > 1.5 in absolute value", "split": "first half / second half", "symbols": ["WLDAUD", "WLDEUR", "WLDGBP", "WLDUSD", "WLDXAU"], "ticks_per_symbol": 30000, "tie": "loss"}`
- criteria: `{"applies_to": "entry_delay_ticks=1", "both_halves_above_break_even": true, "controls_must_not_pass": true, "if_passed": "candidate only: confirm on fresh ticks collected later", "z_min": 3.0}`
- result R003 (run followup_wld): `{"best_hit_delay1": 0.522, "best_symbol": "WLDXAU h10", "both_halves_above_be": false, "break_even": 0.526, "controls_pass": false, "max_z_all": 0.01, "tests_total": 28}`
- notes: Reversal in WLD baskets not tradable with 1-tick entry delay.

### P002 - Next-candle direction predictability (lagged returns) on Deriv real markets  [not_supported]
*2026-11-06T19:56:11Z* - Past returns predict the next 15m/1h move well enough to beat the break-even hurdle.
- rule: `{"granularities_s": [900, 3600], "horizon": "next candle", "hurdle": 0.549, "lookbacks_candles": [1, 4, 16], "markets": ["forex", "indices", "commodities"], "modes": ["mom", "rev"], "script": "experiments/autolab.py", "split": "first 70% / last 30%", "tie": "loss"}`
- criteria: `{"bar": "two-sided Bonferroni via judge.z_threshold over all tests + 40 earlier tests", "candidate_if": "accuracy>=hurdle AND z_vs_hurdle>=3 AND accuracy>=hurdle in BOTH first 70% and last 30%", "else": "not_supported"}`
- result R001 (run autolab): `{"bar": 3.89, "best_acc": 0.5281, "candidates": 0, "tests": 464}`
- notes: see FINAL_SUMMARY.txt

### P003 - Intraday momentum on indices and metals  [not_supported]
*2026-11-06T19:56:11Z* - The first half-hour return of a session predicts the last half-hour return beyond the hurdle.
- rule: `{"granularity_s": 900, "hurdle": 0.549, "markets": ["indices", "commodities"], "pooled": true, "script": "experiments/autolab.py", "signal": "sign of first 30 min return of a session", "target": "sign of last 30 min return"}`
- criteria: `{"candidate_if": "pooled accuracy>=hurdle AND z_vs_hurdle>=3", "else": "not_supported"}`
- result R002 (run autolab): `{"acc": 0.5152, "sessions": 792, "z_vs_hurdle": -1.91}`
- notes: see FINAL_SUMMARY.txt

### P004 - Forex session continuation: Asia direction predicts London direction  [not_supported]
*2026-11-07T12:25:10Z* - The Asia-session move on forex 1h candles predicts the London-session move beyond the 54.9% hurdle.
- rule: `{"bet": "London continues Asia", "hurdle": 0.549, "markets": "forex (frx*) 1h candles, cached", "pooled": true, "signal": "sign of Asia return = close(06:00 UTC bar) - open(00:00 UTC bar)", "split": "first 50% / last 50% of days", "target": "sign of London return = close(11:00 UTC bar) - open(07:00 UTC bar)", "tie": "loss"}`
- criteria: `{"candidate_if": "pooled accuracy >= hurdle AND z_vs_hurdle >= 3 AND accuracy >= hurdle in BOTH halves", "else": "not_supported", "note": "candidate only; confirm on fresh data"}`
- result R004 (run session_continuation): `{"acc": 0.5223, "days": 5131, "halves": [0.5127, 0.5319], "z": -3.84}`
- notes: see stdout

## Notes and decisions

- N001 (2026-11-05T11:21:13Z): A/B 700 trades 1HZ100V: SMA 161/358 (45.0%), random 167/342 (48.8%), break-even 52.63%. SMA vs random z -1.02. Aucun avantage detecte. P&L -76.80 USD (demo). Regle fixee a lavance, non reinterpretee.
- D001 (2026-11-07T12:20:46Z): CLOTURE autolab: A) next-candle prediction 15m/1h, 9 tests above z-bar vs 50%, best accuracy 52.8%, no candidate above break-even 54.6-56.8%, halves unstable -> not_supported. B) intraday momentum 51.5% over 792 sessions, z=-1.91 vs 54.9% -> not_supported. Line closed. No real trade. No profitable strategy identified.
