from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from app.ml.forecasting.trend import compute_trend
from app.ml.forecasting.types import ForecastResult, rounded


def prophet_forecast(
    prices: list[float],
    dates: list[datetime],
    days_ahead: int,
    params: dict[str, Any],
    volumes: list[float] | None = None,
) -> ForecastResult:
    """Prophet estimé au maximum a posteriori, avec le volume en régresseur s'il couvre toute la série."""
    from prophet import Prophet

    df = pd.DataFrame({"ds": dates, "y": prices})
    regressor = volumes if volumes is not None and len(volumes) == len(prices) else None
    if regressor is not None:
        df["volume"] = regressor
    model = Prophet(
        daily_seasonality=False,
        weekly_seasonality=len(prices) >= 14,
        yearly_seasonality=len(prices) >= 365,
        changepoint_prior_scale=params.get("changepoint_prior_scale", 0.1),
        seasonality_mode=params.get("seasonality_mode", "additive"),
        interval_width=0.95,
        mcmc_samples=0,
    )
    if regressor is not None:
        model.add_regressor("volume")
    model.fit(df)
    future = model.make_future_dataframe(periods=days_ahead)
    if regressor is not None:
        recent = float(np.mean(regressor[-7:])) if len(regressor) >= 7 else float(np.mean(regressor))
        future["volume"] = (list(regressor) + [recent] * days_ahead)[: len(future)]
    fc = model.predict(future).tail(days_ahead)
    result_prices = [max(0.0, p) for p in fc["yhat"].tolist()]
    return rounded(
        [d.strftime("%Y-%m-%d") for d in fc["ds"]],
        result_prices,
        [max(0.0, p) for p in fc["yhat_lower"].tolist()],
        fc["yhat_upper"].tolist(),
        compute_trend(prices[-1], result_prices[-1], prices),
        "prophet",
    )
