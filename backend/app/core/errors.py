from typing import ClassVar


class DomainError(Exception):
    """Erreur métier, convertie en réponse HTTP par le gestionnaire central."""

    status_code: ClassVar[int] = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    status_code: ClassVar[int] = 404
