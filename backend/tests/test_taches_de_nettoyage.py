"""Filet sur les deux tâches de nettoyage qui **écrivent** en base.

`app/tasks/cleanup.py` était couvert à **0 %**. Deux de ses fonctions ne se
contentent pas de lire :

- `_cleanup_duplicate_transactions_async` **supprime** des transactions ;
- `_validate_portfolio_consistency_async` **réécrit** la quantité d'un actif
  cold-wallet à partir de la somme de ses transactions.

Le projet garde la mémoire de ce que ce genre d'écriture peut coûter : NEW-06
raconte sept lignes de « réconciliation » qui ont dégradé le P&L affiché de
214 €. Ces tests décrivent ce que les tâches font aujourd'hui, y compris les
cas où elles s'abstiennent — c'est cette abstention qui protège.

Les fonctions ouvrent leur propre session (`AsyncSessionLocal`) au lieu d'en
recevoir une : le filet la remplace par celle du test, sans quoi elles
écriraient dans la vraie base.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction, TransactionType
from app.services.transfer_service import COLD_WALLET_DESTINATION
from app.tasks import cleanup


@pytest.fixture
def session_de_test(db_session, monkeypatch):
    """Fait travailler les tâches sur la session du test.

    `commit()` est neutralisé : la fixture `db_session` gère elle-même la
    transaction, et un commit interne la clôturerait au milieu du test.
    """

    @asynccontextmanager
    async def _fabrique():
        yield db_session

    async def _flush_seulement():
        await db_session.flush()

    monkeypatch.setattr(cleanup, "AsyncSessionLocal", _fabrique)
    monkeypatch.setattr(db_session, "commit", _flush_seulement)
    return db_session


async def _portefeuille(db, user, nom="P"):
    pf = Portfolio(user_id=user.id, name=nom)
    db.add(pf)
    await db.flush()
    return pf


async def _actif(db, pf, symbole="BTC", quantite="1", exchange=""):
    a = Asset(
        portfolio_id=pf.id,
        symbol=symbole,
        name=symbole,
        asset_type=AssetType.CRYPTO,
        quantity=Decimal(quantite),
        avg_buy_price=Decimal("100"),
        exchange=exchange,
    )
    db.add(a)
    await db.flush()
    return a


def _tx(asset, *, type_tx=TransactionType.BUY, quantite="1", externe=None, quand=None):
    return Transaction(
        asset_id=asset.id,
        transaction_type=type_tx,
        quantity=Decimal(quantite),
        price=Decimal("100"),
        fee=Decimal("0"),
        external_id=externe,
        executed_at=quand or datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


class TestDeduplicationDeTransactions:
    async def test_deux_lignes_de_meme_identifiant_externe_ne_laissent_que_la_plus_ancienne(
        self, session_de_test, regular_user
    ):
        """La première créée est gardée — c'est l'ordre de `created_at` qui tranche.

        Garder la plus ancienne plutôt que la plus récente n'est pas neutre :
        si un ré-import corrige une ligne, c'est la version corrigée qui part.
        Comportement épinglé, pas approuvé.
        """
        pf = await _portefeuille(session_de_test, regular_user)
        btc = await _actif(session_de_test, pf)
        session_de_test.add(_tx(btc, externe="binance-42"))
        session_de_test.add(_tx(btc, externe="binance-42", quantite="99"))
        await session_de_test.flush()

        res = await cleanup._cleanup_duplicate_transactions_async()

        assert res["deleted_duplicates"] == 1
        restantes = (
            (
                await session_de_test.execute(
                    __import__("sqlalchemy").select(Transaction).where(Transaction.external_id == "binance-42")
                )
            )
            .scalars()
            .all()
        )
        assert len(restantes) == 1

    async def test_les_transactions_sans_identifiant_externe_sont_intouchees(self, session_de_test, regular_user):
        """Deux saisies manuelles identiques ne sont pas des doublons.

        Sans `external_id`, rien ne dit qu'une ligne est la copie d'une autre —
        deux achats du même montant le même jour sont un cas courant de DCA. Le
        filtre `external_id IS NOT NULL` est donc ce qui empêche la tâche de
        supprimer des transactions légitimes.
        """
        pf = await _portefeuille(session_de_test, regular_user)
        btc = await _actif(session_de_test, pf)
        session_de_test.add(_tx(btc))
        session_de_test.add(_tx(btc))
        await session_de_test.flush()

        res = await cleanup._cleanup_duplicate_transactions_async()

        assert res["deleted_duplicates"] == 0

    async def test_sans_doublon_rien_n_est_supprime(self, session_de_test, regular_user):
        pf = await _portefeuille(session_de_test, regular_user)
        btc = await _actif(session_de_test, pf)
        session_de_test.add(_tx(btc, externe="a"))
        session_de_test.add(_tx(btc, externe="b"))
        await session_de_test.flush()

        res = await cleanup._cleanup_duplicate_transactions_async()

        assert res["deleted_duplicates"] == 0


class TestCoherenceDesQuantites:
    async def test_un_actif_de_cold_wallet_est_recale_sur_ses_transactions(self, session_de_test, regular_user):
        pf = await _portefeuille(session_de_test, regular_user)
        froid = await _actif(session_de_test, pf, quantite="5", exchange=COLD_WALLET_DESTINATION)
        session_de_test.add(_tx(froid, quantite="3"))
        await session_de_test.flush()

        res = await cleanup._validate_portfolio_consistency_async()

        assert len(res["healed"]) == 1
        assert float(froid.quantity) == 3.0

    async def test_un_actif_d_exchange_est_signale_mais_jamais_reecrit(self, session_de_test, regular_user):
        """La quantité d'un exchange fait foi, pas la somme des transactions.

        L'exchange est la source de vérité : la synchronisation l'y réconcilie,
        et l'écart peut être légitime — un frais prélevé hors historique, un
        airdrop non importé. Réécrire ici effacerait cette vérité.
        """
        pf = await _portefeuille(session_de_test, regular_user)
        chaud = await _actif(session_de_test, pf, quantite="5", exchange="Binance")
        session_de_test.add(_tx(chaud, quantite="3"))
        await session_de_test.flush()

        res = await cleanup._validate_portfolio_consistency_async()

        assert len(res["details"]) == 1
        assert res["healed"] == []
        assert float(chaud.quantity) == 5.0

    async def test_une_quantite_calculee_negative_n_est_jamais_ecrite(self, session_de_test, regular_user):
        """Plus de sorties que d'entrées : la somme part en négatif.

        L'écrire violerait `ck_assets_quantity_positive` et ferait échouer la
        tâche entière. L'écart est signalé, la quantité laissée en place.
        """
        pf = await _portefeuille(session_de_test, regular_user)
        froid = await _actif(session_de_test, pf, quantite="1", exchange=COLD_WALLET_DESTINATION)
        session_de_test.add(_tx(froid, type_tx=TransactionType.SELL, quantite="4"))
        await session_de_test.flush()

        res = await cleanup._validate_portfolio_consistency_async()

        assert res["healed"] == []
        assert float(froid.quantity) == 1.0

    async def test_un_ecart_infinitesimal_ne_declenche_rien(self, session_de_test, regular_user):
        # Seuil à 1e-5 : les arrondis de flottants ne doivent pas provoquer
        # d'écriture en base à chaque passage de la tâche.
        pf = await _portefeuille(session_de_test, regular_user)
        froid = await _actif(session_de_test, pf, quantite="1.000001", exchange=COLD_WALLET_DESTINATION)
        session_de_test.add(_tx(froid, quantite="1"))
        await session_de_test.flush()

        res = await cleanup._validate_portfolio_consistency_async()

        assert res["details"] == []
        assert res["healed"] == []

    async def test_un_portefeuille_coherent_ne_produit_aucune_ecriture(self, session_de_test, regular_user):
        pf = await _portefeuille(session_de_test, regular_user)
        froid = await _actif(session_de_test, pf, quantite="2", exchange=COLD_WALLET_DESTINATION)
        session_de_test.add(_tx(froid, quantite="2"))
        await session_de_test.flush()

        res = await cleanup._validate_portfolio_consistency_async()

        assert res["details"] == []
        assert res["healed"] == []


class TestPurgesParAnciennete:
    async def test_les_predictions_anterieures_au_seuil_partent(self, session_de_test, regular_user):
        from app.models.prediction_log import PredictionLog

        def _log(symbole, jours):
            return PredictionLog(
                user_id=regular_user.id,
                symbol=symbole,
                asset_type="crypto",
                model_name="test",
                prediction_data={},
                created_at=datetime.now(timezone.utc) - timedelta(days=jours),
            )

        vieille = _log("BTC", 200)
        recente = _log("ETH", 5)
        session_de_test.add(vieille)
        session_de_test.add(recente)
        await session_de_test.flush()

        res = await cleanup._cleanup_old_predictions_async(days_to_keep=90)

        assert res["deleted_predictions"] == 1
