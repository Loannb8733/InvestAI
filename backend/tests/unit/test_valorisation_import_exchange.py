"""Mise en euros des prix et des frais d'un mouvement importé.

Un exchange cote ses paires dans sa devise et prélève ses frais dans le jeton
qui l'arrange. Ces conversions décident du coût de revient, donc de la
plus-value imposable — et vivaient sans test au milieu d'une boucle d'écriture.
"""

import logging

import pytest

from app.services.exchange_import_valuation import (
    convertir_frais_en_eur,
    est_cote_en_usd,
    frais_a_convertir,
    lire_prix_jeton,
)


class TestDeviseDeCotation:
    @pytest.mark.parametrize("paire", ["BTCUSDT", "ETHUSDC", "SOLBUSD", "ADAFDUSD", "XRPUSD"])
    def test_les_paires_en_dollar_demandent_une_conversion(self, paire):
        assert est_cote_en_usd(paire) is True

    @pytest.mark.parametrize("paire", ["BTCEUR", "ETHEUR", "BTCGBP", "SOLBTC"])
    def test_les_autres_paires_sont_laissees_telles_quelles(self, paire):
        assert est_cote_en_usd(paire) is False

    def test_c_est_le_suffixe_qui_compte_pas_l_actif(self):
        """« USDCEUR » est de l'USDC coté en euros : aucune conversion."""
        assert est_cote_en_usd("USDCEUR") is False

    def test_symbole_absent(self):
        assert est_cote_en_usd("") is False


class TestFraisAConvertir:
    @pytest.mark.parametrize("devise", ["EUR", "USD", "GBP", "CAD", "JPY"])
    def test_une_devise_exploitable_ne_demande_rien(self, devise):
        assert frais_a_convertir(devise, 10.0) is False

    def test_un_jeton_demande_une_conversion(self):
        assert frais_a_convertir("BNB", 0.01) is True

    def test_des_frais_nuls_n_ont_rien_a_convertir(self):
        assert frais_a_convertir("BNB", 0.0) is False

    def test_des_frais_negatifs_non_plus(self):
        assert frais_a_convertir("BNB", -1.0) is False


class TestConversionDesFrais:
    def test_frais_dans_le_jeton_echange(self):
        """Des frais en PEPE sur un achat de PEPE : le prix de l'actif suffit."""
        assert convertir_frais_en_eur(100.0, "PEPE", "PEPE", prix_actif_eur=0.02) == 2.0

    def test_frais_dans_un_autre_jeton(self):
        """Des frais en BNB sur un achat de PEPE : il faut le cours du BNB."""
        montant = convertir_frais_en_eur(0.01, "BNB", "PEPE", prix_actif_eur=0.02, prix_jeton_eur=500.0)
        assert montant == 5.0

    def test_le_cours_du_jeton_prime_sur_celui_de_l_actif(self):
        montant = convertir_frais_en_eur(2.0, "BNB", "PEPE", prix_actif_eur=1000.0, prix_jeton_eur=500.0)
        assert montant == 1000.0, "le cours du BNB, pas celui du PEPE"

    def test_repli_sur_le_prix_de_l_actif(self):
        """Comportement d'origine, épinglé sans être approuvé : faute de cours
        propre, les frais sont valorisés au cours de l'actif échangé — du BNB
        au prix du PEPE. Le montant n'a pas de sens en soi, mais un zéro
        minorerait le coût de revient et gonflerait la plus-value imposable."""
        montant = convertir_frais_en_eur(2.0, "BNB", "PEPE", prix_actif_eur=3.0, prix_jeton_eur=0.0)
        assert montant == 6.0

    def test_sans_aucun_cours_les_frais_sont_abandonnes(self):
        assert convertir_frais_en_eur(2.0, "BNB", "PEPE", prix_actif_eur=0.0, prix_jeton_eur=0.0) == 0.0

    def test_meme_jeton_sans_prix_ne_se_replie_pas(self):
        """Le repli n'existe que pour un jeton tiers : ici il n'y a rien
        d'autre à essayer."""
        assert convertir_frais_en_eur(100.0, "PEPE", "PEPE", prix_actif_eur=0.0) == 0.0

    def test_montant_nul(self):
        assert convertir_frais_en_eur(0.0, "BNB", "PEPE", prix_actif_eur=1.0, prix_jeton_eur=1.0) == 0.0


class TestLectureDuCoursDuJeton:
    def test_cle_en_minuscules(self):
        assert lire_prix_jeton({"bnb": {"price": 500.0}}, "BNB") == 500.0

    def test_cle_en_majuscules(self):
        assert lire_prix_jeton({"BNB": {"price": 500.0}}, "bnb") == 500.0

    def test_jeton_absent(self):
        assert lire_prix_jeton({"eth": {"price": 2000.0}}, "BNB") == 0.0

    def test_reponse_vide(self):
        assert lire_prix_jeton({}, "BNB") == 0.0

    def test_reponse_sans_prix(self):
        assert lire_prix_jeton({"bnb": {}}, "BNB") == 0.0

    def test_reponse_malformee_ne_leve_pas(self):
        """Une source qui rend autre chose qu'un dictionnaire ne doit pas faire
        échouer tout l'import."""
        assert lire_prix_jeton({"bnb": "500"}, "BNB") == 0.0


class TestFraisApproximatifsVisibles:
    """Un repli qui change le coût de revient doit se voir en production.

    Au niveau DEBUG, ces messages n'apparaissaient jamais : des frais valorisés
    au cours d'un autre jeton, ou purement abandonnés, passaient pour exacts.
    """

    NOM_JOURNAL = "app.services.exchange_import_valuation"

    def _avertissements(self, caplog):
        return [r for r in caplog.records if r.name == self.NOM_JOURNAL and r.levelno == logging.WARNING]

    def test_le_repli_sur_le_cours_de_l_actif_est_signale(self, caplog):
        caplog.set_level("DEBUG", logger=self.NOM_JOURNAL)
        convertir_frais_en_eur(2.0, "BNB", "PEPE", prix_actif_eur=3.0, prix_jeton_eur=0.0)
        messages = [r.getMessage() for r in self._avertissements(caplog)]
        assert len(messages) == 1
        assert "BNB" in messages[0] and "PEPE" in messages[0] and "approximatif" in messages[0]

    def test_des_frais_abandonnes_faute_de_tout_cours_sont_signales(self, caplog):
        caplog.set_level("DEBUG", logger=self.NOM_JOURNAL)
        convertir_frais_en_eur(2.0, "BNB", "PEPE", prix_actif_eur=0.0, prix_jeton_eur=0.0)
        messages = [r.getMessage() for r in self._avertissements(caplog)]
        assert len(messages) == 1
        assert "abandonnés" in messages[0] and "BNB" in messages[0]

    def test_des_frais_dans_l_actif_sans_cours_sont_signales(self, caplog):
        caplog.set_level("DEBUG", logger=self.NOM_JOURNAL)
        convertir_frais_en_eur(100.0, "PEPE", "PEPE", prix_actif_eur=0.0)
        messages = [r.getMessage() for r in self._avertissements(caplog)]
        assert len(messages) == 1
        assert "abandonnés" in messages[0] and "PEPE" in messages[0]

    def test_une_conversion_exacte_reste_silencieuse(self, caplog):
        caplog.set_level("DEBUG", logger=self.NOM_JOURNAL)
        convertir_frais_en_eur(2.0, "BNB", "PEPE", prix_actif_eur=3.0, prix_jeton_eur=500.0)
        convertir_frais_en_eur(100.0, "PEPE", "PEPE", prix_actif_eur=0.02)
        convertir_frais_en_eur(0.0, "BNB", "PEPE", prix_actif_eur=0.0)
        assert self._avertissements(caplog) == []
