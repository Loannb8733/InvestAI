from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.error_handlers import register_error_handlers
from app.core.health import router as health_router
from app.core.http.cache_invalidation import dashboard_cache_invalidation
from app.core.http.cors import add_cors_middleware
from app.core.http.request_logging import RequestLoggingMiddleware
from app.core.http.security_headers import security_headers
from app.core.logging import setup_logging
from app.core.openapi import OPENAPI_TAGS
from app.core.rate_limit import limiter
from app.core.sentry import init_sentry
from app.core.startup.lifespan import lifespan

DESCRIPTION = (
    "**InvestAI** — API de gestion et d'analyse d'investissements multi-actifs.\n\n"
    "Supporte crypto, actions, ETF et immobilier avec analytics avancés, "
    "prédictions ML, et intégrations exchanges (Binance, Kraken, Crypto.com).\n\n"
    "**Auth**: JWT Bearer token (15min) + refresh token (7j). "
    "Inclure `Authorization: Bearer <token>` dans les headers."
)


def create_app() -> FastAPI:
    """Assemble l'application : documentation, erreurs, middlewares et routes."""
    docs_prefix = settings.API_V1_PREFIX if settings.DEBUG else None
    application = FastAPI(
        title=settings.APP_NAME,
        description=DESCRIPTION,
        version="1.0.0",
        openapi_tags=OPENAPI_TAGS,
        openapi_url=f"{docs_prefix}/openapi.json" if docs_prefix else None,
        docs_url=f"{docs_prefix}/docs" if docs_prefix else None,
        redoc_url=f"{docs_prefix}/redoc" if docs_prefix else None,
        lifespan=lifespan,
        redirect_slashes=False,
    )
    application.state.limiter = limiter
    register_error_handlers(application)
    application.add_middleware(RequestLoggingMiddleware)
    application.add_middleware(GZipMiddleware, minimum_size=500)
    add_cors_middleware(application)
    application.middleware("http")(security_headers)
    application.middleware("http")(dashboard_cache_invalidation)
    application.include_router(api_router, prefix=settings.API_V1_PREFIX)
    application.include_router(health_router)
    return application


setup_logging()
init_sentry()
app = create_app()
