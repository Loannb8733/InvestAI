"""Sur une seule instance, le limiteur compte en mémoire, pas dans Upstash.

Mesuré le 2026-09-15 : une requête authentifiée coûtait quatre commandes Redis
avant tout travail utile — trois pour le limiteur (EVALSHA, INCRBY, EXPIRE),
une pour la révocation du jeton. Render (offre gratuite) ne fait tourner qu'un
uvicorn sans --workers : un compteur en mémoire y est exactement aussi efficace
et ne coûte rien. Le partage dans Redis reste possible dès qu'une seconde
instance existe (NEW-84).
"""

from app.core import rate_limit, redis_client
from app.core.config import settings


class TestStockageDuLimiteur:
    def test_en_memoire_par_defaut(self):
        assert type(settings).model_fields["RATE_LIMIT_SHARED_STORAGE"].default is False

    def test_une_seule_instance_compte_en_memoire(self, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMIT_SHARED_STORAGE", False)

        assert rate_limit._limiter_storage_uri() == "memory://"
        assert rate_limit._limiter_storage_options() == {}

    def test_plusieurs_instances_partagent_redis(self, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMIT_SHARED_STORAGE", True)

        assert rate_limit._limiter_storage_uri().startswith("redis")
        options = rate_limit._limiter_storage_options()
        assert options["socket_timeout"] == redis_client.REDIS_DELAI_RESEAU


class TestConnexionSobre:
    def test_aucune_annonce_de_version_au_serveur(self):
        """redis-py 5 envoie deux CLIENT SETINFO par connexion, facturés par
        Upstash, pour une information que rien n'exploite."""
        options = redis_client.redis_client_kwargs()

        assert options["lib_name"] is None
        assert options["lib_version"] is None
