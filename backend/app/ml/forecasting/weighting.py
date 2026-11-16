import logging
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from app.ml.forecasting.types import Candidate, ForecastResult, ModelRunner

logger = logging.getLogger(__name__)

WINDOW = 14
MAX_OFFSET = 180
MIN_TRAIN = 30
RECENCY_DECAY = 0.85
MIN_WEIGHT = 0.05
TARGET_COVERAGE = 0.95


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


def _mape(predicted: list[float], actual: list[float]) -> float | None:
    errs = [abs(predicted[j] - actual[j]) / max(actual[j], 1e-10) for j in range(min(len(predicted), len(actual)))]
    return float(np.mean(errs)) * 100 if errs else None


def _offsets(n: int) -> list[int]:
    return [offset for offset in range(WINDOW, min(n // 2, MAX_OFFSET) + 1, WINDOW) if n - offset >= MIN_TRAIN]


def _backtest_mape(
    run: ModelRunner, name: str, prices: list[float], dates: list[datetime], cut: int, actual: list[float]
) -> tuple[ForecastResult | None, float | None]:
    try:
        bt = run(name, prices[:-cut], dates[:-cut], len(actual))
    except Exception as e:  # noqa: BLE001
        logger.warning("Backtest window of %s failed (window excluded): %s", name, e)
        return None, None
    return bt, _mape(bt.prices[: len(actual)], actual)


def _window_scores(
    prices: list[float],
    dates: list[datetime],
    candidates: list[Candidate],
    offset: int,
    run: ModelRunner,
    coverage: _Coverage,
) -> list[float | None]:
    actual = prices[-offset : -offset + WINDOW] if offset > WINDOW else prices[-offset:]
    scores: list[float | None] = []
    for name, _ in candidates:
        bt, mape = _backtest_mape(run, name, prices, dates, offset, actual)
        if bt is not None and mape is not None:
            for j in range(min(len(bt.confidence_low), len(bt.confidence_high), len(actual))):
                coverage.total += 1
                if bt.confidence_low[j] <= actual[j] <= bt.confidence_high[j]:
                    coverage.covered += 1
        scores.append(None if mape is None else 1.0 / max(mape, 0.1))
    return scores


def _recency_mean(per_window: list[list[float | None]], n_cand: int) -> list[float | None]:
    """Moyenne des scores d'un modèle sur ses fenêtres réussies, les plus récentes pesant plus ; None sans aucune."""
    n_windows = len(per_window)
    recency = [RECENCY_DECAY ** (n_windows - 1 - i) for i in range(n_windows)]
    means: list[float | None] = []
    for ci_idx in range(n_cand):
        pairs = [(per_window[w][ci_idx], recency[w]) for w in range(n_windows) if per_window[w][ci_idx] is not None]
        total = sum(weight for _, weight in pairs)
        means.append(sum(score * weight for score, weight in pairs if score is not None) / total if pairs else None)
    return means


def _floored(scores: list[float | None]) -> list[float]:
    """Poids normalisés avec un plancher de 5 % ; nul pour un modèle sans aucune fenêtre réussie."""
    valid = [s for s in scores if s is not None]
    if not valid:
        return [0.0] * len(scores)
    total = sum(valid)
    weights = [0.0 if s is None else (1.0 / len(valid) if total == 0 else max(s / total, MIN_WEIGHT)) for s in scores]
    total_w = sum(weights)
    return [w / total_w for w in weights]


def single_window_weights(
    prices: list[float], dates: list[datetime], candidates: list[Candidate], run: ModelRunner, split: int = 7
) -> tuple[list[float], list[float | None]]:
    """Poids inverses de l'erreur sur une seule fenêtre de test, pour un historique court ; égaux sous 14 points.

    Un modèle dont le backtest échoue reçoit un poids nul et une erreur None.
    """
    n_cand = len(candidates)
    if len(prices) < 14 or split < 1:
        return [1.0 / n_cand] * n_cand, [None] * n_cand
    split = min(split, len(prices) // 2)
    actual = prices[-split:]
    mapes = [_backtest_mape(run, name, prices, dates, split, actual)[1] for name, _ in candidates]
    mapes = [None if m is None else max(m, 0.1) for m in mapes]
    return _floored([None if m is None else 1.0 / m for m in mapes]), mapes


def compute_weights(
    prices: list[float], dates: list[datetime], candidates: list[Candidate], run: ModelRunner
) -> tuple[list[float], float, list[float | None]]:
    """Poids par backtest glissant (fenêtres de 14 jours, les récentes pèsent plus, plancher de 5 %).

    Une fenêtre en échec est exclue de la moyenne du modèle ; un modèle sans aucune fenêtre réussie reçoit un poids
    nul et une erreur None. Renvoie aussi le facteur de calibrage de l'intervalle d'après la couverture observée,
    et l'erreur moyenne (MAPE) hors échantillon de chaque modèle.
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
    per_model_mape = [None if score is None else 1.0 / score for score in accumulated]
    return _floored(accumulated), coverage.factor(), per_model_mape


def quick_mape(prices: list[float], result: ForecastResult) -> float:
    """Écart entre la variation récente sur 7 points et la variation prévue, à défaut d'erreur de backtest."""
    if not prices or not result.prices:
        return 0.0
    base = prices[-min(7, len(prices))]
    recent_change = (prices[-1] - base) / max(base, 1e-10) * 100
    predicted_change = (result.prices[-1] - prices[-1]) / max(prices[-1], 1e-10) * 100
    return abs(recent_change - predicted_change)
