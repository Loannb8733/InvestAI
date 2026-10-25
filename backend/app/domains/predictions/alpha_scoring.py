import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import numpy as np
from numpy.typing import NDArray

from app.domains.portfolio.models import Asset
from app.domains.predictions.types import PricePrediction
from app.ml.regime_detector import RegimeResult, _rsi

logger = logging.getLogger(__name__)

Reason = dict[str, Any]


@dataclass(frozen=True, slots=True)
class _Momentum:
    symbol: str
    price_t7: float
    price_t: float
    change_7d: float
    rsi_prev: float
    rsi_now: float

    @property
    def rsi_delta(self) -> float:
        return self.rsi_now - self.rsi_prev


def _bullish_divergence(m: _Momentum, log: dict[str, Any]) -> tuple[float, Reason]:
    rsi_delta = m.rsi_delta
    log["is_bullish_divergence"] = True
    div_score = min(35, 15 + rsi_delta * 2)
    reason = {
        "label": "Divergence Haussière",
        "detail": f"Prix {m.change_7d:+.1f}% mais RSI {rsi_delta:+.1f} pts",
        "score": round(div_score),
    }
    logger.info(
        "Divergence %s CONFIRMÉE: Prix(T-7)=%.4f > Prix(T)=%.4f ET RSI(T-7)=%.2f < RSI(T)=%.2f",
        m.symbol,
        m.price_t7,
        m.price_t,
        m.rsi_prev,
        m.rsi_now,
    )
    return div_score, reason


def _unconfirmed_divergence(m: _Momentum, log: dict[str, Any]) -> tuple[float, Reason]:
    rsi_delta = m.rsi_delta
    penalty = min(10, abs(rsi_delta) * 1.5)
    log["degraded"] = True
    log["penalty"] = round(penalty, 1)
    reason = {
        "label": "Divergence Non Confirmée",
        "detail": f"Prix {m.change_7d:+.1f}% et RSI {rsi_delta:+.1f} pts (pas de divergence)",
        "score": round(-penalty),
    }
    logger.info(
        "Divergence %s NON CONFIRMÉE: Prix(T-7)=%.4f > Prix(T)=%.4f mais RSI(T-7)=%.2f → RSI(T)=%.2f (delta %.1f ≤ 3)",
        m.symbol,
        m.price_t7,
        m.price_t,
        m.rsi_prev,
        m.rsi_now,
        rsi_delta,
    )
    return -penalty, reason


def rsi_divergence(symbol: str, prices: list[float]) -> tuple[float, Reason | None, dict[str, Any]]:
    """Points RSI/prix (0-35) : divergence haussière, divergence non confirmée pénalisée, ou survente sous 35."""
    rsi_now = _rsi(prices, period=14)
    rsi_prev = _rsi(prices[:-7], period=14) if len(prices) > 21 else None
    price_t = prices[-1]
    price_t7 = prices[-8] if len(prices) > 8 else price_t
    price_change_7d = (price_t / price_t7 - 1) * 100 if price_t7 > 0 else 0

    divergence_log: dict[str, Any] = {
        "price_t7": round(price_t7, 4),
        "price_t": round(price_t, 4),
        "rsi_t7": round(rsi_prev, 2) if rsi_prev is not None else None,
        "rsi_t": round(rsi_now, 2) if rsi_now is not None else None,
        "price_change_7d_pct": round(price_change_7d, 2),
        "is_bullish_divergence": False,
    }
    if rsi_now is None or rsi_prev is None:
        return 0.0, None, divergence_log

    m = _Momentum(symbol, price_t7, price_t, price_change_7d, rsi_prev, rsi_now)
    if price_change_7d < -2 and m.rsi_delta > 3:
        return (*_bullish_divergence(m, divergence_log), divergence_log)
    if price_change_7d < -2 and m.rsi_delta <= 3:
        return (*_unconfirmed_divergence(m, divergence_log), divergence_log)
    if rsi_now < 35:
        ov_score = min(20, (35 - rsi_now) * 1.2)
        reason = {"label": "Survente RSI", "detail": f"RSI à {rsi_now:.0f} (seuil 35)", "score": round(ov_score)}
        return ov_score, reason, divergence_log
    return 0.0, None, divergence_log


def btc_decorrelation(btc_returns: NDArray[np.float64], prices: list[float]) -> tuple[float, Reason | None]:
    """Points de décorrélation de Spearman au BTC (0-30) ; motif affiché au-delà de 10 points."""
    if not (len(btc_returns) > 10 and len(prices) > 10):
        return 0.0, None
    a_returns = np.diff(np.log(np.array(prices[-len(btc_returns) - 1 :], dtype=float)))
    min_len = min(len(btc_returns), len(a_returns))
    if min_len < 10:
        return 0.0, None
    from scipy.stats import spearmanr

    corr, _ = spearmanr(btc_returns[-min_len:], a_returns[-min_len:])
    if np.isnan(corr):
        return 0.0, None
    decorr_score = max(0, (0.6 - corr) / 0.6 * 30)
    if decorr_score > 10:
        return decorr_score, {
            "label": "Décorrélé du BTC",
            "detail": f"Corrélation {corr:.2f} (faible = indépendant)",
            "score": round(decorr_score),
        }
    return decorr_score, None


def regime_momentum(regime_result: RegimeResult) -> tuple[float, Reason | None]:
    """Points de transition creux/baissier vers haussier (0-35), au-delà d'un signal de 0,3."""
    probs = regime_result.probabilities
    bottom_prob = probs.get("bottom", 0)
    bullish_prob = probs.get("bullish", 0)
    transition_signal = bottom_prob * 0.6 + bullish_prob * 0.4
    if transition_signal > 0.3:
        reg_score = min(35, transition_signal * 70)
        dominant = regime_result.dominant_regime
        return reg_score, {
            "label": "Momentum de Régime",
            "detail": f"Régime: {dominant} (bottom {bottom_prob:.0%}, bull {bullish_prob:.0%})",
            "score": round(reg_score),
        }
    return 0.0, None


def _ema20_move(symbol: str, prices: list[float]) -> Decimal | None:
    try:
        arr = np.array(prices[-20:], dtype=float)
        ema = arr.copy()
        k = 2 / 21
        for idx in range(1, len(ema)):
            ema[idx] = arr[idx] * k + ema[idx - 1] * (1 - k)
        daily_slope = (ema[-1] - ema[-5]) / max(ema[-5], 1e-10) / 5
        ema_7d_pct = daily_slope * 7 * 100
        if abs(ema_7d_pct) > 0.01:
            return Decimal(str(round(ema_7d_pct, 4)))
    except Exception as exc:  # noqa: BLE001
        logger.debug("EMA-20 slope fallback failed for %s: %s", symbol, exc)
    return None


def predicted_move(
    symbol: str, prediction: PricePrediction | None, price_dec: Decimal, prices: list[float]
) -> tuple[Decimal, str]:
    """Variation prévue à 7 jours : ensemble écarté au-delà de ±50 %, à défaut pente de l'EMA-20 extrapolée."""
    predicted_7d_pct = Decimal("0")
    prediction_source = "none"
    if prediction and prediction.predictions:
        pred_price = prediction.predictions[-1].get("price", 0)
        if pred_price > 0 and price_dec > 0:
            raw_pct = (Decimal(str(pred_price)) / price_dec - 1) * 100
            if abs(raw_pct) > 50:
                logger.warning(
                    "SANITY CHECK (alpha): %s ensemble 7d prediction unrealistic (%.1f%%). Falling back to EMA-20.",
                    symbol,
                    float(raw_pct),
                )
            else:
                predicted_7d_pct = raw_pct
                prediction_source = "ensemble"

    if predicted_7d_pct == 0 and len(prices) >= 20:
        ema_move = _ema20_move(symbol, prices)
        if ema_move is not None:
            predicted_7d_pct = ema_move
            prediction_source = "ema20_slope"
    return predicted_7d_pct, prediction_source


def alpha_row(
    asset: Asset,
    price_dec: Decimal,
    value_dec: Decimal,
    score: float,
    reasons: list[Reason],
    move: tuple[Decimal, str],
    regime_result: RegimeResult,
    divergence_log: dict[str, Any],
) -> dict[str, Any]:
    predicted_7d_pct, prediction_source = move
    return {
        "symbol": asset.symbol,
        "name": asset.name,
        "asset_type": asset.asset_type.value,
        "current_price": float(round(price_dec, 2)),
        "score": round(score, 1),
        "predicted_7d_pct": float(round(predicted_7d_pct, 2)),
        "prediction_source": prediction_source,
        "reasons": sorted(reasons, key=lambda r: -r["score"]),
        "regime": regime_result.dominant_regime,
        "regime_confidence": round(regime_result.confidence, 2),
        "value": float(round(value_dec, 2)),
        "divergence_log": divergence_log,
    }


def rank_alpha(scored_assets: list[dict[str, Any]], total_value: Decimal) -> dict[str, Any]:
    """Classement par score décroissant ; risque de concentration si l'actif en tête dépasse 50 % du portefeuille."""
    total_value_f = float(total_value)
    for sa in scored_assets:
        if total_value_f > 0:
            sa["weight_pct"] = round(sa["value"] / total_value_f * 100, 1)
        else:
            sa["weight_pct"] = 0.0

    scored_assets.sort(key=lambda x: -x["score"])
    top = scored_assets[0]
    return {
        "found": True,
        "top_alpha": top,
        "concentration_risk": top["weight_pct"] > 50,
        "all_scores": scored_assets[:5],
        "total_portfolio_value": float(round(total_value, 2)),
    }
