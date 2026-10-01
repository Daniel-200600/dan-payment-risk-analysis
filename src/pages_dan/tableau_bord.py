# -*- coding: utf-8 -*-
import streamlit as st
from style import entete_page, badge_niveau, carte_interpretation
from logic.donnees import charger_mapping, calculer_scores
from logic.interpretation import interpretation_absolue, interpreter_score_global
from logic.graphiques import camembert_reseaux


def afficher():
    entete_page("Tableau de bord", "Score de risque consolidé, expliqué et interprété")

    # evt_df_complet (tous les pays du dernier lot importe) est prioritaire
    # sur evt_df (qui peut n'etre qu'un pays isole apres un ancien flux) --
    # ainsi, apres un clic sur "Analyser" depuis un lot multi-pays, TOUS les
    # pays du lot restent proposes dans le filtre ci-dessous, pas seulement
    # celui qui a ete clique.
    donnees_source = st.session_state.get("evt_df_complet")
    if donnees_source is None:
        donnees_source = st.session_state.get("evt_df")
    if donnees_source is None:
        st.info("Importez d'abord des fichiers dans la page « Import des reportings ».")
        from pages_dan.widget_assistant import afficher_assistant
        afficher_assistant("Tableau de bord")
        return

    mapping_df = charger_mapping()
    if mapping_df is None:
        st.error("La table de correspondance des risques est introuvable. Contactez le support technique (voir page Aide).")
        from pages_dan.widget_assistant import afficher_assistant
        afficher_assistant("Tableau de bord")
        return

    evt_df_complet = donnees_source

    # ------------------------------------------------------------------
    # Filtres -- RIEN ne s'affiche en dessous tant qu'ils n'ont pas ete
    # explicitement valides (voir plus bas) : evite d'agir sur une
    # combinaison de filtres partiellement ajustee.
    # ------------------------------------------------------------------
    st.markdown("### 🔎 Filtres")
    col1, col2, col3 = st.columns(3)
    reseaux_dispo = sorted(evt_df_complet[evt_df_complet["domaine"] != "INCONNU"]["domaine"].unique())
    sites_dispo = sorted(evt_df_complet["site"].unique())

    reseaux_choisis = col1.multiselect("Système", reseaux_dispo, default=reseaux_dispo)
    sites_choisis = col2.multiselect("Site (Siège / Agence)", sites_dispo, default=sites_dispo)
    statut_choisi = col3.selectbox("Statut des événements", ["Tous", "Survenus uniquement", "Non survenus uniquement"])

    col4, col5 = st.columns(2)
    pays_dispo = sorted(evt_df_complet["pays"].unique()) if "pays" in evt_df_complet.columns else []
    pays_defaut = st.session_state.get("pays_filtre_par_defaut")
    pays_defaut = [p for p in (pays_defaut or pays_dispo) if p in pays_dispo] or pays_dispo
    pays_choisis = col4.multiselect("Pays", pays_dispo, default=pays_defaut)

    # Valeurs deja canoniques (ex. "Mars") depuis logic.donnees.lire_reporting
    # (detection prioritaire par dossier, repli sur le contenu normalise) --
    # aucune conversion supplementaire necessaire ici.
    mois_dispo = sorted(evt_df_complet["mois"].dropna().unique()) if "mois" in evt_df_complet.columns else []
    mois_choisis = col5.multiselect("Mois", mois_dispo, default=mois_dispo)

    st.caption(
        "Sélectionnez les filtres souhaités puis validez pour afficher les résultats — "
        "toute modification des filtres masque à nouveau l'affichage jusqu'à la "
        "prochaine validation."
    )
    signature_filtres = (
        tuple(sorted(reseaux_choisis)), tuple(sorted(sites_choisis)), statut_choisi,
        tuple(sorted(pays_choisis)), tuple(sorted(mois_choisis)),
    )
    if st.button("✅ Valider les filtres", type="primary"):
        st.session_state["tb_filtres_valides"] = signature_filtres

    st.markdown("---")

    if st.session_state.get("tb_filtres_valides") != signature_filtres:
        st.info(
            "ℹ️ Ajustez les filtres ci-dessus puis cliquez sur « Valider les filtres » "
            "pour afficher le tableau de bord."
        )
        from pages_dan.widget_assistant import afficher_assistant
        afficher_assistant("Tableau de bord")
        return

    evt_df = evt_df_complet[
        evt_df_complet["domaine"].isin(reseaux_choisis) & evt_df_complet["site"].isin(sites_choisis)
    ]
    if pays_dispo:
        evt_df = evt_df[evt_df["pays"].isin(pays_choisis)]
    if mois_dispo:
        # Une ligne sans mois renseigne (NaN) reste visible tant que le
        # filtre n'exclut pas explicitement les mois connus -- seul un
        # mois EFFECTIVEMENT present et deselectionne doit filtrer.
        evt_df = evt_df[evt_df["mois"].isna() | evt_df["mois"].isin(mois_choisis)]
    if statut_choisi == "Survenus uniquement":
        evt_df = evt_df[evt_df["survenance_bin"] == 1]
    elif statut_choisi == "Non survenus uniquement":
        evt_df = evt_df[evt_df["survenance_bin"] == 0]

    # Rend la selection filtree et validee disponible aux autres pages
    # (Analyse des incidents, Génération des rapports) qui dependent encore
    # de evt_df -- sans cette ligne, ces pages restent vides des lors que
    # le lot importe couvre plusieurs pays (le seul "evt_df" pose par
    # Import des reportings dans ce cas est evt_df_complet, jamais evt_df).
    st.session_state["evt_df"] = evt_df

    if len(evt_df) == 0:
        st.warning("Aucun événement ne correspond aux filtres sélectionnés.")
        from pages_dan.widget_assistant import afficher_assistant
        afficher_assistant("Tableau de bord", evt_df=evt_df_complet)
        return

    # ------------------------------------------------------------------
    # Score : un bloc complet par pays quand plusieurs pays sont valides
    # a la fois dans les filtres -- pas un seul score global qui les
    # confondrait. Un seul pays selectionne (ou present) revient au
    # comportement d'un score unique, sans changement visuel.
    # ------------------------------------------------------------------
    pays_dans_selection = sorted(evt_df["pays"].dropna().unique()) if "pays" in evt_df.columns else []
    info_dernier = None
    score_reseau_dernier = None

    if len(pays_dans_selection) > 1:
        st.info(
            f"ℹ️ {len(pays_dans_selection)} pays sélectionnés — le score est calculé "
            f"et affiché séparément pour chacun, pas comme un total unique qui les "
            f"mélangerait."
        )
        for pays in pays_dans_selection:
            st.markdown(f"## 🌍 {pays}")
            info_dernier, score_reseau_dernier = _afficher_bloc_score(
                evt_df[evt_df["pays"] == pays], mapping_df
            )
            st.markdown("---")
    else:
        info_dernier, score_reseau_dernier = _afficher_bloc_score(evt_df, mapping_df)

    st.markdown("<br>", unsafe_allow_html=True)
    afficher_evolution_et_historique(evt_df, mapping_df)

    st.markdown("<br>", unsafe_allow_html=True)
    _afficher_camembert_global(evt_df, mapping_df)

    from pages_dan.widget_assistant import afficher_assistant
    reseau_principal_nom = (
        score_reseau_dernier.sort_values("score_100", ascending=False).iloc[0]["domaine"]
        if score_reseau_dernier is not None and len(score_reseau_dernier) else None
    )
    afficher_assistant(
        "Tableau de bord", evt_df=evt_df, score_reseau=score_reseau_dernier,
        niveau_info=info_dernier, reseau_principal=reseau_principal_nom,
    )


def _afficher_camembert_global(evt_df, mapping_df):
    """
    Camembert de repartition du risque par systeme, calcule sur TOUTES
    les donnees actuellement filtrees (tous pays confondus si plusieurs
    sont selectionnes) -- vue d'ensemble globale, distincte des
    camemberts par pays affiches plus haut (un par pays, dans
    _afficher_bloc_score). Positionne tout en bas de la page.
    """
    st.subheader("📊 Répartition globale du risque par système")
    df_gravite_global = calculer_scores(evt_df, mapping_df)
    score_reseau_global = df_gravite_global.groupby("domaine")["gravite"].sum().reset_index()
    score_reseau_global = score_reseau_global[score_reseau_global["domaine"] != "INCONNU"]
    total_global = score_reseau_global["gravite"].sum()
    score_reseau_global["score_100"] = (
        (score_reseau_global["gravite"] / total_global * 100).round(1) if total_global > 0 else 0
    )

    if total_global > 0:
        st.plotly_chart(camembert_reseaux(score_reseau_global), use_container_width=True)
        st.caption(
            "Répartition du risque par système, tous pays et tous mois actuellement "
            "affichés confondus — une vue d'ensemble, en complément des répartitions "
            "individuelles par pays plus haut."
        )
    else:
        st.info("Camembert non affiché : aucun risque à répartir sur la sélection actuelle.")


def _afficher_bloc_score(evt_df, mapping_df):
    """
    Affiche le bloc complet (KPI, interprétation, camembert) pour UN
    sous-ensemble d'événements (un seul pays, ou toutes les données si
    un seul pays est de toute façon présent) -- factorisé pour pouvoir
    être appelé une fois (cas simple) ou en boucle (plusieurs pays
    validés dans les filtres, voir afficher()). Pas de score global ni de
    jauge : l'évolution du score par mois et par pays (voir
    afficher_evolution_et_historique) remplace ces deux elements, plus
    lisible qu'un chiffre ou une jauge isolee par pays. Renvoie
    (info, score_reseau) pour alimenter l'assistant contextuel de la page.
    """
    df_gravite = calculer_scores(evt_df, mapping_df)
    score_reseau = df_gravite.groupby("domaine")["gravite"].sum().reset_index()
    score_reseau = score_reseau[score_reseau["domaine"] != "INCONNU"]
    total = score_reseau["gravite"].sum()
    score_reseau["score_100"] = (
        (score_reseau["gravite"] / total * 100).round(1) if total > 0 else 0
    )
    niveau_global = interpretation_absolue(total)["niveau"]

    nb_evenements = len(evt_df)
    nb_incidents = int(evt_df["survenance_bin"].sum())
    nb_reseaux = evt_df[evt_df["domaine"] != "INCONNU"]["domaine"].nunique()
    disponibilite = round(100 * (1 - nb_incidents / nb_evenements), 1) if nb_evenements else 100

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(
        "Événements suivis", nb_evenements,
        help="Nombre total de lignes du référentiel suivies dans les fichiers importés, qu'elles se soient produites ou non ce mois-ci.",
    )
    c2.metric(
        "Incidents ce mois-ci", nb_incidents,
        help="Parmi les événements suivis, combien sont réellement survenus (déclarés « Oui ») sur la période.",
    )
    c3.metric(
        "Systèmes surveillés", nb_reseaux,
        help="Nombre de systèmes (sur SYGMA, SYSTAC, SWIFT, RESEAU) pour lesquels au moins un fichier a été importé.",
    )
    c4.metric(
        "Disponibilité globale", f"{disponibilite}%",
        help=(
            "100 % moins la part d'événements survenus (incidents ÷ événements suivis). "
            "Un indicateur simple d'activité — à ne pas confondre avec le niveau de risque, "
            "qui tient aussi compte de la gravité de chaque incident."
        ),
    )
    c5.markdown(
        f"<div style='padding-top:8px;'>Indice de risque "
        f"<span title=\"Traduction du score en 5 niveaux (Très faible à Critique), "
        f"pour une lecture rapide sans avoir à interpréter le chiffre brut.\">ℹ️</span>"
        f"<br>{badge_niveau(niveau_global)}</div>",
        unsafe_allow_html=True,
    )

    st.markdown("#### 🧭 Interprétation du score")
    info = interpretation_absolue(total)
    st.markdown(carte_interpretation(info), unsafe_allow_html=True)
    st.caption(
        "ℹ️ Ces seuils sont modifiables dans Paramètres → « Seuils de score », "
        "selon vos propres besoins d'analyse."
    )
    st.markdown(interpreter_score_global(score_reseau, nb_incidents, nb_evenements))

    st.markdown("<br>", unsafe_allow_html=True)

    col_evolution, col_camembert = st.columns(2)
    with col_evolution:
        _afficher_graphique_evolution_pays(evt_df, mapping_df)
    with col_camembert:
        if total > 0:
            st.plotly_chart(camembert_reseaux(score_reseau), use_container_width=True)
            st.caption("Ce graphique montre quelle part du risque total revient à chaque système.")
        else:
            st.info("Camembert non affiché : aucun risque à répartir ce mois-ci (score global nul).")

    return info, score_reseau


def _afficher_graphique_evolution_pays(evt_df, mapping_df):
    """
    Graphique d'evolution du score par mois, pour UN SEUL pays (celui du
    bloc en cours -- voir _afficher_bloc_score) -- distinct du graphique
    de comparaison multi-pays affiche plus bas dans afficher_evolution_et_historique,
    qui compare plusieurs pays entre eux. Ici, une seule courbe, propre a
    ce pays, pour voir sa propre tendance sans les autres pays autour.
    """
    from logic.donnees import calculer_scores, MOIS_CANONIQUES
    import plotly.express as px
    import pandas as pd

    mois_presents = evt_df["mois"].dropna().unique() if "mois" in evt_df.columns else []
    if len(mois_presents) <= 1:
        st.info(
            "📈 L'évolution par mois s'affiche automatiquement dès que les données "
            "de ce pays couvrent plusieurs mois."
        )
        return

    scores_par_mois = []
    for mois, groupe in evt_df.groupby("mois"):
        df_gravite_mois = calculer_scores(groupe, mapping_df)
        scores_par_mois.append({"mois": mois, "score": round(df_gravite_mois["gravite"].sum(), 1)})
    df_scores_mois = pd.DataFrame(scores_par_mois)
    df_scores_mois["mois"] = pd.Categorical(df_scores_mois["mois"], categories=MOIS_CANONIQUES, ordered=True)
    df_scores_mois = df_scores_mois.sort_values("mois")

    fig = px.line(df_scores_mois, x="mois", y="score", markers=True,
                   color_discrete_sequence=["#0B2E59"])
    fig.update_layout(xaxis_title="Mois", yaxis_title="Score de gravité")
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Évolution du score de ce pays, mois par mois (classés chronologiquement)."
    )


def afficher_evolution_et_historique(evt_df, mapping_df):
    from logic.donnees import MOIS_CANONIQUES
    import plotly.express as px
    import pandas as pd

    st.subheader("Évolution")

    # ------------------------------------------------------------------
    # Score par mois, calcule sur les DONNEES ACTUELLEMENT CHARGEES --
    # pertinent des lors qu'un pays peut a lui seul couvrir plusieurs mois
    # (arborescence Pays/MOIS X/Banque/...). Une courbe par pays des que
    # plusieurs pays sont selectionnes dans les filtres (ex. l'agent valide
    # tous les pays a la fois) -- avec legende et mois dans l'ordre
    # chronologique (pas alphabetique : "Avril" ne doit pas passer avant
    # "Février").
    # ------------------------------------------------------------------
    mois_presents = evt_df["mois"].dropna().unique() if "mois" in evt_df.columns else []
    if len(mois_presents) <= 1:
        st.info(
            "📈 Ce graphique compare le score de gravité par mois — il s'affiche "
            "automatiquement dès que les données chargées couvrent plusieurs mois "
            "(ex. un pays avec plusieurs sous-dossiers MOIS X)."
        )
        return

    a_plusieurs_pays = "pays" in evt_df.columns and evt_df["pays"].nunique() > 1
    colonnes_groupe = ["mois", "pays"] if a_plusieurs_pays else ["mois"]

    scores_par_mois = []
    for cles, groupe in evt_df.groupby(colonnes_groupe):
        cles = cles if isinstance(cles, tuple) else (cles,)
        df_gravite_mois = calculer_scores(groupe, mapping_df)
        ligne = dict(zip(colonnes_groupe, cles))
        ligne["score"] = round(df_gravite_mois["gravite"].sum(), 1)
        scores_par_mois.append(ligne)
    df_scores_mois = pd.DataFrame(scores_par_mois)

    # Tri chronologique (Janvier avant Février, etc.), pas alphabetique.
    df_scores_mois["mois"] = pd.Categorical(df_scores_mois["mois"], categories=MOIS_CANONIQUES, ordered=True)
    df_scores_mois = df_scores_mois.sort_values("mois")

    st.markdown("##### 📅 Comparaison des scores par mois")
    fig_mois = px.line(
        df_scores_mois, x="mois", y="score",
        color="pays" if a_plusieurs_pays else None,
        markers=True,
        color_discrete_sequence=["#0B2E59", "#C9A227", "#2F855A", "#C05621", "#6B46C1", "#B83280"],
    )
    fig_mois.update_layout(
        xaxis_title="Mois", yaxis_title="Score de gravité",
        legend_title="Pays" if a_plusieurs_pays else None,
    )
    st.plotly_chart(fig_mois, use_container_width=True)
    st.caption(
        "Ce graphique compare le score de gravité de chaque mois présent dans les "
        "données actuellement chargées"
        + (", une courbe par pays" if a_plusieurs_pays else "")
        + " — les mois sont classés chronologiquement, pas alphabétiquement."
    )
