# -*- coding: utf-8 -*-
"""DAN - Journalisation simple des erreurs dans un fichier texte local."""
import os
from datetime import datetime

from chemins import chemin_donnees

CHEMIN_LOG = chemin_donnees("data/processed/erreurs.log")


def journaliser_erreur(contexte, erreur):
    os.makedirs(os.path.dirname(CHEMIN_LOG), exist_ok=True)
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(CHEMIN_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{horodatage}] {contexte} : {erreur}\n")
