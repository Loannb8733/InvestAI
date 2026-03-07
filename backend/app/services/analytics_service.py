"""Advanced analytics service for portfolio analysis."""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import httpx
import numpy as np
from scipy import optimize as sp_optimize
from scipy.stats import spearmanr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml import adaptive_thresholds as adaptive_th
from app.ml.historical_data import HistoricalDataFetcher
from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction, TransactionType
from app.services.price_service import PriceService
from app.tasks.history_cache import get_cached_history

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configurable risk-free rate (annualized, as decimal e.g. 0.03 = 3%)
# In a production system this would be fetched from an API (ECB ESTER, OAT 10Y)
# ---------------------------------------------------------------------------
RISK_FREE_RATE = 0.035  # 3.5% — approximate EUR risk-free Jan 2026

# Cache TTL for historical data (seconds) — shared across all endpoint calls
_HISTORY_CACHE_TTL = 300  # 5 minutes


@dataclass
class AssetPerformance:
    """Performance metrics for a single asset."""

    symbol: str
    name: str
    asset_type: str
    current_value: float
    total_invested: float
    gain_loss: float
    gain_loss_percent: float
    weight: float
    daily_return: float
    volatility_30d: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float


@dataclass
class PortfolioAnalytics:
    """Comprehensive portfolio analytics."""

    total_value: float
    total_invested: float
    total_gain_loss: float
    total_gain_loss_percent: float

    # Risk metrics
    portfolio_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    var_95: float
    cvar_95: float  # Conditional VaR / Expected Shortfall

    # Diversification
    diversification_score: float
    concentration_risk: float
    asset_count: int

    # Allocation
    allocation_by_type: Dict[str, float]
    allocation_by_asset: Dict[str, float]

    # Performance
    assets: List[AssetPerformance]
    best_performer: Optional[str]
    worst_performer: Optional[str]

    # Human-readable VaR explanation (P12)
    var_95_description: str = ""

    # Contextual interpretations for ratios
    interpretations: Dict[str, str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.interpretations is None:
            self.interpretations = {}


@dataclass
class CorrelationData:
    """Correlation matrix data."""

    symbols: List[str]
    matrix: List[List[float]]
    strongly_correlated: List[Tuple[str, str, float]]
    negatively_correlated: List[Tuple[str, str, float]]


@dataclass
class MonteCarloResult:
    """Monte Carlo simulation result."""

    percentiles: Dict[str, float]  # p5, p25, p50, p75, p95
    expected_return: float
    prob_positive: float  # probability of positive return
    prob_loss_10: float  # probability of >10% loss
    prob_ruin: float  # probability of portfolio reaching zero
    simulations: int
    horizon_days: int


@dataclass
class RebalanceOrder:
    """Single rebalancing order."""

    symbol: str
    name: str
    asset_type: str
    current_weight: float
    target_weight: float
    diff_weight: float
    current_value: float
    target_value: float
    diff_value: float  # positive = buy, negative = sell
    action: str  # "buy" | "sell" | "hold"


@dataclass
class OptimizationResult:
    """Portfolio optimization (MPT) result."""

    weights: Dict[str, float]
    expected_return: float
    expected_volatility: float
    sharpe_ratio: float


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _compute_returns(prices: List[float]) -> np.ndarray:
    """Compute daily log returns from price series."""
    arr = np.array(prices, dtype=float)
    if len(arr) < 2:
        return np.array([])
    arr = arr[arr > 0]
    if len(arr) < 2:
        return np.array([])
    return np.diff(np.log(arr))


def _trading_days(asset_type) -> int:
    """Return annualization factor: 252 for stocks/ETF, 365 for crypto/other."""
    if isinstance(asset_type, str):
        at = asset_type.lower()
    else:
        at = asset_type.value.lower() if hasattr(asset_type, "value") else str(asset_type).lower()
    if at in ("stock", "etf"):
        return 252
    return 365


def _annualized_volatility(returns: np.ndarray, asset_type=None) -> float:
    """Annualized volatility (%) from daily log returns."""
    if len(returns) < 2:
        return 0.0
    td = _trading_days(asset_type) if asset_type else 365
    return float(np.std(returns, ddof=1) * np.sqrt(td) * 100)


def _downside_deviation(returns: np.ndarray, threshold: float = 0.0, asset_type=None) -> float:
    """Annualized downside deviation (%) — only negative returns count."""
    if len(returns) < 2:
        return 0.0
    neg = returns[returns < threshold] - threshold
    if len(neg) == 0:
        return 0.0
    td = _trading_days(asset_type) if asset_type else 365
    return float(np.sqrt(np.mean(neg**2)) * np.sqrt(td) * 100)


def _max_drawdown(prices: List[float]) -> float:
    """Max drawdown (%) from price series. Returns negative number."""
    if len(prices) < 2:
        return 0.0
    arr = np.array(prices, dtype=float)
    peak = np.maximum.accumulate(arr)
    dd = (arr - peak) / np.where(peak > 0, peak, 1)
    return float(np.min(dd) * 100)


def _daily_return_pct(prices: List[float]) -> float:
    """Latest daily return %."""
    if len(prices) < 2:
        return 0.0
    p0, p1 = prices[-2], prices[-1]
    if p0 <= 0:
        return 0.0
    return (p1 - p0) / p0 * 100


def _var_historical(returns: np.ndarray, confidence: float = 0.95) -> float:
    """Historical VaR as positive % (loss). E.g. 3.2 means 3.2% daily loss."""
    if len(returns) < 5:
        return 0.0
    q = np.percentile(returns, (1 - confidence) * 100)
    return float(-q * 100)


def _var_parametric(returns: np.ndarray, confidence: float = 0.95) -> float:
    """Parametric (Gaussian) VaR as positive % daily loss.

    Assumes returns ~ N(mu, sigma). VaR = -(mu + z * sigma).
    More stable than historical VaR with small samples.
    """
    if len(returns) < 5:
        return 0.0
    from scipy.stats import norm

    mu = float(np.mean(returns))
    sigma = float(np.std(returns, ddof=1))
    z = norm.ppf(1 - confidence)  # negative, e.g. -1.645 for 95%
    var = -(mu + z * sigma)
    return float(max(0.0, var * 100))


def _cvar_historical(returns: np.ndarray, confidence: float = 0.95) -> float:
    """Conditional VaR (Expected Shortfall) as positive %."""
    if len(returns) < 5:
        return 0.0
    q = np.percentile(returns, (1 - confidence) * 100)
    tail = returns[returns <= q]
    if len(tail) == 0:
        return float(-q * 100)
    return float(-np.mean(tail) * 100)


def _sharpe(return_pct: float, volatility: float, risk_free_rate: float = RISK_FREE_RATE) -> float:
    """Sharpe ratio. return_pct and volatility in % (annualized)."""
    if volatility == 0:
        return 0.0
    excess = return_pct - (risk_free_rate * 100)
    return round(excess / volatility, 2)


def _sortino(return_pct: float, downside_dev: float, risk_free_rate: float = RISK_FREE_RATE) -> float:
    """Sortino ratio."""
    if downside_dev == 0:
        return 0.0
    excess = return_pct - (risk_free_rate * 100)
    return round(excess / downside_dev, 2)


def _calmar(return_pct: float, max_dd: float) -> float:
    """Calmar ratio = annualized return / |max drawdown|."""
    if max_dd == 0:
        return 0.0
    return round(return_pct / abs(max_dd), 2)


def _annualized_return(returns: np.ndarray, asset_type=None) -> float:
    """Annualized return (%) from daily log returns.

    Converts continuous (log) return to discrete % for human-readable display:
    discrete_annual = (exp(mean_daily * td) - 1) * 100
    This avoids misleading values like -328% for assets that dropped ~96%.
    """
    if len(returns) < 2:
        return 0.0
    td = _trading_days(asset_type) if asset_type else 365
    mean_daily = float(np.mean(returns))
    return (np.exp(mean_daily * td) - 1) * 100


def _xirr(cashflows: List[Tuple[datetime, float]], guess: float = 0.1) -> Optional[float]:
    """
    Compute XIRR (Extended Internal Rate of Return) from a list of (date, amount).
    Positive amount = outflow (investment), negative = inflow (value/withdrawal).
    Returns annualized rate as decimal (0.12 = 12%).
    """
    if len(cashflows) < 2:
        return None

    dates = [cf[0] for cf in cashflows]
    amounts = [cf[1] for cf in cashflows]
    d0 = min(dates)

    def npv(rate: float) -> float:
        return sum(amt / (1.0 + rate) ** ((d - d0).days / 365.25) for d, amt in zip(dates, amounts))

    try:
        result = sp_optimize.brentq(npv, -0.99, 10.0, maxiter=200)
        return float(result)
    except (ValueError, RuntimeError, TypeError, OverflowError):
        try:
            result = sp_optimize.newton(npv, guess, maxiter=200)
            return float(result)
        except (ValueError, RuntimeError, TypeError, OverflowError):
            return None


class AnalyticsService:
    """Service for advanced portfolio analytics."""

    # ECB Data Portal API — deposit facility rate (risk-free proxy for EUR)
    _ECB_DFR_URL = (
        "https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR.LEV" "?lastNObservations=1&format=jsondata"
    )
    _ECB_RATE_TTL = 86400  # 24h cache

    _MAX_CACHE_ENTRIES = 200

    def __init__(self):
        self.price_service = PriceService()
        # In-memory cache: key -> (timestamp, dates, prices) — bounded with LRU eviction
        self._history_cache: Dict[str, Tuple[float, List[datetime], List[float]]] = {}
        self._fetch_locks: Dict[str, asyncio.Lock] = {}  # Per-symbol locks
        # ECB risk-free rate cache: (timestamp, rate_decimal)
        self._ecb_rate_cache: Optional[Tuple[float, float]] = None

    def _get_fetch_lock(self, symbol: str) -> asyncio.Lock:
        """Get or create a per-symbol lock to allow parallel fetches for different symbols."""
        if symbol not in self._fetch_locks:
            self._fetch_locks[symbol] = asyncio.Lock()
        return self._fetch_locks[symbol]

    def _cache_put(self, key: str, value: Tuple[float, List[datetime], List[float]]) -> None:
        """Insert into cache with bounded size — evict oldest entry if full."""
        if len(self._history_cache) >= self._MAX_CACHE_ENTRIES:
            oldest_key = min(self._history_cache, key=lambda k: self._history_cache[k][0])
            del self._history_cache[oldest_key]
        self._history_cache[key] = value

    async def _fetch_risk_free_rate(self) -> float:
        """Fetch ECB deposit facility rate with 24h in-memory cache.

        Returns the rate as a decimal (e.g. 0.035 for 3.5%).
        Falls back to RISK_FREE_RATE constant on failure.
        """
        now = time.time()
        if self._ecb_rate_cache:
            ts, rate = self._ecb_rate_cache
            if now - ts < self._ECB_RATE_TTL:
                return rate

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self._ECB_DFR_URL)
                resp.raise_for_status()
                data = resp.json()

            # Navigate SDMX-JSON structure to extract the rate value
            datasets = data.get("dataSets", [{}])
            if datasets:
                series = datasets[0].get("series", {})
                # Single series: key "0:0:0:0:0:0:0"
                for key, series_data in series.items():
                    observations = series_data.get("observations", {})
                    if observations:
                        # Get the last observation value
                        last_obs_key = max(observations.keys(), key=int)
                        rate_pct = float(observations[last_obs_key][0])
                        rate_decimal = rate_pct / 100.0
                        self._ecb_rate_cache = (now, rate_decimal)
                        logger.info("ECB deposit facility rate: %.2f%%", rate_pct)
                        return rate_decimal

        except Exception as e:
            logger.warning("Failed to fetch ECB risk-free rate: %s — using fallback %.1f%%", e, RISK_FREE_RATE * 100)

        return RISK_FREE_RATE

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    async def _fetch_history(self, symbol: str, asset_type, days: int = 60) -> Tuple[List[float], List[float]]:
        """Fetch historical prices. Returns (timestamps, prices).
        Priority: in-memory cache → Redis cache → live API (with rate limiting)."""
        fetch_days = 90
        cache_key = f"{symbol}_{fetch_days}"
        now = time.time()

        # 1. In-memory cache (fast, shared across endpoints in same process)
        if cache_key in self._history_cache:
            ts, dates, prices = self._history_cache[cache_key]
            if now - ts < _HISTORY_CACHE_TTL:
                if days < fetch_days and len(dates) > days:
                    return [d.timestamp() for d in dates[-days:]], prices[-days:]
                return [d.timestamp() for d in dates], prices

        # 2. Redis cache (filled by Celery task every 30 min)
        dates, prices = get_cached_history(symbol, days=fetch_days)
        if dates and prices:
            self._cache_put(cache_key, (now, dates, prices))
            if days < fetch_days and len(dates) > days:
                return [d.timestamp() for d in dates[-days:]], prices[-days:]
            return [d.timestamp() for d in dates], prices

        # 3. Live API fallback (per-symbol lock so different symbols fetch in parallel)
        async with self._get_fetch_lock(symbol):
            # Double-check after lock
            if cache_key in self._history_cache:
                ts, dates, prices = self._history_cache[cache_key]
                if now - ts < _HISTORY_CACHE_TTL:
                    if days < fetch_days and len(dates) > days:
                        return [d.timestamp() for d in dates[-days:]], prices[-days:]
                    return [d.timestamp() for d in dates], prices

            fetcher = HistoricalDataFetcher()
            try:
                at = asset_type.value if isinstance(asset_type, AssetType) else asset_type
                dates, prices = await fetcher.get_history(symbol, at, days=fetch_days)
                if dates and prices:
                    self._cache_put(cache_key, (time.time(), dates, prices))
                await asyncio.sleep(1.5)
                if days < fetch_days and len(dates) > days:
                    return [d.timestamp() for d in dates[-days:]], prices[-days:]
                return [d.timestamp() for d in dates], prices
            except Exception as e:
                logger.warning("History fetch failed for %s: %s", symbol, e)
                return [], []
            finally:
                await fetcher.close()

    async def _get_asset_price(self, asset: Asset) -> float:
        """Get current price for an asset."""
        try:
            price_data = None
            if asset.asset_type == AssetType.CRYPTO:
                price_data = await self.price_service.get_crypto_price(asset.symbol)
            elif asset.asset_type in [AssetType.STOCK, AssetType.ETF]:
                price_data = await self.price_service.get_stock_price(asset.symbol)
            if price_data and "price" in price_data:
                return float(price_data["price"])
            return float(asset.avg_buy_price)
        except Exception as e:
            logger.warning("Price fetch failed for %s: %s", asset.symbol, e)
            return float(asset.avg_buy_price)

    # ------------------------------------------------------------------
    # Shared: fetch user assets (filtered, deduplicated)
    # ------------------------------------------------------------------

    async def _get_user_assets(
        self,
        db: AsyncSession,
        user_id: str,
        portfolio_id: Optional[str] = None,
        exclude_stablecoins: bool = True,
        min_value: float = 0.10,
    ) -> List[Asset]:
        """Get user assets with consistent filtering (no dust, no stablecoins by default)."""
        if portfolio_id:
            result = await db.execute(
                select(Asset).where(
                    Asset.portfolio_id == portfolio_id,
                    Asset.quantity > 0,
                )
            )
        else:
            result = await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
            portfolios = result.scalars().all()
            pids = [p.id for p in portfolios]
            if not pids:
                return []
            result = await db.execute(
                select(Asset).where(
                    Asset.portfolio_id.in_(pids),
                    Asset.quantity > 0,
                )
            )

        assets = result.scalars().all()

        filtered = []
        for a in assets:
            # Filter stablecoins
            if exclude_stablecoins and PriceService.is_stablecoin(a.symbol):
                continue
            # Filter dust by estimated value
            est_value = float(a.quantity) * float(a.avg_buy_price) if a.avg_buy_price else 0
            if est_value < min_value:
                continue
            filtered.append(a)
        return filtered

    # ------------------------------------------------------------------
    # Core: build asset-level metrics
    # ------------------------------------------------------------------

    async def _build_asset_data(self, assets, days: int = 60) -> list:
        """Fetch history first (gives current price too), then compute per-asset metrics.

        Note: Stablecoins are included for valuation but flagged so their
        near-zero volatility doesn't distort portfolio risk metrics.
        """
        asset_data = []
        for asset in assets:
            _, hist_prices = await self._fetch_history(asset.symbol, asset.asset_type, days=days)

            # Use last historical price as current price (avoids extra API call)
            if hist_prices and hist_prices[-1] > 0:
                price = hist_prices[-1]
            else:
                price = float(asset.avg_buy_price)

            current_value = float(asset.quantity) * price if price else 0
            total_invested = float(asset.quantity) * float(asset.avg_buy_price)
            gain_loss = current_value - total_invested
            gain_loss_pct = (gain_loss / total_invested * 100) if total_invested > 0 else 0

            rets = _compute_returns(hist_prices)
            at = asset.asset_type
            vol = _annualized_volatility(rets, asset_type=at)
            dd_dev = _downside_deviation(rets, asset_type=at)
            ann_ret = _annualized_return(rets, asset_type=at)
            dd = _max_drawdown(hist_prices)
            dr = _daily_return_pct(hist_prices)

            is_stable = PriceService.is_stablecoin(asset.symbol)

            # Skip dust positions (value < $0.10)
            if current_value < 0.10:
                continue

            asset_data.append(
                {
                    "asset": asset,
                    "price": price,
                    "current_value": current_value,
                    "total_invested": total_invested,
                    "gain_loss": gain_loss,
                    "gain_loss_percent": gain_loss_pct,
                    "hist_prices": hist_prices,
                    "returns": rets,
                    "volatility": vol,
                    "downside_dev": dd_dev,
                    "annualized_return": ann_ret,
                    "max_drawdown": dd,
                    "daily_return": dr,
                    "is_stablecoin": is_stable,
                }
            )
        return asset_data

    def _build_portfolio_metrics(self, asset_data_list: list, total_value: float) -> dict:
        """Compute portfolio-level risk metrics from asset data."""
        # --- weights (exclude stablecoins from risk computations) ---
        weights = []
        vols = []
        returns_list = []
        asset_types = []
        for d in asset_data_list:
            w = d.get("current_value", 0) / total_value if total_value > 0 else 0
            # Stablecoins: keep weight for allocation but zero out risk contribution
            if d.get("is_stablecoin", False):
                weights.append(w)
                vols.append(0.0)
                returns_list.append(np.array([]))  # empty → excluded from covariance
                asset_types.append(d["asset"].asset_type)
            else:
                weights.append(w)
                vols.append(d.get("volatility", 0))
                returns_list.append(d.get("returns", np.array([])))
                asset_types.append(d["asset"].asset_type)

        weights = np.array(weights)

        # Weighted-average trading days for the portfolio
        td_per_asset = np.array([_trading_days(at) for at in asset_types], dtype=float)
        port_td = float(weights @ td_per_asset) if weights.sum() > 0 else 365

        # --- portfolio volatility (matrix form: σ_p = √(w'Σw)) ---
        # Align returns to same length
        valid = [(i, r) for i, r in enumerate(returns_list) if len(r) >= 5]
        if len(valid) >= 2:
            min_len = min(len(r) for _, r in valid)
            aligned = np.array([r[-min_len:] for _, r in valid])
            cov_matrix = np.atleast_2d(np.cov(aligned))  # covariance matrix
            valid_weights = np.array([weights[i] for i, _ in valid])
            # Renormalize valid weights
            vw_sum = valid_weights.sum()
            if vw_sum > 0:
                valid_weights = valid_weights / vw_sum
            port_var = float(valid_weights @ cov_matrix @ valid_weights)
            port_vol = float(np.sqrt(port_var) * np.sqrt(port_td) * 100)

            # Portfolio returns for VaR/CVaR
            port_returns = aligned.T @ valid_weights  # daily portfolio returns
        else:
            # Fallback to weighted average
            port_vol = float(np.sum(weights * np.array(vols)))
            port_returns = np.array([])

        # --- Downside deviation (portfolio level) ---
        if len(port_returns) >= 5:
            port_dd_dev = _downside_deviation(port_returns, asset_type=None)
            # Override with portfolio trading days
            neg = port_returns[port_returns < 0]
            if len(neg) > 0:
                port_dd_dev = float(np.sqrt(np.mean(neg**2)) * np.sqrt(port_td) * 100)
        else:
            port_dd_dev = 0.0

        # --- VaR / CVaR ---
        var95 = _var_historical(port_returns) if len(port_returns) >= 5 else 0.0
        cvar95 = _cvar_historical(port_returns) if len(port_returns) >= 5 else 0.0

        # --- Max Drawdown (portfolio level) ---
        if len(port_returns) >= 5:
            # Reconstruct portfolio price series from returns
            port_prices = np.exp(np.concatenate([[0], np.cumsum(port_returns)]))
            portfolio_dd = _max_drawdown(port_prices.tolist())
        else:
            portfolio_dd = 0.0
            if total_value > 0:
                for d in asset_data_list:
                    w = d.get("current_value", 0) / total_value
                    portfolio_dd += w * d.get("max_drawdown", 0)

        # --- Annualized portfolio return from daily returns (geometric) ---
        if len(port_returns) >= 5:
            mean_daily = float(np.mean(port_returns))
            port_ann_ret = float((np.exp(mean_daily * port_td) - 1) * 100)
        else:
            port_ann_ret = 0.0

        return {
            "volatility": round(port_vol, 1),
            "downside_dev": round(port_dd_dev, 1),
            "annualized_return": round(port_ann_ret, 2),
            "max_drawdown": round(portfolio_dd, 2),
            "var_95_pct": round(var95, 2),
            "cvar_95_pct": round(cvar95, 2),
        }

    # ------------------------------------------------------------------
    # Main analytics methods
    # ------------------------------------------------------------------

    async def get_portfolio_analytics(
        self,
        db: AsyncSession,
        portfolio_id: str,
        currency: str = "EUR",
        days: int = 60,
    ) -> PortfolioAnalytics:
        """Get comprehensive analytics for a portfolio."""

        result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id == portfolio_id,
                Asset.quantity > 0,
            )
        )
        assets = result.scalars().all()
        if not assets:
            return self._empty_analytics()

        risk_free_rate = await self._fetch_risk_free_rate()
        asset_data = await self._build_asset_data(assets, days=days)
        return self._assemble_analytics(asset_data, risk_free_rate=risk_free_rate)

    async def get_user_analytics(
        self,
        db: AsyncSession,
        user_id: str,
        currency: str = "EUR",
        days: int = 60,
    ) -> PortfolioAnalytics:
        """Get analytics across all user portfolios."""

        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == user_id,
            )
        )
        portfolios = result.scalars().all()
        if not portfolios:
            return self._empty_analytics()

        portfolio_ids = [p.id for p in portfolios]
        result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id.in_(portfolio_ids),
                Asset.quantity > 0,
            )
        )
        assets = result.scalars().all()
        if not assets:
            return self._empty_analytics()

        risk_free_rate = await self._fetch_risk_free_rate()
        asset_data = await self._build_asset_data(assets, days=days)

        # Aggregate by symbol
        aggregated: Dict[str, dict] = {}
        for data in asset_data:
            sym = data["asset"].symbol
            if sym in aggregated:
                aggregated[sym]["current_value"] += data["current_value"]
                aggregated[sym]["total_invested"] += data["total_invested"]
            else:
                aggregated[sym] = dict(data)

        for sym, d in aggregated.items():
            d["gain_loss"] = d["current_value"] - d["total_invested"]
            d["gain_loss_percent"] = (d["gain_loss"] / d["total_invested"] * 100) if d["total_invested"] > 0 else 0

        return self._assemble_analytics(list(aggregated.values()), risk_free_rate=risk_free_rate)

    @staticmethod
    def _build_interpretations(
        sharpe: float,
        sortino: float,
        calmar: float,
        volatility: float,
        max_dd: float,
        asset_data: list,
    ) -> Dict[str, str]:
        """Build contextual, human-readable interpretations for portfolio ratios."""
        interp: Dict[str, str] = {}

        # Detect actual data depth (min data points across non-stablecoin assets)
        data_lengths = [
            len(d.get("returns", []))
            for d in asset_data
            if not d.get("is_stablecoin", False) and len(d.get("returns", [])) > 0
        ]
        min_days = min(data_lengths) if data_lengths else 0

        # ── Short history warning ──
        if min_days < 20:
            short_msg = (
                "Donnée non significative (échantillon < 20 jours). "
                "Les ratios nécessitent au moins 30 jours d'historique pour être fiables."
            )
            interp["sharpe"] = short_msg
            interp["sortino"] = short_msg
            interp["calmar"] = short_msg
            interp["global"] = "Historique trop court pour des conclusions fiables."
            return interp

        # ── Sharpe ──
        if sharpe > 3:
            interp["sharpe"] = (
                "Performance atypique (Sharpe > 3) : probablement liée à une volatilité "
                "extrême ou un pump récent. Ne pas extrapoler."
            )
        elif sharpe >= 2:
            interp["sharpe"] = "Excellent rapport rendement/risque. Vérifiez que la période est représentative."
        elif sharpe >= 1:
            interp["sharpe"] = "Bon ratio — le portefeuille rémunère correctement le risque pris."
        elif sharpe >= 0:
            interp["sharpe"] = "Rendement positif mais faible par rapport au risque. Marge d'optimisation possible."
        else:
            interp["sharpe"] = "Rendement inférieur au taux sans risque. Le portefeuille ne compense pas sa volatilité."

        # ── Sortino vs Sharpe ──
        if sortino > sharpe + 0.5 and sortino > 0:
            interp["sortino"] = (
                "Sortino nettement supérieur au Sharpe : votre volatilité est principalement "
                "positive (hausses). C'est un signe de force — le Sortino est plus pertinent "
                "en crypto car il ne punit pas les gains explosifs."
            )
        elif sortino > 0:
            interp["sortino"] = (
                "Ratio positif. Le Sortino est le ratio de référence en crypto car il "
                "ne pénalise que la volatilité baissière, pas les hausses brutales."
            )
        else:
            interp["sortino"] = "Sortino négatif : les pertes dominent. Le risque baissier dépasse le rendement."

        # ── Calmar ──
        if calmar > 2:
            interp["calmar"] = "Excellente récupération : le rendement compense largement le pire drawdown subi."
        elif calmar > 1:
            interp["calmar"] = "Le rendement annualisé dépasse le max drawdown. Bonne résilience."
        elif calmar > 0:
            interp["calmar"] = "Rendement positif mais inférieur au max drawdown. Récupération lente."
        else:
            interp["calmar"] = "Le portefeuille n'a pas récupéré de sa plus grosse perte."

        return interp

    def _assemble_analytics(self, asset_data: list, risk_free_rate: float = RISK_FREE_RATE) -> PortfolioAnalytics:
        """From a list of asset dicts, compute all portfolio-level analytics."""
        # Separate stablecoins from real assets
        real_assets = [d for d in asset_data if not d.get("is_stablecoin", False)]

        total_value_dec = sum((Decimal(str(d["current_value"])) for d in real_assets), Decimal("0"))
        total_invested_dec = sum((Decimal(str(d["total_invested"])) for d in real_assets), Decimal("0"))
        total_gl_dec = total_value_dec - total_invested_dec
        total_value = float(total_value_dec)
        total_invested = float(total_invested_dec)
        total_gl = float(total_gl_dec)
        total_gl_pct = float(total_gl_dec / total_invested_dec * 100) if total_invested_dec > 0 else 0

        # Weights & allocation
        allocation_by_type: Dict[str, float] = {}
        allocation_by_asset: Dict[str, float] = {}
        for d in real_assets:
            a = d["asset"]
            w = (d["current_value"] / total_value * 100) if total_value > 0 else 0
            d["weight"] = w
            at = a.asset_type.value
            allocation_by_type[at] = allocation_by_type.get(at, 0) + w
            allocation_by_asset[a.symbol] = w

        # Portfolio-level risk (only real assets)
        pm = self._build_portfolio_metrics(real_assets, total_value)

        vol = pm["volatility"]
        dd_dev = pm["downside_dev"]
        ann_ret = pm["annualized_return"]
        max_dd = pm["max_drawdown"]
        var95_pct = pm["var_95_pct"]
        cvar95_pct = pm["cvar_95_pct"]

        sharpe = _sharpe(ann_ret, vol, risk_free_rate)
        sortino = _sortino(ann_ret, dd_dev, risk_free_rate)
        calmar = _calmar(ann_ret, max_dd)

        var_95_eur = round(total_value * var95_pct / 100, 2)
        cvar_95_eur = round(total_value * cvar95_pct / 100, 2)
        var_95_desc = (
            (f"Perte journalière maximale attendue (95%): {var_95_eur:.2f} EUR " f"({var95_pct:.2f}% du portefeuille)")
            if var95_pct > 0
            else ""
        )

        concentration = self._hhi(allocation_by_asset)
        diversification = self._diversification_score(len(real_assets), len(allocation_by_type), concentration)

        # Build per-asset performances (exclude stablecoins)
        perfs = []
        for d in real_assets:
            a = d["asset"]
            v = d["volatility"]
            dd_d = d["downside_dev"]
            ann_r = d.get("annualized_return", 0.0)
            perfs.append(
                AssetPerformance(
                    symbol=a.symbol,
                    name=a.name or a.symbol,
                    asset_type=a.asset_type.value,
                    current_value=d["current_value"],
                    total_invested=d["total_invested"],
                    gain_loss=d["gain_loss"],
                    gain_loss_percent=d["gain_loss_percent"],
                    weight=d["weight"],
                    daily_return=round(d["daily_return"], 2),
                    volatility_30d=round(v, 1),
                    sharpe_ratio=_sharpe(ann_r, v, risk_free_rate),
                    sortino_ratio=_sortino(ann_r, dd_d, risk_free_rate),
                    max_drawdown=round(d["max_drawdown"], 2),
                )
            )

        sorted_p = sorted(perfs, key=lambda x: x.gain_loss_percent, reverse=True)
        best = sorted_p[0].symbol if sorted_p else None
        worst = sorted_p[-1].symbol if len(sorted_p) > 1 else None

        # ── Contextual interpretations ──
        interpretations = self._build_interpretations(
            sharpe=sharpe,
            sortino=sortino,
            calmar=calmar,
            volatility=vol,
            max_dd=max_dd,
            asset_data=real_assets,
        )

        return PortfolioAnalytics(
            total_value=total_value,
            total_invested=total_invested,
            total_gain_loss=total_gl,
            total_gain_loss_percent=total_gl_pct,
            portfolio_volatility=vol,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_drawdown=max_dd,
            var_95=var_95_eur,
            cvar_95=cvar_95_eur,
            var_95_description=var_95_desc,
            diversification_score=diversification,
            concentration_risk=concentration,
            asset_count=len(real_assets),
            allocation_by_type=allocation_by_type,
            allocation_by_asset=allocation_by_asset,
            assets=perfs,
            best_performer=best,
            worst_performer=worst,
            interpretations=interpretations,
        )

    # ------------------------------------------------------------------
    # Correlation
    # ------------------------------------------------------------------

    async def get_correlation_matrix(
        self,
        db: AsyncSession,
        user_id: str,
        portfolio_id: Optional[str] = None,
        days: int = 60,
    ) -> CorrelationData:
        """Calculate correlation matrix from real historical returns."""

        assets = await self._get_user_assets(db, user_id, portfolio_id=portfolio_id)

        seen = {}
        for a in assets:
            if a.symbol not in seen:
                seen[a.symbol] = a
        symbols = list(seen.keys())

        if len(symbols) < 2:
            return CorrelationData(
                symbols=symbols,
                matrix=[[1.0]] if symbols else [],
                strongly_correlated=[],
                negatively_correlated=[],
            )

        returns_map: Dict[str, np.ndarray] = {}
        for sym, asset in seen.items():
            _, prices = await self._fetch_history(sym, asset.asset_type, days=days)
            rets = _compute_returns(prices)
            if len(rets) >= 5:
                returns_map[sym] = rets

        valid_symbols = [s for s in symbols if s in returns_map]
        if len(valid_symbols) < 2:
            return CorrelationData(
                symbols=symbols,
                matrix=[[1.0 if i == j else 0.0 for j in range(len(symbols))] for i in range(len(symbols))],
                strongly_correlated=[],
                negatively_correlated=[],
            )

        min_len = min(len(returns_map[s]) for s in valid_symbols)
        aligned = {s: returns_map[s][-min_len:] for s in valid_symbols}
        # P14: Spearman rank correlation — more robust for fat-tailed crypto distributions
        stacked = np.array([aligned[s] for s in valid_symbols])
        corr_result = spearmanr(stacked, axis=1)
        matrix_np = corr_result.statistic
        # spearmanr returns a scalar for exactly 2 variables — expand to 2x2 matrix
        if np.ndim(matrix_np) == 0:
            matrix_np = np.array([[1.0, float(matrix_np)], [float(matrix_np), 1.0]])

        full_n = len(symbols)
        matrix = [[0.0] * full_n for _ in range(full_n)]
        valid_idx = {s: symbols.index(s) for s in valid_symbols}
        strongly, negatively = [], []

        for vi, s1 in enumerate(valid_symbols):
            for vj, s2 in enumerate(valid_symbols):
                i, j = valid_idx[s1], valid_idx[s2]
                corr = float(matrix_np[vi, vj])
                if np.isnan(corr):
                    corr = 0.0
                matrix[i][j] = round(corr, 3)
                if vi < vj:
                    strong_pos, neg_th = adaptive_th.correlation_thresholds()
                    if corr > strong_pos:
                        strongly.append((s1, s2, round(corr, 3)))
                    elif corr < neg_th:
                        negatively.append((s1, s2, round(corr, 3)))

        for i in range(full_n):
            matrix[i][i] = 1.0

        return CorrelationData(
            symbols=symbols,
            matrix=matrix,
            strongly_correlated=sorted(strongly, key=lambda x: -x[2]),
            negatively_correlated=sorted(negatively, key=lambda x: x[2]),
        )

    # ------------------------------------------------------------------
    # Diversification
    # ------------------------------------------------------------------

    async def get_diversification_analysis(
        self,
        db: AsyncSession,
        user_id: str,
        portfolio_id: Optional[str] = None,
        days: int = 60,
    ) -> dict:
        if portfolio_id:
            analytics = await self.get_portfolio_analytics(db, portfolio_id, days=days)
        else:
            analytics = await self.get_user_analytics(db, user_id, days=days)

        conc_warn, conc_crit = adaptive_th.concentration_thresholds()
        recs = []
        if analytics.concentration_risk > conc_warn:
            top = sorted(analytics.allocation_by_asset.items(), key=lambda x: -x[1])[:3]
            recs.append(
                {
                    "type": "concentration",
                    "severity": "high" if analytics.concentration_risk > conc_crit else "medium",
                    "message": f"Concentration élevée: {top[0][0]} représente {top[0][1]:.1f}% du portefeuille",
                    "action": "Envisagez de diversifier vers d'autres actifs",
                }
            )
        if len(analytics.allocation_by_type) < 3:
            recs.append(
                {
                    "type": "asset_types",
                    "severity": "medium",
                    "message": f"Seulement {len(analytics.allocation_by_type)} classe(s) d'actifs",
                    "action": "Diversifiez entre crypto, actions, ETF et immobilier",
                }
            )
        for at, w in analytics.allocation_by_type.items():
            if w > 70:
                recs.append(
                    {
                        "type": "overweight",
                        "severity": "medium",
                        "message": f"{at} représente {w:.1f}% du portefeuille",
                        "action": f"Réduisez l'exposition à {at}",
                    }
                )
        if analytics.asset_count < 5:
            recs.append(
                {
                    "type": "asset_count",
                    "severity": "low",
                    "message": f"Seulement {analytics.asset_count} actif(s) en portefeuille",
                    "action": "Un portefeuille diversifié contient généralement 10-20 actifs",
                }
            )

        return {
            "score": analytics.diversification_score,
            "concentration_risk": analytics.concentration_risk,
            "asset_count": analytics.asset_count,
            "type_count": len(analytics.allocation_by_type),
            "allocation_by_type": analytics.allocation_by_type,
            "recommendations": recs,
            "rating": self._diversification_rating(analytics.diversification_score),
        }

    # ------------------------------------------------------------------
    # Monte Carlo simulation
    # ------------------------------------------------------------------

    async def monte_carlo(
        self,
        db: AsyncSession,
        user_id: str,
        horizon_days: int = 90,
        num_simulations: int = 5000,
        portfolio_id: Optional[str] = None,
        annual_withdrawal_rate: float = 0.0,
        ter_percentage: float = 0.0,
        monthly_withdrawal: float = 0.0,
        contribution: Optional[Dict[str, float]] = None,
        vol_regime: str = "normal",
    ) -> MonteCarloResult:
        """Run Monte Carlo simulation on the portfolio."""

        from app.services.metrics_service import is_cash_like

        # Get ALL user assets (including stablecoins/fiat for liquidity cushion)
        assets = await self._get_user_assets(
            db,
            user_id,
            portfolio_id=portfolio_id,
            exclude_stablecoins=False,
        )

        if not assets:
            return MonteCarloResult(
                percentiles={"p5": 0, "p25": 0, "p50": 0, "p75": 0, "p95": 0},
                expected_return=0,
                prob_positive=0,
                prob_loss_10=0,
                prob_ruin=0,
                simulations=0,
                horizon_days=horizon_days,
            )

        # Separate risky assets from liquidity (vol=0, corr=0 cushion)
        seen = {}
        liquidity_value = Decimal("0")
        for a in assets:
            if is_cash_like(a.symbol):
                price = float(a.avg_buy_price) if a.avg_buy_price and float(a.avg_buy_price) > 0 else 1.0
                liquidity_value += Decimal(str(a.quantity)) * Decimal(str(price))
                continue
            if a.symbol not in seen:
                seen[a.symbol] = a

        # Collect returns per risky asset
        all_returns = []
        all_weights = []
        total_value_dec = liquidity_value  # include liquidity in total

        for sym, asset in seen.items():
            _, prices = await self._fetch_history(sym, asset.asset_type, days=90)
            price = prices[-1] if prices and prices[-1] > 0 else float(asset.avg_buy_price)
            val_dec = Decimal(str(asset.quantity)) * Decimal(str(price))
            total_value_dec += val_dec
            rets = _compute_returns(prices)
            if len(rets) >= 10:
                all_returns.append(rets)
                all_weights.append(float(val_dec))

        # Add liquidity as a zero-volatility pseudo-asset (dampens overall risk)
        if float(liquidity_value) > 0 and all_returns:
            min_len = min(len(r) for r in all_returns)
            all_returns.append(np.zeros(min_len))  # vol=0, corr=0
            all_weights.append(float(liquidity_value))

        total_value = float(total_value_dec)
        if not all_returns or total_value == 0:
            return MonteCarloResult(
                percentiles={"p5": 0, "p25": 0, "p50": 0, "p75": 0, "p95": 0},
                expected_return=0,
                prob_positive=0,
                prob_loss_10=0,
                prob_ruin=0,
                simulations=0,
                horizon_days=horizon_days,
            )

        # Apply contribution: add capital to a specific asset before normalizing
        if contribution:
            sym_list = list(seen.keys())
            for sym_c, amount_eur in contribution.items():
                if sym_c in sym_list:
                    idx = sym_list.index(sym_c)
                    all_weights[idx] += amount_eur
                    total_value += amount_eur

        # Build weight vector and aligned return matrix
        w = np.array(all_weights)
        w = w / w.sum()
        n_assets = len(all_returns)
        min_len = min(len(r) for r in all_returns)
        aligned = np.array([r[-min_len:] for r in all_returns])  # (n_assets, min_len)

        # Per-asset mean and covariance matrix
        mu_vec = np.mean(aligned, axis=1)  # (n_assets,)
        cov_matrix = np.cov(aligned)  # (n_assets, n_assets)

        # Ensure cov_matrix is 2D even for single asset
        if cov_matrix.ndim == 0:
            cov_matrix = np.array([[float(cov_matrix)]])
        elif cov_matrix.ndim == 1:
            cov_matrix = cov_matrix.reshape(1, 1)

        # Cholesky decomposition for correlated sampling
        # Add small regularization for numerical stability
        try:
            L = np.linalg.cholesky(cov_matrix + np.eye(n_assets) * 1e-10)
        except np.linalg.LinAlgError:
            # Fallback: use diagonal (uncorrelated) if Cholesky fails
            L = np.diag(np.sqrt(np.diag(cov_matrix)))

        # Offload CPU-heavy simulation to a thread pool to avoid blocking
        # the async event loop.
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._monte_carlo_compute,
            mu_vec,
            L,
            w,
            num_simulations,
            horizon_days,
            n_assets,
            user_id,
            annual_withdrawal_rate,
            ter_percentage,
            monthly_withdrawal,
            total_value,
            vol_regime,
        )

    @staticmethod
    def _monte_carlo_compute(
        mu_vec: np.ndarray,
        L: np.ndarray,
        w: np.ndarray,
        num_simulations: int,
        horizon_days: int,
        n_assets: int,
        user_id: str,
        annual_withdrawal_rate: float = 0.0,
        ter_percentage: float = 0.0,
        monthly_withdrawal: float = 0.0,
        initial_portfolio_value: float = 0.0,
        vol_regime: str = "normal",
    ) -> "MonteCarloResult":
        """CPU-bound Monte Carlo with volatility shrinkage, withdrawals and fees.

        Volatility shrinkage: for horizons > 90 days, the Cholesky factor (L)
        is blended towards a long-term average volatility (~20% annualized)
        using a linear shrinkage schedule.  This prevents unrealistic
        extreme outcomes when short-term crypto vol (80%+) is extrapolated
        over multi-year horizons.

        vol_regime controls the long-term vol assumption:
        - "stress" (bear): 30% annualized — heavier tails, more pessimistic
        - "normal": 20% annualized — baseline
        - "low" (bull): 15% annualized — compressed vol, more optimistic

        Withdrawal modes (mutually exclusive, ``monthly_withdrawal`` takes priority):
        - ``monthly_withdrawal`` (€): absolute daily deduction = amount / 30.
          Formula: V(t) = V(t-1) * exp(r_t) * (1 - ter/365) - monthly_withdrawal/30
        - ``annual_withdrawal_rate`` (%): proportional daily deduction.

        A path is marked as "ruined" when portfolio value drops to ≤ 0.
        """
        # Cap allocation: 200 MB / 8 bytes per float64
        max_elements = 200_000_000 // 8
        capped_sims = min(num_simulations, max_elements // max(horizon_days * n_assets, 1))
        capped_sims = max(capped_sims, 100)  # At least 100 simulations

        # --- Volatility shrinkage (mean reversion) ---
        # Regime-aware long-term vol target
        _VOL_BY_REGIME = {"stress": 0.30, "normal": 0.20, "low": 0.15}
        LONG_TERM_DAILY_VOL = _VOL_BY_REGIME.get(vol_regime, 0.20) / np.sqrt(252)
        # Shrinkage ramps from 0 at 90 days to 1 at 1825 days (5 years)
        shrinkage = np.clip((horizon_days - 90) / (1825 - 90), 0.0, 1.0)

        if shrinkage > 0:
            # Build a long-term L: diagonal matrix with uniform long-term vol
            L_longterm = np.eye(n_assets) * LONG_TERM_DAILY_VOL
            L_blended = (1 - shrinkage) * L + shrinkage * L_longterm
        else:
            L_blended = L

        seed = int(time.time()) ^ (hash(user_id) % (2**31))
        rng = np.random.default_rng(seed & 0x7FFFFFFF)
        Z = rng.standard_normal(size=(capped_sims, horizon_days, n_assets))
        correlated_returns = mu_vec + np.einsum("ij,...j->...i", L_blended, Z)
        port_daily_returns = correlated_returns @ w  # (capped_sims, horizon_days)

        # --- Daily deductions from withdrawals + TER ---
        # TER: multiplicative daily factor  (1 - ter/365) applied each day.
        daily_ter_factor = 1.0
        if ter_percentage > 0:
            daily_ter_factor = 1.0 - ter_percentage / 100.0 / 365.0

        # Withdrawal: absolute daily amount (monthly_withdrawal / 30) normalised
        # to portfolio-relative units (we simulate starting at V=1.0).
        # Fallback: proportional annual_withdrawal_rate for backward compat.
        daily_abs_withdrawal = 0.0  # in normalised units (fraction of initial)
        daily_prop_withdrawal = 1.0  # multiplicative factor
        use_absolute = monthly_withdrawal > 0 and initial_portfolio_value > 0

        if use_absolute:
            daily_abs_withdrawal = (monthly_withdrawal / 30.0) / initial_portfolio_value
        elif annual_withdrawal_rate > 0:
            daily_prop_withdrawal = (1 - annual_withdrawal_rate / 100) ** (1 / 252)

        has_deductions = daily_ter_factor < 1.0 or daily_abs_withdrawal > 0 or daily_prop_withdrawal < 1.0

        if has_deductions:
            # Step-by-step simulation: V(t) starts at 1.0 (normalised)
            portfolio_values = np.ones((capped_sims, horizon_days + 1))
            for day in range(horizon_days):
                # V(t) = V(t-1) * exp(r_t) * ter_factor - abs_withdrawal
                # (or  * prop_factor  when using proportional mode)
                v_next = (
                    portfolio_values[:, day]
                    * np.exp(port_daily_returns[:, day])
                    * daily_ter_factor
                    * daily_prop_withdrawal
                )
                if daily_abs_withdrawal > 0:
                    v_next -= daily_abs_withdrawal
                # Floor at zero: once ruined, stay ruined
                portfolio_values[:, day + 1] = np.maximum(v_next, 0.0)

            # Ruin = portfolio touched 0 (or near-zero)
            ruin_mask = np.any(portfolio_values[:, 1:] <= 0.001, axis=1)
            prob_ruin = float(np.mean(ruin_mask) * 100)

            # Total returns from final portfolio value
            final_values = portfolio_values[:, -1]
            total_returns_pct = (final_values - 1.0) * 100
        else:
            # Original path without deductions (faster vectorized)
            cumulative_path = np.cumsum(port_daily_returns, axis=1)
            portfolio_values = np.exp(cumulative_path)  # relative to initial (1.0)
            ruin_mask = np.any(portfolio_values <= 0.01, axis=1)
            prob_ruin = float(np.mean(ruin_mask) * 100)

            cumulative = cumulative_path[:, -1]
            total_returns_pct = (np.exp(cumulative) - 1) * 100

        return MonteCarloResult(
            percentiles={
                "p5": round(float(np.percentile(total_returns_pct, 5)), 2),
                "p25": round(float(np.percentile(total_returns_pct, 25)), 2),
                "p50": round(float(np.percentile(total_returns_pct, 50)), 2),
                "p75": round(float(np.percentile(total_returns_pct, 75)), 2),
                "p95": round(float(np.percentile(total_returns_pct, 95)), 2),
            },
            expected_return=round(float(np.mean(total_returns_pct)), 2),
            prob_positive=round(float(np.mean(total_returns_pct > 0) * 100), 1),
            prob_loss_10=round(float(np.mean(total_returns_pct < -10) * 100), 1),
            prob_ruin=round(prob_ruin, 1),
            simulations=capped_sims,
            horizon_days=horizon_days,
        )

    # ------------------------------------------------------------------
    # Rebalancing
    # ------------------------------------------------------------------

    async def get_rebalance_orders(
        self,
        db: AsyncSession,
        user_id: str,
        target_weights: Dict[str, float],
    ) -> List[RebalanceOrder]:
        """
        Calculate rebalancing orders to move from current to target allocation.
        target_weights: {symbol: weight_percent} e.g. {"BTC": 40, "ETH": 30, "AAPL": 30}
        """
        analytics = await self.get_user_analytics(db, user_id)
        if analytics.asset_count == 0:
            return []

        total_value = analytics.total_value
        orders = []
        for a in analytics.assets:
            target_w = target_weights.get(a.symbol, a.weight)  # default: keep current
            diff_w = target_w - a.weight
            target_val = total_value * target_w / 100
            diff_val = target_val - a.current_value

            action = "hold"
            if diff_val > total_value * 0.005:  # >0.5% threshold
                action = "buy"
            elif diff_val < -total_value * 0.005:
                action = "sell"

            orders.append(
                RebalanceOrder(
                    symbol=a.symbol,
                    name=a.name,
                    asset_type=a.asset_type,
                    current_weight=round(a.weight, 2),
                    target_weight=round(target_w, 2),
                    diff_weight=round(diff_w, 2),
                    current_value=round(a.current_value, 2),
                    target_value=round(target_val, 2),
                    diff_value=round(diff_val, 2),
                    action=action,
                )
            )

        return sorted(orders, key=lambda x: abs(x.diff_value), reverse=True)

    # ------------------------------------------------------------------
    # Portfolio Optimization (MPT - Markowitz)
    # ------------------------------------------------------------------

    async def optimize_portfolio(
        self,
        db: AsyncSession,
        user_id: str,
        objective: str = "max_sharpe",
        days: int = 90,
    ) -> Optional[OptimizationResult]:
        """
        Find optimal portfolio weights using Modern Portfolio Theory.
        objective: "max_sharpe" or "min_volatility"
        """

        assets = await self._get_user_assets(db, user_id)

        seen = {}
        for a in assets:
            if a.symbol not in seen:
                seen[a.symbol] = a

        risk_free_rate = await self._fetch_risk_free_rate()

        symbols = []
        returns_list = []
        for sym, asset in seen.items():
            _, prices = await self._fetch_history(sym, asset.asset_type, days=days)
            rets = _compute_returns(prices)
            if len(rets) >= 10:
                symbols.append(sym)
                returns_list.append(rets)

        if len(symbols) < 2:
            return None

        min_len = min(len(r) for r in returns_list)
        aligned = np.array([r[-min_len:] for r in returns_list])
        n = len(symbols)

        # Weighted-average trading days for annualization
        opt_td = np.mean([_trading_days(seen[s].asset_type) for s in symbols])
        mu = np.mean(aligned, axis=1) * opt_td  # annualized mean return
        cov = np.cov(aligned) * opt_td  # annualized covariance

        def neg_sharpe(w):
            ret = w @ mu
            vol = np.sqrt(w @ cov @ w)
            if vol == 0:
                return 0
            return -(ret - risk_free_rate) / vol

        def portfolio_vol(w):
            return np.sqrt(w @ cov @ w)

        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
        bounds = [(0.0, 1.0)] * n
        w0 = np.array([1.0 / n] * n)

        if objective == "min_volatility":
            res = sp_optimize.minimize(portfolio_vol, w0, bounds=bounds, constraints=constraints, method="SLSQP")
        else:
            res = sp_optimize.minimize(neg_sharpe, w0, bounds=bounds, constraints=constraints, method="SLSQP")

        if not res.success:
            return None

        opt_w = res.x
        # Convert annualized log return to discrete % for display
        # log return * td is continuous; (exp(r) - 1)*100 gives intuitive %
        ann_log_ret = float(opt_w @ mu)
        opt_ret = (np.exp(ann_log_ret) - 1) * 100  # discrete annualized %
        opt_vol = float(np.sqrt(opt_w @ cov @ opt_w)) * 100
        opt_sharpe = _sharpe(opt_ret, opt_vol, risk_free_rate)

        weights = {sym: round(float(opt_w[i]) * 100, 2) for i, sym in enumerate(symbols)}

        return OptimizationResult(
            weights=weights,
            expected_return=round(opt_ret, 2),
            expected_volatility=round(opt_vol, 2),
            sharpe_ratio=opt_sharpe,
        )

    # ------------------------------------------------------------------
    # XIRR
    # ------------------------------------------------------------------

    async def compute_xirr(self, db: AsyncSession, user_id: str, currency: str = "EUR") -> Optional[float]:
        """Compute XIRR across all user portfolios.

        Uses metrics_service for current portfolio value (single source of truth)
        and converts transaction amounts to the user's preferred currency.
        Returns annualized rate as percentage, or None if not computable.
        """
        from app.services.metrics_service import metrics_service

        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == user_id,
            )
        )
        portfolios = result.scalars().all()
        if not portfolios:
            return None

        pids = [p.id for p in portfolios]

        # Get all transactions
        tx_result = await db.execute(
            select(Transaction)
            .join(Asset, Transaction.asset_id == Asset.id)
            .where(
                Asset.portfolio_id.in_(pids),
            )
            .order_by(Transaction.executed_at.asc())
        )
        transactions = tx_result.scalars().all()

        if not transactions:
            return None

        # ── Forex rate for multi-currency conversion ──
        # Transaction amounts are stored in the asset's quote currency (usually USD).
        # Convert to user's preferred currency for accurate XIRR.
        usd_to_target = 1.0
        target = currency.upper()
        if target != "USD":
            try:
                rate = await self.price_service.get_forex_rate("USD", target)
                usd_to_target = float(rate) if rate else 1.0
            except Exception:
                logger.warning("Forex USD→%s unavailable, using 1.0", target)

        cashflows: List[Tuple[datetime, float]] = []
        skipped = 0
        for tx in transactions:
            # Guard: skip transactions without a date (data integrity issue)
            dt = tx.executed_at
            if dt is None:
                skipped += 1
                continue

            amount = float(tx.quantity) * float(tx.price) * usd_to_target
            fee = float(tx.fee or 0) * usd_to_target

            # Ensure timezone-aware datetime
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            if tx.transaction_type in [TransactionType.BUY, TransactionType.TRANSFER_IN]:
                # Cash outflow (investment) — negative for XIRR convention
                cashflows.append((dt, -(amount + fee)))
            elif tx.transaction_type in [TransactionType.SELL, TransactionType.TRANSFER_OUT]:
                # Cash inflow — positive
                cashflows.append((dt, amount - fee))
            elif tx.transaction_type in [TransactionType.STAKING_REWARD, TransactionType.AIRDROP]:
                cashflows.append((dt, amount))

        if skipped > 0:
            logger.warning("XIRR: skipped %d transactions with NULL executed_at", skipped)

        if not cashflows:
            return None

        # Add current portfolio value as final cashflow (positive)
        # Use metrics_service for live, currency-converted value
        try:
            dashboard = await metrics_service.get_user_dashboard_metrics(db, user_id, currency=currency, days=0)
            current_value = float(dashboard.get("total_value", 0.0))
        except Exception as exc:
            logger.warning("XIRR: metrics_service fallback to _get_asset_price: %s", exc)
            assets = await self._get_user_assets(db, user_id, exclude_stablecoins=False)
            current_value = 0.0
            for asset in assets:
                price = await self._get_asset_price(asset)
                current_value += float(asset.quantity) * price
            current_value *= usd_to_target

        if current_value <= 0:
            return None

        cashflows.append((datetime.now(timezone.utc), current_value))

        # Guard: need at least one investment + current value
        negatives = sum(1 for _, a in cashflows if a < 0)
        if negatives == 0:
            return None

        rate = _xirr(cashflows)
        if rate is not None:
            # Clamp to reasonable range: -95% to +1000%
            rate_pct = round(rate * 100, 2)
            return max(-95.0, min(rate_pct, 1000.0))
        return None

    # ------------------------------------------------------------------
    # Stress Tests (#15)
    # ------------------------------------------------------------------

    # Historical crisis scenario definitions
    HISTORICAL_SCENARIOS = [
        {
            "id": "covid_2020",
            "name": "COVID-19 (Mars 2020)",
            "description": "Krach pandémique — chute rapide sur toutes les classes d'actifs en 30 jours",
            "shocks": {"crypto": -50, "stock": -35, "etf": -30, "real_estate": -10, "crowdfunding": -5},
            "duration_days": 30,
            "historical_recovery_months": 5,
        },
        {
            "id": "luna_ftx_2022",
            "name": "LUNA/FTX (2022)",
            "description": "Effondrement crypto (Luna Mai + FTX Nov) — altcoins -60%, BTC -40%",
            "shocks": {"crypto": -60, "stock": -20, "etf": -15, "real_estate": -5, "crowdfunding": -3},
            "duration_days": 60,
            "historical_recovery_months": 18,
        },
        {
            "id": "crisis_2008",
            "name": "Crise financière 2008",
            "description": "Crise systémique bancaire — chute massive des actions et immobilier",
            "shocks": {"crypto": -30, "stock": -50, "etf": -45, "real_estate": -25, "crowdfunding": -15},
            "duration_days": 180,
            "historical_recovery_months": 48,
        },
        {
            "id": "bull_run_2021",
            "name": "Bull Run 2021",
            "description": "Hausse généralisée — crypto +100%, actions +25%, ETF +20%",
            "shocks": {"crypto": 100, "stock": 25, "etf": 20, "real_estate": 10, "crowdfunding": 5},
            "duration_days": 365,
            "historical_recovery_months": 0,
        },
        {
            "id": "rate_hike",
            "name": "Hausse des taux (+300bp)",
            "description": "Resserrement monétaire brutal — impact sur les valorisations",
            "shocks": {"crypto": -25, "stock": -18, "etf": -15, "real_estate": -10, "crowdfunding": -5},
            "duration_days": 90,
            "historical_recovery_months": 12,
        },
        {
            "id": "flash_crash",
            "name": "Flash Crash",
            "description": "Chute éclair intra-journalière sur tous les marchés",
            "shocks": {"crypto": -15, "stock": -10, "etf": -8, "real_estate": -3, "crowdfunding": -1},
            "duration_days": 1,
            "historical_recovery_months": 1,
        },
    ]

    async def stress_test(
        self,
        db: AsyncSession,
        user_id: str,
        portfolio_id: Optional[str] = None,
        currency: str = "EUR",
        scenario_ids: Optional[List[str]] = None,
    ) -> dict:
        """Run stress tests simulating historical crash scenarios on the portfolio.

        Uses metrics_service for live prices and risk_weight per asset.
        Shocks are modulated by each asset's volatility-based risk_weight:
        high-risk assets receive proportionally larger shocks.

        Returns MaxDD (worst-case drawdown) and estimated recovery time.
        """
        from app.services.metrics_service import metrics_service

        # Fetch live portfolio data from metrics_service (single source of truth)
        result = await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
        portfolios = result.scalars().all()

        if not portfolios:
            return {"scenarios": [], "total_value": 0, "currency": currency, "max_drawdown": None}

        # Collect per-asset live data with risk_weight
        all_assets = []
        for portfolio in portfolios:
            if portfolio_id and str(portfolio.id) != portfolio_id:
                continue
            pm = await metrics_service.get_portfolio_metrics(db, str(portfolio.id), currency=currency)
            all_assets.extend(pm.get("assets", []))

        if not all_assets:
            return {"scenarios": [], "total_value": 0, "currency": currency, "max_drawdown": None}

        total_value = float(sum(Decimal(str(a.get("current_value", 0))) for a in all_assets))
        if total_value <= 0:
            return {"scenarios": [], "total_value": 0, "currency": currency, "max_drawdown": None}

        # Compute risk-weight statistics for modulation
        n_assets = len(all_assets)
        total_risk_weight = sum(a.get("risk_weight", 0) for a in all_assets) or 1.0
        avg_risk_weight = total_risk_weight / n_assets if n_assets > 0 else 1.0

        # Filter scenarios if specific IDs requested
        scenarios_to_run = self.HISTORICAL_SCENARIOS
        if scenario_ids:
            scenarios_to_run = [s for s in self.HISTORICAL_SCENARIOS if s["id"] in scenario_ids]

        scenarios = []
        worst_loss_pct = 0.0
        worst_scenario_name = ""
        worst_recovery_months = 0

        for scenario_def in scenarios_to_run:
            stressed_value = 0.0
            per_asset = []
            is_bullish = any(v > 0 for v in scenario_def["shocks"].values())

            for asset in all_assets:
                val = asset.get("current_value", 0)
                symbol = asset.get("symbol", "")
                asset_type = asset.get("asset_type", "crypto")
                risk_weight = asset.get("risk_weight", 0)

                # Base shock from asset class
                base_shock = scenario_def["shocks"].get(asset_type, -10)

                # Apply risk-weight modulation (only for negative shocks)
                if not is_bullish and avg_risk_weight > 0 and risk_weight > 0:
                    multiplier = risk_weight / avg_risk_weight
                    multiplier = min(max(multiplier, 0.3), 2.5)
                    shock_pct = base_shock * multiplier
                else:
                    shock_pct = base_shock
                # Cap to prevent negative asset values or absurd gains
                shock_pct = max(min(shock_pct, 300.0), -95.0)

                stressed = val * (1 + shock_pct / 100)
                loss = stressed - val
                stressed_value += stressed
                per_asset.append(
                    {
                        "symbol": symbol,
                        "name": asset.get("name", ""),
                        "current_value": round(val, 2),
                        "stressed_value": round(stressed, 2),
                        "loss": round(loss, 2),
                        "shock_pct": round(shock_pct, 1),
                        "risk_weight": risk_weight,
                    }
                )

            total_loss = stressed_value - total_value
            total_loss_pct = (total_loss / total_value * 100) if total_value > 0 else 0

            # Track worst drawdown for MaxDD calculation
            if total_loss_pct < worst_loss_pct:
                worst_loss_pct = total_loss_pct
                worst_scenario_name = scenario_def["name"]
                worst_recovery_months = scenario_def["historical_recovery_months"]

            # Estimated recovery time: scale historical recovery by avg risk weight
            # Higher average risk = longer recovery
            base_recovery = scenario_def["historical_recovery_months"]
            if base_recovery > 0 and avg_risk_weight > 0:
                # Normalize: risk_weight is a percentage (sum=100), avg across N assets
                # Scale: if avg risk is 2x the baseline, recovery takes ~1.5x longer
                risk_factor = 1.0 + (avg_risk_weight - (100 / max(n_assets, 1))) / 100
                risk_factor = min(max(risk_factor, 0.5), 3.0)
                estimated_recovery = round(base_recovery * risk_factor)
            else:
                estimated_recovery = base_recovery

            scenarios.append(
                {
                    "id": scenario_def["id"],
                    "name": scenario_def["name"],
                    "description": scenario_def["description"],
                    "duration_days": scenario_def["duration_days"],
                    "stressed_value": round(stressed_value, 2),
                    "total_loss": round(total_loss, 2),
                    "total_loss_pct": round(total_loss_pct, 2),
                    "estimated_recovery_months": estimated_recovery,
                    "per_asset": sorted(per_asset, key=lambda x: x["loss"]),
                }
            )

        # Sort by worst-case first (negative values first)
        scenarios.sort(key=lambda s: s["total_loss"])

        # MaxDD: worst theoretical drawdown across all scenarios
        max_drawdown = (
            {
                "value": round(abs(worst_loss_pct), 2),
                "scenario": worst_scenario_name,
                "estimated_recovery_months": worst_recovery_months,
            }
            if worst_loss_pct < 0
            else None
        )

        return {
            "total_value": round(total_value, 2),
            "currency": currency,
            "scenarios": scenarios,
            "max_drawdown": max_drawdown,
        }

    # ------------------------------------------------------------------
    # Beta vs Benchmark (#17)
    # ------------------------------------------------------------------

    async def compute_beta(
        self,
        db: AsyncSession,
        user_id: str,
        days: int = 90,
        portfolio_id: Optional[str] = None,
    ) -> dict:
        """Compute beta of each asset and the portfolio vs relevant benchmarks.

        - Crypto assets: beta vs BTC
        - Stock/ETF assets: beta vs SPY (S&P 500)
        Beta = Cov(asset, benchmark) / Var(benchmark)
        """
        raw_assets = await self._get_user_assets(db, user_id, portfolio_id=portfolio_id)

        if not raw_assets:
            return {"assets": [], "portfolio_beta_crypto": None, "portfolio_beta_stock": None}

        # Deduplicate
        seen: Dict[str, Asset] = {}
        qty_map: Dict[str, float] = {}
        for a in raw_assets:
            if a.symbol not in seen:
                seen[a.symbol] = a
                qty_map[a.symbol] = float(a.quantity)
            else:
                qty_map[a.symbol] += float(a.quantity)

        # Fetch benchmark returns
        _, btc_prices = await self._fetch_history("BTC", "crypto", days=days)
        btc_returns = _compute_returns(btc_prices)

        _, spy_prices = await self._fetch_history("SPY", "stock", days=days)
        spy_returns = _compute_returns(spy_prices)

        asset_betas = []
        total_value_dec = Decimal("0")
        crypto_weighted_beta = 0.0
        crypto_total_val = 0.0
        stock_weighted_beta = 0.0
        stock_total_val = 0.0

        for sym, asset in seen.items():
            _, prices = await self._fetch_history(sym, asset.asset_type, days=days)
            price = prices[-1] if prices and prices[-1] > 0 else float(asset.avg_buy_price)
            val_dec = Decimal(str(qty_map[sym])) * Decimal(str(price))
            total_value_dec += val_dec
            val = float(val_dec)
            rets = _compute_returns(prices)

            at = asset.asset_type.value if isinstance(asset.asset_type, AssetType) else asset.asset_type

            # Choose benchmark
            if at == "crypto":
                bench_returns = btc_returns
                bench_name = "BTC"
            else:
                bench_returns = spy_returns
                bench_name = "SPY"

            beta = self._calc_beta(rets, bench_returns)

            asset_betas.append(
                {
                    "symbol": sym,
                    "asset_type": at,
                    "beta": round(beta, 3) if beta is not None else None,
                    "benchmark": bench_name,
                    "interpretation": self._interpret_beta(beta),
                    "value": round(val, 2),
                }
            )

            if beta is not None:
                if at == "crypto":
                    crypto_weighted_beta += beta * val
                    crypto_total_val += val
                else:
                    stock_weighted_beta += beta * val
                    stock_total_val += val

        port_beta_crypto = round(crypto_weighted_beta / crypto_total_val, 3) if crypto_total_val > 0 else None
        port_beta_stock = round(stock_weighted_beta / stock_total_val, 3) if stock_total_val > 0 else None

        return {
            "assets": sorted(asset_betas, key=lambda x: abs(x["beta"] or 0), reverse=True),
            "portfolio_beta_crypto": port_beta_crypto,
            "portfolio_beta_stock": port_beta_stock,
            "benchmarks": {
                "crypto": "BTC",
                "stock": "SPY (S&P 500)",
            },
        }

    @staticmethod
    def _calc_beta(asset_returns: np.ndarray, bench_returns: np.ndarray) -> Optional[float]:
        """Compute beta = Cov(asset, bench) / Var(bench)."""
        if len(asset_returns) < 10 or len(bench_returns) < 10:
            return None
        min_len = min(len(asset_returns), len(bench_returns))
        a = asset_returns[-min_len:]
        b = bench_returns[-min_len:]
        var_b = float(np.var(b, ddof=1))
        if var_b == 0:
            return None
        cov = float(np.cov(a, b)[0, 1])
        return cov / var_b

    @staticmethod
    def _interpret_beta(beta: Optional[float]) -> str:
        """Interpret beta value in French using centralized classification."""
        if beta is None:
            return "Données insuffisantes"
        category = adaptive_th.beta_classification(beta)
        labels = {
            "very_aggressive": "Très agressif — amplifie les mouvements du marché",
            "aggressive": "Agressif — plus volatil que le marché",
            "neutral": "Neutre — suit le marché",
            "defensive": "Défensif — moins volatil que le marché",
            "very_defensive": "Très défensif — quasi décorrélé du marché",
            "inverse": "Inversement corrélé — se comporte à l'inverse du marché",
        }
        return labels.get(category, "Données insuffisantes")

    # ------------------------------------------------------------------
    # Parametric VaR (#16)
    # ------------------------------------------------------------------

    def _build_portfolio_var_parametric(self, port_returns: np.ndarray, total_value: float) -> dict:
        """Compute parametric VaR alongside historical VaR for comparison."""
        var_hist = _var_historical(port_returns) if len(port_returns) >= 5 else 0.0
        var_param = _var_parametric(port_returns) if len(port_returns) >= 5 else 0.0
        cvar = _cvar_historical(port_returns) if len(port_returns) >= 5 else 0.0

        return {
            "var_95_historical_pct": round(var_hist, 2),
            "var_95_parametric_pct": round(var_param, 2),
            "var_95_historical_eur": round(total_value * var_hist / 100, 2),
            "var_95_parametric_eur": round(total_value * var_param / 100, 2),
            "cvar_95_pct": round(cvar, 2),
            "cvar_95_eur": round(total_value * cvar / 100, 2),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _empty_analytics(self) -> PortfolioAnalytics:
        return PortfolioAnalytics(
            total_value=0,
            total_invested=0,
            total_gain_loss=0,
            total_gain_loss_percent=0,
            portfolio_volatility=0,
            sharpe_ratio=0,
            sortino_ratio=0,
            calmar_ratio=0,
            max_drawdown=0,
            var_95=0,
            cvar_95=0,
            diversification_score=0,
            concentration_risk=0,
            asset_count=0,
            allocation_by_type={},
            allocation_by_asset={},
            assets=[],
            best_performer=None,
            worst_performer=None,
        )

    @staticmethod
    def _hhi(allocation: Dict[str, float]) -> float:
        if not allocation:
            return 0
        return round(sum((w / 100) ** 2 for w in allocation.values()), 4)

    @staticmethod
    def _diversification_score(asset_count: int, type_count: int, concentration: float) -> float:
        a = min(asset_count * 3, 30)
        t = min(type_count * 10, 30)
        c = max(0, 40 * (1 - concentration * 2))
        return round(a + t + c, 1)

    @staticmethod
    def _diversification_rating(score: float) -> str:
        if score >= 80:
            return "Excellent"
        elif score >= 60:
            return "Bon"
        elif score >= 40:
            return "Moyen"
        elif score >= 20:
            return "Faible"
        return "Très faible"


# Singleton instance
analytics_service = AnalyticsService()
