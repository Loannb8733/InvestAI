from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domains.planning.simulations.models import SimulationType


class FIREProbabilisticParameters(BaseModel):
    """Taux en décimal (0.04 = 4 %) ; les valeurs omises sont déduites du portefeuille live et du profil."""

    current_value: float | None = Field(
        None,
        ge=0,
        description="Valeur de départ. Si omise, valeur live du portefeuille (metrics_service).",
    )
    monthly_contribution: float | None = Field(
        None,
        ge=0,
        description="Épargne mensuelle. Si omise, users.monthly_dca_eur (profil investisseur), sinon 0.",
    )
    annual_expenses: float = Field(
        ..., gt=0, description="Dépenses annuelles cibles à la retraite (euros d'aujourd'hui)."
    )
    withdrawal_rate: float = Field(default=0.04, ge=0.02, le=0.08)
    annual_return_mean: float | None = Field(
        None,
        ge=-0.05,
        le=0.20,
        description="Rendement annuel moyen. Si omis, dérivé de users.risk_profile, sinon 0.07.",
    )
    annual_volatility: float | None = Field(
        None,
        ge=0.01,
        le=0.80,
        description="Volatilité annuelle. Si omise, dérivée de users.risk_profile, sinon 0.15.",
    )
    inflation: float = Field(default=0.02, ge=0.0, le=0.10)
    index_contributions: bool = Field(
        default=True,
        description="Indexer l'épargne mensuelle sur l'inflation (le nombre FIRE l'est toujours).",
    )
    years_horizon: int = Field(default=30, gt=0, le=50)
    n_paths: int = Field(default=1000, ge=100, le=2000)
    seed: int | None = Field(None, description="Reproductibilité — tests uniquement.")


class FIREProbabilisticResult(BaseModel):
    """``prob_by_year`` : probabilité cumulée d'avoir atteint FIRE ; ``fire_year_p10/p50/p90`` : années
    optimiste, médiane et prudente (null si jamais atteint) ; ``survival_prob_30y`` : part des chemins qui
    survivent à 30 ans de retraits ; ``assumptions`` : hypothèses appliquées et provenance des défauts."""

    prob_by_year: list[dict[str, Any]]
    prob_at_horizon: float
    fire_year_p10: int | None
    fire_year_p50: int | None
    fire_year_p90: int | None
    final_value_p10: float
    final_value_p50: float
    final_value_p90: float
    fire_number_today: float
    survival_prob_30y: float
    median_path: list[dict[str, Any]]
    n_paths: int
    currency: str
    assumptions: dict[str, Any]


class ProjectionParameters(BaseModel):
    """Taux en pourcentage ; ``expense_ratio`` (TER) est déduit du rendement attendu."""

    years: int = Field(default=10, gt=0, le=50)
    expected_return: float = Field(default=7.0, ge=-20, le=50)
    expense_ratio: float = Field(
        default=0.0,
        ge=0,
        le=5,
        description="Annual expense ratio / TER (%), deducted from expected return.",
    )
    monthly_contribution: float = Field(default=0, ge=0)
    inflation_adjustment: bool = True
    inflation_rate: float = Field(default=2.0, ge=0, le=20)


class ProjectionResult(BaseModel):
    """``real_final_value`` : valeur finale corrigée de l'inflation."""

    current_value: float
    projections: list[dict[str, Any]]
    final_value: float
    total_contributions: float
    total_returns: float
    real_final_value: float
    currency: str


class DCAParameters(BaseModel):
    """``frequency`` : ``weekly``, ``monthly`` ou ``quarterly``."""

    total_amount: float = Field(..., gt=0)
    frequency: Literal["weekly", "monthly", "quarterly"] = "monthly"
    duration_months: int = Field(default=12, gt=0, le=120)
    expected_volatility: float = Field(default=20.0, ge=0, le=100)
    expected_return: float = Field(default=7.0, ge=-50, le=100)


class DCAResult(BaseModel):
    """Les champs historiques reprennent la médiane de la simulation multi-chemins ; ``prob_dca_beats_ls`` est
    la part (0-100) des chemins où le DCA finit au-dessus du Lump Sum, évalué sur les mêmes rendements."""

    total_invested: float
    final_value: float
    average_cost: float
    total_units: float
    return_percent: float
    projections: list[dict[str, Any]]
    currency: str
    dca_p10: float
    dca_p50: float
    dca_p90: float
    lumpsum_p10: float
    lumpsum_p50: float
    lumpsum_p90: float
    prob_dca_beats_ls: float
    n_paths: int


class SimulationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    simulation_type: SimulationType
    parameters: dict[str, Any]


class SimulationResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    simulation_type: str
    parameters: dict[str, Any]
    results: dict[str, Any] | None
    created_at: datetime
