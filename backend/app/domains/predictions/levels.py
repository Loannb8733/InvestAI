import math
from typing import Any

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]

MIN_HISTORY = 60


def _pivot_levels(arr: FloatArray) -> list[float]:
    high = float(np.max(arr))
    low = float(np.min(arr))
    close = float(arr[-1])
    pivot = (high + low + close) / 3
    s1 = 2 * pivot - high
    s2 = pivot - (high - low)
    r1 = 2 * pivot - low
    r2 = pivot + (high - low)
    return [s1, s2, r1, r2, pivot]


def _local_extrema(arr: FloatArray) -> list[float]:
    extrema: list[float] = []
    for i in range(2, len(arr) - 2):
        if (arr[i] <= arr[i - 1] and arr[i] <= arr[i + 1] and arr[i] <= arr[i - 2] and arr[i] <= arr[i + 2]) or (
            arr[i] >= arr[i - 1] and arr[i] >= arr[i + 1] and arr[i] >= arr[i - 2] and arr[i] >= arr[i + 2]
        ):
            extrema.append(float(arr[i]))
    return extrema


def _cluster_centroids(levels: list[float]) -> list[float]:
    levels.sort()
    clusters: list[list[float]] = []
    for lv in levels:
        if clusters and abs(lv - np.mean(clusters[-1])) / max(np.mean(clusters[-1]), 1e-10) < 0.015:
            clusters[-1].append(lv)
        else:
            clusters.append([lv])
    return [float(np.mean(c)) for c in clusters]


def _round_steps(current_price: float) -> list[float]:
    if current_price >= 10_000:
        return [10_000, 5_000, 1_000]
    if current_price >= 1_000:
        return [1_000, 500, 100]
    if current_price >= 100:
        return [100, 50, 10]
    if current_price >= 10:
        return [10, 5, 1]
    if current_price >= 1:
        return [1, 0.5, 0.1]
    return [0.01, 0.001, 0.0001]


def _add_round_levels(key_levels: list[float], current_price: float) -> None:
    zone_low = current_price * 0.85
    zone_high = current_price * 1.15
    for step in _round_steps(current_price):
        level = math.ceil(zone_low / step) * step
        while level <= zone_high:
            snapped = False
            for i, kl in enumerate(key_levels):
                if abs(kl - level) / max(level, 1e-10) < 0.03:
                    key_levels[i] = level
                    snapped = True
                    break
            if not snapped:
                key_levels.append(level)
            level += step


def support_resistance(prices: list[float], current_price: float) -> tuple[float, float]:
    """Support et résistance les plus proches du cours : points pivots et extrema locaux des 60 derniers points
    regroupés à 1,5 %, plus les nombres ronds à ±15 % (un niveau à moins de 3 % d'un nombre rond s'y aligne) ;
    à défaut ±5 % du cours."""
    recent = prices[-min(60, len(prices)) :]
    arr = np.array(recent, dtype=float)
    levels = _pivot_levels(arr) + _local_extrema(arr)
    key_levels = _cluster_centroids(levels)
    _add_round_levels(key_levels, current_price)
    key_levels = sorted(set(key_levels))

    supports = [lv for lv in key_levels if lv < current_price]
    resistances = [lv for lv in key_levels if lv > current_price]
    support = max(supports) if supports else current_price * 0.95
    resistance = min(resistances) if resistances else current_price * 1.05
    return support, resistance


def _skill_from_mape(models_detail: list[dict[str, Any]]) -> float:
    mapes = []
    weights = []
    for m in models_detail:
        mape = m.get("mape")
        w = m.get("weight_pct", 10)
        if mape is not None and mape > 0:
            mapes.append(mape)
            weights.append(w)
    if not mapes:
        return 50.0
    total_w = sum(weights)
    if total_w > 0:
        avg_mape = sum(m * w for m, w in zip(mapes, weights, strict=False)) / total_w
    else:
        avg_mape = float(np.mean(mapes))
    return float(np.clip(100.0 - avg_mape * 4, 15, 95))


def _direction_votes(models_detail: list[dict[str, Any]], ensemble_trend: str) -> tuple[float, int]:
    compatible = 0.0
    opposing = 0
    for t in [m.get("trend", "neutral") for m in models_detail]:
        if t == ensemble_trend:
            compatible += 1
        elif t == "neutral":
            compatible += 0.5
        else:
            opposing += 1
    return compatible, opposing


def reliability_from_ensemble(
    models_detail: list[dict[str, Any]], ensemble_trend: str
) -> tuple[float, float, int, bool]:
    """(score de compétence, taux de réussite estimé, nombre de modèles, significatif) sans backtest : la compétence
    vaut 100 - 4 * MAPE pondéré (bornée 15-95), le taux suit l'accord des modèles sur la direction (30-85, un modèle
    neutre compte pour moitié), significatif dès quatre modèles avec au plus un opposé."""
    if not models_detail:
        return 50.0, 50.0, 0, False

    n_models = len(models_detail)
    skill_score = _skill_from_mape(models_detail)
    compatible, opposing = _direction_votes(models_detail, ensemble_trend)
    consensus_ratio = compatible / max(n_models, 1)
    hit_rate = float(np.clip(30 + consensus_ratio * 65, 30, 85))
    significant = n_models >= 4 and opposing <= 1
    return round(skill_score, 1), round(hit_rate, 1), n_models, significant


def _avg_autocorrelation(returns: FloatArray, mean_r: float, var_r: float) -> float:
    n = len(returns)
    autocorr_sum = 0.0
    for lag in range(1, min(8, n)):
        cov = float(np.mean((returns[lag:] - mean_r) * (returns[:-lag] - mean_r)))
        autocorr_sum += abs(cov / var_r)
    return autocorr_sum / 7


def _trend_consistency(returns: FloatArray) -> float:
    consistent = 0
    total_windows = 0
    for i in range(0, len(returns) - 7, 7):
        pos = np.sum(returns[i : i + 7] > 0)
        if pos >= 5 or pos <= 2:
            consistent += 1
        total_windows += 1
    return consistent / max(total_windows, 1)


def lightweight_skill(prices: list[float]) -> float:
    """Prévisibilité estimée (20-80, 50 = neutre) d'après l'autocorrélation des rendements (40 %) et la constance
    des tendances hebdomadaires (60 %), sans relancer de modèle."""
    if not prices or len(prices) < MIN_HISTORY:
        return 50.0
    try:
        arr = np.array(prices[-365:], dtype=float)
        returns = np.diff(arr) / np.maximum(arr[:-1], 1e-10)
        mean_r = float(np.mean(returns))
        var_r = float(np.var(returns))
        if var_r < 1e-15:
            return 50.0
        raw = _avg_autocorrelation(returns, mean_r, var_r) * 0.4 + _trend_consistency(returns) * 0.6
        score = 30 + raw * 60
        return round(float(np.clip(score, 20, 80)), 1)
    except Exception:  # noqa: BLE001
        return 50.0


def _persistence_hits(arr: FloatArray) -> tuple[int, int]:
    hits = 0
    total = 0
    for i in range(14, len(arr), 7):
        prev_dir = arr[i - 7] < arr[i - 14]
        curr_dir = arr[i] > arr[i - 7]
        if prev_dir == curr_dir:
            hits += 1
        total += 1
    return hits, total


def lightweight_hit_rate(prices: list[float]) -> tuple[float, int, bool]:
    """(taux de réussite en %, échantillons, significatif) d'un prédicteur « la direction des 7 derniers jours
    continue », significatif au seuil unilatéral de 5 % à partir de 15 échantillons."""
    if not prices or len(prices) < MIN_HISTORY:
        return 50.0, 0, False
    try:
        hits, total = _persistence_hits(np.array(prices[-365:], dtype=float))
        if total < 3:
            return 50.0, total, False
        hit_rate = (hits / total) * 100
        significant = False
        if total >= 15:
            z = (hits - total * 0.5) / max((total * 0.25) ** 0.5, 1e-10)
            significant = z > 1.645
        return round(hit_rate, 1), total, significant
    except Exception:  # noqa: BLE001
        return 50.0, 0, False
