from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import session_factory
from app.domains.market_data.history.repository import HistoryRepository
from app.domains.market_data.history.series import PriceSeries


async def local_history(
    symbols: Iterable[str], days: int, session: AsyncSession | None = None
) -> dict[str, PriceSeries]:
    """Séries des ``days`` derniers jours lues en base, sans réseau ; série vide pour un symbole inconnu.

    Le réseau est le travail des tâches de ``history.tasks`` : une requête web ne
    dépend jamais d'une API tierce.
    """
    wanted = list(dict.fromkeys(s.upper() for s in symbols if s))
    since = datetime.now(UTC).date() - timedelta(days=days)
    if session is not None:
        found = await HistoryRepository(session).series(wanted, since)
    else:
        async with session_factory() as own:
            found = await HistoryRepository(own).series(wanted, since)
    return {s: found.get(s, PriceSeries()) for s in wanted}


async def local_series(symbol: str, days: int, session: AsyncSession | None = None) -> PriceSeries:
    """Série d'un seul symbole, voir :func:`local_history`."""
    return (await local_history([symbol], days, session))[symbol.upper()]
