"""Caractérisation de `_fetch_period_changes`.

Cette fonction alimente les pourcentages de variation affichés sur le
dashboard. 140 lignes, couvertes à **7 %**.

Elle enchaîne quatre sources, chacune servant de repli à la précédente :

1. l'historique en cache (Redis puis PostgreSQL), sans aucun appel réseau ;
2. l'API groupée de CoinGecko, pour les cryptos restantes ;
3. la table `asset_price_history`, en une requête pour tout le reliquat ;
4. un appel live, symbole par symbole, en dernier recours.

Ce qui compte ici n'est pas le calcul — une variation entre deux prix — mais la
**cascade** : chaque étape ne traite que ce que la précédente n'a pas résolu, et
chacune échoue en silence sans interrompre les suivantes. Un symbole
introuvable partout est simplement absent du résultat, jamais à zéro : l'écran
peut ainsi distinguer « pas de variation » de « variation inconnue ».
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.metrics_service import metrics_service


def _cache(reponses):
    """Fige l'historique en cache. `reponses` : {SYMBOLE: [prix, ...]}."""

    def faux_cache(symbol, days=2):
        prix = reponses.get(symbol.upper())
        if prix is None:
            raise KeyError(symbol)
        return ([], prix)

    return patch("app.tasks.history_cache.get_cached_history", side_effect=faux_cache)


def _replis_muets():
    """Neutralise les étapes 2 à 4, pour n'observer que le cache.

    Les trois points d'injection diffèrent, et c'est ce qui rend ces tests
    fragiles à écrire : `get_cached_history` est importé **dans** la fonction,
    `AsyncSessionLocal` aussi, mais `HistoricalDataFetcher` l'est **en tête du
    module** — le patcher à sa source d'origine n'a donc aucun effet. Une
    première version laissait passer de vrais appels à CoinGecko, et un test
    attendait 30 % là où le marché rendait 26,46 %.
    """
    return (
        patch("httpx.AsyncClient", side_effect=RuntimeError("étape 2 neutralisée")),
        patch("app.core.database.AsyncSessionLocal", side_effect=RuntimeError("étape 3 neutralisée")),
        patch("app.services.metrics_service.HistoricalDataFetcher", MagicMock()),
    )


def _fetcher_live(prix=None, erreur=None):
    """Fige l'étape 4 — le fetch live, symbole par symbole."""
    faux = MagicMock()
    if erreur is not None:
        faux.return_value.get_crypto_history = AsyncMock(side_effect=erreur)
        faux.return_value.get_stock_history = AsyncMock(side_effect=erreur)
    else:
        faux.return_value.get_crypto_history = AsyncMock(return_value=([], prix or []))
        faux.return_value.get_stock_history = AsyncMock(return_value=([], prix or []))
    faux.return_value.close = AsyncMock()
    return patch("app.services.metrics_service.HistoricalDataFetcher", faux), faux


class TestCalculDeLaVariation:
    async def test_une_hausse_est_rendue_en_pourcentage(self):
        with _cache({"BTC": [100.0, 110.0, 120.0]}):
            resultat = await metrics_service._fetch_period_changes({"crypto": ["BTC"]}, 30)

        assert resultat["BTC"] == pytest.approx(20.0), "du premier au dernier prix"

    async def test_une_baisse_est_negative(self):
        with _cache({"BTC": [100.0, 80.0]}):
            resultat = await metrics_service._fetch_period_changes({"crypto": ["BTC"]}, 30)

        assert resultat["BTC"] == pytest.approx(-20.0)

    async def test_seuls_les_prix_extremes_comptent(self):
        """Le chemin parcouru entre les deux n'entre pas dans le calcul."""
        with _cache({"BTC": [100.0, 500.0, 10.0, 110.0]}):
            resultat = await metrics_service._fetch_period_changes({"crypto": ["BTC"]}, 30)

        assert resultat["BTC"] == pytest.approx(10.0)

    async def test_les_symboles_sont_normalises_en_majuscules(self):
        with _cache({"BTC": [100.0, 110.0]}):
            resultat = await metrics_service._fetch_period_changes({"crypto": ["btc"]}, 30)

        assert "BTC" in resultat


class TestGardes:
    """Trois situations où le cache ne peut rien conclure, et passe la main."""

    async def test_un_seul_prix_ne_fait_pas_une_variation(self):
        muet_http, muet_db, _ = _replis_muets()
        fige, _f = _fetcher_live([])
        with _cache({"BTC": [100.0]}), muet_http, muet_db, fige:
            resultat = await metrics_service._fetch_period_changes({"crypto": ["BTC"]}, 30)

        assert "BTC" not in resultat, "absent, et non pas à zéro"

    async def test_un_premier_prix_nul_ne_donne_pas_de_division(self):
        """Sans cette garde, la variation serait une division par zéro."""
        muet_http, muet_db, _ = _replis_muets()
        fige, _f = _fetcher_live([])
        with _cache({"BTC": [0.0, 110.0]}), muet_http, muet_db, fige:
            resultat = await metrics_service._fetch_period_changes({"crypto": ["BTC"]}, 30)

        assert "BTC" not in resultat

    async def test_un_cache_en_erreur_n_interrompt_pas_le_calcul(self):
        """Le cache peut tomber ; les autres symboles doivent aboutir."""
        muet_http, muet_db, _ = _replis_muets()
        fige, _f = _fetcher_live([])
        with _cache({"ETH": [50.0, 55.0]}), muet_http, muet_db, fige:
            resultat = await metrics_service._fetch_period_changes({"crypto": ["BTC", "ETH"]}, 30)

        assert resultat["ETH"] == pytest.approx(10.0)
        assert "BTC" not in resultat


class TestSortieAnticipee:
    async def test_tout_resolu_par_le_cache_evite_le_reseau(self):
        """C'est l'intérêt de l'étape 1 : sur un dashboard rafraîchi souvent,
        aucun appel externe n'est émis.

        Vérifié sur le mécanisme et non sur le résultat : les étapes suivantes
        rattrapent leurs propres erreurs, donc les neutraliser ne changerait
        rien à la valeur rendue. Ce qui se contrôle ici, c'est qu'aucun client
        live n'est instancié.

        À noter, mesuré par canari : supprimer le `return` anticipé ne change
        **rien** au comportement observable. Les étapes suivantes sont alors
        traversées, mais leurs propres gardes — `if uncached_crypto`,
        `if remaining` — portent sur des listes vides. Cette sortie est une
        optimisation redondante, pas une garde. Aucun test ne peut donc la
        défendre, et il ne faut pas en écrire un artificiel.
        """
        muet_http, muet_db, _ = _replis_muets()
        fige, faux = _fetcher_live([1.0, 2.0])

        with _cache({"BTC": [100.0, 110.0], "ETH": [50.0, 45.0]}), muet_http, muet_db, fige:
            resultat = await metrics_service._fetch_period_changes({"crypto": ["BTC", "ETH"]}, 30)

        assert set(resultat) == {"BTC", "ETH"}
        assert resultat["ETH"] == pytest.approx(-10.0)
        assert not faux.called, "aucun client live ne doit être instancié"

    async def test_les_actions_passent_par_le_meme_chemin(self):
        muet_http, muet_db, muet_fetch = _replis_muets()

        with _cache({"AAPL": [200.0, 220.0]}), muet_http, muet_db, muet_fetch:
            resultat = await metrics_service._fetch_period_changes({"stock": ["AAPL"]}, 30)

        assert resultat["AAPL"] == pytest.approx(10.0)

    async def test_plusieurs_types_dans_le_meme_appel(self):
        muet_http, muet_db, muet_fetch = _replis_muets()

        with _cache({"BTC": [100.0, 110.0], "AAPL": [200.0, 190.0]}), muet_http, muet_db, muet_fetch:
            resultat = await metrics_service._fetch_period_changes({"crypto": ["BTC"], "stock": ["AAPL"]}, 30)

        assert resultat["BTC"] == pytest.approx(10.0)
        assert resultat["AAPL"] == pytest.approx(-5.0)


class TestCascade:
    async def test_le_repli_live_recupere_ce_que_le_cache_ignore(self):
        """Étape 4 : un symbole absent partout ailleurs est cherché en direct."""
        muet_http, muet_db, _ = _replis_muets()
        fige, _f = _fetcher_live([100.0, 130.0])

        with _cache({}), muet_http, muet_db, fige:
            resultat = await metrics_service._fetch_period_changes({"crypto": ["BTC"]}, 30)

        assert resultat["BTC"] == pytest.approx(30.0)

    async def test_un_echec_du_repli_laisse_le_symbole_absent(self):
        muet_http, muet_db, _ = _replis_muets()
        fige, _f = _fetcher_live(erreur=Exception("réseau"))

        with _cache({}), muet_http, muet_db, fige:
            resultat = await metrics_service._fetch_period_changes({"crypto": ["BTC"]}, 30)

        assert resultat == {}, "aucune variation inventée quand rien n'est connu"

    async def test_le_client_est_ferme_meme_en_cas_d_echec(self):
        """Le `finally` ferme le client : sans lui, chaque rafraîchissement du
        dashboard laisserait une connexion ouverte."""
        muet_http, muet_db, _ = _replis_muets()
        fige, faux = _fetcher_live(erreur=Exception("réseau"))

        with _cache({}), muet_http, muet_db, fige:
            await metrics_service._fetch_period_changes({"crypto": ["BTC"]}, 30)

        faux.return_value.close.assert_awaited_once()


class TestCasLimites:
    async def test_aucun_symbole(self):
        muet_http, muet_db, muet_fetch = _replis_muets()
        with _cache({}), muet_http, muet_db, muet_fetch:
            assert await metrics_service._fetch_period_changes({}, 30) == {}

    async def test_listes_vides(self):
        muet_http, muet_db, muet_fetch = _replis_muets()
        with _cache({}), muet_http, muet_db, muet_fetch:
            resultat = await metrics_service._fetch_period_changes({"crypto": [], "stock": []}, 30)

        assert resultat == {}
