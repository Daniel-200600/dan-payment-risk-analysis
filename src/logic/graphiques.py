# -*- coding: utf-8 -*-
"""
DAN - Graphiques avances (jauge, radar, camembert) via Plotly.
"""
import plotly.graph_objects as go
from logic.interpretation import interpretation_absolue, SEUILS_GRAVITE_ABSOLUE, libelle_risque

BLEU_FONCE = "#0B2E59"
OR = "#C9A227"


def jauge_risque(gravite_brute, titre="Score de risque global"):
    """
    Jauge (speedometer) fondee sur la gravite BRUTE et les memes seuils que
    le badge et les rapports (interpretation_absolue / SEUILS_GRAVITE_ABSOLUE)
    -- utilisait auparavant un score relatif (part de marche sur 100), ce qui
    pouvait afficher "Critique" en rouge pour un incident isole mineur des
    lors qu'il etait le seul evenement du mois (100% d'un total quasi nul).
    """
    seuil_critique, seuil_eleve, seuil_moyen, seuil_faible = SEUILS_GRAVITE_ABSOLUE
    info = interpretation_absolue(gravite_brute)
    niveau, couleur = info["niveau"], info["couleur"]

    # Plage dynamique : toujours un peu au-dessus du seuil Critique et de la
    # valeur affichee, pour que l'aiguille ne soit jamais hors cadre.
    plage_max = max(seuil_critique * 1.4, gravite_brute * 1.1, 1)

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=round(gravite_brute, 1),
        number={"font": {"size": 34, "color": BLEU_FONCE}},
        title={"text": f"{titre}<br><span style='font-size:14px;color:{couleur}'>{niveau}</span>"},
        gauge={
            "axis": {"range": [0, plage_max], "tickwidth": 1},
            "bar": {"color": BLEU_FONCE},
            "steps": [
                {"range": [0, seuil_faible], "color": "#C6F6D5"},
                {"range": [seuil_faible, seuil_moyen], "color": "#FEEBC8"},
                {"range": [seuil_moyen, seuil_eleve], "color": "#FEB2B2"},
                {"range": [seuil_eleve, seuil_critique], "color": "#F97070"},
                {"range": [seuil_critique, plage_max], "color": "#7B1E1E"},
            ],
            "threshold": {
                "line": {"color": OR, "width": 4},
                "thickness": 0.8,
                "value": round(gravite_brute, 1),
            },
        },
    ))
    fig.update_layout(height=280, margin=dict(l=20, r=20, t=60, b=10))
    return fig


def camembert_reseaux(score_reseau_df):
    """Repartition du score entre les 4 reseaux, avec etiquettes directes
    (nom + valeur + pourcentage) pour etre lisible sans avoir a survoler
    le graphique."""
    couleurs = [BLEU_FONCE, OR, "#4A5568", "#8AA6C1"]
    fig = go.Figure(go.Pie(
        labels=score_reseau_df["domaine"],
        values=score_reseau_df["score_100"],
        hole=0.45,
        marker=dict(colors=couleurs, line=dict(color="white", width=2)),
        textinfo="label+percent",
        textfont=dict(size=14),
        hovertemplate="<b>%{label}</b><br>%{percent} du risque total<extra></extra>",
    ))
    fig.update_layout(
        height=340, margin=dict(l=10, r=10, t=40, b=10),
        showlegend=True, title="Répartition du risque par système",
        title_font_size=16,
        annotations=[dict(text="Part du<br>risque total", x=0.5, y=0.5, showarrow=False, font_size=12)],
    )
    return fig


def barres_categories(detail_df, hauteur_barre=42):
    """
    Gravite par categorie de risque pour le reseau selectionne, sous forme
    de barres horizontales -- remplace l'ancien diagramme radar, dont la
    lecture (comparaison de surfaces et d'angles) est peu intuitive pour un
    public non specialiste. Une barre horizontale avec sa valeur affichee
    directement dessus se lit sans effort ni legende a decoder.

    detail_df doit avoir les colonnes categorie_risque / gravite (deja
    agregees), triees par gravite decroissante de preference.
    """
    if detail_df.empty:
        return None

    labels = [libelle_risque(c).capitalize() for c in detail_df["categorie_risque"]]
    valeurs = detail_df["gravite"].tolist()

    # Ordre d'affichage : la plus grave en haut (Plotly empile les barres
    # horizontales du bas vers le haut, donc on inverse la liste).
    labels_affiches = labels[::-1]
    valeurs_affichees = valeurs[::-1]

    couleurs_barres = [OR if v == max(valeurs) else BLEU_FONCE for v in valeurs_affichees]

    fig = go.Figure(go.Bar(
        x=valeurs_affichees, y=labels_affiches, orientation="h",
        marker=dict(color=couleurs_barres),
        text=[f"{v:.1f}" for v in valeurs_affichees],
        textposition="outside", textfont=dict(size=13),
        hovertemplate="<b>%{y}</b><br>Gravité : %{x:.1f}<extra></extra>",
    ))
    fig.update_layout(
        height=max(220, hauteur_barre * len(labels_affiches) + 80),
        margin=dict(l=10, r=40, t=40, b=30),
        title="Gravité par catégorie de risque", title_font_size=16,
        xaxis=dict(title="Gravité cumulée", showgrid=True, gridcolor="#E2E8F0"),
        yaxis=dict(title=None),
        showlegend=False,
        uniformtext_minsize=11,
    )
    return fig
