from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.market_data.history.models import AssetPriceHistory
from app.domains.portfolio.models import AssetType
from app.domains.predictions.recommendation import generate_recommendation
from app.domains.predictions.service import prediction_service
from app.ml.forecaster import ForecastResult
from tests.sample_portfolio import FROZEN_NOW, seed_history, seed_portfolio

pytestmark = pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes")
BULLISH = {"dominant_regime": "bullish", "confidence": 0.9}


class _SoaringForecaster:
    def ensemble_forecast(self, prices: list[float], dates: list[Any], days_ahead: int = 7, **_: Any) -> ForecastResult:
        path = [prices[-1] * (1 + 0.12 * (i + 1)) for i in range(days_ahead)]
        return ForecastResult(
            dates=[(dates[-1] + timedelta(days=i + 1)).strftime("%Y-%m-%d") for i in range(days_ahead)],
            prices=path,
            confidence_low=[p * 0.9 for p in path],
            confidence_high=[p * 1.1 for p in path],
            trend="bullish",
            trend_strength=90.0,
            model_used="ensemble (prophet: 100%)",
            models_detail=[{"name": "Prophet", "weight_pct": 100, "mape": 3.0, "trend": "bullish"}],
        )


@pytest.mark.usefixtures("deterministic_forecaster")
async def test_backtest_lists_assets_in_symbol_order(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    headers = {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}
    with time_machine.travel(FROZEN_NOW, tick=False):
        await seed_history(db_session)
        await seed_portfolio(client, headers)
        response = await client.get("/api/v1/predictions/backtest", headers=headers)
    symbols = [a["symbol"] for a in response.json()["assets"]]
    assert symbols == sorted(symbols)


def test_price_levels_below_one_euro_keep_their_decimals() -> None:
    text = generate_recommendation("bullish", 30, 0.8, 0.7, 0.9512, regime_info=BULLISH)
    assert "surveiller : 0.9512" in text


def test_price_levels_keep_two_decimals_between_one_and_a_hundred() -> None:
    text = generate_recommendation("bullish", 30, 9.0, 8.0, 9.876, regime_info=BULLISH)
    assert "surveiller : 9.88" in text


def test_price_levels_above_a_hundred_stay_whole() -> None:
    text = generate_recommendation("bullish", 30, 60000.0, 55000.0, 65000.4, regime_info=BULLISH)
    assert "surveiller : 65000." in text


async def test_unrealistic_forecast_without_enough_history_is_clamped_not_emptied(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(prediction_service, "forecaster", _SoaringForecaster())
    with time_machine.travel(FROZEN_NOW, tick=False):
        start = FROZEN_NOW.date() - timedelta(days=9)
        for day in range(10):
            db_session.add(
                AssetPriceHistory(
                    symbol="BTC", price_date=start + timedelta(days=day), price_eur=Decimal("60000"), source="test"
                )
            )
        await db_session.commit()
        prediction = await prediction_service.get_price_prediction("BTC", AssetType.CRYPTO, 7)
    assert len(prediction.predictions) == 7
    assert max(p["price"] for p in prediction.predictions) == pytest.approx(90000)
