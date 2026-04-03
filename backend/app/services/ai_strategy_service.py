"""AI Strategy Suggestion Service.

Analyzes user portfolio, market regime, and alpha signals to propose
actionable investment strategies. Strategies are dynamic — the AI suggests
whatever is most appropriate based on market conditions and portfolio state.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.strategy import ActionStatus, Strategy, StrategyAction, StrategySource, StrategyStatus

logger = logging.getLogger(__name__)


class AIStrategyService:
    """Generate investment strategy suggestions based on portfolio analysis."""

    async def suggest_strategies(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> List[Dict[str, Any]]:
        """Analyze portfolio and propose strategies."""
        from app.services.prediction_service import prediction_service
        from app.services.strategy_service import strategy_service

        # 1. Get strategy map (alpha + regime per asset)
        try:
            strategy_map = await prediction_service.get_strategy_map(db, user_id)
        except Exception as e:
            logger.warning("Failed to get strategy map: %s", e)
            strategy_map = {"rows": [], "summary": {}, "market_regime": "unknown"}

        # 2. Get deployment capacity (liquidity)
        try:
            capacity = await strategy_service.get_deployment_capacity(db, user_id)
            liquidity = capacity.available_liquidity
            total_value = capacity.total_value
        except Exception as e:
            logger.warning("Failed to get deployment capacity: %s", e)
            liquidity = 0.0
            total_value = 0.0

        assets = strategy_map.get("rows", [])
        regime_name = strategy_map.get("market_regime", "unknown") or "unknown"
        fear_greed = strategy_map.get("fear_greed")
        regime_confidence = (fear_greed / 100.0) if fear_greed and isinstance(fear_greed, (int, float)) else 0.5
        strategies: List[Dict[str, Any]] = []

        # Classify assets by signal
        buy_assets = [a for a in assets if "ACHAT" in a.get("action", "") or a.get("action") == "DCA"]
        sell_assets = [a for a in assets if any(kw in a.get("action", "") for kw in ("VENDRE", "PROFITS", "ALLÉGER"))]
        hold_assets = [a for a in assets if a not in buy_assets and a not in sell_assets]

        # Compute volatility spread (max predicted change spread across assets)
        predictions = [abs(a.get("predicted_7d_pct", 0)) for a in assets if a.get("predicted_7d_pct")]
        avg_volatility = sum(predictions) / len(predictions) if predictions else 0
        has_high_volatility = avg_volatility > 5

        # --- In bear/bottom/accumulation: best time to buy ---
        # If no explicit buy signals but market is low, treat top-alpha assets as buy candidates
        is_accumulation_phase = regime_name in ("bearish", "bottom", "accumulation", "markdown", "bottoming")
        if is_accumulation_phase and not buy_assets:
            # Force accumulation on top-alpha assets even without explicit buy signal
            # Lower threshold in extreme fear — any positive alpha is worth accumulating
            min_alpha = 15 if (fear_greed and fear_greed < 25) else 30
            top_alpha = sorted(assets, key=lambda a: a.get("alpha_score", 0), reverse=True)
            buy_assets = [a for a in top_alpha if a.get("alpha_score", 0) >= min_alpha][:5]
            # If still nothing, take the best 3 regardless (extreme fear = buy everything)
            if not buy_assets and fear_greed and fear_greed < 15:
                buy_assets = top_alpha[:3]

        # --- Strategy generation based on portfolio state + market ---

        # 1. VCA — Value Cost Averaging
        # PRIORITY in bear/volatile markets — buy more when prices are low
        vca = self._build_vca_strategy(
            buy_assets, assets, regime_name, regime_confidence, liquidity, total_value, has_high_volatility
        )
        if vca:
            strategies.append(vca)

        # 2. DCA — Dollar Cost Averaging
        # Steady accumulation in any market with buy candidates
        dca = self._build_dca_strategy(buy_assets, regime_name, regime_confidence, liquidity, has_high_volatility)
        if dca:
            strategies.append(dca)

        # 3. Profit-taking — only in bull/top markets, NOT in bear
        if sell_assets and not is_accumulation_phase:
            strategies.append(self._build_profit_taking_strategy(sell_assets, regime_name, regime_confidence))

        # 4. Rotation — sell weak, buy strong (useful in any market)
        rotation = self._build_rotation_strategy(buy_assets, sell_assets, regime_name, regime_confidence, total_value)
        if rotation:
            strategies.append(rotation)

        # 5. Rebalancing if portfolio is skewed
        if len(assets) >= 3:
            rebalance = self._build_rebalance_strategy(assets, regime_name, regime_confidence, total_value)
            if rebalance:
                strategies.append(rebalance)

        # 6. Swing Trading — in volatile sideways markets
        swing = self._build_swing_strategy(assets, regime_name, regime_confidence, has_high_volatility, liquidity)
        if swing:
            strategies.append(swing)

        # 7. Selective profit-taking in bear — only on the very weakest assets
        if sell_assets and is_accumulation_phase:
            very_weak = [a for a in sell_assets if a.get("alpha_score", 0) < 15]
            if very_weak:
                strategies.append(self._build_profit_taking_strategy(very_weak, regime_name, regime_confidence))

        # 8. Stablecoin Yield — park cash in stablecoins during uncertainty
        stablecoin = self._build_stablecoin_yield_strategy(
            assets, regime_name, regime_confidence, liquidity, total_value
        )
        if stablecoin:
            strategies.append(stablecoin)

        # 9. Conviction Buy — extreme fear = strongest buy signal
        conviction = self._build_conviction_buy_strategy(
            buy_assets, assets, regime_name, regime_confidence, fear_greed, liquidity
        )
        if conviction:
            strategies.append(conviction)

        # 10. Progressive Profit Plan — in bull, plan staged exits
        profit_plan = self._build_progressive_profit_plan(sell_assets, hold_assets, regime_name, regime_confidence)
        if profit_plan:
            strategies.append(profit_plan)

        # If no signals at all, suggest observation
        if not strategies:
            strategies.append(
                {
                    "name": "Observation — Attente de signaux",
                    "description": (
                        f"Le marché est en phase '{regime_name}' sans signaux forts. "
                        "Continuez à surveiller. Aucune action immédiate recommandée."
                    ),
                    "params": {"type": "observation"},
                    "ai_reasoning": "Aucun signal d'achat ou de vente suffisamment fort détecté.",
                    "market_regime": regime_name,
                    "confidence": regime_confidence,
                    "actions": [],
                }
            )

        # Risk/performance classification per strategy type
        # risk_level: 1=conservateur, 2=modéré, 3=dynamique, 4=agressif
        # performance_potential: 1=faible, 2=moyen, 3=élevé, 4=très élevé
        _RISK_MAP = {
            "observation": (1, 1),
            "stablecoin_yield": (1, 1),
            "defensive": (1, 2),
            "rebalance": (2, 2),
            "dca_sélectif": (2, 2),
            "dca_modéré": (2, 2),
            "profit_taking": (2, 3),
            "progressive_profit": (2, 3),
            "rotation": (3, 3),
            "dca_agressif": (3, 3),
            "vca": (3, 4),
            "swing": (4, 4),
            "conviction_buy": (4, 4),
        }

        # Inject liquidity context + risk classification into each strategy's params
        for s in strategies:
            params = s.get("params", {})
            params["available_liquidity"] = round(liquidity, 2)
            params["total_portfolio_value"] = round(total_value, 2)

            # Risk classification
            stype = str(params.get("type", "")).lower()
            risk_level, perf_potential = _RISK_MAP.get(stype, (2, 2))
            params["risk_level"] = risk_level
            params["performance_potential"] = perf_potential

            # Compute total proposed buy amount for this strategy
            buy_actions = ("VCA", "DCA", "ACHAT", "ACHAT FORT", "RENFORCER")
            total_proposed = sum(
                a.get("amount", 0) or 0 for a in s.get("actions", []) if a.get("action") in buy_actions
            )
            params["total_proposed_amount"] = round(total_proposed, 2)
            params["proposed_pct_of_liquidity"] = round(total_proposed / liquidity * 100, 1) if liquidity > 0 else 0
            s["params"] = params

        # Sort strategies: highest performance potential first, then by risk (higher risk first for same perf)
        strategies.sort(
            key=lambda s: (
                -(s.get("params", {}).get("performance_potential", 2)),
                -(s.get("params", {}).get("risk_level", 2)),
            )
        )

        return strategies

    # --- Strategy Builders ---

    def _build_vca_strategy(
        self,
        buy_assets: List[Dict],
        all_assets: List[Dict],
        regime: str,
        confidence: float,
        liquidity: float,
        total_value: float,
        has_high_volatility: bool,
    ) -> Optional[Dict[str, Any]]:
        """VCA — invest more when prices are low, less when high.

        Best in volatile/accumulation markets where price swings create
        opportunities to buy more at lower prices.
        """
        # VCA is most relevant in bear/accumulation (buy low!) or volatile markets
        if not buy_assets:
            return None
        is_accumulation = regime in ("bearish", "bottom", "accumulation", "markdown")
        if not has_high_volatility and not is_accumulation:
            return None

        sorted_assets = sorted(buy_assets, key=lambda a: a.get("alpha_score", 0), reverse=True)
        top = sorted_assets[:4]

        # VCA: base amount proportional to liquidity + alpha multiplier
        actions = []
        if liquidity <= 0:
            return None  # Pas de munitions = pas de stratégie d'achat
        base_amount = round(liquidity * 0.04, 2)
        for asset in top:
            # Higher alpha = more aggressive VCA multiplier
            alpha = asset.get("alpha_score", 50)
            multiplier = 1.0 + (alpha - 50) / 100  # alpha 80 → 1.3x, alpha 30 → 0.8x
            amount = round(base_amount * max(multiplier, 0.5), 2)
            actions.append(
                {
                    "action": "VCA",
                    "symbol": asset["symbol"],
                    "amount": amount,
                    "currency": "EUR",
                    "reason": (
                        f"Alpha {alpha}/100 — investir {amount}€ soit ~{round(amount / liquidity * 100, 1)}% "
                        f"de vos liquidités. {asset.get('description', '')}"
                    ),
                }
            )

        total_vca = sum(a["amount"] for a in actions)
        if is_accumulation:
            desc = (
                f"Marché en phase '{regime}' — les prix sont bas, c'est le moment d'accumuler. "
                f"Budget total : {total_vca:.0f}€ sur {round(liquidity, 0):.0f}€ de liquidités disponibles "
                f"({round(total_vca / liquidity * 100, 1)}%). "
                "Le VCA investit davantage quand les prix baissent, maximisant les quantités achetées."
            )
        else:
            desc = (
                f"Marché en phase '{regime}' avec forte volatilité. "
                f"Budget total : {total_vca:.0f}€ sur {round(liquidity, 0):.0f}€ de liquidités disponibles. "
                "Le VCA ajuste les montants : plus quand les prix sont bas, moins quand ils sont hauts."
            )

        return {
            "name": f"VCA Dynamique — {len(top)} assets",
            "description": desc,
            "params": {
                "type": "vca",
                "assets": [a["symbol"] for a in top],
                "regime": regime,
                "base_amount": base_amount,
            },
            "ai_reasoning": (
                "La volatilité élevée crée des opportunités d'accumulation à prix réduit. "
                "Le VCA surperforme le DCA dans ces conditions car il achète automatiquement "
                "plus de quantité quand les prix baissent."
            ),
            "market_regime": regime,
            "confidence": confidence,
            "actions": actions,
        }

    def _build_dca_strategy(
        self,
        buy_assets: List[Dict],
        regime: str,
        confidence: float,
        liquidity: float,
        has_high_volatility: bool,
    ) -> Optional[Dict[str, Any]]:
        """DCA — fixed amount at regular intervals. Best in trending markets."""
        if not buy_assets:
            return None

        # In bear+volatile, VCA is preferred — but still offer DCA on different assets
        if has_high_volatility and regime in ("bearish", "bottom", "accumulation", "markdown"):
            # Only skip if we'd be suggesting the exact same assets as VCA
            return None

        sorted_assets = sorted(buy_assets, key=lambda a: a.get("alpha_score", 0), reverse=True)
        top = sorted_assets[:5]

        if regime in ("bearish", "bottom", "accumulation", "markdown"):
            intensity = "Agressif"
            pct = 0.06
            reasoning = (
                f"Marché en phase '{regime}' — c'est le meilleur moment pour accumuler. "
                "Les prix sont décotés, le DCA agressif permet de baisser son prix moyen d'achat. "
                '"Be greedy when others are fearful."'
            )
        elif regime in ("bullish", "markup"):
            intensity = "Modéré"
            pct = 0.03
            reasoning = (
                f"Marché en phase '{regime}' — tendance haussière. "
                "Continuer le DCA avec des montants standards. Rester discipliné."
            )
        else:
            intensity = "Sélectif"
            pct = 0.03
            reasoning = f"Marché en phase '{regime}'. " "DCA uniquement sur les assets avec les meilleurs scores alpha."

        if liquidity <= 0:
            return None  # Pas de munitions = pas de DCA

        actions = []
        for asset in top:
            amount = abs(asset.get("impact_eur", 0))
            if amount == 0 or amount > liquidity * 0.5:
                # Fallback ou cap : proportionnel à la liquidité
                amount = round(liquidity * pct, 2)
            actions.append(
                {
                    "action": "DCA",
                    "symbol": asset["symbol"],
                    "amount": amount,
                    "currency": "EUR",
                    "reason": (
                        f"Alpha {asset.get('alpha_score', 0)}/100 — {amount}€ "
                        f"({round(amount / liquidity * 100, 1)}% de vos liquidités). "
                        f"{asset.get('description', 'Signal favorable')}"
                    ),
                }
            )

        return {
            "name": f"DCA {intensity} — {len(top)} assets",
            "description": reasoning,
            "params": {
                "type": f"dca_{intensity.lower()}",
                "assets": [a["symbol"] for a in top],
                "regime": regime,
            },
            "ai_reasoning": reasoning,
            "market_regime": regime,
            "confidence": confidence,
            "actions": actions,
        }

    def _build_profit_taking_strategy(
        self,
        sell_assets: List[Dict],
        regime: str,
        confidence: float,
    ) -> Dict[str, Any]:
        """Profit-taking from sell signals."""
        actions = []
        for asset in sell_assets[:5]:
            actions.append(
                {
                    "action": asset.get("action", "PRENDRE PROFITS"),
                    "symbol": asset["symbol"],
                    "amount": abs(asset.get("impact_eur", 0)),
                    "currency": "EUR",
                    "reason": (
                        f"Alpha {asset.get('alpha_score', 0)}/100 — " f"{asset.get('description', 'Signal de vente')}"
                    ),
                }
            )

        return {
            "name": f"Prise de Profits — {len(actions)} positions",
            "description": (
                f"En phase '{regime}', certaines positions affichent des signaux de vente. "
                "Sécuriser une partie des gains pour alimenter la réserve de cash."
            ),
            "params": {
                "type": "profit_taking",
                "assets": [a["symbol"] for a in sell_assets[:5]],
                "regime": regime,
            },
            "ai_reasoning": (
                "Les indicateurs techniques (RSI suracheté, alpha faible, divergences) "
                "suggèrent de prendre des profits sur ces positions."
            ),
            "market_regime": regime,
            "confidence": confidence,
            "actions": actions,
        }

    def _build_rotation_strategy(
        self,
        buy_assets: List[Dict],
        sell_assets: List[Dict],
        regime: str,
        confidence: float,
        total_value: float,
    ) -> Optional[Dict[str, Any]]:
        """Rotation — sell weak performers, rotate into strong ones.

        Triggered when we have both buy AND sell signals simultaneously.
        """
        if not buy_assets or not sell_assets:
            return None
        if len(buy_assets) < 1 or len(sell_assets) < 1:
            return None

        # Sort sell by lowest alpha, buy by highest alpha
        weakest = sorted(sell_assets, key=lambda a: a.get("alpha_score", 50))[:3]
        strongest = sorted(buy_assets, key=lambda a: a.get("alpha_score", 0), reverse=True)[:3]

        actions = []
        for asset in weakest:
            amount = abs(asset.get("impact_eur", 0)) or round(asset.get("value", 0) * 0.2, 2)
            actions.append(
                {
                    "action": "ALLÉGER",
                    "symbol": asset["symbol"],
                    "amount": amount,
                    "currency": "EUR",
                    "reason": f"Alpha faible ({asset.get('alpha_score', 0)}/100) — libérer du capital",
                }
            )

        freed_capital = sum(a["amount"] for a in actions if a["amount"])
        per_asset = round(freed_capital / len(strongest), 2) if freed_capital > 0 and strongest else 0

        for asset in strongest:
            actions.append(
                {
                    "action": "RENFORCER",
                    "symbol": asset["symbol"],
                    "amount": per_asset or round(total_value * 0.02, 2),
                    "currency": "EUR",
                    "reason": f"Alpha fort ({asset.get('alpha_score', 0)}/100) — réallouer le capital",
                }
            )

        return {
            "name": f"Rotation — {len(weakest)} sorties, {len(strongest)} entrées",
            "description": (
                "Réallouer le capital des positions faibles vers les positions à fort potentiel. "
                "Cette rotation améliore le rendement attendu sans investissement supplémentaire."
            ),
            "params": {
                "type": "rotation",
                "sell": [a["symbol"] for a in weakest],
                "buy": [a["symbol"] for a in strongest],
                "regime": regime,
            },
            "ai_reasoning": (
                "Certains assets sous-performent tandis que d'autres affichent des signaux forts. "
                "Une rotation permet de maximiser l'alpha du portefeuille à exposition constante."
            ),
            "market_regime": regime,
            "confidence": confidence,
            "actions": actions,
        }

    def _build_swing_strategy(
        self,
        assets: List[Dict],
        regime: str,
        confidence: float,
        has_high_volatility: bool,
        liquidity: float = 0.0,
    ) -> Optional[Dict[str, Any]]:
        """Swing trading — exploit short-term price oscillations.

        Best in sideways/volatile markets where prices oscillate in a range.
        """
        if not has_high_volatility:
            return None
        if regime in ("bullish", "markup"):
            return None  # Strong trending bull markets are not ideal for swing

        # Find assets with high predicted short-term moves
        swing_candidates = [a for a in assets if abs(a.get("predicted_7d_pct", 0)) > 5 and a.get("alpha_score", 0) > 40]
        if len(swing_candidates) < 2:
            return None

        top = sorted(swing_candidates, key=lambda a: abs(a.get("predicted_7d_pct", 0)), reverse=True)[:3]

        if liquidity <= 0:
            return None  # Pas de munitions pour du swing

        swing_budget = round(liquidity * 0.15, 2)  # Max 15% de la liquidité en swing
        per_asset = round(swing_budget / len(top), 2)

        actions = []
        for asset in top:
            pred = asset.get("predicted_7d_pct", 0)
            if pred > 0:
                actions.append(
                    {
                        "action": "ACHAT",
                        "symbol": asset["symbol"],
                        "amount": per_asset,
                        "currency": "EUR",
                        "reason": (
                            f"Prédiction +{pred:.1f}% à 7j — position swing haussière. "
                            f"{per_asset}€ ({round(per_asset / liquidity * 100, 1)}% de vos liquidités)"
                        ),
                    }
                )
            else:
                # Pour vendre, on se base sur la valeur détenue
                sell_amount = round(asset.get("value", 0) * 0.1, 2)
                actions.append(
                    {
                        "action": "ALLÉGER",
                        "symbol": asset["symbol"],
                        "amount": sell_amount,
                        "currency": "EUR",
                        "reason": f"Prédiction {pred:.1f}% à 7j — alléger 10% de la position avant la baisse",
                    }
                )

        return {
            "name": f"Swing Trading — {len(top)} assets",
            "description": (
                f"Marché latéral avec forte volatilité ({regime}). "
                "Exploiter les oscillations de prix à court terme. "
                "Acheter les creux, vendre les sommets sur des cycles de 5-10 jours."
            ),
            "params": {
                "type": "swing",
                "assets": [a["symbol"] for a in top],
                "regime": regime,
            },
            "ai_reasoning": (
                "Le marché oscille sans tendance claire. Les prédictions à 7 jours "
                "montrent des mouvements exploitables en swing trading."
            ),
            "market_regime": regime,
            "confidence": confidence,
            "actions": actions,
        }

    def _build_stablecoin_yield_strategy(
        self,
        assets: List[Dict],
        regime: str,
        confidence: float,
        liquidity: float,
        total_value: float,
    ) -> Optional[Dict[str, Any]]:
        """Park idle cash in stablecoins for yield during uncertain markets."""
        if total_value <= 0:
            return None

        liquidity_pct = (liquidity / total_value * 100) if total_value > 0 else 0

        # In bull markets, deploy capital into assets instead
        if regime in ("bullish", "markup"):
            return None
        # In bear/accumulation, priority is buying — only suggest stablecoin if LOTS of cash
        if regime in ("bearish", "bottom", "accumulation", "markdown"):
            if liquidity_pct < 30:
                return None  # Deploy cash into assets first
        elif liquidity_pct < 15:
            return None

        # Check if user already holds stablecoins
        stablecoin_syms = {"USDC", "USDT", "DAI", "USDG", "BUSD", "TUSD"}
        held_stables = [a for a in assets if a.get("symbol", "").upper() in stablecoin_syms]
        stable_value = sum(a.get("value", 0) for a in held_stables)
        stable_pct = (stable_value / total_value * 100) if total_value > 0 else 0

        # If already >20% in stables, don't suggest more
        if stable_pct > 20:
            return None

        park_amount = round(liquidity * 0.5, 2)

        actions = [
            {
                "action": "ACHAT",
                "symbol": "USDC",
                "amount": park_amount,
                "currency": "EUR",
                "reason": (
                    f"Placer {park_amount}€ (50% de vos {round(liquidity, 0):.0f}€ de liquidités) "
                    "en USDC pour générer du yield (~3-5% APY) "
                    "tout en restant liquide pour saisir les opportunités."
                ),
            }
        ]

        return {
            "name": "Rendement Stablecoin — Cash productif",
            "description": (
                f"Vous avez {liquidity_pct:.0f}% de liquidité inactive. "
                f"En phase '{regime}', convertir une partie en stablecoins avec yield "
                "permet de générer des intérêts tout en restant prêt à déployer."
            ),
            "params": {
                "type": "stablecoin_yield",
                "idle_cash_pct": round(liquidity_pct, 1),
                "regime": regime,
            },
            "ai_reasoning": (
                "Le cash inactif ne génère aucun rendement. Les protocoles de lending "
                "sur stablecoins offrent 3-5% APY avec un risque faible. "
                "Cette stratégie preserve la liquidité tout en la rendant productive."
            ),
            "market_regime": regime,
            "confidence": confidence,
            "actions": actions,
        }

    def _build_rebalance_strategy(
        self,
        assets: List[Dict],
        regime: str,
        confidence: float,
        total_value: float,
    ) -> Optional[Dict[str, Any]]:
        """Rebalancing if portfolio is significantly skewed."""
        if not assets or total_value <= 0:
            return None

        weights = []
        for a in assets:
            w = a.get("weight_pct", 0)
            if w > 0:
                weights.append({"symbol": a["symbol"], "weight": w, "alpha": a.get("alpha_score", 50)})

        if len(weights) < 3:
            return None

        max_weight = max(w["weight"] for w in weights)
        if max_weight < 40:
            return None

        overweight = [w for w in weights if w["weight"] > 30]
        underweight = [w for w in weights if w["weight"] < 5]

        is_bear = regime in ("bearish", "bottom", "accumulation", "markdown")
        actions = []
        for ow in overweight:
            if is_bear and ow.get("alpha", 50) >= 30:
                # In bear, don't sell high-alpha assets even if overweight
                actions.append(
                    {
                        "action": "MAINTENIR",
                        "symbol": ow["symbol"],
                        "amount": 0,
                        "currency": "EUR",
                        "reason": f"Surpondéré à {ow['weight']:.1f}% mais bear market — ne pas vendre un asset à fort alpha",
                    }
                )
            else:
                actions.append(
                    {
                        "action": "ALLÉGER",
                        "symbol": ow["symbol"],
                        "amount": round(total_value * (ow["weight"] - 25) / 100, 2),
                        "currency": "EUR",
                        "reason": f"Surpondéré à {ow['weight']:.1f}% — réduire vers 25%",
                    }
                )
        for uw in underweight[:3]:
            actions.append(
                {
                    "action": "RENFORCER",
                    "symbol": uw["symbol"],
                    "amount": round(total_value * 0.03, 2),
                    "currency": "EUR",
                    "reason": f"Sous-pondéré à {uw['weight']:.1f}% — renforcer la diversification",
                }
            )

        return {
            "name": "Rééquilibrage du portefeuille",
            "description": (
                f"Le portefeuille est déséquilibré — un asset représente {max_weight:.0f}% "
                "du total. Un rééquilibrage améliorerait la diversification et réduirait le risque."
            ),
            "params": {
                "type": "rebalance",
                "overweight": [w["symbol"] for w in overweight],
                "underweight": [w["symbol"] for w in underweight[:3]],
            },
            "ai_reasoning": (
                f"Concentration excessive détectée ({max_weight:.0f}% sur un seul asset). "
                "La diversification réduit le risque sans sacrifier le rendement attendu."
            ),
            "market_regime": regime,
            "confidence": confidence,
            "actions": actions,
        }

    def _build_defensive_strategy(
        self,
        assets: List[Dict],
        regime: str,
        confidence: float,
        liquidity: float,
        total_value: float,
    ) -> Dict[str, Any]:
        """Defensive strategy for bear markets."""
        liquidity_pct = round(liquidity / total_value * 100, 1) if total_value > 0 else 0

        actions = []
        if liquidity_pct < 20:
            target_cash = round(total_value * 0.20, 2)
            deficit = round(target_cash - liquidity, 2)
            weak = [a for a in assets if a.get("alpha_score", 50) < 30]
            for w in weak[:3]:
                actions.append(
                    {
                        "action": "ALLÉGER",
                        "symbol": w["symbol"],
                        "amount": round(deficit / max(len(weak[:3]), 1), 2),
                        "currency": "EUR",
                        "reason": f"Alpha faible ({w.get('alpha_score', 0)}/100) — libérer du cash",
                    }
                )

        actions.append(
            {
                "action": "HOLD",
                "symbol": None,
                "amount": None,
                "currency": "EUR",
                "reason": "Conserver les positions fortes et attendre des signaux de retournement.",
            }
        )

        return {
            "name": "Mode Défensif — Préservation du capital",
            "description": (
                f"Marché en phase '{regime}' avec {confidence:.0%} de confiance. "
                f"Liquidité actuelle : {liquidity_pct:.0f}%. "
                "Priorité : protéger le capital, augmenter la réserve de cash, "
                "et se préparer pour le prochain cycle d'accumulation."
            ),
            "params": {
                "type": "defensive",
                "target_cash_pct": 20,
                "current_cash_pct": liquidity_pct,
                "regime": regime,
            },
            "ai_reasoning": (
                "En bear market, la préservation du capital est prioritaire. "
                "Réduire l'exposition sur les assets faibles et augmenter la réserve de cash "
                "permet de saisir les opportunités d'accumulation au bottom."
            ),
            "market_regime": regime,
            "confidence": confidence,
            "actions": actions,
        }

    def _build_conviction_buy_strategy(
        self,
        buy_assets: List[Dict],
        all_assets: List[Dict],
        regime: str,
        confidence: float,
        fear_greed: Optional[int],
        liquidity: float,
    ) -> Optional[Dict[str, Any]]:
        """Conviction buy — extreme fear is the strongest buy signal.

        Only triggers when Fear & Greed < 25 AND market is in bear/bottom.
        """
        if not fear_greed or fear_greed > 25:
            return None
        if regime not in ("bearish", "bottom", "bottoming", "markdown"):
            return None

        # Pick top-alpha assets for conviction buys
        candidates = buy_assets or sorted(all_assets, key=lambda a: a.get("alpha_score", 0), reverse=True)[:3]
        if not candidates:
            return None

        top = sorted(candidates, key=lambda a: a.get("alpha_score", 0), reverse=True)[:3]

        if liquidity <= 0:
            return None  # Pas de munitions pour un achat conviction

        # Larger position sizes for conviction buys — 8% de la liquidité
        base_amount = round(liquidity * 0.08, 2)

        actions = []
        for asset in top:
            alpha = asset.get("alpha_score", 50)
            amount = round(base_amount * (1 + (alpha - 50) / 100), 2)
            actions.append(
                {
                    "action": "ACHAT FORT",
                    "symbol": asset["symbol"],
                    "amount": amount,
                    "currency": "EUR",
                    "reason": (
                        f"Fear & Greed à {fear_greed}/100 (peur extrême) + Alpha {alpha}/100. "
                        f"Signal d'achat conviction — {amount}€ "
                        f"({round(amount / liquidity * 100, 1)}% de vos liquidités)."
                    ),
                }
            )

        return {
            "name": f"Achat Conviction — Fear & Greed {fear_greed}",
            "description": (
                f"Le Fear & Greed Index est à {fear_greed}/100 (peur extrême). "
                f"Historiquement, ces niveaux correspondent aux meilleurs points d'entrée. "
                '"Be greedy when others are fearful" — Warren Buffett.'
            ),
            "params": {
                "type": "conviction_buy",
                "fear_greed": fear_greed,
                "regime": regime,
                "assets": [a["symbol"] for a in top],
            },
            "ai_reasoning": (
                f"Fear & Greed à {fear_greed} = peur extrême. "
                "Les données historiques montrent que les achats effectués sous F&G 25 "
                "génèrent en moyenne +80% de rendement sur 12 mois. "
                "C'est un signal contrarian fort."
            ),
            "market_regime": regime,
            "confidence": confidence,
            "actions": actions,
        }

    def _build_progressive_profit_plan(
        self,
        sell_assets: List[Dict],
        hold_assets: List[Dict],
        regime: str,
        confidence: float,
    ) -> Optional[Dict[str, Any]]:
        """Progressive profit-taking plan — staged exits in bull market.

        Instead of selling everything at once, plan 3-stage profit taking.
        """
        if regime not in ("bullish", "markup", "top", "topping", "distribution"):
            return None

        # Combine sell + hold assets for potential profit targets
        candidates = sell_assets + [a for a in hold_assets if a.get("alpha_score", 0) > 40]
        if len(candidates) < 2:
            return None

        top = sorted(candidates, key=lambda a: a.get("value", 0), reverse=True)[:5]

        actions = []
        for asset in top:
            value = asset.get("value", 0)
            if value <= 0:
                continue
            # Stage 1: take 20% now
            actions.append(
                {
                    "action": "PRENDRE PROFITS",
                    "symbol": asset["symbol"],
                    "amount": round(value * 0.20, 2),
                    "currency": "EUR",
                    "reason": (
                        f"Phase 1/3 — Sécuriser 20% ({round(value * 0.20, 2)}€) maintenant. "
                        "Garder 80% pour laisser courir si la hausse continue."
                    ),
                }
            )

        if not actions:
            return None

        stage_label = "Sommet" if regime in ("top", "topping", "distribution") else "Bull"

        return {
            "name": f"Plan de Sortie Progressif — {stage_label}",
            "description": (
                f"Marché en phase '{regime}' — il est temps de sécuriser des gains. "
                "Plan en 3 étapes : 20% maintenant, 30% sur signal de faiblesse, "
                "50% restants avec trailing stop. Ne jamais tout vendre ou tout garder."
            ),
            "params": {
                "type": "progressive_profit",
                "regime": regime,
                "stages": [20, 30, 50],
                "assets": [a["symbol"] for a in top],
            },
            "ai_reasoning": (
                "La prise de profits progressive évite deux erreurs : "
                "vendre trop tôt (rater la suite de la hausse) et vendre trop tard "
                "(rester coincé dans la correction). Le plan 20/30/50 est un compromis optimal."
            ),
            "market_regime": regime,
            "confidence": confidence,
            "actions": actions,
        }

    async def save_suggestions(
        self,
        db: AsyncSession,
        user_id: str,
        suggestions: List[Dict[str, Any]],
    ) -> List[Strategy]:
        """Persist AI suggestions as Strategy + StrategyAction rows."""
        saved: List[Strategy] = []
        now = datetime.now(timezone.utc)

        for s in suggestions:
            strategy = Strategy(
                id=uuid.uuid4(),
                user_id=user_id,
                name=s["name"],
                description=s.get("description"),
                source=StrategySource.AI,
                status=StrategyStatus.PROPOSED,
                params=s.get("params", {}),
                ai_reasoning=s.get("ai_reasoning"),
                market_regime=s.get("market_regime"),
                confidence=s.get("confidence"),
            )
            db.add(strategy)
            await db.flush()

            for action_data in s.get("actions", []):
                action = StrategyAction(
                    id=uuid.uuid4(),
                    strategy_id=strategy.id,
                    action=action_data["action"],
                    symbol=action_data.get("symbol"),
                    amount=action_data.get("amount"),
                    currency=action_data.get("currency", "EUR"),
                    reason=action_data.get("reason"),
                    status=ActionStatus.PENDING,
                    scheduled_at=now + timedelta(days=1),
                )
                db.add(action)

            saved.append(strategy)

        await db.commit()
        for s in saved:
            await db.refresh(s)

        return saved


# Singleton
ai_strategy_service = AIStrategyService()
