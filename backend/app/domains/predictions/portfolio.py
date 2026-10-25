from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.portfolio.classification import is_stablecoin
from app.domains.portfolio.models import Asset
from app.domains.predictions.core import held_assets, user_portfolio_ids
from app.domains.predictions.forecast import ForecastMixin
from app.domains.predictions.levels import reliability_from_ensemble
from app.domains.predictions.types import PricePrediction
from app.ml import adaptive_thresholds as at

MAX_PREDICTED_ASSETS = 10


def _empty_portfolio(days_ahead: int) -> dict[str, Any]:
    return {
        "predictions": [],
        "summary": {
            "total_current_value": 0.0,
            "total_predicted_value": 0.0,
            "expected_change_percent": 0.0,
            "overall_sentiment": "neutral",
            "bullish_assets": 0,
            "bearish_assets": 0,
            "neutral_assets": 0,
            "days_ahead": days_ahead,
        },
        "display_thresholds": at.build_display_thresholds(None),
    }


def _merged_by_symbol(raw_assets: Sequence[Asset]) -> tuple[list[Asset], dict[str, Decimal]]:
    asset_map: dict[str, Asset] = {}
    quantity_map: dict[str, Decimal] = {}
    for a in raw_assets:
        key = a.symbol
        if key not in asset_map:
            asset_map[key] = a
            quantity_map[key] = Decimal(str(a.quantity))
        else:
            quantity_map[key] += Decimal(str(a.quantity))
    return list(asset_map.values()), quantity_map


def _model_confidence(reliability_score: float) -> str:
    if reliability_score >= 60:
        return "useful"
    if reliability_score >= 40:
        return "uncertain"
    return "unreliable"


def _final_price(prediction: PricePrediction) -> float:
    price: float = prediction.predictions[-1]["price"] if prediction.predictions else prediction.current_price
    return price


def _asset_entry(asset: Asset, prediction: PricePrediction) -> dict[str, Any]:
    predicted_price = _final_price(prediction)
    change_percent = (
        ((predicted_price - prediction.current_price) / prediction.current_price * 100)
        if prediction.current_price > 0
        else 0.0
    )
    models_detail = prediction.models_detail or []
    skill_score, hit_rate, hit_rate_n, hit_rate_significant = reliability_from_ensemble(models_detail, prediction.trend)
    reliability_score = round(min(skill_score * 0.6 + hit_rate * 0.4, 95.0), 1)
    models_agree = len({m.get("trend", "neutral") for m in models_detail}) == 1 if len(models_detail) >= 2 else True
    return {
        "symbol": asset.symbol,
        "name": asset.name or asset.symbol,
        "asset_type": asset.asset_type.value,
        "current_price": prediction.current_price,
        "predicted_price": predicted_price,
        "change_percent": round(change_percent, 2),
        "trend": prediction.trend,
        "trend_strength": prediction.trend_strength,
        "recommendation": prediction.recommendation,
        "model_used": prediction.model_used,
        "predictions": prediction.predictions,
        "support_level": prediction.support_level,
        "resistance_level": prediction.resistance_level,
        "skill_score": skill_score,
        "hit_rate": round(hit_rate, 1),
        "hit_rate_significant": hit_rate_significant,
        "hit_rate_n_samples": hit_rate_n,
        "reliability_score": reliability_score,
        "model_confidence": _model_confidence(reliability_score),
        "models_agree": models_agree,
        "models_detail": models_detail,
        "explanations": prediction.explanations or [],
        "regime_info": prediction.regime_info,
        "display_thresholds": prediction.display_thresholds,
    }


def _summary(
    predictions: list[dict[str, Any]], total_current: Decimal, total_predicted: Decimal, days_ahead: int
) -> dict[str, Any]:
    bullish_count = sum(1 for p in predictions if p["trend"] == "bullish")
    bearish_count = sum(1 for p in predictions if p["trend"] == "bearish")
    total_current_f = float(total_current)
    total_predicted_f = float(total_predicted)
    portfolio_change = ((total_predicted_f - total_current_f) / total_current_f * 100) if total_current_f > 0 else 0
    overall_sentiment = (
        "bullish" if bullish_count > bearish_count else "bearish" if bearish_count > bullish_count else "neutral"
    )
    return {
        "total_current_value": round(total_current_f, 2),
        "total_predicted_value": round(total_predicted_f, 2),
        "expected_change_percent": round(portfolio_change, 2),
        "overall_sentiment": overall_sentiment,
        "bullish_assets": bullish_count,
        "bearish_assets": bearish_count,
        "neutral_assets": len(predictions) - bullish_count - bearish_count,
        "days_ahead": days_ahead,
    }


class PortfolioMixin(ForecastMixin):
    async def get_portfolio_predictions(
        self,
        db: AsyncSession,
        user_id: str,
        days_ahead: int = 7,
    ) -> dict[str, Any]:
        """Prévisions des dix premiers actifs détenus, regroupés par symbole et hors stablecoins, avec fiabilité
        (60 % compétence, 40 % accord des modèles, plafonnée à 95) et valeur prévue du portefeuille."""
        portfolio_ids = await user_portfolio_ids(db, user_id)
        if not portfolio_ids:
            return _empty_portfolio(days_ahead)
        raw_assets = await held_assets(db, portfolio_ids)
        if not raw_assets:
            return _empty_portfolio(days_ahead)

        assets, quantity_map = _merged_by_symbol(raw_assets)
        predictions: list[dict[str, Any]] = []
        total_current = Decimal("0")
        total_predicted = Decimal("0")
        for asset in assets[:MAX_PREDICTED_ASSETS]:
            if is_stablecoin(asset.symbol):
                continue
            prediction = await self.get_price_prediction(asset.symbol, asset.asset_type, days_ahead)
            qty = quantity_map[asset.symbol]
            total_current += Decimal(str(prediction.current_price)) * qty
            total_predicted += Decimal(str(_final_price(prediction))) * qty
            predictions.append(_asset_entry(asset, prediction))

        first_thresholds = (
            predictions[0].get("display_thresholds") if predictions else at.build_display_thresholds(None)
        )
        return {
            "predictions": predictions,
            "summary": _summary(predictions, total_current, total_predicted, days_ahead),
            "display_thresholds": first_thresholds,
        }
