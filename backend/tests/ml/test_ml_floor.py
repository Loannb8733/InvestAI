"""La prévision servie ne fait jamais pire que la prévision naïve : elle est ancrée sur le dernier cours.

Mesuré le 2026-11-19 sur 300 prévisions de validation (6 cryptos, janvier 2022 à octobre 2024) : aucune combinaison
des modèles ne battait la prévision naïve, et toute part donnée aux modèles dégradait au moins un actif. Les
intervalles des modèles couvraient 99 % des cas à 1 jour pour 91 % à 30 jours, au lieu de 95 % partout.
"""

import math

import numpy as np
import pytest

from app.ml.forecasting import floor
from app.ml.forecasting.ensemble import PriceForecaster
from tests.ml.series import SERIES, dates


def _forecast(prices: list[float], days: int = 30):
    return PriceForecaster().ensemble_forecast(prices, dates(len(prices)), days)


def test_the_served_path_is_the_last_price_even_on_a_trending_series() -> None:
    prices = SERIES["bull"]
    result = _forecast(prices)
    assert result.prices == [round(prices[-1], 8)] * 30
    assert result.model_used == floor.FLOOR_MODEL


def test_the_models_stay_listed_for_transparency() -> None:
    result = _forecast(SERIES["bull"])
    assert {d["name"] for d in result.models_detail} >= {"Naive"}


def test_the_interval_follows_past_volatility_scaled_per_horizon() -> None:
    prices = SERIES["bull"]
    result = _forecast(prices)
    sigma = float(np.std(np.diff(np.log(np.asarray(prices[-floor.HISTORY_DAYS :], dtype=float)))))
    for horizon in (1, 7, 30):
        spread = 1.96 * floor.interval_scale(horizon) * sigma * math.sqrt(horizon)
        assert result.confidence_low[horizon - 1] == pytest.approx(prices[-1] * math.exp(-spread), rel=1e-6)
        assert result.confidence_high[horizon - 1] == pytest.approx(prices[-1] * math.exp(spread), rel=1e-6)


def test_the_interval_widens_with_the_horizon() -> None:
    result = _forecast(SERIES["calm"])
    widths = [h - lo for lo, h in zip(result.confidence_low, result.confidence_high, strict=True)]
    assert widths[0] < widths[6] < widths[29]
    assert floor.interval_scale(1) < floor.interval_scale(30)


def test_a_short_history_still_gets_an_ordered_interval() -> None:
    prices = SERIES["calm"][:20]
    point, low, high = floor.anchored(prices, 7)
    assert point == [prices[-1]] * 7
    assert all(lo < prices[-1] < hi for lo, hi in zip(low, high, strict=True))


def test_the_mape_correction_lowers_longer_horizons_only_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    prices = SERIES["bull"]
    monkeypatch.setattr(floor, "MAPE_SHIFT_PER_LOG_DAY", 0.15)
    point, _, _ = floor.anchored(prices, 30)
    assert point[0] == prices[-1]
    assert point[29] < point[6] < prices[-1]
