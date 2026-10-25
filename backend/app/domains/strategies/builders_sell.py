from typing import Any

from app.domains.strategies.suggestion_types import AssetRow, Suggestion


def build_profit_taking_strategy(sell_assets: list[AssetRow], regime: str, confidence: float) -> Suggestion:
    actions = [
        {
            "action": asset.get("action", "PRENDRE PROFITS"),
            "symbol": asset["symbol"],
            "amount": round(abs(asset.get("impact_eur", 0)), 2),
            "currency": "EUR",
            "reason": (f"Alpha {asset.get('alpha_score', 0)}/100 — {asset.get('description', 'Signal de vente')}"),
        }
        for asset in sell_assets[:5]
    ]

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


def _rotation_actions(weakest: list[AssetRow], strongest: list[AssetRow], total_value: float) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for asset in weakest:
        amount = round(abs(asset.get("impact_eur", 0)), 2) or round(asset.get("value", 0) * 0.2, 2)
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
    return actions


def build_rotation_strategy(
    buy_assets: list[AssetRow],
    sell_assets: list[AssetRow],
    regime: str,
    confidence: float,
    total_value: float,
) -> Suggestion | None:
    """Rotation des 3 plus faibles alphas vendeurs vers les 3 plus forts acheteurs ; le capital libéré est réparti à
    parts égales, sinon 2 % de la valeur du portefeuille par achat."""
    if not buy_assets or not sell_assets:
        return None
    if len(buy_assets) < 1 or len(sell_assets) < 1:
        return None

    weakest = sorted(sell_assets, key=lambda a: a.get("alpha_score", 50))[:3]
    strongest = sorted(buy_assets, key=lambda a: a.get("alpha_score", 0), reverse=True)[:3]

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
        "actions": _rotation_actions(weakest, strongest, total_value),
    }


def _first_stage_exit(asset: AssetRow, value: Any) -> dict[str, Any]:
    return {
        "action": "PRENDRE PROFITS",
        "symbol": asset["symbol"],
        "amount": round(value * 0.20, 2),
        "currency": "EUR",
        "reason": (
            f"Phase 1/3 — Sécuriser 20% ({round(value * 0.20, 2)}€) maintenant. "
            "Garder 80% pour laisser courir si la hausse continue."
        ),
    }


def build_progressive_profit_plan(
    sell_assets: list[AssetRow],
    hold_assets: list[AssetRow],
    regime: str,
    confidence: float,
) -> Suggestion | None:
    """Sortie en trois temps (20/30/50) en phase haussière ou de sommet, sur les vendeurs et les conservés d'alpha
    > 40 ; seule la première tranche de 20 % devient une action."""
    if regime not in ("bullish", "markup", "top", "topping", "distribution"):
        return None

    candidates = sell_assets + [a for a in hold_assets if a.get("alpha_score", 0) > 40]
    if len(candidates) < 2:
        return None

    top = sorted(candidates, key=lambda a: a.get("value", 0), reverse=True)[:5]
    actions = [_first_stage_exit(asset, asset.get("value", 0)) for asset in top if asset.get("value", 0) > 0]
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
