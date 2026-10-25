from typing import Any

from app.domains.portfolio.classification import STABLECOIN_SYMBOLS
from app.domains.strategies.suggestion_types import BEAR_REGIMES, BULL_REGIMES, AssetRow, Suggestion


def _rebalance_actions(
    overweight: list[dict[str, Any]],
    underweight: list[dict[str, Any]],
    is_bear: bool,
    total_value: float,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for ow in overweight:
        if is_bear and ow.get("alpha", 50) >= 30:
            actions.append(
                {
                    "action": "MAINTENIR",
                    "symbol": ow["symbol"],
                    "amount": 0,
                    "currency": "EUR",
                    "reason": (
                        f"Surpondéré à {ow['weight']:.1f}% mais bear market — ne pas vendre un asset à fort alpha"
                    ),
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
    return actions


def build_rebalance_strategy(
    assets: list[AssetRow],
    regime: str,
    confidence: float,
    total_value: float,
) -> Suggestion | None:
    """Rééquilibrage dès qu'un actif pèse 40 % ou plus : alléger les lignes > 30 % vers 25 % (sauf alpha ≥ 30 en
    marché baissier, alors maintenues) et renforcer de 3 % du portefeuille jusqu'à trois lignes < 5 %."""
    if not assets or total_value <= 0:
        return None

    weights = [
        {"symbol": a["symbol"], "weight": a.get("weight_pct", 0), "alpha": a.get("alpha_score", 50)}
        for a in assets
        if a.get("weight_pct", 0) > 0
    ]
    if len(weights) < 3:
        return None

    max_weight = max(w["weight"] for w in weights)
    if max_weight < 40:
        return None

    overweight = [w for w in weights if w["weight"] > 30]
    underweight = [w for w in weights if w["weight"] < 5]
    is_bear = regime in BEAR_REGIMES

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
        "actions": _rebalance_actions(overweight, underweight, is_bear, total_value),
    }


def _idle_cash_is_low(regime: str, liquidity_pct: float) -> bool:
    if regime in BEAR_REGIMES:
        return liquidity_pct < 30
    return liquidity_pct < 15


def build_stablecoin_yield_strategy(
    assets: list[AssetRow],
    regime: str,
    confidence: float,
    liquidity: float,
    total_value: float,
) -> Suggestion | None:
    """Placer la moitié de la liquidité en USDC hors marché haussier, si le cash inactif atteint 15 % (30 % en marché
    baissier, où l'achat d'actifs prime) et que les stablecoins détenus ne dépassent pas 20 %."""
    if total_value <= 0:
        return None

    liquidity_pct = (liquidity / total_value * 100) if total_value > 0 else 0
    if regime in BULL_REGIMES:
        return None
    if _idle_cash_is_low(regime, liquidity_pct):
        return None

    held_stables = [a for a in assets if a.get("symbol", "").upper() in STABLECOIN_SYMBOLS]
    stable_value = sum(a.get("value", 0) for a in held_stables)
    stable_pct = (stable_value / total_value * 100) if total_value > 0 else 0
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


def _swing_action(asset: AssetRow, per_asset: float, liquidity: float) -> dict[str, Any]:
    pred = asset.get("predicted_7d_pct", 0)
    if pred > 0:
        return {
            "action": "ACHAT",
            "symbol": asset["symbol"],
            "amount": per_asset,
            "currency": "EUR",
            "reason": (
                f"Prédiction +{pred:.1f}% à 7j — position swing haussière. "
                f"{per_asset}€ ({round(per_asset / liquidity * 100, 1)}% de vos liquidités)"
            ),
        }
    return {
        "action": "ALLÉGER",
        "symbol": asset["symbol"],
        "amount": round(asset.get("value", 0) * 0.1, 2),
        "currency": "EUR",
        "reason": f"Prédiction {pred:.1f}% à 7j — alléger 10% de la position avant la baisse",
    }


def build_swing_strategy(
    assets: list[AssetRow],
    regime: str,
    confidence: float,
    has_high_volatility: bool,
    liquidity: float = 0.0,
) -> Suggestion | None:
    """Swing en marché volatil sans tendance haussière, sur les 3 plus fortes prévisions à 7 j (> 5 %, alpha > 40) :
    15 % de la liquidité répartis à l'achat, ventes à 10 % de la valeur détenue."""
    if not has_high_volatility:
        return None
    if regime in BULL_REGIMES:
        return None

    swing_candidates = [a for a in assets if abs(a.get("predicted_7d_pct", 0)) > 5 and a.get("alpha_score", 0) > 40]
    if len(swing_candidates) < 2:
        return None

    top = sorted(
        swing_candidates,
        key=lambda a: abs(a.get("predicted_7d_pct", 0)),
        reverse=True,
    )[:3]
    if liquidity <= 0:
        return None

    swing_budget = round(liquidity * 0.15, 2)
    per_asset = round(swing_budget / len(top), 2)

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
        "actions": [_swing_action(asset, per_asset, liquidity) for asset in top],
    }
