from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from app.core.config import settings

BASELINE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}
HSTS = "max-age=31536000; includeSubDomains"


async def security_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Ajoute les en-têtes de sécurité de base ; HSTS seulement en production."""
    response = await call_next(request)
    for name, value in BASELINE_HEADERS.items():
        response.headers.setdefault(name, value)
    if settings.is_production:
        response.headers.setdefault("Strict-Transport-Security", HSTS)
    return response
