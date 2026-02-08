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
    signal: str        # dominant phase
    strength: float    # 0-1
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
    """Compute RSI."""
    if len(prices) < period + 1:
        return None
    deltas = [prices[i] - prices[i - 1] for i in range(-period, 0)]
    gains = [d for d in deltas if d > 0]
    losses = [-d for d in deltas if d < 0]
    avg_gain = np.mean(gains) if gains else 0.0
    avg_loss = np.mean(losses) if losses else 1e-10
    rs = avg_gain / max(avg_loss, 1e-10)
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


def _macd(prices: List[float]) -> Optional[Tuple[float, float, float]]:
    """Return (macd_line, signal_line, histogram) for last value."""
    if len(prices) < 35:
        return None
    ema12 = _ema(prices, 12)
    ema26 = _ema(prices, 26)
    if not ema12 or not ema26:
        return None
    # Align lengths
    min_len = min(len(ema12), len(ema26))
    macd_line = [ema12[len(ema12) - min_len + i] - ema26[len(ema26) - min_len + i]
                 for i in range(min_len)]
    if len(macd_line) < 9:
        return None
    # Signal = EMA9 of MACD line
    k = 2 / 10
    signal = [float(np.mean(macd_line[:9]))]
    for v in macd_line[9:]:
        signal.append(signal[-1] * (1 - k) + v * k)
    hist = macd_line[-1] - signal[-1]
    prev_hist = macd_line[-2] - signal[-2] if len(signal) >= 2 and len(macd_line) >= 2 else hist
    return (macd_line[-1], signal[-1], hist)


def _bollinger(prices: List[float], period: int = 20, num_std: float = 2.0
               ) -> Optional[Tuple[float, float, float]]:
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
    ) -> RegimeResult:
        """Analyze prices and return regime probabilities.

        Args:
            prices: Daily closing prices (oldest → newest), at least 7 values.
            symbol: Identifier for the result.
            fear_greed: Fear & Greed Index (0-100), optional.

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

        signals: List[IndicatorSignal] = []
        all_votes: List[Dict[str, float]] = []

        # 1. RSI 14
        sig = self._analyze_rsi(prices)
        if sig:
            signals.append(sig)
            all_votes.append(self._signal_to_votes(sig))

        # 2. MACD
        sig = self._analyze_macd(prices)
        if sig:
            signals.append(sig)
            all_votes.append(self._signal_to_votes(sig))

        # 3. Bollinger Bands
        sig = self._analyze_bollinger(prices)
        if sig:
            signals.append(sig)
            all_votes.append(self._signal_to_votes(sig))

        # 4. MA Cross (SMA20 / SMA50)
        sig = self._analyze_ma_cross(prices)
        if sig:
            signals.append(sig)
            all_votes.append(self._signal_to_votes(sig))

        # 5. Momentum ROC 14d
        sig = self._analyze_momentum(prices)
        if sig:
            signals.append(sig)
            all_votes.append(self._signal_to_votes(sig))

        # 6. Volatility regime
        sig = self._analyze_volatility(prices)
        if sig:
            signals.append(sig)
            all_votes.append(self._signal_to_votes(sig))

        # 7. Fear & Greed
        if fear_greed is not None:
            sig = self._analyze_fear_greed(fear_greed)
            if sig:
                signals.append(sig)
                all_votes.append(self._signal_to_votes(sig))

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
        confidence = self._compute_confidence(probabilities, len(all_votes), len(prices))
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

    def _analyze_rsi(self, prices: List[float]) -> Optional[IndicatorSignal]:
        rsi = _rsi(prices)
        if rsi is None:
            return None

        if rsi > 75:
            signal, strength = "top", min(1.0, (rsi - 70) / 30)
            desc = f"RSI en zone de surachat ({rsi:.0f}) — signal de sommet"
        elif rsi > 60:
            signal, strength = "bullish", 0.4 + 0.3 * (rsi - 60) / 15
            desc = f"RSI haussier ({rsi:.0f})"
        elif rsi > 40:
            signal, strength = "bullish", 0.3
            desc = f"RSI neutre ({rsi:.0f})"
        elif rsi > 25:
            signal, strength = "bearish", 0.4 + 0.3 * (40 - rsi) / 15
            desc = f"RSI baissier ({rsi:.0f})"
        else:
            signal, strength = "bottom", min(1.0, (30 - rsi) / 30)
            desc = f"RSI en zone de survente ({rsi:.0f}) — signal de creux"

        return IndicatorSignal("RSI 14", round(rsi, 1), signal, round(strength, 2), desc)

    def _analyze_macd(self, prices: List[float]) -> Optional[IndicatorSignal]:
        result = _macd(prices)
        if result is None:
            return None
        macd_line, signal_line, histogram = result

        # Check histogram direction (last 3 values for trend)
        ema12 = _ema(prices, 12)
        ema26 = _ema(prices, 26)
        if not ema12 or not ema26:
            return None
        min_len = min(len(ema12), len(ema26))
        macd_series = [ema12[len(ema12) - min_len + i] - ema26[len(ema26) - min_len + i]
                       for i in range(min_len)]
        k = 2 / 10
        signal_series = [float(np.mean(macd_series[:9]))]
        for v in macd_series[9:]:
            signal_series.append(signal_series[-1] * (1 - k) + v * k)

        if len(signal_series) < 3 or len(macd_series) < 3:
            return None

        hist_now = macd_series[-1] - signal_series[-1]
        hist_prev = macd_series[-2] - signal_series[-2]
        hist_prev2 = macd_series[-3] - signal_series[-3] if len(signal_series) >= 3 else hist_prev
        hist_rising = hist_now > hist_prev
        hist_accelerating = (hist_now - hist_prev) > (hist_prev - hist_prev2)

        if histogram > 0 and hist_rising:
            signal, strength = "bullish", min(1.0, abs(histogram) * 50)
            desc = "MACD positif et croissant — tendance haussiere"
        elif histogram > 0 and not hist_rising:
            signal, strength = "top", min(1.0, abs(histogram) * 30)
            desc = "MACD positif mais ralentit — possible sommet"
        elif histogram < 0 and not hist_rising:
            signal, strength = "bearish", min(1.0, abs(histogram) * 50)
            desc = "MACD negatif et decroissant — tendance baissiere"
        else:  # histogram < 0 and hist_rising
            signal, strength = "bottom", min(1.0, abs(histogram) * 30)
            desc = "MACD negatif mais remonte — possible creux"

        strength = min(strength, 0.95)
        return IndicatorSignal("MACD", round(histogram, 4), signal, round(strength, 2), desc)

    def _analyze_bollinger(self, prices: List[float]) -> Optional[IndicatorSignal]:
        bb = _bollinger(prices)
        if bb is None:
            return None
        lower, middle, upper = bb
        current = prices[-1]
        band_width = upper - lower
        if band_width <= 0:
            return None

        position = (current - lower) / band_width  # 0 = lower band, 1 = upper band

        if position > 0.95:
            signal, strength = "top", min(1.0, (position - 0.9) * 5)
            desc = f"Prix au-dessus de la bande haute de Bollinger — surachat"
        elif position > 0.65:
            signal, strength = "bullish", 0.3 + 0.4 * (position - 0.65) / 0.3
            desc = f"Prix dans la partie haute des bandes de Bollinger"
        elif position > 0.35:
            signal, strength = "bullish", 0.2
            desc = f"Prix au milieu des bandes de Bollinger — neutre"
        elif position > 0.05:
            signal, strength = "bearish", 0.3 + 0.4 * (0.35 - position) / 0.3
            desc = f"Prix dans la partie basse des bandes de Bollinger"
        else:
            signal, strength = "bottom", min(1.0, (0.1 - position) * 5)
            desc = f"Prix sous la bande basse de Bollinger — survente"

        return IndicatorSignal(
            "Bollinger Bands", round(position, 2), signal, round(strength, 2), desc
        )

    def _analyze_ma_cross(self, prices: List[float]) -> Optional[IndicatorSignal]:
        sma20 = _sma(prices, 20)
        sma50 = _sma(prices, 50)
        if sma20 is None or sma50 is None:
            # Fallback: use SMA7 vs SMA20 if not enough data
            sma20 = _sma(prices, 7)
            sma50 = _sma(prices, 20)
            if sma20 is None or sma50 is None:
                return None
            label = "MA Cross (SMA7/SMA20)"
        else:
            label = "MA Cross (SMA20/SMA50)"

        diff_pct = (sma20 - sma50) / max(abs(sma50), 1e-10) * 100

        # Check if recently crossed (compare with 5 days ago)
        if len(prices) > 55:
            old_sma20 = _sma(prices[:-5], 20)
            old_sma50 = _sma(prices[:-5], 50)
        elif len(prices) > 25:
            old_sma20 = _sma(prices[:-3], 7)
            old_sma50 = _sma(prices[:-3], 20)
        else:
            old_sma20, old_sma50 = sma20, sma50

        recently_crossed_up = (old_sma20 and old_sma50 and
                               old_sma20 < old_sma50 and sma20 > sma50)
        recently_crossed_down = (old_sma20 and old_sma50 and
                                 old_sma20 > old_sma50 and sma20 < sma50)

        if recently_crossed_up:
            signal, strength = "bottom", 0.8
            desc = f"Golden cross — la MA courte croise la MA longue a la hausse"
        elif recently_crossed_down:
            signal, strength = "top", 0.8
            desc = f"Death cross — la MA courte croise la MA longue a la baisse"
        elif diff_pct > 3:
            signal, strength = "bullish", min(0.9, diff_pct / 10)
            desc = f"MA courte au-dessus de la MA longue (+{diff_pct:.1f}%)"
        elif diff_pct > 0:
            signal, strength = "bullish", 0.3
            desc = f"MA courte legerement au-dessus de la MA longue"
        elif diff_pct > -3:
            signal, strength = "bearish", 0.3
            desc = f"MA courte legerement sous la MA longue"
        else:
            signal, strength = "bearish", min(0.9, abs(diff_pct) / 10)
            desc = f"MA courte sous la MA longue ({diff_pct:.1f}%)"

        return IndicatorSignal(label, round(diff_pct, 2), signal, round(strength, 2), desc)

    def _analyze_momentum(self, prices: List[float]) -> Optional[IndicatorSignal]:
        period = 14 if len(prices) >= 20 else 7
        if len(prices) < period + 5:
            return None

        roc = (prices[-1] - prices[-period - 1]) / max(abs(prices[-period - 1]), 1e-10) * 100
        prev_roc = ((prices[-2] - prices[-period - 2]) /
                    max(abs(prices[-period - 2]), 1e-10) * 100) if len(prices) > period + 2 else roc

        roc_accelerating = roc > prev_roc
        roc_decelerating = roc < prev_roc

        if roc > 10 and roc_decelerating:
            signal, strength = "top", min(0.9, roc / 30)
            desc = f"Momentum positif mais en ralentissement ({roc:+.1f}%) — essoufflement"
        elif roc > 3:
            signal, strength = "bullish", min(0.9, roc / 20)
            desc = f"Momentum haussier ({roc:+.1f}%)"
        elif roc > -3:
            signal, strength = "bullish" if roc > 0 else "bearish", 0.2
            desc = f"Momentum neutre ({roc:+.1f}%)"
        elif roc > -10:
            signal, strength = "bearish", min(0.9, abs(roc) / 20)
            desc = f"Momentum baissier ({roc:+.1f}%)"
        else:
            if roc_accelerating:  # negative but less negative = reversing
                signal, strength = "bottom", min(0.9, abs(roc) / 30)
                desc = f"Momentum tres negatif mais en amelioration ({roc:+.1f}%) — possible creux"
            else:
                signal, strength = "bearish", min(0.9, abs(roc) / 20)
                desc = f"Momentum fortement baissier ({roc:+.1f}%)"

        return IndicatorSignal(
            f"Momentum {period}j", round(roc, 1), signal, round(strength, 2), desc
        )

    def _analyze_volatility(self, prices: List[float]) -> Optional[IndicatorSignal]:
        if len(prices) < 15:
            return None

        returns = [(prices[i] - prices[i - 1]) / max(abs(prices[i - 1]), 1e-10)
                    for i in range(-14, 0)]
        vol = float(np.std(returns)) * np.sqrt(365) * 100  # annualized %

        # Price position relative to recent range
        recent = prices[-14:]
        price_position = ((prices[-1] - min(recent)) /
                          max(max(recent) - min(recent), 1e-10))

        if vol > 80 and price_position > 0.7:
            signal, strength = "top", min(0.8, vol / 150)
            desc = f"Volatilite extreme ({vol:.0f}%) avec prix en haut de range — instabilite"
        elif vol > 80 and price_position < 0.3:
            signal, strength = "bottom", min(0.8, vol / 150)
            desc = f"Volatilite extreme ({vol:.0f}%) avec prix en bas de range — capitulation possible"
        elif vol > 50:
            signal, strength = "bearish" if price_position < 0.5 else "top", 0.4
            desc = f"Volatilite elevee ({vol:.0f}%) — marche incertain"
        else:
            signal, strength = "bullish", 0.3
            desc = f"Volatilite moderee ({vol:.0f}%) — marche stable"

        return IndicatorSignal("Volatilite 14j", round(vol, 0), signal, round(strength, 2), desc)

    def _analyze_fear_greed(self, fg: int) -> IndicatorSignal:
        if fg >= 80:
            signal, strength = "top", min(1.0, (fg - 75) / 25)
            desc = f"Extreme Greed ({fg}) — euphorie, risque de correction"
        elif fg >= 55:
            signal, strength = "bullish", 0.3 + 0.3 * (fg - 55) / 25
            desc = f"Greed ({fg}) — optimisme du marche"
        elif fg >= 45:
            signal, strength = "bullish", 0.2
            desc = f"Neutre ({fg})"
        elif fg >= 20:
            signal, strength = "bearish", 0.3 + 0.3 * (45 - fg) / 25
            desc = f"Fear ({fg}) — pessimisme du marche"
        else:
            signal, strength = "bottom", min(1.0, (25 - fg) / 25)
            desc = f"Extreme Fear ({fg}) — panique, opportunite d'achat potentielle"

        return IndicatorSignal("Fear & Greed", float(fg), signal, round(strength, 2), desc)

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _signal_to_votes(self, sig: IndicatorSignal) -> Dict[str, float]:
        """Convert a signal into weighted votes for each phase.

        The dominant phase gets the full strength, adjacent phases get partial,
        opposite phase gets a small residual.
        """
        s = sig.strength
        votes = {p: 0.05 for p in PHASES}  # small base for all

        if sig.signal == "bullish":
            votes["bullish"] += s
            votes["top"] += s * 0.15
            votes["bottom"] += s * 0.1
        elif sig.signal == "bearish":
            votes["bearish"] += s
            votes["bottom"] += s * 0.15
            votes["top"] += s * 0.1
        elif sig.signal == "top":
            votes["top"] += s
            votes["bullish"] += s * 0.2
            votes["bearish"] += s * 0.15
        elif sig.signal == "bottom":
            votes["bottom"] += s
            votes["bearish"] += s * 0.2
            votes["bullish"] += s * 0.15

        return votes

    def _compute_confidence(
        self, probs: Dict[str, float], num_indicators: int, num_prices: int
    ) -> float:
        """Confidence based on indicator count, data length, and probability spread."""
        # More indicators → more confidence
        indicator_factor = min(1.0, num_indicators / 7)
        # More data → more confidence
        data_factor = min(1.0, num_prices / 60)
        # Higher spread → more confident decision
        values = list(probs.values())
        spread = max(values) - min(values)
        spread_factor = min(1.0, spread / 0.4)

        return indicator_factor * 0.4 + data_factor * 0.3 + spread_factor * 0.3

    def _make_description(
        self, dominant: str, probs: Dict[str, float], confidence: float
    ) -> str:
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


# Singleton
regime_detector = MarketRegimeDetector()
