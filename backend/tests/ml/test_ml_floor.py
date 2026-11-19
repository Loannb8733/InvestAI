"""La prévision servie part du dernier cours, corrigé pour l'erreur relative, avec un intervalle calibré.

Mesuré le 2026-11-19 en walk-forward quotidien sur la validation (6 cryptos, janvier 2022 à novembre 2024) :
aucune combinaison des modèles ni aucun modèle appris sur des signaux de marché ne battait la prévision naïve ;
la correction ``exp(-kappa(h) · sigma² · h)`` la battait sur chaque actif. Les intervalles des modèles couvraient
99 % des cas à 1 jour pour 91 % à 30 jours, au lieu de 95 % partout.
"""

import math

import numpy as np
import pytest

from app.ml.forecasting import floor
from app.ml.forecasting.ensemble import PriceForecaster
from tests.ml.series import SERIES, dates


def _forecast(prices: list[float], days: int = 30):
    return PriceForecaster().ensemble_forecast(prices, dates(len(prices)), days)


def _sigma(prices: list[float]) -> float:
    returns = np.diff(np.log(np.asarray(prices[-(floor.VOL_WINDOW + 1) :], dtype=float)))
    return float(np.std(returns, ddof=1))


def test_the_served_path_is_the_last_price_lowered_by_the_mape_correction() -> None:
    prices = SERIES["bull"]
    result = _forecast(prices)
    sigma = _sigma(prices)
    for horizon in (1, 7, 30):
        expected = prices[-1] * math.exp(-floor.mape_kappa(horizon) * sigma**2 * horizon)
        assert result.prices[horizon - 1] == pytest.approx(expected, rel=1e-7)
    assert result.prices[29] < result.prices[0] < prices[-1]
    assert result.model_used == floor.FLOOR_MODEL


def test_the_correction_reaches_its_full_strength_at_a_week() -> None:
    assert floor.mape_kappa(1) == floor.MAPE_KAPPA[0]
    assert floor.mape_kappa(7) == pytest.approx(floor.MAPE_KAPPA[1])
    assert floor.mape_kappa(30) == floor.MAPE_KAPPA[1]


def test_without_correction_the_path_is_the_naive_forecast(monkeypatch: pytest.MonkeyPatch) -> None:
    prices = SERIES["bull"]
    monkeypatch.setattr(floor, "MAPE_KAPPA", (0.0, 0.0))
    point, _, _ = floor.anchored(prices, 30)
    assert point == [prices[-1]] * 30


def test_the_models_stay_listed_for_transparency() -> None:
    result = _forecast(SERIES["bull"])
    assert {d["name"] for d in result.models_detail} >= {"Naive"}


def test_the_interval_follows_past_volatility_scaled_per_horizon() -> None:
    prices = SERIES["bull"]
    result = _forecast(prices)
    sigma = _sigma(prices)
    for horizon in (1, 7, 30):
        spread = 1.96 * floor.interval_scale(horizon) * sigma * math.sqrt(horizon)
        assert result.confidence_low[horizon - 1] == pytest.approx(prices[-1] * math.exp(-spread), rel=1e-6)
        assert result.confidence_high[horizon - 1] == pytest.approx(prices[-1] * math.exp(spread), rel=1e-6)


def test_the_interval_widens_with_the_horizon() -> None:
    result = _forecast(SERIES["calm"])
    widths = [h - lo for lo, h in zip(result.confidence_low, result.confidence_high, strict=True)]
    assert widths[0] < widths[6] < widths[29]


def test_a_short_history_still_gets_an_ordered_interval() -> None:
    prices = SERIES["calm"][:20]
    point, low, high = floor.anchored(prices, 7)
    assert all(lo < p <= prices[-1] < hi for lo, p, hi in zip(low, point, high, strict=True))
