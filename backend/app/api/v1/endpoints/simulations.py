"""Simulations endpoints for what-if scenarios, projections, and FIRE calculator."""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.portfolio import Portfolio
from app.models.simulation import Simulation, SimulationType
from app.models.user import User
from app.services.metrics_service import metrics_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ Internal helpers ============


async def _get_portfolio_live_data(db: AsyncSession, user_id: str, currency: str = "EUR") -> Dict[str, Any]:
    """Fetch reconciled portfolio data from metrics_service.

    Returns dict with:
      - total_value: float (live portfolio value in target currency)
      - assets: list of dicts per asset with symbol, current_value, risk_weight, etc.
    """
    dashboard = await metrics_service.get_user_dashboard_metrics(db, user_id, currency=currency, days=0)
    # Collect per-asset data from all portfolios (includes risk_weight)
    result = await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
    portfolios = result.scalars().all()

    all_assets = []
    for portfolio in portfolios:
        pm = await metrics_service.get_portfolio_metrics(db, str(portfolio.id), currency=currency)
        all_assets.extend(pm.get("assets", []))

    return {
        "total_value": dashboard.get("total_value", 0.0),
        "assets": all_assets,
    }


# ============ Schemas ============


class FIREParameters(BaseModel):
    """Parameters for FIRE calculation."""

    current_portfolio_value: Optional[float] = Field(
        None,
        description="Override portfolio value. If omitted, uses live dashboard value.",
    )
    monthly_contribution: float = Field(default=0, ge=0)
    monthly_expenses: float = Field(..., gt=0)
    expected_annual_return: float = Field(default=7.0, ge=0, le=30)
    expense_ratio: float = Field(
        default=0.0,
        ge=0,
        le=5,
        description="Annual expense ratio / TER (%), deducted from expected return.",
    )
    inflation_rate: float = Field(default=2.0, ge=0, le=20)
    withdrawal_rate: float = Field(default=4.0, gt=0, le=10)
    target_years: int = Field(default=30, gt=0, le=50)


class FIREResult(BaseModel):
    """FIRE calculation result."""

    fire_number: float
    years_to_fire: Optional[int]
    monthly_passive_income: float
    projected_values: List[Dict[str, Any]]
    is_fire_achieved: bool
    current_progress_percent: float
    currency: str


class ProjectionParameters(BaseModel):
    """Parameters for portfolio projection."""

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
    """Portfolio projection result."""

    current_value: float
    projections: List[Dict[str, Any]]
    final_value: float
    total_contributions: float
    total_returns: float
    real_final_value: float  # Inflation-adjusted
    currency: str


class DCAParameters(BaseModel):
    """Parameters for DCA simulation."""

    total_amount: float = Field(..., gt=0)
    frequency: str = Field(default="monthly")  # weekly, monthly, quarterly
    duration_months: int = Field(default=12, gt=0, le=120)
    expected_volatility: float = Field(default=20.0, ge=0, le=100)
    expected_return: float = Field(default=7.0, ge=-50, le=100)


class DCAResult(BaseModel):
    """DCA simulation result (distribution multi-chemins).

    Correction audit : les champs historiques (``final_value``, ``average_cost``,
    ``total_units``, ``return_percent``, ``projections``) sont désormais alimentés
    par la MÉDIANE (p50) d'une simulation Monte Carlo à ``n_paths`` trajectoires —
    plus jamais par un tirage aléatoire unique. Les nouveaux champs exposent la
    distribution complète (p10/p50/p90 par stratégie) et la probabilité que le
    DCA batte le Lump Sum, calculée sur les MÊMES chemins de rendements.
    """

    total_invested: float
    final_value: float
    average_cost: float
    total_units: float
    return_percent: float
    projections: List[Dict[str, Any]]
    currency: str
    # Distribution multi-chemins (nouveaux champs)
    dca_p10: float
    dca_p50: float
    dca_p90: float
    lumpsum_p10: float
    lumpsum_p50: float
    lumpsum_p90: float
    prob_dca_beats_ls: float  # % des chemins (0-100) où la valeur finale DCA > Lump Sum
    n_paths: int


class WhatIfParameters(BaseModel):
    """Parameters for what-if scenario."""

    scenario_type: str  # price_change, allocation_change, withdrawal
    asset_changes: Dict[str, float] = {}  # symbol -> percent change
    market_change: Optional[float] = None  # uniform market shock (e.g. -20)
    use_risk_weighting: bool = True  # weight market shock by asset risk
    withdrawal_amount: float = Field(default=0, ge=0)
    contribution_amount: float = Field(default=0, ge=0)


class WhatIfResult(BaseModel):
    """What-if scenario result."""

    current_value: float
    projected_value: float
    difference: float
    difference_percent: float
    asset_breakdown: List[Dict[str, Any]]
    currency: str


class SimulationCreate(BaseModel):
    """Schema for creating a simulation."""

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    simulation_type: SimulationType
    parameters: Dict[str, Any]


class SimulationResponse(BaseModel):
    """Simulation response schema."""

    id: UUID
    name: str
    description: Optional[str]
    simulation_type: str
    parameters: Dict[str, Any]
    results: Optional[Dict[str, Any]]
    created_at: datetime


class SimulationTypeInfo(BaseModel):
    """Simulation type information."""

    value: str
    label: str
    description: str


# ============ Endpoints ============


@router.get("/types", response_model=List[SimulationTypeInfo])
async def list_simulation_types() -> List[SimulationTypeInfo]:
    """List all available simulation types."""
    types = [
        {
            "value": "fire",
            "label": "FIRE Calculator",
            "description": "Calculez votre nombre FIRE et le temps pour l'atteindre",
        },
        {
            "value": "projection",
            "label": "Projection de portefeuille",
            "description": "Projetez la valeur future de votre portefeuille",
        },
        {
            "value": "dca",
            "label": "DCA Simulation",
            "description": "Simulez une strategie d'investissement programme (DCA)",
        },
        {
            "value": "what_if",
            "label": "Scenario What-If",
            "description": "Analysez l'impact de changements sur votre portefeuille",
        },
        {
            "value": "rebalance",
            "label": "Reequilibrage",
            "description": "Simulez un reequilibrage de votre allocation",
        },
    ]
    return [SimulationTypeInfo(**t) for t in types]


@router.post("/fire", response_model=FIREResult)
async def calculate_fire(
    params: FIREParameters,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FIREResult:
    """Calculate FIRE (Financial Independence, Retire Early) metrics.

    Uses live portfolio value from metrics_service if current_portfolio_value is not provided.
    """
    currency = getattr(current_user, "preferred_currency", "EUR") or "EUR"

    # Use live dashboard value if not overridden
    if params.current_portfolio_value is not None:
        portfolio_value = params.current_portfolio_value
    else:
        live = await _get_portfolio_live_data(db, str(current_user.id), currency)
        portfolio_value = live["total_value"]

    if portfolio_value <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La valeur du portefeuille doit être positive pour le calcul FIRE.",
        )

    # FIRE number = annual expenses / withdrawal rate
    annual_expenses = params.monthly_expenses * 12
    if params.withdrawal_rate <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le taux de retrait doit être supérieur à 0",
        )
    fire_number = annual_expenses / (params.withdrawal_rate / 100)

    # Monthly passive income at current portfolio value
    monthly_passive_income = portfolio_value * (params.withdrawal_rate / 100) / 12

    # Check if already FIRE
    is_fire_achieved = portfolio_value >= fire_number
    current_progress = (portfolio_value / fire_number) * 100

    # Project portfolio growth (net of expense ratio / TER) — Decimal precision
    projections = []
    value = Decimal(str(portfolio_value))
    net_annual_return = Decimal(str(params.expected_annual_return)) - Decimal(str(params.expense_ratio))
    monthly_return = net_annual_return / 100 / 12
    monthly_contribution = Decimal(str(params.monthly_contribution))
    inflation = Decimal(str(params.inflation_rate)) / 100
    withdrawal = Decimal(str(params.withdrawal_rate)) / 100
    years_to_fire = None

    for year in range(params.target_years + 1):
        # Adjust expenses for inflation
        adjusted_expenses = Decimal(str(annual_expenses)) * ((1 + inflation) ** year)
        adjusted_fire_number = adjusted_expenses / withdrawal

        projections.append(
            {
                "year": year,
                "portfolio_value": float(round(value, 2)),
                "fire_number": float(round(adjusted_fire_number, 2)),
                "is_fire": value >= adjusted_fire_number,
                "progress_percent": float(round(value / adjusted_fire_number * 100, 1)),
            }
        )

        # Check if FIRE achieved this year
        if years_to_fire is None and value >= adjusted_fire_number:
            years_to_fire = year

        # Grow portfolio for next year (monthly compounding + contributions)
        for _ in range(12):
            value = value * (1 + monthly_return) + monthly_contribution

    return FIREResult(
        fire_number=round(fire_number, 2),
        years_to_fire=years_to_fire,
        monthly_passive_income=round(monthly_passive_income, 2),
        projected_values=projections,
        is_fire_achieved=is_fire_achieved,
        current_progress_percent=round(current_progress, 1),
        currency=currency,
    )


@router.post("/projection", response_model=ProjectionResult)
async def project_portfolio(
    params: ProjectionParameters,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectionResult:
    """Project portfolio value over time using live reconciled values."""
    currency = getattr(current_user, "preferred_currency", "EUR") or "EUR"
    live = await _get_portfolio_live_data(db, str(current_user.id), currency)
    current_value = live["total_value"]

    if current_value <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La valeur du portefeuille est nulle. Ajoutez des actifs d'abord.",
        )

    # Project growth (net of expense ratio / TER) — Decimal precision
    projections = []
    value = Decimal(str(current_value))
    initial_value = value
    net_annual_return = Decimal(str(params.expected_return)) - Decimal(str(params.expense_ratio))
    monthly_return = net_annual_return / 100 / 12
    monthly_contribution = Decimal(str(params.monthly_contribution))
    inflation = Decimal(str(params.inflation_rate)) / 100
    total_contributions = Decimal("0")

    for year in range(params.years + 1):
        real_value = value
        if params.inflation_adjustment:
            real_value = value / ((1 + inflation) ** year)

        projections.append(
            {
                "year": year,
                "nominal_value": float(round(value, 2)),
                "real_value": float(round(real_value, 2)),
                "contributions": float(round(total_contributions, 2)),
                "returns": float(round(value - initial_value - total_contributions, 2)),
            }
        )

        # Grow for next year
        for _ in range(12):
            value = value * (1 + monthly_return) + monthly_contribution
            total_contributions += monthly_contribution

    final_value = projections[-1]["nominal_value"]
    real_final_value = projections[-1]["real_value"]
    total_returns = final_value - current_value - float(total_contributions)

    return ProjectionResult(
        current_value=round(current_value, 2),
        projections=projections,
        final_value=round(final_value, 2),
        total_contributions=float(round(total_contributions, 2)),
        total_returns=round(total_returns, 2),
        real_final_value=round(real_final_value, 2),
        currency=currency,
    )


@router.post("/dca", response_model=DCAResult)
async def simulate_dca(
    params: DCAParameters,
    current_user: User = Depends(get_current_user),
) -> DCAResult:
    """Simulate Dollar Cost Averaging vs Lump Sum on N stochastic paths.

    Correction (audit financier) : l'ancienne implémentation tirait UN SEUL
    chemin aléatoire (``random.gauss`` par période, sans seed) présenté comme
    « le » résultat, tandis que le Lump Sum était recalculé côté front en
    composé déterministe — la conclusion DCA vs Lump Sum changeait donc à
    chaque clic. On simule désormais ``N_PATHS = 500`` trajectoires de
    rendements vectorisées (numpy, ``np.random.default_rng`` sans seed fixe
    car on renvoie une DISTRIBUTION, pas un chiffre unique) et on évalue les
    DEUX stratégies sur les MÊMES chemins :

    - DCA : ``amount_per_investment`` investi au prix de chaque période ;
    - Lump Sum : la totalité investie au prix initial (période 0).

    La réponse expose p10/p50/p90 de la valeur finale par stratégie et la
    probabilité (fraction des chemins, en %) que le DCA batte le Lump Sum.
    Compatibilité : les champs historiques sont alimentés par la médiane
    (p50), et ``projections`` contient la trajectoire médiane par période
    avec sa bande p10-p90 (``current_value_p10`` / ``current_value_p90``)
    ainsi que la valeur Lump Sum médiane (``lump_sum_value``).

    Le drift et la volatilité annualisés sont convertis à la période réelle
    d'investissement (hebdo/mensuel/trimestriel) — l'ancien code appliquait
    un pas mensuel quelle que soit la fréquence.
    """
    import numpy as np

    currency = getattr(current_user, "preferred_currency", "EUR") or "EUR"

    # Determine investment frequency and per-period scaling
    if params.frequency == "weekly":
        num_investments = params.duration_months * 4
        periods_per_year = 48  # 4 semaines/mois x 12 mois (cohérent avec num_investments)
    elif params.frequency == "quarterly":
        num_investments = max(params.duration_months // 3, 1)
        periods_per_year = 4
    else:  # monthly
        num_investments = params.duration_months
        periods_per_year = 12
    amount_per_investment = params.total_amount / num_investments
    total_invested = amount_per_investment * num_investments

    n_paths = 500
    # No fixed seed — we return a distribution, not a single stochastic draw
    rng = np.random.default_rng()
    period_return = params.expected_return / 100 / periods_per_year
    period_vol = params.expected_volatility / 100 / (periods_per_year**0.5)

    # Same return paths for BOTH strategies — shape (n_paths, num_investments)
    returns = rng.normal(period_return, period_vol, size=(n_paths, num_investments))
    growth = np.clip(1.0 + returns, 0.01, None)  # prevent negative prices
    start_price = 100.0
    prices = start_price * np.cumprod(growth, axis=1)

    # DCA: buy amount_per_investment at each period's price
    units_per_period = amount_per_investment / prices
    cum_units = np.cumsum(units_per_period, axis=1)
    dca_values = cum_units * prices  # portfolio value at each period, per path
    dca_final = dca_values[:, -1]

    # Lump Sum: everything invested at the initial price, on the SAME paths
    ls_units = total_invested / start_price
    ls_values = ls_units * prices
    ls_final = ls_values[:, -1]

    dca_p10, dca_p50, dca_p90 = (float(v) for v in np.percentile(dca_final, [10, 50, 90]))
    ls_p10, ls_p50, ls_p90 = (float(v) for v in np.percentile(ls_final, [10, 50, 90]))
    prob_dca_beats_ls = float(np.mean(dca_final > ls_final) * 100)

    # Median trajectory per period (p50 across paths) + p10-p90 band
    price_p50 = np.percentile(prices, 50, axis=0)
    units_p50 = np.percentile(units_per_period, 50, axis=0)
    cum_units_p50 = np.percentile(cum_units, 50, axis=0)
    dca_val_p10 = np.percentile(dca_values, 10, axis=0)
    dca_val_p50 = np.percentile(dca_values, 50, axis=0)
    dca_val_p90 = np.percentile(dca_values, 90, axis=0)
    ls_val_p50 = np.percentile(ls_values, 50, axis=0)

    projections: List[Dict[str, Any]] = [
        {
            "period": i + 1,
            "price": round(float(price_p50[i]), 2),
            "amount_invested": round(amount_per_investment, 2),
            "units_bought": round(float(units_p50[i]), 4),
            "total_units": round(float(cum_units_p50[i]), 4),
            "total_invested": round(amount_per_investment * (i + 1), 2),
            "current_value": round(float(dca_val_p50[i]), 2),
            "current_value_p10": round(float(dca_val_p10[i]), 2),
            "current_value_p90": round(float(dca_val_p90[i]), 2),
            "lump_sum_value": round(float(ls_val_p50[i]), 2),
        }
        for i in range(num_investments)
    ]

    median_total_units = float(np.percentile(cum_units[:, -1], 50))
    average_cost = total_invested / median_total_units if median_total_units > 0 else 0.0
    return_percent = ((dca_p50 - total_invested) / total_invested * 100) if total_invested > 0 else 0.0

    return DCAResult(
        total_invested=round(total_invested, 2),
        final_value=round(dca_p50, 2),
        average_cost=round(average_cost, 2),
        total_units=round(median_total_units, 4),
        return_percent=round(return_percent, 2),
        projections=projections,
        currency=currency,
        dca_p10=round(dca_p10, 2),
        dca_p50=round(dca_p50, 2),
        dca_p90=round(dca_p90, 2),
        lumpsum_p10=round(ls_p10, 2),
        lumpsum_p50=round(ls_p50, 2),
        lumpsum_p90=round(ls_p90, 2),
        prob_dca_beats_ls=round(prob_dca_beats_ls, 1),
        n_paths=n_paths,
    )


@router.post("/what-if", response_model=WhatIfResult)
async def simulate_what_if(
    params: WhatIfParameters,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WhatIfResult:
    """Simulate what-if scenario on current portfolio using live prices.

    When `market_change` is set (e.g. -20 for a 20% crash) and `use_risk_weighting`
    is True, the shock is distributed proportionally to each asset's risk_weight:
    - High-risk assets (e.g. PEPE with 40% risk_weight) receive a larger shock
    - Low-risk assets (e.g. BTC with 10% risk_weight) receive a smaller shock
    The total portfolio-level impact equals the requested market_change.
    """
    currency = getattr(current_user, "preferred_currency", "EUR") or "EUR"
    live = await _get_portfolio_live_data(db, str(current_user.id), currency)
    all_assets = live["assets"]

    current_value = Decimal("0")
    projected_value = Decimal("0")
    asset_breakdown = []

    # Compute total risk weight for normalization
    total_risk_weight = sum(a.get("risk_weight", 0) for a in all_assets) or 1.0
    n_assets = len(all_assets) or 1

    for asset in all_assets:
        asset_val_f = asset.get("current_value", 0.0)
        asset_value = Decimal(str(asset_val_f))
        symbol = asset.get("symbol", "")
        risk_weight = asset.get("risk_weight", 0.0)
        current_value += asset_value

        # Determine per-asset change percent
        if symbol in params.asset_changes:
            # Explicit per-asset override
            change_percent = params.asset_changes[symbol]
        elif params.market_change is not None:
            # Uniform market shock, optionally weighted by risk
            if params.use_risk_weighting and total_risk_weight > 0 and risk_weight > 0:
                avg_risk_weight = total_risk_weight / n_assets
                multiplier = risk_weight / avg_risk_weight if avg_risk_weight > 0 else 1.0
                multiplier = min(max(multiplier, 0.2), 3.0)
                change_percent = params.market_change * multiplier
            else:
                change_percent = params.market_change
        else:
            change_percent = 0.0

        change_dec = Decimal(str(change_percent))
        new_value = asset_value * (1 + change_dec / 100)
        projected_value += new_value

        asset_breakdown.append(
            {
                "symbol": symbol,
                "name": asset.get("name", ""),
                "current_value": float(round(asset_value, 2)),
                "change_percent": round(change_percent, 2),
                "projected_value": float(round(new_value, 2)),
                "difference": float(round(new_value - asset_value, 2)),
                "risk_weight": risk_weight,
            }
        )

    # Apply withdrawal/contribution
    projected_value = (
        projected_value - Decimal(str(params.withdrawal_amount)) + Decimal(str(params.contribution_amount))
    )

    difference = projected_value - current_value
    difference_percent = float(difference / current_value * 100) if current_value > 0 else 0.0

    return WhatIfResult(
        current_value=float(round(current_value, 2)),
        projected_value=float(round(projected_value, 2)),
        difference=float(round(difference, 2)),
        difference_percent=round(difference_percent, 2),
        asset_breakdown=asset_breakdown,
        currency=currency,
    )


@router.get("", response_model=List[SimulationResponse])
async def list_simulations(
    simulation_type: Optional[SimulationType] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[SimulationResponse]:
    """List all saved simulations."""
    query = select(Simulation).where(Simulation.user_id == current_user.id)

    if simulation_type:
        query = query.where(Simulation.simulation_type == simulation_type)

    result = await db.execute(query.order_by(Simulation.created_at.desc()).offset(skip).limit(limit))
    simulations = result.scalars().all()

    return [
        SimulationResponse(
            id=s.id,
            name=s.name,
            description=s.description,
            simulation_type=s.simulation_type.value,
            parameters=s.parameters,
            results=s.results,
            created_at=s.created_at,
        )
        for s in simulations
    ]


@router.post("", response_model=SimulationResponse, status_code=status.HTTP_201_CREATED)
async def save_simulation(
    sim_in: SimulationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SimulationResponse:
    """Save a simulation for later reference."""
    simulation = Simulation(
        user_id=current_user.id,
        name=sim_in.name,
        description=sim_in.description,
        simulation_type=sim_in.simulation_type,
        parameters=sim_in.parameters,
    )

    db.add(simulation)
    await db.commit()
    await db.refresh(simulation)

    return SimulationResponse(
        id=simulation.id,
        name=simulation.name,
        description=simulation.description,
        simulation_type=simulation.simulation_type.value,
        parameters=simulation.parameters,
        results=simulation.results,
        created_at=simulation.created_at,
    )


@router.get("/{simulation_id}", response_model=SimulationResponse)
async def get_simulation(
    simulation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SimulationResponse:
    """Get a specific simulation."""
    result = await db.execute(
        select(Simulation).where(
            Simulation.id == simulation_id,
            Simulation.user_id == current_user.id,
        )
    )
    simulation = result.scalar_one_or_none()

    if not simulation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Simulation non trouvée",
        )

    return SimulationResponse(
        id=simulation.id,
        name=simulation.name,
        description=simulation.description,
        simulation_type=simulation.simulation_type.value,
        parameters=simulation.parameters,
        results=simulation.results,
        created_at=simulation.created_at,
    )


@router.delete("/{simulation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_simulation(
    simulation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a simulation."""
    result = await db.execute(
        select(Simulation).where(
            Simulation.id == simulation_id,
            Simulation.user_id == current_user.id,
        )
    )
    simulation = result.scalar_one_or_none()

    if not simulation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Simulation non trouvée",
        )

    await db.delete(simulation)
    await db.commit()
