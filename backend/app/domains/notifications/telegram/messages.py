from typing import Any

PRIORITY_PREFIXES = {
    "critical": "\U0001f6a8",
    "high": "⚠️",
    "normal": "\U0001f514",
    "low": "\U0001f4ac",
}
DEFAULT_PREFIX = "\U0001f514"

REGIME_TONES = {
    "bottoming": ("\U0001f50e Opportunité de Creux détectée", "Zone sécurisée pour accumulation progressive."),
    "accumulation": ("\U0001f4c8 Signal d'Accumulation", "Phase d'entrée progressive — Smart Money en action."),
    "markup": ("\U0001f680 Signal de Momentum confirmé", "Phase d'Expansion — laissez courir vos positions."),
    "topping": ("⚠️ Surchauffe détectée", "Prudence — sécurisez une partie de vos gains."),
    "distribution": ("\U0001f6a8 Phase de Distribution", "Prenez vos profits avant le retournement."),
    "markdown": ("\U0001f4c9 Marché en Markdown", "Patience — attendez les signaux de creux pour accumuler."),
    "bottom": ("\U0001f50e Opportunité de Creux détectée", "Zone sécurisée pour accumulation progressive."),
    "bearish": ("\U0001f4c9 Marché Baissier", "Conservation recommandée — préparez votre watchlist."),
    "bullish": ("\U0001f680 Signal de Momentum confirmé", "Phase d'Expansion — conditions favorables."),
    "top": ("⚠️ Sommet potentiel", "Prudence — sécurisez vos gains."),
}
DEFAULT_TONE = ("\U0001f514 Alerte Stratégie", "")


def smart_alert_text(message: str, priority: str) -> str:
    """Message d'alerte précédé de l'emoji de sa priorité et de l'en-tête InvestAI."""
    return f"{PRIORITY_PREFIXES.get(priority, DEFAULT_PREFIX)} <b>InvestAI</b>\n\n{message}"


def anomaly_text(symbol: str, anomaly_type: str, severity: str, description: str, price_change_pct: float) -> str:
    sign = "+" if price_change_pct > 0 else ""
    return (
        f"<b>Anomalie détectée — {symbol}</b>\n"
        f"Type : {anomaly_type}\n"
        f"Sévérité : {severity}\n"
        f"Variation : {sign}{price_change_pct:.1f}%\n\n"
        f"{description}"
    )


def bottom_zone_text(
    symbol: str, current_price: float, estimated_bottom: float, confidence: float, distance_pct: float
) -> str:
    return (
        f"<b>Zone de Bottom détectée — {symbol}</b>\n"
        f"Prix actuel : {current_price:,.2f} €\n"
        f"Bottom estimé : {estimated_bottom:,.2f} €\n"
        f"Distance : {distance_pct:.1f}%\n"
        f"Confiance : {confidence * 100:.0f}%\n\n"
        f"Opportunité d'achat potentielle."
    )


def regime_alert_text(symbol: str, action: str, regime: str, description: str) -> str:
    """Alerte de stratégie dont le titre et le conseil suivent la phase de marché."""
    title, hint = REGIME_TONES.get(regime, DEFAULT_TONE)
    return f"<b>{title} — {symbol}</b>\nAction : {action}\n{description}\n\n<i>{hint}</i>"


def alpha_keyboard(user_id: str, symbol: str, order_eur: float) -> dict[str, Any]:
    """Boutons d'un signal alpha : simuler l'impact sur la ruine, ou planifier l'ordre."""
    payload = f"alpha:{user_id}:{symbol}:{order_eur}"
    return {
        "inline_keyboard": [
            [
                {"text": "\U0001f50d Simuler Impact Ruine", "callback_data": f"sim_ruin:{payload}"},
                {"text": "✅ Marquer comme Planifié", "callback_data": f"plan_order:{payload}"},
            ]
        ]
    }
