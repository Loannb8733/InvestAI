from typing import ClassVar


class DomainError(Exception):
    """Erreur métier, convertie en réponse HTTP par le gestionnaire central."""

    status_code: ClassVar[int] = 400
    headers: ClassVar[dict[str, str] | None] = None

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    status_code: ClassVar[int] = 404


class UnauthorizedError(DomainError):
    status_code: ClassVar[int] = 401
    headers: ClassVar[dict[str, str] | None] = {"WWW-Authenticate": "Bearer"}


class ForbiddenError(DomainError):
    status_code: ClassVar[int] = 403


class TooManyRequestsError(DomainError):
    status_code: ClassVar[int] = 429


class BadGatewayError(DomainError):
    status_code: ClassVar[int] = 502


class ServiceUnavailableError(DomainError):
    status_code: ClassVar[int] = 503
