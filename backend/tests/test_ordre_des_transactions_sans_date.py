"""Filet sur l'ordre d'affichage quand une transaction n'a pas de date.

Le constat qui a lancé ce filet, fait sur les données réelles :

    SELECT symbol, transaction_type, executed_at
    FROM transactions ORDER BY executed_at DESC LIMIT 5;

    ETH  TRANSFER_OUT  SANS DATE
    ETH  TRANSFER_IN   SANS DATE
    ETH  TRANSFER_IN   SANS DATE
    ETH  TRANSFER_IN   SANS DATE
    ETH  TRANSFER_IN   SANS DATE

PostgreSQL place les valeurs nulles **en tête** d'un tri décroissant. Or 195 des
840 transactions n'ont pas de date d'exécution. Le panneau « Transactions
récentes » du tableau de bord, qui en prend cinq, n'a donc jamais montré autre
chose que ces transferts sans date — et la première page de la liste des
transactions non plus.

Les fonctions qui *somment* des transactions sans les limiter ne sont pas
concernées : l'ordre n'y change rien. Ce filet porte sur les endroits où
l'ordre décide de ce que l'utilisateur voit.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.api.v1.endpoints.dashboard import get_recent_transactions_internal
from app.core.security import create_access_token
from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction, TransactionType
from app.models.user import User

MAINTENANT = datetime.now(timezone.utc)


@pytest.fixture
def entetes(regular_user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=str(regular_user.id))}"}


@pytest.fixture
async def actif(db_session, regular_user: User) -> Asset:
    portefeuille = Portfolio(user_id=regular_user.id, name="Principal")
    db_session.add(portefeuille)
    await db_session.flush()
    a = Asset(
        portfolio_id=portefeuille.id,
        symbol="BTC",
        name="Bitcoin",
        asset_type=AssetType.CRYPTO,
        quantity=Decimal("10"),
        avg_buy_price=Decimal("30000"),
        exchange="Binance",
    )
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    return a


async def _mouvement(db_session, actif: Asset, note: str, *, quand, cree_le=None) -> None:
    """`cree_le` est explicite parce qu'il compte : une ligne sans date
    d'exécution est située par sa date de création, et les 195 lignes réelles
    concernées ont été importées il y a des mois."""
    db_session.add(
        Transaction(
            asset_id=actif.id,
            transaction_type=TransactionType.BUY,
            quantity=Decimal("1"),
            price=Decimal("30000"),
            fee=Decimal("0"),
            currency="EUR",
            executed_at=quand,
            created_at=cree_le or MAINTENANT,
            notes=note,
        )
    )
    await db_session.commit()


class TestPanneauRecent:
    async def test_une_transaction_sans_date_ne_prend_pas_la_tete(self, db_session, regular_user, actif):
        """Le défaut vu sur les données réelles.

        Une transaction sans date d'exécution garde sa date de création, et
        c'est elle qui doit la situer dans le temps — l'affichage fait déjà ce
        repli (`executed_at or created_at`), le tri ne le faisait pas.
        """
        await _mouvement(db_session, actif, "sans date", quand=None, cree_le=MAINTENANT - timedelta(days=90))
        await _mouvement(db_session, actif, "hier", quand=MAINTENANT - timedelta(days=1))
        await _mouvement(db_session, actif, "aujourd'hui", quand=MAINTENANT)

        recentes = await get_recent_transactions_internal(db_session, regular_user, limit=2)

        symboles = [t.executed_at for t in recentes]
        assert len(recentes) == 2
        assert symboles == sorted(symboles, reverse=True)

    async def test_les_mouvements_dates_passent_devant(self, db_session, regular_user, actif):
        # Cinq lignes sans date noieraient les deux mouvements réels si les
        # nulles restaient en tête : c'est exactement ce qui se passait.
        for i in range(5):
            await _mouvement(
                db_session, actif, f"sans date {i}", quand=None, cree_le=MAINTENANT - timedelta(days=90 + i)
            )
        await _mouvement(db_session, actif, "achat récent", quand=MAINTENANT)

        recentes = await get_recent_transactions_internal(db_session, regular_user, limit=1)

        assert len(recentes) == 1
        transaction = (
            (await db_session.execute(select(Transaction).where(Transaction.id == recentes[0].id))).scalars().one()
        )
        assert transaction.notes == "achat récent"

    async def test_l_ordre_reste_decroissant_entre_deux_dates(self, db_session, regular_user, actif):
        await _mouvement(db_session, actif, "ancien", quand=MAINTENANT - timedelta(days=10))
        await _mouvement(db_session, actif, "recent", quand=MAINTENANT - timedelta(days=1))

        recentes = await get_recent_transactions_internal(db_session, regular_user, limit=5)

        assert [t.executed_at for t in recentes] == sorted([t.executed_at for t in recentes], reverse=True)

    async def test_sans_portefeuille_la_liste_est_vide(self, db_session, admin_user):
        assert await get_recent_transactions_internal(db_session, admin_user) == []


class TestListeDesTransactions:
    async def test_la_premiere_page_montre_les_mouvements_les_plus_recents(self, client, entetes, db_session, actif):
        for i in range(3):
            await _mouvement(
                db_session, actif, f"sans date {i}", quand=None, cree_le=MAINTENANT - timedelta(days=90 + i)
            )
        await _mouvement(db_session, actif, "achat récent", quand=MAINTENANT)

        reponse = await client.get("/api/v1/transactions", params={"limit": 1}, headers=entetes)

        assert reponse.status_code == 200
        assert reponse.json()[0]["notes"] == "achat récent"
