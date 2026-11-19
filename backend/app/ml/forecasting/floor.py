"""Prévision ponctuelle ancrée sur la prévision naïve, corrigée pour l'erreur relative, et intervalles calibrés.

Réglages choisis en walk-forward quotidien sur la validation (6 cryptos, janvier 2022 à novembre 2024, plus de
6 000 prévisions par horizon, ``docs/ml-evaluation.md``). Aucun modèle ni signal de marché appris n'y bat la
prévision naïve ; seule la correction qui minimise l'erreur relative attendue de rendements log-normaux le fait,
sur chaque actif et avec un test de Diebold-Mariano significatif : ``p0 · exp(-kappa(h) · sigma² · h)``, sigma
étant la volatilité quotidienne de l'année passée et ``kappa(h)`` passant de 0,6 à 1 jour à 0,9 dès 7 jours. La
prévision est donc volontairement un peu sous le dernier cours. L'intervalle vaut ``p0 · exp(± 1,96 · m(h) ·
sigma · √h)`` avec ``m(h) = a + b · ln h`` ajusté pour couvrir 95 % des cas à chaque horizon de 1 à 30 jours.
"""

import math

import numpy as np

from app.ml.forecasting.trend import compute_trend
from app.ml.forecasting.types import ForecastResult

VOL_WINDOW = 365
NORMAL_Z = 1.96
INTERVAL_SCALE = (0.978, 0.020)
MAPE_KAPPA = (0.6, 0.9)
MAPE_KAPPA_FULL_AT = 7
FLOOR_MODEL = "plancher naïf corrigé"


def interval_scale(horizon: int) -> float:
    """Multiplicateur de l'intervalle normal à ``horizon`` jours."""
    intercept, slope = INTERVAL_SCALE
    return intercept + slope * math.log(horizon)


def mape_kappa(horizon: int) -> float:
    """Coefficient de la correction MAPE, interpolé en ln h entre 1 jour et ``MAPE_KAPPA_FULL_AT`` jours."""
    short, full = MAPE_KAPPA
    return short + (full - short) * min(1.0, math.log(horizon) / math.log(MAPE_KAPPA_FULL_AT))


def daily_volatility(prices: list[float]) -> float:
    """Écart-type (corrigé) des rendements log quotidiens sur ``VOL_WINDOW`` jours."""
    log_prices = np.log(np.asarray(prices[-(VOL_WINDOW + 1) :], dtype=float))
    return float(np.std(np.diff(log_prices), ddof=1)) if len(log_prices) > 2 else 0.0


def anchored(prices: list[float], days_ahead: int) -> tuple[list[float], list[float], list[float]]:
    """Prévision, borne basse et borne haute pour chaque jour de 1 à ``days_ahead``."""
    sigma = daily_volatility(prices)
    last = prices[-1]
    point, low, high = [], [], []
    for horizon in range(1, days_ahead + 1):
        spread = NORMAL_Z * interval_scale(horizon) * sigma * math.sqrt(horizon)
        point.append(last * math.exp(-mape_kappa(horizon) * sigma**2 * horizon))
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
