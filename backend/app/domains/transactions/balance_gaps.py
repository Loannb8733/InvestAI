from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.portfolio.models import Asset, AssetType, Portfolio
from app.domains.transactions.ledger import INFLOWS, OUTFLOWS
from app.domains.transactions.models import Transaction, TransactionType
from app.domains.transactions.schemas import (
    BalanceGap,
    BalanceGapsResponse,
    CreditDetails,
    CreditedGap,
    CreditResult,
    SkippedGap,
)

RECENT_REWARD = timedelta(days=30)


async def find_gaps(session: AsyncSession, user_id: UUID, threshold_eur: float) -> BalanceGapsResponse:
    """Actifs dont la quantité enregistrée dépasse la somme signée du journal, au-delà de ``threshold_eur``.

    Un actif dont du principal est en staking est écarté : ce principal vit hors du
    journal. ``source_hint`` oriente : récompense de moins de 30 jours
    (``earn_pending``), airdrop déjà vu (``airdrop``), sinon ``unknown``.
    """
    kind, quantity = Transaction.transaction_type, Transaction.quantity
    journal = func.coalesce(func.sum(case((kind.in_(INFLOWS), quantity), (kind.in_(OUTFLOWS), -quantity), else_=0)), 0)
    staked = func.coalesce(
        func.sum(
            case((kind == TransactionType.STAKING, quantity), (kind == TransactionType.UNSTAKING, -quantity), else_=0)
        ),
        0,
    )
    last_reward = func.max(case((kind == TransactionType.STAKING_REWARD, Transaction.executed_at)))
    last_airdrop = func.max(case((kind == TransactionType.AIRDROP, Transaction.executed_at)))
    query = (
        select(
            Asset.id,
            Asset.symbol,
            Asset.exchange,
            Asset.quantity,
            Asset.current_price,
            journal,
            staked,
            last_reward,
            last_airdrop,
        )
        .join(Portfolio, Asset.portfolio_id == Portfolio.id)
        .outerjoin(Transaction, Transaction.asset_id == Asset.id)
        .where(Portfolio.user_id == user_id, Asset.asset_type != AssetType.CROWDFUNDING)
        .group_by(Asset.id)
    )
    now = datetime.now(UTC)
    gaps = []
    for asset_id, symbol, exchange, stored, price, computed, staking, reward_at, airdrop_at in (
        await session.execute(query)
    ).all():
        missing = Decimal(stored or 0) - Decimal(computed)
        value = float(missing * Decimal(price or 0))
        if missing <= 0 or Decimal(staking) > 0 or value < threshold_eur:
            continue
        hint: Literal["earn_pending", "airdrop", "unknown"] = (
            "earn_pending"
            if reward_at and now - reward_at < RECENT_REWARD
            else ("airdrop" if airdrop_at else "unknown")
        )
        gaps.append(
            BalanceGap(
                asset_id=str(asset_id),
                symbol=symbol,
                exchange=exchange or "",
                stored=float(stored),
                computed=float(computed),
                missing_qty=float(missing),
                missing_eur=round(value, 2),
                source_hint=hint,
            )
        )
    gaps.sort(key=lambda gap: gap.missing_eur, reverse=True)
    return BalanceGapsResponse(count=len(gaps), threshold_eur=threshold_eur, gaps=gaps)


async def credit_gaps(session: AsyncSession, user_id: UUID, threshold_eur: float) -> CreditResult:
    """Comble chaque écart par un AIRDROP au cours du jour ; un même écart n'est crédité qu'une fois par jour."""
    now = datetime.now(UTC)
    tag = now.strftime("%Y_%m_%d")
    details = CreditDetails()
    for gap in (await find_gaps(session, user_id, threshold_eur)).gaps:
        external_id = f"auto_credit_gap_{gap.asset_id[:8]}_{tag}"
        if (await session.execute(select(Transaction.id).where(Transaction.external_id == external_id))).first():
            details.skipped.append(
                SkippedGap(symbol=gap.symbol, exchange=gap.exchange, reason="already_credited_today")
            )
            continue
        asset = await session.get_one(Asset, UUID(gap.asset_id))
        if not asset.current_price or asset.current_price <= 0:
            details.skipped.append(SkippedGap(symbol=gap.symbol, exchange=gap.exchange, reason="no_market_price"))
            continue
        airdrop = Transaction(
            asset_id=asset.id,
            transaction_type=TransactionType.AIRDROP,
            quantity=Decimal(str(gap.missing_qty)),
            price=asset.current_price,
            fee=Decimal("0"),
            currency="EUR",
            executed_at=now,
            external_id=external_id,
            notes=(
                f"Auto-credit from balance-gaps on {tag} (missing {gap.missing_qty:.6f} {gap.symbol} "
                f"~= {gap.missing_eur:.2f} EUR, hint={gap.source_hint})."
            ),
        )
        airdrop.compute_hash()
        session.add(airdrop)
        details.credited.append(
            CreditedGap(
                symbol=gap.symbol,
                exchange=gap.exchange,
                missing_qty=gap.missing_qty,
                missing_eur=gap.missing_eur,
                source_hint=gap.source_hint,
            )
        )
    await session.flush()
    return CreditResult(credited=len(details.credited), skipped=len(details.skipped), details=details)
