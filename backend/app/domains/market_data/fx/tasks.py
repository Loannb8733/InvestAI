import logging
from datetime import date

from app.core.db.session import session_factory
from app.domains.market_data.fx.repository import FxRateRepository
from app.domains.market_data.fx.service import FxService
from app.tasks.async_runner import run_async
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

EARLIEST = date(2017, 1, 1)
PAIRS = (("USD", "EUR"), ("GBP", "EUR"), ("CHF", "EUR"))


async def refresh_reference_rates() -> dict[str, int]:
    """Complète le référentiel BCE de chaque paire ; -1 pour une paire en échec."""
    results: dict[str, int] = {}
    async with session_factory() as session:
        service = FxService(FxRateRepository(session))
        for base, quote in PAIRS:
            pair = f"{base}->{quote}"
            try:
                results[pair] = await service.refresh(base, quote, EARLIEST)
                await session.commit()
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                logger.warning("FX %s : rafraîchissement échoué (%s)", pair, exc)
                results[pair] = -1
            else:
                if results[pair]:
                    logger.info("FX %s : %d taux ajoutés", pair, results[pair])
    return results


@celery_app.task(name="app.domains.market_data.fx.tasks.refresh_fx_rates")  # type: ignore[untyped-decorator]
def refresh_fx_rates() -> dict[str, int]:
    """Tâche Celery planifiée : rafraîchit les taux de référence BCE."""
    return run_async(refresh_reference_rates())
