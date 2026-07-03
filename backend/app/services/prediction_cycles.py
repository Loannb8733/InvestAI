"""Market-cycle analysis, extracted from the prediction god-module.

``PredictionCyclesMixin`` is mixed into ``PredictionService``; its methods call
sibling methods via ``self`` and resolve through the MRO, so behaviour is
unchanged. Split out purely to shrink the 3.7k-line service.
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import cache_history, get_cached_history
from app.ml import adaptive_thresholds as at
from app.ml.market_context import MarketContext, compute_market_context
from app.ml.regime_detector import MarketRegimeDetector, RegimeConfig, RegimeResult, _rsi
from app.models.asset import Asset
from app.models.portfolio import Portfolio
from app.services.metrics_service import is_cash_like, is_safe_haven
from app.services.prediction_types import _HISTORY_DAYS
from app.services.price_service import PriceService

logger = logging.getLogger(__name__)


class PredictionCyclesMixin:
    async def get_market_cycle(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> Dict:
        """Analyse de cycle de marche globale avec regime par actif."""
        import httpx as _httpx

        # ── 1. BTC as market reference ───────────────────────────────
        btc_prices = None
        for try_days in [_HISTORY_DAYS, 90]:
            btc_hist = await get_cached_history("BTC", "crypto", try_days)
            if btc_hist and btc_hist.get("prices"):
                btc_prices = btc_hist["prices"]
                break
        if not btc_prices:
            btc_dates, btc_prices = await self.data_fetcher.get_crypto_history("BTC", days=_HISTORY_DAYS)
            if btc_dates and btc_prices:
                await cache_history(
                    "BTC",
                    "crypto",
                    _HISTORY_DAYS,
                    {"dates": [d.isoformat() for d in btc_dates], "prices": btc_prices},
                )

        # Fear & Greed
        fear_greed = None
        try:
            async with _httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get("https://api.alternative.me/fng/?limit=1")
                if resp.status_code == 200:
                    fng_data = resp.json()
                    if fng_data.get("data"):
                        fear_greed = int(fng_data["data"][0].get("value", 50))
        except Exception:
            pass

        btc_dominance = None
        try:
            btc_dominance = await self.data_fetcher.get_btc_dominance()
        except Exception:
            pass

        # BTC regime (market reference)
        btc_regime = None
        btc_signals = []
        if btc_prices and len(btc_prices) >= 7:
            try:
                btc_result = self.regime_detector.detect(
                    btc_prices,
                    "BTC",
                    fear_greed,
                    btc_dominance,
                    asset_type="crypto",
                )
                btc_regime = {
                    "dominant_regime": btc_result.dominant_regime,
                    "confidence": btc_result.confidence,
                    "probabilities": btc_result.probabilities,
                    "description": btc_result.description,
                }
                btc_signals = [
                    {
                        "name": s.name,
                        "value": s.value,
                        "signal": s.signal,
                        "strength": s.strength,
                        "description": s.description,
                    }
                    for s in btc_result.signals
                ]
            except Exception as e:
                logger.warning("BTC regime detection failed: %s", e)

        # ── 2. Per-asset regime ──────────────────────────────────────
        result = await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
        portfolios = result.scalars().all()
        portfolio_ids = [p.id for p in portfolios]

        per_asset = []
        total_value = Decimal("0")
        regime_weighted = {"bearish": 0.0, "bottom": 0.0, "bullish": 0.0, "top": 0.0}

        if portfolio_ids:
            result = await db.execute(
                select(Asset).where(
                    Asset.portfolio_id.in_(portfolio_ids),
                    Asset.quantity > 0,
                )
            )
            assets = result.scalars().all()

            # Deduplicate (Decimal precision)
            asset_map: Dict[str, object] = {}
            qty_map: Dict[str, Decimal] = {}
            cash_like_qty: Dict[str, Decimal] = {}
            for a in assets:
                sym = a.symbol
                qty = Decimal(str(a.quantity))
                if is_cash_like(sym):
                    cash_like_qty[sym] = cash_like_qty.get(sym, Decimal("0")) + qty
                    continue
                if sym not in asset_map:
                    asset_map[sym] = a
                    qty_map[sym] = qty
                else:
                    qty_map[sym] += qty

            # Include cash-like value in total for accurate weight calculation
            for sym, qty in cash_like_qty.items():
                try:
                    if PriceService.is_stablecoin(sym):
                        p = await self.price_service._stablecoin_price_eur(sym)
                    else:
                        p = Decimal("1")
                    total_value += qty * p
                except Exception:
                    total_value += qty

            # ── Pre-fetch histories + prices in parallel ──────────────
            import asyncio as _aio

            _top_assets = list(asset_map.values())[:7]

            async def _prefetch_history(a: object) -> tuple:
                """Return (symbol, prices) — fetches from cache then network."""
                sym = a.symbol
                atype = a.asset_type.value
                if sym == "BTC" and btc_prices:
                    p = btc_prices[-90:] if len(btc_prices) > 90 else list(btc_prices)
                    return (sym, p)
                for try_days in [_HISTORY_DAYS, 90]:
                    cached = await get_cached_history(sym, atype, try_days)
                    if cached and cached.get("prices"):
                        p = cached["prices"]
                        return (sym, p[-90:] if len(p) > 90 else p)
                try:
                    a_dates, a_prices = await self.data_fetcher.get_history(sym, atype, days=90)
                    if a_dates and a_prices:
                        await cache_history(
                            sym,
                            atype,
                            90,
                            {
                                "dates": [d.isoformat() for d in a_dates],
                                "prices": a_prices,
                            },
                        )
                        return (sym, a_prices)
                except Exception:
                    logger.warning("Failed to fetch history for %s, skipping", sym)
                return (sym, [])

            async def _prefetch_price(a: object) -> tuple:
                """Return (symbol, price)."""
                try:
                    p = await self._get_current_price(a.symbol, a.asset_type)
                    return (a.symbol, p)
                except Exception:
                    return (a.symbol, 0)

            _hist_results, _price_results = await _aio.gather(
                _aio.gather(*[_prefetch_history(a) for a in _top_assets]),
                _aio.gather(*[_prefetch_price(a) for a in _top_assets]),
            )
            _hist_map: Dict[str, list] = {sym: prices for sym, prices in _hist_results}
            _price_map: Dict[str, float] = {sym: price for sym, price in _price_results}

            for asset in _top_assets:
                try:
                    price = _price_map.get(asset.symbol, 0)
                    if price == 0:
                        continue
                    price_dec = Decimal(str(price))
                    qty_dec = qty_map[asset.symbol]
                    value_dec = price_dec * qty_dec
                    total_value += value_dec
                    value = float(value_dec)

                    a_prices = _hist_map.get(asset.symbol)

                    if a_prices and len(a_prices) >= 7:
                        # Bear market indicators
                        ath = max(a_prices)
                        drawdown_from_ath = round((a_prices[-1] / ath - 1) * 100, 1) if ath > 0 else 0.0
                        btc_corr = None
                        if btc_prices and asset.symbol != "BTC" and len(a_prices) >= 20:
                            try:
                                _bp = btc_prices[-len(a_prices) :] if len(btc_prices) >= len(a_prices) else btc_prices
                                _min = min(len(_bp), len(a_prices))
                                if _min >= 20:
                                    _br = np.diff(np.log(np.array(_bp[-_min:], dtype=float)))
                                    _ar = np.diff(np.log(np.array(a_prices[-_min:], dtype=float)))
                                    btc_corr = round(float(np.corrcoef(_br, _ar)[0, 1]), 2)
                            except Exception:
                                pass

                        # For BTC, reuse the market-reference regime to avoid
                        # inconsistency between "Régime BTC" card and per-asset table
                        if asset.symbol == "BTC" and btc_regime:
                            _btc_rr = RegimeResult(
                                symbol=asset.symbol,
                                probabilities=btc_regime["probabilities"],
                                dominant_regime=btc_regime["dominant_regime"],
                                confidence=btc_regime["confidence"],
                                signals=[],
                                description="",
                            )
                            per_asset.append(
                                {
                                    "symbol": asset.symbol,
                                    "name": asset.name,
                                    "asset_type": asset.asset_type.value,
                                    "value": round(value, 2),
                                    "dominant_regime": btc_regime["dominant_regime"],
                                    "regime_6phase": MarketRegimeDetector.refine_to_6phase(_btc_rr, a_prices),
                                    "confidence": btc_regime["confidence"],
                                    "probabilities": btc_regime["probabilities"],
                                    "drawdown_from_ath": drawdown_from_ath,
                                    "btc_correlation": None,  # BTC correlation with itself is 1.0
                                    "is_resilient": is_safe_haven(asset.symbol),
                                }
                            )
                        else:
                            a_regime = self.regime_detector.detect(
                                a_prices,
                                asset.symbol,
                                fear_greed,
                                btc_dominance,
                                asset_type=asset.asset_type.value,
                            )
                            per_asset.append(
                                {
                                    "symbol": asset.symbol,
                                    "name": asset.name,
                                    "asset_type": asset.asset_type.value,
                                    "value": round(value, 2),
                                    "dominant_regime": a_regime.dominant_regime,
                                    "regime_6phase": MarketRegimeDetector.refine_to_6phase(a_regime, a_prices),
                                    "confidence": a_regime.confidence,
                                    "probabilities": a_regime.probabilities,
                                    "drawdown_from_ath": drawdown_from_ath,
                                    "btc_correlation": btc_corr,
                                    "is_resilient": is_safe_haven(asset.symbol),
                                }
                            )
                        # Accumulate regime weights from whichever branch was used
                        last_probs = per_asset[-1]["probabilities"] if per_asset else {}
                        for phase, prob in last_probs.items():
                            regime_weighted[phase] += prob * value
                except Exception as e:
                    logger.warning("Market cycle error for %s: %s", asset.symbol, e)

        # ── 3. Weighted portfolio regime ──────────────────────────────
        total_value_f = float(total_value)
        if total_value_f > 0:
            portfolio_probs = {p: round(v / total_value_f, 4) for p, v in regime_weighted.items()}
        else:
            portfolio_probs = {p: 0.25 for p in regime_weighted}
        portfolio_dominant = max(portfolio_probs, key=portfolio_probs.get)

        # ── 4. Cycle position (0-100) — regime-based ─────────────────
        # Uses regime probabilities as primary signal + market context refinement
        btc_ctx: Optional[MarketContext] = None
        btc_probs = btc_regime.get("probabilities") if btc_regime else None
        if btc_prices and len(btc_prices) >= 30:
            btc_ctx = compute_market_context(btc_prices, "BTC", "crypto", fear_greed)
            cycle_position = round(at.cycle_position(btc_ctx, regime_probs=btc_probs))
        else:
            # Fallback: simple map when no context available
            cycle_map = {"bottom": 10, "bullish": 40, "top": 75, "bearish": 85}
            cycle_position = cycle_map.get(btc_regime["dominant_regime"] if btc_regime else "bearish", 50)

        # ── 5. Cycle-specific advice (with live portfolio context) ──
        max_rw = 0.0
        if per_asset:
            # Approximate risk_weight from value concentration (actual
            # risk_weight requires metrics_service, but value weight is a
            # fast proxy available here).
            values = [a["value"] for a in per_asset if a.get("value", 0) > 0]
            if values and total_value_f > 0:
                max_rw = max(v / total_value_f * 100 for v in values)

        cycle_advice = self._get_cycle_advice(
            btc_regime["dominant_regime"] if btc_regime else "unknown",
            cycle_position,
            fear_greed,
            portfolio_value=total_value_f,
            max_risk_weight=max_rw,
        )

        # ── 6. Top/Bottom estimates (price + date) ─────────────────
        top_bottom_estimates = {"btc": None, "per_asset": []}

        # BTC estimate
        if btc_prices and len(btc_prices) >= 30:
            try:
                btc_current = float(btc_prices[-1])
                top_bottom_estimates["btc"] = self.estimate_top_bottom(
                    "BTC",
                    btc_prices,
                    btc_current,
                    regime_info=btc_regime,
                    cycle_position=cycle_position,
                    ctx=btc_ctx,
                )
            except Exception as e:
                logger.warning("BTC top/bottom estimate failed: %s", e)

        # Per-asset estimates (reuse prices already fetched for regime detection)
        for asset_data in per_asset:
            sym = asset_data["symbol"]
            if sym == "BTC":
                # Reuse BTC estimate
                if top_bottom_estimates["btc"]:
                    top_bottom_estimates["per_asset"].append(top_bottom_estimates["btc"])
                continue
            try:
                # Fetch prices for this asset (check cache first)
                a_prices_tb = None
                for try_d in [_HISTORY_DAYS, 90]:
                    cached_h = await get_cached_history(sym, asset_data.get("asset_type", "crypto"), try_d)
                    if cached_h and cached_h.get("prices"):
                        a_prices_tb = cached_h["prices"]
                        break
                if a_prices_tb and len(a_prices_tb) >= 30:
                    a_current = float(a_prices_tb[-1])
                    a_regime = {
                        "dominant_regime": asset_data.get("dominant_regime", "neutral"),
                        "confidence": asset_data.get("confidence", 0.5),
                    }
                    # Compute per-asset MarketContext and cycle_position
                    asset_ctx = compute_market_context(
                        a_prices_tb,
                        sym,
                        asset_data.get("asset_type", "crypto"),
                        fear_greed,
                    )
                    asset_probs = asset_data.get("probabilities")
                    asset_cyc_pos = round(at.cycle_position(asset_ctx, regime_probs=asset_probs))
                    est = self.estimate_top_bottom(
                        sym,
                        a_prices_tb,
                        a_current,
                        regime_info=a_regime,
                        cycle_position=asset_cyc_pos,
                        ctx=asset_ctx,
                    )
                    top_bottom_estimates["per_asset"].append(est)
            except Exception as e:
                logger.debug("Top/bottom estimate failed for %s: %s", sym, e)

        # ── 7. Distribution diagnostic ────────────────────────────────
        # Flag assets in distribution phase (top/bearish regime + high cycle
        # position) and cross-reference with RSI / momentum weakness.
        distribution_diagnostic: List[Dict] = []
        for asset_data in per_asset:
            dom = asset_data.get("dominant_regime", "")
            probs = asset_data.get("probabilities", {})
            top_prob = probs.get("top", 0) + probs.get("bearish", 0)
            if top_prob < 0.40:
                continue  # not in distribution zone

            sym = asset_data["symbol"]
            # Try to compute RSI for this asset
            rsi_val = None
            a_prices_diag = None
            for try_d in [_HISTORY_DAYS, 90]:
                cached_h = await get_cached_history(sym, asset_data.get("asset_type", "crypto"), try_d)
                if cached_h and cached_h.get("prices"):
                    a_prices_diag = cached_h["prices"]
                    break
            if sym == "BTC" and btc_prices:
                a_prices_diag = btc_prices

            if a_prices_diag and len(a_prices_diag) >= 15:
                rsi_val = _rsi(a_prices_diag, period=14)

            # Build diagnostic entry
            signals = []
            sell_priority = "low"
            if rsi_val is not None and rsi_val > 70:
                signals.append(f"RSI suracheté ({rsi_val:.0f})")
                sell_priority = "high"
            if dom == "top":
                signals.append("Régime Sommet détecté")
                sell_priority = "high" if sell_priority != "high" else sell_priority
            if probs.get("bearish", 0) > 0.25:
                signals.append(f"Probabilité baissière {probs['bearish']*100:.0f}%")
                sell_priority = "medium" if sell_priority == "low" else sell_priority

            weight_pct = 0.0
            if total_value_f > 0 and asset_data.get("value", 0) > 0:
                weight_pct = asset_data["value"] / total_value_f * 100

            distribution_diagnostic.append(
                {
                    "symbol": sym,
                    "name": asset_data.get("name", sym),
                    "dominant_regime": dom,
                    "top_bearish_prob": round(top_prob * 100, 1),
                    "rsi": round(rsi_val, 1) if rsi_val is not None else None,
                    "weight_pct": round(weight_pct, 1),
                    "signals": signals,
                    "sell_priority": sell_priority,
                }
            )

        # Sort by sell priority (high first)
        priority_order = {"high": 0, "medium": 1, "low": 2}
        distribution_diagnostic.sort(key=lambda d: priority_order.get(d["sell_priority"], 3))

        # ── 8. Time-to-Pivot estimation ──────────────────────────────
        # Estimate days until the next phase change based on OU theta
        # and current cycle position relative to phase boundaries.
        time_to_pivot = self._estimate_time_to_pivot(
            cycle_position,
            btc_regime,
            top_bottom_estimates.get("btc"),
        )

        return {
            "market_regime": btc_regime,
            "market_signals": btc_signals,
            "portfolio_regime": {
                "dominant_regime": portfolio_dominant,
                "probabilities": portfolio_probs,
            },
            "per_asset": per_asset,
            "cycle_position": cycle_position,
            "cycle_advice": cycle_advice,
            "fear_greed": fear_greed,
            "btc_dominance": round(btc_dominance, 1) if btc_dominance else None,
            "display_thresholds": at.build_display_thresholds(btc_ctx),
            "top_bottom_estimates": top_bottom_estimates,
            "distribution_diagnostic": distribution_diagnostic,
            "time_to_pivot": time_to_pivot,
        }

    @staticmethod
    def _estimate_time_to_pivot(
        cycle_position: int,
        btc_regime: Optional[Dict],
        btc_estimate: Optional[Dict],
    ) -> Dict:
        """Estimate days until the next cycle phase transition.

        Uses cycle_position distance to the nearest phase boundary and
        OU theta from btc_estimate to gauge mean-reversion speed.

        Phase boundaries: 0-15 (Creux), 15-40 (Accumulation),
        40-65 (Expansion), 65-85 (Distribution), 85-100 (Euphorie).
        """
        phases = [
            (0, 15, "Creux", "Accumulation"),
            (15, 40, "Accumulation", "Expansion"),
            (40, 65, "Expansion", "Distribution"),
            (65, 85, "Distribution", "Euphorie"),
            (85, 100, "Euphorie", "Creux"),
        ]

        current_phase = "Inconnu"
        next_phase = "Inconnu"
        distance_to_boundary = 50  # default

        for lo, hi, name, nxt in phases:
            if lo <= cycle_position < hi:
                current_phase = name
                next_phase = nxt
                distance_to_boundary = hi - cycle_position
                break
        # Edge case: exactly 100
        if cycle_position >= 100:
            current_phase = "Euphorie"
            next_phase = "Creux"
            distance_to_boundary = 5

        # Base estimate: 1 cycle position unit ≈ 1-3 days
        # Use OU theta to modulate: higher theta = faster transitions
        theta = 0.02  # default
        if btc_estimate and btc_estimate.get("ou_parameters"):
            theta = btc_estimate["ou_parameters"].get("theta", 0.02)

        # Faster mean-reversion → quicker phase transitions
        # theta 0.01 → ~2.5 days/unit, theta 0.05 → ~1.0 day/unit
        days_per_unit = max(0.8, 2.5 - (theta - 0.01) * 37.5)
        estimated_days = max(3, round(distance_to_boundary * days_per_unit))
        estimated_days = min(estimated_days, 90)  # cap at 90 days

        # Confidence based on regime clarity
        confidence = 0.5
        if btc_regime:
            confidence = min(0.85, max(0.2, btc_regime.get("confidence", 0.5)))

        return {
            "current_phase": current_phase,
            "next_phase": next_phase,
            "estimated_days": estimated_days,
            "confidence": round(confidence, 2),
            "cycle_position": cycle_position,
        }

    def estimate_top_bottom(
        self,
        symbol: str,
        prices: List[float],
        current_price: float,
        regime_info: Optional[Dict] = None,
        cycle_position: Optional[float] = None,
        ctx: Optional[MarketContext] = None,
    ) -> Dict:
        """Estimate next market top and bottom (price + date) for an asset.

        Uses Ornstein-Uhlenbeck mean-reversion parameters, support/resistance
        clustering, and historical percentiles.
        """
        arr = np.array(prices, dtype=float)
        n = len(arr)
        today = datetime.now(timezone.utc)

        # ── OU parameters (mu, theta, sigma) ──────────────────────────
        if n >= 200:
            mu = float(np.mean(arr[-200:]))
        else:
            mu = float(np.median(arr))

        log_prices = np.log(np.maximum(arr, 1e-10))
        log_returns = np.diff(log_prices)

        if n >= 10:
            y = log_prices[1:]
            x = log_prices[:-1]
            x_mean = float(np.mean(x))
            cov_xy = float(np.mean((x - x_mean) * (y - float(np.mean(y)))))
            var_x = float(np.var(x))
            phi = cov_xy / max(var_x, 1e-15)
            phi = float(np.clip(phi, 0.01, 0.999))
            theta = -np.log(phi)
        else:
            theta = 0.05
            phi = 0.95

        sigma = float(np.std(log_returns)) if len(log_returns) > 1 else 0.02

        # ── Support / Resistance ──────────────────────────────────────
        support, resistance = self._compute_support_resistance(prices, current_price)

        # ── Historical percentiles ────────────────────────────────────
        p5 = float(np.percentile(arr, 5))
        p95 = float(np.percentile(arr, 95))
        p10 = float(np.percentile(arr, 10))
        p90 = float(np.percentile(arr, 90))

        # ── Regime context ────────────────────────────────────────────
        regime = regime_info.get("dominant_regime", "neutral") if regime_info else "neutral"
        regime_conf = regime_info.get("confidence", 0.5) if regime_info else 0.5
        cyc_pos = cycle_position if cycle_position is not None else 50.0

        # ── BOTTOM estimation ─────────────────────────────────────────
        if current_price > mu:
            # Price above mean: bottom is the mean or support below mean
            bottom_price = max(support, min(mu * 0.95, p10))
        else:
            # Price already below mean: bottom is deeper support or P5
            bottom_price = max(p5, min(support, current_price * 0.85))

        # Ensure bottom < current price (use sigma-based minimum distance)
        min_bottom_distance = max(0.05, sigma * np.sqrt(30) * 1.5)  # at least 1.5σ√30
        bottom_price = min(bottom_price, current_price * (1 - min_bottom_distance))

        # Time to bottom: combine OU-based estimate with volatility-based estimate
        # OU estimate (how long mean-reversion takes)
        ou_bottom_days = 30  # default
        if current_price > bottom_price and theta > 1e-4:
            if abs(current_price - mu) > 1e-10 and abs(bottom_price - mu) > 1e-10:
                ratio = abs(bottom_price - mu) / abs(current_price - mu)
                ratio = float(np.clip(ratio, 0.01, 0.99))
                ou_bottom_days = int(-np.log(ratio) / theta)
            else:
                ou_bottom_days = int(2.3 / theta)

        # Volatility-based estimate: how many days of sigma-sized moves to
        # cover the distance from current to bottom
        price_distance_pct = abs(current_price - bottom_price) / current_price
        daily_move = sigma if sigma > 0.005 else 0.02  # daily log-volatility
        vol_bottom_days = max(5, int(price_distance_pct / daily_move))

        # Blend: use the larger of the two (more conservative), but cap OU
        # contribution to avoid extreme values from tiny theta
        ou_bottom_days = min(ou_bottom_days, 120)  # cap OU estimate
        bottom_days = max(vol_bottom_days, (ou_bottom_days + vol_bottom_days) // 2)

        # Asset-specific adjustment: combine volatility + mean-reversion speed
        # More volatile & faster mean-reversion = faster cycle
        # sigma: 0.02->1.0x, 0.04->0.85x, 0.06->0.7x
        vol_factor = max(0.5, 1.0 - (sigma - 0.02) * 7.5)
        # theta: higher theta = faster reversion = shorter time
        # theta 0.005->1.0x, 0.01->0.9x, 0.05->0.5x
        theta_factor = max(0.5, 1.0 - (theta - 0.005) * 11)
        asset_adj = (vol_factor + theta_factor) / 2
        bottom_days = max(3, int(bottom_days * asset_adj))

        # Adjust by cycle position: if near bottom already, shorten estimate
        if cyc_pos < 15:
            bottom_days = max(3, int(bottom_days * 0.4))
        elif cyc_pos < 30:
            bottom_days = max(5, int(bottom_days * 0.65))

        bottom_days = max(3, min(180, bottom_days))
        bottom_date = (today + timedelta(days=bottom_days)).strftime("%Y-%m-%d")

        # ── TOP estimation ────────────────────────────────────────────
        if current_price < mu:
            # Price below mean: top is the mean or resistance above mean
            top_price = min(resistance, max(mu * 1.05, p90))
        else:
            # Price already above mean: top is higher resistance or P95
            top_price = min(p95, max(resistance, current_price * 1.15))

        # Ensure top > current price (use sigma-based minimum distance)
        min_top_distance = max(0.05, sigma * np.sqrt(60) * 1.5)  # at least 1.5σ√60
        top_price = max(top_price, current_price * (1 + min_top_distance))

        # Time to top: price must first reach bottom then recover to top
        # Volatility-based recovery estimate
        top_distance_pct = abs(top_price - bottom_price) / max(bottom_price, 1e-10)
        vol_recovery_days = max(10, int(top_distance_pct / daily_move))

        # OU-based recovery estimate
        ou_recovery_days = 60  # default
        if theta > 1e-4:
            distance_bottom_to_top = abs(top_price - bottom_price)
            distance_bottom_to_mu = abs(mu - bottom_price)
            if distance_bottom_to_mu > 1e-10 and distance_bottom_to_top > 1e-10:
                ratio = min(0.99, distance_bottom_to_mu / distance_bottom_to_top)
                ratio = max(0.01, ratio)
                ou_recovery_days = min(120, int(-np.log(ratio) / theta))

        recovery_days = max(vol_recovery_days, (ou_recovery_days + vol_recovery_days) // 2)
        top_days = bottom_days + max(10, recovery_days)

        # Adjust by cycle position: if near top already, shorten estimate
        if cyc_pos > 85:
            top_days = max(14, int(top_days * 0.3))
        elif cyc_pos > 70:
            top_days = max(14, int(top_days * 0.6))

        # Apply same asset-specific adjustment
        top_days = max(bottom_days + 7, int(top_days * asset_adj))

        # Ensure top_days > bottom_days
        top_days = max(bottom_days + 7, min(180, top_days))
        top_date = (today + timedelta(days=top_days)).strftime("%Y-%m-%d")

        # ── Confidence calculation ────────────────────────────────────
        # Weighted average (not min) so one weak factor doesn't crush confidence
        theta_reliability = min(1.0, theta / 0.05)  # theta > 0.05 = decent reversion
        data_sufficiency = min(1.0, n / 120)  # 120 days is sufficient
        # Weights: regime clarity 50%, theta reliability 25%, data 25%
        raw_conf = regime_conf * 0.50 + theta_reliability * 0.25 + data_sufficiency * 0.25
        confidence = round(
            max(0.15, min(0.85, raw_conf)),
            2,
        )

        # Distance from current price
        bottom_distance_pct = round((current_price - bottom_price) / current_price * 100, 1)
        top_distance_pct = round((top_price - current_price) / current_price * 100, 1)

        return {
            "symbol": symbol,
            "current_price": round(current_price, 2),
            "next_bottom": {
                "estimated_price": round(bottom_price, 2),
                "estimated_days": bottom_days,
                "estimated_date": bottom_date,
                "confidence": confidence,
                "distance_pct": bottom_distance_pct,
                "method": "OU mean-reversion + support clustering",
                "support_level": round(support, 2),
            },
            "next_top": {
                "estimated_price": round(top_price, 2),
                "estimated_days": top_days,
                "estimated_date": top_date,
                "confidence": confidence,
                "distance_pct": top_distance_pct,
                "method": "OU mean-reversion + resistance clustering",
                "resistance_level": round(resistance, 2),
            },
            "current_regime": regime,
            "cycle_position": round(cyc_pos, 1),
            "ou_parameters": {
                "mu": round(mu, 2),
                "theta": round(theta, 4),
                "sigma": round(sigma, 4),
            },
        }

    @staticmethod
    def _get_cycle_advice(
        regime: str,
        cycle_pos: int,
        fear_greed: Optional[int],
        portfolio_value: float = 0.0,
        max_risk_weight: float = 0.0,
    ) -> List[Dict]:
        """Generate actionable advice based on market cycle position.

        Args:
            regime: Market regime (bottom/bearish/bullish/top).
            cycle_pos: 0-100 cycle position.
            fear_greed: Fear & Greed index (0-100).
            portfolio_value: User's live portfolio value in €.
            max_risk_weight: Highest risk_weight (%) among held assets.
        """
        advice = []

        # ── Risk guard: warn if portfolio is already highly concentrated ──
        RISK_WEIGHT_CAP = 60.0  # % — single asset > 60% of total risk = danger
        if max_risk_weight > RISK_WEIGHT_CAP:
            advice.append(
                {
                    "title": "Concentration de risque élevée",
                    "description": (
                        f"Un actif représente {max_risk_weight:.0f}% de votre risque total. "
                        "Tout achat supplémentaire sur cet actif augmenterait dangereusement "
                        "votre exposition. Privilégiez la diversification."
                    ),
                    "action": "DIVERSIFIER",
                    "priority": "critical",
                }
            )

        # ── DCA amount suggestion based on real portfolio value ──
        # risk_multiplier adjusts DCA sizing: 1.5× in bear (accumulate!) → 0.5× in bull
        _rcfg = RegimeConfig.from_regime(regime)
        _risk_mult = _rcfg.risk_multiplier

        def _dca_hint() -> str:
            if portfolio_value <= 0:
                return ""
            # Base: 2-5% of portfolio, scaled by regime risk_multiplier
            low = round(portfolio_value * 0.02 * _risk_mult, 2)
            high = round(portfolio_value * 0.05 * _risk_mult, 2)
            return f" Montant suggéré par tranche : {low:.0f}–{high:.0f} € ({_risk_mult:.1f}× régime)."

        if regime == "bottom" or (fear_greed and fear_greed < 20):
            advice.append(
                {
                    "title": "Zone d'accumulation",
                    "description": (
                        "Les indicateurs suggèrent un creux potentiel. C'est historiquement "
                        "le meilleur moment pour accumuler via DCA (achat périodique). "
                        "Ne tentez pas de timer le bottom exact — étalez vos achats." + _dca_hint()
                    ),
                    "action": "DCA",
                    "priority": "high",
                }
            )
            advice.append(
                {
                    "title": "Préparation au rebond",
                    "description": (
                        "Identifiez les actifs de qualité qui ont le plus corrigé. "
                        "Préparez votre watchlist pour être prêt quand le rebond se confirme."
                    ),
                    "action": "RECHERCHE",
                    "priority": "medium",
                }
            )
        elif regime == "bearish":
            advice.append(
                {
                    "title": "Zone d'accumulation — Be greedy when others are fearful",
                    "description": (
                        "Marché baissier = opportunité d'accumulation ! "
                        "Les prix sont décotés, c'est historiquement le meilleur moment "
                        "pour construire son portefeuille via DCA/VCA agressif." + _dca_hint()
                    ),
                    "action": "DCA",
                    "priority": "high",
                }
            )
            advice.append(
                {
                    "title": "Évitez le levier",
                    "description": (
                        "Accumulez avec du capital réel, jamais avec du levier. "
                        "Les liquidations en cascade amplifient les baisses en bear market."
                    ),
                    "action": "RISQUE",
                    "priority": "high",
                }
            )
            advice.append(
                {
                    "title": "VCA > DCA en bear market",
                    "description": (
                        "Le Value Cost Averaging (investir plus quand les prix baissent) "
                        "surperforme le DCA classique en marché volatile. "
                        "Augmentez vos montants d'achat quand les prix chutent davantage."
                    ),
                    "action": "VCA",
                    "priority": "medium",
                }
            )
        elif regime == "top" or (fear_greed and fear_greed > 80):
            advice.append(
                {
                    "title": "Prise de profits",
                    "description": (
                        "Signes d'euphorie — prenez des profits partiels (20-30%). "
                        "Personne ne regrette d'avoir sécurisé des gains."
                    ),
                    "action": "VENDRE",
                    "priority": "high",
                }
            )
            advice.append(
                {
                    "title": "Stop-loss protecteurs",
                    "description": (
                        "Placez des stop-loss 10-15% sous le prix actuel pour protéger "
                        "vos positions restantes en cas de correction brutale."
                    ),
                    "action": "PROTÉGER",
                    "priority": "high",
                }
            )
            advice.append(
                {
                    "title": "N'achetez pas sur l'euphorie",
                    "description": (
                        "Quand tout le monde est euphorique, c'est le pire moment pour acheter. " "Résistez au FOMO."
                    ),
                    "action": "ATTENDRE",
                    "priority": "medium",
                }
            )
        elif regime == "bullish":
            advice.append(
                {
                    "title": "Préparez la prise de profits",
                    "description": (
                        "Tendance haussière — laissez courir vos positions mais "
                        "définissez VOS niveaux de sortie maintenant. "
                        '"Be fearful when others are greedy." Ne soyez pas le dernier à vendre.'
                    ),
                    "action": "PLANIFIER",
                    "priority": "high",
                }
            )
            advice.append(
                {
                    "title": "Stop-loss progressifs",
                    "description": (
                        "Remontez progressivement vos stop-loss pour verrouiller les gains. "
                        "Un trailing stop sous l'EMA-20 protège sans couper trop tôt."
                    ),
                    "action": "PROTÉGER",
                    "priority": "high",
                }
            )
            advice.append(
                {
                    "title": "Réduisez le DCA",
                    "description": (
                        "En marché haussier, les prix sont chers. Réduisez vos montants "
                        "d'achat réguliers et gardez du cash pour accumuler au prochain creux."
                    ),
                    "action": "ATTENDRE",
                    "priority": "medium",
                }
            )
        else:
            advice.append(
                {
                    "title": "Observation",
                    "description": "Tendance incertaine — attendez un signal plus clair avant de prendre de nouvelles positions.",
                    "action": "ATTENDRE",
                    "priority": "low",
                }
            )
        return advice
