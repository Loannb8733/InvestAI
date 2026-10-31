import asyncio
import gc
import logging
from decimal import Decimal
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.market_data.fear_greed import fetch_fear_greed_index
from app.domains.market_data.history.reader import local_series
from app.domains.market_data.prices.service import price_feed
from app.domains.market_data.prices.stablecoins import peg_quote
from app.domains.portfolio.models import Asset, AssetType
from app.domains.predictions.alpha_scoring import (
    alpha_row,
    btc_decorrelation,
    predicted_move,
    rank_alpha,
    regime_momentum,
    rsi_divergence,
)
from app.domains.predictions.core import held_assets, user_portfolio_ids
from app.domains.predictions.cycles import CyclesMixin
from app.domains.predictions.forecast import ForecastMixin
from app.domains.predictions.holdings import group_holdings
from app.domains.predictions.strategy_map import strategy_map
from app.domains.predictions.types import PricePrediction

logger = logging.getLogger(__name__)

MAX_ALPHA_ASSETS = 7
PREDICTION_BATCH_SIZE = 3
MAX_WHAT_IF_ASSETS = 15


async def _quotes(asset_map: dict[str, Asset]) -> dict[str, float]:
    crypto_symbols = [s for s, a in asset_map.items() if a.asset_type == AssetType.CRYPTO]
    stock_symbols = [s for s, a in asset_map.items() if a.asset_type in (AssetType.STOCK, AssetType.ETF)]
    price_map: dict[str, float] = {}

    if crypto_symbols:
        try:
            batch = await price_feed.crypto(crypto_symbols)
            for sym, quote in batch.items():
                price_map[sym] = float(quote.price)
        except Exception as e:  # noqa: BLE001
            logger.warning("Batch crypto price fetch failed: %s", e)

    for sym in stock_symbols:
        try:
            stock_quote = (await price_feed.stocks([sym])).get(sym.upper())
            if stock_quote is not None:
                price_map[sym.upper()] = float(stock_quote.price)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Stock price fetch failed for %s (alpha scoring): %s", sym, exc)
    return price_map


async def _history(sym: str) -> tuple[str, list[float]]:
    return (sym, (await local_series(sym, 90)).prices)


async def _add_cash_like(total_value: Decimal, cash_like_qty: dict[str, Decimal]) -> Decimal:
    for sym, qty in cash_like_qty.items():
        try:
            pegged = await peg_quote(sym.upper(), "EUR")
            p = pegged.price if pegged is not None else Decimal("1")
            total_value += qty * p
        except Exception:  # noqa: BLE001
            total_value += qty
    return total_value


def _empty_what_if() -> dict[str, Any]:
    return {"current_value": 0, "simulated_value": 0, "impact_percent": 0, "per_asset": []}


class AlphaMixin(ForecastMixin, CyclesMixin):
    async def get_top_alpha_asset(self, db: AsyncSession, user_id: str) -> dict[str, Any]:
        """Actif au plus fort alpha à court terme : divergence RSI/prix, décorrélation au BTC, momentum de régime.

        Sept actifs au plus et prévisions par lots de trois, pour tenir dans 512 Mo.
        """
        portfolio_ids = await user_portfolio_ids(db, user_id)
        if not portfolio_ids:
            return {"found": False}

        holdings = group_holdings(await held_assets(db, portfolio_ids))
        if not holdings.assets:
            return {"found": False, "total_portfolio_value": 0.0}

        btc_prices = (await local_series("BTC", 90)).prices
        btc_returns: NDArray[np.float64] = (
            np.diff(np.log(np.array(btc_prices, dtype=float))) if len(btc_prices) > 10 else np.array([])
        )
        fear_greed: int | None = await fetch_fear_greed_index()
        price_map = await _quotes(holdings.assets)

        items = list(holdings.assets.items())[:MAX_ALPHA_ASSETS]
        history_map: dict[str, list[float]] = dict(await asyncio.gather(*[_history(s) for s, _ in items]))
        predictions = await self._batched_predictions(items)

        scored_assets: list[dict[str, Any]] = []
        total_value = Decimal("0")
        for symbol, asset in items:
            try:
                price = price_map.get(symbol.upper(), 0.0)
                if price <= 0:
                    price = await self._get_current_price(symbol, asset.asset_type) or 0.0
                if price <= 0:
                    logger.warning("Price fetch failed for %s (batch + fallback), skipping", symbol)
                    continue
                price_dec = Decimal(str(price))
                value_dec = holdings.quantities[symbol] * price_dec
                total_value += value_dec

                a_prices = history_map.get(symbol, [])
                if len(a_prices) < 20:
                    continue
                scored_assets.append(
                    self._score_asset(
                        asset, a_prices, btc_returns, fear_greed, predictions.get(symbol), price_dec, value_dec
                    )
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("Alpha scoring failed for %s: %s", symbol, e)

        if not scored_assets:
            return {"found": False, "total_portfolio_value": 0.0}
        return rank_alpha(scored_assets, await _add_cash_like(total_value, holdings.cash_like))

    async def _batched_predictions(self, items: list[tuple[str, Asset]]) -> dict[str, PricePrediction | None]:
        cache: dict[str, PricePrediction | None] = {}

        async def fetch(sym: str, atype: AssetType) -> tuple[str, PricePrediction | None]:
            try:
                pred = await self.get_price_prediction(sym, atype, days_ahead=7)
                return (sym, pred)
            except Exception as e:  # noqa: BLE001
                logger.debug("7d prediction failed for %s: %s", sym, e)
                return (sym, None)

        for batch_start in range(0, len(items), PREDICTION_BATCH_SIZE):
            batch = items[batch_start : batch_start + PREDICTION_BATCH_SIZE]
            batch_results = await asyncio.gather(*[fetch(s, a.asset_type) for s, a in batch])
            for sym, pred in batch_results:
                cache[sym] = pred
            gc.collect()
        return cache

    def _score_asset(
        self,
        asset: Asset,
        a_prices: list[float],
        btc_returns: NDArray[np.float64],
        fear_greed: int | None,
        prediction: PricePrediction | None,
        price_dec: Decimal,
        value_dec: Decimal,
    ) -> dict[str, Any]:
        symbol = asset.symbol
        div_points, div_reason, divergence_log = rsi_divergence(symbol, a_prices)
        decorr_points, decorr_reason = btc_decorrelation(btc_returns, a_prices)
        regime_result = self.regime_detector.detect(
            a_prices,
            symbol,
            fear_greed,
            asset_type=asset.asset_type.value,
        )
        regime_points, regime_reason = regime_momentum(regime_result)

        score = 0.0
        score += div_points
        score += decorr_points
        score += regime_points
        reasons = [r for r in (div_reason, decorr_reason, regime_reason) if r is not None]

        move = predicted_move(symbol, prediction, price_dec, a_prices)
        return alpha_row(asset, price_dec, value_dec, score, reasons, move, regime_result, divergence_log)

    async def get_strategy_map(self, db: AsyncSession, user_id: str) -> dict[str, Any]:
        """Table de décision croisant les scores alpha et la phase de cycle de chaque actif."""
        alpha_data, cycle_data = await asyncio.gather(
            self.get_top_alpha_asset(db, user_id),
            self.get_market_cycle(db, user_id),
        )
        return strategy_map(alpha_data, cycle_data)

    async def get_what_if(self, db: AsyncSession, user_id: str, scenarios: list[dict[str, Any]]) -> dict[str, Any]:
        """Simule des variations de cours en % par symbole sur les quinze premiers actifs du portefeuille."""
        portfolio_ids = await user_portfolio_ids(db, user_id)
        if not portfolio_ids:
            return _empty_what_if()

        wi_asset_map: dict[str, Asset] = {}
        wi_qty_map: dict[str, Decimal] = {}
        for a in await held_assets(db, portfolio_ids):
            if a.symbol not in wi_asset_map:
                wi_asset_map[a.symbol] = a
                wi_qty_map[a.symbol] = Decimal(str(a.quantity))
            else:
                wi_qty_map[a.symbol] += Decimal(str(a.quantity))

        scenario_map = {s["symbol"].upper(): s["change_percent"] for s in scenarios}

        per_asset = []
        total_current = Decimal("0")
        total_simulated = Decimal("0")
        for asset in list(wi_asset_map.values())[:MAX_WHAT_IF_ASSETS]:
            price = await self._get_current_price(asset.symbol, asset.asset_type)
            if price is None:
                continue
            current_val = Decimal(str(price)) * wi_qty_map[asset.symbol]
            change = scenario_map.get(asset.symbol.upper(), 0.0)
            simulated_val = current_val * Decimal(str(1 + change / 100))

            total_current += current_val
            total_simulated += simulated_val
            per_asset.append(
                {
                    "symbol": asset.symbol,
                    "name": asset.name,
                    "current_value": round(float(current_val), 2),
                    "simulated_value": round(float(simulated_val), 2),
                    "change_percent": change,
                    "impact": round(float(simulated_val - current_val), 2),
                }
            )

        total_current_f = float(total_current)
        total_simulated_f = float(total_simulated)
        impact_pct = ((total_simulated_f - total_current_f) / total_current_f * 100) if total_current_f > 0 else 0
        return {
            "current_value": round(total_current_f, 2),
            "simulated_value": round(total_simulated_f, 2),
            "impact_percent": round(impact_pct, 2),
            "per_asset": per_asset,
        }
