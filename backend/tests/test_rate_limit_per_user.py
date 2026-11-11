import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token

ROUTE = "/api/v1/crowdfunding/sync-calendar"


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(str(user.id))}"}


@pytest.fixture
async def other_user(db_session: AsyncSession) -> User:
    user = User(email="autre@test.com", password_hash="x")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_users_behind_one_proxy_have_their_own_limit(
    client: AsyncClient, regular_user: User, other_user: User
) -> None:
    """Derrière Vercel, toutes les requêtes arrivent de la même adresse : la limite doit suivre l'utilisateur."""
    statuses = [(await client.post(ROUTE, headers=_headers(regular_user))).status_code for _ in range(6)]
    assert statuses[-1] == 429
    assert (await client.post(ROUTE, headers=_headers(other_user))).status_code == 200
