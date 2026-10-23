from collections.abc import Sequence
from uuid import UUID

from app.core.errors import DomainError, NotFoundError
from app.domains.identity.models import User
from app.domains.identity.passwords import hash_password
from app.domains.identity.repository import UserRepository
from app.domains.identity.schemas import UserCreate, UserUpdate

USER_NOT_FOUND = "Utilisateur non trouvé"
EMAIL_TAKEN = "Email already registered"


class AdminService:
    """Gestion des comptes réservée aux administrateurs.

    Une suppression désactive le compte ; un mot de passe imposé coupe les sessions ouvertes.
    """

    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def list(self, *, skip: int, limit: int, active_only: bool) -> Sequence[User]:
        return await self._users.page(skip=skip, limit=limit, active_only=active_only)

    async def create(self, data: UserCreate) -> User:
        if await self._users.by_email(data.email) is not None:
            raise DomainError(EMAIL_TAKEN)
        return await self._users.add(
            User(
                email=data.email,
                password_hash=hash_password(data.password),
                role=data.role,
                first_name=data.first_name,
                last_name=data.last_name,
            )
        )

    async def get(self, user_id: UUID) -> User:
        user = await self._users.by_id(user_id, active_only=True)
        if user is None:
            raise NotFoundError(USER_NOT_FOUND)
        return user

    async def update(self, user_id: UUID, data: UserUpdate) -> User:
        user = await self.get(user_id)
        changes = data.model_dump(exclude_unset=True)
        email = changes.get("email")
        if email is not None and email != user.email and await self._users.by_email(email) is not None:
            raise DomainError(EMAIL_TAKEN)
        password = changes.pop("password", None)
        if password is not None:
            user.password_hash = hash_password(password)
            user.token_version += 1
        for field, value in changes.items():
            setattr(user, field, value)
        return await self._users.save(user)

    async def deactivate(self, user_id: UUID, requester: User) -> None:
        if user_id == requester.id:
            raise DomainError("Vous ne pouvez pas supprimer votre propre compte")
        user = await self.get(user_id)
        user.is_active = False
        await self._users.save(user)
