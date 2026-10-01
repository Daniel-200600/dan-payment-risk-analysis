# -*- coding: utf-8 -*-
"""
DAN - Regroupement et comparaison par pays.

Un lot de fichiers depose en une seule fois peut concerner plusieurs pays
(chacun identifie par le nom du dossier de premier niveau qui contenait ses
fichiers lors d'un depot de dossier entier -- voir
logic.donnees._deduire_pays et normaliser_pays). Ce module regroupe les
evenements par pays et calcule un resume comparatif, sans dupliquer la
logique de score deja centralisee dans logic.donnees.

DAN ne cherche plus a identifier un participant precis (Code Banque) : le
classement se fait uniquement par pays, tel qu'organise par l'equipe de surveillance dans
son arborescence de dossiers -- aucune liste de reference a charger, les
six pays membres de la CEMAC etant un ensemble fixe et connu.
"""
import pandas as pd

from logic.donnees import calculer_scores, PAYS_CEMAC
from logic.interpretation import interpretation_absolue


def grouper_par_pays(evt_df):
    """
    Repartit un DataFrame d'evenements (issu de la concatenation de
    plusieurs fichiers, potentiellement plusieurs pays) en un
    dictionnaire {pays: sous_dataframe}.
    """
    if "pays" not in evt_df.columns:
        return {"INCONNU": evt_df}
    return {
        pays: sous_df.copy()
        for pays, sous_df in evt_df.groupby("pays", dropna=False)
    }


def resume_pays(evt_df, mapping_df, inclure_cemac_complet=False):
    """
    Calcule, pour chaque pays present dans evt_df, son score total, son
    niveau de risque, le nombre de systemes couverts et le nombre
    d'incidents -- sous forme d'un DataFrame trie du plus au moins
    critique, pret pour affichage/comparaison.

    Si inclure_cemac_complet=True, les six pays membres de la CEMAC
    apparaissent tous dans le resultat, y compris ceux pour lesquels
    aucun fichier n'a encore ete importe -- ceux-ci obtiennent le statut
    special "Non transmis" plutot que d'etre absents du tableau.
    """
    groupes = grouper_par_pays(evt_df) if len(evt_df) else {}
    lignes = []
    pays_avec_donnees = set()
    for pays, sous_df in groupes.items():
        df_gravite = calculer_scores(sous_df, mapping_df)
        total = float(df_gravite["gravite"].sum())
        info = interpretation_absolue(total)
        pays_avec_donnees.add(pays)
        lignes.append({
            "pays": pays,
            "systemes_couverts": sorted(sous_df[sous_df["domaine"] != "INCONNU"]["domaine"].unique().tolist()),
            "nb_systemes": sous_df[sous_df["domaine"] != "INCONNU"]["domaine"].nunique(),
            "nb_fichiers": sous_df["fichier_source"].nunique(),
            "nb_evenements": len(sous_df),
            "nb_incidents": int(sous_df["survenance_bin"].sum()),
            "score": round(total, 1),
            "niveau": info["niveau"],
            "couleur": info["couleur"],
            "emoji": info["emoji"],
            "transmis": True,
        })

    if inclure_cemac_complet:
        for pays in PAYS_CEMAC:
            if pays in pays_avec_donnees:
                continue
            lignes.append({
                "pays": pays,
                "systemes_couverts": [], "nb_systemes": 0, "nb_fichiers": 0,
                "nb_evenements": 0, "nb_incidents": 0, "score": None,
                "niveau": "Non transmis", "couleur": "#A0AEC0", "emoji": "⬜",
                "transmis": False,
            })

    resultat = pd.DataFrame(lignes)
    if len(resultat):
        resultat = resultat.sort_values(
            ["transmis", "score"], ascending=[False, False], na_position="last"
        ).reset_index(drop=True)
    return resultat


def filtrer_pays(evt_df, pays):
    """Sous-ensemble des evenements d'un seul pays -- utilise pour le
    'zoom' sur un pays depuis la vue comparative, en reutilisant telles
    quelles les pages existantes (tableau de bord, analyse des
    risques...) qui attendent un evt_df limite a un seul perimetre."""
    if "pays" not in evt_df.columns:
        return evt_df
    return evt_df[evt_df["pays"] == pays].copy()
