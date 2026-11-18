from app.domains.notifications.formatting import amount, percent

PRIORITY_PREFIXES = {
    "critical": "\U0001f6a8",
    "high": "⚠️",
    "normal": "\U0001f514",
    "low": "\U0001f4ac",
}
DEFAULT_PREFIX = "\U0001f514"


def smart_alert_text(message: str, priority: str) -> str:
    """Message d'alerte précédé de l'emoji de sa priorité et de l'en-tête InvestAI."""
    return f"{PRIORITY_PREFIXES.get(priority, DEFAULT_PREFIX)} <b>InvestAI</b>\n\n{message}"


def anomaly_text(symbol: str, anomaly_type: str, severity: str, description: str, price_change_pct: float) -> str:
    return (
        f"<b>Anomalie détectée — {symbol}</b>\n"
        f"Type : {anomaly_type}\n"
        f"Sévérité : {severity}\n"
        f"Variation : {percent(price_change_pct, signed=price_change_pct > 0)}\n\n"
        f"{description}"
    )


def bottom_zone_text(
    symbol: str, current_price: float, estimated_bottom: float, confidence: float, distance_pct: float
) -> str:
    return (
        f"<b>Zone de Bottom détectée — {symbol}</b>\n"
        f"Prix actuel : {amount(current_price, '€')}\n"
        f"Bottom estimé : {amount(estimated_bottom, '€')}\n"
        f"Distance : {percent(distance_pct)}\n"
        f"Confiance : {percent(confidence * 100, decimals=0)}\n\n"
        "Information générale, pas un conseil en investissement."
    )
