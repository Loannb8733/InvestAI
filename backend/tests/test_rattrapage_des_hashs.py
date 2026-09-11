"""Le rattrapage des hashs de déduplication doit aboutir, et le dire.

`_rehash_transactions_internal_hash` recalcule `internal_hash` sur toutes les
transactions à chaque démarrage. Il **échouait à chaque fois** depuis le
2026-06-06, et son échec était invisible.

Le mécanisme, constaté le 2026-09-10 : deux bons Binance de 20 000 PEPE,
légitimes tous les deux, partagent le même hash (la formule n'horodate qu'au
jour). Le rattrapage prévoit ce cas — il met le second à `NULL` pour le sortir
de l'index d'unicité — mais il faisait un **seul commit**. SQLAlchemy émettait
alors l'`UPDATE` qui *pose* le hash avant celui qui *libère* la place, la
contrainte rejetait, et tout était annulé.

Trois conditions ont rendu la panne invisible : l'échec était journalisé en
avertissement, noyé dans le flot SQL du démarrage ; le rattrapage est idempotent
par conception, donc son inaction ressemble en tout point à son succès ; et le
message disait « skipped or failed », sans distinguer « rien à faire » de « tout
a échoué ».

Bilan sur les données réelles : 48 hashs périmés et 21 lignes sans hash s'étaient
accumulés en trois mois, la déduplication cessant d'y protéger des doublons.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.main import _rehash_transactions_internal_hash
from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction, TransactionType, compute_transaction_hash
from app.models.user import User

QUAND = datetime(2026, 3, 25, 0, 7, 0, tzinfo=timezone.utc)


def _hash_attendu(tx: Transaction) -> str:
    return compute_transaction_hash(
        asset_id=str(tx.asset_id),
        transaction_type=tx.transaction_type.value,
        quantity=str(tx.quantity),
        price=str(tx.price),
        executed_at=tx.executed_at.strftime("%Y-%m-%d") if tx.executed_at else "",
    )


@pytest.fixture
async def actif(db_session, regular_user: User) -> Asset:
    portefeuille = Portfolio(id=uuid.uuid4(), user_id=regular_user.id, name="Crypto")
    db_session.add(portefeuille)
    await db_session.flush()
    a = Asset(
        id=uuid.uuid4(),
        portfolio_id=portefeuille.id,
        symbol="PEPE",
        name="Pepe",
        asset_type=AssetType.CRYPTO,
        quantity=Decimal("40000"),
        avg_buy_price=Decimal("0"),
        currency="EUR",
    )
    db_session.add(a)
    await db_session.commit()
    return a


async def _ajouter(db_session, actif, *, hash_pose, quantite="20000", quand=QUAND) -> Transaction:
    tx = Transaction(
        id=uuid.uuid4(),
        asset_id=actif.id,
        transaction_type=TransactionType.AIRDROP,
        quantity=Decimal(quantite),
        price=Decimal("0.00000344"),
        fee=Decimal("0"),
        currency="EUR",
        executed_at=quand,
        internal_hash=hash_pose,
    )
    db_session.add(tx)
    await db_session.commit()
    return tx


async def _rattraper(db_session):
    """Appelle le rattrapage sur la session de test.

    Sans injection, il ouvrirait la sienne sur la base de l'application : le
    test le regarderait travailler ailleurs en croyant l'éprouver.
    """
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _fabrique():
        yield db_session

    await _rehash_transactions_internal_hash(session_factory=_fabrique)


async def _relire(db_session, actif) -> list[Transaction]:
    resultat = await db_session.execute(
        select(Transaction).where(Transaction.asset_id == actif.id).order_by(Transaction.quantity)
    )
    lignes = list(resultat.scalars().all())
    for tx in lignes:
        await db_session.refresh(tx)
    return lignes


class TestCollisionLegitime:
    """Deux lignes distinctes qui partagent un hash ne doivent rien casser."""

    async def test_le_rattrapage_aboutit_malgre_une_collision(self, db_session, actif):
        """Le défaut exact : un seul commit, et l'ordre des écritures décidait.

        La situation doit être posée avec soin, sans quoi le test ne prouve
        rien : la **seconde** ligne détient déjà le hash que le rattrapage va
        vouloir poser sur la **première**. C'est l'état réel observé le
        2026-09-10, et c'est lui qui fait entrer les deux écritures en conflit.

        Deux hashs simplement périmés ne suffiraient pas — l'index resterait
        libre, aucune contrainte ne serait heurtée, et le commit unique
        passerait. Le canari l'a montré.
        """
        premiere = await _ajouter(db_session, actif, hash_pose="hash_perime")
        seconde = await _ajouter(db_session, actif, hash_pose=None)
        seconde.internal_hash = _hash_attendu(premiere)
        await db_session.commit()

        await _rattraper(db_session)

        lignes = await _relire(db_session, actif)
        hashs = [tx.internal_hash for tx in lignes]
        assert sum(h is not None for h in hashs) == 1, "une seule des deux garde un hash"
        assert sum(h is None for h in hashs) == 1, "l'autre sort de l'index sans être supprimée"

    async def test_aucune_ligne_n_est_supprimee(self, db_session, actif):
        # La collision se règle en retirant un hash, jamais une transaction :
        # ce sont deux bons de 20 000 PEPE bien réels.
        premiere = await _ajouter(db_session, actif, hash_pose="hash_perime")
        seconde = await _ajouter(db_session, actif, hash_pose=None)
        seconde.internal_hash = _hash_attendu(premiere)
        await db_session.commit()

        await _rattraper(db_session)

        assert len(await _relire(db_session, actif)) == 2

    async def test_les_autres_lignes_sont_corrigees_malgre_la_collision(self, db_session, actif):
        """Le vrai coût du défaut, et ce qui le rendait grave.

        L'échec n'était pas cantonné aux deux lignes en collision : le rollback
        emportait **toutes** les corrections de la passe. Quarante-huit hashs
        périmés se sont ainsi accumulés en trois mois sur les données réelles.
        """
        premiere = await _ajouter(db_session, actif, hash_pose="hash_perime")
        seconde = await _ajouter(db_session, actif, hash_pose=None)
        seconde.internal_hash = _hash_attendu(premiere)
        await db_session.commit()
        isolee = await _ajouter(
            db_session,
            actif,
            hash_pose="autre_hash_perime",
            quantite="777",
            quand=datetime(2026, 4, 1, tzinfo=timezone.utc),
        )

        await _rattraper(db_session)

        await db_session.refresh(isolee)
        assert isolee.internal_hash == _hash_attendu(isolee)


class TestPasseOrdinaire:
    async def test_un_hash_perime_est_recalcule(self, db_session, actif):
        tx = await _ajouter(db_session, actif, hash_pose="hash_de_l_ancienne_formule")

        await _rattraper(db_session)

        await db_session.refresh(tx)
        assert tx.internal_hash == _hash_attendu(tx)

    async def test_une_ligne_sans_hash_en_recoit_un(self, db_session, actif):
        # Sans hash, la ligne échappe à toute déduplication : un réimport la
        # recréerait en double.
        tx = await _ajouter(db_session, actif, hash_pose=None)

        await _rattraper(db_session)

        await db_session.refresh(tx)
        assert tx.internal_hash == _hash_attendu(tx)

    async def test_une_seconde_passe_ne_change_rien(self, db_session, actif):
        """L'idempotence, qui est aussi ce qui rendait la panne invisible.

        Une passe sans effet et une passe qui échoue laissent la base dans le
        même état — d'où le message d'erreur, désormais explicite.
        """
        tx = await _ajouter(db_session, actif, hash_pose="perime")
        await _rattraper(db_session)
        await db_session.refresh(tx)
        apres_premiere = tx.internal_hash

        await _rattraper(db_session)

        await db_session.refresh(tx)
        assert tx.internal_hash == apres_premiere
