"""Repères sur la phase de cycle, en information générale.

Les textes décrivent la phase de marché et les comportements historiquement observés ; ils ne disent jamais quoi
acheter, vendre ou à quel montant. Le champ ``action`` est un thème d'affichage (CONTEXTE, RISQUE, HISTORIQUE,
CONCENTRATION), pas une consigne.
"""

Advice = dict[str, str]

RISK_WEIGHT_CAP = 60.0

CONCENTRATION = "CONCENTRATION"
CONTEXT = "CONTEXTE"
RISK = "RISQUE"
HISTORY = "HISTORIQUE"


def _concentration_warning(max_risk_weight: float) -> Advice:
    return {
        "title": "Concentration de risque élevée",
        "description": (
            f"Un actif représente {max_risk_weight:.0f} % du risque total du portefeuille, au-delà du seuil de "
            f"{RISK_WEIGHT_CAP:.0f} % : sa variation pèse davantage sur l'ensemble que celle de tous les autres "
            "actifs réunis."
        ),
        "action": CONCENTRATION,
        "priority": "critical",
    }


def _bottom_advice() -> list[Advice]:
    return [
        {
            "title": "Phase de creux potentiel",
            "description": (
                "Les indicateurs (RSI, momentum, Fear & Greed) sont proches des niveaux observés lors des creux "
                "passés. Un creux ne se confirme qu'a posteriori : la baisse peut se prolonger."
            ),
            "action": CONTEXT,
            "priority": "high",
        },
        {
            "title": "Ce que montre l'historique",
            "description": (
                "Sur les cycles passés, les achats étalés dans le temps (DCA) en phase de creux ont lissé le prix "
                "d'entrée. Les performances passées ne préjugent pas des performances futures."
            ),
            "action": HISTORY,
            "priority": "medium",
        },
    ]


def _bearish_advice() -> list[Advice]:
    return [
        {
            "title": "Marché baissier",
            "description": (
                "La tendance de fond est baissière : prix sous leurs moyennes mobiles et momentum négatif. Les "
                "rebonds y sont fréquents et souvent de courte durée."
            ),
            "action": CONTEXT,
            "priority": "high",
        },
        {
            "title": "Levier et liquidations",
            "description": (
                "En marché baissier, les liquidations en cascade de positions à effet de levier amplifient les baisses."
            ),
            "action": RISK,
            "priority": "high",
        },
        {
            "title": "DCA et VCA : définitions",
            "description": (
                "Le DCA investit un montant fixe à intervalle régulier ; le VCA ajuste le montant pour suivre une "
                "trajectoire de valeur cible, donc investit davantage quand les prix baissent. Le simulateur de "
                "stratégies permet de tester ces règles avec vos propres paramètres."
            ),
            "action": HISTORY,
            "priority": "medium",
        },
    ]


def _top_advice() -> list[Advice]:
    return [
        {
            "title": "Phase d'euphorie",
            "description": (
                "Les indicateurs sont proches des niveaux observés lors des sommets passés (RSI élevé, Fear & Greed "
                "en zone d'avidité). Un sommet ne se confirme qu'a posteriori."
            ),
            "action": CONTEXT,
            "priority": "high",
        },
        {
            "title": "Volatilité en sommet de cycle",
            "description": (
                "Historiquement, les corrections qui suivent les phases d'euphorie ont été rapides et profondes, "
                "souvent de plus de 30 % sur les cryptoactifs."
            ),
            "action": RISK,
            "priority": "high",
        },
    ]


def _bullish_advice() -> list[Advice]:
    return [
        {
            "title": "Marché haussier",
            "description": (
                "La tendance de fond est haussière : prix au-dessus de leurs moyennes mobiles et momentum positif."
            ),
            "action": CONTEXT,
            "priority": "high",
        },
        {
            "title": "Ce que montre l'historique",
            "description": (
                "Les phases haussières se sont terminées par des corrections d'ampleur variable ; un repère comme "
                "l'EMA-20 sert souvent à suivre la tendance. Les performances passées ne préjugent pas des "
                "performances futures."
            ),
            "action": HISTORY,
            "priority": "medium",
        },
    ]


def _neutral_advice() -> list[Advice]:
    return [
        {
            "title": "Tendance incertaine",
            "description": "Les indicateurs ne dégagent pas de tendance nette ; le régime de marché est indéterminé.",
            "action": CONTEXT,
            "priority": "low",
        }
    ]


def _phase_advice(regime: str, fear_greed: int | None) -> list[Advice]:
    if regime == "bottom" or (fear_greed and fear_greed < 20):
        return _bottom_advice()
    if regime == "bearish":
        return _bearish_advice()
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
    """Repères généraux sur la phase de cycle, précédés d'un constat si un actif dépasse 60 % du risque.

    ``cycle_pos`` et ``portfolio_value`` sont conservés pour les appelants : aucun montant n'est plus calculé."""
    advice: list[Advice] = []
    if max_risk_weight > RISK_WEIGHT_CAP:
        advice.append(_concentration_warning(max_risk_weight))
    advice.extend(_phase_advice(regime, fear_greed))
    return advice
