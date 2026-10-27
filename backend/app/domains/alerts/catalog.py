from app.domains.alerts.schemas import AlertConditionInfo

CONDITIONS = (
    AlertConditionInfo(
        value="price_above", label="Prix supérieur à", description="Alerte quand le prix dépasse un seuil"
    ),
    AlertConditionInfo(
        value="price_below", label="Prix inférieur à", description="Alerte quand le prix passe sous un seuil"
    ),
    AlertConditionInfo(
        value="change_percent_up", label="Hausse de X%", description="Alerte quand le gain dépasse un pourcentage"
    ),
    AlertConditionInfo(
        value="change_percent_down", label="Baisse de X%", description="Alerte quand la perte dépasse un pourcentage"
    ),
    AlertConditionInfo(
        value="daily_change_up",
        label="Hausse journalière de X%",
        description="Alerte sur la variation journalière positive",
    ),
    AlertConditionInfo(
        value="daily_change_down",
        label="Baisse journalière de X%",
        description="Alerte sur la variation journalière négative",
    ),
    AlertConditionInfo(
        value="target_break_even",
        label="Retour au break-even",
        description="Alerte quand le prix dépasse le seuil de rentabilité (calculé automatiquement)",
    ),
    AlertConditionInfo(
        value="volatility_spike",
        label="Pic de volatilité",
        description="Alerte quand la contribution au risque augmente fortement en 24h",
    ),
    AlertConditionInfo(
        value="portfolio_drawdown",
        label="Repli du portefeuille (drawdown)",
        description="Alerte quand le portefeuille recule de X% depuis son plus-haut historique",
        is_portfolio=True,
        threshold_unit="%",
    ),
    AlertConditionInfo(
        value="concentration_hhi",
        label="Concentration excessive (HHI)",
        description="Alerte quand l'indice de concentration HHI dépasse un seuil (0 = dispersé, 1 = un seul actif)",
        is_portfolio=True,
        threshold_unit="0-1",
    ),
    AlertConditionInfo(
        value="allocation_drift",
        label="Dérive d'allocation",
        description="Alerte quand l'écart max vs votre allocation cible dépasse X points",
        is_portfolio=True,
        threshold_unit="pts",
    ),
)
