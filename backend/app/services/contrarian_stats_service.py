"""Contrarian (Fear & Greed) backtest statistics.

Computes the *real* forward return of BTC after the Crypto Fear & Greed
Index drops below a threshold. The conviction-buy strategy quotes these
figures in its reasoning. A daily Celery task refreshes them into Redis
so the displayed numbers always reflect the latest data — no manual
re-run required.

Data sources (same the app already uses):
- Fear & Greed : https://api.alternative.me/fng/?limit=0  (since 2018-02-01)
- BTC daily close (USD) : Binance klines BTCUSDT 1d  (since 2017-08)

Everything here is synchronous (httpx + pandas) so it runs cleanly inside
a Celery worker. The result is a small JSON-serializable dict.
"""

from __future__ import annotations

import logging
import statistics
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 25
HORIZON_12M = 365
HORIZON_SHORT = 90
_BTC_START_MS = 1_501_545_600_000  # 2017-08-01T00:00:00Z


def _fetch_fng(httpx_mod):  # type: ignore[no-untyped-def]
    resp = httpx_mod.get("https://api.alternative.me/fng/?limit=0&format=json", timeout=30.0)
    resp.raise_for_status()
    return resp.json()["data"]


def _fetch_btc_daily(httpx_mod):  # type: ignore[no-untyped-def]
    # Use Binance's public market-data host (data-api.binance.vision) instead of
    # api.binance.com: the latter rate-bans shared cloud IPs (Render) with HTTP 418
    # when paginating ~8 years of klines. data-api.binance.vision serves the same
    # /api/v3/klines schema and tolerates this from datacenter IPs.
    base = "https://data-api.binance.vision/api/v3/klines"
    start = _BTC_START_MS
    rows: list = []
    while True:
        resp = httpx_mod.get(
            base,
            params={"symbol": "BTCUSDT", "interval": "1d", "startTime": start, "limit": 1000},
            timeout=30.0,
        )
        resp.raise_for_status()
        chunk = resp.json()
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < 1000:
            break
        start = chunk[-1][0] + 86_400_000
    return rows


def _forward_returns(closes, entry_dates, horizon: int, pd_mod) -> list[float]:  # type: ignore[no-untyped-def]
    out: list[float] = []
    for d in entry_dates:
        future = closes[closes.index >= d + pd_mod.Timedelta(days=horizon)]
        if len(future) == 0:
            continue  # not enough forward data yet
        out.append(float(future.iloc[0]) / float(closes.loc[d]) - 1.0)
    return out


def compute_contrarian_stats(threshold: int = DEFAULT_THRESHOLD) -> dict[str, Any]:
    """Run the backtest and return a JSON-serializable stats dict.

    Raises on network/parse errors so the caller (Celery task) can log and
    keep the previously cached value instead of overwriting with garbage.
    """
    import httpx
    import pandas as pd

    fng_raw = _fetch_fng(httpx)
    fng = pd.DataFrame(fng_raw)
    fng["value"] = fng["value"].astype(int)
    fng["date"] = pd.to_datetime(fng["timestamp"].astype(int), unit="s", utc=True).dt.normalize()
    fng = fng[["date", "value"]].sort_values("date").reset_index(drop=True)

    btc_raw = _fetch_btc_daily(httpx)
    btc = pd.DataFrame(
        btc_raw,
        columns=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "qav",
            "trades",
            "tbav",
            "tqav",
            "ignore",
        ],
    )
    btc["date"] = pd.to_datetime(btc["open_time"], unit="ms", utc=True).dt.normalize()
    btc["close"] = btc["close"].astype(float)
    btc = btc[["date", "close"]].drop_duplicates("date").sort_values("date").reset_index(drop=True)

    df = fng.merge(btc, on="date", how="inner").sort_values("date").reset_index(drop=True).set_index("date")
    closes = df["close"]
    fear_days = df.index[df["value"] < threshold]

    rets_12m = _forward_returns(closes, fear_days, HORIZON_12M, pd)
    rets_90d = _forward_returns(closes, fear_days, HORIZON_SHORT, pd)
    if not rets_12m:
        raise ValueError("Backtest produced no 12-month samples")

    pct_12m = [r * 100 for r in rets_12m]
    wins = sum(1 for r in rets_12m if r > 0)

    return {
        "threshold": threshold,
        "horizon_days": HORIZON_12M,
        "n": len(pct_12m),
        "median_12m_pct": round(statistics.median(pct_12m), 1),
        "mean_12m_pct": round(statistics.mean(pct_12m), 1),
        "win_rate_12m_pct": round(wins / len(pct_12m) * 100),
        "min_12m_pct": round(min(pct_12m), 1),
        "max_12m_pct": round(max(pct_12m), 1),
        "median_90d_pct": round(statistics.median([r * 100 for r in rets_90d]), 1) if rets_90d else None,
        "period_start": df.index.min().date().isoformat(),
        "period_end": df.index.max().date().isoformat(),
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


def format_reasoning(fear_greed: Optional[int], stats: Optional[dict[str, Any]]) -> str:
    """Build a short, precise reasoning sentence from cached stats.

    Falls back to a qualitative sentence (no numbers) when stats are absent,
    so we never display a fabricated figure.
    """
    if not stats or stats.get("median_12m_pct") is None:
        return (
            f"Peur extrême (Fear & Greed {fear_greed}) — historiquement un point "
            "d'entrée contrarien de long terme, mais sans garantie à court terme."
        )
    year = str(stats.get("period_start", ""))[:4] or "2018"
    median = stats["median_12m_pct"]
    win = stats["win_rate_12m_pct"]
    return (
        f"Peur extrême (Fear & Greed {fear_greed}). Depuis {year}, acheter BTC à "
        f"ces niveaux a rapporté en médiane {median:+.0f}% sur 12 mois "
        f"({win}% de cas positifs), mais souvent une baisse à court terme et de "
        "fortes variations."
    )
