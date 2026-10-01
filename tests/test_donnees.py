# -*- coding: utf-8 -*-
"""
Tests de logic.donnees : lecture des reportings, detection du systeme et du
site par contenu, traitement de la survenance, calcul du score.

Chaque test correspond a un bug reellement rencontre et corrige au cours du
developpement de DAN -- ils existent pour empecher ces regressions de
revenir silencieusement.
"""
import pandas as pd
import pytest

from logic.donnees import (
    lire_reporting, detecter_domaine_site_par_contenu, detecter_domaine_site_repli,
    localiser_entete, calculer_scores, calculer_gravite_evenement, poids_occurrence,
    FichierReportingInvalide,
)


# ---------------------------------------------------------------------------
# Detection du systeme et du site PAR CONTENU (pas par nom de fichier)
# ---------------------------------------------------------------------------

class TestDetectionParContenu:

    def test_detecte_le_bon_systeme_quel_que_soit_le_nom_de_fichier(self, fabriquer_excel, entete_standard):
        """Un fichier dont le contenu est SYSTAC doit etre reconnu comme
        SYSTAC meme si son nom ne contient aucun indice (bug corrige :
        la detection reposait initialement sur le nom du fichier)."""
        lignes = [entete_standard] + [
            [f"RPSYSPS{n:02d}", f"Evenement {n}", "Non", "", "", "", "", ""]
            for n in range(1, 6)
        ]
        f = fabriquer_excel(lignes, nom="rapport_final_v2_DEFINITIF.xlsx")
        df = lire_reporting(f)
        assert (df["domaine"] == "SYSTAC").all()
        assert df["detection_confiance"].iloc[0] == 1.0

    def test_le_nom_de_fichier_trompeur_est_ignore(self, fabriquer_excel, entete_standard):
        """Un fichier nomme SWIFT mais dont le contenu est SYGMA doit etre
        classe SYGMA -- le contenu fait foi, jamais le nom."""
        lignes = [entete_standard] + [["RPSYGPS01", "Evt", "Non", "", "", "", "", ""]]
        f = fabriquer_excel(lignes, nom="SWIFT_faux.xlsx")
        df = lire_reporting(f)
        assert df["domaine"].iloc[0] == "SYGMA"

    def test_repli_sur_nom_de_fichier_si_contenu_illisible(self, fabriquer_excel, entete_standard):
        """Si aucune reference ne suit la codification attendue, DAN doit
        se rabattre sur le nom de fichier plutot que planter, et le
        signaler via detection_avertissement."""
        lignes = [entete_standard] + [["XYZ00001", "Evt bizarre", "Non", "", "", "", "", ""]]
        f = fabriquer_excel(lignes, nom="SYGMA_format_atypique.xlsx")
        df = lire_reporting(f)
        assert df["domaine"].iloc[0] == "SYGMA"
        assert df["detection_confiance"].iloc[0] == 0.0
        assert df["detection_avertissement"].iloc[0] is not None

    def test_vote_majoritaire_resiste_a_une_ligne_isolee_incoherente(self, fabriquer_excel, entete_standard):
        """Une seule ligne d'un AUTRE systeme, isolee au milieu d'un
        fichier majoritairement SYSTAC, ne doit pas faire basculer la
        detection globale (vote majoritaire)."""
        lignes = [entete_standard] + [
            ["RPSYSPS01", "Evt 1", "Non", "", "", "", "", ""],
            ["RPSYSPS02", "Evt 2", "Non", "", "", "", "", ""],
            ["RPSWIPS01", "Evt egare", "Non", "", "", "", "", ""],  # code valide mais autre systeme
        ]
        f = fabriquer_excel(lignes, nom="test.xlsx")
        df = lire_reporting(f)
        assert df["domaine"].iloc[0] == "SYSTAC"
        assert df["detection_confiance"].iloc[0] == pytest.approx(2 / 3, abs=0.001)


# ---------------------------------------------------------------------------
# Detection de l'en-tete : tolerance aux variations de format reelles
# ---------------------------------------------------------------------------

class TestLocalisationEntete:

    def test_entete_avec_accent(self, fabriquer_excel):
        """'Référence' (avec accent) doit etre reconnu comme 'REFERENCE'."""
        lignes = [
            ["Référence", "Evenement", "Survenance", "Occurrence", "Motif", "Statut", "Duree", "Commentaire"],
            ["RPSYGPS01", "Evt", "Non", "", "", "", "", ""],
        ]
        f = fabriquer_excel(lignes, nom="test.xlsx")
        df = lire_reporting(f)
        assert len(df) == 1

    def test_entete_decalee_en_colonne(self, fabriquer_excel):
        """Une colonne vide avant REFERENCE ne doit pas empecher la
        lecture (cas reel : fichiers avec une colonne de numerotation)."""
        lignes = [
            ["", "REFERENCE", "EVENEMENT", "SURVENANCE", "OCCURRENCE", "MOTIF", "STATUT", "DUREE", "COMMENTAIRE"],
            ["", "RPSYGPS01", "Evt", "Non", "", "", "", "", ""],
        ]
        f = fabriquer_excel(lignes, nom="test.xlsx")
        df = lire_reporting(f)
        assert len(df) == 1
        assert df["reference"].iloc[0] == "RPSYGPS01"

    def test_entete_decalee_en_ligne(self, fabriquer_excel, entete_standard):
        """Des lignes de titre avant l'en-tete ne doivent pas empecher
        la lecture (cas reel : bandeau institutionnel en tete de fichier)."""
        lignes = [
            ["RAPPORT MENSUEL"], ["Participant : XYZ"], [],
            entete_standard,
            ["RPSYGPS01", "Evt", "Non", "", "", "", "", ""],
        ]
        f = fabriquer_excel(lignes, nom="test.xlsx")
        df = lire_reporting(f)
        assert len(df) == 1

    def test_colonnes_manquantes_en_fin_de_fichier(self, fabriquer_excel):
        """Un fichier dont les dernieres colonnes (DUREE, COMMENTAIRE) sont
        totalement absentes ne doit pas planter."""
        lignes = [
            ["REFERENCE", "EVENEMENT"],
            ["RPSYGPS01", "Evt"],
        ]
        f = fabriquer_excel(lignes, nom="test.xlsx")
        df = lire_reporting(f)
        assert len(df) == 1
        assert set(["reference", "evenement", "duree_indispo_min", "commentaire"]).issubset(df.columns)

    def test_fichier_non_reporting_leve_une_exception_explicite(self, fabriquer_excel):
        """Un fichier sans aucune colonne REFERENCE doit lever
        FichierReportingInvalide avec un message diagnostique, pas une
        erreur pandas brute illisible."""
        lignes = [["Nom", "Prenom"], ["Jean", "Dupont"]]
        f = fabriquer_excel(lignes, nom="pas_un_reporting.xlsx")
        with pytest.raises(FichierReportingInvalide):
            lire_reporting(f)


# ---------------------------------------------------------------------------
# Traitement de la survenance : RAS, NaN, variantes de casse
# ---------------------------------------------------------------------------

class TestSurvenance:

    @pytest.mark.parametrize("valeur_brute,attendu", [
        ("Oui", 1), ("OUI", 1), ("oui ", 1), (" Oui", 1),
        ("Non", 0), ("RAS", 0), ("ras", 0), (None, 0), ("", 0), ("N/A", 0),
    ])
    def test_variantes_de_survenance(self, fabriquer_excel, entete_standard, valeur_brute, attendu):
        """RAS et les cellules vides doivent etre traites comme 'non
        survenu' (0), pas comme une valeur indeterminee (NaN) -- bug
        corrige qui faisait disparaitre ces evenements des filtres
        'survenus' ET 'non survenus' a la fois."""
        lignes = [entete_standard, ["RPSYGPS01", "Evt", valeur_brute, "", "", "", "", ""]]
        f = fabriquer_excel(lignes, nom="test.xlsx")
        df = lire_reporting(f)
        assert df["survenance_bin"].iloc[0] == attendu
        assert not pd.isna(df["survenance_bin"].iloc[0])

    def test_aucun_nan_ne_subsiste_dans_survenance_bin(self, fabriquer_excel, entete_standard):
        lignes = [entete_standard] + [
            ["RPSYGPS01", "Evt1", "Oui", "", "", "", "", ""],
            ["RPSYGPS02", "Evt2", "RAS", "", "", "", "", ""],
            ["RPSYGPS03", "Evt3", None, "", "", "", "", ""],
        ]
        f = fabriquer_excel(lignes, nom="test.xlsx")
        df = lire_reporting(f)
        assert df["survenance_bin"].isna().sum() == 0


# ---------------------------------------------------------------------------
# Evenements sans code de reference ("hors referentiel")
# ---------------------------------------------------------------------------

class TestHorsReferentiel:

    def test_evenement_sans_reference_est_capture_pas_perdu(self, fabriquer_excel, entete_standard):
        """Un evenement survenu mais sans code de reference (saisi en
        texte libre par l'assujetti) doit etre conserve, pas supprime
        silencieusement (bug reel : 4 evenements perdus sur un fichier
        de production reel)."""
        lignes = [entete_standard] + [
            ["RPSYGPS01", "Evt normal", "Non", "", "", "", "", ""],
            [None, None, "Oui", "Permanent", "Description dans le motif", "NR", "", ""],
        ]
        f = fabriquer_excel(lignes, nom="test.xlsx")
        df = lire_reporting(f)
        assert len(df) == 2
        ligne_libre = df[df["hors_referentiel"]]
        assert len(ligne_libre) == 1
        assert ligne_libre["survenance_bin"].iloc[0] == 1
        assert "Description dans le motif" in str(ligne_libre["evenement"].iloc[0])

    def test_reference_generee_est_tracable(self, fabriquer_excel, entete_standard):
        lignes = [entete_standard] + [
            [None, None, "Oui", "", "motif ici", "", "", ""],
        ]
        f = fabriquer_excel(lignes, nom="test.xlsx")
        df = lire_reporting(f)
        assert df["reference"].iloc[0].startswith("HORS-REF-")


# ---------------------------------------------------------------------------
# Calcul du score : lissage logarithmique, repli NaN -> RO
# ---------------------------------------------------------------------------

class TestCalculScore:

    def test_poids_occurrence_croissance_ralentie(self):
        """Le poids d'un evenement tres recurrent ne doit pas croitre
        lineairement (bug corrige : un evenement a 200 occurrences
        ecrasait tout le reste du score)."""
        assert poids_occurrence(0) == pytest.approx(1.0)
        poids_10 = poids_occurrence(10)
        poids_100 = poids_occurrence(100)
        poids_200 = poids_occurrence(200)
        # Le poids continue de croitre avec la recurrence...
        assert poids_10 < poids_100 < poids_200
        # ...mais beaucoup plus lentement qu'une simple addition (101, 201).
        assert poids_100 < 10
        assert poids_200 < 10

    def test_categorie_risque_non_mappee_retombe_sur_ro_pas_sur_nan(self, mapping_minimal_pret):
        """Un evenement sans correspondance dans le mapping (risque=NaN
        apres fusion) doit obtenir la categorie 'RO' par defaut, jamais
        la chaine litterale 'nan' (bug reel trouve et corrige)."""
        evt = pd.DataFrame([{
            "reference": "HORS-REF-SYS-01", "evenement": "Test", "survenance": "Oui",
            "occurrence": None, "motif": "test", "statut": "NR", "duree_indispo_min": None,
            "commentaire": None, "domaine": "SYSTAC", "site": "PS", "fichier_source": "t.xlsx",
            "detection_confiance": 1.0, "detection_avertissement": None, "hors_referentiel": True,
            "survenance_bin": 1, "occurrence_num": None,
        }])
        resultat = calculer_scores(evt, mapping_minimal_pret)
        assert "nan" not in resultat["categorie_risque"].astype(str).str.lower().values
        assert "RO" in resultat["categorie_risque"].values

    def test_evenement_non_survenu_ne_contribue_pas_au_score(self, mapping_minimal_pret):
        evt = pd.DataFrame([{
            "reference": "RPSYGPS01", "evenement": "Test", "survenance": "Non",
            "occurrence": None, "motif": None, "statut": None, "duree_indispo_min": None,
            "commentaire": None, "domaine": "SYGMA", "site": "PS", "fichier_source": "t.xlsx",
            "detection_confiance": 1.0, "detection_avertissement": None, "hors_referentiel": False,
            "survenance_bin": 0, "occurrence_num": None,
        }])
        resultat = calculer_scores(evt, mapping_minimal_pret)
        assert resultat["gravite"].sum() == 0

    def test_gravite_zero_si_non_survenu_quelle_que_soit_loccurrence(self):
        assert calculer_gravite_evenement(0, 500, 4) == 0

    def test_categorie_combinee_est_eclatee_en_plusieurs_lignes(self):
        """'RO+RJ' doit produire deux lignes distinctes (une par
        categorie), avec le poids du niveau partage a parts egales entre
        les deux -- donc une gravite IDENTIQUE sur les deux lignes."""
        mapping = pd.DataFrame({
            "reference": ["RPSYGPS01"], "evenement_ref": ["a"], "domaine": ["SYGMA"], "site": ["PS"],
            "code_referentiel": ["RS1"], "element_appreciation": ["x"],
            "risque": ["RO+RJ"], "niveau": ["Critique"], "confiance": ["Forte"], "justification": ["j"],
        })
        evt = pd.DataFrame([{
            "reference": "RPSYGPS01", "evenement": "Test", "survenance": "Oui",
            "occurrence": None, "motif": None, "statut": None, "duree_indispo_min": None,
            "commentaire": None, "domaine": "SYGMA", "site": "PS", "fichier_source": "t.xlsx",
            "detection_confiance": 1.0, "detection_avertissement": None, "hors_referentiel": False,
            "survenance_bin": 1, "occurrence_num": None,
        }])
        resultat = calculer_scores(evt, mapping)
        assert len(resultat) == 2
        assert set(resultat["categorie_risque"]) == {"RO", "RJ"}
        assert resultat["gravite"].iloc[0] == pytest.approx(resultat["gravite"].iloc[1])

    def test_occurrence_entierement_absente_ne_plante_pas(self, mapping_minimal_pret):
        """Cas qui a reellement fait echouer la version vectorisee lors de
        son developpement : quand TOUTES les occurrences d'un lot sont
        None, la colonne peut se retrouver en dtype 'object' au lieu de
        numerique, ce qui casse le calcul vectorise (np.log1p) meme si un
        calcul ligne par ligne s'en accommodait silencieusement."""
        evt = pd.DataFrame([
            {"reference": "RPSYGPS01", "evenement": "Test1", "survenance": "Oui",
             "occurrence": None, "motif": None, "statut": None, "duree_indispo_min": None,
             "commentaire": None, "domaine": "SYGMA", "site": "PS", "fichier_source": "t.xlsx",
             "detection_confiance": 1.0, "detection_avertissement": None, "hors_referentiel": False,
             "survenance_bin": 1, "occurrence_num": None},
            {"reference": "RPSWIPS01", "evenement": "Test2", "survenance": "Oui",
             "occurrence": None, "motif": None, "statut": None, "duree_indispo_min": None,
             "commentaire": None, "domaine": "SWIFT", "site": "PS", "fichier_source": "t.xlsx",
             "detection_confiance": 1.0, "detection_avertissement": None, "hors_referentiel": False,
             "survenance_bin": 1, "occurrence_num": None},
        ])
        resultat = calculer_scores(evt, mapping_minimal_pret)
        assert resultat["gravite"].notna().all()
        assert (resultat["gravite"] > 0).all()

    def test_gros_volume_reste_coherent(self, mapping_minimal_pret):
        """Le resultat vectorise doit rester coherent sur un volume
        realiste pour un import multi-pays/multi-mois (pas seulement sur
        un exemple jouet a une ligne)."""
        lignes = []
        refs = mapping_minimal_pret["reference"].tolist()
        for i in range(500):
            lignes.append({
                "reference": refs[i % len(refs)], "evenement": "Test", "survenance": "Oui" if i % 2 == 0 else "Non",
                "occurrence": i if i % 2 == 0 else None, "motif": None, "statut": None, "duree_indispo_min": None,
                "commentaire": None, "domaine": "SYGMA", "site": "PS", "fichier_source": "t.xlsx",
                "detection_confiance": 1.0, "detection_avertissement": None, "hors_referentiel": False,
                "survenance_bin": 1 if i % 2 == 0 else 0, "occurrence_num": i if i % 2 == 0 else None,
            })
        evt = pd.DataFrame(lignes)
        resultat = calculer_scores(evt, mapping_minimal_pret)
        assert len(resultat) >= 500  # au moins autant que de lignes d'origine (eclatement eventuel en plus)
        assert resultat["gravite"].notna().all()
        # Les non-survenus ne doivent jamais contribuer, meme dans un gros lot.
        non_survenus = resultat[resultat["survenance_bin"] == 0]
        assert (non_survenus["gravite"] == 0).all()
