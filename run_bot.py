import argparse, atexit, logging, os, shutil, signal, sys, tempfile
from datetime import datetime
from pathlib import Path

from phase2 import orchestrator
from phase2 import deriv_api

REAL_DIR = Path(__file__).resolve().parent / "deriv-lab-data"
SUBDIRS = ("checkpoints", "journal", "artifacts", "runs")


def setup_logging(base):
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=[
        logging.StreamHandler(),
        logging.FileHandler(base / "journal" / "run_bot.log", encoding="utf-8"),
    ])
    return logging.getLogger("run_bot")


def acquire_lock(base):
    lock = base / ".run_bot.lock"
    if lock.exists():
        try:
            os.kill(int(lock.read_text()), 0)
            sys.exit(f"Instance déjà active (PID {lock.read_text()}).")
        except (ValueError, ProcessLookupError, PermissionError):
            lock.unlink(missing_ok=True)  # verrou périmé après un crash
    lock.write_text(str(os.getpid()))
    atexit.register(lambda: lock.unlink(missing_ok=True))


def backup_trades(base, log):
    src = base / "trades.csv"
    if src.exists():
        dst = base / f"trades.backup-{datetime.now():%Y%m%d-%H%M%S}.csv"
        shutil.copy2(src, dst)
        log.info("Sauvegarde : %s", dst.name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sandbox", action="store_true",
                    help="Copie jetable (rien n'est conservé)")
    ap.add_argument("--allow-non-vrtc", action="store_true",
                    help="Autorise un compte dont l'ID ne commence pas par VRTC")
    args = ap.parse_args()

    if args.sandbox:
        tmp = Path(tempfile.mkdtemp(prefix="deriv-lab-sandbox-"))
        base = tmp / "deriv-lab-data"
        if REAL_DIR.exists():
            shutil.copytree(REAL_DIR, base, ignore=shutil.ignore_patterns("*.lock"))
        atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    else:
        base = REAL_DIR

    for d in SUBDIRS:
        (base / d).mkdir(parents=True, exist_ok=True)
    log = setup_logging(base)

    acct = os.environ.get("DERIV_ACCOUNT_ID", "")
    log.info("Mode : %s | Compte : %s*** | Dossier : %s",
             "SANDBOX" if args.sandbox else "DÉFINITIF", acct[:4], base)
    if not acct.startswith("VRTC") and not args.allow_non_vrtc:
        log.error("Compte non reconnu comme démo (VRTC). Arrêt par sécurité.")
        return 2

    acquire_lock(base)
    if not args.sandbox:
        backup_trades(base, log)

    def stop(signum, _frame):
        log.warning("Signal %s reçu : arrêt propre.", signum)
        raise KeyboardInterrupt
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    api = None
    try:
        api = deriv_api.Deriv()
        orchestrator.run(api, str(base))
        log.info("Exécution terminée avec succès.")
        return 0
    except KeyboardInterrupt:
        log.warning("Interrompu par l'utilisateur.")
        return 130
    except Exception:
        log.exception("Échec de l'orchestrateur.")
        return 1
    finally:
        close = getattr(api, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                log.exception("Erreur à la fermeture de l'API.")


if __name__ == "__main__":
    sys.exit(main())
