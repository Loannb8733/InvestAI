from typing import Any

from app.domains.market_data.history.reader import local_series
from app.domains.predictions.types import HISTORY_DAYS
from app.ml.regime_detector import _rsi

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _diagnostic_entry(
    asset_data: dict[str, Any],
    top_prob: float,
    rsi_val: float | None,
    total_value: float,
) -> dict[str, Any]:
    sym = asset_data["symbol"]
    dom = asset_data.get("dominant_regime", "")
    probs = asset_data.get("probabilities", {})

    signals = []
    sell_priority = "low"
    if rsi_val is not None and rsi_val > 70:
        signals.append(f"RSI suracheté ({rsi_val:.0f})")
        sell_priority = "high"
    if dom == "top":
        signals.append("Régime Sommet détecté")
        sell_priority = "high" if sell_priority != "high" else sell_priority
    if probs.get("bearish", 0) > 0.25:
        signals.append(f"Probabilité baissière {probs['bearish'] * 100:.0f}%")
        sell_priority = "medium" if sell_priority == "low" else sell_priority

    weight_pct = 0.0
    if total_value > 0 and asset_data.get("value", 0) > 0:
        weight_pct = asset_data["value"] / total_value * 100

    return {
        "symbol": sym,
        "name": asset_data.get("name", sym),
        "dominant_regime": dom,
        "top_bearish_prob": round(top_prob * 100, 1),
        "rsi": round(rsi_val, 1) if rsi_val is not None else None,
        "weight_pct": round(weight_pct, 1),
        "signals": signals,
        "sell_priority": sell_priority,
    }


async def distribution_diagnostic(
    per_asset: list[dict[str, Any]],
    btc_prices: list[float] | None,
    total_value: float,
) -> list[dict[str, Any]]:
    """Actifs en zone de distribution (sommet + baissier ≥ 40 %), croisés avec le RSI,
    par priorité de vente décroissante."""
    diagnostic: list[dict[str, Any]] = []
    for asset_data in per_asset:
        probs = asset_data.get("probabilities", {})
        top_prob = probs.get("top", 0) + probs.get("bearish", 0)
        if top_prob < 0.40:
            continue

        sym = asset_data["symbol"]
        rsi_val = None
        a_prices_diag = (await local_series(sym, HISTORY_DAYS)).prices or None
        if sym == "BTC" and btc_prices:
            a_prices_diag = btc_prices

        if a_prices_diag and len(a_prices_diag) >= 15:
            rsi_val = _rsi(a_prices_diag, period=14)

        diagnostic.append(_diagnostic_entry(asset_data, top_prob, rsi_val, total_value))

    diagnostic.sort(key=lambda d: PRIORITY_ORDER.get(d["sell_priority"], 3))
    return diagnostic
