"""Filet de caractérisation du calendrier de marché (`market_data_service`).

Le module est couvert à **0 %**. Ses cinq fonctions de niveau module sont
pourtant pures et décident de choses concrètes : si un prix d'action est
considéré comme frais ou périmé, et donc s'il faut le rafraîchir.

Le calcul d'heure d'été se déclare lui-même « approximate ». Ces tests mesurent
de combien, plutôt que de le supposer juste : ils épinglent le comportement
**actuel**, écarts compris, et nomment les jours où il diverge de la règle
réelle.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services import market_data_service as mds
from app.services.market_data_service import (
    MarketExchange,
    _detect_exchange,
    _is_dst,
    is_market_closed_today,
    is_market_open,
    price_staleness_hours,
)


def utc(annee, mois, jour, heure=12, minute=0):
    return datetime(annee, mois, jour, heure, minute, tzinfo=timezone.utc)


class TestDetectionDeLaBourse:
    def test_un_ticker_sans_suffixe_est_americain(self):
        assert _detect_exchange("AAPL") is MarketExchange.NYSE

    def test_les_suffixes_connus_sont_reconnus(self):
        assert _detect_exchange("MC.PA") is MarketExchange.EURONEXT
        assert _detect_exchange("SAP.DE") is MarketExchange.XETRA
        assert _detect_exchange("HSBA.L") is MarketExchange.LSE
        assert _detect_exchange("RY.TO") is MarketExchange.TSX

    def test_le_suffixe_est_insensible_a_la_casse(self):
        assert _detect_exchange("mc.pa") is MarketExchange.EURONEXT

    def test_seul_le_dernier_suffixe_compte(self):
        assert _detect_exchange("BRK.B.PA") is MarketExchange.EURONEXT

    def test_un_suffixe_inconnu_donne_une_bourse_inconnue(self):
        assert _detect_exchange("XYZ.ZZ") is MarketExchange.UNKNOWN

    def test_une_bourse_inconnue_est_reputee_toujours_ouverte(self):
        """Faute d'horaires, le module suppose le marché ouvert.

        Conséquence concrète : sur un ticker à suffixe non reconnu, un prix
        vieux de plus de 15 minutes est déclaré périmé même la nuit et le
        week-end — le régime le plus strict s'applique en permanence.
        """
        # Un samedi, à 3 h du matin.
        assert is_market_open("XYZ.ZZ", utc(2026, 9, 5, 3)) is True


class TestHeureDEte:
    """L'approximation du DST, mesurée plutôt que supposée.

    En 2026 : DST américain du 8 mars au 1er novembre, européen du 29 mars au
    25 octobre.
    """

    def test_le_debut_du_dst_americain_tombe_juste(self):
        assert _is_dst(utc(2026, 3, 7), MarketExchange.NYSE) is False
        assert _is_dst(utc(2026, 3, 8), MarketExchange.NYSE) is True

    def test_la_fin_du_dst_americain_est_en_retard_de_six_jours(self):
        """Le DST américain finit le 1er novembre 2026 ; le code le prolonge au 6.

        La règle codée est `day < 7`, calée sur « 1er dimanche de novembre »
        pris au pire cas. Du 1er au 6 novembre, l'offset appliqué au NYSE est
        donc -4 au lieu de -5 : le marché est réputé ouvrir une heure trop tôt
        et fermer une heure trop tôt.
        """
        assert _is_dst(utc(2026, 11, 1), MarketExchange.NYSE) is True  # DST déjà fini
        assert _is_dst(utc(2026, 11, 6), MarketExchange.NYSE) is True  # encore
        assert _is_dst(utc(2026, 11, 7), MarketExchange.NYSE) is False  # enfin

    def test_le_debut_du_dst_europeen_est_en_avance_de_quatre_jours(self):
        """Le DST européen commence le 29 mars 2026 ; le code l'avance au 25."""
        assert _is_dst(utc(2026, 3, 24), MarketExchange.EURONEXT) is False
        assert _is_dst(utc(2026, 3, 25), MarketExchange.EURONEXT) is True  # 4 jours trop tôt

    def test_la_fin_du_dst_europeen_tombe_juste(self):
        assert _is_dst(utc(2026, 10, 24), MarketExchange.EURONEXT) is True
        assert _is_dst(utc(2026, 10, 25), MarketExchange.EURONEXT) is False

    def test_le_canada_suit_les_regles_americaines(self):
        assert _is_dst(utc(2026, 11, 5), MarketExchange.TSX) is True

    def test_le_royaume_uni_suit_les_regles_europeennes(self):
        assert _is_dst(utc(2026, 11, 5), MarketExchange.LSE) is False


class TestOuvertureDesMarches:
    def test_le_nyse_est_ouvert_en_pleine_seance(self):
        # Jeudi 10 septembre 2026, 15 h UTC = 11 h à New York (DST, -4).
        assert is_market_open("AAPL", utc(2026, 9, 10, 15)) is True

    def test_le_nyse_est_ferme_avant_l_ouverture(self):
        # 12 h UTC = 8 h à New York, avant 9 h 30.
        assert is_market_open("AAPL", utc(2026, 9, 10, 12)) is False

    def test_les_bornes_d_ouverture_et_de_fermeture_sont_incluses(self):
        # 13 h 30 UTC = 9 h 30 local, 20 h UTC = 16 h local.
        assert is_market_open("AAPL", utc(2026, 9, 10, 13, 30)) is True
        assert is_market_open("AAPL", utc(2026, 9, 10, 20, 0)) is True

    def test_le_week_end_ferme_tout(self):
        assert is_market_open("AAPL", utc(2026, 9, 12, 15)) is False  # samedi
        assert is_market_open("AAPL", utc(2026, 9, 13, 15)) is False  # dimanche

    def test_un_jour_ferie_ferme_la_bourse_concernee(self):
        # Thanksgiving 2026 : le NYSE ferme, Euronext non.
        assert is_market_open("AAPL", utc(2026, 11, 26, 15)) is False
        assert is_market_open("MC.PA", utc(2026, 11, 26, 10)) is True

    def test_le_nasdaq_partage_le_calendrier_ferie_du_nyse(self):
        # Le suffixe absent renvoie NYSE ; l'alias existe pour les tickers
        # explicitement rattachés au NASDAQ dans `_MARKET_HOLIDAYS_2026`.
        assert mds._MARKET_HOLIDAYS_2026["NASDAQ"] == mds._MARKET_HOLIDAYS_2026["NYSE"]

    def test_l_erreur_de_dst_de_novembre_decale_l_ouverture_d_une_heure(self):
        """Le 2 novembre 2026 à 13 h 45 UTC, le NYSE est **fermé** en réalité.

        L'heure d'été américaine s'est terminée la veille : 13 h 45 UTC vaut
        8 h 45 à New York, avant l'ouverture de 9 h 30. Le module, qui croit
        encore au DST, calcule 9 h 45 et déclare le marché ouvert.

        Ce test épingle l'écart, il ne l'approuve pas.
        """
        assert is_market_open("AAPL", utc(2026, 11, 2, 13, 45)) is True

    def test_les_jours_feries_ne_sont_connus_que_pour_2026(self):
        # La table est codée en dur. En 2027, le 1er janvier — un vendredi —
        # est traité comme un jour ouvré normal.
        assert is_market_closed_today("AAPL", utc(2027, 1, 1)) is False


class TestFermetureDeLaJournee:
    def test_le_week_end_ferme_la_journee_entiere(self):
        assert is_market_closed_today("AAPL", utc(2026, 9, 12, 3)) is True

    def test_un_jour_ferie_ferme_la_journee_entiere(self):
        assert is_market_closed_today("AAPL", utc(2026, 12, 25)) is True

    def test_hors_seance_un_jour_ouvre_n_est_pas_une_fermeture(self):
        # 3 h du matin un jeudi : le marché n'est pas ouvert, mais la journée
        # n'est pas fermée pour autant. La distinction commande le seuil de
        # fraîcheur appliqué aux prix.
        assert is_market_closed_today("AAPL", utc(2026, 9, 10, 3)) is False
        assert is_market_open("AAPL", utc(2026, 9, 10, 3)) is False


class TestFraicheurDesPrix:
    """Trois régimes de tolérance, selon l'état du marché."""

    def _figer(self, monkeypatch, *, ferme_aujourdhui: bool, ouvert: bool):
        monkeypatch.setattr(mds, "is_market_closed_today", lambda *a, **k: ferme_aujourdhui)
        monkeypatch.setattr(mds, "is_market_open", lambda *a, **k: ouvert)

    def test_marche_ouvert_la_tolerance_est_de_quinze_minutes(self, monkeypatch):
        self._figer(monkeypatch, ferme_aujourdhui=False, ouvert=True)
        maintenant = datetime.now(timezone.utc)

        _, frais = price_staleness_hours("AAPL", maintenant - timedelta(minutes=10))
        _, perime = price_staleness_hours("AAPL", maintenant - timedelta(minutes=20))

        assert frais is True
        assert perime is False

    def test_hors_seance_un_jour_ouvre_la_tolerance_monte_a_dix_huit_heures(self, monkeypatch):
        self._figer(monkeypatch, ferme_aujourdhui=False, ouvert=False)
        maintenant = datetime.now(timezone.utc)

        _, frais = price_staleness_hours("AAPL", maintenant - timedelta(hours=17))
        _, perime = price_staleness_hours("AAPL", maintenant - timedelta(hours=19))

        assert frais is True
        assert perime is False

    def test_marche_ferme_pour_la_journee_la_tolerance_monte_a_soixante_douze_heures(self, monkeypatch):
        # Le seuil couvre un long week-end : vendredi soir à lundi matin.
        self._figer(monkeypatch, ferme_aujourdhui=True, ouvert=False)
        maintenant = datetime.now(timezone.utc)

        _, frais = price_staleness_hours("AAPL", maintenant - timedelta(hours=70))
        _, perime = price_staleness_hours("AAPL", maintenant - timedelta(hours=74))

        assert frais is True
        assert perime is False

    def test_l_age_brut_est_rendu_quel_que_soit_le_verdict(self, monkeypatch):
        self._figer(monkeypatch, ferme_aujourdhui=False, ouvert=True)
        maintenant = datetime.now(timezone.utc)

        age, acceptable = price_staleness_hours("AAPL", maintenant - timedelta(hours=5))

        assert age == pytest.approx(5.0, abs=0.01)
        assert acceptable is False
