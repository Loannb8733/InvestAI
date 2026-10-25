from dataclasses import dataclass, field


@dataclass
class ProjectionPoint:
    """Point mensuel de la courbe ; ``date_label`` au format ``Mar 2026``."""

    month: int
    date_label: str
    projected_p50: float
    projected_p25: float
    projected_p75: float
    target_line: float


@dataclass
class GoalProjection:
    """``rmc`` : effort mensuel requis sans rendement, ``rmc_with_returns`` avec ; ``probability_on_track`` en %
    (libellé ``Forte``, ``Moyenne`` ou ``Faible``) ; ``eta_date`` : mois d'arrivée estimé, au format ``Mar 2027``."""

    goal_id: str
    current_amount: float
    target_amount: float
    months_remaining: int
    rmc: float
    rmc_with_returns: float
    probability_on_track: float
    probability_label: str
    alert_message: str | None = None
    regime_label: str = ""
    strategy_type: str = "moderate"
    gold_shield_active: bool = False
    eta_date: str | None = None
    eta_months: int = 0
    gold_shield_advice: str | None = None
    curve: list[ProjectionPoint] = field(default_factory=list)
