import numpy as np
from numpy.typing import NDArray

from app.core.finance_constants import annualization_days
from app.domains.analytics.core import AssetData
from app.domains.analytics.metrics import cvar_historical, downside_deviation, max_drawdown, var_historical
from app.domains.portfolio.models import AssetType

FloatArray = NDArray[np.float64]

MIN_RETURNS = 5


def _risk_inputs(
    asset_data: list[AssetData], total_value: float
) -> tuple[FloatArray, list[float], list[FloatArray], list[AssetType]]:
    weights: list[float] = []
    vols: list[float] = []
    returns_list: list[FloatArray] = []
    asset_types: list[AssetType] = []
    for d in asset_data:
        weights.append(d.get("current_value", 0) / total_value if total_value > 0 else 0)
        asset_types.append(d["asset"].asset_type)
        if d.get("is_stablecoin", False):
            vols.append(0.0)
            returns_list.append(np.array([]))
        else:
            vols.append(d.get("volatility", 0))
            returns_list.append(d.get("returns", np.array([])))
    return np.array(weights), vols, returns_list, asset_types


def _volatility_and_returns(
    weights: FloatArray, vols: list[float], returns_list: list[FloatArray], port_td: float
) -> tuple[float, FloatArray]:
    valid = [(i, r) for i, r in enumerate(returns_list) if len(r) >= MIN_RETURNS]
    if len(valid) < 2:
        return float(np.sum(weights * np.array(vols))), np.array([])
    min_len = min(len(r) for _, r in valid)
    aligned = np.array([r[-min_len:] for _, r in valid])
    cov_matrix = np.atleast_2d(np.cov(aligned))
    valid_weights = np.array([weights[i] for i, _ in valid])
    vw_sum = valid_weights.sum()
    if vw_sum > 0:
        valid_weights = valid_weights / vw_sum
    port_var = float(valid_weights @ cov_matrix @ valid_weights)
    port_vol = float(np.sqrt(port_var) * np.sqrt(port_td) * 100)
    return port_vol, aligned.T @ valid_weights


def _downside(port_returns: FloatArray, port_td: float) -> float:
    if len(port_returns) < MIN_RETURNS:
        return 0.0
    port_dd_dev = downside_deviation(port_returns, asset_type=None)
    neg = port_returns[port_returns < 0]
    if len(neg) > 0:
        port_dd_dev = float(np.sqrt(np.mean(neg**2)) * np.sqrt(port_td) * 100)
    return port_dd_dev


def _drawdown(port_returns: FloatArray, asset_data: list[AssetData], total_value: float) -> float:
    if len(port_returns) >= MIN_RETURNS:
        port_prices = np.exp(np.concatenate([[0], np.cumsum(port_returns)]))
        return max_drawdown(port_prices.tolist())
    portfolio_dd = 0.0
    if total_value > 0:
        for d in asset_data:
            portfolio_dd += d.get("current_value", 0) / total_value * d.get("max_drawdown", 0)
    return portfolio_dd


def portfolio_risk(asset_data: list[AssetData], total_value: float) -> dict[str, float]:
    """Risque du portefeuille : volatilité √(w'Σw) sur les rendements alignés, annualisée au nombre de jours
    de cotation moyen pondéré ; les stablecoins gardent leur poids mais ne portent aucun risque."""
    weights, vols, returns_list, asset_types = _risk_inputs(asset_data, total_value)
    td_per_asset = np.array([annualization_days(at) for at in asset_types], dtype=float)
    port_td = float(weights @ td_per_asset) if weights.sum() > 0 else 365
    port_vol, port_returns = _volatility_and_returns(weights, vols, returns_list, port_td)
    enough = len(port_returns) >= MIN_RETURNS
    var95 = var_historical(port_returns) if enough else 0.0
    cvar95 = cvar_historical(port_returns) if enough else 0.0
    port_ann_ret = float((np.exp(float(np.mean(port_returns)) * port_td) - 1) * 100) if enough else 0.0
    return {
        "volatility": round(port_vol, 1),
        "downside_dev": round(_downside(port_returns, port_td), 1),
        "annualized_return": round(port_ann_ret, 2),
        "max_drawdown": round(_drawdown(port_returns, asset_data, total_value), 2),
        "var_95_pct": round(var95, 2),
        "cvar_95_pct": round(cvar95, 2),
    }
