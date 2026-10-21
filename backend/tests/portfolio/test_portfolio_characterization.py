from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.portfolio.models import Asset
from app.models.transaction import Transaction

pytestmark = pytest.mark.usefixtures("empty_test_redis")


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(str(user.id))}"}


async def _portfolio(client: AsyncClient, user: User, name: str = "P") -> str:
    response = await client.post("/api/v1/portfolios", json={"name": name}, headers=_bearer(user))
    assert response.status_code == 201
    return str(response.json()["id"])


async def _asset(client: AsyncClient, user: User, portfolio_id: str, **fields: Any) -> dict[str, Any]:
    body = {"portfolio_id": portfolio_id, "symbol": "btc", "asset_type": "crypto", **fields}
    response = await client.post("/api/v1/assets", json=body, headers=_bearer(user))
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _buy(client: AsyncClient, user: User, asset_id: str) -> None:
    body = {
        "asset_id": asset_id,
        "transaction_type": "buy",
        "quantity": "1",
        "price": "100",
        "currency": "EUR",
        "executed_at": "2025-01-10T10:00:00Z",
    }
    assert (await client.post("/api/v1/transactions", json=body, headers=_bearer(user))).status_code == 201


class TestPortfolios:
    async def test_a_portfolio_is_invisible_to_other_users(
        self, client: AsyncClient, regular_user: User, admin_user: User
    ) -> None:
        portfolio_id = await _portfolio(client, regular_user)
        other = _bearer(admin_user)
        assert (await client.get(f"/api/v1/portfolios/{portfolio_id}", headers=other)).status_code == 404
        assert (await client.get("/api/v1/portfolios", headers=other)).json() == []
        assert (await client.delete(f"/api/v1/portfolios/{portfolio_id}", headers=other)).status_code == 404

    async def test_list_is_newest_first(self, client: AsyncClient, regular_user: User) -> None:
        await _portfolio(client, regular_user, "A")
        await _portfolio(client, regular_user, "B")
        names = [p["name"] for p in (await client.get("/api/v1/portfolios", headers=_bearer(regular_user))).json()]
        assert names == ["B", "A"]

    async def test_rename(self, client: AsyncClient, regular_user: User) -> None:
        portfolio_id = await _portfolio(client, regular_user)
        response = await client.patch(
            f"/api/v1/portfolios/{portfolio_id}", json={"name": "Renamed"}, headers=_bearer(regular_user)
        )
        assert (response.json()["name"], response.json()["kind"]) == ("Renamed", None)

    async def test_cash_balance_is_set_then_removed(self, client: AsyncClient, regular_user: User) -> None:
        portfolio_id = await _portfolio(client, regular_user)
        headers = _bearer(regular_user)
        url = f"/api/v1/portfolios/{portfolio_id}/cash-balance"
        assert (await client.put(url, json={"exchange": "Kraken", "amount": 120.5}, headers=headers)).json()[
            "cash_balances"
        ] == {"Kraken": 120.5}
        await client.put(url, json={"exchange": "Binance", "amount": 10}, headers=headers)
        assert (await client.put(url, json={"exchange": "Kraken", "amount": 0}, headers=headers)).json()[
            "cash_balances"
        ] == {"Binance": 10}
        assert (await client.delete(f"{url}/Binance", headers=headers)).json()["cash_balances"] == {}
        assert (await client.put(url, json={"exchange": "X", "amount": -1}, headers=headers)).status_code == 422

    async def test_deleting_a_portfolio_deletes_its_assets_and_transactions(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        portfolio_id = await _portfolio(client, regular_user)
        asset = await _asset(client, regular_user, portfolio_id)
        await _buy(client, regular_user, asset["id"])
        assert (
            await client.delete(f"/api/v1/portfolios/{portfolio_id}", headers=_bearer(regular_user))
        ).status_code == 204
        assert (await db_session.execute(select(func.count()).select_from(Asset))).scalar() == 0
        assert (await db_session.execute(select(func.count()).select_from(Transaction))).scalar() == 0


class TestAssets:
    async def test_symbol_is_uppercased_and_unique_per_exchange(self, client: AsyncClient, regular_user: User) -> None:
        portfolio_id = await _portfolio(client, regular_user)
        created = await _asset(client, regular_user, portfolio_id)
        assert (created["symbol"], created["exchange"]) == ("BTC", "")
        body = {"portfolio_id": portfolio_id, "symbol": "BTC", "asset_type": "crypto"}
        duplicate = await client.post("/api/v1/assets", json=body, headers=_bearer(regular_user))
        assert duplicate.status_code == 400
        await _asset(client, regular_user, portfolio_id, exchange="Kraken")

    async def test_another_users_portfolio_is_refused(
        self, client: AsyncClient, regular_user: User, admin_user: User
    ) -> None:
        portfolio_id = await _portfolio(client, regular_user)
        body = {"portfolio_id": portfolio_id, "symbol": "ETH", "asset_type": "crypto"}
        assert (await client.post("/api/v1/assets", json=body, headers=_bearer(admin_user))).status_code == 404

    async def test_list_hides_crowdfunding_and_filters_by_portfolio(
        self, client: AsyncClient, regular_user: User
    ) -> None:
        first = await _portfolio(client, regular_user, "A")
        second = await _portfolio(client, regular_user, "B")
        await _asset(client, regular_user, first, symbol="eth")
        await _asset(client, regular_user, first, symbol="TOKIMO1", asset_type="crowdfunding")
        await _asset(client, regular_user, second, symbol="sol")
        headers = _bearer(regular_user)
        assert [a["symbol"] for a in (await client.get("/api/v1/assets", headers=headers)).json()] == ["ETH", "SOL"]
        filtered = await client.get("/api/v1/assets", params={"portfolio_id": first}, headers=headers)
        assert [a["symbol"] for a in filtered.json()] == ["ETH"]

    async def test_patch_normalizes_a_null_exchange(self, client: AsyncClient, regular_user: User) -> None:
        portfolio_id = await _portfolio(client, regular_user)
        asset = await _asset(client, regular_user, portfolio_id, exchange="Kraken")
        response = await client.patch(
            f"/api/v1/assets/{asset['id']}", json={"exchange": None, "quantity": "2.5"}, headers=_bearer(regular_user)
        )
        assert (response.json()["exchange"], response.json()["quantity"]) == ("", 2.5)

    async def test_deleting_an_asset_keeps_the_transfers_that_pointed_to_it(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        portfolio_id = await _portfolio(client, regular_user)
        source = await _asset(client, regular_user, portfolio_id)
        target = await _asset(client, regular_user, portfolio_id, exchange="Ledger")
        await _buy(client, regular_user, source["id"])
        await _buy(client, regular_user, target["id"])
        rows = (await db_session.execute(select(Transaction).order_by(Transaction.created_at))).scalars().all()
        rows[1].related_transaction_id = rows[0].id
        await db_session.commit()
        assert (await client.delete(f"/api/v1/assets/{source['id']}", headers=_bearer(regular_user))).status_code == 204
        remaining = (await db_session.execute(select(Transaction))).scalars().all()
        await db_session.refresh(remaining[0])
        assert [(str(t.asset_id), t.related_transaction_id) for t in remaining] == [(target["id"], None)]

    async def test_the_list_returns_every_asset(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        portfolio_id = await _portfolio(client, regular_user)
        db_session.add_all(
            [Asset(portfolio_id=portfolio_id, symbol=f"T{i:02d}", asset_type="crypto", exchange="") for i in range(60)]
        )
        await db_session.commit()
        assert len((await client.get("/api/v1/assets", headers=_bearer(regular_user))).json()) == 60
