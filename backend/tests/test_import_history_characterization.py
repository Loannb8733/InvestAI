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
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import create_access_token, encrypt_api_key
from app.models.api_key import APIKey
from app.models.asset import Asset
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction
from app.models.user import User
from app.services.exchanges.base import ExchangeBalance, ExchangeFiatOrder, ExchangeTrade, ExchangeWithdrawal

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


def _solde(symbole, total, libre=None, bloque="0"):
    total = Decimal(total)
    return ExchangeBalance(
        symbol=symbole,
        free=Decimal(libre) if libre is not None else total,
        locked=Decimal(bloque),
        total=total,
    )


def _retrait(wid, symbole, montant, frais="0"):
    return ExchangeWithdrawal(
        withdrawal_id=wid,
        symbol=symbole,
        amount=Decimal(montant),
        fee=Decimal(frais),
        timestamp=MAINTENANT - timedelta(days=20),
        status="completed",
        tx_id="tx",
        address="adresse",
    )


def _ordre_fiat(oid, symbole, quantite, montant_fiat, prix, frais="0"):
    return ExchangeFiatOrder(
        order_id=oid,
        crypto_symbol=symbole,
        fiat_currency="EUR",
        side="buy",
        crypto_amount=Decimal(quantite),
        fiat_amount=Decimal(montant_fiat),
        price=Decimal(prix),
        fee=Decimal(frais),
        status="completed",
        timestamp=MAINTENANT - timedelta(days=20),
    )


class ServiceDouble:
    """Double du service d'exchange, fidèle au contrat de `base.py`.

    Les taux sont figés (forex à 1, prix historique à 50 000 €) pour que les
    montants attendus soient lisibles : sans cela, chaque assertion de prix
    dépendrait d'une conversion.
    """

    exchange_name = "binance"
    trades: list = []
    balances: list = []
    rewards: list = []
    conversions: list = []
    withdrawals: list = []
    fiat_orders: list = []
    auto_invest: list = []
    # `get_auto_invest_history` est interrogé par fenêtres de 30 jours : sans ce
    # compteur, le double rendrait le même ordre à chaque fenêtre.
    fenetres_auto_invest: int = 0

    def __init__(self, *args, **kwargs):
        pass

    async def get_trades(self, **k):
        return list(type(self).trades)

    async def get_balances(self, **k):
        return list(type(self).balances)

    async def get_fiat_orders(self, **k):
        return list(type(self).fiat_orders)

    async def get_rewards(self, **k):
        return list(type(self).rewards)

    async def get_withdrawals(self, **k):
        return list(type(self).withdrawals)

    async def get_crypto_conversions(self, **k):
        return list(type(self).conversions)

    async def get_instant_buys(self, **k):
        # Seule méthode du contrat à rendre un tuple : (trades, refids).
        return [], set()

    async def get_auto_invest_history(self, **k):
        # Une seule fenêtre porte les ordres : l'exchange ne rend pas le même
        # ordre dans deux tranches de temps disjointes.
        type(self).fenetres_auto_invest += 1
        return list(type(self).auto_invest) if type(self).fenetres_auto_invest == 1 else []

    async def get_convert_history(self, **k):
        return []

    async def get_ledgers(self, **k):
        return []

    async def get_forex_rate(self, *a, **k):
        return 1.0

    async def get_historical_crypto_price(self, *a, **k):
        return 50000.0

    async def get_multiple_crypto_prices(self, *a, **k):
        return {}

    async def close(self):
        pass


@pytest.fixture
def service_double():
    ServiceDouble.trades = []
    ServiceDouble.balances = []
    ServiceDouble.rewards = []
    ServiceDouble.conversions = []
    ServiceDouble.withdrawals = []
    ServiceDouble.fiat_orders = []
    ServiceDouble.auto_invest = []
    ServiceDouble.fenetres_auto_invest = 0
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
    """Lance l'import avec le double, et le cours historique figé.

    Le prix des récompenses et des conversions ne vient **pas** du service
    d'exchange mais de `price_service.get_historical_crypto_price` — donc de
    CoinGecko. Sans ce second patch, le test part sur le réseau, attend 1,5 s
    par prix, et son résultat dépend du cours du jour.
    """
    cle = await _cle_api(db_session, utilisateur)
    token = create_access_token(subject=str(utilisateur.id))
    # Le double est injecté à la frontière `construire_service_exchange`, qui rend
    # une **instance** (l'ancien `get_exchange_service` rendait une classe). C'est
    # le point d'injection qui a changé avec l'extraction, pas le comportement.
    with patch(
        "app.api.v1.endpoints.api_keys.construire_service_exchange",
        return_value=service(),
    ), patch(
        "app.services.price_service.price_service.get_historical_crypto_price",
        new=AsyncMock(return_value=50000.0),
    ):
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
            "app.api.v1.endpoints.api_keys.construire_service_exchange",
            return_value=service_double(),
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


class TestClassificationParPrefixe:
    """Le type d'une transaction se lit sur le **préfixe de `trade_id`**.

    `reward_staking_`, `reward_` (airdrop), `fiat_`, `instant_`, `convert_`,
    `withdrawal_` — tout le reste est un trade spot. C'est la mécanique
    centrale de la fonction, et la plus fragile : un découpage qui perdrait ces
    préfixes reclasserait silencieusement toute l'activité en achats.

    Vérifié par l'exploration : le même objet avec `trade_id="r1"` est importé
    comme spot, avec `trade_id="reward_staking_1"` comme récompense.
    """

    async def test_sans_prefixe_c_est_un_trade_spot(
        self, client: AsyncClient, regular_user: User, db_session, service_double
    ):
        service_double.rewards = [_trade("r1", "BTCEUR", "buy", "0.01", "0")]

        corps = (await _importer(client, db_session, regular_user, service_double)).json()

        assert corps["spot_trades"] == 1
        assert corps["rewards"] == 0, "sans préfixe, la récompense est comptée comme un achat"

    async def test_prefixe_reward_staking(self, client: AsyncClient, regular_user: User, db_session, service_double):
        service_double.rewards = [_trade("reward_staking_1", "BTCEUR", "buy", "0.01", "0")]

        corps = (await _importer(client, db_session, regular_user, service_double)).json()

        assert corps["rewards"] == 1
        assert corps["spot_trades"] == 0
        tx = (await db_session.execute(select(Transaction))).scalars().first()
        assert tx.transaction_type.value == "staking_reward"

    async def test_prefixe_convert(self, client: AsyncClient, regular_user: User, db_session, service_double):
        service_double.conversions = [_trade("convert_1", "ETHEUR", "buy", "1", "2000")]

        corps = (await _importer(client, db_session, regular_user, service_double)).json()

        assert corps["conversions"] == 1
        tx = (await db_session.execute(select(Transaction))).scalars().first()
        assert tx.transaction_type.value == "conversion_in"


class TestRecompenses:
    async def test_le_prix_vient_du_cours_historique(
        self, client: AsyncClient, regular_user: User, db_session, service_double
    ):
        """Une récompense arrive sans prix : il est reconstitué au cours du jour.

        Le double fige `get_historical_crypto_price` à 50 000 € et le forex à 1.
        """
        service_double.rewards = [_trade("reward_staking_1", "BTCEUR", "buy", "0.01", "0")]

        await _importer(client, db_session, regular_user, service_double)

        tx = (await db_session.execute(select(Transaction))).scalars().first()
        assert float(tx.price) == 50000.0
        assert float(tx.quantity) == 0.01


class TestRetraits:
    async def test_un_retrait_produit_deux_ecritures(
        self, client: AsyncClient, regular_user: User, db_session, service_double
    ):
        """Le retrait est **miroité** : une sortie et son entrée correspondante.

        C'est le mécanisme qui avait produit les écritures fantômes de NEW-02 :
        un découpage doit garder les deux écritures ensemble, ou n'en garder
        aucune.
        """
        service_double.withdrawals = [_retrait("w1", "BTC", "0.1")]

        corps = (await _importer(client, db_session, regular_user, service_double)).json()

        assert corps["withdrawals"] == 1
        transactions = (await db_session.execute(select(Transaction))).scalars().all()
        types = sorted(t.transaction_type.value for t in transactions)
        assert types == ["transfer_in", "transfer_out"]

    async def test_les_deux_ecritures_sont_au_prix_zero(
        self, client: AsyncClient, regular_user: User, db_session, service_double
    ):
        """Un transfert n'est pas une cession : il ne porte pas de prix."""
        service_double.withdrawals = [_retrait("w1", "BTC", "0.1")]

        await _importer(client, db_session, regular_user, service_double)

        transactions = (await db_session.execute(select(Transaction))).scalars().all()
        assert all(float(t.price) == 0.0 for t in transactions)
        assert all(float(t.quantity) == 0.1 for t in transactions)


class TestOrdresFiat:
    async def test_un_ordre_fiat_devient_un_achat(
        self, client: AsyncClient, regular_user: User, db_session, service_double
    ):
        service_double.fiat_orders = [_ordre_fiat("f1", "BTC", "0.02", "1000", "50000")]

        corps = (await _importer(client, db_session, regular_user, service_double)).json()

        assert corps["fiat_orders"] == 1
        assert corps["spot_trades"] == 0
        tx = (await db_session.execute(select(Transaction))).scalars().first()
        assert tx.transaction_type.value == "buy"
        assert float(tx.price) == 50000.0

    async def test_le_bloc_debug_compte_les_ordres_recus(
        self, client: AsyncClient, regular_user: User, db_session, service_double
    ):
        """`debug` compte ce que l'exchange a **rendu** ; les compteurs de haut
        niveau comptent ce qui a été **importé**. Les deux peuvent différer."""
        service_double.fiat_orders = [_ordre_fiat("f1", "BTC", "0.02", "1000", "50000")]

        corps = (await _importer(client, db_session, regular_user, service_double)).json()

        assert corps["debug"]["fiat_orders_count"] == 1
        assert corps["debug"]["total_fiat_orders"] == 1


class TestAutoInvest:
    async def test_un_ordre_programme_devient_un_achat(
        self, client: AsyncClient, regular_user: User, db_session, service_double
    ):
        """L'auto-invest rend des `ExchangeFiatOrder`, pas des `ExchangeTrade`.

        Un double qui se trompe de type échoue sur
        `AttributeError: 'ExchangeTrade' object has no attribute 'crypto_symbol'`.
        """
        service_double.auto_invest = [_ordre_fiat("ai1", "BTC", "0.005", "240", "48000")]

        corps = (await _importer(client, db_session, regular_user, service_double)).json()

        assert corps["imported_transactions"] == 1
        assert corps["fiat_orders"] == 1, "l'auto-invest est compté avec les ordres fiat"
        tx = (await db_session.execute(select(Transaction))).scalars().first()
        assert float(tx.price) == 48000.0


class TestDeduplicationIntraImport:
    """La déduplication ne couvre pas les doublons d'un même import.

    `existing_trade_ids` est construit **avant** la boucle, à partir de la base,
    et n'est jamais complété pendant. Deux occurrences du même identifiant dans
    un même flux sont donc insérées deux fois.

    Observé à l'improviste : un double qui rendait le même ordre à chacune des
    fenêtres de 30 jours a produit **28 transactions identiques**. Les fenêtres
    réelles sont disjointes, donc le cas ne devrait pas se présenter — mais rien
    dans le code ne l'empêche, et un découpage ne doit pas croire cette
    protection acquise.
    """

    async def test_deux_fois_le_meme_identifiant_dans_un_import(
        self, client: AsyncClient, regular_user: User, db_session, service_double
    ):
        meme = _trade("t1", "BTCEUR", "buy", "0.5", "30000")
        service_double.trades = [meme, meme]

        corps = (await _importer(client, db_session, regular_user, service_double)).json()

        transactions = (await db_session.execute(select(Transaction))).scalars().all()
        assert len(transactions) == corps["imported_transactions"]
        # Comportement épinglé, non approuvé : le doublon passe.
        assert len(transactions) == 2


class TestSoldesEtRapprochement:
    """Le chemin qui lit `get_balances`, laissé à découvert jusqu'ici.

    Aucun des tests précédents ne fournissait de soldes : la boucle de
    rapprochement n'était donc jamais exécutée. Une extraction a supprimé un
    import dont elle dépendait sans qu'un seul test ne bronche — c'est `flake8`
    qui l'a signalé, pas le filet. Ces tests ferment le trou.
    """

    async def test_un_solde_cree_l_actif_correspondant(
        self, client: AsyncClient, regular_user: User, db_session, service_double
    ):
        service_double.balances = [_solde("BTC", "0.75")]

        corps = (await _importer(client, db_session, regular_user, service_double)).json()

        assert corps["debug"]["balances_count"] == 1
        assert "BTC" in corps["debug"]["balances_symbols"]

    async def test_une_variante_earn_ne_cree_pas_un_second_actif(
        self, client: AsyncClient, regular_user: User, db_session, service_double
    ):
        """`LDUSDC` est de l'USDC placé : un seul actif, pas deux."""
        service_double.balances = [_solde("USDC", "100"), _solde("LDUSDC", "300")]

        await _importer(client, db_session, regular_user, service_double)

        actifs = (await db_session.execute(select(Asset))).scalars().all()
        symboles = sorted(a.symbol for a in actifs)
        assert "LDUSDC" not in symboles, "la variante ne doit pas devenir un actif"

    async def test_les_devises_fiat_ne_deviennent_pas_des_actifs(
        self, client: AsyncClient, regular_user: User, db_session, service_double
    ):
        service_double.balances = [_solde("EUR", "500"), _solde("BTC", "0.1")]

        await _importer(client, db_session, regular_user, service_double)

        actifs = (await db_session.execute(select(Asset))).scalars().all()
        assert "EUR" not in [a.symbol for a in actifs]


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
