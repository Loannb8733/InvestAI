import logging
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.db.session import engine
from app.core.redis_client import redis_async_url, redis_client_kwargs

logger = logging.getLogger(__name__)

UNKNOWN_COMMIT = "inconnu"
UNKNOWN_REVISION = "inconnue"
READINESS_REDIS_TIMEOUT_S = 2

router = APIRouter()


def resolve_commit(env: Mapping[str, str] | None = None) -> str:
    """SHA court du commit déployé (RENDER_GIT_COMMIT ou GIT_COMMIT), « inconnu » sinon."""
    source = os.environ if env is None else env
    raw = (source.get("RENDER_GIT_COMMIT") or source.get("GIT_COMMIT") or "").strip()
    return raw[:7] if raw else UNKNOWN_COMMIT


def resolve_expected_revision() -> str:
    """Révision Alembic attendue par ce code, lue dans le graphe des migrations."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        root = Path(__file__).resolve().parent.parent.parent
        heads = ScriptDirectory.from_config(Config(str(root / "alembic.ini"))).get_heads()
        return heads[0] if len(heads) == 1 else UNKNOWN_REVISION
    except Exception:
        logger.warning("Révision de schéma attendue illisible", exc_info=True)
        return UNKNOWN_REVISION


DEPLOYED_COMMIT = resolve_commit()
EXPECTED_REVISION = resolve_expected_revision()
STARTED_AT = datetime.now(UTC).isoformat(timespec="seconds")


@router.get("/health")
@router.get("/api/v1/health")
async def health_check() -> dict[str, str]:
    """Sonde de vivacité : version déployée et schéma attendu."""
    return {
        "app": settings.APP_NAME,
        "status": "alive",
        "commit": DEPLOYED_COMMIT,
        "schema_attendu": EXPECTED_REVISION,
        "demarre_a": STARTED_AT,
    }


async def _applied_revision() -> str:
    try:
        async with engine.connect() as conn:
            applied = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
        return str(applied) if applied else "aucune"
    except Exception:  # noqa: BLE001
        return "illisible"


async def _redis_error() -> str | None:
    try:
        client = aioredis.from_url(
            redis_async_url(), **{**redis_client_kwargs(), "socket_timeout": READINESS_REDIS_TIMEOUT_S}
        )
        await client.ping()
        await client.aclose()
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Readiness: Redis ping failed (%s): %s", type(exc).__name__, exc)
        return type(exc).__name__


async def _database_ok() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False


@router.get("/health/ready")
@router.get("/api/v1/health/ready")
async def readiness_check() -> JSONResponse:
    """Sonde de disponibilité : base, révision de schéma appliquée et Redis."""
    checks: dict[str, Any] = {"app": settings.APP_NAME, "status": "ready"}
    healthy = True
    checks["database"] = "ok" if await _database_ok() else "error"
    healthy = healthy and checks["database"] == "ok"
    checks["schema_attendu"] = EXPECTED_REVISION
    checks["schema_applique"] = applied = await _applied_revision()
    if applied != "illisible" and EXPECTED_REVISION != UNKNOWN_REVISION and applied != EXPECTED_REVISION:
        healthy = False
    redis_error = await _redis_error()
    checks["redis"] = "error" if redis_error else "ok"
    if redis_error:
        checks["redis_erreur"] = redis_error
        healthy = False
    if not healthy:
        checks["status"] = "degraded"
    return JSONResponse(content=checks, status_code=200 if healthy else 503)
