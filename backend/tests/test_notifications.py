"""Notification endpoint tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.notification import Notification, NotificationPriority, NotificationType
from app.models.user import User


async def _create_notification(
    db: AsyncSession, user_id, title: str = "Test Alert"
) -> Notification:
    """Helper to create a notification."""
    notification = Notification(
        user_id=user_id,
        type=NotificationType.ALERT_TRIGGERED,
        title=title,
        message="Test notification message",
        priority=NotificationPriority.NORMAL,
        is_read=False,
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    return notification


@pytest.mark.asyncio
async def test_list_notifications(
    client: AsyncClient, regular_user: User, db_session: AsyncSession
):
    """Test listing notifications."""
    token = create_access_token(subject=str(regular_user.id))
    headers = {"Authorization": f"Bearer {token}"}

    await _create_notification(db_session, regular_user.id, "Alert 1")
    await _create_notification(db_session, regular_user.id, "Alert 2")

    response = await client.get("/api/v1/notifications/", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_list_unread_only(
    client: AsyncClient, regular_user: User, db_session: AsyncSession
):
    """Test listing only unread notifications."""
    token = create_access_token(subject=str(regular_user.id))
    headers = {"Authorization": f"Bearer {token}"}

    n1 = await _create_notification(db_session, regular_user.id, "Unread")
    n2 = await _create_notification(db_session, regular_user.id, "Read")
    n2.is_read = True
    await db_session.commit()

    response = await client.get(
        "/api/v1/notifications/?unread_only=true", headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "Unread"


@pytest.mark.asyncio
async def test_unread_count(
    client: AsyncClient, regular_user: User, db_session: AsyncSession
):
    """Test getting unread notification count."""
    token = create_access_token(subject=str(regular_user.id))
    headers = {"Authorization": f"Bearer {token}"}

    await _create_notification(db_session, regular_user.id)
    await _create_notification(db_session, regular_user.id)

    response = await client.get("/api/v1/notifications/count", headers=headers)
    assert response.status_code == 200
    assert response.json()["unread_count"] == 2


@pytest.mark.asyncio
async def test_mark_as_read(
    client: AsyncClient, regular_user: User, db_session: AsyncSession
):
    """Test marking a notification as read."""
    token = create_access_token(subject=str(regular_user.id))
    headers = {"Authorization": f"Bearer {token}"}

    notification = await _create_notification(db_session, regular_user.id)

    response = await client.post(
        f"/api/v1/notifications/{notification.id}/read",
        headers=headers,
    )
    assert response.status_code == 200

    # Count should be 0 now
    count_resp = await client.get("/api/v1/notifications/count", headers=headers)
    assert count_resp.json()["unread_count"] == 0


@pytest.mark.asyncio
async def test_mark_all_as_read(
    client: AsyncClient, regular_user: User, db_session: AsyncSession
):
    """Test marking all notifications as read."""
    token = create_access_token(subject=str(regular_user.id))
    headers = {"Authorization": f"Bearer {token}"}

    await _create_notification(db_session, regular_user.id)
    await _create_notification(db_session, regular_user.id)
    await _create_notification(db_session, regular_user.id)

    response = await client.post("/api/v1/notifications/read-all", headers=headers)
    assert response.status_code == 200

    count_resp = await client.get("/api/v1/notifications/count", headers=headers)
    assert count_resp.json()["unread_count"] == 0


@pytest.mark.asyncio
async def test_mark_nonexistent_notification(
    client: AsyncClient, regular_user: User
):
    """Test marking a nonexistent notification as read."""
    token = create_access_token(subject=str(regular_user.id))
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.post(
        "/api/v1/notifications/00000000-0000-0000-0000-000000000000/read",
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_notifications_no_auth(client: AsyncClient):
    """Test accessing notifications without auth."""
    response = await client.get("/api/v1/notifications/")
    assert response.status_code in (401, 403)
