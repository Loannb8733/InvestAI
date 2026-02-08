"""
InvestAI - Backend API
Plateforme multi-utilisateurs de gestion et d'analyse d'investissements
"""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import engine
from app.core.logging import setup_logging, get_logger
from app.core.rate_limit import limiter
from app.models import Base

# Setup structured logging
setup_logging()
logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging HTTP requests with timing."""

    async def dispatch(self, request: Request, call_next):
        """Log request details and timing."""
        start_time = time.perf_counter()

        try:
            # Process the request
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log based on response status
            log_data = {
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "client_ip": request.client.host if request.client else "unknown",
            }

            # Skip health check logs to reduce noise
            if request.url.path != "/health":
                if response.status_code >= 500:
                    logger.error("Request failed", extra=log_data)
                elif response.status_code >= 400:
                    logger.warning("Request error", extra=log_data)
                elif duration_ms > 1000:  # Log slow requests (>1s)
                    logger.warning("Slow request", extra=log_data)
                else:
                    logger.debug("Request completed", extra=log_data)

            return response
        except Exception as e:
            import traceback
            logger.error(f"Middleware error: {type(e).__name__}: {e}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info(f"Starting {settings.APP_NAME} (env={settings.APP_ENV}, debug={settings.DEBUG})")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Trigger historical data cache on startup (via Celery)
    try:
        from app.tasks.history_cache import cache_historical_data
        cache_historical_data.delay()
        logger.info("Triggered historical data cache task")
    except Exception as e:
        logger.warning("Could not trigger history cache task: %s", e)
    yield
    # Shutdown
    logger.info(f"Shutting down {settings.APP_NAME}")
    await engine.dispose()


# Conditionally expose OpenAPI docs (only in development/debug mode)
app = FastAPI(
    title=settings.APP_NAME,
    description="API pour la gestion et l'analyse d'investissements",
    version="1.0.0",
    # Disable OpenAPI in production for security
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json" if settings.DEBUG else None,
    docs_url=f"{settings.API_V1_PREFIX}/docs" if settings.DEBUG else None,
    redoc_url=f"{settings.API_V1_PREFIX}/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# Global exception handler to log errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions and log them."""
    import traceback
    logger.error(f"Unhandled exception: {type(exc).__name__}: {exc}")
    logger.error(f"Traceback:\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
    )

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware with restricted methods and headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=settings.CORS_ALLOWED_METHODS,  # Restricted, not "*"
    allow_headers=settings.CORS_ALLOWED_HEADERS,  # Restricted, not "*"
    expose_headers=["X-Total-Count"],  # For pagination
    max_age=600,  # Cache preflight for 10 minutes
)

# Request logging middleware
app.add_middleware(RequestLoggingMiddleware)

# Include API router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health")
async def health_check():
    """Health check endpoint with DB and Redis connectivity."""
    status = {"app": settings.APP_NAME, "status": "healthy"}

    # Check database
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        status["database"] = "ok"
    except Exception:
        status["database"] = "error"
        status["status"] = "degraded"

    # Check Redis
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL, socket_timeout=2)
        await r.ping()
        await r.aclose()
        status["redis"] = "ok"
    except Exception:
        status["redis"] = "error"
        status["status"] = "degraded"

    return status
