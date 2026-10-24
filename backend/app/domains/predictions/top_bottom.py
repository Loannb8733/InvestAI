from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from numpy.typing import NDArray

from app.domains.predictions.levels import support_resistance

PIVOT_PHASES = [
    (0, 15, "Creux", "Accumulation"),
    (15, 40, "Accumulation", "Expansion"),
    (40, 65, "Expansion", "Distribution"),
    (65, 85, "Distribution", "Euphorie"),
    (85, 100, "Euphorie", "Creux"),
]


@dataclass(frozen=True, slots=True)
class _Inputs:
    current_price: float
    mu: float
    theta: float
    sigma: float
    support: float
    resistance: float
    p5: float
    p10: float
    p90: float
    p95: float
    cyc_pos: float
    asset_adj: float


def time_to_pivot(
    cycle_position: int,
    btc_regime: dict[str, Any] | None,
    btc_estimate: dict[str, Any] | None,
) -> dict[str, Any]:
    """Jours avant la prochaine phase : distance à la borne, vitesse tirée du theta OU du BTC, plafond de 90 jours."""
    current_phase = "Inconnu"
    next_phase = "Inconnu"
    distance_to_boundary = 50

    for lo, hi, name, nxt in PIVOT_PHASES:
        if lo <= cycle_position < hi:
            current_phase = name
            next_phase = nxt
            distance_to_boundary = hi - cycle_position
            break
    if cycle_position >= 100:
        current_phase = "Euphorie"
        next_phase = "Creux"
        distance_to_boundary = 5

    theta = 0.02
    if btc_estimate and btc_estimate.get("ou_parameters"):
        theta = btc_estimate["ou_parameters"].get("theta", 0.02)

    days_per_unit = max(0.8, 2.5 - (theta - 0.01) * 37.5)
    estimated_days = max(3, round(distance_to_boundary * days_per_unit))
    estimated_days = min(estimated_days, 90)

    confidence = 0.5
    if btc_regime:
        confidence = min(0.85, max(0.2, btc_regime.get("confidence", 0.5)))

    return {
        "current_phase": current_phase,
        "next_phase": next_phase,
        "estimated_days": estimated_days,
        "confidence": round(confidence, 2),
        "cycle_position": cycle_position,
    }


def _ou_parameters(arr: NDArray[np.float64]) -> tuple[float, float, float]:
    n = len(arr)
    mu = float(np.mean(arr[-200:])) if n >= 200 else float(np.median(arr))

    log_prices = np.log(np.maximum(arr, 1e-10))
    log_returns = np.diff(log_prices)

    theta: float
    if n >= 10:
        y = log_prices[1:]
        x = log_prices[:-1]
        x_mean = float(np.mean(x))
        cov_xy = float(np.mean((x - x_mean) * (y - float(np.mean(y)))))
        var_x = float(np.var(x))
        phi = cov_xy / max(var_x, 1e-15)
        phi = float(np.clip(phi, 0.01, 0.999))
        theta = -np.log(phi)
    else:
        theta = 0.05

    sigma = float(np.std(log_returns)) if len(log_returns) > 1 else 0.02
    return mu, theta, sigma


def _asset_adjustment(sigma: float, theta: float) -> float:
    vol_factor = max(0.5, 1.0 - (sigma - 0.02) * 7.5)
    theta_factor = max(0.5, 1.0 - (theta - 0.005) * 11)
    return (vol_factor + theta_factor) / 2


def _bottom(i: _Inputs) -> tuple[float, int]:
    current_price, mu, theta, sigma = i.current_price, i.mu, i.theta, i.sigma
    if current_price > mu:
        bottom_price = max(i.support, min(mu * 0.95, i.p10))
    else:
        bottom_price = max(i.p5, min(i.support, current_price * 0.85))

    min_bottom_distance = max(0.05, sigma * np.sqrt(30) * 1.5)
    bottom_price = min(bottom_price, current_price * (1 - min_bottom_distance))

    ou_bottom_days = 30
    if current_price > bottom_price and theta > 1e-4:
        if abs(current_price - mu) > 1e-10 and abs(bottom_price - mu) > 1e-10:
            ratio = abs(bottom_price - mu) / abs(current_price - mu)
            ratio = float(np.clip(ratio, 0.01, 0.99))
            ou_bottom_days = int(-np.log(ratio) / theta)
        else:
            ou_bottom_days = int(2.3 / theta)

    price_distance_pct = abs(current_price - bottom_price) / current_price
    daily_move = sigma if sigma > 0.005 else 0.02
    vol_bottom_days = max(5, int(price_distance_pct / daily_move))

    ou_bottom_days = min(ou_bottom_days, 120)
    bottom_days = max(vol_bottom_days, (ou_bottom_days + vol_bottom_days) // 2)
    bottom_days = max(3, int(bottom_days * i.asset_adj))

    if i.cyc_pos < 15:
        bottom_days = max(3, int(bottom_days * 0.4))
    elif i.cyc_pos < 30:
        bottom_days = max(5, int(bottom_days * 0.65))

    bottom_days = max(3, min(180, bottom_days))
    return bottom_price, bottom_days


def _top(i: _Inputs, bottom_price: float, bottom_days: int) -> tuple[float, int]:
    current_price, mu, theta, sigma = i.current_price, i.mu, i.theta, i.sigma
    if current_price < mu:
        top_price = min(i.resistance, max(mu * 1.05, i.p90))
    else:
        top_price = min(i.p95, max(i.resistance, current_price * 1.15))

    min_top_distance = max(0.05, sigma * np.sqrt(60) * 1.5)
    top_price = max(top_price, current_price * (1 + min_top_distance))

    daily_move = sigma if sigma > 0.005 else 0.02
    top_distance_pct = abs(top_price - bottom_price) / max(bottom_price, 1e-10)
    vol_recovery_days = max(10, int(top_distance_pct / daily_move))

    ou_recovery_days = 60
    if theta > 1e-4:
        distance_bottom_to_top = abs(top_price - bottom_price)
        distance_bottom_to_mu = abs(mu - bottom_price)
        if distance_bottom_to_mu > 1e-10 and distance_bottom_to_top > 1e-10:
            ratio = min(0.99, distance_bottom_to_mu / distance_bottom_to_top)
            ratio = max(0.01, ratio)
            ou_recovery_days = min(120, int(-np.log(ratio) / theta))

    recovery_days = max(vol_recovery_days, (ou_recovery_days + vol_recovery_days) // 2)
    top_days = bottom_days + max(10, recovery_days)

    if i.cyc_pos > 85:
        top_days = max(14, int(top_days * 0.3))
    elif i.cyc_pos > 70:
        top_days = max(14, int(top_days * 0.6))

    top_days = max(bottom_days + 7, int(top_days * i.asset_adj))
    top_days = max(bottom_days + 7, min(180, top_days))
    return top_price, top_days


def _confidence(regime_conf: float, theta: float, n: int) -> float:
    theta_reliability = min(1.0, theta / 0.05)
    data_sufficiency = min(1.0, n / 120)
    raw_conf = regime_conf * 0.50 + theta_reliability * 0.25 + data_sufficiency * 0.25
    return round(max(0.15, min(0.85, raw_conf)), 2)


def top_bottom_estimate(
    symbol: str,
    prices: list[float],
    current_price: float,
    regime_info: dict[str, Any] | None = None,
    cycle_position: float | None = None,
) -> dict[str, Any]:
    """Prochain creux et sommet (prix, date) : retour à la moyenne d'Ornstein-Uhlenbeck, supports et percentiles."""
    arr = np.array(prices, dtype=float)
    n = len(arr)
    today = datetime.now(UTC)

    mu, theta, sigma = _ou_parameters(arr)
    support, resistance = support_resistance(prices, current_price)

    regime = regime_info.get("dominant_regime", "neutral") if regime_info else "neutral"
    regime_conf = regime_info.get("confidence", 0.5) if regime_info else 0.5
    cyc_pos = cycle_position if cycle_position is not None else 50.0

    inputs = _Inputs(
        current_price=current_price,
        mu=mu,
        theta=theta,
        sigma=sigma,
        support=support,
        resistance=resistance,
        p5=float(np.percentile(arr, 5)),
        p10=float(np.percentile(arr, 10)),
        p90=float(np.percentile(arr, 90)),
        p95=float(np.percentile(arr, 95)),
        cyc_pos=cyc_pos,
        asset_adj=_asset_adjustment(sigma, theta),
    )
    bottom_price, bottom_days = _bottom(inputs)
    top_price, top_days = _top(inputs, bottom_price, bottom_days)
    confidence = _confidence(regime_conf, theta, n)

    bottom_distance_pct = round((current_price - bottom_price) / current_price * 100, 1)
    top_distance_pct = round((top_price - current_price) / current_price * 100, 1)

    return {
        "symbol": symbol,
        "current_price": round(current_price, 2),
        "next_bottom": {
            "estimated_price": round(bottom_price, 2),
            "estimated_days": bottom_days,
            "estimated_date": (today + timedelta(days=bottom_days)).strftime("%Y-%m-%d"),
            "confidence": confidence,
            "distance_pct": bottom_distance_pct,
            "method": "OU mean-reversion + support clustering",
            "support_level": round(support, 2),
        },
        "next_top": {
            "estimated_price": round(top_price, 2),
            "estimated_days": top_days,
            "estimated_date": (today + timedelta(days=top_days)).strftime("%Y-%m-%d"),
            "confidence": confidence,
            "distance_pct": top_distance_pct,
            "method": "OU mean-reversion + resistance clustering",
            "resistance_level": round(resistance, 2),
        },
        "current_regime": regime,
        "cycle_position": round(cyc_pos, 1),
        "ou_parameters": {
            "mu": round(mu, 2),
            "theta": round(theta, 4),
            "sigma": round(sigma, 4),
        },
    }
