# -*- coding: utf-8 -*-
"""
Tests de la detection du pays a l'import : depot de dossier natif de
Streamlit (accept_multiple_files="directory", seul canal restant --
l'ancien depot par chemin local et par archive .zip a ete retire), et
normalisation des noms de pays (casse, accents, sigles).
"""
import os
import pytest

from logic.donnees import lire_reporting, normaliser_pays, PAYS_CEMAC


class TestDetectionPaysDepotDossierNatif:
    """
    Depuis Streamlit >= 1.61 environ, st.file_uploader accepte
    accept_multiple_files="directory" : le navigateur envoie alors le
    CHEMIN RELATIF complet (webkitRelativePath) comme nom de fichier,
    au lieu du seul nom du fichier. lire_reporting() doit en deduire le
    pays a partir du premier segment de ce chemin.
    """

    def _fichier_depot_natif(self, chemin_reel, chemin_relatif):
        import io

        class FauxDepotDossierNatif(io.BytesIO):
            pass

        with open(chemin_reel, "rb") as f:
            data = f.read()
        faux = FauxDepotDossierNatif(data)
        faux.name = chemin_relatif
        faux.size = len(data)
        return faux

    def test_pays_deduit_du_premier_segment_du_chemin(self):
        chemin_reel = "data/sample/Cameroun/MOIS MARS 2026/BANQUE_A/SWIFT_PARTICIPANT.xlsx"
        if not os.path.exists(chemin_reel):
            pytest.skip("Fichier de test reel indisponible dans cet environnement")
        faux = self._fichier_depot_natif(chemin_reel, "Cameroun/Banque_A/SWIFT.xlsx")
        df = lire_reporting(faux)
        assert df["pays"].iloc[0] == "Cameroun"

    def test_fonctionne_avec_une_profondeur_quelconque(self):
        chemin_reel = "data/sample/Cameroun/MOIS MARS 2026/BANQUE_A/SWIFT_PARTICIPANT.xlsx"
        if not os.path.exists(chemin_reel):
            pytest.skip("Fichier de test reel indisponible dans cet environnement")
        faux = self._fichier_depot_natif(
            chemin_reel, "Congo/Direction/Banque_C/Reportings/Avril/SWIFT.xlsx"
        )
        df = lire_reporting(faux)
        assert df["pays"].iloc[0] == "Congo"

    def test_gere_les_antislashs_windows(self):
        """Le webkitRelativePath peut arriver avec des antislashs sur
        certaines configurations Windows -- doit etre normalise."""
        chemin_reel = "data/sample/Cameroun/MOIS MARS 2026/BANQUE_A/SWIFT_PARTICIPANT.xlsx"
        if not os.path.exists(chemin_reel):
            pytest.skip("Fichier de test reel indisponible dans cet environnement")
        faux = self._fichier_depot_natif(chemin_reel, "Tchad\\Banque_D\\SWIFT.xlsx")
        df = lire_reporting(faux)
        assert df["pays"].iloc[0] == "Tchad"

    def test_variante_de_casse_et_de_sigle_reconnue_a_limport(self):
        """La normalisation s'applique directement au moment de la
        lecture : un dossier nomme 'CMR' donne bien pays='Cameroun'."""
        chemin_reel = "data/sample/Cameroun/MOIS MARS 2026/BANQUE_A/SWIFT_PARTICIPANT.xlsx"
        if not os.path.exists(chemin_reel):
            pytest.skip("Fichier de test reel indisponible dans cet environnement")
        faux = self._fichier_depot_natif(chemin_reel, "CMR/Banque_A/SWIFT.xlsx")
        df = lire_reporting(faux)
        assert df["pays"].iloc[0] == "Cameroun"

    def test_fichier_depose_seul_sans_dossier_a_pays_inconnu(self):
        """Un fichier depose via st.file_uploader classique (sans chemin
        de dossier dans son nom) doit se rabattre sur 'INCONNU'."""
        chemin_reel = "data/sample/Cameroun/MOIS MARS 2026/BANQUE_A/SWIFT_PARTICIPANT.xlsx"
        if not os.path.exists(chemin_reel):
            pytest.skip("Fichier de test reel indisponible dans cet environnement")
        faux = self._fichier_depot_natif(chemin_reel, "SWIFT_PARTICIPANT.xlsx")
        df = lire_reporting(faux)
        assert df["pays"].iloc[0] == "INCONNU"


class TestDetectionPaysDansGrandDossierEnglobant:
    """
    Cas reel rencontre : les dossiers de pays ne sont pas forcement au
    premier niveau du dossier depose -- l'utilisateur peut deposer un
    grand dossier englobant (ex. 'CEMAC/CAMEROUN/MOIS AVRIL 2026/
    BANQUE_A/reporting.xlsx'). _deduire_pays doit alors trouver le pays
    ou qu'il se trouve dans le chemin, pas seulement au premier niveau.
    """

    def _fichier_depot_natif(self, chemin_reel, chemin_relatif):
        import io

        class FauxDepotDossierNatif(io.BytesIO):
            pass

        with open(chemin_reel, "rb") as f:
            data = f.read()
        faux = FauxDepotDossierNatif(data)
        faux.name = chemin_relatif
        faux.size = len(data)
        return faux

    def test_pays_trouve_au_deuxieme_niveau(self):
        chemin_reel = "data/sample/Cameroun/MOIS MARS 2026/BANQUE_A/SWIFT_PARTICIPANT.xlsx"
        if not os.path.exists(chemin_reel):
            pytest.skip("Fichier de test reel indisponible dans cet environnement")
        faux = self._fichier_depot_natif(
            chemin_reel, "CEMAC/CAMEROUN/MOIS MARS 2026/BANQUE_A/reporting.xlsx"
        )
        df = lire_reporting(faux)
        assert df["pays"].iloc[0] == "Cameroun"

    def test_pays_trouve_tres_profond_dans_larborescence(self):
        chemin_reel = "data/sample/Cameroun/MOIS MARS 2026/BANQUE_A/SWIFT_PARTICIPANT.xlsx"
        if not os.path.exists(chemin_reel):
            pytest.skip("Fichier de test reel indisponible dans cet environnement")
        faux = self._fichier_depot_natif(
            chemin_reel, "Exports/2026/Referentiels/TCHAD/MOIS JUIN 2026/BANQUE_C/reporting.xlsx"
        )
        df = lire_reporting(faux)
        assert df["pays"].iloc[0] == "Tchad"

    def test_sigle_pays_reconnu_meme_en_profondeur(self):
        chemin_reel = "data/sample/Cameroun/MOIS MARS 2026/BANQUE_A/SWIFT_PARTICIPANT.xlsx"
        if not os.path.exists(chemin_reel):
            pytest.skip("Fichier de test reel indisponible dans cet environnement")
        faux = self._fichier_depot_natif(chemin_reel, "Exports/CMR/Banque_X/reporting.xlsx")
        df = lire_reporting(faux)
        assert df["pays"].iloc[0] == "Cameroun"

    def test_aucun_pays_reconnu_se_rabat_sur_premier_segment(self):
        """Si aucun segment du chemin ne correspond a un pays CEMAC
        connu, DAN se rabat sur le premier segment (visible, pas masque
        en 'INCONNU') plutot que de perdre l'information de dossier."""
        chemin_reel = "data/sample/Cameroun/MOIS MARS 2026/BANQUE_A/SWIFT_PARTICIPANT.xlsx"
        if not os.path.exists(chemin_reel):
            pytest.skip("Fichier de test reel indisponible dans cet environnement")
        faux = self._fichier_depot_natif(chemin_reel, "DossierDivers/Sous/reporting.xlsx")
        df = lire_reporting(faux)
        assert df["pays"].iloc[0] == "DossierDivers"

    def test_priorite_reste_coherente_pour_le_premier_niveau(self):
        """Cas historique (pays directement au premier niveau) toujours
        correctement gere apres le passage a la recherche multi-niveaux."""
        chemin_reel = "data/sample/Cameroun/MOIS MARS 2026/BANQUE_A/SWIFT_PARTICIPANT.xlsx"
        if not os.path.exists(chemin_reel):
            pytest.skip("Fichier de test reel indisponible dans cet environnement")
        faux = self._fichier_depot_natif(chemin_reel, "Cameroun/Banque_A/reporting.xlsx")
        df = lire_reporting(faux)
        assert df["pays"].iloc[0] == "Cameroun"

    def test_plusieurs_pays_dans_un_seul_grand_dossier_sont_bien_separes(self):
        """Reproduction du cas d'usage reel : un seul dossier depose,
        contenant plusieurs pays a l'interieur -- chaque fichier doit
        obtenir le bon pays independamment des autres."""
        chemin_reel = "data/sample/Cameroun/MOIS MARS 2026/BANQUE_A/SWIFT_PARTICIPANT.xlsx"
        if not os.path.exists(chemin_reel):
            pytest.skip("Fichier de test reel indisponible dans cet environnement")
        f_cameroun = self._fichier_depot_natif(chemin_reel, "CEMAC/CAMEROUN/Banque_A/reporting.xlsx")
        f_congo = self._fichier_depot_natif(chemin_reel, "CEMAC/CONGO/Banque_B/reporting.xlsx")
        df_cameroun = lire_reporting(f_cameroun)
        df_congo = lire_reporting(f_congo)
        assert df_cameroun["pays"].iloc[0] == "Cameroun"
        assert df_congo["pays"].iloc[0] == "Congo"


class TestNormalisationMois:
    """
    DAN ne doit pas s'attarder sur la forme exacte des caracteres :
    janvier, JANVIER, Janvier et 1 doivent tous designer le meme mois.
    """

    @pytest.mark.parametrize("valeur_brute,attendu", [
        ("janvier", "Janvier"), ("JANVIER", "Janvier"), ("Janvier", "Janvier"),
        ("1", "Janvier"), ("01", "Janvier"), ("Janv", "Janvier"),
        ("mars", "Mars"), ("MARS", "Mars"), ("3", "Mars"),
        ("avril", "Avril"), ("4", "Avril"), ("04", "Avril"),
        ("decembre", "Décembre"), ("DECEMBRE", "Décembre"), ("12", "Décembre"), ("DEC", "Décembre"),
        ("aout", "Août"), ("AOUT", "Août"), ("8", "Août"),
        ("juillet", "Juillet"), ("JUIL", "Juillet"),
    ])
    def test_variantes_reconnues(self, valeur_brute, attendu):
        from logic.donnees import normaliser_mois
        assert normaliser_mois(valeur_brute) == attendu

    def test_valeur_non_reconnue_passe_telle_quelle(self):
        from logic.donnees import normaliser_mois
        assert normaliser_mois("PeriodeInconnue") == "PeriodeInconnue"

    def test_valeur_vide_ou_none_ne_plante_pas(self):
        from logic.donnees import normaliser_mois
        assert normaliser_mois("") == ""
        assert normaliser_mois(None) is None


class TestDetectionMoisDepuisDossier:
    """
    Cas reel rencontre : les dossiers de reporting incluent un segment
    "MOIS <NOM> <ANNEE>" (ex. "MOIS MARS 2026") -- DAN doit lire le mois
    depuis cette organisation des dossiers, sans l'inventer, avec
    reconnaissance de la casse (janvier = JANVIER).
    """

    def _fichier_depot_natif(self, chemin_reel, chemin_relatif):
        import io

        class FauxDepotDossierNatif(io.BytesIO):
            pass

        with open(chemin_reel, "rb") as f:
            data = f.read()
        faux = FauxDepotDossierNatif(data)
        faux.name = chemin_relatif
        faux.size = len(data)
        return faux

    def test_mois_et_annee_lus_depuis_le_dossier_reel(self):
        chemin_reel = "data/sample/Cameroun/MOIS MARS 2026/BANQUE_A/SWIFT_PARTICIPANT.xlsx"
        if not os.path.exists(chemin_reel):
            pytest.skip("Fichier de test reel indisponible dans cet environnement")
        faux = self._fichier_depot_natif(chemin_reel, "CAMEROUN/MOIS MARS 2026/BANQUE_A/reporting.xlsx")
        df = lire_reporting(faux)
        assert df["mois"].iloc[0] == "Mars"
        assert df["annee"].iloc[0] == "2026"

    def test_casse_differente_donne_le_meme_resultat(self):
        chemin_reel = "data/sample/Cameroun/MOIS MARS 2026/BANQUE_A/SWIFT_PARTICIPANT.xlsx"
        if not os.path.exists(chemin_reel):
            pytest.skip("Fichier de test reel indisponible dans cet environnement")
        f_minuscule = self._fichier_depot_natif(chemin_reel, "Tchad/MOIS janvier 2026/Banque/reporting.xlsx")
        f_majuscule = self._fichier_depot_natif(chemin_reel, "Tchad/MOIS JANVIER 2026/Banque/reporting.xlsx")
        df_min = lire_reporting(f_minuscule)
        df_maj = lire_reporting(f_majuscule)
        assert df_min["mois"].iloc[0] == df_maj["mois"].iloc[0] == "Janvier"

    def test_aucun_mois_dans_le_dossier_laisse_mois_none(self):
        chemin_reel = "data/sample/Cameroun/MOIS MARS 2026/BANQUE_A/SWIFT_PARTICIPANT.xlsx"
        if not os.path.exists(chemin_reel):
            pytest.skip("Fichier de test reel indisponible dans cet environnement")
        faux = self._fichier_depot_natif(chemin_reel, "Cameroun/Banque_A/reporting.xlsx")
        df = lire_reporting(faux)
        assert df["mois"].iloc[0] is None


class TestNormalisationPays:
    """
    DAN ne doit pas s'attarder sur la forme exacte des caracteres :
    CAMEROUN, Cameroun, CMR et cmr doivent tous designer le meme pays.
    """

    @pytest.mark.parametrize("valeur_brute,attendu", [
        ("CAMEROUN", "Cameroun"), ("Cameroun", "Cameroun"), ("cameroun", "Cameroun"),
        ("CMR", "Cameroun"), ("cmr", "Cameroun"), ("Cameroon", "Cameroun"),
        ("TCHAD", "Tchad"), ("chad", "Tchad"), ("TD", "Tchad"), ("TCD", "Tchad"),
        ("CONGO", "Congo"), ("congo", "Congo"), ("COG", "Congo"), ("Congo Brazzaville", "Congo"),
        ("RCA", "Centrafrique"), ("CAF", "Centrafrique"),
        ("République Centrafricaine", "Centrafrique"), ("centrafrique", "Centrafrique"),
        ("GABON", "Gabon"), ("gabon", "Gabon"), ("GAB", "Gabon"),
        ("Guinée Équatoriale", "Guinée Équatoriale"), ("guinee equatoriale", "Guinée Équatoriale"),
        ("GNQ", "Guinée Équatoriale"), ("GQ", "Guinée Équatoriale"),
    ])
    def test_variantes_reconnues(self, valeur_brute, attendu):
        assert normaliser_pays(valeur_brute) == attendu

    def test_valeur_non_reconnue_passe_telle_quelle(self):
        """Un nom de dossier qui ne correspond a aucun des six pays CEMAC
        doit rester visible tel quel, pas etre masque ou rejete."""
        assert normaliser_pays("Nigeria") == "Nigeria"
        assert normaliser_pays("DossierDivers") == "DossierDivers"

    def test_valeur_vide_ou_none_ne_plante_pas(self):
        assert normaliser_pays("") == ""
        assert normaliser_pays(None) is None

    def test_toutes_les_valeurs_normalisees_sont_dans_pays_cemac_ou_passent_telles_quelles(self):
        for pays in PAYS_CEMAC:
            assert normaliser_pays(pays) == pays

    def test_espaces_superflus_sont_nettoyes(self):
        assert normaliser_pays("  Cameroun  ") == "Cameroun"
