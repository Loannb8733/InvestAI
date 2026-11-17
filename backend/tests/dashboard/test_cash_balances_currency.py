import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.dashboard.metrics.quotes import RateResolver
from app.domains.identity.models import User
from app.domains.identity.tokens import create_token


async def _usd_rate(self: RateResolver, from_currency: str, to_currency: str) -> tuple[float, bool]:
    return (1.1, False) if (from_currency, to_currency) == ("EUR", "USD") else (1.0, False)


@pytest.mark.usefixtures("empty_test_redis", "offline")
async def test_cash_entered_in_euros_is_converted_to_the_user_currency(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(RateResolver, "rate", _usd_rate)
    regular_user.preferred_currency = "USD"
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}
    portfolio_id = (await client.post("/api/v1/portfolios", json={"name": "Cash"}, headers=headers)).json()["id"]
    saved = await client.put(
        f"/api/v1/portfolios/{portfolio_id}/cash-balance", json={"exchange": "Binance", "amount": 100}, headers=headers
    )
    assert saved.status_code == 200, saved.text

    portfolio = (await client.get(f"/api/v1/dashboard/portfolio/{portfolio_id}", headers=headers)).json()
    account = (await client.get("/api/v1/dashboard", headers=headers)).json()

    assert portfolio["cash_from_balances"] == pytest.approx(110.0)
    assert account["available_liquidity"] == pytest.approx(110.0)
