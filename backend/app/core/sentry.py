import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def init_sentry() -> None:
    """Active Sentry si un DSN est configuré ; un échec n'empêche jamais le démarrage."""
    if not settings.sentry_enabled:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.redis import RedisIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        from app.core.sentry_scrub import scrub_event

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.APP_ENV,
            release="investai@1.0.0",
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            profile_session_sample_rate=settings.SENTRY_PROFILES_SAMPLE_RATE,
            profile_lifecycle="trace",
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlalchemyIntegration(),
                CeleryIntegration(),
                RedisIntegration(),
            ],
            before_send=scrub_event,
            before_send_transaction=scrub_event,
        )
        logger.info("Sentry initialized (env=%s)", settings.APP_ENV)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Sentry init failed, continuing without it: %s", exc)
