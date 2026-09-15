"""Lire l'historique en cache coûte une commande Redis, pas une par symbole.

Upstash facture chaque commande (500 000 par mois sur le plan gratuit, épuisés
le 2026-09-15). Mesuré à froid sur un tableau de bord recalculé : 107 commandes,
dont 40 GET d'historique lus symbole par symbole et 30 CLIENT SETINFO — une
connexion neuve par lecture (NEW-81).
"""

import json
from unittest.mock import MagicMock, patch

from app.tasks import history_cache
from app.tasks.history_cache import get_cached_histories


def _charge(prix):
    return json.dumps({"dates": ["2026-09-01T00:00:00", "2026-09-02T00:00:00"], "prices": prix})


class TestClientPartage:
    def test_deux_lectures_partagent_un_client(self, monkeypatch):
        monkeypatch.setattr(history_cache, "_client", None)
        monkeypatch.setattr(history_cache, "_client_pid", None)

        with patch.object(history_cache.Redis, "from_url", side_effect=lambda *a, **k: MagicMock()) as fabrique:
            premier = history_cache._get_redis()
            second = history_cache._get_redis()

        assert premier is second
        assert fabrique.call_count == 1

    def test_un_processus_enfant_ouvre_sa_propre_connexion(self, monkeypatch):
        """Après un fork (worker Celery prefork), partager la connexion du parent
        mélangerait les réponses des deux processus."""
        monkeypatch.setattr(history_cache, "_client", None)
        monkeypatch.setattr(history_cache, "_client_pid", None)

        with patch.object(history_cache.Redis, "from_url", side_effect=lambda *a, **k: MagicMock()) as fabrique:
            parent = history_cache._get_redis()
            with patch.object(history_cache.os, "getpid", return_value=-1):
                enfant = history_cache._get_redis()

        assert enfant is not parent
        assert fabrique.call_count == 2


class TestLectureGroupee:
    def test_plusieurs_symboles_en_une_commande(self):
        client = MagicMock()
        stockees = {
            history_cache._cache_key("BTC", 30): _charge([50000.0, 51000.0]),
            f"{history_cache._cache_key('ETH', 365)}:fallback": _charge([2000.0, 2100.0]),
        }
        client.mget.side_effect = lambda cles: [stockees.get(cle) for cle in cles]
        base = MagicMock(return_value=([], []))

        with patch.object(history_cache, "_get_redis", return_value=client), patch.object(
            history_cache, "_charger_prix_depuis_db_sync", base
        ):
            resultats = get_cached_histories(["BTC", "ETH", "SOL"], 30)

        assert client.mget.call_count == 1
        client.get.assert_not_called()
        assert resultats["BTC"][1] == [50000.0, 51000.0]
        assert resultats["ETH"][1] == [2000.0, 2100.0], "le secours de la clé 365 jours est bien essayé"
        assert resultats["SOL"] == ([], [])
        base.assert_called_once_with("SOL", 30)  # seul le symbole absent du cache va en base

    def test_la_cle_exacte_prime_sur_les_secours(self):
        client = MagicMock()
        stockees = {
            history_cache._cache_key("BTC", 30): _charge([1.0, 2.0]),
            f"{history_cache._cache_key('BTC', 30)}:fallback": _charge([9.0, 9.0]),
            history_cache._cache_key("BTC", 365): _charge([8.0, 8.0]),
        }
        client.mget.side_effect = lambda cles: [stockees.get(cle) for cle in cles]

        with patch.object(history_cache, "_get_redis", return_value=client):
            _, prix = get_cached_histories(["BTC"], 30)["BTC"]

        assert prix == [1.0, 2.0]
