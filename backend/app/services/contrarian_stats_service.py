"""Contrarian (Fear & Greed) backtest statistics.

Computes the *real* forward return of BTC after the Crypto Fear & Greed
Index drops below a threshold. The conviction-buy strategy quotes these
figures in its reasoning. A daily Celery task refreshes them into Redis
so the displayed numbers always reflect the latest data — no manual
re-run required.

Data sources (same the app already uses):
- Fear & Greed : https://api.alternative.me/fng/?limit=0  (since 2018-02-01)
- BTC daily close (USD) : Yahoo Finance BTC-USD 1d  (since 2014, one request)
  with CryptoCompare histoday as fallback. Binance is NOT used: both
  api.binance.com and data-api.binance.vision rate-ban shared cloud IPs
  (Render) with HTTP 418.

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
_BTC_START = datetime(2017, 8, 1, tzinfo=timezone.utc)


def _fetch_fng(httpx_mod):  # type: ignore[no-untyped-def]
    resp = httpx_mod.get("https://api.alternative.me/fng/?limit=0&format=json", timeout=30.0)
    resp.raise_for_status()
    return resp.json()["data"]


def _fetch_btc_yahoo(httpx_mod, pd_mod):  # type: ignore[no-untyped-def]
    """BTC daily close (USD) from Yahoo Finance — full history in one request."""
    resp = httpx_mod.get(
        "https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD",
        params={
            "period1": int(_BTC_START.timestamp()),
            "period2": int(datetime.now(timezone.utc).timestamp()),
            "interval": "1d",
        },
        headers={"User-Agent": "Mozilla/5.0"},  # Yahoo rejects the default httpx UA
        timeout=30.0,
    )
    resp.raise_for_status()
    result = resp.json()["chart"]["result"][0]
    df = pd_mod.DataFrame({"ts": result["timestamp"], "close": result["indicators"]["quote"][0]["close"]})
    df = df.dropna(subset=["close"])
    df["date"] = pd_mod.to_datetime(df["ts"], unit="s", utc=True).dt.normalize()
    df["close"] = df["close"].astype(float)
    return df[["date", "close"]].drop_duplicates("date").sort_values("date").reset_index(drop=True)


def _fetch_btc_cryptocompare(httpx_mod, pd_mod):  # type: ignore[no-untyped-def]
    """BTC daily close (USD) from CryptoCompare histoday — paginated fallback."""
    base = "https://min-api.cryptocompare.com/data/v2/histoday"
    start_ts = int(_BTC_START.timestamp())
    to_ts = int(datetime.now(timezone.utc).timestamp())
    rows: list = []
    seen: set = set()
    # Hard cap on pages: ~10y of daily data at limit=2000 needs <3 pages.
    # 20 pages is a defensive ceiling that protects against an API regression
    # where ``oldest`` stops decreasing — we'd otherwise spin until rate-limited.
    max_pages = 20
    for _ in range(max_pages):
        resp = httpx_mod.get(base, params={"fsym": "BTC", "tsym": "USD", "limit": 2000, "toTs": to_ts}, timeout=30.0)
        resp.raise_for_status()
        data = [d for d in resp.json().get("Data", {}).get("Data", []) if d.get("close")]
        fresh = [d for d in data if d["time"] not in seen]
        if not fresh:
            break
        seen.update(d["time"] for d in fresh)
        rows.extend(fresh)
        oldest = min(d["time"] for d in fresh)
        if oldest <= start_ts:
            break
        to_ts = oldest - 86_400
    else:
        logger.warning("CryptoCompare pagination hit max_pages=%d cap", max_pages)
    if not rows:
        raise ValueError("CryptoCompare returned no rows")
    df = pd_mod.DataFrame(rows)
    df["date"] = pd_mod.to_datetime(df["time"], unit="s", utc=True).dt.normalize()
    df["close"] = df["close"].astype(float)
    df = df[df["date"] >= pd_mod.Timestamp(_BTC_START)]
    return df[["date", "close"]].drop_duplicates("date").sort_values("date").reset_index(drop=True)


def _fetch_btc_daily(httpx_mod, pd_mod):  # type: ignore[no-untyped-def]
    """Daily BTC close (USD) as DataFrame[date(UTC, normalized), close].

    Tries Yahoo Finance first (one request, full history, tolerates datacenter
    IPs — the app already uses it for stocks), then CryptoCompare. Binance is
    unusable from cloud hosts (HTTP 418 on every host).
    """
    errors: list[str] = []
    for name, fn in (("yahoo", _fetch_btc_yahoo), ("cryptocompare", _fetch_btc_cryptocompare)):
        try:
            df = fn(httpx_mod, pd_mod)
            if df is not None and len(df) > 300:
                logger.info("contrarian: BTC daily from %s (%d rows)", name, len(df))
                return df
            errors.append(f"{name}: only {0 if df is None else len(df)} rows")
        except Exception as exc:  # noqa: BLE001 — try the next source
            errors.append(f"{name}: {type(exc).__name__} {exc}")
    raise RuntimeError("All BTC daily sources failed: " + " | ".join(errors))


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

    btc = _fetch_btc_daily(httpx, pd)

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
