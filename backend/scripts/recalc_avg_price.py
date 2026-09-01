"""Recalculate avg_buy_price for all assets from their transactions."""

import asyncio
import os
import sys
from decimal import Decimal

# « /app » est le chemin dans le conteneur ; le second couvre une exécution
# locale ou en CI, où ce répertoire n'existe pas.
sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts._danger_guard import require_consent  # noqa: E402

# Refus prononcé AVANT tout import applicatif : il ne doit dépendre ni de SQLAlchemy,
# ni de la configuration, ni de la base. Placé plus bas, un import qui échoue le
# court-circuite et le script sort en erreur sans jamais expliquer pourquoi — constaté
# en CI, où le chemin « /app » du conteneur n'existe pas.
if __name__ == "__main__":
    require_consent(
        "recalc_avg_price.py",
        "Ce script réécrit avg_buy_price à partir des seuls quantity × price des achats,\n"
        "  SANS lire conversion_rate. Sur un trade libellé en USD, il rétablit le prix brut\n"
        "  en devise étrangère comme s'il s'agissait d'euros : exactement l'erreur de coût\n"
        "  de base que FIN-01 corrige. Le lancer défait FIN-01 sur tout le portefeuille.",
        "vérifier d'abord si un écart existe réellement — voir scripts/check_invariants.py\n"
        "  et docs/audit/BACKLOG.md (NEW-08).",
    )


from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.asset import Asset, AssetType  # noqa: E402
from app.models.transaction import Transaction, TransactionType  # noqa: E402

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
