from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.domains.identity.dependencies import CurrentUser
from app.domains.identity.models import User
from app.domains.planning.simulations.dca import simulate_dca_paths
from app.domains.planning.simulations.fire import fire_result, resolve_fire_inputs
from app.domains.planning.simulations.models import Simulation, SimulationType
from app.domains.planning.simulations.projection import build_projection
from app.domains.planning.simulations.schemas import (
    DCAParameters,
    DCAResult,
    FIREProbabilisticParameters,
    FIREProbabilisticResult,
    ProjectionParameters,
    ProjectionResult,
    SimulationCreate,
    SimulationResponse,
)
from app.domains.portfolio.models import Portfolio
from app.services.metrics_service import metrics_service

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]

SIMULATION_NOT_FOUND = "Simulation non trouvée"


def _currency(user: User) -> str:
    return user.preferred_currency or "EUR"


async def _portfolio_live_data(db: AsyncSession, user_id: str, currency: str = "EUR") -> dict[str, Any]:
    dashboard = await metrics_service.get_user_dashboard_metrics(db, user_id, currency=currency, days=0)
    result = await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
    portfolios = result.scalars().all()

    all_assets: list[Any] = []
    for portfolio in portfolios:
        pm = await metrics_service.get_portfolio_metrics(db, str(portfolio.id), currency=currency)
        all_assets.extend(pm.get("assets", []))

    return {
        "total_value": dashboard.get("total_value", 0.0),
        "assets": all_assets,
    }


def _response(simulation: Simulation) -> SimulationResponse:
    return SimulationResponse(
        id=simulation.id,
        name=simulation.name,
        description=simulation.description,
        simulation_type=simulation.simulation_type.value,
        parameters=simulation.parameters,
        results=simulation.results,
        created_at=simulation.created_at,
    )


async def _owned_or_404(db: AsyncSession, simulation_id: UUID, user: User) -> Simulation:
    result = await db.execute(
        select(Simulation).where(
            Simulation.id == simulation_id,
            Simulation.user_id == user.id,
        )
    )
    simulation = result.scalar_one_or_none()
    if not simulation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SIMULATION_NOT_FOUND)
    return simulation


@router.post("/fire-probabilistic", response_model=FIREProbabilisticResult)
async def calculate_fire_probabilistic(
    params: FIREProbabilisticParameters, user: CurrentUser, session: Session
) -> FIREProbabilisticResult:
    """Probabilité cumulée d'être FIRE chaque année (Monte-Carlo) et survie à 30 ans de retraits ; les paramètres
    omis viennent du portefeuille live et du profil investisseur, leur source est exposée dans
    ``assumptions.defaults_from``."""
    currency = _currency(user)
    defaults_from: dict[str, str] = {}
    current_value = params.current_value
    if current_value is None:
        live = await _portfolio_live_data(session, str(user.id), currency)
        current_value = max(float(live["total_value"]), 0.0)
        defaults_from["current_value"] = "portefeuille live"

    inputs = resolve_fire_inputs(params, current_value, defaults_from, user.risk_profile, user.monthly_dca_eur)
    return fire_result(params, inputs, currency)


@router.post("/projection", response_model=ProjectionResult)
async def project_portfolio(params: ProjectionParameters, user: CurrentUser, session: Session) -> ProjectionResult:
    """Projection de la valeur live du portefeuille ; 400 si elle est nulle."""
    currency = _currency(user)
    live = await _portfolio_live_data(session, str(user.id), currency)
    current_value = live["total_value"]

    if current_value <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La valeur du portefeuille est nulle. Ajoutez des actifs d'abord.",
        )
    return build_projection(current_value, params, currency)


@router.post("/dca", response_model=DCAResult)
async def simulate_dca(params: DCAParameters, user: CurrentUser) -> DCAResult:
    return simulate_dca_paths(params, _currency(user))


@router.get("", response_model=list[SimulationResponse])
async def list_simulations(
    user: CurrentUser,
    session: Session,
    simulation_type: SimulationType | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[SimulationResponse]:
    query = select(Simulation).where(Simulation.user_id == user.id)
    if simulation_type:
        query = query.where(Simulation.simulation_type == simulation_type)

    result = await session.execute(query.order_by(Simulation.created_at.desc()).offset(skip).limit(limit))
    return [_response(s) for s in result.scalars().all()]


@router.post("", response_model=SimulationResponse, status_code=status.HTTP_201_CREATED)
async def save_simulation(sim_in: SimulationCreate, user: CurrentUser, session: Session) -> SimulationResponse:
    simulation = Simulation(
        user_id=user.id,
        name=sim_in.name,
        description=sim_in.description,
        simulation_type=sim_in.simulation_type,
        parameters=sim_in.parameters,
    )
    session.add(simulation)
    await session.commit()
    await session.refresh(simulation)
    return _response(simulation)


@router.get("/{simulation_id}", response_model=SimulationResponse)
async def get_simulation(simulation_id: UUID, user: CurrentUser, session: Session) -> SimulationResponse:
    return _response(await _owned_or_404(session, simulation_id, user))


@router.delete("/{simulation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_simulation(simulation_id: UUID, user: CurrentUser, session: Session) -> None:
    simulation = await _owned_or_404(session, simulation_id, user)
    await session.delete(simulation)
    await session.commit()
