"""Point d'entrée des métriques : portefeuille, historique et agrégat mis en cache."""

import asyncio
import logging
import time
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_client
from app.domains.dashboard.metrics import repository
from app.domains.dashboard.metrics.aggregate import (
    EMPTY_DASHBOARD,
    HISTORY_UNAVAILABLE,
    DashboardTotals,
    aggregate_by_symbol,
    apply_period_changes,
    build_dashboard_summary,
    gain_figures,
    symbols_by_type,
)
from app.domains.dashboard.metrics.cache import (
    DASHBOARD_CACHE_TTL,
    dashboard_cache,
    dashboard_inflight,
    put_dashboard,
)
from app.domains.dashboard.metrics.history import compute_portfolio_history
from app.domains.dashboard.metrics.portfolio import compute_portfolio_metrics
from app.domains.market_data.history.reader import local_history
from app.domains.portfolio.models import Portfolio

logger = logging.getLogger(__name__)

_LOCK_TTL = 20
_PEER_WAIT = 3.0
_PEER_POLL = 0.15
_CACHE_SECTION = "metrics"


class MetricsService:
    """Calcule les métriques d'un portefeuille et l'agrégat d'un utilisateur."""

    async def get_portfolio_metrics(
        self,
        db: AsyncSession,
        portfolio_id: str,
        currency: str = "EUR",
        include_zero_quantity: bool = False,
        min_value_eur: float = 0.10,
    ) -> dict[str, Any]:
        """Métriques complètes d'un portefeuille."""
        return await compute_portfolio_metrics(db, portfolio_id, currency, include_zero_quantity, min_value_eur)

    async def get_portfolio_history(self, db: AsyncSession, portfolio_id: str, currency: str = "EUR") -> dict[str, Any]:
        """Historique d'investissement d'un portefeuille."""
        return await compute_portfolio_history(db, portfolio_id, currency)

    async def get_portfolio_performance(
        self, db: AsyncSession, portfolio_id: str, currency: str = "EUR"
    ) -> dict[str, Any]:
        """Métriques d'un portefeuille et son gain total, comme l'agrégat du compte."""
        metrics = await self.get_portfolio_metrics(db, portfolio_id, currency)
        history = await self.get_portfolio_history(db, portfolio_id, currency)
        gain = gain_figures(
            Decimal(str(metrics["unrealized_gain"])),
            Decimal(str(history["realized_gains"])),
            Decimal(str(history["total_invested_all_time"])),
            Decimal(str(metrics["total_dividend_income"])),
        )
        return {**metrics, **gain, "by_exchange": history["by_exchange"]}

    async def fetch_period_changes(self, symbols: dict[str, list[str]], days: int) -> dict[str, float]:
        """Variation en pourcentage sur `days` jours ; un symbole sans deux cours connus est absent."""
        flat = [symbol for group in symbols.values() for symbol in group]
        changes: dict[str, float] = {}
        for symbol, history in (await local_history(flat, max(days, 2))).items():
            if len(history.prices) >= 2 and history.prices[0] != 0:
                changes[symbol] = (history.prices[-1] - history.prices[0]) / history.prices[0] * 100
        return changes

    async def get_user_dashboard_metrics(
        self, db: AsyncSession, user_id: str, currency: str = "EUR", days: int = 30
    ) -> dict[str, Any]:
        """Agrégat de l'utilisateur, en cache 2 minutes ; des requêtes simultanées partagent un seul calcul."""
        key = (user_id, days, currency)
        cached = dashboard_cache.get(key)
        if cached is not None and time.time() - cached[0] < DASHBOARD_CACHE_TTL:
            return cached[1]
        inflight = dashboard_inflight.get(key)
        if inflight is not None:
            return await inflight
        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        dashboard_inflight[key] = future
        try:
            result = await self._shared_or_computed(db, user_id, currency, days)
            if not future.done():
                future.set_result(result)
            return result
        except BaseException as exc:
            if not future.done():
                future.set_exception(exc)
            raise
        finally:
            dashboard_inflight.pop(key, None)

    async def _shared_or_computed(self, db: AsyncSession, user_id: str, currency: str, days: int) -> dict[str, Any]:
        key = (user_id, days, currency)
        shared = await redis_client.get_cached_dashboard(user_id, days, currency, section=_CACHE_SECTION)
        if shared is not None:
            put_dashboard(key, (time.time(), shared))
            return shared
        result = await self._compute_dashboard_cross_worker(db, user_id, currency, days)
        put_dashboard(key, (time.time(), result))
        await redis_client.cache_dashboard(user_id, days, currency, result, section=_CACHE_SECTION)
        return result

    async def _compute_dashboard_cross_worker(
        self, db: AsyncSession, user_id: str, currency: str, days: int
    ) -> dict[str, Any]:
        lock = f"dashboard:{user_id}:{days}:{currency}"
        acquired = await redis_client.try_acquire_lock(lock, ttl=_LOCK_TTL)
        if not acquired:
            deadline = time.time() + _PEER_WAIT
            while time.time() < deadline:
                await asyncio.sleep(_PEER_POLL)
                shared = await redis_client.get_cached_dashboard(user_id, days, currency, section=_CACHE_SECTION)
                if shared is not None:
                    return shared
        try:
            return await self._compute_user_dashboard_metrics(db, user_id, currency, days)
        finally:
            if acquired:
                await redis_client.release_lock(lock)

    async def _portfolio_figures(
        self, db: AsyncSession, portfolio: Portfolio, currency: str
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        try:
            metrics = await self.get_portfolio_metrics(db, str(portfolio.id), currency)
        except Exception:
            logger.exception("get_portfolio_metrics failed for portfolio %s", portfolio.id)
            return None
        try:
            history = await self.get_portfolio_history(db, str(portfolio.id), currency)
        except Exception:
            logger.exception("get_portfolio_history failed for portfolio %s", portfolio.id)
            history = HISTORY_UNAVAILABLE
        return metrics, history

    async def _compute_user_dashboard_metrics(
        self, db: AsyncSession, user_id: str, currency: str = "EUR", days: int = 30
    ) -> dict[str, Any]:
        portfolios = await repository.user_portfolios(db, user_id)
        if not portfolios:
            return {**EMPTY_DASHBOARD, "allocation": [], "top_performers": [], "worst_performers": []}
        totals = DashboardTotals()
        for portfolio in portfolios:
            figures = await self._portfolio_figures(db, portfolio, currency)
            if figures is not None:
                totals.add(portfolio, *figures)
        aggregated = aggregate_by_symbol(totals.assets)
        changes = await self.fetch_period_changes(symbols_by_type(aggregated), days)
        apply_period_changes(aggregated, changes)
        return build_dashboard_summary(len(portfolios), totals, list(aggregated.values()), changes)


metrics_service = MetricsService()
