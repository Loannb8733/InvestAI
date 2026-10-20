from typing import Any

from fastapi import Response

from app.core.config import settings
from app.domains.identity.tokens import TokenPair

ACCESS_COOKIE_PATH = "/api"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _attributes() -> dict[str, Any]:
    """Cookies inter-sites (front Vercel, API Render) : SameSite=None et Secure, sauf en développement local."""
    return {
        "samesite": "none" if settings.COOKIE_SECURE else "lax",
        "secure": settings.COOKIE_SECURE,
        "domain": settings.COOKIE_DOMAIN,
    }


def set_auth_cookies(response: Response, tokens: TokenPair) -> None:
    attributes = _attributes()
    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path=ACCESS_COOKIE_PATH,
        httponly=True,
        **attributes,
    )
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        max_age=tokens.refresh_days * 86400,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        **attributes,
    )


def clear_auth_cookies(response: Response) -> None:
    """Mêmes attributs qu'à la pose, sans quoi le navigateur ignore l'effacement en contexte inter-sites."""
    attributes = _attributes()
    response.delete_cookie("access_token", path=ACCESS_COOKIE_PATH, **attributes)
    response.delete_cookie("refresh_token", path=REFRESH_COOKIE_PATH, **attributes)
