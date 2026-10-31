from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Date, String, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.db import session
from app.domains.dashboard.models import PortfolioSnapshot
from app.domains.portfolio.models import Asset, AssetType
from app.domains.transactions.models import Transaction, TransactionType

MATERIALITY_VALUE = Decimal("1.00")
MATERIALITY_DIFF_VALUE = Decimal("0.01")
HOLDINGS_TOLERANCE = Decimal("0.00000001")
HOLDING_INFLOWS = (
    TransactionType.BUY,
    TransactionType.TRANSFER_IN,
    TransactionType.CONVERSION_IN,
    TransactionType.AIRDROP,
    TransactionType.STAKING_REWARD,
)
HOLDING_OUTFLOWS = (TransactionType.SELL, TransactionType.TRANSFER_OUT, TransactionType.CONVERSION_OUT)
FX_SAMPLE = 20
SNAPSHOT_SAMPLE = 10
DETAILS_SAMPLE = 50


def ledger_quantity() -> ColumnElement[Decimal]:
    """Quantité qu'expliquent les transactions d'un actif : entrées moins sorties, 0 sans transaction."""
    kind, quantity = Transaction.transaction_type, Transaction.quantity
    signed = case((kind.in_(HOLDING_INFLOWS), quantity), (kind.in_(HOLDING_OUTFLOWS), -quantity), else_=0)
    return func.coalesce(func.sum(signed), 0)


def classify_holdings_gap(stored: Decimal, computed: Decimal, pru: Decimal) -> tuple[bool, str]:
    """``(immatériel, raison)`` d'un écart entre quantité stockée et quantité des transactions.

    Un écart est immatériel quand la position est soldée (valeur sous 1) ou quand il vaut moins d'un centime :
    il est alors signalé sans faire échouer le contrôle.
    """
    position_value = abs(stored) * pru
    diff_value = abs(stored - computed) * pru
    if position_value < MATERIALITY_VALUE:
        return True, f"position soldée, valeur {position_value:.4f} — sans impact"
    if diff_value < MATERIALITY_DIFF_VALUE:
        return True, f"écart de {diff_value:.6f} — bruit d'arrondi"
    return False, ""


async def _holdings_gaps(conn: AsyncConnection) -> list[dict[str, Any]]:
    query = (
        select(
            cast(Asset.id, String).label("aid"),
            Asset.symbol,
            Asset.exchange,
            Asset.quantity.label("stored"),
            Asset.avg_buy_price.label("pru"),
            ledger_quantity().label("computed"),
        )
        .outerjoin(Transaction, Transaction.asset_id == Asset.id)
        .where(Asset.asset_type != AssetType.CROWDFUNDING)
        .group_by(Asset.id)
    )
    gaps = []
    for row in (await conn.execute(query)).mappings().all():
        stored = Decimal(str(row["stored"] or 0))
        computed = Decimal(str(row["computed"] or 0))
        if abs(stored - computed) <= HOLDINGS_TOLERANCE:
            continue
        immaterial, reason = classify_holdings_gap(stored, computed, Decimal(str(row["pru"] or 0)))
        gaps.append(
            {
                "asset_id": row["aid"],
                "symbol": row["symbol"],
                "exchange": row["exchange"],
                "stored": float(stored),
                "computed": float(computed),
                "diff": float(stored - computed),
                "material": not immaterial,
                "reason": reason,
            }
        )
    return gaps


async def _missing_fx_rates(conn: AsyncConnection) -> list[dict[str, Any]]:
    rate = Transaction.conversion_rate
    query = (
        select(cast(Transaction.id, String).label("tx_id"), Asset.symbol, Transaction.currency, rate)
        .join(Asset, Asset.id == Transaction.asset_id)
        .where(
            Transaction.transaction_type.in_((TransactionType.BUY, TransactionType.SELL)),
            func.coalesce(func.upper(Transaction.currency), "EUR") != "EUR",
            or_(rate.is_(None), rate <= 0),
        )
        .limit(FX_SAMPLE)
    )
    return [dict(row) for row in (await conn.execute(query)).mappings().all()]


async def _duplicate_snapshots(conn: AsyncConnection) -> list[dict[str, Any]]:
    snapshots = PortfolioSnapshot.__table__.c
    day = cast(func.timezone("UTC", snapshots.snapshot_date), Date)
    query = (
        select(
            cast(snapshots.user_id, String).label("user_id"),
            day.label("day"),
            cast(snapshots.portfolio_id, String).label("portfolio_id"),
            func.count().label("n"),
        )
        .group_by(snapshots.user_id, day, snapshots.portfolio_id)
        .having(func.count() > 1)
        .limit(SNAPSHOT_SAMPLE)
    )
    return [dict(row) for row in (await conn.execute(query)).mappings().all()]


async def check_invariants() -> dict[str, Any]:
    """Écarts de quantité, taux de change manquants et snapshots en double sur toute la base.

    Sont bloquants les écarts de quantité matériels et les doublons de snapshot ; un taux manquant reste un
    avertissement.
    """
    async with session.engine.connect() as conn:
        invariants = {
            "holdings": await _holdings_gaps(conn),
            "fx": await _missing_fx_rates(conn),
            "snapshots": await _duplicate_snapshots(conn),
        }
    material = sum(1 for gap in invariants["holdings"] if gap["material"]) + len(invariants["snapshots"])
    return {
        "total_violations": sum(len(found) for found in invariants.values()),
        "material_violations": material,
        "counts": {name: len(found) for name, found in invariants.items()},
        "details": {name: found[:DETAILS_SAMPLE] for name, found in invariants.items()},
    }
