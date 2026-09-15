"""Le pré-chargement d'historique ne s'occupe que des actifs cotés.

Un projet de crowdfunding n'a d'historique nulle part : `get_history` rend
vide, mais la boucle de démarrage dormait quand même ses 7 s « entre deux
appels » — 42 s par démarrage pour six projets, et six avertissements
« No history data » à chaque fois (journaux Render du 2026-09-15, NEW-89).
"""

from decimal import Decimal

import pytest

from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.user import User
from app.tasks import history_cache
from tests.conftest import TestSessionLocal


@pytest.mark.asyncio
async def test_seuls_les_actifs_cotes_sont_precharges(db_session, regular_user: User, monkeypatch):
    portefeuille = Portfolio(user_id=regular_user.id, name="Mixte")
    db_session.add(portefeuille)
    await db_session.flush()
    for symbole, genre, quantite in (
        ("BTC", AssetType.CRYPTO, "0.5"),
        ("AAPL", AssetType.STOCK, "3"),
        ("TOKIMO-CLAMART", AssetType.CROWDFUNDING, "1"),
        ("OAT-2030", AssetType.BOND, "1"),
        ("ETH", AssetType.CRYPTO, "0"),  # position soldée : rien à précharger
    ):
        db_session.add(
            Asset(
                portfolio_id=portefeuille.id,
                symbol=symbole,
                name=symbole,
                asset_type=genre,
                quantity=Decimal(quantite),
                exchange="",
            )
        )
    await db_session.commit()
    # La fonction ouvre sa propre session : elle doit viser la base de test.
    monkeypatch.setattr(history_cache, "AsyncSessionLocal", TestSessionLocal)

    actifs = await history_cache._get_all_crypto_symbols()

    assert sorted(actifs) == [("AAPL", "stock"), ("BTC", "crypto")]
