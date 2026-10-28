import asyncio
import contextlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta

from celery.schedules import BaseSchedule, maybe_schedule, schedule

from app.core.redis_client import _get_redis_txt
from app.domains.system.jobs import HEAVY_PREFIX, JOBS, Job
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

STATE_KEY = "scheduler:tasks"
TICK_S = 30
SAVED_FROM = timedelta(hours=1)
ERROR_LENGTH = 500
RESULT_LENGTH = 500


def _stamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass
class JobState:
    """Dernière exécution d'une tâche planifiée ; gardée dans Redis entre deux démarrages si l'entrée l'exige."""

    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error: str | None = None
    last_duration_s: float | None = None
    last_result: str | None = None
    running: bool = False

    @property
    def failed(self) -> bool:
        """Vrai quand la dernière exécution s'est terminée en erreur."""
        return (
            self.last_error_at is not None and self.last_run_at is not None and self.last_error_at >= self.last_run_at
        )

    def dumps(self) -> str:
        """Forme stockée, sans l'indicateur d'exécution en cours."""
        stored = {key: value for key, value in asdict(self).items() if key != "running"}
        return json.dumps(
            {key: value.isoformat() if isinstance(value, datetime) else value for key, value in stored.items()}
        )

    @classmethod
    def loads(cls, raw: str) -> "JobState":
        """État relu depuis sa forme stockée."""
        data = json.loads(raw)
        return cls(
            last_run_at=_stamp(data.get("last_run_at")),
            last_success_at=_stamp(data.get("last_success_at")),
            last_error_at=_stamp(data.get("last_error_at")),
            last_error=data.get("last_error"),
            last_duration_s=data.get("last_duration_s"),
            last_result=data.get("last_result"),
        )


@dataclass(frozen=True)
class Entry:
    """Tâche de la planification Celery : son nom, sa tâche, son rythme et le travail qu'elle lance."""

    name: str
    task: str
    schedule: BaseSchedule
    job: Job

    @property
    def saved(self) -> bool:
        """Vrai quand un redémarrage pourrait lui faire manquer son passage : horaire fixe ou rythme d'une heure et
        plus. Les autres repassent dans l'heure ; leur état reste en mémoire, sans commande Redis."""
        return not isinstance(self.schedule, schedule) or self.schedule.run_every >= SAVED_FROM

    @property
    def heavy(self) -> bool:
        """Vrai pour une tâche de prédiction : elles s'exécutent une à la fois."""
        return self.task.startswith(HEAVY_PREFIX)


def beat_entries() -> list[Entry]:
    """Entrées de ``celery_app.conf.beat_schedule``, chacune liée à son travail asynchrone."""
    return [
        Entry(name, config["task"], maybe_schedule(config["schedule"], app=celery_app), JOBS[config["task"]])
        for name, config in celery_app.conf.beat_schedule.items()
    ]


async def _stored_states() -> dict[str, str]:
    try:
        raw = await (await _get_redis_txt()).hgetall(STATE_KEY)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Scheduler state unreadable, starting from scratch: %s", exc)
        return {}
    return {str(name): str(state) for name, state in raw.items()}


async def _store(name: str, state: JobState) -> None:
    try:
        await (await _get_redis_txt()).hset(STATE_KEY, name, state.dumps())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Scheduler state of %s not saved: %s", name, exc)


@dataclass
class Scheduler:
    """Exécute la planification Celery dans le service web quand aucun worker n'existe."""

    entries: dict[str, Entry]
    states: dict[str, JobState] = field(default_factory=dict)
    _heavy: asyncio.Lock = field(default_factory=asyncio.Lock)
    _tasks: set[asyncio.Task[JobState]] = field(default_factory=set)

    def state(self, name: str) -> JobState:
        """État de la tâche ``name``, vide tant qu'elle n'a pas tourné."""
        return self.states.setdefault(name, JobState())

    async def load(self) -> None:
        """Relit les états de Redis ; une tâche jamais vue part de maintenant, comme dans Celery beat."""
        stored = await _stored_states()
        now = datetime.now(UTC)
        for name in self.entries:
            if name in stored:
                self.states[name] = JobState.loads(stored[name])
            else:
                self.states[name] = JobState(last_run_at=now)
                if self.entries[name].saved:
                    await _store(name, self.states[name])

    def next_run_at(self, name: str) -> datetime | None:
        """Prochaine exécution prévue, None tant que les états ne sont pas chargés."""
        last = self.state(name).last_run_at
        if last is None:
            return None
        remaining: timedelta = self.entries[name].schedule.remaining_estimate(last)
        return datetime.now(UTC) + max(remaining, timedelta(0))

    def due(self) -> list[str]:
        """Tâches à lancer maintenant : échues et pas déjà en cours."""
        return [
            name
            for name, entry in self.entries.items()
            if not self.state(name).running
            and self.state(name).last_run_at is not None
            and entry.schedule.is_due(self.state(name).last_run_at).is_due
        ]

    async def run(self, name: str) -> JobState:
        """Lance la tâche maintenant et enregistre son issue, et son résultat quand elle réussit ; une erreur est
        consignée, jamais propagée."""
        entry, state = self.entries[name], self.state(name)
        state.running, state.last_run_at = True, datetime.now(UTC)
        started = time.monotonic()
        try:
            async with self._heavy if entry.heavy else contextlib.nullcontext():
                result = await entry.job()
        except Exception as exc:
            logger.exception("Scheduled task %s failed", name)
            state.last_error_at, state.last_error = datetime.now(UTC), f"{type(exc).__name__}: {exc}"[:ERROR_LENGTH]
        else:
            state.last_success_at = datetime.now(UTC)
            state.last_result = json.dumps(result, default=str, ensure_ascii=False)[:RESULT_LENGTH]
        finally:
            state.running, state.last_duration_s = False, round(time.monotonic() - started, 1)
            if entry.saved:
                await _store(name, state)
        return state

    def start(self, name: str) -> asyncio.Task[JobState]:
        """Lance la tâche en arrière-plan."""
        task = asyncio.create_task(self.run(name))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def serve(self) -> None:
        """Charge les états puis lance les tâches échues toutes les 30 s, jusqu'à l'arrêt du service."""
        await self.load()
        logger.info("In-process scheduler started with %d tasks", len(self.entries))
        while True:
            for name in self.due():
                self.start(name)
            await asyncio.sleep(TICK_S)


api_scheduler = Scheduler({entry.name: entry for entry in beat_entries()})
