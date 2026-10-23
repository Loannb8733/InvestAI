from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.domains.identity.admin_service import AdminService
from app.domains.identity.dependencies import CurrentAdmin
from app.domains.identity.repository import UserRepository
from app.domains.identity.schemas import UserCreate, UserResponse, UserUpdate

router = APIRouter()


def get_admin_service(session: Annotated[AsyncSession, Depends(get_session)]) -> AdminService:
    return AdminService(UserRepository(session))


Admin = Annotated[AdminService, Depends(get_admin_service)]


@router.get("")
async def list_users(
    admin: CurrentAdmin,
    service: Admin,
    skip: int = 0,
    limit: int = 100,
    active_only: Annotated[bool, Query(description="Inclure uniquement les utilisateurs actifs")] = True,
) -> list[UserResponse]:
    users = await service.list(skip=skip, limit=limit, active_only=active_only)
    return [UserResponse.model_validate(user) for user in users]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(data: UserCreate, admin: CurrentAdmin, service: Admin) -> UserResponse:
    return UserResponse.model_validate(await service.create(data))


@router.get("/{user_id}")
async def get_user(user_id: UUID, admin: CurrentAdmin, service: Admin) -> UserResponse:
    return UserResponse.model_validate(await service.get(user_id))


@router.patch("/{user_id}")
async def update_user(user_id: UUID, data: UserUpdate, admin: CurrentAdmin, service: Admin) -> UserResponse:
    return UserResponse.model_validate(await service.update(user_id, data))


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: UUID, admin: CurrentAdmin, service: Admin) -> None:
    await service.deactivate(user_id, admin)
