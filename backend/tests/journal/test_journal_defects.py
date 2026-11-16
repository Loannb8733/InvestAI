from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.journal.models import Note


async def test_une_modification_peut_vider_le_sentiment_le_contenu_et_les_tags(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    note = Note(user_id=regular_user.id, title="Avant", content="c", tags="t", sentiment="bullish")
    db_session.add(note)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}

    response = await client.patch(
        f"/api/v1/notes/{note.id}",
        json={"title": None, "content": None, "tags": None, "sentiment": None},
        headers=headers,
    )

    body = response.json()
    assert response.status_code == 200
    assert (body["title"], body["content"], body["tags"], body["sentiment"]) == ("Avant", None, None, None)
