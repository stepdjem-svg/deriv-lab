# Role statisticien : test binomial unilateral contre le seuil de rentabilite reel + Bonferroni.
from math import sqrt
from scipy.stats import binomtest

def evaluate(wins, n, breakeven, n_tests=1, alpha=0.05, min_n=200):
    if n < min_n:
        return {"verdict": "INSUFFISANT", "wr": (wins / n if n else None), "n": n}
    p = binomtest(wins, n, breakeven, alternative="greater").pvalue
    p_adj = min(1.0, p * max(1, n_tests))
    wr = wins / n
    z = (wr - breakeven) / sqrt(breakeven * (1 - breakeven) / n)
    v = "AVANTAGE POSSIBLE (a confirmer en forward)" if p_adj < alpha else "AUCUN AVANTAGE FIABLE"
    return {"verdict": v, "wr": wr, "n": n, "z": z, "p": p, "p_adj": p_adj}
