import csv, sys, os
sys.path.insert(0, '.')
from lab import judge

def load(p):
    try:
        rows = list(csv.DictReader(open(p)))
    except Exception:
        return []
    if rows and 'strategy' in rows[0] and 'status' in rows[0] and 'profit' in rows[0]:
        return rows
    return []

cands = []
for base in ('/workspaces', os.path.expanduser('~')):
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__pycache__', '.cache')]
        for f in files:
            if f.startswith('trades') and f.endswith('.csv'):
                p = os.path.join(root, f)
                rows = load(p)
                if rows:
                    cands.append((len(rows), p, rows))
cands.sort(key=lambda c: c[0], reverse=True)
if not cands:
    print("AUCUN fichier de trades valide")
    sys.exit(1)
for n, p, _ in cands[:3]:
    print(n, "lignes", p[-35:])
_, path, rows = cands[0]

start = 0
for i in range(1, len(rows)):
    try:
        if abs(float(rows[i]['session_pnl']) - float(rows[i]['profit'])) < 1e-9:
            start = i
    except Exception:
        pass
sub = rows[start:]
print("session finale:", len(sub), "trades")

def stat(name):
    r = [x for x in sub if x['strategy'] == name and x['status'] in ('won', 'lost')]
    return len(r), sum(x['status'] == 'won' for x in r), sum(float(x['profit']) for x in r)

p0 = 1 / 1.9
ns, ws, ps = stat('sma')
nr, wr, pr = stat('random')
print("sma", ns, ws, round(ps, 2))
print("rnd", nr, wr, round(pr, 2))
print("be", round(judge.break_even(1.0, 1.9), 4))
print("z sma", round(judge.z_vs(ws, ns, p0), 2), "| rnd", round(judge.z_vs(wr, nr, p0), 2))
print("sma vs rnd", str(judge.two_prop_z(ws, ns, wr, nr))[:30])

shown = False
for label, ctl in (("tuple", (wr, nr)), ("dict", {"wins": wr, "n": nr}), ("none", None)):
    try:
        res = judge.evaluate(ws, ns, p0, 1, control=ctl)
    except Exception as e:
        print("evaluate", label, "ERR", type(e).__name__, str(e)[:40])
        continue
    g = res.get('gates', {}) if isinstance(res, dict) else {}
    ok = g.get('beats_random_control') is not None
    if ok or label == "none":
        print("== evaluate control:", label)
        for k in ('verdict', 'z', 'z_bar', 'win_rate', 'ev_per_stake', 'trades', 'trades_needed'):
            if k in res:
                print(" ", k, res[k])
        for k, v in g.items():
            print("  gate", k, v)
        for r_ in res.get('reasons', []):
            print("  why:", str(r_)[:50])
        shown = True
        break
if not shown:
    print("evaluate: rien d'affichable")
