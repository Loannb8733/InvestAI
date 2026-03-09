"""Recalculate avg_buy_price for all assets from their transactions."""

import asyncio
import sys
from decimal import Decimal

sys.path.insert(0, "/app")

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.asset import Asset, AssetType
from app.models.transaction import Transaction, TransactionType

BUY_TYPES = [
    TransactionType.BUY,
    TransactionType.TRANSFER_IN,
    TransactionType.CONVERSION_IN,
]


async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Asset).where(
                Asset.asset_type != AssetType.CROWDFUNDING,
                Asset.quantity > 0,
            )
        )
        assets = result.scalars().all()
        print(f"=== RECALCUL AVG_BUY_PRICE ({len(assets)} assets) ===\n")

        for asset in assets:
            tx_result = await db.execute(
                select(Transaction).where(
                    Transaction.asset_id == asset.id,
                    Transaction.transaction_type.in_(BUY_TYPES),
                    Transaction.price > 0,
                )
            )
            buy_txs = tx_result.scalars().all()

            if not buy_txs:
                print(f"  {asset.symbol:8s} ({str(asset.exchange or ''):10s}) | Pas de BUY avec prix > 0")
                continue

            total_cost = sum(float(tx.quantity) * float(tx.price) for tx in buy_txs)
            total_qty = sum(float(tx.quantity) for tx in buy_txs)

            if total_qty > 0:
                new_avg = total_cost / total_qty
                old_avg = float(asset.avg_buy_price)
                asset.avg_buy_price = Decimal(str(round(new_avg, 12)))
                diff = abs(new_avg - old_avg)
                flag = " CORRIGE" if diff > 0.01 else ""
                print(
                    f"  {asset.symbol:8s} ({str(asset.exchange or ''):10s}) | ancien={old_avg:>12.2f} | nouveau={new_avg:>12.2f}{flag}"
                )

        await db.commit()
        print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
