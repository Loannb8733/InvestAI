"""Reproducible backtest behind the conviction-buy reasoning stat.

Measures the *real* forward return of BTC after the Crypto Fear & Greed
Index drops below a threshold (default 25 = "extreme fear"). The figures
quoted in ``ai_strategy_service._build_conviction_buy_strategy`` come from
running this script — they are computed from public data, not invented.

Data sources
------------
- Fear & Greed Index : https://api.alternative.me/fng/?limit=0
  (same source the app uses everywhere; history since 2018-02-01)
- BTC daily close (USD) : Yahoo Finance BTC-USD 1d (full history, one request)
  Binance is not used: it rate-bans shared cloud IPs (Render) with HTTP 418.

Method
------
For every UTC day where F&G < THRESHOLD, take BTC close that day and the
close H days later, compute the return. Report count, median, mean,
win-rate and dispersion per horizon. Also report a de-clustered view
(one entry per maximal run of consecutive fear days) to expose the
overlap bias that inflates the per-day mean.

Reference run (2018-02-01 → 2026-06-04), per-day, 365d horizon:
    n=508 | median +36.5% | mean +100.1% | win 61% | min -70.0% | max +1092.1%
The mean is dominated by buying into the March-2020 COVID crash; the
median is the representative central tendency. Short-term (90d) median
is negative (-3.9%). Re-run periodically to refresh the quoted numbers.

Usage
-----
    python -m scripts.fng_contrarian_backtest            # threshold 25
    python -m scripts.fng_contrarian_backtest --threshold 20
"""

from __future__ import annotations

import argparse
import datetime as dt
import statistics

import httpx
import pandas as pd

HORIZONS = (30, 90, 180, 365)


def fetch_fng() -> pd.DataFrame:
    """Full Fear & Greed history as (date, value)."""
    resp = httpx.get("https://api.alternative.me/fng/?limit=0&format=json", timeout=30.0)
    resp.raise_for_status()
    df = pd.DataFrame(resp.json()["data"])
    df["value"] = df["value"].astype(int)
    df["date"] = pd.to_datetime(df["timestamp"].astype(int), unit="s", utc=True).dt.normalize()
    return df[["date", "value"]].sort_values("date").reset_index(drop=True)


def fetch_btc_daily() -> pd.DataFrame:
    """BTC daily close (USD) from Yahoo Finance — full history in one request."""
    resp = httpx.get(
        "https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD",
        params={
            "period1": int(dt.datetime(2017, 8, 1, tzinfo=dt.timezone.utc).timestamp()),
            "period2": int(dt.datetime.now(dt.timezone.utc).timestamp()),
            "interval": "1d",
        },
        headers={"User-Agent": "Mozilla/5.0"},  # Yahoo rejects the default httpx UA
        timeout=30.0,
    )
    resp.raise_for_status()
    result = resp.json()["chart"]["result"][0]
    df = pd.DataFrame({"ts": result["timestamp"], "close": result["indicators"]["quote"][0]["close"]})
    df = df.dropna(subset=["close"])
    df["date"] = pd.to_datetime(df["ts"], unit="s", utc=True).dt.normalize()
    df["close"] = df["close"].astype(float)
    return df[["date", "close"]].drop_duplicates("date").sort_values("date").reset_index(drop=True)


def _forward_returns(closes: pd.Series, entry_dates, horizon: int) -> list[float]:
    out: list[float] = []
    for d in entry_dates:
        future = closes[closes.index >= d + pd.Timedelta(days=horizon)]
        if len(future) == 0:
            continue  # not enough forward data yet
        out.append(future.iloc[0] / closes.loc[d] - 1.0)
    return out


def _summarize(label: str, returns: list[float]) -> None:
    if not returns:
        print(f"  {label:>5}: aucun signal")
        return
    pct = [r * 100 for r in returns]
    wins = sum(1 for r in returns if r > 0)
    print(
        f"  {label:>5}: n={len(pct):4d} | "
        f"médiane={statistics.median(pct):+6.1f}% | "
        f"moyenne={statistics.mean(pct):+6.1f}% | "
        f"win={wins / len(pct) * 100:4.0f}% | "
        f"min={min(pct):+6.1f}% | max={max(pct):+6.1f}%"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=int, default=25, help="F&G threshold (default 25)")
    args = parser.parse_args()
    threshold = args.threshold

    fng = fetch_fng()
    btc = fetch_btc_daily()
    df = fng.merge(btc, on="date", how="inner").sort_values("date").reset_index(drop=True).set_index("date")
    closes = df["close"]

    print(f"F&G : {fng['date'].min().date()} → {fng['date'].max().date()} ({len(fng)} jours)")
    print(f"BTC : {btc['date'].min().date()} → {btc['date'].max().date()} ({len(btc)} jours)")
    print(f"Alignés : {len(df)} | jours F&G < {threshold} : {(df['value'] < threshold).sum()}\n")

    per_day = df.index[df["value"] < threshold]
    print(f"=== Forward BTC après un jour F&G < {threshold} (par jour) ===")
    for h in HORIZONS:
        _summarize(f"{h}j", _forward_returns(closes, per_day, h))

    mask = (df["value"] < threshold).values
    episodes = [df.index[i] for i in range(len(mask)) if mask[i] and (i == 0 or not mask[i - 1])]
    print(f"\nÉpisodes de peur distincts : {len(episodes)}")
    print("=== Forward depuis le 1er jour de chaque épisode ===")
    for h in HORIZONS:
        _summarize(f"{h}j", _forward_returns(closes, episodes, h))


if __name__ == "__main__":
    main()
