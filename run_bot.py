import os
from phase2 import orchestrator
from phase2 import deriv_api

BASE_DIR = "deriv-lab-data"

def main():
    print("=== Démarrage de l'orchestrateur Deriv (Mode Démo) ===")
    for d in ("checkpoints", "journal", "artifacts"):
        os.makedirs(os.path.join(BASE_DIR, d), exist_ok=True)
    
    print("Initialisation de l'API Deriv...")
    api = deriv_api.Deriv()
    
    print(f"Dossier de travail cible : {BASE_DIR}")
    print("Lancement de l'orchestrateur en cours...")
    
    orchestrator.run(api, BASE_DIR)
    print("Exécution terminée avec succès.")

if __name__ == "__main__":
    main()
