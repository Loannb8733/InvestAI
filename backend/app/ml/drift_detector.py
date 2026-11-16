"""Dérive des données par l'indice de stabilité de population (PSI) entre une période de référence et la récente."""

import logging
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)

PSI_OK = 0.1
PSI_WARNING = 0.2


@dataclass
class DriftResult:
    """PSI par variable, PSI moyen et statut : ``ok``, ``warning`` (au-delà de 0,1) ou ``drift`` (de 0,2)."""

    symbol: str
    psi_values: dict[str, float] = field(default_factory=dict)
    overall_psi: float = 0.0
    drifted_features: list[str] = field(default_factory=list)
    status: str = "ok"


def _compute_psi(reference: np.ndarray, current: np.ndarray, n_bins: int = 10) -> float:
    """PSI sur des classes bornées par les quantiles de la référence ; 0 si une série a moins de ``n_bins`` points."""
    if len(reference) < n_bins or len(current) < n_bins:
        return 0.0
    edges = np.percentile(reference, np.linspace(0, 100, n_bins + 1))
    edges[0] = -np.inf
    edges[-1] = np.inf
    ref_counts = np.histogram(reference, bins=edges)[0].astype(float)
    cur_counts = np.histogram(current, bins=edges)[0].astype(float)
    eps = 1e-6
    ref_pct = ref_counts / ref_counts.sum() + eps
    cur_pct = cur_counts / cur_counts.sum() + eps
    psi = float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))
    return max(psi, 0.0)


def _extract_features(prices: np.ndarray) -> dict[str, np.ndarray]:
    features: dict[str, np.ndarray] = {}
    if len(prices) < 20:
        return features
    returns = np.diff(prices) / np.maximum(prices[:-1], 1e-10)
    features["returns"] = returns
    if len(returns) >= 10:
        features["volatility_10d"] = np.array([np.std(returns[max(0, i - 10) : i]) for i in range(10, len(returns))])
    if len(prices) >= 6:
        features["momentum_5d"] = (prices[5:] - prices[:-5]) / np.maximum(prices[:-5], 1e-10)
    features["log_price"] = np.log(np.maximum(prices, 1e-10))
    return features


def check_drift(
    reference_prices: np.ndarray,
    current_prices: np.ndarray,
    symbol: str = "",
    n_bins: int = 10,
) -> DriftResult:
    """Dérive des rendements, de la volatilité 10 jours, de l'élan 5 jours et du niveau de prix ; 20 cours minimum."""
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
        logger.info("Data drift warning for %s: overall_psi=%.4f", symbol, result.overall_psi)
    return result
