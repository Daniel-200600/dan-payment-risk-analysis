# -*- coding: utf-8 -*-
"""
DAN - Point d'entree principal (Phase 1 : architecture multi-pages + identite visuelle)

Lancement : streamlit run src/dashboard.py  (depuis la racine du projet DAN/)

Structure :
    style.py            -> charte graphique bleu/or, composants visuels reutilisables
    logic/donnees.py     -> lecture des reportings + calcul du score (logique metier)
    logic/rapports.py    -> generation des rapports Word (logique metier)
    pages_dan/*.py        -> une page = un fichier, chacun expose une fonction afficher()
"""
import streamlit as st
from style import injecter_css
from logic.configuration import charger_configuration

from pages_dan import (
    accueil, import_reportings, tableau_bord,
    analyse_risques, glossaire, rapports, historique, multi_participants, parametres, aide,
)

st.set_page_config(
    page_title="DAN - Payment Systems Oversight",
    page_icon="🏦",
    layout="wide",
)
_config = charger_configuration()
injecter_css(
    theme=_config["theme"],
    couleur_principale=_config["couleur_principale"],
    couleur_secondaire=_config["couleur_secondaire"],
)

page_accueil = st.Page(accueil.afficher, title="Accueil", icon="🏠", url_path="accueil")
page_import = st.Page(import_reportings.afficher, title="Import des reportings", icon="📂", url_path="import")
page_tableau_bord = st.Page(tableau_bord.afficher, title="Tableau de bord", icon="📊", url_path="tableau-de-bord")
page_analyse_risques = st.Page(analyse_risques.afficher, title="Analyse des incidents", icon="📈", url_path="analyse-incidents")
page_glossaire = st.Page(glossaire.afficher, title="Glossaire des événements", icon="📚", url_path="glossaire")
page_rapports = st.Page(rapports.afficher, title="Génération des rapports", icon="📄", url_path="rapports")
page_historique = st.Page(historique.afficher, title="Historique des analyses", icon="🕓", url_path="historique")
page_multi_participants = st.Page(multi_participants.afficher, title="Vue multi-participants", icon="👥", url_path="multi-participants")
page_parametres = st.Page(parametres.afficher, title="Paramètres", icon="⚙️", url_path="parametres")
page_aide = st.Page(aide.afficher, title="Aide", icon="❓", url_path="aide")

# Expose les objets Page (necessaires, pas de simples chaines, pour cibler une
# page definie par fonction -- voir st.switch_page) afin que d'autres pages
# puissent y naviguer directement, ex. le bouton "Analyser" depuis Import des
# reportings ou Vue multi-participants renvoyant droit au Tableau de bord.
st.session_state["_pages_dan"] = {
    "accueil": page_accueil, "import": page_import, "tableau_bord": page_tableau_bord,
    "analyse_risques": page_analyse_risques, "glossaire": page_glossaire,
    "rapports": page_rapports, "historique": page_historique,
    "multi_participants": page_multi_participants, "parametres": page_parametres, "aide": page_aide,
}

pg = st.navigation([
    page_accueil, page_import, page_tableau_bord, page_analyse_risques, page_glossaire,
    page_rapports, page_historique, page_multi_participants, page_parametres, page_aide,
])
pg.run()
