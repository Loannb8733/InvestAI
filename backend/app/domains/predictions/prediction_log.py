import logging
from datetime import datetime
from typing import Any

from app.core.db.session import session_factory
from app.domains.portfolio.models import AssetType
from app.domains.predictions.models import PredictionLog
from app.domains.predictions.types import ForecastPoint

logger = logging.getLogger(__name__)


def _prediction_data(
    current_price: float,
    fear_greed: int | None,
    btc_dominance: float | None,
    regime_info: dict[str, Any] | None,
    prices: list[float],
    models_detail: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "current_price": float(current_price),
        "fear_greed": fear_greed,
        "btc_dominance": btc_dominance,
        "regime": regime_info.get("dominant_regime") if regime_info else None,
        "history_days": len(prices) if prices else 0,
        "model_weights": {m["name"]: m.get("weight_pct") for m in models_detail} if models_detail else None,
    }


async def log_prediction(
    *,
    symbol: str,
    asset_type: AssetType,
    model_used: str,
    predictions: list[ForecastPoint],
    current_price: float,
    days_ahead: int,
    models_detail: list[dict[str, Any]],
    fear_greed: int | None,
    btc_dominance: float | None,
    regime_info: dict[str, Any] | None,
    prices: list[float],
) -> None:
    """Journalise le dernier point de la prévision et son intervalle pour la calibration ; un échec est seulement
    signalé dans les logs."""
    try:
        if predictions:
            last_pred = predictions[-1]
            log_entry = PredictionLog(
                symbol=symbol,
                asset_type=asset_type.value,
                model_name=model_used,
                predicted_price=float(last_pred["price"]),
                price_at_creation=float(current_price),
                target_date=datetime.strptime(last_pred["date"], "%Y-%m-%d"),
                horizon_days=days_ahead,
                models_detail=models_detail,
                confidence_low=float(last_pred.get("confidence_low", 0)),
                confidence_high=float(last_pred.get("confidence_high", 0)),
                prediction_data=_prediction_data(
                    current_price, fear_greed, btc_dominance, regime_info, prices, models_detail
                ),
            )
            async with session_factory() as log_db:
                log_db.add(log_entry)
                await log_db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to log prediction for %s: %s", symbol, e)
