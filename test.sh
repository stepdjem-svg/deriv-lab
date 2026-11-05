cd /workspaces/deriv-lab || exit 1
if [ "$1" = "resume" ]; then
  echo "=== RESUME ==="
  pgrep -f "python3 bot/agent.py" >/dev/null && echo "Statut : EN COURS" || echo "Statut : ARRETE"
  echo "Trades achetes : $(grep -c 'Bought' run.log)"
  echo "Coupures connexion : $(grep -c 'Connection problem' run.log)"
  echo "Erreurs : $(grep -c -E 'ERROR|Traceback' run.log)"
  grep 'SUMMARY' run.log | tail -n 2
  grep 'Session P&L' run.log | tail -n 1
  grep -E 'Max trades|Loss limit|losses in a row' run.log | tail -n 1
  exit 0
fi
echo "1) Ancien bot ?"
if pgrep -f "python3 bot/agent.py" >/dev/null; then echo "ARRET : un bot tourne deja (pkill -f agent.py)"; exit 1; fi
echo "OK, aucun bot"
echo "2) Reglages :"
grep -n -E "max_daily_loss:|max_consecutive_losses:|max_trades:|cooldown_s:|strategy:|dry_run:" bot/agent.py
grep -q "dry_run: bool = False" bot/agent.py || { echo "ARRET : dry_run n'est pas False"; exit 1; }
echo "3) Lancement..."
nohup python3 bot/agent.py > run.log 2>&1 &
sleep 25
echo "4) Verification :"
tail -n 6 run.log
if grep -q "Connected (demo)" run.log && grep -q "strategy=ab, dry_run=False" run.log; then
  echo "=== RESUME DEMARRAGE : OK (demo, strategie ab, reel=False) ==="
  echo "Suivi plus tard : bash test.sh resume"
else
  pkill -f "python3 bot/agent.py"
  echo "=== RESUME DEMARRAGE : ECHEC, bot arrete. Copiez-moi ce qui precede ==="
fi
