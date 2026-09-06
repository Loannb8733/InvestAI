"""Caractérisation des analyses de risque d'`AnalyticsService`.

Pourquoi ce fichier existe
--------------------------
Corrélation, bêta, diversification, ordres de rééquilibrage : quatre calculs
qui alimentent des écrans de décision, et que la mesure de couverture donnait
entre 14 % et 24 %. Le noyau statistique a ses tests ; ce sont les méthodes du
service — celles qui assemblent actifs, historiques et seuils — qui étaient à
découvert.

Ces tests épinglent ce que ces méthodes font aujourd'hui, avant tout découpage.
Ils ne disent pas ce qu'elles devraient faire : deux comportements y sont
consignés comme des pièges, non comme des choix approuvés.

Le service ne contacte rien ici : `_fetch_history` et `_get_user_assets` sont
les deux seuls points de délégation des sept fonctions analytiques, et les
figer suffit à rendre les calculs déterministes.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.services.analytics_service import AnalyticsService

# Deux séries qui montent ensemble : corrélation forte et positive.
SERIE_BTC = [100, 102, 101, 105, 108, 107, 110, 112, 111, 115] * 3
SERIE_ETH = [50, 51, 50.5, 52, 54, 53.5, 55, 56, 55.5, 57] * 3
# Une série qui descend quand les autres montent.
SERIE_INVERSE = [115, 111, 112, 110, 107, 108, 105, 101, 102, 100] * 3


@pytest.fixture
def service():
    return AnalyticsService()


def _historique(prix):
    return ([float(i) for i in range(len(prix))], [float(p) for p in prix])


def _actif(symbole, quantite, prix, type_actif=AssetType.CRYPTO):
    return Asset(
        symbol=symbole,
        name=symbole,
        asset_type=type_actif,
        quantity=quantite,
        avg_buy_price=prix,
        current_price=prix,
        currency="EUR",
    )


async def _persister(db_session, user, actifs):
    """Certaines méthodes lisent la base directement, sans passer par
    `_get_user_assets` : elles ont besoin d'actifs réellement enregistrés."""
    portefeuille = Portfolio(user_id=user.id, name="Crypto", description="test")
    db_session.add(portefeuille)
    await db_session.flush()
    for actif in actifs:
        actif.portfolio_id = portefeuille.id
        db_session.add(actif)
    await db_session.commit()
    return portefeuille


def _figer(service, actifs, series):
    """Fige les deux points de délégation du service."""

    async def faux_historique(symbol, asset_type, days=60):
        return series.get(symbol, ([], []))

    return (
        patch.object(service, "_get_user_assets", new=AsyncMock(return_value=actifs)),
        patch.object(service, "_fetch_history", side_effect=faux_historique),
    )


class TestMatriceDeCorrelation:
    async def test_la_diagonale_vaut_un(self, service, db_session, regular_user):
        """Un actif est parfaitement corrélé à lui-même."""
        actifs = [_actif("BTC", 1.0, 30000.0), _actif("ETH", 10.0, 2000.0)]
        series = {"BTC": _historique(SERIE_BTC), "ETH": _historique(SERIE_ETH)}
        a, b = _figer(service, actifs, series)

        with a, b:
            resultat = await service.get_correlation_matrix(db_session, str(regular_user.id))

        assert [resultat.matrix[i][i] for i in range(len(resultat.symbols))] == [1.0, 1.0]

    async def test_la_matrice_est_symetrique(self, service, db_session, regular_user):
        actifs = [_actif("BTC", 1.0, 30000.0), _actif("ETH", 10.0, 2000.0)]
        series = {"BTC": _historique(SERIE_BTC), "ETH": _historique(SERIE_ETH)}
        a, b = _figer(service, actifs, series)

        with a, b:
            resultat = await service.get_correlation_matrix(db_session, str(regular_user.id))

        assert resultat.matrix[0][1] == resultat.matrix[1][0]

    async def test_deux_actifs_qui_montent_ensemble_sont_signales(self, service, db_session, regular_user):
        """C'est l'information utile de cet écran : deux lignes qui ne
        diversifient rien."""
        actifs = [_actif("BTC", 1.0, 30000.0), _actif("ETH", 10.0, 2000.0)]
        series = {"BTC": _historique(SERIE_BTC), "ETH": _historique(SERIE_ETH)}
        a, b = _figer(service, actifs, series)

        with a, b:
            resultat = await service.get_correlation_matrix(db_session, str(regular_user.id))

        assert resultat.strongly_correlated, "une corrélation de 0,93 doit être signalée"
        paire = resultat.strongly_correlated[0]
        assert set(paire[:2]) == {"BTC", "ETH"}
        assert paire[2] > 0.9

    async def test_une_serie_inverse_n_est_pas_signalee_comme_correlee(self, service, db_session, regular_user):
        actifs = [_actif("BTC", 1.0, 30000.0), _actif("XYZ", 10.0, 100.0)]
        series = {"BTC": _historique(SERIE_BTC), "XYZ": _historique(SERIE_INVERSE)}
        a, b = _figer(service, actifs, series)

        with a, b:
            resultat = await service.get_correlation_matrix(db_session, str(regular_user.id))

        assert resultat.strongly_correlated == []
        assert resultat.negatively_correlated, "une corrélation négative forte doit être vue"

    async def test_un_seul_actif_ne_donne_pas_de_matrice(self, service, db_session, regular_user):
        """Il n'y a pas de corrélation à une seule ligne."""
        actifs = [_actif("BTC", 1.0, 30000.0)]
        a, b = _figer(service, actifs, {"BTC": _historique(SERIE_BTC)})

        with a, b:
            resultat = await service.get_correlation_matrix(db_session, str(regular_user.id))

        assert resultat.symbols == [] or len(resultat.symbols) <= 1


class TestBeta:
    async def test_le_benchmark_a_un_beta_de_un_contre_lui_meme(self, service, db_session, regular_user):
        """Le BTC sert de référence aux cryptos : son bêta vaut 1 par
        construction. C'est le repère qui valide le calcul."""
        actifs = [_actif("BTC", 1.0, 30000.0), _actif("ETH", 10.0, 2000.0)]
        series = {"BTC": _historique(SERIE_BTC), "ETH": _historique(SERIE_ETH)}
        a, b = _figer(service, actifs, series)

        with a, b:
            resultat = await service.compute_beta(db_session, str(regular_user.id))

        btc = next(x for x in resultat["assets"] if x["symbol"] == "BTC")
        assert btc["beta"] == 1.0
        assert btc["benchmark"] == "BTC"

    async def test_le_beta_du_portefeuille_est_pondere_par_les_valeurs(self, service, db_session, regular_user):
        actifs = [_actif("BTC", 1.0, 30000.0), _actif("ETH", 10.0, 2000.0)]
        series = {"BTC": _historique(SERIE_BTC), "ETH": _historique(SERIE_ETH)}
        a, b = _figer(service, actifs, series)

        with a, b:
            resultat = await service.compute_beta(db_session, str(regular_user.id))

        betas = {x["symbol"]: x["beta"] for x in resultat["assets"]}
        agrege = resultat["portfolio_beta_crypto"]
        assert min(betas.values()) <= agrege <= max(betas.values())

    async def test_la_valeur_vient_du_dernier_prix_historique(self, service, db_session, regular_user):
        """Piège épinglé : la valeur affichée par cette méthode n'utilise pas
        `current_price` mais le **dernier point de l'historique**. Un actif à
        30 000 € y vaut 115 € si sa série s'arrête là."""
        actifs = [_actif("BTC", 1.0, 30000.0), _actif("ETH", 10.0, 2000.0)]
        series = {"BTC": _historique(SERIE_BTC), "ETH": _historique(SERIE_ETH)}
        a, b = _figer(service, actifs, series)

        with a, b:
            resultat = await service.compute_beta(db_session, str(regular_user.id))

        btc = next(x for x in resultat["assets"] if x["symbol"] == "BTC")
        assert btc["value"] == pytest.approx(SERIE_BTC[-1]), "1 unité × dernier prix de la série"


class TestDiversification:
    async def test_un_portefeuille_mono_classe_est_signale(self, service, db_session, regular_user):
        actifs = [_actif("BTC", 1.0, 115.0), _actif("ETH", 10.0, 57.0)]
        await _persister(db_session, regular_user, actifs)

        resultat = await service.get_diversification_analysis(db_session, str(regular_user.id))

        assert resultat["type_count"] == 1
        assert resultat["allocation_by_type"] == {"crypto": 100.0}
        types = {r["type"] for r in resultat["recommendations"]}
        assert "asset_types" in types

    async def test_une_ligne_dominante_est_signalee(self, service, db_session, regular_user):
        actifs = [_actif("BTC", 1.0, 115.0), _actif("ETH", 10.0, 57.0)]
        await _persister(db_session, regular_user, actifs)

        resultat = await service.get_diversification_analysis(db_session, str(regular_user.id))

        concentration = [r for r in resultat["recommendations"] if r["type"] == "concentration"]
        assert concentration, "83 % sur une ligne doit être signalé"
        assert concentration[0]["severity"] == "high"

    async def test_le_score_est_borne_entre_zero_et_cent(self, service, db_session, regular_user):
        actifs = [_actif("BTC", 1.0, 115.0), _actif("ETH", 10.0, 57.0)]
        await _persister(db_session, regular_user, actifs)

        resultat = await service.get_diversification_analysis(db_session, str(regular_user.id))

        assert 0 <= resultat["score"] <= 100


class TestOrdresDeReequilibrage:
    """Le rééquilibrage part de `get_user_analytics`, qui **valorise au cours
    du jour** — pas au `current_price` enregistré. Sans figer cette source, un
    test dépendrait du marché : c'est ce qu'a montré une première version, où
    un portefeuille de 685 € était valorisé 90 296 €.
    """

    @staticmethod
    def _analytics_figees():
        """Un patrimoine de 1 000 € : 800 € d'ETH, 200 € de BTC."""

        class _Ligne:
            def __init__(self, symbole, valeur, poids):
                self.symbol = symbole
                self.name = symbole
                self.asset_type = "crypto"
                self.current_value = valeur
                self.weight = poids

        class _Analytics:
            total_value = 1000.0
            asset_count = 2
            assets = [_Ligne("ETH", 800.0, 80.0), _Ligne("BTC", 200.0, 20.0)]

        return _Analytics()

    async def test_une_cible_en_pourcentage_reequilibre_les_deux_sens(self, service, db_session, regular_user):
        """Avec 50 et 50, la ligne dominante est allégée et l'autre renforcée."""
        with patch.object(service, "get_user_analytics", new=AsyncMock(return_value=self._analytics_figees())):
            ordres = await service.get_rebalance_orders(db_session, str(regular_user.id), {"BTC": 50.0, "ETH": 50.0})

        actions = {o.symbol: o.action for o in ordres}
        assert actions["ETH"] == "sell", "80 % du portefeuille pour une cible de 50 %"
        assert actions["BTC"] == "buy", "20 % du portefeuille pour une cible de 50 %"

    async def test_les_poids_sont_des_pourcentages_pas_des_fractions(self, service, db_session, regular_user):
        """La docstring l'annonce — `{"BTC": 40, "ETH": 30}` — mais rien dans la
        signature ne l'impose. Passer `0.5` en croyant demander la moitié
        demande **0,5 %**, et le service propose alors de tout vendre.
        """
        with patch.object(service, "get_user_analytics", new=AsyncMock(return_value=self._analytics_figees())):
            ordres = await service.get_rebalance_orders(db_session, str(regular_user.id), {"BTC": 0.5, "ETH": 0.5})

        assert all(o.action == "sell" for o in ordres)
        assert all(o.target_value == pytest.approx(5.0) for o in ordres), "0,5 % de 1 000 €"

    async def test_la_valeur_cible_suit_le_poids_demande(self, service, db_session, regular_user):
        with patch.object(service, "get_user_analytics", new=AsyncMock(return_value=self._analytics_figees())):
            ordres = await service.get_rebalance_orders(db_session, str(regular_user.id), {"BTC": 30.0, "ETH": 70.0})

        cibles = {o.symbol: o.target_value for o in ordres}
        assert cibles["BTC"] == pytest.approx(300.0)
        assert cibles["ETH"] == pytest.approx(700.0)

    async def test_un_actif_sans_cible_garde_son_poids(self, service, db_session, regular_user):
        """Le défaut documenté : une ligne absente des cibles n'est pas touchée."""
        with patch.object(service, "get_user_analytics", new=AsyncMock(return_value=self._analytics_figees())):
            ordres = await service.get_rebalance_orders(db_session, str(regular_user.id), {"BTC": 20.0})

        eth = next(o for o in ordres if o.symbol == "ETH")
        assert eth.diff_weight == 0.0
        assert eth.target_weight == 80.0

    async def test_patrimoine_vide(self, service, db_session, regular_user):
        class _Vide:
            total_value = 0.0
            asset_count = 0
            assets = []

        with patch.object(service, "get_user_analytics", new=AsyncMock(return_value=_Vide())):
            ordres = await service.get_rebalance_orders(db_session, str(regular_user.id), {"BTC": 100.0})

        assert ordres == []
