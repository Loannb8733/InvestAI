import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.system.models import AuditLog

logger = logging.getLogger(__name__)


async def log_audit(
    db: AsyncSession,
    action: str,
    user_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Ajoute une trace d'audit à la transaction en cours ; un échec est journalisé sans interrompre l'opération."""
    try:
        db.add(
            AuditLog(
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
        await db.flush()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to log audit event: %s", exc)
