"""Caractérisation de `_compute_user_dashboard_metrics`.

Pourquoi ce fichier existe
--------------------------
C'est la fonction qui compose l'écran principal : valeur du patrimoine, capital
net, plus-value latente et réalisée, répartition, meilleures et pires lignes.
281 lignes, couvertes à **3 %**.

Elle n'est pas atteignable simplement : elle agrège trois sources — les
métriques par portefeuille, l'historique, et les variations de période — dont
la première fait à elle seule 831 lignes. Les figer suffit à rendre le calcul
déterministe, et c'est ce qui permet de le vérifier.

Deux pièges de double, rencontrés en écrivant ces tests :
`get_portfolio_history` rend un **dictionnaire**, pas une liste ; et un actif
porte `total_invested`, pas `invested`. Un double infidèle échoue sur un
`TypeError` ou un `KeyError` qui semblent venir du code.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.services.metrics_service import metrics_service


def _actif(symbole, valeur, investi, quantite=1.0, type_actif="crypto"):
    return {
        "symbol": symbole,
        "name": symbole,
        "asset_type": type_actif,
        "current_value": valeur,
        "total_invested": investi,
        "gain_loss": valeur - investi,
        "quantity": quantite,
        "current_price": valeur / quantite if quantite else 0.0,
        "risk_weight": 0,
    }


def _metriques(actifs, cash_stable=0.0, cash_fiat=0.0):
    valeur = sum(a["current_value"] for a in actifs)
    investi = sum(a["total_invested"] for a in actifs)
    return {
        "total_value": valeur,
        "total_invested": investi,
        "total_gain_loss": valeur - investi,
        "total_gain_loss_percent": ((valeur - investi) / investi * 100) if investi else 0.0,
        "asset_count": len(actifs),
        "assets": actifs,
        "cash_from_stablecoins": cash_stable,
        "cash_from_fiat": cash_fiat,
    }


def _historique(investi_total, vendu=0.0, realise=0.0, frais=0.0):
    return {
        "total_invested_all_time": investi_total,
        "total_sold_fiat": vendu,
        "realized_gains": realise,
        "total_fees": frais,
    }


async def _portefeuille(db_session, user):
    portefeuille = Portfolio(user_id=user.id, name="Crypto", description="test")
    db_session.add(portefeuille)
    await db_session.flush()
    db_session.add(
        Asset(
            portfolio_id=portefeuille.id,
            symbol="BTC",
            name="Bitcoin",
            asset_type=AssetType.CRYPTO,
            quantity=1.0,
            avg_buy_price=20000.0,
            current_price=30000.0,
            currency="EUR",
        )
    )
    await db_session.commit()
    return portefeuille


def _figer(metriques, historique, variations=None):
    """Fige les trois sources agrégées par le calcul."""
    return (
        patch.object(metrics_service, "get_portfolio_metrics", new=AsyncMock(return_value=metriques)),
        patch.object(metrics_service, "get_portfolio_history", new=AsyncMock(return_value=historique)),
        patch.object(metrics_service, "_fetch_period_changes", new=AsyncMock(return_value=variations or {})),
    )


async def _calculer(db_session, user, metriques, historique, variations=None, devise="EUR", jours=30):
    a, b, c = _figer(metriques, historique, variations)
    with a, b, c:
        return await metrics_service._compute_user_dashboard_metrics(db_session, str(user.id), devise, jours)


class TestFormeDeLaReponse:
    async def test_les_vingt_et_une_cles_attendues_par_le_dashboard(self, db_session, regular_user):
        """L'écran principal lit ces clés : en perdre une le casse."""
        await _portefeuille(db_session, regular_user)
        actifs = [_actif("BTC", 30000.0, 20000.0)]

        resultat = await _calculer(db_session, regular_user, _metriques(actifs), _historique(20000.0))

        assert set(resultat) == {
            "aggregated_assets",
            "allocation",
            "assets_count",
            "available_liquidity",
            "daily_change",
            "daily_change_percent",
            "forex_stale",
            "net_capital",
            "net_gain_loss",
            "net_gain_loss_percent",
            "period_change",
            "period_change_percent",
            "period_changes",
            "pnl_data",
            "portfolios_count",
            "top_performers",
            "total_gain_loss",
            "total_gain_loss_percent",
            "total_invested",
            "total_value",
            "worst_performers",
        }


class TestAgregation:
    async def test_la_valeur_et_l_investi_remontent_tels_quels(self, db_session, regular_user):
        await _portefeuille(db_session, regular_user)
        actifs = [_actif("BTC", 30000.0, 20000.0)]

        resultat = await _calculer(db_session, regular_user, _metriques(actifs), _historique(20000.0))

        assert resultat["total_value"] == 30000.0
        assert resultat["total_invested"] == 20000.0
        assert resultat["total_gain_loss"] == 10000.0
        assert resultat["total_gain_loss_percent"] == pytest.approx(50.0)

    async def test_plusieurs_lignes_sont_additionnees(self, db_session, regular_user):
        await _portefeuille(db_session, regular_user)
        actifs = [_actif("BTC", 30000.0, 20000.0), _actif("ETH", 10000.0, 12000.0, quantite=5.0)]

        resultat = await _calculer(db_session, regular_user, _metriques(actifs), _historique(32000.0))

        assert resultat["total_value"] == 40000.0
        assert resultat["total_invested"] == 32000.0
        assert resultat["total_gain_loss"] == 8000.0

    async def test_un_meme_symbole_sur_deux_lignes_est_regroupe(self, db_session, regular_user):
        """Le même actif détenu sur deux plateformes ne doit apparaître qu'une
        fois à l'écran, quantités cumulées."""
        await _portefeuille(db_session, regular_user)
        actifs = [_actif("BTC", 30000.0, 20000.0), _actif("BTC", 15000.0, 10000.0, quantite=0.5)]

        resultat = await _calculer(db_session, regular_user, _metriques(actifs), _historique(30000.0))

        regroupes = resultat["aggregated_assets"]
        assert len(regroupes) == 1
        assert regroupes[0]["symbol"] == "BTC"
        assert regroupes[0]["current_value"] == pytest.approx(45000.0)
        assert regroupes[0]["total_invested"] == pytest.approx(30000.0)
        # `total_quantity` sert au calcul mais n'est pas publié : c'est
        # `avg_buy_price` qui porte la trace du regroupement — 30 000 € investis
        # pour 1,5 unité cumulée.
        assert regroupes[0]["avg_buy_price"] == pytest.approx(20000.0)


class TestCapitalNet:
    async def test_sans_vente_le_capital_net_est_l_investi(self, db_session, regular_user):
        await _portefeuille(db_session, regular_user)
        actifs = [_actif("BTC", 30000.0, 20000.0)]

        resultat = await _calculer(db_session, regular_user, _metriques(actifs), _historique(20000.0))

        assert resultat["net_capital"] == 20000.0

    async def test_une_vente_diminue_le_capital_net(self, db_session, regular_user):
        """Le capital net, c'est ce qui reste engagé : l'argent ressorti n'en
        fait plus partie."""
        await _portefeuille(db_session, regular_user)
        actifs = [_actif("BTC", 30000.0, 20000.0)]

        resultat = await _calculer(db_session, regular_user, _metriques(actifs), _historique(20000.0, vendu=5000.0))

        assert resultat["net_capital"] == 15000.0


class TestClassements:
    async def test_les_meilleures_et_pires_lignes_sont_separees(self, db_session, regular_user):
        await _portefeuille(db_session, regular_user)
        actifs = [
            _actif("BTC", 30000.0, 20000.0),  # +50 %
            _actif("ETH", 8000.0, 10000.0, quantite=5.0),  # −20 %
        ]

        resultat = await _calculer(db_session, regular_user, _metriques(actifs), _historique(30000.0))

        meilleurs = [a["symbol"] for a in resultat["top_performers"]]
        pires = [a["symbol"] for a in resultat["worst_performers"]]
        assert meilleurs[0] == "BTC"
        assert pires[0] == "ETH"


class TestRepartition:
    async def test_l_allocation_couvre_les_lignes_detenues(self, db_session, regular_user):
        await _portefeuille(db_session, regular_user)
        actifs = [_actif("BTC", 30000.0, 20000.0), _actif("ETH", 10000.0, 12000.0, quantite=5.0)]

        resultat = await _calculer(db_session, regular_user, _metriques(actifs), _historique(32000.0))

        assert resultat["allocation"], "la répartition alimente le camembert du dashboard"
        assert resultat["assets_count"] == 2
        assert resultat["portfolios_count"] == 1


class TestPatrimoineVide:
    async def test_un_compte_sans_actif_rend_des_zeros(self, db_session, regular_user):
        """Un compte neuf doit afficher un dashboard, pas une erreur."""
        await _portefeuille(db_session, regular_user)

        resultat = await _calculer(db_session, regular_user, _metriques([]), _historique(0.0))

        assert resultat["total_value"] == 0.0
        assert resultat["total_invested"] == 0.0
        assert resultat["assets_count"] == 0
        assert resultat["aggregated_assets"] == []
