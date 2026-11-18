from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.core.rate_limit import limiter
from app.domains.identity.dependencies import CurrentUser
from app.domains.identity.models import User
from app.domains.strategies.backtest import run_backtest
from app.domains.strategies.disclaimer import SIMULATION_DISCLAIMER
from app.domains.strategies.models import ActionStatus, Strategy, StrategyAction, StrategySource, StrategyStatus
from app.domains.strategies.repository import (
    find_owned_action,
    find_owned_strategy,
    list_actions,
    list_user_strategies,
)
from app.domains.strategies.schemas import (
    SimulationRequest,
    SimulationResponse,
    StrategyActionUpdate,
    StrategyCreate,
    StrategyResponse,
    StrategyUpdate,
    TemplateStrategyCreate,
)
from app.domains.strategies.service import strategy_service
from app.domains.strategies.templates import (
    actions_from_schedule,
    build_schedule,
    describe_rule,
    parse_template_params,
    schedule_totals,
)

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]

STRATEGY_NOT_FOUND = "Stratégie non trouvée"


def _action_payload(a: StrategyAction) -> dict[str, Any]:
    return {
        "id": a.id,
        "strategy_id": a.strategy_id,
        "action": a.action,
        "symbol": a.symbol,
        "amount": float(a.amount) if a.amount else None,
        "currency": a.currency,
        "reason": a.reason,
        "status": a.status.value if a.status else "PENDING",
        "scheduled_at": a.scheduled_at,
        "executed_at": a.executed_at,
        "created_at": a.created_at,
    }


def _rule_summary(params: dict[str, Any] | None) -> str | None:
    template = parse_template_params(params)
    return describe_rule(template) if template else None


async def _enrich(db: AsyncSession, strategy: Strategy) -> dict[str, Any]:
    actions = await list_actions(db, strategy.id)
    return {
        "id": strategy.id,
        "user_id": strategy.user_id,
        "name": strategy.name,
        "description": strategy.description,
        "source": strategy.source.value if strategy.source else "USER",
        "status": strategy.status.value if strategy.status else "ACTIVE",
        "params": strategy.params or {},
        "rule_summary": _rule_summary(strategy.params),
        "ai_reasoning": strategy.ai_reasoning,
        "market_regime": strategy.market_regime,
        "confidence": float(strategy.confidence) if strategy.confidence else None,
        "actions": [_action_payload(a) for a in actions],
        "created_at": strategy.created_at,
        "updated_at": strategy.updated_at,
    }


async def _owned_or_404(db: AsyncSession, strategy_id: UUID, user: User) -> Strategy:
    strategy = await find_owned_strategy(db, strategy_id, user.id)
    if not strategy:
        raise HTTPException(status_code=404, detail=STRATEGY_NOT_FOUND)
    return strategy


async def _set_status(db: AsyncSession, strategy: Strategy, new_status: StrategyStatus) -> dict[str, Any]:
    strategy.status = new_status
    await db.commit()
    await db.refresh(strategy)
    return await _enrich(db, strategy)


@router.get("", response_model=list[StrategyResponse])
@limiter.limit("30/minute")
async def list_strategies(request: Request, user: CurrentUser, session: Session) -> list[dict[str, Any]]:
    strategies = await list_user_strategies(session, user.id)
    return [await _enrich(session, s) for s in strategies]


@router.post("", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_strategy(
    request: Request, data: StrategyCreate, user: CurrentUser, session: Session
) -> dict[str, Any]:
    """Stratégie utilisateur, créée ACTIVE avec ses actions en PENDING."""
    strategy = Strategy(
        user_id=user.id,
        name=data.name,
        description=data.description,
        source=StrategySource.USER,
        status=StrategyStatus.ACTIVE,
        params=data.params,
    )
    session.add(strategy)
    await session.flush()

    for action_data in data.actions:
        action = StrategyAction(
            strategy_id=strategy.id,
            action=action_data.action,
            symbol=action_data.symbol,
            amount=action_data.amount,
            currency=action_data.currency,
            reason=action_data.reason,
            status=ActionStatus.PENDING,
        )
        session.add(action)

    await session.commit()
    await session.refresh(strategy)
    return await _enrich(session, strategy)


@router.patch("/{strategy_id}", response_model=StrategyResponse)
@limiter.limit("20/minute")
async def update_strategy(
    request: Request, strategy_id: UUID, data: StrategyUpdate, user: CurrentUser, session: Session
) -> dict[str, Any]:
    strategy = await _owned_or_404(session, strategy_id, user)

    if data.name is not None:
        strategy.name = data.name
    if data.description is not None:
        strategy.description = data.description
    if data.status is not None:
        strategy.status = StrategyStatus(data.status)
    if data.params is not None:
        strategy.params = data.params

    await session.commit()
    await session.refresh(strategy)
    return await _enrich(session, strategy)


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def delete_strategy(request: Request, strategy_id: UUID, user: CurrentUser, session: Session) -> None:
    """Supprime la stratégie et ses actions ; une stratégie héritée de l'ancienne génération automatique est
    refusée (403) : on la rejette pour l'archiver."""
    strategy = await _owned_or_404(session, strategy_id, user)

    if strategy.source == StrategySource.AI:
        raise HTTPException(
            status_code=403,
            detail=(
                "Les stratégies générées automatiquement par l'ancienne version ne peuvent pas être "
                "supprimées : rejetez-les pour les archiver"
            ),
        )

    await session.delete(strategy)
    await session.commit()


@router.post("/simulate", response_model=SimulationResponse)
@limiter.limit("20/minute")
async def simulate_strategy(
    request: Request, data: SimulationRequest, user: CurrentUser, session: Session
) -> SimulationResponse:
    """Aperçu d'un modèle paramétré, sans rien enregistrer : échéancier et montants qui découlent des seuls
    paramètres saisis, et, si ``backtest_start`` est fourni, la règle rejouée sur l'historique de prix."""
    schedule = build_schedule(data.params)
    total_buy, total_sell, deferred = schedule_totals(schedule)
    backtest = await run_backtest(session, data.params, data.backtest_start) if data.backtest_start else None
    return SimulationResponse(
        template=data.params.template,
        rule_summary=describe_rule(data.params),
        schedule=schedule,
        total_buy_eur=total_buy,
        total_sell_eur=total_sell,
        has_amounts_at_execution=deferred,
        backtest=backtest,
        disclaimer=SIMULATION_DISCLAIMER,
    )


@router.post("/from-template", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_strategy_from_template(
    request: Request, data: TemplateStrategyCreate, user: CurrentUser, session: Session
) -> dict[str, Any]:
    """Enregistre la règle paramétrée (source USER, ACTIVE) avec une action PENDING par achat ou vente de son
    échéancier, datée de son échéance."""
    strategy = Strategy(
        user_id=user.id,
        name=data.name,
        description=data.description,
        source=StrategySource.USER,
        status=StrategyStatus.ACTIVE,
        params=data.params.model_dump(mode="json"),
    )
    session.add(strategy)
    await session.flush()
    for planned in actions_from_schedule(build_schedule(data.params)):
        session.add(StrategyAction(strategy_id=strategy.id, status=ActionStatus.PENDING, **planned))
    await session.commit()
    await session.refresh(strategy)
    return await _enrich(session, strategy)


@router.patch("/{strategy_id}/accept", response_model=StrategyResponse)
@limiter.limit("10/minute")
async def accept_strategy(request: Request, strategy_id: UUID, user: CurrentUser, session: Session) -> dict[str, Any]:
    strategy = await _owned_or_404(session, strategy_id, user)
    return await _set_status(session, strategy, StrategyStatus.ACTIVE)


@router.patch("/{strategy_id}/reject", response_model=StrategyResponse)
@limiter.limit("10/minute")
async def reject_strategy(request: Request, strategy_id: UUID, user: CurrentUser, session: Session) -> dict[str, Any]:
    strategy = await _owned_or_404(session, strategy_id, user)
    return await _set_status(session, strategy, StrategyStatus.REJECTED)


@router.get("/{strategy_id}/performance", response_model=dict)
@limiter.limit("30/minute")
async def get_strategy_performance(
    request: Request, strategy_id: UUID, user: CurrentUser, session: Session
) -> dict[str, Any]:
    """Rendement des actions exécutées : P&L latent pour les achats, impact (gain ou perte évités) pour les ventes,
    taux de suivi et comparaison au « ne rien faire »."""
    strategy = await _owned_or_404(session, strategy_id, user)
    actions = await list_actions(session, strategy.id)

    performance = await strategy_service.get_strategy_performance(session, actions)
    return {
        "strategy_id": str(strategy.id),
        "strategy_name": strategy.name,
        "strategy_status": strategy.status.value if strategy.status else "ACTIVE",
        **performance,
    }


@router.patch("/actions/{action_id}", response_model=dict)
@limiter.limit("20/minute")
async def update_action_status(
    request: Request, action_id: UUID, data: StrategyActionUpdate, user: CurrentUser, session: Session
) -> dict[str, Any]:
    """Marque une action EXECUTED (horodatée) ou SKIPPED, ou corrige son montant."""
    action = await find_owned_action(session, action_id, user.id)
    if not action:
        raise HTTPException(status_code=404, detail="Action non trouvée")

    if data.amount is not None:
        action.amount = data.amount  # type: ignore[assignment]

    if data.status is not None:
        action.status = ActionStatus(data.status)
        if data.status == "EXECUTED":
            action.executed_at = datetime.now(UTC)

    await session.commit()
    return {
        "id": str(action.id),
        "status": action.status.value,
        "amount": float(action.amount) if action.amount else None,
    }
