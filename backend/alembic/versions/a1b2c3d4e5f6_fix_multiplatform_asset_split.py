"""fix_multiplatform_asset_split

Split transactions whose exchange differs from their asset's exchange
into separate per-exchange assets so the Résumé tab shows correct
platform distribution.

Revision ID: a1b2c3d4e5f6
Revises: 293ca70d7b68
Create Date: 2026-03-16 01:00:00.000000

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '293ca70d7b68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Find transactions whose exchange doesn't match their asset's exchange
    mismatched = conn.execute(sa.text("""
        SELECT t.id AS tx_id, t.exchange AS tx_exchange, t.quantity, t.price,
               t.transaction_type, t.fee, t.currency, t.executed_at, t.notes, t.external_id,
               a.id AS asset_id, a.portfolio_id, a.symbol, a.name, a.asset_type,
               a.exchange AS asset_exchange, a.currency AS asset_currency
        FROM transactions t
        JOIN assets a ON t.asset_id = a.id
        WHERE t.exchange IS NOT NULL
          AND t.exchange != ''
          AND LOWER(TRIM(t.exchange)) != LOWER(TRIM(a.exchange))
    """)).fetchall()

    if not mismatched:
        return

    # Group by (portfolio_id, symbol, tx_exchange) to create assets
    new_assets = {}  # (portfolio_id, symbol, tx_exchange) -> asset_id
    for row in mismatched:
        key = (str(row.portfolio_id), row.symbol, row.tx_exchange.strip())
        if key not in new_assets:
            # Check if asset already exists
            existing = conn.execute(sa.text("""
                SELECT id FROM assets
                WHERE portfolio_id = :pid AND symbol = :sym AND exchange = :exc
            """), {"pid": row.portfolio_id, "sym": row.symbol, "exc": row.tx_exchange.strip()}).fetchone()

            if existing:
                new_assets[key] = str(existing.id)
            else:
                new_id = str(uuid.uuid4())
                conn.execute(sa.text("""
                    INSERT INTO assets (id, portfolio_id, symbol, name, asset_type, quantity, avg_buy_price, exchange, currency)
                    VALUES (:id, :pid, :sym, :name, :atype, 0, 0, :exc, :cur)
                """), {
                    "id": new_id,
                    "pid": row.portfolio_id,
                    "sym": row.symbol,
                    "name": row.name,
                    "atype": row.asset_type,
                    "exc": row.tx_exchange.strip(),
                    "cur": row.asset_currency,
                })
                new_assets[key] = new_id

    # Move transactions to the correct asset
    for row in mismatched:
        key = (str(row.portfolio_id), row.symbol, row.tx_exchange.strip())
        target_asset_id = new_assets[key]
        conn.execute(sa.text("""
            UPDATE transactions SET asset_id = :new_aid WHERE id = :tid
        """), {"new_aid": target_asset_id, "tid": row.tx_id})

    # Recalculate quantities for affected assets
    affected_asset_ids = set()
    for row in mismatched:
        affected_asset_ids.add(str(row.asset_id))  # original asset
        key = (str(row.portfolio_id), row.symbol, row.tx_exchange.strip())
        affected_asset_ids.add(new_assets[key])  # new/target asset

    add_types = ('buy', 'conversion_in', 'transfer_in', 'airdrop', 'staking_reward', 'dividend', 'interest')
    sub_types = ('sell', 'transfer_out', 'conversion_out', 'fee')

    for aid in affected_asset_ids:
        # Recalculate quantity
        result = conn.execute(sa.text("""
            SELECT
                COALESCE(SUM(CASE WHEN LOWER(transaction_type) IN :add_types THEN quantity ELSE 0 END), 0)
                - COALESCE(SUM(CASE WHEN LOWER(transaction_type) IN :sub_types THEN quantity ELSE 0 END), 0)
                AS net_qty
            FROM transactions WHERE asset_id = :aid
        """), {"aid": aid, "add_types": add_types, "sub_types": sub_types}).fetchone()

        net_qty = max(0, float(result.net_qty)) if result else 0

        # Recalculate avg_buy_price from BUY + CONVERSION_IN
        buy_result = conn.execute(sa.text("""
            SELECT COALESCE(SUM(quantity), 0) AS total_qty,
                   COALESCE(SUM(quantity * price), 0) AS total_cost
            FROM transactions
            WHERE asset_id = :aid AND LOWER(transaction_type) IN ('buy', 'conversion_in')
        """), {"aid": aid}).fetchone()

        avg_price = 0
        if buy_result and float(buy_result.total_qty) > 0:
            avg_price = float(buy_result.total_cost) / float(buy_result.total_qty)

        conn.execute(sa.text("""
            UPDATE assets SET quantity = :qty, avg_buy_price = :avg WHERE id = :aid
        """), {"qty": net_qty, "avg": avg_price, "aid": aid})


def downgrade() -> None:
    # This migration is a data fix; downgrade would require re-merging
    # which is destructive. Skip.
    pass
