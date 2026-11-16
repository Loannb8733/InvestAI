from collections.abc import Callable
from typing import Any

from app.ml import adaptive_thresholds as at
from app.ml.market_context import MarketContext, compute_market_context
from app.ml.regime.indicators import ema, normalize, rsi
from app.ml.regime.oscillators import analyze_bollinger, analyze_macd, analyze_rsi
from app.ml.regime.trend_signals import (
    analyze_fear_greed,
    analyze_ma_cross,
    analyze_momentum,
    analyze_vix,
    analyze_volatility,
)
from app.ml.regime.types import PHASES, IndicatorSignal, RegimeResult

Analyzer = Callable[[list[float], MarketContext | None], IndicatorSignal | None]
PRICE_ANALYZERS: tuple[Analyzer, ...] = (
    analyze_rsi,
    analyze_macd,
    analyze_bollinger,
    analyze_ma_cross,
    analyze_momentum,
    analyze_volatility,
)
LABELS = {
    "bearish": "Markdown — structure de prix descendante (Lower Highs)",
    "bottom": "Bottoming — RSI en survente, epuisement vendeur",
    "bullish": "Mark-up — cassure de resistance, volume croissant",
    "top": "Topping — RSI surchauffe, risque de retournement",
}
SECOND_LABELS = {
    "bearish": "avec pression baissiere",
    "bottom": "avec signes d'accumulation",
    "bullish": "avec tendance haussiere",
    "top": "avec signes de distribution",
}


def _unknown(symbol: str, description: str) -> RegimeResult:
    return RegimeResult(symbol, dict.fromkeys(PHASES, 0.25), "unknown", 0.0, [], description)


def signal_to_votes(sig: IndicatorSignal, ctx: MarketContext | None = None) -> dict[str, float]:
    """Votes d'un signal : sa phase prend sa force, les phases voisines une part qui croît avec la volatilité."""
    s = sig.strength
    votes = dict.fromkeys(PHASES, 0.05)
    if ctx:
        w = at.phase_spillover_weights(ctx)
        adj, opp, diag = w["adjacent"], w["opposite"], w["diagonal"]
    else:
        adj, opp, diag = 0.15, 0.10, 0.20
    spill = {
        "bullish": (("top", adj), ("bottom", opp)),
        "bearish": (("bottom", adj), ("top", opp)),
        "top": (("bullish", diag), ("bearish", adj)),
        "bottom": (("bearish", diag), ("bullish", adj)),
    }
    if sig.signal in spill:
        votes[sig.signal] += s
        for phase, share in spill[sig.signal]:
            votes[phase] += s * share
    return votes


def _confidence(probs: dict[str, float], num_indicators: int, num_prices: int, ctx: MarketContext | None) -> float:
    indicator_factor = min(1.0, num_indicators / 7)
    data_factor = min(1.0, num_prices / 60)
    values = list(probs.values())
    spread_factor = min(1.0, (max(values) - min(values)) / 0.4)
    ind_w, data_w, spread_w = at.confidence_weights(ctx) if ctx else (0.40, 0.30, 0.30)
    return indicator_factor * ind_w + data_factor * data_w + spread_factor * spread_w


def _description(dominant: str, probs: dict[str, float]) -> str:
    pct = probs[dominant] * 100
    label = LABELS.get(dominant, dominant)
    second = sorted(probs.items(), key=lambda x: -x[1])[1]
    if second[1] > 0.25:
        return f"{label} ({pct:.0f}%), {SECOND_LABELS.get(second[0], '')}."
    return f"{label} ({pct:.0f}%)."


def _ema20_slope(prices: list[float]) -> float | None:
    if len(prices) < 25:
        return None
    series = ema(prices, 20)
    if series and len(series) >= 5:
        return (series[-1] - series[-5]) / max(abs(series[-5]), 1e-10)
    return None


def _refine_bottom(prices: list[float], slope: float | None) -> str:
    value = rsi(prices) if len(prices) >= 15 else None
    if value is not None and value > 35:
        return "accumulation"
    if slope is not None and slope > -0.005:
        return "accumulation"
    return "bottoming"


def _refine_top(probs: dict[str, float], slope: float | None) -> str:
    if probs.get("bearish", 0) > 0.20:
        return "distribution"
    if slope is not None and slope < 0.005:
        return "distribution"
    return "topping"


class MarketRegimeDetector:
    """Régime de marché probabiliste (baissier, creux, haussier, sommet) tiré de huit indicateurs au plus."""

    def detect(
        self,
        prices: list[float],
        symbol: str = "MARKET",
        fear_greed: int | None = None,
        btc_dominance: float | None = None,
        asset_type: str | None = None,
        market_context: MarketContext | None = None,
        vix: float | None = None,
    ) -> RegimeResult:
        """Probabilités des phases d'après les cours (au moins 7), le Fear & Greed et le VIX s'ils sont fournis."""
        if len(prices) < 7:
            return _unknown(symbol, "Pas assez de donnees pour analyser le regime de marche.")
        ctx = market_context
        if ctx is None and len(prices) >= 30:
            ctx = compute_market_context(prices, symbol, asset_type or "crypto", fear_greed)
        signals = [sig for analyze in PRICE_ANALYZERS if (sig := analyze(prices, ctx))]
        if fear_greed is not None:
            signals.append(analyze_fear_greed(fear_greed, btc_dominance=btc_dominance, ctx=ctx))
        if vix is not None and (vix_signal := analyze_vix(vix, ctx=ctx)):
            signals.append(vix_signal)
        if not signals:
            return _unknown(symbol, "Indicateurs insuffisants.")
        combined = dict.fromkeys(PHASES, 0.0)
        for votes in [signal_to_votes(sig, ctx=ctx) for sig in signals]:
            for p in PHASES:
                combined[p] += votes.get(p, 0.0)
        probabilities = normalize(combined)
        dominant = max(probabilities, key=lambda phase: probabilities[phase])
        confidence = _confidence(probabilities, len(signals), len(prices), ctx)
        return RegimeResult(
            symbol=symbol,
            probabilities=probabilities,
            dominant_regime=dominant,
            confidence=round(confidence, 2),
            signals=signals,
            description=_description(dominant, probabilities),
        )

    @staticmethod
    def refine_to_6phase(result: RegimeResult, prices: list[float]) -> str:
        """Phase en six temps (de markdown à distribution) d'après le RSI et la pente de l'EMA 20."""
        slope = _ema20_slope(prices)
        if result.dominant_regime == "bottom":
            return _refine_bottom(prices, slope)
        if result.dominant_regime == "top":
            return _refine_top(result.probabilities, slope)
        return {"bullish": "markup", "bearish": "markdown"}.get(result.dominant_regime, result.dominant_regime)

    def detect_multi_timeframe(
        self,
        prices: list[float],
        symbol: str = "MARKET",
        fear_greed: int | None = None,
        btc_dominance: float | None = None,
        asset_type: str | None = None,
        market_context: MarketContext | None = None,
    ) -> dict[str, Any]:
        """Régimes journalier et hebdomadaire (dernier cours de chaque semaine) et leur concordance."""
        daily = self.detect(
            prices, symbol, fear_greed, btc_dominance, asset_type=asset_type, market_context=market_context
        )
        weekly = None
        if len(prices) >= 28:
            weekly_prices = [prices[min(i + 7, len(prices)) - 1] for i in range(0, len(prices), 7)]
            if len(weekly_prices) >= 7:
                weekly = self.detect(
                    weekly_prices, f"{symbol}_weekly", fear_greed, btc_dominance, asset_type=asset_type
                )
        if weekly is None:
            return {
                "daily": daily,
                "weekly": None,
                "timeframe_alignment": "daily_only",
                "note": "Pas assez de donnees pour l'analyse hebdomadaire.",
            }
        if daily.dominant_regime == weekly.dominant_regime:
            alignment = "aligned"
            note = f"Les timeframes journalier et hebdomadaire convergent: {daily.dominant_regime}."
        else:
            alignment = "divergent"
            note = (
                f"Divergence: regime journalier = {daily.dominant_regime}, "
                f"regime hebdomadaire = {weekly.dominant_regime}. "
                f"Prudence recommandee."
            )
        return {"daily": daily, "weekly": weekly, "timeframe_alignment": alignment, "note": note}
