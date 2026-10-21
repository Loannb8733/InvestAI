from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.portfolio.models import Asset
from app.models.audit_log import AuditLog
from app.models.transaction import Transaction

pytestmark = pytest.mark.usefixtures("empty_test_redis")
URL = "/api/v1/transactions"


@pytest.fixture
def headers(regular_user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}


async def _portfolio(client: AsyncClient, headers: dict[str, str]) -> str:
    return str((await client.post("/api/v1/portfolios", json={"name": "P"}, headers=headers)).json()["id"])


async def _asset(
    client: AsyncClient, headers: dict[str, str], portfolio_id: str, symbol: str = "BTC", **extra: Any
) -> str:
    body = {"portfolio_id": portfolio_id, "symbol": symbol, "asset_type": "crypto", **extra}
    return str((await client.post("/api/v1/assets", json=body, headers=headers)).json()["id"])


async def _tx(client: AsyncClient, headers: dict[str, str], asset_id: str, **fields: Any) -> dict[str, Any]:
    body = {
        "asset_id": asset_id,
        "transaction_type": "buy",
        "quantity": "1",
        "price": "100",
        "currency": "EUR",
        "executed_at": "2025-01-10T10:00:00Z",
        **fields,
    }
    response = await client.post(URL, json=body, headers=headers)
    return {"status": response.status_code, **(response.json() if response.status_code < 300 else {})}


async def _asset_row(db: AsyncSession, asset_id: str) -> Asset:
    asset = (await db.execute(select(Asset).where(Asset.id == asset_id))).scalar_one()
    await db.refresh(asset)
    return asset


class TestCreate:
    async def test_another_platform_goes_to_its_own_asset(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        portfolio_id = await _portfolio(client, headers)
        asset_id = await _asset(client, headers, portfolio_id)
        created = await _tx(client, headers, asset_id, exchange="Kraken")
        assert created["asset_id"] != asset_id
        kraken = await _asset_row(db_session, created["asset_id"])
        assert (kraken.exchange, kraken.quantity) == ("Kraken", Decimal("1"))
        assert (await _asset_row(db_session, asset_id)).quantity == 0

    async def test_the_same_transaction_twice_is_a_conflict(self, client: AsyncClient, headers: dict[str, str]) -> None:
        asset_id = await _asset(client, headers, await _portfolio(client, headers))
        assert (await _tx(client, headers, asset_id))["status"] == 201
        assert (await _tx(client, headers, asset_id))["status"] == 409

    async def test_cost_basis_includes_fees_and_transfers_in(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        asset_id = await _asset(client, headers, await _portfolio(client, headers))
        await _tx(client, headers, asset_id, quantity="1", price="100", fee="10")
        await _tx(client, headers, asset_id, transaction_type="transfer_in", quantity="1", price="200")
        await _tx(client, headers, asset_id, transaction_type="airdrop", quantity="2", price="50")
        asset = await _asset_row(db_session, asset_id)
        assert (asset.quantity, asset.avg_buy_price) == (Decimal("4"), Decimal("155"))

    async def test_an_audit_entry_is_written(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        asset_id = await _asset(client, headers, await _portfolio(client, headers))
        created = await _tx(client, headers, asset_id)
        await client.patch(f"{URL}/{created['id']}", json={"notes": "n"}, headers=headers)
        await client.delete(f"{URL}/{created['id']}", headers=headers)
        actions = (await db_session.execute(select(AuditLog.action).order_by(AuditLog.created_at))).scalars().all()
        assert list(actions) == ["transaction.create", "transaction.update", "transaction.delete"]


class TestList:
    async def test_filters(self, client: AsyncClient, headers: dict[str, str]) -> None:
        portfolio_id = await _portfolio(client, headers)
        btc = await _asset(client, headers, portfolio_id)
        eth = await _asset(client, headers, portfolio_id, symbol="ETH", exchange="Kraken")
        await _tx(client, headers, btc, notes="100%_sure", executed_at="2025-01-01T10:00:00Z")
        await _tx(client, headers, eth, transaction_type="conversion_in", executed_at="2025-02-01T10:00:00Z")
        await _tx(client, headers, eth, transaction_type="sell", quantity="0.5", executed_at="2025-03-01T10:00:00Z")

        async def symbols(**params: Any) -> list[str]:
            body = (await client.get(URL, params=params, headers=headers)).json()
            return [t["asset_symbol"] + ":" + t["transaction_type"] for t in body]

        assert await symbols() == ["ETH:sell", "ETH:conversion_in", "BTC:buy"]
        assert await symbols(transaction_type="conversions") == ["ETH:conversion_in"]
        assert await symbols(exchange="manuel") == ["BTC:buy"]
        assert await symbols(exchange="KRAKEN") == ["ETH:sell", "ETH:conversion_in"]
        assert await symbols(asset_symbol="btc") == ["BTC:buy"]
        assert await symbols(date_from="2025-02-01", date_to="2025-02-01") == ["ETH:conversion_in"]
        assert await symbols(search="0%_s") == ["BTC:buy"]
        assert await symbols(search="%") == ["BTC:buy"]
        page = (await client.get(URL, params={"include_total": True, "limit": 1}, headers=headers)).json()
        assert (len(page["items"]), page["total"]) == (1, 3)
        assert (await client.get(URL, params={"transaction_type": "nope"}, headers=headers)).status_code == 422

    async def test_platforms_merge_case_insensitively(self, client: AsyncClient, headers: dict[str, str]) -> None:
        portfolio_id = await _portfolio(client, headers)
        await _asset(client, headers, portfolio_id, exchange="Kraken")
        btc = await _asset(client, headers, portfolio_id, symbol="ETH")
        await _tx(client, headers, btc, exchange="kraken")
        await _tx(client, headers, btc, exchange="Binance", quantity="2")
        body = (await client.get(f"{URL}/platforms", headers=headers)).json()
        assert body == {"platforms": ["Binance", "Kraken"]}

    async def test_export_csv(self, client: AsyncClient, headers: dict[str, str]) -> None:
        asset_id = await _asset(client, headers, await _portfolio(client, headers), exchange="Kraken")
        await _tx(client, headers, asset_id, notes="first")
        response = await client.get(f"{URL}/export-csv", headers=headers)
        assert response.headers["content-disposition"] == "attachment; filename=transactions_export.csv"
        assert response.text.splitlines() == [
            "symbol;type;quantity;price;fee;date;exchange;notes",
            "BTC;buy;1.000000000000;100.000000000000;0E-12;2025-01-10 10:00:00;Kraken;first",
        ]


class TestDeleteAll:
    async def test_resets_or_deletes_assets(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        portfolio_id = await _portfolio(client, headers)
        asset_id = await _asset(client, headers, portfolio_id)
        await _tx(client, headers, asset_id)
        assert (await client.delete(f"{URL}/all", headers=headers)).json() == {"deleted_count": 1}
        asset = await _asset_row(db_session, asset_id)
        assert (asset.quantity, asset.avg_buy_price) == (0, 0)
        await _tx(client, headers, asset_id, quantity="3")
        result = await client.delete(f"{URL}/all", params={"delete_assets": True}, headers=headers)
        assert result.json() == {"deleted_count": 1}
        assert (await db_session.execute(select(func.count()).select_from(Asset))).scalar() == 0


class TestCurrentBehaviourToBeFixed:
    async def test_patching_the_platform_keeps_the_transaction_on_its_asset(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        asset_id = await _asset(client, headers, await _portfolio(client, headers))
        created = await _tx(client, headers, asset_id)
        patched = (await client.patch(f"{URL}/{created['id']}", json={"exchange": "Kraken"}, headers=headers)).json()
        assert (patched["asset_id"], patched["exchange"]) == (asset_id, "Kraken")

    async def test_csv_import_cost_basis_ignores_fees(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        portfolio_id = await _portfolio(client, headers)
        content = b"symbol,type,quantity,price,fee,date,notes\nSOL,buy,2,100,10,2025-01-10 10:00:00,\n"
        response = await client.post(
            f"{URL}/import-csv",
            params={"portfolio_id": portfolio_id, "platform": "generic"},
            files={"file": ("h.csv", content, "text/csv")},
            headers=headers,
        )
        assert response.json()["success_count"] == 1
        asset = (await db_session.execute(select(Asset).where(Asset.symbol == "SOL"))).scalar_one()
        await db_session.refresh(asset)
        assert (asset.quantity, asset.avg_buy_price) == (Decimal("2"), Decimal("100"))
        assert (await db_session.execute(select(func.count()).select_from(Transaction))).scalar() == 1
