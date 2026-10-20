from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.core.errors import ForbiddenError, UnauthorizedError
from app.domains.identity.models import User, UserRole
from app.domains.identity.repository import UserRepository
from app.domains.identity.sessions import authenticate

bearer = HTTPBearer(auto_error=False)


def access_token_of(request: Request, credentials: HTTPAuthorizationCredentials | None) -> str | None:
    """Jeton d'accès de l'en-tête Authorization, sinon du cookie httpOnly."""
    return credentials.credentials if credentials else request.cookies.get("access_token")


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """Utilisateur authentifié par son jeton d'accès ; son identifiant est exposé dans ``request.state.user_id``."""
    token = access_token_of(request, credentials)
    if not token:
        raise UnauthorizedError("Not authenticated")
    user, _ = await authenticate(token, "access", request.headers.get("user-agent", ""), UserRepository(session))
    request.state.user_id = str(user.id)
    return user


async def get_current_admin_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != UserRole.ADMIN:
        raise ForbiddenError("Admin access required")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentAdmin = Annotated[User, Depends(get_current_admin_user)]
