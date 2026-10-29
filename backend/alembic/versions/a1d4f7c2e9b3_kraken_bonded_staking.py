"""kraken bonded staking

Revision ID: a1d4f7c2e9b3
Revises: 3c9e1f7a2b8d
Create Date: 2026-10-28 23:00:00.000000

Kraken nomme un staking lié avec sa durée de blocage (SOL03.S). Le connecteur ne retirait que le suffixe .S :
la SOL stakée devenait un actif SOL03, sans cours donc compté à zéro, et son passage en staking s'écrivait en
sortie de SOL puis entrée de SOL03. Chaque actif ainsi né rejoint l'actif Kraken de son sous-jacent dans le même
portefeuille, et la paire sortie/entrée, qui n'était pas un mouvement, disparaît. La logique est figée ici.
"""

import hashlib
from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal, localcontext

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from alembic import op

revision: str = "a1d4f7c2e9b3"
down_revision: str | None = "3c9e1f7a2b8d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BONDED = "^([A-Z]{2,})[0-9]{2}$"
SAME_MOVE = Decimal("0.001")
MOVE_WINDOW = timedelta(days=1)


def _canonical(value: object) -> str:
    with localcontext() as context:
        context.prec = 50
        return format(Decimal(str(value)).quantize(Decimal(1).scaleb(-12)), "f")


def transaction_hash(asset_id: object, kind: str, quantity: object, price: object, day: str) -> str:
    """Empreinte anti-doublon telle que la calcule le modèle au 2026-10-28."""
    parts = [str(asset_id), kind.lower(), _canonical(quantity), _canonical(price), day]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:40]


def _staking_move(conn: Connection, staked: object, base: object) -> list[str]:
    opening = conn.execute(
        sa.text(
            "SELECT id, quantity, executed_at FROM transactions WHERE asset_id = :s"
            " AND transaction_type::text = 'TRANSFER_IN' AND notes LIKE 'Import initial%'"
        ),
        {"s": staked},
    ).first()
    if opening is None or opening.executed_at is None:
        return []
    leaving = conn.execute(
        sa.text(
            "SELECT id, quantity FROM transactions WHERE asset_id = :b AND transaction_type::text = 'TRANSFER_OUT'"
            " AND notes LIKE 'Ajustement balance%' AND executed_at BETWEEN :start AND :end"
            " ORDER BY ABS(quantity - :q) LIMIT 1"
        ),
        {
            "b": base,
            "start": opening.executed_at - MOVE_WINDOW,
            "end": opening.executed_at + MOVE_WINDOW,
            "q": opening.quantity,
        },
    ).first()
    quantity = Decimal(opening.quantity)
    if leaving is None or abs(Decimal(leaving.quantity) - quantity) > quantity * SAME_MOVE:
        return []
    return [str(opening.id), str(leaving.id)]


def _rehash(conn: Connection, asset_id: object) -> None:
    rows = conn.execute(
        sa.text(
            "SELECT id, transaction_type::text AS kind, quantity, price, internal_hash,"
            " TO_CHAR(executed_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day"
            " FROM transactions WHERE asset_id = :a ORDER BY created_at, id"
        ),
        {"a": asset_id},
    ).all()
    taken: set[str] = set()
    assigned: list[tuple[str, str | None]] = []
    for row in rows:
        target: str | None = transaction_hash(asset_id, row.kind, row.quantity, row.price, row.day or "")
        if target in taken:
            target = None
        else:
            taken.add(str(target))
        if row.internal_hash != target:
            assigned.append((str(row.id), target))
    for transaction_id, _ in assigned:
        conn.execute(sa.text("UPDATE transactions SET internal_hash = NULL WHERE id = :t"), {"t": transaction_id})
    for transaction_id, target in assigned:
        conn.execute(
            sa.text("UPDATE transactions SET internal_hash = :h WHERE id = :t"), {"h": target, "t": transaction_id}
        )


def _refresh_cost(conn: Connection, asset_id: object) -> None:
    conn.execute(
        sa.text(
            "UPDATE assets SET avg_buy_price = COALESCE((SELECT SUM(quantity * price + fee)"
            " / NULLIF(SUM(quantity), 0) FROM transactions WHERE asset_id = :a AND price > 0"
            " AND transaction_type::text IN ('BUY', 'CONVERSION_IN', 'TRANSFER_IN')), 0) WHERE id = :a"
        ),
        {"a": asset_id},
    )


def merge_bonded_staking(conn: Connection) -> None:
    """Fond chaque actif Kraken de staking lié (SOL03) dans l'actif Kraken de son sous-jacent (SOL)."""
    pairs = conn.execute(
        sa.text(
            "SELECT s.id AS staked, s.quantity, b.id AS base FROM assets s JOIN assets b"
            " ON b.portfolio_id = s.portfolio_id AND LOWER(b.exchange) = 'kraken'"
            " AND b.symbol = SUBSTRING(s.symbol FROM :bonded)"
            " WHERE LOWER(s.exchange) = 'kraken' AND s.symbol ~ :bonded"
        ),
        {"bonded": BONDED},
    ).all()
    for pair in pairs:
        move = _staking_move(conn, pair.staked, pair.base)
        if move:
            conn.execute(
                sa.text("DELETE FROM transactions WHERE id IN :ids").bindparams(sa.bindparam("ids", expanding=True)),
                {"ids": move},
            )
        conn.execute(
            sa.text("UPDATE transactions SET asset_id = :b WHERE asset_id = :s"), {"b": pair.base, "s": pair.staked}
        )
        conn.execute(
            sa.text("UPDATE assets SET quantity = quantity + :q WHERE id = :b"), {"q": pair.quantity, "b": pair.base}
        )
        conn.execute(sa.text("DELETE FROM assets WHERE id = :s"), {"s": pair.staked})
        _rehash(conn, pair.base)
        _refresh_cost(conn, pair.base)


def upgrade() -> None:
    merge_bonded_staking(op.get_bind())


def downgrade() -> None:
    pass
