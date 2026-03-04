"""Data Drift detection using Population Stability Index (PSI).

Compares the distribution of recent feature data against a reference
(training) distribution.  A PSI > 0.2 signals significant drift and
suggests the ML models may need retraining.

Reference:
  PSI = sum( (actual_pct - expected_pct) * ln(actual_pct / expected_pct) )
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

logger = logging.getLogger(__name__)

# PSI thresholds (industry standard)
PSI_OK = 0.1  # No significant drift
PSI_WARNING = 0.2  # Moderate drift — monitor closely
# > 0.2 → significant drift — recommend retraining


@dataclass
class DriftResult:
    """Result of a drift check for one symbol."""

    symbol: str
    psi_values: Dict[str, float] = field(default_factory=dict)  # feature → PSI
    overall_psi: float = 0.0
    drifted_features: List[str] = field(default_factory=list)
    status: str = "ok"  # "ok" | "warning" | "drift"


def _compute_psi(
    reference: np.ndarray,
    current: np.ndarray,
    n_bins: int = 10,
) -> float:
    """Compute PSI between reference and current distributions.

    Args:
        reference: Array of values from the training/reference period.
        current: Array of values from the recent period.
        n_bins: Number of equal-width bins.

    Returns:
        PSI score (0 = identical distributions).
    """
    if len(reference) < n_bins or len(current) < n_bins:
        return 0.0

    # Use reference quantiles as bin edges for stability
    edges = np.percentile(reference, np.linspace(0, 100, n_bins + 1))
    edges[0] = -np.inf
    edges[-1] = np.inf

    ref_counts = np.histogram(reference, bins=edges)[0].astype(float)
    cur_counts = np.histogram(current, bins=edges)[0].astype(float)

    # Normalize to proportions (add small epsilon to avoid log(0))
    eps = 1e-6
    ref_pct = ref_counts / ref_counts.sum() + eps
    cur_pct = cur_counts / cur_counts.sum() + eps

    psi = float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))
    return max(psi, 0.0)  # PSI is non-negative by definition


def _extract_features(prices: np.ndarray) -> Dict[str, np.ndarray]:
    """Extract key features from a price series for drift monitoring.

    Returns a dict of feature_name → values array.
    """
    features: Dict[str, np.ndarray] = {}

    if len(prices) < 20:
        return features

    # Daily returns
    returns = np.diff(prices) / np.maximum(prices[:-1], 1e-10)
    features["returns"] = returns

    # Rolling volatility (10-day)
    if len(returns) >= 10:
        vol = np.array([np.std(returns[max(0, i - 10) : i]) for i in range(10, len(returns))])
        features["volatility_10d"] = vol

    # Price momentum (5-day % change)
    if len(prices) >= 6:
        momentum = (prices[5:] - prices[:-5]) / np.maximum(prices[:-5], 1e-10)
        features["momentum_5d"] = momentum

    # Log prices (level shift detection)
    log_prices = np.log(np.maximum(prices, 1e-10))
    features["log_price"] = log_prices

    return features


def check_drift(
    reference_prices: np.ndarray,
    current_prices: np.ndarray,
    symbol: str = "",
    n_bins: int = 10,
) -> DriftResult:
    """Check for data drift between reference and current price series.

    Args:
        reference_prices: Historical prices used for training (e.g. first 80%).
        current_prices: Recent prices to check for drift (e.g. last 30 days).
        symbol: Asset symbol for logging.
        n_bins: Number of bins for PSI computation.

    Returns:
        DriftResult with per-feature PSI scores and overall status.
    """
    result = DriftResult(symbol=symbol)

    ref_features = _extract_features(reference_prices)
    cur_features = _extract_features(current_prices)

    if not ref_features or not cur_features:
        return result

    psi_scores = []
    for feat_name in ref_features:
        if feat_name not in cur_features:
            continue
        psi = _compute_psi(ref_features[feat_name], cur_features[feat_name], n_bins)
        result.psi_values[feat_name] = round(psi, 4)
        psi_scores.append(psi)

        if psi > PSI_WARNING:
            result.drifted_features.append(feat_name)

    if psi_scores:
        result.overall_psi = round(float(np.mean(psi_scores)), 4)

    if result.overall_psi > PSI_WARNING:
        result.status = "drift"
        logger.warning(
            "DATA DRIFT detected for %s: overall_psi=%.4f drifted=%s",
            symbol,
            result.overall_psi,
            result.drifted_features,
        )
    elif result.overall_psi > PSI_OK:
        result.status = "warning"
        logger.info(
            "Data drift warning for %s: overall_psi=%.4f",
            symbol,
            result.overall_psi,
        )

    return result
