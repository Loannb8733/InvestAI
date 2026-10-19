from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.errors import DomainError


async def _domain_error_response(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, DomainError):
        raise TypeError(f"unexpected exception type {type(exc).__name__}")
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


def register_error_handlers(app: FastAPI) -> None:
    """Convertit toute DomainError levée par un service en réponse HTTP."""
    app.add_exception_handler(DomainError, _domain_error_response)
