"""Le chemin d'une requête HTTP ne doit pas dépendre d'une API tierce.

Pourquoi c'est une règle et pas un détail
-----------------------------------------
``/predictions/market-cycle`` allait chercher l'historique chez CoinGecko
pendant qu'il servait une requête. Quand le quota était épuisé — ce qui arrive
d'autant plus vite qu'il n'y a pas de clé API — chaque symbole encaissait des
secondes de backoff : **65 secondes** pour finir sans donnée, et un bandeau de
régime figé en squelette (NEW-13).

Le réseau appartient à ``tasks.history_cache``, qui passe toutes les 30 minutes
et persiste dans PostgreSQL. Le chemin web lit ce dépôt, rien d'autre.

Mesuré une fois la règle appliquée, Redis vidé et quota épuisé : **1,3 s, sept
actifs analysés** — contre 65 s et un seul auparavant. La base a 367 jours
d'historique par symbole ; elle n'a pas besoin de CoinGecko pour répondre.
"""

import ast
import inspect
from pathlib import Path

import app.services.prediction_cycles as pc

_SOURCE = Path(pc.__file__).read_text(encoding="utf-8")

# Appels réseau qui rapatrient de l'**historique**. La dominance BTC et le
# Fear & Greed sortent aussi, mais ce sont des enrichissements d'une fraction de
# seconde, bornés par le budget : les interdire ici n'apporterait rien.
_RESEAU_HISTORIQUE = ("get_crypto_history", "get_history(")


def _corps_de(nom: str) -> ast.AST:
    for noeud in ast.walk(ast.parse(_SOURCE)):
        if isinstance(noeud, (ast.AsyncFunctionDef, ast.FunctionDef)) and noeud.name == nom:
            return noeud
    raise AssertionError(f"fonction {nom} introuvable")


class TestAucunAppelReseauPourLHistorique:
    def test_le_cycle_de_marche_ne_recupere_plus_d_historique_en_ligne(self):
        fonction = _corps_de("get_market_cycle")
        fautifs = []
        for n in ast.walk(fonction):
            if not isinstance(n, ast.Await):
                continue
            appel = ast.unparse(n.value)
            if any(motif in appel for motif in _RESEAU_HISTORIQUE):
                fautifs.append(f"ligne {n.lineno} : {appel[:90]}")

        assert (
            not fautifs
        ), "appel réseau d'historique réintroduit dans le chemin HTTP — " "utiliser `prix_locaux()` : " + " | ".join(
            fautifs
        )

    def test_l_historique_passe_par_les_sources_locales(self):
        assert "prix_locaux" in _SOURCE, (
            "le cycle de marché ne lit plus les sources locales : sans elles, "
            "un Redis vide renvoie une analyse vide au lieu d'interroger PostgreSQL"
        )


class TestSourcesLocales:
    """`prix_locaux` doit rester sans réseau, et garder son filet PostgreSQL."""

    def test_la_lecture_locale_ne_sort_jamais_sur_le_reseau(self):
        import app.services.price_history_store as store

        # Les imports, pas le texte : la docstring du module explique justement
        # de quelle API il s'affranchit, et la citer suffirait à faire échouer
        # une recherche naïve dans le fichier.
        arbre = ast.parse(Path(store.__file__).read_text(encoding="utf-8"))
        modules = set()
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Import):
                modules.update(a.name.split(".")[0] for a in noeud.names)
            elif isinstance(noeud, ast.ImportFrom) and noeud.module:
                modules.add(noeud.module.split(".")[0])

        for interdit in ("httpx", "requests", "aiohttp", "urllib"):
            assert interdit not in modules, (
                f"`{interdit}` importé dans le module de lecture locale : " "il ne doit faire aucun appel sortant"
            )

        code = ast.unparse(arbre)
        assert "data_fetcher" not in code, "le module de lecture locale ne doit pas appeler le fetcher réseau"

    def test_postgres_sert_de_filet_quand_redis_est_vide(self):
        import app.services.price_history_store as store

        src = inspect.getsource(store.prix_locaux)
        assert "charger_depuis_postgres" in src, (
            "sans repli PostgreSQL, un Redis vide — après un redémarrage, par exemple — "
            "rendrait l'analyse vide alors que la base a l'historique"
        )

    def test_l_ordre_privilegie_redis(self):
        import app.services.price_history_store as store

        src = inspect.getsource(store.prix_locaux)
        assert src.index("get_cached_history") < src.index(
            "charger_depuis_postgres"
        ), "PostgreSQL avant Redis : on paierait une requête SQL là où le cache suffit"
