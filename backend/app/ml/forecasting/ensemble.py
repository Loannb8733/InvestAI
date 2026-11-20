import logging
from datetime import datetime
from functools import partial
from typing import Any

from app.ml.forecasting import confidence
from app.ml.forecasting.cache import cached_hyperparams, run_cached
from app.ml.forecasting.floor import floored
from app.ml.forecasting.models.arima import arima_forecast
from app.ml.forecasting.models.prophet import prophet_forecast
from app.ml.forecasting.models.simple import (
    ema_forecast,
    fallback_forecast,
    linear_forecast,
    mean_reversion_forecast,
    naive_forecast,
)
from app.ml.forecasting.models.xgboost import xgboost_forecast
from app.ml.forecasting.trend import compute_trend
from app.ml.forecasting.types import Candidate, ForecastResult
from app.ml.forecasting.weighting import compute_weights, quick_mape
from app.ml.market_context import MarketContext

logger = logging.getLogger(__name__)

MAX_MODEL_MOVE = 0.5
NAIVE = "Naive"
SKILL_GATE_MIN_HISTORY = 60
MIN_HISTORY = {"Prophet": 14, "ARIMA": 20, "XGBoost": 30, "EMA": 7, "Linear": 0, "MeanReversion": 30, "Naive": 0}


def _available(module: str, attribute: str) -> bool:
    try:
        getattr(__import__(module, fromlist=[attribute]), attribute)
        return True
    except (ImportError, AttributeError):
        logger.warning("%s.%s not available", module, attribute)
        return False


def _skip(name: str, reason: str) -> dict[str, str]:
    return {"name": name, "reason": reason}


def _combined_prices(candidates: list[Candidate], weights: list[float], n_days: int) -> list[float]:
    combined = [0.0] * n_days
    for (_name, res), w in zip(candidates, weights, strict=False):
        for i in range(min(n_days, len(res.prices))):
            combined[i] += res.prices[i] * w
    return combined


def _interval(
    prices: list[float],
    candidates: list[Candidate],
    weights: list[float],
    combined: list[float],
    ctx: MarketContext | None,
    calibration: float,
) -> confidence.Interval:
    n_days = len(combined)
    interval = confidence.combine_native_ci(candidates, weights, combined, n_days)
    if interval is None:
        vols = confidence.ewma_volatility_forecast(prices, n_days)
        interval = confidence.empirical_quantile_ci(prices, prices[-1], n_days, combined, vols)
    if ctx:
        confidence.apply_floor(ctx, combined, interval)
    if calibration != 1.0:
        confidence.calibrate(combined, interval, calibration)
    return interval


def _vote(candidates: list[Candidate], weights: list[float]) -> str:
    scores = {"bullish": 0.0, "bearish": 0.0, "neutral": 0.0}
    for (_name, res), w in zip(candidates, weights, strict=False):
        scores[res.trend] += w
    return max(scores, key=lambda trend: scores[trend])


def _details(
    candidates: list[Candidate], weights: list[float], mapes: list[float | None], prices: list[float]
) -> list[dict[str, Any]]:
    details = []
    for idx, ((name, res), w) in enumerate(zip(candidates, weights, strict=False)):
        mape = mapes[idx] if idx < len(mapes) and mapes[idx] is not None else quick_mape(prices, res)
        details.append({"name": name, "weight_pct": round(w * 100), "mape": round(mape or 0.0, 1), "trend": res.trend})
    return details


def _skill_gated(
    candidates: list[Candidate], weights: list[float], mapes: list[float | None], skipped: list[dict[str, str]]
) -> list[float]:
    """Poids nul pour un modèle dont l'erreur de backtest ne bat pas celle de la prévision naïve sur la même série."""
    names = [name for name, _ in candidates]
    reference = mapes[names.index(NAIVE)] if NAIVE in names else None
    if reference is None:
        return weights
    gated = list(weights)
    for i, (name, mape) in enumerate(zip(names, mapes, strict=True)):
        if name != NAIVE and gated[i] > 0 and mape is not None and mape >= reference:
            gated[i] = 0.0
            reason = f"moins précis que la prévision naïve en backtest ({mape:.1f} % contre {reference:.1f} %)"
            skipped.append(_skip(name, reason))
    return gated


def _aberrant(result: ForecastResult, last_price: float) -> bool:
    if not result.prices or last_price <= 0:
        return False
    return abs(result.prices[-1] / last_price - 1) > MAX_MODEL_MOVE


class PriceForecaster:
    """Prévision de prix par un ensemble de modèles pondérés selon leur erreur de backtest."""

    def __init__(self, hyperparams: dict[str, Any] | None = None) -> None:
        self.prophet_available = _available("prophet", "Prophet")
        self.xgboost_available = _available("xgboost", "XGBRegressor")
        self.arima_available = _available("statsmodels.tsa.arima.model", "ARIMA")
        self.auto_arima_available = _available("pmdarima", "auto_arima")
        self.hyperparams: dict[str, Any] = hyperparams or {}

    def run_model(
        self,
        name: str,
        prices: list[float],
        dates: list[datetime],
        days: int,
        volumes: list[float] | None = None,
        btc_prices: list[float] | None = None,
        hyperparams: dict[str, Any] | None = None,
    ) -> ForecastResult:
        """Prévision d'un seul modèle ; un nom inconnu donne la régression linéaire.

        ``hyperparams`` remplace pour cet appel seulement ceux du prévisionniste.
        """
        params = self.hyperparams if hyperparams is None else hyperparams
        if name == "Prophet":
            return prophet_forecast(prices, dates, days, params.get("prophet", {}), volumes=volumes)
        if name == "ARIMA":
            return arima_forecast(prices, dates, days, self.auto_arima_available)
        if name == "XGBoost":
            return xgboost_forecast(
                prices, dates, days, params.get("xgboost", {}), volumes=volumes, btc_prices=btc_prices
            )
        if name == "EMA":
            return ema_forecast(prices, dates, days)
        if name == "Naive":
            return naive_forecast(prices, dates, days)
        if name == "MeanReversion":
            return mean_reversion_forecast(prices, dates, days)
        return linear_forecast(prices, dates, days)

    def forecast(self, prices: list[float], dates: list[datetime], days_ahead: int = 7) -> ForecastResult:
        """Prophet seul dès 14 points, sinon régression linéaire ; marche aléatoire sous 5 points."""
        if len(prices) < 5:
            return fallback_forecast(prices, days_ahead)
        if self.prophet_available and len(prices) >= 14:
            try:
                return prophet_forecast(prices, dates, days_ahead, self.hyperparams.get("prophet", {}))
            except Exception as e:  # noqa: BLE001
                logger.warning("Prophet failed: %s", e)
        return linear_forecast(prices, dates, days_ahead)

    def _unavailable(self, name: str) -> bool:
        installed = {
            "Prophet": self.prophet_available,
            "XGBoost": self.xgboost_available,
            "ARIMA": self.arima_available,
        }
        return not installed.get(name, True)

    def _candidates(
        self,
        prices: list[float],
        dates: list[datetime],
        days_ahead: int,
        cache_key: tuple[str | None, str | None],
        extra: tuple[list[float] | None, list[float] | None],
        hyperparams: dict[str, Any],
    ) -> tuple[list[Candidate], list[dict[str, str]]]:
        n = len(prices)
        candidates: list[Candidate] = []
        skipped: list[dict[str, str]] = []
        for name, minimum in MIN_HISTORY.items():
            if self._unavailable(name):
                skipped.append(_skip(name, "non installé"))
                continue
            if n < minimum:
                skipped.append(_skip(name, f"historique insuffisant ({n} cours, {minimum} requis)"))
                continue
            volumes, btc = extra if name == "XGBoost" else (None, None)
            run = partial(self.run_model, name, prices, dates, days_ahead, volumes, btc, hyperparams)
            try:
                result = run_cached(name, *cache_key, days_ahead, run)
            except Exception as e:  # noqa: BLE001
                logger.warning("%s excluded from the ensemble: %s", name, e)
                skipped.append(_skip(name, f"erreur : {type(e).__name__}: {e}"[:200]))
                continue
            if _aberrant(result, prices[-1]):
                logger.warning("%s excluded from the ensemble: forecast beyond ±50%%", name)
                skipped.append(_skip(name, "prévision aberrante (au-delà de ±50 %)"))
                continue
            candidates.append((name, result))
        return candidates, skipped

    def _weighted(
        self,
        prices: list[float],
        dates: list[datetime],
        candidates: list[Candidate],
        hyperparams: dict[str, Any],
        skipped: list[dict[str, str]],
    ) -> tuple[list[Candidate], list[float], float, list[float | None]]:
        run = partial(self._backtest_run, hyperparams=hyperparams)
        weights, calibration, mapes = compute_weights(prices, dates, candidates, run)
        if not any(w > 0 for w in weights):
            return candidates, [1.0 / len(candidates)] * len(candidates), 1.0, mapes
        for i in range(len(candidates)):
            if weights[i] == 0:
                logger.warning("%s excluded from the ensemble: every backtest window failed", candidates[i][0])
                skipped.append(_skip(candidates[i][0], "backtest en échec sur toutes les fenêtres"))
        if len(prices) >= SKILL_GATE_MIN_HISTORY:
            weights = _skill_gated(candidates, weights, mapes, skipped)
        kept = [i for i, w in enumerate(weights) if w > 0]
        total = sum(weights[i] for i in kept)
        return (
            [candidates[i] for i in kept],
            [weights[i] / total for i in kept],
            calibration,
            [mapes[i] for i in kept],
        )

    def _backtest_run(
        self, name: str, prices: list[float], dates: list[datetime], days: int, hyperparams: dict[str, Any]
    ) -> ForecastResult:
        return self.run_model(name, prices, dates, days, hyperparams=hyperparams)

    def ensemble_forecast(
        self, prices: list[float], dates: list[datetime], days_ahead: int = 7, **inputs: Any
    ) -> ForecastResult:
        """Ensemble des modèles (``_models_forecast``), puis trajectoire et intervalle ancrés par ``floor``."""
        result = self._models_forecast(prices, dates, days_ahead, **inputs)
        return floored(prices, result) if len(prices) >= 5 else result

    def _models_forecast(
        self,
        prices: list[float],
        dates: list[datetime],
        days_ahead: int = 7,
        symbol: str | None = None,
        data_hash: str | None = None,
        volumes: list[float] | None = None,
        btc_prices: list[float] | None = None,
        fear_greed: int | None = None,
        btc_dominance: float | None = None,
        market_context: MarketContext | None = None,
    ) -> ForecastResult:
        """Moyenne des modèles disponibles pondérée par backtest, intervalle par variance totale, tendance votée.

        Les hyperparamètres réglés pour ``symbol`` ne valent que pour cet appel. Un modèle absent, à l'historique
        trop court, en erreur, à la prévision aberrante (±50 %) ou sans backtest réussi est écarté et listé dans
        ``skipped_models``. ``fear_greed`` et ``btc_dominance`` sont acceptés pour les appelants mais n'entrent dans
        aucun modèle.
        """
        if len(prices) < 5:
            return fallback_forecast(prices, days_ahead)
        hyperparams = {**self.hyperparams, **((cached_hyperparams(symbol) if symbol else None) or {})}
        candidates, skipped = self._candidates(
            prices, dates, days_ahead, (symbol, data_hash), (volumes, btc_prices), hyperparams
        )
        if not candidates:
            result = fallback_forecast(prices, days_ahead)
            result.skipped_models = skipped
            return result
        if len(candidates) == 1:
            name, result = candidates[0]
            result.model_used = name.lower()
            result.models_detail = [{"name": name, "weight_pct": 100, "mape": 0, "trend": result.trend}]
            result.skipped_models = skipped
            return result
        candidates, weights, calibration, mapes = self._weighted(prices, dates, candidates, hyperparams, skipped)
        combined = _combined_prices(candidates, weights, days_ahead)
        low, high = _interval(prices, candidates, weights, combined, market_context, calibration)
        strength = compute_trend(prices[-1], combined[-1], prices, days_ahead=days_ahead, ctx=market_context)[1]
        details = _details(candidates, weights, mapes, prices)
        parts = ", ".join(f"{d['name']}: {d['weight_pct']}%" for d in details)
        return ForecastResult(
            dates=candidates[0][1].dates[:days_ahead],
            prices=[round(p, 8) for p in combined],
            confidence_low=[round(max(0, p), 8) for p in low],
            confidence_high=[round(p, 8) for p in high],
            trend=_vote(candidates, weights),
            trend_strength=round(strength, 1),
            model_used=f"ensemble ({parts})",
            models_detail=details,
            skipped_models=skipped,
        )
