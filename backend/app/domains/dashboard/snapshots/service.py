"""Point d'entrée des instantanés : série de valeur mise en cache, instantané d'un compte, indicateurs de risque."""

import asyncio
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.dashboard.metrics.cache import put_bounded
from app.domains.dashboard.metrics.service import metrics_service
from app.domains.dashboard.models import PortfolioSnapshot
from app.domains.dashboard.snapshots.risk import (
    calculate_hhi,
    calculate_max_drawdown,
    calculate_sharpe_ratio,
    calculate_stress_test,
    calculate_var,
    calculate_volatility,
)
from app.domains.dashboard.snapshots.series import compute_value_series

_SERIES_CACHE_TTL = 120
_MAX_SERIES_CACHE = 200

series_cache: dict[tuple[str, int], tuple[float, list[dict[str, Any]]]] = {}
series_inflight: dict[tuple[str, int], asyncio.Future[list[dict[str, Any]]]] = {}


class SnapshotService:
    """Série de valeur d'un compte et ce qui s'en déduit."""

    async def create_user_snapshot(
        self, db: AsyncSession, user_id: str, currency: str = "EUR"
    ) -> PortfolioSnapshot | None:
        """Enregistre la valeur du compte ; rien sans actif."""
        metrics = await metrics_service.get_user_dashboard_metrics(db, user_id, currency)
        if metrics["assets_count"] == 0:
            return None
        snapshot = PortfolioSnapshot(
            user_id=user_id,
            portfolio_id=None,
            snapshot_date=datetime.now(UTC),
            total_value=Decimal(str(metrics["total_value"])),
            total_invested=Decimal(str(metrics["total_invested"])),
            total_gain_loss=Decimal(str(metrics["total_gain_loss"])),
            currency=currency,
        )
        db.add(snapshot)
        await db.commit()
        await db.refresh(snapshot)
        return snapshot

    async def build_portfolio_value_series(
        self, db: AsyncSession, user_id: str, days: int = 30
    ) -> list[dict[str, Any]]:
        """Série quotidienne en cache 2 minutes ; des requêtes simultanées partagent un seul calcul."""
        key = (user_id, days)
        cached = series_cache.get(key)
        if cached is not None and time.time() - cached[0] < _SERIES_CACHE_TTL:
            return cached[1]
        inflight = series_inflight.get(key)
        if inflight is not None:
            return await inflight
        future: asyncio.Future[list[dict[str, Any]]] = asyncio.get_event_loop().create_future()
        series_inflight[key] = future
        try:
            result = await self._compute_portfolio_value_series(db, user_id, days)
            put_bounded(series_cache, key, (time.time(), result), _MAX_SERIES_CACHE)
            if not future.done():
                future.set_result(result)
            return result
        except BaseException as exc:
            if not future.done():
                future.set_exception(exc)
            raise
        finally:
            series_inflight.pop(key, None)

    async def _compute_portfolio_value_series(self, db: AsyncSession, user_id: str, days: int) -> list[dict[str, Any]]:
        return await compute_value_series(db, user_id, days)

    async def get_all_risk_metrics(
        self,
        db: AsyncSession,
        user_id: str,
        current_value: float,
        allocations: list[dict[str, Any]],
        days: int = 30,
        history: list[dict[str, Any]] | None = None,
        roi_annualized: float | None = None,
    ) -> dict[str, Any]:
        """Tous les indicateurs de risque, sur une seule série de valeur."""
        series = history if history is not None else await self.build_portfolio_value_series(db, user_id, days)
        return {
            "volatility": calculate_volatility(series),
            "sharpe_ratio": calculate_sharpe_ratio(series, roi_annualized=roi_annualized),
            "max_drawdown": calculate_max_drawdown(series),
            "var_95": calculate_var(series, 0.95, current_value),
            "concentration": calculate_hhi(allocations),
            "stress_test_20": calculate_stress_test(current_value, 0.20),
            "stress_test_40": calculate_stress_test(current_value, 0.40),
        }


snapshot_service = SnapshotService()
