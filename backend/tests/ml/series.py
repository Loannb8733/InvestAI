from datetime import datetime, timedelta

import numpy as np

START = datetime(2025, 1, 1)
LENGTH = 240


def _walk(seed: int, drift: float, vol: float, start: float, length: int = LENGTH) -> list[float]:
    rng = np.random.RandomState(seed)
    returns = drift + vol * rng.standard_normal(length - 1)
    season = 0.01 * np.sin(np.arange(length - 1) / 9.0)
    path = start * np.exp(np.concatenate([[0.0], np.cumsum(returns + season)]))
    return [round(float(p), 6) for p in path]


def _range(seed: int, length: int = LENGTH) -> list[float]:
    rng = np.random.RandomState(seed)
    level = 100.0
    prices = []
    for shock in rng.standard_normal(length):
        level = level + 0.2 * (100.0 - level) + 1.5 * shock
        prices.append(round(level, 6))
    return prices


SERIES = {
    "bull": _walk(1, 0.003, 0.02, 30000.0),
    "bear": _walk(2, -0.003, 0.025, 2500.0),
    "range": _range(3),
    "calm": _walk(4, 0.0004, 0.008, 150.0),
}


def dates(count: int) -> list[datetime]:
    return [START + timedelta(days=i) for i in range(count)]


def with_spike(prices: list[float], factor: float) -> list[float]:
    return [*prices[:-1], round(prices[-1] * factor, 6)]
