"""Le cache de prix ne doit jamais faire tomber la page qu'il accélère.

Constaté en production le 2026-09-10. `/api/v1/dashboard` répondait **500** et
l'écran d'accueil restait vide — patrimoine, transactions et alertes compris.
La cause était ici : `get_cached_history` ouvrait une connexion Redis et lisait
trois clés **sans aucune garde**, alors que sa docstring annonce « falling back
to PostgreSQL ». Le repli existait bien, vingt lignes plus bas, mais l'exception
levée par Redis passait devant et ne l'atteignait jamais.

Elle remontait alors à `build_portfolio_value_series`, puis à
`_get_dashboard_impl`, et emportait toute la réponse. Upstash mettant sa base
gratuite en veille, l'écran tombait par intermittence, sans que rien ne relie la
panne à un cache.

C'est le motif traqué toute la session : **un repli inopérant**. Celui-ci
annonçait sa protection en toutes lettres.
"""

from unittest.mock import MagicMock, patch

from app.tasks.history_cache import get_cached_history


class TestRedisInjoignable:
    def _redis_en_panne(self):
        return patch(
            "app.tasks.history_cache._get_redis",
            side_effect=ConnectionError("Upstash injoignable"),
        )

    def test_la_lecture_ne_leve_pas(self):
        """Le point exact du défaut : l'appelant ne doit rien recevoir d'autre
        qu'un couple de listes, même quand Redis est mort."""
        with self._redis_en_panne(), patch(
            "app.tasks.history_cache._charger_prix_depuis_db_sync", return_value=([], [])
        ):
            assert get_cached_history("BTC", 30) == ([], [])

    def test_le_repli_sur_la_base_est_reellement_atteint(self):
        """La promesse de la docstring, tenue.

        Les prix vivent aussi en PostgreSQL : une panne de cache doit coûter du
        temps de calcul, pas les données.
        """
        from datetime import datetime

        dates = [datetime(2026, 9, 1), datetime(2026, 9, 2)]
        prix = [50000.0, 51000.0]

        with self._redis_en_panne(), patch(
            "app.tasks.history_cache._charger_prix_depuis_db_sync", return_value=(dates, prix)
        ):
            assert get_cached_history("BTC", 30) == (dates, prix)

    def test_une_lecture_qui_echoue_en_cours_de_route_replie_aussi(self):
        # La connexion s'ouvre, puis la commande échoue — le cas d'une base
        # mise en veille entre deux requêtes.
        client = MagicMock()
        client.get.side_effect = ConnectionError("connexion perdue")

        with patch("app.tasks.history_cache._get_redis", return_value=client), patch(
            "app.tasks.history_cache._charger_prix_depuis_db_sync", return_value=([], [])
        ):
            assert get_cached_history("ETH", 90) == ([], [])

    def test_le_cache_reste_utilise_quand_il_repond(self):
        """La garde ne doit pas court-circuiter le chemin normal.

        Sans cette vérification, on pourrait « corriger » le défaut en ignorant
        Redis — et perdre le cache que la fonction existe pour lire.
        """
        import json
        from datetime import datetime

        client = MagicMock()
        client.get.return_value = json.dumps(
            {"dates": ["2026-09-01T00:00:00", "2026-09-02T00:00:00"], "prices": [50000.0, 51000.0]}
        )
        base = MagicMock()

        with patch("app.tasks.history_cache._get_redis", return_value=client), patch(
            "app.tasks.history_cache._charger_prix_depuis_db_sync", new=base
        ):
            dates, prix = get_cached_history("BTC", 30)

        assert dates == [datetime(2026, 9, 1), datetime(2026, 9, 2)]
        assert prix == [50000.0, 51000.0]
        base.assert_not_called()
