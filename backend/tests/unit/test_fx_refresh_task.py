from datetime import date

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.market_data.fx import tasks as fx_tasks
from app.tasks.celery_app import celery_app
from tests.conftest import TestSessionLocal
from tests.http_stubs import HttpStub

TASK_NAME = "app.domains.market_data.fx.tasks.refresh_fx_rates"
SCHEDULE_KEY = "refresh-fx-rates"


class TestPlanification:
    def test_la_tache_est_planifiee_sur_la_bonne_tache(self) -> None:
        assert celery_app.conf.beat_schedule[SCHEDULE_KEY]["task"] == TASK_NAME

    def test_le_module_est_dans_include(self) -> None:
        assert "app.domains.market_data.fx.tasks" in celery_app.conf.include

    def test_une_passe_par_jour_apres_la_publication_bce(self) -> None:
        crontab = celery_app.conf.beat_schedule[SCHEDULE_KEY]["schedule"]
        assert len(crontab.hour) == 1
        assert 15 <= min(int(h) for h in crontab.hour) <= 20

    def test_elle_est_enregistree(self) -> None:
        assert TASK_NAME in celery_app.tasks

    def test_les_paires_couvrent_les_devises_converties(self) -> None:
        assert {base for base, _ in fx_tasks.PAIRS} >= {"USD", "GBP", "CHF"}
        assert all(quote == "EUR" for _, quote in fx_tasks.PAIRS)


async def test_une_paire_en_echec_n_arrete_pas_les_autres(
    db_session: AsyncSession, http_stub: HttpStub, monkeypatch: pytest.MonkeyPatch
) -> None:
    def ecb(request: httpx.Request) -> httpx.Response:
        if request.url.params["base"] == "USD":
            return httpx.Response(503, request=request)
        return httpx.Response(200, json={"rates": {"2026-10-16": {"EUR": 0.9}}}, request=request)

    http_stub.on("api.frankfurter.dev", ecb)
    monkeypatch.setattr(fx_tasks, "session_factory", TestSessionLocal)
    monkeypatch.setattr(fx_tasks, "EARLIEST", date(2026, 10, 1))
    assert await fx_tasks.refresh_reference_rates() == {"USD->EUR": -1, "GBP->EUR": 1, "CHF->EUR": 1}
