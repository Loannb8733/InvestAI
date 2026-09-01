"""Signaux alpha, carte de stratégie et scénarios « what-if ».

``PredictionAlphaMixin`` est mixé dans ``PredictionService`` : ses méthodes appellent
``self.get_price_prediction``, ``self.get_market_cycle``, ``self.data_fetcher`` et
``self.regime_detector``, fournis par la classe finale.

Extrait de ``prediction_service.py`` (ARC-05), qui dépassait 2 400 lignes. Ce bloc en
formait le tiers le plus volumineux et la responsabilité la plus autonome : classer
les actifs par signal, en dériver une matrice de décision, et simuler une allocation
alternative. Découpage à l'identique — aucune ligne de logique modifiée.
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import cache_history, get_cached_history
from app.ml.regime_detector import RegimeConfig, _rsi
from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.services.asset_classification import is_cash_like, is_safe_haven
from app.services.market_sentiment import fetch_fear_greed_index
from app.services.prediction_types import _HISTORY_DAYS  # noqa: F401 — re-exported
from app.services.prediction_types import (  # noqa: F401 — re-exported for compatibility
    AnomalyDetection,
    MarketSentiment,
    PricePrediction,
)
from app.services.price_service import PriceService

logger = logging.getLogger(__name__)


class PredictionAlphaMixin:
    """Signaux alpha, carte de stratégie et what-if."""

    async def get_top_alpha_asset(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> Dict:
        """Detect the asset with the highest short-term alpha potential.

        Scores each held asset (quantity > 0) on 3 axes:
        1. RSI/Price divergence (bullish divergence = price down + RSI up).
        2. BTC de-correlation (lower Spearman correlation = more alpha).
        3. Regime momentum (bottom→bullish transition).

        Returns the top-scoring asset with reasons and 7d price prediction.
        """
        result = await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
        portfolios = result.scalars().all()
        portfolio_ids = [p.id for p in portfolios]

        if not portfolio_ids:
            return {"found": False}

        result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id.in_(portfolio_ids),
                Asset.quantity > 0,
            )
        )
        raw_assets = result.scalars().all()

        # Deduplicate by symbol (Decimal precision)
        asset_map: Dict[str, object] = {}
        qty_map: Dict[str, Decimal] = {}
        cash_like_qty: Dict[str, Decimal] = {}
        for a in raw_assets:
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

        if not asset_map:
            return {"found": False, "total_portfolio_value": 0.0}

        # ── Fetch BTC prices for correlation baseline ──
        btc_prices: List[float] = []
        try:
            cached = await get_cached_history("BTC", "crypto", 90)
            if cached and cached.get("prices"):
                btc_prices = cached["prices"]
            else:
                dates, prices = await self.data_fetcher.get_history("BTC", "crypto", days=90)
                if dates and prices:
                    btc_prices = prices
                    await cache_history(
                        "BTC",
                        "crypto",
                        90,
                        {"dates": [d.isoformat() for d in dates], "prices": prices},
                    )
        except Exception:
            logger.warning("Failed to fetch BTC history for alpha scoring")

        btc_returns = np.diff(np.log(np.array(btc_prices, dtype=float))) if len(btc_prices) > 10 else np.array([])

        # ── Fetch Fear & Greed for regime detection ──
        fear_greed: Optional[int] = await fetch_fear_greed_index()

        # ── Batch-fetch prices (same source as Dashboard for parity) ──
        crypto_symbols = [s for s, a in asset_map.items() if a.asset_type == AssetType.CRYPTO]
        stock_symbols = [s for s, a in asset_map.items() if a.asset_type in (AssetType.STOCK, AssetType.ETF)]
        price_map: Dict[str, float] = {}

        if crypto_symbols:
            try:
                batch = await self.price_service.get_multiple_crypto_prices(crypto_symbols, "eur")
                for sym, data in batch.items():
                    p = data.get("price", 0)
                    price_map[sym.upper()] = float(p) if p else 0.0
            except Exception as e:
                logger.warning("Batch crypto price fetch failed: %s", e)

        for sym in stock_symbols:
            try:
                data = await self.price_service.get_stock_price(sym)
                if data and data.get("price"):
                    price_map[sym.upper()] = float(data["price"])
            except Exception as exc:
                logger.debug("Stock price fetch failed for %s (alpha scoring): %s", sym, exc)

        # ── Pre-fetch all 90d histories in parallel ──
        import asyncio as _aio

        async def _fetch_history(sym: str, atype: str) -> tuple:
            """Fetch 90d history from cache or API."""
            cached_hist = await get_cached_history(sym, atype, 90)
            if cached_hist and cached_hist.get("prices"):
                return (sym, cached_hist["prices"])
            try:
                a_dates, a_prices_raw = await self.data_fetcher.get_history(sym, atype, days=90)
                if a_dates and a_prices_raw:
                    await cache_history(
                        sym,
                        atype,
                        90,
                        {
                            "dates": [d.isoformat() for d in a_dates],
                            "prices": a_prices_raw,
                        },
                    )
                    return (sym, a_prices_raw)
            except Exception as exc:
                logger.debug("90d history fetch failed for %s (alpha scoring): %s", sym, exc)
            return (sym, [])

        # Limit assets to reduce memory usage on free-tier hosting (512 MB)
        _MAX_ASSETS = 7
        _PREDICTION_BATCH_SIZE = 3  # Process ensemble predictions in small batches

        _items = list(asset_map.items())[:_MAX_ASSETS]
        history_results = await _aio.gather(*[_fetch_history(s, a.asset_type.value) for s, a in _items])
        history_map: Dict[str, List[float]] = {sym: prices for sym, prices in history_results}

        # ── Pre-fetch 7d predictions in batches to limit memory ──
        import gc

        _prediction_cache: Dict[str, Optional[PricePrediction]] = {}

        async def _fetch_prediction(sym: str, atype: AssetType) -> tuple:
            try:
                pred = await self.get_price_prediction(sym, atype, days_ahead=7)
                return (sym, pred)
            except Exception as e:
                logger.debug("7d prediction failed for %s: %s", sym, e)
                return (sym, None)

        for batch_start in range(0, len(_items), _PREDICTION_BATCH_SIZE):
            batch = _items[batch_start : batch_start + _PREDICTION_BATCH_SIZE]
            batch_results = await _aio.gather(*[_fetch_prediction(s, a.asset_type) for s, a in batch])
            for sym, pred in batch_results:
                _prediction_cache[sym] = pred

            # Free memory between batches
            gc.collect()

        # ── Score each asset ──
        scored_assets = []
        total_value = Decimal("0")
        value_map: Dict[str, float] = {}

        for symbol, asset in _items:
            try:
                price = price_map.get(symbol.upper(), 0.0)
                if price <= 0:
                    # Fallback to individual fetch
                    price = await self._get_current_price(symbol, asset.asset_type)
                if price <= 0:
                    logger.warning("Price fetch failed for %s (batch + fallback), skipping", symbol)
                    continue
                qty_dec = qty_map[symbol]
                price_dec = Decimal(str(price))
                value_dec = qty_dec * price_dec
                total_value += value_dec
                value = float(value_dec)
                value_map[symbol] = value

                a_prices = history_map.get(symbol, [])

                if len(a_prices) < 20:
                    continue

                reasons = []
                score = 0.0

                # ── 1. RSI/Price divergence (0-35 points) ──
                rsi_now = _rsi(a_prices, period=14)
                rsi_prev = _rsi(a_prices[:-7], period=14) if len(a_prices) > 21 else None
                price_t = a_prices[-1]
                price_t7 = a_prices[-8] if len(a_prices) > 8 else price_t
                price_change_7d = (price_t / price_t7 - 1) * 100 if price_t7 > 0 else 0

                # Divergence log for audit / Telegram recap
                divergence_log = {
                    "price_t7": round(price_t7, 4),
                    "price_t": round(price_t, 4),
                    "rsi_t7": round(rsi_prev, 2) if rsi_prev is not None else None,
                    "rsi_t": round(rsi_now, 2) if rsi_now is not None else None,
                    "price_change_7d_pct": round(price_change_7d, 2),
                    "is_bullish_divergence": False,
                }

                if rsi_now is not None and rsi_prev is not None:
                    # Bullish divergence: price goes down but RSI goes up
                    rsi_delta = rsi_now - rsi_prev
                    if price_change_7d < -2 and rsi_delta > 3:
                        divergence_log["is_bullish_divergence"] = True
                        div_score = min(35, 15 + rsi_delta * 2)
                        score += div_score
                        reasons.append(
                            {
                                "label": "Divergence Haussière",
                                "detail": f"Prix {price_change_7d:+.1f}% mais RSI {rsi_delta:+.1f} pts",
                                "score": round(div_score),
                            }
                        )
                        logger.info(
                            "Divergence %s CONFIRMÉE: Prix(T-7)=%.4f > Prix(T)=%.4f " "ET RSI(T-7)=%.2f < RSI(T)=%.2f",
                            symbol,
                            price_t7,
                            price_t,
                            rsi_prev,
                            rsi_now,
                        )
                    elif price_change_7d < -2 and rsi_delta <= 3:
                        # Price dropped but RSI did NOT diverge — degrade score
                        penalty = min(10, abs(rsi_delta) * 1.5)
                        score -= penalty
                        divergence_log["degraded"] = True
                        divergence_log["penalty"] = round(penalty, 1)
                        reasons.append(
                            {
                                "label": "Divergence Non Confirmée",
                                "detail": f"Prix {price_change_7d:+.1f}% et RSI {rsi_delta:+.1f} pts (pas de divergence)",
                                "score": round(-penalty),
                            }
                        )
                        logger.info(
                            "Divergence %s NON CONFIRMÉE: Prix(T-7)=%.4f > Prix(T)=%.4f "
                            "mais RSI(T-7)=%.2f → RSI(T)=%.2f (delta %.1f ≤ 3)",
                            symbol,
                            price_t7,
                            price_t,
                            rsi_prev,
                            rsi_now,
                            rsi_delta,
                        )
                    elif rsi_now < 35:
                        # Oversold but no divergence yet — mild signal
                        ov_score = min(20, (35 - rsi_now) * 1.2)
                        score += ov_score
                        reasons.append(
                            {
                                "label": "Survente RSI",
                                "detail": f"RSI à {rsi_now:.0f} (seuil 35)",
                                "score": round(ov_score),
                            }
                        )

                # ── 2. BTC de-correlation (0-30 points) ──
                if len(btc_returns) > 10 and len(a_prices) > 10:
                    a_returns = np.diff(np.log(np.array(a_prices[-len(btc_returns) - 1 :], dtype=float)))
                    min_len = min(len(btc_returns), len(a_returns))
                    if min_len >= 10:
                        from scipy.stats import spearmanr

                        corr, _ = spearmanr(btc_returns[-min_len:], a_returns[-min_len:])
                        if not np.isnan(corr):
                            # Lower correlation = more alpha potential
                            # corr < 0.3 is considered "decoupled"
                            decorr_score = max(0, (0.6 - corr) / 0.6 * 30)
                            score += decorr_score
                            if decorr_score > 10:
                                reasons.append(
                                    {
                                        "label": "Décorrélé du BTC",
                                        "detail": f"Corrélation {corr:.2f} (faible = indépendant)",
                                        "score": round(decorr_score),
                                    }
                                )

                # ── 3. Regime momentum (0-35 points) ──
                regime_result = self.regime_detector.detect(
                    a_prices,
                    symbol,
                    fear_greed,
                    asset_type=asset.asset_type.value,
                )
                probs = regime_result.probabilities
                # Transition from bottom/bearish → bullish = strong alpha signal
                bottom_prob = probs.get("bottom", 0)
                bullish_prob = probs.get("bullish", 0)
                transition_signal = bottom_prob * 0.6 + bullish_prob * 0.4

                if transition_signal > 0.3:
                    reg_score = min(35, transition_signal * 70)
                    score += reg_score
                    dominant = regime_result.dominant_regime
                    reasons.append(
                        {
                            "label": "Momentum de Régime",
                            "detail": f"Régime: {dominant} (bottom {bottom_prob:.0%}, bull {bullish_prob:.0%})",
                            "score": round(reg_score),
                        }
                    )

                # ── 7d price prediction (Decimal precision) ──
                # Use pre-fetched batch prediction if available
                predicted_7d_pct = Decimal("0")
                prediction_source = "none"
                prediction = _prediction_cache.get(symbol)
                if prediction and prediction.predictions:
                    last_pred = prediction.predictions[-1]
                    pred_price = last_pred.get("price", 0)
                    if pred_price > 0 and price > 0:
                        raw_pct = (Decimal(str(pred_price)) / price_dec - 1) * 100
                        # Sanity check: reject > ±50% moves
                        if abs(raw_pct) > 50:
                            logger.warning(
                                "SANITY CHECK (alpha): %s ensemble 7d prediction "
                                "unrealistic (%.1f%%). Falling back to EMA-20.",
                                symbol,
                                float(raw_pct),
                            )
                            predicted_7d_pct = Decimal("0")
                            prediction_source = "none"
                        else:
                            predicted_7d_pct = raw_pct
                            prediction_source = "ensemble"

                # EMA-20 slope fallback: extrapolate 7 days if model unavailable
                if predicted_7d_pct == 0 and len(a_prices) >= 20:
                    try:
                        arr = np.array(a_prices[-20:], dtype=float)
                        ema = arr.copy()
                        k = 2 / 21  # EMA-20 smoothing factor
                        for idx in range(1, len(ema)):
                            ema[idx] = arr[idx] * k + ema[idx - 1] * (1 - k)
                        # Daily slope from last 5 EMA values
                        daily_slope = (ema[-1] - ema[-5]) / max(ema[-5], 1e-10) / 5
                        ema_7d_pct = daily_slope * 7 * 100
                        if abs(ema_7d_pct) > 0.01:  # only if meaningful
                            predicted_7d_pct = Decimal(str(round(ema_7d_pct, 4)))
                            prediction_source = "ema20_slope"
                    except Exception as exc:
                        logger.debug("EMA-20 slope fallback failed for %s: %s", symbol, exc)

                scored_assets.append(
                    {
                        "symbol": symbol,
                        "name": asset.name,
                        "asset_type": asset.asset_type.value,
                        "current_price": float(round(price_dec, 2)),
                        "score": round(score, 1),
                        "predicted_7d_pct": float(round(predicted_7d_pct, 2)),
                        "prediction_source": prediction_source,
                        "reasons": sorted(reasons, key=lambda r: -r["score"]),
                        "regime": regime_result.dominant_regime,
                        "regime_confidence": round(regime_result.confidence, 2),
                        "value": float(round(value_dec, 2)),
                        "divergence_log": divergence_log,
                    }
                )
            except Exception as e:
                logger.warning("Alpha scoring failed for %s: %s", symbol, e)

        if not scored_assets:
            return {"found": False, "total_portfolio_value": 0.0}

        # Include cash-like assets in total for accurate weight calculation
        for sym, qty in cash_like_qty.items():
            try:
                if PriceService.is_stablecoin(sym):
                    p = await self.price_service._stablecoin_price_eur(sym)
                else:
                    p = Decimal("1")  # fiat EUR=1, others approximated
                total_value += qty * p
            except Exception:
                total_value += qty  # fallback: assume 1:1

        total_value_f = float(total_value)

        # ── Concentration risk guard ──
        for sa in scored_assets:
            if total_value_f > 0:
                sa["weight_pct"] = round(sa["value"] / total_value_f * 100, 1)
            else:
                sa["weight_pct"] = 0.0

        # Sort by score desc
        scored_assets.sort(key=lambda x: -x["score"])
        top = scored_assets[0]

        # Flag if top alpha asset is already over-concentrated (> 50% weight)
        concentration_risk = top["weight_pct"] > 50

        return {
            "found": True,
            "top_alpha": top,
            "concentration_risk": concentration_risk,
            "all_scores": scored_assets[:5],  # Top 5 for frontend display
            "total_portfolio_value": float(round(total_value, 2)),
        }

    # ------------------------------------------------------------------
    # Strategy Map — decision matrix Alpha × Cycle
    # ------------------------------------------------------------------

    STRATEGY_MATRIX = {
        # (alpha_level, cycle_phase) → (action, description, impact_pct)
        # alpha_level: high (>= 60), medium (30-59), low (< 30)
        # cycle_phase: 6 professional phases
        # --- Bottoming (RSI < 30, divergence haussière, épuisement vendeur) ---
        ("high", "bottoming"): (
            "ACHAT FORT",
            "Alpha élevé + Bottoming : signal d'achat optimal (RSI survente + divergence)",
            5.0,
        ),
        ("medium", "bottoming"): (
            "DCA",
            "Signal moyen + Bottoming : DCA conservateur",
            3.0,
        ),
        ("low", "bottoming"): (
            "OBSERVER",
            "Faible alpha + Bottoming : surveiller les signaux",
            0.0,
        ),
        # --- Accumulation (prix stable, Smart Money Flow positif) ---
        ("high", "accumulation"): (
            "DCA",
            "Alpha élevé + Accumulation : accumuler progressivement",
            4.0,
        ),
        ("medium", "accumulation"): (
            "DCA",
            "Signal moyen + Accumulation : fenêtre d'entrée progressive",
            2.0,
        ),
        ("low", "accumulation"): (
            "OBSERVER",
            "Faible alpha + Accumulation : pas encore de signal clair",
            0.0,
        ),
        # --- Mark-up (cassure de résistance, volume croissant) ---
        ("high", "markup"): (
            "MAINTENIR",
            "Alpha élevé + Mark-up : laisser courir les gains",
            0.0,
        ),
        ("medium", "markup"): (
            "MAINTENIR",
            "Signal moyen + Mark-up : conserver les positions",
            0.0,
        ),
        ("low", "markup"): (
            "CONSERVER",
            "Faible alpha en Mark-up : ne pas vendre",
            0.0,
        ),
        # --- Topping (RSI > 70, divergence baissière, risque de retournement) ---
        ("high", "topping"): (
            "PRENDRE PROFITS",
            "Alpha élevé mais Topping : sécuriser 20-30%",
            -2.0,
        ),
        ("medium", "topping"): (
            "ALLÉGER",
            "Signal moyen + Topping : réduire l'exposition",
            -3.0,
        ),
        ("low", "topping"): (
            "VENDRE",
            "Faible alpha + Topping : signal de vente prioritaire",
            -5.0,
        ),
        # --- Distribution (prix stagne sur sommets, gros volumes sortants) ---
        ("high", "distribution"): (
            "ALLÉGER",
            "Alpha élevé + Distribution : sécuriser une partie",
            -2.0,
        ),
        ("medium", "distribution"): (
            "VENDRE",
            "Signal moyen + Distribution : réduire avant le markdown",
            -4.0,
        ),
        ("low", "distribution"): (
            "VENDRE",
            "Faible alpha + Distribution : sortir avant la chute",
            -5.0,
        ),
        # --- Markdown (structure descendante, Lower Highs) ---
        ("high", "markdown"): (
            "DCA",
            "Alpha élevé en Markdown : accumuler progressivement (contrarian)",
            3.0,
        ),
        ("medium", "markdown"): (
            "ATTENDRE",
            "Signal moyen en Markdown : patience, pas de renforcement",
            0.0,
        ),
        ("low", "markdown"): (
            "ÉVITER",
            "Faible alpha en Markdown : ne pas renforcer",
            0.0,
        ),
        # --- Backward-compat: old 4-phase names still work ---
        ("high", "bottom"): (
            "ACHAT FORT",
            "Alpha élevé + creux de marché : signal d'achat optimal",
            5.0,
        ),
        ("high", "bearish"): (
            "DCA",
            "Alpha élevé en bear market : accumuler progressivement",
            3.0,
        ),
        ("high", "bullish"): ("MAINTENIR", "Alpha élevé en bull : laisser courir", 0.0),
        ("high", "top"): (
            "PRENDRE PROFITS",
            "Alpha élevé mais sommet : sécuriser 20-30%",
            -2.0,
        ),
        ("medium", "bottom"): ("DCA", "Signal moyen + creux : DCA conservateur", 3.0),
        ("medium", "bearish"): ("ATTENDRE", "Signal moyen en bear : patience", 0.0),
        ("medium", "bullish"): (
            "MAINTENIR",
            "Signal moyen en bull : conserver les positions",
            0.0,
        ),
        ("medium", "top"): (
            "ALLÉGER",
            "Signal moyen au sommet : réduire l'exposition",
            -3.0,
        ),
        ("low", "bottom"): (
            "OBSERVER",
            "Faible alpha + creux : surveiller les signaux",
            0.0,
        ),
        ("low", "bearish"): ("ÉVITER", "Faible alpha en bear : ne pas renforcer", 0.0),
        ("low", "bullish"): (
            "CONSERVER",
            "Faible alpha en bull : ne pas vendre non plus",
            0.0,
        ),
        ("low", "top"): (
            "VENDRE",
            "Faible alpha + sommet : signal de vente prioritaire",
            -5.0,
        ),
    }

    async def get_strategy_map(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> Dict:
        """Build a strategy decision table crossing Alpha scores with Cycle phase.

        Calls get_top_alpha_asset() and get_market_cycle() then merges
        per-asset data using a decision matrix.
        """
        # Fetch both datasets in parallel (independent operations)
        import asyncio as _aio

        alpha_data, cycle_data = await _aio.gather(
            self.get_top_alpha_asset(db, user_id),
            self.get_market_cycle(db, user_id),
        )

        total_value = alpha_data.get("total_portfolio_value", 0.0)
        alpha_scores = alpha_data.get("all_scores", [])
        per_asset_cycle = cycle_data.get("per_asset", [])
        market_regime = cycle_data.get("market_regime", {})
        fear_greed = cycle_data.get("fear_greed")

        # Build regime lookup by symbol
        regime_map: Dict[str, Dict] = {}
        for a in per_asset_cycle:
            regime_map[a["symbol"]] = a

        # Merge: for each scored asset, cross with its cycle regime
        strategy_rows: List[Dict] = []
        summary_buys = 0
        summary_sells = 0
        summary_holds = 0

        for scored in alpha_scores:
            sym = scored["symbol"]
            score = scored["score"]
            value = scored.get("value", 0)
            weight_pct = scored.get("weight_pct", 0)

            # Alpha level — regime-aware thresholds via RegimeConfig.alpha_threshold
            _global_regime = market_regime.get("dominant_regime", "") if market_regime else ""
            _alpha_cfg = RegimeConfig.from_regime(_global_regime)
            _high_thresh = _alpha_cfg.alpha_threshold  # 85 in bear, 60 in bull
            _mid_thresh = max(30, _high_thresh - 30)  # 55 in bear, 30 in bull
            if score >= _high_thresh:
                alpha_level = "high"
            elif score >= _mid_thresh:
                alpha_level = "medium"
            else:
                alpha_level = "low"

            # Cycle phase — prefer 6-phase, fallback to 4-phase dominant_regime
            cycle_info = regime_map.get(sym, {})
            regime = cycle_info.get(
                "regime_6phase",
                cycle_info.get(
                    "dominant_regime",
                    market_regime.get("dominant_regime", "bullish") if market_regime else "bullish",
                ),
            )

            # Decision matrix lookup
            key = (alpha_level, regime)
            action, description, impact_pct = self.STRATEGY_MATRIX.get(key, ("OBSERVER", "Données insuffisantes", 0.0))

            # Bear market validation: ACHAT FORT requires RSI < 35 confirmation
            # when the global market is in markdown/bearish/distribution
            global_regime = market_regime.get("dominant_regime", "") if market_regime else ""
            if action == "ACHAT FORT" and global_regime in (
                "bearish",
                "top",
                "markdown",
                "distribution",
            ):
                # Check if scored asset has RSI divergence confirmation
                has_divergence = any(r.get("label", "") == "Divergence Haussière" for r in scored.get("reasons", []))
                if not has_divergence:
                    action = "DCA"
                    description = "Bear market : ACHAT FORT dégradé en DCA (divergence RSI non confirmée)"
                    impact_pct = 2.0

            # Compute portfolio impact
            impact_eur = round(value * impact_pct / 100, 2) if value > 0 else 0.0

            # Count summary
            if "ACHAT" in action or action == "DCA":
                summary_buys += 1
            elif "VENDRE" in action or "PROFITS" in action or "ALLÉGER" in action:
                summary_sells += 1
            else:
                summary_holds += 1

            # Bull market: virtual trailing stop hint based on EMA-20
            trailing_stop = None
            if regime in ("markup", "bullish") and action in ("MAINTENIR", "CONSERVER"):
                trailing_stop = "EMA-20 trailing stop recommandé — remonter le stop-loss sous l'EMA-20"

            strategy_rows.append(
                {
                    "symbol": sym,
                    "name": scored.get("name", sym),
                    "alpha_score": round(score, 1),
                    "alpha_level": alpha_level,
                    "regime": regime,
                    "regime_confidence": round(cycle_info.get("confidence", 0.5), 2),
                    "action": action,
                    "description": description,
                    "value": round(value, 2),
                    "weight_pct": round(weight_pct, 1),
                    "impact_pct": impact_pct,
                    "impact_eur": impact_eur,
                    "predicted_7d_pct": scored.get("predicted_7d_pct", 0),
                    "is_resilient": is_safe_haven(sym),
                    "trailing_stop": trailing_stop,
                }
            )

        return {
            "rows": strategy_rows,
            "total_portfolio_value": round(total_value, 2),
            "market_regime": market_regime.get("dominant_regime", "unknown") if market_regime else "unknown",
            "fear_greed": fear_greed,
            "summary": {
                "buys": summary_buys,
                "sells": summary_sells,
                "holds": summary_holds,
            },
        }

    async def get_what_if(
        self,
        db: AsyncSession,
        user_id: str,
        scenarios: List[Dict],
    ) -> Dict:
        """Simulate what-if scenarios on the portfolio."""
        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == user_id,
            )
        )
        portfolios = result.scalars().all()
        portfolio_ids = [p.id for p in portfolios]

        if not portfolio_ids:
            return {
                "current_value": 0,
                "simulated_value": 0,
                "impact_percent": 0,
                "per_asset": [],
            }

        result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id.in_(portfolio_ids),
                Asset.quantity > 0,
            )
        )
        raw_assets = result.scalars().all()

        # Deduplicate by symbol (Decimal precision)
        wi_asset_map: Dict[str, object] = {}
        wi_qty_map: Dict[str, Decimal] = {}
        for a in raw_assets:
            if a.symbol not in wi_asset_map:
                wi_asset_map[a.symbol] = a
                wi_qty_map[a.symbol] = Decimal(str(a.quantity))
            else:
                wi_qty_map[a.symbol] += Decimal(str(a.quantity))
        assets = list(wi_asset_map.values())

        # Build scenario map
        scenario_map = {s["symbol"].upper(): s["change_percent"] for s in scenarios}

        per_asset = []
        total_current = Decimal("0")
        total_simulated = Decimal("0")

        for asset in assets[:15]:
            price = await self._get_current_price(asset.symbol, asset.asset_type)
            price_dec = Decimal(str(price))
            qty_dec = wi_qty_map[asset.symbol]
            current_val = price_dec * qty_dec
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
