"""UPDATE MD: refresh PROJECT_STATE.md (AUTO block only) and RESEARCH_LOG.md from the journal. Stdlib only.

Run from the repo root:   python3 -m lab.handoff            (writes, with .bak backups)
                          python3 -m lab.handoff --dry-run  (shows what would change)
Hand-written text outside the AUTO markers is never touched. MISSION.md is never written here.
"""
import shutil
import subprocess
import sys
from pathlib import Path

from .journal import Journal
from .paths import ensure_dirs

ROOT = Path(__file__).resolve().parents[1]
START, END = "<!-- AUTO:START -->", "<!-- AUTO:END -->"

HEAD = """# PROJECT_STATE - deriv-lab

Mission : voir MISSION.md (seule copie de référence, ne pas dupliquer).
Règles : démo uniquement, aucun trade réel sans autorisation écrite, aucun secret dans le dépôt,
pré-enregistrement avant tout nouveau test, aucune stratégie présentée comme rentable sans preuve.
Décisions : DECISIONS.md. Journal détaillé : journal/JOURNAL.md (généré, ne pas éditer à la main).

## Ce qui est en place
- Lab : persistance Drive, checkpoints, synchro GitHub, journal pré-enregistré, juge statistique (lab/judge.py).
- Bot démo : bot/agent.py (SMA vs contrôle aléatoire). Non relancé sans nouvelle hypothèse pré-enregistrée.
"""

NEXT = """- P005 prêt (experiments/overreaction.py) : retournement après une bougie extrême (>= 2,5 écarts-types), forex + métaux,
  15 min et 1 h, seuil 54,9 %. Lancer dans Colab après autolab.py (cache des bougies), puis python3 -m lab.handoff.
- Lancer le test pré-enregistré sur de nouvelles données (plus de bougies) avant toute conclusion.
- Momentum intraday indices 30 min / 1 h (seuil 54,9 %) : pas encore testé avec assez de données.
- Contrats 1 jour : barrière à vérifier (longcode) avant tout calcul de gain.
- Proposer la prochaine expérience à partir des résultats du journal ; ne pas répéter un test sans justification.
"""


def git_log(n=5):
    try:
        out = subprocess.run(["git", "log", f"-{n}", "--oneline"], cwd=ROOT, capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "(no git history)"
    except Exception as e:  # git missing: keep going
        return f"(git unavailable: {e})"


def auto_block(j):
    prereg = [e for e in j.events() if e.get("type") == "prereg"]
    results = {e["prereg_id"]: e for e in j.events() if e.get("type") == "result"}
    lines = ["Expériences pré-enregistrées (journal) :"]
    for p in prereg:
        r = results.get(p["id"])
        status = f"{r['verdict']} ({r['id']})" if r else "OUVERTE (aucun résultat enregistré)"
        lines.append(f"- {p['id']} {p['title']} : {status}")
    if not prereg:
        lines.append("- (aucune)")
    lines += ["", "Derniers commits :", "```", git_log(), "```", "", "Prochaines tâches :", NEXT.rstrip()]
    return "\n".join(lines)


def research_log(j):
    legacy = [e for e in j.events() if e.get("type") == "legacy"]
    out = ["# RESEARCH_LOG - deriv-lab", "",
           "Journal narratif. Source détaillée et horodatée : journal/journal.jsonl et journal/JOURNAL.md.",
           "Règle : une entrée par expérience, avec verdict. Les anciennes entrées ne sont jamais réécrites.", "",
           "## Expériences antérieures au pré-enregistrement"]
    for e in legacy:
        out.append(f"- {e.get('id')} ({e.get('date', '')}) {e.get('title', '')} : {e.get('verdict', '?')}")
        out.append(f"  {e.get('summary', '')}")
    out += ["", "## Expériences pré-enregistrées", ""]
    for e in j.events():
        if e.get("type") in ("prereg", "result", "decision"):
            text = e.get("title") or e.get("verdict") or e.get("text", "")
            out.append(f"- {e.get('id')} {e.get('ts', '')[:10]} : {text}")
    return "\n".join(out) + "\n"


def write_safe(path, text, dry):
    if dry:
        print(f"[dry-run] would write {path.name} ({len(text)} chars)")
        return
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    print(f"written {path.name}")


def update(dry=False):
    j = Journal(ensure_dirs())
    project = ROOT / "PROJECT_STATE.md"
    body = project.read_text(encoding="utf-8") if project.exists() else HEAD + START + "\n" + END + "\n"
    if START in body and END in body:
        pre, rest = body.split(START, 1)
        _, post = rest.split(END, 1)
        head = pre if pre.strip() else HEAD
    else:
        head, post = body.rstrip() + "\n\n", ""
    new = head.rstrip() + "\n" + START + "\n" + auto_block(j) + "\n" + END + post
    write_safe(project, new, dry)
    write_safe(ROOT / "RESEARCH_LOG.md", research_log(j), dry)
    if not dry:
        Path(ROOT / "journal").mkdir(exist_ok=True)
        (ROOT / "journal" / "JOURNAL.md").write_text(j.render_markdown(), encoding="utf-8")
        print("regenerated journal/JOURNAL.md | verify:", j.verify())


if __name__ == "__main__":
    update(dry="--dry-run" in sys.argv)
