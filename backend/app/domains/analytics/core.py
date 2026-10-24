import logging
import time
from collections.abc import Sequence
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.finance_constants import RISK_FREE_RATE
from app.domains.analytics.metrics import (
    annualized_return,
    annualized_volatility,
    compute_returns,
    daily_return_pct,
    downside_deviation,
    max_drawdown,
)
from app.domains.market_data.history.reader import local_series
from app.domains.market_data.prices.service import price_feed
from app.domains.portfolio.classification import is_stablecoin
from app.domains.portfolio.models import Asset, Portfolio

logger = logging.getLogger(__name__)

AssetData = dict[str, Any]

DUST_VALUE = 0.10


def _ecb_rate_pct(payload: Any) -> float | None:
    datasets = payload.get("dataSets", [{}])
    if not datasets:
        return None
    for series_data in datasets[0].get("series", {}).values():
        observations = series_data.get("observations", {})
        if observations:
            last_obs_key = max(observations.keys(), key=int)
            return float(observations[last_obs_key][0])
    return None


def _asset_entry(asset: Asset, hist_prices: list[float]) -> AssetData:
    price = hist_prices[-1] if hist_prices and hist_prices[-1] > 0 else float(asset.avg_buy_price)
    current_value = float(asset.quantity) * price if price else 0
    total_invested = float(asset.quantity) * float(asset.avg_buy_price)
    gain_loss = current_value - total_invested
    rets = compute_returns(hist_prices)
    at = asset.asset_type
    return {
        "asset": asset,
        "price": price,
        "current_value": current_value,
        "total_invested": total_invested,
        "gain_loss": gain_loss,
        "gain_loss_percent": (gain_loss / total_invested * 100) if total_invested > 0 else 0,
        "hist_prices": hist_prices,
        "returns": rets,
        "volatility": annualized_volatility(rets, asset_type=at),
        "downside_dev": downside_deviation(rets, asset_type=at),
        "annualized_return": annualized_return(rets, asset_type=at),
        "max_drawdown": max_drawdown(hist_prices),
        "daily_return": daily_return_pct(hist_prices),
        "is_stablecoin": is_stablecoin(asset.symbol),
    }


class AnalyticsCore:
    _ECB_DFR_URL = (
        "https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR.LEV?lastNObservations=1&format=jsondata"
    )
    _ECB_RATE_TTL = 86400

    def __init__(self) -> None:
        self._ecb_rate_cache: tuple[float, float] | None = None

    async def _fetch_risk_free_rate(self) -> float:
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
            rate_pct = _ecb_rate_pct(data)
            if rate_pct is not None:
                rate_decimal = rate_pct / 100.0
                self._ecb_rate_cache = (now, rate_decimal)
                logger.info("ECB deposit facility rate: %.2f%%", rate_pct)
                return rate_decimal
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "Failed to fetch ECB risk-free rate: %s — using fallback %.1f%%",
                e,
                RISK_FREE_RATE * 100,
            )

        return RISK_FREE_RATE

    async def _history_prices(self, symbol: str, days: int) -> list[float]:
        return (await local_series(symbol, days)).prices

    async def _get_asset_price(self, asset: Asset) -> float:
        quote = await price_feed.quote(asset.symbol, asset.asset_type)
        return float(quote.price) if quote is not None else float(asset.avg_buy_price)

    async def _get_user_assets(
        self,
        db: AsyncSession,
        user_id: str,
        portfolio_id: str | None = None,
        exclude_stablecoins: bool = True,
        min_value: float = DUST_VALUE,
    ) -> list[Asset]:
        if portfolio_id:
            result = await db.execute(select(Asset).where(Asset.portfolio_id == portfolio_id, Asset.quantity > 0))
        else:
            portfolios = (await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))).scalars().all()
            pids = [p.id for p in portfolios]
            if not pids:
                return []
            result = await db.execute(select(Asset).where(Asset.portfolio_id.in_(pids), Asset.quantity > 0))

        filtered: list[Asset] = []
        for a in result.scalars().all():
            if exclude_stablecoins and is_stablecoin(a.symbol):
                continue
            est_value = float(a.quantity) * float(a.avg_buy_price) if a.avg_buy_price else 0
            if est_value < min_value:
                continue
            filtered.append(a)
        return filtered

    async def _build_asset_data(self, assets: Sequence[Asset], days: int = 60) -> list[AssetData]:
        asset_data: list[AssetData] = []
        for asset in assets:
            entry = _asset_entry(asset, await self._history_prices(asset.symbol, days=days))
            if entry["current_value"] < DUST_VALUE:
                continue
            asset_data.append(entry)
        return asset_data
