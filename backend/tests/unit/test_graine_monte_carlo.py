"""La projection Monte Carlo ne doit pas changer sans raison.

La graine par défaut valait `int(time.time()) ^ hash(user_id)` : elle changeait
donc à **chaque seconde**. Les percentiles bougeaient d'un rafraîchissement à
l'autre sans qu'aucune donnée n'ait varié, et l'utilisateur ne pouvait plus
distinguer une évolution réelle de son portefeuille d'un simple bruit de calcul.

Le test de caractérisation qui affirmait le contraire passait par accident :
deux appels consécutifs tombent dans la même seconde **dix-huit fois sur
vingt**. Il vérifiait la vitesse de la machine, non le déterminisme.

Ce que la graine constante apporte, et pourquoi elle n'est pas dérivée des
données d'entrée : deux scénarios comparés partagent alors les mêmes chocs —
c'est la technique des *nombres aléatoires communs* — et leur différence isole
l'effet de la décision au lieu de le noyer dans deux tirages distincts.
"""

import inspect

from app.services import analytics_simulation


def _appels_du_module() -> set[str]:
    """Les fonctions appelées dans le module, commentaires exclus.

    Une recherche de texte ne convient pas ici : les commentaires citent
    `time.time()` et `hash(user_id)` pour expliquer ce qui a été retiré, et
    feraient échouer le test sur sa propre documentation.
    """
    import ast

    arbre = ast.parse(inspect.getsource(analytics_simulation))
    noms = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Call):
            f = noeud.func
            if isinstance(f, ast.Name):
                noms.add(f.id)
            elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                noms.add(f"{f.value.id}.{f.attr}")
    return noms


class TestGraineParDefaut:
    def test_elle_ne_depend_plus_de_l_horloge(self):
        """Le défaut exact.

        `time.time()` avançant d'une seconde suffisait à changer toute la
        projection.
        """
        appels = _appels_du_module()
        # `.time` quel que soit l'alias du module : un `import time as _t`
        # contournerait une recherche de « time.time ». Le canari l'a montré.
        horloges = {a for a in appels if a.endswith(".time") or a in {"time", "monotonic"}}

        assert not horloges, (
            f"la graine repart de l'horloge ({horloges}) : la projection " "changera de nouveau à chaque seconde"
        )

    def test_elle_ne_depend_pas_de_l_utilisateur(self):
        """`hash()` est instable d'un processus à l'autre.

        Python randomise le hachage des chaînes à chaque démarrage : deux
        processus de l'application auraient tiré des graines différentes pour
        le même utilisateur.
        """
        assert "hash" not in _appels_du_module()

    def test_elle_est_constante_et_nommee(self):
        # Sa valeur n'importe pas ; sa constance, si. Une constante nommée dit
        # l'intention mieux qu'un nombre posé au milieu du calcul.
        assert isinstance(analytics_simulation._GRAINE_PAR_DEFAUT, int)

    def test_deux_calculs_identiques_donnent_le_meme_tirage(self):
        """La propriété qui compte, éprouvée sur le générateur lui-même.

        Sans dépendance à l'horloge ni au processus, deux appels séparés dans
        le temps produisent la même suite.
        """
        import numpy as np

        graine = analytics_simulation._GRAINE_PAR_DEFAUT & 0x7FFFFFFF
        premier = np.random.default_rng(graine).standard_normal(5)
        second = np.random.default_rng(graine).standard_normal(5)

        assert np.array_equal(premier, second)

    def test_deux_projections_separees_par_une_seconde_concordent(self):
        """Le test qui prouve, là où les autres décrivent.

        Un test de forme se contourne par un alias ; celui-ci appelle la
        fonction deux fois de part et d'autre d'une frontière de seconde — la
        condition exacte qui faisait diverger l'ancienne graine. Il coûte une
        seconde d'attente, ce qui est peu pour verrouiller un chiffre que
        l'utilisateur lit comme une prévision.

        Le test de caractérisation existant ne le faisait pas : deux appels
        consécutifs tombent dans la même seconde dix-huit fois sur vingt, et il
        passait donc par chance.
        """
        import time

        import numpy as np

        entrees = dict(
            mu_vec=np.array([0.0005]),
            L=np.array([[0.04]]),
            w=np.array([1.0]),
            num_simulations=200,
            horizon_days=30,
            n_assets=1,
            user_id="utilisateur-quelconque",
            initial_portfolio_value=10000.0,
        )

        premier = analytics_simulation._monte_carlo_compute(**entrees)
        time.sleep(1.05)
        second = analytics_simulation._monte_carlo_compute(**entrees)

        assert premier.percentiles == second.percentiles

    def test_deux_scenarios_partagent_les_memes_chocs(self):
        """La propriété financière, et la raison de ne pas dériver la graine des entrées.

        C'est la technique des *nombres aléatoires communs*. Deux scénarios
        comparés — « et si j'ajoutais 1 BTC ? », ou simplement deux
        portefeuilles — doivent subir **les mêmes chocs de marché** ; leur
        différence isole alors l'effet de la décision au lieu de le noyer dans
        deux tirages distincts.

        Une graine dérivée de l'utilisateur ou de la composition détruirait
        cette propriété sans qu'aucun autre test ne s'en aperçoive : chaque
        scénario serait juste pris isolément, et toute comparaison fausse.
        """
        import numpy as np

        marche = dict(
            mu_vec=np.array([0.0005]),
            L=np.array([[0.04]]),
            w=np.array([1.0]),
            num_simulations=200,
            horizon_days=30,
            n_assets=1,
            initial_portfolio_value=10000.0,
        )

        premier = analytics_simulation._monte_carlo_compute(user_id="alice", **marche)
        second = analytics_simulation._monte_carlo_compute(user_id="bob-nom-bien-plus-long", **marche)

        assert premier.percentiles == second.percentiles, (
            "les tirages diffèrent d'un scénario à l'autre : leur comparaison "
            "mélangerait l'effet de la décision et le bruit de simulation"
        )

    def test_une_graine_explicite_reste_respectee(self):
        """Les appelants qui imposent leur graine gardent la main.

        C'est ce qui permet d'explorer plusieurs tirages quand on le veut
        vraiment — l'inverse du hasard subi.
        """
        signature = inspect.signature(analytics_simulation._monte_carlo_compute)

        assert "seed" in signature.parameters
        assert signature.parameters["seed"].default is None
