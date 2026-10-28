import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
import time_machine
from celery.schedules import crontab, maybe_schedule
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ServiceUnavailableError
from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.market_data.prices.quote import PriceQuote
from app.domains.market_data.prices.service import price_feed
from app.domains.portfolio.models import Asset, AssetType, Portfolio
from app.domains.predictions import tasks as prediction_tasks
from app.domains.predictions.models import PredictionLog
from app.domains.system import price_socket, router
from app.domains.system.jobs import JOBS
from app.domains.system.scheduler import Entry, Scheduler
from app.tasks import contrarian_stats
from app.tasks.celery_app import celery_app
from tests.conftest import TestSessionLocal
from tests.sample_portfolio import FROZEN_NOW

pytestmark = pytest.mark.usefixtures("empty_test_redis")
SECRET = "jeton-des-defauts"
FIVE_MINUTES = maybe_schedule(300.0, app=celery_app)


def _entry(name: str, job: Any, task: str = "app.tasks.demo.job", schedule: Any = FIVE_MINUTES) -> Entry:
    return Entry(name, task, schedule, job)


async def _ok() -> dict[str, str]:
    return {"status": "ok"}


async def _boom() -> None:
    raise RuntimeError("API en panne")


def test_every_scheduled_celery_task_has_a_job_in_the_api() -> None:
    assert set(JOBS) == {config["task"] for config in celery_app.conf.beat_schedule.values()}


async def test_due_tasks_follow_their_celery_schedule() -> None:
    nightly = maybe_schedule(crontab(hour=0, minute=0), app=celery_app)
    scheduler = Scheduler({name: _entry(name, _ok) for name in ("late", "recent", "running")})
    scheduler.entries["nightly"] = _entry("nightly", _ok, schedule=nightly)
    with time_machine.travel(FROZEN_NOW, tick=False):
        now = datetime.now(UTC)
        scheduler.state("late").last_run_at = now - timedelta(minutes=6)
        scheduler.state("recent").last_run_at = now - timedelta(minutes=2)
        scheduler.state("running").last_run_at = now - timedelta(minutes=6)
        scheduler.state("running").running = True
        scheduler.state("nightly").last_run_at = now - timedelta(hours=1)
        assert scheduler.due() == ["late"]


async def test_runs_are_recorded_and_survive_a_restart() -> None:
    entries = {"good": _entry("good", _ok), "bad": _entry("bad", _boom), "new": _entry("new", _ok)}
    with time_machine.travel(FROZEN_NOW, tick=False):
        first = Scheduler(entries)
        good, bad = await first.run("good"), await first.run("bad")
        restarted = Scheduler(entries)
        await restarted.load()
    assert (good.failed, bad.failed, bad.last_error) == (False, True, "RuntimeError: API en panne")
    assert restarted.state("good").last_success_at == FROZEN_NOW
    assert restarted.state("bad").last_error_at == FROZEN_NOW
    assert restarted.state("new").last_run_at == FROZEN_NOW


async def test_prediction_tasks_never_run_together() -> None:
    running, peak = 0, 0

    async def predict() -> None:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.05)
        running -= 1

    heavy = "app.domains.predictions.tasks."
    scheduler = Scheduler(
        {
            "tune": _entry("tune", predict, heavy + "tune_hyperparameters"),
            "daily": _entry("daily", predict, heavy + "run_daily_predictions"),
            "alerts": _entry("alerts", predict, "app.domains.alerts.tasks.check_all_alerts"),
        }
    )
    await asyncio.gather(scheduler.run("tune"), scheduler.run("daily"))
    heavy_peak, peak = peak, 0
    await asyncio.gather(scheduler.run("tune"), scheduler.run("alerts"))
    assert (heavy_peak, peak) == (1, 2)


@pytest.fixture
def cron_jobs(monkeypatch: pytest.MonkeyPatch) -> Scheduler:
    monkeypatch.setattr(settings, "CRON_SECRET", SECRET)
    monkeypatch.setattr(settings, "CELERY_WORKER_AVAILABLE", False)
    scheduler = Scheduler({"good": _entry("good", _ok), "bad": _entry("bad", _boom)})
    monkeypatch.setattr(router, "api_scheduler", scheduler)
    return scheduler


@pytest.mark.usefixtures("cron_jobs")
async def test_a_task_can_be_run_by_hand_and_its_failure_is_an_error(client: AsyncClient) -> None:
    token = {"X-Cron-Token": SECRET}
    good = await client.post("/api/v1/cron/jobs/good", headers=token)
    bad = await client.post("/api/v1/cron/jobs/bad", headers=token)
    unknown = await client.post("/api/v1/cron/jobs/nope", headers=token)
    assert (good.status_code, good.json()["last_error"], good.json()["last_result"]) == (200, None, '{"status": "ok"}')
    assert (bad.status_code, bad.json()["detail"]) == (502, "bad : RuntimeError: API en panne")
    assert unknown.status_code == 404


async def test_status_reports_each_scheduled_task(client: AsyncClient, admin_user: User, cron_jobs: Scheduler) -> None:
    headers = {"Authorization": f"Bearer {create_token(str(admin_user.id))}"}
    await client.post("/api/v1/cron/jobs/bad", headers={"X-Cron-Token": SECRET})
    status = (await client.get("/api/v1/system/status", headers=headers)).json()
    tasks = {task["name"]: task for task in status["tasks"]}
    assert (status["scheduler"], sorted(tasks)) == ("api", ["bad", "good"])
    assert (tasks["bad"]["last_error"], tasks["good"]["last_run_at"]) == ("RuntimeError: API en panne", None)


async def test_prediction_accuracy_is_checked(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    db_session.add(
        PredictionLog(
            symbol="BTC",
            asset_type="crypto",
            model_name="ensemble",
            predicted_price=110.0,
            price_at_creation=Decimal("100"),
            target_date=datetime(2026, 10, 10),
            horizon_days=7,
        )
    )
    await db_session.commit()

    async def quote(symbol: str, asset_type: str, currency: str = "EUR") -> PriceQuote:
        return PriceQuote(price=Decimal("100"))

    monkeypatch.setattr(price_feed, "quote", quote)
    monkeypatch.setattr(prediction_tasks, "session_factory", TestSessionLocal)
    with time_machine.travel(FROZEN_NOW, tick=False):
        await prediction_tasks._check_prediction_accuracy()
    log = (await db_session.execute(select(PredictionLog).execution_options(populate_existing=True))).scalar_one()
    assert (log.accuracy_checked, round(log.mape or 0, 2)) == (FROZEN_NOW.replace(tzinfo=None), 10.0)


@pytest.mark.usefixtures("offline")
def test_contrarian_refresh_failure_is_raised() -> None:
    with pytest.raises(ServiceUnavailableError, match="Statistiques contrarian non rafraîchies"):
        contrarian_stats.refresh_contrarian_stats()


async def test_binance_follows_held_crypto_only_and_shrinks(
    db_session: AsyncSession, regular_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    portfolio = Portfolio(user_id=regular_user.id, name="P")
    db_session.add(portfolio)
    await db_session.flush()
    for symbol, kind in (("BTC", AssetType.CRYPTO), ("eth", AssetType.CRYPTO), ("AAPL", AssetType.STOCK)):
        db_session.add(Asset(portfolio_id=portfolio.id, symbol=symbol, name=symbol, asset_type=kind, quantity=1))
    await db_session.commit()
    monkeypatch.setattr(price_socket, "session_factory", TestSessionLocal)
    streamed: list[list[str]] = []

    async def binance(symbols: set[str]) -> None:
        streamed.append(sorted(symbols))
        await asyncio.sleep(3600)

    monkeypatch.setattr(price_socket, "binance_prices", binance)
    hub = price_socket.PriceHub()
    held = await price_socket.crypto_symbols({"BTC", "ETH", "AAPL", "XYZ"})
    for symbols in (held, {"BTC"}, set()):
        await hub.stream(symbols)
        await asyncio.sleep(0)
    assert (held, streamed) == ({"BTC", "ETH"}, [["BTC", "ETH"], ["BTC"]])
