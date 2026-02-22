"""Market Regime Detector — probabilistic phase detection.

Analyzes price data using 7 technical indicators to output probabilities
for 4 market phases: Bearish, Bottom, Bullish, Top.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

from app.ml import adaptive_thresholds as at
from app.ml.market_context import MarketContext, compute_market_context

logger = logging.getLogger(__name__)

PHASES = ("bearish", "bottom", "bullish", "top")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class IndicatorSignal:
    """Single indicator signal."""

    name: str
    value: float
    signal: str  # dominant phase
    strength: float  # 0-1
    description: str


@dataclass
class RegimeResult:
    """Regime detection result for a single symbol."""

    symbol: str
    probabilities: Dict[str, float]
    dominant_regime: str
    confidence: float
    signals: List[IndicatorSignal]
    description: str


@dataclass
class MarketRegime:
    """Aggregate regime for market + per-asset."""

    market: RegimeResult
    per_asset: List[RegimeResult] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe(v) -> float:
    if v is None:
        return 0.0
    f = float(v)
    if math.isnan(f) or math.isinf(f):
        return 0.0
    return f


def _normalize(votes: Dict[str, float]) -> Dict[str, float]:
    """Normalize votes so they sum to 1."""
    total = sum(votes.values())
    if total <= 0:
        return {p: 0.25 for p in PHASES}
    return {p: round(votes[p] / total, 3) for p in PHASES}


def _rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """Compute RSI using Wilder's smoothing method (P8)."""
    if len(prices) < period + 1:
        return None
    all_deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    all_gains = [max(d, 0) for d in all_deltas]
    all_losses = [-min(d, 0) for d in all_deltas]
    if len(all_deltas) < period:
        return None
    avg_gain = sum(all_gains[:period]) / period
    avg_loss = sum(all_losses[:period]) / period
    for i in range(period, len(all_deltas)):
        avg_gain = (avg_gain * (period - 1) + all_gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + all_losses[i]) / period
    if avg_loss < 1e-10:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - 100 / (1 + rs))


def _sma(prices: List[float], period: int) -> Optional[float]:
    if len(prices) < period:
        return None
    return float(np.mean(prices[-period:]))


def _ema(prices: List[float], period: int) -> Optional[List[float]]:
    """Compute full EMA series."""
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema_vals = [float(np.mean(prices[:period]))]
    for p in prices[period:]:
        ema_vals.append(ema_vals[-1] * (1 - k) + p * k)
    return ema_vals


def _macd(prices: List[float]) -> Optional[Tuple[List[float], List[float], List[float]]]:
    """Return (macd_series, signal_series, histogram_series) as full lists (P9)."""
    if len(prices) < 35:
        return None
    ema12 = _ema(prices, 12)
    ema26 = _ema(prices, 26)
    if not ema12 or not ema26:
        return None
    min_len = min(len(ema12), len(ema26))
    macd_series = [ema12[len(ema12) - min_len + i] - ema26[len(ema26) - min_len + i] for i in range(min_len)]
    if len(macd_series) < 9:
        return None
    k = 2 / 10
    signal_series = [float(np.mean(macd_series[:9]))]
    for v in macd_series[9:]:
        signal_series.append(signal_series[-1] * (1 - k) + v * k)
    offset = len(macd_series) - len(signal_series)
    histogram_series = [macd_series[offset + i] - signal_series[i] for i in range(len(signal_series))]
    return (macd_series, signal_series, histogram_series)


def _bollinger(prices: List[float], period: int = 20, num_std: float = 2.0) -> Optional[Tuple[float, float, float]]:
    """Return (lower_band, middle, upper_band) for last value."""
    if len(prices) < period:
        return None
    window = prices[-period:]
    middle = float(np.mean(window))
    std = float(np.std(window))
    return (middle - num_std * std, middle, middle + num_std * std)


# ---------------------------------------------------------------------------
# Main Detector
# ---------------------------------------------------------------------------


class MarketRegimeDetector:
    """Detects market regime from price history using 7 technical indicators."""

    def detect(
        self,
        prices: List[float],
        symbol: str = "MARKET",
        fear_greed: Optional[int] = None,
        btc_dominance: Optional[float] = None,
        asset_type: Optional[str] = None,
        market_context: Optional[MarketContext] = None,
    ) -> RegimeResult:
        """Analyze prices and return regime probabilities.

        Args:
            prices: Daily closing prices (oldest → newest), at least 7 values.
            symbol: Identifier for the result.
            fear_greed: Fear & Greed Index (0-100), optional.
            asset_type: Asset type for adaptive thresholds.
            market_context: Pre-computed MarketContext. Computed from prices if None.

        Returns:
            RegimeResult with probabilities and indicator signals.
        """
        if len(prices) < 7:
            return RegimeResult(
                symbol=symbol,
                probabilities={p: 0.25 for p in PHASES},
                dominant_regime="unknown",
                confidence=0.0,
                signals=[],
                description="Pas assez de donnees pour analyser le regime de marche.",
            )

        # Compute MarketContext if not provided (needs >= 30 prices)
        ctx = market_context
        if ctx is None and len(prices) >= 30:
            ctx = compute_market_context(prices, symbol, asset_type or "crypto", fear_greed)

        signals: List[IndicatorSignal] = []
        all_votes: List[Dict[str, float]] = []

        # 1. RSI 14
        sig = self._analyze_rsi(prices, ctx=ctx)
        if sig:
            signals.append(sig)
            all_votes.append(self._signal_to_votes(sig, ctx=ctx))

        # 2. MACD
        sig = self._analyze_macd(prices, ctx=ctx)
        if sig:
            signals.append(sig)
            all_votes.append(self._signal_to_votes(sig, ctx=ctx))

        # 3. Bollinger Bands
        sig = self._analyze_bollinger(prices, ctx=ctx)
        if sig:
            signals.append(sig)
            all_votes.append(self._signal_to_votes(sig, ctx=ctx))

        # 4. MA Cross (SMA20 / SMA50)
        sig = self._analyze_ma_cross(prices, ctx=ctx)
        if sig:
            signals.append(sig)
            all_votes.append(self._signal_to_votes(sig, ctx=ctx))

        # 5. Momentum ROC 14d
        sig = self._analyze_momentum(prices, ctx=ctx)
        if sig:
            signals.append(sig)
            all_votes.append(self._signal_to_votes(sig, ctx=ctx))

        # 6. Volatility regime
        sig = self._analyze_volatility(prices, ctx=ctx)
        if sig:
            signals.append(sig)
            all_votes.append(self._signal_to_votes(sig, ctx=ctx))

        # 7. Fear & Greed (P19: weighted by BTC dominance)
        if fear_greed is not None:
            sig = self._analyze_fear_greed(fear_greed, btc_dominance=btc_dominance, ctx=ctx)
            if sig:
                signals.append(sig)
                all_votes.append(self._signal_to_votes(sig, ctx=ctx))

        # Combine votes
        if not all_votes:
            return RegimeResult(
                symbol=symbol,
                probabilities={p: 0.25 for p in PHASES},
                dominant_regime="unknown",
                confidence=0.0,
                signals=[],
                description="Indicateurs insuffisants.",
            )

        combined = {p: 0.0 for p in PHASES}
        for votes in all_votes:
            for p in PHASES:
                combined[p] += votes.get(p, 0.0)

        probabilities = _normalize(combined)
        dominant = max(probabilities, key=probabilities.get)  # type: ignore
        confidence = self._compute_confidence(probabilities, len(all_votes), len(prices), ctx=ctx)
        description = self._make_description(dominant, probabilities, confidence)

        return RegimeResult(
            symbol=symbol,
            probabilities=probabilities,
            dominant_regime=dominant,
            confidence=round(confidence, 2),
            signals=signals,
            description=description,
        )

    # -----------------------------------------------------------------------
    # Individual indicator analyzers
    # -----------------------------------------------------------------------

    def _analyze_rsi(self, prices: List[float], ctx: Optional[MarketContext] = None) -> Optional[IndicatorSignal]:
        """Analyze RSI with adaptive thresholds derived from historical percentiles."""
        rsi = _rsi(prices)
        if rsi is None:
            return None

        if ctx:
            overbought, oversold = at.rsi_thresholds(ctx)
            bullish_upper, bearish_lower = at.rsi_midpoints(ctx)
        else:
            overbought, oversold = 78.0, 22.0
            bullish_upper, bearish_lower = 60.0, 40.0

        if rsi > overbought:
            signal, strength = "top", min(1.0, (rsi - overbought + 5) / max(100 - overbought, 1))
            desc = f"RSI en zone de surachat ({rsi:.0f}) — signal de sommet"
        elif rsi > bullish_upper:
            signal, strength = "bullish", 0.4 + 0.3 * (rsi - bullish_upper) / max(overbought - bullish_upper, 1)
            desc = f"RSI haussier ({rsi:.0f})"
        elif rsi > bearish_lower:
            # Neutral zone: split at RSI 50 to avoid false bullish bias in bear markets
            if rsi >= 50:
                signal, strength = "bullish", 0.15
            else:
                signal, strength = "bearish", 0.15
            desc = f"RSI neutre ({rsi:.0f})"
        elif rsi > oversold:
            signal, strength = "bearish", 0.4 + 0.3 * (bearish_lower - rsi) / max(bearish_lower - oversold, 1)
            desc = f"RSI baissier ({rsi:.0f})"
        else:
            signal, strength = "bottom", min(1.0, (oversold + 5 - rsi) / max(oversold, 1))
            desc = f"RSI en zone de survente ({rsi:.0f}) — signal de creux"

        return IndicatorSignal("RSI 14", round(rsi, 1), signal, round(strength, 2), desc)

    def _analyze_macd(self, prices: List[float], ctx: Optional[MarketContext] = None) -> Optional[IndicatorSignal]:
        result = _macd(prices)
        if result is None:
            return None
        macd_series, signal_series, histogram_series = result

        if len(histogram_series) < 3:
            return None

        hist_now = histogram_series[-1]
        hist_prev = histogram_series[-2]
        hist_prev2 = histogram_series[-3]
        macd_now = macd_series[-1]
        histogram = hist_now
        hist_rising = hist_now > hist_prev
        hist_accelerating = (hist_now - hist_prev) > (hist_prev - hist_prev2)

        # Adaptive scaling: normalize by volatility instead of hardcoded *50/*30
        scale = at.macd_signal_scaling(ctx) if ctx else 50.0
        scale_weak = scale * 0.6  # weaker signal for turning-point phases

        # Key insight: histogram sign alone is misleading.
        # MACD line sign tells the actual trend direction.
        # Histogram sign tells whether momentum is accelerating or decelerating.
        #
        # MACD > 0, histogram > 0 & rising → bullish (confirmed uptrend)
        # MACD > 0, histogram declining   → top (uptrend losing steam)
        # MACD < 0, histogram < 0 & falling → bearish (confirmed downtrend)
        # MACD < 0, histogram rising       → bottom (downtrend losing steam)

        if macd_now > 0:
            # MACD above zero — uptrend territory
            if histogram > 0 and hist_rising:
                base = min(1.0, abs(histogram) * scale)
                signal, strength = "bullish", base * (1.1 if hist_accelerating else 1.0)
                desc = "MACD positif et croissant — tendance haussiere confirmee"
            elif histogram > 0 and not hist_rising:
                signal, strength = "top", min(1.0, abs(histogram) * scale_weak)
                desc = "MACD positif mais ralentit — possible sommet"
            elif histogram <= 0 and hist_rising:
                signal, strength = "bullish", min(1.0, abs(histogram) * scale_weak) * 0.5
                desc = "MACD positif, histogram remonte — correction temporaire"
            else:
                signal, strength = "top", min(1.0, abs(histogram) * scale_weak)
                desc = "MACD positif mais histogram negatif — fin de tendance haussiere"
        else:
            # MACD below zero — downtrend territory
            # Scale bottom signal by how much of the MACD gap the histogram has recovered
            # e.g. MACD=-3400, histogram=+580 → recovery_ratio=0.17 → weak bottom
            recovery_ratio = abs(histogram) / max(abs(macd_now), 1e-10)
            recovery_ratio = min(recovery_ratio, 1.0)

            if histogram < 0 and not hist_rising:
                base = min(1.0, abs(histogram) * scale)
                signal, strength = "bearish", base * (1.1 if not hist_accelerating else 1.0)
                desc = "MACD negatif et decroissant — tendance baissiere confirmee"
            elif histogram > 0 and hist_rising:
                # Downtrend slowing — strength proportional to recovery
                signal, strength = "bottom", min(0.7, recovery_ratio * 0.8)
                desc = "MACD negatif, histogram remonte — possible creux (bear rally)"
            elif histogram > 0 and not hist_rising:
                signal, strength = "bottom", min(0.5, recovery_ratio * 0.5)
                desc = "MACD negatif, histogram positif mais ralentit"
            else:  # histogram < 0 and hist_rising
                signal, strength = "bottom", min(0.3, recovery_ratio * 0.3)
                desc = "MACD negatif, chute ralentit — possible stabilisation"

        strength = min(strength, 0.95)
        return IndicatorSignal("MACD", round(histogram, 4), signal, round(strength, 2), desc)

    def _analyze_bollinger(self, prices: List[float], ctx: Optional[MarketContext] = None) -> Optional[IndicatorSignal]:
        bb = _bollinger(prices)
        if bb is None:
            return None
        lower, middle, upper = bb
        current = prices[-1]
        band_width = upper - lower
        if band_width <= 0:
            return None

        position = (current - lower) / band_width  # 0 = lower band, 1 = upper band

        # Adaptive thresholds based on volatility regime
        if ctx:
            ext_high, high, low, ext_low = at.bollinger_thresholds(ctx)
        else:
            ext_high, high, low, ext_low = 0.95, 0.65, 0.35, 0.05

        if position > ext_high:
            signal, strength = "top", min(1.0, (position - ext_high) / max(1 - ext_high, 0.01) * 2)
            desc = "Prix au-dessus de la bande haute de Bollinger — surachat"
        elif position > high:
            signal, strength = "bullish", 0.3 + 0.4 * (position - high) / max(ext_high - high, 0.01)
            desc = "Prix dans la partie haute des bandes de Bollinger"
        elif position > low:
            # Middle zone: slightly bullish if above midpoint, slightly bearish if below
            if position > 0.5:
                signal, strength = "bullish", 0.1
            else:
                signal, strength = "bearish", 0.1
            desc = "Prix au milieu des bandes de Bollinger — neutre"
        elif position > ext_low:
            signal, strength = "bearish", 0.3 + 0.4 * (low - position) / max(low - ext_low, 0.01)
            desc = "Prix dans la partie basse des bandes de Bollinger"
        else:
            signal, strength = "bottom", min(1.0, (ext_low - position) / max(ext_low, 0.01) * 2)
            desc = "Prix sous la bande basse de Bollinger — survente"

        return IndicatorSignal("Bollinger Bands", round(position, 2), signal, round(strength, 2), desc)

    def _analyze_ma_cross(self, prices: List[float], ctx: Optional[MarketContext] = None) -> Optional[IndicatorSignal]:
        sma20 = _sma(prices, 20)
        sma50 = _sma(prices, 50)
        if sma20 is None or sma50 is None:
            sma20 = _sma(prices, 7)
            sma50 = _sma(prices, 20)
            if sma20 is None or sma50 is None:
                return None
            label = "MA Cross (SMA7/SMA20)"
        else:
            label = "MA Cross (SMA20/SMA50)"

        diff_pct = (sma20 - sma50) / max(abs(sma50), 1e-10) * 100

        # Adaptive significance threshold instead of hardcoded 3%
        significance = at.ma_cross_significance(ctx) if ctx else 3.0

        # Check if recently crossed (compare with 5 days ago)
        if len(prices) > 55:
            old_sma20 = _sma(prices[:-5], 20)
            old_sma50 = _sma(prices[:-5], 50)
        elif len(prices) > 25:
            old_sma20 = _sma(prices[:-3], 7)
            old_sma50 = _sma(prices[:-3], 20)
        else:
            old_sma20, old_sma50 = sma20, sma50

        recently_crossed_up = old_sma20 and old_sma50 and old_sma20 < old_sma50 and sma20 > sma50
        recently_crossed_down = old_sma20 and old_sma50 and old_sma20 > old_sma50 and sma20 < sma50

        if recently_crossed_up:
            signal, strength = "bottom", 0.8
            desc = "Golden cross — la MA courte croise la MA longue a la hausse"
        elif recently_crossed_down:
            signal, strength = "top", 0.8
            desc = "Death cross — la MA courte croise la MA longue a la baisse"
        elif diff_pct > significance:
            signal, strength = "bullish", min(0.9, diff_pct / (significance * 3))
            desc = f"MA courte au-dessus de la MA longue (+{diff_pct:.1f}%)"
        elif diff_pct > 0:
            signal, strength = "bullish", 0.3
            desc = "MA courte legerement au-dessus de la MA longue"
        elif diff_pct > -significance:
            signal, strength = "bearish", 0.3
            desc = "MA courte legerement sous la MA longue"
        else:
            signal, strength = "bearish", min(0.9, abs(diff_pct) / (significance * 3))
            desc = f"MA courte sous la MA longue ({diff_pct:.1f}%)"

        return IndicatorSignal(label, round(diff_pct, 2), signal, round(strength, 2), desc)

    def _analyze_momentum(self, prices: List[float], ctx: Optional[MarketContext] = None) -> Optional[IndicatorSignal]:
        period = 14 if len(prices) >= 20 else 7
        if len(prices) < period + 5:
            return None

        roc = (prices[-1] - prices[-period - 1]) / max(abs(prices[-period - 1]), 1e-10) * 100
        prev_roc = (
            ((prices[-2] - prices[-period - 2]) / max(abs(prices[-period - 2]), 1e-10) * 100)
            if len(prices) > period + 2
            else roc
        )

        roc_accelerating = roc > prev_roc
        roc_decelerating = roc < prev_roc

        # Adaptive momentum thresholds from historical distribution
        if ctx:
            strong_bull, bull, bear, strong_bear = at.momentum_thresholds(ctx)
        else:
            strong_bull, bull, bear, strong_bear = 10.0, 3.0, -3.0, -10.0

        if roc > strong_bull and roc_decelerating:
            signal, strength = "top", min(0.9, roc / (strong_bull * 3))
            desc = f"Momentum positif mais en ralentissement ({roc:+.1f}%) — essoufflement"
        elif roc > bull:
            signal, strength = "bullish", min(0.9, roc / (strong_bull * 2))
            desc = f"Momentum haussier ({roc:+.1f}%)"
        elif roc > bear:
            signal, strength = "bullish" if roc > 0 else "bearish", 0.2
            desc = f"Momentum neutre ({roc:+.1f}%)"
        elif roc > strong_bear:
            signal, strength = "bearish", min(0.9, abs(roc) / (abs(strong_bear) * 2))
            desc = f"Momentum baissier ({roc:+.1f}%)"
        else:
            if roc_accelerating:
                signal, strength = "bottom", min(0.9, abs(roc) / (abs(strong_bear) * 3))
                desc = f"Momentum tres negatif mais en amelioration ({roc:+.1f}%) — possible creux"
            else:
                signal, strength = "bearish", min(0.9, abs(roc) / (abs(strong_bear) * 2))
                desc = f"Momentum fortement baissier ({roc:+.1f}%)"

        return IndicatorSignal(f"Momentum {period}j", round(roc, 1), signal, round(strength, 2), desc)

    def _analyze_volatility(
        self, prices: List[float], ctx: Optional[MarketContext] = None
    ) -> Optional[IndicatorSignal]:
        if len(prices) < 15:
            return None

        returns = [(prices[i] - prices[i - 1]) / max(abs(prices[i - 1]), 1e-10) for i in range(-14, 0)]
        ann_factor = ctx.annualization_factor if ctx else 365
        vol = float(np.std(returns)) * np.sqrt(ann_factor) * 100  # annualized %

        # Adaptive thresholds from historical vol distribution
        if ctx:
            extreme_vol, high_vol = at.volatility_regime_thresholds(ctx)
        else:
            extreme_vol, high_vol = 80.0, 50.0

        # Price position relative to recent range
        recent = prices[-14:]
        price_position = (prices[-1] - min(recent)) / max(max(recent) - min(recent), 1e-10)

        if vol > extreme_vol and price_position > 0.7:
            signal, strength = "top", min(0.8, vol / (extreme_vol * 2))
            desc = f"Volatilite extreme ({vol:.0f}%) avec prix en haut de range — instabilite"
        elif vol > extreme_vol and price_position < 0.3:
            signal, strength = "bottom", min(0.8, vol / (extreme_vol * 2))
            desc = f"Volatilite extreme ({vol:.0f}%) avec prix en bas de range — capitulation possible"
        elif vol > high_vol:
            signal, strength = "bearish" if price_position < 0.5 else "top", 0.4
            desc = f"Volatilite elevee ({vol:.0f}%) — marche incertain"
        else:
            # Moderate volatility — use longer-term trend to decide direction
            # Use 30-day SMA if available, else 14-day; avoids false signals from bounces
            lookback = min(30, len(prices))
            sma_long = float(np.mean(prices[-lookback:]))
            trend_up = prices[-1] > sma_long
            if trend_up and price_position > 0.6:
                signal, strength = "bullish", 0.10
            elif not trend_up and price_position < 0.4:
                signal, strength = "bearish", 0.10
            elif not trend_up:
                signal, strength = "bearish", 0.03
            else:
                signal, strength = "bullish", 0.03
            desc = f"Volatilite moderee ({vol:.0f}%) — marche stable"

        return IndicatorSignal("Volatilite 14j", round(vol, 0), signal, round(strength, 2), desc)

    def _analyze_fear_greed(
        self, fg: int, btc_dominance: Optional[float] = None, ctx: Optional[MarketContext] = None
    ) -> IndicatorSignal:
        # Adaptive F&G thresholds (vol-adjusted)
        if ctx:
            ext_greed, greed, fear, ext_fear = at.fear_greed_thresholds(ctx)
        else:
            ext_greed, greed, fear, ext_fear = 75.0, 55.0, 45.0, 25.0

        if fg >= ext_greed:
            signal, strength = "top", min(1.0, (fg - ext_greed) / max(100 - ext_greed, 1))
            desc = f"Extreme Greed ({fg}) — euphorie, risque de correction"
        elif fg >= greed:
            signal, strength = "bullish", 0.3 + 0.3 * (fg - greed) / max(ext_greed - greed, 1)
            desc = f"Greed ({fg}) — optimisme du marche"
        elif fg >= fear:
            signal, strength = "bullish", 0.2
            desc = f"Neutre ({fg})"
        elif fg >= ext_fear:
            signal, strength = "bearish", 0.3 + 0.3 * (fear - fg) / max(fear - ext_fear, 1)
            desc = f"Fear ({fg}) — pessimisme du marche"
        else:
            signal, strength = "bottom", min(1.0, (ext_fear - fg) / max(ext_fear, 1))
            desc = f"Extreme Fear ({fg}) — panique, opportunite d'achat potentielle"

        # P19: Adjust F&G signal strength by BTC dominance for altcoins
        if btc_dominance is not None and btc_dominance > 0:
            dominance_factor = btc_dominance / 100.0
            strength = strength * dominance_factor

        return IndicatorSignal("Fear & Greed", float(fg), signal, round(strength, 2), desc)

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _signal_to_votes(self, sig: IndicatorSignal, ctx: Optional[MarketContext] = None) -> Dict[str, float]:
        """Convert a signal into weighted votes for each phase.

        Spillover weights are adaptive: higher volatility → more regime
        uncertainty → more spillover to neighboring phases.
        """
        s = sig.strength
        votes = {p: 0.05 for p in PHASES}

        if ctx:
            w = at.phase_spillover_weights(ctx)
            adj, opp, diag = w["adjacent"], w["opposite"], w["diagonal"]
        else:
            adj, opp, diag = 0.15, 0.10, 0.20

        # Phase adjacency: bullish↔top, bearish↔bottom are "adjacent"
        # bullish↔bottom, bearish↔top are "diagonal" (turning-point neighbors)
        # bullish↔bearish, top↔bottom are "opposite"
        if sig.signal == "bullish":
            votes["bullish"] += s
            votes["top"] += s * adj
            votes["bottom"] += s * opp
        elif sig.signal == "bearish":
            votes["bearish"] += s
            votes["bottom"] += s * adj
            votes["top"] += s * opp
        elif sig.signal == "top":
            votes["top"] += s
            votes["bullish"] += s * diag
            votes["bearish"] += s * adj
        elif sig.signal == "bottom":
            votes["bottom"] += s
            votes["bearish"] += s * diag
            votes["bullish"] += s * adj

        return votes

    def _compute_confidence(
        self, probs: Dict[str, float], num_indicators: int, num_prices: int, ctx: Optional[MarketContext] = None
    ) -> float:
        """Confidence based on indicator count, data length, and probability spread.

        Weights adapt to market conditions: in high-vol markets, data length
        matters more (need more samples for reliability).
        """
        indicator_factor = min(1.0, num_indicators / 7)
        data_factor = min(1.0, num_prices / 60)
        values = list(probs.values())
        spread = max(values) - min(values)
        spread_factor = min(1.0, spread / 0.4)

        if ctx:
            ind_w, data_w, spread_w = at.confidence_weights(ctx)
        else:
            ind_w, data_w, spread_w = 0.40, 0.30, 0.30

        return indicator_factor * ind_w + data_factor * data_w + spread_factor * spread_w

    def _make_description(self, dominant: str, probs: Dict[str, float], confidence: float) -> str:
        pct = probs[dominant] * 100
        labels = {
            "bearish": "Marche baissier",
            "bottom": "Creux potentiel — zone d'accumulation",
            "bullish": "Marche haussier",
            "top": "Sommet potentiel — zone de distribution",
        }
        label = labels.get(dominant, dominant)

        # Check for secondary signal
        sorted_phases = sorted(probs.items(), key=lambda x: -x[1])
        second = sorted_phases[1]
        second_labels = {
            "bearish": "avec pression baissiere",
            "bottom": "avec signes de creux",
            "bullish": "avec tendance haussiere",
            "top": "avec signes de surchauffe",
        }

        if second[1] > 0.25:
            return f"{label} ({pct:.0f}%), {second_labels.get(second[0], '')}."
        return f"{label} ({pct:.0f}%)."

    def detect_multi_timeframe(
        self,
        prices: List[float],
        symbol: str = "MARKET",
        fear_greed: Optional[int] = None,
        btc_dominance: Optional[float] = None,
        asset_type: Optional[str] = None,
        market_context: Optional[MarketContext] = None,
    ) -> Dict:
        """Detect regime on daily and weekly timeframes (P15).

        Returns dict with daily_regime, weekly_regime, timeframe_alignment, and note.
        """
        daily = self.detect(
            prices, symbol, fear_greed, btc_dominance, asset_type=asset_type, market_context=market_context
        )

        weekly_result = None
        if len(prices) >= 28:
            weekly_prices = []
            for i in range(0, len(prices), 7):
                end = min(i + 7, len(prices))
                weekly_prices.append(prices[end - 1])
            if len(weekly_prices) >= 7:
                weekly_result = self.detect(
                    weekly_prices, f"{symbol}_weekly", fear_greed, btc_dominance, asset_type=asset_type
                )

        if weekly_result is None:
            return {
                "daily": daily,
                "weekly": None,
                "timeframe_alignment": "daily_only",
                "note": "Pas assez de donnees pour l'analyse hebdomadaire.",
            }

        if daily.dominant_regime == weekly_result.dominant_regime:
            alignment = "aligned"
            note = f"Les timeframes journalier et hebdomadaire convergent: {daily.dominant_regime}."
        else:
            alignment = "divergent"
            note = (
                f"Divergence: regime journalier = {daily.dominant_regime}, "
                f"regime hebdomadaire = {weekly_result.dominant_regime}. "
                f"Prudence recommandee."
            )

        return {
            "daily": daily,
            "weekly": weekly_result,
            "timeframe_alignment": alignment,
            "note": note,
        }


# Singleton
regime_detector = MarketRegimeDetector()
