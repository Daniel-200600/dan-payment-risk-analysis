# -*- coding: utf-8 -*-
import streamlit as st
import json
import os
from style import entete_page
from logic.donnees import charger_mapping
from logic.rapports import (
    generer_rapport_docx, generer_rapport_general, generer_rapport_activite,
    convertir_en_pdf, afficher_pdf_inline, generer_apercu_html,
)
from logic.historique import ajouter_rapport_a_analyse
from chemins import chemin_donnees


def _charger_analyse_qualitative():
    chemin_qualitatif = chemin_donnees("data/processed/analyse_qualitative.json")
    if os.path.exists(chemin_qualitatif):
        with open(chemin_qualitatif, encoding="utf-8") as f:
            return json.load(f)
    return {}


def afficher():
    entete_page("Génération des rapports", "Synthèse générale consolidée, ou rapport d'activité")

    if "evt_df" not in st.session_state:
        st.info("Importez d'abord des fichiers dans la page « Import des reportings ».")
        from pages_dan.widget_assistant import afficher_assistant
        afficher_assistant("Génération des rapports")
        return

    mapping_df = charger_mapping()
    if mapping_df is None:
        st.error("La table de correspondance des risques est introuvable. Contactez le support technique (voir page Aide).")
        from pages_dan.widget_assistant import afficher_assistant
        afficher_assistant("Génération des rapports")
        return

    evt_df = st.session_state["evt_df"]
    # Le rapport d'activite (taux de reponse, analyse par pays) doit
    # toujours porter sur TOUS les pays du lot importe, meme si le
    # Tableau de bord a ete filtre sur un sous-ensemble entre-temps --
    # evt_df_complet (non filtre) est donc prioritaire ici specifiquement.
    evt_df_pour_activite = st.session_state.get("evt_df_complet", evt_df)
    analyse_qualitative = _charger_analyse_qualitative()

    type_rapport = st.radio(
        "Type de rapport",
        ["Rapport général consolidé", "Rapport d'activité"],
        horizontal=True,
    )

    if type_rapport == "Rapport général consolidé":
        st.caption(
            "Liste de tous les incidents survenus, classés par pays puis par mois, "
            "avec leurs caractéristiques (système, motif, statut, occurrences, durée "
            "d'indisponibilité) — rien d'autre."
        )

        pays_dispo = sorted(evt_df_pour_activite["pays"].dropna().unique()) if "pays" in evt_df_pour_activite.columns else []
        pays_choisis_rapport = pays_dispo
        if len(pays_dispo) > 1:
            pays_choisis_rapport = st.multiselect(
                "Pays à inclure dans ce rapport", pays_dispo, default=pays_dispo,
                help="Choisissez un seul pays, ou plusieurs à la fois — l'en-tête du "
                     "rapport (participant et période) s'adapte automatiquement à votre sélection.",
            )
            evt_df_rapport_general = evt_df_pour_activite[evt_df_pour_activite["pays"].isin(pays_choisis_rapport)]
        else:
            evt_df_rapport_general = evt_df

        if st.button("🔄 Générer le rapport général", type="primary", disabled=(len(pays_dispo) > 1 and not pays_choisis_rapport)):
            with st.spinner("Génération en cours..."):
                chemin_docx, erreur = generer_rapport_general(evt_df_rapport_general, mapping_df, analyse_qualitative)
            if erreur:
                st.error(f"❌ {erreur}")
            else:
                st.session_state["dernier_rapport_docx"] = chemin_docx
                st.success(f"✅ Rapport général généré : {os.path.basename(chemin_docx)}")
                st.toast("Rapport prêt", icon="📄")
                ajouter_rapport_a_analyse(
                    st.session_state.get("historique_id_courant"), "Rapport général consolidé", chemin_docx
                )

    else:
        st.caption(
            "Structure type d'un rapport d'activité mensuel : "
            "Chapitre I (présentation générale, identique à chaque génération), Chapitre II "
            "avec le taux de réponses par pays et l'analyse des reportings par pays calculés "
            "automatiquement. Les sections dépendant de l'agent (contrôle sur place, autres "
            "activités, difficultés institutionnelles) restent à compléter manuellement."
        )
        if st.button("🔄 Générer le rapport d'activité", type="primary"):
            with st.spinner("Génération en cours..."):
                chemin_docx, erreur = generer_rapport_activite(evt_df_pour_activite, mapping_df, analyse_qualitative)
            if erreur:
                st.error(f"❌ {erreur}")
            else:
                st.session_state["dernier_rapport_docx"] = chemin_docx
                st.success(f"✅ Rapport d'activité généré : {os.path.basename(chemin_docx)}")
                st.toast("Rapport prêt", icon="📄")
                ajouter_rapport_a_analyse(
                    st.session_state.get("historique_id_courant"), "Rapport d'activité", chemin_docx
                )

    if "dernier_rapport_docx" in st.session_state:
        chemin_docx = st.session_state["dernier_rapport_docx"]

        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            with open(chemin_docx, "rb") as f:
                st.download_button(
                    "💾 Enregistrer en Word (.docx)", f,
                    file_name=os.path.basename(chemin_docx),
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )

        with st.spinner("Préparation de l'aperçu..."):
            chemin_pdf = convertir_en_pdf(chemin_docx)

        if chemin_pdf:
            with col_dl2:
                with open(chemin_pdf, "rb") as f:
                    st.download_button(
                        "🖨️ Imprimer / Enregistrer en PDF", f,
                        file_name=os.path.basename(chemin_pdf), mime="application/pdf",
                    )
            st.subheader("Aperçu du rapport")
            st.caption("Ctrl+P (ou Cmd+P) dans l'aperçu ci-dessous pour imprimer directement.")
            afficher_pdf_inline(chemin_pdf)
        else:
            # Repli garanti : apercu HTML du contenu, sans dependre de
            # Word ou LibreOffice installes sur la machine. Moins fidele
            # qu'un vrai PDF (pas de page de garde ni de pagination) mais
            # toujours disponible.
            st.info(
                "ℹ️ Aperçu PDF exact indisponible sur cette machine (Word/LibreOffice "
                "non détecté) — aperçu du contenu affiché ci-dessous à la place. "
                "Le fichier Word téléchargé conserve toute la mise en forme."
            )
            st.subheader("Aperçu du contenu du rapport")
            st.markdown(generer_apercu_html(chemin_docx), unsafe_allow_html=True)

    st.caption("📄 Page de garde et pied de page institutionnel : actifs sur tous les rapports générés.")

    from pages_dan.widget_assistant import afficher_assistant
    afficher_assistant("Génération des rapports", evt_df=st.session_state.get("evt_df"))
