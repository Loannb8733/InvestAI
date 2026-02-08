"""Script to recalculate asset quantities from all transactions."""

import os
import sys
from decimal import Decimal

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.core.config import settings


def recalculate_quantities():
    """Recalculate all asset quantities based on transaction history."""
    database_url = settings.DATABASE_URL_SYNC
    print("Connecting to database...")

    engine = create_engine(database_url)

    with engine.connect() as conn:
        # Get all assets
        result = conn.execute(text("""
            SELECT a.id, a.symbol, a.portfolio_id, p.name as portfolio_name
            FROM assets a
            JOIN portfolios p ON a.portfolio_id = p.id
            ORDER BY p.name, a.symbol
        """))
        assets = result.fetchall()

        print(f"\nFound {len(assets)} assets to process\n")

        for asset in assets:
            asset_id = asset[0]
            symbol = asset[1]
            portfolio_name = asset[3]

            # Get all transactions for this asset, ordered by date
            tx_result = conn.execute(text("""
                SELECT transaction_type, quantity, price
                FROM transactions
                WHERE asset_id = :asset_id
                ORDER BY executed_at ASC
            """), {"asset_id": asset_id})
            transactions = tx_result.fetchall()

            # Calculate quantities
            total_quantity = Decimal("0")
            total_cost = Decimal("0")
            total_bought = Decimal("0")

            for tx in transactions:
                tx_type = tx[0].upper()
                quantity = Decimal(str(tx[1]))
                price = Decimal(str(tx[2]))

                if tx_type in ["BUY", "TRANSFER_IN", "AIRDROP", "STAKING_REWARD", "CONVERSION_IN"]:
                    total_quantity += quantity
                    total_cost += quantity * price
                    total_bought += quantity
                elif tx_type in ["SELL", "TRANSFER_OUT", "CONVERSION_OUT"]:
                    total_quantity -= quantity

            # Calculate average buy price
            avg_price = total_cost / total_bought if total_bought > 0 else Decimal("0")

            # Ensure non-negative
            if total_quantity < 0:
                total_quantity = Decimal("0")

            # Update asset
            conn.execute(text("""
                UPDATE assets
                SET quantity = :quantity, avg_buy_price = :avg_price, updated_at = NOW()
                WHERE id = :asset_id
            """), {
                "asset_id": asset_id,
                "quantity": float(total_quantity),
                "avg_price": float(avg_price)
            })

            print(f"[{portfolio_name}] {symbol}: {float(total_quantity):.8f} (avg: {float(avg_price):.2f})")

        conn.commit()
        print("\n✓ All quantities recalculated successfully!")


if __name__ == "__main__":
    recalculate_quantities()
