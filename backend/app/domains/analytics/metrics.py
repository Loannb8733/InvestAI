import numpy as np
from numpy.typing import NDArray

from app.core.finance_constants import RISK_FREE_RATE, annualization_days


def _year_days(asset_type: str | None) -> int:
    return annualization_days(asset_type) if asset_type else 365


def compute_returns(prices: list[float]) -> NDArray[np.float64]:
    """Rendements logarithmiques journaliers, prix nuls ou négatifs écartés."""
    arr = np.array(prices, dtype=float)
    if len(arr) < 2:
        return np.array([])
    arr = arr[arr > 0]
    if len(arr) < 2:
        return np.array([])
    return np.diff(np.log(arr))


def annualized_volatility(returns: NDArray[np.float64], asset_type: str | None = None) -> float:
    """Volatilité annualisée en %, sur 252 jours pour actions et ETF, 365 sinon."""
    if len(returns) < 2:
        return 0.0
    td = _year_days(asset_type)
    return float(np.std(returns, ddof=1) * np.sqrt(td) * 100)


def downside_deviation(returns: NDArray[np.float64], threshold: float = 0.0, asset_type: str | None = None) -> float:
    """Écart baissier annualisé en %, seuls les rendements sous le seuil comptent."""
    if len(returns) < 2:
        return 0.0
    neg = returns[returns < threshold] - threshold
    if len(neg) == 0:
        return 0.0
    td = _year_days(asset_type)
    return float(np.sqrt(np.mean(neg**2)) * np.sqrt(td) * 100)


def max_drawdown(prices: list[float]) -> float:
    """Pire repli depuis un sommet, en % négatif."""
    if len(prices) < 2:
        return 0.0
    arr = np.array(prices, dtype=float)
    peak = np.maximum.accumulate(arr)
    dd = (arr - peak) / np.where(peak > 0, peak, 1)
    return float(np.min(dd) * 100)


def daily_return_pct(prices: list[float]) -> float:
    if len(prices) < 2:
        return 0.0
    p0, p1 = prices[-2], prices[-1]
    if p0 <= 0:
        return 0.0
    return (p1 - p0) / p0 * 100


def var_historical(returns: NDArray[np.float64], confidence: float = 0.95) -> float:
    """VaR historique journalière en % de perte positive (3.2 = 3,2 % de perte) ; nulle sous cinq points."""
    if len(returns) < 5:
        return 0.0
    q = np.percentile(returns, (1 - confidence) * 100)
    return float(-q * 100)


def cvar_historical(returns: NDArray[np.float64], confidence: float = 0.95) -> float:
    """Expected Shortfall journalière en % de perte positive : moyenne des rendements sous le quantile de la VaR."""
    if len(returns) < 5:
        return 0.0
    q = np.percentile(returns, (1 - confidence) * 100)
    tail = returns[returns <= q]
    if len(tail) == 0:
        return float(-q * 100)
    return float(-np.mean(tail) * 100)


def sharpe(return_pct: float, volatility: float, risk_free_rate: float = RISK_FREE_RATE) -> float:
    """Ratio de Sharpe sur rendement et volatilité annualisés en %, taux sans risque en décimal."""
    if volatility == 0:
        return 0.0
    excess = return_pct - (risk_free_rate * 100)
    return round(excess / volatility, 2)


def sortino(return_pct: float, downside_dev: float, risk_free_rate: float = RISK_FREE_RATE) -> float:
    if downside_dev == 0:
        return 0.0
    excess = return_pct - (risk_free_rate * 100)
    return round(excess / downside_dev, 2)


def calmar(return_pct: float, max_dd: float) -> float:
    """Rendement annualisé rapporté à la valeur absolue du pire repli."""
    if max_dd == 0:
        return 0.0
    return round(return_pct / abs(max_dd), 2)


def annualized_return(returns: NDArray[np.float64], asset_type: str | None = None) -> float:
    """Rendement annualisé discret en %, exp(moyenne journalière * jours) - 1, pour éviter les -328 % du log."""
    if len(returns) < 2:
        return 0.0
    td = _year_days(asset_type)
    mean_daily = float(np.mean(returns))
    return np.float64((np.exp(mean_daily * td) - 1) * 100)
