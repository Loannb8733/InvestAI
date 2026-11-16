from app.ml import adaptive_thresholds as at
from app.ml.market_context import MarketContext
from app.ml.regime.indicators import bollinger, macd, rsi
from app.ml.regime.types import IndicatorSignal

Reading = tuple[str, float, str]


def _rsi_zone(value: float, overbought: float, oversold: float, bullish_upper: float, bearish_lower: float) -> Reading:
    if value > overbought:
        strength = min(1.0, (value - overbought + 5) / max(100 - overbought, 1))
        return "top", strength, f"RSI en zone de surachat ({value:.0f}) — signal de sommet"
    if value > bullish_upper:
        strength = 0.4 + 0.3 * (value - bullish_upper) / max(overbought - bullish_upper, 1)
        return "bullish", strength, f"RSI haussier ({value:.0f})"
    if value > bearish_lower:
        return ("bullish" if value >= 50 else "bearish"), 0.15, f"RSI neutre ({value:.0f})"
    if value > oversold:
        strength = 0.4 + 0.3 * (bearish_lower - value) / max(bearish_lower - oversold, 1)
        return "bearish", strength, f"RSI baissier ({value:.0f})"
    strength = min(1.0, (oversold + 5 - value) / max(oversold, 1))
    return "bottom", strength, f"RSI en zone de survente ({value:.0f}) — signal de creux"


def analyze_rsi(prices: list[float], ctx: MarketContext | None = None) -> IndicatorSignal | None:
    """RSI 14 lu contre des seuils tirés des percentiles historiques de l'actif ; 78/22 sans contexte."""
    value = rsi(prices)
    if value is None:
        return None
    if ctx:
        overbought, oversold = at.rsi_thresholds(ctx)
        bullish_upper, bearish_lower = at.rsi_midpoints(ctx)
    else:
        overbought, oversold = 78.0, 22.0
        bullish_upper, bearish_lower = 60.0, 40.0
    signal, strength, desc = _rsi_zone(value, overbought, oversold, bullish_upper, bearish_lower)
    return IndicatorSignal("RSI 14", round(value, 1), signal, round(strength, 2), desc)


def _uptrend(histogram: float, rising: bool, accelerating: bool, scale: float) -> Reading:
    weak = scale * 0.6
    if histogram > 0 and rising:
        base = min(1.0, abs(histogram) * scale)
        strength = base * (1.1 if accelerating else 1.0)
        return "bullish", strength, "MACD positif et croissant — tendance haussiere confirmee"
    if histogram > 0:
        return "top", min(1.0, abs(histogram) * weak), "MACD positif mais ralentit — possible sommet"
    if rising:
        strength = min(1.0, abs(histogram) * weak) * 0.5
        return "bullish", strength, "MACD positif, histogram remonte — correction temporaire"
    strength = min(1.0, abs(histogram) * weak)
    return "top", strength, "MACD positif mais histogram negatif — fin de tendance haussiere"


def _downtrend(histogram: float, macd_now: float, rising: bool, accelerating: bool, scale: float) -> Reading:
    recovery_ratio = min(abs(histogram) / max(abs(macd_now), 1e-10), 1.0)
    if histogram < 0 and not rising:
        base = min(1.0, abs(histogram) * scale)
        strength = base * (1.1 if not accelerating else 1.0)
        return "bearish", strength, "MACD negatif et decroissant — tendance baissiere confirmee"
    if histogram > 0 and rising:
        strength = min(0.7, recovery_ratio * 0.8)
        return "bottom", strength, "MACD negatif, histogram remonte — possible creux (bear rally)"
    if histogram > 0:
        return "bottom", min(0.5, recovery_ratio * 0.5), "MACD negatif, histogram positif mais ralentit"
    return "bottom", min(0.3, recovery_ratio * 0.3), "MACD negatif, chute ralentit — possible stabilisation"


def analyze_macd(prices: list[float], ctx: MarketContext | None = None) -> IndicatorSignal | None:
    """MACD : le signe de la ligne donne la tendance, l'histogramme son accélération ou son essoufflement."""
    result = macd(prices)
    if result is None:
        return None
    macd_series, _signal_series, histogram_series = result
    if len(histogram_series) < 3:
        return None
    hist_now, hist_prev, hist_prev2 = histogram_series[-1], histogram_series[-2], histogram_series[-3]
    macd_now = macd_series[-1]
    rising = hist_now > hist_prev
    accelerating = (hist_now - hist_prev) > (hist_prev - hist_prev2)
    scale = at.macd_signal_scaling(ctx) if ctx else 50.0
    if macd_now > 0:
        signal, strength, desc = _uptrend(hist_now, rising, accelerating, scale)
    else:
        signal, strength, desc = _downtrend(hist_now, macd_now, rising, accelerating, scale)
    return IndicatorSignal("MACD", round(hist_now, 4), signal, round(min(strength, 0.95), 2), desc)


def _band_zone(position: float, ext_high: float, high: float, low: float, ext_low: float) -> Reading:
    if position > ext_high:
        strength = min(1.0, (position - ext_high) / max(1 - ext_high, 0.01) * 2)
        return "top", strength, "Prix au-dessus de la bande haute de Bollinger — surachat"
    if position > high:
        strength = 0.3 + 0.4 * (position - high) / max(ext_high - high, 0.01)
        return "bullish", strength, "Prix dans la partie haute des bandes de Bollinger"
    if position > low:
        return ("bullish" if position > 0.5 else "bearish"), 0.1, "Prix au milieu des bandes de Bollinger — neutre"
    if position > ext_low:
        strength = 0.3 + 0.4 * (low - position) / max(low - ext_low, 0.01)
        return "bearish", strength, "Prix dans la partie basse des bandes de Bollinger"
    strength = min(1.0, (ext_low - position) / max(ext_low, 0.01) * 2)
    return "bottom", strength, "Prix sous la bande basse de Bollinger — survente"


def analyze_bollinger(prices: list[float], ctx: MarketContext | None = None) -> IndicatorSignal | None:
    """Position du dernier prix entre les bandes de Bollinger, seuils selon le régime de volatilité."""
    bands = bollinger(prices)
    if bands is None:
        return None
    lower, _middle, upper = bands
    band_width = upper - lower
    if band_width <= 0:
        return None
    position = (prices[-1] - lower) / band_width
    if ctx:
        ext_high, high, low, ext_low = at.bollinger_thresholds(ctx)
    else:
        ext_high, high, low, ext_low = 0.95, 0.65, 0.35, 0.05
    signal, strength, desc = _band_zone(position, ext_high, high, low, ext_low)
    return IndicatorSignal("Bollinger Bands", round(position, 2), signal, round(strength, 2), desc)
