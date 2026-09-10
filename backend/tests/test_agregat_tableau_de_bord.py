"""Filet sur l'agrégat qui produit tous les chiffres de l'écran d'accueil.

`_get_dashboard_impl` fait **465 lignes** et n'avait aucun test. C'est elle qui
assemble la réponse du tableau de bord : elle appelle une demi-douzaine de
services, puis prend une série de décisions qui n'existent nulle part ailleurs —
la résolution de « depuis le début », le calcul des positions en staking et de
leur rendement, la répartition par devise, le déclenchement de l'instantané
quotidien.

Ce que le filet double : les quatre appels lourds (métriques, série historique,
indices de marché, métriques de risque) et le taux de change, qui sortent tous
sur le réseau. Ce qu'il laisse s'exécuter : la base de test, et **toutes** les
décisions propres à cette fonction — c'est précisément ce qu'on vient éprouver.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from app.api.v1.endpoints.dashboard import _get_dashboard_impl
from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.models.transaction import Transaction, TransactionType
from app.models.user import User

MAINTENANT = datetime.now(timezone.utc)


def actif_agrege(symbole: str, valeur: float, quantite: float, *, investi: float | None = None) -> dict:
    """Une ligne de `aggregated_assets`, telle que le service de métriques la rend."""
    investi = valeur if investi is None else investi
    return {
        "symbol": symbole,
        "name": symbole,
        "asset_type": "crypto",
        "current_value": valeur,
        "percentage": 100.0,
        "gain_loss_percent": 0.0,
        "avg_buy_price": investi / quantite if quantite else 0.0,
        "quantity": quantite,
        "current_price": valeur / quantite if quantite else 0.0,
    }


def metriques(agreges: list[dict] | None = None, **surcharge) -> dict:
    agreges = agreges if agreges is not None else []
    valeur = sum(a["current_value"] for a in agreges)
    base = {
        "total_value": valeur,
        "total_invested": valeur,
        "net_capital": valeur,
        "total_gain_loss": 0.0,
        "total_gain_loss_percent": 0.0,
        "daily_change": 0.0,
        "daily_change_percent": 0.0,
        "portfolios_count": 1,
        "assets_count": len(agreges),
        "allocation": [],
        "aggregated_assets": agreges,
        "assets": [],
        "top_performers": [],
        "worst_performers": [],
        "pnl_data": {},
        "available_liquidity": 0.0,
        "total_dividend_income": 0.0,
        "total_return": 0.0,
    }
    base.update(surcharge)
    return base


RISQUES = {
    "volatility": 0.0,
    "sharpe_ratio": 0.0,
    "max_drawdown": {"max_drawdown_percent": 0.0},
    "var_95": {"var_percent": 0.0, "var_amount": 0.0, "confidence_level": 95},
    "concentration": {"hhi": 0.0, "interpretation": "N/A", "is_concentrated": False},
}


async def appeler(db_session, utilisateur, *, jours=30, mesures=None, historique=None, taux_usd=0.92):
    """Appelle l'agrégat en ne doublant que ce qui sort sur le réseau."""
    mesures = mesures if mesures is not None else metriques()
    historique = historique if historique is not None else []
    with (
        patch(
            "app.api.v1.endpoints.dashboard.metrics_service.get_user_dashboard_metrics",
            new=AsyncMock(return_value=mesures),
        ),
        patch(
            "app.api.v1.endpoints.dashboard.snapshot_service.build_portfolio_value_series",
            new=AsyncMock(return_value=historique),
        ),
        patch("app.api.v1.endpoints.dashboard.get_index_comparison", new=AsyncMock(return_value=[])),
        patch(
            "app.api.v1.endpoints.dashboard.snapshot_service.get_all_risk_metrics",
            new=AsyncMock(return_value=RISQUES),
        ),
        patch(
            "app.services.price_service.PriceService._get_eur_usd_rate",
            new=AsyncMock(return_value=taux_usd),
        ),
    ):
        return await _get_dashboard_impl(None, jours, utilisateur, db_session)


@pytest.fixture
async def portefeuille(db_session, regular_user: User) -> Portfolio:
    p = Portfolio(user_id=regular_user.id, name="Crypto")
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


async def _actif(db_session, portefeuille, symbole="BTC", *, devise="EUR", type_=AssetType.CRYPTO) -> Asset:
    a = Asset(
        portfolio_id=portefeuille.id,
        symbol=symbole,
        name=symbole,
        asset_type=type_,
        quantity=Decimal("1"),
        avg_buy_price=Decimal("100"),
        currency=devise,
    )
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    return a


async def _mouvement(db_session, actif, type_, quantite, *, quand=MAINTENANT):
    db_session.add(
        Transaction(
            asset_id=actif.id,
            transaction_type=type_,
            quantity=Decimal(str(quantite)),
            price=Decimal("100"),
            fee=Decimal("0"),
            currency="EUR",
            executed_at=quand,
        )
    )
    await db_session.commit()


class TestResolutionDeLaPeriode:
    async def test_depuis_le_debut_part_de_la_premiere_transaction(self, db_session, regular_user, portefeuille):
        """`days=0` n'est pas une période : c'est « tout l'historique ».

        Il faut le résoudre en un nombre de jours réel avant d'interroger les
        séries, sans quoi elles ne rendraient rien.
        """
        actif = await _actif(db_session, portefeuille)
        await _mouvement(db_session, actif, TransactionType.BUY, 1, quand=MAINTENANT - timedelta(days=200))

        reponse = await appeler(db_session, regular_user, jours=0)

        assert reponse.period_days == 201
        assert reponse.period_label == "Depuis le début"

    async def test_un_historique_trop_court_est_porte_a_sept_jours(self, db_session, regular_user, portefeuille):
        # En dessous d'une semaine, aucune série n'a de sens : le plancher évite
        # de demander une fenêtre d'un jour au lendemain du premier achat.
        actif = await _actif(db_session, portefeuille)
        await _mouvement(db_session, actif, TransactionType.BUY, 1, quand=MAINTENANT - timedelta(days=1))

        assert (await appeler(db_session, regular_user, jours=0)).period_days == 7

    async def test_sans_aucune_transaction_la_periode_vaut_trente_jours(self, db_session, regular_user, portefeuille):
        assert (await appeler(db_session, regular_user, jours=0)).period_days == 30

    async def test_une_periode_explicite_est_conservee(self, db_session, regular_user, portefeuille):
        reponse = await appeler(db_session, regular_user, jours=90)

        assert reponse.period_days == 90
        assert reponse.period_label != "Depuis le début"


class TestVariationDeLaPeriode:
    async def test_depuis_le_debut_compare_le_patrimoine_a_l_investi(self, db_session, regular_user, portefeuille):
        """Sur « tout », la variation est le vrai gain, non une moyenne de cours.

        Pour les autres périodes, le service de métriques rend une moyenne
        pondérée des variations de prix ; sur l'ensemble de l'historique, cette
        moyenne n'aurait aucun sens face aux dépôts successifs.
        """
        mesures = metriques(total_value=15000.0, total_invested=10000.0, assets_count=1)

        reponse = await appeler(db_session, regular_user, jours=0, mesures=mesures)

        assert reponse.period_change == 5000.0
        assert reponse.period_change_percent == 50.0

    async def test_sans_investissement_la_variation_reste_nulle(self, db_session, regular_user, portefeuille):
        # Éviter la division par zéro sur un portefeuille reçu par transfert.
        mesures = metriques(total_value=15000.0, total_invested=0.0)

        reponse = await appeler(db_session, regular_user, jours=0, mesures=mesures)

        assert (reponse.period_change, reponse.period_change_percent) == (0.0, 0.0)


class TestStakingEtRendement:
    async def test_le_staking_net_deduit_les_sorties(self, db_session, regular_user, portefeuille):
        actif = await _actif(db_session, portefeuille, "ETH")
        await _mouvement(db_session, actif, TransactionType.STAKING, 10)
        await _mouvement(db_session, actif, TransactionType.UNSTAKING, 4)
        mesures = metriques([actif_agrege("ETH", valeur=12000.0, quantite=6.0)])

        reponse = await appeler(db_session, regular_user, mesures=mesures)

        assert reponse.earn_summary is not None
        assert reponse.earn_summary.assets[0].staked_quantity == 6.0

    async def test_un_staking_entierement_defait_disparait(self, db_session, regular_user, portefeuille):
        """Une position soldée ne doit pas rester affichée à zéro.

        Deux gardes se superposent ici et une seule agit : le `max(0, …)`
        appliqué à la somme, puis le `if staked_qty <= 0: continue` de la
        boucle. Retirer le premier ne change rien — une quantité négative est
        écartée par le second aussi sûrement qu'une quantité nulle. La borne est
        inerte ; c'est le filtre de la boucle que ce test éprouve.
        """
        actif = await _actif(db_session, portefeuille, "ETH")
        await _mouvement(db_session, actif, TransactionType.STAKING, 5)
        await _mouvement(db_session, actif, TransactionType.UNSTAKING, 9)

        assert (await appeler(db_session, regular_user)).earn_summary is None

    async def test_sans_position_en_staking_il_n_y_a_pas_de_bloc_earn(self, db_session, regular_user, portefeuille):
        assert (await appeler(db_session, regular_user)).earn_summary is None

    async def test_la_position_est_valorisee_au_prix_de_l_actif(self, db_session, regular_user, portefeuille):
        actif = await _actif(db_session, portefeuille, "ETH")
        await _mouvement(db_session, actif, TransactionType.STAKING, 2)
        # 6 ETH valant 12 000 € → 2 000 € l'unité, donc 4 000 € pour 2 stakés.
        mesures = metriques([actif_agrege("ETH", valeur=12000.0, quantite=6.0)])

        reponse = await appeler(db_session, regular_user, mesures=mesures)

        assert reponse.earn_summary.total_staked_value == pytest.approx(4000.0)

    async def test_un_stablecoin_est_valorise_au_taux_de_change(self, db_session, regular_user, portefeuille):
        """Un stablecoin absent des positions garde une valeur connue.

        Sans cette règle, une position en USDC placée en Earn — donc hors du
        solde courant — serait comptée à zéro euro.
        """
        actif = await _actif(db_session, portefeuille, "USDC")
        await _mouvement(db_session, actif, TransactionType.STAKING, 1000)

        reponse = await appeler(db_session, regular_user, taux_usd=0.9)

        assert reponse.earn_summary.total_staked_value == pytest.approx(900.0)

    async def test_un_jeton_au_prix_inconnu_est_compte_pour_rien(self, db_session, regular_user, portefeuille):
        # Faute de cours, mieux vaut zéro qu'un chiffre inventé : la ligne reste
        # visible, sa valeur ne gonfle pas le total.
        actif = await _actif(db_session, portefeuille, "OBSCUR")
        await _mouvement(db_session, actif, TransactionType.STAKING, 50)

        reponse = await appeler(db_session, regular_user)

        assert reponse.earn_summary.total_staked_value == 0.0
        assert reponse.earn_summary.assets[0].symbol == "OBSCUR"

    async def test_les_positions_sont_classees_de_la_plus_grosse_a_la_plus_petite(
        self, db_session, regular_user, portefeuille
    ):
        eth = await _actif(db_session, portefeuille, "ETH")
        usdc = await _actif(db_session, portefeuille, "USDC")
        await _mouvement(db_session, eth, TransactionType.STAKING, 1)
        await _mouvement(db_session, usdc, TransactionType.STAKING, 10000)
        mesures = metriques([actif_agrege("ETH", valeur=2000.0, quantite=1.0)])

        reponse = await appeler(db_session, regular_user, mesures=mesures, taux_usd=1.0)

        assert [a.symbol for a in reponse.earn_summary.assets] == ["USDC", "ETH"]

    async def test_le_rendement_annualise_rapporte_les_gains_a_leur_duree(self, db_session, regular_user, portefeuille):
        """365 jours de récompenses pour 10 % de la position ⇒ 10 % l'an.

        Le même montant gagné en six mois vaudrait le double en rythme annuel :
        c'est la division par la durée qui rend les deux comparables.
        """
        actif = await _actif(db_session, portefeuille, "ETH")
        await _mouvement(db_session, actif, TransactionType.STAKING, 10)
        await _mouvement(db_session, actif, TransactionType.STAKING_REWARD, 1, quand=MAINTENANT - timedelta(days=365))
        mesures = metriques([actif_agrege("ETH", valeur=10000.0, quantite=10.0)])

        reponse = await appeler(db_session, regular_user, mesures=mesures)

        assert reponse.earn_summary.total_rewards == pytest.approx(1000.0)
        assert reponse.earn_summary.apr == pytest.approx(10.0, abs=0.2)


class TestExpositionParDevise:
    async def test_une_crypto_ordinaire_expose_au_dollar(self, db_session, regular_user, portefeuille):
        mesures = metriques(assets=[{"id": "x", "asset_type": "crypto", "symbol": "BTC", "current_value": 1000.0}])

        reponse = await appeler(db_session, regular_user, mesures=mesures)

        assert [(e.currency, e.percentage) for e in reponse.currency_exposure] == [("USD", 100.0)]

    async def test_l_or_tokenise_n_est_pas_une_exposition_au_dollar(self, db_session, regular_user, portefeuille):
        """PAXG suit l'once d'or, pas le billet vert.

        Le compter en USD masquait la seule ligne du portefeuille qui protège
        justement du risque de change.
        """
        mesures = metriques(assets=[{"id": "x", "asset_type": "crypto", "symbol": "PAXG", "current_value": 500.0}])

        reponse = await appeler(db_session, regular_user, mesures=mesures)

        assert reponse.currency_exposure[0].currency == "OR"

    async def test_un_stablecoin_expose_a_sa_devise_d_ancrage(self, db_session, regular_user, portefeuille):
        mesures = metriques(
            assets=[
                {"id": "a", "asset_type": "crypto", "symbol": "USDC", "current_value": 600.0},
                {"id": "b", "asset_type": "crypto", "symbol": "EURC", "current_value": 400.0},
            ]
        )

        reponse = await appeler(db_session, regular_user, mesures=mesures)

        expositions = {e.currency: e.value for e in reponse.currency_exposure}
        assert expositions["USD"] == 600.0
        assert expositions.get("EUR") == 400.0

    async def test_une_action_suit_la_devise_enregistree_sur_l_actif(self, db_session, regular_user, portefeuille):
        actif = await _actif(db_session, portefeuille, "AAPL", devise="usd", type_=AssetType.STOCK)
        mesures = metriques(
            assets=[{"id": str(actif.id), "asset_type": "stock", "symbol": "AAPL", "current_value": 800.0}]
        )

        reponse = await appeler(db_session, regular_user, mesures=mesures)

        assert reponse.currency_exposure[0].currency == "USD"

    async def test_les_lignes_sans_valeur_sont_ignorees(self, db_session, regular_user, portefeuille):
        """Une position soldée n'ajoute pas sa devise au graphique.

        La ligne à zéro porte ici un **stablecoin euro** : si elle passait le
        filtre, une exposition « EUR » à 0 % apparaîtrait à côté du dollar. Une
        seconde ligne en dollar ne prouverait rien, sa devise étant déjà là.
        """
        mesures = metriques(
            assets=[
                {"id": "a", "asset_type": "crypto", "symbol": "BTC", "current_value": 1000.0},
                {"id": "b", "asset_type": "crypto", "symbol": "EURC", "current_value": 0.0},
            ]
        )

        reponse = await appeler(db_session, regular_user, mesures=mesures)

        assert [e.currency for e in reponse.currency_exposure] == ["USD"]

    async def test_sans_actif_la_repartition_est_vide(self, db_session, regular_user, portefeuille):
        assert (await appeler(db_session, regular_user)).currency_exposure == []


class TestInstantaneQuotidien:
    async def test_un_instantane_est_pose_a_la_premiere_consultation(self, db_session, regular_user, portefeuille):
        """Le tableau de bord alimente lui-même l'historique qu'il affiche.

        Sans cet enregistrement, les séries de valeur n'auraient de points que
        ceux de la tâche planifiée nocturne.
        """
        mesures = metriques(total_value=5000.0, total_invested=4000.0, assets_count=1, total_gain_loss=1000.0)

        await appeler(db_session, regular_user, mesures=mesures)

        compte = await db_session.execute(
            select(func.count()).select_from(PortfolioSnapshot).where(PortfolioSnapshot.user_id == regular_user.id)
        )
        assert compte.scalar() == 1

    async def test_deux_consultations_le_meme_jour_n_en_posent_qu_un(self, db_session, regular_user, portefeuille):
        mesures = metriques(total_value=5000.0, total_invested=4000.0, assets_count=1, total_gain_loss=1000.0)

        await appeler(db_session, regular_user, mesures=mesures)
        await appeler(db_session, regular_user, mesures=mesures)

        compte = await db_session.execute(
            select(func.count()).select_from(PortfolioSnapshot).where(PortfolioSnapshot.user_id == regular_user.id)
        )
        assert compte.scalar() == 1

    async def test_un_portefeuille_vide_ne_laisse_pas_de_trace(self, db_session, regular_user, portefeuille):
        await appeler(db_session, regular_user, mesures=metriques(assets_count=0))

        compte = await db_session.execute(
            select(func.count()).select_from(PortfolioSnapshot).where(PortfolioSnapshot.user_id == regular_user.id)
        )
        assert compte.scalar() == 0


class TestQualiteDesDonnees:
    async def test_une_serie_trop_creuse_est_signalee_comme_estimee(self, db_session, regular_user, portefeuille):
        """Moins d'un tiers des points attendus : le graphique est une esquisse.

        Le signaler évite qu'une courbe reconstituée à partir de trois points
        soit lue comme une mesure.
        """
        serie = [{"date": "2026-01-01", "value": 100.0, "net_capital": 100.0}]

        reponse = await appeler(db_session, regular_user, jours=90, historique=serie)

        assert reponse.is_data_estimated is True
        assert all(p.is_estimated for p in reponse.historical_data)

    async def test_une_periode_courte_n_est_jamais_declaree_estimee(self, db_session, regular_user, portefeuille):
        # Sur sept jours ou moins, le peu de points est normal.
        reponse = await appeler(db_session, regular_user, jours=7, historique=[])

        assert reponse.is_data_estimated is False


class TestRendementAnnualise:
    async def test_moins_de_six_mois_ne_donne_pas_de_rendement_annualise(self, db_session, regular_user, portefeuille):
        """Annualiser trois mois de hausse produirait un chiffre absurde.

        Un gain de 10 % sur un trimestre deviendrait « +46 % l'an » — une
        projection, pas une mesure.
        """
        actif = await _actif(db_session, portefeuille)
        await _mouvement(db_session, actif, TransactionType.BUY, 1, quand=MAINTENANT - timedelta(days=60))
        mesures = metriques(total_value=11000.0, total_invested=10000.0, net_capital=10000.0)

        reponse = await appeler(db_session, regular_user, jours=60, mesures=mesures)

        assert reponse.advanced_metrics.roi_annualized is None

    async def test_au_dela_de_six_mois_le_rendement_est_annualise(self, db_session, regular_user, portefeuille):
        actif = await _actif(db_session, portefeuille)
        await _mouvement(db_session, actif, TransactionType.BUY, 1, quand=MAINTENANT - timedelta(days=730))
        # 10 000 € devenus 12 100 € en deux ans : 10 % par an.
        mesures = metriques(total_value=12100.0, total_invested=10000.0, net_capital=10000.0)

        reponse = await appeler(db_session, regular_user, jours=730, mesures=mesures)

        assert reponse.advanced_metrics.roi_annualized == pytest.approx(10.0, abs=0.3)

    async def test_sans_investissement_il_n_y_a_rien_a_annualiser(self, db_session, regular_user, portefeuille):
        mesures = metriques(total_value=500.0, total_invested=0.0, net_capital=0.0)

        reponse = await appeler(db_session, regular_user, mesures=mesures)

        assert reponse.advanced_metrics.roi_annualized is None


class TestResistanceDesBlocsSecondaires:
    """L'écran d'accueil ne doit pas tomber pour un graphique.

    Constaté en production le 2026-09-10 : `/api/v1/dashboard` répondait 500,
    et l'utilisateur perdait **tout** — patrimoine, transactions, alertes —
    sans qu'aucun message ne dise pourquoi. La réponse assemble une douzaine de
    blocs, dont la plupart ne portent que des graphiques ou des indicateurs
    d'analyse ; l'échec de l'un d'eux emportait les autres.

    Ces tests posent la frontière : ce qui est secondaire dégrade et se
    journalise en ERREUR ; ce qui est le cœur — la valeur du patrimoine —
    continue de faire échouer la requête, parce qu'un tableau de bord qui
    afficherait de faux montants serait pire qu'un tableau de bord absent.
    """

    async def _appeler_avec_panne(self, db_session, utilisateur, cible, **surcharges):
        mesures = surcharges.pop("mesures", None) or metriques()
        patches = {
            "app.api.v1.endpoints.dashboard.metrics_service.get_user_dashboard_metrics": AsyncMock(
                return_value=mesures
            ),
            "app.api.v1.endpoints.dashboard.snapshot_service.build_portfolio_value_series": AsyncMock(return_value=[]),
            "app.api.v1.endpoints.dashboard.get_index_comparison": AsyncMock(return_value=[]),
            "app.api.v1.endpoints.dashboard.snapshot_service.get_all_risk_metrics": AsyncMock(return_value=RISQUES),
            "app.services.price_service.PriceService._get_eur_usd_rate": AsyncMock(return_value=0.92),
        }
        patches[cible] = AsyncMock(side_effect=RuntimeError("panne simulée"))
        contextes = [patch(nom, new=double) for nom, double in patches.items()]
        for c in contextes:
            c.__enter__()
        try:
            return await _get_dashboard_impl(None, 30, utilisateur, db_session)
        finally:
            for c in reversed(contextes):
                c.__exit__(None, None, None)

    async def test_une_serie_de_valeur_en_panne_laisse_l_ecran_debout(self, db_session, regular_user, portefeuille):
        mesures = metriques(total_value=5000.0, total_invested=4000.0, assets_count=3)

        reponse = await self._appeler_avec_panne(
            db_session,
            regular_user,
            "app.api.v1.endpoints.dashboard.snapshot_service.build_portfolio_value_series",
            mesures=mesures,
        )

        assert reponse.total_value == 5000.0
        assert reponse.assets_count == 3
        assert reponse.historical_data == []

    async def test_des_indices_de_marche_en_panne_laissent_l_ecran_debout(self, db_session, regular_user, portefeuille):
        mesures = metriques(total_value=5000.0, total_invested=4000.0)

        reponse = await self._appeler_avec_panne(
            db_session,
            regular_user,
            "app.api.v1.endpoints.dashboard.get_index_comparison",
            mesures=mesures,
        )

        assert reponse.total_value == 5000.0
        assert reponse.index_comparison == []

    async def test_des_metriques_de_risque_en_panne_laissent_l_ecran_debout(
        self, db_session, regular_user, portefeuille
    ):
        """Volatilité, Sharpe, VaR, concentration : de l'analyse, pas le patrimoine.

        La carte affiche des valeurs neutres et une concentration
        « Indisponible » — visible à l'écran, plutôt qu'un écran vide.
        """
        mesures = metriques(total_value=5000.0, total_invested=4000.0)

        reponse = await self._appeler_avec_panne(
            db_session,
            regular_user,
            "app.api.v1.endpoints.dashboard.snapshot_service.get_all_risk_metrics",
            mesures=mesures,
        )

        assert reponse.total_value == 5000.0
        assert reponse.advanced_metrics.concentration.interpretation == "Indisponible"
        assert reponse.advanced_metrics.risk_metrics.volatility == 0.0

    async def test_le_patrimoine_lui_ne_se_remplace_pas(self, db_session, regular_user, portefeuille):
        """La limite de la règle.

        Si le calcul du patrimoine échoue, la requête doit échouer aussi. Rendre
        un tableau de bord à zéro euro laisserait croire à une perte totale — et
        rien, à l'écran, ne distinguerait ce zéro d'un vrai.
        """
        with pytest.raises(RuntimeError):
            await self._appeler_avec_panne(
                db_session,
                regular_user,
                "app.api.v1.endpoints.dashboard.metrics_service.get_user_dashboard_metrics",
            )
