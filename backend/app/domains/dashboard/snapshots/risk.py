"""Indicateurs de risque calculés sur une série de valeur, sans accès à la base."""

import logging
import math
from datetime import datetime
from itertools import pairwise
from typing import Any

from app.core.finance_constants import CALENDAR_DAYS_PER_YEAR, RISK_FREE_RATE

logger = logging.getLogger(__name__)

History = list[dict[str, Any]]

_MAX_LOG_RETURN = 1.0
_MIN_VAR_POINTS = 5
_MIN_VAR_RETURNS = 20
_HHI_DIVERSIFIED = 1500
_HHI_MODERATE = 2500


def estimate_interval_days(history: History) -> float:
    """Écart moyen en jours entre deux points, pour annualiser une série échantillonnée."""
    if len(history) < 2:
        return 1.0
    try:
        dates = [datetime.fromisoformat(point["full_date"]) for point in history if point.get("full_date")]
        if len(dates) >= 2:
            total_days = (dates[-1] - dates[0]).days
            if total_days > 0:
                return total_days / (len(dates) - 1)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to estimate data-point interval, defaulting to 1 day: %s", exc)
    return 1.0


def twr_log_returns(history: History) -> list[float]:
    """Rendements logarithmiques hors flux de capital, bornés à ±1 par intervalle."""
    returns = []
    for previous, current in pairwise(history):
        if previous["value"] <= 0:
            continue
        flow = current.get("net_capital", 0) - previous.get("net_capital", 0)
        adjusted = current["value"] - flow
        if adjusted <= 0:
            continue
        log_return = math.log(adjusted / previous["value"])
        returns.append(max(-_MAX_LOG_RETURN, min(_MAX_LOG_RETURN, log_return)))
    return returns


def _annualized_deviation(returns: list[float], periods_per_year: float) -> tuple[float, float]:
    count = len(returns)
    mean = sum(returns) / count
    variance = sum((value - mean) ** 2 for value in returns) / (count - 1)
    return math.sqrt(variance) * math.sqrt(periods_per_year), mean


def calculate_volatility(history: History) -> float:
    """Volatilité annualisée en pourcentage, sur les rendements hors flux."""
    if len(history) < 2:
        return 0.0
    returns = twr_log_returns(history)
    if len(returns) < 2:
        return 0.0
    periods_per_year = CALENDAR_DAYS_PER_YEAR / estimate_interval_days(history)
    deviation, _ = _annualized_deviation(returns, periods_per_year)
    return round(deviation * 100, 2)


def calculate_sharpe_ratio(
    history: History, risk_free_rate: float = RISK_FREE_RATE, roi_annualized: float | None = None
) -> float:
    """Ratio de Sharpe : le rendement annualisé fourni prime sur celui de la série."""
    if len(history) < 2:
        return 0.0
    returns = twr_log_returns(history)
    if len(returns) < 2:
        return 0.0
    periods_per_year = CALENDAR_DAYS_PER_YEAR / estimate_interval_days(history)
    deviation, mean = _annualized_deviation(returns, periods_per_year)
    if deviation == 0:
        return 0.0
    annual_return = roi_annualized / 100.0 if roi_annualized is not None else mean * periods_per_year
    return round((annual_return - risk_free_rate) / deviation, 2)


def calculate_max_drawdown(history: History) -> dict[str, Any]:
    """Plus forte baisse depuis un sommet, avec ses dates et ses valeurs."""
    if len(history) < 2:
        return {"max_drawdown_percent": 0.0, "peak_date": None, "trough_date": None}
    values = [point["value"] for point in history]
    dates = [point.get("full_date", point["date"]) for point in history]
    deepest = 0.0
    peak = values[0]
    peak_index = deepest_peak = deepest_trough = 0
    for index, value in enumerate(values):
        if value > peak:
            peak = value
            peak_index = index
        drawdown = (peak - value) / peak if peak > 0 else 0
        if drawdown > deepest:
            deepest = drawdown
            deepest_peak = peak_index
            deepest_trough = index
    found = deepest > 0
    return {
        "max_drawdown_percent": round(deepest * 100, 2),
        "peak_date": dates[deepest_peak] if found else None,
        "trough_date": dates[deepest_trough] if found else None,
        "peak_value": values[deepest_peak] if found else None,
        "trough_value": values[deepest_trough] if found else None,
    }


def calculate_var(history: History, confidence_level: float = 0.95, current_value: float = 0) -> dict[str, Any]:
    """Perte potentielle par simulation historique ; nulle sous 20 rendements ou sans perte dans la queue."""
    returns = twr_log_returns(history) if len(history) >= _MIN_VAR_POINTS else []
    if len(returns) < _MIN_VAR_RETURNS:
        return {"var_percent": 0.0, "var_amount": 0.0, "confidence_level": confidence_level}
    ordered = sorted(returns)
    index = max(0, math.ceil((1 - confidence_level) * len(ordered)) - 1)
    var_percent = max(0.0, -ordered[index]) * 100
    amount = current_value * (var_percent / 100) if current_value > 0 else 0
    return {"var_percent": round(var_percent, 2), "var_amount": round(amount, 2), "confidence_level": confidence_level}


def _allocation_value(allocation: dict[str, Any]) -> Any:
    return allocation.get("value", 0) or allocation.get("current_value", 0)


def _hhi_reading(hhi: float) -> tuple[str, bool]:
    if hhi < _HHI_DIVERSIFIED:
        return "Bien diversifié", False
    if hhi < _HHI_MODERATE:
        return "Concentration modérée", False
    return "Forte concentration", True


def calculate_hhi(allocations: list[dict[str, Any]]) -> dict[str, Any]:
    """Indice de concentration de Herfindahl, de 0 à 10 000."""
    total = sum(_allocation_value(allocation) for allocation in allocations)
    if total == 0:
        return {"hhi": 0, "interpretation": "N/A", "is_concentrated": False, "top_concentration": None}
    hhi = 0.0
    top_share = 0.0
    top_asset = None
    for allocation in allocations:
        share = (_allocation_value(allocation) / total) * 100
        hhi += share**2
        if share > top_share:
            top_share = share
            top_asset = allocation.get("symbol", "Unknown")
    hhi = round(hhi, 0)
    interpretation, concentrated = _hhi_reading(hhi)
    return {
        "hhi": hhi,
        "interpretation": interpretation,
        "is_concentrated": concentrated,
        "top_asset": top_asset,
        "top_concentration": round(top_share, 1),
    }


def calculate_stress_test(current_value: float, scenario_drop: float = 0.20) -> dict[str, Any]:
    """Valeur du portefeuille après une baisse uniforme."""
    name = f"Correction -{int(scenario_drop * 100)}%"
    if current_value == 0:
        return {
            "scenario_name": name,
            "current_value": 0,
            "stressed_value": 0,
            "potential_loss": 0,
            "potential_loss_percent": scenario_drop * 100,
        }
    stressed = current_value * (1 - scenario_drop)
    return {
        "scenario_name": name,
        "current_value": round(current_value, 2),
        "stressed_value": round(stressed, 2),
        "potential_loss": round(current_value - stressed, 2),
        "potential_loss_percent": round(scenario_drop * 100, 1),
    }
