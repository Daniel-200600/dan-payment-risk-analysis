# -*- coding: utf-8 -*-
"""
DAN - Logique metier : lecture des reportings et calcul du score de risque.
AUCUN changement de calcul par rapport aux Etapes 3 et 4 -- uniquement
deplace ici pour separer la logique de l'affichage (Streamlit).
"""
import pandas as pd
import os
import io
import streamlit as st

POIDS_NIVEAU = {
    "Critique": 4, "Majeur": 3, "Sensible": 2, "Faible": 1,
    "A valider": 1.5, "À valider": 1.5,
}
EXCLUS = {"RPSYSPA09"}
COLS = [
    "reference", "evenement", "survenance", "occurrence",
    "motif", "statut", "duree_indispo_min", "commentaire",
]


def poids_occurrence(occurrence):
    """
    Lissage logarithmique de la contribution du nombre d'occurrences a la
    gravite. Avant : poids = 1 + occurrence (lineaire) -- un evenement a
    200 occurrences pesait 200x plus qu'un evenement isole, ecrasant tout
    le reste du score a lui seul (cas reel observe : echange bilateral
    SYSTAC a 124/106 occurrences). Desormais : poids = 1 + ln(1+occurrence)
    -- rendements decroissants au-dela d'une poignee d'occurrences, sans
    plafond dur (pas d'effet de seuil arbitraire). Inchange pour
    occurrence=0 (poids=1, comme avant).

    Fonctionne aussi bien sur une valeur seule (float/int) que sur une
    colonne entiere (pandas Series) -- utilise numpy pour cette raison,
    pas le module math qui ne supporte que les scalaires.
    """
    import numpy as np
    occurrence = np.maximum(0, np.nan_to_num(occurrence, nan=0.0))
    return 1 + np.log1p(occurrence)


def calculer_gravite_evenement(survenance_bin, occurrence_finale, poids_niveau):
    """Point de calcul UNIQUE de la gravite d'un evenement -- reutilise par
    calculer_scores() et par la generation de rapports (logic/rapports.py,
    ) pour garantir un score identique partout dans DAN."""
    return survenance_bin * poids_occurrence(occurrence_finale) * poids_niveau


import re
from collections import Counter

CODES_DOMAINE = {"SYG": "SYGMA", "SWI": "SWIFT", "SYS": "SYSTAC", "RES": "RESEAU"}
MOTIF_REFERENCE = re.compile(r"^RP(SYG|SWI|SYS|RES)([A-Z]{2})\d{2}")


def detecter_domaine_site_par_contenu(references):
    """
    Detecte le reseau et le site a partir du CONTENU des references
    (colonne REFERENCE), et non du nom de fichier. La convention de
    codification RP[domaine 3L][site 2L][numero 2 chiffres] (ex:
    RPSYSPA01) est appliquee de facon homogene par tous les participants
    -- cette detection reste donc fiable meme si le fichier est renomme,
    contrairement a une detection fondee sur le nom de fichier.

    Utilise un vote majoritaire sur l'ensemble des references du fichier
    pour rester robuste a une eventuelle ligne mal formee. Renvoie
    (domaine, site, confiance) ; (None, None, 0.0) si aucune reference
    exploitable n'a ete trouvee dans le fichier.
    """
    domaines_trouves, sites_trouves = [], []
    for ref in references:
        m = MOTIF_REFERENCE.match(str(ref).strip().upper())
        if m:
            domaines_trouves.append(CODES_DOMAINE[m.group(1)])
            sites_trouves.append(m.group(2))
    if not domaines_trouves:
        return None, None, 0.0

    domaine_maj, n_domaine = Counter(domaines_trouves).most_common(1)[0]
    site_maj, _ = Counter(sites_trouves).most_common(1)[0]
    confiance = round(n_domaine / len(domaines_trouves), 3)
    return domaine_maj, site_maj, confiance


def detecter_domaine_site_repli(nom_fichier):
    """
    Repli sur le nom de fichier, utilise UNIQUEMENT si aucune reference
    exploitable n'a ete trouvee dans le contenu (fichier au format
    inhabituel). Moins fiable qu'une detection par contenu -- conserve
    ici pour ne jamais bloquer un import, avec un signalement explicite
    a l'utilisateur (voir lire_reporting).
    """
    nom = nom_fichier.upper()
    if "SYGMA" in nom:
        domaine = "SYGMA"
    elif "SWIFT" in nom:
        domaine = "SWIFT"
    elif "SYSTAC" in nom:
        domaine = "SYSTAC"
    elif "RESEAU" in nom:
        domaine = "RESEAU"
    else:
        domaine = "INCONNU"
    site = "PA" if "AGENCE" in nom else "PS"
    return domaine, site


import unicodedata


def _normaliser(texte):
    """Majuscules, sans accents, espaces superflus retires -- pour comparer
    des libelles d'en-tete de facon tolerante (ex: 'Référence', 'REFERENCE ',
    'reference' sont tous reconnus comme equivalents)."""
    texte = str(texte).strip().upper()
    texte = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode("ascii")
    return texte


LIBELLES_PERIODE = {"ANNEE": "annee", "MOIS": "mois"}


# Les six pays membres de la CEMAC -- ensemble fixe, ne necessitant aucune
# liste de reference a maintenir ou a televerser. Definis ici (et non dans
# logic.participants) pour eviter un import circulaire : c'est ici, au
# moment de la lecture des fichiers, que le pays est normalise.
PAYS_CEMAC = ["Cameroun", "Centrafrique", "Congo", "Gabon", "Guinée Équatoriale", "Tchad"]

# Alias reconnus par pays (cle = forme normalisee via _normaliser : majuscules,
# sans accents, espaces simples) -- couvre les variantes de casse, les sigles
# usuels et quelques variantes orthographiques courantes. Le nom de dossier
# n'a donc pas besoin de suivre une orthographe precise : CAMEROUN, Cameroun,
# CMR et cmr designent tous le meme pays.
_ALIAS_PAYS = {
    "CAMEROUN": "Cameroun", "CAMEROON": "Cameroun", "CMR": "Cameroun", "CM": "Cameroun",
    "CENTRAFRIQUE": "Centrafrique", "CENTRAFRICAINE": "Centrafrique",
    "REPUBLIQUE CENTRAFRICAINE": "Centrafrique", "RCA": "Centrafrique", "CAF": "Centrafrique",
    "CENTRAL AFRICAN REPUBLIC": "Centrafrique",
    "CONGO": "Congo", "REPUBLIQUE DU CONGO": "Congo", "CONGO BRAZZAVILLE": "Congo",
    "COG": "Congo", "CG": "Congo",
    "GABON": "Gabon", "GAB": "Gabon", "GA": "Gabon",
    "GUINEE EQUATORIALE": "Guinée Équatoriale", "GUINEE-EQUATORIALE": "Guinée Équatoriale",
    "EQUATORIAL GUINEA": "Guinée Équatoriale", "GUINEA ECUATORIAL": "Guinée Équatoriale",
    "GNQ": "Guinée Équatoriale", "GQ": "Guinée Équatoriale",
    "TCHAD": "Tchad", "CHAD": "Tchad", "TCD": "Tchad", "TD": "Tchad",
}


def normaliser_pays(valeur_brute):
    """
    Ramene une valeur de pays quelconque (nom de dossier, casse et accents
    variables, sigle usuel...) a la forme canonique utilisee dans
    PAYS_CEMAC -- DAN ne doit pas s'attarder sur la forme exacte des
    caracteres : CAMEROUN, Cameroun, CMR et cmr designent tous "Cameroun".

    Si la valeur ne correspond a aucun alias connu, elle est renvoyee telle
    quelle (nettoyee des espaces superflus) plutot que rejetee -- un nom de
    dossier qui ne correspond a aucun des six pays CEMAC reste visible tel
    quel, DAN ne masque jamais une information qu'il ne reconnait pas.
    """
    if not valeur_brute:
        return valeur_brute
    cle = _normaliser(valeur_brute)
    return _ALIAS_PAYS.get(cle, str(valeur_brute).strip())


# Les 12 mois, sous leur forme canonique (utilisee partout dans DAN --
# tableau de bord, rapports, analyse des risques). Alias reconnus : nom
# complet (accents/casse variables), abreviations usuelles a 3-4 lettres,
# et numero (1-12 ou 01-12) -- DAN ne doit pas s'attarder sur la forme
# exacte : janvier = JANVIER = Janv = 1 = 01 designent tous "Janvier".
MOIS_CANONIQUES = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]
_ALIAS_MOIS = {}
for _i, _nom in enumerate(MOIS_CANONIQUES, start=1):
    for _forme in (_nom, str(_i), f"{_i:02d}", _nom[:3], _nom[:4]):
        _ALIAS_MOIS[_normaliser(_forme)] = _nom
# Quelques abreviations usuelles supplementaires qui ne sont pas de simples
# troncatures a 3-4 lettres du nom complet.
_ALIAS_MOIS.update({
    "JUIL": "Juillet", "SEPT": "Septembre", "AOUT": "Août", "DEC": "Décembre",
})


def normaliser_mois(valeur_brute):
    """
    Ramene une valeur de mois quelconque (nom en toutes lettres, casse et
    accents variables, abreviation, numero 1-12...) a la forme canonique
    utilisee dans DAN -- janvier, JANVIER, Janv et 1 designent tous
    "Janvier". Renvoie la valeur d'origine (nettoyee) si elle ne
    correspond a aucun mois reconnu.
    """
    if not valeur_brute:
        return valeur_brute
    cle = _normaliser(valeur_brute)
    return _ALIAS_MOIS.get(cle, str(valeur_brute).strip())


import re as _re
_MOTIF_ANNEE = _re.compile(r"\b(20\d{2})\b")


def _deduire_mois_annee_dossier(segments):
    """
    Recherche un mois et une annee dans les segments du chemin d'un
    fichier depose (dossier(s) parcourus lors d'un depot de dossier natif)
    -- DAN doit lire le mois depuis l'organisation reelle des dossiers
    (ex. "MOIS JANVIER 2026"), pas l'inventer ou dependre uniquement du
    contenu du fichier, souvent incomplet sur ce point.

    Parcourt chaque segment, en cherchant un des mots qu'il contient qui
    corresponde a un mois connu (voir normaliser_mois) et un nombre a 4
    chiffres commençant par 20 pour l'annee. Renvoie (mois, annee), l'un
    ou l'autre pouvant etre None si non trouve.
    """
    mois_trouve, annee_trouvee = None, None
    for segment in segments:
        if annee_trouvee is None:
            correspondance_annee = _MOTIF_ANNEE.search(segment)
            if correspondance_annee:
                annee_trouvee = correspondance_annee.group(1)
        if mois_trouve is None:
            for mot in _re.split(r"[\s\-_/]+", segment):
                candidat = normaliser_mois(mot)
                if candidat in MOIS_CANONIQUES:
                    mois_trouve = candidat
                    break
    return mois_trouve, annee_trouvee


def extraire_periode(df, lignes_max=20, colonnes_max=10):
    """
    Recherche, dans les premieres lignes/colonnes du fichier, l'Annee et
    le Mois du reporting (bloc present de facon coherente dans les
    fichiers reels observes). La valeur est cherchee dans la cellule
    immediatement a droite du libelle. Renvoie un dict avec des valeurs
    None si non trouvees (fichier plus ancien ou gabarit incomplet).

    Ne cherche plus le Code Banque / Code Agence : DAN ne classe plus les
    fichiers par participant mais par pays, deduit du nom du dossier qui
    contient le fichier lors d'un depot de dossier entier (voir
    _deduire_pays) -- une information de classement externe au contenu
    du fichier, pas a en extraire.
    """
    resultat = {v: None for v in LIBELLES_PERIODE.values()}
    limite_lignes = min(lignes_max, len(df))
    limite_colonnes = min(colonnes_max, len(df.columns))
    for i in range(limite_lignes):
        for j in range(limite_colonnes):
            valeur = df.iat[i, j]
            if pd.isna(valeur):
                continue
            libelle_normalise = _normaliser(valeur)
            if libelle_normalise in LIBELLES_PERIODE and j + 1 < df.shape[1]:
                cle = LIBELLES_PERIODE[libelle_normalise]
                if resultat[cle] is None:
                    val_brute = df.iat[i, j + 1]
                    resultat[cle] = None if pd.isna(val_brute) else str(val_brute).strip()
    if resultat.get("mois"):
        resultat["mois"] = normaliser_mois(resultat["mois"])
    return resultat


def localiser_entete(df, lignes_max=40, colonnes_max=12):
    """
    Recherche la cellule d'en-tete 'REFERENCE' dans les premieres lignes et
    colonnes du fichier, de facon tolerante (accents, casse, espaces). Ne
    suppose plus que cette cellule est necessairement en colonne 0 -- un
    fichier avec une colonne supplementaire en tete (numero de ligne,
    colonne vide, etc.) reste ainsi lisible.

    Renvoie (ligne_entete, colonne_entete) ou (None, None) si introuvable.
    """
    limite_lignes = min(lignes_max, len(df))
    limite_colonnes = min(colonnes_max, len(df.columns))
    for i in range(limite_lignes):
        for j in range(limite_colonnes):
            valeur = df.iat[i, j]
            if pd.notna(valeur) and _normaliser(valeur) == "REFERENCE":
                return i, j
    return None, None


def _apercu_premieres_lignes(df, n=5):
    """Petit resume textuel des premieres cellules non vides du fichier,
    utilise dans le message d'erreur pour aider a diagnostiquer un fichier
    dont l'en-tete REFERENCE n'a pas ete trouve."""
    extraits = []
    for i in range(min(n, len(df))):
        valeurs = [str(v) for v in df.iloc[i].tolist()[:6] if pd.notna(v)]
        if valeurs:
            extraits.append(f"  ligne {i} : " + " | ".join(valeurs))
    return "\n".join(extraits) if extraits else "  (aucune cellule non vide trouvée dans les premières lignes)"


class FichierReportingInvalide(Exception):
    """Levee quand la colonne REFERENCE n'a pas pu etre localisee dans le
    fichier depose, avec un apercu du contenu pour faciliter le diagnostic."""
    pass


EXTENSIONS_RECONNUES = (".xlsx", ".xls")


def _segments_chemin(fichier_uploade):
    """Segments du chemin relatif d'un fichier depose en mode dossier
    natif (Streamlit), hors nom du fichier lui-meme. Liste vide si le
    fichier a ete depose isolement (sans dossier parent)."""
    nom = getattr(fichier_uploade, "name", "") or ""
    nom_normalise = nom.replace("\\", "/")
    return [s.strip() for s in nom_normalise.split("/")[:-1] if s.strip()]


def _deduire_pays(segments):
    """
    Determine le pays a partir des segments du chemin d'un fichier
    depose en mode dossier natif de Streamlit -- "INCONNU" si le fichier
    a ete depose isolement (segments vide).

    Parcourt TOUS les segments (pas seulement le premier) a la recherche
    d'un nom de pays reconnu (voir normaliser_pays) : le dossier choisi
    lors du depot peut aussi bien etre un dossier de pays directement
    (Cameroun/Banque_A/...) qu'un grand dossier englobant plusieurs pays
    (Referentiels/CAMEROUN/MOIS MARS 2026/BANQUE_A/...) -- dans les deux
    cas, c'est le premier segment qui correspond a un pays de la CEMAC
    qui est retenu, quelle que soit sa position dans le chemin. Si aucun
    segment ne correspond a un pays connu, on se rabat sur le tout
    premier segment, pour ne pas perdre une information de classement
    meme non reconnue.
    """
    if not segments:
        return "INCONNU"

    for segment in segments:
        candidat = normaliser_pays(segment)
        if candidat in PAYS_CEMAC:
            return candidat

    return normaliser_pays(segments[0])


def lire_reporting(fichier_uploade):
    df = pd.read_excel(fichier_uploade, header=None)
    header_row, header_col = localiser_entete(df)
    if header_row is None:
        raise FichierReportingInvalide(
            f"Colonne « REFERENCE » introuvable dans les 40 premières lignes / "
            f"12 premières colonnes de « {fichier_uploade.name} ». Ce fichier n'est "
            f"peut-être pas un reporting mensuel DAN, ou son format diffère de "
            f"l'attendu. Aperçu du contenu lu :\n{_apercu_premieres_lignes(df)}"
        )

    body = df.iloc[header_row + 1:, header_col:header_col + len(COLS)].copy()
    # Si le fichier a moins de colonnes que prevu apres l'en-tete (colonnes
    # finales vides omises par Excel, par exemple), completer avec des
    # colonnes vides plutot que de planter sur une affectation de longueur
    # incompatible.
    if body.shape[1] < len(COLS):
        for _ in range(len(COLS) - body.shape[1]):
            body[body.shape[1]] = pd.NA
    body = body.iloc[:, :len(COLS)]
    body.columns = COLS

    # Une ligne est retenue des lors qu'elle porte soit une reference
    # codifiee (cas normal), soit un signal de contenu clair -- survenance
    # renseignee ET un libelle ou un motif renseigne. Cas reel observe :
    # des participants ajoutent des incidents en texte libre sous le
    # tableau structure du referentiel, sans code de reference ni libelle
    # en colonne EVENEMENT (la description se trouve alors dans MOTIF).
    # Ces lignes etaient auparavant perdues silencieusement (l'ancien
    # filtre ne gardait que les lignes avec une reference non vide) --
    # DAN doit rester exploitable sur des fichiers qui s'ecartent du
    # format strict, pas seulement sur le gabarit de reference.
    a_une_reference = body["reference"].notna()
    a_du_contenu_libre = (
        body["survenance"].notna() & (body["evenement"].notna() | body["motif"].notna())
    )
    body = body[a_une_reference | a_du_contenu_libre].copy()

    # Detection PAR CONTENU en priorite ; repli sur le nom de fichier
    # seulement si aucune reference du fichier ne suit la codification
    # attendue (cas degrade, signale via detection_avertissement).
    domaine, site, confiance = detecter_domaine_site_par_contenu(body["reference"])
    detection_avertissement = None
    if domaine is None:
        domaine, site = detecter_domaine_site_repli(fichier_uploade.name)
        confiance = 0.0
        detection_avertissement = (
            f"Système détecté à partir du nom de fichier (« {fichier_uploade.name} ») : "
            f"aucune référence de ce fichier ne suit la codification RP[domaine][site][n°] "
            f"attendue. Vérifiez que ce fichier est un reporting valide."
        )
    elif confiance < 1.0:
        detection_avertissement = (
            f"{round((1 - confiance) * 100)} % des références de ce fichier ne correspondent "
            f"pas au système majoritaire détecté ({domaine}) — fichier possiblement composite "
            f"ou partiellement corrompu."
        )

    body["domaine"] = domaine
    body["site"] = site
    body["fichier_source"] = fichier_uploade.name
    body["detection_confiance"] = confiance
    body["detection_avertissement"] = detection_avertissement

    # Pays : deduit du nom du dossier de premier niveau qui contenait le
    # fichier lors d'un depot de dossier entier (voir _deduire_pays),
    # PAS du contenu du fichier -- DAN ne cherche plus a identifier un
    # participant precis (Code Banque), seulement le pays d'appartenance,
    # tel qu'organise par l'equipe de surveillance dans son arborescence de dossiers.
    # Un simple fichier depose isolement (sans dossier parent) n'a pas de
    # pays connu.
    segments = _segments_chemin(fichier_uploade)
    body["pays"] = _deduire_pays(segments)

    # Le mois et l'annee sont lus en priorite depuis l'organisation des
    # dossiers (ex. "MOIS JANVIER 2026"), pas inventes ni dependants
    # uniquement du contenu du fichier -- souvent incomplet sur ce point.
    # Repli sur le contenu (Annee/Mois releves dans le fichier) si le
    # dossier ne fournit pas cette information.
    mois_dossier, annee_dossier = _deduire_mois_annee_dossier(segments)
    periode_contenu = extraire_periode(df)
    body["mois"] = mois_dossier or periode_contenu["mois"]
    body["annee"] = annee_dossier or periode_contenu["annee"]

    # Completer les lignes sans reference codifiee : identifiant tracable
    # genere, et libelle repris du motif quand la colonne EVENEMENT est
    # vide (cas observe : la description y est saisie a la place). Ces
    # evenements sont marques hors_referentiel=True -- ils ne pourront pas
    # etre rattaches a un point du Referentiel de Surveillance (mapping),
    # et recoivent donc un niveau de risque par defaut plutot qu'une
    # correspondance validee (voir calculer_scores).
    body["hors_referentiel"] = body["reference"].isna()
    n_sans_ref = int(body["hors_referentiel"].sum())
    if n_sans_ref > 0:
        prefixe = domaine[:3] if domaine != "INCONNU" else "GEN"
        body.loc[body["hors_referentiel"], "reference"] = [
            f"HORS-REF-{prefixe}-{i+1:02d}" for i in range(n_sans_ref)
        ]
        manque_libelle = body["hors_referentiel"] & body["evenement"].isna()
        body.loc[manque_libelle, "evenement"] = (
            body.loc[manque_libelle, "motif"].fillna("Événement signalé sans libellé ni code de référence")
        )
        if detection_avertissement is None:
            detection_avertissement = (
                f"{n_sans_ref} événement(s) sans code de référence détecté(s) dans ce fichier "
                f"(ajoutés en texte libre par l'assujetti) — repris sous un identifiant généré, "
                f"mais non rattachables au Référentiel de Surveillance."
            )
            body["detection_avertissement"] = detection_avertissement

    # Toute valeur autre que "Oui" (explicitement) est traitee comme "non
    # survenu" -- notamment "RAS" (rien a signaler), les cellules vides/NaN,
    # ou toute autre mention. Auparavant seul "Non" donnait 0 ; RAS et les
    # cellules vides restaient a NaN, ce qui les faisait disparaitre a la
    # fois du filtre "Survenus" (normal) ET du filtre "Non survenus"
    # (== 0 exclut NaN) -- ces evenements devenaient invisibles partout.
    body["survenance_bin"] = (
        body["survenance"].astype(str).str.strip().str.lower().eq("oui").astype(int)
    )
    body["occurrence_num"] = pd.to_numeric(body["occurrence"], errors="coerce")
    body["duree_indispo_min"] = pd.to_numeric(body["duree_indispo_min"], errors="coerce")
    return body


@st.cache_data
def charger_mapping():
    from chemins import chemin_ressource
    chemin = chemin_ressource("mapping/mapping_risques.xlsx")
    if not os.path.exists(chemin):
        return None
    mapping = pd.read_excel(chemin)
    mapping = mapping.rename(columns={
        "Code événement": "reference", "Événement": "evenement_ref",
        "Domaine": "domaine", "Site": "site",
        "Code référentiel": "code_referentiel",
        "Élément d'appréciation": "element_appreciation",
        "Risque(s)": "risque", "Niveau": "niveau", "Confiance": "confiance",
        "Justification": "justification",
    })
    return mapping


@st.cache_data
def calculer_scores(evt_df, mapping_df):
    """
    Calcule la gravite de chaque evenement, avec eclatement d'une ligne en
    plusieurs si son code de risque combine plusieurs categories (ex.
    "RO+RJ" -> une ligne "RO" et une ligne "RJ", poids partage entre les
    deux). Version vectorisee (split/explode pandas) plutot qu'une boucle
    Python ligne par ligne -- plus rapide sur de gros volumes, memes
    regles de calcul exactement (reutilise calculer_gravite_evenement et
    poids_occurrence, deja concus pour fonctionner aussi bien sur une
    Series entiere que sur une valeur seule).
    """
    df = evt_df.merge(mapping_df[["reference", "risque", "niveau"]], on="reference", how="left")
    df = df[~df["reference"].isin(EXCLUS)].copy()

    df["occurrence_finale"] = df["occurrence_num"]
    mask_texte = df["occurrence_finale"].isna() & (df["survenance_bin"] == 1)
    df.loc[mask_texte, "occurrence_finale"] = 1
    df["occurrence_finale"] = df["occurrence_finale"].fillna(0).astype(float)
    df["poids_niveau"] = df["niveau"].map(POIDS_NIVEAU).fillna(1.5)

    # Categories de risque par ligne : "RO+RJ" -> ["RO","RJ"] ; valeur
    # manquante ou vide -> ["RO"] (repli par defaut, comme dans l'ancienne
    # version ligne par ligne).
    categories = df["risque"].astype(str).str.replace(" ", "", regex=False).str.split("+")
    categories = categories.where(df["risque"].notna(), None)
    categories = categories.apply(
        lambda lst: [r for r in lst if r] if isinstance(lst, list) else []
    )
    categories = categories.apply(lambda lst: lst if lst else ["RO"])

    df["categorie_risque"] = categories
    df["poids_part"] = df["poids_niveau"] / df["categorie_risque"].str.len()
    df["gravite"] = calculer_gravite_evenement(
        df["survenance_bin"], df["occurrence_finale"], df["poids_part"]
    )

    return df.explode("categorie_risque", ignore_index=True)


def niveau_depuis_score_100(score_100):
    """Traduit un score relatif (0-100) en niveau qualitatif + couleur."""
    if score_100 >= 75:
        return "Critique"
    elif score_100 >= 50:
        return "Élevé"
    elif score_100 >= 25:
        return "Moyen"
    return "Faible"
