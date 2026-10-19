from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.asset import Asset, AssetType
from app.models.asset_price_history import AssetPriceHistory
from app.models.note import Note
from app.models.portfolio import Portfolio
from app.models.user import User, UserRole

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}


async def _asset(db: AsyncSession, user: User, symbol: str = "JRNL", price: str = "120") -> Asset:
    portfolio = Portfolio(user_id=user.id, name=f"P-{symbol}")
    db.add(portfolio)
    await db.flush()
    asset = Asset(
        portfolio_id=portfolio.id,
        symbol=symbol,
        name=f"{symbol} name",
        asset_type=AssetType.CRYPTO,
        quantity=1,
        avg_buy_price=100,
        current_price=Decimal(price),
        currency="EUR",
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


async def _other_user(db: AsyncSession) -> User:
    user = User(email="other@test.com", password_hash=hash_password("otherpassword"), role=UserRole.USER)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _note_body(response: Any) -> dict[str, Any]:
    body: dict[str, Any] = response.json()
    for key in ("id", "created_at", "updated_at"):
        body.pop(key)
    return body


async def test_create_without_asset(client: AsyncClient, regular_user: User) -> None:
    response = await client.post(
        "/api/v1/notes",
        json={"title": "Thèse", "content": "Long terme", "tags": "macro, btc", "sentiment": "bullish"},
        headers=_headers(regular_user),
    )
    assert response.status_code == 201
    assert _note_body(response) == {
        "title": "Thèse",
        "content": "Long terme",
        "tags": "macro, btc",
        "asset_id": None,
        "asset_symbol": None,
        "asset_name": None,
        "transaction_ids": None,
        "attachments": None,
        "sentiment": "bullish",
    }


async def test_create_with_owned_asset_returns_asset_details(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    asset = await _asset(db_session, regular_user)
    response = await client.post(
        "/api/v1/notes", json={"title": "Achat", "asset_id": str(asset.id)}, headers=_headers(regular_user)
    )
    assert response.status_code == 201
    body = response.json()
    assert (body["asset_id"], body["asset_symbol"], body["asset_name"]) == (str(asset.id), "JRNL", "JRNL name")


async def test_create_with_foreign_asset_is_404(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    foreign = await _asset(db_session, await _other_user(db_session), symbol="FRGN")
    response = await client.post(
        "/api/v1/notes", json={"title": "X", "asset_id": str(foreign.id)}, headers=_headers(regular_user)
    )
    assert (response.status_code, response.json()) == (404, {"detail": "Actif non trouvé"})


@pytest.mark.parametrize(
    "payload",
    [{"title": ""}, {"title": "x" * 201}, {"title": "ok", "sentiment": "euphoric"}, {"title": "ok", "tags": "t" * 501}],
)
async def test_create_rejects_invalid_payload(client: AsyncClient, regular_user: User, payload: dict[str, str]) -> None:
    response = await client.post("/api/v1/notes", json=payload, headers=_headers(regular_user))
    assert response.status_code == 422


async def test_list_filters_orders_and_paginates(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    asset = await _asset(db_session, regular_user)
    other = await _other_user(db_session)
    base = NOW - timedelta(days=10)
    db_session.add_all(
        [
            Note(user_id=regular_user.id, title="Alpha", content="rotation", tags="macro", created_at=base),
            Note(
                user_id=regular_user.id,
                title="Beta",
                content="BTC halving",
                tags="btc",
                asset_id=asset.id,
                created_at=base + timedelta(days=1),
            ),
            Note(
                user_id=regular_user.id,
                title="Gamma",
                content=None,
                tags="macro, btc",
                created_at=base + timedelta(days=2),
            ),
            Note(user_id=other.id, title="Hidden", tags="macro", created_at=base),
        ]
    )
    await db_session.commit()
    headers = _headers(regular_user)

    async def titles(params: dict[str, Any]) -> list[str]:
        response = await client.get("/api/v1/notes", params=params, headers=headers)
        assert response.status_code == 200
        return [n["title"] for n in response.json()]

    assert await titles({}) == ["Gamma", "Beta", "Alpha"]
    assert await titles({"tag": "macro"}) == ["Gamma", "Alpha"]
    assert await titles({"asset_id": str(asset.id)}) == ["Beta"]
    assert await titles({"search": "HALVING"}) == ["Beta"]
    assert await titles({"search": "gam"}) == ["Gamma"]
    assert await titles({"skip": 1, "limit": 1}) == ["Beta"]
    listed = (await client.get("/api/v1/notes", headers=headers)).json()
    assert [(n["asset_symbol"], n["asset_name"]) for n in listed] == [(None, None), ("JRNL", "JRNL name"), (None, None)]


async def test_get_own_note_and_404_for_others(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    asset = await _asset(db_session, regular_user)
    mine = Note(user_id=regular_user.id, title="Mine", asset_id=asset.id)
    theirs = Note(user_id=(await _other_user(db_session)).id, title="Theirs")
    db_session.add_all([mine, theirs])
    await db_session.commit()
    headers = _headers(regular_user)

    response = await client.get(f"/api/v1/notes/{mine.id}", headers=headers)
    assert (response.status_code, response.json()["asset_symbol"]) == (200, "JRNL")
    for note_id in (theirs.id, uuid4()):
        response = await client.get(f"/api/v1/notes/{note_id}", headers=headers)
        assert (response.status_code, response.json()) == (404, {"detail": "Note non trouvée"})


async def test_update_fields_link_and_unlink_asset(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    asset = await _asset(db_session, regular_user)
    note = Note(user_id=regular_user.id, title="Avant", content="c", tags="t", sentiment="neutral")
    db_session.add(note)
    await db_session.commit()
    headers = _headers(regular_user)
    url = f"/api/v1/notes/{note.id}"

    response = await client.patch(url, json={"title": "Après", "asset_id": str(asset.id)}, headers=headers)
    body = response.json()
    assert response.status_code == 200
    assert (body["title"], body["content"], body["tags"], body["sentiment"]) == ("Après", "c", "t", "neutral")
    assert (body["asset_id"], body["asset_symbol"]) == (str(asset.id), "JRNL")

    response = await client.patch(url, json={"content": "nouveau"}, headers=headers)
    assert (response.json()["asset_id"], response.json()["content"]) == (str(asset.id), "nouveau")

    response = await client.patch(url, json={"asset_id": None}, headers=headers)
    assert (response.json()["asset_id"], response.json()["asset_symbol"]) == (None, None)


async def test_update_errors(client: AsyncClient, db_session: AsyncSession, regular_user: User) -> None:
    note = Note(user_id=regular_user.id, title="N")
    db_session.add(note)
    await db_session.commit()
    foreign = await _asset(db_session, await _other_user(db_session), symbol="FRGN")
    headers = _headers(regular_user)

    response = await client.patch(f"/api/v1/notes/{uuid4()}", json={"title": "x"}, headers=headers)
    assert (response.status_code, response.json()) == (404, {"detail": "Note non trouvée"})
    response = await client.patch(f"/api/v1/notes/{note.id}", json={"asset_id": str(foreign.id)}, headers=headers)
    assert (response.status_code, response.json()) == (404, {"detail": "Actif non trouvé"})
    response = await client.patch(f"/api/v1/notes/{note.id}", json={"sentiment": "euphoric"}, headers=headers)
    assert response.status_code == 422


async def test_delete(client: AsyncClient, db_session: AsyncSession, regular_user: User) -> None:
    note = Note(user_id=regular_user.id, title="Bye")
    db_session.add(note)
    await db_session.commit()
    headers = _headers(regular_user)

    response = await client.delete(f"/api/v1/notes/{note.id}", headers=headers)
    assert (response.status_code, response.content) == (204, b"")
    assert (await client.get(f"/api/v1/notes/{note.id}", headers=headers)).status_code == 404
    response = await client.delete(f"/api/v1/notes/{note.id}", headers=headers)
    assert (response.status_code, response.json()) == (404, {"detail": "Note non trouvée"})


async def test_summary(client: AsyncClient, db_session: AsyncSession, regular_user: User) -> None:
    db_session.add_all(
        [
            Note(user_id=regular_user.id, title="a", tags=" macro ,btc,", created_at=NOW - timedelta(days=2)),
            Note(user_id=regular_user.id, title="b", tags="btc", created_at=NOW - timedelta(days=40)),
            Note(user_id=regular_user.id, title="c", tags=None, created_at=NOW - timedelta(days=1)),
        ]
    )
    await db_session.commit()
    with time_machine.travel(NOW, tick=False):
        response = await client.get("/api/v1/notes/summary", headers=_headers(regular_user))
    assert response.json() == {"total_notes": 3, "notes_this_month": 2, "unique_tags": ["btc", "macro"]}


async def test_scorecard_empty(client: AsyncClient, regular_user: User) -> None:
    response = await client.get("/api/v1/notes/scorecard", headers=_headers(regular_user))
    assert response.json() == {
        "entries": [],
        "summary": {
            "total_scored": 0,
            "unscorable": 0,
            "hit_rate_30d": None,
            "hit_rate_90d": None,
            "by_sentiment": {s: {"n": 0, "hit_rate": None} for s in ("bullish", "bearish", "neutral")},
        },
    }


async def _price_history(db: AsyncSession, symbol: str, points: dict[date, str]) -> None:
    db.add_all(
        [AssetPriceHistory(symbol=symbol, price_date=d, price_eur=Decimal(p), source="test") for d, p in points.items()]
    )
    await db.commit()


async def test_scorecard_verdicts_and_aggregates(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    asset = await _asset(db_session, regular_user, symbol="SCOR", price="150")
    no_history = await _asset(db_session, regular_user, symbol="NOHI", price="10")
    d0 = (NOW - timedelta(days=120)).date()
    d1 = (NOW - timedelta(days=40)).date()
    await _price_history(
        db_session,
        "SCOR",
        {
            d0 - timedelta(days=2): "100",
            d0 + timedelta(days=31): "110",
            d0 + timedelta(days=92): "90",
            d1 + timedelta(days=1): "200",
            d1 + timedelta(days=30): "199",
        },
    )

    def at(day: date) -> datetime:
        return datetime(day.year, day.month, day.day, 9, 0, tzinfo=UTC)

    db_session.add_all(
        [
            Note(
                user_id=regular_user.id,
                title="bull old",
                asset_id=asset.id,
                sentiment="bullish",
                created_at=at(d0) + timedelta(hours=1),
            ),
            Note(user_id=regular_user.id, title="bear old", asset_id=asset.id, sentiment="bearish", created_at=at(d0)),
            Note(
                user_id=regular_user.id,
                title="neutral recent",
                asset_id=asset.id,
                sentiment="neutral",
                created_at=at(d1),
            ),
            Note(
                user_id=regular_user.id,
                title="no history",
                asset_id=no_history.id,
                sentiment="bullish",
                created_at=at(d1),
            ),
            Note(user_id=regular_user.id, title="no sentiment", asset_id=asset.id, created_at=at(d1)),
            Note(user_id=regular_user.id, title="no asset", sentiment="bullish", created_at=at(d1)),
        ]
    )
    await db_session.commit()

    with time_machine.travel(NOW, tick=False):
        response = await client.get("/api/v1/notes/scorecard", headers=_headers(regular_user))
    assert response.status_code == 200
    body = response.json()
    entries = {e["title"]: {k: v for k, v in e.items() if k != "note_id"} for e in body["entries"]}
    assert [e["title"] for e in body["entries"]] == ["neutral recent", "bull old", "bear old"]
    assert entries == {
        "neutral recent": {
            "title": "neutral recent",
            "symbol": "SCOR",
            "sentiment": "neutral",
            "note_date": d1.isoformat(),
            "perf_30d": -0.5,
            "perf_90d": -25.0,
            "verdict_30d": "correct",
            "verdict_90d": "pending",
        },
        "bull old": {
            "title": "bull old",
            "symbol": "SCOR",
            "sentiment": "bullish",
            "note_date": d0.isoformat(),
            "perf_30d": 10.0,
            "perf_90d": -10.0,
            "verdict_30d": "correct",
            "verdict_90d": "incorrect",
        },
        "bear old": {
            "title": "bear old",
            "symbol": "SCOR",
            "sentiment": "bearish",
            "note_date": d0.isoformat(),
            "perf_30d": 10.0,
            "perf_90d": -10.0,
            "verdict_30d": "incorrect",
            "verdict_90d": "correct",
        },
    }
    assert body["summary"] == {
        "total_scored": 3,
        "unscorable": 1,
        "hit_rate_30d": 66.7,
        "hit_rate_90d": 50.0,
        "by_sentiment": {
            "bullish": {"n": 1, "hit_rate": 50.0},
            "bearish": {"n": 1, "hit_rate": 50.0},
            "neutral": {"n": 1, "hit_rate": 100.0},
        },
    }


async def test_notes_require_authentication(client: AsyncClient) -> None:
    for method, url in (("get", "/api/v1/notes"), ("get", "/api/v1/notes/summary"), ("post", "/api/v1/notes")):
        response = await getattr(client, method)(url)
        assert response.status_code == 401
