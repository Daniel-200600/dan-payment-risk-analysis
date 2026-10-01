# -*- coding: utf-8 -*-
"""
DAN - Widget assistant IA, a appeler en bas de chaque page via :
    from widget_assistant import afficher_assistant
    afficher_assistant("Nom de la page", evt_df=..., score_reseau=..., niveau_info=...)

Panneau repliable (pas un vrai bouton flottant -- limite native de
Streamlit, voir echange de cadrage), avec historique de conversation
conserve pendant la session.
"""
import streamlit as st
from logic.assistant import (
    construire_contexte_page, repondre_question, suggestion_proactive, synthese_decisionnelle,
)


def afficher_assistant(nom_page, evt_df=None, score_reseau=None, niveau_info=None,
                        reseau_principal=None, facteurs=None):
    if "assistant_historique" not in st.session_state:
        st.session_state["assistant_historique"] = []

    contexte_page = construire_contexte_page(nom_page, evt_df, score_reseau, niveau_info)

    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("🤖 Assistant DAN — poser une question sur cette page", expanded=False):
        suggestion = suggestion_proactive(niveau_info)
        if suggestion:
            st.info(suggestion)

        if score_reseau is not None and len(score_reseau) and niveau_info:
            if st.button("💡 Obtenir l'avis de DAN", key=f"avis_{nom_page}"):
                avis = synthese_decisionnelle(
                    reseau_principal, score_reseau["score_100"].max(), niveau_info, facteurs or []
                )
                st.session_state["assistant_historique"].append({"role": "assistant", "content": avis})

        for tour in st.session_state["assistant_historique"][-10:]:
            with st.chat_message(tour["role"]):
                st.write(tour["content"])

        question = st.chat_input("Posez votre question…", key=f"question_{nom_page}")
        if question:
            st.session_state["assistant_historique"].append({"role": "user", "content": question})
            with st.chat_message("user"):
                st.write(question)
            with st.chat_message("assistant"):
                with st.spinner("Réflexion en cours (jusqu'à une minute selon votre machine)…"):
                    reponse, erreur = repondre_question(
                        question, contexte_page, st.session_state["assistant_historique"]
                    )
                if erreur:
                    st.error(f"⚠️ {erreur}")
                else:
                    st.write(reponse)
                    st.session_state["assistant_historique"].append({"role": "assistant", "content": reponse})

        if st.session_state["assistant_historique"]:
            if st.button("🗑️ Effacer la conversation", key=f"effacer_{nom_page}"):
                st.session_state["assistant_historique"] = []
                st.rerun()
