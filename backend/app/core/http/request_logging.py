import logging
import time
import traceback
import uuid

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import settings

logger = logging.getLogger(__name__)

SLOW_REQUEST_MS = 1000


def _set_sentry_user(request: Request) -> None:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return
    try:
        from app.core.security import decode_access_token

        payload = decode_access_token(auth_header.split(" ")[1])
        if payload:
            import sentry_sdk

            sentry_sdk.set_user({"id": payload.get("sub"), "ip_address": "{{auto}}"})
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to set Sentry user context from token: %s", exc)


def _log_response(request: Request, response: Response, duration_ms: float, trace_id: str) -> None:
    if request.url.path.startswith("/health"):
        return
    log_data = {
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "duration_ms": round(duration_ms, 2),
        "client_ip": request.client.host if request.client else "unknown",
        "trace_id": trace_id,
    }
    if response.status_code >= 500:
        logger.error("Request failed", extra=log_data)
    elif response.status_code >= 400:
        logger.warning("Request error", extra=log_data)
    elif duration_ms > SLOW_REQUEST_MS:
        logger.warning("Slow request", extra=log_data)
    else:
        logger.debug("Request completed", extra=log_data)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Journalise chaque requête avec sa durée et un trace_id renvoyé en X-Request-ID."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        trace_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:16])
        request.state.trace_id = trace_id
        if settings.sentry_enabled:
            _set_sentry_user(request)
        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001
            logger.error("Middleware error: %s: %s", type(exc).__name__, exc)
            logger.error("Traceback:\n%s", traceback.format_exc())
            return JSONResponse(
                status_code=500, content={"detail": "Internal server error"}, headers={"X-Request-ID": trace_id}
            )
        response.headers["X-Request-ID"] = trace_id
        _log_response(request, response, (time.perf_counter() - start) * 1000, trace_id)
        return response
