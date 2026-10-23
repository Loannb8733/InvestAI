import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from app.domains.exchanges.schemas import TaskStatus
from app.domains.exchanges.sync.runner import sync_account

logger = logging.getLogger(__name__)

Mode = Literal["import", "fx_refresh"]
FAILURE_MESSAGE = "L'import a échoué. Consultez les journaux du serveur pour le détail."
DONE_MESSAGES: dict[Mode, str] = {"import": "Import réussi", "fx_refresh": "Recalcul FX terminé"}


@dataclass
class _Task:
    owner: UUID
    status: TaskStatus
    handle: "asyncio.Task[None] | None" = field(default=None, repr=False)


_tasks: dict[str, _Task] = {}


async def _run(task_id: str, api_key_id: UUID, mode: Mode) -> None:
    task = _tasks[task_id]
    try:
        outcome = await sync_account(api_key_id, heal_fx=mode == "fx_refresh")
    except Exception:
        logger.exception("Background import error for task %s", task_id)
        task.status = TaskStatus(task_id=task_id, status="failed", error=FAILURE_MESSAGE)
        return
    if outcome.success:
        task.status = TaskStatus(
            task_id=task_id, status="completed", synced=outcome.synced, message=DONE_MESSAGES[mode]
        )
    else:
        task.status = TaskStatus(task_id=task_id, status="failed", error=outcome.error or FAILURE_MESSAGE)


def start(owner: UUID, api_key_id: UUID, mode: Mode) -> str:
    """Lance la synchronisation (ou le recalcul FX) en tâche de fond ; rend l'identifiant à interroger."""
    task_id = uuid.uuid4().hex
    task = _Task(owner=owner, status=TaskStatus(task_id=task_id, status="pending"))
    _tasks[task_id] = task
    task.handle = asyncio.create_task(_run(task_id, api_key_id, mode))
    return task_id


def status_of(owner: UUID, task_id: str) -> TaskStatus | None:
    """État de la tâche pour son propriétaire ; None pour tout autre, comme pour une tâche inconnue."""
    task = _tasks.get(task_id)
    return task.status if task is not None and task.owner == owner else None
