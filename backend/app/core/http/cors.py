from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

PROD_FRONTEND_ORIGINS = ("https://investai-orcin.vercel.app",)
VERCEL_SUFFIX = ".vercel.app"


def is_allowed_origin(origin: str) -> bool:
    """Origine explicitement autorisée, ou aperçu Vercel hors production."""
    if origin in settings.CORS_ORIGINS or origin in PROD_FRONTEND_ORIGINS:
        return True
    return not settings.is_production and origin.startswith("https://") and origin.endswith(VERCEL_SUFFIX)


def _origin_regex() -> str:
    origins = list(dict.fromkeys([*settings.CORS_ORIGINS, *PROD_FRONTEND_ORIGINS]))
    parts = [origin.replace(".", r"\.") for origin in origins]
    if not settings.is_production:
        parts.append(r"https://.*\.vercel\.app")
    return f"^({'|'.join(parts)})$"


def add_cors_middleware(app: FastAPI) -> None:
    """Ajoute CORS avec méthodes et en-têtes restreints."""
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=_origin_regex(),
        allow_credentials=True,
        allow_methods=settings.CORS_ALLOWED_METHODS,
        allow_headers=settings.CORS_ALLOWED_HEADERS,
        expose_headers=["X-Total-Count", "X-Request-ID"],
        max_age=600,
    )
