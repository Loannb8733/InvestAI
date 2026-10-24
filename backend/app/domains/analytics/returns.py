import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.analytics.core import AnalyticsCore, last_known_price
from app.domains.analytics.metrics import compute_returns
from app.domains.analytics.scoring import calc_beta, interpret_beta
from app.domains.analytics.xirr import build_xirr_cashflows, xirr
from app.domains.market_data.fx.spot import spot_rates
from app.domains.portfolio.models import Asset, AssetType, Portfolio
from app.domains.transactions.models import Transaction
from app.services.metrics_service import metrics_service

logger = logging.getLogger(__name__)

XIRR_MIN_PCT = -95.0
XIRR_MAX_PCT = 1000.0


async def _spot_or_one(from_ccy: str, target: str, failure_log: str) -> float:
    try:
        rate = await spot_rates.get(from_ccy, target)
        return float(rate) if rate else 1.0
    except Exception as exc:  # noqa: BLE001
        logger.warning(failure_log, target, exc)
        return 1.0


def _clamped_pct(rate: float) -> float:
    rate_pct = round(rate * 100, 2)
    clamped = max(XIRR_MIN_PCT, min(rate_pct, XIRR_MAX_PCT))
    if clamped != rate_pct:
        logger.warning("XIRR %.2f%% out of range, clamped to %.2f%% (possible data issue)", rate_pct, clamped)
    return clamped


def _merge_quantities(raw_assets: list[Asset]) -> tuple[dict[str, Asset], dict[str, float]]:
    seen: dict[str, Asset] = {}
    qty_map: dict[str, float] = {}
    for a in raw_assets:
        if a.symbol not in seen:
            seen[a.symbol] = a
            qty_map[a.symbol] = float(a.quantity)
        else:
            qty_map[a.symbol] += float(a.quantity)
    return seen, qty_map


def _weighted_beta(rows: list[tuple[str, float | None, float]], crypto: bool) -> float | None:
    weighted = 0.0
    total = 0.0
    for at, beta, val in rows:
        if beta is not None and (at == "crypto") == crypto:
            weighted += beta * val
            total += val
    return round(weighted / total, 3) if total > 0 else None


class AnalyticsReturns(AnalyticsCore):
    async def _current_value(self, db: AsyncSession, user_id: str, currency: str, target: str) -> float:
        try:
            dashboard = await metrics_service.get_user_dashboard_metrics(db, user_id, currency=currency, days=0)
            return float(dashboard.get("total_value", 0.0))
        except Exception as exc:  # noqa: BLE001
            logger.warning("XIRR: metrics_service fallback to _get_asset_price: %s", exc)
        current_value = 0.0
        for asset in await self._get_user_assets(db, user_id, exclude_stablecoins=False):
            current_value += float(asset.quantity) * await self._get_asset_price(asset)
        usd_to_target = 1.0
        if target != "USD":
            usd_to_target = await _spot_or_one("USD", target, "XIRR fallback forex USD→%s unavailable (%s)")
        return current_value * usd_to_target

    async def compute_xirr(self, db: AsyncSession, user_id: str, currency: str = "EUR") -> float | None:
        """TRI annualisé en %, borné à [-95, 1000] : chaque flux externe est converti au taux historique de sa
        transaction, la valeur finale vient de metrics_service ; None si le calcul n'a pas de sens."""
        portfolios = (await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))).scalars().all()
        if not portfolios:
            return None

        tx_result = await db.execute(
            select(Transaction)
            .join(Asset, Transaction.asset_id == Asset.id)
            .where(Asset.portfolio_id.in_([p.id for p in portfolios]))
            .order_by(Transaction.executed_at.asc())
        )
        transactions = list(tx_result.scalars().all())
        if not transactions:
            return None

        target = currency.upper()
        eur_to_target = 1.0
        if target != "EUR":
            eur_to_target = await _spot_or_one("EUR", target, "Forex EUR→%s unavailable (%s), using 1.0")

        cashflows, skipped = build_xirr_cashflows(transactions, eur_to_target)
        if skipped > 0:
            logger.warning("XIRR: skipped %d transactions with NULL executed_at", skipped)
        if not cashflows:
            return None

        current_value = await self._current_value(db, user_id, currency, target)
        if current_value <= 0:
            return None
        cashflows.append((datetime.now(UTC), current_value))

        if not any(a < 0 for _, a in cashflows):
            return None
        rate = xirr(cashflows)
        return _clamped_pct(rate) if rate is not None else None

    async def compute_beta(
        self,
        db: AsyncSession,
        user_id: str,
        days: int = 90,
        portfolio_id: str | None = None,
    ) -> dict[str, Any]:
        """Bêta = Cov(actif, référence) / Var(référence), contre BTC pour la crypto et SPY pour le reste ;
        les bêtas de portefeuille sont pondérés par la valeur."""
        raw_assets = await self._get_user_assets(db, user_id, portfolio_id=portfolio_id)
        if not raw_assets:
            return {"assets": [], "portfolio_beta_crypto": None, "portfolio_beta_stock": None}

        seen, qty_map = _merge_quantities(raw_assets)
        btc_returns = compute_returns(await self._history_prices("BTC", days=days))
        spy_returns = compute_returns(await self._history_prices("SPY", days=days))

        asset_betas: list[dict[str, Any]] = []
        rows: list[tuple[str, float | None, float]] = []
        for sym, asset in seen.items():
            prices = await self._history_prices(sym, days=days)
            price = prices[-1] if prices and prices[-1] > 0 else last_known_price(asset)
            if price <= 0:
                continue
            val = float(Decimal(str(qty_map[sym])) * Decimal(str(price)))
            at = asset.asset_type.value if isinstance(asset.asset_type, AssetType) else asset.asset_type
            bench_returns, bench_name = (btc_returns, "BTC") if at == "crypto" else (spy_returns, "SPY")
            beta = calc_beta(compute_returns(prices), bench_returns)
            asset_betas.append(
                {
                    "symbol": sym,
                    "asset_type": at,
                    "beta": round(beta, 3) if beta is not None else None,
                    "benchmark": bench_name,
                    "interpretation": interpret_beta(beta),
                    "value": round(val, 2),
                }
            )
            rows.append((at, beta, val))

        return {
            "assets": sorted(asset_betas, key=lambda x: abs(x["beta"] or 0), reverse=True),
            "portfolio_beta_crypto": _weighted_beta(rows, crypto=True),
            "portfolio_beta_stock": _weighted_beta(rows, crypto=False),
            "benchmarks": {
                "crypto": "BTC",
                "stock": "SPY (S&P 500)",
            },
        }
