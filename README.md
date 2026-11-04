# deriv-lab

Free, private research lab for Deriv **demo** experiments. Phase 1: persistence, journal, GitHub sync.

## Layout
- `lab/` persistence (`storage`), pre-registered journal (`journal`), git sync (`gitsync`), Colab setup (`colab`), checks (`selftest`)
- `experiments/` the scripts from earlier work, unchanged (audit, contracts, candles, structure, followup, forward_test, scan)
- `bot/` the demo trading bot (needs a Deriv token, DEMO only) and `bot/archive/` older versions
- `journal/` `seed.jsonl` (earlier experiments), plus `journal.jsonl` and `JOURNAL.md` after the first sync
- `tests/` run with `python -m unittest discover -s tests -v`
- `DECISIONS.md` the decision log

## One-time setup (iPhone)
1. GitHub: create a **private** repository named `deriv-lab`, EMPTY (no README, no license, no .gitignore).
2. GitHub > Settings > Developer settings > Fine-grained tokens > new token: repository access
   "Only select repositories" = deriv-lab; permission Repository > **Contents: Read and write**. Expiry 90 days.
3. Colab > key icon > add secrets (Notebook access ON): `GITHUB_TOKEN` (the token) and `GITHUB_REPO` (`your-username/deriv-lab`).
4. Colab > folder icon > upload `deriv-lab.zip`, then run:
```python
!unzip -q -o /content/deriv-lab.zip -d /content
import sys; sys.path.insert(0, "/content/deriv-lab")
from lab import colab, selftest
ctx = colab.setup()        # mounts Drive, pushes the project to GitHub the first time
selftest.run(ctx)          # must end with: PHASE 1 VERIFIED
```

## After every Colab reset (resume)
```python
from google.colab import userdata, drive
import subprocess, sys
drive.mount("/content/drive")
t, r = userdata.get("GITHUB_TOKEN"), userdata.get("GITHUB_REPO")
p = subprocess.run(["git", "clone", f"https://x-access-token:{t}@github.com/{r}.git", "/content/deriv-lab"],
                   capture_output=True, text=True)
print((p.stdout + p.stderr).replace(t, "***"))
sys.path.insert(0, "/content/deriv-lab")
from lab import colab
ctx = colab.setup()
```
(If `/content/deriv-lab` still exists, skip the clone: `colab.setup()` alone updates it.)

## Daily use
```python
from lab.storage import save_artifact, new_run_id
rid = new_run_id("audit")
save_artifact("/content/audit.csv", rid)       # copies to Drive with a SHA-256 check
ctx["journal"].note("what I learned")          # persistent, append-only
colab.sync(ctx)                                # journal -> GitHub (history + backup)
```
