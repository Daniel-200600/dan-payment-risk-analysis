# -*- coding: utf-8 -*-
import streamlit as st
import os
import pandas as pd
from style import entete_page
from logic.configuration import (
    charger_configuration, sauvegarder_configuration, reinitialiser_configuration,
    exporter_configuration_json, importer_configuration_json, valider_seuils_gravite,
    construire_participants_depuis_tableau,
)
from chemins import chemin_ressource, chemin_donnees


def ligne_statut(libelle, chemin):
    icone = "✅" if os.path.exists(chemin) else "⚠️"
    st.write(f"{icone} {libelle}")


def afficher():
    entete_page("Paramètres", "Centre de configuration de DAN")
    config = charger_configuration()

    onglets = st.tabs([
        "⚙️ Général", "🎚️ Seuils de score", "👥 Participants attendus/reçus",
        "💾 Sauvegarde", "🔍 État système",
    ])

    # ------------------------------------------------------------------
    # Configuration generale -- le nom du responsable est editable, le
    # reste demeure informatif (modification desactivee pour eviter un
    # changement accidentel des reglages institutionnels)
    # ------------------------------------------------------------------
    with onglets[0]:
        st.subheader("Configuration générale")
        st.write(f"**Nom de l'application** : {config['nom_application']}")
        st.write(f"**Nom de l'institution** : {config['nom_institution']}")
        st.write(f"**Direction / Service** : {config['direction']}")
        st.write(f"**Version** : {config['version']}")
        st.write(f"**Dossier de sauvegarde des rapports** : {config['chemin_sauvegarde']}")

        st.markdown("---")
        nom_responsable = st.text_input(
            "Nom du responsable",
            value=config.get("responsable", ""),
            placeholder="Nom et prénom du responsable de l'analyse",
        )
        if st.button("Enregistrer le nom du responsable"):
            config["responsable"] = nom_responsable.strip()
            sauvegarder_configuration(config)
            st.success("✅ Nom du responsable enregistré.")
            st.rerun()

    # ------------------------------------------------------------------
    # Seuils de score : parametrables par l'agent selon ses propres
    # besoins d'analyse -- ne sont plus une valeur figee dans le code.
    # ------------------------------------------------------------------
    with onglets[1]:
        st.subheader("Seuils de niveau de risque")
        st.caption(
            "Ces quatre seuils déterminent à partir de quelle gravité un système ou "
            "un pays est classé Critique, Élevé, Moyen ou Faible (en dessous du dernier "
            "seuil : Très faible). Ajustez-les selon vos propres besoins d'analyse — "
            "aucune valeur n'est imposée par DAN."
        )

        seuils_actuels = config.get("seuils_gravite", [25, 10, 3, 0.5])
        col_a, col_b, col_c, col_d = st.columns(4)
        seuil_critique = col_a.number_input(
            "Critique à partir de", value=float(seuils_actuels[0]), min_value=0.1, step=0.5,
        )
        seuil_eleve = col_b.number_input(
            "Élevé à partir de", value=float(seuils_actuels[1]), min_value=0.1, step=0.5,
        )
        seuil_moyen = col_c.number_input(
            "Moyen à partir de", value=float(seuils_actuels[2]), min_value=0.1, step=0.5,
        )
        seuil_faible = col_d.number_input(
            "Faible à partir de", value=float(seuils_actuels[3]), min_value=0.01, step=0.1,
        )
        nouveaux_seuils = [seuil_critique, seuil_eleve, seuil_moyen, seuil_faible]

        est_valide, message = valider_seuils_gravite(nouveaux_seuils)
        if not est_valide:
            st.error(f"❌ {message}")
        else:
            st.caption(f"✅ {message} En dessous de {seuil_faible}, le niveau est Très faible.")

        if st.button("Enregistrer ces seuils", disabled=not est_valide, type="primary"):
            config["seuils_gravite"] = nouveaux_seuils
            sauvegarder_configuration(config)
            st.success("✅ Seuils enregistrés — appliqués immédiatement partout dans DAN.")
            st.toast("Seuils de score mis à jour", icon="🎚️")
            st.rerun()

        if nouveaux_seuils != [25, 10, 3, 0.5]:
            if st.button("↩️ Revenir aux valeurs de départ (25 / 10 / 3 / 0,5)"):
                config["seuils_gravite"] = [25, 10, 3, 0.5]
                sauvegarder_configuration(config)
                st.success("✅ Seuils réinitialisés aux valeurs de départ.")
                st.rerun()

    # ------------------------------------------------------------------
    # Participants attendus / recus par pays : donnees utilisees par le
    # Rapport d'activite (tableau 1.1, taux de reponses). L'attendu est
    # une donnee institutionnelle que DAN ne peut pas deviner ; le recu
    # est estime automatiquement a partir des dossiers importes, mais
    # reste modifiable si l'agent sait que l'estimation n'est pas exacte.
    # ------------------------------------------------------------------
    with onglets[2]:
        st.subheader("Participants attendus et reçus par pays")
        st.caption(
            "« Attendu » est une donnée institutionnelle, à renseigner vous-même — DAN "
            "ne peut pas la déduire des fichiers importés. « Reçu » est estimé "
            "automatiquement à partir du dernier lot importé (nombre de dossiers "
            "distincts par pays) ; vous pouvez le corriger ici si cette estimation "
            "ne correspond pas à la réalité. Ces valeurs s'appliquent automatiquement "
            "au prochain rapport d'activité généré, sans autre action de votre part."
        )

        attendus_actuels = config.get("participants_attendus", {}) or {}
        recus_manuels_actuels = config.get("participants_recus_manuel", {}) or {}

        recus_auto = {}
        if "evt_df_complet" in st.session_state or "evt_df" in st.session_state:
            from logic.rapports import _compter_participants_recus_par_pays
            donnees_dispo = st.session_state.get("evt_df_complet", st.session_state.get("evt_df"))
            recus_auto = _compter_participants_recus_par_pays(donnees_dispo)

        tous_pays = sorted(set(attendus_actuels.keys()) | set(recus_auto.keys()) | set(recus_manuels_actuels.keys()))
        if not tous_pays:
            tous_pays = ["Cameroun", "Congo", "Tchad", "Guinée Équatoriale", "Gabon", "Centrafrique"]

        lignes_tableau = []
        for pays in tous_pays:
            lignes_tableau.append({
                "Pays": pays,
                "Attendu": attendus_actuels.get(pays, 0),
                "Reçu (estimation automatique)": recus_auto.get(pays, 0),
                "Reçu (correction manuelle, optionnel)": recus_manuels_actuels.get(pays),
            })
        df_edition = pd.DataFrame(lignes_tableau)

        df_modifie = st.data_editor(
            df_edition, use_container_width=True, hide_index=True, num_rows="dynamic",
            column_config={
                "Pays": st.column_config.TextColumn(required=True),
                "Attendu": st.column_config.NumberColumn(min_value=0, step=1, required=True),
                "Reçu (estimation automatique)": st.column_config.NumberColumn(disabled=True),
                "Reçu (correction manuelle, optionnel)": st.column_config.NumberColumn(min_value=0, step=1),
            },
            key="editeur_participants",
        )

        if st.button("Enregistrer ces réglages", type="primary"):
            nouveaux_attendus, nouveaux_recus_manuels = construire_participants_depuis_tableau(df_modifie)
            config["participants_attendus"] = nouveaux_attendus
            config["participants_recus_manuel"] = nouveaux_recus_manuels
            sauvegarder_configuration(config)
            st.success("✅ Réglages enregistrés — appliqués au prochain rapport d'activité généré.")
            st.toast("Participants mis à jour", icon="👥")
            st.rerun()

    # ------------------------------------------------------------------
    # Sauvegarde / export-import config
    # ------------------------------------------------------------------
    with onglets[3]:
        st.subheader("Sauvegarde de la configuration")
        st.download_button(
            "⬇️ Exporter la configuration (.json)",
            exporter_configuration_json(),
            file_name="dan_configuration.json", mime="application/json",
        )

        fichier_config = st.file_uploader("Importer une configuration (.json)", type=["json"])
        if fichier_config and st.button("Importer cette configuration"):
            try:
                importer_configuration_json(fichier_config.read().decode("utf-8"))
                st.success("✅ Configuration importée avec succès.")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Fichier de configuration invalide : {e}")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Réinitialiser la configuration par défaut"):
            reinitialiser_configuration()
            st.success("✅ Configuration réinitialisée.")
            st.rerun()

    # ------------------------------------------------------------------
    # Etat systeme (ancienne page, conservee)
    # ------------------------------------------------------------------
    with onglets[4]:
        ligne_statut("Table de correspondance des risques", chemin_ressource("mapping/mapping_risques.xlsx"))
        ligne_statut("Guide de surveillance", chemin_ressource("referentiels/GUIDE_DE_SURVEILLANCE.docx"))
        ligne_statut("Logo", chemin_ressource("referentiels/logo.png"))
        ligne_statut("Analyse qualitative des commentaires disponible", chemin_donnees("data/processed/analyse_qualitative.json"))

        st.markdown("<br>", unsafe_allow_html=True)
        if "evt_df" in st.session_state or "evt_df_complet" in st.session_state:
            if st.button("🗑️ Réinitialiser les données de la session en cours"):
                for cle in [
                    "evt_df", "evt_df_complet", "dernier_rapport_docx", "historique_id_courant",
                    "historique_ids_lot", "pays_filtre_par_defaut", "tb_filtres_valides",
                ]:
                    st.session_state.pop(cle, None)
                st.rerun()

    from pages_dan.widget_assistant import afficher_assistant
    afficher_assistant("Paramètres")
