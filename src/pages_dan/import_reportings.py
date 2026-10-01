# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from style import entete_page
from logic.donnees import (
    lire_reporting, charger_mapping, calculer_scores, FichierReportingInvalide,
)
from logic.interpretation import interpretation_absolue
from logic.historique import enregistrer_analyse, detecter_import_duplique, enregistrer_lot_multi_pays
from logic.participants import grouper_par_pays, resume_pays
from logic.journalisation import journaliser_erreur
from logic.configuration import charger_configuration
from logic.rapports import generer_rapport_general


def traiter_lot_fichiers(fichiers):
    """
    Lit, agrege et enregistre un lot de fichiers de reporting deja
    identifies (depot individuel ou depot de dossier natif -- voir
    accept_multiple_files="directory" dans afficher()). Met a jour st.session_state et
    provoque un st.rerun() en cas de succes.
    """
    noms = [f.name for f in fichiers]
    doublons = {n for n in noms if noms.count(n) > 1}
    if doublons:
        st.warning(
            f"⚠️ Fichier(s) présent(s) plusieurs fois, une seule copie sera "
            f"conservée : {', '.join(doublons)}"
        )
        fichiers = list({f.name: f for f in fichiers}.values())

    # Filtrage par extension AVANT toute lecture : le mode de depot de
    # dossier de Streamlit (accept_multiple_files="directory") n'applique
    # pas toujours fidelement le filtre "type=" cote navigateur (limite
    # connue de Streamlit) -- un dossier contenant aussi des .zip, .rar,
    # .pdf (referentiels, archives...) peut donc atterrir ici. Ces
    # fichiers ne sont pas des reportings : on les ignore silencieusement
    # (simple recapitulatif), plutot que d'assener une erreur par fichier
    # non pertinent.
    fichiers_excel = [f for f in fichiers if f.name.lower().endswith((".xlsx", ".xls"))]
    fichiers_ignores = [f for f in fichiers if f not in fichiers_excel]
    if fichiers_ignores:
        st.info(
            f"ℹ️ {len(fichiers_ignores)} fichier(s) non-Excel ignoré(s) (ex. .zip, "
            f".rar, .pdf) — seuls les fichiers .xlsx et .xls sont traités comme "
            f"des reportings."
        )
    fichiers = fichiers_excel
    if not fichiers:
        return

    signature_lot = tuple(sorted((f.name, f.size) for f in fichiers))
    deja_traite = st.session_state.get("dernier_lot_traite") == signature_lot

    noms_fichiers = [f.name for f in fichiers]
    entree_dupliquee = detecter_import_duplique(noms_fichiers)
    confirmer_import_duplique = True
    if entree_dupliquee and not deja_traite:
        confirmer_import_duplique = st.session_state.get("confirmer_import_duplique", False)
        st.warning(
            f"⚠️ Ce même ensemble de fichiers a déjà été importé le "
            f"{entree_dupliquee['date']} à {entree_dupliquee['heure']} "
            f"(niveau obtenu à l'époque : {entree_dupliquee['niveau_risque']}). "
            f"Réimporter créera une nouvelle entrée distincte dans l'historique."
        )
        confirmer_import_duplique = st.checkbox(
            "Je confirme vouloir importer à nouveau ces mêmes fichiers.",
            key="confirmer_import_duplique",
        )

    if deja_traite or not confirmer_import_duplique:
        return

    barre = st.progress(0, text="Lecture des fichiers...")
    frames = []
    fichiers_non_reporting = []
    for i, f in enumerate(fichiers):
        try:
            df_lu = lire_reporting(f)
            if "REFERENCE" not in "".join(map(str, df_lu.columns)) and len(df_lu) == 0:
                st.warning(f"⚠️ {f.name} semble vide ou mal structuré (aucun événement lu).")
            avertissement = df_lu["detection_avertissement"].iloc[0] if len(df_lu) else None
            if avertissement:
                st.warning(f"⚠️ {f.name} — {avertissement}")
            frames.append(df_lu)
        except ImportError as e:
            journaliser_erreur(f"Import fichier {f.name}", e)
            st.error(
                f"❌ {f.name} n'a pas pu être lu — une composante nécessaire à la "
                f"lecture de ce type de fichier manque sur cet ordinateur. "
                f"Contactez le support technique (voir page Aide)."
            )
        except FichierReportingInvalide as e:
            # Un fichier qui n'est pas un reporting DAN (registre de chèques,
            # autre document Excel isole dans le meme dossier...) n'est pas
            # une ERREUR a proprement parler -- DAN le signale simplement et
            # passe au suivant, sans alarmer inutilement l'agent avec un
            # message rouge pour un fichier qui n'avait de toute facon pas
            # vocation a etre traite.
            journaliser_erreur(f"Import fichier {f.name}", e)
            fichiers_non_reporting.append((f.name, str(e)))
        except Exception as e:
            journaliser_erreur(f"Import fichier {f.name}", e)
            st.error(
                f"❌ Erreur inattendue en lisant {f.name} : {e}. "
                f"Le format du fichier diffère peut-être de celui attendu — "
                f"contactez le support si le problème persiste."
            )
        barre.progress((i + 1) / len(fichiers), text=f"Lecture de {f.name}...")
    barre.empty()

    if fichiers_non_reporting:
        st.info(
            f"ℹ️ {len(fichiers_non_reporting)} fichier(s) Excel ne correspondent pas au "
            f"format d'un reporting DAN et n'ont pas été pris en compte — c'est normal si "
            f"un dossier contient d'autres documents (registres, référentiels...) à côté "
            f"des reportings."
        )
        with st.expander("Voir le détail des fichiers non pris en compte"):
            for nom, detail in fichiers_non_reporting:
                st.write(f"**{nom}**")
                st.caption(detail)

    if not frames:
        return

    evt_df = pd.concat(frames, ignore_index=True)
    st.session_state["dernier_lot_traite"] = signature_lot
    st.success(f"✅ {len(fichiers)} fichier(s) importé(s) avec succès.")
    st.toast("Import terminé", icon="✅")

    mapping_df = charger_mapping()
    pays_detectes = evt_df["pays"].nunique() if "pays" in evt_df.columns else 1

    if mapping_df is not None and pays_detectes > 1:
        # Lot multi-pays (arborescence Pays / Banque parcourue) : une
        # entree d'historique par pays, et une vue comparative immediate
        # plutot qu'une analyse unique qui melangerait les pays entre eux.
        st.session_state["evt_df_complet"] = evt_df
        st.session_state.pop("evt_df", None)
        identifiants = enregistrer_lot_multi_pays(evt_df, mapping_df)
        st.session_state["historique_ids_lot"] = identifiants
        st.info(
            f"ℹ️ {pays_detectes} pays distincts détectés dans ce lot (d'après "
            f"les dossiers parcourus) — une analyse séparée a été enregistrée "
            f"pour chacun. Voir la comparaison ci-dessous."
        )
    elif mapping_df is not None:
        # Cas normal : un seul pays dans le lot (ou fichiers deposes sans
        # structure de dossiers) -- comportement inchange.
        st.session_state["evt_df"] = evt_df
        st.session_state.pop("evt_df_complet", None)
        df_gravite = calculer_scores(evt_df, mapping_df)
        score_reseau = df_gravite.groupby("domaine")["gravite"].sum().reset_index()
        score_reseau = score_reseau[score_reseau["domaine"] != "INCONNU"]
        total = score_reseau["gravite"].sum()
        score_reseau["score_100"] = (
            (score_reseau["gravite"] / total * 100).round(1) if total > 0 else 0
        )
        niveau_info = interpretation_absolue(total)
        id_analyse = enregistrer_analyse(evt_df, score_reseau, niveau_info)
        st.session_state["historique_id_courant"] = id_analyse

        config = charger_configuration()
        if config.get("ia_generation_auto"):
            with st.spinner("Génération automatique du rapport général consolidé…"):
                chemin_docx, erreur = generer_rapport_general(evt_df, mapping_df, {})
            if erreur:
                journaliser_erreur("Génération automatique du rapport", erreur)
                st.warning(f"⚠️ Génération automatique du rapport impossible : {erreur}")
            else:
                from logic.historique import ajouter_rapport_a_analyse
                ajouter_rapport_a_analyse(id_analyse, "Rapport général consolidé", chemin_docx)
                st.success(
                    f"📄 Rapport général généré automatiquement : "
                    f"{chemin_docx.split('/')[-1]} (voir page Historique)."
                )
    else:
        st.session_state["evt_df"] = evt_df

    # Reinitialisation AUTOMATIQUE du widget de depot juste apres un import
    # reussi : le prochain depot de fichiers repart toujours de zero, sans
    # jamais se cumuler avec le lot precedent.
    st.session_state["uploader_key_suffix"] += 1
    st.rerun()


def afficher():
    entete_page("Import des reportings", "Déposez des fichiers ou un dossier entier")

    if "uploader_key_suffix" not in st.session_state:
        st.session_state["uploader_key_suffix"] = 0

    mode_dossier = st.toggle(
        "Déposer un dossier entier plutôt que des fichiers individuels",
        key="mode_depot_dossier",
    )
    if mode_dossier:
        st.caption(
            "Cliquez ci-dessous puis choisissez un **dossier** dans la fenêtre qui "
            "s'ouvre (pas des fichiers) — tous les fichiers Excel qu'il contient, à "
            "n'importe quelle profondeur, seront lus. Le pays de chacun est déduit "
            "du nom du dossier de premier niveau sous celui que vous choisissez "
            "(ex. Cameroun/Banque_A/... → pays = Cameroun ; les variantes de casse "
            "ou sigles comme CMR, cmr, CAMEROUN sont reconnus de la même façon). "
            "Le bouton reste actif après un premier choix : cliquez à nouveau pour "
            "ajouter un ou plusieurs autres dossiers (par exemple d'autres pays) "
            "avant de lancer l'import — ils s'additionnent, sans jamais remplacer "
            "la sélection précédente.\n\n"
            "⚠️ Si un sélecteur de fichiers s'ouvre à la place d'un sélecteur de "
            "dossier, contactez le support technique (voir page Aide)."
        )
        fichiers = st.file_uploader(
            "Dossier(s) de reportings (SYGMA, SWIFT, SYSTAC, RESEAU)",
            accept_multiple_files="directory",
            key=f"uploader_dossier_{st.session_state['uploader_key_suffix']}",
        )
        st.caption(
            "ℹ️ Un dossier réel contient souvent d'autres documents (référentiels, "
            "archives...) mélangés aux reportings — DAN les ignore automatiquement, "
            "sans faire échouer l'import à cause d'eux."
        )
    else:
        fichiers = st.file_uploader(
            "Fichiers de reporting (SYGMA, SWIFT, SYSTAC, RESEAU)",
            type=["xlsx", "xls"], accept_multiple_files=True,
            key=f"uploader_principal_{st.session_state['uploader_key_suffix']}",
        )
        st.caption(
            "ℹ️ Après chaque import réussi, la zone de dépôt se vide automatiquement — "
            "un nouveau dépôt ne se cumule jamais avec le lot précédent. Les analyses "
            "passées restent consultables dans « Historique des analyses »."
        )
    if fichiers:
        traiter_lot_fichiers(fichiers)

    if "evt_df_complet" in st.session_state:
        evt_df_complet = st.session_state["evt_df_complet"]
        st.subheader("Comparaison des pays de ce lot")
        mapping_df = charger_mapping()
        resume = resume_pays(evt_df_complet, mapping_df) if mapping_df is not None else pd.DataFrame()

        if len(resume):
            for _, ligne in resume.iterrows():
                col_a, col_b, col_c, col_d = st.columns([2, 2, 2, 2])
                col_a.markdown(f"**{ligne['pays']}**")
                col_b.write(", ".join(ligne["systemes_couverts"]) or "—")
                col_c.write(f"{ligne['nb_incidents']} incident(s)")
                col_d.markdown(f"{ligne['emoji']} **{ligne['score']}** — {ligne['niveau']}")

            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("📊 Analyser le lot", type="primary"):
                # evt_df_complet reste la source (TOUS les pays du lot) --
                # c'est sur le Tableau de bord, via les filtres, que l'agent
                # choisit ensuite le ou les pays a examiner et valide sa
                # selection -- pas de choix impose ici en amont.
                st.session_state.pop("historique_id_courant", None)
                st.session_state.pop("pays_filtre_par_defaut", None)
                st.switch_page(st.session_state["_pages_dan"]["tableau_bord"])
            st.caption(
                "Ouvre le Tableau de bord avec tous les pays de ce lot disponibles dans "
                "les filtres — sélectionnez le ou les pays à examiner, puis validez pour "
                "afficher les résultats."
            )

        if st.button("🗑️ Réinitialiser ce lot"):
            st.session_state.pop("evt_df_complet", None)
            st.session_state.pop("historique_ids_lot", None)
            st.session_state["uploader_key_suffix"] += 1
            st.rerun()

    elif "evt_df" in st.session_state:
        evt_df = st.session_state["evt_df"]
        st.subheader("Fichiers actuellement chargés")
        recap = (
            evt_df.groupby(["fichier_source", "domaine", "site"])
            .agg(nb_evenements=("reference", "size"), confiance=("detection_confiance", "first"))
            .reset_index()
        )
        recap["détection"] = recap["confiance"].apply(
            lambda c: "✅ Par contenu" if c and c >= 1.0
            else ("⚠️ Par contenu (partiel)" if c and c > 0 else "⚠️ Par nom de fichier")
        )
        recap = recap.drop(columns=["confiance"])
        st.dataframe(recap, use_container_width=True)
        st.caption(
            "Le système et le site sont détectés à partir des références des événements "
            "(ex. RPSYSPA01), pas du nom du fichier — celui-ci peut donc être renommé "
            "librement sans perturber l'import."
        )

        if "pays" in evt_df.columns:
            pays_actif = evt_df["pays"].dropna().iloc[0] if evt_df["pays"].notna().any() else "INCONNU"
            if pays_actif != "INCONNU":
                st.caption(f"🌍 Pays identifié : **{pays_actif}**")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("📊 Analyser le lot", type="primary", key="analyser_lot_mono"):
            st.switch_page(st.session_state["_pages_dan"]["tableau_bord"])

        domaines_inconnus = evt_df[evt_df["domaine"] == "INCONNU"]["fichier_source"].unique()
        if len(domaines_inconnus) > 0:
            st.warning(f"Système non reconnu pour : {', '.join(domaines_inconnus)}")

        if st.button("🗑️ Réinitialiser les fichiers importés"):
            del st.session_state["evt_df"]
            st.session_state.pop("historique_id_courant", None)
            st.session_state["uploader_key_suffix"] += 1  # force un widget d'upload neuf, vide
            st.rerun()
    else:
        st.info("En attente de fichiers à analyser.")

    from pages_dan.widget_assistant import afficher_assistant
    afficher_assistant("Import des reportings", evt_df=st.session_state.get("evt_df"))
