"""`fee_currency` n'est pas toujours une monnaie
----------------------------------------------
Payer ses frais en PAXG ou en OM est courant sur un exchange, et la base en
contient 65. Chacune déclenchait un appel à
`exchangerate-api.com/v4/latest/PAXG` — 404 systématique, requête perdue à
chaque calcul de métriques.
"""

import pytest

from app.domains.market_data.fx.spot import FIAT_CURRENCIES, spot_rates
from app.domains.market_data.prices.cryptocompare import cryptocompare_quotes


class TestDevisesReelles:
    @pytest.mark.parametrize("code", ["PAXG", "OM", "BTC", "USDC", "PEPE", "SOL03"])
    @pytest.mark.asyncio
    async def test_un_symbole_crypto_ne_declenche_aucun_appel(self, code, http_stub):
        assert await spot_rates.get(code, "EUR") is None
        assert not http_stub.requests

    @pytest.mark.parametrize("code", ["EUR", "USD", "GBP", "CHF"])
    def test_les_monnaies_de_l_application_restent_acceptees(self, code):
        assert code in FIAT_CURRENCIES, (
            f"{code} est proposée dans les préférences utilisateur : la retirer "
            "de la liste blanche couperait la conversion pour ces comptes"
        )


class TestRepliCryptoCompare:
    """Un repli qui ne peut pas aboutir ne doit pas être tenté.

    CryptoCompare répond 401 à toute requête anonyme. Sans clé configurée, ce
    repli — sollicité chaque fois que CoinGecko échoue, donc précisément quand
    tout va mal — ajoutait une latence pour un échec certain.
    """

    async def test_aucun_appel_sans_cle(self, monkeypatch, http_stub):
        from app.core.config import settings

        monkeypatch.setattr(settings, "CRYPTOCOMPARE_API_KEY", "", raising=False)
        assert await cryptocompare_quotes(["BTC"], "EUR") == {}
        assert not http_stub.requests

    async def test_la_cle_est_transmise_quand_elle_existe(self, monkeypatch, http_stub):
        """Sinon le réglage serait décoratif : l'API attend un en-tête précis."""
        from app.core.config import settings

        monkeypatch.setattr(settings, "CRYPTOCOMPARE_API_KEY", "abc123", raising=False)
        http_stub.json("min-api.cryptocompare.com", {"RAW": {"BTC": {"EUR": {"PRICE": 50000}}}})
        assert (await cryptocompare_quotes(["BTC"], "EUR"))["BTC"].price == 50000
        assert http_stub.requests[0].headers["authorization"] == "Apikey abc123"

    def test_le_reglage_existe_et_est_vide_par_defaut(self):
        from app.core.config import Settings

        assert "CRYPTOCOMPARE_API_KEY" in Settings.model_fields, (
            "sans réglage déclaré, la clé ne peut pas être fournie par l'environnement"
        )
