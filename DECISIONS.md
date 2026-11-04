# Decisions

Each decision: what, why, and when to revisit. Add new ones at the bottom; never rewrite old ones.

**D001 - Free stack only.** GitHub (private repo) for code, versions and the journal export; Google Drive for data
and backups; Colab for compute; GitHub Actions for tests. No paid plan, no paid API.

**D002 - Demo only.** No real-money trade without explicit written authorisation from the owner. The bot code
refuses a real-account endpoint; experiments use public market data only.

**D003 - Pre-registration.** A hypothesis, its exact rule and its pass/fail criteria are written to the journal
before the run. `Journal.record_result` refuses a result if the rule or criteria changed (SHA-256 fingerprint).
Changing a rule means registering a NEW hypothesis.

**D004 - Secrets.** Never in the repository, never in `.git/config`, never printed. Colab Secrets only. The GitHub
token is fine-grained, limited to this one repository, permission "Contents: Read and write". Scheduled collectors
must use Deriv's public endpoint (no Deriv token).

**D005 - Where things live.** Drive is the authoritative store for data (journal, runs, artifacts, checkpoints,
backups). GitHub holds code plus an exported copy of the journal (`journal/journal.jsonl`, `journal/JOURNAL.md`)
for history. Large CSV results stay in Drive.

**D006 - The four roles are code, not paid AI agents.** Researcher (writes pre-registrations), developer (experiment
scripts), statistician (tests, thresholds, multiple-testing guard), auditor (`Journal.verify`, the pre-registration
guard, CI tests). They are modules that run in Colab or Actions. The human-in-the-loop researcher is the Claude chat.

**D007 - Preserve what works.** Existing scripts are copied unchanged into `experiments/` and `bot/`. They are
refactored into shared modules only when covered by tests (phase 2).

**D008 - Actions: tests now, schedules later.** CI runs the tests on every push. Scheduled collection is NOT enabled
yet: sources disagree on whether schedule triggers run in private repositories of free accounts. Known limits: 5-minute
minimum interval, delays under load, 2,000 free minutes per month for private repos, and public repos lose schedules after
60 days without activity. Test with a tiny scheduled workflow before relying on it.

**D009 - Colab limits are respected, not bypassed.** Free sessions end (about 12 h max, idle timeout). Every long job
saves a `Checkpoint` and can resume. No keep-alive tricks.
