"""Filet sur la devise attribuée à chaque transaction importée d'un exchange.

`_resolve_trade_fx` décide, pour chaque trade venu d'un exchange, dans quelle
devise il est libellé et à quel taux le ramener en euros. C'est le cœur de
FIN-01 : la synchronisation enregistrait tout en `EUR` en dur, même quand le
prix venait d'une paire en dollars — une erreur de **8 à 9 %** sur le prix de
revient, donc sur la plus-value imposable.

`tasks/sync_exchanges.py` est couvert à 32 %. Cette fonction ne touche la base
qu'à travers le service de change, que le filet double : le reste du chemin est
parcouru pour de vrai, `quote_fx_currency` compris.

Sa règle de prudence est la clé : on ne libelle jamais une ligne dans une devise
étrangère sans détenir le taux historique correspondant. Le faire laisserait un
taux implicite de 1 — un prix en dollars compté comme des euros, soit exactement
l'écart que FIN-01 a corrigé.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.tasks.sync_exchanges import _resolve_trade_fx

QUAND = datetime(2026, 3, 15, tzinfo=timezone.utc)


class ServiceDeChange:
    """Double du service de taux historiques, qui note ce qu'on lui demande."""

    def __init__(self, taux=None):
        self._taux = taux
        self.appels = []

    async def get_rate(self, jour, depuis, vers):
        self.appels.append((jour, depuis, vers))
        return self._taux


class TestSansConversion:
    @pytest.mark.parametrize("quote", ["EUR", "EURT", "EURC", "eur"])
    async def test_une_paire_en_euro_ne_demande_aucun_taux(self, quote):
        fx = ServiceDeChange(Decimal("0.92"))

        assert await _resolve_trade_fx(fx, quote, QUAND) == ("EUR", None)
        assert fx.appels == []

    async def test_une_paire_sans_devise_reconnue_reste_en_euro(self):
        # `split_pair` rend un quote nul sur un symbole qu'il ne sait pas
        # découper : mieux vaut le repli que d'inventer une devise.
        fx = ServiceDeChange(Decimal("0.92"))

        assert await _resolve_trade_fx(fx, None, QUAND) == ("EUR", None)
        assert fx.appels == []

    @pytest.mark.parametrize("quote", ["BTC", "ETH", "BNB"])
    async def test_une_paire_cotee_en_crypto_reste_en_euro(self, quote):
        """Une cotation en bitcoin n'est pas une devise au sens du change.

        Ramener un prix libellé en BTC demanderait le cours du bitcoin à la date
        du trade, non un taux de change. La fonction s'en abstient plutôt que
        d'appeler le service avec une devise qu'il ne connaît pas.
        """
        fx = ServiceDeChange(Decimal("0.92"))

        assert await _resolve_trade_fx(fx, quote, QUAND) == ("EUR", None)
        assert fx.appels == []

    @pytest.mark.parametrize("quote", ["XYZ", "SHIB", ""])
    async def test_un_quote_inconnu_reste_en_euro(self, quote):
        fx = ServiceDeChange(Decimal("0.92"))

        assert await _resolve_trade_fx(fx, quote, QUAND) == ("EUR", None)
        assert fx.appels == []


class TestConversion:
    @pytest.mark.parametrize("quote", ["USD", "USDT", "USDC", "BUSD", "FDUSD", "TUSD", "USDP", "DAI"])
    async def test_les_stablecoins_en_dollar_se_ramenent_tous_au_dollar(self, quote):
        """Le stablecoin précis ne change pas la conversion.

        USDT, USDC, BUSD… suivent tous le dollar : c'est ce dollar qu'il faut
        convertir, et un seul taux les couvre. La devise enregistrée est donc
        « USD », jamais « USDT ».
        """
        fx = ServiceDeChange(Decimal("0.92"))

        assert await _resolve_trade_fx(fx, quote, QUAND) == ("USD", Decimal("0.92"))
        assert fx.appels == [(QUAND.date(), "USD", "EUR")]

    @pytest.mark.parametrize("quote", ["GBP", "JPY", "CHF", "CAD", "AUD"])
    async def test_les_autres_fiats_sont_conservees_telles_quelles(self, quote):
        fx = ServiceDeChange(Decimal("1.17"))

        assert await _resolve_trade_fx(fx, quote, QUAND) == (quote, Decimal("1.17"))
        assert fx.appels == [(QUAND.date(), quote, "EUR")]

    async def test_le_taux_est_demande_a_la_date_du_trade(self):
        # Un taux d'aujourd'hui appliqué à un achat de 2024 fausserait le prix de
        # revient de tout l'écart de change accumulé depuis.
        fx = ServiceDeChange(Decimal("0.88"))
        ancien = datetime(2024, 6, 1, 14, 30, tzinfo=timezone.utc)

        await _resolve_trade_fx(fx, "USDT", ancien)

        assert fx.appels == [(ancien.date(), "USD", "EUR")]

    async def test_le_taux_rendu_est_bien_celui_du_service(self):
        # Deux taux distincts pour que l'égalité ne puisse pas être vraie par
        # hasard sur une valeur par défaut.
        assert (await _resolve_trade_fx(ServiceDeChange(Decimal("0.85")), "USD", QUAND))[1] == Decimal("0.85")
        assert (await _resolve_trade_fx(ServiceDeChange(Decimal("0.95")), "USD", QUAND))[1] == Decimal("0.95")


class TestPrudence:
    async def test_sans_taux_disponible_la_ligne_reste_en_euro(self):
        """La règle qui protège du défaut d'origine.

        Libeller la ligne « USD » sans taux la laisserait avec une conversion
        implicite de 1 : un prix en dollars compté comme des euros, soit l'écart
        de 8 à 9 % que FIN-01 a corrigé. Le repli est explicite et journalisé.
        """
        fx = ServiceDeChange(None)

        assert await _resolve_trade_fx(fx, "USDT", QUAND) == ("EUR", None)
        assert fx.appels == [(QUAND.date(), "USD", "EUR")]

    async def test_sans_service_de_change_la_ligne_reste_en_euro(self):
        # Même raison : pas de taux, pas de devise étrangère.
        assert await _resolve_trade_fx(None, "USDT", QUAND) == ("EUR", None)
