import asyncio
import logging
from collections.abc import Awaitable, Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.market_data.history.reader import local_series
from app.domains.market_data.prices.service import price_feed
from app.domains.market_data.prices.stablecoins import peg_quote
from app.domains.portfolio.models import Asset
from app.domains.predictions.core import PredictionCore, held_assets, user_portfolio_ids
from app.domains.predictions.cycle_advice import cycle_advice
from app.domains.predictions.cycle_assets import (
    MarketReference,
    PortfolioCycle,
    asset_cycle_row,
    market_cycle_position,
    max_value_weight,
    portfolio_probabilities,
)
from app.domains.predictions.cycle_diagnostic import distribution_diagnostic
from app.domains.predictions.holdings import group_holdings
from app.domains.predictions.top_bottom import time_to_pivot, top_bottom_estimate
from app.domains.predictions.types import HISTORY_DAYS
from app.ml import adaptive_thresholds as at
from app.ml.market_context import MarketContext, compute_market_context
from app.services.market_sentiment import fetch_fear_greed_index

EXTERNAL_CALL_BUDGET = 12.0

logger = logging.getLogger(__name__)


class _Budget:
    def __init__(self) -> None:
        self._deadline = asyncio.get_event_loop().time() + EXTERNAL_CALL_BUDGET

    def remaining(self) -> float:
        return max(0.1, self._deadline - asyncio.get_event_loop().time())


async def _bounded(coro: Awaitable[tuple[str, Any]], default: tuple[str, Any], budget: _Budget) -> tuple[str, Any]:
    try:
        return await asyncio.wait_for(coro, timeout=budget.remaining())
    except TimeoutError:
        return default
    except Exception as exc:  # noqa: BLE001
        logger.debug("Pré-chargement abandonné : %s", exc)
        return default


async def _fear_greed(budget: _Budget) -> int | None:
    try:
        return await asyncio.wait_for(fetch_fear_greed_index(), timeout=min(5.0, budget.remaining()))
    except TimeoutError:
        logger.debug("Fear & Greed : délai dépassé, ignoré")
        return None


async def _btc_dominance(budget: _Budget) -> float | None:
    try:
        return await asyncio.wait_for(price_feed.btc_dominance(), timeout=min(5.0, budget.remaining()))
    except TimeoutError:
        logger.debug("Dominance BTC : délai dépassé, enrichissement ignoré")
    except Exception as exc:  # noqa: BLE001
        logger.debug("BTC dominance fetch failed (optional enrichment): %s", exc)
    return None


async def _add_cash_like(total_value: Decimal, cash_like_qty: dict[str, Decimal], budget: _Budget) -> Decimal:
    for sym, qty in cash_like_qty.items():
        try:
            pegged = await asyncio.wait_for(peg_quote(sym.upper(), "EUR"), timeout=min(3.0, budget.remaining()))
            p = pegged.price if pegged is not None else Decimal("1")
            total_value += qty * p
        except Exception:  # noqa: BLE001
            total_value += qty
    return total_value


class CyclesMixin(PredictionCore):
    async def get_market_cycle(self, db: AsyncSession, user_id: str) -> dict[str, Any]:
        """Cycle de marché global et régime par actif ; les données externes partagent un budget unique de 12 s.

        Le budget est un compte à rebours commun (appliqué appel par appel, il s'additionnait) et borne chaque
        actif séparément : un symbole absent du cache ne prive pas les autres de leur analyse.
        """
        budget = _Budget()
        ref = await self._market_reference(budget)
        book = await self._portfolio_cycle(db, user_id, ref, budget)

        total_value_f = float(book.total_value)
        portfolio_probs = portfolio_probabilities(book.regime_weighted, total_value_f)
        portfolio_dominant = max(portfolio_probs, key=lambda p: portfolio_probs[p])

        btc_ctx, cycle_position = market_cycle_position(ref)
        advice = cycle_advice(
            ref.btc_regime["dominant_regime"] if ref.btc_regime else "unknown",
            cycle_position,
            ref.fear_greed,
            portfolio_value=total_value_f,
            max_risk_weight=max_value_weight(book.per_asset, total_value_f),
        )
        estimates = await self._top_bottom_estimates(ref, book.per_asset, cycle_position, btc_ctx)
        diagnostic = await distribution_diagnostic(book.per_asset, ref.btc_prices, total_value_f)

        return {
            "market_regime": ref.btc_regime,
            "market_signals": ref.btc_signals,
            "portfolio_regime": {
                "dominant_regime": portfolio_dominant,
                "probabilities": portfolio_probs,
            },
            "per_asset": book.per_asset,
            "cycle_position": cycle_position,
            "cycle_advice": advice,
            "fear_greed": ref.fear_greed,
            "btc_dominance": round(ref.btc_dominance, 1) if ref.btc_dominance else None,
            "display_thresholds": at.build_display_thresholds(btc_ctx),
            "top_bottom_estimates": estimates,
            "distribution_diagnostic": diagnostic,
            "time_to_pivot": time_to_pivot(cycle_position, ref.btc_regime, estimates.get("btc")),
        }

    def estimate_top_bottom(
        self,
        symbol: str,
        prices: list[float],
        current_price: float,
        regime_info: dict[str, Any] | None = None,
        cycle_position: float | None = None,
        ctx: MarketContext | None = None,
    ) -> dict[str, Any]:
        """Prochain creux et prochain sommet (prix et date) d'un actif ; ``ctx`` est accepté mais inutilisé."""
        return top_bottom_estimate(symbol, prices, current_price, regime_info, cycle_position)

    async def _market_reference(self, budget: _Budget) -> MarketReference:
        btc_prices = (await local_series("BTC", HISTORY_DAYS)).prices or None
        if not btc_prices:
            logger.warning("Historique BTC absent de la base — analyse rendue sans référence de marché")

        ref = MarketReference(btc_prices, await _fear_greed(budget), await _btc_dominance(budget))
        if btc_prices and len(btc_prices) >= 7:
            try:
                btc_result = self.regime_detector.detect(
                    btc_prices,
                    "BTC",
                    ref.fear_greed,
                    ref.btc_dominance,
                    asset_type="crypto",
                )
                ref.btc_regime = {
                    "dominant_regime": btc_result.dominant_regime,
                    "confidence": btc_result.confidence,
                    "probabilities": btc_result.probabilities,
                    "description": btc_result.description,
                }
                ref.btc_signals = [
                    {
                        "name": s.name,
                        "value": s.value,
                        "signal": s.signal,
                        "strength": s.strength,
                        "description": s.description,
                    }
                    for s in btc_result.signals
                ]
            except Exception as e:  # noqa: BLE001
                logger.warning("BTC regime detection failed: %s", e)
        return ref

    async def _portfolio_cycle(
        self, db: AsyncSession, user_id: str, ref: MarketReference, budget: _Budget
    ) -> PortfolioCycle:
        book = PortfolioCycle()
        portfolio_ids = await user_portfolio_ids(db, user_id)
        if not portfolio_ids:
            return book

        holdings = group_holdings(await held_assets(db, portfolio_ids))
        book.total_value = await _add_cash_like(book.total_value, holdings.cash_like, budget)

        top_assets = list(holdings.assets.values())[:7]
        hist_map, price_map = await self._prefetch(top_assets, ref.btc_prices, budget)

        for asset in top_assets:
            try:
                price = price_map.get(asset.symbol)
                if not price:
                    continue
                value_dec = Decimal(str(price)) * holdings.quantities[asset.symbol]
                book.total_value += value_dec
                value = float(value_dec)

                a_prices = hist_map.get(asset.symbol)
                if a_prices and len(a_prices) >= 7:
                    row = asset_cycle_row(self.regime_detector, asset, value, a_prices, ref)
                    book.per_asset.append(row)
                    for phase, prob in row["probabilities"].items():
                        book.regime_weighted[phase] += prob * value
            except Exception as e:  # noqa: BLE001
                logger.warning("Market cycle error for %s: %s", asset.symbol, e)
        return book

    async def _prefetch(
        self, assets: Sequence[Asset], btc_prices: list[float] | None, budget: _Budget
    ) -> tuple[dict[str, list[float]], dict[str, float | None]]:
        async def history(a: Asset) -> tuple[str, list[float]]:
            sym = a.symbol
            if sym == "BTC" and btc_prices:
                p = btc_prices[-90:] if len(btc_prices) > 90 else list(btc_prices)
                return (sym, p)
            return (sym, (await local_series(sym, 90)).prices)

        async def price(a: Asset) -> tuple[str, float | None]:
            try:
                p = await self._get_current_price(a.symbol, a.asset_type)
                return (a.symbol, p)
            except Exception:  # noqa: BLE001
                return (a.symbol, 0)

        hist_results, price_results = await asyncio.gather(
            asyncio.gather(*[_bounded(history(a), (a.symbol, []), budget) for a in assets]),
            asyncio.gather(*[_bounded(price(a), (a.symbol, 0), budget) for a in assets]),
        )
        return dict(hist_results), dict(price_results)

    async def _top_bottom_estimates(
        self,
        ref: MarketReference,
        per_asset: list[dict[str, Any]],
        cycle_position: int,
        btc_ctx: MarketContext | None,
    ) -> dict[str, Any]:
        estimates: dict[str, Any] = {"btc": None, "per_asset": []}
        btc_prices = ref.btc_prices
        if btc_prices and len(btc_prices) >= 30:
            try:
                btc_current = float(btc_prices[-1])
                estimates["btc"] = self.estimate_top_bottom(
                    "BTC",
                    btc_prices,
                    btc_current,
                    regime_info=ref.btc_regime,
                    cycle_position=cycle_position,
                    ctx=btc_ctx,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("BTC top/bottom estimate failed: %s", e)

        for asset_data in per_asset:
            sym = asset_data["symbol"]
            if sym == "BTC":
                if estimates["btc"]:
                    estimates["per_asset"].append(estimates["btc"])
                continue
            try:
                est = await self._asset_top_bottom(asset_data, ref.fear_greed)
                if est is not None:
                    estimates["per_asset"].append(est)
            except Exception as e:  # noqa: BLE001
                logger.debug("Top/bottom estimate failed for %s: %s", sym, e)
        return estimates

    async def _asset_top_bottom(self, asset_data: dict[str, Any], fear_greed: int | None) -> dict[str, Any] | None:
        sym = asset_data["symbol"]
        a_prices = (await local_series(sym, HISTORY_DAYS)).prices or None
        if not (a_prices and len(a_prices) >= 30):
            return None
        a_regime = {
            "dominant_regime": asset_data.get("dominant_regime", "neutral"),
            "confidence": asset_data.get("confidence", 0.5),
        }
        asset_ctx = compute_market_context(a_prices, sym, asset_data.get("asset_type", "crypto"), fear_greed)
        asset_cyc_pos = round(at.cycle_position(asset_ctx, regime_probs=asset_data.get("probabilities")))
        return self.estimate_top_bottom(
            sym,
            a_prices,
            float(a_prices[-1]),
            regime_info=a_regime,
            cycle_position=asset_cyc_pos,
            ctx=asset_ctx,
        )
