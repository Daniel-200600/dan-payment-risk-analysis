# -*- coding: utf-8 -*-
"""
DAN - Interpretation automatique en langage clair.

Objectif : ne jamais laisser un chiffre ou un code seul a l'ecran sans une
phrase qui explique ce qu'il signifie concretement pour un lecteur non
technique (direction, comité de pilotage).
"""

LIBELLE_RISQUE = {
    "RC": "risque de crédit",
    "RL": "risque de liquidité",
    "RJ": "risque juridique",
    "RO": "risque opérationnel",
    "RO(PROVISOIRE)": "risque opérationnel (à valider)",
    "RA": "risque d'activité",
    "RCI": "risque de conservation et d'investissement",
    "RS": "risque systémique",
}

DESCRIPTION_RISQUE = {
    "RC": "la capacité d'une contrepartie à honorer ses engagements financiers",
    "RL": "la disponibilité de liquidités suffisantes pour faire face aux paiements",
    "RJ": "le respect des textes réglementaires et contractuels applicables",
    "RO": "le bon fonctionnement des processus, systèmes et procédures internes",
    "RA": "la continuité et la qualité du service rendu aux participants",
    "RCI": "la sécurité des fonds et instruments financiers conservés",
    "RS": "la capacité d'un incident local à se propager à l'ensemble du système de paiement",
}


def libelle_risque(code):
    """'RO' -> 'risque opérationnel'"""
    code = str(code).strip().upper()
    return LIBELLE_RISQUE.get(code, code)


def description_risque(code):
    code = str(code).strip().upper()
    return DESCRIPTION_RISQUE.get(code, "")


ECHELLE_SCORE = [
    {
        "seuil_min": 80, "niveau": "Critique", "emoji": "⚫", "couleur": "#3B0A0A",
        "signification": (
            "Dysfonctionnements majeurs et récurrents détectés, menaçant la "
            "continuité du service de paiement."
        ),
        "impact": "Risque élevé d'incident systémique affectant le système et ses participants.",
        "action": "Intervention immédiate requise, escalade à la direction de la surveillance.",
    },
    {
        "seuil_min": 60, "niveau": "Élevé", "emoji": "🔴", "couleur": "#C53030",
        "signification": "Anomalies significatives et récurrentes nécessitant une investigation.",
        "impact": "Probabilité importante qu'un incident affecte le service dans les jours à venir.",
        "action": "Investigation immédiate et mise en place d'un plan d'action prioritaire.",
    },
    {
        "seuil_min": 40, "niveau": "Moyen", "emoji": "🟠", "couleur": "#C05621",
        "signification": "Présence de quelques anomalies nécessitant une surveillance renforcée.",
        "impact": "Des incidents pourraient apparaître si la situation n'est pas surveillée.",
        "action": "Renforcer la surveillance et analyser les causes des anomalies relevées.",
    },
    {
        "seuil_min": 20, "niveau": "Faible", "emoji": "🟡", "couleur": "#B7950B",
        "signification": "Quelques écarts mineurs, sans caractère préoccupant à ce stade.",
        "impact": "Faible probabilité d'incident à court terme.",
        "action": "Surveillance de routine, aucune action corrective urgente.",
    },
    {
        "seuil_min": 0, "niveau": "Très faible", "emoji": "🟢", "couleur": "#2F855A",
        "signification": "Le système fonctionne normalement. Aucune anomalie majeure détectée.",
        "impact": "Faible probabilité d'incident.",
        "action": "Simple surveillance de routine.",
    },
]


# Seuils de gravite ABSOLUE par defaut (Critique / Eleve / Moyen / Faible
# -> sinon Tres faible). Calibres empiriquement de sorte qu'un evenement
# isole de faible gravite (~1 a 4) ne ressorte pas en Critique, contrairement
# a l'ancienne echelle relative (score_100). DESORMAIS MODIFIABLES PAR
# L'AGENT depuis Parametres, selon ses propres besoins d'analyse -- cette
# constante ne sert plus que de valeur de depart / repli si la
# configuration est absente ou invalide.
SEUILS_GRAVITE_ABSOLUE = [25, 10, 3, 0.5]  # Critique / Eleve / Moyen / Faible -> sinon Tres faible


def interpretation_absolue(gravite_brute, seuils=None):
    """
    Renvoie niveau/emoji/couleur/signification/impact/action, calcules
    sur la gravite BRUTE (somme ponderee reelle, sans normalisation a 100).
    C'est cette fonction qu'il faut utiliser pour classer un niveau de risque
    (badges, rapports, assistant) -- score_100 (part relative) reste reserve
    aux graphiques de repartition (camembert, comparaison entre reseaux).

    Les seuils utilises sont ceux configures par l'agent (voir Parametres
    -> logic.configuration), avec repli sur SEUILS_GRAVITE_ABSOLUE si aucune
    configuration valide n'est trouvee. Un appelant peut aussi imposer des
    seuils explicites via le parametre seuils (utile pour les tests, ou
    pour simuler un autre parametrage sans toucher a la configuration
    persistee).
    """
    if seuils is None:
        from logic.configuration import charger_configuration, valider_seuils_gravite
        config = charger_configuration()
        seuils_config = config.get("seuils_gravite", SEUILS_GRAVITE_ABSOLUE)
        est_valide, _ = valider_seuils_gravite(seuils_config)
        seuils = seuils_config if est_valide else SEUILS_GRAVITE_ABSOLUE

    gravite_brute = max(0, gravite_brute or 0)
    if gravite_brute >= seuils[0]:
        palier = ECHELLE_SCORE[0]
    elif gravite_brute >= seuils[1]:
        palier = ECHELLE_SCORE[1]
    elif gravite_brute >= seuils[2]:
        palier = ECHELLE_SCORE[2]
    elif gravite_brute >= seuils[3]:
        palier = ECHELLE_SCORE[3]
    else:
        palier = ECHELLE_SCORE[4]
    return {**palier, "score": round(gravite_brute, 1)}


def interpreter_score_global(score_reseau_df, nb_incidents, nb_evenements):
    """
    Construit un paragraphe d'interpretation du score global, a partir du
    tableau des scores par reseau (colonnes: domaine, gravite, score_100).
    """
    total = score_reseau_df["score_100"].sum()
    if total == 0 or nb_incidents == 0:
        return (
            "Aucun incident significatif n'a été relevé ce mois-ci sur l'ensemble "
            "des systèmes surveillés. La situation est jugée normale : aucune action "
            "particulière n'est requise."
        )

    top = score_reseau_df.sort_values("score_100", ascending=False).iloc[0]
    niveau = interpretation_absolue(top["gravite"])["niveau"]
    part_incidents = round(100 * nb_incidents / nb_evenements, 1) if nb_evenements else 0

    phrase = (
        f"Sur les {nb_evenements} événements suivis ce mois-ci, {nb_incidents} "
        f"sont effectivement survenus ({part_incidents} %). "
        f"Le système **{top['domaine']}** concentre la majorité du risque relevé "
        f"({top['score_100']:.0f} % du score total), ce qui correspond à un "
        f"niveau de risque **{niveau.lower()}** sur ce système. "
    )

    autres = score_reseau_df[score_reseau_df["domaine"] != top["domaine"]]
    autres_actifs = autres[autres["score_100"] > 0]
    if len(autres_actifs) == 0:
        phrase += "Les autres systèmes n'ont signalé aucun incident significatif ce mois-ci."
    else:
        noms = ", ".join(autres_actifs["domaine"].tolist())
        phrase += f"Une attention secondaire peut être portée sur : {noms}."

    return phrase


def interpreter_reseau(domaine, gravite, evenements_survenus_df):
    """
    Interpretation textuelle pour le detail d'un reseau specifique. Prend la
    gravite BRUTE du reseau (pas sa part relative score_100), pour rester
    coherent avec le badge affiche juste au-dessus (voir interpretation_absolue).
    """
    niveau = interpretation_absolue(gravite)["niveau"]

    if len(evenements_survenus_df) == 0:
        return (
            f"Aucun événement n'est survenu sur le système {domaine} ce mois-ci. "
            f"Niveau de risque : **{niveau.lower()}**, situation stable."
        )

    top_evt = evenements_survenus_df.sort_values(
        "occurrence_num", ascending=False, na_position="last"
    ).iloc[0]
    occ = top_evt.get("occurrence_num")
    occ_txt = f" (observé {int(occ)} fois)" if pd_notna(occ) else ""

    return (
        f"{len(evenements_survenus_df)} événement(s) suivi(s) sur {domaine} sont "
        f"survenus ce mois-ci. L'événement le plus significatif est "
        f"**{top_evt['reference']}** ({top_evt['evenement']}){occ_txt}. "
        f"Niveau de risque du système : **{niveau.lower()}**."
    )


def pd_notna(val):
    import pandas as pd
    return pd.notna(val)


def interpreter_categorie(code_risque, gravite):
    """Explique ce qu'implique une categorie de risque particuliere en tension."""
    nom = libelle_risque(code_risque)
    description = description_risque(code_risque)
    return (
        f"**{nom.capitalize()}** ({code_risque}) : {description}. "
        f"Score de gravité cumulé sur cette catégorie : {gravite:.1f}."
    )
