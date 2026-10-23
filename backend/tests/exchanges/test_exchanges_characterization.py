import asyncio
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_api_key
from app.domains.exchanges.models import APIKey
from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.portfolio.models import Asset
from app.services.exchanges.base import ExchangeBalance

pytestmark = pytest.mark.usefixtures("empty_test_redis")
KEYS = "/api/v1/api-keys"
WALLETS = "/api/v1/cold-wallets"


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(str(user.id))}"}


class FakeExchange:
    exchange_name = "kraken"

    def __init__(self, connected: bool = True, balances: list[ExchangeBalance] | None = None) -> None:
        self.connected = connected
        self.balances = balances or []

    async def test_connection(self) -> bool:
        return self.connected

    async def get_balances(self) -> list[ExchangeBalance]:
        return self.balances

    async def connection_error(self) -> str | None:
        return None


def _balance(symbol: str, total: str) -> ExchangeBalance:
    amount = Decimal(total)
    return ExchangeBalance(symbol=symbol, free=amount, locked=Decimal("0"), total=amount)


@pytest.fixture
def exchange(monkeypatch: pytest.MonkeyPatch) -> FakeExchange:
    fake = FakeExchange()
    monkeypatch.setattr("app.domains.exchanges.service.construire_service_exchange", lambda key: fake)
    return fake


async def _key(client: AsyncClient, user: User, **fields: Any) -> dict[str, Any]:
    body = {"exchange": "Kraken", "label": "K", "api_key": "pub", "secret_key": "sec", **fields}
    response = await client.post(KEYS, json=body, headers=_bearer(user))
    assert response.status_code == 201, response.text
    return dict(response.json())


class TestKeys:
    async def test_exchanges_are_listed(self, client: AsyncClient) -> None:
        ids = [e["id"] for e in (await client.get(f"{KEYS}/exchanges")).json()]
        assert {"binance", "kraken", "okx"} <= set(ids)

    async def test_secrets_are_encrypted_and_never_returned(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        created = await _key(client, regular_user, passphrase="pp")
        assert created["exchange"] == "kraken"
        assert not {"api_key", "secret_key", "passphrase", "encrypted_api_key"} & set(created)
        row = (await db_session.execute(select(APIKey))).scalar_one()
        assert (decrypt_api_key(row.encrypted_api_key), decrypt_api_key(row.encrypted_secret_key)) == ("pub", "sec")
        assert decrypt_api_key(row.encrypted_passphrase) == "pp"

    async def test_unsupported_exchange_is_refused(self, client: AsyncClient, regular_user: User) -> None:
        response = await client.post(KEYS, json={"exchange": "nope", "api_key": "x"}, headers=_bearer(regular_user))
        assert response.status_code == 400

    async def test_update_rotates_only_the_given_secrets(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User
    ) -> None:
        created = await _key(client, regular_user)
        body = {"label": "New", "secret_key": "sec2", "is_active": False}
        updated = (await client.patch(f"{KEYS}/{created['id']}", json=body, headers=_bearer(regular_user))).json()
        assert (updated["label"], updated["is_active"]) == ("New", False)
        row = (await db_session.execute(select(APIKey))).scalar_one()
        await db_session.refresh(row)
        assert (decrypt_api_key(row.encrypted_api_key), decrypt_api_key(row.encrypted_secret_key)) == ("pub", "sec2")

    async def test_keys_are_private(self, client: AsyncClient, regular_user: User, admin_user: User) -> None:
        created = await _key(client, regular_user)
        other = _bearer(admin_user)
        assert (await client.get(KEYS, headers=other)).json() == []
        for method in ("get", "delete"):
            response = await client.request(method.upper(), f"{KEYS}/{created['id']}", headers=other)
            assert response.status_code == 404
        assert (await client.delete(f"{KEYS}/{created['id']}", headers=_bearer(regular_user))).status_code == 204
        assert (await client.get(KEYS, headers=_bearer(regular_user))).json() == []


class TestConnection:
    async def test_success_shows_balances_and_clears_the_error(
        self, client: AsyncClient, regular_user: User, exchange: FakeExchange
    ) -> None:
        exchange.balances = [_balance("BTC", "0.5")]
        created = await _key(client, regular_user)
        body = (await client.post(f"{KEYS}/{created['id']}/test", headers=_bearer(regular_user))).json()
        assert body == {"success": True, "message": "Connexion réussie", "balance": {"BTC": 0.5}}
        listed = (await client.get(f"{KEYS}/{created['id']}", headers=_bearer(regular_user))).json()
        assert listed["last_sync_at"] is not None and listed["last_error"] is None

    async def test_failure_is_recorded(self, client: AsyncClient, regular_user: User, exchange: FakeExchange) -> None:
        exchange.connected = False
        created = await _key(client, regular_user)
        body = (await client.post(f"{KEYS}/{created['id']}/test", headers=_bearer(regular_user))).json()
        assert body["success"] is False and body["message"].startswith("Échec de la connexion")
        listed = (await client.get(f"{KEYS}/{created['id']}", headers=_bearer(regular_user))).json()
        assert listed["last_error"]


class TestBalanceSync:
    async def test_balances_become_assets_and_fiat_is_skipped(
        self, client: AsyncClient, db_session: AsyncSession, regular_user: User, exchange: FakeExchange
    ) -> None:
        exchange.balances = [_balance("BTC", "0.5"), _balance("LDBTC", "0.25"), _balance("EUR", "100")]
        created = await _key(client, regular_user)
        body = (await client.post(f"{KEYS}/{created['id']}/sync", headers=_bearer(regular_user))).json()
        assert (body["message"], body["synced_assets"]) == ("Synchronisation réussie", 1)
        assets = (await db_session.execute(select(Asset.symbol, Asset.quantity, Asset.exchange))).all()
        assert [(s, q, e) for s, q, e in assets] == [("BTC", Decimal("0.75"), "kraken")]

    async def test_nothing_on_the_exchange(
        self, client: AsyncClient, regular_user: User, exchange: FakeExchange
    ) -> None:
        created = await _key(client, regular_user)
        body = (await client.post(f"{KEYS}/{created['id']}/sync", headers=_bearer(regular_user))).json()
        assert (body["message"], body["synced_assets"]) == ("Aucun solde trouvé sur l'exchange", 0)


class TestBackgroundImport:
    @pytest.mark.parametrize(
        ("route", "message"), [("import-async", "Import réussi"), ("refresh-fx", "Recalcul FX terminé")]
    )
    async def test_the_owner_reads_the_final_status(
        self,
        client: AsyncClient,
        regular_user: User,
        admin_user: User,
        monkeypatch: pytest.MonkeyPatch,
        route: str,
        message: str,
    ) -> None:
        async def sync(api_key_id: str, heal_fx: bool = False) -> dict[str, Any]:
            return {"success": True, "synced": 3}

        monkeypatch.setattr("app.tasks.sync_exchanges._sync_single_exchange", sync)
        created = await _key(client, regular_user)
        task = (await client.post(f"{KEYS}/{created['id']}/{route}", headers=_bearer(regular_user))).json()
        assert task["status"] == "dispatched"
        url = f"{KEYS}/import-status/{task['task_id']}"
        await asyncio.sleep(0.05)
        body = (await client.get(url, headers=_bearer(regular_user))).json()
        assert {k: body[k] for k in ("status", "synced", "message")} == {
            "status": "completed",
            "synced": 3,
            "message": message,
        }
        assert (await client.get(url, headers=_bearer(admin_user))).status_code == 404

    async def test_a_failure_shows_a_generic_message(
        self, client: AsyncClient, regular_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def sync(api_key_id: str, heal_fx: bool = False) -> dict[str, Any]:
            raise RuntimeError("secret internal path /app/x")

        monkeypatch.setattr("app.tasks.sync_exchanges._sync_single_exchange", sync)
        created = await _key(client, regular_user)
        task = (await client.post(f"{KEYS}/{created['id']}/import-async", headers=_bearer(regular_user))).json()
        await asyncio.sleep(0.05)
        body = (await client.get(f"{KEYS}/import-status/{task['task_id']}", headers=_bearer(regular_user))).json()
        assert body["status"] == "failed" and "secret" not in body["error"]


class TestColdWallets:
    async def test_upsert_by_address_and_privacy(
        self, client: AsyncClient, regular_user: User, admin_user: User
    ) -> None:
        headers = _bearer(regular_user)
        first = (await client.post(WALLETS, json={"address": " 0xabc ", "label": " Ledger "}, headers=headers)).json()
        assert (first["address"], first["label"]) == ("0xabc", "Ledger")
        renamed = (await client.post(WALLETS, json={"address": "0xabc", "label": "Tangem"}, headers=headers)).json()
        assert (renamed["id"], renamed["label"]) == (first["id"], "Tangem")
        assert [w["label"] for w in (await client.get(WALLETS, headers=headers)).json()] == ["Tangem"]
        assert (await client.get(WALLETS, headers=_bearer(admin_user))).json() == []
        assert (await client.delete(f"{WALLETS}/{first['id']}", headers=_bearer(admin_user))).status_code == 404
        assert (await client.delete(f"{WALLETS}/{first['id']}", headers=headers)).status_code == 204
        blank = await client.post(WALLETS, json={"address": "    ", "label": "x"}, headers=headers)
        assert blank.status_code == 422
