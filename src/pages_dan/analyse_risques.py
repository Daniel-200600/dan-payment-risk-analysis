# -*- coding: utf-8 -*-
import streamlit as st
import json
import os
import pandas as pd
from style import entete_page
from chemins import chemin_donnees
from logic.donnees import charger_mapping
from logic.analyse_intelligente import generer_analyse


def afficher():
    entete_page("Analyse des incidents", "Synthèse automatique : incidents survenus et causes probables")

    if "evt_df" not in st.session_state:
        st.info("Importez d'abord des fichiers dans la page « Import des reportings ».")
        from pages_dan.widget_assistant import afficher_assistant
        afficher_assistant("Analyse des incidents")
        return

    mapping_df = charger_mapping()
    if mapping_df is None:
        st.error("La table de correspondance des risques est introuvable. Contactez le support technique (voir page Aide).")
        from pages_dan.widget_assistant import afficher_assistant
        afficher_assistant("Analyse des incidents")
        return

    evt_df = st.session_state["evt_df"]

    chemin_qualitatif = chemin_donnees("data/processed/analyse_qualitative.json")
    analyse_qualitative = {}
    if os.path.exists(chemin_qualitatif):
        with open(chemin_qualitatif, encoding="utf-8") as f:
            analyse_qualitative = json.load(f)

    # generer_analyse() calcule aussi risques_dominants/recommandations en
    # interne (utilises ailleurs, ex. le Tableau de bord) -- cette page,
    # dediee au controle sur pieces, ne les affiche volontairement plus :
    # on y analyse les incidents survenus, pas leur classement en
    # categories de risque.
    analyse = generer_analyse(evt_df, mapping_df, analyse_qualitative)

    if analyse["source"] == "llm":
        st.success("✅ Analyse enrichie par une lecture automatique des commentaires.")
    else:
        st.info(
            "ℹ️ Analyse basée sur des comptages et tris simples. Une analyse plus fine "
            "du langage des commentaires est disponible en option — contactez le "
            "support technique (voir page Aide) pour l'activer."
        )

    st.markdown("### 📋 Résumé des incidents")
    st.markdown(analyse["resume"])

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### ⚠️ Incidents survenus et causes probables")
    st.caption(
        "Un incident survenu par ligne — tous les incidents marqués « Oui » dans "
        "les fichiers importés figurent ici, sans exception ni sélection."
    )
    survenus_affiches = evt_df[evt_df["survenance_bin"] == 1].copy()
    if len(survenus_affiches):
        survenus_affiches["Incident survenu"] = (
            "[" + survenus_affiches["domaine"] + "] " + survenus_affiches["reference"]
            + " — " + survenus_affiches["evenement"].astype(str)
        )
        survenus_affiches["Cause probable"] = (
            survenus_affiches["motif"].apply(
                lambda m: str(m).strip() if pd.notna(m) and str(m).strip().lower() != "nan"
                else "Non renseignée par l'assujetti"
            )
        )
        survenus_affiches["Statut"] = (
            survenus_affiches["statut"].apply(
                lambda s: str(s).strip() if pd.notna(s) and str(s).strip().lower() != "nan"
                else "Non renseigné"
            )
        )
        survenus_affiches["Durée d'indisponibilité"] = (
            survenus_affiches["duree_indispo_min"].apply(
                lambda d: f"{int(d)} min" if pd.notna(d) else "Non renseignée"
            )
        )
        survenus_affiches["Pays"] = (
            survenus_affiches["pays"] if "pays" in survenus_affiches.columns
            else "INCONNU"
        )
        survenus_affiches["Mois"] = (
            survenus_affiches["mois"].apply(
                lambda m: str(m).strip() if pd.notna(m) else "Non renseigné"
            ) if "mois" in survenus_affiches.columns
            else "Non renseigné"
        )
        colonnes_affichees = [
            "Pays", "Mois", "Incident survenu", "Cause probable", "Statut", "Durée d'indisponibilité",
        ]
        st.dataframe(
            survenus_affiches[colonnes_affichees],
            use_container_width=True, hide_index=True,
            column_config={
                "Pays": st.column_config.TextColumn(width="small"),
                "Mois": st.column_config.TextColumn(width="small"),
                "Incident survenu": st.column_config.TextColumn(width="large"),
                "Cause probable": st.column_config.TextColumn(width="large"),
                "Statut": st.column_config.TextColumn(width="small"),
                "Durée d'indisponibilité": st.column_config.TextColumn(width="small"),
            },
        )
        st.caption(f"{len(survenus_affiches)} incident(s) survenu(s) au total ce mois-ci.")
    else:
        st.info("Aucun incident survenu ce mois-ci sur les systèmes importés.")

    from pages_dan.widget_assistant import afficher_assistant
    afficher_assistant(
        "Analyse des incidents", evt_df=evt_df,
        facteurs=[p["texte"] for p in analyse["principaux_problemes"][:3]],
    )
