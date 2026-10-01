# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from style import entete_page, badge_niveau
from logic.historique import charger_historique
from logic.participants import PAYS_CEMAC


BLEU_FONCE = "#0B2E59"
OR = "#C9A227"
GRIS = "#A0AEC0"


def _dernieres_analyses_par_pays(historique):
    """
    Reduit l'historique complet a UNE ligne par pays : sa derniere
    analyse enregistree (l'historique est deja trie du plus recent au
    plus ancien, voir logic.historique.enregistrer_analyse).
    """
    vues = {}
    for entree in historique:
        pays = entree.get("pays", "INCONNU")
        if pays not in vues:
            vues[pays] = entree
    return list(vues.values())


def _completer_avec_cemac(dernieres):
    """
    Complete les dernieres analyses connues avec les pays membres de la
    CEMAC n'ayant encore jamais ete importes -- pour que la vue montre
    "tout le monde", pas seulement les pays deja rencontres. Aucune liste
    a charger : les six pays sont un ensemble fixe et connu de DAN.
    """
    pays_connus = {e["pays"] for e in dernieres}
    complet = list(dernieres)
    for pays in PAYS_CEMAC:
        if pays in pays_connus:
            continue
        complet.append({
            "pays": pays, "date": None, "heure": None,
            "systemes_analyses": [], "score_obtenu": None,
            "niveau_risque": "Non transmis", "id": None,
        })
    return complet


def _graphique_comparaison(dernieres):
    evalues = [e for e in dernieres if e["score_obtenu"] is not None]
    if not evalues:
        return None
    dernieres_triees = sorted(evalues, key=lambda e: e["score_obtenu"], reverse=True)
    labels = [e.get("pays", "INCONNU") for e in dernieres_triees]
    valeurs = [e["score_obtenu"] for e in dernieres_triees]
    couleurs = [OR if v == max(valeurs) else BLEU_FONCE for v in valeurs]

    fig = go.Figure(go.Bar(
        x=valeurs[::-1], y=labels[::-1], orientation="h",
        marker=dict(color=couleurs[::-1]),
        text=[f"{v:.1f}" for v in valeurs[::-1]], textposition="outside",
        hovertemplate="<b>%{y}</b><br>Score : %{x:.1f}<extra></extra>",
    ))
    fig.update_layout(
        height=max(220, 45 * len(labels) + 80),
        margin=dict(l=10, r=40, t=30, b=30),
        xaxis=dict(title="Gravité cumulée (dernière analyse)", showgrid=True, gridcolor="#E2E8F0"),
        yaxis=dict(title=None), showlegend=False,
    )
    return fig


def afficher():
    entete_page(
        "Vue multi-participants",
        "Comparaison de tous les pays suivis par DAN",
    )

    historique = charger_historique()
    if not historique:
        st.info(
            "Aucune analyse enregistrée pour l'instant. Importez des fichiers dans "
            "« Import des reportings » pour commencer — si votre lot provient d'un "
            "dossier organisé par Pays / Banque, les pays apparaîtront ici "
            "automatiquement."
        )
        from pages_dan.widget_assistant import afficher_assistant
        afficher_assistant("Vue multi-participants")
        return

    dernieres = _dernieres_analyses_par_pays(historique)
    dernieres = _completer_avec_cemac(dernieres)
    nb_transmis = sum(1 for e in dernieres if e["score_obtenu"] is not None)

    st.caption(
        f"✅ Comparaison sur l'ensemble des {len(PAYS_CEMAC)} pays membres de la "
        f"CEMAC — aucune liste à charger, cet ensemble est fixe et intégré à DAN."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Taux de transmission", f"{nb_transmis} / {len(PAYS_CEMAC)}")
    evalues = [e for e in dernieres if e["score_obtenu"] is not None]
    c2.metric(
        "Niveau le plus élevé actuellement",
        max(evalues, key=lambda e: e["score_obtenu"])["niveau_risque"] if evalues else "—",
    )
    nb_critiques = sum(1 for e in evalues if e["niveau_risque"] == "Critique")
    c3.metric("Pays au niveau Critique", nb_critiques)
    nb_non_transmis = sum(1 for e in dernieres if e["score_obtenu"] is None)
    c4.metric("Non transmis", nb_non_transmis)

    fig = _graphique_comparaison(dernieres)
    if fig:
        st.markdown("### Comparaison des scores (pays transmis)")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Détail par pays")
    evt_df_complet = st.session_state.get("evt_df_complet")

    for entree in sorted(
        dernieres,
        key=lambda e: (e["score_obtenu"] is None, -(e["score_obtenu"] or 0)),
    ):
        col_a, col_b, col_c, col_d, col_e = st.columns([2, 2, 2, 2, 2])
        col_a.markdown(f"**{entree.get('pays', 'INCONNU')}**")
        col_b.write(", ".join(entree.get("systemes_analyses", []) or []) or "—")
        col_c.write(f"Analysé le {entree['date']}" if entree.get("date") else "Jamais transmis")
        col_d.markdown(badge_niveau(entree["niveau_risque"]), unsafe_allow_html=True)

        peut_zoomer = (
            evt_df_complet is not None
            and "pays" in evt_df_complet.columns
            and entree.get("pays") in evt_df_complet["pays"].values
        )
        if peut_zoomer:
            if col_e.button("🔍 Ouvrir le tableau de bord", key=f"zoom_{entree.get('pays', 'INCONNU')}_{entree.get('id') or 'ref'}"):
                st.session_state["historique_id_courant"] = entree.get("id")
                st.session_state["pays_filtre_par_defaut"] = [entree.get("pays")]
                st.switch_page(st.session_state["_pages_dan"]["tableau_bord"])
        elif entree["score_obtenu"] is None:
            col_e.caption("En attente de transmission")
        else:
            col_e.caption("Réimportez ses fichiers pour le détail complet")

    st.markdown("---")
    st.caption(
        "**Limite actuelle** : le tableau de bord détaillé d'un pays n'est "
        "disponible que pour les données de la session en cours (juste après un "
        "import). Les scores, eux, restent visibles indéfiniment via l'historique. "
        "Pour ré-ouvrir le détail complet d'un pays plus ancien, réimportez ses "
        "fichiers."
    )

    from pages_dan.widget_assistant import afficher_assistant
    afficher_assistant("Vue multi-participants")
