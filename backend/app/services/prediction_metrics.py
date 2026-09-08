"""Prediction accuracy / reliability metric helpers, extracted from the
prediction god-module.

``PredictionMetricsMixin`` is mixed into ``PredictionService``; the methods are
pure computations (support/resistance, walk-forward accuracy, hit-rate,
reliability, lightweight skill) called via ``self`` and resolved through the MRO,
so behaviour is unchanged.
"""

import logging
import math
from typing import Dict, List, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class PredictionMetricsMixin:
    @staticmethod
    def _compute_support_resistance(prices: List[float], current_price: float) -> Tuple[float, float]:
        """Compute support/resistance using pivot points + price clustering.

        1. Classic pivot points (H, L, C of recent window)
        2. K-means clustering of local extrema to find key price levels
        3. Pick nearest support below and resistance above current price
        """
        recent = prices[-min(60, len(prices)) :]
        arr = np.array(recent, dtype=float)

        # --- Pivot points ---
        high = float(np.max(arr))
        low = float(np.min(arr))
        close = float(arr[-1])
        pivot = (high + low + close) / 3
        s1 = 2 * pivot - high
        s2 = pivot - (high - low)
        r1 = 2 * pivot - low
        r2 = pivot + (high - low)

        # --- Local extrema detection ---
        levels = [s1, s2, r1, r2, pivot]
        # Find local minima and maxima (±2 neighbors)
        for i in range(2, len(arr) - 2):
            if arr[i] <= arr[i - 1] and arr[i] <= arr[i + 1] and arr[i] <= arr[i - 2] and arr[i] <= arr[i + 2]:
                levels.append(float(arr[i]))
            elif arr[i] >= arr[i - 1] and arr[i] >= arr[i + 1] and arr[i] >= arr[i - 2] and arr[i] >= arr[i + 2]:
                levels.append(float(arr[i]))

        # --- Cluster nearby levels (within 1.5% of each other) ---
        levels.sort()
        clusters: List[List[float]] = []
        for lv in levels:
            if clusters and abs(lv - np.mean(clusters[-1])) / max(np.mean(clusters[-1]), 1e-10) < 0.015:
                clusters[-1].append(lv)
            else:
                clusters.append([lv])

        # Use cluster centroids as key levels
        key_levels = [float(np.mean(c)) for c in clusters]

        # P18: Add psychological round number levels
        # Determine the scale of the price to pick relevant round numbers
        if current_price >= 10_000:
            round_steps = [10_000, 5_000, 1_000]
        elif current_price >= 1_000:
            round_steps = [1_000, 500, 100]
        elif current_price >= 100:
            round_steps = [100, 50, 10]
        elif current_price >= 10:
            round_steps = [10, 5, 1]
        elif current_price >= 1:
            round_steps = [1, 0.5, 0.1]
        else:
            # Micro-price assets (PEPE, SHIB, etc.)
            round_steps = [0.01, 0.001, 0.0001]

        # Add round numbers within ±15% of current price
        zone_low = current_price * 0.85
        zone_high = current_price * 1.15
        for step in round_steps:
            # Find the first round number above zone_low
            start = math.ceil(zone_low / step) * step
            level = start
            while level <= zone_high:
                # Snap existing pivots to round number if within 3%
                snapped = False
                for i, kl in enumerate(key_levels):
                    if abs(kl - level) / max(level, 1e-10) < 0.03:
                        key_levels[i] = level  # snap to round
                        snapped = True
                        break
                if not snapped:
                    key_levels.append(level)
                level += step

        # Deduplicate close levels after adding round numbers
        key_levels = sorted(set(key_levels))

        # Find nearest support (below current) and resistance (above current)
        supports = [lv for lv in key_levels if lv < current_price]
        resistances = [lv for lv in key_levels if lv > current_price]

        support = max(supports) if supports else current_price * 0.95
        resistance = min(resistances) if resistances else current_price * 1.05

        return support, resistance

    # -- Reliability from ensemble results (instant, no backtest) --

    @staticmethod
    def _compute_reliability_from_ensemble(
        models_detail: List[Dict], ensemble_trend: str
    ) -> Tuple[float, float, int, bool]:
        """Compute reliability from the ensemble's own MAPE and model consensus.

        Uses the already-computed backtest MAPE from each model (available in
        models_detail) plus directional agreement between models.

        Returns (skill_score, hit_rate_proxy, n_models, significant).
        """
        if not models_detail:
            return 50.0, 50.0, 0, False

        n_models = len(models_detail)

        # 1. Skill score: weighted MAPE → skill
        # Lower MAPE = better model. MAPE < 2% is excellent, > 20% is poor.
        mapes = []
        weights = []
        for m in models_detail:
            mape = m.get("mape")
            w = m.get("weight_pct", 10)
            if mape is not None and mape > 0:
                mapes.append(mape)
                weights.append(w)

        if mapes:
            # Weighted average MAPE
            total_w = sum(weights)
            if total_w > 0:
                avg_mape = sum(m * w for m, w in zip(mapes, weights)) / total_w
            else:
                avg_mape = float(np.mean(mapes))

            # Convert MAPE to skill: MAPE=1% → 90, MAPE=5% → 70, MAPE=15% → 40
            # Formula: skill = 100 - mape * 4 (clamped 15-95)
            skill_score = float(np.clip(100.0 - avg_mape * 4, 15, 95))
        else:
            skill_score = 50.0

        # 2. Hit rate proxy: model consensus on direction
        # "neutral" is compatible with both bullish and bearish (not opposing)
        trends = [m.get("trend", "neutral") for m in models_detail]
        compatible = 0
        opposing = 0
        for t in trends:
            if t == ensemble_trend:
                compatible += 1  # exact match
            elif t == "neutral":
                compatible += 0.5  # neutral is partially compatible
            else:
                opposing += 1  # opposite direction
        consensus_ratio = compatible / max(n_models, 1)

        # Map consensus: high agreement → high hit rate
        # All agree → 85, half agree → 60, all disagree → 30
        hit_rate = float(np.clip(30 + consensus_ratio * 65, 30, 85))

        # Significance: significant if >= 4 models and no strong opposition
        significant = n_models >= 4 and opposing <= 1

        return round(skill_score, 1), round(hit_rate, 1), n_models, significant

    # -- Lightweight accuracy metrics (no expensive backtest) --

    @staticmethod
    def _compute_lightweight_skill(prices: List[float]) -> float:
        """Estimate model skill from price predictability metrics.

        Uses autocorrelation and trend consistency as a proxy for how well
        ML models can predict this asset. Fast (no model re-runs).
        Returns 0-100 where 50 = baseline.
        """
        if not prices or len(prices) < 60:
            return 50.0
        try:
            arr = np.array(prices[-365:], dtype=float)
            returns = np.diff(arr) / np.maximum(arr[:-1], 1e-10)

            # 1. Autocorrelation of returns (lag 1-7)
            # High autocorrelation = more predictable
            n = len(returns)
            mean_r = float(np.mean(returns))
            var_r = float(np.var(returns))
            if var_r < 1e-15:
                return 50.0
            autocorr_sum = 0.0
            for lag in range(1, min(8, n)):
                cov = float(np.mean((returns[lag:] - mean_r) * (returns[:-lag] - mean_r)))
                autocorr_sum += abs(cov / var_r)
            avg_autocorr = autocorr_sum / 7

            # 2. Trend consistency: % of 7-day windows with consistent direction
            consistent = 0
            total_windows = 0
            for i in range(0, n - 7, 7):
                window = returns[i : i + 7]
                pos = np.sum(window > 0)
                if pos >= 5 or pos <= 2:  # 5+ up or 5+ down = consistent
                    consistent += 1
                total_windows += 1
            trend_consistency = consistent / max(total_windows, 1)

            # 3. Combine: autocorrelation (40%) + trend consistency (60%)
            # Scale to 30-75 range (realistic for crypto)
            raw = avg_autocorr * 0.4 + trend_consistency * 0.6
            score = 30 + raw * 60  # maps [0,1] -> [30,90]
            return round(float(np.clip(score, 20, 80)), 1)
        except Exception:
            return 50.0

    @staticmethod
    def _compute_lightweight_hit_rate(
        prices: List[float],
    ) -> Tuple[float, int, bool]:
        """Estimate directional hit rate from trend persistence.

        Measures how often the 7-day direction matches the prior 7-day
        direction (proxy for whether trend-following models would succeed).
        Returns (hit_rate_pct, n_samples, significant).
        """
        if not prices or len(prices) < 60:
            return 50.0, 0, False
        try:
            arr = np.array(prices[-365:], dtype=float)
            hits = 0
            total = 0
            for i in range(14, len(arr), 7):
                prev_dir = arr[i - 7] < arr[i - 14]  # prior 7d went up?
                curr_dir = arr[i] > arr[i - 7]  # this 7d went up?
                # A simple predictor would predict "same direction continues"
                if prev_dir == curr_dir:
                    hits += 1
                total += 1

            if total < 3:
                return 50.0, total, False

            hit_rate = (hits / total) * 100

            # Significance: binomial test approximation
            significant = False
            if total >= 15:
                z = (hits - total * 0.5) / max((total * 0.25) ** 0.5, 1e-10)
                significant = z > 1.645  # one-sided 5%

            return round(hit_rate, 1), total, significant
        except Exception:
            return 50.0, 0, False
