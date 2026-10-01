# -*- coding: utf-8 -*-
"""
Tests de logic.historique : deduplication des rapports rattaches a une
analyse (bug reel : un rapport regenere deux fois provoquait une cle de
bouton de telechargement dupliquee et faisait planter la page Historique),
et effacement complet.
"""
import json
import pytest

from logic.historique import (
    charger_historique, ajouter_rapport_a_analyse, effacer_historique,
    supprimer_analyse, _dedoublonner_rapports, detecter_import_duplique,
    enregistrer_analyse,
)


def _entree_minimale(id_analyse="test-1"):
    return {
        "id": id_analyse, "date": "2026-01-01", "heure": "10:00:00",
        "utilisateur": "test", "systemes_analyses": ["SYSTAC"],
        "score_obtenu": 10.0, "niveau_risque": "Moyen", "niveau_emoji": "🟠",
        "nb_evenements": 30, "nb_incidents": 2,
        "detail_reseaux": [], "rapports_generes": [],
    }


class TestDeduplicationRapports:

    def test_meme_chemin_ajoute_deux_fois_ne_duplique_pas(self, dossier_historique_isole):
        entree = _entree_minimale()
        with open(dossier_historique_isole, "w") as f:
            json.dump([entree], f)

        ajouter_rapport_a_analyse("test-1", "rapport.docx", "outputs/rapports/rapport.docx")
        ajouter_rapport_a_analyse("test-1", "rapport.docx", "outputs/rapports/rapport.docx")

        historique = charger_historique()
        assert len(historique[0]["rapports_generes"]) == 1

    def test_chemins_differents_sajoutent_normalement(self, dossier_historique_isole):
        entree = _entree_minimale()
        with open(dossier_historique_isole, "w") as f:
            json.dump([entree], f)

        ajouter_rapport_a_analyse("test-1", "rapport_A.docx", "outputs/rapports/rapport_A.docx")
        ajouter_rapport_a_analyse("test-1", "rapport_B.docx", "outputs/rapports/rapport_B.docx")

        historique = charger_historique()
        assert len(historique[0]["rapports_generes"]) == 2

    def test_chargement_repare_automatiquement_un_historique_deja_corrompu(self, dossier_historique_isole):
        """Simule un historique.json ecrit par une version anterieure et
        bugguee du code (doublon deja present sur disque) -- le simple
        chargement doit le nettoyer, sans que l'utilisateur ait a tout
        effacer."""
        entree = _entree_minimale()
        entree["rapports_generes"] = [
            {"fichier_source": "x.docx", "chemin": "outputs/x.docx", "date_generation": "d1"},
            {"fichier_source": "x.docx", "chemin": "outputs/x.docx", "date_generation": "d2"},
        ]
        with open(dossier_historique_isole, "w") as f:
            json.dump([entree], f)

        historique = charger_historique()
        assert len(historique[0]["rapports_generes"]) == 1

    def test_dedoublonnage_ne_modifie_pas_une_entree_deja_propre(self):
        entree = _entree_minimale()
        entree["rapports_generes"] = [
            {"fichier_source": "a.docx", "chemin": "outputs/a.docx", "date_generation": "d1"},
        ]
        resultat = _dedoublonner_rapports([entree])
        assert len(resultat[0]["rapports_generes"]) == 1


class TestMigrationVersPays:
    """
    Bug reel : des entrees d'historique creees AVANT l'ajout du suivi par
    pays ne portent pas ce champ dans leur JSON d'origine -- la Vue
    multi-participants plantait dessus (KeyError: 'pays') des qu'une
    telle entree ancienne existait. Couvre aussi les entrees issues d'une
    version intermediaire de DAN qui suivait les participants par Code
    Banque (champ desormais abandonne).
    """

    def test_entree_ancienne_sans_pays_est_completee(self, dossier_historique_isole):
        entree_ancienne = _entree_minimale()
        entree_ancienne.pop("pays", None)
        with open(dossier_historique_isole, "w") as f:
            json.dump([entree_ancienne], f)

        historique = charger_historique()
        assert "pays" in historique[0]
        assert historique[0]["pays"] == "INCONNU"

    def test_migration_est_persistee_sur_disque(self, dossier_historique_isole):
        entree_ancienne = _entree_minimale()
        entree_ancienne.pop("pays", None)
        with open(dossier_historique_isole, "w") as f:
            json.dump([entree_ancienne], f)

        charger_historique()  # declenche la migration et la sauvegarde

        with open(dossier_historique_isole) as f:
            contenu_disque = json.load(f)
        assert contenu_disque[0]["pays"] == "INCONNU"

    def test_entree_recente_avec_pays_nest_pas_modifiee(self, dossier_historique_isole):
        entree_recente = _entree_minimale()
        entree_recente["pays"] = "Cameroun"
        with open(dossier_historique_isole, "w") as f:
            json.dump([entree_recente], f)

        historique = charger_historique()
        assert historique[0]["pays"] == "Cameroun"

    def test_entree_ancien_format_code_banque_est_aussi_migree(self, dossier_historique_isole):
        """Une entree issue de la version intermediaire (suivi par Code
        Banque) doit elle aussi obtenir un champ 'pays' -- DAN ne peut pas
        deviner retroactivement le pays reel, elle est donc marquee
        INCONNU comme toute autre entree sans pays."""
        entree_ancien_format = _entree_minimale()
        entree_ancien_format.pop("pays", None)
        entree_ancien_format["code_banque"] = "1039"
        with open(dossier_historique_isole, "w") as f:
            json.dump([entree_ancien_format], f)

        historique = charger_historique()
        assert historique[0]["pays"] == "INCONNU"


class TestEffacement:

    def test_effacer_historique_vide_completement(self, dossier_historique_isole):
        with open(dossier_historique_isole, "w") as f:
            json.dump([_entree_minimale("a"), _entree_minimale("b")], f)

        effacer_historique()
        assert charger_historique() == []

    def test_supprimer_une_analyse_ne_touche_pas_les_autres(self, dossier_historique_isole):
        with open(dossier_historique_isole, "w") as f:
            json.dump([_entree_minimale("a"), _entree_minimale("b")], f)

        supprimer_analyse("a")
        historique = charger_historique()
        assert len(historique) == 1
        assert historique[0]["id"] == "b"

    def test_chargement_sans_fichier_renvoie_liste_vide(self, dossier_historique_isole):
        assert charger_historique() == []


class TestDetectionImportDuplique:

    def test_meme_ensemble_de_fichiers_est_detecte(self):
        historique = [{**_entree_minimale(), "fichiers_sources": ["A.xlsx", "B.xlsx"]}]
        resultat = detecter_import_duplique(["B.xlsx", "A.xlsx"], historique)  # ordre different
        assert resultat is not None

    def test_ensemble_different_nest_pas_detecte(self):
        historique = [{**_entree_minimale(), "fichiers_sources": ["A.xlsx", "B.xlsx"]}]
        assert detecter_import_duplique(["C.xlsx"], historique) is None

    def test_sous_ensemble_partiel_nest_pas_un_doublon(self):
        """Un import partiel (un seul des deux fichiers precedents) n'est
        pas le meme import -- il ne doit pas etre signale comme doublon."""
        historique = [{**_entree_minimale(), "fichiers_sources": ["A.xlsx", "B.xlsx"]}]
        assert detecter_import_duplique(["A.xlsx"], historique) is None

    def test_liste_vide_ne_declenche_jamais_de_faux_positif(self):
        historique = [{**_entree_minimale(), "fichiers_sources": []}]
        assert detecter_import_duplique(["A.xlsx"], historique) is None

    def test_historique_vide_ne_detecte_rien(self):
        assert detecter_import_duplique(["A.xlsx"], []) is None

    def test_enregistrer_analyse_trace_bien_les_fichiers_sources(self, dossier_historique_isole):
        """enregistrer_analyse() doit inscrire fichiers_sources dans
        l'entree creee, sans quoi la detection de doublon ne peut
        jamais fonctionner pour les imports reels."""
        import pandas as pd
        evt_df = pd.DataFrame({
            "domaine": ["SYGMA", "SYGMA"],
            "fichier_source": ["SYGMA_PARTICIPANT.xlsx", "SYGMA_PARTICIPANT.xlsx"],
            "survenance_bin": [1, 0],
        })
        score_reseau_df = pd.DataFrame({"domaine": ["SYGMA"], "gravite": [4.0], "score_100": [100.0]})
        niveau_info = {"niveau": "Moyen", "emoji": "🟠"}

        enregistrer_analyse(evt_df, score_reseau_df, niveau_info)
        historique = charger_historique()
        assert historique[0]["fichiers_sources"] == ["SYGMA_PARTICIPANT.xlsx"]
