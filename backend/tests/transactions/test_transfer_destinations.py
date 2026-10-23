from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.portfolio.models import Asset
from app.domains.transactions.models import Transaction, TransactionType
from tests.transactions.test_transactions_characterization import URL, _asset, _portfolio, _tx

pytestmark = pytest.mark.usefixtures("empty_test_redis")


@pytest.fixture
def headers(regular_user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}


async def _holdings(db: AsyncSession) -> dict[str, Decimal]:
    db.expire_all()
    return {a.exchange: a.quantity for a in (await db.execute(select(Asset))).scalars()}


async def _linked(db: AsyncSession) -> list[tuple[TransactionType, bool]]:
    rows = (await db.execute(select(Transaction).order_by(Transaction.transaction_type))).scalars()
    return [(t.transaction_type, t.related_transaction_id is not None) for t in rows]


class TestOutgoingTransfers:
    async def test_without_destination_the_default_cold_wallet_receives_it(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        asset_id = await _asset(client, headers, await _portfolio(client, headers), exchange="Kraken")
        await _tx(client, headers, asset_id, quantity="5")
        await _tx(client, headers, asset_id, transaction_type="transfer_out", quantity="2")
        assert await _holdings(db_session) == {"Kraken": Decimal("3"), "Tangem": Decimal("2")}
        assert (TransactionType.TRANSFER_OUT, True) in await _linked(db_session)

    async def test_leaving_the_default_wallet_itself_has_no_mirror(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        asset_id = await _asset(client, headers, await _portfolio(client, headers), exchange="Tangem")
        await _tx(client, headers, asset_id, quantity="5")
        await _tx(client, headers, asset_id, transaction_type="transfer_out", quantity="2")
        assert await _holdings(db_session) == {"Tangem": Decimal("3")}

    async def test_becoming_a_transfer_out_creates_the_mirror(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        asset_id = await _asset(client, headers, await _portfolio(client, headers), exchange="Kraken")
        await _tx(client, headers, asset_id, quantity="5")
        sold = await _tx(client, headers, asset_id, transaction_type="sell", quantity="2")
        response = await client.patch(f"{URL}/{sold['id']}", json={"transaction_type": "transfer_out"}, headers=headers)
        assert response.status_code == 200
        assert await _holdings(db_session) == {"Kraken": Decimal("3"), "Tangem": Decimal("2")}

    async def test_a_csv_transfer_out_without_destination_is_mirrored(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        portfolio_id = await _portfolio(client, headers)
        content = (
            b"symbol,type,quantity,price,fee,date,notes\n"
            b"SOL,buy,5,100,0,2025-01-10 10:00:00,\n"
            b"SOL,transfer_out,2,100,0,2025-01-11 10:00:00,\n"
        )
        response = await client.post(
            f"{URL}/import-csv",
            params={"portfolio_id": portfolio_id, "platform": "generic"},
            files={"file": ("h.csv", content, "text/csv")},
            headers=headers,
        )
        assert response.json()["success_count"] == 2
        holdings = await _holdings(db_session)
        assert holdings["Tangem"] == Decimal("2") and sum(holdings.values()) == Decimal("5")


class TestAssetPlatform:
    async def test_transactions_follow_the_asset_to_its_new_platform(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        asset_id = await _asset(client, headers, await _portfolio(client, headers), exchange="Kraken")
        await _tx(client, headers, asset_id, exchange="Kraken")
        response = await client.patch(f"/api/v1/assets/{asset_id}", json={"exchange": "Bitpanda"}, headers=headers)
        assert response.status_code == 200
        db_session.expire_all()
        assert (await db_session.execute(select(Transaction.exchange))).scalars().all() == ["Bitpanda"]
