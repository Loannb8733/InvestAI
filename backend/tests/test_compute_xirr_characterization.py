"""Tests de caractérisation de `AnalyticsService.compute_xirr`.

Pourquoi ce fichier existe
--------------------------
Le taux de rendement interne est un des chiffres que l'utilisateur regarde pour
juger la performance de son patrimoine. Son **noyau de calcul** est bien
couvert : `_xirr` et `_build_xirr_cashflows` ont leurs tests dorés.

Son **orchestration** ne l'était pas. `compute_xirr` — qui va de la base au
chiffre affiché : lecture des portefeuilles, conversion de devise, valeur
courante, garde-fous, écrêtage — était couverte à 7 %, seules ses premières
lignes étant atteintes. C'est pourtant là que vivent les décisions qui font
qu'un TRI s'affiche, ou pas.

Ces tests épinglent ce qu'elle fait aujourd'hui, avant tout découpage. Ils ne
disent pas ce qu'elle devrait faire.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction, TransactionType
from app.services.analytics_service import AnalyticsService

MAINTENANT = datetime.now(timezone.utc)


@pytest.fixture
def service():
    return AnalyticsService()


async def _portefeuille_avec_achat(db_session, user, quantite="1", prix="10000", il_y_a_jours=365):
    """Un portefeuille, un actif, un achat daté — le minimum pour un TRI."""
    portefeuille = Portfolio(user_id=user.id, name="Crypto", description="test")
    db_session.add(portefeuille)
    await db_session.flush()

    actif = Asset(
        portfolio_id=portefeuille.id,
        symbol="BTC",
        name="Bitcoin",
        asset_type=AssetType.CRYPTO,
        quantity=float(quantite),
        avg_buy_price=float(prix),
        current_price=float(prix),
        currency="EUR",
    )
    db_session.add(actif)
    await db_session.flush()

    achat = Transaction(
        asset_id=actif.id,
        transaction_type=TransactionType.BUY,
        quantity=float(quantite),
        price=float(prix),
        fee=0,
        currency="EUR",
        executed_at=MAINTENANT - timedelta(days=il_y_a_jours),
        external_id="t1",
    )
    db_session.add(achat)
    await db_session.commit()
    return portefeuille, actif


def _valeur_courante(montant: float):
    """Fige la valeur du patrimoine rendue par `metrics_service`."""
    return patch(
        "app.services.metrics_service.metrics_service.get_user_dashboard_metrics",
        new=AsyncMock(return_value={"total_value": montant}),
    )


class TestCasSansResultat:
    """Quatre situations où aucun TRI n'est rendu. Un `None` n'est pas une
    erreur : c'est l'absence de sens, et l'interface doit pouvoir la distinguer
    d'un rendement nul."""

    async def test_aucun_portefeuille(self, service, db_session, regular_user):
        assert await service.compute_xirr(db_session, regular_user.id) is None

    async def test_portefeuille_sans_transaction(self, service, db_session, regular_user):
        db_session.add(Portfolio(user_id=regular_user.id, name="Crypto", description="vide"))
        await db_session.commit()

        assert await service.compute_xirr(db_session, regular_user.id) is None

    async def test_valeur_courante_nulle(self, service, db_session, regular_user):
        """Un patrimoine qui ne vaut plus rien ne donne pas un TRI de −100 % :
        il n'en donne aucun.

        La garde est vérifiée sur le mécanisme, pas sur le résultat : sans elle,
        `_xirr` rendrait `None` de toute façon, faute de converger. Un test qui
        ne regarderait que la valeur rendue ne verrait donc pas sa disparition.
        """
        await _portefeuille_avec_achat(db_session, regular_user)

        with _valeur_courante(0.0), patch("app.services.analytics_service._xirr") as calcul:
            resultat = await service.compute_xirr(db_session, regular_user.id)

        assert resultat is None
        calcul.assert_not_called(), "le calcul doit être court-circuité, pas tenté"

    async def test_aucun_flux_negatif(self, service, db_session, regular_user):
        """Sans sortie d'argent, il n'y a pas d'investissement à rémunérer.

        Une récompense de staking entre sans qu'on ait rien versé.
        """
        portefeuille = Portfolio(user_id=regular_user.id, name="Crypto", description="t")
        db_session.add(portefeuille)
        await db_session.flush()
        actif = Asset(
            portfolio_id=portefeuille.id,
            symbol="BTC",
            name="Bitcoin",
            asset_type=AssetType.CRYPTO,
            quantity=1.0,
            avg_buy_price=0.0,
            current_price=10000.0,
            currency="EUR",
        )
        db_session.add(actif)
        await db_session.flush()
        db_session.add(
            Transaction(
                asset_id=actif.id,
                transaction_type=TransactionType.STAKING_REWARD,
                quantity=1.0,
                price=10000.0,
                fee=0,
                currency="EUR",
                executed_at=MAINTENANT - timedelta(days=200),
                external_id="r1",
            )
        )
        await db_session.commit()

        with _valeur_courante(12000.0), patch("app.services.analytics_service._xirr") as calcul:
            resultat = await service.compute_xirr(db_session, regular_user.id)

        assert resultat is None
        calcul.assert_not_called(), "sans flux négatif, le calcul n'est pas tenté"


class TestCalcul:
    async def test_un_doublement_en_un_an_donne_environ_cent_pour_cent(self, service, db_session, regular_user):
        """10 000 € investis il y a un an, 20 000 € aujourd'hui."""
        await _portefeuille_avec_achat(db_session, regular_user, prix="10000", il_y_a_jours=365)

        with _valeur_courante(20000.0):
            taux = await service.compute_xirr(db_session, regular_user.id)

        assert taux == pytest.approx(100.0, abs=1.0)

    async def test_un_patrimoine_stable_donne_environ_zero(self, service, db_session, regular_user):
        await _portefeuille_avec_achat(db_session, regular_user, prix="10000", il_y_a_jours=365)

        with _valeur_courante(10000.0):
            taux = await service.compute_xirr(db_session, regular_user.id)

        assert taux == pytest.approx(0.0, abs=1.0)

    async def test_le_resultat_est_un_pourcentage_arrondi_au_centieme(self, service, db_session, regular_user):
        await _portefeuille_avec_achat(db_session, regular_user, prix="10000", il_y_a_jours=365)

        with _valeur_courante(15000.0):
            taux = await service.compute_xirr(db_session, regular_user.id)

        assert taux is not None
        assert round(taux, 2) == taux, "le taux est arrondi à deux décimales"


class TestEcretage:
    """Les valeurs aberrantes sont bornées à [−95 %, +1 000 %].

    Un TRI hors de ces bornes signale presque toujours une donnée fausse — une
    date, un prix ou une quantité. Le clamp est journalisé plutôt que silencieux
    (FIN-11), pour que l'anomalie reste visible.
    """

    async def test_un_rendement_delirant_est_borne_a_mille(self, service, db_session, regular_user):
        """1 € investi hier, 1 000 000 € aujourd'hui."""
        await _portefeuille_avec_achat(db_session, regular_user, quantite="1", prix="1", il_y_a_jours=1)

        with _valeur_courante(1_000_000.0):
            taux = await service.compute_xirr(db_session, regular_user.id)

        assert taux == 1000.0

    async def test_une_perte_de_95_pour_cent_touche_la_borne_basse(self, service, db_session, regular_user):
        """10 000 € investis il y a un an, 500 € aujourd'hui : le calcul donne
        −95,01 %, juste sous la borne, donc écrêté à −95."""
        await _portefeuille_avec_achat(db_session, regular_user, prix="10000", il_y_a_jours=365)

        with _valeur_courante(500.0):
            taux = await service.compute_xirr(db_session, regular_user.id)

        assert taux == -95.0

    @pytest.mark.parametrize("reste", [100.0, 1.0, 0.01])
    async def test_une_perte_plus_grave_ne_donne_aucun_taux(self, service, db_session, regular_user, reste):
        """Comportement contre-intuitif, épinglé sans être approuvé.

        Au-delà de 95 % de perte, `_xirr` ne converge plus et rend `None` :
        l'utilisateur qui a le plus perdu ne voit **aucun** taux, là où une
        perte de 95 % en affiche un. La borne basse ne protège donc que d'une
        bande étroite ; au-delà, c'est l'absence de résultat qui fait office
        de garde-fou.
        """
        await _portefeuille_avec_achat(db_session, regular_user, prix="10000", il_y_a_jours=365)

        with _valeur_courante(reste):
            assert await service.compute_xirr(db_session, regular_user.id) is None


class TestDevise:
    async def test_l_euro_ne_demande_aucune_conversion(self, service, db_session, regular_user):
        await _portefeuille_avec_achat(db_session, regular_user)
        appels = AsyncMock(return_value=1.1)

        with _valeur_courante(20000.0), patch.object(service.price_service, "get_forex_rate", appels):
            await service.compute_xirr(db_session, regular_user.id, currency="EUR")

        appels.assert_not_called()

    async def test_une_autre_devise_demande_le_taux(self, service, db_session, regular_user):
        await _portefeuille_avec_achat(db_session, regular_user)
        taux_change = AsyncMock(return_value=1.1)

        with _valeur_courante(20000.0), patch.object(service.price_service, "get_forex_rate", taux_change):
            await service.compute_xirr(db_session, regular_user.id, currency="USD")

        taux_change.assert_awaited_once_with("EUR", "USD")

    async def test_un_taux_indisponible_ne_fait_pas_echouer_le_calcul(self, service, db_session, regular_user):
        """Le service de change peut tomber ; le TRI reste calculé à taux 1."""
        await _portefeuille_avec_achat(db_session, regular_user)

        with _valeur_courante(20000.0), patch.object(
            service.price_service, "get_forex_rate", AsyncMock(side_effect=Exception("réseau"))
        ):
            taux = await service.compute_xirr(db_session, regular_user.id, currency="USD")

        assert taux is not None


class TestRepliSurLesPrixDesActifs:
    async def test_metrics_indisponible_le_calcul_se_poursuit(self, service, db_session, regular_user):
        """Si `metrics_service` échoue, la valeur est reconstituée actif par
        actif. Le TRI est rendu quand même, plutôt que perdu."""
        await _portefeuille_avec_achat(db_session, regular_user, quantite="1", prix="10000")

        with patch(
            "app.services.metrics_service.metrics_service.get_user_dashboard_metrics",
            new=AsyncMock(side_effect=Exception("indisponible")),
        ), patch.object(service, "_get_asset_price", new=AsyncMock(return_value=20000.0)), patch.object(
            service.price_service, "get_forex_rate", new=AsyncMock(return_value=1.0)
        ):
            taux = await service.compute_xirr(db_session, regular_user.id)

        assert taux is not None
        assert taux == pytest.approx(100.0, abs=1.0)
