import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.errors import DomainError
from app.core.http.cors import is_allowed_origin

logger = logging.getLogger(__name__)

GENERIC_ERROR_DETAIL = "An internal error occurred. Please try again later."


async def _domain_error_response(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, DomainError):
        raise TypeError(f"unexpected exception type {type(exc).__name__}")
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


async def _unhandled_error_response(request: Request, exc: Exception) -> JSONResponse:
    tb = traceback.format_exc()
    logger.error("Unhandled exception: %s: %s", type(exc).__name__, exc)
    logger.error("Traceback:\n%s", tb)
    detail = GENERIC_ERROR_DETAIL
    if not settings.is_production and settings.DEBUG:
        detail = f"{type(exc).__name__}: {exc}\n{tb}"
    origin = request.headers.get("origin", "")
    headers = (
        {"Access-Control-Allow-Origin": origin, "Access-Control-Allow-Credentials": "true"}
        if origin and is_allowed_origin(origin)
        else None
    )
    return JSONResponse(status_code=500, content={"detail": detail}, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    """DomainError en réponse métier, exception non gérée en 500 journalisée, quota en 429."""
    app.add_exception_handler(Exception, _unhandled_error_response)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_exception_handler(DomainError, _domain_error_response)
