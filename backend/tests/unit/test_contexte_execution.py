"""Face à un 429, la conduite dépend de qui attend.

Pourquoi cette distinction est la bonne
---------------------------------------
`GET /dashboard` mettait **13,4 secondes** cache vide. Ni le SQL (0,43 s sur 30
requêtes), ni le réseau (2,47 s), ni un blocage de l'event loop : **une unique
attente de 10 secondes**, celle du `Retry-After` de CoinGecko.

Un `Retry-After` mérite d'être respecté — mais pas devant un utilisateur. En
tâche de fond, personne n'attend et l'API demande poliment qu'on patiente ; dans
une requête HTTP, le cache et PostgreSQL savent déjà répondre, et faire patienter
dix secondes pour un enrichissement est un mauvais échange.

Sans cette distinction il faut choisir un compromis unique : brusquer l'API ou
figer l'écran. Mesuré après : 13,4 s → 2,6 s, contenu identique.
"""

import ast
import asyncio
import inspect
from pathlib import Path

import pytest

from app.core.contexte_execution import sert_une_requete_http, un_humain_attend


class TestValeurParDefaut:
    def test_hors_requete_personne_n_attend(self):
        """Workers Celery, scripts, tests : le défaut doit être False.

        S'il était True, les tâches de fond renonceraient au moindre 429 et le
        cache ne se remplirait jamais — l'inverse de ce qu'on cherche.
        """
        assert un_humain_attend() is False

    @pytest.mark.asyncio
    async def test_la_valeur_suit_la_tache_asyncio(self):
        sert_une_requete_http.set(True)
        assert un_humain_attend() is True

        async def tache_de_fond():
            # Une tâche créée hérite du contexte : c'est voulu, elle sert encore
            # la même requête. Ce test fige ce comportement pour qu'un
            # remplacement par une variable globale se voie.
            return un_humain_attend()

        assert await asyncio.create_task(tache_de_fond()) is True
        sert_une_requete_http.set(False)


class TestConduiteSurLe429:
    """Le code du 429 doit lire le contexte, et attendre seulement sinon."""

    def _bloc_429(self) -> str:
        import app.ml.historical_data as hd

        source = Path(hd.__file__).read_text(encoding="utf-8")
        for noeud in ast.walk(ast.parse(source)):
            if isinstance(noeud, ast.If):
                bloc = ast.unparse(noeud)
                if "429" in bloc and "sleep" in bloc:
                    return bloc
        raise AssertionError("bloc de traitement du 429 introuvable")

    def test_une_requete_http_renonce_sans_attendre(self):
        bloc = self._bloc_429()
        assert "un_humain_attend()" in bloc, (
            "le 429 ne consulte pas le contexte : la requête HTTP attendra le "
            "Retry-After, soit une dizaine de secondes devant l'utilisateur"
        )
        # Le renoncement doit précéder l'attente, sinon il ne sert à rien.
        assert bloc.index("un_humain_attend()") < bloc.index(
            "sleep"
        ), "le contexte est consulté après l'attente : l'utilisateur patiente quand même"

    def test_une_tache_de_fond_respecte_le_retry_after(self):
        bloc = self._bloc_429()
        assert "Retry-After" in bloc, (
            "hors requête HTTP, l'en-tête Retry-After doit être respecté : "
            "c'est ce que l'API demande, et rien ne presse"
        )


class TestPoseDuContexte:
    def test_le_middleware_marque_les_requetes_http(self):
        import app.main as main

        source = inspect.getsource(main.RequestLoggingMiddleware.dispatch)
        assert "sert_une_requete_http.set(True)" in source, (
            "sans ce marquage, aucune requête HTTP n'est reconnue comme telle "
            "et le renoncement au 429 ne se déclenche jamais"
        )
