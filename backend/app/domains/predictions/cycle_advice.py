from app.ml.regime_detector import RegimeConfig

Advice = dict[str, str]

RISK_WEIGHT_CAP = 60.0


def _concentration_warning(max_risk_weight: float) -> Advice:
    return {
        "title": "Concentration de risque élevée",
        "description": (
            f"Un actif représente {max_risk_weight:.0f}% de votre risque total. "
            "Tout achat supplémentaire sur cet actif augmenterait dangereusement "
            "votre exposition. Privilégiez la diversification."
        ),
        "action": "DIVERSIFIER",
        "priority": "critical",
    }


def _dca_hint(portfolio_value: float, risk_mult: float) -> str:
    if portfolio_value <= 0:
        return ""
    low = round(portfolio_value * 0.02 * risk_mult, 2)
    high = round(portfolio_value * 0.05 * risk_mult, 2)
    return f" Montant suggéré par tranche : {low:.0f}–{high:.0f} € ({risk_mult:.1f}× régime)."  # noqa: RUF001


def _bottom_advice(dca_hint: str) -> list[Advice]:
    return [
        {
            "title": "Zone d'accumulation",
            "description": (
                "Les indicateurs suggèrent un creux potentiel. C'est historiquement "
                "le meilleur moment pour accumuler via DCA (achat périodique). "
                "Ne tentez pas de timer le bottom exact — étalez vos achats." + dca_hint
            ),
            "action": "DCA",
            "priority": "high",
        },
        {
            "title": "Préparation au rebond",
            "description": (
                "Identifiez les actifs de qualité qui ont le plus corrigé. "
                "Préparez votre watchlist pour être prêt quand le rebond se confirme."
            ),
            "action": "RECHERCHE",
            "priority": "medium",
        },
    ]


def _bearish_advice(dca_hint: str) -> list[Advice]:
    return [
        {
            "title": "Zone d'accumulation — Be greedy when others are fearful",
            "description": (
                "Marché baissier = opportunité d'accumulation ! "
                "Les prix sont décotés, c'est historiquement le meilleur moment "
                "pour construire son portefeuille via DCA/VCA agressif." + dca_hint
            ),
            "action": "DCA",
            "priority": "high",
        },
        {
            "title": "Évitez le levier",
            "description": (
                "Accumulez avec du capital réel, jamais avec du levier. "
                "Les liquidations en cascade amplifient les baisses en bear market."
            ),
            "action": "RISQUE",
            "priority": "high",
        },
        {
            "title": "VCA > DCA en bear market",
            "description": (
                "Le Value Cost Averaging (investir plus quand les prix baissent) "
                "surperforme le DCA classique en marché volatile. "
                "Augmentez vos montants d'achat quand les prix chutent davantage."
            ),
            "action": "VCA",
            "priority": "medium",
        },
    ]


def _top_advice() -> list[Advice]:
    return [
        {
            "title": "Prise de profits",
            "description": (
                "Signes d'euphorie — prenez des profits partiels (20-30%). "
                "Personne ne regrette d'avoir sécurisé des gains."
            ),
            "action": "VENDRE",
            "priority": "high",
        },
        {
            "title": "Stop-loss protecteurs",
            "description": (
                "Placez des stop-loss 10-15% sous le prix actuel pour protéger "
                "vos positions restantes en cas de correction brutale."
            ),
            "action": "PROTÉGER",
            "priority": "high",
        },
        {
            "title": "N'achetez pas sur l'euphorie",
            "description": "Quand tout le monde est euphorique, c'est le pire moment pour acheter. Résistez au FOMO.",
            "action": "ATTENDRE",
            "priority": "medium",
        },
    ]


def _bullish_advice() -> list[Advice]:
    return [
        {
            "title": "Préparez la prise de profits",
            "description": (
                "Tendance haussière — laissez courir vos positions mais "
                "définissez VOS niveaux de sortie maintenant. "
                '"Be fearful when others are greedy." Ne soyez pas le dernier à vendre.'
            ),
            "action": "PLANIFIER",
            "priority": "high",
        },
        {
            "title": "Stop-loss progressifs",
            "description": (
                "Remontez progressivement vos stop-loss pour verrouiller les gains. "
                "Un trailing stop sous l'EMA-20 protège sans couper trop tôt."
            ),
            "action": "PROTÉGER",
            "priority": "high",
        },
        {
            "title": "Réduisez le DCA",
            "description": (
                "En marché haussier, les prix sont chers. Réduisez vos montants "
                "d'achat réguliers et gardez du cash pour accumuler au prochain creux."
            ),
            "action": "ATTENDRE",
            "priority": "medium",
        },
    ]


def _neutral_advice() -> list[Advice]:
    return [
        {
            "title": "Observation",
            "description": (
                "Tendance incertaine — attendez un signal plus clair avant de prendre de nouvelles positions."
            ),
            "action": "ATTENDRE",
            "priority": "low",
        }
    ]


def _phase_advice(regime: str, fear_greed: int | None, dca_hint: str) -> list[Advice]:
    if regime == "bottom" or (fear_greed and fear_greed < 20):
        return _bottom_advice(dca_hint)
    if regime == "bearish":
        return _bearish_advice(dca_hint)
    if regime == "top" or (fear_greed and fear_greed > 80):
        return _top_advice()
    if regime == "bullish":
        return _bullish_advice()
    return _neutral_advice()


def cycle_advice(
    regime: str,
    cycle_pos: int,
    fear_greed: int | None,
    portfolio_value: float = 0.0,
    max_risk_weight: float = 0.0,
) -> list[Advice]:
    """Conseils de cycle : alerte si un actif dépasse 60 % du risque, tranches DCA de 2-5 % modulées par le régime."""
    advice: list[Advice] = []
    if max_risk_weight > RISK_WEIGHT_CAP:
        advice.append(_concentration_warning(max_risk_weight))
    risk_mult = RegimeConfig.from_regime(regime).risk_multiplier
    advice.extend(_phase_advice(regime, fear_greed, _dca_hint(portfolio_value, risk_mult)))
    return advice
