# -*- coding: utf-8 -*-
"""
Tests de logic.interpretation : coherence du niveau de risque affiche entre
le badge, la jauge et les textes narratifs. C'est ici qu'a ete trouve le bug
le plus significatif de DAN (un incident isole mineur ressortait "Critique"
sur la jauge et dans le texte, mais "Moyen" sur le badge, sur le meme
ecran) -- ces tests existent pour qu'il ne puisse plus jamais revenir
silencieusement.
"""
import re
import pytest

from logic.interpretation import (
    interpretation_absolue, interpreter_score_global, interpreter_reseau,
    SEUILS_GRAVITE_ABSOLUE,
)
from logic.graphiques import jauge_risque
import pandas as pd


class TestInterpretationAbsolue:

    def test_incident_isole_mineur_nest_pas_critique(self):
        """Reproduction exacte du bug historique : un seul evenement de
        faible gravite (le seul du mois) ne doit pas etre classe Critique
        sous pretexte qu'il represente 100% du score relatif."""
        info = interpretation_absolue(4.0)
        assert info["niveau"] != "Critique"

    def test_cas_reellement_grave_reste_critique(self):
        """A l'inverse, un score cumule genuinement eleve doit rester
        Critique -- le correctif ne doit pas sur-corriger."""
        info = interpretation_absolue(30.0)
        assert info["niveau"] == "Critique"

    def test_zero_est_tres_faible(self):
        assert interpretation_absolue(0)["niveau"] == "Très faible"

    @pytest.mark.parametrize("gravite,niveau_attendu", [
        (0, "Très faible"),
        (0.4, "Très faible"),
        (0.5, "Faible"),
        (2.9, "Faible"),
        (3, "Moyen"),
        (9.9, "Moyen"),
        (10, "Élevé"),
        (24.9, "Élevé"),
        (25, "Critique"),
        (100, "Critique"),
    ])
    def test_seuils_exacts(self, gravite, niveau_attendu):
        """Verifie les bornes exactes de l'echelle -- si les seuils
        provisoires changent un jour, ce test doit etre mis a jour en
        connaissance de cause, pas casser silencieusement ailleurs."""
        assert interpretation_absolue(gravite)["niveau"] == niveau_attendu

    def test_valeur_negative_traitee_comme_zero(self):
        """Robustesse : une gravite negative (ne devrait jamais arriver)
        ne doit pas faire planter le calcul."""
        info = interpretation_absolue(-5)
        assert info["niveau"] == "Très faible"


class TestCoherenceEntreAffichages:
    """
    Ces tests comparent DIRECTEMENT le niveau produit par les differentes
    fonctions d'affichage pour un MEME cas -- c'est cette coherence
    croisee qui avait ete rompue par le bug historique.
    """

    def _score_reseau_isole(self, gravite):
        return pd.DataFrame({
            "domaine": ["SWIFT", "SYGMA", "SYSTAC", "RESEAU"],
            "gravite": [gravite, 0, 0, 0],
            "score_100": [100.0, 0, 0, 0],
        })

    def test_badge_et_jauge_saccordent_sur_incident_isole(self):
        gravite = 4.0
        score_reseau = self._score_reseau_isole(gravite)
        total = score_reseau["gravite"].sum()

        niveau_badge = interpretation_absolue(total)["niveau"]
        fig = jauge_risque(total)
        niveau_jauge = re.search(r">([^<]+)</span>", fig.data[0].title.text).group(1)

        assert niveau_badge == niveau_jauge

    def test_badge_et_texte_narratif_saccordent_sur_incident_isole(self):
        gravite = 4.0
        score_reseau = self._score_reseau_isole(gravite)
        total = score_reseau["gravite"].sum()

        niveau_badge = interpretation_absolue(total)["niveau"]
        texte = interpreter_score_global(score_reseau, 1, 1)
        niveau_texte = texte.split("niveau de risque **")[1].split("**")[0]

        assert niveau_badge.lower() == niveau_texte.lower()

    def test_badge_et_texte_par_systeme_saccordent(self):
        gravite_swift = 4.0
        niveau_badge = interpretation_absolue(gravite_swift)["niveau"]
        texte = interpreter_reseau("SWIFT", gravite_swift, pd.DataFrame())
        niveau_texte = texte.split("**")[-2]

        assert niveau_badge.lower() == niveau_texte.lower()

    def test_coherence_sur_cas_reellement_grave(self):
        """Meme verification, mais sur un cas ou Critique est justifie --
        garantit que la coherence tient dans les deux sens."""
        gravite = 32.79
        score_reseau = self._score_reseau_isole(gravite)
        total = score_reseau["gravite"].sum()

        niveau_badge = interpretation_absolue(total)["niveau"]
        fig = jauge_risque(total)
        niveau_jauge = re.search(r">([^<]+)</span>", fig.data[0].title.text).group(1)

        assert niveau_badge == niveau_jauge == "Critique"


class TestJaugeGraphique:

    def test_jauge_narrete_jamais_hors_cadre(self):
        """La plage de la jauge doit toujours depasser la valeur affichee,
        meme pour un score exceptionnellement eleve."""
        fig = jauge_risque(1000)
        plage_max = fig.data[0].gauge.axis.range[1]
        assert plage_max > 1000

    def test_jauge_gere_un_score_nul(self):
        fig = jauge_risque(0)
        assert fig.data[0].value == 0


class TestSeuilsConfigurables:
    """
    Les seuils de gravite sont desormais parametrables par l'agent (voir
    Parametres -> Seuils de score), et non plus une valeur figee dans le
    code -- interpretation_absolue() doit refleter la configuration
    active, avec repli sur les valeurs de depart si aucune config valide
    n'est trouvee ou si des seuils explicites sont passes en parametre.
    """

    def test_seuils_explicites_prioritaires_sur_la_configuration(self):
        """Passer des seuils explicites doit toujours l'emporter, sans
        toucher a la configuration persistee."""
        info = interpretation_absolue(6, seuils=[10, 5, 2, 0.5])
        assert info["niveau"] == "Élevé"

    def test_configuration_personnalisee_est_appliquee(self, dossier_config_isole):
        from logic.configuration import charger_configuration, sauvegarder_configuration
        config = charger_configuration()
        config["seuils_gravite"] = [10, 5, 2, 0.5]
        sauvegarder_configuration(config)

        assert interpretation_absolue(6)["niveau"] == "Élevé"

    def test_seuils_invalides_en_configuration_se_rabattent_sur_le_depart(self, dossier_config_isole):
        """Une configuration corrompue ou incoherente (ex. ordre inverse)
        ne doit jamais faire planter le calcul -- repli silencieux sur
        les seuils de depart."""
        from logic.configuration import charger_configuration, sauvegarder_configuration
        config = charger_configuration()
        config["seuils_gravite"] = [1, 5, 10, 25]  # ordre inverse, invalide
        sauvegarder_configuration(config)

        # Avec les seuils de depart [25,10,3,0.5], gravite=6 -> Moyen
        assert interpretation_absolue(6)["niveau"] == "Moyen"

    def test_validation_seuils(self):
        from logic.configuration import valider_seuils_gravite
        assert valider_seuils_gravite([25, 10, 3, 0.5])[0] is True
        assert valider_seuils_gravite([3, 10, 25, 0.5])[0] is False  # ordre inverse
        assert valider_seuils_gravite([25, 10, -3, 0.5])[0] is False  # negatif
        assert valider_seuils_gravite([25, 10, 3])[0] is False  # pas 4 valeurs
        assert valider_seuils_gravite([25, 25, 3, 0.5])[0] is False  # pas strictement decroissant (egalite)
