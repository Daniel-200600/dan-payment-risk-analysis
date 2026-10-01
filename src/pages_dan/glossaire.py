# -*- coding: utf-8 -*-
import streamlit as st
from style import entete_page
from logic.donnees import charger_mapping

TAILLE_PAGE = 15


def afficher():
    entete_page("Glossaire des événements", "Recherchez et filtrez la table de correspondance des événements")

    mapping_df = charger_mapping()
    if mapping_df is None:
        st.error("La table de correspondance des risques est introuvable. Contactez le support technique (voir page Aide).")
        return

    # ------------------------------------------------------------------
    # Recherche + filtres
    # ------------------------------------------------------------------
    recherche = st.text_input("🔍 Rechercher un code ou un mot-clé", "")

    with st.expander("🔎 Filtres avancés", expanded=False):
        domaines_dispo = sorted(mapping_df["domaine"].dropna().unique()) if "domaine" in mapping_df else []
        domaines_choisis = st.multiselect("Système", domaines_dispo, default=domaines_dispo)

    colonnes_affichees = [
        "reference", "evenement_ref", "domaine", "code_referentiel", "element_appreciation",
    ]
    colonnes_dispo = [c for c in colonnes_affichees if c in mapping_df.columns]
    resultat = mapping_df[colonnes_dispo].copy()

    if domaines_dispo:
        resultat = resultat[resultat["domaine"].isin(domaines_choisis)]

    if recherche:
        masque = resultat.apply(
            lambda col: col.astype(str).str.contains(recherche, case=False, na=False)
        ).any(axis=1)
        resultat = resultat[masque]

    st.caption(f"{len(resultat)} entrée(s) trouvée(s) sur {len(mapping_df)} au total.")

    if len(resultat) == 0:
        st.warning("Aucun résultat pour ces critères.")
        return

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------
    nb_pages = max(1, -(-len(resultat) // TAILLE_PAGE))  # arrondi superieur
    if "glossaire_page" not in st.session_state:
        st.session_state["glossaire_page"] = 1
    st.session_state["glossaire_page"] = min(st.session_state["glossaire_page"], nb_pages)

    col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])
    with col_nav1:
        if st.button("⬅️ Précédent", disabled=st.session_state["glossaire_page"] <= 1):
            st.session_state["glossaire_page"] -= 1
            st.rerun()
    with col_nav2:
        st.markdown(
            f"<div style='text-align:center;'>Page {st.session_state['glossaire_page']} / {nb_pages}</div>",
            unsafe_allow_html=True,
        )
    with col_nav3:
        if st.button("Suivant ➡️", disabled=st.session_state["glossaire_page"] >= nb_pages):
            st.session_state["glossaire_page"] += 1
            st.rerun()

    debut = (st.session_state["glossaire_page"] - 1) * TAILLE_PAGE
    page_resultat = resultat.iloc[debut:debut + TAILLE_PAGE]

    # ------------------------------------------------------------------
    # Tableau (le tri par colonne est natif : cliquez sur un en-tete)
    # ------------------------------------------------------------------
    st.dataframe(page_resultat, use_container_width=True, height=560)
    st.caption("💡 Cliquez sur l'en-tête d'une colonne pour trier.")

    from pages_dan.widget_assistant import afficher_assistant
    afficher_assistant("Glossaire des événements")
