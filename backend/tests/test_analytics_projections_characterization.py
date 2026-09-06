"""Caractérisation des trois projections d'`AnalyticsService`.

Monte-Carlo, optimisation de portefeuille et tests de résistance : les trois
fonctions les plus lourdes du service, et les dernières à découvert. Elles
produisent des chiffres que l'utilisateur lit pour décider — une probabilité de
ruine, une répartition cible, une perte en cas de krach.

Ce que l'exploration a établi avant d'écrire ces tests :

- **Monte-Carlo est reproductible.** Deux appels identiques rendent les mêmes
  percentiles. La graine est explicite (FIN-06) ; sans cela, aucune assertion
  chiffrée ne tiendrait.
- **Le test de résistance valorise au cours du jour.** Il passe par
  `metrics_service.get_portfolio_metrics`, pas par le `current_price`
  enregistré : un portefeuille déclaré à 50 000 € y était valorisé 90 186 €.
  La source est figée ici, sans quoi le test dépendrait du marché.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.services.analytics_service import AnalyticsService

# Une série qui monte régulièrement, assez longue pour les calculs de volatilité.
SERIE_HAUSSIERE = [100, 102, 101, 105, 108, 107, 110, 112, 111, 115] * 6


@pytest.fixture
def service():
    return AnalyticsService()


def _actif(symbole, quantite, prix):
    return Asset(
        symbol=symbole,
        name=symbole,
        asset_type=AssetType.CRYPTO,
        quantity=quantite,
        avg_buy_price=prix,
        current_price=prix,
        currency="EUR",
    )


def _figer_series(service, actifs, serie=SERIE_HAUSSIERE):
    async def faux_historique(symbol, asset_type, days=60):
        return ([float(i) for i in range(len(serie))], [float(p) for p in serie])

    return (
        patch.object(service, "_get_user_assets", new=AsyncMock(return_value=actifs)),
        patch.object(service, "_fetch_history", side_effect=faux_historique),
    )


async def _portefeuille(db_session, user):
    portefeuille = Portfolio(user_id=user.id, name="Crypto", description="test")
    db_session.add(portefeuille)
    await db_session.commit()
    return portefeuille


class TestMonteCarlo:
    async def test_les_percentiles_sont_ordonnes(self, service, db_session, regular_user):
        """p5 ≤ p25 ≤ p50 ≤ p75 ≤ p95 : c'est ce qui fait d'eux des percentiles."""
        actifs = [_actif("BTC", 1.0, 30000.0)]
        a, b = _figer_series(service, actifs)

        with a, b:
            resultat = await service.monte_carlo(
                db_session, str(regular_user.id), horizon_days=365, num_simulations=200
            )

        p = resultat.percentiles
        assert p["p5"] <= p["p25"] <= p["p50"] <= p["p75"] <= p["p95"]

    async def test_deux_appels_identiques_donnent_le_meme_resultat(self, service, db_session, regular_user):
        """La graine est explicite (FIN-06) : sans cela, l'utilisateur verrait
        sa projection changer à chaque rafraîchissement, sans rien avoir fait."""
        actifs = [_actif("BTC", 1.0, 30000.0)]
        a, b = _figer_series(service, actifs)

        with a, b:
            premier = await service.monte_carlo(db_session, str(regular_user.id), horizon_days=365, num_simulations=200)
            second = await service.monte_carlo(db_session, str(regular_user.id), horizon_days=365, num_simulations=200)

        assert premier.percentiles == second.percentiles

    async def test_le_nombre_de_simulations_est_rapporte(self, service, db_session, regular_user):
        actifs = [_actif("BTC", 1.0, 30000.0)]
        a, b = _figer_series(service, actifs)

        with a, b:
            resultat = await service.monte_carlo(
                db_session, str(regular_user.id), horizon_days=180, num_simulations=150
            )

        assert resultat.simulations == 150
        assert resultat.horizon_days == 180

    async def test_les_probabilites_sont_des_pourcentages(self, service, db_session, regular_user):
        actifs = [_actif("BTC", 1.0, 30000.0)]
        a, b = _figer_series(service, actifs)

        with a, b:
            resultat = await service.monte_carlo(
                db_session, str(regular_user.id), horizon_days=365, num_simulations=200
            )

        for nom in ("prob_positive", "prob_loss_10", "prob_ruin"):
            valeur = getattr(resultat, nom)
            assert 0.0 <= valeur <= 100.0, f"{nom} = {valeur}"

    async def test_une_serie_haussiere_donne_une_majorite_de_scenarios_positifs(
        self, service, db_session, regular_user
    ):
        actifs = [_actif("BTC", 1.0, 30000.0)]
        a, b = _figer_series(service, actifs)

        with a, b:
            resultat = await service.monte_carlo(
                db_session, str(regular_user.id), horizon_days=365, num_simulations=300
            )

        assert resultat.prob_positive > 50.0
        assert resultat.prob_ruin == 0.0, "aucune ruine sur une série qui ne fait que monter"

    async def test_sans_actif_aucune_projection(self, service, db_session, regular_user):
        a, b = _figer_series(service, [])

        with a, b:
            resultat = await service.monte_carlo(db_session, str(regular_user.id))

        assert resultat.simulations == 0 or resultat.percentiles == {}


class TestOptimisation:
    async def test_les_poids_totalisent_cent(self, service, db_session, regular_user):
        actifs = [_actif("BTC", 1.0, 30000.0), _actif("ETH", 10.0, 2000.0)]
        a, b = _figer_series(service, actifs)

        with a, b:
            resultat = await service.optimize_portfolio(db_session, str(regular_user.id))

        assert sum(resultat.weights.values()) == pytest.approx(100.0, abs=0.5)

    async def test_aucun_poids_negatif(self, service, db_session, regular_user):
        """L'optimiseur travaille sans vente à découvert."""
        actifs = [_actif("BTC", 1.0, 30000.0), _actif("ETH", 10.0, 2000.0)]
        a, b = _figer_series(service, actifs)

        with a, b:
            resultat = await service.optimize_portfolio(db_session, str(regular_user.id))

        assert all(p >= 0 for p in resultat.weights.values())

    async def test_deux_actifs_de_meme_serie_se_partagent_egalement(self, service, db_session, regular_user):
        """Rien ne distingue deux actifs qui bougent exactement pareil."""
        actifs = [_actif("BTC", 1.0, 30000.0), _actif("ETH", 10.0, 2000.0)]
        a, b = _figer_series(service, actifs)

        with a, b:
            resultat = await service.optimize_portfolio(db_session, str(regular_user.id))

        assert resultat.weights["BTC"] == pytest.approx(resultat.weights["ETH"], abs=1.0)

    async def test_l_objectif_de_volatilite_minimale_est_accepte(self, service, db_session, regular_user):
        actifs = [_actif("BTC", 1.0, 30000.0), _actif("ETH", 10.0, 2000.0)]
        a, b = _figer_series(service, actifs)

        with a, b:
            resultat = await service.optimize_portfolio(db_session, str(regular_user.id), objective="min_volatility")

        assert sum(resultat.weights.values()) == pytest.approx(100.0, abs=0.5)
        assert resultat.expected_volatility >= 0


class TestTestsDeResistance:
    """Les scénarios appliquent un choc historique au patrimoine courant."""

    @staticmethod
    def _metriques_figees(valeur_btc=60000.0, valeur_eth=40000.0):
        return AsyncMock(
            return_value={
                "assets": [
                    {"symbol": "BTC", "name": "BTC", "current_value": valeur_btc, "risk_weight": 0},
                    {"symbol": "ETH", "name": "ETH", "current_value": valeur_eth, "risk_weight": 0},
                ]
            }
        )

    async def test_la_valeur_totale_est_la_somme_des_lignes(self, service, db_session, regular_user):
        await _portefeuille(db_session, regular_user)

        with patch("app.services.metrics_service.metrics_service.get_portfolio_metrics", self._metriques_figees()):
            resultat = await service.stress_test(db_session, str(regular_user.id))

        assert resultat["total_value"] == pytest.approx(100000.0)

    async def test_tous_les_scenarios_ne_sont_pas_baissiers(self, service, db_session, regular_user):
        """Le nom de la méthode trompe : parmi les six scénarios historiques,
        `bull_run_2021` applique **+100 %** aux cryptos. Un « test de
        résistance » qui enrichit le patrimoine reste un scénario délibéré, pas
        un défaut — mais un appelant qui supposerait que toute sortie est une
        perte se tromperait de signe.
        """
        await _portefeuille(db_session, regular_user)

        with patch("app.services.metrics_service.metrics_service.get_portfolio_metrics", self._metriques_figees()):
            resultat = await service.stress_test(db_session, str(regular_user.id))

        par_id = {s["id"]: s for s in resultat["scenarios"]}
        assert par_id["bull_run_2021"]["total_loss"] > 0, "le bull run fait gagner"
        assert par_id["luna_ftx_2022"]["total_loss"] < 0, "la crise fait perdre"

    async def test_les_scenarios_de_crise_appauvrissent(self, service, db_session, regular_user):
        await _portefeuille(db_session, regular_user)

        with patch("app.services.metrics_service.metrics_service.get_portfolio_metrics", self._metriques_figees()):
            resultat = await service.stress_test(db_session, str(regular_user.id))

        crises = [s for s in resultat["scenarios"] if s["id"] != "bull_run_2021"]
        assert crises, "au moins un scénario de crise doit être évalué"
        for scenario in crises:
            assert scenario["stressed_value"] < resultat["total_value"]
            assert scenario["total_loss"] < 0
            assert scenario["total_loss_pct"] < 0

    async def test_le_pire_scenario_est_celui_du_plus_fort_recul(self, service, db_session, regular_user):
        await _portefeuille(db_session, regular_user)

        with patch("app.services.metrics_service.metrics_service.get_portfolio_metrics", self._metriques_figees()):
            resultat = await service.stress_test(db_session, str(regular_user.id))

        pire = resultat["max_drawdown"]
        # Seuls les scénarios défavorables comptent : le +100 % du bull run
        # n'est pas un recul, et n'entre pas dans ce classement.
        pertes = {s["name"]: abs(s["total_loss_pct"]) for s in resultat["scenarios"] if s["total_loss_pct"] < 0}
        assert pire["value"] == pytest.approx(max(pertes.values()))
        assert pire["scenario"] == max(pertes, key=pertes.get)

    async def test_le_pire_recul_vaut_soixante_pour_cent_sur_un_portefeuille_crypto(
        self, service, db_session, regular_user
    ):
        """Valeur métier figée : LUNA/FTX applique −60 % aux cryptos, et c'est
        le plus fort recul des six scénarios. Sur un patrimoine 100 % crypto, le
        pire cas est donc une perte de 60 %.

        Sans cette assertion, adoucir un choc passerait inaperçu : les autres
        tests ne vérifient que la cohérence du classement, pas ses valeurs.
        """
        await _portefeuille(db_session, regular_user)

        with patch("app.services.metrics_service.metrics_service.get_portfolio_metrics", self._metriques_figees()):
            resultat = await service.stress_test(db_session, str(regular_user.id))

        assert resultat["max_drawdown"]["value"] == pytest.approx(60.0)
        assert resultat["max_drawdown"]["scenario"] == "LUNA/FTX (2022)"

        luna = next(s for s in resultat["scenarios"] if s["id"] == "luna_ftx_2022")
        assert luna["stressed_value"] == pytest.approx(40000.0), "100 000 € amputés de 60 %"

    async def test_le_detail_par_actif_couvre_toutes_les_lignes(self, service, db_session, regular_user):
        await _portefeuille(db_session, regular_user)

        with patch("app.services.metrics_service.metrics_service.get_portfolio_metrics", self._metriques_figees()):
            resultat = await service.stress_test(db_session, str(regular_user.id))

        for scenario in resultat["scenarios"]:
            symboles = {a["symbol"] for a in scenario["per_asset"]}
            assert symboles == {"BTC", "ETH"}

    async def test_un_filtre_de_scenarios_est_respecte(self, service, db_session, regular_user):
        await _portefeuille(db_session, regular_user)

        with patch("app.services.metrics_service.metrics_service.get_portfolio_metrics", self._metriques_figees()):
            resultat = await service.stress_test(db_session, str(regular_user.id), scenario_ids=["luna_ftx_2022"])

        assert [s["id"] for s in resultat["scenarios"]] == ["luna_ftx_2022"]

    async def test_un_patrimoine_vide_ne_donne_aucun_scenario(self, service, db_session, regular_user):
        await _portefeuille(db_session, regular_user)

        with patch(
            "app.services.metrics_service.metrics_service.get_portfolio_metrics",
            new=AsyncMock(return_value={"assets": []}),
        ):
            resultat = await service.stress_test(db_session, str(regular_user.id))

        assert resultat["scenarios"] == []
        assert resultat["total_value"] == 0
        assert resultat["max_drawdown"] is None
