from datetime import timedelta
from decimal import Decimal

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.market_data.prices.quote import PriceQuote
from app.domains.market_data.prices.service import price_feed
from tests.sample_portfolio import FROZEN_NOW, seed_history, seed_portfolio

pytestmark = pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes")
BASE = "/api/v1/alerts"


async def _seeded(client: AsyncClient, db: AsyncSession, user: User) -> tuple[dict[str, str], dict[str, str]]:
    headers = {"Authorization": f"Bearer {create_token(str(user.id))}"}
    await seed_history(db)
    await seed_portfolio(client, headers)
    assets = (await client.get("/api/v1/assets", headers=headers)).json()
    return headers, {asset["symbol"]: asset["id"] for asset in assets}


def _quotes_at(monkeypatch: pytest.MonkeyPatch, prices: dict[tuple[str, str], str]) -> None:
    async def quote(symbol: str, asset_type: str, currency: str = "EUR") -> PriceQuote | None:
        price = prices.get((symbol.upper(), currency.upper()))
        return PriceQuote(price=Decimal(price)) if price is not None else None

    monkeypatch.setattr(price_feed, "quote", quote)


async def test_portfolio_alert_is_created(client: AsyncClient, db_session: AsyncSession, regular_user: User) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        headers, _ = await _seeded(client, db_session, regular_user)
        body = {"name": "Concentration", "condition": "concentration_hhi", "threshold": 0.3}
        created = await client.post(BASE, headers=headers, json=body)
    assert created.status_code == 201
    assert (created.json()["condition"], created.json()["asset_id"]) == ("concentration_hhi", None)


async def test_alert_fires_once_until_its_condition_clears(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False) as clock:
        headers, assets = await _seeded(client, db_session, regular_user)
        body = {"name": "BTC haut", "condition": "price_above", "threshold": 50000, "asset_id": assets["BTC"]}
        await client.post(BASE, headers=headers, json=body)
        fired = []
        for price in ("60000", "61000", "45000", "62000"):
            _quotes_at(monkeypatch, {("BTC", "EUR"): price})
            clock.shift(timedelta(minutes=10))
            fresh = {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}
            fired.append(len((await client.post(f"{BASE}/check", headers=fresh)).json()))
    assert fired == [1, 0, 0, 1]


async def test_break_even_counts_purchase_fees_once(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        headers, assets = await _seeded(client, db_session, regular_user)
        body = {"name": "ETH rentable", "condition": "target_break_even", "threshold": 0, "asset_id": assets["ETH"]}
        await client.post(BASE, headers=headers, json=body)
        triggered = (await client.post(f"{BASE}/check", headers=headers)).json()
    assert [round(t["threshold"], 2) for t in triggered] == [2001.0]


async def test_price_alert_compares_in_its_currency(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        headers, assets = await _seeded(client, db_session, regular_user)
        body = {"name": "BTC USD", "condition": "price_above", "threshold": 65000, "asset_id": assets["BTC"]}
        await client.post(BASE, headers=headers, json={**body, "currency": "USD"})
        _quotes_at(monkeypatch, {("BTC", "EUR"): "60000", ("BTC", "USD"): "69600"})
        triggered = (await client.post(f"{BASE}/check", headers=headers)).json()
    assert [(t["alert_name"], t["current_value"]) for t in triggered] == [("BTC USD", 69600.0)]
