from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.domains.identity.dependencies import get_current_user
from app.domains.identity.models import User
from app.domains.notifications.repository import NotificationRepository
from app.domains.notifications.schemas import MessageResponse, NotificationCountResponse, NotificationResponse
from app.domains.notifications.service import NotificationService
from app.domains.notifications.telegram.connection import send_connection_check

router = APIRouter()


def get_notification_service(session: Annotated[AsyncSession, Depends(get_session)]) -> NotificationService:
    return NotificationService(NotificationRepository(session))


Service = Annotated[NotificationService, Depends(get_notification_service)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def current_user_id(user: CurrentUser) -> UUID:
    return cast(UUID, user.id)


UserId = Annotated[UUID, Depends(current_user_id)]


@router.get("")
async def list_notifications(
    user_id: UserId, service: Service, unread_only: bool = False, limit: int = 50, offset: int = 0
) -> list[NotificationResponse]:
    return await service.find(user_id, unread_only, limit, offset)


@router.get("/count")
async def get_unread_count(user_id: UserId, service: Service) -> NotificationCountResponse:
    return await service.unread_count(user_id)


@router.post("/{notification_id}/read")
async def mark_as_read(notification_id: UUID, user_id: UserId, service: Service) -> MessageResponse:
    return await service.mark_read(notification_id, user_id)


@router.post("/read-all")
async def mark_all_as_read(user_id: UserId, service: Service) -> MessageResponse:
    return await service.mark_all_read(user_id)


@router.post("/telegram/test")
async def send_telegram_test(user: CurrentUser) -> MessageResponse:
    return await send_connection_check(user)
