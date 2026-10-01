# -*- coding: utf-8 -*-
"""
DAN - Configuration de l'application (Phase 9).

Stockage JSON, meme logique que l'historique (data/processed/configuration.json).
Toute page qui a besoin d'un reglage (couleurs, nom institution, options IA...)
appelle charger_configuration() -- jamais de valeur codee en dur ailleurs que
dans DEFAUTS ci-dessous.
"""
import json
import os
import shutil
from datetime import datetime

from chemins import chemin_donnees

CHEMIN_CONFIG = chemin_donnees("data/processed/configuration.json")

DEFAUTS = {
    "nom_application": "DAN",
    "nom_institution": "Institution (à configurer)",
    "direction": "Cellule de surveillance des systèmes de paiement",
    "version": "1.0",
    "responsable": "",
    "theme": "clair",  # "clair" ou "sombre"
    "couleur_principale": "#0B2E59",
    "couleur_secondaire": "#C9A227",
    "ia_recommandations": True,
    "ia_resume_intelligent": True,
    "ia_generation_auto": False,
    "ia_modele_ollama": "mistral",
    "chemin_sauvegarde": "outputs/rapports",
    # Seuils de gravite ABSOLUE (Critique / Eleve / Moyen / Faible -- sinon
    # Tres faible), modifiables par l'agent selon ses propres besoins
    # d'analyse -- voir Parametres. Valeurs de depart calibrees
    # empiriquement (voir logic/interpretation.py), pas une norme figee.
    "seuils_gravite": [25, 10, 3, 0.5],
    # Nombre de participants ATTENDUS par pays (donnee institutionnelle,
    # modifiable par l'agent -- voir Parametres). Valeurs de depart
    # purement illustratives (60 au total), a adapter dans Parametres.
    "participants_attendus": {
        "Cameroun": 10, "Congo": 10, "Tchad": 10,
        "Guinée Équatoriale": 10, "Gabon": 10, "Centrafrique": 10,
    },
    # Nombre de participants RECUS par pays, saisi/corrige manuellement par
    # l'agent (voir Parametres) -- prioritaire sur le comptage automatique
    # de DAN (base sur les dossiers du lot importe) quand une valeur est
    # presente ici pour un pays donne. Vide par defaut : DAN utilise alors
    # son estimation automatique.
    "participants_recus_manuel": {},
}


def construire_participants_depuis_tableau(df_edite):
    """
    Extrait (attendus, recus_manuels) a partir du tableau edite par
    l'agent dans Parametres -> Participants attendus/recus (voir
    pages_dan.parametres). Fonction pure, testable independamment du
    widget Streamlit qui la produit (st.data_editor) -- ce dernier
    supporte deja l'ajout et la suppression de lignes via
    num_rows="dynamic" ; cette fonction se contente de refleter EXACTEMENT
    les lignes presentes dans le tableau au moment de l'enregistrement,
    qu'un pays ait ete ajoute, retire ou renomme par l'agent.

    Une ligne dont le nom de pays est vide est ignoree (evite qu'une ligne
    vierge laissee par l'agent ne pollue la configuration).
    """
    nouveaux_attendus = {}
    nouveaux_recus_manuels = {}
    for _, ligne in df_edite.iterrows():
        pays = str(ligne.get("Pays", "")).strip()
        if not pays or pays.lower() == "nan":
            continue
        attendu = ligne.get("Attendu")
        nouveaux_attendus[pays] = int(attendu) if attendu is not None and str(attendu) != "nan" else 0

        valeur_manuelle = ligne.get("Reçu (correction manuelle, optionnel)")
        if valeur_manuelle is not None and str(valeur_manuelle).strip() not in ("", "nan", "None"):
            nouveaux_recus_manuels[pays] = int(valeur_manuelle)
    return nouveaux_attendus, nouveaux_recus_manuels


def valider_seuils_gravite(seuils):
    """
    Verifie qu'une liste de 4 seuils [critique, eleve, moyen, faible] est
    utilisable pour classer un niveau de risque : 4 nombres strictement
    positifs et strictement decroissants (le niveau Critique doit
    correspondre a la gravite la plus elevee, jusqu'a Faible qui est le
    plus proche de zero -- sinon la classification en cascade de
    interpretation_absolue() donnerait des resultats incoherents).
    Renvoie (est_valide, message).
    """
    if len(seuils) != 4:
        return False, "Il faut exactement 4 seuils (Critique, Élevé, Moyen, Faible)."
    try:
        valeurs = [float(s) for s in seuils]
    except (TypeError, ValueError):
        return False, "Les seuils doivent être des nombres."
    if any(v <= 0 for v in valeurs):
        return False, "Les seuils doivent être strictement positifs."
    if not (valeurs[0] > valeurs[1] > valeurs[2] > valeurs[3]):
        return False, (
            "Les seuils doivent être strictement décroissants : "
            "Critique > Élevé > Moyen > Faible."
        )
    return True, "Seuils valides."


def charger_configuration():
    """Renvoie la configuration actuelle, complétée par les défauts pour
    toute cle manquante (robuste a un fichier partiel ou a une ancienne version)."""
    config = dict(DEFAUTS)
    if os.path.exists(CHEMIN_CONFIG):
        try:
            with open(CHEMIN_CONFIG, encoding="utf-8") as f:
                config.update(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass
    return config


def sauvegarder_configuration(config):
    os.makedirs(os.path.dirname(CHEMIN_CONFIG), exist_ok=True)
    with open(CHEMIN_CONFIG, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def reinitialiser_configuration():
    sauvegarder_configuration(dict(DEFAUTS))
    return dict(DEFAUTS)


def exporter_configuration_json():
    """Renvoie la configuration actuelle sous forme de texte JSON, pour telechargement."""
    return json.dumps(charger_configuration(), ensure_ascii=False, indent=2)


def importer_configuration_json(texte_json):
    """Valide et remplace la configuration a partir d'un JSON fourni par l'utilisateur."""
    nouvelle_config = json.loads(texte_json)  # leve ValueError si invalide
    config = dict(DEFAUTS)
    config.update(nouvelle_config)
    sauvegarder_configuration(config)
    return config


def remplacer_image(fichier_uploade, destination):
    """Enregistre un logo/filigrane uploade a l'emplacement attendu, avec
    sauvegarde de l'ancien fichier (horodatee) plutot qu'un ecrasement sec."""
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    if os.path.exists(destination):
        horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
        sauvegarde = f"{destination}.backup_{horodatage}"
        shutil.copy(destination, sauvegarde)
    with open(destination, "wb") as f:
        f.write(fichier_uploade.getbuffer())
