from dataclasses import dataclass
from datetime import datetime

import numpy as np

from app.ml.forecasting.types import Candidate, ForecastResult, ModelRunner

WINDOW = 14
MAX_OFFSET = 180
MIN_TRAIN = 30
RECENCY_DECAY = 0.85
MIN_WEIGHT = 0.05
TARGET_COVERAGE = 0.95
FAILED_MAPE = 50.0


@dataclass
class _Coverage:
    covered: int = 0
    total: int = 0

    def factor(self) -> float:
        if self.total == 0:
            return 1.0
        rate = self.covered / self.total
        factor = 1.0
        if rate < 0.90:
            factor = TARGET_COVERAGE / max(rate, 0.01)
        elif rate > 0.98:
            factor = TARGET_COVERAGE / rate
        return max(0.5, min(2.0, factor))


def _mape(predicted: list[float], actual: list[float]) -> float:
    errs = [abs(predicted[j] - actual[j]) / max(actual[j], 1e-10) for j in range(min(len(predicted), len(actual)))]
    return float(np.mean(errs)) * 100 if errs else FAILED_MAPE


def _offsets(n: int) -> list[int]:
    return [offset for offset in range(WINDOW, min(n // 2, MAX_OFFSET) + 1, WINDOW) if n - offset >= MIN_TRAIN]


def _window_scores(
    prices: list[float],
    dates: list[datetime],
    candidates: list[Candidate],
    offset: int,
    run: ModelRunner,
    coverage: _Coverage,
) -> list[float]:
    actual = prices[-offset : -offset + WINDOW] if offset > WINDOW else prices[-offset:]
    horizon = min(WINDOW, len(actual))
    scores = []
    for name, _ in candidates:
        try:
            bt = run(name, prices[:-offset], dates[:-offset], horizon)
            mape = _mape(bt.prices[:horizon], actual)
            for j in range(min(len(bt.confidence_low), len(bt.confidence_high), len(actual))):
                coverage.total += 1
                if bt.confidence_low[j] <= actual[j] <= bt.confidence_high[j]:
                    coverage.covered += 1
        except Exception:  # noqa: BLE001
            mape = FAILED_MAPE
        scores.append(1.0 / max(mape, 0.1))
    return scores


def _recency_mean(per_window: list[list[float]], n_cand: int) -> list[float]:
    n_windows = len(per_window)
    window_weights = [RECENCY_DECAY ** (n_windows - 1 - i) for i in range(n_windows)]
    ww_total = sum(window_weights)
    window_weights = [w / ww_total for w in window_weights]
    accumulated = [0.0] * n_cand
    for w_idx in range(n_windows):
        for ci_idx in range(n_cand):
            accumulated[ci_idx] += per_window[w_idx][ci_idx] * window_weights[w_idx]
    return accumulated


def _floored(accumulated: list[float]) -> list[float]:
    n_cand = len(accumulated)
    total = sum(accumulated)
    weights = [1.0 / n_cand] * n_cand if total == 0 else [w / total for w in accumulated]
    weights = [max(w, MIN_WEIGHT) for w in weights]
    total_w = sum(weights)
    return [w / total_w for w in weights]


def single_window_weights(
    prices: list[float], dates: list[datetime], candidates: list[Candidate], run: ModelRunner, split: int = 7
) -> tuple[list[float], list[float]]:
    """Poids inverses de l'erreur sur une seule fenêtre de test, pour un historique court ; égaux sous 14 points."""
    n_cand = len(candidates)
    if len(prices) < 14 or split < 1:
        return [1.0 / n_cand] * n_cand, [FAILED_MAPE] * n_cand
    split = min(split, len(prices) // 2)
    actual = prices[-split:]
    mapes = []
    for name, _ in candidates:
        try:
            mape = _mape(run(name, prices[:-split], dates[:-split], split).prices[:split], actual)
        except Exception:  # noqa: BLE001
            mape = FAILED_MAPE
        mapes.append(max(mape, 0.1))
    inv = [1.0 / m for m in mapes]
    total = sum(inv)
    return [w / total for w in inv], mapes


def compute_weights(
    prices: list[float], dates: list[datetime], candidates: list[Candidate], run: ModelRunner
) -> tuple[list[float], float, list[float]]:
    """Poids par backtest glissant (fenêtres de 14 jours, les récentes pèsent plus, plancher de 5 %).

    Renvoie aussi le facteur de calibrage de l'intervalle d'après la couverture observée, et l'erreur
    moyenne (MAPE) hors échantillon de chaque modèle.
    """
    n = len(prices)
    if n < 28:
        weights, mapes = single_window_weights(prices, dates, candidates, run, split=min(7, n // 2))
        return weights, 1.0, mapes
    offsets = _offsets(n)
    if not offsets:
        weights, mapes = single_window_weights(prices, dates, candidates, run, split=7)
        return weights, 1.0, mapes
    coverage = _Coverage()
    per_window = [_window_scores(prices, dates, candidates, offset, run, coverage) for offset in offsets]
    accumulated = _recency_mean(per_window, len(candidates))
    per_model_mape = [(1.0 / inv) if inv > 0 else FAILED_MAPE for inv in accumulated]
    return _floored(accumulated), coverage.factor(), per_model_mape


def quick_mape(prices: list[float], result: ForecastResult) -> float:
    """Écart entre la variation récente sur 7 points et la variation prévue, à défaut d'erreur de backtest."""
    if not prices or not result.prices:
        return 0.0
    base = prices[-min(7, len(prices))]
    recent_change = (prices[-1] - base) / max(base, 1e-10) * 100
    predicted_change = (result.prices[-1] - prices[-1]) / max(prices[-1], 1e-10) * 100
    return abs(recent_change - predicted_change)
