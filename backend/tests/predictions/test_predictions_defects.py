import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.ml import forecaster as forecaster_module
from app.ml.forecaster import PriceForecaster
from app.models.prediction_log import PredictionLog
from tests.predictions.forecaster_double import WEIGHTS
from tests.sample_portfolio import FROZEN_NOW, seed_history, seed_portfolio

pytestmark = pytest.mark.usefixtures("empty_test_redis", "offline", "live_quotes", "deterministic_forecaster")


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(str(user.id))}"}


async def _seed(client: AsyncClient, db: AsyncSession, user: User) -> None:
    await seed_history(db)
    await seed_portfolio(client, _headers(user))


async def test_assets_without_a_name_are_predicted_under_their_symbol(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        await _seed(client, db_session, regular_user)
        response = await client.get("/api/v1/predictions/portfolio", headers=_headers(regular_user))
    assert response.status_code == 200, response.text
    assert all(p["name"] == p["symbol"] for p in response.json()["predictions"])


async def test_each_prediction_is_logged_with_its_model_weights(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        await _seed(client, db_session, regular_user)
        await client.get("/api/v1/predictions/portfolio", headers=_headers(regular_user))
    logs = (await db_session.execute(select(PredictionLog).where(PredictionLog.symbol == "BTC"))).scalars().all()
    assert [log.prediction_data["model_weights"] for log in logs] == [WEIGHTS]


async def test_signal_validation_returns_a_json_response(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    with time_machine.travel(FROZEN_NOW, tick=False):
        await _seed(client, db_session, regular_user)
        response = await client.get("/api/v1/predictions/validate-signal", headers=_headers(regular_user))
    assert response.status_code == 200, response.text
    assert isinstance(response.json()["validated"], bool)


async def test_a_malformed_planned_order_id_is_rejected_as_invalid(client: AsyncClient, regular_user: User) -> None:
    response = await client.patch(
        "/api/v1/predictions/planned-orders/not-a-uuid", json={"status": "executed"}, headers=_headers(regular_user)
    )
    assert response.status_code == 422


def test_a_failing_model_releases_its_compute_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    forecaster = PriceForecaster()

    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("model crashed")

    monkeypatch.setattr(forecaster, "_run_model_by_name", broken)
    with pytest.raises(RuntimeError):
        forecaster._get_or_run_model("Prophet", "BTC", "hash", 7, [1.0, 2.0], [])
    redis = forecaster_module._get_sync_redis()
    assert redis is not None
    assert not redis.exists("computing:BTC:Prophet:hash:7")
