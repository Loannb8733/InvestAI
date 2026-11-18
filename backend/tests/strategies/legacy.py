"""Stratégies héritées de l'ancienne génération automatique, telles qu'elles restent en base."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.strategies.disclaimer import AI_DISCLAIMER
from app.domains.strategies.models import ActionStatus, Strategy, StrategyAction, StrategySource, StrategyStatus

EXECUTED_AT = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)


async def seed_legacy_ai_strategies(db: AsyncSession, user: User) -> tuple[Strategy, Strategy]:
    """Une proposition jamais traitée (PROPOSED) et une proposition acceptée dont un « ACHAT FORT » a été exécuté."""
    proposed = Strategy(
        user_id=user.id,
        name="VCA Contrarian — 2 actifs",
        description="Accumulation progressive",
        source=StrategySource.AI,
        status=StrategyStatus.PROPOSED,
        params={"type": "vca", "available_liquidity": 3000.0, "risk_level": 3, "performance_potential": 4},
        ai_reasoning=f"Le VCA surperforme le DCA en marché volatil.\n\n{AI_DISCLAIMER}",
        market_regime="bearish",
        confidence=Decimal("0.6"),
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    accepted = Strategy(
        user_id=user.id,
        name="Conviction buy — BTC",
        source=StrategySource.AI,
        status=StrategyStatus.ACTIVE,
        params={"type": "conviction_buy", "total_proposed_amount": 120.0},
        ai_reasoning="Peur extrême.",
        market_regime="bottom",
        confidence=Decimal("0.2"),
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    db.add_all([proposed, accepted])
    await db.flush()
    db.add_all(
        [
            StrategyAction(strategy_id=proposed.id, action="VCA", symbol="SOL", amount=Decimal("50")),
            StrategyAction(strategy_id=proposed.id, action="PRENDRE PROFITS", symbol="ETH", amount=Decimal("200")),
            StrategyAction(
                strategy_id=accepted.id,
                action="ACHAT FORT",
                symbol="BTC",
                amount=Decimal("120"),
                status=ActionStatus.EXECUTED,
                executed_at=EXECUTED_AT,
            ),
            StrategyAction(
                strategy_id=accepted.id,
                action="ALLÉGER",
                symbol="ETH",
                amount=Decimal("80"),
                status=ActionStatus.EXECUTED,
                executed_at=EXECUTED_AT,
            ),
        ]
    )
    await db.commit()
    return proposed, accepted
