import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest
import redis.asyncio as aioredis
import time_machine
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis_client import redis_async_url
from app.domains.identity.models import User
from app.domains.market_data.history import reader
from app.domains.notifications.telegram import client as telegram
from app.services import regime_alert_service as service
from tests.conftest import TestSessionLocal
from tests.http_stubs import HttpStub
from tests.sample_portfolio import FROZEN_NOW, seed_history

GOLDEN = Path(__file__).parent / "golden" / "regime_alerts"
UPDATE = os.environ.get("GOLDEN_UPDATE") == "1"
FEAR_GREED = "api.alternative.me"
TELEGRAM = "api.telegram.org"
LAST_REGIME = "regime:global:last"
RECIPIENTS = (
    ("actif@test.com", True, True, "111"),
    ("sans-chat@test.com", True, True, None),
    ("inactif@test.com", False, True, "333"),
    ("sans-telegram@test.com", True, False, "444"),
    ("autre@test.com", True, True, "555"),
)

pytestmark = pytest.mark.usefixtures("empty_test_redis")


def _check(name: str, observed: dict[str, Any]) -> None:
    path = GOLDEN / f"{name}.json"
    rendered = json.dumps(observed, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if UPDATE or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
    assert path.read_text(encoding="utf-8") == rendered, f"golden {name} différent (GOLDEN_UPDATE=1)"


def _telegram(status: int) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"ok": status == 200, "result": {"message_id": 1}}, request=request)

    return handler


@pytest.fixture
def background(monkeypatch: pytest.MonkeyPatch, http_stub: HttpStub) -> HttpStub:
    monkeypatch.setattr(service, "session_factory", TestSessionLocal)
    monkeypatch.setattr(reader, "session_factory", TestSessionLocal)
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "jeton")
    monkeypatch.setattr(telegram, "_redis", None)
    monkeypatch.setattr(telegram.TelegramService, "_client", None)
    http_stub.json(FEAR_GREED, {"data": [{"value": "25"}]})
    return http_stub


@pytest.fixture
async def recipients(db_session: AsyncSession) -> None:
    for email, active, enabled, chat in RECIPIENTS:
        db_session.add(
            User(email=email, password_hash="x", is_active=active, telegram_enabled=enabled, telegram_chat_id=chat)
        )
    await db_session.commit()


async def _redis_state() -> dict[str, Any]:
    client = aioredis.from_url(redis_async_url(), decode_responses=True)
    keys = sorted(await client.keys("*"))
    state = {key: await client.get(key) for key in keys if key == LAST_REGIME or key.startswith("tg:cooldown:")}
    ttl = await client.ttl(LAST_REGIME)
    await client.aclose()
    return {
        "keys": {k: v for k, v in state.items() if k == LAST_REGIME},
        "cooldowns": len(state) - (LAST_REGIME in state),
        "regime_ttl_set": ttl > 0,
    }


async def _remember(regime: str) -> None:
    client = aioredis.from_url(redis_async_url(), decode_responses=True)
    await client.set(LAST_REGIME, regime)
    await client.aclose()


def _sent(http_stub: HttpStub) -> list[dict[str, Any]]:
    messages = [json.loads(r.content) for r in http_stub.requests if r.url.host == TELEGRAM]
    return sorted(({"chat_id": m["chat_id"], "text": m["text"]} for m in messages), key=lambda m: m["chat_id"])


async def _run(http_stub: HttpStub) -> dict[str, Any]:
    http_stub.requests.clear()
    with time_machine.travel(FROZEN_NOW, tick=False):
        result = await service.regime_alert_service.check_and_alert()
    return {"result": result, "sent": _sent(http_stub), "redis": await _redis_state()}


async def _detected(db: AsyncSession, http_stub: HttpStub) -> str:
    with time_machine.travel(FROZEN_NOW, tick=False):
        await seed_history(db)
    seeded = await _run(http_stub)
    return str(seeded["result"]["regime"])


def _other(regime: str) -> str:
    return "bearish" if regime != "bearish" else "bullish"


@pytest.mark.usefixtures("db_session")
async def test_without_btc_history(background: HttpStub) -> None:
    _check("without_history", await _run(background))


async def test_first_run_seeds(db_session: AsyncSession, background: HttpStub) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        await seed_history(db_session)
    _check("first_run", await _run(background))


async def test_unchanged_regime(db_session: AsyncSession, background: HttpStub) -> None:
    await _detected(db_session, background)
    _check("unchanged", await _run(background))


@pytest.mark.usefixtures("recipients")
async def test_mutation_alerts_recipients(db_session: AsyncSession, background: HttpStub) -> None:
    background.on(TELEGRAM, _telegram(200))
    await _remember(_other(await _detected(db_session, background)))
    _check("mutation", await _run(background))


@pytest.mark.usefixtures("recipients")
async def test_mutation_when_telegram_refuses(db_session: AsyncSession, background: HttpStub) -> None:
    background.on(TELEGRAM, _telegram(500))
    await _remember(_other(await _detected(db_session, background)))
    _check("mutation_telegram_refuses", await _run(background))


@pytest.mark.usefixtures("recipients")
async def test_second_mutation_within_cooldown(db_session: AsyncSession, background: HttpStub) -> None:
    background.on(TELEGRAM, _telegram(200))
    regime = await _detected(db_session, background)
    await _remember(_other(regime))
    await _run(background)
    await _remember(_other(regime))
    _check("mutation_within_cooldown", await _run(background))


async def test_fear_greed_unavailable(db_session: AsyncSession, background: HttpStub) -> None:
    background.routes.pop(FEAR_GREED)
    with time_machine.travel(FROZEN_NOW, tick=False):
        await seed_history(db_session)
    _check("fear_greed_unavailable", await _run(background))
