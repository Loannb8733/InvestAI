import json
import math
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import redis
import time_machine

from app.core.redis_client import redis_async_url
from app.domains.strategies.contrarian import CACHE_KEY, CACHE_TTL_S, format_reasoning, refresh_contrarian_stats
from tests.http_stubs import HttpStub

GOLDEN = Path(__file__).parent / "golden" / "contrarian_stats"
UPDATE = os.environ.get("GOLDEN_UPDATE") == "1"
NOW = datetime(2022, 3, 1, 12, 0, tzinfo=UTC)
FIRST_DAY = date(2018, 2, 1)
DAYS = 1460
FEAR_GREED = "api.alternative.me"
YAHOO = "query1.finance.yahoo.com"
CRYPTOCOMPARE = "min-api.cryptocompare.com"

pytestmark = pytest.mark.usefixtures("empty_test_redis")


def _stamp(day: int) -> int:
    return int(datetime.combine(FIRST_DAY + timedelta(days=day), datetime.min.time(), UTC).timestamp())


def _close(day: int) -> float:
    return round(10000 * (1 + 0.001 * day) * (1 + 0.2 * math.sin(day / 60)), 2)


def _fear_greed(request: httpx.Request) -> httpx.Response:
    data = [
        {"value": str(max(0, min(100, int(50 + 45 * math.sin(day / 45))))), "timestamp": str(_stamp(day))}
        for day in reversed(range(DAYS))
    ]
    return httpx.Response(200, json={"data": data}, request=request)


def _yahoo(request: httpx.Request) -> httpx.Response:
    closes: list[float | None] = [_close(day) for day in range(-200, DAYS)]
    closes[10] = None
    quote = {"timestamp": [_stamp(day) for day in range(-200, DAYS)], "indicators": {"quote": [{"close": closes}]}}
    return httpx.Response(200, json={"chart": {"result": [quote]}}, request=request)


def _cryptocompare(request: httpx.Request) -> httpx.Response:
    to_ts, limit = int(request.url.params["toTs"]), int(request.url.params["limit"])
    days = [day for day in range(-200, DAYS) if to_ts - limit * 86400 <= _stamp(day) <= to_ts]
    rows = [{"time": _stamp(day), "close": _close(day)} for day in days]
    return httpx.Response(200, json={"Data": {"Data": rows}}, request=request)


def _unavailable(request: httpx.Request) -> httpx.Response:
    return httpx.Response(503, request=request)


def _client() -> redis.Redis:
    return redis.Redis.from_url(redis_async_url(), decode_responses=True)


def _requests(http_stub: HttpStub) -> list[str]:
    return [f"{r.url.host}{r.url.path}" for r in http_stub.requests]


def _run(http_stub: HttpStub) -> dict[str, Any]:
    with time_machine.travel(NOW, tick=False):
        try:
            outcome: dict[str, Any] = {"result": refresh_contrarian_stats()}
        except Exception as exc:  # noqa: BLE001
            outcome = {"error": f"{type(exc).__name__}: {exc}"}
    client = _client()
    cached = client.get(CACHE_KEY)
    ttl = client.ttl(CACHE_KEY)
    client.close()
    outcome["cached"] = json.loads(cached) if cached else None
    outcome["cache_ttl_is_8_days"] = ttl == CACHE_TTL_S
    outcome["requests"] = _requests(http_stub)
    return outcome


def _check(name: str, observed: dict[str, Any]) -> None:
    path = GOLDEN / f"{name}.json"
    rendered = json.dumps(observed, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if UPDATE or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
    assert path.read_text(encoding="utf-8") == rendered, f"golden {name} différent (GOLDEN_UPDATE=1)"


def test_refresh_from_yahoo(http_stub: HttpStub) -> None:
    http_stub.on(FEAR_GREED, _fear_greed)
    http_stub.on(YAHOO, _yahoo)
    _check("refresh_yahoo", _run(http_stub))


def test_refresh_falls_back_to_cryptocompare(http_stub: HttpStub) -> None:
    http_stub.on(FEAR_GREED, _fear_greed)
    http_stub.on(YAHOO, _unavailable)
    http_stub.on(CRYPTOCOMPARE, _cryptocompare)
    _check("refresh_cryptocompare", _run(http_stub))


def test_failure_keeps_the_cached_stats(http_stub: HttpStub) -> None:
    client = _client()
    client.setex(CACHE_KEY, 3600, json.dumps({"median_12m_pct": 42.0}))
    client.close()
    http_stub.on(FEAR_GREED, _fear_greed)
    http_stub.on(YAHOO, _unavailable)
    http_stub.on(CRYPTOCOMPARE, _unavailable)
    _check("refresh_all_sources_down", _run(http_stub))


def test_fear_greed_unavailable(http_stub: HttpStub) -> None:
    http_stub.on(FEAR_GREED, _unavailable)
    _check("refresh_fear_greed_down", _run(http_stub))


def test_without_extreme_fear(http_stub: HttpStub) -> None:
    def calm(request: httpx.Request) -> httpx.Response:
        data = [{"value": "60", "timestamp": str(_stamp(day))} for day in range(DAYS)]
        return httpx.Response(200, json={"data": data}, request=request)

    http_stub.on(FEAR_GREED, calm)
    http_stub.on(YAHOO, _yahoo)
    _check("refresh_without_fear", _run(http_stub))


def test_reasoning_sentences() -> None:
    stats = {"median_12m_pct": 87.4, "win_rate_12m_pct": 81, "period_start": "2018-02-01"}
    _check(
        "reasoning",
        {
            "with_stats": format_reasoning(12, stats),
            "without_stats": format_reasoning(12, None),
            "without_median": format_reasoning(None, {"median_12m_pct": None}),
            "without_period": format_reasoning(20, {"median_12m_pct": -3.2, "win_rate_12m_pct": 40}),
        },
    )
