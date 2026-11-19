"""Prévision ponctuelle ancrée sur la prévision naïve et intervalles calibrés par horizon.

Sur 300 prévisions de validation (6 cryptos, janvier 2022 à octobre 2024, ``docs/ml-evaluation.md``), aucune
combinaison des modèles ne bat la prévision naïve, et toute part donnée aux modèles dégrade au moins un actif :
la prévision ponctuelle est donc le dernier cours. ``MAPE_SHIFT_PER_LOG_DAY`` active la correction qui minimise
l'erreur relative attendue de rendements log-normaux, ``p0 · exp(-kappa(h) · sigma² · h)`` avec
``kappa(h) = K · ln h`` : elle baisse le MAPE global à 30 jours mais dégrade certains actifs, d'où sa valeur nulle.
L'intervalle vaut ``p0 · exp(± 1,96 · m(h) · sigma · √h)``, sigma étant la volatilité quotidienne de l'année
passée et ``m(h) = a + b · ln h`` réglé sur la même validation pour couvrir 95 % des cas à chaque horizon, avec la
largeur la plus faible des méthodes comparées (quantiles empiriques, volatilité récente EWMA).
"""

import math

import numpy as np

from app.ml.forecasting.trend import compute_trend
from app.ml.forecasting.types import ForecastResult

HISTORY_DAYS = 365
NORMAL_Z = 1.96
INTERVAL_SCALE = (0.612, 0.170)
MAPE_SHIFT_PER_LOG_DAY = 0.0
FLOOR_MODEL = "plancher naïf"


def interval_scale(horizon: int) -> float:
    """Multiplicateur de l'intervalle normal à ``horizon`` jours."""
    intercept, slope = INTERVAL_SCALE
    return intercept + slope * math.log(horizon)


def daily_volatility(prices: list[float]) -> float:
    """Écart-type des rendements log quotidiens de l'année passée."""
    log_prices = np.log(np.asarray(prices[-HISTORY_DAYS:], dtype=float))
    return float(np.std(np.diff(log_prices))) if len(log_prices) > 2 else 0.0


def anchored(prices: list[float], days_ahead: int) -> tuple[list[float], list[float], list[float]]:
    """Prévision, borne basse et borne haute pour chaque jour de 1 à ``days_ahead``, depuis l'année passée."""
    sigma = daily_volatility(prices)
    last = prices[-1]
    point, low, high = [], [], []
    for horizon in range(1, days_ahead + 1):
        shift = MAPE_SHIFT_PER_LOG_DAY * math.log(horizon) * sigma**2 * horizon
        spread = NORMAL_Z * interval_scale(horizon) * sigma * math.sqrt(horizon)
        point.append(last * math.exp(-shift))
        low.append(last * math.exp(-spread))
        high.append(last * math.exp(spread))
    return point, low, high


def floored(prices: list[float], result: ForecastResult) -> ForecastResult:
    """Résultat des modèles dont la trajectoire et l'intervalle sont remplacés par la prévision ancrée.

    Les modèles et leurs poids restent dans ``models_detail`` et ``skipped_models`` pour la transparence ; la
    tendance est recalculée sur la trajectoire servie.
    """
    point, low, high = anchored(prices, len(result.prices))
    result.prices = [round(p, 8) for p in point]
    result.confidence_low = [round(max(0.0, p), 8) for p in low]
    result.confidence_high = [round(p, 8) for p in high]
    trend, strength = compute_trend(prices[-1], point[-1], prices, days_ahead=len(point))
    result.trend, result.trend_strength = trend, round(strength, 1)
    result.model_used = FLOOR_MODEL
    return result
