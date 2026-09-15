"""Le watchdog d'invariants ne compte comme bloquants que les écarts matériels.

Le workflow hebdomadaire ouvrait un ticket quand le total dépassait une
référence, mais restait vert : le ticket #224 a été rafraîchi chaque lundi
depuis juin sans que personne ne soit prévenu (NEW-80). Pour qu'il puisse
échouer sans rougir chaque semaine pour des poussières, l'endpoint doit juger
chaque écart exactement comme ``scripts/check_invariants.py``.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.core import database
from app.core.config import settings
from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from tests.conftest import test_engine

_JETON = "jeton-de-test-du-watchdog"


async def _actif(db, portefeuille, symbole, stocke, achete, pru) -> Asset:
    """Un actif dont le stock vaut ``stocke`` mais l'historique ``achete``."""
    actif = Asset(
        portfolio_id=portefeuille.id,
        symbol=symbole,
        name=symbole,
        asset_type=AssetType.CRYPTO,
        quantity=Decimal(stocke),
        avg_buy_price=Decimal(pru),
        exchange="Binance",
    )
    db.add(actif)
    await db.flush()
    db.add(
        Transaction(
            asset_id=actif.id,
            transaction_type=TransactionType.BUY,
            quantity=Decimal(achete),
            price=Decimal(pru),
            executed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )
    await db.flush()
    return actif


@pytest.fixture
def watchdog(monkeypatch):
    monkeypatch.setattr(settings, "CRON_SECRET", _JETON)
    # L'endpoint lit le moteur de l'application : sans substitution, il
    # interrogerait la base de développement au lieu de la base de test.
    monkeypatch.setattr(database, "engine", test_engine)


async def _controler(client: AsyncClient) -> dict:
    reponse = await client.post("/api/v1/cron/invariants-check", headers={"X-Cron-Token": _JETON})
    assert reponse.status_code == 200, reponse.text
    return reponse.json()["result"]


@pytest.mark.asyncio
async def test_seuls_les_ecarts_materiels_sont_comptes(client: AsyncClient, db_session, regular_user: User, watchdog):
    portefeuille = Portfolio(user_id=regular_user.id, name="Watchdog")
    db_session.add(portefeuille)
    await db_session.flush()
    # 0,003 BTC manquants sur une position ouverte à ~440 € : matériel.
    await _actif(db_session, portefeuille, "BTC", "0.0078", "0.0048", "56000")
    # Écart de deux cent-millionièmes de SOL : bruit d'arrondi.
    await _actif(db_session, portefeuille, "SOL", "1.05798200", "1.05798198", "84")
    await db_session.commit()

    resultat = await _controler(client)

    assert resultat["counts"]["holdings"] == 2, "les deux écarts restent listés"
    assert resultat["material_violations"] == 1
    par_symbole = {h["symbol"]: h for h in resultat["details"]["holdings"]}
    assert par_symbole["BTC"]["material"] is True
    assert par_symbole["SOL"]["material"] is False and "arrondi" in par_symbole["SOL"]["reason"]


@pytest.mark.asyncio
async def test_une_base_saine_ne_compte_rien(client: AsyncClient, db_session, regular_user: User, watchdog):
    portefeuille = Portfolio(user_id=regular_user.id, name="Watchdog")
    db_session.add(portefeuille)
    await db_session.flush()
    await _actif(db_session, portefeuille, "ETH", "2", "2", "2000")
    await db_session.commit()

    resultat = await _controler(client)

    assert resultat["material_violations"] == 0
    assert resultat["total_violations"] == 0
