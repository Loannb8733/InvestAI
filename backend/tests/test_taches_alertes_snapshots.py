"""Filet sur les alertes et les snapshots planifiés.

`app/tasks/alerts.py` et `app/tasks/snapshots.py` étaient couverts à **0 %**.
Ils tournent tous les jours — les alertes toutes les quinze minutes — et NEW-42
a montré ce qu'un module de tâche jamais exécuté peut cacher : un `TypeError`
quotidien pendant des mois, perdu dans les journaux Celery.

Ces tests parcourent le vrai chemin. Les tâches Celery elles-mêmes appellent
`run_async`, qui ouvre sa propre boucle et tuerait celle de la suite : ce sont
donc les coroutines internes qui sont exercées, avec la session du test à la
place de `AsyncSessionLocal`.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.tasks import snapshots as taches_snapshots


@pytest.fixture
def session_snapshots(db_session, monkeypatch):
    @asynccontextmanager
    async def _fabrique():
        yield db_session

    async def _flush_seulement():
        await db_session.flush()

    monkeypatch.setattr(taches_snapshots, "AsyncSessionLocal", _fabrique)
    monkeypatch.setattr(db_session, "commit", _flush_seulement)
    return db_session


async def _portefeuille_garni(db, user, nom="P"):
    pf = Portfolio(user_id=user.id, name=nom)
    db.add(pf)
    await db.flush()
    db.add(
        Asset(
            portfolio_id=pf.id,
            symbol="BTC",
            name="BTC",
            asset_type=AssetType.CRYPTO,
            quantity=Decimal("1"),
            avg_buy_price=Decimal("40000"),
            current_price=Decimal("45000"),
        )
    )
    await db.flush()
    return pf


class TestSnapshotsQuotidiens:
    async def test_une_base_sans_portefeuille_ne_produit_rien(self, session_snapshots):
        """Le chemin est parcouru jusqu'au bout, même sans personne à traiter.

        C'est ce parcours qui trouve les erreurs de construction de requête —
        celles qui lèvent avant d'atteindre la base, comme le `func.case` de
        NEW-42.
        """
        res = await taches_snapshots._create_all_snapshots_async()

        assert res == {"total": 0, "success": 0, "failed": 0}

    async def test_un_utilisateur_avec_portefeuille_obtient_son_instantane(self, session_snapshots, regular_user):
        await _portefeuille_garni(session_snapshots, regular_user)

        res = await taches_snapshots._create_all_snapshots_async()

        assert res["success"] >= 1

    async def test_un_second_passage_le_meme_jour_ne_double_pas_l_instantane(self, session_snapshots, regular_user):
        """L'idempotence protège d'un `beat` qui rejouerait la journée.

        Sans elle, deux passages laisseraient deux instantanés globaux pour la
        même date et la courbe de patrimoine compterait ce jour-là deux fois.
        """
        await _portefeuille_garni(session_snapshots, regular_user)

        await taches_snapshots._create_all_snapshots_async()
        second = await taches_snapshots._create_all_snapshots_async()

        assert second["success"] == 0

    async def test_la_purge_respecte_l_anciennete_demandee(self, session_snapshots, regular_user):
        maintenant = datetime.now(timezone.utc)
        for jours in (400, 10):
            session_snapshots.add(
                PortfolioSnapshot(
                    user_id=regular_user.id,
                    snapshot_date=maintenant - timedelta(days=jours),
                    total_value=Decimal("100"),
                    total_invested=Decimal("100"),
                    total_gain_loss=Decimal("0"),
                )
            )
        await session_snapshots.flush()

        res = await taches_snapshots._cleanup_old_snapshots_async(days_to_keep=365)

        assert res["deleted"] == 1

    async def test_une_purge_sans_rien_a_supprimer_ne_touche_a_rien(self, session_snapshots, regular_user):
        session_snapshots.add(
            PortfolioSnapshot(
                user_id=regular_user.id,
                snapshot_date=datetime.now(timezone.utc),
                total_value=Decimal("100"),
                total_invested=Decimal("100"),
                total_gain_loss=Decimal("0"),
            )
        )
        await session_snapshots.flush()

        res = await taches_snapshots._cleanup_old_snapshots_async(days_to_keep=365)

        assert res["deleted"] == 0


class TestVerificationDesAlertes:
    async def test_le_service_d_alertes_traverse_une_base_vide(self, db_session):
        """`check_all_user_alerts` est ce que la tâche appelle.

        La tâche elle-même passe par `run_async` — une seconde boucle
        d'événements, incompatible avec celle de la suite (le projet en garde
        la trace dans `test_pas_de_boucle_fermee`). C'est donc le service qui
        est exercé ici, sur le même chemin de code.
        """
        from app.services.alert_service import alert_service

        res = await alert_service.check_all_user_alerts(db_session)

        assert res["users_checked"] == 0
        assert res["alerts_triggered"] == 0

    async def test_un_utilisateur_sans_alerte_est_compte_sans_declencher(self, db_session, regular_user):
        from app.services.alert_service import alert_service

        await _portefeuille_garni(db_session, regular_user)
        await db_session.commit()

        res = await alert_service.check_all_user_alerts(db_session)

        assert res["alerts_triggered"] == 0
