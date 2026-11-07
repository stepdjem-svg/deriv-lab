# PROJECT_STATE - deriv-lab

Mission : voir MISSION.md (seule copie de référence, ne pas dupliquer).
Règles : démo uniquement, aucun trade réel sans autorisation écrite, aucun secret dans le dépôt,
pré-enregistrement avant tout nouveau test, aucune stratégie présentée comme rentable sans preuve.
Décisions : DECISIONS.md. Journal détaillé : journal/JOURNAL.md (généré, ne pas éditer à la main).

## Ce qui est en place
- Lab : persistance Drive, checkpoints, synchro GitHub, journal pré-enregistré, juge statistique (lab/judge.py).
- Bot démo : bot/agent.py (SMA vs contrôle aléatoire). Non relancé sans nouvelle hypothèse pré-enregistrée.
<!-- AUTO:START -->
Expériences pré-enregistrées (journal) :
- P001 Mean reversion on WLD baskets with a 1-tick entry delay : not_supported (R003)
- P002 Next-candle direction predictability (lagged returns) on Deriv real markets : not_supported (R001)
- P003 Intraday momentum on indices and metals : not_supported (R002)
- P004 Forex session continuation: Asia direction predicts London direction : not_supported (R004)

Derniers commits :
```
f8f1a87 P004 session continuation: not_supported (52.2%, below 54.9% hurdle)
0d0061e close autolab research line: not_supported
32c67f0 UPDATE MD: handoff (AUTO block), autolab, probe; ignore local data
270f193 UPDATE MD: handoff via lab.handoff (AUTO block, research log)
d9f97f2 run_bot: logging, verrou, arrêt propre, garde compte démo
```

Prochaines tâches :
- P005 prêt (experiments/overreaction.py) : retournement après une bougie extrême (>= 2,5 écarts-types), forex + métaux,
  15 min et 1 h, seuil 54,9 %. Lancer dans Colab après autolab.py (cache des bougies), puis python3 -m lab.handoff.
- Lancer le test pré-enregistré sur de nouvelles données (plus de bougies) avant toute conclusion.
- Momentum intraday indices 30 min / 1 h (seuil 54,9 %) : pas encore testé avec assez de données.
- Contrats 1 jour : barrière à vérifier (longcode) avant tout calcul de gain.
- Proposer la prochaine expérience à partir des résultats du journal ; ne pas répéter un test sans justification.
<!-- AUTO:END -->