import json

import pyotp
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import _get_redis_txt
from app.domains.identity.models import User
from app.domains.identity.tokens import create_token

pytestmark = pytest.mark.usefixtures("empty_test_redis")

USER = {"email": "user@test.com", "password": "userpassword"}


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(str(user.id), token_version=user.token_version)}"}


async def _login(client: AsyncClient, **extra: object) -> tuple[int, dict[str, object]]:
    response = await client.post("/api/v1/auth/login", json={**USER, **extra})
    return response.status_code, response.json()


class TestRegister:
    async def test_new_account_can_log_in(self, client: AsyncClient) -> None:
        body = {"email": "new@test.com", "password": "Motdepasse1", "first_name": "N"}
        response = await client.post("/api/v1/auth/register", json=body)
        assert response.status_code == 201
        login = await client.post("/api/v1/auth/login", json={"email": "new@test.com", "password": "Motdepasse1"})
        assert login.status_code == 200

    async def test_taken_address_gets_the_same_answer(self, client: AsyncClient, regular_user: User) -> None:
        fresh = await client.post("/api/v1/auth/register", json={"email": "x@test.com", "password": "Motdepasse1"})
        taken = await client.post("/api/v1/auth/register", json={"email": "user@test.com", "password": "Motdepasse1"})
        assert (taken.status_code, taken.json()) == (fresh.status_code, fresh.json())

    async def test_weak_password_is_rejected(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/auth/register", json={"email": "w@test.com", "password": "motdepasse"})
        assert response.status_code == 422


class TestLogin:
    async def test_cookies_are_set_and_remember_me_lasts_30_days(self, client: AsyncClient, regular_user: User) -> None:
        response = await client.post("/api/v1/auth/login", json={**USER, "remember_me": True})
        cookies = response.headers.get_list("set-cookie")
        assert any(c.startswith("access_token=") and "HttpOnly" in c for c in cookies)
        assert any(c.startswith("refresh_token=") and f"Max-Age={30 * 86400}" in c for c in cookies)

    async def test_inactive_account_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        regular_user.is_active = False
        await db_session.commit()
        assert (await _login(client))[0] == 401

    async def test_ten_failures_lock_the_account(self, client: AsyncClient, regular_user: User) -> None:
        await (await _get_redis_txt()).set(f"login_fail:{regular_user.id}", 10)
        assert (await _login(client))[0] == 429

    async def test_a_failure_is_counted_and_a_success_clears_it(self, client: AsyncClient, regular_user: User) -> None:
        redis = await _get_redis_txt()
        await client.post("/api/v1/auth/login", json={**USER, "password": "wrong"})
        assert await redis.get(f"login_fail:{regular_user.id}") == "1"
        assert (await _login(client))[0] == 200
        assert await redis.get(f"login_fail:{regular_user.id}") is None


class TestMfa:
    async def _enroll(self, client: AsyncClient, user: User) -> tuple[str, list[str]]:
        setup = (await client.post("/api/v1/auth/mfa/setup", headers=_bearer(user))).json()
        code = pyotp.TOTP(setup["secret"]).now()
        assert (
            await client.post("/api/v1/auth/mfa/verify", json={"code": code}, headers=_bearer(user))
        ).status_code == 200
        return setup["secret"], setup["backup_codes"]

    async def test_setup_stores_an_encrypted_secret_and_hashed_backup_codes(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        setup = (await client.post("/api/v1/auth/mfa/setup", headers=_bearer(regular_user))).json()
        assert setup["qr_code"].startswith("data:image/png;base64,")
        assert len(setup["backup_codes"]) == 10
        await db_session.refresh(regular_user)
        assert regular_user.mfa_secret != setup["secret"]
        assert not regular_user.mfa_enabled
        assert setup["backup_codes"][0] not in json.loads(regular_user.mfa_backup_codes)

    async def test_login_requires_a_valid_code_used_once(self, client: AsyncClient, regular_user: User) -> None:
        secret, _ = await self._enroll(client, regular_user)
        assert (await _login(client))[0] == 400
        assert (await _login(client, mfa_code="000000"))[0] == 401
        code = pyotp.TOTP(secret).now()
        assert (await _login(client, mfa_code=code))[0] == 200
        assert (await _login(client, mfa_code=code))[0] == 401

    async def test_a_backup_code_works_once(self, client: AsyncClient, regular_user: User) -> None:
        _, backups = await self._enroll(client, regular_user)
        assert (await _login(client, mfa_code=backups[0]))[0] == 200
        assert (await _login(client, mfa_code=backups[0]))[0] == 401

    async def test_disable_needs_a_valid_code(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        secret, _ = await self._enroll(client, regular_user)
        headers = _bearer(regular_user)
        assert (
            await client.post("/api/v1/auth/mfa/disable", json={"code": "000000"}, headers=headers)
        ).status_code == 400
        code = pyotp.TOTP(secret).now()
        assert (await client.post("/api/v1/auth/mfa/disable", json={"code": code}, headers=headers)).status_code == 200
        await db_session.refresh(regular_user)
        assert (regular_user.mfa_enabled, regular_user.mfa_secret, regular_user.mfa_backup_codes) == (False, None, None)


class TestRefresh:
    async def test_cookie_refresh_rotates_tokens(self, client: AsyncClient, regular_user: User) -> None:
        await client.post("/api/v1/auth/login", json=USER)
        response = await client.post("/api/v1/auth/refresh")
        assert response.status_code == 200
        assert response.json()["refresh_token"]

    async def test_a_refresh_token_revoked_at_logout_is_refused(self, client: AsyncClient, regular_user: User) -> None:
        refresh = (await client.post("/api/v1/auth/login", json=USER)).json()["refresh_token"]
        await client.post("/api/v1/auth/logout")
        response = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        assert response.status_code == 401

    async def test_another_user_agent_is_refused(self, client: AsyncClient, regular_user: User) -> None:
        refresh = (await client.post("/api/v1/auth/login", json=USER)).json()["refresh_token"]
        response = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh}, headers={"user-agent": "other"}
        )
        assert response.status_code == 401

    async def test_an_access_token_is_not_a_refresh_token(self, client: AsyncClient, regular_user: User) -> None:
        access = (await client.post("/api/v1/auth/login", json=USER)).json()["access_token"]
        assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": access})).status_code == 401


class TestProfile:
    async def test_me_returns_the_profile(self, client: AsyncClient, regular_user: User) -> None:
        body = (await client.get("/api/v1/auth/me", headers=_bearer(regular_user))).json()
        assert {k: body[k] for k in ("email", "role", "preferred_currency", "mfa_enabled", "tmi_rate")} == {
            "email": "user@test.com",
            "role": "user",
            "preferred_currency": "EUR",
            "mfa_enabled": False,
            "tmi_rate": None,
        }

    async def test_patch_rounds_amounts_and_saves_telegram_settings(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        payload = {
            "tmi_rate": 0.30000000000000004,
            "monthly_dca_eur": 150.456,
            "telegram_chat_id": "42",
            "telegram_enabled": True,
        }
        body = (await client.patch("/api/v1/auth/me", json=payload, headers=_bearer(regular_user))).json()
        assert (body["tmi_rate"], body["monthly_dca_eur"]) == (0.3, 150.46)
        assert (body["telegram_chat_id"], body["telegram_enabled"]) == ("42", True)

    @pytest.mark.parametrize(
        "payload",
        [{"tmi_rate": 0.2}, {"preferred_currency": "JPY"}, {"monthly_dca_eur": -1}, {"telegram_chat_id": "abc"}],
    )
    async def test_invalid_values_are_rejected(
        self, client: AsyncClient, regular_user: User, payload: dict[str, object]
    ) -> None:
        assert (await client.patch("/api/v1/auth/me", json=payload, headers=_bearer(regular_user))).status_code == 422


class TestAdminUsers:
    async def test_regular_users_are_forbidden(self, client: AsyncClient, regular_user: User) -> None:
        assert (await client.get("/api/v1/users", headers=_bearer(regular_user))).status_code == 403

    async def test_create_list_update_and_soft_delete(
        self, client: AsyncClient, db_session: AsyncSession, admin_user: User
    ) -> None:
        headers = _bearer(admin_user)
        created = await client.post(
            "/api/v1/users", json={"email": "c@test.com", "password": "Motdepasse1", "role": "user"}, headers=headers
        )
        assert created.status_code == 201
        user_id = created.json()["id"]
        duplicate = await client.post(
            "/api/v1/users", json={"email": "c@test.com", "password": "Motdepasse1"}, headers=headers
        )
        assert duplicate.status_code == 400
        updated = await client.patch(f"/api/v1/users/{user_id}", json={"first_name": "C"}, headers=headers)
        assert updated.json()["first_name"] == "C"
        assert (await client.delete(f"/api/v1/users/{user_id}", headers=headers)).status_code == 204
        assert (await client.get(f"/api/v1/users/{user_id}", headers=headers)).status_code == 404
        emails = [u["email"] for u in (await client.get("/api/v1/users", headers=headers)).json()]
        assert "c@test.com" not in emails
        row = (await db_session.execute(select(User).where(User.email == "c@test.com"))).scalar_one()
        assert row.is_active is False

    async def test_an_admin_cannot_delete_themself(self, client: AsyncClient, admin_user: User) -> None:
        response = await client.delete(f"/api/v1/users/{admin_user.id}", headers=_bearer(admin_user))
        assert response.status_code == 400
