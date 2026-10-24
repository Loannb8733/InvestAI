from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.analytics.schemas import PlatformDistributionItem
from app.domains.portfolio.models import Asset, AssetType, Portfolio

PLATFORM_TRUST_SCORES: dict[str, int] = {
    "tangem": 10,
    "ledger": 10,
    "trezor": 10,
    "safepal": 9,
    "metamask": 8,
    "binance": 7,
    "kraken": 8,
    "coinbase": 7,
    "crypto.com": 6,
    "bitstamp": 7,
    "kucoin": 5,
    "bybit": 5,
    "okx": 6,
    "gate.io": 5,
    "bitpanda": 6,
    "revolut": 6,
    "trade republic": 6,
    "tokimo": 4,
}
DEFAULT_TRUST_SCORE = 4
UNASSIGNED = "Non assigné"


async def platform_distribution(db: AsyncSession, user_id: UUID) -> list[PlatformDistributionItem]:
    """Valeur au cours stocké, par plateforme fusionnée sans tenir compte de la casse (première graphie gardée)."""
    result = await db.execute(
        select(
            Asset.exchange,
            func.sum(Asset.current_price * Asset.quantity).label("total_value"),
        )
        .join(Portfolio, Asset.portfolio_id == Portfolio.id)
        .where(
            Portfolio.user_id == user_id,
            Asset.quantity > 0,
            Asset.asset_type != AssetType.CROWDFUNDING,
        )
        .group_by(Asset.exchange)
    )

    seen_names: dict[str, str] = {}
    merged: dict[str, float] = {}
    for exchange, value in result.all():
        display = (exchange or "").strip() or UNASSIGNED
        key = display.lower()
        if key not in seen_names:
            seen_names[key] = display
        merged[key] = merged.get(key, 0) + float(value or 0)

    grand_total = sum(merged.values())
    return [
        PlatformDistributionItem(
            name=seen_names[key],
            value=round(val, 2),
            percentage=round(val / grand_total * 100, 1) if grand_total > 0 else 0,
            trust_score=PLATFORM_TRUST_SCORES.get(key, DEFAULT_TRUST_SCORE),
        )
        for key, val in sorted(merged.items(), key=lambda x: -x[1])
    ]
