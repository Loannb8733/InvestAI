"""Une écriture réussie vide le cache du tableau de bord de son auteur.

Le tableau de bord est mis en cache par utilisateur (2 minutes en mémoire,
5 minutes dans Redis). Le middleware `dashboard_cache_invalidation_middleware`
vide ce cache après toute écriture réussie ; sans lui, une correction de
quantité reste masquée par un ancien résultat — c'est ce qu'a vu l'utilisateur
le 2026-06-08 (+630 € de plus-value périmée affichée après un correctif Tangem).

Le middleware ne connaît l'utilisateur que par `request.state.user_id`, posé
par la dépendance d'authentification. Que l'un ou l'autre change, et
l'invalidation cesse sans erreur ni trace : aucun test ne le gardait.

La création de portefeuille sert d'écriture témoin : la route n'invalide rien
elle-même, seul le middleware peut le faire.
"""

import logging
import time
import uuid

import pytest
from httpx import AsyncClient

from app.core import redis_client
from app.core.security import create_access_token
from app.models.user import User
from app.services import metrics_service


@pytest.fixture
def entetes(regular_user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=str(regular_user.id))}"}


@pytest.fixture
def cache_amorce(regular_user: User):
    """Place une entrée pour l'utilisateur et une pour un tiers dans le cache en mémoire."""
    moi = (str(regular_user.id), 30)
    tiers = (str(uuid.uuid4()), 30)
    metrics_service._dashboard_cache[moi] = (time.time(), {"total_value": 1})
    metrics_service._dashboard_cache[tiers] = (time.time(), {"total_value": 2})
    yield moi, tiers
    metrics_service._dashboard_cache.pop(moi, None)
    metrics_service._dashboard_cache.pop(tiers, None)


@pytest.fixture
def purges_redis(monkeypatch) -> list:
    """Relève les purges Redis demandées, sans dépendre d'un Redis joignable."""
    appels: list = []

    async def _relever(user_id: str) -> None:
        appels.append(user_id)

    monkeypatch.setattr(redis_client, "invalidate_dashboard_cache", _relever)
    return appels


async def _creer_portefeuille(client: AsyncClient, entetes: dict) -> int:
    reponse = await client.post("/api/v1/portfolios", json={"name": "Témoin"}, headers=entetes)
    return reponse.status_code


@pytest.mark.asyncio
async def test_l_ecriture_vide_le_cache_en_memoire_de_son_auteur(
    client: AsyncClient, regular_user: User, entetes, cache_amorce, purges_redis
):
    moi, tiers = cache_amorce

    assert await _creer_portefeuille(client, entetes) == 201

    assert moi not in metrics_service._dashboard_cache, "le tableau de bord de l'auteur doit être recalculé"
    assert tiers in metrics_service._dashboard_cache, "le cache d'un autre utilisateur n'est pas concerné"


@pytest.mark.asyncio
async def test_l_ecriture_purge_aussi_le_cache_partage(
    client: AsyncClient, regular_user: User, entetes, cache_amorce, purges_redis
):
    assert await _creer_portefeuille(client, entetes) == 201

    # Demandée par le middleware, et une seconde fois par la purge en mémoire :
    # redondant, sans danger. Ce qui compte, c'est qu'elle vise l'auteur seul.
    assert purges_redis and set(purges_redis) == {str(regular_user.id)}


@pytest.mark.asyncio
async def test_une_lecture_ne_purge_rien(client: AsyncClient, regular_user: User, entetes, cache_amorce, purges_redis):
    moi, _ = cache_amorce

    reponse = await client.get("/api/v1/portfolios", headers=entetes)

    assert reponse.status_code == 200
    assert moi in metrics_service._dashboard_cache
    assert purges_redis == []


@pytest.mark.asyncio
async def test_un_echec_d_invalidation_se_voit_sans_casser_l_ecriture(
    client: AsyncClient, regular_user: User, entetes, cache_amorce, monkeypatch, caplog
):
    """Un cache non vidé affiche des chiffres périmés pendant plusieurs minutes :
    l'écriture doit réussir, le cache en mémoire être vidé malgré tout, et
    l'échec ne peut pas rester en DEBUG."""
    moi, _ = cache_amorce

    async def _redis_en_panne(user_id: str) -> None:
        raise ConnectionError("Redis injoignable")

    monkeypatch.setattr(redis_client, "invalidate_dashboard_cache", _redis_en_panne)
    caplog.set_level(logging.DEBUG, logger="app.main")

    assert await _creer_portefeuille(client, entetes) == 201

    assert moi not in metrics_service._dashboard_cache, "une panne Redis ne doit pas épargner le cache en mémoire"
    avertissements = [r.getMessage() for r in caplog.records if r.name == "app.main" and r.levelno >= logging.WARNING]
    assert any("Redis injoignable" in m for m in avertissements), avertissements
