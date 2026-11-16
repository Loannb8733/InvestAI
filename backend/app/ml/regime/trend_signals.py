import numpy as np

from app.ml import adaptive_thresholds as at
from app.ml.market_context import MarketContext
from app.ml.regime.indicators import sma
from app.ml.regime.oscillators import Reading
from app.ml.regime.types import IndicatorSignal


def _averages(prices: list[float]) -> tuple[float, float, str] | None:
    short, long = sma(prices, 20), sma(prices, 50)
    if short is not None and long is not None:
        return short, long, "MA Cross (SMA20/SMA50)"
    short, long = sma(prices, 7), sma(prices, 20)
    if short is None or long is None:
        return None
    return short, long, "MA Cross (SMA7/SMA20)"


def _previous_averages(prices: list[float], short: float, long: float) -> tuple[float | None, float | None]:
    if len(prices) > 55:
        return sma(prices[:-5], 20), sma(prices[:-5], 50)
    if len(prices) > 25:
        return sma(prices[:-3], 7), sma(prices[:-3], 20)
    return short, long


def _cross_zone(diff_pct: float, significance: float, crossed_up: bool, crossed_down: bool) -> Reading:
    if crossed_up:
        return "bottom", 0.8, "Golden cross — la MA courte croise la MA longue a la hausse"
    if crossed_down:
        return "top", 0.8, "Death cross — la MA courte croise la MA longue a la baisse"
    if diff_pct > significance:
        strength = min(0.9, diff_pct / (significance * 3))
        return "bullish", strength, f"MA courte au-dessus de la MA longue (+{diff_pct:.1f}%)"
    if diff_pct > 0:
        return "bullish", 0.3, "MA courte legerement au-dessus de la MA longue"
    if diff_pct > -significance:
        return "bearish", 0.3, "MA courte legerement sous la MA longue"
    strength = min(0.9, abs(diff_pct) / (significance * 3))
    return "bearish", strength, f"MA courte sous la MA longue ({diff_pct:.1f}%)"


def analyze_ma_cross(prices: list[float], ctx: MarketContext | None = None) -> IndicatorSignal | None:
    """Écart et croisement récent des moyennes 20/50 jours (7/20 sur un historique court)."""
    averages = _averages(prices)
    if averages is None:
        return None
    short, long, label = averages
    diff_pct = (short - long) / max(abs(long), 1e-10) * 100
    significance = at.ma_cross_significance(ctx) if ctx else 3.0
    old_short, old_long = _previous_averages(prices, short, long)
    crossed_up = bool(old_short and old_long and old_short < old_long and short > long)
    crossed_down = bool(old_short and old_long and old_short > old_long and short < long)
    signal, strength, desc = _cross_zone(diff_pct, significance, crossed_up, crossed_down)
    return IndicatorSignal(label, round(diff_pct, 2), signal, round(strength, 2), desc)


def _momentum_zone(roc: float, prev_roc: float, thresholds: tuple[float, float, float, float]) -> Reading:
    strong_bull, bull, bear, strong_bear = thresholds
    if roc > strong_bull and roc < prev_roc:
        strength = min(0.9, roc / (strong_bull * 3))
        return "top", strength, f"Momentum positif mais en ralentissement ({roc:+.1f}%) — essoufflement"
    if roc > bull:
        return "bullish", min(0.9, roc / (strong_bull * 2)), f"Momentum haussier ({roc:+.1f}%)"
    if roc > bear:
        return ("bullish" if roc > 0 else "bearish"), 0.2, f"Momentum neutre ({roc:+.1f}%)"
    if roc > strong_bear:
        return "bearish", min(0.9, abs(roc) / (abs(strong_bear) * 2)), f"Momentum baissier ({roc:+.1f}%)"
    if roc > prev_roc:
        strength = min(0.9, abs(roc) / (abs(strong_bear) * 3))
        return "bottom", strength, f"Momentum tres negatif mais en amelioration ({roc:+.1f}%) — possible creux"
    strength = min(0.9, abs(roc) / (abs(strong_bear) * 2))
    return "bearish", strength, f"Momentum fortement baissier ({roc:+.1f}%)"


def analyze_momentum(prices: list[float], ctx: MarketContext | None = None) -> IndicatorSignal | None:
    """Variation sur 14 jours (7 sur un historique court) et son accélération par rapport à la veille."""
    period = 14 if len(prices) >= 20 else 7
    if len(prices) < period + 5:
        return None
    roc = (prices[-1] - prices[-period - 1]) / max(abs(prices[-period - 1]), 1e-10) * 100
    if len(prices) > period + 2:
        prev_roc = (prices[-2] - prices[-period - 2]) / max(abs(prices[-period - 2]), 1e-10) * 100
    else:
        prev_roc = roc
    thresholds = at.momentum_thresholds(ctx) if ctx else (10.0, 3.0, -3.0, -10.0)
    signal, strength, desc = _momentum_zone(roc, prev_roc, thresholds)
    return IndicatorSignal(f"Momentum {period}j", round(roc, 1), signal, round(strength, 2), desc)


def _calm_direction(prices: list[float], price_position: float) -> tuple[str, float]:
    trend_up = prices[-1] > float(np.mean(prices[-min(30, len(prices)) :]))
    if trend_up and price_position > 0.6:
        return "bullish", 0.10
    if not trend_up and price_position < 0.4:
        return "bearish", 0.10
    return ("bearish", 0.03) if not trend_up else ("bullish", 0.03)


def analyze_volatility(prices: list[float], ctx: MarketContext | None = None) -> IndicatorSignal | None:
    """Volatilité annualisée sur 14 jours croisée avec la position du prix dans son range."""
    if len(prices) < 15:
        return None
    returns = [(prices[i] - prices[i - 1]) / max(abs(prices[i - 1]), 1e-10) for i in range(-14, 0)]
    vol = float(np.std(returns)) * np.sqrt(ctx.annualization_factor if ctx else 365) * 100
    extreme_vol, high_vol = at.volatility_regime_thresholds(ctx) if ctx else (80.0, 50.0)
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
        signal, strength = _calm_direction(prices, price_position)
        desc = f"Volatilite moderee ({vol:.0f}%) — marche stable"
    return IndicatorSignal("Volatilite 14j", round(vol, 0), signal, round(strength, 2), desc)


def analyze_fear_greed(
    fg: int, btc_dominance: float | None = None, ctx: MarketContext | None = None
) -> IndicatorSignal:
    """Fear & Greed lu contre des seuils ajustés à la volatilité ; force pondérée par la dominance du BTC."""
    ext_greed, greed, fear, ext_fear = at.fear_greed_thresholds(ctx) if ctx else (75.0, 55.0, 45.0, 25.0)
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
    if btc_dominance is not None and btc_dominance > 0:
        strength = strength * (btc_dominance / 100.0)
    return IndicatorSignal("Fear & Greed", float(fg), signal, round(strength, 2), desc)


def _vix_zone(vix: float) -> Reading:
    if vix > 40:
        return (
            "bottom",
            min(1.0, (vix - 40) / 30),
            f"VIX extreme ({vix:.0f}) — panique sur les marches actions, capitulation possible",
        )
    if vix > 30:
        return (
            "bearish",
            0.5 + 0.3 * (vix - 30) / 10,
            f"VIX tres eleve ({vix:.0f}) — forte crainte sur les marches TradFi",
        )
    if vix > 25:
        return "bearish", 0.3 + 0.2 * (vix - 25) / 5, f"VIX eleve ({vix:.0f}) — stress accru sur les marches actions"
    if vix > 20:
        return "bearish", 0.2, f"VIX moderement eleve ({vix:.0f}) — prudence sur les marches"
    if vix > 15:
        return "bullish", 0.2, f"VIX normal ({vix:.0f}) — conditions de marche stables"
    if vix > 12:
        return "bullish", 0.3, f"VIX bas ({vix:.0f}) — faible volatilite, marche confiant"
    return "top", 0.3 + 0.2 * max(0, 12 - vix) / 5, f"VIX tres bas ({vix:.0f}) — complaisance, risque de retournement"


def analyze_vix(vix: float, ctx: MarketContext | None = None) -> IndicatorSignal | None:
    """VIX comme sentiment des marchés actions : panique au-dessus de 40, complaisance sous 12 ; None si nul."""
    if vix <= 0:
        return None
    signal, strength, desc = _vix_zone(vix)
    return IndicatorSignal("VIX (TradFi)", vix, signal, round(strength, 2), desc)
