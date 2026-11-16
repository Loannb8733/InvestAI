import numpy as np

from app.ml.regime.types import PHASES


def normalize(votes: dict[str, float]) -> dict[str, float]:
    """Votes ramenés à une somme de 1, arrondis au millième ; un quart chacun sans vote."""
    total = sum(votes.values())
    if total <= 0:
        return dict.fromkeys(PHASES, 0.25)
    return {p: round(votes[p] / total, 3) for p in PHASES}


def rsi(prices: list[float], period: int = 14) -> float | None:
    """RSI de Wilder sur toute la série ; None sous ``period + 1`` prix, 100 sans aucune baisse."""
    if len(prices) < period + 1:
        return None
    all_deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    all_gains = [max(d, 0) for d in all_deltas]
    all_losses = [-min(d, 0) for d in all_deltas]
    avg_gain = sum(all_gains[:period]) / period
    avg_loss = sum(all_losses[:period]) / period
    for i in range(period, len(all_deltas)):
        avg_gain = (avg_gain * (period - 1) + all_gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + all_losses[i]) / period
    if avg_loss < 1e-10:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - 100 / (1 + rs))


def sma(prices: list[float], period: int) -> float | None:
    """Moyenne des ``period`` derniers prix ; None si la série est plus courte."""
    if len(prices) < period:
        return None
    return float(np.mean(prices[-period:]))


def ema(prices: list[float], period: int) -> list[float] | None:
    """Série complète de la moyenne exponentielle, amorcée par la moyenne des ``period`` premiers prix."""
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema_vals = [float(np.mean(prices[:period]))]
    for p in prices[period:]:
        ema_vals.append(ema_vals[-1] * (1 - k) + p * k)
    return ema_vals


def macd(prices: list[float]) -> tuple[list[float], list[float], list[float]] | None:
    """Séries MACD (12, 26), signal (9) et histogramme ; None sous 35 prix."""
    if len(prices) < 35:
        return None
    ema12 = ema(prices, 12)
    ema26 = ema(prices, 26)
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
    return macd_series, signal_series, histogram_series


def bollinger(prices: list[float], period: int = 20, num_std: float = 2.0) -> tuple[float, float, float] | None:
    """Bandes basse, médiane et haute au dernier prix ; None sous ``period`` prix."""
    if len(prices) < period:
        return None
    window = prices[-period:]
    middle = float(np.mean(window))
    std = float(np.std(window))
    return middle - num_std * std, middle, middle + num_std * std
