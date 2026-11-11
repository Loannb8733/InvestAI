from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.portfolio.models import Asset
from app.domains.transactions.csv_parsers.generic import GenericCSVParser
from app.domains.transactions.csv_parsers.kraken import KrakenCSVParser

KRAKEN_HEADER = '"txid","refid","time","type","subtype","aclass","asset","amount","fee","balance"\n'


def _kraken(*lines: str) -> list[tuple[str, str, Decimal, Decimal, str]]:
    rows, errors = KrakenCSVParser().parse_csv(KRAKEN_HEADER + "".join(lines))
    assert errors == []
    return [(r.symbol, r.transaction_type, r.quantity, r.price, r.currency) for r in rows]


@pytest.mark.usefixtures("empty_test_redis", "offline")
async def test_earn_subscriptions_are_imported_without_moving_the_balance(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    headers = {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}
    portfolio_id = (await client.post("/api/v1/portfolios", json={"name": "P"}, headers=headers)).json()["id"]
    content = (
        "symbol,type,quantity,price,fee,date\n"
        "USDC,buy,100,1,0,2025-01-10\n"
        "USDC,staking,100,0,0,2025-01-11\n"
        "USDC,unstaking,100,0,0,2025-01-12\n"
    )
    response = await client.post(
        "/api/v1/transactions/import-csv",
        params={"portfolio_id": portfolio_id},
        files={"file": ("earn.csv", content.encode(), "text/csv")},
        headers=headers,
    )
    asset = (await db_session.execute(select(Asset).where(Asset.symbol == "USDC"))).scalar_one()
    await db_session.refresh(asset)
    assert (response.json()["success_count"], response.json()["errors"]) == (3, [])
    assert asset.quantity == Decimal("100")


def test_a_kraken_trade_takes_its_price_from_the_fiat_leg() -> None:
    assert _kraken(
        '"L1","T1","2025-03-01 11:00:00","trade","","currency","XXBT","0.01","0","0.01"\n',
        '"L2","T1","2025-03-01 11:00:00","trade","","currency","ZEUR","-900","1.5","100"\n',
        '"L3","T2","2025-03-02 10:00:00","trade","","currency","XETH","-0.3","0","0.7"\n',
        '"L4","T2","2025-03-02 10:00:00","trade","","currency","ZUSD","750","0","750"\n',
        '"L5","T3","2025-03-03 11:00:00","spend","","currency","ZEUR","-100","0","0"\n',
        '"L6","T3","2025-03-03 11:00:00","receive","","currency","ADA","40","0","40"\n',
    ) == [
        ("BTC", "buy", Decimal("0.01"), Decimal("90000"), "EUR"),
        ("ETH", "sell", Decimal("0.3"), Decimal("2500"), "USD"),
        ("ADA", "buy", Decimal("40"), Decimal("2.5"), "EUR"),
    ]


def test_kraken_dogecoin_is_doge() -> None:
    assert _kraken('"L1","R1","2025-03-02 12:00:00","reward","","currency","XXDG","15","0","15"\n') == [
        ("DOGE", "airdrop", Decimal("15"), Decimal("0"), "EUR")
    ]


def test_a_decimal_comma_is_read() -> None:
    rows, errors = GenericCSVParser().parse_csv("symbol;type;quantity;price;fee\nBTC;buy;0,1;40000,5;0,25\n")
    assert errors == []
    assert [(r.quantity, r.price, r.fee) for r in rows] == [(Decimal("0.1"), Decimal("40000.5"), Decimal("0.25"))]
