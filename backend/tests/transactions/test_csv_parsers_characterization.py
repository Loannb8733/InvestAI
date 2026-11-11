import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.portfolio.models import Asset, Portfolio
from app.domains.transactions.csv_parsers.base import parse_timestamp
from app.domains.transactions.csv_parsers.registry import detect_csv_format, get_available_platforms, get_parser_by_name
from app.domains.transactions.models import Transaction
from tests.transactions import csv_samples

GOLDEN = Path(__file__).parent / "golden" / "csv_parsers"
UPDATE = os.environ.get("GOLDEN_UPDATE") == "1"
NOW = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
URL = "/api/v1/transactions/import-csv"
SAMPLES = {
    "crypto_com": csv_samples.CRYPTO_COM,
    "binance": csv_samples.BINANCE,
    "kraken": csv_samples.KRAKEN,
    "generic": csv_samples.GENERIC,
    "generic_semicolon": csv_samples.GENERIC_SEMICOLON,
    "generic_tab": csv_samples.GENERIC_TAB,
    "unknown": csv_samples.UNKNOWN,
    "empty": "",
}

pytestmark = pytest.mark.usefixtures("empty_test_redis", "offline")


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _check(name: str, observed: Any) -> None:
    path = GOLDEN / f"{name}.json"
    rendered = json.dumps(_plain(observed), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if UPDATE or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
    assert path.read_text(encoding="utf-8") == rendered, f"golden {name} différent (GOLDEN_UPDATE=1)"


def _parsed(content: str, platform: str | None = None) -> dict[str, Any]:
    parser = get_parser_by_name(platform) if platform else detect_csv_format(content)
    if parser is None:
        return {"parser": None}
    with time_machine.travel(NOW, tick=False):
        rows, errors = parser.parse_csv(content)
    return {"parser": parser.name, "rows": [asdict(r) for r in rows], "errors": errors}


@pytest.mark.parametrize("sample", sorted(SAMPLES))
def test_parsing(sample: str) -> None:
    _check(f"parse_{sample}", _parsed(SAMPLES[sample]))


def test_forced_platform_on_a_foreign_file() -> None:
    _check("parse_generic_as_kraken", _parsed(csv_samples.GENERIC, "kraken"))


def test_platform_lookup() -> None:
    names = ["binance", "Crypto.com", "crypto", "kraken", "generic", "investai", "InvestAI / Generic", "", "coinbase"]
    lookup = {name: getattr(get_parser_by_name(name), "name", None) for name in names}
    stamps = [
        "2025-01-02 10:00:00",
        "2025-01-02T10:00:00",
        "2025-01-02T10:00:00.5",
        "2025-01-02 10:00:00.5",
        "2025-01-02T10:00:00Z",
        "02/01/2025 10:00:00",
        "02/01/2025 10:00",
        "13/31/2025 10:00:00",
        "  2025-01-02 10:00:00 ",
        "2025-01-02",
    ]
    parsed: dict[str, str] = {}
    for stamp in stamps:
        try:
            parsed[stamp] = parse_timestamp(stamp).isoformat()
        except ValueError as exc:
            parsed[stamp] = f"ValueError: {exc}"
    _check("lookup", {"platforms": get_available_platforms(), "by_name": lookup, "timestamps": parsed})


@pytest.fixture
def headers(regular_user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}


async def _import(
    client: AsyncClient, headers: dict[str, str], portfolio_id: str, content: str, **params: str
) -> dict[str, Any]:
    with time_machine.travel(NOW, tick=False):
        response = await client.post(
            URL,
            params={"portfolio_id": portfolio_id, **params},
            files={"file": ("export.csv", content.encode(), "text/csv")},
            headers=headers,
        )
    body = response.json()
    if isinstance(body, dict):
        body.pop("created_transactions", None)
    return {"status": response.status_code, "body": body}


async def _state(db: AsyncSession, user: User) -> list[dict[str, Any]]:
    query = select(Asset).join(Portfolio).where(Portfolio.user_id == user.id).order_by(Asset.exchange, Asset.symbol)
    state = []
    for asset in (await db.execute(query)).scalars():
        await db.refresh(asset)
        moves = (
            await db.execute(
                select(Transaction)
                .where(Transaction.asset_id == asset.id)
                .order_by(Transaction.executed_at, Transaction.transaction_type, Transaction.quantity)
            )
        ).scalars()
        state.append(
            {
                "symbol": asset.symbol,
                "exchange": asset.exchange,
                "asset_type": asset.asset_type.value,
                "currency": asset.currency,
                "quantity": asset.quantity,
                "avg_buy_price": asset.avg_buy_price,
                "transactions": [
                    {
                        "type": t.transaction_type.value,
                        "quantity": t.quantity,
                        "price": t.price,
                        "fee": t.fee,
                        "fee_currency": t.fee_currency,
                        "currency": t.currency,
                        "executed_at": t.executed_at,
                        "exchange": t.exchange,
                        "notes": t.notes,
                    }
                    for t in moves
                ],
            }
        )
    return state


async def _portfolio(client: AsyncClient, headers: dict[str, str]) -> str:
    return str((await client.post("/api/v1/portfolios", json={"name": "P"}, headers=headers)).json()["id"])


@pytest.mark.parametrize("sample", ["crypto_com", "binance", "kraken", "generic"])
async def test_import(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, headers: dict[str, str], sample: str
) -> None:
    portfolio_id = await _portfolio(client, headers)
    result = await _import(client, headers, portfolio_id, SAMPLES[sample])
    again = await _import(client, headers, portfolio_id, SAMPLES[sample])
    _check(f"import_{sample}", {"first": result, "again": again, "state": await _state(db_session, regular_user)})


async def test_import_with_destination_and_platform_choices(
    client: AsyncClient, db_session: AsyncSession, regular_user: User, headers: dict[str, str]
) -> None:
    portfolio_id = await _portfolio(client, headers)
    outcomes = {
        "destination": await _import(
            client, headers, portfolio_id, csv_samples.BINANCE, destination_exchange=" Ledger "
        ),
        "unknown_format": await _import(client, headers, portfolio_id, csv_samples.UNKNOWN),
        "unknown_platform": await _import(client, headers, portfolio_id, csv_samples.GENERIC, platform="coinbase"),
        "forced_platform": await _import(client, headers, portfolio_id, csv_samples.GENERIC, platform="kraken"),
        "semicolon": await _import(client, headers, portfolio_id, csv_samples.GENERIC_SEMICOLON),
    }
    _check("import_choices", {"outcomes": outcomes, "state": await _state(db_session, regular_user)})


async def test_import_rejections(client: AsyncClient, headers: dict[str, str]) -> None:
    portfolio_id = await _portfolio(client, headers)
    files = {"file": ("export.txt", b"symbol,type,quantity,price\n", "text/plain")}
    wrong_extension = await client.post(URL, params={"portfolio_id": portfolio_id}, files=files, headers=headers)
    csv_file = {"file": ("export.csv", b"symbol,type,quantity,price\n", "text/csv")}
    no_portfolio = await client.post(URL, files=csv_file, headers=headers)
    latin1 = {"file": ("export.csv", "symbol,type,quantity,price\nÉ,buy,1,1\n".encode("latin-1"), "text/csv")}
    undecodable = await client.post(URL, params={"portfolio_id": portfolio_id}, files=latin1, headers=headers)
    bom = {"file": ("export.csv", "﻿symbol,type,quantity,price\nBTC,buy,1,1\n".encode(), "text/csv")}
    with time_machine.travel(NOW, tick=False):
        with_bom = await client.post(URL, params={"portfolio_id": portfolio_id}, files=bom, headers=headers)
    foreign = await client.post(
        URL, params={"portfolio_id": "00000000-0000-0000-0000-000000000000"}, files=csv_file, headers=headers
    )
    _check(
        "import_rejections",
        {
            name: {"status": r.status_code, "body": {k: v for k, v in r.json().items() if k != "created_transactions"}}
            for name, r in {
                "wrong_extension": wrong_extension,
                "no_portfolio": no_portfolio,
                "undecodable": undecodable,
                "with_bom": with_bom,
                "foreign_portfolio": foreign,
            }.items()
        },
    )
