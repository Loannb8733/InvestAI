from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.notifications.models import Notification
from app.domains.portfolio.models import Portfolio

_users = User.__table__
_portfolios = Portfolio.__table__
_RECIPIENT_COLUMNS = (_users.c.id, _users.c.email, _users.c.first_name, _users.c.last_name)


@dataclass(frozen=True)
class Recipient:
    id: UUID
    email: str
    first_name: str | None
    last_name: str | None


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, notification: Notification) -> Notification:
        self._session.add(notification)
        await self._session.flush()
        await self._session.refresh(notification)
        return notification

    async def find(self, user_id: UUID, unread_only: bool, limit: int, offset: int) -> Sequence[Notification]:
        query = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            query = query.where(Notification.is_read.is_(False))
        query = query.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
        return (await self._session.execute(query)).scalars().all()

    async def unread_count(self, user_id: UUID) -> int:
        query = select(func.count(Notification.id)).where(
            Notification.user_id == user_id, Notification.is_read.is_(False)
        )
        return (await self._session.execute(query)).scalar() or 0

    async def mark_read(self, notification_id: UUID, user_id: UUID) -> int:
        statement = (
            update(Notification)
            .where(Notification.id == notification_id, Notification.user_id == user_id)
            .values(is_read=True)
        )
        return int(getattr(await self._session.execute(statement), "rowcount", 0) or 0)

    async def mark_all_read(self, user_id: UUID) -> int:
        statement = (
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
            .values(is_read=True)
        )
        return int(getattr(await self._session.execute(statement), "rowcount", 0) or 0)

    async def _recipients(self, query: Select[Any]) -> list[Recipient]:
        rows = (await self._session.execute(query)).all()
        return [Recipient(row.id, row.email, row.first_name, row.last_name) for row in rows]

    async def recipient(self, user_id: UUID) -> Recipient | None:
        found = await self._recipients(select(*_RECIPIENT_COLUMNS).where(_users.c.id == user_id))
        return found[0] if found else None

    async def portfolio_owners(self) -> list[Recipient]:
        owners = select(_portfolios.c.user_id).distinct()
        return await self._recipients(select(*_RECIPIENT_COLUMNS).where(_users.c.id.in_(owners)))

    async def notified_since(self, since: datetime) -> list[Recipient]:
        notified = select(Notification.user_id).where(Notification.created_at >= since).distinct()
        return await self._recipients(select(*_RECIPIENT_COLUMNS).where(_users.c.id.in_(notified)))

    async def received_since(self, user_id: UUID, since: datetime) -> Sequence[Notification]:
        query = (
            select(Notification)
            .where(Notification.user_id == user_id, Notification.created_at >= since)
            .order_by(Notification.created_at.desc())
        )
        return (await self._session.execute(query)).scalars().all()
