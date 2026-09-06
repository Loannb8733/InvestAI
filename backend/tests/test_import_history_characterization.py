"""Tests de caractérisation de ``import_trade_history`` (api_keys.py).

Pourquoi ce fichier existe
--------------------------
``import_trade_history`` fait **1 174 lignes** — 63 % de son module — dans un
seul ``try`` de 1 148 lignes, et n'avait **aucun test**. Elle écrit des
transactions financières en base à partir de treize appels distincts au service
d'exchange.

Un tel bloc ne se découpe pas à vue. Ces tests épinglent le comportement
d'aujourd'hui, bizarreries comprises, pour que le découpage à venir puisse être
jugé sur pièce : tout écart devient un échec explicite, à valider ou à corriger
sciemment.

Ce ne sont donc **pas** des tests de spécification. Ils ne disent pas ce que la
fonction devrait faire, mais ce qu'elle fait — la distinction compte le jour où
l'un d'eux devient gênant.

Le contrat du service d'exchange, relevé dans ``exchanges/base.py``
------------------------------------------------------------------
Toutes les méthodes rendent une liste, **sauf** ``get_instant_buys`` qui rend
``tuple[List[ExchangeTrade], set]``. Un faux service qui l'ignore fait échouer
l'import sur un ``ValueError: not enough values to unpack`` — c'est la première
chose que cette exploration a révélée, et elle venait du double, pas du code.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import create_access_token, encrypt_api_key
from app.models.api_key import APIKey
from app.models.asset import Asset
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction
from app.models.user import User
from app.services.exchanges.base import ExchangeTrade

MAINTENANT = datetime.now(timezone.utc)


def _trade(trade_id, symbol, side, quantite, prix, frais="0", quand=None):
    return ExchangeTrade(
        trade_id=trade_id,
        symbol=symbol,
        side=side,
        quantity=Decimal(quantite),
        price=Decimal(prix),
        fee=Decimal(frais),
        fee_currency="EUR",
        timestamp=quand or (MAINTENANT - timedelta(days=30)),
    )


class ServiceDouble:
    """Double du service d'exchange, fidèle au contrat de `base.py`."""

    exchange_name = "binance"
    trades: list = []
    balances: list = []

    def __init__(self, *args, **kwargs):
        pass

    async def get_trades(self, **k):
        return list(type(self).trades)

    async def get_balances(self, **k):
        return list(type(self).balances)

    async def get_fiat_orders(self, **k):
        return []

    async def get_rewards(self, **k):
        return []

    async def get_withdrawals(self, **k):
        return []

    async def get_crypto_conversions(self, **k):
        return []

    async def get_instant_buys(self, **k):
        # Seule méthode du contrat à rendre un tuple : (trades, refids).
        return [], set()

    async def get_auto_invest_history(self, **k):
        return []

    async def get_convert_history(self, **k):
        return []

    async def get_ledgers(self, **k):
        return []

    async def get_forex_rate(self, *a, **k):
        return 0.92

    async def get_historical_crypto_price(self, *a, **k):
        return None

    async def get_multiple_crypto_prices(self, *a, **k):
        return {}

    async def close(self):
        pass


@pytest.fixture
def service_double():
    ServiceDouble.trades = []
    ServiceDouble.balances = []
    return ServiceDouble


async def _cle_api(db_session, utilisateur) -> APIKey:
    cle = APIKey(
        user_id=utilisateur.id,
        exchange="binance",
        label="test",
        encrypted_api_key=encrypt_api_key("cle"),
        encrypted_secret_key=encrypt_api_key("secret"),
        is_active=True,
    )
    db_session.add(cle)
    await db_session.commit()
    await db_session.refresh(cle)
    return cle


async def _importer(client, db_session, utilisateur, service):
    cle = await _cle_api(db_session, utilisateur)
    token = create_access_token(subject=str(utilisateur.id))
    with patch("app.api.v1.endpoints.api_keys.get_exchange_service", return_value=service):
        reponse = await client.post(
            f"/api/v1/api-keys/{cle.id}/import-history",
            headers={"Authorization": f"Bearer {token}"},
        )
    return reponse


class TestExchangeSansDonnee:
    """Le cas dégénéré : aucun trade, aucun solde."""

    async def test_reussit_au_lieu_d_echouer(self, client: AsyncClient, regular_user: User, db_session, service_double):
        reponse = await _importer(client, db_session, regular_user, service_double)
        assert reponse.status_code == 200

    async def test_tous_les_compteurs_a_zero(self, client: AsyncClient, regular_user: User, db_session, service_double):
        corps = (await _importer(client, db_session, regular_user, service_double)).json()
        for cle in (
            "imported_transactions",
            "fiat_orders",
            "rewards",
            "conversions",
            "withdrawals",
            "spot_trades",
            "assets_created",
            "reconciled_assets",
        ):
            assert corps[cle] == 0, cle

    async def test_cree_le_portefeuille_crypto(
        self, client: AsyncClient, regular_user: User, db_session, service_double
    ):
        """Le portefeuille est créé même quand il n'y a rien à y mettre."""
        corps = (await _importer(client, db_session, regular_user, service_double)).json()
        assert corps["portfolio_name"] == "Crypto"

        portefeuilles = (
            (await db_session.execute(select(Portfolio).where(Portfolio.user_id == regular_user.id))).scalars().all()
        )
        assert [p.name for p in portefeuilles] == ["Crypto"]

    async def test_la_forme_de_la_reponse_est_stable(
        self, client: AsyncClient, regular_user: User, db_session, service_double
    ):
        """Douze clés, dont un bloc `debug` que le front peut afficher."""
        corps = (await _importer(client, db_session, regular_user, service_double)).json()
        assert set(corps) == {
            "message",
            "imported_transactions",
            "fiat_orders",
            "rewards",
            "conversions",
            "withdrawals",
            "spot_trades",
            "assets_created",
            "reconciled_assets",
            "portfolio_id",
            "portfolio_name",
            "debug",
        }


class TestAchatSpot:
    async def test_cree_une_transaction_et_un_actif(
        self, client: AsyncClient, regular_user: User, db_session, service_double
    ):
        service_double.trades = [_trade("t1", "BTCEUR", "buy", "0.5", "30000")]

        corps = (await _importer(client, db_session, regular_user, service_double)).json()

        assert corps["imported_transactions"] == 1
        transactions = (await db_session.execute(select(Transaction))).scalars().all()
        assert len(transactions) == 1
        assert float(transactions[0].quantity) == 0.5
        assert float(transactions[0].price) == 30000

    async def test_l_actif_porte_le_symbole_de_base(
        self, client: AsyncClient, regular_user: User, db_session, service_double
    ):
        """« BTCEUR » donne un actif « BTC » : la paire est décomposée."""
        service_double.trades = [_trade("t1", "BTCEUR", "buy", "0.5", "30000")]

        await _importer(client, db_session, regular_user, service_double)

        actifs = (await db_session.execute(select(Asset))).scalars().all()
        assert [a.symbol for a in actifs] == ["BTC"]

    async def test_l_identifiant_externe_est_conserve(
        self, client: AsyncClient, regular_user: User, db_session, service_double
    ):
        """C'est lui qui permet de ne pas réimporter deux fois le même trade."""
        service_double.trades = [_trade("t1", "BTCEUR", "buy", "0.5", "30000")]

        await _importer(client, db_session, regular_user, service_double)

        tx = (await db_session.execute(select(Transaction))).scalars().first()
        assert tx.external_id is not None
        assert "t1" in tx.external_id


class TestVenteSpot:
    async def test_la_vente_est_importee(self, client: AsyncClient, regular_user: User, db_session, service_double):
        service_double.trades = [
            _trade(
                "t1",
                "BTCEUR",
                "buy",
                "1",
                "30000",
                quand=MAINTENANT - timedelta(days=60),
            ),
            _trade(
                "t2",
                "BTCEUR",
                "sell",
                "0.4",
                "35000",
                quand=MAINTENANT - timedelta(days=10),
            ),
        ]

        corps = (await _importer(client, db_session, regular_user, service_double)).json()

        assert corps["imported_transactions"] == 2
        transactions = (await db_session.execute(select(Transaction))).scalars().all()
        cotes = {t.transaction_type.value for t in transactions}
        assert len(cotes) == 2, f"un achat et une vente attendus, obtenu {cotes}"


class TestFrais:
    async def test_les_frais_sont_reportes(self, client: AsyncClient, regular_user: User, db_session, service_double):
        service_double.trades = [_trade("t1", "BTCEUR", "buy", "0.5", "30000", frais="1.5")]

        await _importer(client, db_session, regular_user, service_double)

        tx = (await db_session.execute(select(Transaction))).scalars().first()
        assert float(tx.fee) == 1.5


class TestIdempotence:
    """Le point le plus important pour le découpage à venir.

    Deux imports successifs ne doivent pas doubler l'historique. Si un
    refactor casse cette propriété, il double des transactions financières.
    """

    async def test_deux_imports_ne_doublent_pas_l_historique(
        self, client: AsyncClient, regular_user: User, db_session, service_double
    ):
        service_double.trades = [_trade("t1", "BTCEUR", "buy", "0.5", "30000")]
        cle = await _cle_api(db_session, regular_user)
        token = create_access_token(subject=str(regular_user.id))

        with patch(
            "app.api.v1.endpoints.api_keys.get_exchange_service",
            return_value=service_double,
        ):
            for _ in range(2):
                reponse = await client.post(
                    f"/api/v1/api-keys/{cle.id}/import-history",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert reponse.status_code == 200

        transactions = (await db_session.execute(select(Transaction))).scalars().all()
        assert len(transactions) == 1, "le second import a dupliqué la transaction"


class TestDoubleDeduplication:
    """La déduplication passe par **deux** chemins, et c'est délibéré.

    `existing_trade_ids` se remplit depuis `Transaction.external_id` *et*
    depuis les notes contenant « trade_id: ». Couper l'un des deux ne change
    rien — vérifié par canari : seule la suppression des deux fait réapparaître
    le doublon.

    Le second chemin existe pour les transactions anciennes, importées avant
    que `external_id` ne soit rempli. Un découpage qui n'en garderait qu'un
    réimporterait cet historique-là.
    """

    async def test_l_identifiant_est_inscrit_dans_les_deux_champs(
        self, client: AsyncClient, regular_user: User, db_session, service_double
    ):
        service_double.trades = [_trade("t1", "BTCEUR", "buy", "0.5", "30000")]

        await _importer(client, db_session, regular_user, service_double)

        tx = (await db_session.execute(select(Transaction))).scalars().first()
        assert "t1" in tx.external_id
        assert tx.notes is not None and "trade_id:" in tx.notes, (
            "les notes portent aussi l'identifiant : c'est le second filet de "
            "déduplication, pour l'historique importé avant `external_id`"
        )


class TestAutorisation:
    async def test_sans_jeton_l_import_est_refuse(self, client: AsyncClient, regular_user: User, db_session):
        cle = await _cle_api(db_session, regular_user)
        reponse = await client.post(f"/api/v1/api-keys/{cle.id}/import-history")
        assert reponse.status_code in (401, 403)

    async def test_cle_inexistante(self, client: AsyncClient, regular_user: User):
        from uuid import uuid4

        token = create_access_token(subject=str(regular_user.id))
        reponse = await client.post(
            f"/api/v1/api-keys/{uuid4()}/import-history",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert reponse.status_code == 404
