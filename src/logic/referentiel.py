# -*- coding: utf-8 -*-
"""
DAN - Gestion des mises a jour du referentiel (table de correspondance des
risques, mapping/mapping_risques.xlsx).

Principe retenu : DAN n'exploite QUE cette table de correspondance (aucune
autre partie de l'application ne relit les documents Word du referentiel
de surveillance) -- la mettre a jour consiste donc a remplacer ce fichier par une
version corrigee/completee, prealablement editee hors ligne (Excel) par
l'equipe de surveillance ou l'analyste. Ce module fournit :
  - la validation d'un fichier candidat avant remplacement,
  - le remplacement effectif, avec sauvegarde horodatee de l'ancienne
    version (retour en arriere toujours possible),
  - la reconstruction automatique de la colonne Domaine a partir des codes
    evenement, pour eviter la recurrence du bug ou cette colonne restait
    vide (corrige le 2026-08-03).
"""
import os
import re
import shutil
from datetime import datetime

import pandas as pd

from chemins import chemin_ressource, chemin_donnees

CHEMIN_MAPPING = chemin_ressource("mapping/mapping_risques.xlsx")
DOSSIER_VERSIONS = chemin_donnees("mapping/versions_precedentes")

COLONNES_REQUISES = [
    "Code événement", "Événement", "Domaine", "Site", "Code référentiel",
    "Élément d'appréciation", "Risque(s)", "Niveau", "Confiance", "Justification",
]

CODES_DOMAINE = {"SYG": "SYGMA", "SWI": "SWIFT", "SYS": "SYSTAC", "RES": "RESEAU"}
MOTIF_CODE_EVENEMENT = re.compile(r"^RP(SYG|SWI|SYS|RES)")


def _deduire_domaine(code_evenement):
    m = MOTIF_CODE_EVENEMENT.match(str(code_evenement).strip().upper())
    return CODES_DOMAINE[m.group(1)] if m else None


def valider_fichier_mapping(fichier_uploade):
    """
    Verifie qu'un fichier candidat peut remplacer la table de correspondance
    active. Renvoie (est_valide, messages, dataframe_corrige_ou_None).

    messages est une liste de chaines : erreurs bloquantes si est_valide
    est False, avertissements informatifs sinon (ex : domaines reconstruits).
    """
    messages = []
    try:
        df = pd.read_excel(fichier_uploade)
    except Exception as e:
        return False, [f"Fichier illisible : {e}"], None

    colonnes_manquantes = [c for c in COLONNES_REQUISES if c not in df.columns]
    if colonnes_manquantes:
        return False, [
            "Colonnes manquantes par rapport au format attendu : "
            + ", ".join(colonnes_manquantes)
        ], None

    if len(df) == 0:
        return False, ["Le fichier ne contient aucune ligne."], None

    doublons = df["Code événement"].duplicated().sum()
    if doublons > 0:
        messages.append(
            f"⚠️ {doublons} code(s) événement en double détecté(s) — la dernière "
            f"occurrence de chaque doublon sera conservée."
        )
        df = df.drop_duplicates(subset=["Code événement"], keep="last")

    # Reconstruction systematique de la colonne Domaine a partir du code
    # evenement, plutot que de faire confiance a une colonne potentiellement
    # vide ou incoherente (c'est exactement le bug corrige sur la version
    # precedente de ce fichier).
    domaine_deduit = df["Code événement"].apply(_deduire_domaine)
    incoherences = int((df["Domaine"].notna() & (df["Domaine"] != domaine_deduit)).sum())
    non_deductibles = int(domaine_deduit.isna().sum())
    df["Domaine"] = domaine_deduit

    if incoherences > 0:
        messages.append(
            f"ℹ️ {incoherences} ligne(s) avaient un domaine différent de celui déduit "
            f"du code événement — corrigées automatiquement (le code fait foi)."
        )
    if non_deductibles > 0:
        messages.append(
            f"⚠️ {non_deductibles} ligne(s) ont un code événement qui ne suit pas la "
            f"codification RP[SYG|SWI|SYS|RES]... attendue — leur domaine n'a pas pu "
            f"être déterminé et reste vide."
        )

    return True, messages, df


def resume_mapping(chemin=None):
    """Petit etat des lieux d'une table de correspondance (actuelle ou
    candidate), pour affichage avant/apres remplacement.

    chemin=None resout CHEMIN_MAPPING au moment de l'appel (et non a la
    definition de la fonction) -- necessaire pour que ce module reste
    testable via monkeypatch (voir tests/test_referentiel.py)."""
    if chemin is None:
        chemin = CHEMIN_MAPPING
    if not os.path.exists(chemin):
        return None
    df = pd.read_excel(chemin)
    return {
        "nb_lignes": len(df),
        "par_domaine": df["Domaine"].value_counts().to_dict() if "Domaine" in df.columns else {},
        "par_confiance": df["Confiance"].value_counts().to_dict() if "Confiance" in df.columns else {},
        "derniere_modification": (
            datetime.fromtimestamp(os.path.getmtime(chemin)) if chemin == CHEMIN_MAPPING else None
        ),
    }


def remplacer_mapping(nouveau_df):
    """
    Remplace la table de correspondance active par nouveau_df, apres avoir
    sauvegarde une copie horodatee de l'ancienne version dans
    mapping/versions_precedentes/ (permet un retour en arriere via
    restaurer_version). Le cache Streamlit de charger_mapping() doit etre
    vide par l'appelant (st.cache_data.clear()) pour que le changement soit
    visible immediatement dans le reste de l'application.
    """
    os.makedirs(DOSSIER_VERSIONS, exist_ok=True)
    if os.path.exists(CHEMIN_MAPPING):
        horodatage = datetime.now().strftime("%Y%m%d_%H%M%S_%f")  # microseconde : evite toute collision entre operations rapprochees
        shutil.copy(
            CHEMIN_MAPPING,
            os.path.join(DOSSIER_VERSIONS, f"mapping_risques_{horodatage}.xlsx"),
        )
    nouveau_df.to_excel(CHEMIN_MAPPING, index=False)


def lister_versions_precedentes():
    """Versions sauvegardees, les plus recentes en premier."""
    if not os.path.exists(DOSSIER_VERSIONS):
        return []
    fichiers = [f for f in os.listdir(DOSSIER_VERSIONS) if f.endswith(".xlsx")]
    return sorted(fichiers, reverse=True)


def restaurer_version(nom_fichier):
    """Restaure une version precedente comme table active (l'actuelle est
    elle-meme sauvegardee avant d'etre remplacee, via remplacer_mapping)."""
    chemin_source = os.path.join(DOSSIER_VERSIONS, nom_fichier)
    if not os.path.exists(chemin_source):
        raise FileNotFoundError(f"Version introuvable : {nom_fichier}")
    remplacer_mapping(pd.read_excel(chemin_source))


# ---------------------------------------------------------------------------
# Guide de surveillance (document Word normatif qui definit la nomenclature
# des codes du referentiel). C'est ce document -- pas la table de
# correspondance ci-dessus -- qui evolue dans le temps du point de vue
# institutionnel et necessite une mise a jour occasionnelle, sous le meme
# format (Word) que l'original.
# ---------------------------------------------------------------------------
CHEMIN_GUIDE = chemin_ressource("referentiels/GUIDE_DE_SURVEILLANCE.docx")
DOSSIER_VERSIONS_GUIDE = chemin_donnees("referentiels/versions_precedentes_guide")


def resume_guide():
    """Petit etat des lieux du Guide de surveillance actuellement en place."""
    if not os.path.exists(CHEMIN_GUIDE):
        return None
    from docx import Document
    try:
        doc = Document(CHEMIN_GUIDE)
        nb_paragraphes = len(doc.paragraphs)
    except Exception:
        nb_paragraphes = None
    return {
        "nb_paragraphes": nb_paragraphes,
        "taille_ko": round(os.path.getsize(CHEMIN_GUIDE) / 1024, 1),
        "derniere_modification": datetime.fromtimestamp(os.path.getmtime(CHEMIN_GUIDE)),
    }


def valider_fichier_guide(fichier_uploade):
    """
    Verifie qu'un fichier candidat est un document Word exploitable avant de
    remplacer le Guide de surveillance. Contrairement a la table de
    correspondance, aucune structure de colonnes n'est imposee -- le guide
    est un document normatif en texte libre, pas une donnee tabulaire.
    Renvoie (est_valide, message).
    """
    nom = getattr(fichier_uploade, "name", "")
    if not nom.lower().endswith(".docx"):
        return False, "Le Guide de surveillance doit être déposé au format Word (.docx), comme l'original."
    try:
        from docx import Document
        doc = Document(fichier_uploade)
        if len(doc.paragraphs) == 0:
            return False, "Le document déposé semble vide."
    except Exception as e:
        return False, f"Fichier Word illisible : {e}"
    fichier_uploade.seek(0)
    return True, "Document valide."


def remplacer_guide(fichier_uploade):
    """Remplace le Guide de surveillance actif par le fichier depose, apres
    avoir sauvegarde une copie horodatee de l'ancienne version (retour en
    arriere possible via restaurer_version_guide)."""
    os.makedirs(DOSSIER_VERSIONS_GUIDE, exist_ok=True)
    if os.path.exists(CHEMIN_GUIDE):
        horodatage = datetime.now().strftime("%Y%m%d_%H%M%S_%f")  # microseconde : evite toute collision entre operations rapprochees
        shutil.copy(
            CHEMIN_GUIDE,
            os.path.join(DOSSIER_VERSIONS_GUIDE, f"GUIDE_DE_SURVEILLANCE_{horodatage}.docx"),
        )
    with open(CHEMIN_GUIDE, "wb") as f:
        f.write(fichier_uploade.getbuffer() if hasattr(fichier_uploade, "getbuffer") else fichier_uploade.read())


def lister_versions_precedentes_guide():
    if not os.path.exists(DOSSIER_VERSIONS_GUIDE):
        return []
    fichiers = [f for f in os.listdir(DOSSIER_VERSIONS_GUIDE) if f.endswith(".docx")]
    return sorted(fichiers, reverse=True)


def restaurer_version_guide(nom_fichier):
    chemin_source = os.path.join(DOSSIER_VERSIONS_GUIDE, nom_fichier)
    if not os.path.exists(chemin_source):
        raise FileNotFoundError(f"Version introuvable : {nom_fichier}")
    os.makedirs(DOSSIER_VERSIONS_GUIDE, exist_ok=True)
    if os.path.exists(CHEMIN_GUIDE):
        horodatage = datetime.now().strftime("%Y%m%d_%H%M%S_%f")  # microseconde : evite toute collision entre operations rapprochees
        shutil.copy(
            CHEMIN_GUIDE,
            os.path.join(DOSSIER_VERSIONS_GUIDE, f"GUIDE_DE_SURVEILLANCE_{horodatage}.docx"),
        )
    shutil.copy(chemin_source, CHEMIN_GUIDE)
