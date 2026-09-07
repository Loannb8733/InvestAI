"""Filet de caractérisation des métriques de risque (`SnapshotRiskMixin`).

Volatilité, Sharpe, drawdown maximal, VaR, HHI et stress test : tout ce que
l'application affiche du risque d'un portefeuille sort d'ici. Le module est
couvert à **11 %**.

Ces méthodes acceptent leur `history` en paramètre, ce qui les rend testables
sans base ni réseau — c'est ce qui a rendu ce filet possible sans montage.

Comme pour le rejeu de transactions, ces tests épinglent le comportement
**actuel**. Plusieurs seuils ci-dessous sont des arbitrages (VaR muette sous 20
intervalles, rendements bornés à ±1 en log) qu'il faudrait confirmer, pas des
vérités démontrées.
"""

import math

import pytest

from app.services.snapshot_service import snapshot_service


def point(jour: str, valeur: float, capital_net: float | None = None) -> dict:
    p = {"date": jour, "full_date": f"{jour}T00:00:00", "value": valeur}
    if capital_net is not None:
        p["net_capital"] = capital_net
    return p


def serie(valeurs: list[float], pas_jours: int = 1) -> list[dict]:
    """Série quotidienne (ou sous-échantillonnée) sans flux de capital."""
    from datetime import date, timedelta

    debut = date(2026, 1, 1)
    return [point((debut + timedelta(days=i * pas_jours)).isoformat(), v, capital_net=0) for i, v in enumerate(valeurs)]


class TestIntervalleEntrePoints:
    def test_une_serie_quotidienne_donne_un_jour(self):
        assert snapshot_service._estimate_interval_days(serie([1, 2, 3, 4])) == 1.0

    def test_une_serie_hebdomadaire_donne_sept_jours(self):
        assert snapshot_service._estimate_interval_days(serie([1, 2, 3], pas_jours=7)) == 7.0

    def test_moins_de_deux_points_retombe_sur_un_jour(self):
        assert snapshot_service._estimate_interval_days([]) == 1.0
        assert snapshot_service._estimate_interval_days(serie([100])) == 1.0

    def test_sans_full_date_l_intervalle_retombe_sur_un_jour(self):
        # Le champ `date` seul ne suffit pas : seul `full_date` est lu. Une
        # série sous-échantillonnée sans lui serait annualisée comme si elle
        # était quotidienne.
        sans = [{"date": "2026-01-01", "value": 100}, {"date": "2026-01-08", "value": 110}]

        assert snapshot_service._estimate_interval_days(sans) == 1.0


class TestRendementsTWR:
    def test_le_flux_de_capital_est_retire_du_rendement(self):
        """Un versement ne doit pas se lire comme une performance.

        100 € qui deviennent 200 € après un apport de 100 € : le TWR est nul,
        là où un rendement brut annoncerait +69 % en log.
        """
        histoire = [point("2026-01-01", 100, 100), point("2026-01-02", 200, 200)]

        assert snapshot_service._compute_twr_log_returns(histoire) == [0.0]

    def test_une_valeur_de_depart_nulle_fait_sauter_l_intervalle(self):
        histoire = [point("2026-01-01", 0, 0), point("2026-01-02", 100, 0)]

        assert snapshot_service._compute_twr_log_returns(histoire) == []

    def test_un_intervalle_dont_la_valeur_ajustee_est_negative_est_saute(self):
        # Retirer un apport supérieur à la valeur finale rendrait le log
        # indéfini : l'intervalle est écarté plutôt que forcé.
        histoire = [point("2026-01-01", 100, 0), point("2026-01-02", 50, 200)]

        assert snapshot_service._compute_twr_log_returns(histoire) == []

    def test_les_rendements_extremes_sont_bornes_a_plus_ou_moins_un(self):
        # ±1 en log ≈ +172 % / −63 %. La borne protège la volatilité d'un point
        # de prix manquant, au prix d'une sous-estimation des vrais chocs.
        hausse = snapshot_service._compute_twr_log_returns(serie([100, 10000]))
        baisse = snapshot_service._compute_twr_log_returns(serie([10000, 100]))

        assert hausse == [1.0]
        assert baisse == [-1.0]


class TestVolatilite:
    @pytest.mark.asyncio
    async def test_une_serie_plate_a_une_volatilite_nulle(self):
        vol = await snapshot_service.calculate_volatility(None, "u", history=serie([100, 100, 100, 100]))

        assert vol == 0.0

    @pytest.mark.asyncio
    async def test_moins_de_deux_points_rend_zero(self):
        assert await snapshot_service.calculate_volatility(None, "u", history=serie([100])) == 0.0

    @pytest.mark.asyncio
    async def test_la_variance_est_corrigee_du_biais_d_echantillon(self):
        """Trois log-rendements de 0,1 / 0,2 / 0,3 donnent **191,05 %**.

        Comparer deux volatilités entre elles ne dit rien du diviseur : le
        rapport `sqrt(n/(n-1))` s'annule. Seule une valeur absolue le trahit —
        diviser par `n` au lieu de `n-1` donnerait ici 155,99.
        """
        import math as _m

        valeurs = [100.0]
        for r in (0.1, 0.2, 0.3):
            valeurs.append(valeurs[-1] * _m.exp(r))

        vol = await snapshot_service.calculate_volatility(None, "u", history=serie(valeurs))

        assert vol == 191.05

    @pytest.mark.asyncio
    async def test_l_annualisation_suit_l_intervalle_reel(self):
        """Une série hebdomadaire ne s'annualise pas comme une quotidienne.

        Le facteur est `sqrt(365 / intervalle)` : à écarts-types égaux, passer
        de 1 à 7 jours divise la volatilité annualisée par `sqrt(7)` ≈ 2,65.
        Sans cet ajustement, une série échantillonnée tous les 7 jours
        afficherait une volatilité 2,6 fois trop élevée.
        """
        valeurs = [100, 110, 105, 120, 115]
        quotidienne = await snapshot_service.calculate_volatility(None, "u", history=serie(valeurs))
        hebdomadaire = await snapshot_service.calculate_volatility(None, "u", history=serie(valeurs, pas_jours=7))

        assert quotidienne / hebdomadaire == pytest.approx(math.sqrt(7), rel=1e-3)


class TestSharpe:
    @pytest.mark.asyncio
    async def test_un_cagr_negatif_donne_un_sharpe_negatif(self):
        # C'est la raison d'être du paramètre `roi_annualized` : la moyenne des
        # log-rendements pouvait rester positive sur un portefeuille en perte.
        sharpe = await snapshot_service.calculate_sharpe_ratio(
            None, "u", history=serie([100, 110, 105, 120, 90]), roi_annualized=-30.0
        )

        assert sharpe < 0

    @pytest.mark.asyncio
    async def test_le_cagr_est_lu_en_pourcentage_et_converti_en_decimal(self):
        """`roi_annualized=100` signifie +100 %, soit 1,0 en décimal.

        Vérifier le seul signe ne suffit pas : oublier la division par 100
        laisse un Sharpe négatif négatif et un positif positif. C'est
        l'amplitude qui trahit l'unité, ici recoupée avec la volatilité que
        `calculate_volatility` annonce pour la même série.
        """
        from app.core.finance_constants import RISK_FREE_RATE

        histoire = serie([100, 110, 105, 120, 115, 130])
        volatilite = await snapshot_service.calculate_volatility(None, "u", history=histoire)
        sharpe = await snapshot_service.calculate_sharpe_ratio(None, "u", history=histoire, roi_annualized=100.0)

        assert sharpe == pytest.approx((1.0 - RISK_FREE_RATE) / (volatilite / 100), rel=1e-2)

    @pytest.mark.asyncio
    async def test_une_volatilite_nulle_rend_zero_et_non_l_infini(self):
        sharpe = await snapshot_service.calculate_sharpe_ratio(
            None, "u", history=serie([100, 100, 100, 100]), roi_annualized=50.0
        )

        assert sharpe == 0.0


class TestDrawdown:
    @pytest.mark.asyncio
    async def test_une_serie_croissante_n_a_pas_de_drawdown(self):
        res = await snapshot_service.calculate_max_drawdown(None, "u", history=serie([100, 110, 120]))

        assert res["max_drawdown_percent"] == 0.0
        assert res["peak_date"] is None
        assert res["trough_date"] is None

    @pytest.mark.asyncio
    async def test_le_creux_est_mesure_depuis_le_sommet_qui_le_precede(self):
        # 120 → 60 : -50 %. Le rebond final ne l'efface pas.
        res = await snapshot_service.calculate_max_drawdown(None, "u", history=serie([100, 120, 60, 90]))

        assert res["max_drawdown_percent"] == 50.0
        assert res["peak_value"] == 120
        assert res["trough_value"] == 60

    @pytest.mark.asyncio
    async def test_un_second_sommet_plus_haut_ouvre_un_nouveau_drawdown(self):
        # 100→80 (-20 %) puis 200→100 (-50 %) : c'est le second qui compte.
        res = await snapshot_service.calculate_max_drawdown(None, "u", history=serie([100, 80, 200, 100]))

        assert res["max_drawdown_percent"] == 50.0
        assert res["peak_value"] == 200


class TestVaR:
    @pytest.mark.asyncio
    async def test_moins_de_vingt_intervalles_rendent_une_var_nulle(self):
        """Sous 20 rendements, la VaR est déclarée nulle — pas « indisponible ».

        Une série quotidienne sur 30 jours en fournit assez ; une série
        hebdomadaire sur un an n'en a que 52, mais sur 3 mois elle tombe à 12 et
        la VaR affichée devient 0 alors que le risque, lui, ne l'est pas.
        """
        # La série descend pour de bon : sans le seuil, la VaR serait non
        # nulle. Une série croissante ne prouverait rien — sa VaR vaut 0 par la
        # queue gauche positive, seuil ou pas.
        valeurs = [100 * (0.97 if i % 3 else 1.02) ** i for i in range(15)]

        res = await snapshot_service.calculate_var(None, "u", history=serie(valeurs), current_value=1000)

        assert res["var_percent"] == 0.0
        # Preuve que le seuil est bien la cause : la même série, allongée
        # au-delà de 20 intervalles, produit une VaR non nulle.
        longue = [100 * (0.97 if i % 3 else 1.02) ** i for i in range(30)]
        res_longue = await snapshot_service.calculate_var(None, "u", history=serie(longue), current_value=1000)

        assert res_longue["var_percent"] > 0

    @pytest.mark.asyncio
    async def test_une_queue_gauche_positive_ne_fabrique_pas_de_perte(self):
        # Portefeuille en hausse continue : le 5ᵉ centile des rendements est
        # positif. `abs()` en aurait fait une perte ; `max(0, -r)` rend 0.
        res = await snapshot_service.calculate_var(
            None, "u", history=serie([100 * (1.01**i) for i in range(30)]), current_value=1000
        )

        assert res["var_percent"] == 0.0

    @pytest.mark.asyncio
    async def test_la_var_lit_le_centile_et_non_le_pire_rendement(self):
        """Sur 25 rendements dont un à −50 % et un à −20 %, la VaR 95 % vaut **20 %**.

        `ceil(0.05 x 25) - 1 = 1` désigne le deuxième pire, pas le premier.
        Sans cette valeur chiffrée, prendre systématiquement le pire rendement
        passerait inaperçu : les autres tests ne regardent que le signe.
        """
        import math as _m

        rendements = [-0.5, -0.2] + [0.01] * 23
        valeurs = [100.0]
        for r in rendements:
            valeurs.append(valeurs[-1] * _m.exp(r))

        res = await snapshot_service.calculate_var(None, "u", history=serie(valeurs), current_value=1000)

        assert res["var_percent"] == 20.0
        assert res["var_amount"] == 200.0

    @pytest.mark.asyncio
    async def test_le_montant_suit_le_pourcentage_et_la_valeur_courante(self):
        valeurs = [100 * (0.98 if i % 2 else 1.03) ** i for i in range(30)]
        res = await snapshot_service.calculate_var(None, "u", history=serie(valeurs), current_value=10000)

        assert res["var_percent"] > 0
        assert res["var_amount"] == pytest.approx(10000 * res["var_percent"] / 100, abs=0.01)

    @pytest.mark.asyncio
    async def test_sans_valeur_courante_le_montant_reste_nul(self):
        valeurs = [100 * (0.98 if i % 2 else 1.03) ** i for i in range(30)]
        res = await snapshot_service.calculate_var(None, "u", history=serie(valeurs), current_value=0)

        assert res["var_amount"] == 0


class TestHHI:
    def test_un_portefeuille_mono_actif_est_au_maximum(self):
        res = snapshot_service.calculate_hhi([{"symbol": "BTC", "value": 1000}])

        assert res["hhi"] == 10000
        assert res["is_concentrated"] is True
        assert res["top_asset"] == "BTC"

    def test_dix_lignes_egales_sont_bien_diversifiees(self):
        res = snapshot_service.calculate_hhi([{"symbol": f"A{i}", "value": 100} for i in range(10)])

        assert res["hhi"] == 1000
        assert res["interpretation"] == "Bien diversifié"

    def test_le_seuil_de_forte_concentration_est_a_2500(self):
        # Quatre lignes égales : HHI = 2500 exactement, donc « forte », le test
        # étant `< 2500` pour « modérée ».
        res = snapshot_service.calculate_hhi([{"symbol": f"A{i}", "value": 100} for i in range(4)])

        assert res["hhi"] == 2500
        assert res["interpretation"] == "Forte concentration"

    def test_un_portefeuille_vide_ou_sans_valeur_rend_n_a(self):
        assert snapshot_service.calculate_hhi([])["interpretation"] == "N/A"
        assert snapshot_service.calculate_hhi([{"symbol": "X", "value": 0}])["interpretation"] == "N/A"

    def test_current_value_sert_de_repli_quand_value_est_absente(self):
        res = snapshot_service.calculate_hhi([{"symbol": "BTC", "current_value": 1000}])

        assert res["hhi"] == 10000

    def test_une_ligne_a_zero_bascule_sur_current_value(self):
        # `a.get("value", 0) or a.get("current_value", 0)` : le `or` traite un
        # zéro explicite comme une absence. Une ligne réellement à 0 mais
        # portant un `current_value` non nul sera comptée à ce dernier.
        res = snapshot_service.calculate_hhi(
            [{"symbol": "BTC", "value": 0, "current_value": 300}, {"symbol": "ETH", "value": 100}]
        )

        assert res["top_asset"] == "BTC"
        assert res["top_concentration"] == 75.0


class TestStressTest:
    def test_la_baisse_est_appliquee_uniformement(self):
        res = snapshot_service.calculate_stress_test(10000, [], scenario_drop=0.20)

        assert res["stressed_value"] == 8000
        assert res["potential_loss"] == 2000
        assert res["potential_loss_percent"] == 20.0

    def test_les_allocations_ne_changent_rien(self):
        # Le scénario est un choc uniforme : la répartition n'est pas lue.
        # Un « stress test » qui ignore la composition du portefeuille traite
        # une ligne stablecoin comme une ligne altcoin.
        avec = snapshot_service.calculate_stress_test(10000, [{"symbol": "USDT", "value": 10000}])
        sans = snapshot_service.calculate_stress_test(10000, [])

        assert avec["stressed_value"] == sans["stressed_value"]

    def test_un_portefeuille_vide_annonce_quand_meme_le_pourcentage(self):
        res = snapshot_service.calculate_stress_test(0, [], scenario_drop=0.35)

        assert res["stressed_value"] == 0
        assert res["potential_loss_percent"] == 35.0

    def test_le_nom_du_scenario_tronque_les_decimales(self):
        # `int(0.255 * 100)` → 25 : le libellé annonce -25 % pendant que le
        # calcul applique -25,5 %.
        res = snapshot_service.calculate_stress_test(10000, [], scenario_drop=0.255)

        assert res["scenario_name"] == "Correction -25%"
        assert res["stressed_value"] == 7450.0
