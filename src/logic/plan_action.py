# -*- coding: utf-8 -*-
"""
DAN - Plan d'action : propositions automatiques d'actions correctives a
partir des risques dominants detectes par l'analyse intelligente.

Les propositions sont volontairement generiques (regles simples), pensees
pour etre relues et ajustees par un analyste avant integration au rapport
-- pas une decision automatisee definitive.
"""

SERVICE_PAR_RISQUE = {
    "RO": "Exploitation / Support technique",
    "RJ": "Conformité / Juridique",
    "RL": "Trésorerie",
    "RC": "Risques / Crédit",
    "RA": "Relation participants",
    "RCI": "Sécurité des systèmes",
    "RS": "Direction de la surveillance",
}

ACTION_PAR_RISQUE = {
    "RO": "Auditer le processus opérationnel concerné et corriger la cause technique identifiée.",
    "RJ": "Vérifier la conformité réglementaire et documenter les écarts constatés.",
    "RL": "Analyser la position de trésorerie et anticiper les besoins de couverture.",
    "RC": "Évaluer la solvabilité de la contrepartie concernée.",
    "RA": "Renforcer le suivi du participant concerné et formaliser un plan de continuité.",
    "RCI": "Vérifier les dispositifs de sécurité et de sauvegarde des fonds/instruments.",
    "RS": "Évaluer le risque de propagation et alerter les systèmes interconnectés.",
}

DELAI_PAR_PRIORITE = {
    "Critique": "Sous 48h", "Élevé": "Sous 1 semaine",
    "Moyen": "Sous 1 mois", "Faible": "Prochaine revue", "Très faible": "Prochaine revue",
}

PRIORITES_VALIDES = ["Critique", "Élevé", "Moyen", "Faible"]
STATUTS_VALIDES = ["À faire", "En cours", "Résolu"]


def _priorite_depuis_occurrences(occurrences):
    """
    Seuils ABSOLUS (pas une part relative parmi les risques detectes) --
    evite qu'un risque isole avec une seule occurrence ressorte en priorite
    Critique simplement parce que c'est le seul detecte ce mois-ci.
    """
    if occurrences >= 10:
        return "Critique"
    elif occurrences >= 5:
        return "Élevé"
    elif occurrences >= 2:
        return "Moyen"
    return "Faible"


def generer_plan_action(risques_dominants):
    """
    Une ligne de proposition par risque dominant (jusqu'a 6), avec une
    priorite deduite du nombre absolu d'occurrences de ce risque -- pas de
    sa part relative parmi les autres risques detectes (voir
    _priorite_depuis_occurrences).
    """
    if not risques_dominants:
        return []

    lignes = []
    for risque in risques_dominants[:6]:
        code = risque["code"]
        priorite = _priorite_depuis_occurrences(risque["occurrences"])
        lignes.append({
            "Risque": f"{risque['libelle'].capitalize()} ({code})",
            "Action corrective": ACTION_PAR_RISQUE.get(
                code, "Analyser la cause racine et documenter les mesures correctives."
            ),
            "Priorité": priorite,
            "Service responsable": SERVICE_PAR_RISQUE.get(code, "Cellule de surveillance"),
            "Délai recommandé": DELAI_PAR_PRIORITE.get(priorite, "À définir"),
            "Statut": "À faire",
            "Impact attendu": f"Réduction du risque {risque['libelle']} et de sa récurrence.",
        })
    return lignes
