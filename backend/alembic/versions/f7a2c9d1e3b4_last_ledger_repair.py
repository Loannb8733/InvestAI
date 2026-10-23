"""last ledger repair

Revision ID: f7a2c9d1e3b4
Revises: e6a0b5c7d8f9
Create Date: 2026-10-23 18:00:00.000000

Dernière passe des trois auto-réparations que le démarrage jouait à chaque fois
(ADR-012). Plus aucun chemin d'écriture ne produit ces incohérences : saisie,
import CSV, synchronisation et changement de plateforme d'un actif écrivent
désormais juste. La logique est figée ici, sans dépendre du code de l'application.
"""

import hashlib
import uuid
from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal, localcontext

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from alembic import op

revision: str = "f7a2c9d1e3b4"
down_revision: str | None = "e6a0b5c7d8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_WALLET = "Tangem"
INFLOWS = ("BUY", "TRANSFER_IN", "CONVERSION_IN", "AIRDROP", "STAKING_REWARD", "DIVIDEND", "INTEREST")
OUTFLOWS = ("SELL", "TRANSFER_OUT", "CONVERSION_OUT", "FEE")
INTERNAL_NOTES = [
    f"{prefix}%"
    for prefix in (
        "Ajustement balance",
        "Phantom holding zeroed",
        "Solde zéro sur",
        "Dust sweep",
        "Manual adjustment",
        "Réconciliation :",
        "Cale ",
    )
]
SAME_TRANSFER = Decimal("0.01")
ZERO = Decimal("0")


def _signed(kind: str, quantity: Decimal) -> Decimal:
    if kind in INFLOWS:
        return quantity
    return -quantity if kind in OUTFLOWS else ZERO


def _platform_asset(conn: Connection, like: sa.Row[tuple[object, ...]], exchange: str) -> str:
    found = conn.execute(
        sa.text("SELECT id FROM assets WHERE portfolio_id = :p AND symbol = :s AND exchange = :e"),
        {"p": like.portfolio_id, "s": like.symbol, "e": exchange},
    ).first()
    if found is not None:
        return str(found.id)
    created = str(uuid.uuid4())
    conn.execute(
        sa.text(
            "INSERT INTO assets (id, portfolio_id, symbol, name, asset_type, quantity, avg_buy_price, exchange,"
            " currency) VALUES (:id, :p, :s, :n, :t, 0, 0, :e, :c)"
        ),
        {
            "id": created,
            "p": like.portfolio_id,
            "s": like.symbol,
            "n": like.name,
            "t": like.asset_type,
            "e": exchange,
            "c": like.asset_currency,
        },
    )
    return created


def _shift(conn: Connection, asset_id: str, delta: Decimal) -> None:
    conn.execute(
        sa.text("UPDATE assets SET quantity = GREATEST(quantity + :d, 0) WHERE id = :a"), {"d": delta, "a": asset_id}
    )


def _refresh_cost(conn: Connection, asset_ids: set[str]) -> None:
    for asset_id in asset_ids:
        conn.execute(
            sa.text(
                "UPDATE assets SET avg_buy_price = COALESCE((SELECT SUM(quantity * price + fee)"
                " / NULLIF(SUM(quantity), 0) FROM transactions WHERE asset_id = :a AND price > 0"
                " AND transaction_type::text IN ('BUY', 'CONVERSION_IN', 'TRANSFER_IN')), 0) WHERE id = :a"
            ),
            {"a": asset_id},
        )


def move_multiplatform(conn: Connection) -> None:
    """Range chaque transaction qui nomme une autre plateforme que son actif sur l'actif de cette plateforme."""
    rows = conn.execute(
        sa.text(
            "SELECT t.id, TRIM(t.exchange) AS exchange, t.quantity, t.transaction_type::text AS kind,"
            " a.id AS asset_id, a.portfolio_id, a.symbol, a.name, a.asset_type, a.currency AS asset_currency"
            " FROM transactions t JOIN assets a ON t.asset_id = a.id"
            " WHERE TRIM(COALESCE(t.exchange, '')) != '' AND LOWER(TRIM(t.exchange)) != LOWER(TRIM(a.exchange))"
        )
    ).all()
    touched: set[str] = set()
    for row in rows:
        target = _platform_asset(conn, row, row.exchange)
        conn.execute(sa.text("UPDATE transactions SET asset_id = :a WHERE id = :t"), {"a": target, "t": row.id})
        delta = _signed(row.kind, Decimal(row.quantity))
        _shift(conn, str(row.asset_id), -delta)
        _shift(conn, target, delta)
        touched |= {str(row.asset_id), target}
    _refresh_cost(conn, touched)


def _received(row: sa.Row[tuple[object, ...]]) -> Decimal:
    quantity = Decimal(row.quantity)
    fee = Decimal(row.fee or 0)
    if fee > 0 and (row.fee_currency or "").upper() in ("", row.symbol.upper()):
        return quantity - fee
    return quantity


def _same_transfer_in(conn: Connection, destination: str, row: sa.Row[tuple[object, ...]], quantity: Decimal) -> str | None:
    if row.executed_at is None:
        return None
    candidates = conn.execute(
        sa.text(
            "SELECT id, quantity FROM transactions WHERE asset_id = :a AND transaction_type::text = 'TRANSFER_IN'"
            " AND executed_at BETWEEN :lo AND :hi"
        ),
        {"a": destination, "lo": row.executed_at - timedelta(days=1), "hi": row.executed_at + timedelta(days=1)},
    )
    for candidate in candidates:
        if candidate.quantity > 0 and abs(candidate.quantity - quantity) / candidate.quantity < SAME_TRANSFER:
            return str(candidate.id)
    return None


def mirror_transfers(conn: Connection) -> None:
    """Relie chaque sortie non interne sans miroir à une entrée sur le wallet froid par défaut."""
    rows = conn.execute(
        sa.text(
            "SELECT t.id, t.quantity, t.price, t.fee, t.fee_currency, t.currency, t.executed_at, t.exchange,"
            " a.portfolio_id, a.symbol, a.name, a.asset_type, a.exchange AS asset_exchange,"
            " a.currency AS asset_currency"
            " FROM transactions t JOIN assets a ON t.asset_id = a.id"
            " LEFT JOIN transactions m ON t.related_transaction_id = m.id"
            " WHERE t.transaction_type::text = 'TRANSFER_OUT' AND m.id IS NULL"
            " AND NOT (COALESCE(t.notes, '') LIKE ANY(:internal)) AND LOWER(TRIM(a.exchange)) != LOWER(:wallet)"
        ),
        {"internal": INTERNAL_NOTES, "wallet": DEFAULT_WALLET},
    ).all()
    touched: set[str] = set()
    for row in rows:
        conn.execute(sa.text("UPDATE transactions SET related_transaction_id = NULL WHERE id = :t"), {"t": row.id})
        quantity = _received(row)
        if quantity <= 0:
            continue
        destination = _platform_asset(conn, row, DEFAULT_WALLET)
        mirror = _same_transfer_in(conn, destination, row, quantity)
        if mirror is None:
            mirror = str(uuid.uuid4())
            conn.execute(
                sa.text(
                    "INSERT INTO transactions (id, asset_id, transaction_type, quantity, price, fee, currency,"
                    " executed_at, exchange, notes, related_transaction_id)"
                    " VALUES (:id, :a, 'TRANSFER_IN', :q, :p, 0, :c, :at, :e, :n, :r)"
                ),
                {
                    "id": mirror,
                    "a": destination,
                    "q": quantity,
                    "p": row.price,
                    "c": row.currency,
                    "at": row.executed_at,
                    "e": DEFAULT_WALLET,
                    "n": f"Auto-mirror from {row.exchange or row.asset_exchange or 'unknown'}",
                    "r": row.id,
                },
            )
            _shift(conn, destination, quantity)
            touched.add(destination)
        conn.execute(
            sa.text("UPDATE transactions SET related_transaction_id = :m WHERE id = :t"), {"m": mirror, "t": row.id}
        )
    _refresh_cost(conn, touched)


def _canonical(value: object) -> str:
    with localcontext() as context:
        context.prec = 50
        return format(Decimal(str(value)).quantize(Decimal(1).scaleb(-12)), "f")


def transaction_hash(asset_id: object, kind: str, quantity: object, price: object, day: str) -> str:
    """Empreinte anti-doublon telle que la calcule le modèle au 2026-10-23."""
    parts = [str(asset_id), kind.lower(), _canonical(quantity), _canonical(price), day]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:40]


def rehash(conn: Connection) -> None:
    """Recalcule les empreintes ; en cas de collision, la plus ancienne garde la sienne, les autres sont vidées."""
    rows = conn.execute(
        sa.text(
            "SELECT id, asset_id, transaction_type::text AS kind, quantity, price, internal_hash,"
            " TO_CHAR(executed_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day"
            " FROM transactions ORDER BY created_at, id"
        )
    ).all()
    seen: set[str] = set()
    released: list[str] = []
    assigned: list[tuple[str, str]] = []
    for row in rows:
        target = transaction_hash(row.asset_id, row.kind, row.quantity, row.price, row.day or "")
        if target in seen:
            if row.internal_hash is not None:
                released.append(str(row.id))
            continue
        seen.add(target)
        if row.internal_hash != target:
            assigned.append((str(row.id), target))
    for transaction_id in released + [t for t, _ in assigned]:
        conn.execute(sa.text("UPDATE transactions SET internal_hash = NULL WHERE id = :t"), {"t": transaction_id})
    for transaction_id, target in assigned:
        conn.execute(
            sa.text("UPDATE transactions SET internal_hash = :h WHERE id = :t"), {"h": target, "t": transaction_id}
        )


def upgrade() -> None:
    conn = op.get_bind()
    move_multiplatform(conn)
    mirror_transfers(conn)
    rehash(conn)


def downgrade() -> None:
    pass
