from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def by_email(self, email: str, *, lock: bool = False) -> User | None:
        query = select(User).where(User.email == email)
        if lock:
            query = query.with_for_update()
        return (await self._session.execute(query)).scalar_one_or_none()

    async def by_id(self, user_id: UUID, *, active_only: bool = False) -> User | None:
        query = select(User).where(User.id == user_id)
        if active_only:
            query = query.where(User.is_active.is_(True))
        return (await self._session.execute(query)).scalar_one_or_none()

    async def by_reset_token(self, token: str) -> User | None:
        return (
            await self._session.execute(select(User).where(User.password_reset_token == token))
        ).scalar_one_or_none()

    async def page(self, *, skip: int, limit: int, active_only: bool) -> Sequence[User]:
        query = select(User).order_by(User.created_at.desc()).offset(skip).limit(limit)
        if active_only:
            query = query.where(User.is_active.is_(True))
        return (await self._session.execute(query)).scalars().all()

    async def add(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def save(self, user: User) -> User:
        await self._session.flush()
        await self._session.refresh(user)
        return user
