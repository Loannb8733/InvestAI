from typing import Any


def _level(price: float) -> str:
    if abs(price) >= 100:
        return f"{price:.0f}"
    if abs(price) >= 1:
        return f"{price:.2f}"
    return f"{price:.4g}"


def _bottom(trend: str) -> str:
    if trend == "bearish":
        return (
            "Zone de creux potentiel avec une tendance encore baissière. "
            "Historiquement, ces phases ont été associées à une accumulation "
            "progressive plutôt qu'à un timing précis du point bas."
        )
    return (
        "Signaux de creux détectés ; un rebond pourrait se confirmer. "
        "Ces configurations ont historiquement précédé des phases de reprise."
    )


def _bearish(trend: str, trend_strength: float, current_price: float) -> str:
    if trend == "bearish" and trend_strength > 50:
        return (
            "Marché baissier confirmé : les prix sont décotés par rapport aux "
            f"plus hauts récents. Support technique estimé vers {_level(current_price * 0.9)}."
        )
    if trend == "bullish":
        return (
            "Signal haussier en marché baissier — possible retournement, sans garantie. "
            "Ces zones ont historiquement présenté un rapport rendement/risque plus favorable."
        )
    return (
        "Marché baissier — contexte historiquement associé aux phases "
        "d'accumulation ; les creux de cycle s'y sont souvent formés."
    )


def _bullish(trend: str, trend_strength: float, resistance: float) -> str:
    if trend == "bullish" and trend_strength > 50:
        return (
            "Tendance haussière forte. Le risque de retournement tend à "
            f"augmenter à mesure que le mouvement s'étend ; résistance à surveiller : {_level(resistance)}."
        )
    return f"Marché haussier : la dynamique reste positive. Résistance à surveiller : {_level(resistance)}."


def _regime_body(
    regime: str, trend: str, trend_strength: float, current_price: float, support: float, resistance: float
) -> str | None:
    if regime == "bottom":
        return _bottom(trend)
    if regime == "bearish":
        return _bearish(trend, trend_strength, current_price)
    if regime == "top":
        return (
            "Signes de sommet de marché : le risque de correction est "
            f"historiquement élevé dans ces configurations. Support à surveiller : {_level(support)}."
        )
    if regime == "bullish":
        return _bullish(trend, trend_strength, resistance)
    return None


def _trend_body(trend: str, trend_strength: float) -> str:
    if trend == "bullish" and trend_strength > 50:
        return "Tendance haussière forte détectée."
    if trend == "bullish":
        return "Tendance légèrement haussière détectée."
    if trend == "bearish" and trend_strength > 50:
        return "Tendance baissière forte détectée ; prix décotés par rapport aux plus hauts récents."
    if trend == "bearish":
        return "Tendance légèrement baissière détectée."
    return "Tendance neutre — pas de signal directionnel clair."


def _recommendation_body(
    trend: str,
    trend_strength: float,
    current_price: float,
    support: float,
    resistance: float,
    regime_info: dict[str, Any] | None = None,
) -> str:
    regime = regime_info.get("dominant_regime") if regime_info else None
    reg_conf = regime_info.get("confidence", 0) if regime_info else 0
    if reg_conf > 0.4 and regime:
        body = _regime_body(regime, trend, trend_strength, current_price, support, resistance)
        if body is not None:
            return body
    return _trend_body(trend, trend_strength)


def generate_recommendation(
    trend: str,
    trend_strength: float,
    current_price: float,
    support: float,
    resistance: float,
    regime_info: dict[str, Any] | None = None,
) -> str:
    """Constat sur le régime (au-delà de 40 % de confiance) ou la tendance, jamais une consigne, toujours suivi
    de l'avertissement « pas un conseil en investissement »."""
    from app.services.ai_strategy_service import AI_DISCLAIMER

    body = _recommendation_body(trend, trend_strength, current_price, support, resistance, regime_info)
    return f"{body}\n\n{AI_DISCLAIMER}"
