# -*- coding: utf-8 -*-
"""
DAN - Statistiques d'evolution (Phase 7), calculees a partir de l'historique
des analyses (logic/historique.py). Ne modifie rien au calcul du score
lui-meme -- se contente d'agreger des analyses deja enregistrees.
"""
import pandas as pd


def _historique_en_dataframe(historique):
    if not historique:
        return pd.DataFrame()
    df = pd.DataFrame(historique)
    df["horodatage"] = pd.to_datetime(df["date"] + " " + df["heure"])
    return df.sort_values("horodatage")


def evolution_scores(historique):
    """DataFrame [horodatage, score_obtenu, niveau_risque] trie chronologiquement."""
    df = _historique_en_dataframe(historique)
    if df.empty:
        return df
    return df[["horodatage", "score_obtenu", "niveau_risque", "niveau_emoji"]]


def evolution_par_pays(historique):
    """
    Format long [horodatage, pays, score_obtenu], directement lisible
    depuis l'historique (chaque entree y est deja rattachee a un seul
    pays -- contrairement a evolution_par_systeme, pas besoin de
    depaqueter detail_reseaux).
    """
    df = _historique_en_dataframe(historique)
    if df.empty or "pays" not in df.columns:
        return pd.DataFrame(columns=["horodatage", "pays", "score_obtenu"])
    return df[["horodatage", "pays", "score_obtenu"]].dropna(subset=["pays"])


def evolution_par_systeme(historique):
    """
    Format long [horodatage, domaine, score_100], reconstruit a partir du
    detail_reseaux de chaque entree -- une ligne par (analyse x reseau).
    """
    df = _historique_en_dataframe(historique)
    if df.empty:
        return pd.DataFrame(columns=["horodatage", "domaine", "score_100"])
    lignes = []
    for _, row in df.iterrows():
        for d in row.get("detail_reseaux", []):
            lignes.append({
                "horodatage": row["horodatage"],
                "domaine": d["domaine"],
                "score_100": d["score_100"],
            })
    return pd.DataFrame(lignes)


def statistiques_mensuelles(historique):
    """DataFrame [mois, nb_analyses, score_moyen, score_max] groupe par mois."""
    df = _historique_en_dataframe(historique)
    if df.empty:
        return df
    df["mois"] = df["horodatage"].dt.strftime("%Y-%m")
    return (
        df.groupby("mois")
        .agg(nb_analyses=("id", "count"), score_moyen=("score_obtenu", "mean"),
             score_max=("score_obtenu", "max"))
        .round(1)
        .reset_index()
        .sort_values("mois")
    )


def repartition_niveaux(historique):
    """Series : nombre d'analyses par niveau de risque."""
    df = _historique_en_dataframe(historique)
    if df.empty:
        return pd.Series(dtype=int)
    return df["niveau_risque"].value_counts()


def derniers_rapports(historique, n=5):
    """Liste a plat des N derniers rapports generes, tous historiques confondus."""
    resultat = []
    for entree in historique:
        for rap in entree.get("rapports_generes", []):
            resultat.append({
                "date_generation": rap["date_generation"],
                "fichier_source": rap["fichier_source"],
                "chemin": rap["chemin"],
                "niveau": entree["niveau_risque"],
                "emoji": entree["niveau_emoji"],
            })
    resultat.sort(key=lambda r: r["date_generation"], reverse=True)
    return resultat[:n]


def incidents_recents(historique, n=5):
    """Les N analyses les plus recentes ayant enregistre au moins un incident."""
    df = _historique_en_dataframe(historique)
    if df.empty:
        return pd.DataFrame()
    avec_incidents = df[df["nb_incidents"] > 0].sort_values("horodatage", ascending=False)
    return avec_incidents[["horodatage", "systemes_analyses", "nb_incidents", "niveau_risque", "niveau_emoji"]].head(n)
