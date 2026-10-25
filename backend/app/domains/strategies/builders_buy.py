from typing import Any

from app.domains.strategies.suggestion_types import BEAR_REGIMES, BULL_REGIMES, AssetRow, Suggestion, asset_count
from app.services.contrarian_stats_service import format_reasoning


def _vca_action(asset: AssetRow, base_amount: float, liquidity: float) -> dict[str, Any]:
    alpha = asset.get("alpha_score", 50)
    multiplier = 1.0 + (alpha - 50) / 100
    amount = round(base_amount * max(multiplier, 0.5), 2)
    return {
        "action": "VCA",
        "symbol": asset["symbol"],
        "amount": amount,
        "currency": "EUR",
        "reason": (
            f"Alpha {alpha}/100 — investir {amount}€ soit ~{round(amount / liquidity * 100, 1)}% "
            f"de vos liquidités. {asset.get('description', '')}"
        ),
    }


def _vca_description(regime: str, is_accumulation: bool, total_vca: float, liquidity: float) -> str:
    if is_accumulation:
        return (
            f"Marché en phase '{regime}' — les prix sont bas, c'est le moment d'accumuler. "
            f"Budget total : {total_vca:.0f}€ sur {round(liquidity, 0):.0f}€ de liquidités disponibles "
            f"({round(total_vca / liquidity * 100, 1)}%). "
            "Le VCA investit davantage quand les prix baissent, maximisant les quantités achetées."
        )
    return (
        f"Marché en phase '{regime}' avec forte volatilité. "
        f"Budget total : {total_vca:.0f}€ sur {round(liquidity, 0):.0f}€ de liquidités disponibles. "
        "Le VCA ajuste les montants : plus quand les prix sont bas, moins quand ils sont hauts."
    )


def build_vca_strategy(
    buy_assets: list[AssetRow],
    regime: str,
    confidence: float,
    liquidity: float,
    has_high_volatility: bool,
) -> Suggestion | None:
    """VCA sur les 4 meilleurs alphas en marché baissier ou volatil : 4 % de la liquidité par actif, modulés par
    l'alpha (80 → 1,3x, plancher 0,5x)."""
    if not buy_assets:
        return None
    is_accumulation = regime in BEAR_REGIMES
    if not has_high_volatility and not is_accumulation:
        return None

    top = sorted(buy_assets, key=lambda a: a.get("alpha_score", 0), reverse=True)[:4]
    if liquidity <= 0:
        return None
    base_amount = round(liquidity * 0.04, 2)
    actions = [_vca_action(asset, base_amount, liquidity) for asset in top]
    total_vca = sum(a["amount"] for a in actions)

    return {
        "name": f"VCA Dynamique — {asset_count(len(top))}",
        "description": _vca_description(regime, is_accumulation, total_vca, liquidity),
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


def _dca_intensity(regime: str) -> tuple[str, float, str]:
    if regime in BEAR_REGIMES:
        return (
            "Agressif",
            0.06,
            (
                f"Marché en phase '{regime}' — c'est le meilleur moment pour accumuler. "
                "Les prix sont décotés, le DCA agressif permet de baisser son prix moyen d'achat. "
                '"Be greedy when others are fearful."'
            ),
        )
    if regime in BULL_REGIMES:
        return (
            "Modéré",
            0.03,
            (
                f"Marché en phase '{regime}' — tendance haussière. "
                "Continuer le DCA avec des montants standards. Rester discipliné."
            ),
        )
    return (
        "Sélectif",
        0.03,
        f"Marché en phase '{regime}'. DCA uniquement sur les assets avec les meilleurs scores alpha.",
    )


def _dca_action(asset: AssetRow, liquidity: float, pct: float) -> dict[str, Any]:
    amount = round(abs(asset.get("impact_eur", 0)), 2)
    if amount == 0 or amount > liquidity * 0.5:
        amount = round(liquidity * pct, 2)
    return {
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


def build_dca_strategy(
    buy_assets: list[AssetRow],
    regime: str,
    confidence: float,
    liquidity: float,
    has_high_volatility: bool,
) -> Suggestion | None:
    """DCA sur les 5 meilleurs alphas, écarté en marché baissier volatil où le VCA prime : montant = impact_eur,
    ou une part fixe de la liquidité s'il est nul ou dépasse la moitié de celle-ci."""
    if not buy_assets:
        return None
    if has_high_volatility and regime in BEAR_REGIMES:
        return None

    top = sorted(buy_assets, key=lambda a: a.get("alpha_score", 0), reverse=True)[:5]
    intensity, pct, reasoning = _dca_intensity(regime)
    if liquidity <= 0:
        return None

    return {
        "name": f"DCA {intensity} — {asset_count(len(top))}",
        "description": reasoning,
        "params": {
            "type": f"dca_{intensity.lower()}",
            "assets": [a["symbol"] for a in top],
            "regime": regime,
        },
        "ai_reasoning": reasoning,
        "market_regime": regime,
        "confidence": confidence,
        "actions": [_dca_action(asset, liquidity, pct) for asset in top],
    }


def _conviction_action(asset: AssetRow, base_amount: float, fear_greed: int, liquidity: float) -> dict[str, Any]:
    alpha = asset.get("alpha_score", 50)
    amount = round(base_amount * (1 + (alpha - 50) / 100), 2)
    return {
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


def build_conviction_buy_strategy(
    buy_assets: list[AssetRow],
    all_assets: list[AssetRow],
    regime: str,
    confidence: float,
    fear_greed: int | None,
    liquidity: float,
    contrarian_stats: dict[str, Any] | None = None,
) -> Suggestion | None:
    """Achat conviction si Fear & Greed ≤ 25 en phase baissière : 8 % de la liquidité modulés par l'alpha ; le
    raisonnement cite les statistiques contrariennes en cache, sinon une phrase qualitative sans chiffres."""
    if not fear_greed or fear_greed > 25:
        return None
    if regime not in ("bearish", "bottom", "bottoming", "markdown"):
        return None

    candidates = buy_assets or sorted(all_assets, key=lambda a: a.get("alpha_score", 0), reverse=True)[:3]
    if not candidates:
        return None
    top = sorted(candidates, key=lambda a: a.get("alpha_score", 0), reverse=True)[:3]
    if liquidity <= 0:
        return None

    base_amount = round(liquidity * 0.08, 2)
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
        "ai_reasoning": format_reasoning(fear_greed, contrarian_stats),
        "market_regime": regime,
        "confidence": confidence,
        "actions": [_conviction_action(asset, base_amount, fear_greed, liquidity) for asset in top],
    }
