# -*- coding: utf-8 -*-
"""
DAN - Logique metier : generation des rapports Word par reseau.
Deplace tel quel depuis l'ancienne version de dashboard.py -- aucun
changement de comportement.
"""
import pandas as pd
import os
import io
import base64
import subprocess
from datetime import date, datetime
from .donnees import POIDS_NIVEAU, EXCLUS, calculer_gravite_evenement
from .interpretation import interpretation_absolue
from chemins import chemin_ressource

TEMPLATES = {
    "SYGMA": chemin_ressource("templates/rapport_SYGMA.docx"),
    "SWIFT": chemin_ressource("templates/rapport_SWIFT.docx"),
    "SYSTAC": chemin_ressource("templates/rapport_SYSTAC.docx"),
    "RESEAU": chemin_ressource("templates/rapport_RESEAU.docx"),
}
PARTICIPANT = "Participant (à personnaliser)"


def nettoyer_espacement(doc):
    """
    Retire les paragraphes vides EXCEDENTAIRES d'un document deja rendu
    par docxtpl -- les balises Jinja ({% if %}, {% for %}...{% endfor %})
    laissent souvent des paragraphes vides une fois le texte substitue,
    meme quand le modele source ne comportait pas de sequence de 3
    paragraphes vides consecutifs (chaque balise occupe sa propre ligne
    dans le modele ; une fois rendue, cette ligne ne disparait pas,
    seulement son contenu). Ne garde qu'UN SEUL paragraphe vide par
    sequence consecutive, pour un espacement propre et regulier partout
    dans le document -- appelee juste avant la sauvegarde finale.

    IMPORTANT : un paragraphe contenant une IMAGE (graphique, logo) a un
    .text vide (le texte ne reflete que les runs textuels, pas les
    dessins/images), mais n'est PAS un paragraphe vide -- le retirer
    supprimerait l'image elle-meme. Il est donc explicitement exclu du
    nettoyage, jamais compte dans une sequence a collapser.
    """
    from docx.oxml.ns import qn

    def contient_une_image(paragraphe):
        return bool(paragraphe._element.findall(f".//{qn('w:drawing')}"))

    a_retirer = []
    sequence_vide = []
    for p in doc.paragraphs:
        if p.text.strip() == "" and not contient_une_image(p):
            sequence_vide.append(p)
        else:
            if len(sequence_vide) >= 2:
                a_retirer.extend(sequence_vide[1:])
            sequence_vide = []
    if len(sequence_vide) >= 2:
        a_retirer.extend(sequence_vide[1:])

    for p in a_retirer:
        p._element.getparent().remove(p._element)


def identifier_participant_periode(evt_df):
    """
    Construit le libelle du participant et la periode (mois/annee) pour
    l'en-tete des rapports. Le libelle reprend le(s) pays (deduit du nom
    du dossier de premier niveau lors d'un depot de dossier entier -- voir
    logic.donnees._deduire_pays) quand il est connu -- TOUS les pays
    presents si plusieurs, pas seulement le premier trouve. La periode
    reprend l'Annee/le Mois -- lus en priorite depuis l'organisation des
    dossiers, a defaut depuis le CONTENU du fichier (voir
    logic.donnees.lire_reporting et extraire_periode), deja normalises
    sous forme canonique (ex. "Mars", pas "3") au moment de la lecture --
    et couvre la PLAGE COMPLETE (ex. "Février - Avril") si plusieurs mois
    sont presents, pas seulement le premier. Se rabat sur le texte de
    remplissage manuel PARTICIPANT, et sur "-" pour la periode, quand ces
    informations ne sont pas disponibles (fichiers deposes isolement,
    sans dossier parent, ou gabarit incomplet).
    """
    from logic.donnees import MOIS_CANONIQUES

    libelle = PARTICIPANT
    if "pays" in evt_df.columns and evt_df["pays"].notna().any():
        pays_presents = sorted(p for p in evt_df["pays"].dropna().unique() if p != "INCONNU")
        if pays_presents:
            libelle = ", ".join(pays_presents)

    mois = "-"
    if "mois" in evt_df.columns and evt_df["mois"].notna().any():
        mois_presents = [m for m in evt_df["mois"].dropna().unique() if m in MOIS_CANONIQUES]
        if mois_presents:
            mois_presents.sort(key=MOIS_CANONIQUES.index)
            mois = mois_presents[0] if len(mois_presents) == 1 else f"{mois_presents[0]} - {mois_presents[-1]}"
        else:
            mois = str(evt_df["mois"].dropna().iloc[0]).strip()
    annee = "-"
    if "annee" in evt_df.columns and evt_df["annee"].notna().any():
        annees_presentes = sorted(evt_df["annee"].dropna().unique())
        annee = annees_presentes[0] if len(annees_presentes) == 1 else f"{annees_presentes[0]} - {annees_presentes[-1]}"

    return libelle, mois, annee


def inserer_logo(doc):
    from docxtpl import InlineImage
    from docx.shared import Mm
    chemin_logo = chemin_ressource("referentiels/logo.png")
    if os.path.exists(chemin_logo):
        return InlineImage(doc, chemin_logo, width=Mm(25))
    return ""


def construire_evenements(sous_df):
    evenements = []
    for _, e in sous_df.iterrows():
        survenu = e["survenance_bin"] == 1
        occurrence = e.get("occurrence_num")
        duree = e.get("duree_indispo_min")
        evenements.append({
            "reference": e["reference"],
            "evenement": e["evenement"],
            "survenu": survenu,
            "statut_affiche": "Survenu ce mois-ci" if survenu else "Non survenu ce mois-ci",
            "motif": e["motif"] if pd.notna(e["motif"]) else "(non renseigné)",
            "statut": e["statut"] if pd.notna(e.get("statut")) else "(non renseigné)",
            "occurrence": int(occurrence) if pd.notna(occurrence) else "(non renseigné)",
            "duree": f"{int(duree)} min" if pd.notna(duree) else "(non renseignée)",
        })
    return evenements


def construire_recommandations(domaine, sous_df, score_valeur=None):
    survenus = sous_df[sous_df["survenance_bin"] == 1]
    if len(survenus) == 0:
        return f"Aucun événement significatif suivi sur {domaine} n'est survenu ce mois-ci."
    top = survenus.sort_values("occurrence_num", ascending=False).iloc[0]
    return (
        f"Sur le système {domaine}, l'événement {top['reference']} "
        f"({top['evenement']}) mérite une attention particulière ce mois-ci. "
        f"Il convient d'en analyser les causes et de suivre sa résolution."
    )


def _calculer_score_domaine(sous_df, mapping_df):
    """Meme logique de gravite que l'Etape 4, pour un sous-ensemble d'evenements."""
    df = sous_df.merge(mapping_df[["reference", "risque", "niveau"]], on="reference", how="left")
    df = df[~df["reference"].isin(EXCLUS)].copy()
    df["occurrence_finale"] = df["occurrence_num"]
    mask_texte = df["occurrence_finale"].isna() & (df["survenance_bin"] == 1)
    df.loc[mask_texte, "occurrence_finale"] = 1
    df["occurrence_finale"] = df["occurrence_finale"].fillna(0)
    df["poids_niveau"] = df["niveau"].map(POIDS_NIVEAU).fillna(1.5)
    df["gravite"] = calculer_gravite_evenement(df["survenance_bin"], df["occurrence_finale"], df["poids_niveau"])
    return round(df["gravite"].sum(), 1)


def generer_rapport_docx(fichier_source, evt_df, mapping_df, analyse_qualitative):
    from docxtpl import DocxTemplate

    sous_df = evt_df[evt_df["fichier_source"] == fichier_source]
    domaine = sous_df["domaine"].iloc[0]
    if domaine not in TEMPLATES or not os.path.exists(TEMPLATES[domaine]):
        return None, f"Aucun template disponible pour le système {domaine}."

    doc = DocxTemplate(TEMPLATES[domaine])

    # Score relatif (0-100) calcule sur TOUS les fichiers deja importes, pour
    # rester coherent avec l'interpretation du tableau de bord (meme reseau
    # avec plusieurs fichiers, ex. RESEAU ou SYSTAC Agence, compte une fois)
    scores_par_domaine = {}
    for domaine_calc in evt_df["domaine"].unique():
        if domaine_calc == "INCONNU":
            continue
        scores_par_domaine[domaine_calc] = _calculer_score_domaine(
            evt_df[evt_df["domaine"] == domaine_calc], mapping_df
        )
    total_brut = sum(scores_par_domaine.values())
    score_100_ce_domaine = (
        round(scores_par_domaine.get(domaine, 0) / total_brut * 100, 1) if total_brut > 0 else 0
    )

    df_score = sous_df.merge(mapping_df[["reference", "risque", "niveau"]], on="reference", how="left")
    df_score = df_score[~df_score["reference"].isin(EXCLUS)].copy()
    df_score["occurrence_finale"] = df_score["occurrence_num"]
    mask_texte = df_score["occurrence_finale"].isna() & (df_score["survenance_bin"] == 1)
    df_score.loc[mask_texte, "occurrence_finale"] = 1
    df_score["occurrence_finale"] = df_score["occurrence_finale"].fillna(0)
    df_score["poids_niveau"] = df_score["niveau"].map(POIDS_NIVEAU).fillna(1.5)
    df_score["gravite"] = calculer_gravite_evenement(df_score["survenance_bin"], df_score["occurrence_finale"], df_score["poids_niveau"])
    score_valeur = round(df_score["gravite"].sum(), 1)

    evenements = construire_evenements(sous_df)
    synthese = analyse_qualitative.get(domaine, {}).get("synthese_reseau")
    libelle_participant, mois_detecte, annee_detectee = identifier_participant_periode(sous_df)

    contexte = {
        "participant": libelle_participant,
        "fichier_source": fichier_source,
        "mois": mois_detecte, "annee": annee_detectee,
        "score_reseau": score_valeur,
        "interpretation": interpretation_absolue(score_valeur),
        "nb_total_evenements": len(evenements),
        "nb_evenements_survenus": sum(e["survenu"] for e in evenements),
        "evenements": evenements,
        "synthese": synthese,
        "recommandations": construire_recommandations(domaine, sous_df, score_valeur),
        "logo": inserer_logo(doc),
        "date_generation": date.today().strftime("%d/%m/%Y"),
    }
    doc.render(contexte)
    nettoyer_espacement(doc)

    os.makedirs("outputs/rapports", exist_ok=True)
    chemin_sortie = f"outputs/rapports/rapport_{os.path.splitext(fichier_source)[0]}.docx"
    doc.save(chemin_sortie)
    return chemin_sortie, None


def construire_graphique_comparatif(reseaux_ctx, doc):
    """Graphique en barres du score (%) par reseau, integre au rapport general."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from docxtpl import InlineImage
    from docx.shared import Mm

    domaines = [r["domaine"] for r in reseaux_ctx]
    scores = [r["score_100"] for r in reseaux_ctx]

    fig, ax = plt.subplots(figsize=(5.5, 3))
    ax.bar(domaines, scores, color="#0B2E59")
    ax.set_ylabel("Score (%)")
    ax.set_title("Comparaison du score par système")
    fig.tight_layout()

    os.makedirs("outputs", exist_ok=True)
    chemin_image = "outputs/graph_rapport_general_temp.png"
    fig.savefig(chemin_image, dpi=150)
    plt.close(fig)

    return InlineImage(doc, chemin_image, width=Mm(130))


def _tendances_generales(evt_df):
    """Texte de tendance, base sur l'historique si au moins 2 analyses existent."""
    try:
        from .historique import charger_historique
        from .statistiques import statistiques_mensuelles
    except Exception:
        return "Historique indisponible : tendances non calculées."

    historique = charger_historique()
    if len(historique) < 2:
        return (
            "Historique encore insuffisant pour dégager une tendance fiable "
            f"({len(historique)} analyse(s) enregistrée(s) à ce jour). Cette section "
            "s'enrichira automatiquement au fil des prochains imports, sans "
            "modification du rapport nécessaire."
        )
    stats = statistiques_mensuelles(historique)
    if len(stats) < 2:
        dernier = historique[0]
        precedent = historique[1]
        variation = dernier["score_obtenu"] - precedent["score_obtenu"]
        sens = "en hausse" if variation > 0 else "en baisse" if variation < 0 else "stable"
        return (
            f"Le score global est {sens} par rapport à l'analyse précédente "
            f"({precedent['score_obtenu']:.1f} → {dernier['score_obtenu']:.1f})."
        )
    premier_mois, dernier_mois = stats.iloc[0], stats.iloc[-1]
    sens = (
        "en hausse" if dernier_mois["score_moyen"] > premier_mois["score_moyen"]
        else "en baisse" if dernier_mois["score_moyen"] < premier_mois["score_moyen"]
        else "stable"
    )
    return (
        f"Sur {len(stats)} mois d'historique, le score moyen est {sens} "
        f"({premier_mois['score_moyen']:.1f} en {premier_mois['mois']} → "
        f"{dernier_mois['score_moyen']:.1f} en {dernier_mois['mois']})."
    )


def generer_rapport_general(evt_df, mapping_df, analyse_qualitative=None, plan_action=None):
    """
    Rapport general reduit au strict minimum : la liste des incidents
    SURVENUS et leurs caracteristiques, classes par pays puis par mois de
    survenance -- rien d'autre (pas de chapitres institutionnels, pas de
    synthese statistique, pas de section a completer). Pour le rapport
    complet, voir generer_rapport_activite().

    analyse_qualitative et plan_action ne sont plus utilises par ce
    rapport (conserves comme parametres pour compatibilite avec les
    appels existants).
    """
    from docxtpl import DocxTemplate

    chemin_template = chemin_ressource("templates/rapport_general.docx")
    if not os.path.exists(chemin_template):
        return None, "Le template templates/rapport_general.docx est introuvable."

    doc = DocxTemplate(chemin_template)

    # Incidents survenus de TOUS les pays, a plat (une ligne = un
    # incident), tries par pays puis par mois -- format compact en
    # tableau, pas un paragraphe par caracteristique comme avant, pour
    # tenir sur le moins de pages possible.
    survenus_complet = evt_df[
        (evt_df["survenance_bin"] == 1) & (~evt_df["reference"].isin(EXCLUS))
    ].drop_duplicates(subset=["reference", "fichier_source"]).copy()
    survenus_complet["pays"] = survenus_complet["pays"].fillna("INCONNU")
    survenus_complet["mois"] = survenus_complet["mois"].fillna("Non renseigné")
    survenus_complet = survenus_complet.sort_values(["pays", "mois", "domaine", "reference"])

    incidents_ctx = []
    for _, e in survenus_complet.iterrows():
        occurrence = e.get("occurrence_num")
        duree = e.get("duree_indispo_min")
        incidents_ctx.append({
            "pays": e["pays"], "mois": e["mois"], "domaine": e["domaine"],
            "reference": e["reference"], "evenement": e["evenement"],
            "motif": e["motif"] if pd.notna(e["motif"]) else "(non renseigné)",
            "statut": e["statut"] if pd.notna(e.get("statut")) else "(non renseigné)",
            "occurrence": int(occurrence) if pd.notna(occurrence) else "(non renseigné)",
            "duree": f"{int(duree)} min" if pd.notna(duree) else "(non renseignée)",
        })

    libelle_participant, mois_detecte, annee_detectee = identifier_participant_periode(evt_df)

    contexte = {
        "participant": libelle_participant,
        "mois": mois_detecte, "annee": annee_detectee,
        "incidents_ctx": incidents_ctx,
        "nb_incidents_total": len(incidents_ctx),
        "nb_pays": survenus_complet["pays"].nunique() if len(survenus_complet) else 0,
        "date_generation": date.today().strftime("%d/%m/%Y"),
    }
    doc.render(contexte)
    nettoyer_espacement(doc)

    os.makedirs("outputs/rapports", exist_ok=True)
    horodatage = date.today().strftime("%Y%m%d")
    chemin_sortie = f"outputs/rapports/rapport_general_{horodatage}.docx"
    doc.save(chemin_sortie)
    return chemin_sortie, None


# Categorisation du champ Statut des reportings (valeurs reellement
# observees dans les fichiers : R, ER, NR) vers les 3 categories utilisees
# dans le rapport d'activite.
LIBELLES_STATUT = {"R": "Résolu", "ER": "En cours", "NR": "Non résolu"}


def participants_attendus_par_pays():
    """
    Nombre de participants ATTENDUS par pays -- reglable par l'agent
    depuis Parametres (donnee institutionnelle, DAN ne peut pas la
    deduire des fichiers importes). Lu depuis la configuration
    persistee ; repli sur des valeurs illustratives
    si la configuration est absente ou vide.
    """
    from logic.configuration import charger_configuration
    config = charger_configuration()
    valeurs = config.get("participants_attendus") or {}
    return valeurs if valeurs else {
        "Cameroun": 10, "Congo": 10, "Tchad": 10,
        "Guinée Équatoriale": 10, "Gabon": 10, "Centrafrique": 10,
    }


def _compter_participants_recus_par_pays(evt_df):
    """
    Estime, pour chaque pays, le nombre de participants distincts ayant
    effectivement transmis un reporting dans le lot importe -- deduit du
    dossier immediatement parent de chaque fichier (arborescence
    Pays/MOIS X/Banque/fichier.xlsx), PAS d'un suivi par Code Banque (DAN
    ne classe plus les fichiers par participant, uniquement par pays).
    Cette estimation reste approximative si l'arborescence deposee ne suit
    pas exactement ce format a trois niveaux -- l'agent peut la corriger
    manuellement depuis Parametres si necessaire (voir
    participants_recus_effectifs).
    """
    resultat = {}
    if "fichier_source" not in evt_df.columns or "pays" not in evt_df.columns:
        return resultat
    sous = evt_df[["pays", "fichier_source"]].drop_duplicates()
    for pays, groupe in sous.groupby("pays"):
        participants = set()
        for chemin in groupe["fichier_source"]:
            segments = [s for s in str(chemin).replace("\\", "/").split("/")[:-1] if s]
            if segments:
                participants.add(segments[-1])  # dossier immediatement parent du fichier
            else:
                participants.add(chemin)  # fichier depose isolement : compte comme 1 participant
        resultat[pays] = len(participants)
    return resultat


def participants_recus_effectifs(evt_df):
    """
    Nombre de participants RECUS par pays a utiliser dans le rapport :
    la valeur saisie manuellement par l'agent (Parametres) est
    prioritaire si presente pour un pays donne, sinon DAN se rabat sur
    son estimation automatique (voir _compter_participants_recus_par_pays).
    """
    from logic.configuration import charger_configuration
    config = charger_configuration()
    manuel = config.get("participants_recus_manuel") or {}
    auto = _compter_participants_recus_par_pays(evt_df)
    resultat = dict(auto)
    for pays, valeur in manuel.items():
        if valeur is not None and str(valeur).strip() != "":
            resultat[pays] = int(valeur)
    return resultat


BLEU_FONCE = "#0B2E59"
OR_ACCENT = "#C9A227"
GRIS_CLAIR = "#CBD5E0"


def _graphique_statut_dysfonctionnements(analyse_pays_ctx):
    """
    Camembert de la repartition Resolu / En cours / Non resolu, calcule en
    sommant les colonnes correspondantes du tableau "1.2 Analyse des
    reportings" (analyse_pays_ctx) sur tous les pays -- une lecture directe
    de ce tableau, en complement du detail chiffre par pays qu'il fournit
    deja. Renvoie le chemin du fichier PNG genere, ou None si aucun
    dysfonctionnement n'est present (rien a repartir).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    total_resolu = sum(a["resolu"] for a in analyse_pays_ctx)
    total_en_cours = sum(a["en_cours"] for a in analyse_pays_ctx)
    total_non_resolu = sum(a["non_resolu"] for a in analyse_pays_ctx)
    total = total_resolu + total_en_cours + total_non_resolu
    if total == 0:
        return None

    libelles = ["Résolu", "En cours", "Non résolu"]
    valeurs = [total_resolu, total_en_cours, total_non_resolu]
    couleurs = ["#2F855A", OR_ACCENT, "#C53030"]
    # Ne garde que les tranches non nulles, pour un camembert lisible.
    libelles_non_nuls, valeurs_non_nulles, couleurs_non_nulles = zip(*[
        (l, v, c) for l, v, c in zip(libelles, valeurs, couleurs) if v > 0
    ])

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.pie(
        valeurs_non_nulles, labels=libelles_non_nuls, colors=couleurs_non_nulles,
        autopct=lambda pct: f"{pct:.0f}%\n({int(round(pct / 100 * total))})",
        startangle=90, textprops={"fontsize": 10},
    )
    ax.set_title(
        "Statut des dysfonctionnements (tous pays confondus)",
        fontsize=11, color=BLEU_FONCE, fontweight="bold",
    )
    fig.tight_layout()

    os.makedirs("outputs/rapports/_graphiques", exist_ok=True)
    chemin = f"outputs/rapports/_graphiques/statut_{datetime.now().strftime('%Y%m%d%H%M%S%f')}.png"
    fig.savefig(chemin, dpi=150)
    plt.close(fig)
    return chemin


def _graphique_comparaison_pays(taux_reponse_ctx):
    """
    Barres horizontales du taux de reponse (%) par pays pour la periode
    couverte par le rapport -- permet de voir en un coup d'oeil quels
    pays sont en retard, sans avoir a relire le tableau chiffre. Renvoie
    le chemin du fichier PNG genere, ou None si rien a tracer (aucun
    pays, ou uniquement la ligne TOTAL).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    lignes = [l for l in taux_reponse_ctx if l["pays"] != "TOTAL"]
    if not lignes:
        return None
    lignes = sorted(lignes, key=lambda l: l["pct"], reverse=True)
    pays = [l["pays"] for l in lignes]
    pct = [l["pct"] for l in lignes]
    couleurs = [OR_ACCENT if v == max(pct) else BLEU_FONCE for v in pct]

    fig, ax = plt.subplots(figsize=(6.5, max(2.2, 0.5 * len(pays))))
    barres = ax.barh(pays[::-1], pct[::-1], color=couleurs[::-1])
    ax.set_xlabel("Taux de réponse (%)")
    ax.set_xlim(0, max(100, max(pct) + 10))
    ax.set_title("Taux de réponse par pays", fontsize=11, color=BLEU_FONCE, fontweight="bold")
    for barre, valeur in zip(barres, pct[::-1]):
        ax.text(barre.get_width() + 1, barre.get_y() + barre.get_height() / 2,
                 f"{valeur} %", va="center", fontsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()

    os.makedirs("outputs/rapports/_graphiques", exist_ok=True)
    chemin = f"outputs/rapports/_graphiques/comparaison_{datetime.now().strftime('%Y%m%d%H%M%S%f')}.png"
    fig.savefig(chemin, dpi=150)
    plt.close(fig)
    return chemin


def _graphique_evolution_pays(evt_df, mapping_df):
    """
    Comparaison du score par mois, avec une courbe par pays -- calculee
    sur les DONNEES ACTUELLEMENT TRAITEES par le rapport (pas
    l'historique), pour rester coherente avec le graphique equivalent du
    Tableau de bord. Necessite au moins 2 mois presents dans les donnees
    pour etre pertinente (une seule courbe a un seul point n'apporte
    rien). Renvoie le chemin du fichier PNG genere, ou None si un seul
    mois est present.

    Les mois sont ordonnes chronologiquement (Janvier -> Decembre), pas
    alphabetiquement.
    """
    from logic.donnees import calculer_scores, MOIS_CANONIQUES

    if "mois" not in evt_df.columns:
        return None
    mois_presents = evt_df["mois"].dropna().unique()
    if len(mois_presents) < 2:
        return None

    a_plusieurs_pays = "pays" in evt_df.columns and evt_df["pays"].nunique() > 1
    colonnes_groupe = ["mois", "pays"] if a_plusieurs_pays else ["mois"]

    lignes = []
    for cles, groupe in evt_df.groupby(colonnes_groupe):
        cles = cles if isinstance(cles, tuple) else (cles,)
        df_gravite_mois = calculer_scores(groupe, mapping_df)
        ligne = dict(zip(colonnes_groupe, cles))
        ligne["score"] = round(df_gravite_mois["gravite"].sum(), 1)
        lignes.append(ligne)
    df_scores = pd.DataFrame(lignes)
    df_scores["ordre_mois"] = df_scores["mois"].apply(
        lambda m: MOIS_CANONIQUES.index(m) if m in MOIS_CANONIQUES else 99
    )
    df_scores = df_scores.sort_values("ordre_mois")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.5, 3.5))
    palette = [BLEU_FONCE, OR_ACCENT, "#2F855A", "#C05621", "#6B46C1", "#B83280"]
    if a_plusieurs_pays:
        for i, (pays, groupe) in enumerate(df_scores.groupby("pays")):
            groupe = groupe.sort_values("ordre_mois")
            ax.plot(groupe["mois"], groupe["score"], marker="o",
                    label=pays, color=palette[i % len(palette)], linewidth=2)
        ax.legend(loc="upper left", fontsize=8, ncol=2)
    else:
        ax.plot(df_scores["mois"], df_scores["score"], marker="o", color=BLEU_FONCE, linewidth=2)
    ax.set_ylabel("Score de gravité")
    ax.set_title("Comparaison des scores par mois", fontsize=11, color=BLEU_FONCE, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()

    os.makedirs("outputs/rapports/_graphiques", exist_ok=True)
    chemin = f"outputs/rapports/_graphiques/evolution_{datetime.now().strftime('%Y%m%d%H%M%S%f')}.png"
    fig.savefig(chemin, dpi=150)
    plt.close(fig)
    return chemin


def generer_rapport_activite(evt_df, mapping_df, analyse_qualitative=None):
    """
    Rapport d'activite de surveillance, suivant une structure de
    rapport d'activite institutionnel (page de garde, sommaire, Chapitre I
    identique au rapport general, Chapitre II reorganise autour des pays) :
      1.1 Taux de reponses par pays (Attendu fixe / Recu calcule / %)
      1.2 Analyse des reportings par pays (dysfonctionnements + statut)
      2, 3 : sections dependant de l'agent (controle sur place, autres
             activites), pre-remplies d'un texte a completer
      4, 5 : difficultes et remarques, adaptees au contenu reel calcule
    """
    from docxtpl import DocxTemplate, InlineImage
    from docx.shared import Mm

    chemin_template = chemin_ressource("templates/rapport_activite.docx")
    if not os.path.exists(chemin_template):
        return None, "Le template templates/rapport_activite.docx est introuvable."

    doc = DocxTemplate(chemin_template)

    # --- 1.1 Taux de reponses par pays -------------------------------
    attendus_par_pays = participants_attendus_par_pays()
    recus_par_pays = participants_recus_effectifs(evt_df)
    taux_reponse_ctx = []
    total_att, total_re = 0, 0
    for pays, attendu in attendus_par_pays.items():
        recu = recus_par_pays.get(pays, 0)
        pct = round(100 * recu / attendu, 1) if attendu > 0 else 0
        taux_reponse_ctx.append({"pays": pays, "attendu": attendu, "recu": recu, "pct": pct})
        total_att += attendu
        total_re += recu
    total_pct = round(100 * total_re / total_att, 1) if total_att > 0 else 0
    taux_reponse_ctx.append({"pays": "TOTAL", "attendu": total_att, "recu": total_re, "pct": total_pct})

    if total_pct < 30:
        appreciation = "demeure insignifiant"
    elif total_pct < 60:
        appreciation = "reste en deçà des attentes"
    else:
        appreciation = "est jugé satisfaisant"
    synthese_taux_reponse = (
        f"Au regard du tableau ci-dessus, le taux d'envoi des reportings dans l'ensemble "
        f"des pays {appreciation} ({total_pct} % de transmission globale, {total_re} "
        f"participant(s) sur {total_att} attendus)."
    )
    mesures_incitatrices = []
    if total_pct < 60:
        mesures_incitatrices = [
            "l'implication des instances nationales compétentes ;",
            "la mise en place de rencontres périodiques des participants par Direction Nationale ;",
            "la sensibilisation lors des contrôles sur place effectués sur les sites des participants ;",
            "la réflexion sur des astreintes, si cette tendance persiste.",
        ]

    # --- 1.2 Analyse des reportings par pays --------------------------
    survenus = evt_df[
        (evt_df["survenance_bin"] == 1) & (~evt_df["reference"].isin(EXCLUS))
    ].drop_duplicates(subset=["reference", "fichier_source"])
    total_dysfonctionnements = len(survenus)

    analyse_pays_ctx = []
    for pays in sorted(evt_df["pays"].fillna("INCONNU").unique()):
        sous_pays = survenus[survenus["pays"].fillna("INCONNU") == pays]
        nb = len(sous_pays)
        pct = round(100 * nb / total_dysfonctionnements, 1) if total_dysfonctionnements > 0 else 0
        compte_statut = {"Résolu": 0, "En cours": 0, "Non résolu": 0, "Non renseigné": 0}
        for statut_brut in sous_pays.get("statut", pd.Series(dtype=object)):
            libelle = LIBELLES_STATUT.get(str(statut_brut).strip().upper(), "Non renseigné") if pd.notna(statut_brut) else "Non renseigné"
            compte_statut[libelle] = compte_statut.get(libelle, 0) + 1
        analyse_pays_ctx.append({
            "pays": pays, "nb": nb, "pct": pct,
            "resolu": compte_statut["Résolu"], "en_cours": compte_statut["En cours"],
            "non_resolu": compte_statut["Non résolu"] + compte_statut["Non renseigné"],
        })
    analyse_pays_ctx.sort(key=lambda a: a["nb"], reverse=True)

    if total_dysfonctionnements > 0:
        phrases = [f"{a['pct']} % concernent {a['pays']}" for a in analyse_pays_ctx if a["nb"] > 0]
        synthese_dysfonctionnements = (
            f"L'analyse des reportings reçus révèle un total de {total_dysfonctionnements} "
            f"dysfonctionnement(s) ce mois-ci : " + ", ".join(phrases) + "."
        )
    else:
        synthese_dysfonctionnements = (
            "Aucun dysfonctionnement n'a été relevé sur l'ensemble des pays ayant transmis ce mois-ci."
        )

    graphique_statut = None
    explication_statut = ""
    chemin_statut = _graphique_statut_dysfonctionnements(analyse_pays_ctx)
    if chemin_statut:
        graphique_statut = InlineImage(doc, chemin_statut, width=Mm(110))
        part_resolu = round(
            100 * sum(a["resolu"] for a in analyse_pays_ctx) / total_dysfonctionnements, 1
        ) if total_dysfonctionnements > 0 else 0
        explication_statut = (
            f"Ce graphique illustre la répartition des {total_dysfonctionnements} "
            f"dysfonctionnements du tableau ci-dessus selon leur statut de résolution — "
            f"{part_resolu} % sont actuellement résolus."
        )
    else:
        explication_statut = "Graphique non disponible : aucun dysfonctionnement à répartir ce mois-ci."

    # --- 4. Difficultes (reelles, calculees par DAN) ------------------
    difficultes = []
    if mapping_df is not None and "confiance" in mapping_df.columns:
        nb_faible_confiance = int((mapping_df["confiance"] == "Faible").sum())
        if nb_faible_confiance > 0:
            difficultes.append(
                f"{nb_faible_confiance} événement(s) du référentiel reposent encore sur une "
                f"correspondance de risque à confiance faible, en attente de validation par l'équipe de surveillance."
            )
    if total_pct < 100:
        difficultes.append(
            f"Le taux de transmission des reportings demeure incomplet ({total_pct} %) : "
            f"l'analyse ne couvre que les participants ayant effectivement transmis."
        )

    # --- 5. Remarques (adaptees au taux reellement calcule) -----------
    remarques_activite = (
        f"Tiré d'un taux de {total_pct} % de transmission globale des reportings, cette "
        f"analyse " + (
            "reflète une image encore partielle du comportement des plateformes des "
            "systèmes de paiement, mais permet néanmoins de dégager une tendance générale."
            if total_pct < 100 else
            "reflète une image complète du comportement des plateformes des systèmes de "
            "paiement pour les participants suivis ce mois-ci."
        )
    )

    libelle_participant, mois_detecte, annee_detectee = identifier_participant_periode(evt_df)

    # --- Graphiques (comparaison + evolution) --------------------------
    graphique_comparaison = None
    explication_comparaison = ""
    chemin_comparaison = _graphique_comparaison_pays(taux_reponse_ctx)
    if chemin_comparaison:
        graphique_comparaison = InlineImage(doc, chemin_comparaison, width=Mm(150))
        pays_tries = sorted(
            [l for l in taux_reponse_ctx if l["pays"] != "TOTAL"],
            key=lambda l: l["pct"], reverse=True,
        )
        meilleur = pays_tries[0] if pays_tries else None
        moins_bon = pays_tries[-1] if pays_tries else None
        if meilleur and moins_bon and meilleur["pays"] != moins_bon["pays"]:
            explication_comparaison = (
                f"Ce graphique compare le taux de réponse de chaque pays pour la période. "
                f"{meilleur['pays']} affiche le meilleur taux ({meilleur['pct']} %), tandis que "
                f"{moins_bon['pays']} accuse le plus grand retard ({moins_bon['pct']} %)."
            )
        else:
            explication_comparaison = (
                "Ce graphique compare le taux de réponse de chaque pays pour la période."
            )

    graphique_evolution = None
    explication_evolution = ""
    chemin_evolution = _graphique_evolution_pays(evt_df, mapping_df)
    if chemin_evolution:
        graphique_evolution = InlineImage(doc, chemin_evolution, width=Mm(150))
        explication_evolution = (
            "Ce graphique compare le score de gravité de chaque mois couvert par ce lot"
            + (", pays par pays" if evt_df["pays"].nunique() > 1 else "")
            + " — les mois sont classés chronologiquement. Une hausse marque une "
            "dégradation de la situation, une baisse une amélioration."
        )
    else:
        explication_evolution = (
            "Graphique non disponible : les données couvrent un seul mois pour ce lot."
        )

    contexte = {
        "participant": libelle_participant,
        "mois": mois_detecte, "annee": annee_detectee,
        "taux_reponse_ctx": taux_reponse_ctx,
        "synthese_taux_reponse": synthese_taux_reponse,
        "mesures_incitatrices": mesures_incitatrices,
        "analyse_pays_ctx": analyse_pays_ctx,
        "synthese_dysfonctionnements": synthese_dysfonctionnements,
        "graphique_statut": graphique_statut,
        "explication_statut": explication_statut,
        "difficultes": difficultes,
        "remarques_activite": remarques_activite,
        "graphique_comparaison": graphique_comparaison,
        "explication_comparaison": explication_comparaison,
        "graphique_evolution": graphique_evolution,
        "explication_evolution": explication_evolution,
        "date_generation": date.today().strftime("%d/%m/%Y"),
    }
    doc.render(contexte)
    nettoyer_espacement(doc)

    os.makedirs("outputs/rapports", exist_ok=True)
    horodatage = date.today().strftime("%Y%m%d")
    chemin_sortie = f"outputs/rapports/rapport_activite_{horodatage}.docx"
    doc.save(chemin_sortie)

    for chemin_temp in (chemin_comparaison, chemin_evolution):
        if chemin_temp and os.path.exists(chemin_temp):
            try:
                os.remove(chemin_temp)
            except OSError:
                pass

    return chemin_sortie, None


def generer_pdf_natif(chemin_docx):
    """
    Genere un PDF directement en Python pur (bibliotheque reportlab), sans
    dependre de Microsoft Word ni de LibreOffice installes sur la machine.

    Contrairement a weasyprint (envisage puis ecarte), reportlab ne
    necessite AUCUNE bibliotheque systeme externe (pas de GTK/Pango/Cairo)
    -- crucial sur Windows, ou l'installation de weasyprint suppose sinon
    d'installer separement le runtime GTK3, remplacant un probleme de
    dependance par un autre.

    Le rendu n'est pas pixel-parfait (pas de filigrane, mise en page
    simplifiee) mais produit un VRAI fichier PDF telechargeable et
    imprimable, sur n'importe quelle machine, sans rien installer de plus.
    """
    from docx import Document
    from docx.oxml.ns import qn
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
        Image as RLImage,
    )

    chemin_pdf = chemin_docx.replace(".docx", ".pdf")
    doc_source = Document(chemin_docx)

    styles = getSampleStyleSheet()
    style_titre1 = ParagraphStyle("Titre1DAN", parent=styles["Heading1"],
                                   textColor=colors.HexColor("#0B2E59"), spaceBefore=16, spaceAfter=8)
    style_titre2 = ParagraphStyle("Titre2DAN", parent=styles["Heading2"],
                                   textColor=colors.HexColor("#0B2E59"), spaceBefore=12, spaceAfter=6)
    style_titre3 = ParagraphStyle("Titre3DAN", parent=styles["Heading3"], spaceBefore=10, spaceAfter=4)
    style_normal = ParagraphStyle("NormalDAN", parent=styles["Normal"], fontSize=10, leading=14, spaceAfter=4)
    style_puce = ParagraphStyle("PuceDAN", parent=style_normal, leftIndent=14)

    elements = []
    corps = doc_source.element.body
    map_paragraphes = {p._p: p for p in doc_source.paragraphs}
    map_tableaux = {t._tbl: t for t in doc_source.tables}

    def echapper(texte):
        return (texte.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    for enfant in corps.iterchildren():
        if enfant.tag == qn("w:p") and enfant in map_paragraphes:
            p = map_paragraphes[enfant]

            # Meme precaution que dans generer_apercu_html : un paragraphe
            # porteur d'une image (logo, graphique) a un texte vide -- ce
            # n'est pas un paragraphe a ignorer. Sans ce traitement, le
            # PDF genere nativement (repli sans Word ni LibreOffice)
            # omettait silencieusement toutes les images pourtant
            # presentes dans le document Word exporte.
            octets_image = _extraire_octets_image(p, doc_source)
            if octets_image is not None:
                try:
                    largeur_page = A4[0] - 2 * 2 * cm
                    tampon_image = io.BytesIO(octets_image)
                    img = ImageReader(tampon_image)
                    largeur_native, hauteur_native = img.getSize()
                    largeur_cible = min(largeur_page, largeur_native)
                    hauteur_cible = largeur_cible * (hauteur_native / largeur_native)
                    tampon_image.seek(0)
                    elements.append(Spacer(1, 6))
                    elements.append(RLImage(tampon_image, width=largeur_cible, height=hauteur_cible))
                    elements.append(Spacer(1, 6))
                except Exception:
                    pass
                continue

            texte = p.text.strip()
            if not texte:
                continue
            texte_echappe = echapper(texte)
            nom_style = (p.style.name or "").lower()
            try:
                if "heading 1" in nom_style or "titre 1" in nom_style:
                    elements.append(Paragraph(texte_echappe, style_titre1))
                elif "heading 2" in nom_style or "titre 2" in nom_style:
                    elements.append(Paragraph(texte_echappe, style_titre2))
                elif "heading 3" in nom_style or "titre 3" in nom_style:
                    elements.append(Paragraph(texte_echappe, style_titre3))
                elif "list bullet" in nom_style or "liste" in nom_style:
                    elements.append(Paragraph(f"•  {texte_echappe}", style_puce))
                else:
                    gras = any(r.bold for r in p.runs) if p.runs else False
                    contenu = f"<b>{texte_echappe}</b>" if gras and len(texte) < 120 else texte_echappe
                    elements.append(Paragraph(contenu, style_normal))
            except Exception:
                # Un caractere ou une balise imprevue ne doit pas faire
                # echouer tout le document -- on saute la ligne fautive.
                continue
        elif enfant.tag == qn("w:tbl") and enfant in map_tableaux:
            t = map_tableaux[enfant]
            donnees = [[Paragraph(echapper(cell.text.strip()), style_normal) for cell in row.cells]
                       for row in t.rows]
            if not donnees:
                continue
            try:
                largeur_page = A4[0] - 2 * 2 * cm
                nb_col = len(donnees[0])
                tableau_pdf = Table(donnees, colWidths=[largeur_page / nb_col] * nb_col, repeatRows=1)
                tableau_pdf.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B2E59")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ]))
                elements.append(Spacer(1, 6))
                elements.append(tableau_pdf)
                elements.append(Spacer(1, 6))
            except Exception:
                continue

    if not elements:
        return None

    doc_pdf = SimpleDocTemplate(
        chemin_pdf, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
        title="Rapport DAN",
    )
    doc_pdf.build(elements)
    return chemin_pdf if os.path.exists(chemin_pdf) else None


def convertir_en_pdf(chemin_docx):
    chemin_pdf = chemin_docx.replace(".docx", ".pdf")
    try:
        from docx2pdf import convert
        convert(chemin_docx, chemin_pdf)
        if os.path.exists(chemin_pdf):
            return chemin_pdf
    except Exception:
        pass
    try:
        dossier = os.path.dirname(chemin_docx)
        subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", "--outdir", dossier, chemin_docx],
            check=True, capture_output=True, timeout=60,
        )
        if os.path.exists(chemin_pdf):
            return chemin_pdf
    except Exception:
        pass
    # Repli garanti : generation PDF en Python pur, sans dependance
    # systeme externe -- fonctionne sur n'importe quelle machine, y
    # compris Windows sans Word ni LibreOffice installes.
    try:
        chemin_natif = generer_pdf_natif(chemin_docx)
        if chemin_natif:
            return chemin_natif
    except Exception:
        pass
    return None


def afficher_pdf_inline(chemin_pdf):
    import streamlit as st
    with open(chemin_pdf, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode("utf-8")
    iframe = (
        f'<iframe src="data:application/pdf;base64,{base64_pdf}" '
        f'width="100%" height="750" type="application/pdf"></iframe>'
    )
    st.markdown(iframe, unsafe_allow_html=True)


def generer_apercu_html(chemin_docx):
    """
    Apercu du contenu d'un rapport Word SANS dependre d'une application
    externe (Microsoft Word ou LibreOffice), contrairement a convertir_en_pdf.
    Reconstruit le corps du document -- paragraphes, titres, tableaux, dans
    leur ORDRE reel d'apparition -- sous forme de HTML affichable directement
    dans la page. Ce n'est pas un rendu pixel-parfait (pas de page de garde,
    pas de pagination, pas de filigrane) mais cela garantit qu'un apercu du
    contenu reste TOUJOURS disponible, quelle que soit la machine.
    """
    from docx import Document
    from docx.oxml.ns import qn

    doc = Document(chemin_docx)
    morceaux = ['<div style="font-family:Calibri,Arial,sans-serif;font-size:15px;'
                'line-height:1.5;color:#1a202c;max-width:850px;margin:auto;">']

    # Parcours des elements du corps dans l'ordre reel du document (python-docx
    # expose separement .paragraphs et .tables, sans ordre combine -- il faut
    # donc reparcourir l'arbre XML brut pour respecter l'ordre d'apparition).
    corps = doc.element.body
    map_paragraphes = {p._p: p for p in doc.paragraphs}
    map_tableaux = {t._tbl: t for t in doc.tables}

    for enfant in corps.iterchildren():
        if enfant.tag == qn("w:p") and enfant in map_paragraphes:
            p = map_paragraphes[enfant]
            texte = p.text.strip()

            # Un paragraphe contenant une IMAGE (logo, graphique) a un texte
            # vide -- ce n'est PAS un paragraphe vide a ignorer. Sans ce test,
            # l'apercu HTML omettait silencieusement tout logo et tout
            # graphique pourtant bien presents dans le document exporte,
            # produisant un apercu incomplet par rapport au fichier reel.
            image_b64 = _extraire_premiere_image_base64(p, doc)
            if image_b64:
                morceaux.append(
                    f'<img src="data:image/png;base64,{image_b64}" '
                    f'style="max-width:100%;margin:10px 0;" alt="Graphique du rapport">'
                )
                continue

            if not texte:
                continue
            nom_style = (p.style.name or "").lower()
            if "heading 1" in nom_style or "titre 1" in nom_style:
                morceaux.append(f'<h2 style="color:#0B2E59;margin-top:28px;">{texte}</h2>')
            elif "heading 2" in nom_style or "titre 2" in nom_style:
                morceaux.append(f'<h3 style="color:#0B2E59;margin-top:20px;">{texte}</h3>')
            elif "heading 3" in nom_style or "titre 3" in nom_style:
                morceaux.append(f'<h4 style="color:#1A202C;margin-top:16px;">{texte}</h4>')
            elif "list bullet" in nom_style or "liste" in nom_style:
                morceaux.append(f'<p style="margin:3px 0 3px 20px;">• {texte}</p>')
            else:
                gras_ouvert = any(r.bold for r in p.runs) if p.runs else False
                style_txt = "font-weight:600;" if gras_ouvert and len(texte) < 120 else ""
                morceaux.append(f'<p style="{style_txt}margin:6px 0;">{texte}</p>')
        elif enfant.tag == qn("w:tbl") and enfant in map_tableaux:
            t = map_tableaux[enfant]
            morceaux.append('<table style="border-collapse:collapse;width:100%;margin:12px 0;">')
            for i, row in enumerate(t.rows):
                morceaux.append("<tr>")
                for cell in row.cells:
                    balise = "th" if i == 0 else "td"
                    fond = "#0B2E59" if i == 0 else "#FFFFFF"
                    couleur = "#FFFFFF" if i == 0 else "#1A202C"
                    morceaux.append(
                        f'<{balise} style="border:1px solid #CBD5E0;padding:6px 10px;'
                        f'background:{fond};color:{couleur};text-align:left;font-size:13.5px;">'
                        f'{cell.text.strip()}</{balise}>'
                    )
                morceaux.append("</tr>")
            morceaux.append("</table>")

    morceaux.append("</div>")
    return "\n".join(morceaux)


def _extraire_octets_image(paragraphe, doc):
    """
    Extrait les octets bruts de la premiere image (logo ou graphique)
    trouvee dans un paragraphe -- None si le paragraphe n'en contient pas.
    Fonction commune utilisee par generer_apercu_html() (apercu HTML) ET
    generer_pdf_natif() (repli PDF sans Word ni LibreOffice), pour que les
    DEUX mecanismes de secours affichent vraiment les memes images que le
    document Word exporte, plutot que de les omettre silencieusement (leur
    paragraphe a un texte vide, a ne pas confondre avec un paragraphe
    reellement vide).
    """
    from docx.oxml.ns import qn

    blips = paragraphe._element.findall(f".//{qn('w:drawing')}//{qn('a:blip')}")
    if not blips:
        return None
    id_relation = blips[0].get(qn("r:embed"))
    if not id_relation:
        return None
    try:
        partie_image = doc.part.related_parts[id_relation]
        return partie_image.blob
    except (KeyError, AttributeError):
        return None


def _extraire_premiere_image_base64(paragraphe, doc):
    """
    Version base64 de _extraire_octets_image(), pour l'apercu HTML
    (generer_apercu_html) qui a besoin d'une chaine encodable dans un
    attribut src="data:image/...;base64,...".
    """
    octets = _extraire_octets_image(paragraphe, doc)
    if octets is None:
        return None
    return base64.b64encode(octets).decode("utf-8")
