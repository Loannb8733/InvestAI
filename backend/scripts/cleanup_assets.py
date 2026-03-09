"""
Full asset cleanup (excluding CROWDFUNDING).

Run inside the backend container:
    python -m scripts.cleanup_assets

Steps:
1. Delete assets with quantity=0 (closed positions) — keeps transaction history
2. Delete phantom assets (0 transactions, not crowdfunding)
3. Delete dust assets (value < 0.01 EUR)
4. Recalculate avg_buy_price from transactions for all remaining assets
5. Clean up empty portfolios
"""

import asyncio
import sys
from decimal import Decimal

sys.path.insert(0, "/app")

from sqlalchemy import and_, delete, func, select, text

from app.core.database import AsyncSessionLocal
from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction, TransactionType

BUY_TYPES = [
    TransactionType.BUY,
    TransactionType.TRANSFER_IN,
    TransactionType.AIRDROP,
    TransactionType.STAKING_REWARD,
    TransactionType.CONVERSION_IN,
    TransactionType.DIVIDEND,
    TransactionType.INTEREST,
]

SELL_TYPES = [
    TransactionType.SELL,
    TransactionType.TRANSFER_OUT,
    TransactionType.CONVERSION_OUT,
    TransactionType.FEE,
]


async def main():
    async with AsyncSessionLocal() as db:
        # ── Step 1: Delete QTY=0 assets (closed positions) ──
        result = await db.execute(
            select(Asset).where(
                Asset.quantity == 0,
                Asset.asset_type != AssetType.CROWDFUNDING,
            )
        )
        zero_assets = result.scalars().all()
        print(f"=== ASSETS QTY=0 (positions fermées): {len(zero_assets)} ===")
        for a in zero_assets:
            # Count transactions for info
            tx_count = await db.execute(
                select(func.count()).select_from(Transaction).where(Transaction.asset_id == a.id)
            )
            cnt = tx_count.scalar()
            print(f"  Suppression: {a.symbol:8s} | exchange={str(a.exchange or ''):10s} | {cnt} tx")
            # Delete transactions first, then asset
            await db.execute(delete(Transaction).where(Transaction.asset_id == a.id))
            await db.delete(a)
        await db.commit()
        print(f"  → {len(zero_assets)} assets supprimés.\n")

        # ── Step 2: Delete phantom assets (0 transactions, not crowdfunding) ──
        result = await db.execute(
            select(Asset).where(
                Asset.asset_type != AssetType.CROWDFUNDING,
            )
        )
        all_assets = result.scalars().all()
        phantom_count = 0
        for a in all_assets:
            tx_count = await db.execute(
                select(func.count()).select_from(Transaction).where(Transaction.asset_id == a.id)
            )
            if tx_count.scalar() == 0:
                print(f"  Phantom: {a.symbol:8s} | qty={float(a.quantity):.8f} | exchange={a.exchange}")
                await db.delete(a)
                phantom_count += 1
        await db.commit()
        print(f"=== PHANTOMS (0 tx): {phantom_count} supprimés ===\n")

        # ── Step 3: Delete dust assets (very small qty, negligible value) ──
        result = await db.execute(
            select(Asset).where(
                Asset.asset_type != AssetType.CROWDFUNDING,
                Asset.quantity > 0,
            )
        )
        remaining = result.scalars().all()
        dust_count = 0
        for a in remaining:
            value = float(a.quantity) * float(a.avg_buy_price)
            # Also check if qty is essentially zero (< 0.0001 for most, < 1 for stables)
            is_dust = False
            if float(a.quantity) < 0.00001 and value < 0.01:
                is_dust = True
            if is_dust:
                tx_count_r = await db.execute(
                    select(func.count()).select_from(Transaction).where(Transaction.asset_id == a.id)
                )
                cnt = tx_count_r.scalar()
                print(f"  Dust: {a.symbol:8s} | qty={float(a.quantity):.10f} | val={value:.4f} EUR | {cnt} tx")
                await db.execute(delete(Transaction).where(Transaction.asset_id == a.id))
                await db.delete(a)
                dust_count += 1
        await db.commit()
        print(f"=== DUST: {dust_count} supprimés ===\n")

        # ── Step 4: Recalculate avg_buy_price from transactions ──
        result = await db.execute(
            select(Asset).where(
                Asset.asset_type != AssetType.CROWDFUNDING,
                Asset.quantity > 0,
            )
        )
        remaining = result.scalars().all()
        print(f"=== RECALCUL AVG_BUY_PRICE ({len(remaining)} assets) ===")

        for asset in remaining:
            # Get all BUY-type transactions for this asset
            tx_result = await db.execute(
                select(Transaction).where(
                    Transaction.asset_id == asset.id,
                    Transaction.transaction_type.in_(BUY_TYPES),
                    Transaction.price > 0,
                )
            )
            buy_txs = tx_result.scalars().all()

            if not buy_txs:
                print(f"  {asset.symbol:8s} ({asset.exchange:10s}) | Pas de BUY avec prix > 0, skip")
                continue

            # Weighted average: sum(qty * price) / sum(qty)
            total_cost = sum(float(tx.quantity) * float(tx.price) for tx in buy_txs)
            total_qty = sum(float(tx.quantity) for tx in buy_txs)

            if total_qty > 0:
                new_avg = total_cost / total_qty
                old_avg = float(asset.avg_buy_price)
                asset.avg_buy_price = Decimal(str(round(new_avg, 12)))
                diff = abs(new_avg - old_avg)
                flag = " CORRIGÉ" if diff > 0.01 else ""
                print(
                    f"  {asset.symbol:8s} ({str(asset.exchange or ''):10s}) | ancien={old_avg:>12.2f} | nouveau={new_avg:>12.2f}{flag}"
                )

        await db.commit()
        print()

        # ── Step 5: Clean up empty portfolios ──
        portfolios = await db.execute(select(Portfolio))
        empty_count = 0
        for p in portfolios.scalars().all():
            asset_count = await db.execute(select(func.count()).select_from(Asset).where(Asset.portfolio_id == p.id))
            if asset_count.scalar() == 0:
                print(f"  Portfolio vide: '{p.name}' → suppression")
                await db.delete(p)
                empty_count += 1
        await db.commit()
        print(f"=== PORTFOLIOS VIDES: {empty_count} supprimés ===\n")

        # ── Final summary ──
        final_assets = await db.execute(
            select(func.count()).select_from(Asset).where(Asset.asset_type != AssetType.CROWDFUNDING)
        )
        final_txs = await db.execute(select(func.count()).select_from(Transaction))
        final_portfolios = await db.execute(select(func.count()).select_from(Portfolio))

        print("=== RÉSUMÉ FINAL ===")
        print(f"  Assets crypto: {final_assets.scalar()}")
        print(f"  Transactions: {final_txs.scalar()}")
        print(f"  Portfolios: {final_portfolios.scalar()}")

        # Show remaining assets
        result = await db.execute(
            select(Asset)
            .where(
                Asset.asset_type != AssetType.CROWDFUNDING,
            )
            .order_by(Asset.symbol)
        )
        print(f"\n{'SYMBOL':8s} | {'EXCHANGE':10s} | {'QTY':>16s} | {'AVG_PRICE':>12s}")
        print("-" * 60)
        for a in result.scalars().all():
            print(
                f"{a.symbol:8s} | {str(a.exchange or ''):10s} | {float(a.quantity):>16.8f} | {float(a.avg_buy_price):>12.2f}"
            )


if __name__ == "__main__":
    asyncio.run(main())
