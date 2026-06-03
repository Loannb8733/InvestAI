"""Unit tests for Binance Funding wallet enrichment of get_balances().

Binance Convert results land in the *Funding* wallet, which is separate from the
Spot wallet read by /api/v3/account. Before this fix, get_balances() ignored the
Funding wallet, so converted holdings looked "missing" and the balance-reconciliation
step (sync_exchanges STEP 2) created phantom TRANSFER_IN/OUT adjustments.

These tests fake the HTTP layer so there is no network I/O: they exercise
``_get_funding_positions`` parsing and the merge logic inside ``get_balances``.
"""

from decimal import Decimal

import pytest

from app.services.exchanges.binance import BinanceService


class _FakeResponse:
    def __init__(self, payload, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    """Async context manager standing in for httpx.AsyncClient."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _make_service():
    svc = BinanceService(api_key="k", secret_key="s")
    # Avoid real network for server-time sync
    svc._sync_server_time = _noop  # type: ignore[assignment]
    svc._get_http_client = lambda timeout=30.0: _FakeClient()  # type: ignore[assignment]
    return svc


async def _noop(*args, **kwargs):
    return None


@pytest.mark.asyncio
async def test_get_funding_positions_sums_all_locked_buckets():
    """free + locked + freeze + withdrawing are all part of the holding."""
    svc = _make_service()

    async def fake_post(client, url, **kwargs):
        return _FakeResponse(
            [
                {"asset": "USDC", "free": "100", "locked": "0", "freeze": "0", "withdrawing": "0"},
                {"asset": "BTC", "free": "0.5", "locked": "0.1", "freeze": "0.2", "withdrawing": "0.2"},
                {"asset": "ETH", "free": "0", "locked": "0", "freeze": "0", "withdrawing": "0"},
            ]
        )

    svc._api_post = fake_post  # type: ignore[assignment]

    funding = await svc._get_funding_positions()

    assert funding["USDC"] == Decimal("100")
    assert funding["BTC"] == Decimal("1.0")  # 0.5 + 0.1 + 0.2 + 0.2
    assert "ETH" not in funding  # zero total skipped


@pytest.mark.asyncio
async def test_get_funding_positions_failsafe_on_http_error():
    """A non-200 funding response must not raise — returns empty dict."""
    svc = _make_service()

    async def fake_post(client, url, **kwargs):
        return _FakeResponse({"code": -1, "msg": "nope"}, status_code=403, text="forbidden")

    svc._api_post = fake_post  # type: ignore[assignment]

    funding = await svc._get_funding_positions()
    assert funding == {}


@pytest.mark.asyncio
async def test_get_balances_merges_funding_into_spot():
    """Funding holdings are added to matching spot balances and create new ones."""
    svc = _make_service()

    # Spot wallet: 1 BTC, 50 USDC
    async def fake_get(client, url, **kwargs):
        return _FakeResponse(
            {
                "balances": [
                    {"asset": "BTC", "free": "1", "locked": "0"},
                    {"asset": "USDC", "free": "50", "locked": "0"},
                ]
            }
        )

    svc._api_get = fake_get  # type: ignore[assignment]
    svc._get_earn_positions = _empty_dict  # type: ignore[assignment]

    # Funding wallet: +0.5 BTC (overlap), +10 SOL (new)
    async def fake_funding():
        return {"BTC": Decimal("0.5"), "SOL": Decimal("10")}

    svc._get_funding_positions = fake_funding  # type: ignore[assignment]

    balances = await svc.get_balances()
    by_symbol = {b.symbol: b for b in balances}

    assert by_symbol["BTC"].total == Decimal("1.5")  # 1 spot + 0.5 funding
    assert by_symbol["USDC"].total == Decimal("50")  # untouched
    assert by_symbol["SOL"].total == Decimal("10")  # funding-only, created
    assert "SOL" in svc._all_account_symbols  # tracked for trade discovery


@pytest.mark.asyncio
async def test_get_balances_failsafe_when_funding_raises():
    """If the funding fetch blows up, spot balances are still returned."""
    svc = _make_service()

    async def fake_get(client, url, **kwargs):
        return _FakeResponse({"balances": [{"asset": "BTC", "free": "2", "locked": "0"}]})

    svc._api_get = fake_get  # type: ignore[assignment]
    svc._get_earn_positions = _empty_dict  # type: ignore[assignment]

    async def boom():
        raise RuntimeError("funding endpoint down")

    svc._get_funding_positions = boom  # type: ignore[assignment]

    balances = await svc.get_balances()
    by_symbol = {b.symbol: b for b in balances}
    assert by_symbol["BTC"].total == Decimal("2")
    assert len(balances) == 1


async def _empty_dict(*args, **kwargs):
    return {}
