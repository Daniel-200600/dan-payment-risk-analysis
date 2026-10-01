# -*- coding: utf-8 -*-
"""
DAN - Historique persistant des analyses.

Stockage : data/processed/historique.json (une liste d'entrees). Pas de
base de donnees necessaire vu le volume attendu (quelques dizaines/centaines
d'analyses) -- un fichier JSON reste simple a lire, filtrer et sauvegarder.
"""
import json
import os
import getpass
import uuid
from datetime import datetime

from chemins import chemin_donnees

CHEMIN_HISTORIQUE = chemin_donnees("data/processed/historique.json")


def detecter_import_duplique(fichiers_sources_actuels, historique=None):
    """
    Verifie si le lot de fichiers sur le point d'etre importe (identifie
    par l'ensemble de leurs noms) correspond EXACTEMENT a un import deja
    enregistre dans l'historique -- rien n'empechait jusqu'ici d'importer
    deux fois le meme mois par erreur, ce qui aurait fausse les tendances
    et l'historique sans avertissement.

    Renvoie l'entree correspondante (la plus recente en cas de plusieurs
    correspondances) si un doublon exact est trouve, sinon None. Ne
    bloque rien par lui-meme : c'est a l'appelant de decider quoi faire
    de ce signalement (avertir, demander confirmation...).
    """
    if historique is None:
        historique = charger_historique()
    ensemble_actuel = set(fichiers_sources_actuels)
    if not ensemble_actuel:
        return None
    for entree in historique:
        fichiers_anciens = set(entree.get("fichiers_sources", []))
        if fichiers_anciens and fichiers_anciens == ensemble_actuel:
            return entree
    return None


def _utilisateur_courant():
    try:
        return getpass.getuser()
    except Exception:
        return "Utilisateur inconnu"


def charger_historique():
    if not os.path.exists(CHEMIN_HISTORIQUE):
        return []
    try:
        with open(CHEMIN_HISTORIQUE, encoding="utf-8") as f:
            historique = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    historique = _migrer_entrees_vers_pays(historique)
    return _dedoublonner_rapports(historique)


def _migrer_entrees_vers_pays(historique):
    """
    Complete les entrees d'historique qui ne portent pas encore de champ
    "pays" -- soit des entrees anciennes (avant tout suivi par
    dossier/pays), soit des entrees issues d'une version intermediaire de
    DAN qui suivait les participants par Code Banque. Dans les deux cas,
    DAN ne peut pas deviner retroactivement le pays reel ; ces entrees
    sont marquees "INCONNU" plutot que de faire planter les pages qui
    attendent ce champ (Vue multi-participants).
    """
    modifie = False
    for entree in historique:
        if "pays" not in entree:
            entree["pays"] = "INCONNU"
            modifie = True
        # Nettoyage des champs de l'ancien suivi par Code Banque, devenus
        # inutiles -- on les laisse simplement de cote s'ils sont presents,
        # sans les propager plus loin dans l'application.
    if modifie:
        _sauvegarder(historique)
    return historique


def _dedoublonner_rapports(historique):
    """
    Corrige a la volee d'eventuels doublons de rapports_generes crees par
    une version anterieure de ajouter_rapport_a_analyse (avant correction
    du 2026-08-04), qui provoquaient un plantage de la page Historique
    (cle de bouton de telechargement dupliquee). Ne reecrit le fichier que
    si un doublon a reellement ete trouve, pour ne pas modifier inutilement
    des entrees deja propres.
    """
    modifie = False
    for entree in historique:
        rapports = entree.get("rapports_generes", [])
        if len(rapports) <= 1:
            continue
        vus = set()
        rapports_propres = []
        for rap in rapports:
            if rap["chemin"] in vus:
                modifie = True
                continue
            vus.add(rap["chemin"])
            rapports_propres.append(rap)
        entree["rapports_generes"] = rapports_propres
    if modifie:
        _sauvegarder(historique)
    return historique


def _sauvegarder(liste):
    os.makedirs(os.path.dirname(CHEMIN_HISTORIQUE), exist_ok=True)
    with open(CHEMIN_HISTORIQUE, "w", encoding="utf-8") as f:
        json.dump(liste, f, ensure_ascii=False, indent=2)


def enregistrer_analyse(evt_df, score_reseau_df, niveau_info):
    """
    Cree une nouvelle entree d'historique a partir d'une analyse tout juste
    realisee (apres import + calcul du score), pour UN pays (evt_df ne
    doit contenir que les evenements de ce pays -- voir logic.participants
    pour repartir un lot multi-pays avant d'appeler cette fonction une
    fois par pays).
    Renvoie l'identifiant cree, a garder dans st.session_state pour pouvoir
    y rattacher un rapport plus tard dans la meme session.
    """
    maintenant = datetime.now()
    pays = (
        evt_df["pays"].dropna().iloc[0]
        if "pays" in evt_df.columns and evt_df["pays"].notna().any()
        else "INCONNU"
    )
    entree = {
        "id": maintenant.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6],
        "date": maintenant.strftime("%Y-%m-%d"),
        "heure": maintenant.strftime("%H:%M:%S"),
        "utilisateur": _utilisateur_courant(),
        "pays": pays,
        "systemes_analyses": sorted(evt_df[evt_df["domaine"] != "INCONNU"]["domaine"].unique().tolist()),
        "fichiers_sources": sorted(evt_df["fichier_source"].unique().tolist()),
        "score_obtenu": round(float(score_reseau_df["gravite"].sum()), 1),
        "niveau_risque": niveau_info["niveau"],
        "niveau_emoji": niveau_info["emoji"],
        "nb_evenements": int(len(evt_df)),
        "nb_incidents": int(evt_df["survenance_bin"].sum()),
        "detail_reseaux": [
            {"domaine": row["domaine"], "score_100": round(float(row["score_100"]), 1)}
            for _, row in score_reseau_df.iterrows()
        ],
        "rapports_generes": [],
    }
    historique = charger_historique()
    historique.insert(0, entree)  # plus recent en premier
    _sauvegarder(historique)
    return entree["id"]


def enregistrer_lot_multi_pays(evt_df, mapping_df):
    """
    Repartit un lot d'import (potentiellement plusieurs pays) et
    enregistre UNE entree d'historique par pays detecte, en reutilisant
    le meme calcul de score que le reste de l'application
    (logic.donnees.calculer_scores). Renvoie un dict {pays: id_analyse}
    pour pouvoir, si besoin, rattacher des rapports generes a l'entree du
    bon pays ensuite.
    """
    from logic.donnees import calculer_scores
    from logic.interpretation import interpretation_absolue
    from logic.participants import grouper_par_pays

    identifiants = {}
    for pays, sous_df in grouper_par_pays(evt_df).items():
        df_gravite = calculer_scores(sous_df, mapping_df)
        score_reseau_df = df_gravite.groupby("domaine", as_index=False)["gravite"].sum()
        score_reseau_df = score_reseau_df[score_reseau_df["domaine"] != "INCONNU"]
        total = score_reseau_df["gravite"].sum()
        score_reseau_df["score_100"] = (
            (score_reseau_df["gravite"] / total * 100).round(1) if total > 0 else 0
        )
        niveau_info = interpretation_absolue(total)
        identifiants[pays] = enregistrer_analyse(sous_df, score_reseau_df, niveau_info)
    return identifiants


def ajouter_rapport_a_analyse(id_analyse, fichier_source, chemin_rapport):
    """
    Rattache un rapport genere a une entree d'historique. Si un rapport avec
    exactement le meme chemin est deja rattache a cette analyse (rapport
    regenere une seconde fois dans la meme session, ou rerun Streamlit), on
    met a jour sa date plutot que d'ajouter un doublon -- un doublon exact
    provoquait une cle de bouton de telechargement dupliquee (chemin de
    fichier identique) et faisait planter la page Historique.
    """
    if not id_analyse:
        return
    historique = charger_historique()
    for entree in historique:
        if entree["id"] == id_analyse:
            existant = next(
                (r for r in entree["rapports_generes"] if r["chemin"] == chemin_rapport), None
            )
            if existant:
                existant["date_generation"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            else:
                entree["rapports_generes"].append({
                    "fichier_source": fichier_source,
                    "chemin": chemin_rapport,
                    "date_generation": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
            break
    _sauvegarder(historique)


def supprimer_analyse(id_analyse):
    historique = charger_historique()
    historique = [e for e in historique if e["id"] != id_analyse]
    _sauvegarder(historique)


def effacer_historique():
    """
    Supprime la totalite de l'historique des analyses (remise a zero).
    N'efface PAS les rapports Word deja generes sur le disque (dossier
    outputs/rapports) -- seule la liste des entrees d'historique et leurs
    references aux rapports sont effacees. Action irreversible : la
    confirmation doit etre geree par l'appelant (page historique.py).
    """
    _sauvegarder([])


def filtrer_historique(historique, date_debut=None, date_fin=None, systemes=None, recherche=None):
    resultat = historique
    if date_debut:
        resultat = [e for e in resultat if e["date"] >= str(date_debut)]
    if date_fin:
        resultat = [e for e in resultat if e["date"] <= str(date_fin)]
    if systemes:
        resultat = [e for e in resultat if set(e["systemes_analyses"]) & set(systemes)]
    if recherche:
        r = recherche.lower()
        resultat = [
            e for e in resultat
            if r in e["utilisateur"].lower()
            or r in e["date"]
            or any(r in s.lower() for s in e["systemes_analyses"])
            or r in e["niveau_risque"].lower()
        ]
    return resultat
