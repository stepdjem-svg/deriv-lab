# Role auditeur : cherche activement pourquoi un resultat positif serait faux.
import re

SECRET_RE = re.compile(r"(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})")

def audit(res, ev, n_tests, contract):
    issues = []
    if res["train_end"] > res["test_start"]:
        issues.append("fuite: entrainement et test se chevauchent")
    if ev.get("n", 0) < 200:
        issues.append("echantillon hors echantillon trop petit")
    if contract.get("source") != "proposal":
        issues.append("seuil de rentabilite non issu d'une proposition reelle")
    if n_tests < 1:
        issues.append("correction de tests multiples absente")
    if ev.get("p_adj") is not None and ev["p_adj"] >= 0.05 and ev["verdict"].startswith("AVANTAGE"):
        issues.append("incoherence verdict / p ajustee")
    return issues

def has_secret(text):
    return bool(SECRET_RE.search(text))
