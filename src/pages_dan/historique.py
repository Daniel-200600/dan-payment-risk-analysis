# -*- coding: utf-8 -*-
import streamlit as st
import os
from style import entete_page, badge_niveau
from logic.historique import charger_historique, filtrer_historique, supprimer_analyse, effacer_historique


def afficher():
    entete_page("Historique des analyses", "Consultez, filtrez et gérez toutes les analyses réalisées")

    historique = charger_historique()
    if not historique:
        st.info(
            "Aucune analyse enregistrée pour l'instant. Importez des fichiers dans la page "
            "« Import des reportings » pour créer votre première entrée d'historique."
        )
        from pages_dan.widget_assistant import afficher_assistant
        afficher_assistant("Historique des analyses")
        return

    # ------------------------------------------------------------------
    # Effacement complet de l'historique (action irreversible -> confirmation
    # explicite requise avant d'activer le bouton)
    # ------------------------------------------------------------------
    with st.expander(f"🗑️ Effacer tout l'historique ({len(historique)} analyse(s))"):
        st.warning(
            "⚠️ Cette action supprime **définitivement** les " + str(len(historique)) +
            " analyse(s) enregistrée(s) et ne peut pas être annulée. Les rapports Word déjà "
            "téléchargés sur votre ordinateur ne sont pas affectés ; seuls les liens vers eux "
            "dans l'historique disparaissent."
        )
        confirmer = st.checkbox(
            f"Je confirme vouloir supprimer définitivement les {len(historique)} analyse(s) de l'historique.",
            key="confirmer_effacement_historique",
        )
        if st.button("Effacer définitivement tout l'historique", disabled=not confirmer, type="primary"):
            effacer_historique()
            st.toast("Historique entièrement effacé", icon="🗑️")
            st.rerun()

    # ------------------------------------------------------------------
    # Filtres
    # ------------------------------------------------------------------
    with st.expander("🔎 Filtres", expanded=False):
        col1, col2, col3 = st.columns(3)
        date_debut = col1.date_input("Depuis le", value=None, format="YYYY-MM-DD")
        date_fin = col2.date_input("Jusqu'au", value=None, format="YYYY-MM-DD")
        tous_systemes = sorted({s for e in historique for s in e["systemes_analyses"]})
        systemes_choisis = col3.multiselect("Système", tous_systemes, default=tous_systemes)

    recherche = st.text_input("🔍 Recherche rapide (utilisateur, date, système, niveau)", "")

    resultat = filtrer_historique(
        historique,
        date_debut=date_debut if date_debut else None,
        date_fin=date_fin if date_fin else None,
        systemes=systemes_choisis if systemes_choisis != tous_systemes else None,
        recherche=recherche,
    )

    st.caption(f"{len(resultat)} analyse(s) trouvée(s) sur {len(historique)} au total.")

    if not resultat:
        st.warning("Aucune analyse ne correspond à ces critères.")
        from pages_dan.widget_assistant import afficher_assistant
        afficher_assistant("Historique des analyses")
        return

    # ------------------------------------------------------------------
    # Liste des analyses (une carte par entree)
    # ------------------------------------------------------------------
    for entree in resultat:
        titre = (
            f"{entree['date']} à {entree['heure']} — {entree['utilisateur']} — "
            f"{entree['niveau_emoji']} {entree['niveau_risque']} "
            f"(score {entree['score_obtenu']})"
        )
        with st.expander(titre):
            col_info, col_actions = st.columns([3, 1])

            with col_info:
                st.markdown(f"**Systèmes analysés :** {', '.join(entree['systemes_analyses']) or '—'}")
                st.markdown(
                    f"**Événements suivis :** {entree['nb_evenements']} "
                    f"({entree['nb_incidents']} survenu(s))"
                )
                st.markdown(f"**Niveau de risque :** {badge_niveau(entree['niveau_risque'])}", unsafe_allow_html=True)

                if entree["detail_reseaux"]:
                    st.markdown("**Détail par système :**")
                    for d in entree["detail_reseaux"]:
                        st.markdown(f"- {d['domaine']} : {d['score_100']} / 100")

                if entree["rapports_generes"]:
                    st.markdown("**Rapports générés lors de cette analyse :**")
                    for idx_rap, rap in enumerate(entree["rapports_generes"]):
                        if os.path.exists(rap["chemin"]):
                            with open(rap["chemin"], "rb") as f:
                                st.download_button(
                                    f"💾 {os.path.basename(rap['chemin'])}",
                                    f, file_name=os.path.basename(rap["chemin"]),
                                    key=f"dl_{entree['id']}_{idx_rap}_{rap['chemin']}",
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                )
                        else:
                            st.caption(f"⚠️ Fichier introuvable : {os.path.basename(rap['chemin'])} (déplacé ou supprimé)")
                else:
                    st.caption("Aucun rapport généré lors de cette analyse.")

            with col_actions:
                if st.button("🗑️ Supprimer", key=f"suppr_{entree['id']}"):
                    supprimer_analyse(entree["id"])
                    st.toast("Analyse supprimée", icon="🗑️")
                    st.rerun()

    from pages_dan.widget_assistant import afficher_assistant
    afficher_assistant("Historique des analyses")
