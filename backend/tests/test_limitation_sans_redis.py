"""La limitation de débit tient quand Redis tombe.

Le limiteur compte les requêtes dans Upstash Redis. Il est configuré pour
avaler les erreurs de stockage (`swallow_errors=True`) : sans le compteur en
mémoire qui prend le relais (`in_memory_fallback_enabled=True`), une panne
Redis ne lèverait rien et ne limiterait plus rien — le login redeviendrait
ouvert au bourrage d'identifiants, sans un message.

Ces tests éprouvent le vrai limiteur de l'application, branché sur un Redis
injoignable, à travers la vraie route de login.
"""

import logging

import pytest
from httpx import AsyncClient
from limits.storage import storage_from_string
from limits.strategies import STRATEGIES

from app.core.rate_limit import RATE_LIMITS, limiter
from app.models.user import User

# Personne n'écoute sur ce port : la connexion est refusée tout de suite.
_REDIS_INJOIGNABLE = "redis://127.0.0.1:6399/0"


def _plafond_du_login() -> int:
    return int(RATE_LIMITS["auth_login"].split("/")[0])


@pytest.fixture
def redis_en_panne(monkeypatch):
    """Branche le limiteur de l'application sur un Redis injoignable."""
    stockage_mort = storage_from_string(_REDIS_INJOIGNABLE)
    monkeypatch.setattr(limiter, "_storage", stockage_mort)
    monkeypatch.setattr(limiter, "_limiter", STRATEGIES["fixed-window"](stockage_mort))
    monkeypatch.setattr(limiter, "_storage_dead", False)
    # Absent quand le repli est désactivé : c'est alors l'assertion qui doit
    # échouer, pas la préparation.
    compteur_local = getattr(limiter, "_fallback_storage", None)
    if compteur_local is not None:
        compteur_local.reset()
    yield
    if compteur_local is not None:
        compteur_local.reset()


async def _tentatives_de_login(client: AsyncClient, nombre: int) -> list[int]:
    codes = []
    for _ in range(nombre):
        reponse = await client.post(
            "/api/v1/auth/login",
            json={"email": "user@test.com", "password": "wrongpassword"},
        )
        codes.append(reponse.status_code)
    return codes


@pytest.mark.asyncio
async def test_le_login_reste_limite_sans_redis(client: AsyncClient, regular_user: User, redis_en_panne):
    plafond = _plafond_du_login()

    codes = await _tentatives_de_login(client, plafond + 2)

    assert 429 not in codes[:plafond], f"les {plafond} premières tentatives doivent passer : {codes}"
    assert codes[plafond:] == [429, 429], f"au-delà du plafond, le login doit être refusé : {codes}"


@pytest.mark.asyncio
async def test_la_bascule_sur_le_compteur_local_se_voit(
    client: AsyncClient, regular_user: User, redis_en_panne, caplog
):
    caplog.set_level(logging.INFO)

    await _tentatives_de_login(client, 1)

    bascules = [
        r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING and "unreachable" in r.getMessage()
    ]
    assert bascules, "la perte du stockage partagé doit apparaître dans le journal"
