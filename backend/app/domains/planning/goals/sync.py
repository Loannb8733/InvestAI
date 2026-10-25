import logging
from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.market_data.prices.service import price_feed
from app.domains.planning.goals.models import Goal, GoalStatus, GoalType
from app.domains.portfolio.classification import is_cash_like
from app.domains.portfolio.models import Asset, Portfolio

logger = logging.getLogger(__name__)

PriceCache = dict[tuple[str, str], Decimal]


async def _price(asset: Asset, price_cache: PriceCache) -> Decimal:
    pkey = (asset.symbol, asset.asset_type.value)
    if pkey not in price_cache:
        quote = await price_feed.quote(asset.symbol, asset.asset_type)
        price_cache[pkey] = quote.price if quote is not None else Decimal(str(asset.avg_buy_price or 0))
    return price_cache[pkey]


def _add_cash(total: Decimal, portfolios: Sequence[Portfolio]) -> Decimal:
    for portfolio in portfolios:
        for _ccy, amount in (portfolio.cash_balances or {}).items():
            total += Decimal(str(amount))
    return total


async def _initial_value(db: AsyncSession, user_id: UUID, is_savings: bool) -> Decimal:
    portfolios = (await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))).scalars().all()
    portfolio_ids = [p.id for p in portfolios]
    assets = (await db.execute(select(Asset).where(Asset.portfolio_id.in_(portfolio_ids)))).scalars().all()

    total_value = Decimal("0")
    price_cache: PriceCache = {}
    for asset in assets:
        if float(asset.quantity) > 0:
            if is_savings and not is_cash_like(asset.symbol):
                continue
            total_value += asset.quantity * Decimal(str(await _price(asset, price_cache)))
    if is_savings:
        total_value = _add_cash(total_value, portfolios)
    return total_value


async def initial_sync(db: AsyncSession, goal: Goal, user_id: UUID) -> None:
    """Synchronisation à la création, non bloquante : ``current_amount`` n'est écrit que si la valeur est positive,
    les actifs non liquides d'un objectif SAVINGS ne sont pas valorisés, et tout échec est journalisé puis ignoré."""
    try:
        total_value = await _initial_value(db, user_id, goal.goal_type == GoalType.SAVINGS)
        if total_value > 0:
            goal.current_amount = total_value
            if goal.current_amount >= goal.target_amount and goal.status == GoalStatus.ACTIVE:
                goal.status = GoalStatus.REACHED
            await db.commit()
            await db.refresh(goal)
    except Exception as e:  # noqa: BLE001
        logger.warning("Initial goal sync failed (non-blocking): %s", e)


async def _portfolio_values(db: AsyncSession, user_id: UUID) -> tuple[Decimal, Decimal]:
    portfolios = (await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))).scalars().all()
    portfolio_ids = [p.id for p in portfolios]
    assets = (
        (await db.execute(select(Asset).where(Asset.portfolio_id.in_(portfolio_ids)))).scalars().all()
        if portfolio_ids
        else []
    )

    price_cache: PriceCache = {}
    total_value = Decimal("0")
    liquid_value = Decimal("0")
    for asset in assets:
        if float(asset.quantity) <= 0:
            continue
        value = asset.quantity * Decimal(str(await _price(asset, price_cache)))
        total_value += value
        if is_cash_like(asset.symbol):
            liquid_value += value
    return total_value, liquid_value + _add_cash(Decimal("0"), portfolios)


async def sync_goals_for_user(db: AsyncSession, user_id: UUID, only_goal_id: UUID | None = None) -> int:
    """Recale ``current_amount`` sur le portefeuille réel (valeur totale, ou liquidités et soldes cash pour SAVINGS)
    et passe en REACHED les objectifs actifs atteints ; sans ``only_goal_id``, seuls les objectifs actifs sont
    synchronisés. Renvoie le nombre d'objectifs synchronisés."""
    conditions = [Goal.user_id == user_id, Goal.status == GoalStatus.ACTIVE]
    if only_goal_id is not None:
        conditions = [Goal.user_id == user_id, Goal.id == only_goal_id]
    goals = (await db.execute(select(Goal).where(*conditions))).scalars().all()
    if not goals:
        return 0

    total_value, savings_value = await _portfolio_values(db, user_id)

    synced = 0
    for goal in goals:
        is_savings = goal.goal_type == GoalType.SAVINGS
        goal.current_amount = savings_value if is_savings else total_value
        if goal.current_amount >= goal.target_amount and goal.status == GoalStatus.ACTIVE:
            goal.status = GoalStatus.REACHED
        synced += 1

    await db.commit()
    return synced
