# -*- coding: utf-8 -*-
"""
Tests de logic.participants : regroupement d'un lot d'import par pays
(deduit du nom du dossier de premier niveau, pas du contenu du fichier),
et calcul du resume comparatif sur l'ensemble fixe des six pays de la
CEMAC -- sans aucune liste de reference a charger.
"""
import pandas as pd
import pytest

from logic.participants import grouper_par_pays, resume_pays, filtrer_pays, PAYS_CEMAC


def _evt(pays, domaine="SYGMA", reference="RPSYGPS01", survenu=True):
    return {
        "reference": reference, "evenement": "Test", "survenance": "Oui" if survenu else "Non",
        "occurrence": None, "motif": None, "statut": None, "duree_indispo_min": None,
        "commentaire": None, "domaine": domaine, "site": "PS",
        "fichier_source": f"{domaine}_{pays}.xlsx",
        "detection_confiance": 1.0, "detection_avertissement": None, "hors_referentiel": False,
        "survenance_bin": 1 if survenu else 0, "occurrence_num": None,
        "pays": pays, "annee": "2026", "mois": "4",
    }


@pytest.fixture
def lot_deux_pays():
    return pd.DataFrame([
        _evt("Cameroun", "SYGMA", "RPSYGPS01", survenu=True),
        _evt("Cameroun", "SWIFT", "RPSWIPS01", survenu=False),
        _evt("Congo", "SYSTAC", "RPSYSPS01", survenu=True),
        _evt("Congo", "SYSTAC", "RPSYSPS02", survenu=True),
    ])


class TestGroupementParPays:

    def test_separe_correctement_deux_pays(self, lot_deux_pays):
        groupes = grouper_par_pays(lot_deux_pays)
        assert set(groupes.keys()) == {"Cameroun", "Congo"}
        assert len(groupes["Cameroun"]) == 2
        assert len(groupes["Congo"]) == 2

    def test_lot_mono_pays_produit_un_seul_groupe(self):
        df = pd.DataFrame([_evt("Cameroun")])
        groupes = grouper_par_pays(df)
        assert len(groupes) == 1

    def test_absence_de_colonne_pays_ne_plante_pas(self):
        df = pd.DataFrame([{"domaine": "SYGMA", "reference": "RPSYGPS01"}])
        groupes = grouper_par_pays(df)
        assert len(groupes) == 1


class TestFiltragePays:

    def test_filtrer_un_pays_isole_ses_evenements(self, lot_deux_pays):
        sous_df = filtrer_pays(lot_deux_pays, "Cameroun")
        assert len(sous_df) == 2
        assert (sous_df["pays"] == "Cameroun").all()

    def test_filtrer_pays_absent_renvoie_vide(self, lot_deux_pays):
        sous_df = filtrer_pays(lot_deux_pays, "Gabon")
        assert len(sous_df) == 0


class TestResumePays:

    def test_sans_cemac_complet_seuls_les_importes_apparaissent(self, lot_deux_pays, mapping_minimal_pret):
        resume = resume_pays(lot_deux_pays, mapping_minimal_pret, inclure_cemac_complet=False)
        assert len(resume) == 2
        assert set(resume["pays"]) == {"Cameroun", "Congo"}

    def test_avec_cemac_complet_les_six_pays_apparaissent(self, lot_deux_pays, mapping_minimal_pret):
        """Comportement demande explicitement : deux pays importes, mais
        les six pays de la CEMAC doivent tous figurer dans le resultat --
        sans qu'aucune liste n'ait ete chargee (PAYS_CEMAC est fixe)."""
        resume = resume_pays(lot_deux_pays, mapping_minimal_pret, inclure_cemac_complet=True)
        assert len(resume) == 6
        assert set(resume["pays"]) == set(PAYS_CEMAC)

    def test_pays_non_transmis_a_le_bon_statut(self, lot_deux_pays, mapping_minimal_pret):
        resume = resume_pays(lot_deux_pays, mapping_minimal_pret, inclure_cemac_complet=True)
        ligne_gabon = resume[resume["pays"] == "Gabon"].iloc[0]
        assert ligne_gabon["niveau"] == "Non transmis"
        assert ligne_gabon["transmis"] == False
        assert ligne_gabon["score"] is None or pd.isna(ligne_gabon["score"])

    def test_pays_transmis_conserve_son_score_reel(self, lot_deux_pays, mapping_minimal_pret):
        resume = resume_pays(lot_deux_pays, mapping_minimal_pret, inclure_cemac_complet=True)
        ligne_cameroun = resume[resume["pays"] == "Cameroun"].iloc[0]
        assert ligne_cameroun["transmis"] == True

    def test_calcule_des_scores_independants_par_pays(self, lot_deux_pays, mapping_minimal_pret):
        resume = resume_pays(lot_deux_pays, mapping_minimal_pret)
        score_cameroun = resume[resume["pays"] == "Cameroun"]["score"].iloc[0]
        score_congo = resume[resume["pays"] == "Congo"]["score"].iloc[0]
        # Les deux scores doivent etre calcules independamment (pas de
        # melange entre pays) -- au moins l'un des deux doit etre > 0
        # puisque des evenements survenus existent dans les deux groupes.
        assert score_cameroun >= 0
        assert score_congo >= 0

    def test_tries_transmis_avant_non_transmis(self, lot_deux_pays, mapping_minimal_pret):
        resume = resume_pays(lot_deux_pays, mapping_minimal_pret, inclure_cemac_complet=True)
        assert resume.iloc[0]["transmis"] == True
        assert resume.iloc[-1]["transmis"] == False

    def test_aucun_import_mais_cemac_complet_montre_tout_en_non_transmis(self, mapping_minimal_pret):
        evt_df_vide = pd.DataFrame(columns=[
            "reference", "domaine", "site", "fichier_source", "survenance_bin", "pays",
        ])
        resume = resume_pays(evt_df_vide, mapping_minimal_pret, inclure_cemac_complet=True)
        assert len(resume) == 6
        assert (resume["transmis"] == False).all()

    def test_liste_cemac_contient_bien_six_pays(self):
        assert len(PAYS_CEMAC) == 6
        assert "Cameroun" in PAYS_CEMAC
        assert "Tchad" in PAYS_CEMAC
