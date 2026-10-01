# -*- coding: utf-8 -*-
"""
DAN - Analyse intelligente : synthese des incidents, causes probables,
risques dominants et recommandations.

Fonctionne en deux modes :
- Si data/processed/analyse_qualitative.json existe (sortie de l'Etape 5,
  analyse LLM locale via Ollama) : utilise les syntheses reelles du modele.
- Sinon : repli automatique sur une synthese construite par des regles
  simples (comptages, tris), pour que la page reste utile meme sans LLM.
"""
import pandas as pd
from logic.interpretation import libelle_risque, description_risque


def generer_analyse(evt_df, mapping_df, analyse_qualitative):
    df = evt_df.merge(mapping_df[["reference", "risque", "niveau", "confiance"]],
                       on="reference", how="left")
    survenus = df[df["survenance_bin"] == 1]

    resume = _resume_incidents(evt_df, survenus)
    principaux_problemes = _principaux_problemes(survenus, analyse_qualitative)
    causes_probables = _causes_probables(survenus)
    risques_dominants = _risques_dominants(survenus)
    recommandations = _recommandations(survenus, risques_dominants)

    # "llm" seulement si au moins un probleme affiche vient reellement de
    # l'analyse qualitative (et pas juste parce que le fichier existe --
    # il peut exister mais ne rien contenir de pertinent pour l'import en cours)
    source_reelle = "llm" if any(p.get("source") == "llm" for p in principaux_problemes) else "regles"

    return {
        "resume": resume,
        "principaux_problemes": principaux_problemes,
        "causes_probables": causes_probables,
        "risques_dominants": risques_dominants,
        "recommandations": recommandations,
        "source": source_reelle,
    }


def _resume_incidents(evt_df, survenus):
    nb_total = len(evt_df)
    nb_survenus = len(survenus)
    if nb_survenus == 0:
        return (
            f"Sur les {nb_total} événements suivis ce mois-ci, aucun n'est survenu. "
            "La situation est calme sur l'ensemble des systèmes surveillés."
        )
    reseaux_touches = survenus["domaine"].value_counts()
    reseau_principal = reseaux_touches.index[0]
    return (
        f"Sur les {nb_total} événements suivis ce mois-ci, {nb_survenus} sont "
        f"survenus, touchant {survenus['domaine'].nunique()} système(s). Le système "
        f"**{reseau_principal}** concentre le plus grand nombre d'incidents "
        f"({reseaux_touches.iloc[0]})."
    )


def _principaux_problemes(survenus, analyse_qualitative):
    problemes = []
    # Priorite a l'analyse LLM, MAIS uniquement pour les evenements reellement
    # survenus dans les donnees ACTUELLEMENT chargees -- analyse_qualitative.json
    # est un fichier global, pas regenere a chaque import : sans ce filtre, un
    # ancien import (ex. le jeu de test complet) continuerait a s'afficher meme
    # apres avoir charge un seul fichier different.
    references_actuelles = set(survenus["reference"]) if len(survenus) else set()
    for domaine, contenu in (analyse_qualitative or {}).items():
        for evt in contenu.get("evenements_analyses", []):
            if evt.get("reference") not in references_actuelles:
                continue
            problemes.append({
                "domaine": domaine,
                "reference": evt.get("reference"),
                "texte": evt.get("probleme_identifie"),
                "source": "llm",
            })
    if problemes:
        return problemes

    # Repli : les evenements avec le plus d'occurrences ou un commentaire renseigne
    if len(survenus) == 0:
        return []
    # Tous les evenements survenus doivent figurer, pas seulement les plus
    # significatifs -- classes par pertinence (commentaire renseigne puis
    # recurrence) mais sans plafond, afin qu'aucun probleme lu dans les
    # fichiers ne soit omis de la liste.
    candidats = survenus.copy()
    candidats["a_commentaire"] = candidats["commentaire"].notna()
    candidats = candidats.sort_values(
        ["a_commentaire", "occurrence_num"], ascending=[False, False]
    )
    for _, e in candidats.iterrows():
        texte = e["evenement"]
        if pd.notna(e.get("commentaire")):
            texte += f" — {str(e['commentaire'])[:160]}"
        problemes.append({
            "domaine": e["domaine"], "reference": e["reference"],
            "texte": texte, "source": "regles",
        })
    return problemes


def _causes_probables(survenus):
    if len(survenus) == 0:
        return ["Aucune cause à analyser : aucun incident ce mois-ci."]
    causes = []
    # NaN = vide : un motif non renseigne n'est pas une cause a afficher.
    # Toutes les causes reellement renseignees doivent figurer, pas
    # seulement les 5 premieres.
    motifs = survenus["motif"].dropna()
    for motif in motifs.unique():
        texte = str(motif).strip()
        if texte and texte.lower() != "nan":
            causes.append(texte[:200])
    if not causes:
        causes.append(
            "Aucun motif détaillé renseigné dans les reportings pour les "
            "événements survenus — la cause exacte reste à documenter par l'équipe de surveillance."
        )
    return causes


def _risques_dominants(survenus):
    if len(survenus) == 0 or "risque" not in survenus.columns:
        return []
    eclate = []
    for _, row in survenus.iterrows():
        risque_brut = row.get("risque")
        # Un risque non renseigne (NaN = vide, pas un evenement HORS-REF sans
        # correspondance dans le referentiel) n'est pas une categorie de
        # risque en soi -- on retombe sur RO (risque operationnel), le meme
        # repli que celui utilise pour le calcul du score (calculer_scores),
        # plutot que d'afficher litteralement "nan" comme categorie.
        if pd.isna(risque_brut):
            eclate.append("RO")
            continue
        codes = [r for r in str(risque_brut).replace(" ", "").split("+") if r]
        eclate.extend(codes or ["RO"])
    if not eclate:
        return []
    compte = pd.Series(eclate).value_counts()
    return [
        {"code": code, "libelle": libelle_risque(code),
         "description": description_risque(code), "occurrences": int(n)}
        for code, n in compte.items()
    ]


def _recommandations(survenus, risques_dominants):
    if len(survenus) == 0:
        return ["Aucune action requise ce mois-ci : aucun incident significatif."]

    recos = []
    top_reseau = survenus["domaine"].value_counts().index[0]
    recos.append(
        f"Prioriser la revue du système {top_reseau}, principal contributeur "
        f"aux incidents ce mois-ci."
    )
    if risques_dominants:
        top_risque = risques_dominants[0]
        recos.append(
            f"Porter une attention particulière au {top_risque['libelle']} "
            f"({top_risque['code']}), catégorie la plus fréquemment concernée."
        )
    faible_confiance = survenus[survenus.get("confiance") == "Faible"] if "confiance" in survenus else pd.DataFrame()
    if len(faible_confiance) > 0:
        recos.append(
            f"{len(faible_confiance)} événement(s) survenu(s) reposent sur une "
            f"correspondance de risque « Faible confiance » — à faire valider "
            f"en priorité avec l'équipe de surveillance avant toute décision basée sur le score."
        )
    return recos
