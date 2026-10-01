# -*- coding: utf-8 -*-
import streamlit as st
import os
from datetime import date
from style import entete_page, BLEU_FONCE, OR
from chemins import chemin_ressource

VERSION_APP = "1.0 (prototype)"


def carte(valeur, libelle):
    st.markdown(f"""
    <div class="dan-card">
        <div class="valeur">{valeur}</div>
        <div class="libelle">{libelle}</div>
    </div>
    """, unsafe_allow_html=True)


def afficher():
    entete_page(
        "DAN",
        "Système intégré d'aide à la surveillance des systèmes de paiement",
    )

    col_logo, col_texte = st.columns([1, 3])
    with col_logo:
        chemin_logo = chemin_ressource("referentiels/logo.png")
        if os.path.exists(chemin_logo):
            st.image(chemin_logo, width=180)
    with col_texte:
        st.markdown(f"""
        <h2 style="color:{BLEU_FONCE};">Bienvenue sur DAN</h2>
        <p style="font-size:16px; color:#4A5568;">
        DAN consolide les indicateurs de surveillance des quatre systèmes de paiement
        (SYGMA, SWIFT, SYSTAC, RESEAU) en un score de risque unique par participant,
        enrichi d'une analyse qualitative automatique, et génère le rapport mensuel
        de surveillance sans intervention manuelle.
        </p>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # Cartes de synthese : reelles si des donnees ont deja ete importees
    # (mono ou multi-participants), sinon valeurs de reference du
    # perimetre du referentiel (4 systemes, 4 referentiels fonctionnels).
    # ------------------------------------------------------------------
    evt_df = st.session_state.get("evt_df")
    evt_df_complet = st.session_state.get("evt_df_complet")
    nb_reseaux = 4
    nb_referentiels = 4

    donnees_actives = evt_df_complet if evt_df_complet is not None else evt_df
    if donnees_actives is not None:
        nb_evenements = len(donnees_actives)
        nb_pays = (
            donnees_actives["pays"].nunique()
            if "pays" in donnees_actives.columns else 1
        )
    else:
        nb_evenements = 0
        nb_pays = 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        carte(nb_reseaux, "Systèmes surveillés")
    with c2:
        carte(nb_evenements, "Événements suivis")
    with c3:
        carte(nb_referentiels, "Référentiels intégrés")
    with c4:
        carte(nb_pays, "Pays analysé(s)")

    st.markdown("<br>", unsafe_allow_html=True)
    c5, c6 = st.columns(2)
    with c5:
        carte(date.today().strftime("%d/%m/%Y"), "Date de génération")
    with c6:
        carte(VERSION_APP, "Version de l'application")

    st.markdown("<br>", unsafe_allow_html=True)
    st.info(
        "👈 Utilisez le menu à gauche pour importer des reportings, consulter le "
        "tableau de bord, ou générer un rapport."
    )

    from pages_dan.widget_assistant import afficher_assistant
    afficher_assistant("Accueil")
