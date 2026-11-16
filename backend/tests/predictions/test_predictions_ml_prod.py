"""Suivi de précision et tâches de prédiction corrigés pour la production (lot 1 du projet d'études)."""

import threading
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
import time_machine
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.identity.models import User
from app.domains.identity.tokens import create_token
from app.domains.market_data.history.models import AssetPriceHistory
from app.domains.market_data.history.series import PriceSeries
from app.domains.market_data.prices.quote import PriceQuote
from app.domains.market_data.prices.service import price_feed
from app.domains.portfolio.models import AssetType
from app.domains.predictions import tasks as prediction_tasks
from app.domains.predictions.models import PredictionLog
from tests.conftest import TestSessionLocal
from tests.sample_portfolio import FROZEN_NOW

NOW = FROZEN_NOW.replace(tzinfo=None)


def _log(target: datetime, **checked: Any) -> PredictionLog:
    return PredictionLog(
        symbol="BTC",
        asset_type="crypto",
        model_name="ensemble",
        prediction_data={},
        predicted_price=110.0,
        price_at_creation=Decimal("100"),
        target_date=target,
        horizon_days=7,
        confidence_low=90.0,
        confidence_high=130.0,
        **checked,
    )


async def _checked_log(db_session: AsyncSession) -> PredictionLog:
    statement = select(PredictionLog).execution_options(populate_existing=True)
    return (await db_session.execute(statement)).scalar_one()


async def _run_accuracy_check(monkeypatch: pytest.MonkeyPatch) -> None:
    async def quote(symbol: str, asset_type: str, currency: str = "EUR") -> PriceQuote:
        return PriceQuote(price=Decimal("200"))

    monkeypatch.setattr(price_feed, "quote", quote)
    monkeypatch.setattr(prediction_tasks, "session_factory", TestSessionLocal)
    with time_machine.travel(FROZEN_NOW, tick=False):
        await prediction_tasks._check_prediction_accuracy()


async def test_le_suivi_de_precision_montre_les_predictions_journalisees_sans_utilisateur(
    client: AsyncClient, db_session: AsyncSession, regular_user: User
) -> None:
    target = NOW - timedelta(days=7)
    db_session.add(_log(target, actual_price=100.0, accuracy_checked=target, mape=10.0, direction_correct=False))
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_token(str(regular_user.id))}"}
    body = (await client.get("/api/v1/predictions/track-record/BTC", headers=headers)).json()
    assert (body["summary"]["total_checked"], body["summary"]["avg_mape"]) == (1, 10.0)


async def test_la_precision_se_mesure_au_cours_de_la_date_cible(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = datetime(2026, 10, 10)
    db_session.add(AssetPriceHistory(symbol="BTC", price_date=date(2026, 10, 10), price_eur=Decimal("100"), source="t"))
    db_session.add(_log(target))
    await db_session.commit()
    await _run_accuracy_check(monkeypatch)
    log = await _checked_log(db_session)
    assert (log.actual_price, round(log.mape or 0, 2), log.ci_covered) == (100.0, 10.0, True)


async def test_une_cible_un_samedi_se_mesure_au_cours_du_vendredi(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_session.add(AssetPriceHistory(symbol="BTC", price_date=date(2026, 10, 9), price_eur=Decimal("100"), source="t"))
    db_session.add(_log(datetime(2026, 10, 10)))
    await db_session.commit()
    await _run_accuracy_check(monkeypatch)
    assert (await _checked_log(db_session)).actual_price == 100.0


async def test_une_prediction_n_est_pas_mesuree_avant_que_le_jour_cible_soit_clos(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_session.add(AssetPriceHistory(symbol="BTC", price_date=NOW.date(), price_eur=Decimal("100"), source="t"))
    db_session.add(_log(datetime.combine(NOW.date(), datetime.min.time())))
    await db_session.commit()
    await _run_accuracy_check(monkeypatch)
    assert (await _checked_log(db_session)).accuracy_checked is None


async def test_une_prediction_sans_cours_une_semaine_apres_est_close_sans_mesure(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_session.add(_log(NOW - timedelta(days=8)))
    await db_session.commit()
    await _run_accuracy_check(monkeypatch)
    log = await _checked_log(db_session)
    assert (log.accuracy_checked, log.actual_price, log.mape) == (NOW, None, None)


async def test_le_reglage_optuna_ne_bloque_pas_la_boucle_d_evenements(monkeypatch: pytest.MonkeyPatch) -> None:
    on_loop_thread: list[bool] = []

    def tune(*args: Any, **kwargs: Any) -> dict[str, Any]:
        on_loop_thread.append(threading.current_thread() is threading.main_thread())
        return {}

    async def held(_: AsyncSession) -> list[tuple[str, AssetType]]:
        return [("BTC", AssetType.CRYPTO)]

    async def series(symbol: str, days: int, session: AsyncSession | None = None) -> PriceSeries:
        return PriceSeries([datetime(2026, 1, 1) + timedelta(days=i) for i in range(60)], [100.0] * 60)

    async def cache(*args: Any) -> None:
        return None

    monkeypatch.setattr(prediction_tasks, "tune_xgboost", tune)
    monkeypatch.setattr(prediction_tasks, "tune_prophet", tune)
    monkeypatch.setattr(prediction_tasks, "_held_assets", held)
    monkeypatch.setattr(prediction_tasks, "local_series", series)
    monkeypatch.setattr(prediction_tasks, "cache_hyperparams", cache)
    monkeypatch.setattr(prediction_tasks, "session_factory", TestSessionLocal)
    await prediction_tasks._tune_hyperparameters()
    assert on_loop_thread == [False, False]
