"""Un seul exécuteur de coroutines, et un engine adapté au contexte (ARC-01).

Huit modules de `app/tasks` définissaient leur propre `run_async`, en trois variantes
subtilement différentes, et un neuvième appelait `new_event_loop` directement. Six
omettaient `set_event_loop` — or asyncpg et SQLAlchemy résolvent la boucle courante
via `get_event_loop()` en créant leurs ressources.

Le défaut se propageait par imitation : chaque nouvelle tâche recopiait le helper du
voisin. Une neuvième copie a été ajoutée ainsi le 2026-09-01.

Le vrai dégât venait du pool : une connexion mise au pool par la tâche N reste
attachée à la boucle N, fermée depuis ; la tâche N+1 la reprend et lève
« Task attached to a different loop ». Reproduit avant correctif — 1re passe OK,
2e en échec, 3e OK — puis 6/6 après.
"""

import asyncio
import re
from pathlib import Path

import pytest

from app.core.database import _running_in_worker
from app.tasks.async_runner import run_async

_TASKS = Path(__file__).resolve().parents[2] / "app" / "tasks"


@pytest.fixture(autouse=True)
def _preserver_la_boucle_du_thread():
    """Rend au thread la boucle qu'il avait avant le test.

    `run_async` ferme sa boucle et la laisse installée — sans conséquence dans un
    worker Celery, qui n'en attend aucune ensuite. Mais ces tests l'appellent
    directement : sans ce garde-fou, ils laissaient une boucle fermée comme boucle
    courante et 103 tests ultérieurs tombaient sur « There is no current event
    loop ». Un test ne doit pas modifier l'état global du processus.
    """
    try:
        avant = asyncio.get_event_loop_policy().get_event_loop()
    except RuntimeError:
        avant = None
    try:
        yield
    finally:
        if avant is not None and not avant.is_closed():
            asyncio.set_event_loop(avant)
        else:
            asyncio.set_event_loop(asyncio.new_event_loop())


class TestExecuteurUnique:
    def test_aucune_tache_ne_redefinit_run_async(self):
        coupables = [
            f.name
            for f in _TASKS.glob("*.py")
            if f.name != "async_runner.py" and re.search(r"^def _?run_async\(", f.read_text(encoding="utf-8"), re.M)
        ]
        assert not coupables, f"helper dupliqué dans {coupables} — importer app.tasks.async_runner"

    def test_aucune_tache_ne_cree_sa_propre_boucle(self):
        coupables = [
            f.name
            for f in _TASKS.glob("*.py")
            if f.name != "async_runner.py" and "new_event_loop" in f.read_text(encoding="utf-8")
        ]
        assert not coupables, f"new_event_loop hors du module unique dans {coupables}"

    def test_le_scan_voit_bien_les_fichiers(self):
        # Sans ce garde-fou, les deux tests ci-dessus passeraient à vide.
        assert len(list(_TASKS.glob("*.py"))) >= 10


class TestComportement:
    def test_execute_et_retourne(self):
        async def job():
            return 42

        assert run_async(job()) == 42

    def test_appels_successifs(self):
        # Le cas qui échouait : deux exécutions d'affilée.
        async def job():
            await asyncio.sleep(0)
            return 1

        assert [run_async(job()) for _ in range(3)] == [1, 1, 1]

    def test_la_boucle_est_installee_pendant_l_execution(self):
        # Sans set_event_loop, asyncpg/SQLAlchemy rattachent leurs ressources à une
        # autre boucle que celle qui exécute la coroutine.
        async def job():
            return asyncio.get_event_loop() is asyncio.get_running_loop()

        assert run_async(job()) is True

    def test_la_boucle_est_neuve_a_chaque_appel(self):
        """Chaque exécution repart d'une boucle propre — c'est tout l'enjeu d'ARC-01.

        Une connexion mise au pool par la tâche N reste attachée à la boucle N ;
        si la tâche N+1 réutilisait cette boucle fermée, asyncpg lèverait
        « Task attached to a different loop ».
        """

        async def identite():
            return id(asyncio.get_running_loop())

        assert run_async(identite()) != run_async(identite())

    def test_une_exception_est_propagee(self):
        async def job():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            run_async(job())


class TestDetectionDuContexte:
    def test_variable_d_environnement_prioritaire(self, monkeypatch):
        for valeur, attendu in (("1", True), ("true", True), ("on", True), ("0", False), ("no", False)):
            monkeypatch.setenv("DB_NULLPOOL", valeur)
            assert _running_in_worker() is attendu

    def test_worker_celery_detecte(self, monkeypatch):
        monkeypatch.delenv("DB_NULLPOOL", raising=False)
        monkeypatch.setattr("sys.argv", ["/usr/local/bin/celery", "worker"])
        assert _running_in_worker() is True

    def test_serveur_web_garde_son_pool(self, monkeypatch):
        # FastAPI sert tout dans une seule boucle : le pool y est un gain net.
        monkeypatch.delenv("DB_NULLPOOL", raising=False)
        monkeypatch.setattr("sys.argv", ["/usr/local/bin/uvicorn", "app.main:app"])
        assert _running_in_worker() is False
