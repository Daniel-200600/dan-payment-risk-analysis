# -*- coding: utf-8 -*-
"""
DAN - Assistant IA contextuel (Phase 10).

Meme principe que l'Etape 5 (analyse qualitative) : modele execute
localement via Ollama, aucune donnee ne sort de l'ordinateur, pas de cout.
L'assistant recoit a chaque question un resume de la page consultee et de
l'etat courant de l'analyse, pour repondre en connaissance de cause sans
avoir acces a l'integralite des donnees (inutile et trop volumineux).
"""
from .configuration import charger_configuration

DESCRIPTION_PAGES = {
    "Accueil": "L'utilisateur consulte la page d'accueil de DAN, qui présente l'outil.",
    "Import des reportings": "L'utilisateur importe des fichiers Excel de reporting mensuel.",
    "Tableau de bord": "L'utilisateur consulte le score de risque consolidé, la jauge et les graphiques.",
    "Analyse des incidents": "L'utilisateur consulte la synthèse automatique des incidents survenus et de leurs causes probables.",
    "Glossaire des événements": "L'utilisateur recherche la signification d'un code événement ou référentiel.",
    "Génération des rapports": "L'utilisateur génère un rapport Word détaillé ou consolidé.",
    "Historique des analyses": "L'utilisateur consulte les analyses passées et leurs rapports.",
    "Paramètres": "L'utilisateur configure DAN (logos, thème, institution, options IA).",
    "Aide": "L'utilisateur consulte la documentation d'utilisation de DAN.",
}

INSTRUCTIONS_SYSTEME = """Tu es l'assistant intégré de DAN, un outil de surveillance des systèmes de
paiement, utilisé par une cellule de surveillance.
Tu aides l'utilisateur à comprendre les résultats affichés (scores, graphiques, événements,
recommandations), à interpréter les indicateurs, et à utiliser l'application.
Réponds toujours en français, de façon concise (quelques phrases, pas un essai), factuelle,
et uniquement à partir du contexte fourni ci-dessous -- si une information manque, dis-le
clairement plutôt que d'inventer un chiffre ou un fait."""


def construire_contexte_page(nom_page, evt_df=None, score_reseau=None, niveau_info=None):
    """Resume court de ce que l'utilisateur voit actuellement, pour ancrer les reponses."""
    lignes = [f"Page actuelle : {nom_page}.", DESCRIPTION_PAGES.get(nom_page, "")]

    if evt_df is not None and len(evt_df):
        nb_evenements = len(evt_df)
        nb_incidents = int(evt_df["survenance_bin"].sum())
        lignes.append(f"Données importées : {nb_evenements} événements suivis, {nb_incidents} survenus ce mois-ci.")

    if score_reseau is not None and len(score_reseau):
        top = score_reseau.sort_values("score_100", ascending=False).iloc[0]
        lignes.append(
            f"Système le plus critique : {top['domaine']} (score relatif {top['score_100']} %)."
        )

    if niveau_info:
        lignes.append(
            f"Niveau de risque global : {niveau_info['niveau']} "
            f"({niveau_info['signification']})"
        )

    return "\n".join(l for l in lignes if l)


def _appeler_ollama(prompt_utilisateur, contexte_page, historique_conversation):
    import ollama
    config = charger_configuration()
    modele = config.get("ia_modele_ollama", "mistral")

    messages = [{"role": "system", "content": f"{INSTRUCTIONS_SYSTEME}\n\nContexte actuel :\n{contexte_page}"}]
    for tour in historique_conversation[-6:]:  # 6 derniers messages max, pour rester rapide
        messages.append(tour)
    messages.append({"role": "user", "content": prompt_utilisateur})

    reponse = ollama.chat(model=modele, messages=messages, options={"temperature": 0.3})
    return reponse["message"]["content"].strip()


def repondre_question(question, contexte_page, historique_conversation):
    """
    Renvoie (reponse, erreur). En cas de probleme (Ollama non lance, modele
    absent...), erreur contient un message clair a afficher, reponse est None.
    """
    try:
        return _appeler_ollama(question, contexte_page, historique_conversation), None
    except ImportError:
        return None, "La librairie 'ollama' n'est pas installée (pip install ollama)."
    except Exception as e:
        message = str(e)
        if "memory" in message.lower():
            return None, (
                "Mémoire insuffisante pour ce modèle. Essayez un modèle plus léger "
                "(ex. gemma3:1b) dans Paramètres > IA."
            )
        return None, (
            "Impossible de contacter Ollama. Vérifiez qu'il est bien lancé "
            f"(détail technique : {message})."
        )


def suggestion_proactive(niveau_info):
    """Message d'alerte affiche automatiquement si le risque est eleve/critique."""
    if not niveau_info:
        return None
    if niveau_info["niveau"] in ("Critique", "Élevé"):
        return (
            f"{niveau_info['emoji']} Le niveau de risque actuel est **{niveau_info['niveau']}**. "
            "Voulez-vous que je vous aide à comprendre les causes, ou à préparer un plan d'action ?"
        )
    return None


def synthese_decisionnelle(reseau_principal, score_100, niveau_info, facteurs):
    """« Avis de DAN » : synthese decisionnelle formatee, sans appel au modele
    (regle simple) -- reste disponible meme si Ollama est indisponible."""
    if not reseau_principal:
        return "Aucune donnée suffisante pour formuler un avis pour l'instant."

    texte = (
        f"**Avis de DAN**\n\n"
        f"Le score de risque de {reseau_principal} est de {score_100:.0f}/100, "
        f"ce qui correspond à un niveau **{niveau_info['niveau']}**.\n\n"
    )
    if facteurs:
        texte += "Les principaux facteurs sont :\n" + "\n".join(f"- {f}" for f in facteurs) + "\n\n"
    texte += f"**Recommandation** : {niveau_info['action']}"
    return texte
