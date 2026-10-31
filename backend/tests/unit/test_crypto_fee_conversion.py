"""Résolution des taux : change, puis cours crypto, puis 1 signalé comme périmé.

Les frais d'exchange sont souvent payés en crypto. Un convertisseur de change ne connaît que les monnaies
fiat : sans repli sur le cours crypto, 0,0001 BTC de frais comptait 0,0001 € et `forex_stale` restait levé
en permanence, ce qui ne signalait plus rien.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.domains.dashboard.metrics.quotes import RateResolver
from app.domains.market_data.fx.service import FxService

QUOTES = "app.domains.dashboard.metrics.quotes.price_feed"


def _resolver() -> RateResolver:
    return RateResolver(db=None)


@pytest.mark.asyncio
async def test_le_change_prime_sur_le_cours_crypto():
    feed = AsyncMock()
    with (
        patch.object(FxService, "latest", new=AsyncMock(return_value=SimpleNamespace(rate=0.9, stale=True))),
        patch(QUOTES, feed),
    ):
        assert await _resolver().rate("USD", "EUR") == (0.9, True)
    feed.quote.assert_not_called()


@pytest.mark.asyncio
async def test_un_cours_crypto_est_une_donnee_fraiche():
    feed = AsyncMock()
    feed.quote.return_value = SimpleNamespace(price=68000)
    with patch.object(FxService, "latest", new=AsyncMock(return_value=None)), patch(QUOTES, feed):
        assert await _resolver().rate("BTC", "EUR") == (68000.0, False)
    feed.quote.assert_awaited_once_with("BTC", "crypto", "EUR")


@pytest.mark.asyncio
async def test_sans_aucun_taux_le_montant_reste_non_converti_et_perime():
    feed = AsyncMock()
    feed.quote.return_value = None
    with patch.object(FxService, "latest", new=AsyncMock(return_value=None)), patch(QUOTES, feed):
        assert await _resolver().rate("XYZ", "EUR") == (1.0, True)


@pytest.mark.asyncio
async def test_seul_le_taux_suivi_marque_la_resolution_perimee():
    feed = AsyncMock()
    feed.quote.return_value = None
    with patch.object(FxService, "latest", new=AsyncMock(return_value=None)), patch(QUOTES, feed):
        resolver = _resolver()
        await resolver.rate("XYZ", "EUR")
        assert resolver.stale is False
        assert await resolver.tracked_rate("XYZ", "EUR") == 1.0
        assert resolver.stale is True
