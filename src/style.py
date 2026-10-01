# -*- coding: utf-8 -*-
"""
DAN - Charte graphique institutionnelle (bleu fonce / or)
Injecte du CSS personnalise dans Streamlit pour donner un rendu "logiciel
metier de banque centrale" plutot que l'apparence par defaut de Streamlit.
"""
import streamlit as st
import os
from chemins import chemin_ressource

BLEU_FONCE = "#0B2E59"
BLEU_TRES_FONCE = "#081F3D"
OR = "#C9A227"
OR_CLAIR = "#E8D48A"
BLANC = "#FFFFFF"
GRIS_CLAIR = "#F4F6F9"
GRIS_TEXTE = "#4A5568"
VERT = "#2F855A"
ORANGE = "#C05621"
ROUGE = "#C53030"


def injecter_css(theme="clair", couleur_principale=None, couleur_secondaire=None):
    """
    Injecte la charte graphique. Appelee sans argument (comme partout
    actuellement), le comportement est strictement identique a avant --
    les parametres ne servent qu'a la personnalisation ajoutee en Phase 9
    (page Parametres).
    """
    bleu = couleur_principale or BLEU_FONCE
    or_ = couleur_secondaire or OR
    bleu_tres_fonce = _assombrir(bleu) if couleur_principale else BLEU_TRES_FONCE

    if theme == "sombre":
        fond_app, fond_carte, texte_defaut = "#0D1117", "#161B22", "#E2E8F0"
        gris_texte = "#A0AEC0"
    else:
        fond_app, fond_carte, texte_defaut = GRIS_CLAIR, BLANC, "#1A202C"
        gris_texte = GRIS_TEXTE

    st.markdown(f"""
    <style>
        /* Fond general de l'application */
        .stApp {{
            background-color: {fond_app};
            color: {texte_defaut};
        }}

        /* Barre laterale */
        section[data-testid="stSidebar"] {{
            background-color: {bleu_tres_fonce};
        }}
        section[data-testid="stSidebar"] * {{
            color: {BLANC} !important;
        }}
        section[data-testid="stSidebar"] .stRadio > label {{
            color: {BLANC} !important;
        }}

        /* Titres */
        h1, h2, h3 {{
            color: {bleu};
            font-family: 'Segoe UI', 'Calibri', sans-serif;
        }}

        /* Cartes KPI / metriques */
        div[data-testid="stMetric"] {{
            background-color: {fond_carte};
            border: 1px solid #E2E8F0;
            border-left: 5px solid {or_};
            border-radius: 8px;
            padding: 14px 18px;
            box-shadow: 0 1px 3px rgba(11, 46, 89, 0.08);
        }}
        div[data-testid="stMetric"] label {{
            color: {gris_texte} !important;
        }}

        /* Boutons */
        .stButton > button {{
            background-color: {bleu};
            color: {BLANC};
            border: none;
            border-radius: 6px;
            font-weight: 600;
        }}
        .stButton > button:hover {{
            background-color: {or_};
            color: {bleu_tres_fonce};
        }}

        /* Bandeau d'en-tete */
        .dan-header {{
            background: linear-gradient(90deg, {bleu_tres_fonce} 0%, {bleu} 100%);
            border-bottom: 4px solid {or_};
            padding: 18px 28px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        .dan-header h1 {{
            color: {BLANC} !important;
            margin: 0;
            font-size: 26px;
        }}
        .dan-header p {{
            color: {OR_CLAIR} !important;
            margin: 2px 0 0 0;
            font-style: italic;
        }}
        .dan-header-accueil {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 24px;
        }}
        .dan-header-texte {{
            flex: 1;
        }}
        .dan-header-logo {{
            height: 64px;
            padding: 8px 14px;
            background: {BLANC};
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.18);
            flex-shrink: 0;
        }}

        /* Badges de niveau de risque */
        .badge {{
            display: inline-block;
            padding: 3px 12px;
            border-radius: 999px;
            font-weight: 600;
            font-size: 13px;
            color: {BLANC};
        }}
        .badge-tres-faible {{ background-color: {VERT}; }}
        .badge-faible {{ background-color: #B7950B; }}
        .badge-moyen {{ background-color: {ORANGE}; }}
        .badge-eleve {{ background-color: {ROUGE}; }}
        .badge-critique {{ background-color: #3B0A0A; }}

        /* Carte d'interpretation detaillee de score */
        .dan-interpretation {{
            background-color: {fond_carte};
            border-radius: 8px;
            padding: 16px 20px;
            box-shadow: 0 1px 4px rgba(11, 46, 89, 0.10);
            border-left: 6px solid var(--dan-couleur-niveau, {or_});
            margin: 10px 0;
        }}
        .dan-interpretation h4 {{
            margin: 0 0 8px 0;
            color: {bleu};
        }}
        .dan-interpretation .champ {{
            margin: 4px 0;
            font-size: 14px;
        }}
        .dan-interpretation .champ b {{
            color: {gris_texte};
        }}
        .dan-explication {{
            background-color: rgba(201, 162, 39, 0.10);
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 13.5px;
            line-height: 1.5;
        }}
        .dan-echelle {{
            display: flex;
            gap: 4px;
            margin: 12px 0;
        }}
        .dan-palier {{
            flex: 1;
            text-align: center;
            font-size: 11px;
            font-weight: 600;
            padding: 6px 2px;
            border-radius: 5px;
            background-color: #EDF2F7;
            color: #718096;
            opacity: 0.55;
        }}
        .dan-palier small {{
            font-weight: 400;
            font-size: 10px;
        }}
        .dan-palier.actif {{
            opacity: 1;
            background-color: var(--dan-couleur-niveau, {or_});
            color: white;
            transform: scale(1.05);
        }}

        /* Cartes generiques (page d'accueil) */
        .dan-card {{
            background-color: {fond_carte};
            border-radius: 10px;
            padding: 18px;
            text-align: center;
            box-shadow: 0 1px 4px rgba(11, 46, 89, 0.10);
            border-top: 4px solid {or_};
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }}
        .dan-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 6px 14px rgba(11, 46, 89, 0.18);
        }}
        div[data-testid="stMetric"] {{
            transition: box-shadow 0.15s ease;
        }}
        div[data-testid="stMetric"]:hover {{
            box-shadow: 0 4px 10px rgba(11, 46, 89, 0.15);
        }}
        .stButton > button {{
            transition: background-color 0.15s ease, transform 0.1s ease;
        }}
        .stButton > button:active {{
            transform: scale(0.97);
        }}
        .dan-card .valeur {{
            font-size: 30px;
            font-weight: 700;
            color: {bleu};
        }}
        .dan-card .libelle {{
            color: {gris_texte};
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
    </style>
    """, unsafe_allow_html=True)


def _assombrir(couleur_hex, facteur=0.35):
    """Assombrit une couleur hexadecimale (utilise pour deriver la teinte
    sidebar depuis la couleur principale choisie par l'utilisateur)."""
    couleur_hex = couleur_hex.lstrip("#")
    try:
        r, g, b = (int(couleur_hex[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return BLEU_TRES_FONCE
    r, g, b = (max(0, int(c * (1 - facteur))) for c in (r, g, b))
    return f"#{r:02X}{g:02X}{b:02X}"




def entete_page(titre, sous_titre=""):
    """Bandeau bleu/or en haut de chaque page, precede d'un fil d'Ariane
    et d'un retour rapide vers l'accueil. Le logo n'apparait plus
    sur chaque page : il figure une seule fois, integre directement dans
    ce bandeau, uniquement sur la page d'accueil (la ou le nom de
    l'application est affiche) -- voir _logo_balise_img()."""
    if titre != "DAN":
        fil_ariane = st.columns([1, 6])
        with fil_ariane[0]:
            try:
                st.page_link("pages_dan/accueil.py", label="🏠 Accueil")
            except Exception:
                st.caption("🏠 Accueil")
        with fil_ariane[1]:
            st.caption(f"Accueil / **{titre}**")

        st.markdown(f"""
        <div class="dan-header">
            <h1>{titre}</h1>
            <p>{sous_titre}</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        logo_html = _logo_balise_img()
        st.markdown(f"""
        <div class="dan-header dan-header-accueil">
            <div class="dan-header-texte">
                <h1>{titre}</h1>
                <p>{sous_titre}</p>
            </div>
            {logo_html}
        </div>
        """, unsafe_allow_html=True)


def _logo_balise_img():
    """Balise <img> encodee en base64 pour le logo, integrable
    directement dans un bloc HTML (st.markdown) -- contrairement a
    st.image(), qui ne peut pas cohabiter dans la meme div qu'un autre
    element HTML. Chaine vide si le logo est absent (le bandeau reste
    alors sobre, sans casser la mise en page)."""
    chemin_logo = chemin_ressource("referentiels/logo.png")
    if not os.path.exists(chemin_logo):
        return ""
    import base64
    with open(chemin_logo, "rb") as f:
        logo_b64 = base64.b64encode(f.read()).decode("utf-8")
    return f'<img src="data:image/png;base64,{logo_b64}" class="dan-header-logo" alt="Logo">'


def badge_niveau(niveau_texte):
    """Renvoie le HTML d'un badge colore selon un niveau de risque textuel."""
    correspondance = {
        "très faible": "badge-tres-faible", "tres faible": "badge-tres-faible", "vert": "badge-tres-faible",
        "faible": "badge-faible", "jaune": "badge-faible",
        "moyen": "badge-moyen", "sensible": "badge-moyen", "orange": "badge-moyen",
        "eleve": "badge-eleve", "élevé": "badge-eleve", "majeur": "badge-eleve", "rouge": "badge-eleve",
        "critique": "badge-critique",
    }
    classe = correspondance.get(str(niveau_texte).strip().lower(), "badge-moyen")
    return f'<span class="badge {classe}">{niveau_texte}</span>'


def carte_interpretation(info):
    """
    Affiche le chiffre de gravite d'un score, avec une explication simple
    de ce qu'il represente -- reduit au strict necessaire (le score et son
    explication), sans echelle de paliers ni blocs de recommandation
    supplementaires, a partir du dictionnaire renvoye par
    logic.interpretation.interpretation_absolue().
    """
    return f"""
    <div class="dan-interpretation" style="--dan-couleur-niveau:{info['couleur']};">
        <h4>{info['emoji']} {info['score']:.1f} — {info['niveau']}</h4>
        <div class="champ dan-explication">
            {info['score']:.1f} n'est pas un pourcentage : c'est la somme pondérée de
            tous les incidents détectés (leur gravité et leur fréquence). Plus ce
            nombre est élevé, plus la situation est préoccupante.
        </div>
    </div>
    """
