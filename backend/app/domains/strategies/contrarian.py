import json
import logging
import statistics
from datetime import UTC, datetime
from typing import Any

import httpx
import pandas as pd

from app.core.errors import ServiceUnavailableError
from app.core.redis_client import _get_redis_txt, redis_async_url, redis_client_kwargs
from app.core.redis_guard import GuardedSyncRedis

logger = logging.getLogger(__name__)

EXTREME_FEAR = 25
HORIZON_12M = 365
HORIZON_SHORT = 90
MIN_BTC_ROWS = 300
CRYPTOCOMPARE_MAX_PAGES = 20
CACHE_KEY = "contrarian_stats:btc:fng"
CACHE_TTL_S = 8 * 86400
FNG_URL = "https://api.alternative.me/fng/?limit=0&format=json"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD"
CRYPTOCOMPARE_URL = "https://min-api.cryptocompare.com/data/v2/histoday"
HTTP_TIMEOUT_S = 30.0
_BTC_START = datetime(2017, 8, 1, tzinfo=UTC)


def _fetch_fear_greed() -> list[dict[str, Any]]:
    response = httpx.get(FNG_URL, timeout=HTTP_TIMEOUT_S)
    response.raise_for_status()
    data: list[dict[str, Any]] = response.json()["data"]
    return data


def _daily_closes(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[["date", "close"]].drop_duplicates("date").sort_values("date").reset_index(drop=True)


def _btc_from_yahoo() -> pd.DataFrame:
    response = httpx.get(
        YAHOO_URL,
        params={
            "period1": int(_BTC_START.timestamp()),
            "period2": int(datetime.now(UTC).timestamp()),
            "interval": "1d",
        },
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=HTTP_TIMEOUT_S,
    )
    response.raise_for_status()
    result = response.json()["chart"]["result"][0]
    frame = pd.DataFrame({"ts": result["timestamp"], "close": result["indicators"]["quote"][0]["close"]})
    frame = frame.dropna(subset=["close"])
    frame["date"] = pd.to_datetime(frame["ts"], unit="s", utc=True).dt.normalize()
    frame["close"] = frame["close"].astype(float)
    return _daily_closes(frame)


def _cryptocompare_rows() -> list[dict[str, Any]]:
    start_ts = int(_BTC_START.timestamp())
    to_ts = int(datetime.now(UTC).timestamp())
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for _ in range(CRYPTOCOMPARE_MAX_PAGES):
        response = httpx.get(
            CRYPTOCOMPARE_URL,
            params={"fsym": "BTC", "tsym": "USD", "limit": 2000, "toTs": to_ts},
            timeout=HTTP_TIMEOUT_S,
        )
        response.raise_for_status()
        fresh = [d for d in response.json().get("Data", {}).get("Data", []) if d.get("close") and d["time"] not in seen]
        if not fresh:
            return rows
        seen.update(d["time"] for d in fresh)
        rows.extend(fresh)
        oldest = min(d["time"] for d in fresh)
        if oldest <= start_ts:
            return rows
        to_ts = oldest - 86_400
    logger.warning("CryptoCompare pagination hit max_pages=%d cap", CRYPTOCOMPARE_MAX_PAGES)
    return rows


def _btc_from_cryptocompare() -> pd.DataFrame:
    rows = _cryptocompare_rows()
    if not rows:
        raise ValueError("CryptoCompare returned no rows")
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["time"], unit="s", utc=True).dt.normalize()
    frame["close"] = frame["close"].astype(float)
    return _daily_closes(frame[frame["date"] >= pd.Timestamp(_BTC_START)])


def _btc_daily() -> pd.DataFrame:
    """Clôtures quotidiennes du BTC en USD : Yahoo, puis CryptoCompare ; Binance refuse les IP de Render."""
    errors: list[str] = []
    for name, fetch in (("yahoo", _btc_from_yahoo), ("cryptocompare", _btc_from_cryptocompare)):
        try:
            frame = fetch()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {type(exc).__name__} {exc}")
            continue
        if len(frame) > MIN_BTC_ROWS:
            logger.info("contrarian: BTC daily from %s (%d rows)", name, len(frame))
            return frame
        errors.append(f"{name}: only {len(frame)} rows")
    raise RuntimeError("All BTC daily sources failed: " + " | ".join(errors))


def _forward_returns(closes: pd.Series, entry_dates: pd.Index, horizon: int) -> list[float]:
    returns: list[float] = []
    for day in entry_dates:
        future = closes[closes.index >= day + pd.Timedelta(days=horizon)]
        if len(future):
            returns.append(float(future.iloc[0]) / float(closes.loc[day]) - 1.0)
    return returns


def compute_contrarian_stats(threshold: int = EXTREME_FEAR) -> dict[str, Any]:
    """Rendement du BTC 12 mois et 90 jours après chaque jour où Fear & Greed était sous ``threshold``."""
    fear_greed = pd.DataFrame(_fetch_fear_greed())
    fear_greed["value"] = fear_greed["value"].astype(int)
    fear_greed["date"] = pd.to_datetime(fear_greed["timestamp"].astype(int), unit="s", utc=True).dt.normalize()
    fear_greed = fear_greed[["date", "value"]].sort_values("date").reset_index(drop=True)
    joined = fear_greed.merge(_btc_daily(), on="date", how="inner").sort_values("date").set_index("date")
    closes = joined["close"]
    fear_days = joined.index[joined["value"] < threshold]
    returns_12m = _forward_returns(closes, fear_days, HORIZON_12M)
    returns_90d = _forward_returns(closes, fear_days, HORIZON_SHORT)
    if not returns_12m:
        raise ValueError("Backtest produced no 12-month samples")
    pct_12m = [r * 100 for r in returns_12m]
    wins = sum(1 for r in returns_12m if r > 0)
    return {
        "threshold": threshold,
        "horizon_days": HORIZON_12M,
        "n": len(pct_12m),
        "median_12m_pct": round(statistics.median(pct_12m), 1),
        "mean_12m_pct": round(statistics.mean(pct_12m), 1),
        "win_rate_12m_pct": round(wins / len(pct_12m) * 100),
        "min_12m_pct": round(min(pct_12m), 1),
        "max_12m_pct": round(max(pct_12m), 1),
        "median_90d_pct": round(statistics.median([r * 100 for r in returns_90d]), 1) if returns_90d else None,
        "period_start": joined.index.min().date().isoformat(),
        "period_end": joined.index.max().date().isoformat(),
        "as_of": datetime.now(UTC).isoformat(),
    }


def refresh_contrarian_stats() -> dict[str, Any]:
    """Recalcule le backtest et le met en cache 8 jours ; en échec, lève ``ServiceUnavailableError`` et garde le
    cache."""
    try:
        stats = compute_contrarian_stats()
        GuardedSyncRedis.from_url(redis_async_url(), decode_responses=True, **redis_client_kwargs()).setex(
            CACHE_KEY, CACHE_TTL_S, json.dumps(stats)
        )
    except Exception as exc:
        raise ServiceUnavailableError(f"Statistiques contrarian non rafraîchies : {exc}") from exc
    logger.info(
        "Refreshed contrarian stats: n=%s, median_12m=%s%%, win=%s%%",
        stats["n"],
        stats["median_12m_pct"],
        stats["win_rate_12m_pct"],
    )
    return {"status": "ok", **stats}


async def cached_contrarian_stats() -> dict[str, Any] | None:
    """Statistiques en cache, ou None si absentes ou si Redis est injoignable."""
    try:
        data = await (await _get_redis_txt()).get(CACHE_KEY)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Redis contrarian-stats cache miss: %s", exc)
        return None
    if not data:
        return None
    stats: dict[str, Any] = json.loads(data)
    return stats


def format_reasoning(fear_greed: int | None, stats: dict[str, Any] | None) -> str:
    """Phrase du raisonnement d'achat conviction ; sans statistiques, une phrase qualitative sans chiffre inventé."""
    if not stats or stats.get("median_12m_pct") is None:
        return (
            f"Peur extrême (Fear & Greed {fear_greed}) — historiquement un point "
            "d'entrée contrarien de long terme, mais sans garantie à court terme."
        )
    year = str(stats.get("period_start", ""))[:4] or "2018"
    return (
        f"Peur extrême (Fear & Greed {fear_greed}). Depuis {year}, acheter BTC à "
        f"ces niveaux a rapporté en médiane {stats['median_12m_pct']:+.0f}% sur 12 mois "
        f"({stats['win_rate_12m_pct']}% de cas positifs), mais souvent une baisse à court terme et de "
        "fortes variations."
    )
